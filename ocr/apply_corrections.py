"""Apply the editorial corrections to the diplomatic entries.

Sources, in order (a later edit to the same spot is skipped, not stacked):

  corrections/errata.tsv          the Tryckfel list and confirmed misprints
  corrections/auto.tsv            obvious fixes from errata.py
  corrections/review_items.json   the remaining findings; every one with a
                                  clean proposal is accepted (misprints,
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


def strip_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def merge_edit(x: str, y: str) -> str | None:
    """x with only the changes y makes inside it: a proposal that quotes part
    of the printed passage ("ὁ, ἡ, τὸ" for "Ordagrann, ὁ, η, τὸ") must not
    delete the rest. None when nothing changes."""
    a, b = TOKEN.findall(x), TOKEN.findall(y)
    sa, sb = [m.span() for m in TOKEN.finditer(x)], [m.span() for m in TOKEN.finditer(y)]
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    if ops and ops[0][0] != "delete" and ops[-1][0] != "delete":
        return y if y != x else None      # the proposal covers the whole passage
    while ops and ops[0][0] == "delete":
        ops = ops[1:]
    while ops and ops[-1][0] == "delete":
        ops = ops[:-1]
    if all(op == "equal" for op, *_ in ops):
        return None
    out, pos = [], 0
    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            continue
        new = y[sb[j1][0]:sb[j2 - 1][1]] if j2 > j1 else ""
        if i2 > i1:
            start, end = sa[i1][0], sa[i2 - 1][1]
        else:   # an insertion attaches to the token before it (".:" after a word)
            start = end = sa[i1 - 1][1] if i1 else 0
            gap = y[sb[j1 - 1][1]:sb[j1][0]] if j1 else ""
            new = gap + new
        out.append(x[pos:start] + new)
        pos = end
    out.append(x[pos:])
    return "".join(out)
ACCEPT = {"misprint", "diacritic", "rules", "letter", "auto"}


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
        if found is None:
            # the context straddles a strip break: take the printed text alone,
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
        row["strip"] = sid
        if any(not (end <= a or start >= b) for a, b, _ in edits[sid]):
            row["status"] = "overlap"
            return
        edits[sid].append((start, end, new))
        row["status"] = "applied"

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

    args.out.mkdir(parents=True, exist_ok=True)
    for sid, t in strips.items():
        for start, end, new in sorted(edits[sid], reverse=True):
            t = t[:start] + new + t[end:]
        (args.out / f"{sid}.txt").write_text(t, encoding="utf-8")

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
