/**
 * 型定義。設計仕様書 §5.5 型定義。
 *
 * 同じ形をバックエンド（Pydantic の app/schemas/pos.py）でも宣言している。
 * 片側だけだと、勘違いが実行時まで見つからない（設計 §8.9 型定義による二重防御）。
 *
 * ブラウザ⇄BFF は camelCase。snake_case への変換は BFF の責務（設計 §5.3）。
 */

export type TaxCategory = "STANDARD" | "REDUCED";
export type Role = "CASHIER" | "MANAGER";

/** 商品照会（A-05）の結果 */
export interface Product {
  productCode: string; // 数字 8桁 or 13桁
  productName: string;
  unitPrice: number; // 税抜・整数円
  taxCategory: TaxCategory;
  taxRate: number; // 0.08 / 0.10
}

/** 購入リストの1行 */
export interface CartLine {
  productCode: string;
  productName: string;
  unitPrice: number;
  quantity: number; // 1〜99
  taxCategory: TaxCategory;
}

/** 金額の5項目。購入確定時にサーバと照合されるのはこの5つ（設計 §8.6） */
export interface Amount {
  subtotal: number; // 税抜合計
  discount: number; // 会員割引額
  taxReduced: number; // 8%分の消費税
  taxStandard: number; // 10%分の消費税
  total: number; // 税込合計
}

/** 会員照会（A-04）の結果 */
export interface Member {
  memberCode: string;
  memberName: string;
  isDiscountTarget: boolean;
}

/** 税率一覧（A-06）の1件 */
export interface TaxRateInfo {
  taxCategory: TaxCategory;
  rate: number;
  validFrom: string;
  validTo: string | null;
}

/** 税率区分 → 税率。金額計算に渡す形 */
export type TaxRateMap = Record<TaxCategory, number>;

/** ログイン中の担当（A-03） */
export interface Me {
  cashierId: number;
  cashierName: string;
  role: Role;
}

/** 購入確定（A-07）のリクエスト */
export interface CheckoutRequest {
  memberCode: string | null;
  lines: Array<{ productCode: string; quantity: number }>;
  clientAmount: Amount;
}

/** 確定した明細（レシート表示用） */
export interface ConfirmedLine {
  lineNo: number;
  productCode: string;
  productName: string;
  unitPrice: number;
  quantity: number;
  taxCategory: TaxCategory;
  appliedTaxRate: number;
  lineAmount: number;
}

/** 購入確定（A-07）の応答。amount はサーバが計算した確定金額 */
export interface CheckoutResponse {
  transactionId: number;
  transactedAt: string;
  amount: Amount;
  lines: ConfirmedLine[];
}

/** エラー応答。設計 §5.3 の共通形式 */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
