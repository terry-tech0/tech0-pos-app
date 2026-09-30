"""認証。設計仕様書 §8.1 認証・§8.2 JWT。

パスワードのハッシュに passlib を使わない判断をしている（設計 §8.10）。
passlib の最終リリースが 2020-10-08 でメンテが止まっているため、bcrypt を直接使う。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import Settings
from app.enums import Role
from app.errors import AppError, ErrorCode
from app.models import Cashier
from app.repositories import CashierRepository
from app.schemas.pos import TokenPayload

# bcrypt のコスト係数。設計 §8.1 S-1
BCRYPT_ROUNDS = 12

# IDが存在しないときにも照合するダミーハッシュ。設計 §8.1 S-2。
# 起動時に1度だけ作る。これと照合することで、IDの有無で応答時間が変わらなくなる
# （応答時間の差から有効なIDを推測されるのを防ぐ）。
_DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def hash_password(plain: str) -> str:
    """平文パスワードを bcrypt ハッシュにする。保存するのはこれだけ（NFR-SEC-02）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    """平文とハッシュを照合する。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        # ハッシュの形式が壊れている（bcrypt 形式でない）場合。
        # 例外を外に投げず False にして、E-AUTH-001 に丸める
        return False


@dataclass
class _Attempt:
    """ログイン失敗の記録。"""

    count: int = 0
    locked_until: float = 0.0


class LoginAttemptLimiter:
    """連続失敗の制限。設計 §8.1 S-4。

    **アプリのメモリ上のカウンタという簡易実装**で、インスタンスが増えると効かない。
    設計書でその弱点を承知の上で採用している（恒久策は Lv3 候補）。
    """

    def __init__(self, max_attempts: int, lockout_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._attempts: dict[str, _Attempt] = {}

    def is_locked(self, login_id: str) -> bool:
        attempt = self._attempts.get(login_id)
        if attempt is None:
            return False
        if attempt.locked_until and time.monotonic() < attempt.locked_until:
            return True
        # ロック期間が過ぎたら忘れる
        if attempt.locked_until:
            self._attempts.pop(login_id, None)
        return False

    def record_failure(self, login_id: str) -> None:
        attempt = self._attempts.setdefault(login_id, _Attempt())
        attempt.count += 1
        if attempt.count >= self._max_attempts:
            attempt.locked_until = time.monotonic() + self._lockout_seconds

    def reset(self, login_id: str) -> None:
        """成功したら失敗の記録を消す。"""
        self._attempts.pop(login_id, None)


class AuthService:
    """パスワード照合とJWTの発行・検証。クラス図 AuthService。"""

    def __init__(
        self,
        cashiers: CashierRepository,
        settings: Settings,
        limiter: LoginAttemptLimiter | None = None,
    ) -> None:
        self._cashiers = cashiers
        self._settings = settings
        self._limiter = limiter

    def authenticate(self, login_id: str, password: str) -> Cashier:
        """ログインIDとパスワードを照合する。

        失敗理由を区別して返さない（設計 §7.2 ER-4）。
        「そのIDは存在します」と教えると、有効なIDの洗い出しに使われる。
        IDが無い／パスワード違い／退職者、どれも E-AUTH-001 に統一する。

        Raises:
            AppError: E-AUTH-001（照合失敗、または連続失敗による一時ロック中）
        """
        if self._limiter is not None and self._limiter.is_locked(login_id):
            raise AppError(ErrorCode.AUTH_FAILED)

        cashier = self._cashiers.find_by_login_id(login_id)

        # IDが無い場合もダミーハッシュと照合して、同じ時間をかける（S-2）
        if cashier is None:
            bcrypt.checkpw(password.encode("utf-8"), _DUMMY_HASH)
            self._record_failure(login_id)
            raise AppError(ErrorCode.AUTH_FAILED)

        if not verify_password(password, cashier.password_hash):
            self._record_failure(login_id)
            raise AppError(ErrorCode.AUTH_FAILED)

        # 退職者はログインできない（IT-008）。パスワードが正しくても通さない
        if not cashier.is_active:
            self._record_failure(login_id)
            raise AppError(ErrorCode.AUTH_FAILED)

        if self._limiter is not None:
            self._limiter.reset(login_id)
        return cashier

    def _record_failure(self, login_id: str) -> None:
        if self._limiter is not None:
            self._limiter.record_failure(login_id)

    def issue_token(self, cashier: Cashier) -> str:
        """JWT を発行する。設計 §8.2。

        ペイロードに入れるのは sub / role / iat / exp / iss だけ。
        **氏名や個人情報は入れない**。JWT は署名されているだけで、中身は誰でも読める。
        """
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(cashier.cashier_id),
            "role": Role(cashier.role).value,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._settings.jwt_expire_minutes)).timestamp()),
            "iss": self._settings.jwt_issuer,
        }
        return jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)

    def verify_token(self, token: str) -> TokenPayload:
        """JWT を検証してペイロードを返す。

        **algorithms を明示する**のが要点（設計 §8.2）。
        指定を省くと、攻撃者が alg: none や別方式に差し替えたトークンを通せる余地が生まれる。

        Raises:
            AppError: E-AUTH-002（期限切れ・署名不正・改ざん）
        """
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret_key,
                algorithms=[self._settings.jwt_algorithm],  # ここを省略しない
                issuer=self._settings.jwt_issuer,
                options={"require": ["sub", "exp", "iat", "iss"]},
            )
        except jwt.PyJWTError:
            # 期限切れも改ざんも同じ扱いにする。理由を細かく返す必要がない
            raise AppError(ErrorCode.AUTH_EXPIRED) from None
        return TokenPayload(**claims)
