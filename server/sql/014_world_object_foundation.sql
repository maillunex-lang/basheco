-- Additive schema for the next construction engine. NOT activated by existing API.
-- Keep legacy world_buildings and plot ownership intact until an audited backfill.
CREATE TABLE world_object_catalog (
 code text PRIMARY KEY,
 title text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('building','road','decoration','parking','utility')),
 zone text,
 footprint jsonb NOT NULL CHECK (jsonb_typeof(footprint)='array'),
 cost_kopecks bigint NOT NULL CHECK (cost_kopecks >= 0),
 requires_road boolean NOT NULL DEFAULT false,
 version integer NOT NULL DEFAULT 1 CHECK (version > 0),
 active boolean NOT NULL DEFAULT true
);
CREATE TABLE world_objects (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 plot_id uuid NOT NULL REFERENCES world_plots(id),
 company_id uuid NOT NULL REFERENCES companies(id),
 catalog_code text NOT NULL REFERENCES world_object_catalog(code),
 catalog_version integer NOT NULL,
 cell_x bigint NOT NULL,
 cell_y bigint NOT NULL,
 rotation smallint NOT NULL CHECK (rotation IN (0,90,180,270)),
 cost_kopecks bigint NOT NULL CHECK (cost_kopecks >= 0),
 idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 128),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(company_id,idempotency_key)
);
CREATE INDEX world_objects_plot_idx ON world_objects(plot_id);
-- Global coordinates, no separate cell origin per city.
-- Unique occupancy is authoritative even under simultaneous transactions.
CREATE TABLE world_object_cells (
 object_id uuid NOT NULL REFERENCES world_objects(id) ON DELETE CASCADE,
 layer text NOT NULL DEFAULT 'surface' CHECK (layer IN ('surface','underground','overhead')),
 cell_x bigint NOT NULL,
 cell_y bigint NOT NULL,
 PRIMARY KEY(object_id,layer,cell_x,cell_y),
 UNIQUE(layer,cell_x,cell_y)
);
CREATE INDEX world_object_cells_xy_idx ON world_object_cells(cell_x,cell_y);
CREATE TABLE world_construction_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 object_id uuid NOT NULL REFERENCES world_objects(id),
 account_id uuid NOT NULL REFERENCES accounts(id),
 event_type text NOT NULL CHECK(event_type IN ('created','demolished','upgraded')),
 created_at timestamptz NOT NULL DEFAULT now()
);
-- No sample plots, buildings, prices or artificial neighborhoods inserted.
-- New placement API must be enabled only after geographic occupancy masks,
-- property rights, atomic debit and old-building backfill are implemented.
