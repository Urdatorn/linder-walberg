"""Apply the editorial corrections to the diplomatic entries.

Sources, in order (a later edit to the same spot is skipped, not stacked):

  corrections/errata.tsv          the Tryckfel list and confirmed misprints
  corrections/auto.tsv            obvious fixes from errata.py
  corrections/review_items.json   the remaining findings; every one with a
                                  clean proposal is accepted, unless it would
                                  add an accent or breathing error the print
                                  does not have (then it is rejected) (misprints,
                                  diacritic, accent-rule and one-letter
                                  suspects). Proposals that are notes rather
                                  than text ("possibly an old spelling",
                                  "A / B"), uncertain readings, headword
                                  findings and unattested words stay as printed.

Each correction is placed in a strip, by its context (the text around the
word) or, for the proofreaders' reports, by the strip it was reported on, so
the diplomatic and corrected texts stay aligned strip by strip.

  text/corrected_strips/          the proofread strips with corrections applied;
                                  assemble.py --proof text/corrected_strips
                                  --out text/corrected joins them into
                                  corrected pages and entries
  corrections/errata.sqlite       every finding, its proposal, the decision
                                  and whether and where it was applied

    python apply_corrections.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import difflib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

NOTE = re.compile(r"\b(possibly|probably|as printed|kept|unattested|or|if|maybe|perhaps|correct|note|sic|same|"
                  r"unclear|either|the|from|with|for|written|usual|ending|genitive|dative|form|instead|missing|"
                  r"printed|should|means|word|line|sense|number|before|after)\b|[;/]|\.\.\.|…|=", re.I)
TOKEN = re.compile(r"\w+|[^\w\s]")
ACCEPT = {"misprint", "diacritic", "rules", "letter", "auto"}


def strip_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def merge_edit(x: str, y: str) -> str | None:
    """x with the proposal y put in place of the stretch of x it corrects.

    A proposal often quotes only part of the printed passage ("Sysselsättning"
    for "Göra, se Sysselssättning."), so y replaces the run of x's words most
    like it, of about y's length, and the rest of x stays. None when y matches
    no stretch of x well or changes nothing."""
    a = [m.span() for m in TOKEN.finditer(x)]
    n = len(TOKEN.findall(y))
    if not a or not n:
        return None
    best = (0.0, 0, len(x))
    for length in {max(1, n - 1), n, n + 1}:
        for k in range(0, max(1, len(a) - length + 1)):
            start, end = a[k][0], a[min(len(a), k + length) - 1][1]
            r = difflib.SequenceMatcher(None, x[start:end], y, autojunk=False).ratio()
            if r > best[0]:
                best = (r, start, end)
    r, start, end = best
    if r < 0.7:
        return None
    out = x[:start] + y + x[end:]
    return out if out != x else None


GREEK_LETTER = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")


def place_accent(new: str, after: str) -> str:
    """The last word of a correction keeps a grave only before another Greek word;
    before punctuation, Swedish or the end it takes an acute (a proposal taken
    from a lexicon may carry the grave of running text: προσβατὸς). Words
    inside the correction are left as proposed (κατὰ τὴν χώραν)."""
    m = re.search(r"(\S+)$", new)
    if not m or not GREEK_LETTER.search(m.group(1)):
        return new
    word = unicodedata.normalize("NFD", m.group(1))
    i = word.rfind("\u0300")
    if i < 0 or re.match(r"\s+[\u0370-\u03ff\u1f00-\u1fff]", after):
        return new
    tail = word[i + 1:]
    if any(unicodedata.normalize("NFD", c)[0] in "αεηιουω" for c in tail if not unicodedata.combining(c)):
        return new                         # not the last syllable: leave it
    return new[:m.start()] + unicodedata.normalize("NFC", word[:i] + "\u0301" + word[i + 1:])


def _problems(text: str, start: int, end: int) -> collections.Counter:
    """Formal accent and breathing findings for the Greek words overlapping text[start:end]."""
    from clean import WORD, script, tokens
    from greek_checks import word_findings
    toks = [t for t in tokens(text) if WORD.match(t[2])]
    out = collections.Counter()
    for k, (s0, e0, w) in enumerate(toks):
        if e0 <= start or s0 >= end or script(w) != "greek":
            continue
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        gap = text[e0:nxt[0]] if nxt else "."
        prev = toks[k - 1][2] if k else None
        out.update(f"{kind} ({w})" for kind, _ in word_findings(w, prev, nxt[2] if nxt else None, gap))
    return out


def new_problems(text: str, start: int, end: int, new: str) -> str:
    """What a correction would break: findings in the corrected passage that the printed one lacks."""
    before = _problems(text, start, end)
    after = _problems(text[:start] + new + text[end:], start, start + len(new))
    worse = after - before
    return ", ".join(sorted(worse)) if worse else ""


def clean_proposal(item: dict) -> str | None:
    # the strip's continuation marker "~ " is layout, never text to correct
    y, x = (item.get("y") or "").strip().removeprefix("~ "), (item.get("x") or "").strip().removeprefix("~ ")
    if not y or y == x or NOTE.search(y):
        return None
    if item["c"] in ("rules", "diacritic", "auto") and strip_marks(y) != strip_marks(x):
        return None
    return merge_edit(x, y)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strips", type=Path, default=Path("proof/strips"))
    ap.add_argument("--corrections", type=Path, default=Path("corrections"))
    ap.add_argument("--out", type=Path, default=Path("text/corrected_strips"))
    args = ap.parse_args()

    strips = {f.stem: f.read_text(encoding="utf-8") for f in sorted(args.strips.glob("*_*.txt"))}
    by_page = collections.defaultdict(list)
    for sid in strips:
        by_page[sid[:4]].append(sid)
    edits: dict[str, list[tuple[int, int, str]]] = collections.defaultdict(list)   # strip -> (start, end, new)
    rows: list[dict] = []

    def place(row: dict, candidates: list[str], printed: str, new: str, context: str = "") -> None:
        """Find printed (inside its context where that is on one strip) and queue the edit."""
        found = None
        for sid in dict.fromkeys(candidates):
            t = strips[sid]
            if context and context in t and context.find(printed) >= 0:
                found = (sid, t.index(context) + context.find(printed))
                break
        if found is None and row["category"] in ("misprint", "errata"):
            # a reported passage whose context straddles a strip break: take it alone,
            # in the strip that shares the most words with the context
            words = set(context.split())
            hits = [(len(words & set(strips[sid].split())), sid) for sid in dict.fromkeys(candidates)
                    if printed in strips[sid]]
            if hits:
                sid = max(hits)[1]
                found = (sid, strips[sid].index(printed))
        if found is None:
            row["status"] = "not_found"
            return
        sid, start = found
        end = start + len(printed)
        new = place_accent(new, strips[sid][end:end + 3])
        worse = new_problems(strips[sid], start, end, new)
        if worse:
            row.update(strip=sid, status="rejected", note=(row.get("note") or "") + f" [rejected: would add {worse}]")
            return
        row["strip"] = sid
        if any(not (end <= a or start >= b) for a, b, _ in edits[sid]):
            row["status"] = "overlap"
            return
        edits[sid].append((start, end, new))
        row["status"] = "applied"
        row["_edit"] = (start, end, new)

    def near(page: str, strip: str | None = None) -> list[str]:
        pages = [f"{int(page) + d:04d}" for d in (0, -1, 1)]
        return ([strip] if strip in strips else []) + [s for p in pages for s in by_page[p]]

    # 1. the Tryckfel list and confirmed misprints
    with open(args.corrections / "errata.tsv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            row = {"source": r["source"], "category": "errata", "page": r["page"], "entry": r["entry"],
                   "printed": r["printed"], "proposal": r["corrected"], "note": r["note"], "decision": r["status"]}
            if r["status"] == "accepted":
                place(row, near(r["page"]), r["printed"], r["corrected"])
            else:
                row["status"] = "kept"
            rows.append(row)
    # 2. findings: auto fixes and review items, all from the item list; the
    #    proofreaders' misprints carry the strip they were reported on
    items = json.loads((args.corrections / "review_items.json").read_text(encoding="utf-8"))
    review = json.loads((args.corrections / "review.json").read_text(encoding="utf-8"))
    misprint_strip = iter(m.get("strip") for m in review["misprint"])
    for it in items:
        strip = next(misprint_strip) if it["c"] == "misprint" else None
        row = {"source": it["id"], "category": it["c"], "subcategory": it.get("s", ""), "page": it["p"],
               "column": it.get("col") or None, "entry": it.get("e", ""), "printed": it["x"],
               "proposal": it.get("y", ""), "note": it.get("n", ""), "context": it.get("ctx", ""), "strip": strip}
        new = clean_proposal(it) if it["c"] in ACCEPT else None
        if new is None:
            row.update(decision="kept as printed", status="kept")
        else:
            row["decision"] = "accepted"
            place(row, near(it["p"], strip), it["x"].strip().removeprefix("~ "), new, it.get("ctx", "").strip("…").strip())
        rows.append(row)

    # Each edit was checked alone; edits near each other can still combine badly
    # (λευκαί l. πολιαὶ -> λευκαὶ l. πολιαί). Check every corrected strip against
    # the printed one and undo, one at a time, edits that leave new problems.
    args.out.mkdir(parents=True, exist_ok=True)
    undone = 0
    for sid, t0 in strips.items():
        kept = sorted(edits[sid])
        def build(es):
            t = t0
            for start, end, new in sorted(es, reverse=True):
                t = t[:start] + new + t[end:]
            return t
        base = _problems(t0, 0, len(t0))
        extra = _problems(build(kept), 0, len(build(kept))) - base
        while extra and kept:
            best = min(range(len(kept)), key=lambda i: sum(
                (_problems(build(kept[:i] + kept[i + 1:]), 0, 10 ** 9) - base).values()))
            trial = kept[:best] + kept[best + 1:]
            trial_extra = _problems(build(trial), 0, 10 ** 9) - base
            if sum(trial_extra.values()) >= sum(extra.values()):
                break
            for r in rows:
                if r.get("strip") == sid and r.get("status") == "applied" and r.get("_edit") == kept[best]:
                    r["status"] = "rejected"
                    r["note"] = (r.get("note") or "") + " [rejected: combined with a nearby correction it adds an accent error]"
            kept, extra = trial, trial_extra
            undone += 1
        (args.out / f"{sid}.txt").write_text(build(kept), encoding="utf-8")
    print("edits undone after checking whole strips:", undone)

    db = args.corrections / "errata.sqlite"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    cols = ["source", "category", "subcategory", "page", "column", "strip", "entry", "printed", "proposal",
            "decision", "status", "note", "context"]
    con.execute(f"CREATE TABLE findings (id INTEGER PRIMARY KEY, {', '.join(c + ' TEXT' for c in cols)})")
    con.executemany(f"INSERT INTO findings ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [[r.get(c) for c in cols] for r in rows])
    con.execute("CREATE INDEX findings_page ON findings(page)")
    con.execute("CREATE INDEX findings_category ON findings(category, status)")
    con.commit()
    summary = collections.Counter((r["category"], r["status"]) for r in rows)
    for k in sorted(summary):
        print(*k, summary[k])
    print("strips changed", sum(bool(v) for v in edits.values()))


if __name__ == "__main__":
    main()
