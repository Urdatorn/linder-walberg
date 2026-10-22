"""Find strips in an OCR run that are probably wrong, without a reference.

Every entry in Linder-Walberg opens with a Swedish headword and every column
strip mixes Swedish and Greek, so four signals catch most failures:

  greek_heads   entries whose headword came out in Greek letters
                ("Σκρίφβαρε" for Skrifvare): the model mistaking Swedish for Greek
  density       characters per pixel of strip height, far below the median
                (the model stopped early) or far above it (a loop or invented text)
  latin         share of Latin-script letters, near zero when Swedish was dropped
  repeat        share of repeated 6-word sequences, high for loops the token-level
                guard missed

    python audit_run.py ocr_runs/full/pages [--list suspects.tsv]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
from pathlib import Path

GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
TAG = re.compile(r"<[^>]+>")
HEAD = re.compile(r"([^\s,.:;()]+)\s*,")


def entry_heads(text: str) -> list[str]:
    """Headword candidates: the first word of each line that opens 'Word,'."""
    heads = []
    for line in text.split("\n"):
        t = TAG.sub("", line).replace("#", "").strip()
        m = HEAD.match(t)
        if m and len(m.group(1)) >= 3 and not m.group(1).startswith(("-", "—")):
            heads.append(m.group(1))
    return heads


def latin_share(text: str) -> float:
    letters = [c for c in TAG.sub("", text) if c.isalpha()]
    return sum(c < "Ͱ" for c in letters) / max(len(letters), 1)


def repeat_share(text: str, n: int = 6) -> float:
    words = TAG.sub("", text).split()
    grams = [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]
    counts = collections.Counter(grams)
    return sum(v - 1 for v in counts.values() if v > 1) / max(len(grams), 1)


def audit(pages_dir: Path, first_body: str = "0005", last_body: str = "0538") -> list[dict]:
    rows = []
    for f in sorted(pages_dir.glob("*.json")):
        page = json.loads(f.read_text())
        if not first_body <= page["page"] <= last_body:
            continue
        for s in page["strips"]:
            if s["kind"] != "col":
                continue
            heads = entry_heads(s["text"])
            rows.append({
                "page": page["page"], "n": s["n"], "height": s["size"][1], "chars": len(s["text"]),
                "heads": len(heads), "greek_heads": sum(bool(GREEK.search(h)) for h in heads),
                "latin": latin_share(s["text"]), "repeat": repeat_share(s["text"]),
                "loop": bool(s.get("loop")), "retried": bool(s.get("retried")),
            })
    tall = [r for r in rows if r["height"] > 300]
    median_density = statistics.median(r["chars"] / r["height"] for r in tall)
    for r in rows:
        r["density"] = r["chars"] / r["height"] / median_density
        reasons = []
        if r["greek_heads"] >= 2 or (r["heads"] and r["greek_heads"] / r["heads"] > 0.25):
            reasons.append("greek_heads")
        if r["height"] > 300 and r["density"] < 0.5:
            reasons.append("short")
        if r["density"] > 1.7:
            reasons.append("long")
        if r["height"] > 300 and r["latin"] < 0.12:
            reasons.append("no_swedish")
        if r["repeat"] > 0.08:
            reasons.append("repeat")
        if r["loop"]:
            reasons.append("loop")
        r["reasons"] = reasons
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", type=Path, help="a run's pages/ directory")
    ap.add_argument("--list", type=Path, help="write suspect strips as PAGE<TAB>N<TAB>reasons")
    args = ap.parse_args()

    rows = audit(args.pages)
    heads = sum(r["heads"] for r in rows)
    greek = sum(r["greek_heads"] for r in rows)
    suspects = [r for r in rows if r["reasons"]]
    print(f"column strips {len(rows)}  entry heads {heads}  greek-script heads {greek} "
          f"({100 * greek / max(heads, 1):.1f}%)  suspect strips {len(suspects)}")
    print("by reason:", dict(collections.Counter(x for r in suspects for x in r["reasons"])))
    by_page = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by_page[r["page"]][0] += r["greek_heads"]
        by_page[r["page"]][1] += r["heads"]
    for page, (g, h) in sorted(by_page.items()):
        if g:
            print(f"  {page}: greek heads {g}/{h}")
    if args.list:
        args.list.write_text("".join(f"{r['page']}\t{r['n']}\t{','.join(r['reasons'])}\n" for r in suspects))
        print(f"wrote {len(suspects)} suspects to {args.list}")


if __name__ == "__main__":
    main()
