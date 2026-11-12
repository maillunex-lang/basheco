-- Fixed-price player marketplace; all prices are integer game kopecks.
CREATE TABLE market_listings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 seller_company_id uuid NOT NULL REFERENCES companies(id),
 resource_code text NOT NULL REFERENCES resource_types(code),
 quantity_remaining bigint NOT NULL CHECK(quantity_remaining>=0),
 unit_price_kopecks bigint NOT NULL CHECK(unit_price_kopecks BETWEEN 1 AND 1000000000000),
 status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','sold','cancelled')),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((status='sold' AND quantity_remaining=0) OR (status!='sold' AND quantity_remaining>=0))
);
CREATE INDEX market_active_resource_idx ON market_listings(resource_code,created_at) WHERE status='active';
CREATE TABLE market_purchases (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 listing_id uuid NOT NULL REFERENCES market_listings(id),
 buyer_company_id uuid NOT NULL REFERENCES companies(id),
 buyer_account_id uuid NOT NULL REFERENCES accounts(id),
 quantity bigint NOT NULL CHECK(quantity>0),
 total_kopecks bigint NOT NULL CHECK(total_kopecks>0),
 transfer_id uuid NOT NULL UNIQUE REFERENCES ledger_transfers(id),
 idempotency_key text NOT NULL CHECK(char_length(idempotency_key) BETWEEN 8 AND 128),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(buyer_account_id,idempotency_key)
);
