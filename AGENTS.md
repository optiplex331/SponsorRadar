# NL Sponsor Radar

Junior technical job postings in the Netherlands from employers on the IND register of recognised sponsors.

## Layout

- `backend/src/sponsor_radar/`: CLI, collectors, ingest, register, matching, title signals, report.
- `backend/src/sponsor_radar/migrations/`: forward-only numbered SQL. Never edit an applied migration; add a new file.
- `backend/src/sponsor_radar/seeds.toml`: seed job boards. Set `kvk` only after checking the register by hand.
- `backend/tests/fixtures/`: trimmed real payloads. Refresh them from raw captures, never hand-write them.

## Commands

```bash
docker compose up -d --wait                  # PostgreSQL on 127.0.0.1:5433
cd backend
uv run sponsor-radar run                     # migrate, seed, register, collect, match, report
uv run sponsor-radar collect --only greenhouse:adyen
uv run sponsor-radar replay                  # re-parse latest raw captures, no network
SPONSOR_RADAR_TEST_DATABASE_URL=postgresql://radar:radar@127.0.0.1:5433/radar_test uv run pytest -q
```

## Rules

- Collect only from public ATS job-board APIs (Greenhouse, Ashby, Recruitee) and the IND public register. No LinkedIn, Indeed, or aggregators.
- Store the raw capture before parsing. Parsing must be replayable from raw captures without refetching.
- One failing source must never stop the others.
- Keep `ingest.MIN_INTERVAL` pacing. Recruitee returns 429 for all subdomains together when requests are not paced.
- KvK numbers are text: they have leading zeros.
- PostgreSQL is the only stateful dependency. No ORM, Redis, Kafka, or search engine without a measured need.
- Store no personal data in v1.
- Tests cover parsing against real fixtures and database behavior (idempotency, closing, replay). Matching and title-rule quality are measured against labeled sets, not unit-tested.
