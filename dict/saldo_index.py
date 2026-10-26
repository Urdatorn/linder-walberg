"""A compact index of SALDO's morphology (Språkbanken, saldom.xml): every base form
with its parts of speech, and every participle form with its verb. Read by
parts_of_speech.py; the index is cached next to saldom.xml.

    python dict/saldo_index.py /path/to/saldom.xml
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def build(saldom: Path) -> dict:
    lemmas: dict[str, set[str]] = {}
    participles: dict[str, set[str]] = {}
    lemma, pos = None, None
    for _, el in ET.iterparse(saldom, events=("end",)):
        if el.tag == "FormRepresentation":
            feats = {f.get("att"): f.get("val") for f in el.iter("feat")}
            written, pos = feats.get("writtenForm", ""), feats.get("partOfSpeech", "")
            lemma = written.lower()
            # Roman numerals (VI, X, L) would make "vi", "x", "l" numerals once lower-cased
            if not (pos.startswith("nl") and written.isupper()):
                lemmas.setdefault(lemma, set()).add(pos)
        elif el.tag == "WordForm" and pos in ("vb", "vbm"):
            feats = {f.get("att"): f.get("val") for f in el.iter("feat")}
            if feats.get("msd", "").startswith(("pres_part", "pret_part")):
                participles.setdefault(feats["writtenForm"].lower(), set()).add(lemma)
        elif el.tag == "LexicalEntry":
            el.clear()
    return {"lemmas": {k: sorted(v) for k, v in lemmas.items()},
            "participles": {k: sorted(v) for k, v in participles.items()}}


if __name__ == "__main__":
    src = Path(sys.argv[1])
    index = build(src)
    out = src.with_name("saldo_index.json")
    out.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"{len(index['lemmas'])} base forms, {len(index['participles'])} participle forms -> {out}")
