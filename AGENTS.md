# NL Sponsor Radar

Junior technical job postings in the Netherlands from employers on the IND register of recognised sponsors.

## Layout

- `backend/src/sponsor_radar/`: CLI, collectors, ingest, register, matching, signals, report, `web.py` (FastAPI).
- `backend/src/sponsor_radar/migrations/`: forward-only numbered SQL. Never edit an applied migration; add a new file.
- `backend/src/sponsor_radar/seeds.toml`: seed job boards. Set `kvk` only after checking the register by hand.
- `backend/tests/fixtures/`: trimmed real payloads. Refresh them from raw captures, never hand-write them.
- `frontend/`: Vite + React + TypeScript page, plain CSS, no component or state library. Filtering runs in the browser; filter state lives in URL query params.
- `Dockerfile`: one image for web (default CMD, port 8000) and collector (`sponsor-radar run`). The web app serves `<root>/frontend/dist`.

## Commands

```bash
docker compose up -d --wait                  # PostgreSQL on 127.0.0.1:5433
cd backend
uv run sponsor-radar run                     # migrate, seed, register, collect, match, report, prune
uv run sponsor-radar collect --only greenhouse:adyen
uv run sponsor-radar replay                  # re-parse latest raw captures and recompute signals, no network
uv run sponsor-radar prune                   # drop raw captures unused for 14 days
uv run sponsor-radar evaluate --labels ../../SponsorRadar-workbench/notes/labels   # score rules; no database
uv run uvicorn sponsor_radar.web:app --reload --port 8000
SPONSOR_RADAR_TEST_DATABASE_URL=postgresql://radar:radar@127.0.0.1:5433/radar_test uv run pytest -q
cd ../frontend && npm ci && npm run dev      # http://localhost:5173, proxies /api to :8000
npm run build                                # tsc --noEmit, then vite build into frontend/dist
docker compose up -d --build --wait          # postgres + web image on http://127.0.0.1:8000
```

## Rules

- Collect only from public ATS job-board APIs (Greenhouse, Ashby, Recruitee) and the IND public register. No LinkedIn, Indeed, or aggregators.
- Store the raw capture before parsing. Parsing must be replayable from raw captures without refetching.
- One failing source must never stop the others.
- Keep `ingest.MIN_INTERVAL` pacing. Recruitee returns 429 for all subdomains together when requests are not paced.
- KvK numbers are text: they have leading zeros.
- PostgreSQL is the only stateful dependency. No ORM, Redis, Kafka, or search engine without a measured need.
- Store no personal data in v1.
- `signals.py` rules match explicit phrases only: a wrong `dutch_required` or `min_years` hides a posting. After a rule change, run `replay`.
- The web app is read-only apart from the daily `page_views` counter. No cookies, IPs, or client-side tracking.
- Tests cover parsing against real fixtures, database behavior (idempotency, closing, replay, prune), the API, and table-driven Dutch/years phrases. Matching and title-rule quality are measured against labeled sets, not unit-tested.
