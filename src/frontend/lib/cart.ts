/**
 * 購入リストの操作。設計仕様書 §9.2 ③購入リスト・要件定義書 F-03 / F-05 / F-06。
 *
 * 画面（React）から状態を書き換える処理をここに集める。
 * すべて**元の配列を変更せず新しい配列を返す**（React が変更を検知できるようにするため）。
 */

import type { CartLine, Product } from "@/types/pos";

/** 1行あたりの数量。設計 §6 */
export const QUANTITY_MIN = 1;
export const QUANTITY_MAX = 99;

/** 1会計の明細行数。設計 §6。数量の上限とは別物 */
export const LINE_COUNT_MAX = 100;

/** 操作の結果。失敗したときは購入リストを変えずにエラーコードを返す */
export type CartResult =
  | { ok: true; lines: CartLine[] }
  | { ok: false; code: "E-VAL-002" | "E-VAL-003"; lines: CartLine[] };

/**
 * 商品を追加する。同じ商品コードが既にあれば数量を加算する（F-03）。
 *
 * 同一商品を2回スキャンしたとき行が増えないのは、レシートが読みにくくなるのを避けるため。
 * 商品コードは8桁と13桁を別商品として扱う（確認事項 T-5）ので、完全一致で判定する。
 */
export function addProduct(lines: CartLine[], product: Product, quantity = 1): CartResult {
  if (!Number.isInteger(quantity) || quantity < QUANTITY_MIN || quantity > QUANTITY_MAX) {
    return { ok: false, code: "E-VAL-002", lines };
  }

  const index = lines.findIndex((line) => line.productCode === product.productCode);

  if (index >= 0) {
    const merged = lines[index].quantity + quantity;
    // 加算の結果が上限を超えるときは追加しない。リストはそのまま維持する（ER-1）
    if (merged > QUANTITY_MAX) {
      return { ok: false, code: "E-VAL-002", lines };
    }
    const next = [...lines];
    next[index] = { ...next[index], quantity: merged };
    return { ok: true, lines: next };
  }

  // 新しい行を足すとき、明細行数の上限を超えないか見る
  if (lines.length >= LINE_COUNT_MAX) {
    return { ok: false, code: "E-VAL-003", lines };
  }

  return {
    ok: true,
    lines: [
      ...lines,
      {
        productCode: product.productCode,
        productName: product.productName,
        unitPrice: product.unitPrice,
        quantity,
        taxCategory: product.taxCategory,
      },
    ],
  };
}

/**
 * 数量を変更する（F-06）。範囲外なら変更せず E-VAL-002 を返す。
 *
 * 0 は「削除」であって数量ではないので、ここでは受け付けない（設計 §6）。
 * 削除は removeLine を使う。
 */
export function changeQuantity(
  lines: CartLine[],
  productCode: string,
  quantity: number,
): CartResult {
  if (!Number.isInteger(quantity) || quantity < QUANTITY_MIN || quantity > QUANTITY_MAX) {
    return { ok: false, code: "E-VAL-002", lines };
  }
  const index = lines.findIndex((line) => line.productCode === productCode);
  if (index < 0) {
    return { ok: true, lines };
  }
  const next = [...lines];
  next[index] = { ...next[index], quantity };
  return { ok: true, lines: next };
}

/** 行を削除する（F-06） */
export function removeLine(lines: CartLine[], productCode: string): CartLine[] {
  return lines.filter((line) => line.productCode !== productCode);
}

/** 購入確定後にリストを空にする（F-11） */
export function clearCart(): CartLine[] {
  return [];
}

/**
 * 会計の整理番号を作る。設計 v1.1 §4.3 D-7・§9.3。
 *
 * 会計の開始時に1つ作り、金額不一致や通信エラーで押し直すときも同じ番号を送る。
 * サーバは同じ番号の2回目を保存せず、保存済みの取引を返す（二重保存の防止）。
 * 作り直すのは保存に成功したあとだけ。
 */
export function newCheckoutId(): string {
  return crypto.randomUUID();
}

/** 購入ボタンを押せるか。明細0件では押させない（設計 §9.2・E-TXN-002） */
export function canCheckout(lines: CartLine[]): boolean {
  return lines.length > 0 && lines.length <= LINE_COUNT_MAX;
}

/** 確定リクエストに載せる形（商品コードと数量だけ）に変換する。
 *  単価や税率は送らない。サーバがマスタから引くため（設計 §5.4 A-07） */
export function toRequestLines(lines: CartLine[]): Array<{ productCode: string; quantity: number }> {
  return lines.map((line) => ({ productCode: line.productCode, quantity: line.quantity }));
}
