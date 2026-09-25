CREATE TABLE IF NOT EXISTS expense_batches (
  id SERIAL PRIMARY KEY,
  batch_no VARCHAR(64) UNIQUE NOT NULL,
  visit_no VARCHAR(64) NOT NULL,
  insured_id VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
  total_amount NUMERIC(12, 2) NOT NULL,
  item_count INTEGER NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_batches_open_visit
  ON expense_batches (visit_no)
  WHERE status IN ('UPLOADED', 'PRE_SETTLED');

CREATE INDEX IF NOT EXISTS ix_expense_batches_visit_no ON expense_batches (visit_no);
CREATE INDEX IF NOT EXISTS ix_expense_batches_insured_id ON expense_batches (insured_id);
CREATE INDEX IF NOT EXISTS ix_expense_batches_status ON expense_batches (status);

CREATE TABLE IF NOT EXISTS expense_items (
  id SERIAL PRIMARY KEY,
  batch_no VARCHAR(64) NOT NULL REFERENCES expense_batches(batch_no) ON DELETE CASCADE,
  line_no INTEGER NOT NULL,
  item_code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  category VARCHAR(32) NOT NULL,
  catalog_class VARCHAR(16) NOT NULL,
  unit_price NUMERIC(12, 2) NOT NULL,
  quantity NUMERIC(10, 2) NOT NULL,
  amount NUMERIC(12, 2) NOT NULL,
  self_pay_ratio NUMERIC(5, 4) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_items_batch_line
  ON expense_items (batch_no, line_no);
CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_items_batch_code
  ON expense_items (batch_no, item_code);
CREATE INDEX IF NOT EXISTS ix_expense_items_item_code ON expense_items (item_code);

CREATE TABLE IF NOT EXISTS pre_settlement_vouchers (
  id SERIAL PRIMARY KEY,
  voucher_no VARCHAR(64) UNIQUE NOT NULL,
  batch_no VARCHAR(64) NOT NULL REFERENCES expense_batches(batch_no),
  insured_region VARCHAR(64) NOT NULL,
  total_amount NUMERIC(12, 2) NOT NULL,
  reimbursed_amount NUMERIC(12, 2) NOT NULL,
  account_pay_amount NUMERIC(12, 2) NOT NULL,
  self_pay_amount NUMERIC(12, 2) NOT NULL,
  deductible NUMERIC(12, 2) NOT NULL,
  reimbursement_ratio NUMERIC(5, 4) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'CALCULATED',
  calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  used_at TIMESTAMP,
  reversed_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_pre_settlement_vouchers_active_batch
  ON pre_settlement_vouchers (batch_no)
  WHERE status = 'CALCULATED';
CREATE INDEX IF NOT EXISTS ix_pre_settlement_vouchers_batch_no
  ON pre_settlement_vouchers (batch_no);
CREATE INDEX IF NOT EXISTS ix_pre_settlement_vouchers_status
  ON pre_settlement_vouchers (status);

CREATE TABLE IF NOT EXISTS settlement_records (
  id SERIAL PRIMARY KEY,
  settlement_no VARCHAR(64) UNIQUE NOT NULL,
  voucher_no VARCHAR(64) NOT NULL REFERENCES pre_settlement_vouchers(voucher_no),
  source_batch_no VARCHAR(64) NOT NULL,
  insured_id VARCHAR(32) NOT NULL,
  visit_no VARCHAR(64) NOT NULL,
  total_amount NUMERIC(12, 2) NOT NULL,
  reimbursed_amount NUMERIC(12, 2) NOT NULL,
  account_pay_amount NUMERIC(12, 2) NOT NULL,
  self_pay_amount NUMERIC(12, 2) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'SUCCESS',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reversed_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_settlement_records_successful_voucher
  ON settlement_records (voucher_no)
  WHERE status IN ('SUCCESS', 'REVERSED');
CREATE UNIQUE INDEX IF NOT EXISTS ix_settlement_records_active_visit
  ON settlement_records (visit_no)
  WHERE status = 'SUCCESS';
CREATE INDEX IF NOT EXISTS ix_settlement_records_batch_no
  ON settlement_records (source_batch_no);
CREATE INDEX IF NOT EXISTS ix_settlement_records_insured_id
  ON settlement_records (insured_id);
CREATE INDEX IF NOT EXISTS ix_settlement_records_visit_no
  ON settlement_records (visit_no);
CREATE INDEX IF NOT EXISTS ix_settlement_records_status
  ON settlement_records (status);
CREATE INDEX IF NOT EXISTS ix_settlement_records_created_at
  ON settlement_records (created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
  id SERIAL PRIMARY KEY,
  client_id VARCHAR(64) NOT NULL,
  path VARCHAR(255) NOT NULL,
  action VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
