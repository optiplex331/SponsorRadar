"""Rules for seniority, technical roles, Dutch requirement, and years of experience.

This is the rules baseline. Phase 3 measures it against a labeled set before
anything smarter replaces it.
"""

from __future__ import annotations

import re
from typing import Literal

Seniority = Literal["intern", "junior", "senior", "unspecified"]

_INTERN = re.compile(r"\b(intern|internship|stage|stagiair|werkstudent|working student|thesis)\b", re.I)
_JUNIOR = re.compile(r"\b(junior|jr\.?|graduate|entry[- ]level|trainee|starter|new grad)\b", re.I)
_SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|head|director|manager|vp|chief|architect|expert)\b", re.I)
_TECH = re.compile(
    r"\b(engineer\w*|developer|software|back[- ]?end|front[- ]?end|full[- ]?stack|devops|sre|platform|"
    r"data|machine learning|ml|ai|security|cloud|infrastructure|qa|test automation|mobile|ios|android|"
    r"python|java|golang|kotlin|typescript)\b",
    re.I,
)


def seniority(title: str) -> Seniority:
    # Check junior markers first: "Junior Engineer, Platform Lead team" is still junior.
    if _INTERN.search(title):
        return "intern"
    if _JUNIOR.search(title):
        return "junior"
    if _SENIOR.search(title):
        return "senior"
    return "unspecified"


def is_tech_role(title: str) -> bool:
    return bool(_TECH.search(title))


# Dutch requirement: precision first, because a wrong True hides the posting by default.
# A sentence counts only when it names the Dutch language next to an ability word and says nothing
# that softens it ("a plus", "or English", "not required", "willing to learn").
# "Dutch" must be used as the language: followed by punctuation, a conjunction, or a language word, so
# "Dutch market" or "Dutch tax law" never count.
_DUTCH = re.compile(
    r"\b(dutch|nederlands|nederlandstalig)\b(?=\s*(?:$|[,&/()\-:+]|(?:and|en|én|is|are|at|as|to|both|als|"
    r"language|speak\w*|spoken|written|fluen\w*|native|skills?|proficien\w*|level|required|essential|"
    r"mandatory|a must|vereist|essentieel|vloeiend|mondeling|schriftelijk|[abc][12])\b))",
    re.I,
)
_ABILITY = re.compile(
    r"\b(fluen\w*|native|speak\w*|spoken|written|command|proficien\w*|language|mother tongue|"
    r"communicat\w*|knowledge|level|vloeiend|spreek\w*|spreekt|schrijf\w*|schrijft|beheers\w*|"
    r"mondeling|schriftelijk|communiceer\w*|communicatie\w*|taal|moedertaal|essentieel|vereist|must)\b",
    re.I,
)
_SOFTENER = re.compile(
    r"\b(plus|nice[- ]to[- ]have|advantage\w*|bonus|prefer\w*|asset|benefit\w*|helpful|welcome|optional|"
    r"desirable|ideally|not|no|niet|geen|willing\w*|learn\w*|lessons?|classes|course|leren|cursus|bereid\w*|"
    r"pré|pluspunt|meegenomen|or(?! higher| above| better)|and/or|en/of|of engels|engels of)\b|\bpre\b",
    re.I,
)
_SENTENCE = re.compile(r"[.;!?\n•]+")
_NL_STOPWORDS = {"de", "het", "een", "van", "en", "je", "jij", "wij", "voor", "met", "zijn", "ons", "onze",
                 "bij", "naar", "ook", "niet", "wat", "wordt", "jouw"}
_EN_STOPWORDS = {"the", "and", "of", "to", "a", "in", "you", "with", "for", "our", "is", "are", "we", "your"}


def is_mostly_dutch(text: str) -> bool:
    """Dutch stopwords outnumber English ones clearly. Bilingual postings land near 0.5 and stay False."""
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    nl = sum(w in _NL_STOPWORDS for w in words)
    en = sum(w in _EN_STOPWORDS for w in words)
    return nl >= 15 and nl / (nl + en) >= 0.6


def dutch_required(description: str, title: str = "") -> bool:
    if is_mostly_dutch(f"{title}\n{description}"):
        return True
    for sentence in _SENTENCE.split(f"{title}\n{description}"):
        if _DUTCH.search(sentence) and _ABILITY.search(sentence) and not _SOFTENER.search(sentence):
            return True
    return False


_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                 "ten": 10, "een": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6, "zeven": 7, "acht": 8}
_N = r"(\d{1,2}|%s)" % "|".join(_NUMBER_WORDS)
_YEARS = r"(?:years?|yrs?|jaar|jaren)"
_YEAR_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        # 2-4 years, 2 to 4 years, 3 tot 5 jaar: lower bound
        rf"\b{_N}\s*\+?\s*(?:-|–|to|tot)\s*\d{{1,2}}\s*\+?\s*{_YEARS}\b",
        # 3+ years, 3+ jaar
        rf"\b{_N}\s*\+\s*{_YEARS}\b",
        # at least 2 years, minimum of 3 years, minimaal 3 jaar
        rf"\b(?:at least|minimum(?: of)?|min\.?|minimaal|minstens|ten ?minste)\s+{_N}\s*{_YEARS}\b",
        # 3 years of experience, 3 years' professional experience, 3 jaar werkervaring
        rf"\b{_N}\s*{_YEARS}'?\s+(?:of\s+)?(?:\w+\s+){{0,3}}?(?:experience|ervaring|werkervaring)\b",
    )
]


def min_years(description: str) -> int | None:
    """Smallest explicit years-of-experience requirement, or None.

    The smallest mention wins ("5+ years overall, 2+ with Go" gives 2): overestimating hides a posting
    behind the years filter, underestimating only shows one too many. Values above 15 are not experience.
    """
    found = []
    for pattern in _YEAR_PATTERNS:
        for m in pattern.finditer(description):
            raw = m.group(1).lower()
            n = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
            if n <= 15:
                found.append(n)
    return min(found) if found else None
