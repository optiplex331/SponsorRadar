from __future__ import annotations

import pytest

from sponsor_radar.collectors import ashby, greenhouse, recruitee
from sponsor_radar.register import parse_register

from conftest import FIXTURES, load_fixture


@pytest.mark.parametrize(
    ("collector", "fixture", "expected_nl"),
    [
        # Multi-office jobs count as Netherlands when any office is there.
        (greenhouse, "greenhouse_flowtraders.json", [True, True, False]),
        (ashby, "ashby_mollie.json", [True, False]),
        (recruitee, "recruitee_fastned.json", [True, True, False]),
    ],
)
def test_parses_real_board_payloads(collector, fixture, expected_nl):
    postings = collector.parse(load_fixture(fixture))

    assert [p.in_netherlands for p in postings] == expected_nl
    for p in postings:
        assert p.external_id and p.title and p.url.startswith("https://")
        assert p.published_at is not None and p.published_at.tzinfo is not None
        assert p.description and "<" not in p.description


def test_parses_register_rows_and_update_date():
    entries, updated_on = parse_register((FIXTURES / "ind_register_excerpt.html").read_text())

    assert len(entries) == 9
    assert entries[0].kvk_number == "16051874"
    assert all(len(e.kvk_number) == 8 for e in entries)
    assert "A&S System Integrators B.V." in {e.organisation for e in entries}
    assert updated_on.isoformat() == "2026-09-03"
