/**
 * A-02 POST /api/logout — 設計仕様書 §5.1。
 *
 * BFF が Cookie を削除するだけ。Lv2 ではサーバ側の失効リストを持たない
 * （削除後もトークン自体は期限まで有効という弱点を承知の上での採用。設計 §8.2）。
 */

import { NextResponse } from "next/server";

import { clearSessionCookie } from "@/lib/bff";

export async function POST(): Promise<NextResponse> {
  const response = new NextResponse(null, { status: 204 });
  clearSessionCookie(response);
  return response;
}
