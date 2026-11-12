-- Prototype-only production: inventory is integer units and fully server-owned.
CREATE TABLE resource_types (
 code text PRIMARY KEY,
 title text NOT NULL
);
INSERT INTO resource_types(code,title) VALUES
('vegetables','Овощи'),('packed_food','Упакованные продукты'),('spare_parts','Запчасти');
CREATE TABLE production_recipes (
 code text PRIMARY KEY,
 building_type text NOT NULL REFERENCES building_types(code),
 input_resource text REFERENCES resource_types(code),
 input_quantity bigint NOT NULL DEFAULT 0 CHECK(input_quantity >= 0),
 output_resource text NOT NULL REFERENCES resource_types(code),
 output_quantity bigint NOT NULL CHECK(output_quantity > 0),
 cooldown_seconds integer NOT NULL CHECK(cooldown_seconds BETWEEN 30 AND 86400),
 CHECK ((input_resource IS NULL AND input_quantity=0) OR
        (input_resource IS NOT NULL AND input_quantity>0))
);
INSERT INTO production_recipes VALUES
('grow_vegetables','greenhouse',NULL,0,'vegetables',10,300),
('pack_food','workshop','vegetables',5,'packed_food',3,120),
('make_parts','workshop',NULL,0,'spare_parts',1,600);
CREATE TABLE company_inventory (
 company_id uuid NOT NULL REFERENCES companies(id),
 resource_code text NOT NULL REFERENCES resource_types(code),
 quantity bigint NOT NULL DEFAULT 0 CHECK(quantity >= 0),
 PRIMARY KEY(company_id,resource_code)
);
CREATE TABLE production_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 building_id uuid NOT NULL REFERENCES world_buildings(id),
 company_id uuid NOT NULL REFERENCES companies(id),
 recipe_code text NOT NULL REFERENCES production_recipes(code),
 idempotency_key text NOT NULL CHECK(char_length(idempotency_key) BETWEEN 8 AND 128),
 produced_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(company_id,idempotency_key)
);
CREATE INDEX production_runs_building_time ON production_runs(building_id,produced_at DESC);
