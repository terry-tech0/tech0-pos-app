/**
 * 購入リスト操作の単体テスト。
 * 対応: テスト仕様書 02-単体テスト-frontend-jest.md（UT-FE-001〜026）／要件 F-03 / F-05 / F-06
 */

import {
  LINE_COUNT_MAX,
  QUANTITY_MAX,
  addProduct,
  canCheckout,
  changeQuantity,
  clearCart,
  removeLine,
  toRequestLines,
} from "@/lib/cart";
import type { CartLine, Product } from "@/types/pos";

function product(code: string, price = 100, category: Product["taxCategory"] = "REDUCED"): Product {
  return {
    productCode: code,
    productName: `架空商品${code}`,
    unitPrice: price,
    taxCategory: category,
    taxRate: category === "REDUCED" ? 0.08 : 0.1,
  };
}

function expectOk(result: ReturnType<typeof addProduct>): CartLine[] {
  if (!result.ok) {
    throw new Error(`失敗した: ${result.code}`);
  }
  return result.lines;
}

describe("addProduct", () => {
  test("UT-FE-001 空のリストに1件追加できる", () => {
    const lines = expectOk(addProduct([], product("49012345")));
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(1);
  });

  test("UT-FE-003 同一商品を2回スキャンすると行が増えず数量が2になる（F-03）", () => {
    let lines = expectOk(addProduct([], product("49012345")));
    lines = expectOk(addProduct(lines, product("49012345")));
    expect(lines).toHaveLength(1);
    expect(lines[0].quantity).toBe(2);
  });

  test("確認事項 T-5: 8桁と13桁は別商品として扱う", () => {
    let lines = expectOk(addProduct([], product("49012345")));
    lines = expectOk(addProduct(lines, product("4901234567894")));
    expect(lines).toHaveLength(2);
  });

  test("元の配列を書き換えない（Reactが変更を検知できるようにするため）", () => {
    const original: CartLine[] = [];
    addProduct(original, product("49012345"));
    expect(original).toHaveLength(0);
  });

  test("数量加算の結果が99を超えると追加せず E-VAL-002（リストは維持）", () => {
    const lines: CartLine[] = [
      { productCode: "49012345", productName: "x", unitPrice: 100, quantity: 99, taxCategory: "REDUCED" },
    ];
    const result = addProduct(lines, product("49012345"));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe("E-VAL-002");
      // ER-1: エラーで購入リストを消さない
      expect(result.lines).toHaveLength(1);
      expect(result.lines[0].quantity).toBe(99);
    }
  });

  test("明細100行目は追加できる（境界の内側）", () => {
    const lines: CartLine[] = Array.from({ length: LINE_COUNT_MAX - 1 }, (_, i) => ({
      productCode: `1000000${String(i).padStart(4, "0")}`,
      productName: "x",
      unitPrice: 100,
      quantity: 1,
      taxCategory: "REDUCED" as const,
    }));
    const result = addProduct(lines, product("9999999999999"));
    expect(result.ok).toBe(true);
    expect(expectOk(result)).toHaveLength(LINE_COUNT_MAX);
  });

  test("明細101行目は E-VAL-003（境界の外側）", () => {
    const lines: CartLine[] = Array.from({ length: LINE_COUNT_MAX }, (_, i) => ({
      productCode: `1000000${String(i).padStart(4, "0")}`,
      productName: "x",
      unitPrice: 100,
      quantity: 1,
      taxCategory: "REDUCED" as const,
    }));
    const result = addProduct(lines, product("9999999999999"));
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe("E-VAL-003");
      expect(result.lines).toHaveLength(LINE_COUNT_MAX);
    }
  });
});

describe("changeQuantity（F-06）", () => {
  const lines: CartLine[] = [
    { productCode: "49012345", productName: "x", unitPrice: 100, quantity: 1, taxCategory: "REDUCED" },
  ];

  test.each([
    ["UT-FE-011 下限1は受け付ける", 1, true],
    ["UT-FE-012 上限99は受け付ける", QUANTITY_MAX, true],
    ["UT-FE-013 0は受け付けない（削除とは別物）", 0, false],
    ["UT-FE-014 100は受け付けない", 100, false],
    ["負数は受け付けない", -1, false],
    ["小数は受け付けない", 2.5, false],
  ])("%s", (_name, quantity, shouldSucceed) => {
    const result = changeQuantity(lines, "49012345", quantity as number);
    expect(result.ok).toBe(shouldSucceed);
    if (!result.ok) {
      expect(result.code).toBe("E-VAL-002");
      // 変更前の数量に戻る（設計 §7.1 E-VAL-002 の画面の挙動）
      expect(result.lines[0].quantity).toBe(1);
    }
  });

  test("存在しない商品コードを指定しても落ちない", () => {
    const result = changeQuantity(lines, "00000000", 5);
    expect(result.ok).toBe(true);
  });
});

describe("removeLine / clearCart / canCheckout", () => {
  const lines: CartLine[] = [
    { productCode: "A", productName: "x", unitPrice: 100, quantity: 1, taxCategory: "REDUCED" },
    { productCode: "B", productName: "y", unitPrice: 200, quantity: 1, taxCategory: "STANDARD" },
  ];

  test("指定した行だけ消える", () => {
    expect(removeLine(lines, "A").map((l) => l.productCode)).toEqual(["B"]);
  });

  test("clearCart は空にする（F-11 購入後の再開）", () => {
    expect(clearCart()).toHaveLength(0);
  });

  test("UT-FE-033 明細0件では購入ボタンを押せない（E-TXN-002 を出す前に止める）", () => {
    expect(canCheckout([])).toBe(false);
    expect(canCheckout(lines)).toBe(true);
  });
});

describe("toRequestLines", () => {
  test("単価も税率も送らない（サーバがマスタから引く。設計 §5.4 A-07）", () => {
    const lines: CartLine[] = [
      { productCode: "A", productName: "x", unitPrice: 100, quantity: 2, taxCategory: "REDUCED" },
    ];
    const body = toRequestLines(lines);
    expect(body).toEqual([{ productCode: "A", quantity: 2 }]);
    // unitPrice が混ざっていないことを明示的に確認する（TC-14 の画面側）
    expect(Object.keys(body[0])).toEqual(["productCode", "quantity"]);
  });
});
