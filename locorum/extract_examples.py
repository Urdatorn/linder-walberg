"""The Greek examples of the dictionary: every Greek phrase of three or more
words in the corrected entries, split at the book's full stops between
alternatives, with gender articles and termination numbers removed and
brackets left unmatched by the cut dropped.

  locorum/examples.jsonl   n, headword, page, Swedish gloss, Greek, word count

Corpus match counts from an earlier run (match_counts.json) are carried over
to the new numbering by the examples' normalised words.

    python extract_examples.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "dict"))
from build_xml import GREEK, GREEK_RUN, Renderer, headword_of  # noqa: E402
from find_sources import norm  # noqa: E402

WORD = re.compile(rf"[{GREEK}][{GREEK}̀-ͯ’'ʼ᾽]*")


def tidy(g: str) -> str:
    """Drop brackets left unmatched by the cut between Greek and Swedish, and trailing punctuation."""
    stack, drop = [], set()
    for i, c in enumerate(g):
        if c in "([":
            stack.append(i)
        elif c in ")]":
            if stack:
                stack.pop()
            else:
                drop.add(i)
    drop |= set(stack)
    g = "".join(c for i, c in enumerate(g) if i not in drop)
    return re.sub(r"\s+", " ", g).strip(" ,;:·")


def main() -> None:
    entries = [json.loads(l) for l in (ROOT / "text/corrected/entries.jsonl").read_text(encoding="utf-8").splitlines()]
    old = {}
    if (HERE / "examples.jsonl").exists() and (HERE / "match_counts.json").exists():
        counts = json.loads((HERE / "match_counts.json").read_text())
        for line in (HERE / "examples.jsonl").read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if str(e["n"]) in counts:
                old[" ".join(norm(e["greek"]))] = counts[str(e["n"])]
    out = []
    for e in entries:
        head, rest = headword_of(e["text"])
        for _, chunk in Renderer.senses(rest):
            for ph in Renderer.phrases(chunk):
                m = GREEK_RUN.search(ph)
                swedish = ph[:m.start()].strip(" ,") if m else ""
                for run in GREEK_RUN.finditer(ph):
                    for seg in re.split(r"(?<=[\w)])\.\s+", run.group(0)):
                        seg = re.sub(r",\s*(?:ὁ|ἡ|τό|τὸ|οἱ|αἱ|τά)\.?$|,\s*[23]\.?$", "", seg.strip(" .,;")).strip()
                        seg = tidy(seg)
                        n_words = len(WORD.findall(seg))
                        if n_words >= 3:
                            out.append({"n": len(out), "headword": head, "page": e["page"], "swedish": swedish,
                                        "greek": seg, "words": n_words})
    (HERE / "examples.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out),
                                        encoding="utf-8")
    new_counts = {str(x["n"]): old[k] for x in out if (k := " ".join(norm(x["greek"]))) in old}
    (HERE / "match_counts.json").write_text(json.dumps(new_counts))
    print(f"examples {len(out)}; corpus counts carried over for {len(new_counts)}")


if __name__ == "__main__":
    main()
