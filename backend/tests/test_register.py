from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest

from sponsor_radar import register
from sponsor_radar.matching import match_sources
from sponsor_radar.register import ARCHIVED_URLS, backfill_register, register_changes, store_snapshot

from conftest import FIXTURES


def _snapshot(conn, rows: list[tuple[str, str]], updated_on: str, captured_at: str) -> int:
    snapshot_id = conn.execute(
        "INSERT INTO register_snapshots (content_sha256, register_updated_on, raw_html, captured_at) "
        "VALUES (%s, %s, '', %s) RETURNING id",
        (captured_at, updated_on, captured_at),
    ).fetchone()["id"]
    for kvk, org in rows:
        conn.execute(
            "INSERT INTO register_entries (snapshot_id, kvk_number, organisation) VALUES (%s, %s, %s)", (snapshot_id, kvk, org)
        )
    conn.commit()
    return snapshot_id


def _source(conn, board: str, employer: str, kvk: str | None = None) -> int:
    source_id = conn.execute(
        "INSERT INTO sources (kind, board, employer_name, kvk_number) VALUES ('greenhouse', %s, %s, %s) RETURNING id",
        (board, employer, kvk),
    ).fetchone()["id"]
    conn.commit()
    return source_id


def _match(conn, source_id):
    return conn.execute(
        "SELECT status, kvk_numbers, organisations, delisted_on FROM sponsor_matches WHERE source_id = %s", (source_id,)
    ).fetchone()


def _open_postings(conn, source_id, n):
    raw_id = conn.execute(
        "INSERT INTO raw_captures (source_id, content_sha256, payload) VALUES (%s, 'x', '{}') RETURNING id", (source_id,)
    ).fetchone()["id"]
    for i in range(n):
        conn.execute(
            """
            INSERT INTO job_postings (source_id, external_id, title, url, location, in_netherlands, description,
                                      raw_capture_id, is_tech)
            VALUES (%s, %s, 'Engineer', 'https://example.com', 'Amsterdam', true, '', %s, true)
            """,
            (source_id, str(i), raw_id),
        )
    conn.commit()


def test_delisted_match_keeps_old_kvks_and_clears_when_back(conn):
    acme = _source(conn, "acme", "Acme")
    seeded = _source(conn, "globex", "Globex", kvk="01234567")
    _snapshot(conn, [("00123456", "Acme B.V."), ("01234567", "Globex Nederland B.V.")], "2026-08-03", "2026-08-04")
    match_sources(conn)

    _snapshot(conn, [("09999999", "Other B.V.")], "2026-09-03", "2026-09-04")
    counts = match_sources(conn)
    match_sources(conn)  # a daily rerun on the same snapshot keeps the delisting date

    assert counts["delisted"] == 2
    assert _match(conn, acme) == {
        "status": "unmatched", "kvk_numbers": ["00123456"], "organisations": ["Acme B.V."], "delisted_on": date(2026, 9, 3),
    }
    assert _match(conn, seeded)["delisted_on"] == date(2026, 9, 3)
    assert _match(conn, seeded)["kvk_numbers"] == ["01234567"]

    _snapshot(conn, [("00123456", "Acme B.V.")], "2026-10-03", "2026-10-04")
    match_sources(conn)

    assert _match(conn, acme) == {
        "status": "name_inferred", "kvk_numbers": ["00123456"], "organisations": ["Acme B.V."], "delisted_on": None,
    }
    assert _match(conn, seeded)["delisted_on"] == date(2026, 9, 3)


def test_register_changes_between_latest_two_snapshots(conn):
    _snapshot(conn, [("07654321", "Returning B.V."), ("08888888", "Gone B.V.")], "2025-01-03", "2025-01-10")
    _snapshot(conn, [("08888888", "Gone B.V."), ("00000001", "Stays B.V.")], "2026-08-03", "2026-08-04")
    _snapshot(
        conn,
        [("00000001", "Stays B.V."), ("00123456", "Beta Labs B.V."), ("00123456", "Beta B.V."),
         ("07654321", "Returning B.V."), ("00555555", "Alpha B.V.")],
        "2026-09-03", "2026-09-04",
    )
    beta = _source(conn, "beta", "Beta")
    gone = _source(conn, "gone", "Gone")
    _open_postings(conn, beta, 2)
    _open_postings(conn, gone, 1)
    for source_id, status, kvk, org, delisted_on in ((beta, "name_inferred", "00123456", "Beta B.V.", None),
                                                     (gone, "unmatched", "08888888", "Gone B.V.", "2026-09-03")):
        conn.execute(
            "INSERT INTO sponsor_matches (source_id, snapshot_id, status, kvk_numbers, organisations, delisted_on) "
            "SELECT %s, max(id), %s, %s, %s, %s FROM register_snapshots",
            (source_id, status, [kvk], [org], delisted_on),
        )
    conn.commit()

    changes = register_changes(conn)

    assert changes["current"]["register_updated_on"] == date(2026, 9, 3)
    assert changes["previous"]["register_updated_on"] == date(2026, 8, 3)
    assert (changes["added_count"], changes["removed_count"]) == (3, 1)
    beta_tracked = [{"employer": "Beta", "kind": "greenhouse", "board": "beta", "open_postings": 2}]
    assert changes["added"] == [
        # Tracked with open postings first, then by name.
        {"kvk_number": "00123456", "organisation": "Beta B.V. / Beta Labs B.V.", "first_seen_on": date(2026, 9, 3),
         "new_sponsor": True, "tracked": beta_tracked},
        {"kvk_number": "00555555", "organisation": "Alpha B.V.", "first_seen_on": date(2026, 9, 3),
         "new_sponsor": True, "tracked": []},
        # Back after a gap: first seen more than a year ago, so not a new sponsor.
        {"kvk_number": "07654321", "organisation": "Returning B.V.", "first_seen_on": date(2025, 1, 3),
         "new_sponsor": False, "tracked": []},
    ]
    assert changes["removed"] == [
        {"kvk_number": "08888888", "organisation": "Gone B.V.",
         "tracked": [{"employer": "Gone", "kind": "greenhouse", "board": "gone", "open_postings": 1}]},
    ]


def test_new_sponsor_is_false_when_the_first_snapshot_already_had_it(conn):
    _snapshot(conn, [("00123456", "Beta B.V.")], "2026-06-03", "2026-06-04")
    _snapshot(conn, [("00000001", "Stays B.V.")], "2026-08-03", "2026-08-04")
    _snapshot(conn, [("00000001", "Stays B.V."), ("00123456", "Beta B.V.")], "2026-09-03", "2026-09-04")

    (added,) = register_changes(conn)["added"]

    # Within a year, but no snapshot before June shows whether it was already listed.
    assert added["first_seen_on"] == date(2026, 6, 3)
    assert added["new_sponsor"] is False


def _archive(copies: dict[str, str | int]) -> httpx.Client:
    """archive.org stand-in: CDX listings plus one raw copy (markup, or an HTTP status) per timestamp.

    The copies up to 2026-04 sit under the old register URL, later ones under the new one.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cdx/search/cdx":
            url = request.url.params["url"]
            assert url in ARCHIVED_URLS
            header = ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"]
            listed = [ts for ts in copies if (ts < "20260501") == (url == ARCHIVED_URLS[0])]
            rows = [["k", ts, url, "text/html", "200", ts, "1"] for ts in listed]
            return httpx.Response(200, json=[header, *rows])
        timestamp = request.url.path.split("/")[2].removesuffix("id_")
        copy = copies[timestamp]
        return httpx.Response(copy) if isinstance(copy, int) else httpx.Response(200, text=copy)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_backfill_stores_archive_copies_behind_the_live_snapshot(conn, monkeypatch):
    monkeypatch.setattr(register, "MIN_ROWS", 3)
    live_id, _ = store_snapshot(conn, (FIXTURES / "ind_register_excerpt.html").read_text())
    archived = (FIXTURES / "ind_register_archive_2023-07.html").read_text()
    copies = {
        "20230728194858": archived,
        "20230804052808": archived,  # same rows, different page bytes
        "20260409134839": (FIXTURES / "ind_register_archive_no_table.html").read_text(),
        "20260410000000": 502,
        "20260926000000": (FIXTURES / "ind_register_excerpt.html").read_text(),  # the live version, archived
    }

    counts = backfill_register(conn, _archive(copies), sleep=lambda s: None)

    assert counts == {"copies": 5, "stored": 1, "duplicate": 2, "too_few_rows": 1, "failed": 1}
    old = conn.execute("SELECT * FROM register_snapshots WHERE id <> %s", (live_id,)).fetchone()
    assert old["captured_at"] == datetime(2023, 7, 28, 19, 48, 58, tzinfo=UTC)
    assert old["register_updated_on"] == date(2023, 7, 7)
    assert "247TailorSteel" in old["raw_html"]
    kvks = {r["kvk_number"] for r in conn.execute("SELECT kvk_number FROM register_entries WHERE snapshot_id = %s", (old["id"],))}
    assert "09163645" in kvks and len(kvks) == 5

    changes = register_changes(conn)
    assert changes["current"]["register_updated_on"] == date(2026, 9, 3)
    assert changes["previous"]["register_updated_on"] == date(2023, 7, 7)
    assert changes["added_count"] == 8 and changes["removed_count"] == 4
    assert all(a["new_sponsor"] for a in changes["added"])


def test_live_sync_still_rejects_a_short_parse(conn):
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text=(FIXTURES / "ind_register_excerpt.html").read_text())
    ))

    with pytest.raises(ValueError, match="only 9 rows"):
        register.sync_register(conn, client)


def test_parse_register_reads_old_update_line():
    _, updated_on = register.parse_register((FIXTURES / "ind_register_archive_no_table.html").read_text())
    entries, old_updated_on = register.parse_register((FIXTURES / "ind_register_archive_2023-07.html").read_text())

    assert updated_on == date(2026, 4, 3)
    assert old_updated_on == date(2023, 7, 7)
    assert [e.kvk_number for e in entries if e.kvk_number.startswith("0")] == ["09163645"]


def test_parse_register_reads_padded_kvks_of_mid_2025():
    entries, updated_on = register.parse_register((FIXTURES / "ind_register_archive_2025-06.html").read_text())

    assert updated_on == date(2025, 6, 3)
    assert [e.kvk_number for e in entries] == ["16051874", "17037842", "83892869"]
    assert entries[2].organisation == "@EasePay B.V."
