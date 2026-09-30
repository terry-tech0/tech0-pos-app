/** A-06 GET /api/tax-rates — 現在有効な税率一覧。設計仕様書 §5.1。 */

import type { NextRequest } from "next/server";
import type { NextResponse } from "next/server";

import { proxyGet } from "@/lib/bff";

export async function GET(req: NextRequest): Promise<NextResponse> {
  return proxyGet(req, "/tax-rates");
}
