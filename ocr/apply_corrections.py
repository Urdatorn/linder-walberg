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

Each correction is placed by its context (the text around the word, taken
from the entry) or, for the proofreaders' reports, by the strip it came from.

  text/entries_corrected.jsonl    the entries with corrections applied
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
    y, x = (item.get("y") or "").strip(), (item.get("x") or "").strip()
    if not y or y == x or NOTE.search(y):
        return None
    if item["c"] in ("rules", "diacritic", "auto") and strip_marks(y) != strip_marks(x):
        return None
    return merge_edit(x, y)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entries", type=Path, default=Path("text/entries.jsonl"))
    ap.add_argument("--corrections", type=Path, default=Path("corrections"))
    ap.add_argument("--out", type=Path, default=Path("text/entries_corrected.jsonl"))
    args = ap.parse_args()

    entries = [json.loads(l) for l in args.entries.read_text(encoding="utf-8").splitlines()]
    by_page = collections.defaultdict(list)
    by_strip = collections.defaultdict(list)
    for i, e in enumerate(entries):
        for s in e["source"]:
            by_page[s[:4]].append(i)
            by_strip[s].append(i)
    edits: dict[int, list[tuple[int, int, str, int]]] = collections.defaultdict(list)   # entry -> (start, end, new, row)
    rows: list[dict] = []

    def place(row: dict, candidates: list[int], printed: str, new: str, context: str = "") -> None:
        """Find printed (inside context, if given) in one of the candidate entries and queue the edit."""
        for i in dict.fromkeys(candidates):
            t = entries[i]["text"]
            start = -1
            if context and context in t:
                c0 = t.index(context)
                k = context.find(printed)
                start = c0 + k if k >= 0 else -1
            elif printed in t:
                start = t.index(printed)
            if start < 0:
                continue
            end = start + len(printed)
            if any(not (end <= s or start >= e) for s, e, _, _ in edits[i]):
                row.update(status="overlap", entry_no=i)
                return
            edits[i].append((start, end, new, len(rows)))
            row.update(status="applied", entry_no=i)
            return
        row["status"] = "not_found"

    # 1. the Tryckfel list and confirmed misprints
    with open(args.corrections / "errata.tsv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            row = {"source": r["source"], "category": "errata", "page": r["page"], "entry": r["entry"],
                   "printed": r["printed"], "proposal": r["corrected"], "note": r["note"], "decision": r["status"]}
            if r["status"] == "accepted":
                place(row, by_page[r["page"]], r["printed"], r["corrected"])
            else:
                row["status"] = "kept"
            rows.append(row)
    # 2. findings: auto fixes and review items, all from the item list
    items = json.loads((args.corrections / "review_items.json").read_text(encoding="utf-8"))
    for it in items:
        row = {"source": it["id"], "category": it["c"], "subcategory": it.get("s", ""), "page": it["p"],
               "column": it.get("col") or None, "entry": it.get("e", ""), "printed": it["x"],
               "proposal": it.get("y", ""), "note": it.get("n", ""), "context": it.get("ctx", "")}
        new = clean_proposal(it) if it["c"] in ACCEPT else None
        if new is None:
            row.update(decision="kept as printed", status="kept")
        else:
            row["decision"] = "accepted"
            pages = [f"{int(it['p']) + d:04d}" for d in (0, -1, 1)]
            cands = [i for p in pages for i in by_page[p]]
            place(row, cands, it["x"], new, it.get("ctx", "").strip("…").strip())
        rows.append(row)

    out = []
    for i, e in enumerate(entries):
        t = e["text"]
        for start, end, new, _ in sorted(edits[i], reverse=True):
            t = t[:start] + new + t[end:]
        out.append(e | {"text": t, "diplomatic": e["text"]} if edits[i] else e)
    args.out.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in out), encoding="utf-8")

    db = args.corrections / "errata.sqlite"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    cols = ["source", "category", "subcategory", "page", "column", "entry", "entry_no", "printed", "proposal",
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
    print("entries changed", sum(bool(edits[i]) for i in range(len(entries))))


if __name__ == "__main__":
    main()
