-- Candidate plans are immutable and NEVER published by importing them.
-- Existing generated_locations and player-owned world tables are unchanged.
CREATE TABLE city_plan_snapshots (
 settlement_id text PRIMARY KEY,
 generator_version integer NOT NULL CHECK (generator_version = 2),
 focus_cell_x bigint NOT NULL,
 focus_cell_y bigint NOT NULL,
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
 published boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX city_plan_snapshots_published_idx ON city_plan_snapshots(settlement_id) WHERE published;