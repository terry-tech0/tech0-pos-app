/**
 * 画面側の金額計算。設計仕様書 §4.4 の手順を TypeScript で実装したもの。
 *
 * ★この実装は src/backend/app/services/amount_calculator.py と必ず同じ結果を返すこと。
 *   片方だけ直すと、購入確定時の照合（設計 §8.6）が理由もなく E-TXN-001 で落ちる。
 *   手順を変えるときは、必ず両方を同じコミットで直す。
 *
 * 設計 §4.4 の手順:
 *   1. 行金額 = 単価 × 数量（税抜・整数円）
 *   2. 税抜合計 subtotal = 全行の行金額の合計
 *   3. 会員割引 discount = floor(subtotal × 0.05)（非会員は 0）
 *   4. 割引を税率区分ごとの税抜小計に比例配分し、円未満は切り捨て。
 *      配分の残りは「税抜小計が大きい区分」へ加算する
 *   5. 区分ごとの割引後税抜 = 区分の税抜小計 − 配分された割引額
 *   6. 区分ごとの消費税 = floor(割引後税抜 × その区分の税率)
 *   7. 税込合計 total = (subtotal − discount) + 消費税の合計
 *
 * 【浮動小数点への対応】
 * JavaScript には Python の Decimal がない。`Math.floor(450 * 0.08)` のような書き方は、
 * 現在の税率・金額の範囲では実害が無いことを全探索で確認済み
 * （テスト仕様書 §10.4）。ただし税率は REQ-08 により変更されうるため、
 * ここでは**税率を 1/10000 単位の整数（ベーシスポイント）に直して整数演算だけで計算する**。
 * こうすると税率が変わっても検証し直す必要がない。
 * 税率は DECIMAL(5,4)（小数点以下4桁）なので、10000倍すれば必ず整数になる。
 */

import type { Amount, CartLine, TaxCategory, TaxRateMap } from "@/types/pos";

/** 会員割引率。設計 §4.4 手順3。バックエンドの MEMBER_DISCOUNT_RATE と同じ値 */
export const MEMBER_DISCOUNT_RATE = 0.05;

/** 税率の分母。DECIMAL(5,4) なので 10000 で必ず整数になる */
const RATE_SCALE = 10000;

/**
 * 整数どうしの割り算を、誤差なく切り捨てる。
 *
 * `Math.floor(a / b)` は a/b が浮動小数点になるため、境界でずれる可能性が残る。
 * 先に剰余を引いて割り切れる形にしてから割ると、結果は厳密に正しい整数になる
 * （被除数が 2^53 未満である限り）。
 */
function floorDiv(numerator: number, denominator: number): number {
  const remainder = numerator % denominator;
  return (numerator - remainder) / denominator;
}

/** 税率（0.08 など）を 1/10000 単位の整数（800）に直す */
function toBasisPoints(rate: number): number {
  return Math.round(rate * RATE_SCALE);
}

/**
 * 消費税額。設計 §4.4 手順6。区分ごとに1回だけ切り捨てる。
 *
 * 行ごとに税を計算して足すと、まとめて計算した場合と1円ずれる。
 * 「1つの取引につき、税率ごとに1回」が消費税の端数処理の原則。
 */
export function taxOf(amount: number, rate: number): number {
  return floorDiv(amount * toBasisPoints(rate), RATE_SCALE);
}

/** 行金額 = 単価 × 数量。設計 §4.4 手順1 */
export function lineAmountOf(line: Pick<CartLine, "unitPrice" | "quantity">): number {
  return line.unitPrice * line.quantity;
}

/**
 * 按分の余りを寄せる区分を決める。「税抜小計が大きい区分」（設計 §4.4 手順4）。
 *
 * 確認事項 T-1 への回答: 小計が同額のときは軽減税率（REDUCED）へ寄せる。
 * バックエンドの AmountCalculator._remainder_target と同じルール。
 * 決定的でないと、画面とサーバで寄せ先が割れて E-TXN-001 が理由もなく出る。
 */
function remainderTarget(subtotalByCategory: Map<TaxCategory, number>): TaxCategory {
  let best: TaxCategory | null = null;
  let bestSubtotal = -1;
  for (const [category, subtotal] of subtotalByCategory) {
    if (
      subtotal > bestSubtotal ||
      (subtotal === bestSubtotal && category === "REDUCED")
    ) {
      best = category;
      bestSubtotal = subtotal;
    }
  }
  // 呼び出し元が空でないことを保証している
  return best as TaxCategory;
}

/**
 * 割引額を税率区分ごとの税抜小計に比例配分する。設計 §4.4 手順4。
 *
 * 切り捨てで配分すると合計が割引額に届かないため（例: 23 + 14 = 37 ≠ 38）、
 * 余りを1区分に寄せて必ず合計が discount と一致するようにする。
 */
function allocateDiscount(
  subtotalByCategory: Map<TaxCategory, number>,
  discount: number,
  subtotal: number,
): Map<TaxCategory, number> {
  const allocated = new Map<TaxCategory, number>();
  for (const category of subtotalByCategory.keys()) {
    allocated.set(category, 0);
  }

  // 確認事項 T-7: 税抜合計0円のときは按分しない（ゼロ除算を避ける）。
  // 全商品0円なら割引額も0なので、配分すべきものが無い。
  if (discount === 0 || subtotal === 0) {
    return allocated;
  }

  let assigned = 0;
  for (const [category, categorySubtotal] of subtotalByCategory) {
    const share = floorDiv(discount * categorySubtotal, subtotal);
    allocated.set(category, share);
    assigned += share;
  }

  const remainder = discount - assigned;
  if (remainder !== 0) {
    const target = remainderTarget(subtotalByCategory);
    allocated.set(target, (allocated.get(target) ?? 0) + remainder);
  }
  return allocated;
}

/**
 * 設計 §4.4 の手順どおりに金額を計算する。
 *
 * @param lines 購入リスト（1行以上）
 * @param isMember 会員割引の対象か
 * @param taxRates 税率区分ごとの適用税率（A-06 で取得したもの）
 * @throws 明細が0件のとき（確認事項 T-2。バックエンドの ValueError と同じ扱い）
 */
export function calculateAmount(
  lines: CartLine[],
  isMember: boolean,
  taxRates: TaxRateMap,
): Amount {
  if (lines.length === 0) {
    throw new Error("明細が0件です。購入ボタンは非活性にすること（E-TXN-002）");
  }

  // 手順1・2
  let subtotal = 0;
  const subtotalByCategory = new Map<TaxCategory, number>();
  for (const line of lines) {
    const lineAmount = lineAmountOf(line);
    subtotal += lineAmount;
    subtotalByCategory.set(
      line.taxCategory,
      (subtotalByCategory.get(line.taxCategory) ?? 0) + lineAmount,
    );
  }

  // 手順3
  const discount = isMember
    ? floorDiv(subtotal * toBasisPoints(MEMBER_DISCOUNT_RATE), RATE_SCALE)
    : 0;

  // 手順4
  const allocated = allocateDiscount(subtotalByCategory, discount, subtotal);

  // 手順5・6
  let taxReduced = 0;
  let taxStandard = 0;
  for (const [category, categorySubtotal] of subtotalByCategory) {
    const rate = taxRates[category];
    if (rate === undefined) {
      throw new Error(`税率が取得できていません: ${category}`);
    }
    const discounted = categorySubtotal - (allocated.get(category) ?? 0);
    const tax = taxOf(discounted, rate);
    if (category === "REDUCED") {
      taxReduced = tax;
    } else {
      taxStandard = tax;
    }
  }

  // 手順7
  const total = subtotal - discount + taxReduced + taxStandard;

  return { subtotal, discount, taxReduced, taxStandard, total };
}
