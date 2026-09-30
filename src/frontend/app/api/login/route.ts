/**
 * A-01 POST /api/login — 設計仕様書 §5.4 A-01。
 *
 * ★トークン本体をレスポンスボディに含めない。
 *   含めるとブラウザのJavaScriptが読めてしまい、httpOnly の意味がなくなる。
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { errorResponse, forward, setSessionCookie, unavailable } from "@/lib/bff";
import { loginRequestSchema } from "@/lib/validation";

/** Cookie の寿命。設計 §5.4 A-01 の Max-Age=28800（8時間＝1シフト） */
const COOKIE_MAX_AGE_SECONDS = 28800;

export async function POST(req: NextRequest): Promise<NextResponse> {
  const parsed = loginRequestSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    // 形式違反はバックエンドに投げる前に弾く（設計 §6 の3層検証のうち画面側の層）
    return errorResponse("E-VAL-001", "入力の形式が正しくありません", 400);
  }

  try {
    const { status, body } = await forward("/auth/token", {
      method: "POST",
      token: null, // ログインだけは Bearer を付けない
      body: parsed.data,
    });

    if (status !== 200) {
      return NextResponse.json(body, { status });
    }

    const result = body as { accessToken: string; cashierId: number; cashierName: string; role: string };
    // ボディからは accessToken を落とし、Cookie に移す
    const response = NextResponse.json(
      { cashierId: result.cashierId, cashierName: result.cashierName, role: result.role },
      { status: 200 },
    );
    setSessionCookie(response, result.accessToken, COOKIE_MAX_AGE_SECONDS);
    return response;
  } catch {
    return unavailable();
  }
}
