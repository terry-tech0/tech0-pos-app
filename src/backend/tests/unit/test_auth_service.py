"""AuthService の単体テスト。

対応: テスト仕様書 01-単体テスト-backend-pytest.md（UT-BE-060〜075）／設計 §8.1・§8.2

DBは使わない。CashierRepository を偽物（スタブ）に差し替えてクラス単体で確かめる。

ここで使うパスワードは**この単体テストの中だけの文字列**で、
どこにも保存されず、DBにも入らない（fixtures のパスワードは環境変数から読む別の仕組み）。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import Settings
from app.enums import Role
from app.errors import AppError, ErrorCode
from app.models import Cashier
from app.services.auth_service import (
    AuthService,
    LoginAttemptLimiter,
    hash_password,
    verify_password,
)

# 単体テスト専用の文字列（8〜72バイトの範囲内）
UNIT_TEST_PASSWORD = "unit-test-pass-0001"


class StubCashierRepository:
    """CashierRepository の代わり。DBに触らない。"""

    def __init__(self, cashiers: list[Cashier] | None = None) -> None:
        self._cashiers = cashiers or []

    def find_by_login_id(self, login_id: str) -> Cashier | None:
        for cashier in self._cashiers:
            if cashier.login_id == login_id:
                return cashier
        return None

    def find_by_id(self, cashier_id: int) -> Cashier | None:
        for cashier in self._cashiers:
            if cashier.cashier_id == cashier_id:
                return cashier
        return None


def make_cashier(
    *,
    cashier_id: int = 1,
    login_id: str = "cashier01",
    password: str = UNIT_TEST_PASSWORD,
    role: Role = Role.CASHIER,
    is_active: bool = True,
) -> Cashier:
    return Cashier(
        cashier_id=cashier_id,
        login_id=login_id,
        cashier_name="架空担当",
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings()


class TestPasswordHash:
    """パスワードのハッシュ。設計 §8.1 S-1（NFR-SEC-02）。"""

    def test_ut_be_060_hash_is_not_plaintext(self) -> None:
        """平文がそのまま保存されない。"""
        hashed = hash_password(UNIT_TEST_PASSWORD)
        assert UNIT_TEST_PASSWORD not in hashed

    def test_ut_be_061_hash_is_bcrypt_60_chars(self) -> None:
        """bcrypt のハッシュは60文字（DBの CHAR(60) と一致する）。"""
        hashed = hash_password(UNIT_TEST_PASSWORD)
        assert len(hashed) == 60
        assert hashed.startswith("$2b$12$")  # コスト係数12（設計 §8.1 S-1）

    def test_ut_be_062_same_password_different_hash(self) -> None:
        """同じパスワードでも毎回違うハッシュになる（ソルトが効いている）。"""
        assert hash_password(UNIT_TEST_PASSWORD) != hash_password(UNIT_TEST_PASSWORD)

    def test_ut_be_063_verify_roundtrip(self) -> None:
        """正しいパスワードは通り、違うパスワードは通らない。"""
        hashed = hash_password(UNIT_TEST_PASSWORD)
        assert verify_password(UNIT_TEST_PASSWORD, hashed) is True
        assert verify_password(UNIT_TEST_PASSWORD + "x", hashed) is False

    def test_broken_hash_returns_false_not_exception(self) -> None:
        """ハッシュが壊れていても例外を外に出さない（E-AUTH-001 に丸める）。"""
        assert verify_password(UNIT_TEST_PASSWORD, "not-a-bcrypt-hash") is False


class TestAuthenticate:
    """パスワード照合。設計 §8.1・§7.2 ER-4。"""

    def test_success(self, settings: Settings) -> None:
        cashier = make_cashier()
        service = AuthService(StubCashierRepository([cashier]), settings)
        assert service.authenticate("cashier01", UNIT_TEST_PASSWORD) is cashier

    def test_wrong_password_is_auth_001(self, settings: Settings) -> None:
        service = AuthService(StubCashierRepository([make_cashier()]), settings)
        with pytest.raises(AppError) as exc:
            service.authenticate("cashier01", "wrong-password-0001")
        assert exc.value.code == ErrorCode.AUTH_FAILED

    def test_unknown_id_is_same_error(self, settings: Settings) -> None:
        """★IDが存在しない場合も同じ E-AUTH-001（設計 §7.2 ER-4）。

        「そのIDは存在します」と教えると、有効なIDの洗い出しに使われる。
        """
        service = AuthService(StubCashierRepository([make_cashier()]), settings)
        with pytest.raises(AppError) as exc:
            service.authenticate("nosuchuser", UNIT_TEST_PASSWORD)
        assert exc.value.code == ErrorCode.AUTH_FAILED

    def test_it_008_inactive_cashier_cannot_login(self, settings: Settings) -> None:
        """IT-008 退職者はパスワードが正しくてもログインできない。"""
        cashier = make_cashier(login_id="retired01", is_active=False)
        service = AuthService(StubCashierRepository([cashier]), settings)
        with pytest.raises(AppError) as exc:
            service.authenticate("retired01", UNIT_TEST_PASSWORD)
        assert exc.value.code == ErrorCode.AUTH_FAILED


class TestLoginAttemptLimiter:
    """連続失敗の制限。設計 §8.1 S-4。"""

    def test_locks_after_max_attempts(self) -> None:
        limiter = LoginAttemptLimiter(max_attempts=3, lockout_seconds=60)
        assert limiter.is_locked("cashier01") is False
        for _ in range(3):
            limiter.record_failure("cashier01")
        assert limiter.is_locked("cashier01") is True

    def test_success_resets_counter(self) -> None:
        limiter = LoginAttemptLimiter(max_attempts=3, lockout_seconds=60)
        limiter.record_failure("cashier01")
        limiter.record_failure("cashier01")
        limiter.reset("cashier01")
        limiter.record_failure("cashier01")
        assert limiter.is_locked("cashier01") is False

    def test_lock_expires(self) -> None:
        """ロック期間が過ぎたら受け付ける。"""
        limiter = LoginAttemptLimiter(max_attempts=1, lockout_seconds=0)
        limiter.record_failure("cashier01")
        time.sleep(0.01)
        assert limiter.is_locked("cashier01") is False

    def test_locked_user_rejected_even_with_correct_password(self, settings: Settings) -> None:
        limiter = LoginAttemptLimiter(max_attempts=1, lockout_seconds=60)
        service = AuthService(StubCashierRepository([make_cashier()]), settings, limiter)
        with pytest.raises(AppError):
            service.authenticate("cashier01", "wrong-password-0001")
        # ロック中は正しいパスワードでも通さない
        with pytest.raises(AppError) as exc:
            service.authenticate("cashier01", UNIT_TEST_PASSWORD)
        assert exc.value.code == ErrorCode.AUTH_FAILED

    def test_lock_is_per_login_id(self, settings: Settings) -> None:
        """あるIDのロックが他のIDに波及しない（レジが全部止まると困る）。"""
        limiter = LoginAttemptLimiter(max_attempts=1, lockout_seconds=60)
        other = make_cashier(cashier_id=2, login_id="cashier02")
        service = AuthService(
            StubCashierRepository([make_cashier(), other]), settings, limiter
        )
        with pytest.raises(AppError):
            service.authenticate("cashier01", "wrong-password-0001")
        assert service.authenticate("cashier02", UNIT_TEST_PASSWORD) is other


class TestJwt:
    """JWT の発行と検証。設計 §8.2。"""

    def test_issue_and_verify(self, settings: Settings) -> None:
        cashier = make_cashier(cashier_id=7, role=Role.MANAGER)
        service = AuthService(StubCashierRepository([cashier]), settings)
        payload = service.verify_token(service.issue_token(cashier))
        assert payload.cashier_id == 7
        assert payload.role == Role.MANAGER

    def test_ut_be_064_no_personal_info_in_payload(self, settings: Settings) -> None:
        """★ペイロードに氏名などの個人情報を入れない（設計 §8.2）。

        JWT は署名されているだけで、中身は誰でも読める（暗号化ではない）。
        """
        cashier = make_cashier()
        service = AuthService(StubCashierRepository([cashier]), settings)
        token = service.issue_token(cashier)
        # 署名を検証せずにデコードしても、氏名が読めないこと
        claims = jwt.decode(token, options={"verify_signature": False})
        assert set(claims) == {"sub", "role", "iat", "exp", "iss"}
        assert "架空担当" not in token

    def test_expired_token_is_auth_002(self, settings: Settings) -> None:
        """期限切れは E-AUTH-002。"""
        expired = jwt.encode(
            {
                "sub": "1",
                "role": "CASHIER",
                "iat": int((datetime.now(timezone.utc) - timedelta(hours=9)).timestamp()),
                "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
                "iss": settings.jwt_issuer,
            },
            settings.jwt_secret_key,
            algorithm="HS256",
        )
        service = AuthService(StubCashierRepository(), settings)
        with pytest.raises(AppError) as exc:
            service.verify_token(expired)
        assert exc.value.code == ErrorCode.AUTH_EXPIRED

    def test_tampered_signature_is_rejected(self, settings: Settings) -> None:
        """別の鍵で署名したトークンは通らない。"""
        forged = jwt.encode(
            {
                "sub": "1",
                "role": "MANAGER",
                "iat": int(datetime.now(timezone.utc).timestamp()),
                "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                "iss": settings.jwt_issuer,
            },
            "attacker-key-not-the-real-secret",
            algorithm="HS256",
        )
        service = AuthService(StubCashierRepository(), settings)
        with pytest.raises(AppError) as exc:
            service.verify_token(forged)
        assert exc.value.code == ErrorCode.AUTH_EXPIRED

    def test_ut_be_065_alg_none_is_rejected(self, settings: Settings) -> None:
        """★alg:none（署名なし）のトークンを通さない（設計 §8.2）。

        検証時に algorithms を明示しているかを確かめるテスト。
        指定を省くと、攻撃者が署名方式を差し替えたトークンを通せる余地が生まれる。
        """
        unsigned = jwt.encode(
            {
                "sub": "1",
                "role": "MANAGER",
                "iat": int(datetime.now(timezone.utc).timestamp()),
                "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                "iss": settings.jwt_issuer,
            },
            key="",
            algorithm="none",
        )
        service = AuthService(StubCashierRepository(), settings)
        with pytest.raises(AppError):
            service.verify_token(unsigned)

    def test_wrong_issuer_is_rejected(self, settings: Settings) -> None:
        """発行者（iss）が違うトークンは通らない。"""
        other = jwt.encode(
            {
                "sub": "1",
                "role": "CASHIER",
                "iat": int(datetime.now(timezone.utc).timestamp()),
                "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                "iss": "someone-else",
            },
            settings.jwt_secret_key,
            algorithm="HS256",
        )
        service = AuthService(StubCashierRepository(), settings)
        with pytest.raises(AppError):
            service.verify_token(other)

    def test_garbage_token_is_rejected(self, settings: Settings) -> None:
        service = AuthService(StubCashierRepository(), settings)
        with pytest.raises(AppError):
            service.verify_token("not-a-jwt-at-all")
