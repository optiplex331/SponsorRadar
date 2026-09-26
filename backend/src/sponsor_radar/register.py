"""IND public register of recognised sponsors (regular labour and highly skilled migrants)."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser

import httpx
import psycopg

REGISTER_URL = "https://ind.nl/en/public-register-recognised-sponsors/public-register-regular-labour-and-highly-skilled-migrants"


@dataclass(frozen=True)
class RegisterEntry:
    organisation: str
    kvk_number: str


class _RegisterTable(HTMLParser):
    """Collects `<tr><th scope="row">name</th><td>kvk</td></tr>` rows."""

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
        elif tag == "tr" and len(self._row) == 2 and re.fullmatch(r"\d{8}", self._row[1]):
            self.entries.append(RegisterEntry(organisation=self._row[0], kvk_number=self._row[1]))

    def handle_data(self, data: str) -> None:
        if self._cell:
            self._text.append(data)


def parse_register(markup: str) -> tuple[list[RegisterEntry], date | None]:
    table = _RegisterTable()
    table.feed(markup)
    match = re.search(r"last updated on (\d{1,2} \w+ \d{4})", html.unescape(markup))
    updated_on = datetime.strptime(match.group(1), "%d %B %Y").date() if match else None
    return table.entries, updated_on


def sync_register(conn: psycopg.Connection, client: httpx.Client) -> tuple[int, bool]:
    """Fetch the register; store a snapshot only when the content changed.

    Returns the latest snapshot id and whether a new snapshot was created.
    """
    response = client.get(REGISTER_URL)
    response.raise_for_status()
    markup = response.text
    entries, updated_on = parse_register(markup)
    if len(entries) < 1000:
        raise ValueError(f"register parse returned only {len(entries)} rows; page layout probably changed")
    # Hash the parsed rows, not the page: navigation or tracking markup must not create snapshots.
    rows = sorted({(e.kvk_number, e.organisation) for e in entries})
    digest = hashlib.sha256("\n".join(f"{kvk}\t{org}" for kvk, org in rows).encode()).hexdigest()
    existing = conn.execute("SELECT id FROM register_snapshots WHERE content_sha256 = %s", (digest,)).fetchone()
    conn.commit()  # end the read transaction so the block below commits on its own
    if existing:
        return existing["id"], False
    with conn.transaction():
        snapshot_id = conn.execute(
            "INSERT INTO register_snapshots (content_sha256, register_updated_on, raw_html) VALUES (%s, %s, %s) RETURNING id",
            (digest, updated_on, markup),
        ).fetchone()["id"]
        with conn.cursor().copy("COPY register_entries (snapshot_id, kvk_number, organisation) FROM STDIN") as copy:
            for row in rows:
                copy.write_row((snapshot_id, *row))
    return snapshot_id, True
