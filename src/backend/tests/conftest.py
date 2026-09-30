"""pytest の共通設定。

単体テスト（tests/unit）は **DBを使わない**（テスト仕様書 §1.2）。
ただし app.config が DATABASE_URL と JWT_SECRET_KEY を必須にしているため、
import が通るようにダミー値を入れる。実際に接続はしない。

結合テスト（tests/integration）は本物のテスト用DBを使う。
そちらは環境変数 TEST_DATABASE_URL と TEST_CASHIER_PASSWORD を要求する
（未設定なら実行せず停止する。テスト仕様書 §4）。
"""

from __future__ import annotations

import os

import pytest

# app.config を import する前に入れる必要があるので、モジュール読み込み時に設定する
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://unit:test@127.0.0.1/unit_test_not_connected")
os.environ.setdefault("JWT_SECRET_KEY", "unit-test-only-secret-key-do-not-use-in-production-0001")
os.environ.setdefault("JWT_ISSUER", "tech0-pos-app")
os.environ.setdefault("APP_ENV", "local")


@pytest.fixture
def settings():
    """テスト用の設定。"""
    from app.config import Settings

    return Settings()
