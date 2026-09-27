"""Sponsor lookup: find an organisation on the latest IND register by KvK number, name, or tracked brand.

Names match on whole tokens, never on substrings inside a word: every query token but the last must equal a
token of one organisation name, and the last must start one. So "Ans" finds "ANS Group B.V." and never
"Transport Hollanders B.V.". Hand-checked `kvk` seeds add their brand names, so "DEPT" finds its legal entity.

Trailing legal forms are left out of the index, so a query "b" does not match every "B.V."; a query's own
trailing legal form or "Holding" is dropped. The latest snapshot lives in a small in-process token index,
rebuilt when a newer snapshot appears (about 0.3 s for 13k names). Token normalization reuses `matching`, which
is Python (accents, "&", dotted legal forms); doing it in SQL would mean re-implementing it there.
"""

from __future__ import annotations

import re
import threading
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC

import psycopg

from .matching import LEGAL_FORMS, name_tokens, normalize_employer_name

MIN_QUERY = 2
MAX_RESULTS = 20
# Dropped from the end of a query only, and only while another token remains ("AB" alone stays a query).
QUERY_SUFFIXES = LEGAL_FORMS | {"holding", "holdings"}
KVK_QUERY = re.compile(r"0?(\d{8})")  # same rule as the register parser: 8 digits, one extra leading zero allowed

# The page's default view, apart from the matched-sponsor filter: open, in the Netherlands, tech, not senior,
# no Dutch requirement, at most 2 years asked or unstated, and not ruling out visa sponsorship. A signal not
# computed yet (NULL) hides nothing, as on the page.
DEFAULT_VIEW_SQL = """
    p.closed_at IS NULL AND p.in_netherlands AND p.is_tech AND p.seniority IS DISTINCT FROM 'senior'
    AND p.dutch_required IS NOT TRUE
    AND (p.min_years IS NULL OR p.min_years <= 2) AND p.sponsorship_stance IS DISTINCT FROM 'refuses_visa'
"""


@dataclass
class Index:
    key: tuple
    names: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)  # (kvk, tokens) per organisation name
    organisations: dict[str, list[str]] = field(default_factory=dict)  # kvk -> names, sorted
    sort_keys: dict[str, str] = field(default_factory=dict)  # kvk -> tokens of its first name, so quotes do not sort first
    postings: dict[str, set[int]] = field(default_factory=dict)  # token -> positions in `names`
    tokens: list[str] = field(default_factory=list)  # sorted keys of `postings`, for prefix search


_lock = threading.Lock()
_index: Index | None = None


def _build(conn: psycopg.Connection, snapshot: dict, key: tuple) -> Index:
    index = Index(key)
    organisations: dict[str, list[str]] = defaultdict(list)
    postings: dict[str, set[int]] = defaultdict(set)
    for row in conn.execute(
        "SELECT kvk_number, organisation FROM register_entries WHERE snapshot_id = %s", (snapshot["id"],)
    ):
        organisations[row["kvk_number"]].append(row["organisation"])
        # Trailing legal forms are not indexed, so "b" does not match every "B.V.".
        tokens = tuple(normalize_employer_name(row["organisation"]).split() or name_tokens(row["organisation"]))
        for token in tokens:
            postings[token].add(len(index.names))
        index.names.append((row["kvk_number"], tokens))
    index.organisations = {kvk: sorted(names, key=str.casefold) for kvk, names in organisations.items()}
    index.sort_keys = {kvk: " ".join(name_tokens(names[0])) for kvk, names in index.organisations.items()}
    index.postings = dict(postings)
    index.tokens = sorted(postings)
    return index


def _current_index(conn: psycopg.Connection) -> Index | None:
    global _index
    snapshot = conn.execute(
        "SELECT id, content_sha256, captured_at FROM register_snapshots ORDER BY captured_at DESC LIMIT 1"
    ).fetchone()
    if snapshot is None:
        return None
    key = (snapshot["id"], snapshot["content_sha256"], snapshot["captured_at"])
    with _lock:
        if _index is None or _index.key != key:
            _index = _build(conn, snapshot, key)
        return _index


def query_tokens(q: str) -> list[str]:
    tokens = name_tokens(q)
    while len(tokens) > 1 and tokens[-1] in QUERY_SUFFIXES:
        tokens.pop()
    return tokens


def _matches(tokens: tuple[str, ...] | list[str], query: list[str]) -> bool:
    *whole, last = query
    return all(t in tokens for t in whole) and any(t.startswith(last) for t in tokens)


def _rank(tokens: tuple[str, ...] | list[str], query: list[str]) -> int:
    """0: the name is the query (legal forms aside), 1: the name starts with it, 2: it matches elsewhere."""
    stripped = list(tokens)
    while stripped and stripped[-1] in QUERY_SUFFIXES:
        stripped.pop()
    if stripped == query:
        return 0
    starts = len(tokens) >= len(query) and list(tokens[: len(query) - 1]) == query[:-1]
    return 1 if starts and tokens[len(query) - 1].startswith(query[-1]) else 2


def _name_hits(index: Index, query: list[str]) -> dict[str, int]:
    *whole, last = query
    start = bisect_left(index.tokens, last)
    candidates: set[int] = set()
    for token in index.tokens[start:]:
        if not token.startswith(last):
            break
        candidates |= index.postings[token]
    for token in whole:
        candidates &= index.postings.get(token, set())
    best: dict[str, int] = {}
    for position in candidates:  # every candidate matches: it has the whole tokens and one starting with `last`
        kvk, tokens = index.names[position]
        best[kvk] = min(best.get(kvk, 3), _rank(tokens, query))
    return best


def search(conn: psycopg.Connection, q: str) -> dict:
    """Up to MAX_RESULTS register organisations for a query of at least MIN_QUERY characters."""
    index = _current_index(conn)
    q = q.strip()
    if index is None:
        return {"results": [], "more": False}

    ranks: dict[str, int] = {}
    brands: dict[str, str] = {}
    if kvk := KVK_QUERY.fullmatch(re.sub(r"\s", "", q)):
        if kvk.group(1) in index.organisations:
            ranks[kvk.group(1)] = 0
    elif query := query_tokens(q):
        ranks = _name_hits(index, query)
        for row in conn.execute(
            "SELECT DISTINCT employer_name, kvk_number FROM sources WHERE kvk_number IS NOT NULL ORDER BY employer_name"
        ):
            brand = normalize_employer_name(row["employer_name"]).split()
            if row["kvk_number"] in index.organisations and brand and _matches(brand, query):
                rank = _rank(brand, query)
                if rank < ranks.get(row["kvk_number"], 3):
                    ranks[row["kvk_number"]] = rank
                    brands[row["kvk_number"]] = row["employer_name"]

    ordered = sorted(ranks, key=lambda k: (ranks[k], index.sort_keys[k], k))
    kvks = ordered[:MAX_RESULTS]
    results = [
        {
            "kvk_number": kvk,
            "organisation": " / ".join(index.organisations[kvk]),
            "brand": brands.get(kvk),
            "first_seen_on": None,
            "before_history": False,
            "tracked": [],
        }
        for kvk in kvks
    ]
    if results:
        _add_first_seen(conn, results)
        _add_tracked(conn, results)
    conn.commit()
    return {"results": results, "more": len(ordered) > MAX_RESULTS}


def _add_first_seen(conn: psycopg.Connection, results: list[dict]) -> None:
    """First snapshot each KvK appears in; when that is the oldest snapshot, it joined before our history starts."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (e.kvk_number) e.kvk_number, s.register_updated_on, s.captured_at,
               NOT EXISTS (SELECT 1 FROM register_snapshots o WHERE o.captured_at < s.captured_at) AS oldest
        FROM register_entries e JOIN register_snapshots s ON s.id = e.snapshot_id
        WHERE e.kvk_number = ANY(%s)
        ORDER BY e.kvk_number, s.captured_at
        """,
        ([r["kvk_number"] for r in results],),
    ).fetchall()
    seen = {r["kvk_number"]: r for r in rows}
    for r in results:
        if s := seen.get(r["kvk_number"]):
            r["first_seen_on"] = s["register_updated_on"] or s["captured_at"].astimezone(UTC).date()
            r["before_history"] = s["oldest"]


def _add_tracked(conn: psycopg.Connection, results: list[dict]) -> None:
    rows = conn.execute(
        f"""
        SELECT k.kvk, s.employer_name AS employer, s.kind, s.board,
               (SELECT count(*) FROM job_postings p WHERE p.source_id = s.id AND {DEFAULT_VIEW_SQL})::int AS open_postings
        FROM sponsor_matches m
        JOIN sources s ON s.id = m.source_id
        CROSS JOIN LATERAL unnest(m.kvk_numbers) AS k (kvk)
        WHERE k.kvk = ANY(%s) AND m.status <> 'unmatched'
        ORDER BY s.employer_name, s.kind, s.board
        """,
        ([r["kvk_number"] for r in results],),
    ).fetchall()
    by_kvk: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_kvk[row.pop("kvk")].append(row)
    for r in results:
        r["tracked"] = by_kvk.get(r["kvk_number"], [])
