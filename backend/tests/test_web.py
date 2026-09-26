from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

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
                                  raw_capture_id, seniority, is_tech, dutch_required, min_years, closed_at)
        VALUES (%s, %s, %s, 'https://example.com', 'Amsterdam', %s, 'secret description', %s, 'junior', %s, false, 2, %s)
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
