"""結合テスト §6 金額照合（IT-050〜053）。★セキュリティの中核。

設計 §8.6「Backendでも計算のロジックを入れて、Frontendの計算値と照合」の検証。
攻撃が「失敗すること」を確かめる。成功してしまったらテストが落ちる。
"""

from __future__ import annotations

from tests.integration.conftest import DB, MEMBER, MILK, ONIGIRI, SOAP

BASIC_LINES = [(ONIGIRI, 2), (MILK, 1), (SOAP, 1)]


# IT-050（TC-13）：合計を0に改ざんしても保存されない
def test_it_050_tampered_total_rejected(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
    payload["client_amount"]["total"] = 0
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "E-TXN-001"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0


# IT-051（TC-14）：明細に単価を混ぜても無視され、マスタの単価で計算される
def test_it_051_client_price_ignored(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
    for line in payload["lines"]:
        line["unit_price"] = 1
        line["unitPrice"] = 1
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 201, res.text
    assert res.json()["amount"]["total"] == 798
    assert db.fetch_val(
        "SELECT unit_price FROM transaction_lines WHERE product_code = :c", c=ONIGIRI
    ) == 128


# IT-052：5項目すべてを照合する（discount だけ1円ずらしても拒否）
def test_it_052_all_five_fields_checked(logged_in_client, make_checkout_request, db: DB):
    for field in ("subtotal", "discount", "tax_reduced", "tax_standard", "total"):
        payload = make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
        payload["client_amount"][field] += 1
        res = logged_in_client.post("/transactions", json=payload)
        assert res.status_code == 400, field
        assert res.json()["error"]["code"] == "E-TXN-001", field
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0


# IT-053：拒否の応答にサーバの計算値が入っている（ER-5）
def test_it_053_server_amount_returned(logged_in_client, make_checkout_request):
    payload = make_checkout_request(lines=BASIC_LINES, member_code=MEMBER)
    payload["client_amount"]["total"] = 0
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 400
    assert res.json()["error"]["details"]["serverAmount"] == {
        "subtotal": 772,
        "discount": 38,
        "taxReduced": 36,
        "taxStandard": 28,
        "total": 798,
    }
