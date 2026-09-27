from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from sponsor_radar import db
from sponsor_radar.web import create_app


@pytest.fixture
def client(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["SPONSOR_RADAR_TEST_DATABASE_URL"])
    (tmp_path / "index.html").write_text("<!doctype html><title>NL Sponsor Radar</title>")
    return TestClient(create_app(tmp_path))


def _posting(conn, source_id, external_id, **overrides):
    raw_id = conn.execute(
        "INSERT INTO raw_captures (source_id, content_sha256, payload) VALUES (%s, %s, '{}') RETURNING id",
        (source_id, external_id),
    ).fetchone()["id"]
    values = {"in_netherlands": True, "is_tech": True, "closed_at": None, **overrides}
    conn.execute(
        """
        INSERT INTO job_postings (source_id, external_id, title, url, location, in_netherlands, description,
                                  raw_capture_id, seniority, is_tech, dutch_required, min_years, closed_at,
                                  sponsorship_stance, salary_min, salary_max, salary_currency, salary_period)
        VALUES (%s, %s, %s, 'https://example.com', 'Amsterdam', %s, 'secret description', %s, 'junior', %s, false, 2, %s,
                'refuses_relocation', 4000, 5500, 'EUR', 'month')
        """,
        (source_id, external_id, f"Engineer {external_id}", values["in_netherlands"], raw_id, values["is_tech"],
         values["closed_at"]),
    )


def test_postings_lists_only_open_nl_tech(client, conn):
    source_id = conn.execute(
        "INSERT INTO sources (kind, board, employer_name) VALUES ('greenhouse', 'acme', 'Acme') RETURNING id"
    ).fetchone()["id"]
    _posting(conn, source_id, "open")
    _posting(conn, source_id, "closed", closed_at="2026-01-01")
    _posting(conn, source_id, "abroad", in_netherlands=False)
    _posting(conn, source_id, "sales", is_tech=False)
    conn.commit()

    rows = client.get("/api/postings").json()

    assert [r["title"] for r in rows] == ["Engineer open"]
    assert rows[0]["employer"] == "Acme"
    assert rows[0]["match_status"] == "unmatched"
    assert rows[0]["register_organisations"] == []
    assert rows[0]["sponsorship_stance"] == "refuses_relocation"
    assert (rows[0]["salary_min"], rows[0]["salary_max"], rows[0]["salary_currency"], rows[0]["salary_period"]) == (
        4000, 5500, "EUR", "month")
    assert "description" not in rows[0]


def test_status_on_empty_database(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "last_collect_at": None, "sources_ok": 0, "sources_total": 0, "register_updated_on": None, "postings": 0,
    }


def test_index_counts_page_views(client, conn):
    assert client.get("/healthz").status_code == 200
    assert "NL Sponsor Radar" in client.get("/").text
    client.get("/?seniority=junior")

    assert conn.execute("SELECT sum(views) AS n FROM page_views").fetchone()["n"] == 2


def test_postings_carry_delisted_date(client, conn):
    source_id = conn.execute(
        "INSERT INTO sources (kind, board, employer_name) VALUES ('greenhouse', 'acme', 'Acme') RETURNING id"
    ).fetchone()["id"]
    snapshot_id = conn.execute(
        "INSERT INTO register_snapshots (content_sha256, register_updated_on, raw_html) VALUES ('a', '2026-09-03', '') RETURNING id"
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO sponsor_matches (source_id, snapshot_id, status, kvk_numbers, organisations, delisted_on) "
        "VALUES (%s, %s, 'unmatched', '{00123456}', '{Acme B.V.}', '2026-09-03')",
        (source_id, snapshot_id),
    )
    _posting(conn, source_id, "open")
    conn.commit()

    (row,) = client.get("/api/postings").json()

    assert row["match_status"] == "unmatched"
    assert row["delisted_on"] == "2026-09-03"


def test_register_changes_with_one_snapshot(client, conn):
    conn.execute(
        "INSERT INTO register_snapshots (content_sha256, register_updated_on, raw_html) VALUES ('a', '2026-09-03', '')"
    )
    conn.commit()

    response = client.get("/api/register-changes")
    body = response.json()

    assert response.headers["cache-control"] == "public, max-age=300"
    assert body["current"]["register_updated_on"] == "2026-09-03"
    assert body["previous"] is None
    assert (body["added_count"], body["removed_count"], body["added"], body["removed"]) == (0, 0, [], [])


@pytest.fixture
def site(conn, tmp_path, monkeypatch):
    """An app over a small dist and a hand-driven clock."""
    monkeypatch.setenv("DATABASE_URL", os.environ["SPONSOR_RADAR_TEST_DATABASE_URL"])
    (tmp_path / "index.html").write_text("<!doctype html><title>NL Sponsor Radar</title>")
    (tmp_path / "404.html").write_text("<!doctype html><title>Page not found</title>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    now = [1000.0]
    client = TestClient(create_app(tmp_path, clock=lambda: now[0]), raise_server_exceptions=False)
    return client, now


def _no_database(*args, **kwargs):
    raise psycopg.OperationalError("database down")


def test_security_headers_on_every_response(site):
    client, _ = site
    for path in ("/", "/api/status", "/assets/index-abc123.js", "/nope"):
        headers = client.get(path).headers
        assert "frame-ancestors 'none'" in headers["content-security-policy"], path
        assert headers["strict-transport-security"] == "max-age=31536000", path
        assert headers["x-content-type-options"] == "nosniff", path
        assert headers["referrer-policy"] == "strict-origin-when-cross-origin", path
        assert headers["cross-origin-opener-policy"] == "same-origin", path


def test_cache_control_per_path_class(site):
    client, _ = site

    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/index.html").headers["cache-control"] == "no-cache"
    assert client.get("/assets/index-abc123.js").headers["cache-control"] == "public, max-age=31536000, immutable"
    assert client.get("/favicon.svg").headers["cache-control"] == "public, max-age=3600"
    assert client.get("/api/status").headers["cache-control"] == "public, max-age=300"
    missing = client.get("/assets/missing.js")
    assert missing.status_code == 404
    assert "immutable" not in missing.headers.get("cache-control", "")


def test_api_cache_skips_database_within_ttl(site, conn, monkeypatch):
    client, now = site
    source_id = conn.execute(
        "INSERT INTO sources (kind, board, employer_name) VALUES ('greenhouse', 'acme', 'Acme') RETURNING id"
    ).fetchone()["id"]
    first = client.get("/api/status").json()
    _posting(conn, source_id, "open")
    conn.commit()

    with monkeypatch.context() as m:
        m.setattr(db, "connect", _no_database)
        now[0] += 299
        assert client.get("/api/status").json() == first

    now[0] += 2
    assert client.get("/api/status").json()["postings"] == 1


def test_api_cache_never_stores_a_failure(site, monkeypatch):
    client, _ = site
    with monkeypatch.context() as m:
        m.setattr(db, "connect", _no_database)
        assert client.get("/api/postings").status_code == 500

    response = client.get("/api/postings")
    assert (response.status_code, response.json()) == (200, [])


def test_not_found_is_html_for_pages_and_json_for_api(site):
    client, _ = site

    page = client.get("/nope")
    assert (page.status_code, page.headers["content-type"].split(";")[0]) == (404, "text/html")
    assert "Page not found" in page.text
    api = client.get("/api/nope")
    assert (api.status_code, api.json()) == (404, {"detail": "Not Found"})


def test_head_index_counts_no_view(site, conn):
    client, _ = site

    assert client.head("/").status_code == 200
    assert conn.execute("SELECT count(*) AS n FROM page_views").fetchone()["n"] == 0


def test_plain_http_redirects_to_canonical_https(site):
    client, _ = site

    response = client.get(
        "/api/postings?city=Delft", headers={"X-Forwarded-Proto": "http", "Host": "evil.example"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "https://sponsorradar.halligalli.games/api/postings?city=Delft"
    assert client.get("/", headers={"X-Forwarded-Proto": "https"}).status_code == 200
