"""UAT-014（明細100行）用の架空テスト商品を100種類追加する。

fixtures の商品は有効なものが46種類しかなく、「異なる商品を101種類読む」が実施できない。
単価100円・軽減税率の商品を100種類入れる。100種類すべて読むと税抜 10,000円／税込 10,800円。
101種類目には fixtures の商品（おにぎり等）を使う。

コードは 4999990000001〜4999990000100（13桁）。何度流しても同じ結果になる（既存なら更新）。

使い方（src/backend で実行）:
    .venv/bin/python -m scripts.seed_uat_products
"""

from __future__ import annotations

from app.database import get_session_factory
from app.enums import TaxCategory
from app.models import Product

COUNT = 100
CODE_PREFIX = "4999990000"  # 10桁 + 3桁の連番 = 13桁


def codes() -> list[str]:
    return [f"{CODE_PREFIX}{n:03d}" for n in range(1, COUNT + 1)]


def main() -> int:
    with get_session_factory()() as session:
        for n, code in enumerate(codes(), start=1):
            values = dict(
                product_name=f"【UAT】テスト商品{n:03d}",
                unit_price=100,
                tax_category=TaxCategory.REDUCED,
                is_active=True,
            )
            existing = session.get(Product, code)
            if existing is None:
                session.add(Product(product_code=code, **values))
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
        session.commit()
    print(f"UAT用の商品を {COUNT} 件入れました: {codes()[0]} 〜 {codes()[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
