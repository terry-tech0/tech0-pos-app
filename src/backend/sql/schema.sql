-- ============================================================
-- Lv2 簡易POSアプリ改 スキーマ定義
-- 対応文書: 設計仕様書 §4.1 ER図 / §4.2 テーブル定義
--
-- 課題の指示「Step3-1,2で使ったMySQLにスキーマ新規追加して使用」に対応。
-- 既存のスキーマ（データベース）とは別に pos_terry を作って使う。
--
-- 実行方法:
--   mysql -h <host> -u <user> -p --ssl-mode=REQUIRED < schema.sql
-- または scripts/init_db.py（SQLAlchemy 経由）
--
-- 金額はすべて INT（税抜・税込とも整数の円）。
-- 浮動小数点（FLOAT/DOUBLE）は誤差が出るため使わない（設計 §4.2）。
-- 税率だけ DECIMAL(5,4)（例 0.0800）。
-- ============================================================

CREATE DATABASE IF NOT EXISTS pos_terry
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE pos_terry;

-- ------------------------------------------------------------
-- cashiers: レジ担当
-- パスワードは bcrypt ハッシュのみ保存（NFR-SEC-02）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cashiers (
  cashier_id    INT           NOT NULL AUTO_INCREMENT,
  login_id      VARCHAR(20)   NOT NULL,
  cashier_name  VARCHAR(50)   NOT NULL,
  -- bcrypt のハッシュは常に60文字
  password_hash CHAR(60)      NOT NULL,
  role          ENUM('CASHIER','MANAGER') NOT NULL DEFAULT 'CASHIER',
  -- 退職者は FALSE。物理削除しない（設計 §4.3 D-6）
  is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (cashier_id),
  UNIQUE KEY uk_cashiers_login_id (login_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- members: 会員
-- 学習用の架空データのみ（NFR-SEC-06）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS members (
  member_code   CHAR(10)      NOT NULL,
  member_name   VARCHAR(50)   NOT NULL,
  discount_type ENUM('NONE','RATE5') NOT NULL DEFAULT 'NONE',
  joined_on     DATE          NULL,
  is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
  PRIMARY KEY (member_code)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- products: 商品マスタ
-- 商品コードは JAN（8桁または13桁）。桁の検証はアプリ側で行う
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
  product_code  VARCHAR(13)   NOT NULL,
  product_name  VARCHAR(100)  NOT NULL,
  -- 税抜・整数円 0〜999,999（設計 §6）。DB制約を最後の砦として置く
  unit_price    INT           NOT NULL,
  tax_category  ENUM('STANDARD','REDUCED') NOT NULL,
  -- 取扱終了は FALSE。未登録と取扱終了を画面で区別しない（設計 §5.4 A-05）
  is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
  updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (product_code),
  KEY ix_products_tax_category (tax_category),
  CONSTRAINT ck_products_unit_price CHECK (unit_price BETWEEN 0 AND 999999)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- tax_rates: 税率マスタ
-- 主キーが (区分, 適用開始日) なので、税率改定は「行の追加」で表現できる。
-- 既存行を書き換えないので過去の税率も残る（REQ-08 / NFR-OPS-04 / 設計 §4.3 D-2）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tax_rates (
  tax_category  ENUM('STANDARD','REDUCED') NOT NULL,
  valid_from    DATE          NOT NULL,
  rate          DECIMAL(5,4)  NOT NULL,
  -- NULL は現行（終了日が決まっていない）
  valid_to      DATE          NULL,
  PRIMARY KEY (tax_category, valid_from),
  CONSTRAINT ck_tax_rates_rate CHECK (rate BETWEEN 0.0000 AND 1.0000)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- transactions: 購入履歴のヘッダ
-- 追記のみ。アプリから UPDATE / DELETE しない（NFR-OPS-05 / 設計 §4.3 D-5）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
  transaction_id  BIGINT      NOT NULL AUTO_INCREMENT,
  -- ミリ秒まで保持する（同一秒に複数会計が入るため）
  transacted_at   DATETIME(3) NOT NULL,
  -- JWT の sub から確定した担当。リクエストからは受け取らない（設計 §5.4 A-07）
  cashier_id      INT         NOT NULL,
  -- 非会員は NULL。ダミー会員で表さない（設計 §4.3 D-3）
  member_code     CHAR(10)    NULL,
  subtotal        INT         NOT NULL,
  -- API の Amount では discount。DBのカラム名は discount_amount（設計 §4.1）
  discount_amount INT         NOT NULL,
  -- 税率区分ごとに2列で持つ。合算だけだと内訳を復元できない（設計 §4.3 D-4）
  tax_reduced     INT         NOT NULL,
  tax_standard    INT         NOT NULL,
  total           INT         NOT NULL,
  created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (transaction_id),
  KEY ix_transactions_transacted_at (transacted_at),
  KEY ix_transactions_cashier_id (cashier_id),
  CONSTRAINT fk_transactions_cashier
    FOREIGN KEY (cashier_id) REFERENCES cashiers (cashier_id),
  CONSTRAINT fk_transactions_member
    FOREIGN KEY (member_code) REFERENCES members (member_code)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- transaction_lines: 購入履歴の明細
-- 商品名・単価・税率区分・適用税率を購入時点の値で転記する（原則 P-3 / D-1）。
-- マスタの単価や税率を後から変えても、過去の履歴は動かない
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transaction_lines (
  transaction_id   BIGINT       NOT NULL,
  line_no          SMALLINT     NOT NULL,
  product_code     VARCHAR(13)  NOT NULL,
  -- ここから4つが「購入時点の転記」
  product_name     VARCHAR(100) NOT NULL,
  unit_price       INT          NOT NULL,
  quantity         SMALLINT     NOT NULL,
  tax_category     ENUM('STANDARD','REDUCED') NOT NULL,
  applied_tax_rate DECIMAL(5,4) NOT NULL,
  line_amount      INT          NOT NULL,
  PRIMARY KEY (transaction_id, line_no),
  KEY ix_transaction_lines_product_code (product_code),
  CONSTRAINT fk_transaction_lines_transaction
    FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id),
  CONSTRAINT fk_transaction_lines_product
    FOREIGN KEY (product_code) REFERENCES products (product_code),
  -- 1行あたりの数量は 1〜99（設計 §6）。打ち間違い（2 -> 22 -> 222）を止める
  CONSTRAINT ck_transaction_lines_quantity CHECK (quantity BETWEEN 1 AND 99)
) ENGINE=InnoDB;
