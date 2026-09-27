from __future__ import annotations

from . import Posting, html_to_text, mentions_netherlands, parse_time, salary_amounts

# Recruitee's salary.period vocabulary seen in raw captures: month, year, hour, or null.
# A null period is left unset rather than guessed from the amount.
PERIODS = {"month": "month", "year": "year", "hour": "hour"}


def board_url(board: str) -> str:
    return f"https://{board}.recruitee.com/api/offers/"


def parse_salary(salary: dict | None) -> dict:
    salary = salary or {}
    low, high = salary_amounts(salary.get("min"), salary.get("max"))
    if low is None and high is None:
        return {}
    period = PERIODS.get(salary.get("period"))
    if period == "year" and (high or low) < 1000:
        # Some employers type a yearly range in thousands ("115.00" for 115k); no yearly salary is below 1,000.
        low, high = (v * 1000 if v is not None else None for v in (low, high))
    return {"salary_min": low, "salary_max": high, "salary_currency": salary.get("currency"),
            "salary_period": period}


def parse(payload: dict) -> list[Posting]:
    postings = []
    for offer in payload.get("offers", []):
        countries = {loc.get("country_code") for loc in offer.get("locations", [])} | {offer.get("country_code")}
        description = html_to_text(offer.get("description")) + "\n\n" + html_to_text(offer.get("requirements"))
        postings.append(Posting(
            external_id=str(offer["id"]),
            title=offer["title"].strip(),
            url=offer["careers_url"],
            location=offer.get("location") or "",
            in_netherlands="NL" in countries or mentions_netherlands(offer.get("location")),
            department=offer.get("department"),
            description=description.strip(),
            published_at=parse_time(offer.get("published_at") or offer.get("created_at")),
            **parse_salary(offer.get("salary")),
        ))
    return postings
