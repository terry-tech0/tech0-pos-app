/**
 * BFF 呼び出しの単体テスト。
 * 対応: テスト仕様書 02-単体テスト-frontend-jest.md（UT-FE-070〜076）
 *
 * 通信は必ずモックする（テスト仕様書 §4）。本物のサーバに繋がないので、
 * サーバが落ちていてもこのテストは失敗しない。通信を本物にした瞬間、
 * それは単体テストではなく結合テストになる。
 */

import { ApiError, checkout, fetchMember, fetchProduct, fetchTaxRates, login } from "@/lib/api";

const mockFetch = jest.fn();

beforeEach(() => {
  global.fetch = mockFetch as unknown as typeof fetch;
});

afterEach(() => {
  // モックは毎回初期化する（前のテストの設定を引きずらない）
  mockFetch.mockReset();
});

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("正常系", () => {
  test("UT-FE-070 商品照会は A-05 のパスを叩く", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({
        productCode: "4901234567894",
        productName: "おにぎり 鮭",
        unitPrice: 128,
        taxCategory: "REDUCED",
        taxRate: 0.08,
      }),
    );
    const product = await fetchProduct("4901234567894");
    expect(product.unitPrice).toBe(128);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe("/api/products/4901234567894");
  });

  test("税率一覧は区分→税率の辞書に変換される", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse([
        { taxCategory: "REDUCED", rate: 0.08, validFrom: "2019-10-01", validTo: null },
        { taxCategory: "STANDARD", rate: 0.1, validFrom: "2019-10-01", validTo: null },
      ]),
    );
    await expect(fetchTaxRates()).resolves.toEqual({ REDUCED: 0.08, STANDARD: 0.1 });
  });
});

describe("★UT-FE-076 Authorization ヘッダを付けないこと", () => {
  /**
   * JWT は httpOnly Cookie に入っており、同一オリジンのBFFへブラウザが自動送信する。
   * JavaScript がトークンを扱わないのが設計の要点（設計 §8.4）なので、
   * ヘッダを付ける実装は設計違反。
   *
   * 「あるべきものがある」だけでなく「あってはいけないものがない」もテストになる。
   */
  test("商品照会で Authorization を送らない", async () => {
    mockFetch.mockResolvedValue(jsonResponse({}));
    await fetchProduct("4901234567894").catch(() => undefined);
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(Object.keys(headers).map((k) => k.toLowerCase())).not.toContain("authorization");
  });

  test("購入確定でも Authorization を送らない", async () => {
    mockFetch.mockResolvedValue(jsonResponse({}, 201));
    await checkout({
      checkoutId: "3f2c8a1e-5b7d-4c9a-8e21-6d0f4b9a7c13",
      memberCode: null,
      lines: [{ productCode: "49012345", quantity: 1 }],
      clientAmount: { subtotal: 100, discount: 0, taxReduced: 8, taxStandard: 0, total: 108 },
    }).catch(() => undefined);
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    const headers = (init.headers ?? {}) as Record<string, string>;
    expect(Object.keys(headers).map((k) => k.toLowerCase())).not.toContain("authorization");
  });
});

describe("異常系", () => {
  test("UT-FE-071 未登録商品は E-PROD-001 を ApiError で受け取る", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        { error: { code: "E-PROD-001", message: "商品がマスタ未登録です" } },
        404,
      ),
    );
    await expect(fetchProduct("49999999")).rejects.toMatchObject({
      code: "E-PROD-001",
      status: 404,
    });
  });

  test("会員未登録は E-MEMB-001", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ error: { code: "E-MEMB-001", message: "会員が見つかりません" } }, 404),
    );
    await expect(fetchMember("9999999999")).rejects.toMatchObject({ code: "E-MEMB-001" });
  });

  test("E-TXN-001 では details.serverAmount を受け取れる（ER-5 画面を正しい値に揃える）", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "E-TXN-001",
            message: "金額を再計算しました。内容を確認してもう一度お願いします",
            details: {
              serverAmount: { subtotal: 772, discount: 38, taxReduced: 36, taxStandard: 28, total: 798 },
            },
          },
        },
        400,
      ),
    );
    try {
      await checkout({
        checkoutId: "3f2c8a1e-5b7d-4c9a-8e21-6d0f4b9a7c13",
        memberCode: "1000000001",
        lines: [{ productCode: "4901234567894", quantity: 2 }],
        clientAmount: { subtotal: 0, discount: 0, taxReduced: 0, taxStandard: 0, total: 0 },
      });
      throw new Error("例外が発生しなかった");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const error = e as ApiError;
      expect(error.code).toBe("E-TXN-001");
      expect(error.details?.serverAmount).toMatchObject({ total: 798 });
    }
  });

  test("★UT-FE-074 通信そのものが失敗したら E-SYS-002（手動レジへ切替。TC-20）", async () => {
    mockFetch.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(fetchProduct("49012345")).rejects.toMatchObject({
      code: "E-SYS-002",
      status: 0,
    });
  });

  test("UT-FE-073 未認証は E-AUTH-002 が status 401 で返る", async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ error: { code: "E-AUTH-002", message: "ログインの有効期限が切れました" } }, 401),
    );
    await expect(login("cashier01", "password").catch((e) => e)).resolves.toMatchObject({
      code: "E-AUTH-002",
      status: 401,
    });
  });

  test("エラー本文が壊れていても E-SYS-001 に丸める（ER-6 無言の失敗を作らない）", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response);
    await expect(fetchProduct("49012345")).rejects.toMatchObject({ code: "E-SYS-001" });
  });
});
