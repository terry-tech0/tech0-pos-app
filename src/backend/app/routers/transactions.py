"""購入確定API。設計仕様書 §5.2 B-06。

**金額の再計算・照合・保存**を行う唯一の入口（設計 §8.6）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.deps import get_checkout_service, get_current_payload
from app.schemas.pos import CheckoutRequest, CheckoutResponse, TokenPayload
from app.services import CheckoutService

router = APIRouter(tags=["transactions"])


@router.post(
    "/transactions",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    body: CheckoutRequest,
    response: Response,
    payload: TokenPayload = Depends(get_current_payload),
    checkout: CheckoutService = Depends(get_checkout_service),
) -> CheckoutResponse:
    """B-06 購入を確定し、購入履歴を保存する。

    担当は **JWT の sub から決める**。リクエストの cashier_id は受け取らない
    （スキーマに定義していないので、送られても無視される。設計 §5.4 A-07）。

    新規に保存したら 201、同じ整理番号の取引が保存済みなら 200 でそれを返す（設計 v1.1 D-7）。
    """
    result, created = checkout.confirm(body, cashier_id=payload.cashier_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result
