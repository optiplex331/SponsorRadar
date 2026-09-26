-- Signals computed by signals.py at ingest; replay recomputes them after a rule change.
ALTER TABLE job_postings
    ADD COLUMN seniority text,
    ADD COLUMN is_tech boolean,
    ADD COLUMN dutch_required boolean,
    ADD COLUMN min_years integer;

-- Daily count of index.html requests. No cookies, IPs, or other visitor data.
CREATE TABLE page_views (
    day date PRIMARY KEY,
    views bigint NOT NULL
);

-- Pruning deletes old raw captures; the fetch run keeps its outcome without the payload.
ALTER TABLE fetch_runs DROP CONSTRAINT fetch_runs_raw_capture_id_fkey,
    ADD CONSTRAINT fetch_runs_raw_capture_id_fkey FOREIGN KEY (raw_capture_id) REFERENCES raw_captures (id) ON DELETE SET NULL;
CREATE INDEX fetch_runs_raw_capture_id_idx ON fetch_runs (raw_capture_id);
CREATE INDEX job_postings_raw_capture_id_idx ON job_postings (raw_capture_id);
