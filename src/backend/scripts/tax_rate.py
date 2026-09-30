"""税率マスタの行を追加・取り消す。店長役が使う（UAT-011 / REQ-08）。

Lv2 には税率を変える管理画面がないので、このコマンドで代わりにする。
税率改定は「行の追加」で表す。既存の行は書き換えない（設計 §4.3 D-2）。

使い方（src/backend で実行）:
    .venv/bin/python -m scripts.tax_rate list
    .venv/bin/python -m scripts.tax_rate add REDUCED 2026-10-01 0.01
    .venv/bin/python -m scripts.tax_rate remove REDUCED 2026-10-01

remove はテストで追加した行を片付けるためのもの。初期値の行（2019-10-01）は消せない。
購入履歴は適用税率を値として転記しているので（D-1）、行を消しても過去の取引は変わらない。
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.database import get_session_factory
from app.enums import TaxCategory
from app.models import TaxRate

# 初期値の行。これを消すと税率が引けなくなり、会計ができなくなる
PROTECTED_FROM = date(2019, 10, 1)

USAGE = __doc__.split("使い方（src/backend で実行）:")[1].split("remove は")[0]


def _list() -> int:
    with get_session_factory()() as session:
        rows = session.scalars(select(TaxRate).order_by(TaxRate.tax_category, TaxRate.valid_from)).all()
        print("区分       適用開始日   税率     適用終了日")
        for row in rows:
            print(f"{row.tax_category.value:<10} {row.valid_from}  {row.rate}  {row.valid_to or '（現行）'}")
    return 0


def _add(category: TaxCategory, valid_from: date, rate: Decimal) -> int:
    if not Decimal("0") <= rate <= Decimal("1"):
        print("税率は 0〜1 の小数で指定してください（例 8% なら 0.08）", file=sys.stderr)
        return 1
    with get_session_factory()() as session:
        if session.get(TaxRate, (category, valid_from)) is not None:
            print(f"{category.value} {valid_from} の行は既にあります", file=sys.stderr)
            return 1
        session.add(TaxRate(tax_category=category, valid_from=valid_from, rate=rate, valid_to=None))
        session.commit()
    print(f"追加しました: {category.value} {valid_from} から {rate}")
    return _list()


def _remove(category: TaxCategory, valid_from: date) -> int:
    if valid_from == PROTECTED_FROM:
        print("初期値の行は消せません", file=sys.stderr)
        return 1
    with get_session_factory()() as session:
        row = session.get(TaxRate, (category, valid_from))
        if row is None:
            print(f"{category.value} {valid_from} の行はありません", file=sys.stderr)
            return 1
        session.delete(row)
        session.commit()
    print(f"取り消しました: {category.value} {valid_from}")
    return _list()


def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["list"]:
            return _list()
        if argv[:1] == ["add"] and len(argv) == 4:
            return _add(TaxCategory(argv[1]), date.fromisoformat(argv[2]), Decimal(argv[3]))
        if argv[:1] == ["remove"] and len(argv) == 3:
            return _remove(TaxCategory(argv[1]), date.fromisoformat(argv[2]))
    except (ValueError, InvalidOperation):
        print("区分は REDUCED か STANDARD、日付は YYYY-MM-DD、税率は小数で指定してください", file=sys.stderr)
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
