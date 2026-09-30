import type { Config } from "jest";

/**
 * 単体テスト（Frontend）の設定。テスト仕様書 02-単体テスト-frontend-jest.md。
 *
 * 変換に @swc/jest を使う理由:
 *   設計仕様書 §2.1 が TypeScript 7.0.2 を採用しているが、ts-jest の対応は
 *   typescript >=4.3 <7 で、TS7 を受け付けない。
 *   @swc/jest は TypeScript のバージョンに依存せず型注釈を除去するだけなので、
 *   設計書のバージョンを変えずにテストを動かせる。
 *
 * testEnvironment を node にしているのは、UT-FE の対象が
 * 「純粋な関数（金額計算・購入リスト操作）」と「fetch のモック」で、DOM を使わないため
 * （テスト仕様書 §1.2「単体テスト（Frontend）は画面を開かない」）。
 */
const config: Config = {
  testEnvironment: "node",
  roots: ["<rootDir>/__tests__"],
  transform: {
    "^.+\.(t|j)sx?$": ["@swc/jest", { jsc: { parser: { syntax: "typescript", tsx: true } } }],
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  // 通信のモックは afterEach で必ず初期化する（テスト仕様書 §4）
  clearMocks: true,
  restoreMocks: true,
};

export default config;
