"""テストデータ（fixtures）をDBへ投入する。

読み込むのは docs/test/fixtures/ の4つのCSV。
テスト仕様書 §4 テスト基盤「conftest.py が fixtures のCSVを投入する」と同じデータを、
開発用DBにも入れられるようにしたもの。

**パスワードはCSVに含めない。** 環境変数 SEED_CASHIER_PASSWORD（無ければ
TEST_CASHIER_PASSWORD）から読んでハッシュ化する（NFR-SEC-02, 03）。
未設定なら何もせず止める。本番のパスワードが紛れ込むのを防ぐため。

使い方:
    cd src/backend
    .venv/Scripts/python.exe -m scripts.seed

購入履歴（transactions / transaction_lines）は投入しない。
履歴は「購入した事実」なので、アプリを操作して作る。
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_engine, get_session_factory
from app.enums import DiscountType, Role, TaxCategory
from app.models import Cashier, Member, Product, TaxRate, Transaction, TransactionLine
from app.services import hash_password

# src/backend/scripts/seed.py -> リポジトリ直下
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "docs" / "test" / "fixtures"


def _read_csv(name: str) -> list[dict[str, str]]:
    """CSVを読む。末尾の「用途」列は説明なので使わない。"""
    path = FIXTURES / name
    if not path.exists():
        raise FileNotFoundError(f"fixtures が見つかりません: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_bool(value: str) -> bool:
    return value.strip().upper() == "TRUE"


def _to_date(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None


def _password() -> str:
    """投入するパスワードを環境変数から読む。リポジトリには置かない。"""
    password = os.getenv("SEED_CASHIER_PASSWORD") or os.getenv("TEST_CASHIER_PASSWORD")
    if not password:
        raise SystemExit(
            "環境変数 SEED_CASHIER_PASSWORD（または TEST_CASHIER_PASSWORD）が未設定です。\n"
            "テスト用のパスワードを決めて設定してください（リポジトリには置きません）:\n"
            '  PowerShell: $env:SEED_CASHIER_PASSWORD = "任意のパスワード"'
        )
    length = len(password.encode("utf-8"))
    if not 8 <= length <= 72:
        raise SystemExit(f"パスワードは8〜72バイトにしてください（現在 {length} バイト）")
    return password


def seed(session: Session, *, password: str) -> dict[str, int]:
    """マスタを投入する。既存のマスタは消してから入れ直す（実行順序に依存させない）。

    購入履歴が既にあると外部キーで消せないため、その場合は履歴を残したまま
    マスタの更新（upsert）に切り替える。
    """
    counts: dict[str, int] = {}
    has_history = session.scalar(select(Transaction.transaction_id).limit(1)) is not None

    if not has_history:
        # 履歴が無いので、マスタを全消しして入れ直せる
        session.execute(delete(TransactionLine))
        session.execute(delete(Transaction))
        session.execute(delete(Product))
        session.execute(delete(Member))
        session.execute(delete(Cashier))
        session.execute(delete(TaxRate))
        session.flush()

    # ── 税率 ──
    for row in _read_csv("tax_rates.csv"):
        category = TaxCategory(row["tax_category"].strip())
        valid_from = _to_date(row["valid_from"])
        assert valid_from is not None
        existing = session.get(TaxRate, (category, valid_from))
        if existing is None:
            session.add(
                TaxRate(
                    tax_category=category,
                    valid_from=valid_from,
                    rate=Decimal(row["rate"].strip()),
                    valid_to=_to_date(row["valid_to"]),
                )
            )
        else:
            existing.rate = Decimal(row["rate"].strip())
            existing.valid_to = _to_date(row["valid_to"])
    counts["tax_rates"] = len(_read_csv("tax_rates.csv"))

    # ── レジ担当。パスワードは環境変数からハッシュ化して入れる ──
    cashier_rows = _read_csv("cashiers.csv")
    password_hash = hash_password(password)
    for row in cashier_rows:
        cashier_id = int(row["cashier_id"])
        existing = session.get(Cashier, cashier_id)
        values = dict(
            login_id=row["login_id"].strip(),
            cashier_name=row["cashier_name"].strip(),
            password_hash=password_hash,
            role=Role(row["role"].strip()),
            is_active=_to_bool(row["is_active"]),
        )
        if existing is None:
            session.add(Cashier(cashier_id=cashier_id, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    counts["cashiers"] = len(cashier_rows)

    # ── 会員 ──
    member_rows = _read_csv("members.csv")
    for row in member_rows:
        code = row["member_code"].strip()
        existing = session.get(Member, code)
        values = dict(
            member_name=row["member_name"].strip(),
            discount_type=DiscountType(row["discount_type"].strip()),
            joined_on=_to_date(row["joined_on"]),
            is_active=_to_bool(row["is_active"]),
        )
        if existing is None:
            session.add(Member(member_code=code, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    counts["members"] = len(member_rows)

    # ── 商品 ──
    product_rows = _read_csv("products.csv")
    for row in product_rows:
        code = row["product_code"].strip()
        existing = session.get(Product, code)
        values = dict(
            product_name=row["product_name"].strip(),
            unit_price=int(row["unit_price"]),
            tax_category=TaxCategory(row["tax_category"].strip()),
            is_active=_to_bool(row["is_active"]),
        )
        if existing is None:
            session.add(Product(product_code=code, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    counts["products"] = len(product_rows)

    session.commit()
    return counts


def main() -> int:
    password = _password()
    # エンジンを先に作って接続を確認する（DATABASE_URL の不備を早く出す）
    get_engine()
    with get_session_factory()() as session:
        counts = seed(session, password=password)
    print("投入しました:")
    for table, count in counts.items():
        print(f"  {table}: {count} 件")
    print(
        "\nログイン用の担当ID: cashier01 / manager01"
        "\nパスワード: 環境変数に設定した値",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
