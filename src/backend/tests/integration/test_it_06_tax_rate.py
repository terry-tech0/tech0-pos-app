"""結合テスト §7 税率可変（IT-060〜063）。REQ-08。

合格基準は「プログラムを1行も修正せず、マスタの変更だけで税率が変わること」。
システム日付は freezegun で固定する。ログイン（JWTの発行時刻）も固定した日付の中で行う。
固定した日付の外で発行したトークンは、固定後の時刻から見て期限切れになるため。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from freezegun import freeze_time

from tests.integration.conftest import DB, ONIGIRI


def _checkout_onigiri(login, make_checkout_request, on: date) -> dict:
    client = login("cashier01")
    payload = make_checkout_request(lines=[(ONIGIRI, 1)], member_code=None, on_date=on)
    res = client.post("/transactions", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


# IT-060（TC-05）：税率マスタに1行追加するだけで新税率が適用される
def test_it_060_tax_rate_change_without_code_change(login, make_checkout_request, insert_tax_rate):
    insert_tax_rate("REDUCED", "2027-04-01", "0.0100")
    with freeze_time("2027-04-01"):
        body = _checkout_onigiri(login, make_checkout_request, date(2027, 4, 1))
    assert body["amount"]["tax_reduced"] == 1  # 128 × 0.01 = 1.28 → 1
    assert body["amount"]["total"] == 129


# IT-061：改定日の前日は旧税率
def test_it_061_day_before_uses_old_rate(login, make_checkout_request, insert_tax_rate):
    insert_tax_rate("REDUCED", "2027-04-01", "0.0100")
    with freeze_time("2027-03-31"):
        body = _checkout_onigiri(login, make_checkout_request, date(2027, 3, 31))
    assert Decimal(str(body["lines"][0]["applied_tax_rate"])) == Decimal("0.08")
    assert body["amount"]["tax_reduced"] == 10
    assert body["amount"]["total"] == 138


# IT-062：改定日当日から新税率（商品照会の税率も切り替わる）
def test_it_062_effective_day_uses_new_rate(login, make_checkout_request, insert_tax_rate):
    insert_tax_rate("REDUCED", "2027-04-01", "0.0100")
    with freeze_time("2027-04-01"):
        body = _checkout_onigiri(login, make_checkout_request, date(2027, 4, 1))
        product = login("cashier01").get(f"/products/{ONIGIRI}").json()
    assert Decimal(str(body["lines"][0]["applied_tax_rate"])) == Decimal("0.01")
    assert Decimal(str(product["tax_rate"])) == Decimal("0.01")


# IT-063（TC-06）：改定前の取引の適用税率は 0.08 のまま
def test_it_063_past_transaction_keeps_rate(login, make_checkout_request, insert_tax_rate, db: DB):
    with freeze_time("2027-03-31"):
        before = _checkout_onigiri(login, make_checkout_request, date(2027, 3, 31))
    insert_tax_rate("REDUCED", "2027-04-01", "0.0100")
    with freeze_time("2027-04-01"):
        _checkout_onigiri(login, make_checkout_request, date(2027, 4, 1))
    rate = db.fetch_val(
        "SELECT applied_tax_rate FROM transaction_lines WHERE transaction_id = :t",
        t=before["transaction_id"],
    )
    assert rate == Decimal("0.0800")
