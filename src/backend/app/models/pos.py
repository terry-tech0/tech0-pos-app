"""SQLAlchemy のテーブル定義。設計仕様書 §4.1 ER図・§4.2 テーブル定義。

金額はすべて Integer（税抜・税込とも整数の円）。
浮動小数点（Float/Double）は誤差が出るため使わない（設計 §4.2）。
税率だけは Numeric(5, 4)（例 0.0800）。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.enums import DiscountType, Role, TaxCategory


class Base(DeclarativeBase):
    pass


class Cashier(Base):
    """レジ担当。パスワードは bcrypt ハッシュのみ保存（NFR-SEC-02）。"""

    __tablename__ = "cashiers"

    cashier_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    cashier_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # bcrypt のハッシュは常に60文字
    password_hash: Mapped[str] = mapped_column(CHAR(60), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role, native_enum=True), nullable=False)
    # 退職者は false。物理削除しない（設計 §4.3 D-6）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Member(Base):
    """会員。学習用の架空データのみ（NFR-SEC-06）。"""

    __tablename__ = "members"

    member_code: Mapped[str] = mapped_column(CHAR(10), primary_key=True)
    member_name: Mapped[str] = mapped_column(String(50), nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(
        SAEnum(DiscountType, native_enum=True), nullable=False, default=DiscountType.NONE
    )
    joined_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def is_discount_target(self) -> bool:
        """割引対象か。クラス図 Member.isDiscountTarget()。

        退会済み（is_active=False）の会員は照会自体を通さないので、
        ここでは割引区分だけを見る。
        """
        return DiscountType(self.discount_type).is_discount_target()


class Product(Base):
    """商品マスタ。商品コードは JAN（8桁または13桁）。"""

    __tablename__ = "products"

    product_code: Mapped[str] = mapped_column(String(13), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 税抜・整数円 0〜999,999（設計 §6）
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_category: Mapped[TaxCategory] = mapped_column(
        SAEnum(TaxCategory, native_enum=True), nullable=False
    )
    # 取扱終了は false。未登録と取扱終了を画面で区別しない（設計 §5.4 A-05）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_products_tax_category", "tax_category"),)


class TaxRate(Base):
    """税率マスタ。行を追加するだけで税率改定に対応する（REQ-08 / NFR-OPS-04）。

    主キーが (区分, 適用開始日) なので、既存行を書き換えずに改定を表現できる。
    過去の税率も残るため、履歴の再計算が要らない（設計 §4.3 D-2）。
    """

    __tablename__ = "tax_rates"

    tax_category: Mapped[TaxCategory] = mapped_column(
        SAEnum(TaxCategory, native_enum=True), primary_key=True
    )
    valid_from: Mapped[date] = mapped_column(Date, primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    # NULL は現行（終了日が決まっていない）
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class Transaction(Base):
    """購入履歴のヘッダ。追記のみ。UPDATE / DELETE しない（NFR-OPS-05 / D-5）。"""

    __tablename__ = "transactions"

    transaction_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 会計ごとの整理番号（UUID）。一意制約で同じ会計の二重保存を防ぐ（設計 §4.3 D-7）
    checkout_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, unique=True)
    # ミリ秒まで保持する（同一秒に複数会計が入るため）
    transacted_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    # JWT の sub から確定した担当。リクエストからは受け取らない（設計 §5.4 A-07）
    cashier_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cashiers.cashier_id"), nullable=False
    )
    # 非会員は NULL。ダミー会員で表さない（設計 §4.3 D-3）
    member_code: Mapped[str | None] = mapped_column(
        CHAR(10), ForeignKey("members.member_code"), nullable=True
    )
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    # API の Amount では discount。DBのカラム名は discount_amount（設計 §4.1）
    discount_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    # 税率区分ごとに2列で持つ。合算だけだと内訳を復元できない（設計 §4.3 D-4）
    tax_reduced: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_standard: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lines: Mapped[list["TransactionLine"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", order_by="TransactionLine.line_no"
    )

    __table_args__ = (
        Index("ix_transactions_transacted_at", "transacted_at"),
        Index("ix_transactions_cashier_id", "cashier_id"),
    )


class TransactionLine(Base):
    """購入履歴の明細。

    商品名・単価・税率区分・適用税率を購入時点の値で転記する（原則 P-3 / D-1）。
    マスタの単価や税率を後から変えても、過去の履歴は動かない。
    """

    __tablename__ = "transaction_lines"

    transaction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transactions.transaction_id"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    product_code: Mapped[str] = mapped_column(
        String(13), ForeignKey("products.product_code"), nullable=False
    )
    # ここから4つが「購入時点の転記」
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tax_category: Mapped[TaxCategory] = mapped_column(
        SAEnum(TaxCategory, native_enum=True), nullable=False
    )
    applied_tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    line_amount: Mapped[int] = mapped_column(Integer, nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="lines")

    __table_args__ = (Index("ix_transaction_lines_product_code", "product_code"),)
