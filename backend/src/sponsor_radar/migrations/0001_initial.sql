-- One public job board of one employer.
CREATE TABLE sources (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('greenhouse', 'ashby', 'recruitee')),
    board text NOT NULL,
    employer_name text NOT NULL,
    -- Manually verified KvK number; overrides name matching when present.
    kvk_number text,
    enabled boolean NOT NULL DEFAULT true,
    UNIQUE (kind, board)
);

-- Unmodified board payloads. Identical payloads are stored once per source.
CREATE TABLE raw_captures (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES sources (id),
    content_sha256 text NOT NULL,
    payload jsonb NOT NULL,
    first_fetched_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, content_sha256)
);

-- Every fetch attempt, successful or not. Feeds collection success rate.
CREATE TABLE fetch_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES sources (id),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    ok boolean,
    error text,
    raw_capture_id bigint REFERENCES raw_captures (id),
    posting_count integer
);

CREATE TABLE job_postings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id bigint NOT NULL REFERENCES sources (id),
    external_id text NOT NULL,
    title text NOT NULL,
    url text NOT NULL,
    location text NOT NULL,
    in_netherlands boolean NOT NULL,
    department text,
    description text NOT NULL,
    published_at timestamptz,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    raw_capture_id bigint NOT NULL REFERENCES raw_captures (id),
    UNIQUE (source_id, external_id)
);

-- One capture of the IND register, stored only when its content changes.
CREATE TABLE register_snapshots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_sha256 text NOT NULL UNIQUE,
    register_updated_on date,
    raw_html text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE register_entries (
    snapshot_id bigint NOT NULL REFERENCES register_snapshots (id),
    kvk_number text NOT NULL,
    organisation text NOT NULL,
    PRIMARY KEY (snapshot_id, kvk_number, organisation)
);

-- Latest decision linking a source's employer to the register.
CREATE TABLE sponsor_matches (
    source_id bigint PRIMARY KEY REFERENCES sources (id),
    snapshot_id bigint NOT NULL REFERENCES register_snapshots (id),
    status text NOT NULL CHECK (status IN ('kvk_confirmed', 'name_inferred', 'unmatched')),
    kvk_numbers text[] NOT NULL DEFAULT '{}',
    organisations text[] NOT NULL DEFAULT '{}',
    decided_at timestamptz NOT NULL DEFAULT now()
);
