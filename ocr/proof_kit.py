"""Prepare the cleaned OCR for proofreading against the scans.

For every strip of every page this writes

  proof/strips/NNNN_SS.txt      the text to correct (never overwritten once
                                it exists, so proofreading is not lost)
  <img>/NNNN_SS_k.png           the strip's scan in bands of about fifteen
                                lines at 450 dpi, cut between lines
  <kit>/NNNN.md                 the page's instructions for the proofreader:
                                strips in reading order, their images and
                                text files, and words to look at twice

Strip text: one paragraph per entry, paragraphs separated by a blank line.
A strip whose top continues an entry from the column or page before starts
with "~ ".

    python proof_kit.py ocr_runs/full3-clean
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np
from PIL import Image

from clean import WORD, greek_lexicon, script, swedish_vocabulary, tokens
from suspects import strip_suspects

SCALE = 0.75
BAND_PX = 1000          # target band height in scan pixels (about 15 lines)
PAD = 16


def band_cuts(grey: np.ndarray, top: int, bottom: int, left: int, right: int) -> list[int]:
    """Cut rows between top and bottom, each at the blankest row near a multiple of BAND_PX."""
    ink = (grey[top:bottom, left:right] < 128).mean(axis=1)
    cuts, y = [top], top
    while bottom - y > BAND_PX * 1.3:
        lo, hi = y + int(BAND_PX * 0.75) - top, min(y + int(BAND_PX * 1.15), bottom) - top
        k = lo + int(np.argmin(ink[lo:hi]))
        y = top + k
        cuts.append(y)
    cuts.append(bottom)
    return cuts


def strip_text(strip: dict) -> str:
    paras = [p["text"] for p in strip["paragraphs"]]
    if paras and not strip["paragraphs"][0]["new"]:
        paras[0] = "~ " + paras[0]
    return "\n\n".join(paras) + "\n" if paras else ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clean", type=Path, help="output directory of clean.py")
    ap.add_argument("--images", type=Path, default=Path("svegrek"))
    ap.add_argument("--proof", type=Path, default=Path("proof"))
    ap.add_argument("--img", type=Path, default=Path("ocr_runs/proof/img"))
    ap.add_argument("--kit", type=Path, default=Path("ocr_runs/proof/kit"))
    ap.add_argument("--runeberg", type=Path, default=Path("runeberg_txt/Pages"))
    ap.add_argument("--lexicon", type=Path,
                    default=Path(__file__).resolve().parents[2] / "BSDA-project/data/lexicon/forms.parquet")
    ap.add_argument("--pages", default="")
    args = ap.parse_args()

    for d in (args.proof / "strips", args.img, args.kit):
        d.mkdir(parents=True, exist_ok=True)
    known = greek_lexicon(args.lexicon)
    swedish = swedish_vocabulary(args.runeberg)
    files = sorted((args.clean / "strips").glob("*.json"))
    if args.pages:
        wanted = set()
        for part in args.pages.replace("+", ",").split(","):
            a, _, b = part.partition("-")
            wanted |= {f"{n:04d}" for n in range(int(a), int(b or a) + 1)}
        files = [f for f in files if f.stem in wanted]
    pages = [json.loads(f.read_text()) for f in sorted((args.clean / "strips").glob("*.json"))]
    ours = collections.Counter(t for pg in pages for s in pg["strips"] for p in s["paragraphs"]
                               for _, _, t in tokens(p["text"]) if WORD.match(t) and script(t) == "latin")
    merges = collections.defaultdict(list)
    log = args.clean / "merge_log.jsonl"
    if log.exists():
        for line in log.read_text().splitlines():
            e = json.loads(line)
            merges[(e["page"], e["strip"])].append(e)

    n_bands = 0
    for f in files:
        page = json.loads(f.read_text())
        pid = page["page"]
        grey = np.asarray(Image.open(args.images / f"{pid}.tif").convert("L"))
        img = Image.fromarray(grey)
        md = [f"# Page {pid}\n"]
        for s in page["strips"]:
            text = strip_text(s)
            if not text and s.get("source") == "manual":
                continue
            sid = f"{pid}_{s['n']:02d}"
            tf = args.proof / "strips" / f"{sid}.txt"
            if not tf.exists():
                tf.write_text(text)
            l, t, r, b = s["box"]
            cuts = band_cuts(grey, t, b, l, r)
            bands = []
            for k, (y0, y1) in enumerate(zip(cuts, cuts[1:])):
                crop = Image.new("L", (r - l + 2 * PAD, y1 - y0 + 2 * PAD), 255)
                crop.paste(img.crop((l, y0, r, y1)), (PAD, PAD))
                crop = crop.resize((round(crop.width * SCALE), round(crop.height * SCALE)), Image.LANCZOS)
                path = args.img / f"{sid}_{k}.png"
                crop.save(path, optimize=True)
                bands.append(path)
            n_bands += len(bands)
            where = {"col": f"column {s['column'] + 1}", "span": "full width", "page": "full width"}.get(s["kind"], s["kind"])
            md.append(f"## Strip {sid} ({where}, section {s['section']}{', hand-transcribed' if s.get('source') == 'manual' else ''})\n")
            md.append(f"Text file: `{tf.resolve()}`\n")
            md.append("Images, top to bottom:\n" + "".join(f"- `{p.resolve()}`\n" for p in bands))
            hints = strip_suspects(text, known, known.count, swedish, ours)
            edits = merges.get((pid, s["n"]), [])
            if hints or edits:
                md.append("Look twice at:\n")
                for h in hints:
                    tip = {"greek_unattested": "Greek form not found in the Greek corpus",
                           "swedish_unknown": "Swedish word found nowhere else in the book",
                           "mixed_script": "mixes Greek and Latin letters"}[h["kind"]]
                    likely = f"; perhaps `{h['likely']}`" if h.get("likely") else ""
                    md.append(f"- `{h['word']}`: {tip}{likely}\n")
                stops = sum(e["why"] == "full_stop_colon" for e in edits)
                if stops:
                    md.append(f"- `.:` ({stops}x): the cleaner turned `.` or `:` into `.:` here, following "
                              "the 2013 OCR; check each against the scan\n")
                for e in {(e["from"], e["to"]): e for e in edits}.values():
                    if e["why"] != "full_stop_colon":
                        md.append(f"- `{e['to']}`: the cleaner changed `{e['from']}` to this, following "
                                  "the 2013 OCR; check it\n")
            md.append("\n")
        (args.kit / f"{pid}.md").write_text("".join(md))
    print(f"pages {len(files)} bands {n_bands}")


if __name__ == "__main__":
    main()
