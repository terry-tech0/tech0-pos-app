"""DBアクセス。SQLはこの層だけに閉じ込める（設計仕様書 §8.8）。

SQLAlchemy の式で書くことで、値は必ずパラメータとしてバインドされる。
f文字列や + での文字列連結でSQLを組み立てると、そこがSQLインジェクションの穴になる。
この層の外にSQLを漏らさないのが、穴を作らないための構造上の担保。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TaxCategory
from app.models import Cashier, Member, Product, TaxRate, Transaction, TransactionLine


class CashierRepository:
    """レジ担当の照会。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_login_id(self, login_id: str) -> Cashier | None:
        """ログインIDで引く。退職者（is_active=False）も返す。

        ここで is_active を絞らないのは、呼び出し側（AuthService）が
        「IDが無い」と「無効な担当」のどちらでも同じ E-AUTH-001 を返し、
        かつ同じ時間をかけて応答するため（設計 §8.1 S-2, S-3）。
        """
        return self._session.scalar(select(Cashier).where(Cashier.login_id == login_id))

    def find_by_id(self, cashier_id: int) -> Cashier | None:
        return self._session.get(Cashier, cashier_id)


class MemberRepository:
    """会員の照会。クラス図 MemberRepository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_code(self, member_code: str) -> Member | None:
        """有効な会員だけを返す。退会済みは「見つからない」扱い（IT-023）。"""
        return self._session.scalar(
            select(Member).where(Member.member_code == member_code, Member.is_active.is_(True))
        )


class ProductRepository:
    """商品の照会。クラス図 ProductRepository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_code(self, product_code: str) -> Product | None:
        """有効な商品だけを返す。取扱終了は「未登録」と同じ扱い（設計 §5.4 A-05）。"""
        return self._session.scalar(
            select(Product).where(
                Product.product_code == product_code, Product.is_active.is_(True)
            )
        )

    def find_many_by_codes(self, product_codes: Sequence[str]) -> dict[str, Product]:
        """複数コードをまとめて引く。確定処理で明細ごとにDBへ問い合わせないため。

        100行の会計で100回SELECTすると、会計1件1分以内（NFR-PERF-02）に影響する。
        戻り値はコード→商品の辞書。見つからなかったコードは含まれない。
        """
        if not product_codes:
            return {}
        unique_codes = list(dict.fromkeys(product_codes))
        rows = self._session.scalars(
            select(Product).where(
                Product.product_code.in_(unique_codes), Product.is_active.is_(True)
            )
        ).all()
        return {row.product_code: row for row in rows}


class TaxRateRepository:
    """税率の照会。クラス図 TaxRateRepository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_effective(self, on_date: date) -> dict[TaxCategory, TaxRate]:
        """指定日に有効な税率を区分ごとに返す。

        有効の条件は valid_from <= 指定日 かつ（valid_to が NULL または 指定日 <= valid_to）。
        同じ区分に複数の行が該当する場合は valid_from が新しいものを採る
        （税率改定日に旧行の valid_to を入れ忘れても、新しい方が効く）。
        """
        rows = self._session.scalars(
            select(TaxRate)
            .where(TaxRate.valid_from <= on_date)
            .where((TaxRate.valid_to.is_(None)) | (TaxRate.valid_to >= on_date))
            .order_by(TaxRate.tax_category, TaxRate.valid_from)
        ).all()
        # valid_from の昇順で回すので、後から入る新しい行が上書きする
        effective: dict[TaxCategory, TaxRate] = {}
        for row in rows:
            effective[TaxCategory(row.tax_category)] = row
        return effective

    def rates_only(self, on_date: date) -> dict[TaxCategory, Decimal]:
        """AmountCalculator に渡す形（区分→税率）で返す。"""
        return {
            category: Decimal(rate.rate) for category, rate in self.find_effective(on_date).items()
        }


class TransactionRepository:
    """購入履歴の保存。クラス図 TransactionRepository。

    追記のみ。更新・削除のメソッドを**作らない**（NFR-OPS-05 / 設計 §4.3 D-5）。
    「うっかり消せる口」をコードとして用意しないのが一番確実な担保。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        *,
        transacted_at: datetime,
        cashier_id: int,
        member_code: str | None,
        subtotal: int,
        discount_amount: int,
        tax_reduced: int,
        tax_standard: int,
        total: int,
        lines: Sequence[TransactionLine],
    ) -> Transaction:
        """ヘッダと明細を1トランザクションで保存する。

        commit はここで行う。途中で失敗したら明細だけ残る、という状態を作らない。
        """
        transaction = Transaction(
            transacted_at=transacted_at,
            cashier_id=cashier_id,
            member_code=member_code,
            subtotal=subtotal,
            discount_amount=discount_amount,
            tax_reduced=tax_reduced,
            tax_standard=tax_standard,
            total=total,
        )
        transaction.lines = list(lines)
        self._session.add(transaction)
        self._session.commit()
        self._session.refresh(transaction)
        return transaction
