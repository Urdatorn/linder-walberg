"""Score OCR pages against Project Runeberg's proofread transcriptions.

Pages 0005-0009 (the start of letter A) were corrected by hand on Runeberg
and are close to perfect, so they serve as a diagnostic for the new OCR.
Both sides are reduced to running text before scoring: tags and pseudo-
Markdown removed, line-break hyphens joined, apostrophes and hyphens unified,
NFKC applied and whitespace collapsed, as in the CLLG paper's plain-text CER.

    python eval_runeberg.py --pred <run>/pages --ref ../runeberg_txt/Pages --pages 0005-0009
"""

from __future__ import annotations

import argparse
import html
import re
import unicodedata
from pathlib import Path

import numpy as np

TAG = re.compile(r"</?[A-Za-z][^>]*>")
LINE_HYPHEN = re.compile(r"(\w)-[ \t]*\r?\n[ \t]*(?=[a-zåäöéüͰ-Ͽἀ-῿])")


def levenshtein(a: list, b: list) -> int:
    """Edit distance, one numpy pass per element of a."""
    if not a or not b:
        return max(len(a), len(b))
    vocab = {x: i for i, x in enumerate(set(a) | set(b))}
    av = np.array([vocab[x] for x in a])
    bv = np.array([vocab[x] for x in b])
    idx = np.arange(len(b) + 1)
    prev = idx.copy()
    cur = np.empty_like(prev)
    for i, ca in enumerate(av, 1):
        cur[0] = i
        np.minimum(prev[:-1] + (bv != ca), prev[1:] + 1, out=cur[1:])
        cur = np.minimum.accumulate(cur - idx) + idx     # insertions
        prev, cur = cur, prev
    return int(prev[-1])


def normalise(text: str, prediction: bool) -> str:
    text = html.unescape(text.replace("\r\n", "\n"))
    if prediction:
        text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = TAG.sub("", text)
    text = LINE_HYPHEN.sub(r"\1", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[`´‘’ʼʹ]", "'", text)
    text = re.sub(r"[‐‑‒–−]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_marks(text: str) -> str:
    return unicodedata.normalize("NFC", "".join(
        c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)))


def is_greek(c: str) -> bool:
    return "Ͱ" <= c <= "Ͽ" or "ἀ" <= c <= "῿"


def rates(pred: str, ref: str) -> dict:
    def cer(p, r):
        return levenshtein(list(p), list(r)), len(r)
    out = {}
    for name, (p, r) in {
        "cer": (pred, ref),
        "cer_no_diacritics": (strip_marks(pred), strip_marks(ref)),
        "cer_greek": ("".join(filter(is_greek, pred)), "".join(filter(is_greek, ref))),
        "cer_latin": ("".join(c for c in pred if c.isalpha() and not is_greek(c)),
                      "".join(c for c in ref if c.isalpha() and not is_greek(c))),
    }.items():
        out[name] = cer(p, r)
    out["wer"] = (levenshtein(pred.split(), ref.split()), len(ref.split()))
    return out


def parse_pages(spec: str) -> list[str]:
    pages = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages += [f"{n:04d}" for n in range(int(a), int(b or a) + 1)]
    return pages


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", required=True, help="directory of NNNN.txt OCR output")
    ap.add_argument("--ref", required=True, help="Runeberg Pages/ directory")
    ap.add_argument("--pages", default="0005-0009")
    ap.add_argument("--show", type=int, default=0, help="print this many characters of each normalised pair")
    args = ap.parse_args()

    totals: dict[str, list[int]] = {}
    keys = ["cer", "cer_no_diacritics", "cer_greek", "cer_latin", "wer"]
    print(f"{'page':6}" + "".join(f"{k:>19}" for k in keys))
    for page in parse_pages(args.pages):
        pf, rf = Path(args.pred) / f"{page}.txt", Path(args.ref) / f"{page}.txt"
        if not pf.exists():
            print(f"{page:6} missing prediction")
            continue
        pred = normalise(pf.read_text(encoding="utf-8"), prediction=True)
        ref = normalise(rf.read_text(encoding="utf-8"), prediction=False)
        r = rates(pred, ref)
        print(f"{page:6}" + "".join(f"{100 * e / max(n, 1):18.2f}%" for e, n in (r[k] for k in keys)))
        for k in keys:
            t = totals.setdefault(k, [0, 0])
            t[0] += r[k][0]
            t[1] += r[k][1]
        if args.show:
            print(f"  ref : {ref[:args.show]}\n  pred: {pred[:args.show]}")
    if totals:
        print(f"{'all':6}" + "".join(f"{100 * totals[k][0] / max(totals[k][1], 1):18.2f}%" for k in keys))


if __name__ == "__main__":
    main()
