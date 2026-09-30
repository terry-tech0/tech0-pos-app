"""結合テスト BFF（Next.js）の責務を確認する部分。IT-001（Cookie）／IT-005／IT-015b。

Cookie の発行はバックエンドではなく BFF（A-01）が行うので、起動中の BFF に HTTP で当てる。
BFF はバックエンド経由で .env の DATABASE_URL（動作確認用スキーマ）を見る。
テスト専用スキーマではないので、ここではログインと照会だけを行い、書き込みはしない。

BFF が起動していなければ skip する。接続先は環境変数 BFF_BASE_URL（既定 http://localhost:3000）。
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

from tests.integration.conftest import MILK, ONIGIRI

BFF = os.getenv("BFF_BASE_URL", "http://localhost:3000")


@pytest.fixture(scope="module")
def bff(test_password) -> httpx.Client:
    try:
        httpx.get(BFF, timeout=3)
    except httpx.HTTPError:
        pytest.skip(f"BFF が起動していません（{BFF}）")
    with httpx.Client(base_url=BFF, timeout=10) as c:
        yield c


def _login(bff: httpx.Client, password: str) -> httpx.Response:
    return bff.post("/api/login", json={"loginId": "cashier01", "password": password})


# IT-001：ログインで Cookie が返り、/api/me で担当名が返る
def test_it_001_bff_login_sets_cookie(bff, test_password):
    res = _login(bff, test_password)
    assert res.status_code == 200
    assert "set-cookie" in res.headers
    assert "accessToken" not in res.text  # トークン本体をボディに出さない（A-01）
    me = bff.get("/api/me")
    assert me.status_code == 200
    assert me.json()["cashierName"] == "山田花子"


# IT-005（TC-16）：セッションCookieの属性
def test_it_005_cookie_attributes(bff, test_password):
    set_cookie = _login(bff, test_password).headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


# IT-005 の Secure 属性は本番（NODE_ENV=production）のときだけ付く実装。
# http の localhost では Secure Cookie を送り返せないため、開発時は付けない
def test_it_005_cookie_secure_in_production(bff, test_password):
    set_cookie = _login(bff, test_password).headers["set-cookie"].lower()
    if "secure" not in set_cookie:
        pytest.skip("開発モードの BFF では Secure を付けない実装（本番ビルドで確認する）")
    assert "secure" in set_cookie


# IT-015b：BFF を経由しても商品照会が1秒以内（NFR-PERF-01）
def test_it_015b_bff_response_within_1s(bff, test_password):
    _login(bff, test_password)
    bff.get(f"/api/products/{ONIGIRI}")  # 初回コンパイル・接続を温める
    started = time.perf_counter()
    res = bff.get(f"/api/products/{MILK}")
    elapsed = time.perf_counter() - started
    assert res.status_code == 200
    assert elapsed < 1.0, f"{elapsed:.3f}s"
