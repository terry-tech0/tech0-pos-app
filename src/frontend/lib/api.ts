/**
 * 画面から BFF を呼ぶ関数。設計仕様書 §5.1 API一覧（A-01〜A-07）。
 *
 * ブラウザが通信する相手は**同一オリジンの BFF だけ**（原則 P-2）。
 * バックエンドのURLはここに出てこない。だからクロスオリジン要求も発生しない（設計 §8.5）。
 *
 * JWT は httpOnly Cookie に入っており、ブラウザが自動で送る。
 * ★Authorization ヘッダを付けてはいけない（設計 §8.4）。
 *   付ける実装は「JavaScriptがトークンを扱わない」という設計の前提を壊す。
 *   UT-FE-076 が「付いていないこと」を確認している。
 */

import type {
  ApiErrorBody,
  CheckoutRequest,
  CheckoutResponse,
  Me,
  Member,
  Product,
  TaxRateInfo,
  TaxRateMap,
} from "@/types/pos";

/** APIが返したエラー。画面はこの code を見て次の行動を決める（設計 §7.1） */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;

  constructor(code: string, message: string, status: number, details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      // Cookie は同一オリジンなので既定で送られる。キャッシュは使わない
      cache: "no-store",
    });
  } catch {
    // 通信そのものが失敗した（バックエンド停止・ネットワーク断）。
    // 手動レジ運用へ切り替える（NFR-OPS-02 / E-SYS-002・TC-20）
    throw new ApiError("E-SYS-002", "システムに接続できません", 0);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const error = (body as ApiErrorBody | null)?.error;
    throw new ApiError(
      error?.code ?? "E-SYS-001",
      error?.message ?? "エラーが発生しました。店長に連絡してください",
      response.status,
      error?.details,
    );
  }
  return body as T;
}

/** A-01 ログイン。成功すると BFF が httpOnly Cookie を立てる */
export function login(loginId: string, password: string): Promise<Me> {
  return request<Me>("/api/login", {
    method: "POST",
    body: JSON.stringify({ loginId, password }),
  });
}

/** A-02 ログアウト。BFF が Cookie を削除する */
export function logout(): Promise<void> {
  return request<void>("/api/logout", { method: "POST" });
}

/** A-03 ログイン中の担当。再読込時の復帰に使う */
export function fetchMe(): Promise<Me> {
  return request<Me>("/api/me");
}

/** A-04 会員照会。未登録なら E-MEMB-001 */
export function fetchMember(memberCode: string): Promise<Member> {
  return request<Member>(`/api/members/${encodeURIComponent(memberCode)}`);
}

/** A-05 商品照会。未登録・取扱終了なら E-PROD-001 */
export function fetchProduct(productCode: string): Promise<Product> {
  return request<Product>(`/api/products/${encodeURIComponent(productCode)}`);
}

/** A-06 税率一覧。画面の表示用計算に使う */
export async function fetchTaxRates(): Promise<TaxRateMap> {
  const rows = await request<TaxRateInfo[]>("/api/tax-rates");
  const map = {} as TaxRateMap;
  for (const row of rows) {
    map[row.taxCategory] = row.rate;
  }
  return map;
}

/** A-07 購入確定。金額が合わなければ E-TXN-001（details.serverAmount にサーバ計算値） */
export function checkout(body: CheckoutRequest): Promise<CheckoutResponse> {
  return request<CheckoutResponse>("/api/transactions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
