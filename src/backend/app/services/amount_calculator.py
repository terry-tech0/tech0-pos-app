"""金額計算。設計仕様書 §4.4 の唯一の実装。

この手順は画面（TypeScript の lib/amount.ts）と必ず同じでなければならない。
片方だけ直すと、購入確定時の照合（設計 §8.6）が理由もなく E-TXN-001 で落ちる。
手順を変えるときは、必ず両方を同じコミットで直す。

設計 §4.4 の手順:
  1. 行金額 = 単価 × 数量（税抜・整数円）
  2. 税抜合計 subtotal = 全行の行金額の合計
  3. 会員割引 discount = floor(subtotal × 0.05)（非会員は 0）
  4. 割引を税率区分ごとの税抜小計に比例配分し、円未満は切り捨て。
     配分の残りは「税抜小計が大きい区分」へ加算する
  5. 区分ごとの割引後税抜 = 区分の税抜小計 − 配分された割引額
  6. 区分ごとの消費税 = floor(割引後税抜 × その区分の税率)
  7. 税込合計 total = (subtotal − discount) + 消費税の合計

金額はすべて int（円）。float は誤差が出るため一切使わない（設計 §4.2）。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Mapping, Sequence

from app.enums import TaxCategory

# 会員割引率。設計 §4.4 手順3（要件定義書 Q-3 で「税抜合計から5%」と仮決め）
MEMBER_DISCOUNT_RATE = Decimal("0.05")


@dataclass(frozen=True)
class CalcLine:
    """計算に必要な1行分の情報。

    確認事項 T-6 への回答＝この型。商品名は計算に使わないので持たせない。
    DBのモデルにも Pydantic のスキーマにも依存させないことで、
    単体テスト（UT-BE）が DB もサーバも立てずに書ける。
    """

    unit_price: int       # 税抜・整数円（0〜999,999）
    quantity: int         # 1〜99
    tax_category: TaxCategory

    @property
    def line_amount(self) -> int:
        """行金額 = 単価 × 数量。設計 §4.4 手順1"""
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class AmountSummary:
    """計算結果。クラス図 AmountSummary。

    購入確定時に画面の計算値と照合するのは、この5項目すべて（設計 §8.6 手順4）。
    按分の内訳は外に出さない（税額の内訳 tax_reduced / tax_standard から間接的に分かる）。
    """

    subtotal: int        # 税抜合計
    discount: int        # 会員割引額
    tax_reduced: int     # 軽減税率（8%）分の消費税
    tax_standard: int    # 標準税率（10%）分の消費税
    total: int           # 税込合計


def _floor_mul(amount: int, rate: Decimal) -> int:
    """amount × rate を円未満切り捨てで返す。

    Decimal を使うのは、float の 0.1 が正確に 0.1 ではないため。
    round() は「銀行家の丸め」（0.5 を偶数側へ）なので使わない。切り捨ては ROUND_FLOOR。
    """
    return int((Decimal(amount) * rate).to_integral_value(rounding=ROUND_FLOOR))


class AmountCalculator:
    """金額計算の唯一の実装。クラス図 AmountCalculator。

    DBにもHTTPにも依存しない純粋な計算クラス。状態を持たないので使い回してよい。
    """

    def calculate(
        self,
        lines: Sequence[CalcLine],
        is_member: bool,
        tax_rates: Mapping[TaxCategory, Decimal],
    ) -> AmountSummary:
        """設計 §4.4 の手順どおりに金額を計算する。

        Args:
            lines: 明細（1〜100行）。単価・数量・税率区分はマスタから引いた値を渡す
            is_member: 会員割引の対象か（Member.isDiscountTarget() の結果）
            tax_rates: 税率区分ごとの適用税率（例 {REDUCED: 0.0800, STANDARD: 0.1000}）

        Raises:
            ValueError: 明細が0件のとき（確認事項 T-2）。
                API層は先に E-TXN-002 で弾くが、計算クラスとしては
                「0円の会計」という概念を認めない。呼び出し側のバグを隠さないため例外にする。
            KeyError: 明細の税率区分が tax_rates に無いとき（税率マスタの不備）
        """
        if not lines:
            raise ValueError("明細が0件です。購入確定は E-TXN-002 で弾くこと")

        # 手順1・2: 行金額を積んで税抜合計を出す
        subtotal = sum(line.line_amount for line in lines)

        # 区分ごとの税抜小計。按分（手順4）と消費税（手順6）の両方で使う
        subtotal_by_category: dict[TaxCategory, int] = {}
        for line in lines:
            category = TaxCategory(line.tax_category)
            subtotal_by_category[category] = (
                subtotal_by_category.get(category, 0) + line.line_amount
            )

        # 手順3: 会員割引
        discount = _floor_mul(subtotal, MEMBER_DISCOUNT_RATE) if is_member else 0

        # 手順4: 割引を区分ごとに按分
        allocated = self._allocate_discount(subtotal_by_category, discount, subtotal)

        # 手順5・6: 割引後の税抜に税率をかけ、区分ごとに切り捨て
        tax_by_category: dict[TaxCategory, int] = {}
        for category, category_subtotal in subtotal_by_category.items():
            discounted = category_subtotal - allocated[category]
            tax_by_category[category] = self._tax_of(discounted, tax_rates[category])

        # 手順7: 税込合計
        tax_reduced = tax_by_category.get(TaxCategory.REDUCED, 0)
        tax_standard = tax_by_category.get(TaxCategory.STANDARD, 0)
        total = (subtotal - discount) + tax_reduced + tax_standard

        return AmountSummary(
            subtotal=subtotal,
            discount=discount,
            tax_reduced=tax_reduced,
            tax_standard=tax_standard,
            total=total,
        )

    def _allocate_discount(
        self,
        subtotal_by_category: Mapping[TaxCategory, int],
        discount: int,
        subtotal: int,
    ) -> dict[TaxCategory, int]:
        """割引額を税率区分ごとの税抜小計に比例配分する。設計 §4.4 手順4。

        切り捨てで配分すると合計が割引額に届かないため（例: 23 + 14 = 37 ≠ 38）、
        余りを1区分に寄せて必ず合計が discount と一致するようにする。
        ここを落とすと、割引額とその内訳が1円合わなくなる。
        """
        allocated = {category: 0 for category in subtotal_by_category}

        # 確認事項 T-7: 税抜合計0円のときは按分しない（ゼロ除算を避ける）。
        # 全商品0円なら割引額も0なので、配分すべきものが無い。
        if discount == 0 or subtotal == 0:
            return allocated

        for category, category_subtotal in subtotal_by_category.items():
            # floor(discount × 区分小計 ÷ 税抜合計)。整数の // なので切り捨てになる
            allocated[category] = discount * category_subtotal // subtotal

        remainder = discount - sum(allocated.values())
        if remainder:
            allocated[self._remainder_target(subtotal_by_category)] += remainder

        return allocated

    @staticmethod
    def _remainder_target(subtotal_by_category: Mapping[TaxCategory, int]) -> TaxCategory:
        """按分の余りを寄せる区分を決める。「税抜小計が大きい区分」（設計 §4.4 手順4）。

        確認事項 T-1 への回答: 小計が同額のときは軽減税率（REDUCED）へ寄せる。
        設計は「小計が大きい区分」としか書いておらず同額のときが決まらないため、
        ここで決定的なルールにする。決定的でないと、画面とサーバで寄せ先が割れて
        E-TXN-001 が理由もなく出る。
        """
        return max(
            subtotal_by_category.items(),
            key=lambda item: (item[1], item[0] is TaxCategory.REDUCED),
        )[0]

    @staticmethod
    def _tax_of(amount: int, rate: Decimal) -> int:
        """消費税額。設計 §4.4 手順6。区分ごとに1回だけ切り捨てる。

        行ごとに税を計算して足すと、まとめて計算した場合と1円ずれる。
        「1つの取引につき、税率ごとに1回」が消費税の端数処理の原則。
        """
        return _floor_mul(amount, rate)
