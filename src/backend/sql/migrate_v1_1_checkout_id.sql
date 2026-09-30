-- ============================================================
-- 設計 v1.1：transactions に会計の整理番号 checkout_id を追加する（設計 §4.3 D-7）
-- 既に v1.0 のテーブルを作ってある環境で1回だけ流す。新規作成なら schema.sql だけでよい。
--
-- 既存の取引には整理番号が無いので、UUID() で1件ずつ振ってから NOT NULL と一意制約をかける。
-- ============================================================

ALTER TABLE transactions ADD COLUMN checkout_id CHAR(36) NULL AFTER transaction_id;
UPDATE transactions SET checkout_id = UUID() WHERE checkout_id IS NULL;
ALTER TABLE transactions MODIFY checkout_id CHAR(36) NOT NULL;
ALTER TABLE transactions ADD UNIQUE KEY uq_transactions_checkout_id (checkout_id);
