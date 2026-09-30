"""結合テスト §1 ログイン・認証・基盤（IT-001〜009）。

IT-001 の Cookie 部分と IT-005 は BFF（Next.js）の責務なので test_it_08_bff.py で確認する。
ここではバックエンド（B-01 /auth/token・B-02 /auth/me）を確認する。
"""

from __future__ import annotations

import csv
import re

import pytest

from tests.integration.conftest import BACKEND_DIR, DB

FIXTURES = BACKEND_DIR.parents[1] / "docs" / "test" / "fixtures"
WRONG_PASSWORD = "wrong-password-0000"  # 8バイト以上。短いと形式違反(E-VAL-001)で先に弾かれる


def _error_code(res) -> str:
    return res.json()["error"]["code"]


# IT-001：ログインの基本動作（バックエンド側）
def test_it_001_login_and_me(client, test_password):
    res = client.post("/auth/token", json={"login_id": "cashier01", "password": test_password})
    assert res.status_code == 200
    token = res.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["cashier_name"] == "山田花子"


# IT-002：パスワードは平文で保存されていない（NFR-SEC-02）
def test_it_002_password_is_hashed(db: DB, test_password):
    rows = db.fetch_all("SELECT login_id, password_hash FROM cashiers")
    assert rows
    assert [r for r in rows if r["password_hash"] == test_password] == []
    assert all(r["password_hash"].startswith("$2") for r in rows)  # bcrypt 形式


# IT-003：JWT署名鍵が未設定なら起動に失敗する（NFR-SEC-03）
def test_it_003_missing_jwt_secret_fails_startup(monkeypatch, db):
    from app.config import ConfigError, Settings

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ConfigError):
        Settings()


# IT-004（TC-15）：Cookie/トークンなしで購入確定を直接呼ぶと401
def test_it_004_unauthenticated_checkout_is_401(client, make_checkout_request, db: DB):
    from tests.integration.conftest import MEMBER, ONIGIRI

    payload = make_checkout_request(lines=[(ONIGIRI, 1)], member_code=MEMBER)
    res = client.post("/transactions", json=payload)
    assert res.status_code == 401
    assert _error_code(res) == "E-AUTH-002"
    assert db.fetch_val("SELECT COUNT(*) FROM transactions") == 0


# IT-006（TC-17）：本番設定では /docs と /openapi.json の両方が404
def test_it_006_docs_hidden_in_production(monkeypatch, db):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    with TestClient(create_app(Settings())) as prod:
        assert prod.get("/docs").status_code == 404
        assert prod.get("/openapi.json").status_code == 404


# IT-007：IDの有無でメッセージを変えない（ER-4）
def test_it_007_unknown_id_same_message_as_wrong_password(client):
    wrong_pw = client.post("/auth/token", json={"login_id": "cashier01", "password": WRONG_PASSWORD})
    unknown = client.post("/auth/token", json={"login_id": "unknown99", "password": WRONG_PASSWORD})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert _error_code(wrong_pw) == _error_code(unknown) == "E-AUTH-001"
    assert wrong_pw.json()["error"]["message"] == unknown.json()["error"]["message"]


# IT-008：無効な担当（退職者）はログインできない
def test_it_008_inactive_cashier_cannot_login(client, test_password):
    res = client.post("/auth/token", json={"login_id": "retired01", "password": test_password})
    assert res.status_code == 401
    assert _error_code(res) == "E-AUTH-001"


# IT-009：架空データであること（NFR-SEC-06）
# 「実在の個人か」は機械では判定できないので、連絡先の形をした値が無いことを機械で確かめ、
# 氏名は目視確認の結果をテスト実施記録に残す
def test_it_009_fixtures_have_no_contact_info(db: DB):
    contact = re.compile(r"@|https?://|\d{2,4}-\d{2,4}-\d{3,4}|\d{10,11}")
    for name in ("members.csv", "cashiers.csv"):
        with open(FIXTURES / name, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for key, value in row.items():
                    if key in ("member_code", "cashier_id"):
                        continue
                    assert not contact.search(value or ""), f"{name}: {key}={value}"
    names = [r["member_name"] for r in db.fetch_all("SELECT member_name FROM members")]
    assert "佐藤太郎" in names  # 投入された値が fixtures と一致していること
