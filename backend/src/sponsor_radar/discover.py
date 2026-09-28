"""Find job boards of register sponsors we do not track yet.

Organisation names become Greenhouse, Ashby, and Recruitee slug candidates; each existing board is a
hit for a person to check before it goes into `seeds.toml` with its `kvk`.
"""

from __future__ import annotations

import csv
import html
import logging
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

import httpx
import psycopg

from . import ingest
from .collectors import module_for
from .matching import LEGAL_FORMS

log = logging.getLogger(__name__)
KINDS = ("greenhouse", "ashby", "recruitee")
# Group and country words that register names add to a brand ("Adyen Netherlands B.V.").
NOISE_WORDS = {"holding", "holdings", "netherlands", "nederland", "group", "groep", "the"}
PROGRESS_EVERY = 100  # KvKs between progress log lines
CSV_COLUMNS = ["kvk_number", "organisation", "kind", "board", "nl_postings", "total_postings"]


def slug_candidates(organisation: str) -> list[str]:
    """Board slugs to try: tokens joined, hyphen-joined, and the first token when it is distinctive enough."""
    text = unicodedata.normalize("NFKD", html.unescape(organisation)).encode("ascii", "ignore").decode()
    text = re.sub(r"\([^)]*\)", " ", text.casefold()).replace(".", "")
    tokens = [t for t in re.findall(r"[a-z0-9]+", text) if t not in NOISE_WORDS]
    while tokens and tokens[-1] in LEGAL_FORMS:
        tokens.pop()
    if not tokens:
        return []
    candidates = ["".join(tokens), "-".join(tokens)]
    if len(tokens[0]) >= 4:
        candidates.append(tokens[0])
    return list(dict.fromkeys(candidates))


def targets(conn: psycopg.Connection, since: date | None = None) -> list[dict]:
    """KvKs to probe that no source is linked to.

    Default: KvKs added between the previous and the live snapshot. With `since`: every KvK first seen on or after it.
    """
    linked = """
        NOT EXISTS (SELECT 1 FROM sources s WHERE s.kvk_number = e.kvk_number)
        AND NOT EXISTS (SELECT 1 FROM sponsor_matches m WHERE e.kvk_number = ANY(m.kvk_numbers))
    """
    if since is None:
        snapshots = conn.execute("SELECT id FROM register_snapshots ORDER BY captured_at DESC LIMIT 2").fetchall()
        if len(snapshots) < 2:
            return []
        query = f"""
            SELECT e.kvk_number, string_agg(e.organisation, ' / ' ORDER BY e.organisation) AS organisation
            FROM register_entries e
            WHERE e.snapshot_id = %(current)s AND {linked}
              AND NOT EXISTS (SELECT 1 FROM register_entries p WHERE p.snapshot_id = %(previous)s AND p.kvk_number = e.kvk_number)
            GROUP BY e.kvk_number ORDER BY organisation
        """
        params = {"current": snapshots[0]["id"], "previous": snapshots[1]["id"]}
    else:
        query = f"""
            WITH live AS (SELECT id FROM register_snapshots ORDER BY captured_at DESC LIMIT 1),
            first_seen AS (
                SELECT e.kvk_number, min(coalesce(s.register_updated_on, (s.captured_at AT TIME ZONE 'UTC')::date)) AS day
                FROM register_entries e JOIN register_snapshots s ON s.id = e.snapshot_id
                GROUP BY e.kvk_number
            )
            SELECT e.kvk_number, string_agg(e.organisation, ' / ' ORDER BY e.organisation) AS organisation
            FROM register_entries e JOIN first_seen f USING (kvk_number)
            WHERE e.snapshot_id = (SELECT id FROM live) AND f.day >= %(since)s AND {linked}
            GROUP BY e.kvk_number ORDER BY organisation
        """
        params = {"since": since}
    rows = conn.execute(query, params).fetchall()
    conn.commit()
    return rows


def probe(client: httpx.Client, kind: str, board: str) -> tuple[int, int] | None:
    """(NL postings, all postings) when the board exists, None on 404."""
    collector = module_for(kind)
    try:
        payload = ingest.fetch_json(client, kind, collector.board_url(board))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise
    postings = collector.parse(payload)
    return sum(p.in_netherlands for p in postings), len(postings)


def discover(conn: psycopg.Connection, client: httpx.Client, out: Path, since: date | None = None) -> tuple[int, int]:
    """Probe every slug candidate of the target KvKs and write hits to `out`. Returns (KvKs probed, hits)."""
    rows = targets(conn, since)
    hits = errors = 0
    started = time.monotonic()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Hits are written as they are found, so a run that dies after hours keeps what it found.
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        # Organisation names are joined with " / " when a KvK has several; each name yields its own candidates.
        for done, row in enumerate(rows, 1):
            slugs = list(dict.fromkeys(s for name in row["organisation"].split(" / ") for s in slug_candidates(name)))
            for kind in KINDS:
                for slug in slugs:
                    try:
                        found = probe(client, kind, slug)
                    except Exception as exc:  # one failing probe must not stop the run
                        errors += 1
                        log.warning("probe %s:%s failed: %s: %s", kind, slug, type(exc).__name__, exc)
                        continue
                    if found:
                        hits += 1
                        writer.writerow((row["kvk_number"], row["organisation"], kind, slug, *found))
                        f.flush()
                        log.info("hit %s:%s for %s (%d NL of %d)", kind, slug, row["organisation"], *found)
            if done % PROGRESS_EVERY == 0 or done == len(rows):
                elapsed = time.monotonic() - started
                log.info(
                    "progress %d/%d KvKs, %d hits, %d probe errors, %.0f min elapsed, ~%.0f min left",
                    done, len(rows), hits, errors, elapsed / 60, elapsed / done * (len(rows) - done) / 60,
                )
    return len(rows), hits
