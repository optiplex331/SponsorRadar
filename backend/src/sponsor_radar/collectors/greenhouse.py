from __future__ import annotations

from . import Posting, html_to_text, mentions_netherlands, parse_time


def board_url(board: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


def parse(payload: dict) -> list[Posting]:
    postings = []
    for job in payload.get("jobs", []):
        location = (job.get("location") or {}).get("name") or ""
        offices = " ".join(o.get("location") or o.get("name") or "" for o in job.get("offices", []))
        departments = [d["name"] for d in job.get("departments", []) if d.get("name")]
        postings.append(Posting(
            external_id=str(job["id"]),
            title=job["title"].strip(),
            url=job["absolute_url"],
            location=location,
            in_netherlands=mentions_netherlands(location, offices),
            department=departments[0] if departments else None,
            description=html_to_text(job.get("content")),
            published_at=parse_time(job.get("first_published") or job.get("updated_at")),
        ))
    return postings
