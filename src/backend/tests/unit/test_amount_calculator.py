"""AmountCalculator の単体テスト。

対応: テスト仕様書 01-単体テスト-backend-pytest.md（UT-BE-001〜054）／設計 §4.4

★ここの入力と期待値は、画面側の __tests__/amount.test.ts と**まったく同じ**にしている
  （テスト仕様書 §1.3）。どちらかの実装がずれたら、必ずどちらかのテストが落ちる。

DBもサーバも立てずに動く（計算クラスが DB に依存していないため）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.enums import TaxCategory
from app.services.amount_calculator import AmountCalculator, CalcLine

# 現行の税率（fixtures/tax_rates.csv と同じ）
RATES = {TaxCategory.REDUCED: Decimal("0.0800"), TaxCategory.STANDARD: Decimal("0.1000")}


@pytest.fixture
def calculator() -> AmountCalculator:
    return AmountCalculator()


def line(unit_price: int, quantity: int, category: TaxCategory) -> CalcLine:
    return CalcLine(unit_price=unit_price, quantity=quantity, tax_category=category)


# 設計 §4.4 の計算例と同じ買い物（おにぎり×2・牛乳×1・洗剤×1）
BASE_CART = [
    line(128, 2, TaxCategory.REDUCED),
    line(218, 1, TaxCategory.REDUCED),
    line(298, 1, TaxCategory.STANDARD),
]


def tuple_of(summary) -> tuple[int, int, int, int, int]:
    return (
        summary.subtotal,
        summary.discount,
        summary.tax_reduced,
        summary.tax_standard,
        summary.total,
    )


class TestNormal:
    """正常系。設計 §4.4 の計算例をそのまま期待値にする。"""

    def test_ut_be_001_member_mixed_rates(self, calculator: AmountCalculator) -> None:
        """UT-BE-001 会員・8%と10%混在。設計 §4.4 の計算例と同一。"""
        assert tuple_of(calculator.calculate(BASE_CART, True, RATES)) == (772, 38, 36, 28, 798)

    def test_ut_be_002_non_member(self, calculator: AmountCalculator) -> None:
        """UT-BE-002 同じ買い物を非会員で。"""
        assert tuple_of(calculator.calculate(BASE_CART, False, RATES)) == (772, 0, 37, 29, 838)

    def test_ut_be_009_order_independent(self, calculator: AmountCalculator) -> None:
        """UT-BE-009 行の順序に依存しない（読み取り順で金額が変わらない）。"""
        reversed_cart = list(reversed(BASE_CART))
        assert tuple_of(calculator.calculate(reversed_cart, True, RATES)) == (772, 38, 36, 28, 798)

    def test_reduced_only(self, calculator: AmountCalculator) -> None:
        """軽減税率のみ（10%の行が無い）。"""
        result = calculator.calculate([line(100, 1, TaxCategory.REDUCED)], False, RATES)
        assert tuple_of(result) == (100, 0, 8, 0, 108)

    def test_standard_only(self, calculator: AmountCalculator) -> None:
        """標準税率のみ（8%の行が無い）。"""
        result = calculator.calculate([line(100, 1, TaxCategory.STANDARD)], False, RATES)
        assert tuple_of(result) == (100, 0, 0, 10, 110)

    def test_quantity_multiplies(self, calculator: AmountCalculator) -> None:
        """行金額 = 単価 × 数量（設計 §4.4 手順1）。"""
        result = calculator.calculate([line(128, 2, TaxCategory.REDUCED)], False, RATES)
        assert result.subtotal == 256


class TestTruncationBoundaries:
    """端数切り捨ての境界。テスト仕様書 §2.3。

    四捨五入で実装していると必ず落ちるよう、境目の両側を対で置く。
    """

    @pytest.mark.parametrize(
        ("price", "expected"),
        [(12, 0), (13, 1)],  # 12*0.08=0.96 -> 0 / 13*0.08=1.04 -> 1
        ids=["12円×8%は0円", "13円×8%は1円"],
    )
    def test_reduced_tax_boundary(
        self, calculator: AmountCalculator, price: int, expected: int
    ) -> None:
        result = calculator.calculate([line(price, 1, TaxCategory.REDUCED)], False, RATES)
        assert result.tax_reduced == expected

    @pytest.mark.parametrize(
        ("price", "expected"),
        [(9, 0), (10, 1)],  # 9*0.10=0.90 -> 0 / 10*0.10=1.00 -> 1
        ids=["9円×10%は0円", "10円×10%は1円"],
    )
    def test_standard_tax_boundary(
        self, calculator: AmountCalculator, price: int, expected: int
    ) -> None:
        result = calculator.calculate([line(price, 1, TaxCategory.STANDARD)], False, RATES)
        assert result.tax_standard == expected

    @pytest.mark.parametrize(
        ("price", "expected"),
        [(19, 0), (20, 1)],  # 19*0.05=0.95 -> 0 / 20*0.05=1.00 -> 1
        ids=["税抜19円の5%割引は0円", "税抜20円の5%割引は1円"],
    )
    def test_discount_boundary(
        self, calculator: AmountCalculator, price: int, expected: int
    ) -> None:
        result = calculator.calculate([line(price, 1, TaxCategory.REDUCED)], True, RATES)
        assert result.discount == expected


class TestDiscountAllocation:
    """割引の按分。設計 §4.4 手順4。バグの温床なので厚めに置く。"""

    def test_remainder_goes_to_larger_subtotal(self, calculator: AmountCalculator) -> None:
        """余った1円は税抜小計が大きい区分（8%側）へ寄せる。

        8%小計474・10%小計298・割引38 -> 按分 23+14=37 で1円余る -> 8%へ寄せて24。
        余りを捨てる実装だと 8% の課税対象が 451 になり、税額が 36 にならない。
        """
        result = calculator.calculate(BASE_CART, True, RATES)
        assert result.tax_reduced == 36  # floor((474-24)*0.08) = floor(36.0)
        assert result.tax_standard == 28  # floor((298-14)*0.10) = floor(28.4)
        assert result.subtotal - result.discount == 734

    def test_t1_tie_goes_to_reduced(self, calculator: AmountCalculator) -> None:
        """確認事項 T-1: 税抜小計が同額のときは軽減8%へ寄せる。

        510+510=1020、割引 floor(1020*0.05)=51、按分 25+25=50 で1円余る。
        設計 §4.4 は「小計が大きい区分」としか書いておらず同額のときが決まらないため、
        本実装で「REDUCED優先」と決めた。決定的でないと画面とサーバで寄せ先が割れる。
        """
        result = calculator.calculate(
            [line(510, 1, TaxCategory.REDUCED), line(510, 1, TaxCategory.STANDARD)], True, RATES
        )
        assert tuple_of(result) == (1020, 51, 38, 48, 1055)
        # 8%へ26・10%へ25 を配分した結果。10%側の税額でこの差が出る
        assert result.tax_standard == 48

    def test_allocation_sums_to_discount(self, calculator: AmountCalculator) -> None:
        """按分の合計が必ず割引額と一致する（余りを捨てていないこと）。

        内訳は外から見えないので、税額の合計と税込合計の関係から間接的に確かめる。
        total = (subtotal - discount) + 税額合計 が崩れていなければ、
        配分の合計は discount と一致している。
        """
        for subtotal_pair in [(474, 298), (510, 510), (1, 9999), (0, 100)]:
            result = calculator.calculate(
                [
                    line(subtotal_pair[0], 1, TaxCategory.REDUCED),
                    line(subtotal_pair[1], 1, TaxCategory.STANDARD),
                ],
                True,
                RATES,
            )
            assert result.total == (
                result.subtotal - result.discount + result.tax_reduced + result.tax_standard
            )


class TestEdgeCases:
    """異常系・境界。確認事項 T-2 / T-7 を含む。"""

    def test_t2_empty_lines_raises(self, calculator: AmountCalculator) -> None:
        """確認事項 T-2: 明細0件は ValueError。

        API層は先に E-TXN-002 で弾くが、計算クラスとしては
        「0円の会計」という概念を認めない。呼び出し側のバグを隠さないため。
        """
        with pytest.raises(ValueError):
            calculator.calculate([], False, RATES)

    def test_t7_zero_subtotal_no_division_error(self, calculator: AmountCalculator) -> None:
        """確認事項 T-7: 全商品0円でもゼロ除算にならない。"""
        result = calculator.calculate(
            [line(0, 1, TaxCategory.REDUCED), line(0, 1, TaxCategory.STANDARD)], True, RATES
        )
        assert tuple_of(result) == (0, 0, 0, 0, 0)

    def test_zero_price_line_does_not_affect_others(self, calculator: AmountCalculator) -> None:
        """UT-BE-025 0円商品が混ざっても他の行に影響しない。"""
        result = calculator.calculate(
            [line(0, 1, TaxCategory.REDUCED), line(100, 1, TaxCategory.REDUCED)], False, RATES
        )
        assert tuple_of(result) == (100, 0, 8, 0, 108)

    def test_upper_bound_price(self, calculator: AmountCalculator) -> None:
        """単価の上限 999,999 でも整数のまま計算される（設計 §6）。"""
        result = calculator.calculate([line(999_999, 1, TaxCategory.STANDARD)], False, RATES)
        assert result.subtotal == 999_999
        assert result.tax_standard == 99_999  # floor(999999*0.10)=99999.9 -> 99999
        assert isinstance(result.total, int)

    def test_missing_tax_rate_raises_key_error(self, calculator: AmountCalculator) -> None:
        """税率マスタに区分が無ければ KeyError（無言で0円にしない）。"""
        with pytest.raises(KeyError):
            calculator.calculate(
                [line(100, 1, TaxCategory.STANDARD)],
                False,
                {TaxCategory.REDUCED: Decimal("0.0800")},
            )

    def test_changed_tax_rate(self, calculator: AmountCalculator) -> None:
        """税率が変わっても正しい（REQ-08 により税率は変わりうる。食品1%を想定）。"""
        result = calculator.calculate(
            [line(1000, 1, TaxCategory.REDUCED)],
            False,
            {TaxCategory.REDUCED: Decimal("0.0100"), TaxCategory.STANDARD: Decimal("0.1000")},
        )
        assert result.tax_reduced == 10

    def test_all_amounts_are_int(self, calculator: AmountCalculator) -> None:
        """金額はすべて int（Decimal や float を返さない。設計 §4.2）。"""
        result = calculator.calculate(BASE_CART, True, RATES)
        for value in tuple_of(result):
            assert isinstance(value, int)
