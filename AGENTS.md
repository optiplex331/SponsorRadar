# NL Sponsor Radar

Junior technical job postings in the Netherlands from employers on the IND register of recognised sponsors.

## Layout

- `backend/src/sponsor_radar/`: CLI, collectors, ingest, register, matching, signals, report, `lookup.py` (sponsor search over an in-process index of the latest register snapshot), `web.py` (FastAPI).
- `backend/src/sponsor_radar/migrations/`: forward-only numbered SQL. Never edit an applied migration; add a new file.
- `backend/src/sponsor_radar/seeds.toml`: seed job boards. Set `kvk` only after checking it against evidence recorded in the workbench labels (the employer's own site, a regulator, or a lead-checked KvK search or address match).
- `backend/tests/fixtures/`: trimmed real payloads. Refresh them from raw captures, never hand-write them.
- `frontend/`: Vite + React + TypeScript page, Tailwind v4, Phosphor icons, self-hosted Geist; no component, animation, or state library. Animation is CSS only; no library may inject `<style>` elements (CSP). Filtering runs in the browser; filter state lives in URL query params.
- `Dockerfile`: one image for web (default CMD, port 8000) and collector (`sponsor-radar run`). The web app serves `<root>/frontend/dist`.

## Commands

```bash
docker compose up -d --wait                  # PostgreSQL on 127.0.0.1:5433
cd backend
uv run sponsor-radar run                     # migrate, seed, register, collect, match, report, prune
uv run sponsor-radar collect --only greenhouse:adyen
uv run sponsor-radar replay                  # re-parse latest raw captures and recompute signals, no network
uv run sponsor-radar prune                   # drop raw captures unused for 14 days
uv run sponsor-radar backfill-register       # one-off by hand: past register versions from archive.org, never in `run`
uv run sponsor-radar discover --out ../../SponsorRadar-workbench/notes/discover.csv [--since YYYY-MM-DD]
                                             # probe boards for KvKs added in the last register change (or since a date)
uv run sponsor-radar evaluate --labels ../../SponsorRadar-workbench/notes/labels   # score rules; no database
uv run uvicorn sponsor_radar.web:app --reload --port 8000
SPONSOR_RADAR_TEST_DATABASE_URL=postgresql://radar:radar@127.0.0.1:5433/radar_test uv run pytest -q
cd ../frontend && npm ci && npm run dev      # http://localhost:5173, proxies /api to :8000
npm run build                                # tsc --noEmit, then vite build into frontend/dist
docker compose up -d --build --wait          # postgres + web image on http://127.0.0.1:8000
scripts/probe.sh https://sponsorradar.halligalli.games   # SLO checks; hourly in .github/workflows/probe.yml
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
- The web app is read-only apart from the daily `page_views` counter. No cookies, IPs, or client-side tracking. The page may keep two values in `localStorage`: a `lastVisit` timestamp to mark new postings and a `theme` override; neither leaves the browser.
- `web.py` sends the security headers (strict CSP: no inline `<script>`, `<style>` elements, or `style` attributes in HTML, including `public/404.html`; React `style` props and other CSSOM writes are fine) and caches the postings, status, and register-changes bodies in process for 5 minutes. The page's colours are tokens in `styles.css` checked for WCAG AA in both themes; recheck contrast after any token change.
- Frontend design rules: green, amber, and grey only encode how sure the sponsor link is (KvK confirmed, likely match, not on register); the clay accent is only for actions and the "New" marker, never a status, and never text on dark surfaces. Text stays at 4.5:1 or more and control borders at 3:1. The serif is only for the wordmark and section headings. Text inputs are at least 16px. Motion is CSS only and stops under `prefers-reduced-motion`; keyboard actions may fade (opacity, 150ms or less) but never move.
- `sponsorship_stance` hides `refuses_visa` postings by default, so its rules need the same precision as the Dutch rules. `refuses_visa` also covers postings that ask for existing work rights ("must be authorized to work in the country").
- `is_tech_role` excludes hardware, lab, and physical engineering titles; embedded, firmware, and FPGA stay tech.
- `frontend/dev/` holds dev-only mock data (`MOCK_REGISTER_CHANGES=1 npm run dev`); it never ships in `dist`.
- Tests cover parsing against real fixtures, database behavior (idempotency, closing, replay, prune), the API, and table-driven Dutch/years phrases. Matching and title-rule quality are measured against labeled sets, not unit-tested.
