"""認証API。設計仕様書 §5.2 B-01 / B-02。

このAPIを直接呼ぶのは BFF だけ。ブラウザは呼ばない（原則 P-2）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_auth_service, get_current_payload
from app.errors import AppError, ErrorCode
from app.repositories import CashierRepository
from app.schemas.pos import LoginRequest, MeResponse, TokenPayload, TokenResponse
from app.services import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/token", response_model=TokenResponse)
def issue_token(
    body: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """B-01 パスワード照合とJWT発行。

    ここではトークンをボディで返す。**BFF がこれを httpOnly Cookie に詰め替え、
    ブラウザにはトークンを渡さない**（設計 §5.4 A-01）。

    失敗はすべて E-AUTH-001。IDが無いのかパスワードが違うのかは区別しない（ER-4）。
    """
    cashier = auth.authenticate(body.login_id, body.password)
    return TokenResponse(
        access_token=auth.issue_token(cashier),
        cashier_id=cashier.cashier_id,
        cashier_name=cashier.cashier_name,
        role=cashier.role,
    )


@router.get("/auth/me", response_model=MeResponse)
def read_me(
    payload: TokenPayload = Depends(get_current_payload),
    session: Session = Depends(get_db),
) -> MeResponse:
    """B-02 ログイン中の担当者名・ロールを返す。画面ヘッダ表示と再読込時の復帰用。

    氏名はJWTに入れていない（設計 §8.2）ので、ここでDBから引く。
    """
    cashier = CashierRepository(session).find_by_id(payload.cashier_id)
    if cashier is None or not cashier.is_active:
        # トークンは有効だが、担当が無効化された（退職処理された）場合。再ログインさせる
        raise AppError(ErrorCode.AUTH_EXPIRED)
    return MeResponse(
        cashier_id=cashier.cashier_id,
        cashier_name=cashier.cashier_name,
        role=cashier.role,
    )
