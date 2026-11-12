ALTER TABLE world_plots ADD COLUMN created_by_account_id uuid REFERENCES accounts(id);
CREATE INDEX world_plots_creator_idx ON world_plots(created_by_account_id,sector_id);
