"use client";

/**
 * レジ画面。設計仕様書 §9.2 レジ画面のレイアウト・§9.3 レジ画面の状態。
 *
 * 上から下へ業務の順番どおりに並べる（①会員 →②商品 →③購入リスト →④合計 →購入）。
 *
 * 状態（§9.3）:
 *   会員待ち -> 商品登録中 -> 確定処理中 -> 確定完了 -> （クリアして）会員待ち
 * 「確定処理中」を独立した状態として持つのは、購入ボタンの二重押しで
 * 取引が2件保存されるのを防ぐため。
 * 通信の再送など画面の外で起きる二重送信は、会計の整理番号 checkoutId で
 * サーバ側が防ぐ（設計 v1.1 D-7）。
 *
 * エラー処理の原則（設計 §7.2 ER-1）:
 *   **エラーで購入リストを消さない**（E-AUTH-002 を除く）。
 *   お客様を待たせている最中にリストが消えるのが業務上いちばん困る。
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, checkout, fetchMe, fetchMember, fetchProduct, fetchTaxRates, logout } from "@/lib/api";
import { calculateAmount } from "@/lib/amount";
import {
  addProduct,
  canCheckout,
  changeQuantity,
  clearCart,
  newCheckoutId,
  removeLine,
  toRequestLines,
} from "@/lib/cart";
import type { Amount, CartLine, Me, Member, TaxRateMap } from "@/types/pos";

/** 画面の状態。設計 §9.3 の4状態 */
type ScreenState = "waitingMember" | "registering" | "confirming" | "done";

export default function PosPage() {
  const router = useRouter();

  const [me, setMe] = useState<Me | null>(null);
  const [taxRates, setTaxRates] = useState<TaxRateMap | null>(null);
  const [state, setState] = useState<ScreenState>("waitingMember");

  const [memberCodeInput, setMemberCodeInput] = useState("");
  const [member, setMember] = useState<Member | null>(null);
  /** 会員照会をせずに「会員なし」を選んだ、または非会員として続行した */
  const [treatAsNonMember, setTreatAsNonMember] = useState(false);
  const [memberError, setMemberError] = useState<string | null>(null);
  /** E-MEMB-001 のときだけ「非会員として続行」を出す（設計 §7.1） */
  const [offerNonMember, setOfferNonMember] = useState(false);

  const [productCodeInput, setProductCodeInput] = useState("");
  const [productError, setProductError] = useState<string | null>(null);

  const [lines, setLines] = useState<CartLine[]>([]);
  // 会計の整理番号。押し直しでは作り直さず、保存に成功したら次の会計用に作り直す（設計 v1.1 §9.3）
  const [checkoutId, setCheckoutId] = useState<string>(() => newCheckoutId());
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [doneMessage, setDoneMessage] = useState<string | null>(null);
  /** E-TXN-001 でサーバが返してきた正しい金額。画面をこれに揃える（ER-5） */
  const [serverAmount, setServerAmount] = useState<Amount | null>(null);

  const productInputRef = useRef<HTMLInputElement>(null);
  const memberInputRef = useRef<HTMLInputElement>(null);

  /** セッション切れは購入リストを保持せずログイン画面へ（設計 §7.1 E-AUTH-002） */
  const handleAuthExpired = useCallback(() => {
    router.push("/login");
  }, [router]);

  // 起動時に担当と税率を読む。再読込しても表示が復帰する（A-03 / A-06）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [meResult, rates] = await Promise.all([fetchMe(), fetchTaxRates()]);
        if (!cancelled) {
          setMe(meResult);
          setTaxRates(rates);
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          handleAuthExpired();
        } else if (!cancelled) {
          setCheckoutError(
            e instanceof ApiError ? e.message : "システムに接続できません",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [handleAuthExpired]);

  /** 画面が今どの金額を表示すべきか。明細0件なら null */
  function currentAmount(): Amount | null {
    if (taxRates === null || lines.length === 0) {
      return null;
    }
    // E-TXN-001 の直後はサーバの値を出す（画面を正しい値に揃えるため）
    if (serverAmount !== null) {
      return serverAmount;
    }
    try {
      return calculateAmount(lines, member?.isDiscountTarget === true, taxRates);
    } catch {
      return null;
    }
  }

  // ── ① 会員 ──

  async function handleReadMember(event: React.FormEvent) {
    event.preventDefault();
    setMemberError(null);
    setOfferNonMember(false);
    try {
      const found = await fetchMember(memberCodeInput.trim());
      setMember(found);
      setTreatAsNonMember(false);
      setMemberCodeInput("");
      setServerAmount(null);
      setState("registering");
      // 会員を読んだら次は商品なので、フォーカスを商品コード欄へ送る
      productInputRef.current?.focus();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        handleAuthExpired();
        return;
      }
      const error = e instanceof ApiError ? e : null;
      setMemberError(error?.message ?? "システムに接続できません");
      // 会員が見つからないときは「非会員として続行」を選べるようにする（会計を止めない）
      setOfferNonMember(error?.code === "E-MEMB-001");
    }
  }

  /**
   * 「会員なし」または「非会員として続行」。
   *
   * 確認事項 T-4 の決定: 会員欄を「非会員」表示にし、入力欄を空にして、
   * フォーカスを商品コード欄へ移す。次の操作（商品スキャン）に最短で進めるため。
   */
  function handleNonMember() {
    setMember(null);
    setTreatAsNonMember(true);
    setMemberCodeInput("");
    setMemberError(null);
    setOfferNonMember(false);
    setServerAmount(null);
    setState("registering");
    productInputRef.current?.focus();
  }

  // ── ② 商品 ──

  async function handleAddProduct(event: React.FormEvent) {
    event.preventDefault();
    setProductError(null);
    const code = productCodeInput.trim();
    if (code === "") {
      return;
    }
    try {
      const product = await fetchProduct(code);
      const result = addProduct(lines, product);
      if (!result.ok) {
        // 数量上限・行数上限。リストは維持する（ER-1）
        setProductError(
          result.code === "E-VAL-003"
            ? "1回の会計に登録できるのは100行までです"
            : "数量は1〜99で入力してください",
        );
      } else {
        setLines(result.lines);
        // 金額が変わったのでサーバ値の表示は取り下げる
        setServerAmount(null);
        setCheckoutError(null);
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        handleAuthExpired();
        return;
      }
      // 未登録商品でも購入リストの他の商品は消さない（ER-1・TC-11）
      setProductError(e instanceof ApiError ? e.message : "システムに接続できません");
    } finally {
      // 成否にかかわらず入力欄を空にしてフォーカスを戻す。
      // 連続スキャンが止まらないようにするため（設計 §9.2 ②）
      setProductCodeInput("");
      productInputRef.current?.focus();
    }
  }

  // ── ③ 購入リスト ──

  function handleQuantityChange(productCode: string, raw: string) {
    const quantity = Number(raw);
    const result = changeQuantity(lines, productCode, quantity);
    if (!result.ok) {
      // 範囲外は変更前の数量に戻す（設計 §7.1 E-VAL-002 の画面の挙動）
      setProductError("数量は1〜99で入力してください");
      return;
    }
    setProductError(null);
    setLines(result.lines);
    setServerAmount(null);
  }

  function handleRemove(productCode: string) {
    setLines(removeLine(lines, productCode));
    setServerAmount(null);
    setProductError(null);
  }

  // ── 購入確定 ──

  async function handleCheckout() {
    if (taxRates === null || !canCheckout(lines)) {
      return;
    }
    setCheckoutError(null);
    setDoneMessage(null);
    // 「確定処理中」へ。ここでボタンが非活性になり二重送信を防ぐ（設計 §9.3）
    setState("confirming");

    try {
      const clientAmount = calculateAmount(lines, member?.isDiscountTarget === true, taxRates);
      const response = await checkout({
        checkoutId,
        memberCode: member?.memberCode ?? null,
        lines: toRequestLines(lines),
        clientAmount,
      });
      // 保存成功。購入リストと会員情報をクリアして次のお客様へ（F-11）
      setDoneMessage(
        `購入を登録しました（取引番号 ${response.transactionId}／お支払い ${response.amount.total.toLocaleString()} 円）`,
      );
      setLines(clearCart());
      setCheckoutId(newCheckoutId());
      setMember(null);
      setTreatAsNonMember(false);
      setServerAmount(null);
      setState("done");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        handleAuthExpired();
        return;
      }
      const error = e instanceof ApiError ? e : null;
      setCheckoutError(error?.message ?? "エラーが発生しました。店長に連絡してください");
      if (error?.code === "E-TXN-001") {
        // 保存されていない。サーバ計算値で合計表示を更新し、押し直させる（ER-5）
        const fromServer = error.details?.serverAmount as Amount | undefined;
        if (fromServer !== undefined) {
          setServerAmount(fromServer);
        }
      }
      // 購入リストは保持したまま「商品登録中」に戻す（ER-1）
      setState("registering");
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  const amount = currentAmount();
  const memberLabel = member !== null
    ? `会員：${member.memberName} 様${member.isDiscountTarget ? "（割引対象）" : "（割引対象外）"}`
    : treatAsNonMember
      ? "非会員"
      : null;

  return (
    <>
      <div className="header">
        <span>あおぞらマート POS</span>
        <span>
          {me !== null ? `担当：${me.cashierName}（${me.role === "MANAGER" ? "店長" : "レジ"}）` : "読み込み中"}
          <button className="secondary" onClick={handleLogout} style={{ marginLeft: 12 }}>
            ログアウト
          </button>
        </span>
      </div>

      <div className="container">
        {/* ① 会員カード（F-02, F-07） */}
        <div className="panel">
          <h2>① 会員カード</h2>
          <form className="row" onSubmit={handleReadMember}>
            <input
              ref={memberInputRef}
              type="text"
              inputMode="numeric"
              placeholder="会員番号（数字10桁）"
              value={memberCodeInput}
              onChange={(e) => setMemberCodeInput(e.target.value)}
              style={{ width: 240 }}
            />
            <button type="submit">読み込み</button>
            <button type="button" className="secondary" onClick={handleNonMember}>
              会員なし
            </button>
          </form>
          {memberLabel !== null && <p className="notice">{memberLabel}</p>}
          {memberError !== null && (
            <p className="error">
              {memberError}
              {offerNonMember && (
                <>
                  {" "}
                  <button type="button" className="secondary" onClick={handleNonMember}>
                    非会員として続行
                  </button>
                </>
              )}
            </p>
          )}
        </div>

        {/* ② 商品（F-03, F-04, F-05） */}
        <div className="panel">
          <h2>② 商品</h2>
          <form className="row" onSubmit={handleAddProduct}>
            <input
              ref={productInputRef}
              type="text"
              inputMode="numeric"
              placeholder="バーコード／商品コード（8桁または13桁）"
              value={productCodeInput}
              onChange={(e) => setProductCodeInput(e.target.value)}
              style={{ width: 320 }}
            />
            <button type="submit">追 加</button>
          </form>
          {/* エラーは入力欄の直下に出す（設計 §9.2 ②） */}
          {productError !== null && <p className="error">{productError}</p>}
        </div>

        {/* ③ 購入リスト（F-06） */}
        <div className="panel">
          <h2>③ 購入リスト（{lines.length} 行）</h2>
          {lines.length === 0 ? (
            <p className="muted">商品を読み込むとここに表示されます。</p>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>商品名</th>
                    <th className="num">単価</th>
                    <th className="num">数量</th>
                    <th className="num">金額</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => (
                    <tr key={line.productCode}>
                      <td>
                        {line.productName}
                        {/* 軽減税率対象に ※ を付ける（設計 §9.2 ③） */}
                        {line.taxCategory === "REDUCED" && " ※"}
                      </td>
                      <td className="num">{line.unitPrice.toLocaleString()}</td>
                      <td className="num">
                        <input
                          type="number"
                          min={1}
                          max={99}
                          value={line.quantity}
                          onChange={(e) => handleQuantityChange(line.productCode, e.target.value)}
                          style={{ width: 70, textAlign: "right" }}
                        />
                      </td>
                      <td className="num">{(line.unitPrice * line.quantity).toLocaleString()}</td>
                      <td className="num">
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => handleRemove(line.productCode)}
                        >
                          削除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">※ ＝ 軽減税率8%対象</p>
            </>
          )}
        </div>

        {/* ④ 合計（F-08） */}
        <div className="panel totals">
          <h2>④ 合計</h2>
          {amount === null ? (
            <p className="muted">商品を読み込むと合計が表示されます。</p>
          ) : (
            <>
              <div>
                <span>税抜合計</span>
                <span>{amount.subtotal.toLocaleString()} 円</span>
              </div>
              {amount.discount > 0 && (
                <div>
                  <span>会員割引（5%）</span>
                  <span>− {amount.discount.toLocaleString()} 円</span>
                </div>
              )}
              {/*
                設計 §9.2 のモックは「8%対象 450円 → 36円」と対象額も出しているが、
                割引の按分後の対象額は AmountSummary が外に出していない
                （按分の内訳は公開しない設計）。誤った数字を出さないよう税額のみ表示する。
              */}
              <div>
                <span>消費税（8%対象）</span>
                <span>{amount.taxReduced.toLocaleString()} 円</span>
              </div>
              <div>
                <span>消費税（10%対象）</span>
                <span>{amount.taxStandard.toLocaleString()} 円</span>
              </div>
              <div className="grand">
                <span>お支払い金額（税込）</span>
                <span>{amount.total.toLocaleString()} 円</span>
              </div>
              {serverAmount !== null && (
                <p className="muted">※ サーバが計算し直した金額を表示しています。</p>
              )}
            </>
          )}
        </div>

        <button
          type="button"
          className="checkout"
          // 明細0件では押せない。確定処理中も押せない（設計 §9.2・§9.3）
          disabled={!canCheckout(lines) || state === "confirming" || taxRates === null}
          onClick={handleCheckout}
        >
          {state === "confirming" ? "処理中..." : "購 入"}
        </button>

        {checkoutError !== null && <p className="error">{checkoutError}</p>}
        {doneMessage !== null && <p className="notice">{doneMessage}</p>}
      </div>
    </>
  );
}
