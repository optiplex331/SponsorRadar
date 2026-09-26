"""Title rules for seniority and technical roles.

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
