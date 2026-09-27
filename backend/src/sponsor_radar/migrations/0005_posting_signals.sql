-- Sponsorship stance read from the posting text, and structured salary from the ATS payload.
-- Filled at ingest; replay recomputes both from raw captures.
ALTER TABLE job_postings
    ADD COLUMN sponsorship_stance text CHECK (sponsorship_stance IN ('offers', 'refuses_visa', 'refuses_relocation', 'silent')),
    ADD COLUMN salary_min numeric,
    ADD COLUMN salary_max numeric,
    ADD COLUMN salary_currency text,
    ADD COLUMN salary_period text CHECK (salary_period IN ('year', 'month', 'hour'));
