"""Read-only API and the built frontend.

The postings, status, and register-changes bodies are cached in process for 5 minutes: the data changes once a
day, and one uvicorn process means one cache. Other requests open one short-lived connection each; nothing stale
survives a postgres restart, and with the cache keeping the request rate low a pool would add lifecycle code
without a measured need.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from . import db, lookup, register

log = logging.getLogger(__name__)
# Same relative layout in the repo and the image: <root>/backend/src/sponsor_radar, <root>/frontend/dist.
DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"
# Runs that started within this span of the newest run count as one collect.
COLLECT_WINDOW = "6 hours"
CANONICAL_ORIGIN = "https://sponsorradar.halligalli.games"
API_CACHE_SECONDS = 300
API_CACHE_CONTROL = f"public, max-age={API_CACHE_SECONDS}"
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    # No includeSubDomains or preload: the parent domain is shared with other sites.
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
FALLBACK_404 = '<!doctype html><title>Not found</title><h1>Not found</h1><p><a href="/">NL Sponsor Radar</a></p>'

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


def as_json(value: object) -> bytes:
    return json.dumps(jsonable_encoder(value), ensure_ascii=False, separators=(",", ":")).encode()


class DistFiles(StaticFiles):
    """The built frontend with a cache policy per file class.

    Missing files raise and reach the 404 handler without these headers, so a 404 under /assets/ is never
    marked immutable.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            if path.startswith("assets/"):  # Vite puts a content hash in every name here
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path == "index.html":
                response.headers["Cache-Control"] = "no-cache"
            else:
                response.headers["Cache-Control"] = "public, max-age=3600"
        return response


def create_app(dist: Path = DIST_DIR, clock: Callable[[], float] = time.monotonic) -> FastAPI:
    app = FastAPI(title="NL Sponsor Radar", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def https_and_security_headers(request: Request, call_next: Callable) -> Response:
        # cloudflared forwards the visitor's scheme. No header (local compose, kubelet probes) means no redirect.
        # The target is the fixed canonical host, never the request's Host header.
        if request.headers.get("x-forwarded-proto") == "http":
            path = request.scope.get("raw_path", b"").decode("latin-1") or request.url.path
            query = f"?{request.url.query}" if request.url.query else ""
            response = RedirectResponse(CANONICAL_ORIGIN + path + query, status_code=301)
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    @app.exception_handler(404)
    async def not_found(request: Request, exc: Exception) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        page = dist / "404.html"
        if page.is_file():
            return FileResponse(page, status_code=404)
        return HTMLResponse(FALLBACK_404, status_code=404)

    cache: dict[str, tuple[float, bytes]] = {}
    refresh_locks: dict[str, threading.Lock] = {}

    def cached(key: str, build: Callable[[psycopg.Connection], bytes]) -> Response:
        # Checked before connecting, so a hit never touches postgres. Sync endpoints run in the threadpool: the
        # lock lets one thread rebuild while the others wait for its body. A failure raises and stores nothing.
        def fresh() -> bool:
            return key in cache and clock() - cache[key][0] < API_CACHE_SECONDS

        if not fresh():
            with refresh_locks.setdefault(key, threading.Lock()):
                if not fresh():
                    with db.connect() as conn:
                        body = build(conn)
                    cache[key] = (clock(), body)
        return Response(cache[key][1], media_type="application/json", headers={"Cache-Control": API_CACHE_CONTROL})

    @app.get("/healthz")
    def healthz() -> dict:
        # Liveness only: a database outage should not restart the web pod.
        return {"ok": True}

    @app.get("/api/postings")
    def postings() -> Response:
        # Postgres builds the JSON; this is a few thousand rows and needs no Python round trip.
        return cached("postings", lambda conn: conn.execute(POSTINGS_SQL).fetchone()["body"].encode())

    @app.get("/api/status")
    def status() -> Response:
        return cached("status", lambda conn: as_json(conn.execute(STATUS_SQL).fetchone()))

    @app.get("/api/register-changes")
    def register_changes() -> Response:
        return cached("register-changes", lambda conn: as_json(register.register_changes(conn)))

    @app.get("/api/sponsors")
    def sponsors(response: Response, q: str = "", conn: psycopg.Connection = Depends(get_conn)) -> dict:
        # The query is never stored; it only appears where the server already logs request URLs.
        if not lookup.MIN_QUERY <= len(q.strip()) <= 100:
            raise HTTPException(400, f"q needs {lookup.MIN_QUERY} to 100 characters")
        response.headers["Cache-Control"] = "public, max-age=300"
        return lookup.search(conn, q)

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def index(request: Request) -> FileResponse:
        if request.method == "GET":  # uptime checks send HEAD; they are not page views
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

    # Not html=True: that would answer /api/* misses with 404.html instead of JSON.
    app.mount("/", DistFiles(directory=dist, check_dir=False), name="static")
    return app


app = create_app()
