"""Pydantic のスキーマ。設計仕様書 §5.5 型定義。

同じ形をフロント（TypeScript の types/pos.ts）でも宣言する。
片側だけだと、勘違いが実行時まで見つからない（設計 §8.9 型定義による二重防御）。

命名は snake_case。BFF⇄バックエンドの境界は snake_case で、
camelCase への変換は BFF の責務（設計 §5.3）。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.enums import Role, TaxCategory

# ── 制約つきの型。設計 §6 入力値の下限・上限がここの正 ──
# Pydantic v2 の書き方。設計書の constr(pattern=...) と同じものを Annotated で表す。

# JAN は8桁または13桁のどちらかのみ。あいだの9〜12桁は無効。
# 「8以上13以下」と書くと10桁が通ってしまうので、正規表現で2択にする。
# ★\d ではなく [0-9] を使う: Python の \d は全角数字（０-９）にもマッチするため、
#   \d のままだと全角の商品コードが通ってしまう。JavaScript の \d は半角のみなので、
#   画面（lib/validation.ts）とサーバで判定が食い違う原因になる。
# ★整数には strict=True を付ける: 既定の緩いモードでは文字列 "3" が 3 に変換される
ProductCode = Annotated[str, StringConstraints(pattern=r"^([0-9]{8}|[0-9]{13})$")]
MemberCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{10}$")]
LoginId = Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z]{4,20}$")]
ProductName = Annotated[str, StringConstraints(min_length=1, max_length=100)]
UnitPrice = Annotated[int, Field(ge=0, le=999_999, strict=True)]
Quantity = Annotated[int, Field(ge=1, le=99, strict=True)]
Yen = Annotated[int, Field(ge=0, le=9_999_999, strict=True)]


# ── 認証 ──

class LoginRequest(BaseModel):
    login_id: LoginId
    password: str

    @field_validator("password")
    @classmethod
    def _check_password_length(cls, value: str) -> str:
        """8〜72バイト。設計 §6。

        bcrypt は72バイトを超える部分を無視するため、上限を仕様として明示する。
        「文字数」ではなく「バイト数」で数えるのが要点（日本語1文字は3バイト）。
        """
        length = len(value.encode("utf-8"))
        if not 8 <= length <= 72:
            raise ValueError("パスワードは8〜72バイトです")
        return value


class TokenResponse(BaseModel):
    """B-01 /auth/token の応答。

    ここではトークンを返す。**BFF（A-01）はこれをボディに載せず Cookie に詰め替える**
    （設計 §5.4 A-01「トークン本体はレスポンスボディに含めない」）。
    ブラウザに返る形とバックエンドが返す形は別物。
    """

    access_token: str
    cashier_id: int
    cashier_name: str
    role: Role


class MeResponse(BaseModel):
    """B-02 /auth/me の応答。画面ヘッダ表示・再読込時の復帰用。"""

    cashier_id: int
    cashier_name: str
    role: Role


class TokenPayload(BaseModel):
    """JWT のペイロード。設計 §8.2。

    氏名などの個人情報は入れない。JWT は署名されているだけで、中身は誰でも読める。
    """

    sub: str          # 担当ID（cashier_id を文字列にしたもの）
    role: Role
    iat: int
    exp: int
    iss: str

    @property
    def cashier_id(self) -> int:
        return int(self.sub)


# ── 照会 ──

class MemberOut(BaseModel):
    """B-03 /members/{member_code} の応答。

    割引区分そのものではなく「割引対象か」を返す。
    画面に割引の内部区分（RATE5 等）を知らせる必要がない。
    """

    member_code: MemberCode
    member_name: str
    is_discount_target: bool


class ProductOut(BaseModel):
    """B-04 /products/{product_code} の応答。有効な税率を結合して返す。"""

    product_code: ProductCode
    product_name: ProductName
    unit_price: UnitPrice
    tax_category: TaxCategory
    tax_rate: Decimal


class TaxRateOut(BaseModel):
    """B-05 /tax-rates の応答。画面の表示用計算に使う。"""

    tax_category: TaxCategory
    rate: Decimal
    valid_from: date
    valid_to: Optional[date] = None


# ── 購入確定 ──

class Amount(BaseModel):
    """金額の5項目。購入確定時にこの5つすべてを照合する（設計 §8.6 手順4）。"""

    subtotal: Yen
    discount: Yen
    tax_reduced: Yen
    tax_standard: Yen
    total: Yen


class CheckoutLineIn(BaseModel):
    """確定リクエストの明細1行。

    **単価も税率も受け取らない。** サーバがマスタから引き直す（設計 §5.4 A-07）。
    スキーマに無い項目は送られてきても無視されるので、
    「送られた単価を使ってしまう」事故が型の形として起こりえなくなる。
    """

    product_code: ProductCode
    quantity: Quantity


class CheckoutRequest(BaseModel):
    """B-06 POST /transactions のリクエスト。

    cashier_id を**定義していない**のが要点。担当は JWT の sub から決める（詐称防止）。
    """

    member_code: Optional[MemberCode] = None
    # 1〜100行。0件は E-TXN-002、101行以上は E-VAL-003
    lines: list[CheckoutLineIn] = Field(min_length=1, max_length=100)
    # 画面が計算した金額。照合のみに使い、**保存しない**
    client_amount: Amount


class ConfirmedLine(BaseModel):
    """確定した明細。レシート表示用に商品名・単価・行金額を返す。"""

    line_no: int
    product_code: ProductCode
    product_name: ProductName
    unit_price: UnitPrice
    quantity: Quantity
    tax_category: TaxCategory
    applied_tax_rate: Decimal
    line_amount: int


class CheckoutResponse(BaseModel):
    """B-06 の応答。amount は**サーバが計算した確定金額**。"""

    transaction_id: int
    transacted_at: datetime
    amount: Amount
    lines: list[ConfirmedLine]
