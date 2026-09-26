from __future__ import annotations

from . import Posting, mentions_netherlands, parse_time


def board_url(board: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{board}"


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
        ))
    return postings
