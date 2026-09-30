# tech0-pos-app

Tech0 Step4 の課題で作る POS アプリのプロジェクトリポジトリ。
約3ヶ月かけて Lv1 → Lv2 → その先へと段階的に育てていく。

## 題材

**小型食品スーパー**のレジ（POS）を想定。
食品（軽減税率 8%）と日用雑貨（標準税率 10%)が混在する売場を扱うことで、
税率対応を含む現実的な要件定義・実装を学ぶ。

## 開発スタイル

**AI駆動開発**（Claude Code を中心に据え、AIに指示し人が判断する）で進める。

- 生成AIを使った箇所・プロンプト・困りごとは [docs/ai-dev-log/](docs/ai-dev-log/) に記録する
- 要件定義 → 設計 → 実装の各ドキュメントは Markdown で管理する

## ディレクトリ構成

```
tech0-pos-app/
├── README.md
├── CLAUDE.md              # AI駆動開発の前提・規約（Claude Code が毎回読む）
├── docs/
│   ├── requirements/      # 要件定義書
│   ├── design/            # 設計仕様書
│   ├── test/              # テスト仕様書（総則＋詳細4本＋テストデータ）
│   └── ai-dev-log/        # 生成AI活用の記録・学び・失敗の共有ネタ
└── src/                   # アプリ本体（Lv1/Lv2 実装時に追加）
```

## V字モデルでの進め方

要求から実装へ下りていく左側と、テストで確かめる右側を、文書レベルで1対1に対応させている。

```
  要求（講座配布の要求定義書）  ←────→  ユーザーテスト（UAT）
  要件定義書 §3 機能要件        ←────→  結合・機能テスト（IT）
  設計仕様書（クラス・API・DB）  ←────→  単体テスト（UT / jest・pytest）
                    └── 実装 ──┘
```

設計仕様書 §10 のテスト観点 `TC-01`〜`TC-20` が、
テスト仕様書で190のテストケースへ詳細化されている。

## ドキュメント

| ドキュメント | 版 | 場所 |
|---|---|---|
| Lv2 POS 要件定義書 | v0.2 | [docs/requirements/POS-Lv2-要件定義書.md](docs/requirements/POS-Lv2-要件定義書.md) |
| Lv2 POS 設計仕様書 | v1.0 | [docs/design/POS-Lv2-設計仕様書.md](docs/design/POS-Lv2-設計仕様書.md) |
| **Lv2 POS テスト仕様書（総則）** | v1.0 | [docs/test/POS-Lv2-テスト仕様書.md](docs/test/POS-Lv2-テスト仕様書.md) |
| └ 単体テスト（Backend / pytest） | | [docs/test/01-単体テスト-backend-pytest.md](docs/test/01-単体テスト-backend-pytest.md) |
| └ 単体テスト（Frontend / jest） | | [docs/test/02-単体テスト-frontend-jest.md](docs/test/02-単体テスト-frontend-jest.md) |
| └ 結合・機能テスト | | [docs/test/03-結合機能テスト.md](docs/test/03-結合機能テスト.md) |
| └ ユーザーテスト（UAT） | | [docs/test/04-ユーザーテスト.md](docs/test/04-ユーザーテスト.md) |
| └ テストデータ | | [docs/test/fixtures/](docs/test/fixtures/) |
| AI活用ログ | | [docs/ai-dev-log/](docs/ai-dev-log/) |

## 実装の状況（2026-09-30 時点）

Lv2 のコードを実装中。**単体テスト 141 件が全件合格**、TypeScript の型チェックはエラー0。

| 層 | 実装 | 単体テスト |
|---|---|---|
| バックエンド（FastAPI） | `AmountCalculator` / `AuthService` / `CheckoutService` / API B-01〜B-07 | **94 件合格**（pytest） |
| フロントエンド（Next.js） | BFF A-01〜A-07 ／ ログイン画面 ／ レジ画面 ／ 画面側の金額計算 | **47 件合格**（jest） |
| DB | スキーマ定義（`sql/schema.sql`）・投入スクリプト | 未実行 |

**画面とサーバで同じ金額になることの確認**：設計 §4.4 の計算手順を Python と TypeScript の
両方に実装しているため、ランダム 3,000 ケース（税率5パターン）で両者の結果を突き合わせ、
**不一致0件**を確認した。税率は要求 REQ-08 により変わりうるので、
画面側は税率を 1/10000 単位の整数に直して整数演算だけで計算している。

### 未実施（今週対応）

- DB への接続と投入、結合テスト（46件）、ユーザーテスト（18件）
  → 会社のネットワークが直接のTCP通信を塞いでいて Azure MySQL に到達できないため、自宅環境で実施する
- 設計仕様書への確認事項 T-1〜T-7 の設計側での確定（本実装では推奨値を採用し、コード内に根拠を明記）

## 動かし方

### バックエンド

```powershell
cd srcackend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# .env.example を .env にコピーし、DATABASE_URL と JWT_SECRET_KEY を設定する
.venv\Scripts\python.exe -m scripts.init_db    # テーブル作成
$env:SEED_CASHIER_PASSWORD = "<任意のテスト用パスワード>"
.venv\Scripts\python.exe -m scripts.seed       # fixtures の投入
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

単体テストは DB を使わないので、`.env` が無くても動く。

```powershell
cd srcackend
.venv\Scripts\python.exe -m pytest
```

### フロントエンド

```powershell
cd srcrontend
npm install
# .env.local.example を .env.local にコピーする
npm run dev        # http://localhost:3000
npm run typecheck  # 型チェック
npm test           # 単体テスト（jest）
```

社内プロキシ環境では `npm install --proxy http://<プロキシ>:8080 --https-proxy http://<プロキシ>:8080`、
`pip install --proxy http://<プロキシ>:8080` を付ける。
