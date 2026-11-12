-- Draft PostgreSQL migration. NOT applied.
-- All money values are integer kopecks. Timestamp display uses Ufa local time.
BEGIN;
CREATE TABLE accounts (
 id uuid PRIMARY KEY,
 display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 2 AND 80),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE companies (
 id uuid PRIMARY KEY,
 owner_account_id uuid NOT NULL REFERENCES accounts(id),
 name text NOT NULL CHECK (char_length(name) BETWEEN 2 AND 160),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE wallets (
 id uuid PRIMARY KEY,
 account_id uuid REFERENCES accounts(id),
 company_id uuid REFERENCES companies(id),
 balance_kopecks bigint NOT NULL DEFAULT 0 CHECK (balance_kopecks >= 0),
 CHECK ((account_id IS NULL) <> (company_id IS NULL))
);
CREATE UNIQUE INDEX one_personal_wallet ON wallets(account_id) WHERE account_id IS NOT NULL;
CREATE UNIQUE INDEX one_company_wallet ON wallets(company_id) WHERE company_id IS NOT NULL;
CREATE TABLE ledger_transfers (
 id uuid PRIMARY KEY,
 idempotency_key text NOT NULL UNIQUE CHECK (char_length(idempotency_key) BETWEEN 1 AND 128),
 debit_wallet_id uuid NOT NULL REFERENCES wallets(id),
 credit_wallet_id uuid NOT NULL REFERENCES wallets(id),
 amount_kopecks bigint NOT NULL CHECK (amount_kopecks > 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (debit_wallet_id <> credit_wallet_id)
);
-- No direct balance writes from client. Future migration must add immutable
-- posting journal and audited mint/burn accounts before production use.
COMMIT;
