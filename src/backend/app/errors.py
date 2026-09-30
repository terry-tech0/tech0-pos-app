"""エラーコードと例外。設計仕様書 §7 エラー処理設計。

方針（設計 §7.2）:
  ER-2 画面に出すのは「レジ担当が次に取れる行動」。技術的な原因は出さない
  ER-3 例外の詳細・スタックトレースをレスポンスに含めない
  ER-6 想定外の例外は必ず E-SYS-001 に丸めて返し、握りつぶさない
"""

from __future__ import annotations

from typing import Any


class ErrorCode:
    """設計 §7.1 エラーコード一覧。文字列を直書きしないための定数。"""

    VAL_FORMAT = "E-VAL-001"       # 400 入力の形式が正しくありません
    VAL_QUANTITY = "E-VAL-002"     # 400 数量は1〜99で入力してください
    VAL_LINE_COUNT = "E-VAL-003"   # 400 1回の会計に登録できるのは100行までです
    AUTH_FAILED = "E-AUTH-001"     # 401 IDまたはパスワードが違います
    AUTH_EXPIRED = "E-AUTH-002"    # 401 ログインの有効期限が切れました
    AUTH_FORBIDDEN = "E-AUTH-003"  # 403 この操作の権限がありません
    MEMBER_NOT_FOUND = "E-MEMB-001"  # 404 会員が見つかりません
    PRODUCT_NOT_FOUND = "E-PROD-001"  # 404 商品がマスタ未登録です
    TXN_AMOUNT_MISMATCH = "E-TXN-001"  # 400 金額を再計算しました
    TXN_NO_LINES = "E-TXN-002"     # 400 商品が登録されていません
    SYS_UNEXPECTED = "E-SYS-001"   # 500 エラーが発生しました
    SYS_UNAVAILABLE = "E-SYS-002"  # 503 システムに接続できません


# コード → (HTTPステータス, 画面に出すメッセージ)
# メッセージは設計 §7.1 の「画面に出すメッセージ」列をそのまま使う
ERROR_SPEC: dict[str, tuple[int, str]] = {
    ErrorCode.VAL_FORMAT: (400, "入力の形式が正しくありません"),
    ErrorCode.VAL_QUANTITY: (400, "数量は1〜99で入力してください"),
    ErrorCode.VAL_LINE_COUNT: (400, "1回の会計に登録できるのは100行までです"),
    ErrorCode.AUTH_FAILED: (401, "IDまたはパスワードが違います"),
    ErrorCode.AUTH_EXPIRED: (401, "ログインの有効期限が切れました。もう一度ログインしてください"),
    ErrorCode.AUTH_FORBIDDEN: (403, "この操作の権限がありません"),
    ErrorCode.MEMBER_NOT_FOUND: (404, "会員が見つかりません"),
    ErrorCode.PRODUCT_NOT_FOUND: (404, "商品がマスタ未登録です"),
    ErrorCode.TXN_AMOUNT_MISMATCH: (400, "金額を再計算しました。内容を確認してもう一度お願いします"),
    ErrorCode.TXN_NO_LINES: (400, "商品が登録されていません"),
    ErrorCode.SYS_UNEXPECTED: (500, "エラーが発生しました。店長に連絡してください"),
    ErrorCode.SYS_UNAVAILABLE: (503, "システムに接続できません"),
}


class AppError(Exception):
    """業務エラー。設計 §5.3 の共通エラー形式で返すための例外。

    details に入れてよいのは「レジ担当が次の行動を取るために必要な情報」だけ。
    例外の中身やSQLは入れない（ER-3）。
    """

    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.status_code, self.message = ERROR_SPEC[code]
        self.details = details
        super().__init__(f"{code}: {self.message}")

    def to_response(self) -> dict[str, Any]:
        """設計 §5.3 のエラー形式に変換する。"""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}
