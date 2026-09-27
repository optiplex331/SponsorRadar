from __future__ import annotations

from . import Posting, mentions_netherlands, parse_time, salary_amounts

INTERVALS = {"1 YEAR": "year", "1 MONTH": "month", "1 HOUR": "hour"}


def board_url(board: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"


def parse_salary(compensation: dict | None) -> dict:
    """One salary range from Ashby's compensation tiers.

    Tiers are usually per location ("US Premium", "All other US locations"). EUR components win because the
    posting is Dutch and the KM check compares in EUR; within the chosen currency and interval the range spans
    all tiers. Equity, commission, and components without an amount are ignored.
    """
    compensation = compensation or {}
    components = [c for tier in compensation.get("compensationTiers") or [] for c in tier.get("components") or []]
    components = components or compensation.get("summaryComponents") or []
    salaries = []
    for c in components:
        period = INTERVALS.get(c.get("interval"))
        low, high = salary_amounts(c.get("minValue"), c.get("maxValue"))
        if c.get("compensationType") == "Salary" and period and (low is not None or high is not None):
            salaries.append((c.get("currencyCode"), period, low, high))
    if not salaries:
        return {}
    currency, period = next(((cur, per) for cur, per, *_ in salaries if cur == "EUR"), salaries[0][:2])
    chosen = [s for s in salaries if s[0] == currency and s[1] == period]
    lows = [s[2] for s in chosen if s[2] is not None]
    highs = [s[3] for s in chosen if s[3] is not None]
    return {"salary_min": min(lows) if lows else None, "salary_max": max(highs) if highs else None,
            "salary_currency": currency, "salary_period": period}


def parse(payload: dict) -> list[Posting]:
    postings = []
    for job in payload.get("jobs", []):
        if not job.get("isListed", True):
            continue
        address = ((job.get("address") or {}).get("postalAddress") or {})
        secondary = " ".join(s.get("location") or "" for s in job.get("secondaryLocations", []))
        location = job.get("location") or ""
        postings.append(Posting(
            external_id=job["id"],
            title=job["title"].strip(),
            url=job["jobUrl"],
            location=location,
            in_netherlands=mentions_netherlands(location, address.get("addressCountry"), secondary),
            department=job.get("department"),
            description=(job.get("descriptionPlain") or "").strip(),
            published_at=parse_time(job.get("publishedAt")),
            **parse_salary(job.get("compensation")),
        ))
    return postings
