"""Fetch sources, keep raw captures, and upsert normalized postings."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
import psycopg
from psycopg.types.json import Jsonb

from . import signals
from .collectors import Posting, module_for

log = logging.getLogger(__name__)
SEEDS_PATH = Path(__file__).with_name("seeds.toml")


@dataclass(frozen=True)
class RunResult:
    source: str
    ok: bool
    postings: int = 0
    error: str | None = None


def load_seeds(conn: psycopg.Connection, path: Path = SEEDS_PATH) -> int:
    seeds = tomllib.loads(path.read_text())["source"]
    for seed in seeds:
        conn.execute(
            """
            INSERT INTO sources (kind, board, employer_name, kvk_number)
            VALUES (%(kind)s, %(board)s, %(employer)s, %(kvk)s)
            ON CONFLICT (kind, board) DO UPDATE
            SET employer_name = EXCLUDED.employer_name, kvk_number = EXCLUDED.kvk_number
            """,
            {"kvk": None, **seed},
        )
    conn.commit()
    return len(seeds)


def store_raw_capture(conn: psycopg.Connection, source_id: int, payload: dict) -> int:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body.encode()).hexdigest()
    row = conn.execute(
        """
        INSERT INTO raw_captures (source_id, content_sha256, payload) VALUES (%s, %s, %s)
        ON CONFLICT (source_id, content_sha256) DO UPDATE SET content_sha256 = EXCLUDED.content_sha256
        RETURNING id
        """,
        (source_id, digest, Jsonb(payload)),
    ).fetchone()
    return row["id"]


def apply_postings(
    conn: psycopg.Connection, source_id: int, raw_capture_id: int, postings: list[Posting], seen_at: datetime | None = None
) -> None:
    """Upsert the current board contents and close postings that disappeared.

    `seen_at` is when the payload was fetched (default now); replaying an older capture never moves last_seen_at back.
    """
    for p in postings:
        conn.execute(
            """
            INSERT INTO job_postings (source_id, external_id, title, url, location, in_netherlands,
                                      department, description, published_at, raw_capture_id, first_seen_at, last_seen_at,
                                      seniority, is_tech, dutch_required, min_years, sponsorship_stance,
                                      salary_min, salary_max, salary_currency, salary_period)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, now()), COALESCE(%s::timestamptz, now()),
                    %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, external_id) DO UPDATE SET
                title = EXCLUDED.title, url = EXCLUDED.url, location = EXCLUDED.location,
                in_netherlands = EXCLUDED.in_netherlands, department = EXCLUDED.department,
                description = EXCLUDED.description, published_at = EXCLUDED.published_at,
                raw_capture_id = EXCLUDED.raw_capture_id, closed_at = NULL,
                last_seen_at = GREATEST(job_postings.last_seen_at, EXCLUDED.last_seen_at),
                seniority = EXCLUDED.seniority, is_tech = EXCLUDED.is_tech,
                dutch_required = EXCLUDED.dutch_required, min_years = EXCLUDED.min_years,
                sponsorship_stance = EXCLUDED.sponsorship_stance, salary_min = EXCLUDED.salary_min,
                salary_max = EXCLUDED.salary_max, salary_currency = EXCLUDED.salary_currency,
                salary_period = EXCLUDED.salary_period
            """,
            (source_id, p.external_id, p.title, p.url, p.location, p.in_netherlands,
             p.department, p.description, p.published_at, raw_capture_id, seen_at, seen_at,
             signals.seniority(p.title), signals.is_tech_role(p.title),
             signals.dutch_required(p.description, p.title), signals.min_years(p.description),
             signals.sponsorship_stance(p.description, p.title),
             p.salary_min, p.salary_max, p.salary_currency, p.salary_period),
        )
    conn.execute(
        """
        UPDATE job_postings SET closed_at = now()
        WHERE source_id = %s AND closed_at IS NULL AND NOT (external_id = ANY(%s))
        """,
        (source_id, [p.external_id for p in postings]),
    )


# Minimum seconds between requests per ATS. Recruitee rate-limits across all company
# subdomains together and sends no Retry-After; ~250 requests at full speed hit 429.
MIN_INTERVAL = {"recruitee": 1.0, "greenhouse": 0.2, "ashby": 0.2}
RETRY_DELAYS = (5.0, 15.0, 45.0)
_last_request: dict[str, float] = {}


def fetch_json(client: httpx.Client, kind: str, url: str, sleep=time.sleep, clock=time.monotonic) -> dict:
    for attempt in range(len(RETRY_DELAYS) + 1):
        wait = _last_request.get(kind, float("-inf")) + MIN_INTERVAL[kind] - clock()
        if wait > 0:
            sleep(wait)
        _last_request[kind] = clock()
        response = client.get(url)
        if response.status_code not in (429, 503) or attempt == len(RETRY_DELAYS):
            response.raise_for_status()
            return response.json()
        retry_after = response.headers.get("Retry-After", "")
        delay = float(retry_after) if retry_after.isdigit() else RETRY_DELAYS[attempt]
        log.info("%s %s returned %s; retrying in %.0fs", kind, url, response.status_code, delay)
        sleep(delay)
    raise AssertionError("unreachable")


def collect_source(conn: psycopg.Connection, client: httpx.Client, source: dict) -> RunResult:
    name = f"{source['kind']}:{source['board']}"
    run_id = conn.execute("INSERT INTO fetch_runs (source_id) VALUES (%s) RETURNING id", (source["id"],)).fetchone()["id"]
    conn.commit()
    collector = module_for(source["kind"])
    try:
        payload = fetch_json(client, source["kind"], collector.board_url(source["board"]))
        with conn.transaction():
            # Raw capture first: if parsing fails, the payload is still there to debug and replay.
            raw_id = store_raw_capture(conn, source["id"], payload)
            conn.execute("UPDATE fetch_runs SET raw_capture_id = %s WHERE id = %s", (raw_id, run_id))
        postings = collector.parse(payload)
        with conn.transaction():
            apply_postings(conn, source["id"], raw_id, postings)
            conn.execute(
                "UPDATE fetch_runs SET finished_at = now(), ok = true, posting_count = %s WHERE id = %s",
                (len(postings), run_id),
            )
        return RunResult(name, True, len(postings))
    except Exception as exc:  # one broken source must not stop the others
        conn.rollback()
        error = f"{type(exc).__name__}: {exc}"[:500]
        conn.execute("UPDATE fetch_runs SET finished_at = now(), ok = false, error = %s WHERE id = %s", (error, run_id))
        conn.commit()
        log.warning("collect %s failed: %s", name, error)
        return RunResult(name, False, error=error)


def collect_all(conn: psycopg.Connection, client: httpx.Client, only: str | None = None) -> list[RunResult]:
    sources = conn.execute("SELECT * FROM sources WHERE enabled ORDER BY id").fetchall()
    return [collect_source(conn, client, s) for s in sources if only in (None, f"{s['kind']}:{s['board']}")]


def replay(conn: psycopg.Connection) -> int:
    """Rebuild postings from each source's latest raw capture without refetching.

    Uses the latest fetched capture even when its parse failed, so a parser fix can be replayed.
    """
    latest = conn.execute(
        """
        SELECT DISTINCT ON (f.source_id) f.source_id, f.raw_capture_id, f.started_at, r.payload, s.kind, s.board
        FROM fetch_runs f JOIN raw_captures r ON r.id = f.raw_capture_id JOIN sources s ON s.id = f.source_id
        ORDER BY f.source_id, f.started_at DESC, f.id DESC
        """
    ).fetchall()
    conn.commit()
    replayed = 0
    for row in latest:
        try:
            postings = module_for(row["kind"]).parse(row["payload"])
            with conn.transaction():
                apply_postings(conn, row["source_id"], row["raw_capture_id"], postings, seen_at=row["started_at"])
            replayed += 1
        except Exception as exc:  # one broken payload must not stop the others
            log.warning("replay %s:%s failed: %s: %s", row["kind"], row["board"], type(exc).__name__, exc)
    return replayed


def prune(conn: psycopg.Connection, keep_days: int = 14) -> int:
    """Delete raw captures not used for `keep_days`, keeping each source's latest and any an open posting references.

    Closed postings do not pin captures: they are never replayed, and their reference becomes NULL.
    """
    deleted = conn.execute(
        """
        DELETE FROM raw_captures r
        WHERE r.first_fetched_at < now() - make_interval(days => %(days)s)
          AND NOT EXISTS (SELECT 1 FROM job_postings p WHERE p.raw_capture_id = r.id AND p.closed_at IS NULL)
          AND NOT EXISTS (
              SELECT 1 FROM fetch_runs f
              WHERE f.raw_capture_id = r.id AND f.started_at >= now() - make_interval(days => %(days)s))
          AND r.id NOT IN (
              SELECT DISTINCT ON (source_id) raw_capture_id FROM fetch_runs
              WHERE raw_capture_id IS NOT NULL ORDER BY source_id, started_at DESC, id DESC)
        """,
        {"days": keep_days},
    ).rowcount
    conn.commit()
    return deleted
