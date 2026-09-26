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


def module_for(kind: str) -> ModuleType:
    from . import ashby, greenhouse, recruitee

    return {"greenhouse": greenhouse, "ashby": ashby, "recruitee": recruitee}[kind]
