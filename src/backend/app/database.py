"""DB接続。設計仕様書 §2.2（FastAPI⇄MySQL の境界）。

SQLAlchemy を使うのは、パラメータバインドが既定で、
文字列連結SQLを書かせない仕組みになるため（設計 §8.8 SQLインジェクション対策）。

エンジンは最初に必要になったときだけ作る（遅延初期化）。
import した瞬間に DATABASE_URL を要求すると、DBを使わない単体テストが動かなくなる。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterator

import certifi

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _connect_args(database_url: str, use_ssl: bool) -> dict[str, Any]:
    """ドライバに渡す追加の接続設定を組む。

    Azure Database for MySQL は SSL 必須（設計 §2.4 の DATABASE_URL の備考）。
    PyMySQL では ssl に辞書を渡すと SSL で繋ぐ。
    ただし空の辞書は不可。PyMySQL は `if ssl:` で判定するため、{} は偽とみなされ
    SSL なしで繋ぎに行き、Azure に拒否される（エラー3159。2026-09-30 実DB接続で判明）。
    CA には certifi の証明書束を渡し、サーバ証明書の検証もする。

    ローカルの MySQL や SQLite では SSL を使わないので、DB_SSL=false で外せる。
    """
    if not use_ssl:
        return {}
    if not database_url.startswith("mysql"):
        # SQLite 等に ssl を渡すと落ちるので、MySQL のときだけ付ける
        return {}
    return {"ssl": {"ca": certifi.where()}}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """接続プールを1つだけ作る。"""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        connect_args=_connect_args(settings.database_url, settings.db_ssl),
        # 接続が切れていたら捨てて張り直す。
        # Azure MySQL は一定時間アイドルの接続を切るため、これが無いと初回が失敗する
        pool_pre_ping=True,
        pool_recycle=280,
        future=True,
        echo=False,  # SQLをログに出さない（値が混ざると個人情報がログに乗る。設計 §7.3）
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI の依存関数。リクエストごとにセッションを開いて必ず閉じる。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
