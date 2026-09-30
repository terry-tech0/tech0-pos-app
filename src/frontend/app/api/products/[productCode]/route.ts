/**
 * A-05 GET /api/products/{productCode} — 商品照会。設計仕様書 §5.4 A-05。
 *
 * 数字以外を通さないことが、SQLインジェクション対策の一段目にもなる（設計 §8.8）。
 * 未登録と取扱終了を画面上で区別しない（レジ担当の対応はどちらも「店長へ連絡」）。
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { errorResponse, proxyGet } from "@/lib/bff";
import { productCodeSchema } from "@/lib/validation";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ productCode: string }> },
): Promise<NextResponse> {
  const { productCode } = await params;
  if (!productCodeSchema.safeParse(productCode).success) {
    return errorResponse("E-VAL-001", "入力の形式が正しくありません", 400, { productCode });
  }
  return proxyGet(req, `/products/${encodeURIComponent(productCode)}`);
}
