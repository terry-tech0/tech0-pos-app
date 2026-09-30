"""会計の司令塔。設計仕様書 §8.6 金額のバックエンド再計算と照合。

原則 P-1 の実装。**金額はバックエンドが正**で、画面の計算値は照合にしか使わない。
この節が課題「Backendでも計算のロジックを入れて、Frontendの計算値と照合」への直接の回答。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.enums import TaxCategory
from app.errors import AppError, ErrorCode
from app.models import Transaction, TransactionLine
from app.repositories import (
    DuplicateCheckoutError,
    MemberRepository,
    ProductRepository,
    TaxRateRepository,
    TransactionRepository,
)
from app.schemas.pos import Amount, CheckoutRequest, CheckoutResponse, ConfirmedLine
from app.services.amount_calculator import AmountCalculator, AmountSummary, CalcLine

# 日本時間。設計 §5.3 日時形式（ISO 8601・日本時間オフセット付き）
JST = timezone(timedelta(hours=9))

# 金額の上限。設計 §6。確認事項 T-3 の決定: 超過は E-VAL-001（入力値違反として扱う）
YEN_MAX = 9_999_999


class CheckoutService:
    """会計の司令塔。クラス図 CheckoutService。

    金額の再計算・照合・保存をまとめる。計算そのものは AmountCalculator に委ねる
    （計算の実装を2か所に分けないため）。
    """

    def __init__(
        self,
        products: ProductRepository,
        members: MemberRepository,
        tax_rates: TaxRateRepository,
        transactions: TransactionRepository,
        calculator: AmountCalculator | None = None,
    ) -> None:
        self._products = products
        self._members = members
        self._tax_rates = tax_rates
        self._transactions = transactions
        self._calculator = calculator or AmountCalculator()

    def confirm(self, request: CheckoutRequest, cashier_id: int) -> tuple[CheckoutResponse, bool]:
        """購入を確定して購入履歴を保存する。設計 §8.6 の手順1〜6。

        Args:
            request: 画面から来た確定要求。**単価も税率も担当IDも含まれない**
            cashier_id: JWT の sub から確定した担当。リクエストからは受け取らない

        Returns:
            (応答, 新規に保存したか)。同じ整理番号の取引が保存済みなら、
            保存せずにその取引を返し、2つ目は False になる（設計 v1.1 D-7）

        Raises:
            AppError: E-PROD-001（未登録商品）／E-MEMB-001（会員なし）／
                E-TXN-001（金額照合の不一致）／E-VAL-001（金額が上限超過）
        """
        # 二重送信: 同じ整理番号の取引が保存済みなら、何もせずにそれを返す。
        # 再計算もしない（その間に税率やマスタが変わっていても、保存済みの事実を返す）
        existing = self._transactions.find_by_checkout_id(request.checkout_id)
        if existing is not None:
            return to_response(existing), False

        transacted_at = datetime.now(JST)

        # 手順2: 単価・税率・会員割引区分をマスタから引き直す。
        # 画面から送られた単価や税率はスキーマに存在しないので、使うことができない
        products = self._products.find_many_by_codes(
            [line.product_code for line in request.lines]
        )
        missing = [
            line.product_code for line in request.lines if line.product_code not in products
        ]
        if missing:
            raise AppError(ErrorCode.PRODUCT_NOT_FOUND, {"productCodes": sorted(set(missing))})

        is_member = False
        if request.member_code is not None:
            member = self._members.find_by_code(request.member_code)
            if member is None:
                raise AppError(ErrorCode.MEMBER_NOT_FOUND, {"memberCode": request.member_code})
            is_member = member.is_discount_target()

        rates = self._tax_rates.rates_only(transacted_at.date())

        calc_lines: list[CalcLine] = []
        for line in request.lines:
            product = products[line.product_code]
            category = TaxCategory(product.tax_category)
            if category not in rates:
                # 税率マスタに現行行が無い＝サーバ側の設定不備。入力のせいではない
                raise AppError(ErrorCode.SYS_UNEXPECTED)
            calc_lines.append(
                CalcLine(
                    unit_price=product.unit_price,
                    quantity=line.quantity,
                    tax_category=category,
                )
            )

        # 手順3: サーバ側で §4.4 の手順どおりに計算し直す
        server_amount = self._calculator.calculate(calc_lines, is_member, rates)

        # 確認事項 T-3: 合計が上限を超えたら入力値違反として弾く
        if server_amount.subtotal > YEN_MAX or server_amount.total > YEN_MAX:
            raise AppError(
                ErrorCode.VAL_FORMAT,
                {
                    "limit": YEN_MAX,
                    "subtotal": server_amount.subtotal,
                    "total": server_amount.total,
                },
            )

        # 手順4・5: 5項目すべてを照合。1つでも違えば保存しない
        self._verify_amount(request.client_amount, server_amount)

        # 手順6: 保存するのはサーバの計算値だけ。client_amount はどこにも保存しない
        lines_to_save: list[TransactionLine] = []
        confirmed_lines: list[ConfirmedLine] = []
        for line_no, line in enumerate(request.lines, start=1):
            product = products[line.product_code]
            category = TaxCategory(product.tax_category)
            applied_rate = Decimal(rates[category])
            line_amount = product.unit_price * line.quantity
            # 商品名・単価・税率区分・適用税率を購入時点の値で転記する（原則 P-3 / D-1）
            lines_to_save.append(
                TransactionLine(
                    line_no=line_no,
                    product_code=product.product_code,
                    product_name=product.product_name,
                    unit_price=product.unit_price,
                    quantity=line.quantity,
                    tax_category=category,
                    applied_tax_rate=applied_rate,
                    line_amount=line_amount,
                )
            )
            confirmed_lines.append(
                ConfirmedLine(
                    line_no=line_no,
                    product_code=product.product_code,
                    product_name=product.product_name,
                    unit_price=product.unit_price,
                    quantity=line.quantity,
                    tax_category=category,
                    applied_tax_rate=applied_rate,
                    line_amount=line_amount,
                )
            )

        try:
            transaction = self._transactions.save(
                checkout_id=request.checkout_id,
                # DBは naive datetime で持つので、JST のまま tzinfo を外して渡す
                transacted_at=transacted_at.replace(tzinfo=None),
                cashier_id=cashier_id,
                member_code=request.member_code,
                subtotal=server_amount.subtotal,
                discount_amount=server_amount.discount,
                tax_reduced=server_amount.tax_reduced,
                tax_standard=server_amount.tax_standard,
                total=server_amount.total,
                lines=lines_to_save,
            )
        except DuplicateCheckoutError:
            # 上の判定とこの保存の間に、同じ会計が先に保存された（ほぼ同時の二重送信）
            existing = self._transactions.find_by_checkout_id(request.checkout_id)
            assert existing is not None
            return to_response(existing), False

        return (
            CheckoutResponse(
                transaction_id=transaction.transaction_id,
                transacted_at=transacted_at,
                amount=to_amount(server_amount),
                lines=confirmed_lines,
            ),
            True,
        )

    @staticmethod
    def _verify_amount(client: Amount, server: AmountSummary) -> None:
        """画面の計算値とサーバの計算値を照合する。設計 §8.6 手順4。

        5項目すべてが一致しなければ拒否する。1項目でも一致を免除すると、
        そこが改ざんの通り道になる。

        E-TXN-001 にはサーバ計算値を添えて返す（設計 §7.2 ER-5）。
        単に拒否するだけでは、レジ担当が同じ操作を繰り返すことになる。
        """
        expected = to_amount(server)
        if (
            client.subtotal == expected.subtotal
            and client.discount == expected.discount
            and client.tax_reduced == expected.tax_reduced
            and client.tax_standard == expected.tax_standard
            and client.total == expected.total
        ):
            return
        raise AppError(
            ErrorCode.TXN_AMOUNT_MISMATCH,
            {
                "serverAmount": {
                    "subtotal": expected.subtotal,
                    "discount": expected.discount,
                    "taxReduced": expected.tax_reduced,
                    "taxStandard": expected.tax_standard,
                    "total": expected.total,
                }
            },
        )


def to_response(transaction: Transaction) -> CheckoutResponse:
    """保存済みの取引を確定応答の形に戻す。二重送信の2回目に返す。"""
    return CheckoutResponse(
        transaction_id=transaction.transaction_id,
        # DBには JST の naive datetime で入っているので、オフセットを付け直す
        transacted_at=transaction.transacted_at.replace(tzinfo=JST),
        amount=Amount(
            subtotal=transaction.subtotal,
            discount=transaction.discount_amount,
            tax_reduced=transaction.tax_reduced,
            tax_standard=transaction.tax_standard,
            total=transaction.total,
        ),
        lines=[
            ConfirmedLine(
                line_no=line.line_no,
                product_code=line.product_code,
                product_name=line.product_name,
                unit_price=line.unit_price,
                quantity=line.quantity,
                tax_category=TaxCategory(line.tax_category),
                applied_tax_rate=Decimal(line.applied_tax_rate),
                line_amount=line.line_amount,
            )
            for line in transaction.lines
        ],
    )


def to_amount(summary: AmountSummary) -> Amount:
    """計算結果を API のスキーマに移す。"""
    return Amount(
        subtotal=summary.subtotal,
        discount=summary.discount,
        tax_reduced=summary.tax_reduced,
        tax_standard=summary.tax_standard,
        total=summary.total,
    )
