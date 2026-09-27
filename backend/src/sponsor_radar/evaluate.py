"""Score the rules against labeled sets kept outside this repo.

The labels live in the private workbench (`notes/labels/`), because the posting file keeps a copy of
each posting's text. Rules run on that saved text, so a score does not depend on today's database.

- `pairs.csv`: one row per source with the rule's status and candidate KvKs and a labeled verdict.
- `postings.jsonl`: one object per posting with `title`, `description`, `labels`, and optional `stratum`.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from . import signals

MAX_CASES = 8


def _rate(hits: int, total: int) -> str:
    return f"{hits / total:.2f} ({hits}/{total})" if total else "n/a (0)"


def _binary(rows: list[dict], name: str, rule: Callable[[dict], bool], truth: Callable[[dict], bool]) -> list[str]:
    """Precision and recall of a rule's True against the labels, plus the misses to read."""
    pairs = [(rule(r), truth(r), r) for r in rows]
    tp = sum(1 for p, t, _ in pairs if p and t)
    fp = [r for p, t, r in pairs if p and not t]
    fn = [r for p, t, r in pairs if t and not p]
    lines = [f"{name}: precision {_rate(tp, tp + len(fp))}, recall {_rate(tp, tp + len(fn))}"]
    lines += [f"  false positive: {_case(r, name)}" for r in fp[:MAX_CASES]]
    lines += [f"  false negative: {_case(r, name)}" for r in fn[:MAX_CASES]]
    return lines


def _case(r: dict, field: str) -> str:
    quote = (r.get("evidence") or {}).get(field.split(" ")[0], "")
    return f"#{r['n']} {r['title'][:70]!r}" + (f" — {quote[:120]!r}" if quote else "")


def _postings(rows: list[dict]) -> list[str]:
    for r in rows:
        r["rule"] = {
            "is_tech": signals.is_tech_role(r["title"]),
            "seniority": signals.seniority(r["title"]),
            "dutch_required": signals.dutch_required(r["description"], r["title"]),
            "min_years": signals.min_years(r["description"]),
        }
        if hasattr(signals, "sponsorship_stance"):
            r["rule"]["sponsorship_stance"] = signals.sponsorship_stance(r["description"], r["title"])
    lab = lambda r, f: r["labels"][f]  # noqa: E731

    lines = [f"Postings: {len(rows)} labeled", ""]
    lines += _binary(rows, "is_tech", lambda r: r["rule"]["is_tech"], lambda r: lab(r, "is_tech"))
    tech = [r for r in rows if lab(r, "is_tech")]
    # The rules below only matter for postings the page shows, which are tech postings.
    lines += _binary(tech, "dutch_required", lambda r: r["rule"]["dutch_required"], lambda r: lab(r, "dutch_required"))
    lines += _binary(tech, "min_years >= 3 (hidden by default)",
                     lambda r: (r["rule"]["min_years"] or 0) >= 3, lambda r: (lab(r, "min_years") or 0) >= 3)
    exact = sum(1 for r in tech if r["rule"]["min_years"] == lab(r, "min_years"))
    lines.append(f"min_years exact: {_rate(exact, len(tech))}")
    lines += _binary(tech, "seniority senior (hidden by default)",
                     lambda r: r["rule"]["seniority"] == "senior", lambda r: lab(r, "seniority") == "senior")
    lines += _binary(tech, "seniority intern or junior",
                     lambda r: r["rule"]["seniority"] in ("intern", "junior"),
                     lambda r: lab(r, "seniority") in ("intern", "junior"))
    confusion = Counter((r["rule"]["seniority"], lab(r, "seniority")) for r in tech)
    lines.append("seniority rule -> label: " + ", ".join(f"{a}->{b} {n}" for (a, b), n in sorted(confusion.items())))
    if all("sponsorship_stance" in r["rule"] for r in tech):
        for value in ("offers", "refuses_visa", "refuses_relocation"):
            lines += _binary(tech, f"sponsorship_stance {value}",
                             lambda r, v=value: r["rule"]["sponsorship_stance"] == v,
                             lambda r, v=value: lab(r, "sponsorship_stance") == v)
    lines.append(f"nl_open among postings the NL check accepted: {_rate(sum(lab(r, 'nl_open') for r in rows), len(rows))}")
    for r in rows:
        if not lab(r, "nl_open"):
            lines.append(f"  not open to NL: {_case(r, 'nl_open')}")
    strata = Counter(r.get("stratum", "unknown") for r in rows)
    lines.append("strata: " + ", ".join(f"{k}={v}" for k, v in sorted(strata.items())))
    return lines


def _pairs(rows: list[dict]) -> list[str]:
    def correct(r: dict) -> bool:
        return r["label"] == "confirmed" and r["kvk"] in r["candidate_kvks"].split(";")

    lines = [f"Pairs: {len(rows)} labeled", "Labels: " + ", ".join(
        f"{k}={v}" for k, v in Counter(r["label"] for r in rows).most_common())]
    inferred = [r for r in rows if r["rule_status"] == "name_inferred" and r["label"] != "uncertain"]
    lines.append(f"name_inferred precision: {_rate(sum(map(correct, inferred)), len(inferred))}")
    lines += [f"  wrong: {r['employer']} -> {r['candidate_organisations']} ({r['evidence_quote'][:100]!r})"
              for r in inferred if not correct(r)][:MAX_CASES]
    unmatched = [r for r in rows if r["rule_status"] == "unmatched"]
    found = [r for r in unmatched if r["label"] == "confirmed"]
    lines.append(f"unmatched sources with a confirmed register entry: {_rate(len(found), len(unmatched))}")
    lines.append(f"  of which relation=group: {sum(1 for r in found if r['relation'] == 'group')}")
    return lines


def evaluate(labels: Path) -> str:
    lines: list[str] = []
    if (path := labels / "pairs.csv").exists():
        with path.open(newline="") as f:
            lines += _pairs([r for r in csv.DictReader(f) if r.get("label")]) + [""]
    if (path := labels / "postings.jsonl").exists():
        with path.open() as f:
            lines += _postings([r for line in f if (r := json.loads(line)).get("labels")])
    return "\n".join(lines) if lines else f"no pairs.csv or postings.jsonl in {labels}"
