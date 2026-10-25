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


def bare_words(s: str) -> list[str]:
    return [" ".join(norm(w)) for w in WORD.findall(s)]


def complete(base: str, alt: str) -> str:
    """An alternative after "l." that begins with a word of the phrase before it
    replaces that phrase only from that word on, and is completed with what
    comes before it there: "διαφορὰ ἡ περὶ τὰ θεῖα l. περὶ τὴν τῶν θεῶν
    θεραπείαν" gives "διαφορὰ ἡ περὶ τὴν τῶν θεῶν θεραπείαν"."""
    a, b = bare_words(alt), bare_words(base)
    if not a or a[0] not in b[1:]:
        return alt
    k = b.index(a[0], 1)
    return base[:list(WORD.finditer(base))[k].start()] + alt


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
                found = list(GREEK_RUN.finditer(ph))
                segs = [re.split(r"(?<=[\w)])\.\s+", r.group(0)) for r in found]
                # an alternative after "l." (the first segment of a run) is completed from
                # the phrase it replaces part of (the last segment of the run before;
                # in a chain A l. B l. C, from A)
                base = None
                for i in range(1, len(found)):
                    if re.fullmatch(r"\s*l\.\s*", ph[found[i - 1].end():found[i].start()]):
                        base = base if base is not None and len(segs[i - 1]) == 1 else segs[i - 1][-1]
                        segs[i][0] = complete(base, segs[i][0])
                    else:
                        base = None
                for run in segs:
                    for seg in run:
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
