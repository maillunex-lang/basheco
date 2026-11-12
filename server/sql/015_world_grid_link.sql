-- Stage 1 (unified map): ADDITIVE link between legacy settlement-local plots and
-- the single world grid (EPSG:32640, 6 m cells, origin E=0,N=0, basheco-grid/1).
-- Nothing is deleted or rewritten: sector_id, tile_x, tile_y, ids, owners and
-- buildings stay exactly as they are. Legacy local indices are NOT world cells.

-- How the pre-stage-1 client georeferenced each sector: local equirectangular
-- metres around (origin_lon, origin_lat), drawn at origin_tile + metres / metres_per_tile.
-- Values are the constants of client/scripts/geo_background.gd and the v1 manifests
-- at commit 69b1991. A sector without an anchor cannot be placed and stays unmapped.
CREATE TABLE world_legacy_sector_anchors (
 sector_id text PRIMARY KEY REFERENCES world_sectors(id),
 origin_lon double precision NOT NULL CHECK (origin_lon BETWEEN -180 AND 180),
 origin_lat double precision NOT NULL CHECK (origin_lat BETWEEN -85 AND 85),
 origin_tile_x double precision NOT NULL,
 origin_tile_y double precision NOT NULL,
 metres_per_tile double precision NOT NULL CHECK (metres_per_tile > 0),
 projection text NOT NULL CHECK (projection = 'local_equirectangular_metres'),
 provenance text NOT NULL
);
INSERT INTO world_legacy_sector_anchors
 (sector_id,origin_lon,origin_lat,origin_tile_x,origin_tile_y,metres_per_tile,projection,provenance)
SELECT v.sector_id,v.origin_lon,v.origin_lat,v.tile_x,v.tile_y,6,'local_equirectangular_metres',
       'client/scripts/geo_background.gd + client/data/spatial/*/manifest.json @ 69b1991'
FROM (VALUES
 ('ufa', 55.971999999999994::double precision, 54.7386::double precision, 25::double precision, 25::double precision),
 ('mikhailovka', 55.8925, 54.805499999999995, 150, 180)
) AS v(sector_id,origin_lon,origin_lat,tile_x,tile_y)
WHERE EXISTS (SELECT 1 FROM world_sectors s WHERE s.id=v.sector_id)
ON CONFLICT (sector_id) DO NOTHING;

-- World position of the plot's north-west corner, in global cells. NULL = not
-- placed on the world grid yet (fail closed: such a plot is not shown on the map).
-- Filled by `python -m basheco.world_compat` (also run by basheco.migrate).
ALTER TABLE world_plots
 ADD COLUMN world_cell_x bigint,
 ADD COLUMN world_cell_y bigint,
 ADD COLUMN world_cell_source text,
 ADD COLUMN world_cell_offset_m double precision,
 ADD CONSTRAINT world_plots_world_cell_pair
   CHECK ((world_cell_x IS NULL) = (world_cell_y IS NULL)),
 ADD CONSTRAINT world_plots_world_cell_source
   CHECK ((world_cell_x IS NULL) = (world_cell_source IS NULL));

-- One physical 6x6 m cell can belong to at most one plot in the whole world,
-- whatever sector the plot was created in. Authoritative under concurrency.
ALTER TABLE world_plots ADD CONSTRAINT world_plots_world_cells_no_overlap
 EXCLUDE USING gist (
   int8range(world_cell_x, world_cell_x + width_tiles) WITH &&,
   int8range(world_cell_y, world_cell_y + height_tiles) WITH &&
 ) WHERE (world_cell_x IS NOT NULL);
