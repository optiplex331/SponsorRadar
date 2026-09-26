from __future__ import annotations

import copy

import httpx

from sponsor_radar.collectors import greenhouse
from sponsor_radar.ingest import apply_postings, collect_source, replay, store_raw_capture

from conftest import load_fixture


def _source(conn) -> int:
    return conn.execute(
        "INSERT INTO sources (kind, board, employer_name) VALUES ('greenhouse', 'flowtraders', 'Flow Traders') RETURNING id"
    ).fetchone()["id"]


def _ingest(conn, source_id, payload):
    raw_id = store_raw_capture(conn, source_id, payload)
    apply_postings(conn, source_id, raw_id, greenhouse.parse(payload))
    conn.execute(
        "INSERT INTO fetch_runs (source_id, finished_at, ok, raw_capture_id) VALUES (%s, now(), true, %s)",
        (source_id, raw_id),
    )
    conn.commit()


def _postings(conn):
    return conn.execute(
        "SELECT external_id, title, closed_at IS NULL AS open FROM job_postings ORDER BY external_id"
    ).fetchall()


def test_repeated_fetch_is_idempotent(conn):
    source_id = _source(conn)
    payload = load_fixture("greenhouse_flowtraders.json")

    _ingest(conn, source_id, payload)
    first = _postings(conn)
    _ingest(conn, source_id, payload)

    assert _postings(conn) == first
    assert len(first) == 3
    assert conn.execute("SELECT count(*) AS n FROM raw_captures").fetchone()["n"] == 1


def test_disappearing_posting_closes_and_reopens(conn):
    source_id = _source(conn)
    payload = load_fixture("greenhouse_flowtraders.json")
    gone = str(payload["jobs"][0]["id"])
    shrunk = copy.deepcopy(payload)
    shrunk["jobs"] = shrunk["jobs"][1:]

    _ingest(conn, source_id, payload)
    _ingest(conn, source_id, shrunk)
    assert {p["external_id"]: p["open"] for p in _postings(conn)}[gone] is False

    _ingest(conn, source_id, payload)
    assert all(p["open"] for p in _postings(conn))


def test_replay_rebuilds_postings_from_raw_captures(conn):
    source_id = _source(conn)
    _ingest(conn, source_id, load_fixture("greenhouse_flowtraders.json"))
    before = _postings(conn)

    conn.execute("UPDATE job_postings SET title = 'corrupted'")
    conn.commit()
    replay(conn)

    assert _postings(conn) == before


def test_replay_picks_up_capture_whose_parse_failed(conn, monkeypatch):
    source_id = _source(conn)
    source = conn.execute("SELECT * FROM sources WHERE id = %s", (source_id,)).fetchone()
    payload = load_fixture("greenhouse_flowtraders.json")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))

    with monkeypatch.context() as m:
        m.setattr(greenhouse, "parse", lambda payload: 1 / 0)
        assert not collect_source(conn, client, source).ok
    assert _postings(conn) == []

    assert replay(conn) == 1
    assert len(_postings(conn)) == 3
