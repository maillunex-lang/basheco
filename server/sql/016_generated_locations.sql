-- Additive, unpublished-by-default generated scenery snapshots.
CREATE TABLE generated_locations (
 settlement_id text PRIMARY KEY,
 municipality_id text NOT NULL,
 generator_version integer NOT NULL CHECK (generator_version > 0),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 published boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX generated_locations_published_idx ON generated_locations(municipality_id) WHERE published;
CREATE TABLE generated_location_chunks (
 settlement_id text NOT NULL REFERENCES generated_locations(settlement_id),
 chunk_x bigint NOT NULL,
 chunk_y bigint NOT NULL,
 content jsonb NOT NULL CHECK (jsonb_typeof(content)='array'),
 PRIMARY KEY(settlement_id,chunk_x,chunk_y)
);
CREATE INDEX generated_location_chunks_xy_idx ON generated_location_chunks(chunk_x,chunk_y);