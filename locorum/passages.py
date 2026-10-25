"""Passage references for the loci, from the TEI editions of Perseus
(canonical-greekLit) and First1KGreek.

Each edition is read in document order and every word gets the citation
in force where it stands: the n of each enclosing textpart division (book,
chapter, section), a Stephanus milestone for Plato ("17a" within page 17),
the line number in verse. Notes, headings and the apparatus are skipped. A
locus is then searched, word for word as find_sources.py matched it, in its
own work or, when only the author is known, in all the author's works; the
citation of its first word is the passage.

Editions are cached as token streams in ocr_runs/tei/cache.
"""

from __future__ import annotations

import functools
import pickle
import re
import xml.sax
from pathlib import Path

from find_sources import WILD, norm

ROOT = Path(__file__).resolve().parent.parent
TEI = ROOT / "ocr_runs/tei"
CACHE = TEI / "cache"
SKIP = {"note", "head", "teiHeader", "bibl", "app", "rdg", "del", "ref", "label", "figure", "speaker"}


class Reader(xml.sax.ContentHandler):
    def __init__(self):
        super().__init__()
        self.divs: list[str | None] = []     # n of each open div (None for non-textpart divs)
        self.milestone: str | None = None    # Stephanus-type section within the innermost div
        self.line: str | None = None
        self.skip = 0
        self.in_body = False
        self.tokens: list[str] = []
        self.cites: list[str] = []

    def cite(self) -> str:
        parts = [d for d in self.divs if d]
        if self.milestone:
            parts = parts[:-1] + [self.milestone] if parts else [self.milestone]
        if self.line:
            parts = parts + [self.line]
        return ".".join(parts)

    def startElement(self, name, attrs):
        name = name.split(":")[-1]
        if name == "body":
            self.in_body = True
        if name in SKIP:
            self.skip += 1
        elif name == "div":
            self.divs.append(attrs.get("n") if attrs.get("type") in ("textpart", "edition") and
                             attrs.get("type") == "textpart" else None)
            self.milestone = None
            self.line = None
        elif name == "milestone" and attrs.get("unit") == "section" and attrs.get("n"):
            self.milestone = attrs.get("n")
        elif name == "l" and attrs.get("n"):
            self.line = attrs.get("n")
        elif name == "lb" and attrs.get("n") and self.line is not None:
            self.line = attrs.get("n")

    def endElement(self, name):
        name = name.split(":")[-1]
        if name in SKIP:
            self.skip -= 1
        elif name == "div" and self.divs:
            self.divs.pop()
            self.milestone = None
        elif name == "l":
            pass                                  # keep the last line number until the next <l n>

    def characters(self, content):
        if not self.in_body or self.skip:
            return
        toks = norm(content)
        if toks:
            c = self.cite()
            self.tokens += toks
            self.cites += [c] * len(toks)


@functools.lru_cache(maxsize=None)
def edition(path: Path) -> tuple[list[str], list[str]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (path.name + ".pkl")
    if cached.exists():
        return pickle.loads(cached.read_bytes())
    r = Reader()
    parser = xml.sax.make_parser()
    parser.setFeature(xml.sax.handler.feature_external_ges, False)
    parser.setContentHandler(r)
    try:
        parser.parse(str(path))
    except xml.sax.SAXException:
        pass
    cached.write_bytes(pickle.dumps((r.tokens, r.cites)))
    return r.tokens, r.cites


def editions(group: str, work: str | None = None) -> list[tuple[str, Path]]:
    """(tlg work key, file) for every Greek edition of a group (or one work); Perseus first."""
    out = []
    for repo in ("canonical-greekLit", "First1KGreek"):
        base = TEI / repo / "data" / group
        for f in sorted(base.glob(f"{work or '*'}/*grc*.xml")):
            out.append((f"{group}.{f.parent.name}", f))
    return out


def pattern(greek: str) -> list[str | None]:
    return [None if t in WILD else t for t in norm(greek)]


def find(pat: list[str | None], tokens: list[str]) -> int | None:
    fixed = [(j, p) for j, p in enumerate(pat) if p is not None]
    if len(fixed) < 2:
        return None
    j0, p0 = max(fixed, key=lambda x: len(x[1]))         # the longest fixed word as anchor
    start = 0
    while True:
        try:
            i = tokens.index(p0, start)
        except ValueError:
            return None
        s = i - j0
        if s >= 0 and s + len(pat) <= len(tokens) and all(p is None or p == tokens[s + j] for j, p in enumerate(pat)):
            return s
        start = i + 1


def locate(greek: str, groups: list[str], work: str | None = None) -> tuple[str, str] | None:
    """(tlg work key, citation) of the first edition where the phrase occurs."""
    pat = pattern(greek)
    candidates = []
    for g in groups:
        candidates += editions(g, work.split(".")[1] if work and work.startswith(g + ".") else None)
    for key, f in candidates:
        toks, cites = edition(f)
        s = find(pat, toks)
        if s is not None:
            return key, cites[s]
    return None
