"""Build the Dictionary.app source of Linder & Walberg's Svenskt-grekiskt lexikon.

Reads the corrected entries (text/corrected/entries.jsonl) and writes
dict/src/LinderWalberg.xml in Apple's Dictionary Development Kit format;
`make` in dict/src then compiles it with build_dict.sh (macOS only). Standard
library only, so it runs on the Mac that builds the bundle.

The print's conventions become typography:

  headword       spaced type in the book; an h1, with its variant forms
                 ("Nedanför(e)", "Nedanifrån, -igenom") indexed separately
  senses         1) a) α) I) start indented blocks, numbers in red, nested by kind
  phrases        the book's ".:" between phrase and phrase: each phrase on its
                 own line, the Swedish in roman, the Greek in bold serif
  derivatives    "— glödande, …" opens a run-in sub-entry with its word in bold
  Greek          every run of Greek in a serif face; articles and termination
                 numbers ("ἄδικος, 2") kept with their word
  abbreviations  the grammatical ones italic as printed, all with their
                 expansion from the book's list as a tooltip
  headword initial  "göra a." (a. = the headword) marked and expanded on hover;
                 only with its full stop or ending ("ö:na"), never the bare
                 letter, which is often a word of its own (the preposition i)
  references     "se X", "Jfr X", "Se vidare X" link to the entry X

Greek words given as equivalents are indexed too, so looking up a Greek word
finds the Swedish entries that render it; words starred as lacking ancient
authority are also indexed under "*"; and so are the headwords' modern
Swedish spellings (dict/modern_spelling.tsv), so "avbryta" finds Afbryta.

    python3 dict/build_xml.py
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

GREEK = "Ͱ-Ͽἀ-῿"
GREEK_CHAR = re.compile(f"[{GREEK}]")
# A run of Greek: from a Greek letter to the last Greek letter (or its
# trailing termination number/article) before Swedish starts again.
GREEK_RUN = re.compile(
    rf"(?:\((?=[{GREEK}]))?[{GREEK}][{GREEK}̀-ͯ’'ʼ᾽\-‐]*"
    rf"(?:(?:[\s,.;·()\-‐]|\d(?=[,.\s)]))+[{GREEK}(][{GREEK}̀-ͯ’'ʼ᾽\-‐)]*)*"
    rf"(?:,\s*[23](?![\d)]))?")
STARRED = re.compile(rf"\*\s?([{GREEK}][{GREEK}\u0300-\u036f]*)")
SENSE = re.compile(r"(?:(?<=^)|(?<=[\s.:;,]))((?:[IVX]+|\d{1,2}|[a-h]|[α-θ]))\)(?=\s)")
STOP_INDEX = {"ὁ", "ἡ", "τό", "τὸ", "οἱ", "αἱ", "τά", "τὰ", "καί", "καὶ", "τι", "τὶ", "τινά", "τινὰ", "τινί", "τινὶ",
              "τινός", "τινὸς", "τινα", "τινι", "τινος", "ἤ", "ἢ", "μή", "μὴ", "οὐ", "οὐκ", "ἐν", "εἰς", "ἐκ", "ἐξ",
              "πρός", "πρὸς", "περί", "περὶ", "ἐπί", "ἐπὶ", "ἀπό", "ἀπὸ", "ὑπό", "ὑπὸ", "παρά", "παρὰ", "διά", "διὰ",
              "κατά", "κατὰ", "μετά", "μετὰ", "ὡς", "τε", "δέ", "δὲ", "γάρ", "γὰρ", "ἄν", "ἂν", "τῶν", "τοῦ", "τῆς",
              "τῷ", "τῇ", "τόν", "τὸν", "τήν", "τὴν", "τοῖς", "ταῖς", "τούς", "τοὺς", "τάς", "τὰς"}


def load_abbreviations() -> tuple[dict[str, str], set[str]]:
    expand, grammatical = {}, set()
    lines = (HERE / "abbreviations.tsv").read_text(encoding="utf-8").splitlines()[1:]
    for line in lines:
        abbr, exp, gram = line.split("\t")
        for a in re.split(r",\s+(?=[^\s,]+\.?$)|,\s+", abbr):
            a = a.strip()
            if a:
                expand[a] = exp
                if gram == "1":
                    grammatical.add(a)
    expand.setdefault("vv.", expand.get("v.", "verbum, -a"))
    return expand, grammatical


ABBR, GRAMMATICAL = load_abbreviations()
# longest first, so "t. ex." wins over "t."; each must stand as a word
ABBR_RE = re.compile(r"(?<![\w.])(" + "|".join(re.escape(a) for a in sorted(ABBR, key=len, reverse=True)) + r")(?![\w])")


def headword_of(text: str) -> tuple[str, str]:
    """The headword and the rest of the entry."""
    # the headword ends at its comma, or at a stop the printer set in its place
    # before the Greek ("Hufvudsats. ἡ πρώτη θέσις")
    m = re.match(rf"([^,;:(]+?(?:\([^)]{{1,4}}\)[^,;:(]*)?)(,\s*|\.\s+(?=[{GREEK}(])|\s+(?=[{GREEK}])|\s+(?=se\s)|\s*(?=\()|$)", text)
    if not m:
        return text.split(" ", 1)[0], text.split(" ", 1)[1] if " " in text else ""
    return m.group(1).strip(), text[m.end():]


def index_forms(head: str, rest: str) -> list[str]:
    """Headword variants to index: "Nedanför(e)", "Sjelf(va)", "Nedanifrån, -igenom"."""
    forms = [re.sub(r"\(([^)]*)\)", "", head), re.sub(r"\(([^)]*)\)", r"\1", head)]
    m = re.match(r"((?:-[a-zåäö]+,\s*)+)", rest)
    if m:
        stem = re.sub(r"\(([^)]*)\)", "", head)
        for suffix in re.findall(r"-([a-zåäö]+)", m.group(1)):
            # replace the last element of a compound: Nedanifrån -> Nedanigenom
            k = max((i for i in range(1, len(stem)) if stem[i:].lower() and suffix[:1] == stem[i:i + 1].lower()),
                    default=None)
            forms.append(stem[:k] + suffix if k else stem + suffix)
    out = {}
    for f in (f.strip() for f in forms):
        if f:
            out.setdefault(fold(f), f)      # one key per form as the index folds it
    return list(out.values())


def load_modern() -> dict[str, list[str]]:
    """Modern Swedish spellings of the 1862 headwords (dict/modern_spelling.tsv),
    keyed by the headword's index forms joined with " | "."""
    path = HERE / "modern_spelling.tsv"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        key, modern = line.split("\t")
        out[key] = [m for m in modern.split(" | ") if m]
    return out


def fold(s: str) -> str:
    """A string as Dictionary.app's index compares it: no case, no accents."""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))


def entry_id(n: int) -> str:
    return f"lw_{n:05d}"


class Renderer:
    def __init__(self, heads: dict[str, str]):
        self.heads = heads          # lower-case headword -> entry id
        self.n = 0                  # the entry being rendered

    def link(self, word: str) -> str:
        # "se Föreg." / "se Följ.": the entry before or after this one
        near = {"Föreg": -1, "Följ": 1}.get(word)
        if near is not None:
            label = {"Föreg": "föregående", "Följ": "följande"}[word]
            return f'<a class="xref" href="x-dictionary:r:{entry_id(self.n + near)}" title="{label}">{word}</a>'
        if word + "." in ABBR or word in ("Lex", "Gram", "Subst", "Nedanf"):
            return f'<span class="abbr">{html.escape(word)}</span>'
        key = re.sub(r"\(([^)]*)\)", "", word).strip().lower()
        target = self.heads.get(key)
        if target:
            return f'<a class="xref" href="x-dictionary:r:{target}">{html.escape(word)}</a>'
        # not a headword as printed: let Dictionary.app search for it
        return f'<a class="xref" href="x-dictionary:d:{html.escape(word.strip("-()"), quote=True)}">{html.escape(word)}</a>'

    def inline(self, text: str, head: str) -> str:
        """Greek, abbreviations, headword initials and references in one phrase."""
        out, pos = [], 0
        for m in GREEK_RUN.finditer(text):
            run = m.group(0).rstrip(" (")          # an opening bracket after Greek starts Swedish
            out.append(self.swedish(text[pos:m.start()], head))
            out.append(self.greek(run))
            pos = m.start() + len(run)
        out.append(self.swedish(text[pos:], head))
        return "".join(out)

    def greek(self, run: str) -> str:
        body = html.escape(run)
        body = re.sub(r",(\s*)([23])$", r',\1<span class="term">\2</span>', body)
        return f'<span class="gk">{body}</span>'

    def swedish(self, text: str, head: str) -> str:
        if not text:
            return ""
        initial = head[:1].lower()
        parts, pos = [], 0
        # cross-references: se X, Jfr X, Se vidare X (X capitalised, possibly a list "X, Y")
        ref = re.compile(r"\b((?:[Ss]e|Jfr|jfr)(?:\s+(?:vidare|äfv\.|under))?\s+)"
                         r"([A-ZÅÄÖ][\wåäöÅÄÖ()\-]+(?:,\s+[A-ZÅÄÖ][\wåäöÅÄÖ()\-]+)*)")
        for m in ref.finditer(text):
            parts.append(self.words(text[pos:m.start()], head, initial))
            parts.append(self.words(m.group(1), head, initial))
            parts.append(", ".join(self.link(w) for w in m.group(2).split(", ")))
            pos = m.end()
        parts.append(self.words(text[pos:], head, initial))
        return "".join(parts)

    def words(self, text: str, head: str, initial: str) -> str:
        out, pos = [], 0
        token = re.compile(ABBR_RE.pattern + rf"|(?<![\w.])({re.escape(initial)}(?::[a-zåäö]+\.?|\.))(?![\w])"
                           if initial.isalpha() else ABBR_RE.pattern)
        for m in token.finditer(text):
            out.append(html.escape(text[pos:m.start()]))
            if m.group(1):
                a = m.group(1)
                cls = "abbr gram" if a in GRAMMATICAL else "abbr"
                out.append(f'<span class="{cls}" title="{html.escape(ABBR[a])}">{html.escape(a)}</span>')
            else:
                # the headword's initial standing for the headword: "göra a.", "ö:na"
                out.append(f'<span class="hw-abbr" title="{html.escape(head)}">{html.escape(m.group(2))}</span>')
            pos = m.end()
        out.append(html.escape(text[pos:]))
        return "".join(out)

    def body(self, text: str, head: str, n: int = 0) -> str:
        """Senses, phrases and derivatives of an entry's text after the headword."""
        self.n = n
        blocks = []
        for marker, chunk in self.senses(text):
            phrases = self.phrases(chunk)
            inner = []
            for k, ph in enumerate(phrases):
                cls = "def" if k == 0 else "phrase"
                deriv = re.match(r"—\s*([a-zåäö][\wåäö\-]*(?:\s+[a-zåäö]+)?),\s*(.*)", ph)
                if deriv:
                    inner.append(f'<div class="deriv"><b class="deriv-word">{html.escape(deriv.group(1))}</b>, '
                                 f'{self.inline(deriv.group(2), head)}</div>')
                elif ph:
                    inner.append(f'<div class="{cls}">{self.inline(ph, head)}</div>')
            if marker is None:
                blocks.append("".join(inner))
            else:
                depth = 0 if re.fullmatch(r"[IVX]+", marker) else 1 if marker.isdigit() else \
                    2 if marker.isascii() else 3
                blocks.append(f'<div class="sense depth-{depth}"><span class="sense-num">{html.escape(marker)})</span>'
                              f'<div class="sense-body">{"".join(inner)}</div></div>')
        return "".join(blocks)

    @staticmethod
    def senses(text: str) -> list[tuple[str | None, str]]:
        """Split at sense markers that open a sense, not those inside a
        reference ("se Bryta 2)") or a parenthesis."""
        starts, last = [], {}
        for m in SENSE.finditer(text):
            before = text[:m.start()].rstrip()
            if before.count("(") > before.count(")"):
                continue                                  # inside brackets
            if re.search(r"[A-ZÅÄÖ][\wåäö]*$", before) or re.search(r"\b(se|Jfr|jfr)\s+\S*\w$", before):
                continue                                  # a reference's sense number
            mark = m.group(1)
            series = "roman" if re.fullmatch(r"[IVX]+", mark) else "digit" if mark.isdigit() else \
                "latin" if mark.isascii() else "greek"
            # the next marker of its series opens a sense even after a plain
            # word ("3) vid orsak a) yttre"); others need punctuation before
            expected = {"digit": str(int(last.get("digit", "0")) + 1),
                        "latin": chr(ord(last.get("latin", "`")) + 1),
                        "greek": chr(ord(last.get("greek", "ΰ")) + 1),
                        "roman": ["I", "II", "III", "IV", "V", "VI"][min(5, len(last.get("roman", "")))]}[series]
            if mark != expected and before and before[-1] not in ".:;,—" \
                    and not re.search(r"\b(?:adv|subst|adj|tr|intr)\.$", before):
                continue
            if series == "digit":                        # a new number restarts its sub-series
                last.pop("latin", None), last.pop("greek", None)
            elif series == "latin":
                last.pop("greek", None)
            last[series] = mark if series != "roman" else last.get("roman", "") + "I"
            starts.append(m)
        if not starts:
            return [(None, text)]
        out = []
        if text[:starts[0].start()].strip():
            out.append((None, text[:starts[0].start()].strip()))
        for k, m in enumerate(starts):
            end = starts[k + 1].start() if k + 1 < len(starts) else len(text)
            out.append((m.group(1), text[m.end():end].strip()))
        return out

    @staticmethod
    def phrases(text: str) -> list[str]:
        """The book's ".:" (or ":" after Greek) separates phrase from phrase;
        " — " before a Swedish word opens a derivative."""
        text = re.sub(r"\s+—\s+(?=[a-zåäöA-ZÅÄÖ])", " \x00— ", text)
        parts = re.split(rf"(?<=\.):\s+|(?<=[{GREEK}̀-ͯ)]):\s+|\x00", text)
        return [p.strip() for p in parts if p and p.strip()]


def keep_spaces(markup: str) -> str:
    """Apple's compiler drops whitespace that stands alone between two tags
    ("<span>ngn</span> <span>i.</span>" shows as "ngni."), so each such space
    moves inside the element it follows."""
    return re.sub(r"((?:</(?:span|a|b|i)>)+)([ \t]+)(?=<)", r"\2\1", markup)


def citation_form(w: str) -> str:
    """A Greek word as one looks it up: the grave of running text made acute,
    and the extra accent an enclitic throws onto it (ἐκδύεσθαί τι) dropped."""
    d = unicodedata.normalize("NFD", w).replace("\u0300", "\u0301")
    accents = [k for k, c in enumerate(d) if c in "\u0301\u0342"]
    if len(accents) == 2:
        d = d[:accents[1]] + d[accents[1] + 1:]
    return unicodedata.normalize("NFC", d)


def greek_index(text: str) -> list[str]:
    """Greek words worth looking up: content words of the entry, in citation form."""
    words = []
    for w in re.findall(rf"[{GREEK}][{GREEK}\u0300-\u036f]+", text):
        w = citation_form(unicodedata.normalize("NFC", w))
        if len(w) >= 3 and w not in STOP_INDEX:
            words.append(w)
    return list(dict.fromkeys(words))


def compile_entries(entries_path: Path, pages: Path, with_greek: bool = True) -> list[dict]:
    """Every entry as {id, title, keys: [(value, label)], html}: the one source
    of the Apple, StarDict and MDict editions."""
    entries = [json.loads(l) for l in entries_path.read_text(encoding="utf-8").splitlines()]
    entries = [e for e in entries if not re.fullmatch(r"[A-ZÅÄÖ][.)]?", e["text"].strip())]   # letter headings
    parsed = []
    heads: dict[str, str] = {}
    for n, e in enumerate(entries):
        head, rest = headword_of(e["text"])
        parsed.append((entry_id(n), head, rest, e))
        for f in index_forms(head, rest):
            heads.setdefault(f.lower(), entry_id(n))
    r = Renderer(heads)
    modern = load_modern()
    out = []
    for eid, head, rest, e in parsed:
        title = re.sub(r"\(([^)]*)\)", "", head)
        forms = index_forms(head, rest)
        keys = [(f, f) for f in forms]
        # the same word in modern spelling (Avbryta for Afbryta) finds it too;
        # Dictionary.app folds case and accents in its index, so a form that
        # differs only so ("Kanon" for the stress-marked "Kánon") is left out
        folded = {fold(f) for f in forms}
        for m in modern.get(" | ".join(forms), []):
            if fold(m) not in folded:
                folded.add(fold(m))
                keys.append((m, title))
        # words the book stars as lacking ancient authority: "*" finds them all,
        # "*τυπογραφεῖον" finds each
        starred = list(dict.fromkeys(citation_form(w) for w in STARRED.findall(rest)))
        if starred:
            keys.append(("*", "*" + ", *".join(starred) + " → " + title))
            keys += [("*" + w, f"*{w} → {title}") for w in starred]
        greek = [(w, f"{w} → {title}") for w in greek_index(rest)] if with_greek else []
        body = (f'<h1 class="hw">{html.escape(head)}</h1>\n'
                f'<div class="entry">{keep_spaces(r.body(rest, head, int(eid[3:])))}</div>\n'
                f'<div class="src">Linder &amp; Walberg 1862, s. {int(e["page"]) - 4}</div>\n')
        out.append({"id": eid, "title": title, "keys": keys, "greek": greek, "html": body})
    where = {}
    for eid, head, rest, e in parsed:
        where.setdefault((fold(head), e["page"]), eid)
        where.setdefault((fold(re.sub(r"\(([^)]*)\)", "", head)), e["page"]), eid)
    return out + front_matter(pages) + index_locorum(where) + author_entries()


def write_apple(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    esc = lambda v: html.escape(v, quote=True)
    with open(path, "w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<d:dictionary xmlns="http://www.w3.org/1999/xhtml" '
                  'xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n')
        for rec in records:
            out.write(f'<d:entry id="{rec["id"]}" d:title="{esc(rec["title"])}">\n')
            for v, label in rec["keys"]:
                out.write(f'<d:index d:value="{esc(v)}" d:title="{esc(label)}"/>\n')
            for v, label in rec.get("greek", []):
                out.write(f'<d:index d:value="{esc(v)}" d:title="{esc(label)}" d:priority="2"/>\n')
            out.write(rec["html"])
            out.write('</d:entry>\n')
        out.write('</d:dictionary>\n')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entries", type=Path, default=ROOT / "text/corrected/entries.jsonl")
    ap.add_argument("--pages", type=Path, default=ROOT / "text/corrected/pages")
    ap.add_argument("--out", type=Path, default=HERE / "src/LinderWalberg.xml")
    ap.add_argument("--no-greek-index", action="store_true")
    args = ap.parse_args()
    records = compile_entries(args.entries, args.pages, not args.no_greek_index)
    write_apple(records, args.out)
    print(f"{sum(r['id'].startswith('lw_') and r['id'][3:].isdigit() for r in records)} entries -> {args.out}")


def index_locorum(where: dict[tuple[str, str], str]) -> list[dict]:
    """The Index locorum entry: ancient authors in alphabetical order (LSJ's
    names and abbreviations), their works, and for each passage the Greek as
    the dictionary gives it with links to the entries that use it."""
    path = ROOT / "locorum/index_locorum.json"
    if not path.exists():
        return []
    authors = json.loads(path.read_text(encoding="utf-8"))
    esc = html.escape

    def link(e: dict) -> str:
        eid = where.get((fold(e["headword"]), e["page"]))
        label = f'{esc(e["headword"])}'
        return (f'<a class="xref" href="x-dictionary:r:{eid}">{label}</a>' if eid else label) + \
            f'<span class="loc-page"> s. {int(e["page"]) - 4}</span>'

    parts, n = [], 0
    for a in authors:
        parts.append(f'<div class="loc-author"><span class="loc-name">{esc(a["name"])}</span> '
                     f'<span class="loc-desc">{esc(a["desc"])}</span> <span class="loc-abbr">[{esc(a["abbr"])}]</span></div>')
        for w in a["works"]:
            if w["abbr"] or w["title"]:
                parts.append(f'<div class="loc-work"><span class="loc-wabbr">{esc(w["abbr"])}</span> '
                             f'{esc(w["title"])}</div>')
            for l in w["loci"]:
                n += 1
                # passages as LSJ gives them: "18.200" for a speech, "1.2.3" for book, chapter, section
                cites = [f'{w["abbr"]}.{c}' if w["abbr"].isdigit() and c else c for c in l.get("cites", [])]
                cite = f'<span class="loc-cite">{esc(", ".join(cites))}</span> ' if cites else ""
                parts.append(f'<div class="locus">{cite}<span class="gk">{esc(l["greek"])}</span> → '
                             + ", ".join(link(e) for e in l["entries"]) + '</div>')
    intro = (f'<p class="note">{n} grekiska exempel ur lexikonet, återfunna ordagrant hos {len(authors)} antika '
             'författare, i alfabetisk ordning med namn och förkortningar enligt LSJ. Ställena är sökta i de grekiska '
             'texterna i Perseus och First1KGreek, och hänvisningarna följer dessa utgåvors indelning. Varje ställe '
             'länkar till de artiklar där exemplet står. Fraser som förekommer hos fler än tre författare räknas som '
             'gängse uttryck och är inte med.</p>')
    return [{"id": "lw_locorum", "title": "Index locorum",
             "keys": [("Index locorum", "Index locorum"), ("Ställeregister", "Index locorum")],
             "html": f'<h1 class="hw">Index locorum</h1>\n{intro}<div class="loci">{keep_spaces("".join(parts))}</div>\n'}]


def author_entries() -> list[dict]:
    """The two authors, from their articles in Svenskt biografiskt handlexikon
    (1906; dict/authors.json, transcribed from the scans at Project Runeberg),
    with the book's portraits (src/OtherResources/Images)."""
    path = HERE / "authors.json"
    if not path.exists():
        return []
    targets = {"linder": "lw_linder", "walberg": "lw_walberg", "lexikon": "front_matter"}
    out = []
    for a in json.loads(path.read_text(encoding="utf-8")):
        text = re.sub(r"\{(\w+):([^}]+)\}",
                      lambda m: f'<a href="x-dictionary:r:{targets[m.group(1)]}">{m.group(2)}</a>', a["html"])
        last, first = a["sort"].split(", ")
        note = f' Rättat: {html.escape(a["corrections"])}.' if a.get("corrections") else ""
        credit = (f'<p class="note">Ur {html.escape(a["source"])}, efter faksimilet hos '
                  f'<a href="{html.escape(a["url"], quote=True)}">Project Runeberg</a>.{note}</p>')
        img = (f'<img class="portrait" src="Images/{a["image"]}" alt="{html.escape(a["name"], quote=True)}"/>'
               if a.get("image") else "")
        out.append({"id": a["id"], "title": a["sort"],
                    "keys": [(a["sort"], a["sort"]), (a["name"], a["sort"]), (last, a["sort"])],
                    "html": keep_spaces(f'<h1 class="hw">{html.escape(a["name"])}</h1>\n<div class="front bio">{img}'
                                        f'<p>{text}</p>{credit}</div>\n')})
    return out


def front_matter(pages: Path) -> list[dict]:
    """The title page, preface and list of abbreviations as entries of their own."""
    def paras(p: str) -> str:
        text = (pages / f"{p}.txt").read_text(encoding="utf-8") if (pages / f"{p}.txt").exists() else ""
        return "".join(f"<p>{html.escape(x.strip())}</p>" for x in text.split("\n\n") if x.strip())
    preface = paras("0003") + paras("0004")
    rows = "".join(
        f'<tr><td class="abbr-col">{html.escape(a)}</td><td>{html.escape(x)}</td></tr>'
        for a, x, _ in (l.split("\t") for l in (HERE / "abbreviations.tsv").read_text(encoding="utf-8").splitlines()[1:]))
    return [
        {"id": "front_matter", "title": "Svenskt-grekiskt lexikon",
         "keys": [("Svenskt-grekiskt lexikon", "Svenskt-grekiskt lexikon"), ("Linder Walberg", "Linder Walberg")],
         "html": '<h1 class="hw">Svenskt-grekiskt lexikon</h1>\n'
                 '<div class="front"><p class="byline">af <a href="x-dictionary:r:lw_linder">C. W. Linder</a> och <a href="x-dictionary:r:lw_walberg">C. A. Walberg</a>. Upsala 1862.</p>'
                 '<p>Uppslag på svenska ord; grekiska ord söks fram till de svenska artiklar som återger dem. '
                 'Se <a href="x-dictionary:r:lw_preface">Förord</a>, <a href="x-dictionary:r:lw_abbr">Förkortningar</a> '
                 'och <a href="x-dictionary:r:lw_locorum">Index locorum</a>.</p>'
                 '<p class="note">Texten är korrekturläst mot sidbilderna; tryckfel är rättade enligt bokens '
                 'tryckfelsförteckning och en formell granskning av grekiskan. Ordet efter * saknar auktoritet hos de '
                 'gamle författarne.</p></div>\n'},
        {"id": "lw_preface", "title": "Förord", "keys": [("Förord", "Förord")],
         "html": f'<h1 class="hw">Förord</h1>\n<div class="front">{preface}</div>\n'},
        {"id": "lw_abbr", "title": "Förkortningar", "keys": [("Förkortningar", "Förkortningar")],
         "html": f'<h1 class="hw">Förkortningar</h1>\n<table class="abbrs">{rows}</table>\n'},
    ]


if __name__ == "__main__":
    main()
