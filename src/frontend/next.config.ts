import type { NextConfig } from "next";

/**
 * Next.js の設定。設計仕様書 §2.2 構成図・§8.4 BFF。
 *
 * BACKEND_API_BASE_URL に NEXT_PUBLIC_ を付けないのが要点。
 * 付けるとブラウザのバンドルに埋め込まれ、バックエンドのURLが外に出る（設計 §2.4）。
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  // バックエンドのURLをブラウザに渡さない。BFF（サーバ側）だけが process.env で読む
  env: {},
};

export default nextConfig;
