from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from sponsor_radar.web import create_app

OLDER = [("01234567", "Adyen N.V."), ("11111111", "Transport Hollanders B.V.")]
LATEST = OLDER + [
    ("22222222", "ANS Group B.V."),
    ("33333333", "Boodschappen Technologies B.V."),
    *[(f"9{n:07d}", f"Capstone Consulting {n} B.V.") for n in range(25)],
]


@pytest.fixture
def client(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["SPONSOR_RADAR_TEST_DATABASE_URL"])
    (tmp_path / "index.html").write_text("<!doctype html><title>NL Sponsor Radar</title>")
    _snapshot(conn, "older", "2025-06-02", "2025-06-05", OLDER)
    _snapshot(conn, "latest", "2026-09-03", "2026-09-05", LATEST)
    conn.commit()
    return TestClient(create_app(tmp_path))


def _snapshot(conn, sha, updated_on, captured_at, entries):
    snapshot_id = conn.execute(
        "INSERT INTO register_snapshots (content_sha256, register_updated_on, raw_html, captured_at) "
        "VALUES (%s, %s, '', %s) RETURNING id",
        (sha, updated_on, captured_at),
    ).fetchone()["id"]
    for kvk, org in entries:
        conn.execute("INSERT INTO register_entries VALUES (%s, %s, %s)", (snapshot_id, kvk, org))
    return snapshot_id


def _search(client, q):
    response = client.get("/api/sponsors", params={"q": q})
    assert response.status_code == 200
    return response.json()


def _orgs(client, q):
    return [r["organisation"] for r in _search(client, q)["results"]]


def test_kvk_with_leading_zero(client):
    for q in ("01234567", "001234567", " 0123 4567 "):
        (row,) = _search(client, q)["results"]
        assert (row["kvk_number"], row["organisation"]) == ("01234567", "Adyen N.V.")
    # A dropped leading zero is not a KvK number, and no name has that token.
    assert _orgs(client, "1234567") == []


def test_name_with_legal_suffix(client):
    assert _orgs(client, "Adyen B.V.") == ["Adyen N.V."]
    assert _orgs(client, "adyen holding") == ["Adyen N.V."]
    assert _orgs(client, "ady") == ["Adyen N.V."]


def test_whole_tokens_only(client):
    assert _orgs(client, "Ans") == ["ANS Group B.V."]
    assert _orgs(client, "ollanders") == []
    assert _orgs(client, "Transport Hol") == ["Transport Hollanders B.V."]


def test_empty_result(client):
    assert _search(client, "Nonexistent Employer") == {"results": [], "more": False}


def test_seed_brand_resolves_to_its_kvk(client, conn):
    conn.execute(
        "INSERT INTO sources (kind, board, employer_name, kvk_number) VALUES ('recruitee', 'picnic', 'Picnic', '33333333')"
    )
    conn.commit()

    (row,) = _search(client, "picnic")["results"]

    assert (row["kvk_number"], row["organisation"], row["brand"]) == ("33333333", "Boodschappen Technologies B.V.", "Picnic")


def test_query_needs_two_characters(client):
    assert client.get("/api/sponsors", params={"q": " a "}).status_code == 400
    assert client.get("/api/sponsors").status_code == 400
    assert client.get("/api/sponsors", params={"q": "ad"}).status_code == 200


def test_at_most_twenty_results(client):
    body = _search(client, "capstone")

    assert len(body["results"]) == 20
    assert body["more"] is True


def test_result_details(client, conn):
    source_id = conn.execute(
        "INSERT INTO sources (kind, board, employer_name) VALUES ('greenhouse', 'adyen', 'Adyen') RETURNING id"
    ).fetchone()["id"]
    snapshot_id = conn.execute("SELECT id FROM register_snapshots WHERE content_sha256 = 'latest'").fetchone()["id"]
    conn.execute(
        "INSERT INTO sponsor_matches (source_id, snapshot_id, status, kvk_numbers, organisations) "
        "VALUES (%s, %s, 'name_inferred', '{01234567}', '{Adyen N.V.}')",
        (source_id, snapshot_id),
    )
    for external_id, seniority, dutch in [("a", "junior", False), ("b", "senior", False), ("c", "junior", True)]:
        raw_id = conn.execute(
            "INSERT INTO raw_captures (source_id, content_sha256, payload) VALUES (%s, %s, '{}') RETURNING id",
            (source_id, external_id),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO job_postings (source_id, external_id, title, url, location, in_netherlands, description,
                                      raw_capture_id, seniority, is_tech, dutch_required)
            VALUES (%s, %s, 'Engineer', 'https://example.com', 'Amsterdam', true, '', %s, %s, true, %s)
            """,
            (source_id, external_id, raw_id, seniority, dutch),
        )
    conn.commit()

    response = client.get("/api/sponsors", params={"q": "adyen"})
    (adyen,) = response.json()["results"]
    (ans,) = _search(client, "ans")["results"]

    assert response.headers["cache-control"] == "public, max-age=300"
    assert (adyen["first_seen_on"], adyen["before_history"]) == ("2025-06-02", True)
    assert adyen["tracked"] == [{"employer": "Adyen", "kind": "greenhouse", "board": "adyen", "open_postings": 1}]
    assert (ans["first_seen_on"], ans["before_history"], ans["tracked"]) == ("2026-09-03", False, [])


def test_newer_snapshot_replaces_index(client, conn):
    assert _orgs(client, "ans") == ["ANS Group B.V."]
    _snapshot(conn, "newest", "2026-10-01", "2026-10-02", [("22222222", "ANS Nederland B.V.")])
    conn.commit()

    assert _orgs(client, "ans") == ["ANS Nederland B.V."]
