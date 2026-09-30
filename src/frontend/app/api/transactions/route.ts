/**
 * A-07 POST /api/transactions — 購入確定。設計仕様書 §5.4 A-07。
 *
 * BFF は中継するだけで、金額の判断は一切しない。
 * 金額の再計算と照合はバックエンドの責務（原則 P-1・設計 §8.6）。
 *
 * zod は定義していないキーを落とすので、unitPrice を混ぜて送られても
 * ここで消える（TC-14）。そのうえでバックエンドのスキーマにも無いので二重に防げる。
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ERROR_MESSAGES, errorResponse, forward, readToken, unauthorized, unavailable } from "@/lib/bff";
import { checkoutRequestSchema, mapCheckoutIssues } from "@/lib/validation";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const token = readToken(req);
  if (!token) {
    return unauthorized();
  }

  const parsed = checkoutRequestSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    const code = mapCheckoutIssues(parsed.error);
    return errorResponse(code, ERROR_MESSAGES[code] ?? "入力の形式が正しくありません", 400);
  }

  try {
    const { status, body } = await forward("/transactions", {
      method: "POST",
      token,
      body: parsed.data,
    });
    return NextResponse.json(body, { status });
  } catch {
    return unavailable();
  }
}
