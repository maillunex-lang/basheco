-- BASHECO PostgreSQL migration, one transactional application only.
-- In-game currency is integer kopecks, never floating-point.
CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 80),
  password_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX accounts_email_lower_uniq ON accounts (lower(email));
CREATE TABLE sessions (
  token_hash text PRIMARY KEY CHECK (char_length(token_hash) = 64),
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_account_idx ON sessions(account_id);
CREATE TABLE companies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_account_id uuid NOT NULL REFERENCES accounts(id),
  name text NOT NULL CHECK (char_length(name) BETWEEN 2 AND 160),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX companies_owner_idx ON companies(owner_account_id);
CREATE TABLE wallets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid REFERENCES accounts(id),
  company_id uuid REFERENCES companies(id),
  balance_kopecks bigint NOT NULL DEFAULT 0 CHECK (balance_kopecks >= 0),
  CHECK ((account_id IS NULL) <> (company_id IS NULL))
);
CREATE UNIQUE INDEX one_personal_wallet ON wallets(account_id) WHERE account_id IS NOT NULL;
CREATE UNIQUE INDEX one_company_wallet ON wallets(company_id) WHERE company_id IS NOT NULL;
CREATE TABLE ledger_transfers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  initiated_by uuid NOT NULL REFERENCES accounts(id),
  idempotency_key text NOT NULL CHECK (char_length(idempotency_key) BETWEEN 8 AND 128),
  debit_wallet_id uuid NOT NULL REFERENCES wallets(id),
  credit_wallet_id uuid NOT NULL REFERENCES wallets(id),
  amount_kopecks bigint NOT NULL CHECK (amount_kopecks > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (initiated_by, idempotency_key),
  CHECK (debit_wallet_id <> credit_wallet_id)
);
CREATE TABLE ledger_postings (
  transfer_id uuid NOT NULL REFERENCES ledger_transfers(id),
  wallet_id uuid NOT NULL REFERENCES wallets(id),
  delta_kopecks bigint NOT NULL CHECK (delta_kopecks <> 0),
  PRIMARY KEY (transfer_id, wallet_id)
);
-- Only the trusted server may write wallets and postings. Issuance is not yet implemented.
