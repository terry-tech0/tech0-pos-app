/**
 * 画面側の金額計算の単体テスト。
 * 対応: テスト仕様書 02-単体テスト-frontend-jest.md（UT-FE-040 系）／設計 §4.4
 *
 * ★ここの入力と期待値は、バックエンドの tests/unit/test_amount_calculator.py と
 *   **まったく同じ**にしている（テスト仕様書 §1.3）。
 *   どちらかの実装がずれたら、必ずどちらかのテストが落ちる。
 */

import { calculateAmount, lineAmountOf, taxOf, taxRateLabel } from "@/lib/amount";
import type { CartLine, TaxRateMap } from "@/types/pos";

/** 現行の税率（fixtures/tax_rates.csv と同じ） */
const RATES: TaxRateMap = { REDUCED: 0.08, STANDARD: 0.1 };

function line(unitPrice: number, quantity: number, taxCategory: CartLine["taxCategory"]): CartLine {
  return { productCode: `${unitPrice}`, productName: "架空商品", unitPrice, quantity, taxCategory };
}

/** 設計 §4.4 の計算例と同じ買い物（おにぎり×2・牛乳×1・洗剤×1） */
const BASE_CART: CartLine[] = [
  line(128, 2, "REDUCED"),
  line(218, 1, "REDUCED"),
  line(298, 1, "STANDARD"),
];

function tuple(amount: ReturnType<typeof calculateAmount>) {
  return [amount.subtotal, amount.discount, amount.taxReduced, amount.taxStandard, amount.total];
}

describe("calculateAmount 正常系", () => {
  test("UT-FE-040 会員・8%と10%混在（設計 §4.4 の計算例）", () => {
    expect(tuple(calculateAmount(BASE_CART, true, RATES))).toEqual([772, 38, 36, 28, 798]);
  });

  test("UT-FE-041 同じ買い物を非会員で", () => {
    expect(tuple(calculateAmount(BASE_CART, false, RATES))).toEqual([772, 0, 37, 29, 838]);
  });

  test("行の順序に依存しない", () => {
    const reversed = [...BASE_CART].reverse();
    expect(tuple(calculateAmount(reversed, true, RATES))).toEqual([772, 38, 36, 28, 798]);
  });

  test("軽減税率のみ（10%の行が無い）", () => {
    expect(tuple(calculateAmount([line(100, 1, "REDUCED")], false, RATES))).toEqual([
      100, 0, 8, 0, 108,
    ]);
  });

  test("標準税率のみ（8%の行が無い）", () => {
    expect(tuple(calculateAmount([line(100, 1, "STANDARD")], false, RATES))).toEqual([
      100, 0, 0, 10, 110,
    ]);
  });
});

describe("端数切り捨ての境界（テスト仕様書 §2.3）", () => {
  // 四捨五入で実装していると必ず落ちるケースを対で置く
  test.each([
    ["12円×8% は 0円", 12, "REDUCED" as const, 0],
    ["13円×8% は 1円", 13, "REDUCED" as const, 1],
  ])("%s", (_name, price, category, expected) => {
    expect(calculateAmount([line(price, 1, category)], false, RATES).taxReduced).toBe(expected);
  });

  test.each([
    ["9円×10% は 0円", 9, 0],
    ["10円×10% は 1円", 10, 1],
  ])("%s", (_name, price, expected) => {
    expect(calculateAmount([line(price, 1, "STANDARD")], false, RATES).taxStandard).toBe(expected);
  });

  test.each([
    ["税抜19円の5%割引は 0円", 19, 0],
    ["税抜20円の5%割引は 1円", 20, 1],
  ])("%s", (_name, price, expected) => {
    expect(calculateAmount([line(price, 1, "REDUCED")], true, RATES).discount).toBe(expected);
  });
});

describe("割引の按分（設計 §4.4 手順4）", () => {
  test("余った1円は税抜小計が大きい区分へ寄せる（8%側が大きい場合）", () => {
    // 8%小計474・10%小計298・割引38 -> 按分 23+14=37 で1円余る -> 8%へ寄せて24
    const amount = calculateAmount(BASE_CART, true, RATES);
    // 8%の課税対象は 474-24=450 -> floor(450*0.08)=36
    expect(amount.taxReduced).toBe(36);
    // 10%の課税対象は 298-14=284 -> floor(284*0.10)=28
    expect(amount.taxStandard).toBe(28);
    // 割引の内訳合計が割引額と一致していること（余りを捨てていない証拠）
    expect(amount.subtotal - amount.discount).toBe(734);
  });

  test("確認事項 T-1: 税抜小計が同額のときは軽減8%へ寄せる", () => {
    // 510+510=1020、割引 floor(1020*0.05)=51、按分 25+25=50 で1円余る
    const amount = calculateAmount(
      [line(510, 1, "REDUCED"), line(510, 1, "STANDARD")],
      true,
      RATES,
    );
    expect(tuple(amount)).toEqual([1020, 51, 38, 48, 1055]);
    // 8%へ寄せた場合: 課税対象 510-26=484 -> floor(484*0.08)=38
    // 10%へ寄せた場合なら 510-25=485 -> floor(485*0.08)=38 で同じだが、
    // 10%側が 510-26=484 -> floor(484*0.10)=48 と変わるのでここで差が出る
    expect(amount.taxStandard).toBe(48);
  });
});

describe("異常系・境界", () => {
  test("確認事項 T-2: 明細0件は例外（購入ボタンを非活性にすべき状態）", () => {
    expect(() => calculateAmount([], false, RATES)).toThrow();
  });

  test("確認事項 T-7: 全商品0円でもゼロ除算にならない", () => {
    expect(tuple(calculateAmount([line(0, 1, "REDUCED"), line(0, 1, "STANDARD")], true, RATES))).toEqual(
      [0, 0, 0, 0, 0],
    );
  });

  test("数量99・単価999999 の上限付近でも整数のまま計算される", () => {
    const amount = calculateAmount([line(999_999, 1, "STANDARD")], false, RATES);
    expect(amount.subtotal).toBe(999_999);
    expect(amount.taxStandard).toBe(99_999); // floor(999999*0.10)=99999.9 -> 99999
    expect(Number.isInteger(amount.total)).toBe(true);
  });

  test("税率が変わっても整数演算で正しい（REQ-08 で税率は変わりうる）", () => {
    // 軽減1%・標準10%（食品1%への改定を想定）
    const amount = calculateAmount([line(1000, 1, "REDUCED")], false, {
      REDUCED: 0.01,
      STANDARD: 0.1,
    });
    expect(amount.taxReduced).toBe(10);
  });
});

describe("補助関数", () => {
  test("lineAmountOf は単価×数量", () => {
    expect(lineAmountOf({ unitPrice: 128, quantity: 2 })).toBe(256);
  });

  test("taxOf は切り捨て", () => {
    expect(taxOf(450, 0.08)).toBe(36);
    expect(taxOf(284, 0.1)).toBe(28);
    expect(taxOf(12, 0.08)).toBe(0);
  });
});

describe("taxRateLabel（設計 v1.2 §9.2 税率の表示）", () => {
  test.each([
    [0.08, "8%"],
    [0.1, "10%"],
    [0.01, "1%"],
    [0.0125, "1.25%"],
  ])("%s は %s と表示する", (rate, label) => {
    expect(taxRateLabel(rate)).toBe(label);
  });
});
