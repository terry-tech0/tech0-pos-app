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
