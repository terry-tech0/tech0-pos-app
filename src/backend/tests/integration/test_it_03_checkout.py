"""結合テスト §4 購入確定の入力検証（IT-030〜038）。"""

from __future__ import annotations

from tests.integration.conftest import DB, MEMBER, MILK, ONIGIRI, SOAP


def _error_code(res) -> str:
    return res.json()["error"]["code"]


def _amount_tuple(amount: dict) -> tuple[int, int, int, int, int]:
    return (
        amount["subtotal"],
        amount["discount"],
        amount["tax_reduced"],
        amount["tax_standard"],
        amount["total"],
    )


# IT-030（TC-01）：会員・税率混在。UT-BE-001・UT-FE-040 と同じ入力・同じ期待値
def test_it_030_checkout_member_mixed_tax(logged_in_client, make_checkout_request):
    payload = make_checkout_request(lines=[(ONIGIRI, 2), (MILK, 1), (SOAP, 1)], member_code=MEMBER)
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 201, res.text
    assert _amount_tuple(res.json()["amount"]) == (772, 38, 36, 28, 798)


# IT-031（TC-02）：非会員
def test_it_031_checkout_non_member(logged_in_client, make_checkout_request):
    payload = make_checkout_request(lines=[(ONIGIRI, 2), (MILK, 1), (SOAP, 1)], member_code=None)
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 201, res.text
    assert _amount_tuple(res.json()["amount"]) == (772, 0, 37, 29, 838)


# IT-032 / IT-033（TC-07）：数量の下端1・上端99
def test_it_032_quantity_min(logged_in_client, make_checkout_request):
    res = logged_in_client.post("/transactions", json=make_checkout_request(lines=[(ONIGIRI, 1)]))
    assert res.status_code == 201, res.text


def test_it_033_quantity_max(logged_in_client, make_checkout_request):
    res = logged_in_client.post("/transactions", json=make_checkout_request(lines=[(ONIGIRI, 99)]))
    assert res.status_code == 201, res.text


# IT-034 / IT-035（TC-08）：数量の範囲外は E-VAL-002（500にならない）
def test_it_034_quantity_zero(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=[(ONIGIRI, 1)])
    payload["lines"][0]["quantity"] = 0
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 400
    assert _error_code(res) == "E-VAL-002"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0


def test_it_035_quantity_100(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=[(ONIGIRI, 1)])
    payload["lines"][0]["quantity"] = 100
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 400
    assert _error_code(res) == "E-VAL-002"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0


# IT-036 / IT-037（TC-09）：明細100行は通り、101行は E-VAL-003
def test_it_036_lines_100(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=[(ONIGIRI, 1)] * 100)
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 201, res.text
    assert db.fetch_val("SELECT COUNT(*) FROM transaction_lines") == 100


def test_it_037_lines_101(logged_in_client, make_checkout_request, db: DB):
    payload = make_checkout_request(lines=[(ONIGIRI, 1)] * 101)
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 400
    assert _error_code(res) == "E-VAL-003"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0


# IT-038（TC-10）：明細0件は E-TXN-002
def test_it_038_no_lines(logged_in_client, db: DB):
    payload = {
        "member_code": None,
        "lines": [],
        "client_amount": {"subtotal": 0, "discount": 0, "tax_reduced": 0, "tax_standard": 0, "total": 0},
    }
    res = logged_in_client.post("/transactions", json=payload)
    assert res.status_code == 400
    assert _error_code(res) == "E-TXN-002"
    assert res.json()["error"]["message"] == "商品が登録されていません"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0
