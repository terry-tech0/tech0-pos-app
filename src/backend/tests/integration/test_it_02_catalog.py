"""結合テスト §2 商品照会（IT-010〜015）／§3 会員照会（IT-020〜025）。"""

from __future__ import annotations

import time
from decimal import Decimal
from urllib.parse import quote

from tests.integration.conftest import DB, MILK, ONIGIRI, SOAP


def _error_code(res) -> str:
    return res.json()["error"]["code"]


# ── §2 商品照会 ──

# IT-010：13桁と8桁の両方が通る
def test_it_010_product_13_and_8_digits(logged_in_client):
    for code in ("4901234567894", "45678901"):
        res = logged_in_client.get(f"/products/{code}")
        assert res.status_code == 200, code
        body = res.json()
        assert body["product_code"] == code
        assert body["product_name"]
        assert body["unit_price"] > 0
        assert body["tax_category"] == "REDUCED"
        assert Decimal(str(body["tax_rate"])) == Decimal("0.08")


# IT-011（TC-11）：マスタ未登録
def test_it_011_unknown_product(logged_in_client):
    res = logged_in_client.get("/products/4909999999999")
    assert res.status_code == 404
    assert _error_code(res) == "E-PROD-001"
    assert res.json()["error"]["message"] == "商品がマスタ未登録です"


# IT-012（TC-18）：SQLインジェクションが通らない
def test_it_012_sql_injection_rejected(logged_in_client):
    res = logged_in_client.get("/products/" + quote("4567890' OR '1'='1", safe=""))
    assert res.status_code == 400
    assert _error_code(res) == "E-VAL-001"
    assert "product_name" not in res.text  # 商品が返っていない


# IT-013：取扱終了商品は照会できない
def test_it_013_inactive_product(logged_in_client):
    res = logged_in_client.get("/products/4904567890123")
    assert res.status_code == 404
    assert _error_code(res) == "E-PROD-001"


# IT-014：8桁と13桁の間（9桁）は形式違反
def test_it_014_nine_digits_rejected(logged_in_client):
    res = logged_in_client.get("/products/456789012")
    assert res.status_code == 400
    assert _error_code(res) == "E-VAL-001"


# IT-015：応答1秒以内（NFR-PERF-01）。バックエンド単体の時間。BFF込みは IT-015b で見る
def test_it_015_response_within_1s(logged_in_client):
    logged_in_client.get(f"/products/{ONIGIRI}")  # 接続プールを温める
    started = time.perf_counter()
    res = logged_in_client.get(f"/products/{MILK}")
    elapsed = time.perf_counter() - started
    assert res.status_code == 200
    assert elapsed < 1.0, f"{elapsed:.3f}s"


# ── §3 会員照会 ──

# IT-020：正常系
def test_it_020_member_found(logged_in_client):
    res = logged_in_client.get("/members/1000000001")
    assert res.status_code == 200
    assert res.json()["member_name"] == "佐藤太郎"
    assert res.json()["is_discount_target"] is True


# IT-021（TC-12）：9桁は照会しない
def test_it_021_member_nine_digits(logged_in_client):
    res = logged_in_client.get("/members/100000000")
    assert res.status_code == 400
    assert _error_code(res) == "E-VAL-001"


# IT-022：未登録
def test_it_022_member_not_found(logged_in_client):
    res = logged_in_client.get("/members/1999999999")
    assert res.status_code == 404
    assert _error_code(res) == "E-MEMB-001"


# IT-023：退会済み
def test_it_023_member_inactive(logged_in_client):
    res = logged_in_client.get("/members/1000000003")
    assert res.status_code == 404
    assert _error_code(res) == "E-MEMB-001"


# IT-024：割引区分 NONE の会員は割引対象ではない
def test_it_024_member_discount_none(logged_in_client):
    res = logged_in_client.get("/members/1000000004")
    assert res.status_code == 200
    assert res.json()["member_name"]
    assert res.json()["is_discount_target"] is False


# IT-025：NONE 会員の会計は非会員と同額
def test_it_025_member_none_checkout(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(
        lines=[(ONIGIRI, 2), (MILK, 1), (SOAP, 1)], member_code="1000000004"
    )
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 201, res.text
    amount = res.json()["amount"]
    assert (amount["subtotal"], amount["discount"], amount["total"]) == (772, 0, 838)
    saved = db.fetch_one("SELECT member_code, discount_amount, total FROM transactions")
    assert saved == {"member_code": "1000000004", "discount_amount": 0, "total": 838}
