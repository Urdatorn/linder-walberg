"""Build the web app (an installable, offline-capable iPhone app) from the same
entries as the Dictionary.app edition (dict/build_xml.compile_entries).

  app/dist/              the site, ready to serve as static files
    index.html app.js sync.js app.css sw.js manifest.webmanifest front.png icons/ fonts/ img/ .nojekyll
    data/meta.json       titles of all entries, the daily-word candidates
    data/k/<hex>.json    the search index by first letter: [folded key, key, entry number], sorted
    data/e/NN.json       entry pages, 1000 per file

    python app/build_app.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "dict"))
from build_xml import compile_entries  # noqa: E402

CHUNK = 1000
DIST = HERE / "dist"


def fold(s: str) -> str:
    """Search form: lower case, no accents or breathings, ς = σ; but å, ä and ö, letters
    of their own in Swedish, are kept (app.js folds the same way)."""
    out: list[str] = []
    for c in unicodedata.normalize("NFD", s.lower()):
        if not unicodedata.combining(c):
            out.append(c)
        elif out and out[-1] in "ao" and c in "\u030a\u0308":
            out[-1] = unicodedata.normalize("NFC", out[-1] + c)
    return "".join(out).replace("ς", "σ").replace("’", "'").strip()


def main() -> None:
    records = compile_entries(ROOT / "text/corrected/entries.jsonl", ROOT / "text/corrected/pages")
    index = {r["id"]: i for i, r in enumerate(records)}

    def relink(html: str) -> str:
        html = re.sub(r'href="x-dictionary:r:([^"]+)"',
                      lambda m: f'href="#e/{index.get(m.group(1), m.group(1))}"', html)
        html = re.sub(r'href="x-dictionary:d:([^"]+)"', lambda m: f'href="#s/{m.group(1)}"', html)
        return html.replace('src="Images/', 'src="img/')

    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "data/e").mkdir(parents=True)
    for i in range(0, len(records), CHUNK):
        chunk = {str(j): relink(records[j]["html"]) for j in range(i, min(i + CHUNK, len(records)))}
        (DIST / f"data/e/{i // CHUNK:02d}.json").write_text(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
                                                            encoding="utf-8")
    keys = []
    for i, r in enumerate(records):
        seen = set()
        for value, _ in [(r["title"], r["title"])] + r["keys"] + r.get("greek", []):
            f = fold(value)
            if f and f not in seen:
                seen.add(f)
                keys.append([f, value, i])
    keys.sort(key=lambda k: (k[0], k[2]))
    # one file per first letter, so a search loads only its letter
    (DIST / "data/k").mkdir()
    by_letter = {}
    for k in keys:
        by_letter.setdefault(f"{ord(k[0][0]):x}", []).append(k)
    for code, ks in by_letter.items():
        (DIST / f"data/k/{code}.json").write_text(json.dumps(ks, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # daily words: the book's own entries whose word is rare in Swedish today (dict/frequency.tsv:
    # Zipf under 2.5, under 0.3 in a million words), compounds ("Qvinnoblygd") and short
    # references ("Tokrolig, se Putslustig") as well; in a fixed shuffle, the app taking
    # one a day in turn, so that none comes again before all have been shown
    zipf = {r["id"]: float(r["zipf"]) for r in csv.DictReader((ROOT / "dict/frequency.tsv").open(encoding="utf-8"), delimiter="\t")}
    daily = [i for i, r in enumerate(records) if re.fullmatch(r"lw_\d+", r["id"]) and zipf.get(r["id"], 9) < 2.5]
    random.Random(1862).shuffle(daily)
    special = {k: index[k] for k in ("front_matter", "lw_preface", "lw_abbr", "lw_locorum", "lw_partes", "lw_rara", "lw_linder", "lw_walberg")
               if k in index}
    entries = sum(1 for r in records if re.fullmatch(r"lw_\d+", r["id"]))      # the dictionary's own articles
    meta = {"count": len(records), "entries": entries, "chunk": CHUNK, "titles": [r["title"] for r in records],
            "daily": daily, "special": special}
    (DIST / "data/meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    for f in (HERE / "src").iterdir():
        (shutil.copytree if f.is_dir() else shutil.copy)(f, DIST / f.name)
    shutil.copytree(ROOT / "dict/src/OtherResources/Images", DIST / "img")
    (DIST / ".nojekyll").touch()                                   # GitHub Pages: serve as is
    css = (ROOT / "dict/src/LinderWalberg.css").read_text(encoding="utf-8")
    (DIST / "dictionary.css").write_text(css, encoding="utf-8")
    files = sorted(str(p.relative_to(DIST)) for p in DIST.rglob("*") if p.is_file() and p.name != "sw.js")
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.encode() + b"\0" + (DIST / f).read_bytes())
    version = digest.hexdigest()[:10]
    # the page asks for its scripts and styles with the version (app.js passes it on to data and sw.js)
    page = (DIST / "index.html").read_text(encoding="utf-8")
    page = re.sub(r'(<(?:script src|link rel="stylesheet" href)=")([\w./-]+\.(?:js|css))"', rf'\1\2?v={version}"', page)
    (DIST / "index.html").write_text(page, encoding="utf-8")
    sw = (DIST / "sw.js").read_text(encoding="utf-8")
    (DIST / "sw.js").write_text(sw.replace("__VERSION__", version).replace('"__FILES__"', json.dumps(files)),
                                encoding="utf-8")
    size = sum((DIST / f).stat().st_size for f in files)
    print(f"{len(records)} entries, {len(keys)} search keys, {len(daily)} daily words; "
          f"{len(files)} files, {size / 2**20:.1f} MB -> {DIST}")


if __name__ == "__main__":
    main()
