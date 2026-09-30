import { redirect } from "next/navigation";

/** 入口。設計仕様書 §9.1 画面遷移では [*] -> ログイン画面 */
export default function Home() {
  redirect("/login");
}
