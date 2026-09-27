from __future__ import annotations

import csv

import httpx
import pytest

from sponsor_radar import ingest
from sponsor_radar.discover import discover, slug_candidates

from conftest import load_fixture


@pytest.mark.parametrize(
    ("organisation", "expected"),
    [
        ("Adyen N.V.", ["adyen"]),
        ("Flow Traders B.V.", ["flowtraders", "flow-traders", "flow"]),
        ("Acme Holding Netherlands B.V.", ["acme"]),
        ("Café Groep Nederland B.V.", ["cafe"]),
        # Short first token is too generic to try alone; parenthesised parts are dropped.
        ("A.S. Watson (Health &amp; Beauty Continental Europe) B.V.", ["aswatson", "as-watson"]),
        ("The Next Web B.V.", ["nextweb", "next-web", "next"]),
        ("Holding B.V.", []),
    ],
)
def test_slug_candidates(organisation, expected):
    assert slug_candidates(organisation) == expected


def test_discover_writes_hits_for_added_kvks(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "MIN_INTERVAL", dict.fromkeys(ingest.MIN_INTERVAL, 0.0))
    for captured, rows in (("2026-08-04", [("00000001", "Stays B.V.")]),
                           ("2026-09-04", [("00000001", "Stays B.V."), ("00123456", "Flow Traders Holding B.V.")])):
        snapshot_id = conn.execute(
            "INSERT INTO register_snapshots (content_sha256, raw_html, captured_at) VALUES (%s, '', %s) RETURNING id",
            (captured, captured),
        ).fetchone()["id"]
        for kvk, org in rows:
            conn.execute("INSERT INTO register_entries VALUES (%s, %s, %s)", (snapshot_id, kvk, org))
    conn.commit()
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.host == "boards-api.greenhouse.io" and "/boards/flowtraders/" in request.url.path:
            return httpx.Response(200, json=load_fixture("greenhouse_flowtraders.json"))
        if request.url.host == "api.ashbyhq.com" and request.url.path.endswith("/flow"):
            return httpx.Response(500)  # a failing probe is logged and skipped
        return httpx.Response(404)

    out = tmp_path / "hits.csv"
    probed, hits = discover(conn, httpx.Client(transport=httpx.MockTransport(handler)), out)

    assert (probed, hits) == (1, 1)
    assert len(requested) == 9  # three slugs on three boards
    assert list(csv.DictReader(out.open())) == [{
        "kvk_number": "00123456", "organisation": "Flow Traders Holding B.V.", "kind": "greenhouse",
        "board": "flowtraders", "nl_postings": "2", "total_postings": "3",
    }]
