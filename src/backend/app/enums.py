"""区分を表す列挙。DBのenum・APIの値・計算クラスで同じものを使う。

設計仕様書 §4.1 ER図の enum 定義がここの正。
文字列と比較できるように str を継承させる（DBから読んだ値をそのまま渡せる）。
"""

from enum import Enum


class TaxCategory(str, Enum):
    """税率区分。設計 §4.1 products.tax_category"""

    STANDARD = "STANDARD"  # 標準税率（10%）
    REDUCED = "REDUCED"    # 軽減税率（8%）


class Role(str, Enum):
    """担当のロール。設計 §8.3 認可"""

    CASHIER = "CASHIER"    # 会計操作
    MANAGER = "MANAGER"    # ＋履歴参照・マスタ管理


class DiscountType(str, Enum):
    """会員の割引区分。設計 §4.1 members.discount_type"""

    NONE = "NONE"      # 割引なし
    RATE5 = "RATE5"    # 税抜合計から5%

    def is_discount_target(self) -> bool:
        """割引対象か。クラス図 Member.isDiscountTarget() の実装"""
        return self is DiscountType.RATE5
