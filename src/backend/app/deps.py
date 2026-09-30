"""FastAPI の依存関数。認証・認可とサービスの組み立てをここに集める。

設計仕様書 §8.3 認可。**判定は必ずサーバ側**に置く。
画面でボタンを隠すのは操作性のためで、APIを直接叩かれれば無意味。
"""

from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.enums import Role
from app.errors import AppError, ErrorCode
from app.repositories import (
    CashierRepository,
    MemberRepository,
    ProductRepository,
    TaxRateRepository,
    TransactionRepository,
)
from app.schemas.pos import TokenPayload
from app.services import AuthService, CheckoutService, LoginAttemptLimiter

# ログイン連続失敗のカウンタ。プロセス内で1つだけ持つ（設計 §8.1 S-4）。
# インスタンスが増えると効かない簡易実装であることは設計書に明記済み。
_limiter: LoginAttemptLimiter | None = None


def get_limiter(settings: Settings = Depends(get_settings)) -> LoginAttemptLimiter:
    global _limiter
    if _limiter is None:
        _limiter = LoginAttemptLimiter(
            max_attempts=settings.login_max_attempts,
            lockout_seconds=settings.login_lockout_seconds,
        )
    return _limiter


def get_auth_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limiter: LoginAttemptLimiter = Depends(get_limiter),
) -> AuthService:
    return AuthService(CashierRepository(session), settings, limiter)


def get_checkout_service(session: Session = Depends(get_db)) -> CheckoutService:
    return CheckoutService(
        products=ProductRepository(session),
        members=MemberRepository(session),
        tax_rates=TaxRateRepository(session),
        transactions=TransactionRepository(session),
    )


def get_member_repository(session: Session = Depends(get_db)) -> MemberRepository:
    return MemberRepository(session)


def get_product_repository(session: Session = Depends(get_db)) -> ProductRepository:
    return ProductRepository(session)


def get_tax_rate_repository(session: Session = Depends(get_db)) -> TaxRateRepository:
    return TaxRateRepository(session)


def _extract_bearer_token(request: Request) -> str:
    """Authorization ヘッダから Bearer トークンを取り出す。

    BFF⇄バックエンドの認証は Bearer（設計 §5.3）。
    ヘッダが無い・形式が違う場合も E-AUTH-002 に統一する。
    「ヘッダが無い」と「トークンが無効」を区別して教える必要がない。
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AppError(ErrorCode.AUTH_EXPIRED)
    return token.strip()


def get_current_payload(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
) -> TokenPayload:
    """JWT を検証してペイロードを返す。認証必須のAPIはすべてこれを通す（S-5）。"""
    return auth.verify_token(_extract_bearer_token(request))


def require_role(*allowed: Role):
    """ロールを判定する依存関数。設計 §8.3 のコード例をそのまま実装。"""

    def _dep(payload: TokenPayload = Depends(get_current_payload)) -> TokenPayload:
        if Role(payload.role) not in allowed:
            raise AppError(ErrorCode.AUTH_FORBIDDEN)
        return payload

    return _dep


def db_session() -> Iterator[Session]:
    """テストから差し替えられるようにしておくための別名。"""
    yield from get_db()
