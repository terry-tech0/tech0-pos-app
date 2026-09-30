/**
 * A-04 GET /api/members/{memberCode} — 会員照会。設計仕様書 §5.1。
 *
 * 桁数が違う時点でバックエンドに問い合わせない（設計 §6）。
 * 未登録なら E-MEMB-001 が返り、画面は「非会員として続行」を選べる（会計を止めない）。
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { errorResponse, proxyGet } from "@/lib/bff";
import { memberCodeSchema } from "@/lib/validation";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ memberCode: string }> },
): Promise<NextResponse> {
  const { memberCode } = await params;
  if (!memberCodeSchema.safeParse(memberCode).success) {
    return errorResponse("E-VAL-001", "入力の形式が正しくありません", 400, { memberCode });
  }
  return proxyGet(req, `/members/${encodeURIComponent(memberCode)}`);
}
