"""Build and publish the Hugging Face dataset Urdatorn/linder-walberg.

Four configurations from the same transcription:

  pages        one row per scanned page: the 600 dpi bilevel scan, the model's
               raw OCR, the diplomatic text (proofread, misprints as printed)
               and the corrected text (editorial corrections applied)
  strips       one row per strip the page was cut into for OCR (a column
               section, a heading): its box on the page, the crop, and its
               diplomatic and corrected text. Strips are the unit the text was
               proofread in, so image and text match exactly.
  entries      one row per dictionary entry (pages 5-539), diplomatic and corrected
  corrections  every finding of the proofreading and the formal checks, with the
               decision taken and where it was applied

    python hf/build_dataset.py [--push]
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REPO = "Urdatorn/linder-walberg"


def png(im: Image.Image) -> dict:
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return {"bytes": b.getvalue(), "path": None}


def section(page: str) -> str:
    n = int(page)
    return "front_matter" if n <= 4 else "dictionary" if n <= 538 else "back_matter"


def strip_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").rstrip("\n") if path.exists() else ""


def build():
    import datasets
    layout = {}
    for f in sorted((ROOT / "ocr_runs/full3-clean/strips").glob("*.json")):
        pg = json.loads(f.read_text())
        layout[pg["page"]] = {s["n"]: s for s in pg["strips"]}
    reports = {f.stem: json.loads(f.read_text()) for f in (ROOT / "proof/reports").glob("*.json")}

    def pages():
        for tif in sorted((ROOT / "svegrek").glob("*.tif")):
            p = tif.stem
            raw = ROOT / "ocr_runs/full3/pages" / f"{p}.txt"
            yield {
                "page": p,
                "printed_page": int(p) - 4 if 5 <= int(p) <= 539 else None,
                "section": section(p),
                "image": png(Image.open(tif)),
                "text_diplomatic": strip_text(ROOT / "text/pages" / f"{p}.txt"),
                "text_corrected": strip_text(ROOT / "text/corrected/pages" / f"{p}.txt"),
                "text_ocr_raw": raw.read_text(encoding="utf-8") if raw.exists() else "",
                "proofreading_corrections": reports.get(p, {}).get("corrections"),
            }

    def strips():
        for tif in sorted((ROOT / "svegrek").glob("*.tif")):
            p = tif.stem
            im = None
            for f in sorted((ROOT / "proof/strips").glob(f"{p}_*.txt")):
                n = int(f.stem.split("_")[1])
                s = layout.get(p, {}).get(n)
                text = strip_text(f)
                if s is None or not text:
                    continue
                im = im or Image.open(tif)
                l, t, r, b = s["box"]
                yield {
                    "page": p, "strip": f.stem, "kind": s["kind"], "section_index": s["section"],
                    "column": s["column"] + 1 if s["column"] >= 0 else 0, "box": [l, t, r, b],
                    "image": png(im.crop((l, t, r, b))),
                    "continues": text.startswith("~ "),
                    "text_diplomatic": text.removeprefix("~ "),
                    "text_corrected": strip_text(ROOT / "text/corrected_strips" / f.name).removeprefix("~ "),
                }

    def entries():
        dip = [json.loads(l) for l in (ROOT / "text/entries.jsonl").read_text(encoding="utf-8").splitlines()]
        cor = [json.loads(l) for l in (ROOT / "text/corrected/entries.jsonl").read_text(encoding="utf-8").splitlines()]
        for i, (d, c) in enumerate(zip(dip, cor, strict=True)):
            m = re.match(r"([^,;:(]+?)(?:,|\s+se\s|\s*\(|$)", d["text"])
            yield {"entry": i, "headword": (m.group(1) if m else d["text"].split()[0]).strip(),
                   "page": d["page"], "strips": d["source"],
                   "text_diplomatic": d["text"], "text_corrected": c["text"]}

    def corrections():
        con = sqlite3.connect(ROOT / "corrections/errata.sqlite")
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT * FROM findings ORDER BY id"):
            yield {k: (str(r[k]) if r[k] is not None else "") for k in r.keys() if k != "id"}

    img = datasets.Image()
    feats = {
        "pages": datasets.Features({
            "page": datasets.Value("string"), "printed_page": datasets.Value("int32"),
            "section": datasets.Value("string"), "image": img,
            "text_diplomatic": datasets.Value("string"), "text_corrected": datasets.Value("string"),
            "text_ocr_raw": datasets.Value("string"), "proofreading_corrections": datasets.Value("int32")}),
        "strips": datasets.Features({
            "page": datasets.Value("string"), "strip": datasets.Value("string"), "kind": datasets.Value("string"),
            "section_index": datasets.Value("int32"), "column": datasets.Value("int32"),
            "box": datasets.Sequence(datasets.Value("int32"), length=4), "image": img,
            "continues": datasets.Value("bool"),
            "text_diplomatic": datasets.Value("string"), "text_corrected": datasets.Value("string")}),
        "entries": datasets.Features({
            "entry": datasets.Value("int32"), "headword": datasets.Value("string"), "page": datasets.Value("string"),
            "strips": datasets.Sequence(datasets.Value("string")),
            "text_diplomatic": datasets.Value("string"), "text_corrected": datasets.Value("string")}),
    }
    out = {name: datasets.Dataset.from_generator(gen, features=feats.get(name))
           for name, gen in [("pages", pages), ("strips", strips), ("entries", entries), ("corrections", corrections)]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--push", action="store_true")
    args = ap.parse_args()
    sets = build()
    for name, ds in sets.items():
        print(name, ds)
    if args.push:
        from huggingface_hub import HfApi
        for name, ds in sets.items():
            ds.push_to_hub(REPO, config_name=name, split="train", max_shard_size="200MB")
        HfApi().upload_file(path_or_fileobj=str(Path(__file__).parent / "README.md"), path_in_repo="README.md",
                            repo_id=REPO, repo_type="dataset", commit_message="Dataset card")


if __name__ == "__main__":
    main()
