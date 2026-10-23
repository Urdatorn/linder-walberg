"""Check the headwords of the assembled entries.

Two independent tests, since the headwords are what Dictionary.app indexes:

  order     the dictionary is alphabetical, so a headword that sorts before
            the one above it (and is not a repeat with another sense) is
            misread, or the entry was split or merged wrongly
  runeberg  Project Runeberg's 2013 OCR of the same page, whose entries were
            made searchable by headword, has a different headword at the
            same place in the page's sequence

Swedish order of 1862: a-z with v and w as one letter, then å, ä, ö.

    python check_headwords.py text/entries.jsonl --out corrections/headwords.tsv
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from pathlib import Path

from clean import load_runeberg

ORDER = {c: i for i, c in enumerate("abcdefghijklmnopqrstuvxyzåäö")}
ORDER["w"] = ORDER["v"]
FOLD = {"æ": "ä", "ø": "ö", "é": "e", "è": "e", "ü": "y", "à": "a"}


def headword(text: str) -> str:
    m = re.match(r"([^,;:(]+?)(?:,|\s+se\s|\s*\(|$)", text)
    return m.group(1).strip() if m else text.split()[0]


def sort_key(word: str) -> tuple:
    w = unicodedata.normalize("NFC", word.lower())
    w = "".join(FOLD.get(c, c) for c in w)
    return tuple(ORDER[c] for c in w if c in ORDER)


def runeberg_heads(rb: str) -> list[str]:
    heads = []
    for para in re.split(r"\n\s*\n", rb):
        para = para.strip()
        m = re.match(r"([A-ZÅÄÖ][^,]{0,40}?),", para)
        if m:
            heads.append(re.sub(r"\s+", "", m.group(1)))
    return heads


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entries", type=Path)
    ap.add_argument("--runeberg", type=Path, default=Path("runeberg_txt/Pages"))
    ap.add_argument("--out", type=Path, default=Path("corrections/headwords.tsv"))
    args = ap.parse_args()

    entries = [json.loads(l) for l in args.entries.read_text(encoding="utf-8").splitlines()]
    heads = [headword(e["text"]) for e in entries]
    rows = []
    # order: compare with the nearest previous headword that is a word (not a letter heading)
    for i in range(1, len(entries)):
        a, b = heads[i - 1], heads[i]
        if len(b) < 2 or re.fullmatch(r"[A-ZÅÄÖ][.)]?", b) or re.fullmatch(r"[A-ZÅÄÖ][.)]?", a):
            continue
        if re.search(r"[Ͱ-Ͽἀ-῿]", b):
            rows.append((entries[i]["page"], b, "greek_letters", a, ""))
        elif sort_key(b) < sort_key(a) and (i + 1 >= len(heads) or sort_key(heads[i + 1]) >= sort_key(a)):
            rows.append((entries[i]["page"], b, "out_of_order", a, heads[i + 1] if i + 1 < len(heads) else ""))
    # Runeberg: align each page's headword sequence with Runeberg's
    by_page: dict[str, list[str]] = {}
    for e, h in zip(entries, heads):
        by_page.setdefault(e["page"], []).append(h)
    for page, ours in by_page.items():
        theirs = runeberg_heads(load_runeberg(args.runeberg / f"{page}.txt"))
        sm = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "replace" and i2 - i1 == j2 - j1:
                for o, t in zip(ours[i1:i2], theirs[j1:j2]):
                    if difflib.SequenceMatcher(None, o.lower(), t.lower()).ratio() >= 0.6:
                        rows.append((page, o, "runeberg_differs", t, ""))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("page\theadword\tcheck\tother\tnext\n" + "".join("\t".join(r) + "\n" for r in rows),
                        encoding="utf-8")
    from collections import Counter
    print(len(entries), "entries;", Counter(r[2] for r in rows))


if __name__ == "__main__":
    main()
