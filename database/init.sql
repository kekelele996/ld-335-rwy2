-- 费用上传批次：费用链路的唯一凭据
CREATE TABLE IF NOT EXISTS expense_batches (
  id SERIAL PRIMARY KEY,
  batch_no VARCHAR(64) UNIQUE NOT NULL,
  visit_no VARCHAR(64) NOT NULL,
  insured_id VARCHAR(32) NOT NULL,
  total_amount NUMERIC(12, 2) NOT NULL,
  item_count INTEGER NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reversed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_expense_batches_visit_no ON expense_batches (visit_no);
CREATE INDEX IF NOT EXISTS ix_expense_batches_insured_id ON expense_batches (insured_id);

-- 同一就诊号只允许存在一个未冲正批次；冲正后该索引不再占用，可重新上传
CREATE UNIQUE INDEX IF NOT EXISTS ux_expense_batches_visit_active
  ON expense_batches (visit_no)
  WHERE status = 'ACTIVE';

-- 费用明细
CREATE TABLE IF NOT EXISTS expense_items (
  id SERIAL PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES expense_batches (id),
  line_no INTEGER NOT NULL,
  item_code VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  category VARCHAR(32) NOT NULL,
  catalog_class VARCHAR(8) NOT NULL,
  unit_price NUMERIC(12, 4) NOT NULL,
  quantity NUMERIC(12, 4) NOT NULL,
  amount NUMERIC(12, 2) NOT NULL,
  self_pay_ratio NUMERIC(6, 4) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_expense_items_batch_id ON expense_items (batch_id);
CREATE INDEX IF NOT EXISTS ix_expense_items_item_code ON expense_items (item_code);

-- 预结算凭证：服务端核算生成，正式结算只认凭证号
CREATE TABLE IF NOT EXISTS presettlement_vouchers (
  id SERIAL PRIMARY KEY,
  voucher_no VARCHAR(64) UNIQUE NOT NULL,
  batch_no VARCHAR(64) NOT NULL REFERENCES expense_batches (batch_no),
  region VARCHAR(64) NOT NULL,
  total_amount NUMERIC(12, 2) NOT NULL,
  reimbursed_amount NUMERIC(12, 2) NOT NULL,
  account_pay_amount NUMERIC(12, 2) NOT NULL,
  self_pay_amount NUMERIC(12, 2) NOT NULL,
  deductible NUMERIC(12, 2) NOT NULL,
  reimbursement_ratio NUMERIC(6, 4) NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'VALID',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  settled_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_presettlement_vouchers_batch_no ON presettlement_vouchers (batch_no);

-- 正式结算单
CREATE TABLE IF NOT EXISTS settlement_records (
  id SERIAL PRIMARY KEY,
  settlement_no VARCHAR(64) UNIQUE NOT NULL,
  voucher_no VARCHAR(64) NOT NULL,
  batch_no VARCHAR(64) NOT NULL,
  visit_no VARCHAR(64) NOT NULL,
  insured_id VARCHAR(32) NOT NULL,
  total_amount NUMERIC(12, 2) NOT NULL,
  reimbursed_amount NUMERIC(12, 2) NOT NULL,
  account_pay_amount NUMERIC(12, 2) NOT NULL,
  self_pay_amount NUMERIC(12, 2) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'SUCCESS',
  settlement_date DATE NOT NULL DEFAULT CURRENT_DATE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reversed_at TIMESTAMP,
  CONSTRAINT ux_settlements_voucher UNIQUE (voucher_no)
);

CREATE INDEX IF NOT EXISTS ix_settlement_records_batch_no ON settlement_records (batch_no);
CREATE INDEX IF NOT EXISTS ix_settlement_records_visit_no ON settlement_records (visit_no);
CREATE INDEX IF NOT EXISTS ix_settlement_records_insured_id ON settlement_records (insured_id);
CREATE INDEX IF NOT EXISTS ix_settlement_records_settlement_date ON settlement_records (settlement_date);

CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  client_id VARCHAR(64) NOT NULL,
  path VARCHAR(255) NOT NULL,
  action VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
