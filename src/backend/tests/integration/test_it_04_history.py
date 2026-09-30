"""結合テスト §5 購入履歴の保存（IT-040〜047）。

保存はAPIの応答ではなく、DBを直接読んで確かめる（仕様書 §8 方針）。
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import event

from tests.integration.conftest import DB, MEMBER, MILK, ONIGIRI, SOAP

BASIC_LINES = [(ONIGIRI, 2), (MILK, 1), (SOAP, 1)]


def _checkout(client, make_checkout_request, member_code=MEMBER):
    res = client.post("/transactions", json=make_checkout_request(lines=BASIC_LINES, member_code=member_code))
    assert res.status_code == 201, res.text
    return res.json()


# IT-040（TC-01）：ヘッダ1件・明細3件が保存される（REQ-07）
def test_it_040_saved(logged_in_client, make_checkout_request, db: DB):
    _checkout(logged_in_client, make_checkout_request)
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 1
    assert db.fetch_val("SELECT COUNT(*) FROM transaction_lines") == 3


# IT-041（TC-04）：保存額が画面の金額と一致
def test_it_041_saved_amounts(logged_in_client, make_checkout_request, db: DB):
    _checkout(logged_in_client, make_checkout_request)
    saved = db.fetch_one(
        "SELECT subtotal, discount_amount, tax_reduced, tax_standard, total FROM transactions"
    )
    assert saved == {
        "subtotal": 772,
        "discount_amount": 38,
        "tax_reduced": 36,
        "tax_standard": 28,
        "total": 798,
    }


# IT-042（TC-19）：同じ確定リクエストを連続2回送っても、取引は1件だけ（設計 v1.1 D-7）
# 2回目は保存せず、保存済みの取引を 200 で返す
def test_it_042_double_submit(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
    first = logged_in_client.post("/transactions", json=payload)
    second = logged_in_client.post("/transactions", json=payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["transaction_id"] == first.json()["transaction_id"]
    assert second.json()["amount"] == first.json()["amount"]
    assert len(second.json()["lines"]) == 3
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 1
    assert db.fetch_val("SELECT COUNT(*) FROM transaction_lines") == 3


# IT-042 補足：ほぼ同時の二重送信。事前の判定をすり抜けても、一意制約で2件目を止める
def test_it_042b_double_submit_race(logged_in_client, make_checkout_request, db: DB, monkeypatch):
    from app.repositories import TransactionRepository

    payload = make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
    first = logged_in_client.post("/transactions", json=payload)
    assert first.status_code == 201

    # 2回目の最初の判定だけ「まだ保存されていない」と見せる（同時に届いた状況の再現）
    original = TransactionRepository.find_by_checkout_id
    calls = {"n": 0}

    def _first_miss(self, checkout_id):
        calls["n"] += 1
        return None if calls["n"] == 1 else original(self, checkout_id)

    monkeypatch.setattr(TransactionRepository, "find_by_checkout_id", _first_miss)
    second = logged_in_client.post("/transactions", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["transaction_id"] == first.json()["transaction_id"]
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 1


# IT-042 補足：別の会計（整理番号が違う）は、同じ内容でも別の取引として保存される
def test_it_042c_different_checkout_ids_are_separate(logged_in_client, make_checkout_request, db: DB):
    for _ in range(2):
        res = logged_in_client.post(
            "/transactions", json=make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
        )
        assert res.status_code == 201
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 2


# IT-043：明細は商品名・単価・適用税率を値として転記している（D-1 / P-3）
def test_it_043_lines_are_copied(logged_in_client, make_checkout_request, db: DB):
    _checkout(logged_in_client, make_checkout_request)
    line = db.fetch_one(
        "SELECT product_name, unit_price, applied_tax_rate FROM transaction_lines "
        "WHERE product_code = :c",
        c=ONIGIRI,
    )
    assert line == {"product_name": "おにぎり 鮭", "unit_price": 128, "applied_tax_rate": Decimal("0.0800")}


# IT-044：マスタを値上げしても過去の明細は変わらない（B-6 / P-3）
def test_it_044_history_is_immutable(logged_in_client, make_checkout_request, db: DB):
    _checkout(logged_in_client, make_checkout_request)
    db.execute("UPDATE products SET unit_price = 200 WHERE product_code = :c", c=ONIGIRI)
    line = db.fetch_one(
        "SELECT unit_price, line_amount FROM transaction_lines WHERE product_code = :c", c=ONIGIRI
    )
    assert line == {"unit_price": 128, "line_amount": 256}


# IT-045：非会員は member_code が NULL、割引0（D-3）
def test_it_045_non_member_saved_as_null(logged_in_client, make_checkout_request, db: DB):
    _checkout(logged_in_client, make_checkout_request, member_code=None)
    saved = db.fetch_one("SELECT member_code, discount_amount FROM transactions")
    assert saved == {"member_code": None, "discount_amount": 0}


# IT-046：明細の保存で失敗したら、ヘッダも残らない
def test_it_046_rollback_on_line_failure(app, login, make_checkout_request, db: DB, test_password):
    from app.models import TransactionLine

    def _fail(mapper, connection, target):
        raise RuntimeError("IT-046: 明細の保存を意図的に失敗させる")

    event.listen(TransactionLine, "before_insert", _fail)
    try:
        # 想定外の例外は E-SYS-001 で返す作りなので、TestClient に例外を再送出させない
        with TestClient(app, raise_server_exceptions=False) as c:
            token = c.post(
                "/auth/token", json={"login_id": "cashier01", "password": test_password}
            ).json()["access_token"]
            res = c.post(
                "/transactions",
                json=make_checkout_request(lines=BASIC_LINES, member_code=MEMBER),
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        event.remove(TransactionLine, "before_insert", _fail)

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "E-SYS-001"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0
    assert db.fetch_val("SELECT COUNT(*) FROM transaction_lines") == 0


# IT-047：購入履歴を更新・削除するAPIが存在しない（NFR-OPS-05 / D-5）
def test_it_047_no_update_or_delete_api(app, logged_in_client, make_checkout_request):
    tid = _checkout(logged_in_client, make_checkout_request)["transaction_id"]
    for method in ("put", "patch", "delete"):
        res = getattr(logged_in_client, method)(f"/transactions/{tid}")
        assert res.status_code in (404, 405), (method, res.status_code)
    # ルート定義の上でも、/transactions に GET/POST 以外が無いこと
    methods = {
        m
        for route in app.routes
        if getattr(route, "path", "").startswith("/transactions")
        for m in getattr(route, "methods", set())
    }
    assert methods <= {"POST"}
