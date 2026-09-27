"""Parsers for public ATS job-board APIs.

Each collector module exposes `board_url(board)` and `parse(payload)`. Fetching
and storage live in `ingest`, so every source gets the same raw-capture and
replay behavior.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from types import ModuleType
from typing import Literal

SalaryPeriod = Literal["year", "month", "hour"]


@dataclass(frozen=True)
class Posting:
    external_id: str
    title: str
    url: str
    location: str
    in_netherlands: bool
    department: str | None
    description: str
    published_at: datetime | None
    # Structured salary as the ATS states it; only Recruitee and Ashby expose one.
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None


NL_PLACES = (
    "netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "the hague", "den haag",
    "eindhoven", "maastricht", "delft", "leiden", "groningen", "haarlem", "hilversum",
    "amstelveen", "nijmegen", "enschede", "arnhem", "breda", "tilburg", "zwolle", "hoofddorp",
)


def mentions_netherlands(*texts: str | None) -> bool:
    joined = " ".join(t for t in texts if t).lower()
    return bool(re.search(r"\b(?:%s)\b" % "|".join(NL_PLACES), joined))


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(markup: str | None) -> str:
    if not markup:
        return ""
    extractor = _TextExtractor()
    # Greenhouse double-escapes its content; unescape once before parsing tags.
    extractor.feed(html.unescape(markup) if "&lt;" in markup else markup)
    text = "".join(extractor.parts)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\xa0]+", " ", text)).strip()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace(" UTC", "+00:00"))


def salary_amounts(low, high) -> tuple[float | None, float | None]:
    """Positive amounts as floats; zero or missing means not stated. A single value is kept on its own side."""
    def amount(value) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    low, high = amount(low), amount(high)
    if low is not None and high is not None and low > high:
        low, high = high, low
    return low, high


def module_for(kind: str) -> ModuleType:
    from . import ashby, greenhouse, recruitee

    return {"greenhouse": greenhouse, "ashby": ashby, "recruitee": recruitee}[kind]
