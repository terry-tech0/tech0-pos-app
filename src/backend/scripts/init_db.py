"""テーブルを作成する。設計仕様書 §4.1 ER図 / §4.2 テーブル定義。

sql/schema.sql と同じものを SQLAlchemy のモデル定義から作る。
mysql クライアントを入れずに済むので、こちらを既定の手順にする。

使い方:
    cd src/backend
    .venv/Scripts/python.exe -m scripts.init_db

DATABASE_URL の指すスキーマ（データベース）は事前に作っておく必要がある。
スキーマごと作るなら sql/schema.sql の CREATE DATABASE を使う。
"""

from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.config import get_settings
from app.database import get_engine
from app.models import Base


def main() -> int:
    settings = get_settings()
    engine = get_engine()

    # 接続先を確認できるようにする。パスワードは出さない（設計 §7.3）
    safe_url = settings.database_url
    if "@" in safe_url:
        safe_url = safe_url.split("@", 1)[0].rsplit(":", 1)[0] + ":***@" + safe_url.split("@", 1)[1]
    print(f"接続先: {safe_url}")

    with engine.connect() as conn:
        current = conn.execute(text("SELECT DATABASE()")).scalar()
        print(f"スキーマ: {current}")

    Base.metadata.create_all(bind=engine)

    tables = sorted(inspect(engine).get_table_names())
    print(f"作成・確認したテーブル（{len(tables)}件）: {', '.join(tables)}")
    expected = {
        "cashiers",
        "members",
        "products",
        "tax_rates",
        "transactions",
        "transaction_lines",
    }
    missing = expected - set(tables)
    if missing:
        print(f"不足しているテーブル: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
