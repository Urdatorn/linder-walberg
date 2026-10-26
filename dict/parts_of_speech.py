"""Parts of speech of the headwords, for the Partes orationis index: each headword
in its modern spelling (modern_spelling.tsv) looked up in SALDO's morphology
(Språkbanken; the index written by saldo_index.py):

  1. a base form: its parts of speech in SALDO (several for homographs: "för" is
     a preposition, a conjunction and an adverb);
  2. a participle form of a verb with a participle's ending ("avbruten",
     "brinnande", "ledad"): participium;
  3. otherwise a compound SALDO lacks: the part of speech of its longest final
     element that SALDO has ("barnamord" from "mord"), since a Swedish
     compound takes its class from its last part.

Only parts of speech that are themselves headwords of the dictionary are kept
(dict/parts_of_speech.tsv is read by build_xml.py):

    python dict/parts_of_speech.py /path/to/saldo_index.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_xml import entry_id, headword_of, index_forms, load_modern  # noqa: E402

# SALDO's parts of speech -> the dictionary's own headwords for them
CLASSES = {
    "nn": "Substantiv", "nnm": "Substantiv",
    "av": "Adjektiv", "avm": "Adjektiv",
    "ab": "Adverb", "abm": "Adverb",
    "pp": "Preposition", "ppm": "Preposition",
    "pn": "Pronomen", "pnm": "Pronomen",
    "kn": "Konjunktion", "knm": "Konjunktion", "sn": "Konjunktion", "snm": "Konjunktion",
    "nl": "Räkneord", "nlm": "Räkneord",
    "al": "Artikel",
}
PARTICIPLE = "Participium"
ORDER = ["Adjektiv", "Adverb", "Artikel", "Konjunktion", "Participium", "Preposition", "Pronomen", "Räkneord", "Substantiv"]


# 1862 spelt hvad, hvar, hvi, hvass, hviska with hv-; in modern spelling they meet
# other headwords (vad 'ford', var 'pus', vi 'we', vass 'reed'), which SALDO cannot tell apart
OVERRIDES = {
    "Hvad": ["Adverb", "Pronomen"], "Vad": ["Substantiv"],
    "Hvar": ["Adverb", "Pronomen"], "Var": ["Substantiv"],
    "Hvi": ["Adverb"], "Vi": ["Pronomen"],
    "Hvass": ["Adjektiv"], "Vass": ["Substantiv"],
    "Hviska": [], "Viska": ["Substantiv"],
}

# a participle has a participle's ending; SALDO's participle forms also include
# plain adjectives that happen to coincide with one (bred, mätt, sank)
PARTICIPLE_ENDING = ("ande", "ende", "ad", "ade", "at", "en", "et", "na", "dt")


def participle(f: str, lemmas: dict, participles: dict, adjectival: bool) -> bool:
    """A participle form with a participle's ending. Where SALDO also has it as a
    noun (brinnande, döende), the entry decides: its Greek with an adjective's
    terminations (", 3.") is a participle, with an article (ὁ, ἡ, τό) a verbal noun."""
    if f not in participles or not f.endswith(PARTICIPLE_ENDING):
        return False
    own = set(lemmas.get(f, []))
    return own <= {"av", "avm"} or (own <= {"av", "avm", "nn"} and adjectival)


OPEN = {"Substantiv", "Adjektiv"}
# a compound keeps a closed class only when its first part is of a kind that forms
# such compounds: bak-före, nedan-efter (prepositions, adverbs), fem-tusen (numerals)
FIRST_PART = {"Preposition": {"pp", "ab"}, "Adverb": {"pp", "ab"}, "Räkneord": {"nl"}}


def classify(form: str, lemmas: dict, participles: dict, adjectival: bool = False) -> tuple[list[str], str]:
    f = form.lower()
    found = {CLASSES[p] for p in lemmas.get(f, []) if p in CLASSES}
    # a participle form, unless the form is also a word of another class ("vad", "så")
    if participle(f, lemmas, participles, adjectival):
        found.add(PARTICIPLE)
    if found or f in lemmas:
        return sorted(found), "saldo"
    if " " in f:
        # a phrase SALDO lacks ("tyga till", "flaga sig"): the class of its first word
        first = f.split()[0]
        if first in lemmas or first in participles:
            classes, _ = classify(first, lemmas, participles, adjectival)
            return classes, f"phrase:{first}"
        return [], "none"
    # a compound: its longest final element in SALDO (at least three letters)
    for k in range(1, len(f) - 2):
        head, tail = f[:k], f[k:]
        if tail in lemmas:
            keep = set()
            for p in lemmas[tail]:
                c = CLASSES.get(p)
                if c in OPEN or (c in FIRST_PART and set(lemmas.get(head, [])) & FIRST_PART[c]):
                    keep.add(c)
            if participle(tail, lemmas, participles, adjectival):
                keep.add(PARTICIPLE)
            return sorted(keep), f"compound:{tail}"
    return [], "none"


def main() -> None:
    index = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    lemmas, participles = index["lemmas"], index["participles"]
    modern = load_modern()
    rows = []
    for n, line in enumerate((HERE.parent / "text/corrected/entries.jsonl").read_text(encoding="utf-8").splitlines()):
        e = json.loads(line)
        head, rest = headword_of(e["text"])
        forms = index_forms(head, rest)
        title = re.sub(r"\(([^)]*)\)", "", head).strip()
        # the modern spelling where there is one; a "se X" entry is classed all the same
        candidates = modern.get(" | ".join(forms), []) + [title]
        # the Greek of the first sense declined as an adjective ("ἄκαυστος, 2.")
        adjectival = bool(re.search(r",\s*[23]\b", rest[:250]))
        classes, how, used = [], "none", title
        for c in candidates:
            if not re.fullmatch(r"[A-Za-zÅÄÖåäöéÉüÜ\- ]+", c):
                continue
            classes, how = classify(c, lemmas, participles, adjectival)
            used = c
            if how != "none":
                break
        if title in OVERRIDES:
            classes, how = OVERRIDES[title], "override"
        if len(title) == 1:
            classes = [c for c in classes if c != "Räkneord"]
        rows.append((entry_id(n), title, used, ",".join(classes), how))
    out = HERE / "parts_of_speech.tsv"
    out.write_text("id\theadword\tlooked_up\tclasses\tmethod\n"
                   + "".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    counts = {c: sum(c in r[3].split(",") for r in rows) for c in ORDER}
    how = {}
    for r in rows:
        k = r[4].split(":")[0]
        how[k] = how.get(k, 0) + 1
    print(len(rows), "entries;", how)
    print(counts)


if __name__ == "__main__":
    main()
