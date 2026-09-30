import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  // 架空の店舗名（このリポジトリは public のため実在の社名・店名は入れない）
  title: "あおぞらマート POS",
  description: "Tech0 Step4 Lv2 簡易POSアプリ改",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
