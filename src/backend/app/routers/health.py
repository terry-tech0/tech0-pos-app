"""死活監視API。設計仕様書 §5.2 B-07。

認証不要。**DBの情報は返さない**（設計 §5.2 の備考）。
バージョンや接続先を返すと、攻撃の下調べに使える情報を無認証で配ることになる。
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """生きているかだけを返す。"""
    return {"status": "ok"}
