"""DB接続設定の単体テスト。DBには繋がない。"""

from __future__ import annotations

from app.database import _connect_args


def test_mysql_ssl有効なら空でないssl設定を渡す() -> None:
    # PyMySQL は `if ssl:` で判定する。空の辞書だと SSL が無効になり Azure に拒否される
    args = _connect_args("mysql+pymysql://u:p@h/db", use_ssl=True)
    assert args["ssl"]
    assert args["ssl"]["ca"].endswith(".pem")


def test_ssl無効ならssl設定を渡さない() -> None:
    assert _connect_args("mysql+pymysql://u:p@h/db", use_ssl=False) == {}


def test_sqliteにはssl設定を渡さない() -> None:
    assert _connect_args("sqlite://", use_ssl=True) == {}
