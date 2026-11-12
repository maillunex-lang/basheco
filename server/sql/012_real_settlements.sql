-- The six fictional parcels are removed only when nobody owns or built on them.
-- Abort atomically instead of deleting player property.
DO $$
BEGIN
 IF EXISTS (
   SELECT 1 FROM world_plots p
   LEFT JOIN world_buildings b ON b.plot_id=p.id
   WHERE p.sector_id='ufa-prototype-01'
   AND (p.owner_company_id IS NOT NULL OR b.id IS NOT NULL)
 ) THEN
   RAISE EXCEPTION 'Prototype contains player property: manual migration required';
 END IF;
END $$;

DELETE FROM world_plots WHERE sector_id='ufa-prototype-01';
DELETE FROM world_sectors WHERE id='ufa-prototype-01';

INSERT INTO world_sectors(id,name,city,width_tiles,height_tiles,geometry_source)
VALUES
 ('ufa','Уфа','Уфа',4096,4096,'osm-background'),
 ('mikhailovka','Михайловка','Михайловка',4096,4096,'osm-background')
ON CONFLICT (id) DO NOTHING;

-- No invented cadastral parcels are seeded. Parcels must be requested and
-- validated by the server, separately from real OSM geometry.
