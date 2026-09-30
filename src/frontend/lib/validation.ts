/**
 * 実行時の入力検証。設計仕様書 §8.9 型定義による二重防御。
 *
 * **TypeScript の型はビルド時に消える。** 実行時にネットワーク越しに来たJSONが
 * 型どおりである保証はどこにもない。だから zod で実行時にも検証する。
 *
 * 上下限の値は設計 §6 入力値の下限・上限がすべての正。
 * ここの数値とバックエンド（app/schemas/pos.py）の数値は必ず一致させる。
 */

import { z } from "zod";

/** 担当ログインID: 半角英数 4〜20文字（設計 §6） */
export const loginIdSchema = z
  .string()
  .regex(/^[0-9A-Za-z]{4,20}$/, "担当IDは半角英数4〜20文字です");

/**
 * パスワード: 8〜72バイト（設計 §6）。
 * bcrypt は72バイトを超える部分を無視するため、上限を仕様として明示している。
 * 「文字数」ではなく「バイト数」で数えるのが要点（日本語1文字は3バイト）。
 */
export const passwordSchema = z.string().refine(
  (value) => {
    const bytes = new TextEncoder().encode(value).length;
    return bytes >= 8 && bytes <= 72;
  },
  { message: "パスワードは8〜72バイトです" },
);

/** 会員識別番号: 数字10桁固定（設計 §6） */
export const memberCodeSchema = z.string().regex(/^\d{10}$/, "会員番号は数字10桁です");

/**
 * 商品コード: 数字8桁**または**13桁（設計 §6）。
 * あいだの9〜12桁は無効。「8以上13以下」と書くと10桁が通ってしまう。
 */
export const productCodeSchema = z
  .string()
  .regex(/^(\d{8}|\d{13})$/, "商品コードは数字8桁または13桁です");

/** 1行あたりの数量: 1〜99（設計 §6） */
export const quantitySchema = z.number().int().min(1).max(99);

/** 金額: 0〜9,999,999 の整数円（設計 §6） */
const yenSchema = z.number().int().min(0).max(9_999_999);

export const amountSchema = z.object({
  subtotal: yenSchema,
  discount: yenSchema,
  taxReduced: yenSchema,
  taxStandard: yenSchema,
  total: yenSchema,
});

export const loginRequestSchema = z.object({
  loginId: loginIdSchema,
  password: passwordSchema,
});

/**
 * 購入確定のリクエスト。
 *
 * unitPrice も taxRate も cashierId も**定義しない**。
 * zod の既定は「定義していないキーを落とす」なので、
 * 単価を混ぜて送られても BFF の時点で消える（設計 §5.4 A-07・TC-14）。
 */
export const checkoutRequestSchema = z.object({
  memberCode: memberCodeSchema.nullable(),
  lines: z
    .array(z.object({ productCode: productCodeSchema, quantity: quantitySchema }))
    // 1〜100行。0件は E-TXN-002、101行以上は E-VAL-003（設計 §6）
    .min(1)
    .max(100),
  clientAmount: amountSchema,
});

export type LoginRequestInput = z.infer<typeof loginRequestSchema>;
export type CheckoutRequestInput = z.infer<typeof checkoutRequestSchema>;

/**
 * zod の検証結果を設計 §7.1 のエラーコードに割り当てる。
 *
 * バックエンド（app/main.py の _map_validation_error）と同じ考え方で分ける。
 *   明細0件       -> E-TXN-002
 *   明細101行以上 -> E-VAL-003
 *   数量が範囲外  -> E-VAL-002
 *   それ以外      -> E-VAL-001
 */
export function mapCheckoutIssues(error: z.ZodError): string {
  for (const issue of error.issues) {
    const path = issue.path.join(".");
    if (path === "lines") {
      if (issue.code === "too_small") return "E-TXN-002";
      if (issue.code === "too_big") return "E-VAL-003";
    }
  }
  for (const issue of error.issues) {
    if (issue.path.includes("quantity")) return "E-VAL-002";
  }
  return "E-VAL-001";
}
