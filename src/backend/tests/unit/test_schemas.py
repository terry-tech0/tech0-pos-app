"""Pydantic スキーマの入力検証の単体テスト。

対応: テスト仕様書 01-単体テスト-backend-pytest.md（UT-BE-030〜049）／設計 §6 入力値の下限・上限

同値分割と境界値分析を使う（テスト仕様書 §2.1・§2.2）。
有効範囲の「すぐ外・端・端・すぐ外」の4点を必ず置く。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.pos import (
    Amount,
    CheckoutLineIn,
    CheckoutRequest,
    LoginRequest,
)

VALID_AMOUNT = {
    "subtotal": 772,
    "discount": 38,
    "tax_reduced": 36,
    "tax_standard": 28,
    "total": 798,
}


def checkout_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "member_code": "1000000001",
        "lines": [{"product_code": "4901234567894", "quantity": 1}],
        "client_amount": VALID_AMOUNT,
    }
    body.update(overrides)
    return body


class TestProductCode:
    """商品コード（JAN）。設計 §6: 数字8桁または13桁。"""

    @pytest.mark.parametrize("code", ["49012345", "4901234567894"], ids=["8桁", "13桁"])
    def test_ut_be_040_valid_lengths(self, code: str) -> None:
        assert CheckoutLineIn(product_code=code, quantity=1).product_code == code

    @pytest.mark.parametrize(
        "code",
        ["4901234", "490123456", "4901234567", "49012345678", "490123456789", "49012345678945"],
        ids=["7桁", "9桁", "10桁", "11桁", "12桁", "14桁"],
    )
    def test_ut_be_041_046_invalid_lengths(self, code: str) -> None:
        """★9〜12桁は無効。

        JANは8桁または13桁のどちらかのみ。
        「8以上13以下」と実装すると10桁が通ってしまう。この誤りを検出するケース。
        """
        with pytest.raises(ValidationError):
            CheckoutLineIn(product_code=code, quantity=1)

    @pytest.mark.parametrize(
        "code",
        ["4901234a", "49012 45", "４９０１２３４５", "'; DROP TABLE products; --", ""],
        ids=["英字混在", "空白混在", "全角数字", "SQL断片", "空文字"],
    )
    def test_ut_be_046_non_numeric_rejected(self, code: str) -> None:
        """数字以外を通さない。これがSQLインジェクション対策の一段目にもなる（設計 §8.8）。"""
        with pytest.raises(ValidationError):
            CheckoutLineIn(product_code=code, quantity=1)


class TestQuantity:
    """1行あたりの数量。設計 §6: 1〜99。"""

    @pytest.mark.parametrize("quantity", [1, 50, 99], ids=["下限1", "代表50", "上限99"])
    def test_ut_be_030_031_valid(self, quantity: int) -> None:
        assert CheckoutLineIn(product_code="49012345", quantity=quantity).quantity == quantity

    @pytest.mark.parametrize(
        "quantity", [0, -1, 100, 1000], ids=["下限外0", "負数", "上限外100", "大きすぎ"]
    )
    def test_ut_be_032_033_invalid(self, quantity: int) -> None:
        """0や負数は「削除」であって数量ではない。100以上は打ち間違い対策。"""
        with pytest.raises(ValidationError):
            CheckoutLineIn(product_code="49012345", quantity=quantity)

    @pytest.mark.parametrize("quantity", [2.5, "3", None], ids=["小数", "文字列", "None"])
    def test_type_violations(self, quantity: object) -> None:
        with pytest.raises(ValidationError):
            CheckoutLineIn(product_code="49012345", quantity=quantity)


class TestMemberCode:
    """会員識別番号。設計 §6: 数字10桁固定。"""

    def test_valid(self) -> None:
        assert CheckoutRequest(**checkout_body()).member_code == "1000000001"

    def test_none_means_non_member(self) -> None:
        """非会員は None。ダミー会員で表さない（設計 §4.3 D-3）。"""
        assert CheckoutRequest(**checkout_body(member_code=None)).member_code is None

    @pytest.mark.parametrize(
        "code", ["100000000", "10000000012", "100000000a", ""], ids=["9桁", "11桁", "英字混在", "空文字"]
    )
    def test_ut_be_048_invalid(self, code: str) -> None:
        """TC-12 会員番号が9桁。桁が違う時点で照会しない（設計 §6）。"""
        with pytest.raises(ValidationError):
            CheckoutRequest(**checkout_body(member_code=code))


class TestLineCount:
    """1会計の明細行数。設計 §6: 1〜100。数量の上限とは別物。"""

    def test_ut_be_036_zero_lines_rejected(self) -> None:
        """明細0件は通さない（API層で E-TXN-002 に変換される）。"""
        with pytest.raises(ValidationError):
            CheckoutRequest(**checkout_body(lines=[]))

    def test_ut_be_034_100_lines_ok(self) -> None:
        lines = [{"product_code": "49012345", "quantity": 1} for _ in range(100)]
        assert len(CheckoutRequest(**checkout_body(lines=lines)).lines) == 100

    def test_ut_be_035_101_lines_rejected(self) -> None:
        lines = [{"product_code": "49012345", "quantity": 1} for _ in range(101)]
        with pytest.raises(ValidationError):
            CheckoutRequest(**checkout_body(lines=lines))


class TestRejectedFields:
    """★受け取ってはいけない項目。設計 §5.4 A-07・§8.6。"""

    def test_tc_14_unit_price_is_ignored(self) -> None:
        """単価を混ぜて送られても無視される（スキーマに定義していないため）。

        「送られた単価を使ってしまう」事故が、型の形として起こりえなくなる。
        """
        line = CheckoutLineIn(product_code="49012345", quantity=1, unit_price=1)
        assert not hasattr(line, "unit_price")

    def test_cashier_id_is_ignored(self) -> None:
        """担当IDを送られても無視される。担当はJWTの sub から決める（詐称防止）。"""
        request = CheckoutRequest(**checkout_body(), cashier_id=999)
        assert not hasattr(request, "cashier_id")

    def test_tax_rate_is_ignored(self) -> None:
        """税率を送られても無視される。サーバがマスタから引く。"""
        line = CheckoutLineIn(product_code="49012345", quantity=1, tax_rate=0)
        assert not hasattr(line, "tax_rate")


class TestAmountBounds:
    """金額の上下限。設計 §6: 0〜9,999,999。"""

    @pytest.mark.parametrize("value", [0, 9_999_999], ids=["下限0", "上限9999999"])
    def test_valid_bounds(self, value: int) -> None:
        amount = Amount(
            subtotal=value, discount=0, tax_reduced=0, tax_standard=0, total=value
        )
        assert amount.subtotal == value

    @pytest.mark.parametrize("value", [-1, 10_000_000], ids=["負数", "上限外"])
    def test_invalid_bounds(self, value: int) -> None:
        with pytest.raises(ValidationError):
            Amount(subtotal=value, discount=0, tax_reduced=0, tax_standard=0, total=0)

    def test_float_amount_rejected(self) -> None:
        """金額は整数のみ。小数で送らせない（設計 §5.3）。"""
        with pytest.raises(ValidationError):
            Amount(subtotal=100.5, discount=0, tax_reduced=0, tax_standard=0, total=0)


class TestLoginRequest:
    """ログイン。設計 §6: ID は半角英数4〜20文字、パスワードは8〜72バイト。"""

    @pytest.mark.parametrize("login_id", ["abcd", "a" * 20], ids=["下限4文字", "上限20文字"])
    def test_valid_login_id(self, login_id: str) -> None:
        assert LoginRequest(login_id=login_id, password="12345678").login_id == login_id

    @pytest.mark.parametrize(
        "login_id", ["abc", "a" * 21, "cashier-01", "担当01"], ids=["3文字", "21文字", "記号", "日本語"]
    )
    def test_invalid_login_id(self, login_id: str) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(login_id=login_id, password="12345678")

    @pytest.mark.parametrize(
        ("password", "valid"),
        [
            ("1234567", False),   # 7バイト（下限外）
            ("12345678", True),   # 8バイト（下限）
            ("a" * 72, True),     # 72バイト（上限）
            ("a" * 73, False),    # 73バイト（上限外）
        ],
        ids=["7バイト", "8バイト", "72バイト", "73バイト"],
    )
    def test_password_byte_length(self, password: str, valid: bool) -> None:
        """★bcrypt は72バイトを超える部分を無視するため、上限を仕様として明示している。"""
        if valid:
            assert LoginRequest(login_id="cashier01", password=password).password == password
        else:
            with pytest.raises(ValidationError):
                LoginRequest(login_id="cashier01", password=password)

    def test_password_counted_in_bytes_not_characters(self) -> None:
        """★「文字数」ではなく「バイト数」で数える（日本語1文字は3バイト）。

        日本語24文字＝72バイトは通り、25文字＝75バイトは通らない。
        """
        assert LoginRequest(login_id="cashier01", password="あ" * 24).password == "あ" * 24
        with pytest.raises(ValidationError):
            LoginRequest(login_id="cashier01", password="あ" * 25)
