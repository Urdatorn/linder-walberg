"""Flatten the errata stage's output into one list of findings
(corrections/review_items.json), the input of apply_corrections.py.

Each item: id, category (c), subcategory (s), page (p), printed page (pp),
column, entry, printed text (x), proposal (y), note (n), context (ctx).

    python review_items.py
"""

from __future__ import annotations

import csv
import glob
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    review = json.loads((ROOT / "corrections/review.json").read_text(encoding="utf-8"))
    entries = [json.loads(l) for l in (ROOT / "text/entries.jsonl").read_text(encoding="utf-8").splitlines()]
    col = {}
    for f in glob.glob(str(ROOT / "ocr_runs/full3-clean/strips/*.json")):
        pg = json.load(open(f))
        for s in pg["strips"]:
            col[f"{pg['page']}_{s['n']:02d}"] = s["column"] + 1 if s["column"] >= 0 else 0

    def sm(s):
        return "".join(c for c in unicodedata.normalize("NFD", s or "") if not unicodedata.combining(c))

    def pp(p):
        n = int(p)
        return n - 4 if 5 <= n <= 539 else None

    items, count = [], {}

    def add(cat, sub, page, strip, entry, printed, proposal, note, ctx):
        count[cat] = count.get(cat, 0) + 1
        items.append({"id": f"{cat}-{count[cat] - 1}", "c": cat, "s": sub, "p": page, "pp": pp(page),
                      "col": col.get(strip, 0) if strip else 0, "e": entry or "", "x": printed or "",
                      "y": proposal or "", "n": note or "", "ctx": (ctx or "").replace("\n", " ")})

    def strip_of(no):
        return entries[no]["source"][0] if no is not None and no < len(entries) else None

    with open(ROOT / "corrections/auto.tsv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            add("auto", r["rule"].split(":")[0], r["page"], None, r["entry"], r["printed"], r["corrected"],
                r["rule"], r["context"])
    for m in review["misprint"]:
        a, b = m["printed"] or "", m["likely"] or ""
        wa, wb = re.sub(r"[^\w]", "", a), re.sub(r"[^\w]", "", b)
        if wa == wb and a != b:
            sub = "punctuation"
        elif len(wa) == len(wb) and sum(x != y for x, y in zip(wa, wb)) == 1 and \
                {x for x, y in zip(wa, wb) if x != y} | {y for x, y in zip(wa, wb) if x != y} <= set("un"):
            sub = "turned n"
        elif sm(wa) == sm(wb) and wa != wb:
            sub = "accents"
        elif re.search(r"[Ͱ-Ͽἀ-῿]", a):
            sub = "Greek"
        else:
            sub = "Swedish"
        add("misprint", sub, m["page"], m.get("strip"), "", a, b, m.get("note"), "")
    for k, cat in [("greek_diacritic", "diacritic"), ("accent_rules", "rules"), ("greek_letter", "letter")]:
        for f in review[k]:
            add(cat, f.get("why", "").split(" (")[0] if cat != "letter" else "one letter", f["page"],
                strip_of(f.get("entry_no")), f.get("entry"), f["printed"], f.get("likely"),
                f.get("why") or (f"attested {f.get('count')} times" if f.get("count") else ""), f.get("context"))
    for h in review["headword"]:
        add("headword", h["check"].replace("_", " "), h["page"], None, h["printed"], h["printed"], "",
            f"between {h['before']} and {h['after']}" if h["check"] == "out_of_order" else f"after {h['before']}", "")
    for u in review["uncertain"]:
        add("uncertain", "", u["page"], u.get("strip"), "", u.get("text"), "", u.get("note"), "")
    for f in review["greek_unknown"]:
        add("unknown", "in LSJ" if f.get("lsj") else "not in LSJ", f["page"], strip_of(f.get("entry_no")),
            f.get("entry"), f["printed"], "", "", f.get("context"))
    (ROOT / "corrections/review_items.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")),
                                                       encoding="utf-8")
    print(len(items), count)


if __name__ == "__main__":
    main()
