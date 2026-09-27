"""Link each source's employer to the IND register.

A manually verified KvK number wins. Otherwise the employer name and every
register organisation are normalized, and equal keys count as a name-inferred
match. Phase 3 measures precision and recall of this against labeled pairs.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections import defaultdict

import psycopg


# Legal-form tokens after dots are removed ("B.V." -> "bv"). Only stripped from the end of a name,
# so a word like "AB" inside a brand survives.
LEGAL_FORMS = {
    "bv", "nv", "vof", "cv", "ltd", "limited", "gmbh", "ag", "inc", "llc", "plc", "sa", "sarl",
    "sas", "srl", "spa", "ab", "as", "oy", "pty", "se", "co", "corp", "corporation", "company",
}


def normalize_employer_name(name: str) -> str:
    """Reduce an employer or register organisation name to a comparison key.

    Precision first: only case, accents, punctuation, and trailing legal forms are
    removed. "Adyen" meets "Adyen N.V." but not "Adyen Netherlands B.V.", and
    group words like Holding or Netherlands are kept, because merging them would
    join unrelated companies that share a first word. Brand-to-entity links such as
    Elastic -> elasticsearch B.V. belong in a hand-checked `kvk` seed instead.
    """
    tokens = name_tokens(name)
    while tokens and tokens[-1] in LEGAL_FORMS:
        tokens.pop()
    return " ".join(tokens)


def name_tokens(name: str) -> list[str]:
    """Lowercase ASCII word tokens of a name; dots are dropped first, so "B.V." is one token "bv"."""
    text = unicodedata.normalize("NFKD", html.unescape(name)).encode("ascii", "ignore").decode()
    text = text.casefold().replace("&", " and ").replace(".", "")
    return re.findall(r"[a-z0-9]+", text)


def match_sources(conn: psycopg.Connection) -> dict[str, int]:
    """Link every source to the live (latest captured) snapshot.

    A matched source whose KvKs all left the register becomes `unmatched` with `delisted_on` set; it keeps
    its old KvKs and organisations so the page and the register-changes view can say what was removed.
    """
    snapshot = conn.execute(
        """
        SELECT id, coalesce(register_updated_on, (captured_at AT TIME ZONE 'UTC')::date) AS updated_on
        FROM register_snapshots ORDER BY captured_at DESC LIMIT 1
        """
    ).fetchone()
    if snapshot is None:
        raise RuntimeError("no register snapshot; run `sponsor-radar register` first")
    entries = conn.execute(
        "SELECT kvk_number, organisation FROM register_entries WHERE snapshot_id = %s", (snapshot["id"],)
    ).fetchall()
    by_kvk: dict[str, list[str]] = defaultdict(list)
    by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for e in entries:
        by_kvk[e["kvk_number"]].append(e["organisation"])
        if key := normalize_employer_name(e["organisation"]):
            by_key[key].append((e["kvk_number"], e["organisation"]))

    counts: dict[str, int] = defaultdict(int)
    sources = conn.execute(
        """
        SELECT s.id, s.employer_name, s.kvk_number, m.status AS old_status, m.kvk_numbers AS old_kvks,
               m.organisations AS old_orgs, m.delisted_on AS old_delisted_on
        FROM sources s LEFT JOIN sponsor_matches m ON m.source_id = s.id
        """
    ).fetchall()
    conn.commit()  # end the read transaction so the block below commits on its own
    with conn.transaction():
        for source in sources:
            if source["kvk_number"]:
                # A verified KvK that is absent from the register means the employer is not a sponsor.
                orgs = by_kvk.get(source["kvk_number"], [])
                status, kvks = ("kvk_confirmed", [source["kvk_number"]]) if orgs else ("unmatched", [])
            else:
                candidates = by_key.get(normalize_employer_name(source["employer_name"]), [])
                kvks, orgs = [c[0] for c in candidates], [c[1] for c in candidates]
                status = "name_inferred" if candidates else "unmatched"
            delisted_on = None
            was_linked = source["old_status"] in ("kvk_confirmed", "name_inferred") or source["old_delisted_on"]
            if status == "unmatched" and was_linked and source["old_kvks"] and not any(k in by_kvk for k in source["old_kvks"]):
                # Every KvK it was linked to left the register: keep them, and the first date it was seen gone.
                kvks, orgs = source["old_kvks"], source["old_orgs"]
                delisted_on = source["old_delisted_on"] or snapshot["updated_on"]
            conn.execute(
                """
                INSERT INTO sponsor_matches (source_id, snapshot_id, status, kvk_numbers, organisations, delisted_on)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET snapshot_id = EXCLUDED.snapshot_id, status = EXCLUDED.status,
                    kvk_numbers = EXCLUDED.kvk_numbers, organisations = EXCLUDED.organisations,
                    delisted_on = EXCLUDED.delisted_on, decided_at = now()
                """,
                (source["id"], snapshot["id"], status, kvks, orgs, delisted_on),
            )
            counts[status] += 1
            counts["delisted"] += bool(delisted_on)
    return dict(counts)
