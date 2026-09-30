/**
 * BFF の共通処理。設計仕様書 §8.4 BFF（リバースプロキシ）。
 *
 * BFF の仕事は2つだけ。
 *   1. Cookie と Bearer トークンの詰め替え
 *   2. snake_case ⇄ camelCase の変換
 * **業務ロジックは持たせない。** 持たせると計算の実装が2か所に分かれ、原則 P-1 が崩れる。
 *
 * 環境変数はサーバ側でのみ参照する。NEXT_PUBLIC_ を付けない（付けるとブラウザに埋め込まれる）。
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { toCamel, toSnake } from "@/lib/case";

/** Cookie の名前。設計 §2.4 SESSION_COOKIE_NAME */
export function sessionCookieName(): string {
  return process.env.SESSION_COOKIE_NAME ?? "pos_session";
}

/** バックエンドのURL。**ブラウザには絶対に出さない** */
function backendBaseUrl(): string {
  const url = process.env.BACKEND_API_BASE_URL;
  if (!url) {
    // 設定漏れを無言で流さない（設計 §7.2 ER-6）
    throw new Error("BACKEND_API_BASE_URL が設定されていません");
  }
  return url.replace(/\/+$/, "");
}

/**
 * エラーコード → 画面に出すメッセージ。設計 §7.1 エラーコード一覧。
 *
 * バックエンドの app/errors.py ERROR_SPEC と同じ文言。
 * 画面に出すのは「レジ担当が次に取れる行動」で、技術的な原因は出さない（ER-2）。
 */
export const ERROR_MESSAGES: Record<string, string> = {
  "E-VAL-001": "入力の形式が正しくありません",
  "E-VAL-002": "数量は1〜99で入力してください",
  "E-VAL-003": "1回の会計に登録できるのは100行までです",
  "E-AUTH-001": "IDまたはパスワードが違います",
  "E-AUTH-002": "ログインの有効期限が切れました。もう一度ログインしてください",
  "E-AUTH-003": "この操作の権限がありません",
  "E-MEMB-001": "会員が見つかりません",
  "E-PROD-001": "商品がマスタ未登録です",
  "E-TXN-001": "金額を再計算しました。内容を確認してもう一度お願いします",
  "E-TXN-002": "商品が登録されていません",
  "E-SYS-001": "エラーが発生しました。店長に連絡してください",
  "E-SYS-002": "システムに接続できません",
};

/** 設計 §5.3 の共通エラー形式で返す */
export function errorResponse(
  code: string,
  message: string,
  status: number,
  details?: Record<string, unknown>,
): NextResponse {
  return NextResponse.json({ error: { code, message, ...(details ? { details } : {}) } }, { status });
}

/** Cookie からトークンを取り出す。無ければ null */
export function readToken(req: NextRequest): string | null {
  return req.cookies.get(sessionCookieName())?.value ?? null;
}

/** ログインが必要なのに Cookie が無い場合の応答 */
export function unauthorized(): NextResponse {
  return errorResponse(
    "E-AUTH-002",
    "ログインの有効期限が切れました。もう一度ログインしてください",
    401,
  );
}

/** バックエンドに繋がらない場合の応答。手動レジ運用へ（NFR-OPS-02） */
export function unavailable(): NextResponse {
  return errorResponse("E-SYS-002", "システムに接続できません", 503);
}

type ForwardOptions = {
  method?: "GET" | "POST";
  /** ブラウザから来た camelCase のボディ。snake_case に変換して送る */
  body?: unknown;
  /** Bearer トークン。null なら Authorization を付けない（B-01 のみ） */
  token: string | null;
};

/**
 * バックエンドへ中継し、応答を camelCase にして返す。
 *
 * バックエンドのステータスコードとエラーコードはそのまま通す。
 * BFF が独自に判断を加えないのが要点（判断はバックエンドに集約する）。
 */
export async function forward(
  path: string,
  options: ForwardOptions,
): Promise<{ status: number; body: unknown }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(`${backendBaseUrl()}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(toSnake(options.body)),
    cache: "no-store",
  });

  if (response.status === 204) {
    return { status: 204, body: null };
  }
  let raw: unknown = null;
  try {
    raw = await response.json();
  } catch {
    raw = null;
  }
  return { status: response.status, body: toCamel(raw) };
}

/**
 * GET を中継するだけのルート用のひな形。A-03 / A-04 / A-05 / A-06 がこれを使う。
 */
export async function proxyGet(req: NextRequest, backendPath: string): Promise<NextResponse> {
  const token = readToken(req);
  if (!token) {
    return unauthorized();
  }
  try {
    const { status, body } = await forward(backendPath, { token });
    return NextResponse.json(body, { status });
  } catch {
    return unavailable();
  }
}

/** Cookie を立てる。設計 §5.4 A-01 の Set-Cookie 属性に合わせる */
export function setSessionCookie(response: NextResponse, token: string, maxAgeSeconds: number): void {
  response.cookies.set({
    name: sessionCookieName(),
    value: token,
    // JavaScript から読めない。XSS が成立してもトークンを盗めない（設計 §8.2）
    httpOnly: true,
    // 本番では HTTPS のみ。ローカル開発（http://localhost）では付けない
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

/** Cookie を消す（A-02 ログアウト） */
export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set({
    name: sessionCookieName(),
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}
