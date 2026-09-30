"""マスタ照会API。設計仕様書 §5.2 B-03（会員）／B-04（商品）／B-05（税率）。

いずれも認証必須（設計 §8.1 S-5）。会計に関わる全APIを認証の背後に置く。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends

from app.deps import (
    get_current_payload,
    get_member_repository,
    get_product_repository,
    get_tax_rate_repository,
)
from app.enums import TaxCategory
from app.errors import AppError, ErrorCode
from app.repositories import MemberRepository, ProductRepository, TaxRateRepository
from app.schemas.pos import MemberOut, ProductOut, TaxRateOut

router = APIRouter(tags=["catalog"], dependencies=[Depends(get_current_payload)])


@router.get("/members/{member_code}", response_model=MemberOut)
def read_member(
    member_code: str,
    members: MemberRepository = Depends(get_member_repository),
) -> MemberOut:
    """B-03 会員を照会する。

    桁数・文字種の検証はここで行う。数字10桁でなければDBに問い合わせない
    （設計 §6「桁が違う時点で照会しない」）。
    """
    if not _is_member_code(member_code):
        raise AppError(ErrorCode.VAL_FORMAT, {"memberCode": member_code})

    member = members.find_by_code(member_code)
    if member is None:
        # 未登録・退会済みのどちらも「見つからない」に統一する。
        # 画面は「非会員として続行」を選べるので、会計は止まらない（設計 §7.1 E-MEMB-001）
        raise AppError(ErrorCode.MEMBER_NOT_FOUND, {"memberCode": member_code})

    return MemberOut(
        member_code=member.member_code,
        member_name=member.member_name,
        is_discount_target=member.is_discount_target(),
    )


@router.get("/products/{product_code}", response_model=ProductOut)
def read_product(
    product_code: str,
    products: ProductRepository = Depends(get_product_repository),
    tax_rates: TaxRateRepository = Depends(get_tax_rate_repository),
) -> ProductOut:
    """B-04 商品を照会し、現在有効な税率を結合して返す。

    未登録と取扱終了を区別しない（設計 §5.4 A-05）。
    レジ担当の対応はどちらも「店長へ連絡」で同じため。
    """
    if not _is_product_code(product_code):
        # 数字以外を通さないことが、SQLインジェクション対策の一段目にもなる（設計 §8.8）
        raise AppError(ErrorCode.VAL_FORMAT, {"productCode": product_code})

    product = products.find_by_code(product_code)
    if product is None:
        raise AppError(ErrorCode.PRODUCT_NOT_FOUND, {"productCode": product_code})

    rates = tax_rates.rates_only(date.today())
    category = TaxCategory(product.tax_category)
    if category not in rates:
        # 税率マスタに現行行が無い＝サーバ側の設定不備
        raise AppError(ErrorCode.SYS_UNEXPECTED)

    return ProductOut(
        product_code=product.product_code,
        product_name=product.product_name,
        unit_price=product.unit_price,
        tax_category=category,
        tax_rate=Decimal(rates[category]),
    )


@router.get("/tax-rates", response_model=list[TaxRateOut])
def read_tax_rates(
    tax_rates: TaxRateRepository = Depends(get_tax_rate_repository),
) -> list[TaxRateOut]:
    """B-05 現在有効な税率一覧。画面の表示用計算に使う（F-08 / F-12）。

    画面はこれを使って計算するので、税率マスタに行を追加するだけで
    画面の計算も追従する（REQ-08 / NFR-OPS-04）。
    """
    effective = tax_rates.find_effective(date.today())
    return [
        TaxRateOut(
            tax_category=category,
            rate=Decimal(row.rate),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
        )
        for category, row in sorted(effective.items(), key=lambda item: item[0].value)
    ]


def _is_member_code(value: str) -> bool:
    """数字10桁か。"""
    return len(value) == 10 and value.isdecimal() and value.isascii()


def _is_product_code(value: str) -> bool:
    """JAN（数字8桁または13桁）か。

    あいだの9〜12桁は無効。「8以上13以下」と書くと10桁が通ってしまう（設計 §6）。
    """
    return len(value) in (8, 13) and value.isdecimal() and value.isascii()

