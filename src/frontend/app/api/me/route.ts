/** A-03 GET /api/me — ログイン中の担当者名・ロール。設計仕様書 §5.1。 */

import type { NextRequest } from "next/server";
import type { NextResponse } from "next/server";

import { proxyGet } from "@/lib/bff";

export async function GET(req: NextRequest): Promise<NextResponse> {
  return proxyGet(req, "/auth/me");
}
