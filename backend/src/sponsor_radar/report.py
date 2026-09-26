"""Coverage report: does the seed list produce enough junior NL postings?"""

from __future__ import annotations

from collections import Counter

import psycopg

from .signals import is_tech_role, seniority


def build_report(conn: psycopg.Connection, days: int = 7) -> str:
    rows = conn.execute(
        """
        SELECT p.title, p.location, p.url, p.published_at, p.first_seen_at, s.employer_name,
               coalesce(m.status, 'unmatched') AS match_status,
               p.published_at > now() - make_interval(days => %s) AS recent
        FROM job_postings p
        JOIN sources s ON s.id = p.source_id
        LEFT JOIN sponsor_matches m ON m.source_id = s.id
        WHERE p.closed_at IS NULL AND p.in_netherlands
        """,
        (days,),
    ).fetchall()
    tech = [r | {"seniority": seniority(r["title"])} for r in rows if is_tech_role(r["title"])]
    entry_level = [r for r in tech if r["seniority"] in ("intern", "junior")]
    sponsored = [r for r in entry_level if r["match_status"] != "unmatched"]

    lines = [
        f"Open NL postings: {len(rows)}; tech: {len(tech)}",
        "Tech by seniority: " + ", ".join(f"{k}={v}" for k, v in Counter(r["seniority"] for r in tech).most_common()),
        "Tech by sponsor match: " + ", ".join(f"{k}={v}" for k, v in Counter(r["match_status"] for r in tech).most_common()),
        f"Intern/junior tech from matched sponsors: {len(sponsored)} "
        f"(published in last {days} days: {sum(1 for r in sponsored if r['recent'])})",
        f"Unspecified-seniority tech from matched sponsors, last {days} days: "
        + str(sum(1 for r in tech if r["seniority"] == "unspecified" and r["match_status"] != "unmatched" and r["recent"])),
        "",
    ]
    for r in sorted(sponsored, key=lambda r: r["published_at"] or r["first_seen_at"], reverse=True):
        lines.append(f"[{r['match_status']}] {r['employer_name']} | {r['title']} | {r['location']} | {r['url']}")
    return "\n".join(lines)
