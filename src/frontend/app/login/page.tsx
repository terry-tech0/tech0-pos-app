"use client";

/**
 * ログイン画面。設計仕様書 §9.1 画面遷移・§5.4 A-01。
 *
 * 失敗理由は区別して表示しない（設計 §7.2 ER-4）。
 * 「そのIDは存在します」と教えると、有効なIDの洗い出しに使われる。
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  // 送信中は多重送信を防ぐためボタンを止める
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(loginId, password);
      // 成功したらレジ画面へ（設計 §9.1）
      router.push("/pos");
    } catch (e) {
      // ApiError のメッセージはバックエンドが決めた「画面に出す文言」（設計 §7.1）
      setError(e instanceof ApiError ? e.message : "エラーが発生しました。店長に連絡してください");
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="header">
        <span>あおぞらマート POS</span>
      </div>
      <div className="container" style={{ maxWidth: 420 }}>
        <div className="panel">
          <h2>担当ログイン</h2>
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 10 }}>
              <label htmlFor="loginId" className="muted">
                担当ID
              </label>
              <br />
              <input
                id="loginId"
                type="text"
                value={loginId}
                onChange={(e) => setLoginId(e.target.value)}
                autoComplete="username"
                autoFocus
                style={{ width: "100%" }}
              />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label htmlFor="password" className="muted">
                パスワード
              </label>
              <br />
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                style={{ width: "100%" }}
              />
            </div>
            <button type="submit" disabled={submitting} style={{ width: "100%" }}>
              {submitting ? "確認中..." : "ログイン"}
            </button>
          </form>
          {error !== null && <p className="error">{error}</p>}
        </div>
      </div>
    </>
  );
}
