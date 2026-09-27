-- Date a matched sponsor left the register; its old KvKs stay in kvk_numbers while status is unmatched.
ALTER TABLE sponsor_matches ADD COLUMN delisted_on date;
-- First-seen dates look up a KvK across all snapshots.
CREATE INDEX register_entries_kvk_number_idx ON register_entries (kvk_number);
