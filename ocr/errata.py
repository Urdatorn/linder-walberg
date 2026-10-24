"""Turn the checks and the proofreaders' reports into fixes and an errata report.

Inputs: the assembled entries, greek_checks.py's findings, check_headwords.py's
findings, and the proofreaders' reports (proof/reports/NNNN.json: misprints
they kept as printed, readings they could not settle).

  corrections/auto.tsv     obvious fixes, applied in the editorial layer:
                           - an acute on the last syllable before another Greek
                             word (not an enclitic) becomes a grave
                           - a form unattested in the AncientGreek corpus, one
                             diacritic away from a form attested at least 1000
                             times (and at least 100 times as often), takes it
                             (a missing breathing or accent, a wrong accent
                             kind or place, a stray second accent)
  corrections/review.json  everything else, grouped for a person to decide:
                           misprints the proofreaders reported, unattested Greek
                           with a likely reading one letter away, rarer
                           diacritic fixes, headwords out of order, and the
                           readings the proofreaders could not settle

The diplomatic text is never changed; both files say where and what.

    python errata.py text/entries.jsonl --checks ocr_runs/checks
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import unicodedata
from pathlib import Path

from check_headwords import headword
from clean import greek_lexicon, strip_marks
from greek_checks import ACUTE, GRAVE

AUTO_MIN = 1000      # the attested reading must be at least this frequent
AUTO_RATIO = 100     # and this many times as frequent as the printed form


def to_grave(word: str) -> str:
    d = unicodedata.normalize("NFD", word)
    i = d.rfind(ACUTE)
    return unicodedata.normalize("NFC", d[:i] + GRAVE + d[i + 1:]) if i >= 0 else word


def fix_final_accent(word: str, next_is_greek: bool) -> str:
    """A suggested grave stays only on the last syllable before another Greek word."""
    d = unicodedata.normalize("NFD", word)
    i = d.find(GRAVE)
    if i >= 0 and (not next_is_greek or any(unicodedata.normalize("NFD", c)[0] in "αεηιουω" for c in d[i + 1:])):
        return unicodedata.normalize("NFC", d.replace(GRAVE, ACUTE))
    return word


def n_accents(word: str) -> int:
    return sum(c in (ACUTE, GRAVE, "\u0342") for c in unicodedata.normalize("NFD", word))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entries", type=Path)
    ap.add_argument("--checks", type=Path, default=Path("ocr_runs/checks"))
    ap.add_argument("--reports", type=Path, default=Path("proof/reports"))
    ap.add_argument("--out", type=Path, default=Path("corrections"))
    ap.add_argument("--lexicon", type=Path,
                    default=Path(__file__).resolve().parents[2] / "BSDA-project/data/lexicon/forms.parquet")
    args = ap.parse_args()

    known = greek_lexicon(args.lexicon)
    entries = [json.loads(l) for l in args.entries.read_text(encoding="utf-8").splitlines()]
    findings = [json.loads(l) for l in (args.checks / "greek_findings.jsonl").read_text(encoding="utf-8").splitlines()]

    auto, review = [], collections.defaultdict(list)
    auto_words = set()
    for f in findings:
        e = entries[f["entry"]]
        where = {"page": f["page"], "entry": headword(e["text"]), "entry_no": f["entry"], "context": f["context"]}
        w, likely = f["word"], f.get("likely")
        if f["check"] == "grave" and f["why"].startswith("acute on the last syllable"):
            auto.append(where | {"printed": w, "corrected": to_grave(w), "rule": "grave before another word"})
            auto_words.add((f["entry"], w))
            continue
        if f["check"] == "grave":
            review["accent_rules"].append(where | {"printed": w, "likely": likely, "why": f["why"]})
            continue
        diacritic_only = likely and strip_marks(likely) == strip_marks(w.rstrip("'’ʼ᾽"))
        n_likely, n_printed = (known.count(likely), known.count(w)) if likely else (0, 0)
        # a second accent from a following enclitic ("ἐκφέρεταί τι") is right as printed
        throwback = n_accents(w) == 2 and n_accents(likely or "") == 1
        if diacritic_only and not throwback and n_likely >= AUTO_MIN and n_likely >= AUTO_RATIO * max(n_printed, 1):
            after = f["context"].split(w, 1)[-1]
            next_greek = bool(re.match(r"\s+[Ͱ-Ͽἀ-῿]", after))
            fixed = fix_final_accent(likely, next_greek)
            auto.append(where | {"printed": w, "corrected": fixed, "rule": f"{f['check']}: {f['why']}"})
            auto_words.add((f["entry"], w))
        elif throwback:
            continue
        elif f["check"] == "unattested" and likely and not diacritic_only and n_likely >= 50 \
                and len(strip_marks(likely)) == len(strip_marks(w.rstrip("'’ʼ᾽"))):
            review["greek_letter"].append(where | {"printed": w, "likely": likely, "count": n_likely})
        elif likely and diacritic_only:
            review["greek_diacritic"].append(where | {"printed": w, "likely": likely, "count": n_likely,
                                                      "why": f["why"]})
        elif f["check"] != "unattested":
            review["accent_rules"].append(where | {"printed": w, "likely": likely, "why": f["why"]})
        else:
            review["greek_unknown"].append(where | {"printed": w, "lsj": "LSJ" in f["why"]})

    # the proofreaders' reports
    auto_printed = {a["printed"] for a in auto}
    for f in sorted(args.reports.glob("*.json")):
        r = json.loads(f.read_text())
        for m in r.get("misprints", []):
            if any(w in m.get("printed", "") for w in auto_printed if len(w) > 2):
                continue
            review["misprint"].append({"page": r["page"], "strip": m.get("strip"), "printed": m.get("printed"),
                                       "likely": m.get("probably_meant"), "note": m.get("note")})
        for u in r.get("uncertain", []):
            review["uncertain"].append({"page": r["page"], "strip": u.get("strip"), "text": u.get("text"),
                                        "note": u.get("note")})
    hw = args.checks / "headwords.tsv"
    if hw.exists():
        for line in hw.read_text(encoding="utf-8").splitlines()[1:]:
            page, head, check, other, nxt = (line.split("\t") + [""] * 5)[:5]
            if check in ("out_of_order", "greek_letters"):
                review["headword"].append({"page": page, "printed": head, "check": check,
                                           "before": other, "after": nxt})

    args.out.mkdir(parents=True, exist_ok=True)
    cols = ["page", "entry", "printed", "corrected", "rule", "context"]
    (args.out / "auto.tsv").write_text(
        "\t".join(cols) + "\n" + "".join("\t".join(str(a[c]).replace("\t", " ").replace("\n", " ") for c in cols) + "\n"
                                       for a in auto), encoding="utf-8")
    (args.out / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    print("auto", len(auto), {k: len(v) for k, v in review.items()})


if __name__ == "__main__":
    main()
