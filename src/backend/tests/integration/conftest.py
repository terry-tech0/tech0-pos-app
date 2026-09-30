"""結合テストの共通部品。テスト仕様書 03 §0.2 / §0.3。

本物の MySQL（テスト専用スキーマ）に繋ぎ、テストごとに全消し→fixtures 投入をする。

接続先の決め方:
  - 環境変数 TEST_DATABASE_URL があればそれを使う
  - 無ければ .env の DATABASE_URL のスキーマ名に `_test` を付けたものを使う
    （例: pos_terry → pos_terry_test）
  - どちらの場合も、スキーマ名が `_test` で終わらなければ実行しない。
    動作確認用のスキーマを誤って全消ししないための安全装置

パスワードは環境変数 TEST_CASHIER_PASSWORD から読む（§0.2）。未設定なら停止する。
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]

ONIGIRI = "4901234567894"  # 128円 軽減8%
MILK = "4901234567900"  # 218円 軽減8%
SOAP = "4902345678901"  # 298円 標準10%
MEMBER = "1000000001"


def _test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        base = dotenv_values(BACKEND_DIR / ".env").get("DATABASE_URL")
        if not base:
            pytest.exit("TEST_DATABASE_URL も .env の DATABASE_URL も未設定です", returncode=2)
        parsed = make_url(base)
        url = parsed.set(database=f"{parsed.database}_test").render_as_string(hide_password=False)
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.exit(f"テスト用スキーマ名は _test で終わる必要があります（{database}）", returncode=2)
    return url


def _test_password() -> str:
    password = os.getenv("TEST_CASHIER_PASSWORD") or dotenv_values(BACKEND_DIR / ".env").get(
        "TEST_CASHIER_PASSWORD"
    )
    if not password:
        pytest.exit("環境変数 TEST_CASHIER_PASSWORD が未設定です（テスト仕様書 03 §0.2）", returncode=2)
    return password


# ── 設定とエンジン。セッション全体で1つ ──

@pytest.fixture(scope="session")
def test_password() -> str:
    return _test_password()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_database_url()
    # app.config / app.database は環境変数を読んでキャッシュするので、先に差し替えてから消す
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("DB_SSL", dotenv_values(BACKEND_DIR / ".env").get("DB_SSL") or "true")
    from app.config import get_settings
    from app.database import _connect_args, get_engine, get_session_factory
    from app.models import Base

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    settings = get_settings()
    connect_args = _connect_args(url, settings.db_ssl)

    # スキーマが無ければ作る（CREATE DATABASE のためだけに、スキーマ指定なしで繋ぐ）
    parsed = make_url(url)
    server = create_engine(parsed.set(database="information_schema"), connect_args=connect_args)
    with server.begin() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{parsed.database}` "
                "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_0900_ai_ci"
            )
        )
    server.dispose()

    eng = get_engine()
    # テスト専用スキーマなので、毎回モデル定義から作り直す（列の追加にも追従させる）
    Base.metadata.drop_all(bind=eng)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    from app.database import get_session_factory

    return get_session_factory()


# ── テストごとの初期化 ──

class DB:
    """DBを直接読むためのヘルパー。保存はAPIの応答でなくDBで確かめる（§8 方針）。"""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def fetch_all(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with self._factory() as s:
            return [dict(row._mapping) for row in s.execute(text(sql), params)]

    def fetch_one(self, sql: str, **params: Any) -> dict[str, Any] | None:
        rows = self.fetch_all(sql, **params)
        return rows[0] if rows else None

    def fetch_val(self, sql: str, **params: Any) -> Any:
        with self._factory() as s:
            return s.execute(text(sql), params).scalar()

    def execute(self, sql: str, **params: Any) -> None:
        with self._factory() as s:
            s.execute(text(sql), params)
            s.commit()


@pytest.fixture
def db(session_factory: sessionmaker[Session], test_password: str) -> DB:
    """テスト用DBを初期化し、fixtures のCSVを投入する（§0.3）。"""
    from app import deps
    from app.models import Transaction, TransactionLine
    from scripts.seed import seed

    with session_factory() as s:
        # seed() は履歴があると全消しをしない作りなので、履歴を先に消す
        s.execute(delete(TransactionLine))
        s.execute(delete(Transaction))
        s.commit()
        seed(s, password=test_password)

    # ログイン失敗回数のカウンタもテストごとに戻す
    deps._limiter = None
    return DB(session_factory)


@pytest.fixture
def app(db: DB):
    from app.config import get_settings
    from app.main import create_app

    return create_app(get_settings())


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


LoginFn = Callable[..., TestClient]


@pytest.fixture
def login(client: TestClient, test_password: str) -> LoginFn:
    """ログインして Bearer トークン付きのクライアントを返す（§0.3 login）。

    BFF は Cookie を Bearer に詰め替えてバックエンドを呼ぶ。
    ここではバックエンドを直接呼ぶので、Bearer を付けたクライアントを返す。
    """

    def _login(login_id: str = "cashier01", password: str | None = None) -> TestClient:
        res = client.post(
            "/auth/token", json={"login_id": login_id, "password": password or test_password}
        )
        assert res.status_code == 200, res.text
        client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        return client

    return _login


@pytest.fixture
def logged_in_client(login: LoginFn) -> TestClient:
    return login("cashier01")


@pytest.fixture
def insert_tax_rate(db: DB) -> Callable[[str, str, str], None]:
    """税率マスタに1行追加する（§0.3。IT-060〜063 用）。コードは一切変えない。"""

    def _insert(category: str, valid_from: str, rate: str) -> None:
        db.execute(
            "INSERT INTO tax_rates (tax_category, valid_from, valid_to, rate) "
            "VALUES (:c, :f, NULL, :r)",
            c=category,
            f=valid_from,
            r=rate,
        )

    return _insert


@pytest.fixture
def make_checkout_request(db: DB) -> Callable[..., dict[str, Any]]:
    """画面と同じ計算をして client_amount を含む正しいリクエストを作る（§0.3）。

    単価・税率・割引区分はDBのマスタから引く。on_date は税率の基準日。
    """
    from app.enums import TaxCategory
    from app.services.amount_calculator import AmountCalculator, CalcLine

    def _make(
        lines: list[tuple[str, int]],
        member_code: str | None = None,
        on_date: date | None = None,
    ) -> dict[str, Any]:
        on_date = on_date or date.today()
        rates: dict[TaxCategory, Decimal] = {}
        for row in db.fetch_all(
            "SELECT tax_category, rate FROM tax_rates "
            "WHERE valid_from <= :d AND (valid_to IS NULL OR valid_to >= :d) "
            "ORDER BY valid_from",
            d=on_date,
        ):
            rates[TaxCategory(row["tax_category"])] = Decimal(row["rate"])

        calc_lines = []
        for code, qty in lines:
            product = db.fetch_one(
                "SELECT unit_price, tax_category FROM products WHERE product_code = :c", c=code
            )
            assert product is not None, code
            calc_lines.append(
                CalcLine(
                    unit_price=product["unit_price"],
                    quantity=qty,
                    tax_category=TaxCategory(product["tax_category"]),
                )
            )

        is_member = False
        if member_code is not None:
            member = db.fetch_one(
                "SELECT discount_type FROM members WHERE member_code = :c AND is_active = 1",
                c=member_code,
            )
            is_member = member is not None and member["discount_type"] == "RATE5"

        amount = AmountCalculator().calculate(calc_lines, is_member, rates)
        return {
            "checkout_id": str(uuid.uuid4()),
            "member_code": member_code,
            "lines": [{"product_code": code, "quantity": qty} for code, qty in lines],
            "client_amount": {
                "subtotal": amount.subtotal,
                "discount": amount.discount,
                "tax_reduced": amount.tax_reduced,
                "tax_standard": amount.tax_standard,
                "total": amount.total,
            },
        }

    return _make
