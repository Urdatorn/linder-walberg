"""Words a proofreader should look at twice, with a likely reading.

A Greek word the AncientGreek corpus never attests is either an OCR error
or a misprint, and most OCR errors in this book are one of a few visual
confusions of its italic Greek face: δ read as θ or σ, κ as χ, ψ as φ, υ as
ν, a breathing dropped or turned, an accent of the wrong kind. Each
unattested word is tried with one such change; an attested result is
offered as the likely reading. It is only a hint: whether the print has the
word right is for the scan to decide, since a misprint must stay as printed.

A Latin-script word that neither Runeberg's OCR nor the model's own text
has elsewhere is listed too.
"""

from __future__ import annotations

import unicodedata

from clean import GREEK_CHAR, WORD, script, strip_marks, tokens

# Base letters the model confuses in this face, both ways.
LETTER_SWAPS = {
    "θ": "δσ", "σ": "δθ", "δ": "θσ", "χ": "κ", "κ": "χ", "φ": "ψ", "ψ": "φ", "ν": "υ", "υ": "ν",
    "ο": "σ", "ε": "ς", "ς": "ε", "η": "ν", "ρ": "ϱ", "ι": "ῖ", "γ": "ν", "π": "τ", "τ": "π",
}
BREATHINGS = ("̓", "̔")                    # smooth, rough
ACCENTS = ("́", "̀", "͂")             # acute, grave, circumflex
VOWELS = set("αεηιουωΑΕΗΙΟΥΩ")


def _nfd(w: str) -> list[list[str]]:
    """A word as base letters, each with its combining marks."""
    out: list[list[str]] = []
    for c in unicodedata.normalize("NFD", w):
        if unicodedata.combining(c) and out:
            out[-1].append(c)
        else:
            out.append([c])
    return out


def _join(letters: list[list[str]]) -> str:
    return unicodedata.normalize("NFC", "".join("".join(l) for l in letters))


def variants(word: str):
    """Every word one confusion away."""
    letters = _nfd(word)
    for i, (base, *marks) in enumerate(letters):
        for alt in LETTER_SWAPS.get(base.lower(), ""):
            alt = alt.upper() if base.isupper() else alt
            yield _join(letters[:i] + [[alt, *marks]] + letters[i + 1:])
        # accents: change kind, drop, or add
        accents = [m for m in marks if m in ACCENTS]
        others = [m for m in marks if m not in ACCENTS]
        for acc in ACCENTS:
            if accents != [acc] and base.lower() in VOWELS:
                yield _join(letters[:i] + [[base, *others, acc]] + letters[i + 1:])
        if accents:
            yield _join(letters[:i] + [[base, *others]] + letters[i + 1:])
        # iota subscript
        if base.lower() in "αηω":
            sub = "ͅ"
            new = [m for m in marks if m != sub] if sub in marks else [*marks, sub]
            yield _join(letters[:i] + [[base, *new]] + letters[i + 1:])
    # breathing on the initial vowel (or diphthong's second vowel)
    if letters and letters[0][0].lower() in VOWELS | {"ρ"}:
        k = 1 if len(letters) > 1 and letters[0][0].lower() in "αεο" and letters[1][0] in "ιυ" \
            and not any(m in BREATHINGS for m in letters[0][1:]) else 0
        base, *marks = letters[k]
        rest = [m for m in marks if m not in BREATHINGS]
        for b in BREATHINGS:
            if b not in marks:
                yield _join(letters[:k] + [[base, b, *rest]] + letters[k + 1:])
    # one letter dropped or doubled
    for i in range(len(letters)):
        yield _join(letters[:i] + letters[i + 1:])


def suggest(word: str, known, counts) -> str | None:
    best, best_n = None, 0
    for v in set(variants(word)):
        if v != word and known(v):
            n = counts(v)
            if n > best_n:
                best, best_n = v, n
    return best


def strip_suspects(text: str, known, counts, swedish, ours) -> list[dict]:
    out, seen = [], set()
    for _, _, t in tokens(text):
        if not WORD.match(t) or t in seen:
            continue
        seen.add(t)
        sc = script(t)
        if sc == "greek" and len(t.rstrip("'’ʼ᾽")) > 1 and not known(t):
            out.append({"word": t, "kind": "greek_unattested", "likely": suggest(t.rstrip("'’ʼ᾽"), known, counts)})
        elif sc == "latin" and len(t) > 2 and not swedish[t] and not swedish[t.lower()] and ours[t] <= 1:
            out.append({"word": t, "kind": "swedish_unknown"})
        elif sc == "mixed" or (GREEK_CHAR.search(t) and sc == "latin"):
            out.append({"word": t, "kind": "mixed_script"})
    return out


def strip_marks_eq(a: str, b: str) -> bool:
    return strip_marks(a) == strip_marks(b)
