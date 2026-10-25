"""Formal checks of the Greek in the proofread text, for misprints the
authors' Tryckfel list missed.

Each Greek word is checked against the rules of polytonic orthography and
against the AncientGreek corpus and LSJ:

  breathing      a word beginning with a vowel, diphthong or ρ has a breathing
                 (endings cited after a comma, "ἀσπίς, ίδος", are exempt)
  accent         every word has an accent, except proclitics and enclitics
  one_accent     no word has two accents (outside enclitic throwback, which
                 puts the second accent on the final syllable)
  grave          an oxytone keeps the acute only before punctuation, a
                 non-Greek word or an enclitic; a grave stands only before
                 another Greek word
  position       accent on one of the last three syllables; circumflex only on
                 the last two; no acute on the antepenult or circumflex on the
                 penult when the last syllable is long by nature (η, ω, a
                 diphthong other than final -αι/-οι, ι subscript)
  unattested     the form is not in the AncientGreek corpus; a likely reading
                 one change away is given when the corpus has one
  lemma          a cited lemma (a noun with its article, an adjective with its
                 terminations, an infinitive) has an LSJ headword

A finding with an attested, much more frequent reading one diacritic away is
an obvious fix and goes to the corrections layer; everything else goes to the
errata report for a person to decide.

    python greek_checks.py text/entries.jsonl --out corrections
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import unicodedata
from pathlib import Path

from clean import GREEK_CHAR, WORD, greek_lexicon, script, strip_marks, tokens
from suspects import suggest

SMOOTH, ROUGH = "̓", "̔"
ACUTE, GRAVE, CIRC = "́", "̀", "͂"
IOTA_SUB, DIAER = "ͅ", "̈"
ACCENTS = {ACUTE, GRAVE, CIRC}
VOWELS = set("αεηιουω")
LONG_DIPHTHONGS = {"ει", "ου", "αυ", "ευ", "ηυ", "υι", "αι", "οι", "ωυ"}

PROCLITICS = {"ὁ", "ἡ", "οἱ", "αἱ", "ἐν", "εἰς", "ἐς", "ἐκ", "ἐξ", "εἰ", "ὡς", "οὐ", "οὐκ", "οὐχ"}
ENCLITIC_BARE = {
    "τις", "τι", "τινος", "τινι", "τινα", "τινες", "τινων", "τισι", "τισιν", "τινας", "του", "τω",
    "μου", "μοι", "με", "σου", "σοι", "σε", "ου", "οι", "ε", "σφισι", "σφισιν", "σφας", "σφων", "σφιν",
    "που", "ποι", "πη", "πως", "ποτε", "πω", "ποθεν", "ποθι", "γε", "τε", "τοι", "περ", "νυν", "νυ", "θην", "κε", "κεν",
    "ειμι", "ει", "εστι", "εστιν", "εσμεν", "εστε", "εισι", "εισιν", "εστον",
    "φημι", "φησι", "φησιν", "φαμεν", "φατε", "φασι", "φασιν", "φατον",
}


def letters(word: str) -> list[tuple[str, set[str]]]:
    out: list[tuple[str, set[str]]] = []
    for c in unicodedata.normalize("NFD", word):
        if unicodedata.combining(c) and out:
            out[-1][1].add(c)
        elif c.isalpha():
            out.append((c, set()))
    return out


def bare(word: str) -> str:
    return strip_marks(word).lower().replace("ς", "σ").rstrip("'’ʼ᾽")


ENCLITIC_BARE = {bare(w) for w in ENCLITIC_BARE}
PROCLITIC_BARE = {bare(w) for w in PROCLITICS}


def syllables(ls: list[tuple[str, set[str]]]) -> list[list[int]]:
    """Vowel groups (indices into ls), last syllable last; a diaeresis splits a diphthong."""
    groups: list[list[int]] = []
    for i, (c, marks) in enumerate(ls):
        if c.lower() not in VOWELS:
            continue
        prev = groups[-1] if groups and groups[-1][-1] == i - 1 else None
        if prev and len(prev) == 1 and DIAER not in marks and \
                (ls[prev[0]][0].lower() + c.lower()) in LONG_DIPHTHONGS and not ls[prev[0]][1] & ACCENTS:
            prev.append(i)
        else:
            groups.append([i])
    return groups


def is_long(ls, group: list[int], final: bool) -> bool | None:
    """True if long by nature, False if short, None if the eye cannot tell (α ι υ)."""
    chars = "".join(ls[i][0].lower() for i in group)
    marks = set().union(*(ls[i][1] for i in group))
    if len(group) == 2:
        # final -αι, -οι count short only at the very end of the word (not -οις)
        return not (final and chars in ("αι", "οι") and group[-1] == len(ls) - 1)
    if IOTA_SUB in marks or CIRC in marks or chars in ("η", "ω"):
        return True
    if chars in "εο":
        return False
    return None


def word_findings(word: str, prev: str | None, nxt: str | None, gap: str) -> list[tuple[str, str]]:
    ls = letters(word)
    if not ls:
        return []
    b = bare(word)
    out: list[tuple[str, str]] = []
    marks_all = [m for _, ms in ls for m in ms]
    accents = [(i, m) for i, (_, ms) in enumerate(ls) for m in ms if m in ACCENTS]
    first = ls[0][0].lower()
    ending = prev is not None and gap.strip() == "," and script(prev) == "greek" and len(ls) <= 6 \
        and first in VOWELS and not any(m in (SMOOTH, ROUGH) for m in marks_all)
    if (first in VOWELS or first == "ρ") and not ending:
        breath_at = ls[:2] if len(ls) > 1 and (ls[0][0].lower() + ls[1][0].lower()) in LONG_DIPHTHONGS \
            and DIAER not in ls[1][1] else ls[:1]
        if not any(m in (SMOOTH, ROUGH) for _, ms in breath_at for m in ms) and len(ls) > 1:
            out.append(("breathing", "initial vowel without breathing"))
    if not accents:
        elided = word[-1:] in "'’ʼ᾽"
        if b not in PROCLITIC_BARE and b not in ENCLITIC_BARE and not elided and not ending and len(ls) > 1:
            out.append(("accent", "no accent"))
        return out
    syl = syllables(ls)
    if not syl:
        return out
    pos_of = {i: n for n, g in enumerate(reversed(syl)) for i in g}   # 0 = ultima
    acc_pos = [(pos_of.get(i), m) for i, m in accents]
    if len(accents) > 1:
        if not (len(accents) == 2 and acc_pos[-1][0] == 0 and acc_pos[-1][1] == ACUTE):
            out.append(("one_accent", "more than one accent"))
        return out
    p, m = acc_pos[0]
    if p is None:
        return out
    ult_long = is_long(ls, syl[-1], final=True)
    if p > 2:
        out.append(("position", "accent before the antepenult"))
    if m == CIRC and p > 1:
        out.append(("position", "circumflex before the penult"))
    # Attic -εως/-εων (πόλεως, ἀξιόχρεως) keep the accent on the antepenult
    if p == 2 and ult_long and not re.search(r"ε[ωώ][νς]?$", strip_marks(word).lower()):
        out.append(("position", "accent on the antepenult with a long last syllable"))
    if m == CIRC and p == 1 and ult_long:
        out.append(("position", "circumflex on the penult with a long last syllable"))
    if m == CIRC and is_long(ls, syl[-1 - p], final=p == 0) is False:
        out.append(("position", "circumflex on a short vowel"))
    # A bracket may close an optional word ("(μὴ) ποιεῖν", grave kept) or a
    # list of alternatives ("(εἰ γάρ, ὥς) ὤφελον", acute kept), so brackets
    # excuse either accent.
    greek_next = nxt is not None and script(nxt) == "greek"
    next_greek = greek_next and gap.strip() == ""
    next_greek_or_bracket = greek_next and gap.replace("(", "").replace(")", "").strip() == ""
    # τὶ with a grave is the book's way of citing the indefinite pronoun
    if m == GRAVE and p == 0 and not next_greek_or_bracket and b != "τι":
        out.append(("grave", "grave before a pause or a non-Greek word"))
    if m == GRAVE and p > 0:
        out.append(("grave", "grave not on the last syllable"))
    if m == ACUTE and p == 0 and next_greek and bare(nxt) not in ENCLITIC_BARE \
            and b not in {"τισ", "τι"} and not re.match(r"[’']", word[-1:]):
        out.append(("grave", "acute on the last syllable before another word"))
    return out


def run(entries: list[dict], known, lsj: set[str]) -> list[dict]:
    findings = []
    for e_no, e in enumerate(entries):
        text = e["text"]
        toks = tokens(text)
        words = [k for k, t in enumerate(toks) if WORD.match(t[2])]
        for w_i, k in enumerate(words):
            s, end, w = toks[k]
            # prefixes and endings cited as such: "ἀπο-", "-σθαι", "(δια)κρίνειν"
            # prefixes and endings cited as such: "ἀπο-", "-σθαι", "(δια)κρίνειν", "(ἀπο-, κατα)σφάττειν",
            # and the rest of a compound after a bracket ("δι(εξ)ελθεῖν")
            if script(w) != "greek" or text[end:end + 1] in "-‐" or (s and text[s - 1] in "-‐") \
                    or (text[end:end + 1] == ")" and re.match(r"[^\W\d_]", text[end + 1:end + 2] or " ")) \
                    or (s and text[s - 1] == ")" and s > 1 and re.match(r"[^\W\d_]", text[s - 2])):
                continue
            # "(δι)εσχίσθαι", "(ἐν-, ἐφ-, προσ)αρμόττειν": prefixes in brackets belong to the word
            pre = re.search(r"\((?:[^()]*?[\s,-])?([^\W\d_]+)\)$", text[:s])
            full = pre.group(1) + w if pre else None
            if pre is None and s and text[s - 1] == ")":
                continue
            prev = toks[words[w_i - 1]][2] if w_i else None
            nxt = toks[words[w_i + 1]][2] if w_i + 1 < len(words) else None
            gap_prev = text[toks[words[w_i - 1]][1]:s] if w_i else ""
            gap_next = text[end:toks[words[w_i + 1]][0]] if w_i + 1 < len(words) else "."
            found = word_findings(full or w, prev, nxt, gap_next)
            # an ending after a comma: judge by the gap before it
            # an ending cited after a comma or in brackets ("ποιῶν, οῦσα", "(όντος)", "l. ῶν")
            ending_slot = (gap_prev.strip() in (",", "(", ", (") and prev and script(prev) == "greek") \
                or (s and text[s - 1] == "(" and text[end:end + 1] == ")") \
                or (gap_prev.strip() in ("", ".") and prev == "l" and len(w) <= 4)
            found = [f for f in found if not (f[0] in ("breathing", "accent") and ending_slot and len(w) <= 7)]
            if not known(w) and not (full and known(full)):
                in_lsj = bare(full or w) in lsj
                found.append(("unattested", "not in the AncientGreek corpus"
                              + (" (but an LSJ headword)" if in_lsj else "")))
            for kind, why in found:
                findings.append({"entry": e_no, "page": e["page"], "word": w, "check": kind, "why": why,
                                 "context": text[max(0, s - 40):end + 40]})
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entries", type=Path)
    ap.add_argument("--out", type=Path, default=Path("corrections"))
    ap.add_argument("--lexicon", type=Path,
                    default=Path(__file__).resolve().parents[2] / "BSDA-project/data/lexicon/forms.parquet")
    ap.add_argument("--lsj", type=Path,
                    default=Path(__file__).resolve().parents[2] / "BSDA-project/data/lexicon/lsj_headwords_bare.txt")
    args = ap.parse_args()
    known = greek_lexicon(args.lexicon)
    lsj = set(args.lsj.read_text(encoding="utf-8").split())
    entries = [json.loads(l) for l in args.entries.read_text(encoding="utf-8").splitlines()]
    findings = run(entries, known, lsj)
    for f in findings:
        if f["check"] in ("unattested", "breathing", "accent", "position", "grave", "one_accent"):
            f["likely"] = suggest(f["word"].rstrip("'’ʼ᾽"), known, known.count)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "greek_findings.jsonl").write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in findings))
    print(collections.Counter(f["check"] for f in findings))


if __name__ == "__main__":
    main()
