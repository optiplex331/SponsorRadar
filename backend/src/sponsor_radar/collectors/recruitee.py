from __future__ import annotations

from . import Posting, html_to_text, mentions_netherlands, parse_time


def board_url(board: str) -> str:
    return f"https://{board}.recruitee.com/api/offers/"


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
        ))
    return postings
