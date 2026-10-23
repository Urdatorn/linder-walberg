"""Clean an OCR run into the diplomatic text of the dictionary.

The model's output is close to the print but carries its training markup and
a few systematic faults; Project Runeberg's 2013 OCR of the same scans
(runeberg_txt/Pages) reads Swedish and punctuation well and Greek badly, the
reverse of the model. Each strip is cleaned on its own, then each page is
aligned word by word with Runeberg's text and the two are merged where one
source is known to be stronger:

  markup       <tab/> and "#" mark paragraph starts and are dropped;
               <ref>N</ref> is a sense number "N)" or, after a Greek
               adjective, a number of terminations ("ἄδικος, 2");
               <note>…</note> and stray tags are unwrapped
  hyphens      "κῆ‐ πος" (a line-break hyphen the model kept) is joined
  mixed script a word mostly in one script has its look-alike letters from
               the other mapped back ("Κöl" -> "Köl", "αὐτούς" with a Latin o)
  Runeberg     a Greek-script word where Runeberg has a similar Swedish word
               is replaced by it ("μάνεν" -> "månen"); a Latin word unknown to
               the book's Swedish vocabulary is replaced by Runeberg's reading
               when that is known and similar ("fletet" -> "fältet"); ".:",
               which the model often shortens to "." or ":", is restored
  headwords    a headword left in Greek letters is replaced by Runeberg's

Every change is logged with its reason, so the proofreading step can see
what the cleaner did. Pages listed in manual/ override strips by hand.

    python clean.py ocr_runs/full3 --out text
"""

from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
import unicodedata
from pathlib import Path

import regex

GREEK_CHAR = regex.compile(r"[\p{Greek}]")
LATIN_CHAR = regex.compile(r"[\p{Latin}]")
TOKEN = regex.compile(r"[\p{L}\p{M}\p{N}]+(?:['’ʼ][\p{L}\p{M}]*)?|[^\p{L}\p{M}\p{N}\s]")
WORD = regex.compile(r"^[\p{L}\p{M}]")

# Letters of one script that look like letters of the other. A word written
# mostly in one script has stray letters from the other mapped with these.
GREEK_TO_LATIN = str.maketrans({
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N",
    "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o", "ν": "v", "ι": "i", "κ": "k",
    "τ": "t", "α": "a", "ρ": "p", "υ": "u", "χ": "x", "ϲ": "c",
})
LATIN_TO_GREEK = str.maketrans({
    "A": "Α", "B": "Β", "E": "Ε", "Z": "Ζ", "H": "Η", "I": "Ι", "K": "Κ", "M": "Μ", "N": "Ν",
    "O": "Ο", "P": "Ρ", "T": "Τ", "Y": "Υ", "X": "Χ", "o": "ο", "v": "ν", "i": "ι", "k": "κ",
    "a": "α", "p": "ρ", "u": "υ", "x": "χ", "w": "ω",
})
# Swedish has no grave, acute or macron on a: the model's "Pàlitlig", "pā" are å.
LATIN_ACCENT_FIX = {"à": "å", "á": "å", "ā": "å", "â": "å", "À": "Å", "Á": "Å", "ō": "ö", "ò": "ö"}

# Skeleton: a reading of a word in either script reduced to what the eye
# confuses, so a Swedish word the model put in Greek letters ("μάνεν") and
# Runeberg's Latin reading ("månen") come out the same.
SKELETON = str.maketrans({
    "Α": "a", "Β": "b", "Γ": "g", "Δ": "d", "Ε": "e", "Ζ": "z", "Η": "h", "Θ": "t", "Ι": "i",
    "Κ": "k", "Λ": "l", "Μ": "m", "Ν": "n", "Ξ": "x", "Ο": "o", "Π": "p", "Ρ": "p", "Σ": "s",
    "Τ": "t", "Υ": "y", "Φ": "f", "Χ": "x", "Ψ": "ps", "Ω": "o",
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "n", "θ": "t", "ι": "i",
    "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "u", "φ": "f", "χ": "x", "ψ": "ps", "ω": "o", "ϑ": "t",
    "v": "n", "y": "u", "c": "k", "q": "k", "w": "n", "j": "i",
})

HYPHEN_JOIN = re.compile(r"(?<=[^\W\d_])[-‐]\s+(?=[^\W\d_])")
# Words after which a hyphen and space are a real suspended compound ("fram- o. tillbaka").
SUSPENDED = re.compile(r"(?:o|l|och|eller|s|el|samt|äfv|resp)\b\.?")


def strip_marks(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def skeleton(tok: str) -> str:
    return strip_marks(tok).translate(SKELETON).lower().replace("-", "").replace("‐", "")


def script(tok: str) -> str:
    g, l = len(GREEK_CHAR.findall(tok)), len(LATIN_CHAR.findall(tok))
    return "greek" if g > l else "latin" if l > g else ("mixed" if g else "other")


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ---------------------------------------------------------------- markup

REF = re.compile(r"<ref>(.*?)</ref>")
NOTE = re.compile(r"</?note>")
OTHER_TAG = re.compile(r"</?[a-z]+/?>")


def convert_ref(m: re.Match) -> str:
    x, before, after = m.group(1).strip(), m.string[:m.start()], m.string[m.end():]
    if re.fullmatch(r"\d+", x):
        # "ἄδικος, 2" (two terminations) after a Greek word and a comma; "2)" otherwise.
        prev = re.search(r"(\S+)\s*,\s*$", before)
        if x in ("2", "3") and prev and script(prev.group(1)) == "greek":
            return x
        return x if after.startswith(")") else x + ")"
    if re.fullmatch(r"[a-d]|[α-δ]|[IVX]+", x):      # letter headings ("A") stay bare
        return x if after.startswith(")") else x + ")"
    if x == "l":
        return "l." if not after.startswith(".") else "l"
    return x


def convert_markup(text: str) -> list[tuple[bool, str]]:
    """Paragraphs of a strip, each with whether it was marked as a new entry."""
    paras = []
    for i, p in enumerate(re.split(r"\n\s*\n", text.strip())):
        p = p.strip()
        if not p:
            continue
        marked = bool(re.match(r"(<tab/?>|#)", p))
        p = re.sub(r"^(?:#+\s*|<tab/?>\s*)+", "", p)
        p = re.sub(r"\s*<tab/?>\s*", " ", p)
        p = REF.sub(convert_ref, p)
        p = re.sub(r"<note>(.*?)</note>(?=\S)", r"\1 ", p)
        p = NOTE.sub("", p)
        p = OTHER_TAG.sub("", p)
        p = re.sub(r"[ \t]+", " ", p.replace("\n", " ")).strip()
        if p:
            # A paragraph after a blank line is a new entry even unmarked; a
            # strip's first unmarked paragraph continues the column above.
            paras.append((marked or i > 0, p))
    return paras


def join_hyphens(text: str) -> str:
    def repl(m: re.Match) -> str:
        return m.group(0) if SUSPENDED.match(text, m.end()) else ""
    return HYPHEN_JOIN.sub(repl, text)


def fix_word_script(tok: str) -> str:
    g, l = len(GREEK_CHAR.findall(tok)), len(LATIN_CHAR.findall(tok))
    if g and l:
        if l >= g:
            tok = unicodedata.normalize("NFC", strip_marks(tok).translate(GREEK_TO_LATIN)) \
                if not any(c in tok for c in "åäöÅÄÖ") else "".join(
                    c if not GREEK_CHAR.match(c) else strip_marks(c).translate(GREEK_TO_LATIN) for c in tok)
        else:
            tok = "".join(c.translate(LATIN_TO_GREEK) if LATIN_CHAR.match(c) else c for c in tok)
    if LATIN_CHAR.search(tok) and not GREEK_CHAR.search(tok):
        tok = "".join(LATIN_ACCENT_FIX.get(c, c) for c in unicodedata.normalize("NFC", tok))
    return tok


def fix_scripts(text: str) -> str:
    return TOKEN.sub(lambda m: fix_word_script(m.group(0)), text)


# ---------------------------------------------------------------- Runeberg

RB_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def load_runeberg(path: Path) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").split("\n")
    # Drop the page number and running head ("346", "Påkalla —Påtränga.") at the top.
    body, dropped = [], 0
    for line in lines:
        s = line.strip()
        if dropped < 3 and not body and (not s or re.fullmatch(r"\d+", s)
                                         or (("—" in s or " - " in s) and len(s) < 45)):
            dropped += bool(s)
            continue
        body.append(line)
    text = RB_TAG.sub("", "\n".join(body))
    text = re.sub(r"(?<=[^\W\d_])-\n(?=[^\W\d_])", "", text)
    return unicodedata.normalize("NFC", text)


def tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(0)) for m in TOKEN.finditer(text)]


def align(a: list[str], b: list[str]) -> list[tuple[int | None, int | None]]:
    """Token alignment: exact skeleton matches as anchors, small DP between them."""
    pairs: list[tuple[int | None, int | None]] = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            pairs += [(i1 + k, j1 + k) for k in range(i2 - i1)]
        elif op == "delete":
            pairs += [(i, None) for i in range(i1, i2)]
        elif op == "insert":
            pairs += [(None, j) for j in range(j1, j2)]
        elif (i2 - i1) * (j2 - j1) > 6000 or max(i2 - i1, j2 - j1) > 3 * min(i2 - i1, j2 - j1) + 2:
            # Too large, or one side mostly unmatched text (a strip aligned
            # against the whole page): leave unpaired rather than guess.
            pairs += [(i, None) for i in range(i1, i2)] + [(None, j) for j in range(j1, j2)]
        else:
            pairs += dp_align(a[i1:i2], b[j1:j2], i1, j1)
    return pairs


def dp_align(a, b, oa, ob):
    """Needleman-Wunsch over two short token runs, scored by skeleton similarity."""
    n, m = len(a), len(b)
    gap = -0.4
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]     # 0 diagonal, 1 up (gap in b), 2 left
    for i in range(1, n + 1):
        score[i][0], back[i][0] = gap * i, 1
    for j in range(1, m + 1):
        score[0][j], back[0][j] = gap * j, 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            options = (score[i - 1][j - 1] + similarity(a[i - 1], b[j - 1]) * 2 - 1,
                       score[i - 1][j] + gap, score[i][j - 1] + gap)
            back[i][j] = max(range(3), key=options.__getitem__)
            score[i][j] = options[back[i][j]]
    out = []
    i, j = n, m
    while i or j:
        move = back[i][j]
        if move == 0:
            out.append((oa + i - 1, ob + j - 1))
            i, j = i - 1, j - 1
        elif move == 1:
            out.append((oa + i - 1, None))
            i -= 1
        else:
            out.append((None, ob + j - 1))
            j -= 1
    return out[::-1]


class Merger:
    """Word-level merge of the model's page text with Runeberg's."""

    def __init__(self, swedish: collections.Counter, greek_known, ours: collections.Counter,
                 headwords: set[str]):
        self.swedish = swedish          # Latin-script word -> count in Runeberg's text
        self.greek_known = greek_known  # callable: is this Greek form attested?
        self.ours = ours                # Latin-script word -> count in the model's text
        self.headwords = headwords      # the model's headwords, targets of "se X"

    @staticmethod
    def latin_context(ta, i) -> bool:
        """A real Greek word ("ὅδε", "εν") is taken for Swedish only between Swedish words."""
        def neighbour(step):
            k = i + step
            while 0 <= k < len(ta) and not (WORD.match(ta[k][2]) and len(ta[k][2]) > 1):
                k += step
            return script(ta[k][2]) if 0 <= k < len(ta) else "latin"
        return neighbour(-1) == "latin" and neighbour(1) == "latin"

    def known_swedish(self, w: str, n: int = 2) -> bool:
        return self.swedish[w] >= n or self.swedish[w.lower()] >= n

    def merge(self, text: str, rb: str) -> tuple[str, list[dict]]:
        if not rb.strip():
            return text, []
        ta, tb = tokens(text), tokens(rb)
        pairs = align([skeleton(t[2]) for t in ta], [skeleton(t[2]) for t in tb])
        rb_of = {i: j for i, j in pairs if i is not None and j is not None}
        edits: dict[int, tuple[str, str]] = {}   # our token index -> (new text, reason)
        for i, j in rb_of.items():
            ours, theirs = ta[i][2], tb[j][2]
            if ours == theirs or not WORD.match(ours) or not WORD.match(theirs):
                continue
            so, st = script(ours), script(theirs)
            sim = similarity(skeleton(ours), skeleton(theirs))
            if not 0.67 <= len(theirs) / len(ours) <= 1.5:
                continue        # "pens" against "kroppens": a word split differently
            # Runeberg reads some Greek as Latin ("dia" for δια-, "ode" for
            # ὅδε), so its word must also occur in the model's Swedish.
            seen = self.ours[theirs] >= 1 or self.ours[theirs.lower()] >= 1
            if so == "greek" and st == "latin" and len(theirs) >= 2 and seen and (
                    (sim >= 0.7 and not self.greek_known(ours) and self.known_swedish(theirs))
                    or (sim >= 0.8 and self.known_swedish(theirs, 5) and self.latin_context(ta, i))):
                edits[i] = (theirs, "swedish_in_greek")
            elif so == "latin" and st == "latin" and sim >= 0.6 and len(ours) >= 3 \
                    and not self.known_swedish(ours, 1) and ours not in self.headwords \
                    and self.known_swedish(theirs, 3) and (seen or self.known_swedish(theirs, 10)):
                edits[i] = (theirs, "swedish_unknown_word")
        # ".:" where the model wrote "." or ":", next to a word both sources agree on.
        for i, j in rb_of.items():
            ours = ta[i][2]
            if ours not in (".", ":") or j + 1 >= len(tb):
                continue
            if tb[j][2] == "." and tb[j + 1][2] == ":" and ours == "." and (i + 1 >= len(ta) or ta[i + 1][2] != ":"):
                follow = next((k for k in range(i + 1, min(i + 3, len(ta))) if WORD.match(ta[k][2])), None)
                if follow is not None and rb_of.get(follow) in (j + 2, j + 3):
                    edits[i] = (".:", "full_stop_colon")
            elif ours == ":" and j >= 1 and tb[j - 1][2] == "." and tb[j][2] == ":" and (i == 0 or ta[i - 1][2] != "."):
                if rb_of.get(i - 1) is not None and tb[rb_of[i - 1]][2] != ".":
                    edits[i] = (".:", "full_stop_colon")
        log, out, pos = [], [], 0
        for i, (s, e, t) in enumerate(ta):
            if i in edits:
                new, why = edits[i]
                out.append(text[pos:s] + new)
                pos = e
                log.append({"from": t, "to": new, "why": why, "context": text[max(0, s - 30):e + 30]})
        out.append(text[pos:])
        return "".join(out), log


# ---------------------------------------------------------------- driver


def greek_lexicon(path: Path, min_count: int = 2):
    import pandas as pd
    df = pd.read_parquet(path, columns=["form", "count"])
    df = df[df["count"] >= min_count]
    counts = dict(zip(df["form"].map(lambda s: unicodedata.normalize("NFC", s)), df["count"]))

    def known(w: str, n: int = min_count) -> bool:
        """Whether a Greek form occurs at least n times in the AncientGreek corpus.

        The corpus has its own noise ("ἀδελ" 439 times, an abbreviation), so
        a Swedish reading that is clearly better can override a rare form.
        """
        return count(w) >= n

    def count(w: str) -> int:
        w = unicodedata.normalize("NFC", w).rstrip("'’ʼ᾽")    # elided forms are stored bare
        return max(counts.get(w, 0), counts.get(w.lower(), 0), counts.get(grave_to_acute(w), 0))

    known.count = count
    return known


def grave_to_acute(w: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", w).replace("̀", "́"))


def swedish_vocabulary(rb_dir: Path) -> collections.Counter:
    c = collections.Counter()
    for f in sorted(rb_dir.glob("*.txt")):
        for _, _, t in tokens(load_runeberg(f)):
            if WORD.match(t) and script(t) == "latin":
                c[t] += 1
    return c


def load_manual(manual: Path) -> dict[tuple[str, int], str]:
    out = {}
    for f in sorted(manual.glob("*_*.txt")):
        page, n = f.stem.split("_")
        out[(page, int(n))] = f.read_text(encoding="utf-8").rstrip("\n")
    return out


def clean_page(page: dict, manual: dict, merger: Merger | None, rb: str) -> tuple[list[dict], str, list[dict]]:
    strips, log = [], []
    for s in page["strips"]:
        if s["kind"] == "head":
            continue
        key = (page["page"], s["n"])
        if key in manual:
            paras = [(True, p.strip()) for p in re.split(r"\n\s*\n", manual[key]) if p.strip()]
            source = "manual"
        else:
            paras = [(new, fix_scripts(join_hyphens(p))) for new, p in convert_markup(s.get("text", ""))]
            source = "ocr"
            if merger and rb and paras:
                # Each strip is merged against the whole Runeberg page; the
                # edits replace words only, so the paragraph breaks survive.
                merged, edits = merger.merge("\n\n".join(p for _, p in paras), rb)
                paras = [(new, p) for (new, _), p in zip(paras, merged.split("\n\n"), strict=True)]
                log += [{"strip": s["n"]} | e for e in edits]
        strips.append({k: s[k] for k in ("n", "kind", "section", "column", "box")} | {
            "source": source, "paragraphs": [{"new": new, "text": p} for new, p in paras]})
    # Page text: paragraphs in reading order, a strip's continuation joined to the paragraph before.
    page_paras: list[str] = []
    for s in strips:
        for k, p in enumerate(s["paragraphs"]):
            if page_paras and not p["new"] and k == 0:
                prev = page_paras[-1]
                page_paras[-1] = prev[:-1] + p["text"] if re.search(r"[^\W\d_][-‐]$", prev) \
                    else prev + " " + p["text"]
            else:
                page_paras.append(p["text"])
    return strips, "\n\n".join(page_paras) + "\n", log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path, help="an OCR run directory (with pages/)")
    ap.add_argument("--out", type=Path, default=Path("text"))
    ap.add_argument("--runeberg", type=Path, default=Path("runeberg_txt/Pages"))
    ap.add_argument("--manual", type=Path, default=Path("manual"))
    ap.add_argument("--lexicon", type=Path,
                    default=Path(__file__).resolve().parents[2] / "BSDA-project/data/lexicon/forms.parquet")
    ap.add_argument("--pages", default="", help="e.g. 0005-0009 (default all)")
    ap.add_argument("--no-runeberg", action="store_true")
    args = ap.parse_args()

    files = sorted((args.run / "pages").glob("*.json"))
    if args.pages:
        wanted = set()
        for part in re.split(r"[,+]", args.pages):
            a, _, b = part.partition("-")
            wanted |= {f"{n:04d}" for n in range(int(a), int(b or a) + 1)}
        files = [f for f in files if f.stem in wanted]
    merger = None
    if not args.no_runeberg:
        ours, heads = collections.Counter(), set()
        for f in files:
            for s in json.loads(f.read_text())["strips"]:
                for new, p in convert_markup(s.get("text", "")):
                    words = [t for _, _, t in tokens(fix_scripts(join_hyphens(p))) if WORD.match(t)]
                    ours.update(w for w in words if script(w) == "latin")
                    if new and words:
                        heads.add(words[0])
        merger = Merger(swedish_vocabulary(args.runeberg), greek_lexicon(args.lexicon), ours, heads)
    manual = load_manual(args.manual) if args.manual.exists() else {}
    (args.out / "pages").mkdir(parents=True, exist_ok=True)
    (args.out / "strips").mkdir(parents=True, exist_ok=True)
    stats = collections.Counter()
    all_log = []
    for f in files:
        page = json.loads(f.read_text())
        rb = load_runeberg(args.runeberg / f"{page['page']}.txt")
        strips, text, log = clean_page(page, manual, merger, rb)
        (args.out / "strips" / f"{page['page']}.json").write_text(
            json.dumps({"page": page["page"], "strips": strips}, ensure_ascii=False, indent=1))
        (args.out / "pages" / f"{page['page']}.txt").write_text(text)
        for e in log:
            stats[e["why"]] += 1
            all_log.append({"page": page["page"]} | e)
    (args.out / "merge_log.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in all_log))
    print(f"pages {len(files)} edits {dict(stats)}")


if __name__ == "__main__":
    main()
