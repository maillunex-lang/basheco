-- Alpha-only one-time starter grant, auditable separately from transfers.
-- Each account can receive it once, regardless of how many companies it creates.
CREATE TABLE alpha_starter_grants (
 account_id uuid PRIMARY KEY REFERENCES accounts(id),
 company_id uuid NOT NULL REFERENCES companies(id),
 wallet_id uuid NOT NULL REFERENCES wallets(id),
 amount_kopecks bigint NOT NULL CHECK(amount_kopecks > 0),
 created_at timestamptz NOT NULL DEFAULT now()
);
