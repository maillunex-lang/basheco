-- First fictional test sector in Ufa. Coordinates are local tile units, NOT geodata.
CREATE TABLE world_sectors (
 id text PRIMARY KEY,
 name text NOT NULL,
 city text NOT NULL,
 width_tiles integer NOT NULL CHECK(width_tiles BETWEEN 1 AND 4096),
 height_tiles integer NOT NULL CHECK(height_tiles BETWEEN 1 AND 4096),
 geometry_source text NOT NULL DEFAULT 'prototype',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE world_plots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 sector_id text NOT NULL REFERENCES world_sectors(id),
 tile_x integer NOT NULL CHECK(tile_x >= 0),
 tile_y integer NOT NULL CHECK(tile_y >= 0),
 width_tiles integer NOT NULL CHECK(width_tiles > 0),
 height_tiles integer NOT NULL CHECK(height_tiles > 0),
 zone text NOT NULL CHECK(zone IN ('commercial','industrial','agricultural')),
 owner_company_id uuid REFERENCES companies(id),
 UNIQUE(sector_id,tile_x,tile_y)
);
CREATE TABLE building_types (
 code text PRIMARY KEY,
 title text NOT NULL,
 zone text NOT NULL CHECK(zone IN ('commercial','industrial','agricultural'))
);
CREATE TABLE world_buildings (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 plot_id uuid NOT NULL UNIQUE REFERENCES world_plots(id),
 company_id uuid NOT NULL REFERENCES companies(id),
 building_type text NOT NULL REFERENCES building_types(code),
 built_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO world_sectors(id,name,city,width_tiles,height_tiles)
VALUES ('ufa-prototype-01','Уфа: тестовый квартал','Уфа',32,32);
INSERT INTO building_types(code,title,zone) VALUES
('shop','Магазин','commercial'),
('workshop','Мастерская','industrial'),
('greenhouse','Теплица','agricultural');
INSERT INTO world_plots(sector_id,tile_x,tile_y,width_tiles,height_tiles,zone)
VALUES
('ufa-prototype-01',2,2,5,5,'commercial'),
('ufa-prototype-01',9,2,5,5,'commercial'),
('ufa-prototype-01',2,10,6,6,'industrial'),
('ufa-prototype-01',11,10,6,6,'industrial'),
('ufa-prototype-01',2,20,6,6,'agricultural'),
('ufa-prototype-01',11,20,6,6,'agricultural');
