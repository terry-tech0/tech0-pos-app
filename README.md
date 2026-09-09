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
│   ├── requirements/      # 要件定義書（Lv2 課題の提出物はここ）
│   ├── design/            # 設計ドキュメント
│   └── ai-dev-log/        # 生成AI活用の記録・学び・失敗の共有ネタ
└── src/                   # アプリ本体（Lv1/Lv2 実装時に追加）
```

## ドキュメント

| ドキュメント | 場所 |
|---|---|
| Lv2 POS 要件定義書 | [docs/requirements/POS-Lv2-要件定義書.md](docs/requirements/POS-Lv2-要件定義書.md) |
| **Lv2 POS 設計仕様書** | [docs/design/POS-Lv2-設計仕様書.md](docs/design/POS-Lv2-設計仕様書.md) |
| AI活用ログ | [docs/ai-dev-log/](docs/ai-dev-log/) |
