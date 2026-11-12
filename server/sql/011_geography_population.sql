-- Source-traceable settlement metadata. No invented population or household balances.
CREATE TABLE IF NOT EXISTS geo_locations (
 id text PRIMARY KEY,
 name text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('city','village','settlement','hamlet','other')),
 municipality_id text NOT NULL,
 centroid_lon double precision,
 centroid_lat double precision,
 geography_source text,
 geography_observed_on date,
 playable boolean NOT NULL DEFAULT false,
 CHECK ((centroid_lon IS NULL AND centroid_lat IS NULL) OR
        (centroid_lon BETWEEN -180 AND 180 AND centroid_lat BETWEEN -90 AND 90))
);
CREATE TABLE IF NOT EXISTS geo_statistics (
 location_id text NOT NULL REFERENCES geo_locations(id),
 indicator text NOT NULL CHECK(indicator IN ('population','average_monthly_wage_rub','median_monthly_income_rub','employment','municipal_budget_revenue_rub')),
 reference_year integer NOT NULL CHECK(reference_year BETWEEN 1900 AND 2200),
 value numeric(20,2) NOT NULL CHECK(value >= 0),
 unit text NOT NULL,
 source_name text NOT NULL,
 source_url text NOT NULL,
 published_on date,
 retrieved_on date NOT NULL,
 geography_scope text NOT NULL CHECK(geography_scope IN ('settlement','municipality','region')),
 PRIMARY KEY(location_id,indicator,reference_year,source_url)
);
CREATE TABLE IF NOT EXISTS npc_economy_parameters (
 location_id text PRIMARY KEY REFERENCES geo_locations(id),
 simulation_population integer NOT NULL CHECK(simulation_population >= 0),
 simulation_monthly_income_kopecks bigint NOT NULL CHECK(simulation_monthly_income_kopecks >= 0),
 simulation_consumption_fraction numeric(5,4) NOT NULL CHECK(simulation_consumption_fraction BETWEEN 0 AND 1),
 source_statistics_year integer,
 updated_at timestamptz NOT NULL DEFAULT now()
);
-- Existing playable prototype, without asserting unverified statistics.
INSERT INTO geo_locations(id,name,kind,municipality_id,playable)
VALUES ('ufa','Уфа','city','ufa_city',true)
ON CONFLICT(id) DO NOTHING;
