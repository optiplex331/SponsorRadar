-- A closed posting no longer pins the last capture it appeared in; pruning may drop that capture.
ALTER TABLE job_postings ALTER COLUMN raw_capture_id DROP NOT NULL,
    DROP CONSTRAINT job_postings_raw_capture_id_fkey,
    ADD CONSTRAINT job_postings_raw_capture_id_fkey FOREIGN KEY (raw_capture_id) REFERENCES raw_captures (id) ON DELETE SET NULL;
