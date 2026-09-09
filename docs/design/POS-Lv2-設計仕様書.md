# Lv2 簡易POSアプリ改 設計仕様書

| 項目 | 内容 |
|---|---|
| 文書名 | Lv2 簡易POSアプリ改 設計仕様書 |
| 版 | 1.0 |
| 作成日 | 2026-09-09 |
| 作成者 | terry（Tech0 Step4 / 12期） |
| 上位文書 | [Lv2 簡易POSアプリ改 要件定義書 v0.2](../requirements/POS-Lv2-要件定義書.md) |
| 作成方法 | AI駆動開発（Claude Code と対話しながら作成。詳細は [§13](#13-生成ai活用の記録)） |

> **本書の位置づけ**：Week3 宿題「設計仕様書」の提出物。上位文書の要求 REQ-01〜11／機能 F-01〜12 を、
> **そのままコードに落とせる粒度**まで具体化する。講義で扱った Web アプリのセキュリティ対策（[§8](#8-セキュリティ設計)）と、
> 入力値の上下限・エラー処理・API一覧・型定義・ER図（[§4](#4-データ設計)〜[§7](#7-エラー処理設計)）を本書で確定させる。

---

## 目次

1. [設計方針](#1-設計方針)
2. [システム構成](#2-システム構成)
3. [UML](#3-uml)
4. [データ設計](#4-データ設計)
5. [API設計](#5-api設計)
6. [入力値の下限・上限](#6-入力値の下限上限)
7. [エラー処理設計](#7-エラー処理設計)
8. [セキュリティ設計](#8-セキュリティ設計)
9. [画面設計](#9-画面設計)
10. [テスト観点](#10-テスト観点)
11. [Lv3 への拡張余地](#11-lv3-への拡張余地)
12. [未確定事項・改訂履歴](#12-未確定事項改訂履歴)
13. [生成AI活用の記録](#13-生成ai活用の記録)

---

## 1. 設計方針

### 1.1 上位文書からの引き継ぎ

要件定義書 v0.2 の機能 F-01〜F-12 を本書で設計する。要求→機能→設計要素のトレーサビリティは各章の表に「対応機能」列で示す。

### 1.2 設計の3原則

この3つは、以降のすべての設計判断のよりどころとする。

| # | 原則 | 理由 | 現れる場所 |
|---|---|---|---|
| P-1 | **金額はバックエンドが正**。フロントの計算値は「表示用」であり、確定時に必ずサーバが計算し直して照合する | 画面のJavaScriptはユーザーが書き換えられる。0円で購入確定を送られても弾けなければならない（NFR-SEC-04） | [§3.3.3](#333-シーケンス図購入確定と金額照合f-09-f-10-f-11)、[§5.3](#54-主要apiの入出力)、[§8.6](#86-金額のバックエンド再計算と照合) |
| P-2 | **ブラウザはバックエンドAPIに直接触らない**。通信相手は常に同一オリジンの BFF（Next.js）だけ | JWTをブラウザのJavaScriptから読めない場所（httpOnly Cookie）に置ける。APIの存在自体を外に晒さない | [§2.2](#22-構成図)、[§8.4](#84-bffリバースプロキシ)、[§8.5](#85-cors) |
| P-3 | **購入履歴は購入時点の事実を転記して保存**。マスタを後から変えても過去の履歴は動かない | 税率改定（REQ-08）や単価変更があっても、履歴は売上の証拠として不変であるべき（B-6、NFR-OPS-05） | [§4.2](#42-テーブル定義)、[§4.3](#43-データ設計上の判断) |

---

## 2. システム構成

### 2.1 技術スタック

| 層 | 採用技術 | バージョン | 選定理由 |
|---|---|---|---|
| フロントエンド | Next.js（App Router）／React／TypeScript | 16.3.4 ／ 19.2.8 ／ 7.0.2 | 講座指定の構成。TypeScript で入力・APIの型を静的に固める（[§8.9](#89-型定義による二重防御)） |
| ランタイム検証 | zod | 4.5.4 | TypeScript の型はコンパイル時にしか効かない。ネットワーク越しに来るデータは実行時に検証する |
| BFF | Next.js Route Handlers（`app/api/**/route.ts`） | 同上 | ブラウザとバックエンドの間に立て、JWTの保管とAPI隠蔽を担う（[§8.4](#84-bffリバースプロキシ)） |
| バックエンド | FastAPI（Python） | 0.141.1 | 講座指定。Pydantic によるリクエスト/レスポンスの型検証が標準で付く |
| ORM | SQLAlchemy 2.0（＋Alembic でマイグレーション） | 2.0.52 ／ 1.19.2 | パラメータバインドが既定。文字列連結SQLを書かせない仕組みとして採用（[§8.8](#88-sqlインジェクション対策)） |
| DB | Azure Database for MySQL（フレキシブルサーバー） | 8.0 系 | 講座指定。Vercel／Streamlit は使用不可の指定 |
| 認証 | PyJWT ＋ bcrypt | 2.13.0 ／ 5.0.0 | パスワードハッシュに passlib を**使わない**判断をした（理由は [§8.10](#810-依存ライブラリの脆弱性とバージョン調査)） |
| ホスティング | Azure App Service（フロント／バックエンドの2アプリ） | — | 講座指定 |

### 2.2 構成図

```mermaid
flowchart LR
    U["レジ担当"]
    BR["ブラウザ<br/>Next.js 画面"]

    subgraph azure["Azure"]
        BFF["Next.js Route Handlers<br/>BFF ・ リバースプロキシ<br/>App Service"]
        API["FastAPI<br/>業務ロジック ・ 金額再計算<br/>App Service"]
        DB[("Azure Database for MySQL<br/>商品 ・ 会員 ・ 税率 ・ 購入履歴")]
    end

    U --> BR
    BR -->|"同一オリジンのみ<br/>JWTは httpOnly Cookie"| BFF
    BFF -->|"Authorization: Bearer JWT<br/>アクセス制限で BFF からのみ許可"| API
    API -->|"SQLAlchemy のパラメータバインド"| DB
```

**通信の境界は3つ**あり、それぞれで守るものが違う。

| 境界 | 守ること | 手段 |
|---|---|---|
| ブラウザ ⇄ BFF | JWTを盗まれない／なりすまされない | HTTPS、httpOnly + Secure + SameSite=Lax Cookie、同一オリジン |
| BFF ⇄ FastAPI | バックエンドに外部から直接触らせない | App Service のアクセス制限（BFFのみ許可）、Bearer トークン必須、Swagger非公開 |
| FastAPI ⇄ MySQL | 注入・漏えいを防ぐ | ORMのパラメータバインド、接続情報は環境変数、SSL接続必須 |

### 2.3 なぜ BFF を置くのか

ブラウザから FastAPI を直接呼ぶ構成でも動く。それでも BFF を挟むのは次の3点のため。

1. **JWTをブラウザのJavaScriptから触れない場所に置ける。** ブラウザが直接APIを呼ぶ設計だと、トークンを `localStorage` に置くことになり、XSSが一度でも成立した瞬間に盗まれる。BFF方式なら Cookie に `httpOnly` を付けられ、JavaScript からは読めない。
2. **CORS に頼らなくてよくなる。** ブラウザの通信相手が同一オリジンだけになるため、そもそもクロスオリジン要求が発生しない（[§8.5](#85-cors)）。
3. **バックエンドのURLと仕様を外に出さない。** 攻撃の下調べ（どんなAPIがあるかの列挙）を難しくする。Swagger非公開（[§8.7](#87-swaggeropenapiドキュメントの非公開)）と合わせて効く。

### 2.4 環境変数

秘密情報はコードに書かず、Azure App Service のアプリケーション設定（＝環境変数）で渡す。`.env` は `.gitignore` 済み（NFR-SEC-03）。

| 変数名 | 置き場所 | 例／内容 | 備考 |
|---|---|---|---|
| `BACKEND_API_BASE_URL` | BFF | `https://pos-api-xxxx.azurewebsites.net` | **サーバ側のみ**。`NEXT_PUBLIC_` を付けない（付けるとブラウザに埋め込まれる） |
| `SESSION_COOKIE_NAME` | BFF | `pos_session` | — |
| `JWT_SECRET_KEY` | バックエンド | 32バイト以上のランダム値 | ローテーション可。リポジトリに絶対に置かない |
| `JWT_ALGORITHM` | バックエンド | `HS256` | — |
| `JWT_EXPIRE_MINUTES` | バックエンド | `480`（8時間＝1シフト） | [§8.2](#82-jwt) |
| `DATABASE_URL` | バックエンド | `mysql+pymysql://user:pass@host/db?ssl_ca=...` | SSL必須 |
| `APP_ENV` | バックエンド | `local` / `production` | `production` のとき Swagger を無効化 |
| `CORS_ALLOWED_ORIGINS` | バックエンド | BFFのオリジンのみ | 既定は空（＝誰も許可しない） |

---

## 3. UML

### 3.1 ユースケース図

```mermaid
flowchart LR
    cashier(("レジ担当"))
    manager(("店長"))

    subgraph sys["簡易POSアプリ Lv2"]
        uc01(["ログインする<br/>F-01"])
        uc02(["会員カードを読み込む<br/>F-02"])
        uc03(["商品を登録する<br/>F-03 F-04"])
        uc04(["購入リストを編集する<br/>F-06"])
        uc05(["合計金額を確認する<br/>F-07 F-08"])
        uc06(["購入を確定する<br/>F-09 F-10 F-11"])
        uc07(["購入履歴を参照する<br/>F-10"])
        uc08(["税率を変更する<br/>F-12"])
    end

    cashier --- uc01
    cashier --- uc02
    cashier --- uc03
    cashier --- uc04
    cashier --- uc05
    cashier --- uc06
    manager --- uc07
    manager --- uc08

    uc03 -. "＜＜include＞＞" .-> uc05
    uc04 -. "＜＜include＞＞" .-> uc05
    uc06 -. "＜＜include＞＞" .-> uc05
```

| アクター | 説明 | 認可ロール |
|---|---|---|
| レジ担当 | パート・アルバイト。会計操作を行う | `CASHIER` |
| 店長 | マスタ管理と履歴確認。**Lv2 では画面を作らずDB直接メンテで代替**（B-7）。認可の枠組みだけ用意する | `MANAGER` |

> **スコープの注意**：`uc07`・`uc08` は Lv2 では**画面を作らない**。ユースケースとしては存在するが、実現手段はDB直接メンテ（要件定義書 §5）。図では点線の外に出さず、実装対象外であることをこの表で明示する。

### 3.2 アクティビティ図（会計1件の流れ）

```mermaid
flowchart TD
    start(["開始：お客様がレジに来る"]) --> a1["会員カードを読み込む<br/>または「会員なし」を押す"]
    a1 --> d1{"会員として<br/>特定できたか"}
    d1 -- "いいえ" --> e1["「会員が見つかりません」を表示<br/>非会員として続行も選べる"]
    e1 --> a2
    d1 -- "はい" --> a2["商品のバーコードを読み込む<br/>または商品コードを手入力"]

    a2 --> d2{"商品マスタに<br/>あるか"}
    d2 -- "いいえ" --> e2["「商品がマスタ未登録です」を表示<br/>リストに追加しない"]
    e2 --> a2
    d2 -- "はい" --> a3["購入リストに追加<br/>同一商品なら数量 +1"]

    a3 --> a4["合計を再表示<br/>税抜・割引・税込"]
    a4 --> d3{"まだ商品が<br/>あるか"}
    d3 -- "はい" --> a2
    d3 -- "いいえ" --> d4{"数量変更や<br/>行削除をするか"}
    d4 -- "する" --> a5["数量変更 / 行削除"]
    a5 --> a4
    d4 -- "しない" --> a6["購入ボタンを押す"]

    a6 --> a7["サーバが金額を計算し直し<br/>画面の金額と照合"]
    a7 --> d5{"一致したか"}
    d5 -- "いいえ" --> e3["「金額を再計算しました」を表示<br/>保存せず画面を最新化"]
    e3 --> a4
    d5 -- "はい" --> a8["購入履歴を保存<br/>取引ヘッダ＋明細"]
    a8 --> a9["確定金額を表示し<br/>リストと会員情報をクリア"]
    a9 --> fin(["終了：次のお客様へ"])
```

### 3.3 シーケンス図

#### 3.3.1 シーケンス図：ログイン（F-01）

```mermaid
sequenceDiagram
    autonumber
    actor C as レジ担当
    participant BR as ブラウザ
    participant BFF as BFF/Next.js
    participant API as FastAPI
    participant DB as MySQL

    C->>BR: 担当ID・パスワードを入力
    BR->>BFF: POST /api/login
    BFF->>API: POST /auth/token
    API->>DB: SELECT cashier WHERE login_id = :id
    DB-->>API: ハッシュ済みパスワード・role
    API->>API: bcrypt でパスワード照合
    alt 照合NG
        API-->>BFF: 401 E-AUTH-001
        BFF-->>BR: 401 「IDまたはパスワードが違います」
    else 照合OK
        API->>API: JWT を発行 sub=cashier_id role 有効期限8時間
        API-->>BFF: 200 access_token
        BFF->>BFF: Set-Cookie httpOnly Secure SameSite=Lax
        BFF-->>BR: 200 担当者名のみ返す
        BR-->>C: レジ画面へ遷移
    end
    Note over BR,BFF: トークン本体はブラウザのJSからは読めない
```

#### 3.3.2 シーケンス図：商品スキャン（F-03 / F-05）

```mermaid
sequenceDiagram
    autonumber
    actor C as レジ担当
    participant BR as ブラウザ
    participant BFF as BFF/Next.js
    participant API as FastAPI
    participant DB as MySQL

    C->>BR: バーコードを読み込む
    BR->>BR: 形式チェック 数字8桁または13桁
    BR->>BFF: GET /api/products/4901234567894
    BFF->>BFF: Cookie から JWT を取り出す
    BFF->>API: GET /products/4901234567894 Bearer JWT
    API->>API: JWT検証・Pydanticで商品コード検証
    API->>DB: SELECT product ＋ 有効な税率を結合
    alt 未登録
        DB-->>API: 0件
        API-->>BFF: 404 E-PROD-001
        BFF-->>BR: 404
        BR-->>C: 「商品がマスタ未登録です」入力欄にフォーカスを戻す
    else 登録あり
        DB-->>API: 商品名・単価・税率区分・適用税率
        API-->>BFF: 200 商品情報
        BFF-->>BR: 200
        BR->>BR: 購入リストに追加 同一商品なら数量+1
        BR->>BR: 合計を表示用に再計算
        BR-->>C: 商品名・単価・数量・合計を表示
    end
```

#### 3.3.3 シーケンス図：購入確定と金額照合（F-09 / F-10 / F-11）

**本設計でいちばん重要な流れ。** 画面が計算した金額をサーバがそのまま信用しないことを、ここで担保する（原則 P-1）。

```mermaid
sequenceDiagram
    autonumber
    actor C as レジ担当
    participant BR as ブラウザ
    participant BFF as BFF/Next.js
    participant API as FastAPI
    participant DB as MySQL

    C->>BR: 購入ボタンを押す
    BR->>BFF: POST /api/transactions 明細と画面計算した合計
    BFF->>API: POST /transactions Bearer JWT
    API->>API: JWT検証 → 担当IDを確定 画面から来た担当IDは使わない
    API->>DB: 明細の商品コードで単価・税率区分を再取得
    API->>DB: 現在有効な税率を取得
    API->>API: 単価×数量 → 会員割引 → 税率区分ごとに消費税を再計算
    API->>API: 画面から来た合計と照合
    alt 金額不一致
        API-->>BFF: 400 E-TXN-001 サーバ計算値を添えて返す
        BFF-->>BR: 400
        BR-->>C: 「金額を再計算しました。内容を確認してください」保存しない
    else 一致
        API->>DB: BEGIN
        API->>DB: INSERT transactions ヘッダ
        API->>DB: INSERT transaction_lines 商品名・単価・適用税率を転記
        API->>DB: COMMIT
        DB-->>API: transaction_id
        API-->>BFF: 201 確定金額
        BFF-->>BR: 201
        BR->>BR: リスト・会員情報をクリア
        BR-->>C: 確定金額を表示 次のお客様へ
    end
    Note over API,DB: 保存されるのはサーバが計算した金額のみ
```

### 3.4 クラス図

バックエンド（FastAPI）の主要クラス。**「計算」を `AmountCalculator` 1か所に閉じ込める**のが要点で、画面もサーバも最終的にこの仕様に従う。

```mermaid
classDiagram
    direction LR

    class CheckoutService {
        +quote(lines, memberCode) AmountSummary
        +confirm(request, cashierId) Transaction
        -verifyAmount(client, server) void
    }

    class AmountCalculator {
        +calculate(lines, isMember, taxRates) AmountSummary
        -allocateDiscount(subtotalByCategory, discount) map
        -taxOf(amount, rate) int
    }

    class AmountSummary {
        +int subtotal
        +int discount
        +int taxReduced
        +int taxStandard
        +int total
    }

    class Transaction {
        +int transactionId
        +datetime transactedAt
        +int cashierId
        +str memberCode
        +int subtotal
        +int discount
        +int total
    }

    class TransactionLine {
        +int lineNo
        +str productCode
        +str productName
        +int unitPrice
        +int quantity
        +str taxCategory
        +decimal appliedTaxRate
        +amount() int
    }

    class Product {
        +str productCode
        +str productName
        +int unitPrice
        +str taxCategory
    }

    class Member {
        +str memberCode
        +str memberName
        +str discountType
        +isDiscountTarget() bool
    }

    class TaxRate {
        +str taxCategory
        +decimal rate
        +date validFrom
        +date validTo
    }

    class Cashier {
        +int cashierId
        +str loginId
        +str passwordHash
        +str role
    }

    class ProductRepository {
        +findByCode(code) Product
        +findManyByCodes(codes) list
    }
    class MemberRepository {
        +findByCode(code) Member
    }
    class TaxRateRepository {
        +findEffective(onDate) list
    }
    class TransactionRepository {
        +save(transaction) int
    }
    class AuthService {
        +authenticate(loginId, password) Cashier
        +issueToken(cashier) str
        +verifyToken(token) TokenPayload
    }

    CheckoutService --> AmountCalculator
    CheckoutService --> ProductRepository
    CheckoutService --> MemberRepository
    CheckoutService --> TaxRateRepository
    CheckoutService --> TransactionRepository
    AmountCalculator --> AmountSummary
    AmountCalculator ..> TaxRate
    Transaction "1" *-- "1..*" TransactionLine
    TransactionLine ..> Product
    Transaction ..> Member
    Transaction ..> Cashier
    AuthService --> Cashier
```

| クラス | 役割 | 対応機能 |
|---|---|---|
| `AuthService` | パスワード照合とJWTの発行・検証 | F-01 |
| `CheckoutService` | 会計の司令塔。金額の再計算・照合・保存をまとめる | F-07〜F-10 |
| `AmountCalculator` | 金額計算の唯一の実装。割引の按分と消費税の端数処理を持つ（仕様は [§4.4](#44-金額計算の仕様)） | F-07, F-08, F-12 |
| `AmountSummary` | 計算結果の入れ物。税抜・割引・税率区分ごとの消費税・税込 | F-08 |
| `*Repository` | DBアクセス。SQLはここだけに閉じ込める（[§8.8](#88-sqlインジェクション対策)） | 全般 |

---

## 4. データ設計

### 4.1 ER図

```mermaid
erDiagram
    cashiers ||--o{ transactions : "会計を登録する"
    members ||--o{ transactions : "会員として紐づく"
    transactions ||--|{ transaction_lines : "明細を持つ"
    products ||--o{ transaction_lines : "明細の元になる"
    tax_rates }o--o{ products : "税率区分で対応する"

    cashiers {
        int cashier_id PK "自動採番"
        varchar login_id UK "半角英数 4〜20"
        varchar cashier_name "表示名 50"
        char password_hash "bcrypt 60固定"
        enum role "CASHIER / MANAGER"
        boolean is_active "退職者は false"
        datetime created_at
        datetime updated_at
    }

    members {
        char member_code PK "会員識別番号 数字10桁"
        varchar member_name "50"
        enum discount_type "NONE / RATE5"
        date joined_on
        boolean is_active
    }

    products {
        varchar product_code PK "JAN 8桁または13桁"
        varchar product_name "100"
        int unit_price "税抜・整数円 0〜999999"
        enum tax_category "STANDARD / REDUCED"
        boolean is_active "取扱終了は false"
        datetime updated_at
    }

    tax_rates {
        enum tax_category PK "STANDARD / REDUCED"
        date valid_from PK "適用開始日"
        decimal rate "0.0800 など"
        date valid_to "NULL は現行"
    }

    transactions {
        bigint transaction_id PK "自動採番"
        datetime transacted_at "確定日時 ミリ秒"
        int cashier_id FK "JWTから確定した担当"
        char member_code FK "非会員は NULL"
        int subtotal "税抜合計"
        int discount_amount "会員割引額"
        int tax_reduced "軽減税率分の消費税"
        int tax_standard "標準税率分の消費税"
        int total "税込合計"
        datetime created_at
    }

    transaction_lines {
        bigint transaction_id PK "取引ID・FK"
        smallint line_no PK "明細番号 1から"
        varchar product_code FK "購入時点の商品コード"
        varchar product_name "購入時点の商品名を転記"
        int unit_price "購入時点の単価を転記"
        smallint quantity "1〜99"
        enum tax_category "購入時点の税率区分を転記"
        decimal applied_tax_rate "購入時点の税率を転記"
        int line_amount "単価×数量 税抜"
    }
```

### 4.2 テーブル定義

金額はすべて **`INT`（税抜・税込とも整数の円）** で持つ。浮動小数点（`FLOAT`/`DOUBLE`）は誤差が出るため使わない。税率だけは `DECIMAL(5,4)`（例：`0.0800`）。

| テーブル | 主キー | 主なインデックス | 備考 |
|---|---|---|---|
| `cashiers` | `cashier_id` | `UNIQUE(login_id)` | パスワードは bcrypt ハッシュのみ保存（NFR-SEC-02） |
| `members` | `member_code` | — | 学習用の架空データのみ（NFR-SEC-06） |
| `products` | `product_code` | `INDEX(tax_category)` | 初期データは架空商品30件（食品・雑貨混在） |
| `tax_rates` | `(tax_category, valid_from)` | — | **行を追加するだけで税率改定に対応**（REQ-08 / NFR-OPS-04） |
| `transactions` | `transaction_id` | `INDEX(transacted_at)`, `INDEX(cashier_id)` | 追記のみ。UPDATE/DELETE しない |
| `transaction_lines` | `(transaction_id, line_no)` | `INDEX(product_code)` | 商品名・単価・税率を転記して保存 |

### 4.3 データ設計上の判断

| # | 判断 | 理由 |
|---|---|---|
| D-1 | 明細に商品名・単価・税率区分・適用税率を**転記**する | 原則 P-3。マスタの単価や税率を後から変えても、過去の履歴は購入時点の事実のまま残る（B-6、F-12） |
| D-2 | 税率マスタは「区分＋適用開始日」を主キーにする | 税率改定は「行の追加」で表現できる。既存行を書き換えないので、過去の税率も残る |
| D-3 | 非会員は `transactions.member_code` を `NULL` にする | 「会員なし」を別テーブルやダミー会員で表さない。NULL＝非会員という意味を1か所に固定する |
| D-4 | 消費税を `tax_reduced` / `tax_standard` の2列で持つ | 税率区分ごとの内訳表示（F-08）に必要。合算だけだと後から内訳を復元できない |
| D-5 | 履歴の削除・更新をアプリから提供しない | NFR-OPS-05。加えて、アプリが使うDBユーザーから `transactions` 系の `DELETE` 権限を外す運用とする |
| D-6 | 商品・会員・担当に `is_active` を持たせ、物理削除しない | 退職者や取扱終了商品を消すと、過去の履歴の外部キーが壊れる |

### 4.4 金額計算の仕様

**この節が、画面とサーバの両方が従う唯一の計算仕様。** `AmountCalculator` の実装はこの手順どおりに書く。

1. 行金額 ＝ 単価 × 数量（税抜・整数円）
2. 税抜合計 `subtotal` ＝ 全行の行金額の合計
3. 会員割引 `discount` ＝ `floor(subtotal × 0.05)`（会員のみ。非会員は 0）
4. 割引を**税率区分ごとの税抜小計に比例配分**し、円未満は切り捨てる。
   配分の残り（`discount` − 配分額の合計）は、**税抜小計が大きい区分**に加算する
5. 区分ごとの割引後税抜 ＝ 区分の税抜小計 − 配分された割引額
6. 区分ごとの消費税 ＝ `floor(割引後税抜 × その区分の税率)`
7. 税込合計 `total` ＝ (`subtotal` − `discount`) ＋ 消費税の合計

> **なぜ区分ごとにまとめて計算するのか**：消費税の端数処理は「1つの取引につき、税率ごとに1回」が原則。
> 行ごとに消費税を計算して足すと、まとめて計算した場合と1円ずれることがある。仕様として計算順序を固定しておかないと、
> 画面とサーバで結果が食い違い、[§8.6](#86-金額のバックエンド再計算と照合) の照合が理由もなく落ちる。

**計算例（会員／8%・10%混在）**

| 商品 | 税率区分 | 単価 | 数量 | 行金額 |
|---|---|---:|---:|---:|
| おにぎり 鮭 | 軽減 8% | 128 | 2 | 256 |
| 牛乳 1L | 軽減 8% | 218 | 1 | 218 |
| 食器用洗剤 | 標準 10% | 298 | 1 | 298 |

| 手順 | 計算 | 結果 |
|---|---|---:|
| 税抜合計 | 256 + 218 + 298 | **772** |
| 会員割引 | `floor(772 × 0.05)` = `floor(38.6)` | **38** |
| 割引の按分（8%） | `floor(38 × 474 ÷ 772)` = `floor(23.33)` | 23 |
| 割引の按分（10%） | `floor(38 × 298 ÷ 772)` = `floor(14.67)` | 14 |
| 配分残 | 38 − (23 + 14) = 1 → 小計が大きい8%へ | 8%は24、10%は14 |
| 割引後税抜（8%） | 474 − 24 | 450 |
| 割引後税抜（10%） | 298 − 14 | 284 |
| 消費税（8%） | `floor(450 × 0.08)` = `floor(36.0)` | 36 |
| 消費税（10%） | `floor(284 × 0.10)` = `floor(28.4)` | 28 |
| **税込合計** | (772 − 38) + (36 + 28) | **798** |

同じ買い物を**非会員**で行った場合：消費税 8% = `floor(474×0.08)` = 37、10% = `floor(298×0.10)` = 29、税込合計 = **838**。

---

## 5. API設計

### 5.1 API一覧（BFF ＝ ブラウザから呼ぶAPI）

すべて Next.js の Route Handlers（`app/api/**/route.ts`）。ブラウザはこの一覧以外のエンドポイントを呼ばない。

| ID | メソッド | パス | 概要 | 認証 | 対応機能 | 主なエラー |
|---|---|---|---|---|---|---|
| A-01 | `POST` | `/api/login` | 担当ID・パスワードでログインし、JWTを httpOnly Cookie に格納する | 不要 | F-01 | `E-AUTH-001` |
| A-02 | `POST` | `/api/logout` | Cookie を削除する | 要 | F-01 | — |
| A-03 | `GET` | `/api/me` | ログイン中の担当者名・ロールを返す（画面ヘッダ表示・再読込時の復帰用） | 要 | F-01 | `E-AUTH-002` |
| A-04 | `GET` | `/api/members/{memberCode}` | 会員を照会し、氏名と割引対象かどうかを返す | 要 | F-02 | `E-MEMB-001`, `E-VAL-001` |
| A-05 | `GET` | `/api/products/{productCode}` | 商品を照会し、商品名・単価・税率区分・適用税率を返す | 要 | F-03〜F-05 | `E-PROD-001`, `E-VAL-001` |
| A-06 | `GET` | `/api/tax-rates` | 現在有効な税率一覧を返す（画面の表示用計算に使う） | 要 | F-08, F-12 | — |
| A-07 | `POST` | `/api/transactions` | 購入を確定し、購入履歴を保存する | 要 | F-09〜F-11 | `E-TXN-001`, `E-TXN-002`, `E-VAL-002` |

### 5.2 API一覧（バックエンド ＝ FastAPI）

**BFF からのみ呼ばれる。** BFF は 1:1 に中継するだけで、業務ロジックを持たない（持たせると計算の実装が2か所に分かれ、原則 P-1 が崩れる）。

| ID | メソッド | パス | 対応するBFF | 認証 | 備考 |
|---|---|---|---|---|---|
| B-01 | `POST` | `/auth/token` | A-01 | 不要 | パスワード照合とJWT発行 |
| B-02 | `GET` | `/auth/me` | A-03 | Bearer | — |
| B-03 | `GET` | `/members/{member_code}` | A-04 | Bearer | — |
| B-04 | `GET` | `/products/{product_code}` | A-05 | Bearer | 有効な税率を結合して返す |
| B-05 | `GET` | `/tax-rates` | A-06 | Bearer | — |
| B-06 | `POST` | `/transactions` | A-07 | Bearer | **金額の再計算・照合・保存** |
| B-07 | `GET` | `/healthz` | なし | 不要 | 死活監視用。DBの情報は返さない |

### 5.3 共通仕様

| 項目 | 内容 |
|---|---|
| 文字コード | `Content-Type: application/json; charset=utf-8` |
| 命名規則 | ブラウザ⇄BFF は **camelCase**（TypeScript流）、BFF⇄バックエンドは **snake_case**（Python流）。**変換はBFFの責務** |
| 認証の渡し方 | ブラウザ⇄BFF：`pos_session` Cookie（httpOnly）／ BFF⇄バックエンド：`Authorization: Bearer <JWT>` |
| 日時形式 | ISO 8601・日本時間オフセット付き（例 `2026-09-09T14:23:11+09:00`） |
| 金額 | すべて整数（円）。文字列や小数で送らない |
| エラー形式 | 全API共通（下記） |

```json
{
  "error": {
    "code": "E-PROD-001",
    "message": "商品がマスタ未登録です",
    "details": { "productCode": "4901234567894" }
  }
}
```

### 5.4 主要APIの入出力

#### A-01 `POST /api/login`

| 区分 | 項目 | 型 | 必須 | 制約・説明 |
|---|---|---|---|---|
| 入力 | `loginId` | `string` | ○ | 半角英数、4〜20文字 |
| 入力 | `password` | `string` | ○ | 8〜72バイト（[§6](#6-入力値の下限上限)） |
| 出力 | `cashierName` | `string` | — | 表示名 |
| 出力 | `role` | `"CASHIER" \| "MANAGER"` | — | 認可に使う |
| 副作用 | `Set-Cookie` | — | — | `pos_session=<JWT>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=28800` |

**トークン本体はレスポンスボディに含めない。** 含めるとブラウザのJavaScriptが読めてしまい、httpOnly の意味がなくなる。

#### A-05 `GET /api/products/{productCode}`

| 区分 | 項目 | 型 | 必須 | 制約・説明 |
|---|---|---|---|---|
| 入力 | `productCode`（パス） | `string` | ○ | 数字のみ、8桁または13桁 |
| 出力 | `productCode` | `string` | — | — |
| 出力 | `productName` | `string` | — | 最大100文字 |
| 出力 | `unitPrice` | `number` | — | 税抜・整数円 |
| 出力 | `taxCategory` | `"STANDARD" \| "REDUCED"` | — | 税率区分 |
| 出力 | `taxRate` | `number` | — | 現在有効な税率（例 `0.08`） |

エラー：`404 E-PROD-001`（未登録または `is_active = false`）、`400 E-VAL-001`（桁数・文字種違反）。
**未登録と取扱終了を画面上で区別しない**（レジ担当の対応はどちらも「店長へ連絡」で同じため）。

#### A-07 `POST /api/transactions`

リクエスト：

```jsonc
{
  "memberCode": "1234567890",        // 非会員は null
  "lines": [
    { "productCode": "4901234567894", "quantity": 2 },
    { "productCode": "4902345678901", "quantity": 1 }
  ],
  "clientAmount": {                  // 画面が計算した金額（照合用。保存はされない）
    "subtotal": 772, "discount": 38,
    "taxReduced": 36, "taxStandard": 28, "total": 798
  }
}
```

| 区分 | 項目 | 型 | 必須 | 制約・説明 |
|---|---|---|---|---|
| 入力 | `memberCode` | `string \| null` | ○ | 数字10桁、または `null`（非会員） |
| 入力 | `lines` | `Line[]` | ○ | 1〜100要素。0件は `E-TXN-002` |
| 入力 | `lines[].productCode` | `string` | ○ | 数字8桁または13桁 |
| 入力 | `lines[].quantity` | `number` | ○ | 整数 1〜99 |
| 入力 | `clientAmount` | `Amount` | ○ | 画面の計算結果。**サーバはこれを保存しない**。照合のみに使う |
| 入力 | ~~`cashierId`~~ | — | — | **受け取らない**。担当はJWTから決める（詐称防止） |
| 入力 | ~~`unitPrice` / `taxRate`~~ | — | — | **受け取らない**。単価・税率はサーバがマスタから引く |
| 出力 | `transactionId` | `number` | — | 採番された取引ID |
| 出力 | `transactedAt` | `string` | — | ISO 8601 |
| 出力 | `amount` | `Amount` | — | **サーバが計算した確定金額** |
| 出力 | `lines[]` | `ConfirmedLine[]` | — | 商品名・単価・数量・行金額（レシート表示用） |

エラー：`400 E-TXN-001`（金額照合の不一致。`details.serverAmount` にサーバ計算値を入れて返す）、`400 E-TXN-002`（明細0件）、`400 E-VAL-002`（数量が範囲外）、`404 E-PROD-001`（明細に未登録商品）、`401 E-AUTH-002`（トークン期限切れ）。

### 5.5 型定義

**同じ形をフロント（TypeScript）とバックエンド（Pydantic）の両方で宣言する。** どちらか一方だけだと、片側の勘違いが実行時まで見つからない。

フロントエンド（`src/frontend/types/pos.ts`）:

```ts
export type TaxCategory = "STANDARD" | "REDUCED";
export type Role = "CASHIER" | "MANAGER";

export interface Product {
  productCode: string;   // 数字 8 or 13桁
  productName: string;
  unitPrice: number;     // 税抜・整数円
  taxCategory: TaxCategory;
  taxRate: number;       // 0.08 / 0.10
}

export interface CartLine {
  productCode: string;
  productName: string;
  unitPrice: number;
  quantity: number;      // 1〜99
  taxCategory: TaxCategory;
}

export interface Amount {
  subtotal: number;      // 税抜合計
  discount: number;      // 会員割引額
  taxReduced: number;    // 8%分の消費税
  taxStandard: number;   // 10%分の消費税
  total: number;         // 税込合計
}

export interface CheckoutRequest {
  memberCode: string | null;
  lines: Array<{ productCode: string; quantity: number }>;
  clientAmount: Amount;
}
```

バックエンド（`src/backend/schemas/pos.py`）:

```python
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, conint, constr

PRODUCT_CODE = constr(pattern=r"^(\d{8}|\d{13})$")
MEMBER_CODE = constr(pattern=r"^\d{10}$")

class TaxCategory(str, Enum):
    STANDARD = "STANDARD"
    REDUCED = "REDUCED"

class ProductOut(BaseModel):
    product_code: PRODUCT_CODE
    product_name: constr(max_length=100)
    unit_price: conint(ge=0, le=999_999)
    tax_category: TaxCategory
    tax_rate: Decimal

class Amount(BaseModel):
    subtotal: conint(ge=0, le=9_999_999)
    discount: conint(ge=0, le=9_999_999)
    tax_reduced: conint(ge=0, le=9_999_999)
    tax_standard: conint(ge=0, le=9_999_999)
    total: conint(ge=0, le=9_999_999)

class CheckoutLineIn(BaseModel):
    product_code: PRODUCT_CODE
    quantity: conint(ge=1, le=99)

class CheckoutRequest(BaseModel):
    member_code: MEMBER_CODE | None = None
    lines: list[CheckoutLineIn] = Field(min_length=1, max_length=100)
    client_amount: Amount
```

> **ここが型定義の効きどころ**：`CheckoutRequest` に `cashier_id` も `unit_price` も**定義していない**。
> 定義していない項目は、たとえ送られてきても無視される。「送られた単価を使ってしまう」事故が、型の形として起こりえなくなる。

---

## 6. 入力値の下限・上限

**3層で検証する。** 画面（即座に気づける）／Pydantic（サーバの入口で必ず通る）／DB制約（最後の砦）。
画面のチェックは親切のためのもので、**セキュリティ上の根拠にはしない**（画面のコードは書き換えられるため）。

| 項目 | 型 | 下限 | 上限 | 形式 | 上下限を設けた理由 |
|---|---|---:|---:|---|---|
| 担当ログインID | 文字列 | 4文字 | 20文字 | 半角英数のみ | 総当たりの的を絞らせない最低長。DBの `VARCHAR(20)` と一致させる |
| パスワード | 文字列 | 8バイト | **72バイト** | 印字可能な半角文字 | **bcrypt は72バイトを超える部分を無視する**ため、上限を仕様として明示する（知らずに長いパスワードを許すと、後半が無意味になる） |
| 会員識別番号 | 文字列 | 10桁 | 10桁 | 数字のみ | カード券面の桁数に固定。桁が違う時点で照会しない |
| 商品コード（JAN） | 文字列 | 8桁 | 13桁 | 数字のみ・8桁または13桁 | JAN規格。**数字以外を通さないことがSQLインジェクション対策の一段目**にもなる（[§8.8](#88-sqlインジェクション対策)） |
| **1行あたりの数量** | 整数 | **1** | **99** | 整数 | 0や負数は「削除」であって数量ではない。小型スーパーで同一商品100個以上は運用上ありえず、桁の打ち間違い（`2`→`22`→`222`）を止められる |
| **1会計の明細行数** | 整数 | **1** | **100** | 整数 | 0件では確定させない（`E-TXN-002`）。100行超は会計を分ける運用とし、1リクエストが無制限に大きくなるのを防ぐ |
| 単価（商品マスタ） | 整数 | 0 | 999,999 | 円・整数 | 小型スーパーの取扱商品の現実的上限。0円は景品等で許容 |
| 税抜合計・税込合計 | 整数 | 0 | 9,999,999 | 円・整数 | 現実にありえない額を弾くこと自体が、計算バグや不正な入力の検出になる |
| 割引額 | 整数 | 0 | 税抜合計以下 | 円・整数 | 割引が合計を超えてマイナス会計になることを構造的に防ぐ |
| 税率 | 小数 | 0.0000 | 1.0000 | `DECIMAL(5,4)` | 税率マスタの誤入力（`8` と入れて800%になる等）を防ぐ |
| 商品名 | 文字列 | 1文字 | 100文字 | — | DBの `VARCHAR(100)` と一致させる |

> **「商品数の下限・上限」は2種類ある**という整理が要点。**1行の数量**（1〜99）と**1会計の行数**（1〜100）は別の上限で、
> 前者は打ち間違い対策、後者はリクエストサイズと運用の上限。混同すると、どちらかのチェックが抜ける。

---

## 7. エラー処理設計

### 7.1 エラーコード一覧

| コード | HTTP | 画面に出すメッセージ | 発生元 | 画面の挙動 |
|---|---:|---|---|---|
| `E-VAL-001` | 400 | 入力の形式が正しくありません | 形式違反（桁数・文字種） | 該当入力欄を強調し、フォーカスを戻す |
| `E-VAL-002` | 400 | 数量は1〜99で入力してください | 数量が範囲外 | 変更前の数量に戻す |
| `E-VAL-003` | 400 | 1回の会計に登録できるのは100行までです | 明細行数の上限 | 追加せず、リストは維持 |
| `E-AUTH-001` | 401 | IDまたはパスワードが違います | ログイン失敗 | ログイン画面に留まる。**IDが存在しないのか、パスワードが違うのかは区別して伝えない** |
| `E-AUTH-002` | 401 | ログインの有効期限が切れました。もう一度ログインしてください | トークン期限切れ・改ざん | ログイン画面へ遷移 |
| `E-AUTH-003` | 403 | この操作の権限がありません | ロール不足 | 直前の画面に戻る |
| `E-MEMB-001` | 404 | 会員が見つかりません | 会員未登録 | **非会員として続行**を選べるようにする（会計を止めない） |
| `E-PROD-001` | 404 | 商品がマスタ未登録です | 商品未登録・取扱終了 | リストに追加せず、入力欄をクリアしてフォーカスを戻す |
| `E-TXN-001` | 400 | 金額を再計算しました。内容を確認してもう一度お願いします | 金額照合の不一致 | **保存しない**。サーバ計算値で合計表示を更新し、購入ボタンを押し直させる |
| `E-TXN-002` | 400 | 商品が登録されていません | 明細0件で確定 | 購入ボタンを非活性に戻す |
| `E-SYS-001` | 500 | エラーが発生しました。店長に連絡してください | 想定外の例外 | **購入リストは保持**して再試行できるようにする |
| `E-SYS-002` | 503 | システムに接続できません | DB接続不可・バックエンド停止 | 手動レジ運用へ切り替える（NFR-OPS-02） |

### 7.2 エラー処理の方針

| # | 方針 | 理由 |
|---|---|---|
| ER-1 | **エラーで購入リストを消さない**（`E-AUTH-002` を除く） | お客様を待たせている最中にリストが消えるのが業務上いちばん困る。再スキャンのやり直しは避ける |
| ER-2 | 画面に出すのは「レジ担当が次に取れる行動」。技術的な原因は出さない | 「500 Internal Server Error」や例外の中身を見せても、パート・アルバイトは動けない。原因はサーバログに出す |
| ER-3 | 例外の詳細・スタックトレースをレスポンスに含めない | 内部構造やライブラリ構成のヒントを外に出さない（[§8.11](#811-その他の対策)） |
| ER-4 | ログイン失敗の理由を区別して返さない | 「そのIDは存在します」と教えると、有効なIDの洗い出しに使われる |
| ER-5 | `E-TXN-001` はサーバの計算値を添えて返す | 画面をサーバの正しい値に揃えられる。単に拒否するだけでは、レジ担当が同じ操作を繰り返すことになる |
| ER-6 | 想定外の例外は必ず `E-SYS-001` に丸めて返し、握りつぶさない | 無言で失敗するのがいちばん危ない。画面に何も出ないまま購入が保存されていない状況を作らない |

### 7.3 ログに出すもの・出さないもの

| 出す | 出さない |
|---|---|
| 発生日時、リクエストID、エンドポイント、HTTPステータス、エラーコード | パスワード（平文・ハッシュとも） |
| 担当ID（`cashier_id`）、取引ID | JWTの文字列、Cookieの中身 |
| 例外のスタックトレース（**サーバログのみ**） | 会員氏名などの個人情報 |
| 処理時間 | DB接続文字列・接続情報 |

> 学習用でも「ログに何を書かないか」を先に決めておく。あとから消すのは非常に難しい。

---

## 8. セキュリティ設計

講義で扱った対策を、本アプリのどこで実現するかの対応表。

| 講義の項目 | 本アプリでの実現 | 本書の該当節 |
|---|---|---|
| ログイン | 担当ID＋パスワード、bcryptハッシュ、失敗理由を伏せる | [8.1](#81-認証ログイン) |
| JWTトークン | HS256・有効期限8時間・httpOnly Cookie に保管 | [8.2](#82-jwt) |
| 認証認可 | ロール（`CASHIER` / `MANAGER`）をサーバ側で判定 | [8.3](#83-認可) |
| POSレジ機能 | 会計の全機能を認証必須の背後に置く | [8.1](#81-認証ログイン)〜[8.3](#83-認可) |
| BFF（リバースプロキシ） | Next.js Route Handlers が中継。ブラウザはAPIに直接触らない | [8.4](#84-bffリバースプロキシ) |
| CORS | 同一オリジン構成にし、APIは BFF のオリジンのみ許可 | [8.5](#85-cors) |
| バックエンドでも計算し、フロントの計算値と照合 | 購入確定時にサーバが再計算して照合。不一致は保存しない | [8.6](#86-金額のバックエンド再計算と照合) |
| Swagger Docs 非表示 | 本番は `docs_url` と **`openapi_url` の両方**を無効化 | [8.7](#87-swaggeropenapiドキュメントの非公開) |
| SQLインジェクション対策 | ORMのパラメータバインドのみ。文字列連結SQLを禁止 | [8.8](#88-sqlインジェクション対策) |
| 型定義 / Frontend / TypeScript | TypeScript＋zod と Pydantic の二重検証 | [8.9](#89-型定義による二重防御) |
| ORM | SQLAlchemy 2.0＋Alembic | [8.8](#88-sqlインジェクション対策) |
| ライブラリ・OSSの脆弱性 / Ver調査 | 採用バージョンを固定し、OSVに照会した結果を記録 | [8.10](#810-依存ライブラリの脆弱性とバージョン調査) |

### 8.1 認証（ログイン）

| # | 対策 | 内容 |
|---|---|---|
| S-1 | パスワードは **bcrypt でハッシュ化**して保存（NFR-SEC-02） | コスト係数 12。平文・可逆暗号は使わない。DBが漏れても元のパスワードに戻せない |
| S-2 | ハッシュ照合は**常に同じ時間**をかける | IDが存在しない場合もダミーハッシュと照合する。応答時間の差から有効なIDを推測されないため |
| S-3 | 失敗理由を区別して返さない（`E-AUTH-001` に統一） | ER-4 |
| S-4 | 連続失敗への制限 | 同一ログインIDに対し5回連続失敗で60秒間受け付けない。Lv2ではアプリのメモリ上のカウンタで実装する（**インスタンスが増えると効かない**簡易実装であることを承知の上での採用。恒久策はLv3候補） |
| S-5 | 会計に関わる全APIは認証必須 | 未認証は `401`。ログイン画面以外はサーバ側で弾く |

### 8.2 JWT

| 項目 | 設計 | 理由 |
|---|---|---|
| 署名アルゴリズム | `HS256`（共通鍵） | 学習規模に対して十分。鍵は32バイト以上のランダム値を環境変数で渡す |
| **検証時のアルゴリズム指定** | `jwt.decode(token, key, algorithms=["HS256"])` と**明示** | 指定を省くと、攻撃者が `alg: none` や別方式に差し替えたトークンを通せる余地が生まれる。ここは省略しない |
| ペイロード | `sub`（担当ID）、`role`、`iat`、`exp`、`iss` | **氏名や個人情報は入れない**。JWTは署名されているだけで、中身は誰でも読める（暗号化ではない） |
| 有効期限 | 8時間（1シフト） | 短すぎると会計の途中で切れて業務が止まる。長すぎると盗まれたときの被害が伸びる |
| 保管場所 | **httpOnly + Secure + SameSite=Lax の Cookie**（BFFが付与） | `localStorage` に置くと、XSSが1回でも成立した時点でJavaScriptから読み出せる。httpOnly なら読めない |
| ログアウト | BFFが Cookie を削除 | Lv2ではサーバ側の失効リストを持たない。**削除後もトークン自体は期限まで有効**という弱点を承知の上での採用（Lv3候補） |

### 8.3 認可

- ロールは `CASHIER`（会計操作）と `MANAGER`（＋履歴参照・マスタ管理）の2種類。JWTの `role` クレームで運ぶ。
- FastAPI の依存関数で判定する。

```python
def require_role(*allowed: str):
    def _dep(payload: TokenPayload = Depends(verify_token)) -> TokenPayload:
        if payload.role not in allowed:
            raise HTTPException(status_code=403, detail="E-AUTH-003")
        return payload
    return _dep
```

> **画面でボタンを隠すのは認可ではない。** 画面の出し分けは操作性のためであって、
> APIを直接叩かれれば無意味。**判定は必ずサーバ側**に置く。

### 8.4 BFF（リバースプロキシ）

BFF の仕事は2つだけ。**Cookie と Bearer トークンの詰め替え**と、**snake_case ⇄ camelCase の変換**。業務ロジックは持たせない。

```ts
// src/frontend/app/api/products/[productCode]/route.ts
export async function GET(req: NextRequest, { params }: { params: { productCode: string } }) {
  const token = req.cookies.get(process.env.SESSION_COOKIE_NAME!)?.value;
  if (!token) return NextResponse.json({ error: { code: "E-AUTH-002" } }, { status: 401 });

  // 環境変数はサーバ側でのみ参照する（NEXT_PUBLIC_ を付けない ＝ ブラウザに埋め込まれない）
  const res = await fetch(`${process.env.BACKEND_API_BASE_URL}/products/${params.productCode}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return NextResponse.json(toCamel(await res.json()), { status: res.status });
}
```

加えて、**バックエンドの App Service にアクセス制限をかけ、BFF の送信元以外からの要求を拒否**する。
BFFを置いてもバックエンドが誰からでも叩ける状態なら、隠した意味がない。

### 8.5 CORS

本構成では**ブラウザの通信相手は同一オリジンの BFF だけ**なので、クロスオリジン要求はそもそも発生しない。
それでも FastAPI 側に CORS 設定を書くのは、直接叩かれた場合の保険。

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o],
    allow_credentials=False,          # Bearer運用なのでCookieを跨がせない
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

| やらないこと | 理由 |
|---|---|
| `allow_origins=["*"]` | すべてのサイトのJavaScriptからAPIを呼べる状態になる。開発中の一時しのぎでも書かない |
| `allow_origins=["*"]` ＋ `allow_credentials=True` | ブラウザ仕様として拒否される組み合わせ。動かないうえに危険 |
| 許可メソッドに `DELETE`/`PUT` を含める | 本アプリに削除・更新APIは存在しない。使わないものは開けない |

### 8.6 金額のバックエンド再計算と照合

原則 P-1 の実装。**この節が課題「Backendでも計算のロジックを入れて、Frontendの計算値と照合」への直接の回答**。

1. 画面は `productCode` と `quantity`、そして**画面が計算した合計** `clientAmount` を送る。
2. サーバは**単価・税率・会員割引区分をマスタから引き直す**。画面から送られた単価や税率は受け取らない（[§5.4](#54-主要apiの入出力)）。
3. サーバは [§4.4](#44-金額計算の仕様) の手順で計算する。
4. `subtotal` / `discount` / `taxReduced` / `taxStandard` / `total` の**5項目すべて**が一致することを確認する。
5. 1つでも違えば `E-TXN-001` で拒否し、**保存しない**。サーバ計算値を返して画面を正しい値に更新させる。
6. DBに保存するのは**サーバの計算値だけ**。`clientAmount` はどこにも保存しない。

| 想定される攻撃・事故 | この設計での結果 |
|---|---|
| 画面のJavaScriptを書き換えて `total: 0` を送る | サーバ計算値と一致しないので拒否。0円で保存されない |
| リクエストに `unitPrice: 1` を混ぜる | スキーマに存在しない項目なので無視され、マスタの単価で計算される |
| 別の担当IDを `cashierId` として送る | 受け取らない。担当はJWTの `sub` から決まる |
| 画面の計算にバグがあり1円ずれる | 照合で検出され、保存前に止まる（**セキュリティ対策がバグ検出も兼ねる**） |

### 8.7 Swagger（OpenAPI）ドキュメントの非公開

```python
IS_PROD = os.getenv("APP_ENV") == "production"

app = FastAPI(
    title="POS API",
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None,
    openapi_url=None if IS_PROD else "/openapi.json",   # ここも必ず None にする
)
```

> **`docs_url` だけ消しても足りない。** `/openapi.json` が生きていると、API定義（全エンドポイント・全パラメータ・型）が
> そのまま読み取れてしまう。画面を消しても設計図が置いてあるのと同じなので、`openapi_url` も無効化する。
> 開発中は `APP_ENV=local` のときだけ有効になるようにして、開発しやすさは残す。

### 8.8 SQLインジェクション対策

| 層 | 対策 |
|---|---|
| 入力 | Pydantic で商品コード＝数字8/13桁、会員番号＝数字10桁に限定。**記号がそもそも通らない** |
| 実装 | SQLAlchemy 2.0 のクエリビルダのみ使用。SQLを書くのは `*Repository` クラスの中だけ |
| 例外 | 生SQLがどうしても必要なときは `text()` ＋ バインドパラメータ。**f文字列・`+` による連結を禁止** |
| DB権限 | アプリが使うDBユーザーから `DROP` / `ALTER` / `GRANT` と、履歴テーブルの `DELETE` を外す |

```python
# NG：文字列に値を埋め込む（末尾に OR 1=1 -- のような断片を差し込まれる）
session.execute(text(f"SELECT * FROM products WHERE product_code = {quoted_code}"))

# OK：ORMのクエリビルダ（値はパラメータとして分離される）
session.scalar(select(Product).where(Product.product_code == code))

# OK：やむを得ず生SQLを書く場合もバインドパラメータで
session.execute(text("SELECT * FROM products WHERE product_code = :code"), {"code": code})
```

### 8.9 型定義による二重防御

- **フロント**：`tsconfig.json` で `strict: true`。APIレスポンスは `zod` の `safeParse` を通してから使う。
- **バック**：Pydantic がリクエスト・レスポンスの両方を検証する。

```ts
const ProductSchema = z.object({
  productCode: z.string().regex(/^(\d{8}|\d{13})$/),
  productName: z.string().max(100),
  unitPrice: z.number().int().min(0).max(999_999),
  taxCategory: z.enum(["STANDARD", "REDUCED"]),
  taxRate: z.number().min(0).max(1),
});
```

> **TypeScript の型はビルド時に消える。** 実行時にネットワーク越しに来たJSONが型どおりである保証はどこにもない。
> だから境界（APIレスポンス）だけは zod で実行時にも検証する。逆に、アプリ内部の関数の引数まで zod で固める必要はない。

### 8.10 依存ライブラリの脆弱性とバージョン調査

**調査日：2026-09-09**／照会先：npm registry、PyPI、[OSV.dev](https://osv.dev)（脆弱性データベース）。

| 分類 | パッケージ | 採用バージョン | 既知の脆弱性（OSV照会） | 備考 |
|---|---|---|---|---|
| フロント | `next` | 16.3.4 | なし | 調査時点の最新 |
| フロント | `react` | 19.2.8 | なし | 同上 |
| フロント | `typescript` | 7.0.2 | なし | 同上 |
| フロント | `zod` | 4.5.4 | なし | 実行時検証 |
| バック | `fastapi` | 0.141.1 | なし | 同上 |
| バック | `uvicorn` | 0.52.4 | なし | ASGIサーバ |
| バック | `sqlalchemy` | 2.0.52 | なし | ORM |
| バック | `alembic` | 1.19.2 | なし | マイグレーション |
| バック | `pydantic` | 2.13.5 | なし | 型検証 |
| バック | `pymysql` | 1.2.0 | なし | MySQLドライバ |
| バック | `pyjwt` | 2.13.0 | なし | JWT |
| バック | `bcrypt` | 5.0.0 | なし | パスワードハッシュ |
| 実行環境 | Node.js / Python | 24.15.0 / 3.12系 | — | 開発機の Node は 24.15.0。Python は開発機 3.10.11、本番は App Service で 3.12 系を選択する想定 |

**調査して分かったこと（`passlib` を採用しない判断）**

FastAPI のチュートリアルでは、パスワードハッシュに `passlib` を使う例が広く出回っている。しかし調べたところ：

- `passlib` の最新版は **1.7.4／最終リリース 2020-10-08**（約6年更新が止まっている）
- 既知の脆弱性としては登録されていないが、**メンテナンスが止まったライブラリを認証の中心に置くのは避けたい**
- 実際、新しい `bcrypt`（4.1以降）との組み合わせでバージョン検出に失敗し、警告が出る不整合が知られている

→ **本アプリでは `passlib` を使わず、`bcrypt`（5.0.0、2025-09-25）を直接呼ぶ**。
代替として `pwdlib`（0.3.1、2026-08-12）も候補だが、依存を1つ減らせる `bcrypt` 直利用を採る。

> **これが「Ver調査」の意味だと理解した点**：最新版を並べるだけでなく、**「最終リリース日」を見て、
> そのライブラリが今も手入れされているかを確かめる**。脆弱性が0件でも、更新の止まったライブラリは
> 今後見つかる脆弱性が直らない。チュートリアルに書いてあるからという理由で選ばない。

**継続的な運用**

| 頻度 | やること |
|---|---|
| 毎回（CI／手元） | `npm audit` ／ `pip-audit` を実行し、`high` 以上が出たらマージしない |
| 常時 | GitHub の Dependabot alerts を有効化（publicリポジトリなので無料で使える） |
| 月1回 | 依存の最新版と最終リリース日を確認し、本表を更新する |

### 8.11 その他の対策

| # | 対策 | 内容 |
|---|---|---|
| S-6 | HTTPS の強制 | App Service の「HTTPS Only」を有効化。Cookie に `Secure` を付ける前提が成立する |
| S-7 | CSRF対策 | Cookie を `SameSite=Lax` にする。加えて、状態を変える操作は `POST` ＋ `Content-Type: application/json` に限定する（HTMLフォームからは送れない形式にする） |
| S-8 | セキュリティヘッダ | `X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer`、`X-Frame-Options: DENY`、Content-Security-Policy を Next.js の `headers()` で付与 |
| S-9 | 秘密情報 | 環境変数のみ（[§2.4](#24-環境変数)）。`.env` は `.gitignore` 済み。**publicリポジトリなので、鍵をコミットしたら即ローテーション**する |
| S-10 | DB接続 | SSL必須。パブリックアクセスは許可せず、App Service からのみ到達できるようにする |
| S-11 | 個人情報 | 会員は架空データのみ（NFR-SEC-06）。JWTにもログにも氏名を入れない |

### 8.12 攻撃シナリオと対策の対応

| # | シナリオ | 主な対策 |
|---|---|---|
| T-1 | ログインを総当たりで突破する | 連続失敗の制限（S-4）、失敗理由を伏せる（ER-4）、パスワード最低8文字 |
| T-2 | XSSでトークンを盗む | httpOnly Cookie（[§8.2](#82-jwt)）、React の既定のエスケープ、CSP（S-8） |
| T-3 | 画面を書き換えて0円で購入確定する | サーバでの再計算と照合（[§8.6](#86-金額のバックエンド再計算と照合)） |
| T-4 | 他人の担当IDで取引を登録する | 担当IDはJWTから決定。リクエストからは受け取らない |
| T-5 | 商品コード欄からSQLを注入する | 数字のみのバリデーション＋ORMのパラメータバインド（[§8.8](#88-sqlインジェクション対策)） |
| T-6 | APIの仕様を調べて弱点を探す | Swagger・OpenAPI非公開（[§8.7](#87-swaggeropenapiドキュメントの非公開)）、BFFでのAPI隠蔽、アクセス制限 |
| T-7 | 悪意あるサイトから会計APIを呼ばせる | 同一オリジン構成＋CORS限定（[§8.5](#85-cors)）、`SameSite=Lax`、JSON限定（S-7） |
| T-8 | 依存ライブラリの既知の穴を突く | バージョン固定とOSV照会、Dependabot（[§8.10](#810-依存ライブラリの脆弱性とバージョン調査)） |
| T-9 | 購入履歴を消して売上をごまかす | 履歴の更新・削除APIを作らない。DBユーザーから `DELETE` 権限を外す（D-5） |

---

## 9. 画面設計

### 9.1 画面遷移

```mermaid
stateDiagram-v2
    state "ログイン画面" as login
    state "レジ画面" as pos

    [*] --> login
    login --> pos : ログイン成功
    login --> login : E-AUTH-001 認証失敗
    pos --> login : ログアウト／E-AUTH-002 期限切れ
    pos --> [*]
```

Lv2 の画面は2つだけ（要件定義書 §3.2）。**レジ画面から他の画面へ遷移しない**のは、
会計の途中で操作が分岐すると、お客様を待たせる時間が伸びるため。

### 9.2 レジ画面のレイアウト

上から下へ、業務の順番どおりに並べる。レジ未経験のアルバイトが10分の説明で使えることが要件（NFR-PERF-02）。

```
┌──────────────────────────────────────────────┐
│ あおぞらマート POS      担当：山田（レジ）  [ログアウト] │
├──────────────────────────────────────────────┤
│ ① 会員カード                                          │
│   [ 会員番号 ______________ ] [読み込み] [会員なし]     │
│   → 会員：佐藤 花子 様（割引対象）                      │
├──────────────────────────────────────────────┤
│ ② 商品                                                │
│   [ バーコード／商品コード ______ ] [ 追 加 ]           │
│   ※エラーはこの直下に表示し、入力欄へフォーカスを戻す      │
├──────────────────────────────────────────────┤
│ ③ 購入リスト                                          │
│  ┌────────────┬──────┬────┬──────┬────┐ │
│  │ 商品名      │  単価 │ 数量│  金額 │ 削除│ │
│  ├────────────┼──────┼────┼──────┼────┤ │
│  │ おにぎり 鮭 ※│  128 │[2]▲▼│   256 │ [×] │ │
│  │ 牛乳 1L    ※│  218 │[1]▲▼│   218 │ [×] │ │
│  │ 食器用洗剤   │  298 │[1]▲▼│   298 │ [×] │ │
│  └────────────┴──────┴────┴──────┴────┘ │
│                              ※ ＝ 軽減税率8%対象       │
├──────────────────────────────────────────────┤
│ ④ 合計                                                │
│    税抜合計                                  772 円    │
│    会員割引（5%）                          − 38 円    │
│    消費税  8%対象 450円 →  36 円 ／ 10%対象 284円 → 28 円 │
│    ──────────────────────────────      │
│    お支払い金額（税込）                     798 円    │
├──────────────────────────────────────────────┤
│                 [    購  入    ]                       │
└──────────────────────────────────────────────┘
```

| 画面要素 | 対応機能 | 設計上の注意 |
|---|---|---|
| ① 会員カード | F-02, F-07 | 読み込み後は「割引対象」を明示する。非会員でも会計を止めない |
| ② 商品入力 | F-03, F-04, F-05 | **追加後は入力欄を空にしてフォーカスを戻す**。連続スキャンが止まらないようにする |
| ③ 購入リスト | F-06 | 軽減税率対象に `※` を付ける。数量は上下ボタンと直接入力の両方 |
| ④ 合計 | F-08 | 税率区分ごとの内訳を常に表示。会員割引は「−」付きで別行にする |
| 購入ボタン | F-09〜F-11 | 明細0件のときは押せない。押した直後は二重送信を防ぐため非活性にする |

### 9.3 レジ画面の状態

```mermaid
stateDiagram-v2
    state "会員待ち" as s1
    state "商品登録中" as s2
    state "確定処理中" as s3
    state "確定完了の表示" as s4

    [*] --> s1
    s1 --> s2 : 会員を読み込む／会員なしを選ぶ
    s2 --> s2 : 商品追加・数量変更・行削除
    s2 --> s3 : 購入ボタン
    s3 --> s2 : E-TXN-001 金額不一致（保存しない）
    s3 --> s4 : 保存成功
    s4 --> s1 : リストと会員情報をクリア（F-11）
```

「確定処理中」を独立した状態として持つのは、**購入ボタンの二重押しで取引が2件保存されるのを防ぐ**ため。

---

## 10. テスト観点

設計が正しく実装されたかを確認する観点。数値は [§4.4](#44-金額計算の仕様) の計算例を使う。

| # | 区分 | 観点 | 期待結果 |
|---|---|---|---|
| TC-01 | 正常 | 会員・8%と10%混在で購入確定 | 税抜772／割引38／消費税36と28／税込798 で保存される |
| TC-02 | 正常 | 同じ買い物を非会員で購入確定 | 割引0／消費税37と29／税込838 |
| TC-03 | 正常 | 同一商品を2回スキャン | 行が増えず数量が2になる（F-03） |
| TC-04 | 正常 | 購入確定後の画面 | リストと会員情報が空になり、会員読み込みから再開できる（F-11） |
| TC-05 | 正常 | 税率マスタに新しい行を追加（8%→1%） | **再デプロイなしで**以後の会計に新税率が適用される（REQ-08 / NFR-OPS-04） |
| TC-06 | 正常 | 税率改定後に過去の履歴を参照 | 過去の取引は購入時点の税率のまま（D-1） |
| TC-07 | 境界 | 数量に1／99を入力 | どちらも登録できる |
| TC-08 | 境界 | 数量に0／100を入力 | `E-VAL-002` で拒否。変更前の数量に戻る |
| TC-09 | 境界 | 明細100行目／101行目の追加 | 100行目は成功、101行目は `E-VAL-003` |
| TC-10 | 異常 | 明細0件で購入ボタン | ボタンが押せない。APIを直接叩いた場合は `E-TXN-002` |
| TC-11 | 異常 | マスタ未登録の商品コード | `E-PROD-001`。リストに追加されない（F-05） |
| TC-12 | 異常 | 会員番号が9桁 | `E-VAL-001`。照会そのものを行わない |
| TC-13 | **セキュリティ** | `clientAmount.total` を0に書き換えて送信 | `E-TXN-001` で拒否。**DBに保存されない**（[§8.6](#86-金額のバックエンド再計算と照合)） |
| TC-14 | **セキュリティ** | `unitPrice` を混ぜて送信 | 無視され、マスタの単価で計算される |
| TC-15 | **セキュリティ** | 未ログインで `/api/transactions` を直接呼ぶ | `401 E-AUTH-002` |
| TC-16 | **セキュリティ** | ブラウザのJavaScriptから `document.cookie` を読む | セッションCookieが含まれない（httpOnly） |
| TC-17 | **セキュリティ** | 本番環境で `/docs` と `/openapi.json` を開く | どちらも `404`（[§8.7](#87-swaggeropenapiドキュメントの非公開)） |
| TC-18 | **セキュリティ** | 商品コード欄にSQL断片を入力 | バリデーションで拒否。DBに到達しない |
| TC-19 | 運用 | 購入ボタンを素早く2回押す | 取引は1件だけ保存される（[§9.3](#93-レジ画面の状態)） |
| TC-20 | 運用 | バックエンドを停止して会計 | `E-SYS-002` を表示。購入リストは消えない（ER-1） |

---

## 11. Lv3 への拡張余地

Lv2 では意図的に採らなかった設計を、判断の記録として残す。**今やらない理由**まで書いておくと、後で見直すときに迷わない。

| # | 項目 | Lv2での扱い | 今やらない理由 |
|---|---|---|---|
| X-1 | JWTのリフレッシュトークン・サーバ側の失効リスト | 有効期限8時間の単一トークンのみ | 仕組みが増えるわりに、1店舗・1シフトの運用では効果が薄い。ログアウト後もトークンが期限まで有効という弱点は [§8.2](#82-jwt) に明記した |
| X-2 | ログイン試行制限の外部化（Redis等） | アプリのメモリ上のカウンタ | インスタンスが1台の間は成立する。増やす段階で作り直す（S-4） |
| X-3 | 返品・取引取消 | スコープ外（B-4） | 会計の逆仕訳という別の業務設計が必要で、Lv2の要求に含まれない |
| X-4 | レシート印刷・電子レシート | スコープ外 | ハードウェア依存が入る |
| X-5 | マスタ管理画面 | DB直接メンテで代替（B-7） | 管理画面を作ると認可の設計が一段深くなる。`MANAGER` ロールの枠だけ用意した（[§8.3](#83-認可)） |
| X-6 | 売上分析・ダッシュボード | 履歴の保存まで | 購入履歴のデータ設計（§4）は、後から集計できる形にしてある |
| X-7 | ユーザーストーリー・カスタマージャーニー | 未着手 | Lv3向けの課題（要件定義書 §5） |

---

## 12. 未確定事項・改訂履歴

### 12.1 未確定事項

| # | 事項 | 状態 |
|---|---|---|
| Q-1 | 会員割引の内容（税抜合計から5%）は本プロジェクトの設定。講座指定があればそれに従う | 要件定義書 Q-3 から継続 |
| Q-2 | バーコードの読み取り方式（ハードウェアスキャナ／カメラ／手入力で代用） | **手入力で代用**する前提で設計した。実機スキャナは「キーボード入力＋Enter」として振る舞うため、入力欄の設計は変えなくてよい |
| Q-3 | 会計の途中でトークンが切れた場合、購入リストを復帰させるか | Lv2では復帰させない（リストはブラウザのメモリ上のみ）。有効期限8時間で発生確率を下げる方針 |
| Q-4 | Azure App Service の Python バージョン | 3.12 系を想定。デプロイ時に選択可能なものを確認する |

### 12.2 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 1.0 | 2026-09-09 | 初版。要件定義書 v0.2 を受けて、構成・UML・ER図・API・入力上下限・エラー処理・セキュリティを設計 |

---

## 13. 生成AI活用の記録

課題要件「生成AIを使った部分を記載」への対応。本書は **Claude Code（Claude Opus 5）との対話で作成**した。

### 13.1 何をAIにやらせ、何を人間が決めたか

| 工程 | 人間（青山）の判断 | AI（Claude Code）がやったこと |
|---|---|---|
| 前提の確定 | 技術スタックを Next.js＋FastAPI＋Azure DB for MySQL に確定。Lv2で進めることを決定 | 判断が分かれる点だけを2問に絞って提示（推奨案つき） |
| 構成設計 | BFF方式の採用を承認 | BFFを置く理由を3点に整理し、置かない場合との差を提示 |
| UML | 図の種類と粒度を承認 | ユースケース図・アクティビティ図・シーケンス図3種・クラス図を Mermaid で記述 |
| 金額計算の仕様 | 会員割引5%・端数切り捨ての方針を裁定 | 税率区分ごとの端数処理と割引の按分順序を仕様化し、計算例で検証 |
| バージョン調査 | 「Ver調査」を実測でやると決定 | **npm registry・PyPI・OSV.dev にスクリプトで照会**し、採用バージョンと既知脆弱性を取得（[§8.10](#810-依存ライブラリの脆弱性とバージョン調査)） |
| ライブラリ選定 | `passlib` を使わない判断を承認 | 最終リリース日を調べて根拠を提示（2020-10-08） |
| 検品 | これから（実装しながら設計の穴を見つける） | 未確定事項を §12 に明示 |

### 13.2 うまくいったこと

- **調べられることはAIに実際に調べさせる。** バージョン表を記憶や推測で書かせず、レジストリとOSVに照会させた。
  結果として `passlib` がメンテ停止していることに気づけた。これは自分では調べようと思っていなかった観点。
- **「なぜそうしないのか」を書かせる。** 対策の一覧だけなら誰でも作れるが、
  「`docs_url` だけ消しても `/openapi.json` から読める」「画面でボタンを隠すのは認可ではない」のように、
  やりがちな不十分な対策を並べて書かせると、自分の理解の穴が見える。
- **計算仕様を数値例で検証させた。** 端数処理は文章だけだと必ず解釈が割れる。
  例（税込798円）まで書いておけば、実装時にテストケースがそのまま作れる。

### 13.3 困りごと・仲間へのシェア

- **AIは「もっともらしい設計」をいくらでも出せる。** Lv2の要件定義でも同じ失敗をしていて
  （公式要求を読ませる前のAI出力は要求と食い違っていた）、今回も要件定義書v0.2を先に読ませてから書かせた。
  **上位文書を先に読ませる工程を必ず挟む**のが、AI駆動開発でいちばん効く型だと感じている。
- 会社のPCは社内プロキシ配下で、SSH（`git@github.com`）が通らなかった。HTTPSでクローンして解決。
  同じ環境の人は `git config --global http.proxy` の確認から入ると早い。
- 設計仕様書は分量が出る。**章立てを先に決めてから書く**と、AIに投げる単位も分けやすい。

詳細な作業ログは [docs/ai-dev-log/](../ai-dev-log/) に蓄積している。
