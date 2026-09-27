"""Read-only API and the built frontend.

One short-lived connection per request: traffic is a few requests per page view, and nothing
stale survives a postgres restart, so a pool would add lifecycle code without a measured need.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, register

log = logging.getLogger(__name__)
# Same relative layout in the repo and the image: <root>/backend/src/sponsor_radar, <root>/frontend/dist.
DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"
# Runs that started within this span of the newest run count as one collect.
COLLECT_WINDOW = "6 hours"

POSTINGS_SQL = """
SELECT coalesce(json_agg(t ORDER BY coalesce(t.published_at, t.first_seen_at) DESC, t.id DESC), '[]')::text AS body
FROM (
    SELECT p.id, p.title, p.url, p.location, p.department, p.published_at, p.first_seen_at,
           p.seniority, p.dutch_required, p.min_years, p.sponsorship_stance,
           p.salary_min, p.salary_max, p.salary_currency, p.salary_period, s.employer_name AS employer,
           coalesce(m.status, 'unmatched') AS match_status,
           coalesce(m.organisations, '{}') AS register_organisations,
           m.delisted_on
    FROM job_postings p
    JOIN sources s ON s.id = p.source_id
    LEFT JOIN sponsor_matches m ON m.source_id = p.source_id
    WHERE p.closed_at IS NULL AND p.in_netherlands AND p.is_tech
) t
"""

STATUS_SQL = f"""
WITH window_runs AS (
    SELECT DISTINCT ON (source_id) source_id, ok FROM fetch_runs
    WHERE started_at >= (SELECT max(started_at) FROM fetch_runs) - interval '{COLLECT_WINDOW}'
    ORDER BY source_id, started_at DESC, id DESC
)
SELECT
    (SELECT max(finished_at) FROM fetch_runs WHERE ok) AS last_collect_at,
    (SELECT count(*) FROM window_runs WHERE ok) AS sources_ok,
    (SELECT count(*) FROM window_runs) AS sources_total,
    (SELECT register_updated_on FROM register_snapshots ORDER BY captured_at DESC LIMIT 1) AS register_updated_on,
    (SELECT count(*) FROM job_postings WHERE closed_at IS NULL AND in_netherlands AND is_tech) AS postings
"""


def get_conn() -> Iterator[psycopg.Connection]:
    with db.connect() as conn:
        yield conn


def create_app(dist: Path = DIST_DIR) -> FastAPI:
    app = FastAPI(title="NL Sponsor Radar", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/healthz")
    def healthz() -> dict:
        # Liveness only: a database outage should not restart the web pod.
        return {"ok": True}

    @app.get("/api/postings")
    def postings(conn: psycopg.Connection = Depends(get_conn)) -> Response:
        # Postgres builds the JSON; this is a few thousand rows and needs no Python round trip.
        body = conn.execute(POSTINGS_SQL).fetchone()["body"]
        return Response(body, media_type="application/json", headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/status")
    def status(conn: psycopg.Connection = Depends(get_conn)) -> dict:
        return conn.execute(STATUS_SQL).fetchone()

    @app.get("/api/register-changes")
    def register_changes(response: Response, conn: psycopg.Connection = Depends(get_conn)) -> dict:
        response.headers["Cache-Control"] = "public, max-age=300"
        return register.register_changes(conn)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        try:
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO page_views (day, views) VALUES ((now() AT TIME ZONE 'UTC')::date, 1)
                    ON CONFLICT (day) DO UPDATE SET views = page_views.views + 1
                    """
                )
        except psycopg.Error as exc:  # counting must never block the page
            log.warning("page view not counted: %s", exc)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/", StaticFiles(directory=dist, check_dir=False), name="static")
    return app


app = create_app()
