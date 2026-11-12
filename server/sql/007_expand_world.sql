-- Expand existing prototype dimensions without changing plot/building IDs.
UPDATE world_sectors SET width_tiles=200, height_tiles=200
WHERE id='ufa-prototype-01' AND width_tiles<200 AND height_tiles<200;
