"""IND public register of recognised sponsors (regular labour and highly skilled migrants)."""

from __future__ import annotations

import hashlib
import html
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser

import httpx
import psycopg

from .ingest import paced_get
from .lookup import DEFAULT_VIEW_SQL

log = logging.getLogger(__name__)
REGISTER_URL = "https://ind.nl/en/public-register-recognised-sponsors/public-register-work"
# The register moved to REGISTER_URL in spring 2026 (the old URL redirects); archive.org lists copies per URL.
ARCHIVED_URLS = (
    "https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants",
    REGISTER_URL,
)
CDX_URL = "https://web.archive.org/cdx/search/cdx"
ARCHIVE_TIMEOUT = 120  # archive.org often takes over 30 s for a listing or a 1.5 MB copy
# A parse with fewer rows means the page layout changed; the real register has about 13,000 rows.
MIN_ROWS = 1000


@dataclass(frozen=True)
class RegisterEntry:
    organisation: str
    kvk_number: str


class _RegisterTable(HTMLParser):
    """Collects `<tr><th scope="row">name</th><td>kvk</td></tr>` rows.

    The June and July 2025 pages used `<td>` for the name and padded KvKs to nine digits ("016051874").
    """

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[RegisterEntry] = []
        self._cell: str | None = None
        self._row: list[str] = []
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._cell, self._text = tag, []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("th", "td") and self._cell:
            self._row.append("".join(self._text).strip())
            self._cell = None
        elif tag == "tr" and len(self._row) == 2 and (kvk := re.fullmatch(r"0?(\d{8})", self._row[1])):
            self.entries.append(RegisterEntry(organisation=self._row[0], kvk_number=kvk.group(1)))

    def handle_data(self, data: str) -> None:
        if self._cell:
            self._text.append(data)


def parse_register(markup: str) -> tuple[list[RegisterEntry], date | None]:
    table = _RegisterTable()
    table.feed(markup)
    # Pages since 2025 say "last updated on 3 September 2026"; 2023-2024 copies say "Last update: 7 July 2023".
    match = re.search(r"last update(?:d on|:)\s*(\d{1,2} \w+ \d{4})", html.unescape(markup), re.IGNORECASE)
    updated_on = datetime.strptime(match.group(1), "%d %B %Y").date() if match else None
    return table.entries, updated_on


class TooFewRows(ValueError):
    pass


def store_snapshot(conn: psycopg.Connection, markup: str, captured_at: datetime | None = None) -> tuple[int, bool]:
    """Store a register page as a snapshot unless a snapshot with the same parsed rows exists.

    `captured_at` is set for archive.org copies; live fetches use now(). Returns the snapshot id
    and whether it is new.
    """
    entries, updated_on = parse_register(markup)
    if len(entries) < MIN_ROWS:
        raise TooFewRows(f"register parse returned only {len(entries)} rows; page layout probably changed")
    # Hash the parsed rows, not the page: navigation or tracking markup must not create snapshots.
    rows = sorted({(e.kvk_number, e.organisation) for e in entries})
    digest = hashlib.sha256("\n".join(f"{kvk}\t{org}" for kvk, org in rows).encode()).hexdigest()
    existing = conn.execute("SELECT id FROM register_snapshots WHERE content_sha256 = %s", (digest,)).fetchone()
    conn.commit()  # end the read transaction so the block below commits on its own
    if existing:
        return existing["id"], False
    with conn.transaction():
        snapshot_id = conn.execute(
            """
            INSERT INTO register_snapshots (content_sha256, register_updated_on, raw_html, captured_at)
            VALUES (%s, %s, %s, coalesce(%s, now())) RETURNING id
            """,
            (digest, updated_on, markup, captured_at),
        ).fetchone()["id"]
        with conn.cursor().copy("COPY register_entries (snapshot_id, kvk_number, organisation) FROM STDIN") as copy:
            for row in rows:
                copy.write_row((snapshot_id, *row))
    return snapshot_id, True


def sync_register(conn: psycopg.Connection, client: httpx.Client) -> tuple[int, bool]:
    """Fetch the register; store a snapshot only when the content changed.

    Returns the latest snapshot id and whether a new snapshot was created.
    """
    response = client.get(REGISTER_URL)
    response.raise_for_status()
    return store_snapshot(conn, response.text)


def backfill_register(conn: psycopg.Connection, client: httpx.Client, sleep=time.sleep) -> dict[str, int]:
    """Store past register versions from archive.org copies, so register changes and first-seen dates reach back to 2023.

    Each copy keeps its archive timestamp as `captured_at`, which is older than the live snapshot, so
    matching keeps using the live one. One bad copy is logged and skipped.
    """
    copies = []
    for page_url in ARCHIVED_URLS:
        listing = paced_get(
            client, "archive", CDX_URL,
            params={"url": page_url, "output": "json", "filter": "statuscode:200", "collapse": "digest"},
            sleep=sleep, timeout=ARCHIVE_TIMEOUT,
        ).json()
        copies += [dict(zip(listing[0], row)) for row in listing[1:]]
    counts = {"copies": 0, "stored": 0, "duplicate": 0, "too_few_rows": 0, "failed": 0}
    for copy in sorted(copies, key=lambda c: c["timestamp"]):
        counts["copies"] += 1
        captured_at = datetime.strptime(copy["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        url = f"https://web.archive.org/web/{copy['timestamp']}id_/{copy['original']}"
        try:
            markup = paced_get(client, "archive", url, sleep=sleep, timeout=ARCHIVE_TIMEOUT).text
            _, created = store_snapshot(conn, markup, captured_at)
            counts["stored" if created else "duplicate"] += 1
        except TooFewRows as exc:
            conn.rollback()
            counts["too_few_rows"] += 1
            log.warning("archive copy %s skipped: %s", copy["timestamp"], exc)
        except Exception as exc:  # one broken copy must not stop the others
            conn.rollback()
            counts["failed"] += 1
            log.warning("archive copy %s failed: %s: %s", copy["timestamp"], type(exc).__name__, exc)
    return counts


def _snapshot_day(snapshot: dict) -> date:
    return snapshot["register_updated_on"] or snapshot["captured_at"].astimezone(UTC).date()


def _tracked(conn: psycopg.Connection, kvks: list[str], delisted: bool) -> dict[str, list[dict]]:
    """Sources linked to each KvK: current matches for added KvKs, delisted matches for removed ones."""
    rows = conn.execute(
        f"""
        SELECT k.kvk, s.employer_name AS employer, s.kind, s.board,
               (SELECT count(*) FROM job_postings p WHERE p.source_id = s.id AND {DEFAULT_VIEW_SQL})::int AS open_postings
        FROM sponsor_matches m
        JOIN sources s ON s.id = m.source_id
        CROSS JOIN LATERAL unnest(m.kvk_numbers) AS k (kvk)
        WHERE k.kvk = ANY(%s) AND {"m.delisted_on IS NOT NULL" if delisted else "m.status <> 'unmatched'"}
        ORDER BY s.employer_name, s.kind, s.board
        """,
        (kvks,),
    ).fetchall()
    by_kvk: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_kvk[r.pop("kvk")].append(r)
    return by_kvk


def _diff(conn: psycopg.Connection, left: int, right: int) -> list[dict]:
    """KvKs in snapshot `left` but not in `right`, one row per KvK with its names joined."""
    return conn.execute(
        """
        SELECT a.kvk_number, string_agg(a.organisation, ' / ' ORDER BY a.organisation) AS organisation
        FROM register_entries a
        WHERE a.snapshot_id = %s
          AND NOT EXISTS (SELECT 1 FROM register_entries b WHERE b.snapshot_id = %s AND b.kvk_number = a.kvk_number)
        GROUP BY a.kvk_number
        """,
        (left, right),
    ).fetchall()


def _sorted(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (-sum(t["open_postings"] for t in r["tracked"]), r["organisation"].casefold()))


def register_changes(conn: psycopg.Connection) -> dict:
    """Compare the latest two register snapshots by KvK number."""
    snapshots = conn.execute(
        "SELECT id, register_updated_on, captured_at FROM register_snapshots ORDER BY captured_at DESC LIMIT 2"
    ).fetchall()
    public = [{"register_updated_on": s["register_updated_on"], "captured_at": s["captured_at"]} for s in snapshots]
    result = {
        "current": public[0] if public else None, "previous": public[1] if len(public) > 1 else None,
        "added_count": 0, "removed_count": 0, "added": [], "removed": [],
    }
    if len(snapshots) < 2:
        return result
    current, previous = snapshots
    added, removed = _diff(conn, current["id"], previous["id"]), _diff(conn, previous["id"], current["id"])

    # First snapshot each added KvK appears in; "new sponsor" needs an older snapshot without it to be knowable.
    first_seen = {
        r["kvk_number"]: r for r in conn.execute(
            """
            SELECT DISTINCT ON (e.kvk_number) e.kvk_number, s.register_updated_on, s.captured_at,
                   EXISTS (SELECT 1 FROM register_snapshots o WHERE o.captured_at < s.captured_at) AS has_older
            FROM register_entries e JOIN register_snapshots s ON s.id = e.snapshot_id
            WHERE e.kvk_number = ANY(%s)
            ORDER BY e.kvk_number, s.captured_at
            """,
            ([r["kvk_number"] for r in added],),
        ).fetchall()
    }
    new_since = _snapshot_day(current) - timedelta(days=365)
    tracked = _tracked(conn, [r["kvk_number"] for r in added], delisted=False)
    for r in added:
        seen = first_seen.get(r["kvk_number"])
        r["first_seen_on"] = _snapshot_day(seen) if seen else None
        r["new_sponsor"] = bool(seen and seen["has_older"] and r["first_seen_on"] >= new_since)
        r["tracked"] = tracked.get(r["kvk_number"], [])
    tracked = _tracked(conn, [r["kvk_number"] for r in removed], delisted=True)
    for r in removed:
        r["tracked"] = tracked.get(r["kvk_number"], [])
    conn.commit()
    return result | {
        "added_count": len(added), "removed_count": len(removed), "added": _sorted(added), "removed": _sorted(removed),
    }
