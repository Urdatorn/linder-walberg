"""Join the proofread strips into page texts and into the book's entries.

proof/strips/NNNN_SS.txt hold one paragraph per entry; a strip whose first
paragraph starts with "~ " continues the last entry of the strip before it
(the column above, the previous column, or the previous page).

  text/pages/NNNN.txt   each page's paragraphs, a continuation joined to
                        the paragraph before it on the same page
  text/entries.jsonl    the dictionary body (0005-0539, without the Tryckfel
                        table at the foot of 0539) as entries, each with
                        the pages and strips it was read from

    python assemble.py [--proof proof/strips] [--out text]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

CONTINUES = "~ "
RUNNING_HEAD = re.compile(r"(\d+\s+)?[A-ZÅÄÖ][\wåäöÅÄÖ\- ]*?\s*—\s*[A-ZÅÄÖ][\wåäöÅÄÖ\- ]*\.(\s+\d+)?|\d+")


def join(prev: str, cont: str) -> str:
    """Append a continuation, closing a word hyphenated across the break."""
    if re.search(r"[^\W\d_][-‐]$", prev) and re.match(r"[^\W\d_]", cont) and not re.match(r"(o|l|och)\b", cont):
        return prev[:-1] + cont
    return prev + " " + cont


def read_strips(proof: Path) -> dict[str, list[tuple[int, list[str]]]]:
    pages = collections.defaultdict(list)
    for f in sorted(proof.glob("*_*.txt")):
        page, n = f.stem.split("_")
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", f.read_text(encoding="utf-8"))]
        pages[page].append((int(n), [p for p in paras if p]))
    return {p: sorted(v) for p, v in sorted(pages.items())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proof", type=Path, default=Path("proof/strips"))
    ap.add_argument("--out", type=Path, default=Path("text"))
    ap.add_argument("--body", default="0005-0539", help="pages holding the dictionary entries")
    ap.add_argument("--not-entries", default="0539_05", help="strips in the body that are not entries (the Tryckfel table)")
    args = ap.parse_args()

    first, last = args.body.split("-")
    (args.out / "pages").mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for page, strips in read_strips(args.proof).items():
        paras: list[str] = []
        for n, ps in strips:
            for k, p in enumerate(ps):
                cont = k == 0 and p.startswith(CONTINUES)
                text = p[len(CONTINUES):] if cont else p
                if cont and paras:
                    paras[-1] = join(paras[-1], text)
                else:
                    paras.append(text)
                if first <= page <= last and f"{page}_{n:02d}" not in args.not_entries.split(","):
                    # a running head the proofreading left ("Loppgräs — Lugn.", "Lusta—Lycksalig.",
                    # "253") or a sheet signature ("42"): not part of any entry
                    if RUNNING_HEAD.fullmatch(text):
                        continue
                    # a stray page number at the head of a paragraph ("253 τινι")
                    text = re.sub(rf"^{int(page) - 4}\s+(?=\S)", "", text)
                    # every entry opens with a capitalised headword: anything else
                    # (a lost "~ ", a derivative split off, "— sluttande") continues
                    # the entry before it
                    if not cont and entries and not re.match(r"[A-ZÅÄÖ]", text):
                        cont = True
                        text = text.removeprefix("~ ").removeprefix("~")
                    if cont and entries:
                        entries[-1]["text"] = join(entries[-1]["text"], text)
                        entries[-1]["source"].append(f"{page}_{n:02d}")
                    else:
                        entries.append({"text": text, "page": page, "source": [f"{page}_{n:02d}"]})
        (args.out / "pages" / f"{page}.txt").write_text("\n\n".join(paras) + "\n", encoding="utf-8")
    with open(args.out / "entries.jsonl", "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"pages {len({p for e in entries for p in [e['page']]})} entries {len(entries)}")


if __name__ == "__main__":
    main()
