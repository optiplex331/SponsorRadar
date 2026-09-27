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


# Sponsorship stance: explicit phrases only, judged per sentence so a negation elsewhere never flips a phrase.
# Precedence refuses_visa > offers > refuses_relocation > silent: one refusal outweighs generic perks text.
Stance = Literal["offers", "refuses_visa", "refuses_relocation", "silent"]

_WHERE = r"(?:the\s+)?(?:netherlands|nl|eu|eea|european union|europe|here)\b"
_IN_NL = r"in\s+(?:the\s+)?netherlands\b"
_NEGATOR = (r"(?<!or )\b(?:no|not|unable to|cannot|can ?not|can['’]t|won['’]t|will not|don['’]t|do not|does not|doesn['’]t|"
            r"are not able to|aren['’]t able to|is not|isn['’]t|are not|aren['’]t)")
_REFUSES_VISA = re.compile(
    "|".join((
        # "we do not offer visa sponsorship", "unable to sponsor", "(no sponsorship)"; "relocation sponsorship" is relocation
        rf"{_NEGATOR}(?:\s+\w+){{0,4}}?\s+(?<!relocation )(?:visa\s+|immigration\s+|work permit\s+)?sponsor(?:ship|ing|ed)?s?\b",
        rf"{_NEGATOR}(?:\s+\w+){{0,3}}?\s+(?:support|assist with|help with)\s+(?:\w+\s+)?(?:visa|work permit|residency)",
        r"\b(?:visa\s+)?sponsorship\s+(?:is\s+|will\s+)?(?:\w+\s+)?(?:not|un)\s*(?:be\s+)?(?:available|provided|offered|possible)",
        r"\bwithout\s+(?:the\s+need\s+for\s+|requiring\s+|needing\s+|any\s+)?(?:visa\s+|company\s+)?sponsorship",
        # "must already have the right to work in the Netherlands", "with the right to work in the EU"
        rf"\b(?:must|need to|should|required to|with|who)\s+(?:already\s+)?(?:have|hold|possess|be granted)?\s*"
        rf"(?:the\s+|a\s+|valid\s+|full\s+|legal\s+)*(?:right|authori[sz]ation|permission|permit|eligibility)\s+to\s+work\s+"
        rf"(?:in\s+|within\s+)?{_WHERE}",
        rf"\b(?:allowed|authori[sz]ed|eligible|permitted)\s+to\s+work\s+(?:in|within)\s+{_WHERE}",
        r"\b(?:have|hold|holds|possess)\s+an?\s+(?:valid|existing)\s+(?:\w+\s+){0,3}?"
        r"(?:work\s+permit|work\s+visa|residence\s+permit|visa\s+to\s+work)",
        r"\bvalid\s+(?:eu\s+|eea\s+|dutch\s+)?work\s+permit\s+(?:is\s+)?(?:required|mandatory|needed)",
        r"\b(?:required|mandatory):?\s+(?:a\s+)?valid\s+(?:eu\s+|eea\s+|dutch\s+)?work\s+permit",
        r"\bgeen\b(?:\s+\w+){0,4}?\s+(?:visum|visa)?sponsor\w*",
        r"\bsponsor\w*\s+(?:\w+\s+){0,4}?niet\s+(?:beschikbaar|mogelijk)",
        r"\bwerkvergunning\s+(?:is\s+)?(?:vereist|verplicht|noodzakelijk)",
        r"\bgeen\s+(?:visum|visa|werkvergunning)(?:aanvra\w+)?\b",
        r"\bgemachtigd\s+(?:zijn\s+)?om\s+in\s+nederland\s+te\s+werken",
    )),
    re.I,
)
# A refusal limited to some nationalities ("citizenship from Russia") is not a refusal for everyone.
_NATIONALITY = re.compile(r"\b(?:citizenship|citizens|nationals)\s+(?:from|of)\b|\bcertain\s+(?:nations|nationalities|countries)", re.I)
_OFFERS = re.compile(
    "|".join((
        r"\bvisa\s+sponsorship\s+(?:is\s+)?(?:available|provided|offered|possible)",
        r"\b(?:offer|offers|offering|provide|provides|providing)\s+(?:\w+\s+){0,3}?visa\s+(?:sponsorship|support|assistance)",
        r"\bwe\s+(?:can\s+|will\s+|do\s+|are able to\s+)?sponsor\s+(?:your\s+|a\s+|the\s+)?(?:visa|work permit|highly skilled|"
        r"kennismigrant|relocation|you\b|candidates|international)",
        r"\bwe(?:['’]ll)?\s+(?:will\s+|can\s+|also\s+)?(?:help|assist|support|provide\s+(?:full\s+)?support)\b[^.]{0,40}?"
        r"\b(?:visa|relocat\w*|immigration)",
        r"\brelocation\s+(?:support|package|assistance|allowance|budget|bonus)",
        r"\bvisa\s+and\s+relocation\s+(?:support|assistance)",
        r"\b(?:relocatiepakket|visumsponsoring|relocatieondersteuning)",
        r"\bhighly[- ]skilled\s+migrant|\bkennismigrant",
    )),
    re.I,
)
# Anything that negates or conditions an offer phrase in the same sentence voids it.
_OFFER_BLOCKER = re.compile(
    r"\b(?:no|not|unable|cannot|\w+n['’]t|without|geen|niet|already|reeds|existing)\b"
    # "have a partner / highly skilled migrant visa" is a requirement, not an offer.
    r"|\b(?:have|hold|holding)\b[^.]{0,25}(?:highly[- ]skilled\s+migrant|kennismigrant)",
    re.I,
)
# "preferably already living in the Netherlands" is a wish, not a refusal.
_PREFERENCE = re.compile(r"\b(?:prefer\w*|ideally|a plus|bonus)\b", re.I)
_REFUSES_RELOCATION = re.compile(
    "|".join((
        r"\bno\s+relocation\b",
        r"(?:\b(?:do|does|will|can|are|is)\s*|['’]re\s+)(?:not|n['’]t)\s+(?:be\s+)?(?:able\s+to\s+)?(?:offer|provide|support|cover|offering|providing)\w*\s+"
        r"(?:\w+\s+){0,2}?relocation",
        r"\brelocation\s+(?:\w+\s+)?(?:is|will)\s+(?:\w+\s+)?not\s+(?:be\s+)?(?:offered|provided|available|possible|supported)",
        rf"\b(?:must|need to|needs to|should)\s+(?:already\s+)?(?:live|be based|reside|be located|be living|be residing)\s+{_IN_NL}",
        rf"\bonly\b.*\b(?:based|living|residing|located|reside|live)\s+{_IN_NL}",
        rf"\balready\s+(?:based|living|residing|located)\s+{_IN_NL}",
        rf"\byou(?:['’]re|\s+are)\s+(?:currently\s+|already\s+)?(?:based|living|residing|located)\s+{_IN_NL}",
        rf"^\W*currently\s+(?:based|living|residing|located)\s+{_IN_NL}",
        r"\b(?:nl|netherlands|dutch)\s+residency\s+(?:is\s+)?(?:required|mandatory)",
        r"\bgeen\s+relocatie",
    )),
    re.I,
)


def sponsorship_stance(description: str, title: str = "") -> Stance:
    found = set()
    for sentence in _SENTENCE.split(f"{title}\n{description}"):
        sentence = sentence.strip()
        if _REFUSES_VISA.search(sentence) and not _NATIONALITY.search(sentence):
            return "refuses_visa"
        if _OFFERS.search(sentence) and not _OFFER_BLOCKER.search(sentence):
            found.add("offers")
        elif _REFUSES_RELOCATION.search(sentence) and not _PREFERENCE.search(sentence):
            found.add("refuses_relocation")
    if "offers" in found:
        return "offers"
    return "refuses_relocation" if found else "silent"
