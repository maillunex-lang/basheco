-- Generated plots remain separate from real OSM geometry and cadastral parcels.
ALTER TABLE world_plots ADD COLUMN generated_by_growth boolean NOT NULL DEFAULT false;
CREATE INDEX world_plots_sector_generated_idx ON world_plots(sector_id,generated_by_growth);
