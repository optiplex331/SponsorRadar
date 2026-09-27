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


def test_recruitee_salary_periods():
    postings = {p.external_id: p for p in recruitee.parse(load_fixture("recruitee_northwave.json"))}

    monthly, hourly, yearly, empty = postings["2756160"], postings["2738715"], postings["2701927"], postings["1733171"]
    assert (monthly.salary_min, monthly.salary_max, monthly.salary_currency, monthly.salary_period) == (
        2625, 4000, "EUR", "month")
    assert (hourly.salary_min, hourly.salary_max, hourly.salary_period) == (16, 17, "hour")
    assert (yearly.salary_min, yearly.salary_max, yearly.salary_period) == (47000, 60000, "year")
    # A period without amounts is no salary.
    assert (empty.salary_min, empty.salary_max, empty.salary_currency, empty.salary_period) == (None, None, None, None)


def test_ashby_compensation():
    sentry = {p.title: p for p in ashby.parse(load_fixture("ashby_sentry.json"))}
    yearly, monthly = sentry["Sales Engineer"], sentry["Software Engineer, Intern (Summer 2027)"]
    assert (yearly.salary_min, yearly.salary_max, yearly.salary_currency, yearly.salary_period) == (
        91000, 124000, "EUR", "year")
    assert (monthly.salary_min, monthly.salary_max, monthly.salary_period) == (2800, 3285, "month")

    # Only US tiers: the range spans both tiers and keeps its currency, so the page shows no EUR comparison.
    [clickhouse] = ashby.parse(load_fixture("ashby_clickhouse.json"))
    assert (clickhouse.salary_min, clickhouse.salary_max, clickhouse.salary_currency, clickhouse.salary_period) == (
        195000, 260000, "USD", "year")

    # Boards without compensation data and Greenhouse boards leave salary empty.
    assert all(p.salary_min is None for p in ashby.parse(load_fixture("ashby_mollie.json")))
    assert all(p.salary_period is None for p in greenhouse.parse(load_fixture("greenhouse_flowtraders.json")))


def test_ashby_board_url_requests_compensation():
    assert ashby.board_url("sentry").endswith("/sentry?includeCompensation=true")


def test_recruitee_yearly_salary_in_thousands():
    # Seen live on deephealth.recruitee.com: 115k-130k a year entered as "115.00" and "130.00".
    assert recruitee.parse_salary({"min": "115.00", "max": "130.00", "period": "year", "currency": "EUR"}) == {
        "salary_min": 115000, "salary_max": 130000, "salary_currency": "EUR", "salary_period": "year"}
    assert recruitee.parse_salary({"min": "400", "max": None, "period": "month", "currency": "EUR"})["salary_min"] == 400
