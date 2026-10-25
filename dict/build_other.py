"""StarDict and MDict editions of the dictionary, from the same entries as the
Dictionary.app build (build_xml.compile_entries).

  dist/stardict/LinderWalberg/   .ifo .idx .dict.dz .syn and res/ with the
                                 stylesheet: GoldenDict-ng (Linux, Windows,
                                 macOS) and StarDict readers on iOS/Android
  dist/mdict/LinderWalberg.mdx   with LinderWalberg.mdd holding the stylesheet:
                                 MDict, DictTango, GoldenDict and others

Every search key of the Apple edition carries over: headword variants,
modern spellings, "*" and starred words, Greek equivalents. StarDict keeps
them as synonyms; MDict as linking entries (@@@LINK), and a key shared by
several entries (a Greek word rendered in many) as a short list of links.
Cross-references become bword:// (StarDict) or entry:// (MDict) links.

Needs pyglossary and mdict-utils (pip install pyglossary mdict-utils).

    python dict/build_other.py
"""

from __future__ import annotations

import argparse
import collections
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

from build_xml import HERE, ROOT, compile_entries

CSS = HERE / "src/LinderWalberg.css"
TITLE = "Svenskt-grekiskt lexikon (Linder & Walberg 1862)"
DESCRIPTION = ("C. W. Linder & C. A. Walberg, Svenskt-grekiskt lexikon, Upsala 1862. Proofread against the scans, "
               "with the book's errata and a formal review of the Greek applied. Public domain; transcription CC0. "
               "https://github.com/Urdatorn/linder-walberg")


def relink(markup: str, titles: dict[str, str], scheme: str) -> str:
    """x-dictionary:r:<id> -> <scheme><headword>; x-dictionary:d:<word> -> <scheme><word>."""
    def repl(m: re.Match) -> str:
        kind, target = m.group(1), m.group(2)
        word = titles.get(target, target) if kind == "r" else html.unescape(target)
        return f'href="{scheme}{html.escape(word, quote=True)}"'
    return re.sub(r'href="x-dictionary:([rd]):([^"]*)"', repl, markup)


def stardict(records: list[dict], titles: dict[str, str], out: Path) -> None:
    from pyglossary.glossary_v2 import Glossary
    Glossary.init()
    g = Glossary()
    g.setInfo("title", TITLE)
    g.setInfo("description", DESCRIPTION)
    g.setInfo("author", "C. W. Linder, C. A. Walberg; edited by Albin Thörn Cleland")
    g.setInfo("sourceLang", "sv")
    g.setInfo("targetLang", "grc")
    link = '<link rel="stylesheet" href="LinderWalberg.css">'
    for rec in records:
        words = [rec["title"]] + [v for v, _ in rec["keys"] + rec.get("greek", []) if v != rec["title"]]
        g.addEntry(g.newEntry(list(dict.fromkeys(words)), link + relink(rec["html"], titles, "bword://"),
                              defiFormat="h"))
    g.addEntry(g.newDataEntry("LinderWalberg.css", CSS.read_bytes()))
    out.mkdir(parents=True, exist_ok=True)
    g.write(str(out / "LinderWalberg.ifo"), formatName="Stardict", dictzip=True, sametypesequence="h")


def mdict(records: list[dict], titles: dict[str, str], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    src = out / "LinderWalberg.txt"
    link = '<link rel="stylesheet" type="text/css" href="LinderWalberg.css"/>'
    alt = collections.defaultdict(list)       # key -> titles it should lead to
    with open(src, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(f'{rec["title"]}\n{link}{relink(rec["html"], titles, "entry://")}\n</>\n')
            for v, _ in rec["keys"] + rec.get("greek", []):
                if v != rec["title"]:
                    alt[v].append(rec["title"])
        main = {r["title"] for r in records}
        for key, targets in alt.items():
            targets = list(dict.fromkeys(targets))
            if key in main:
                continue                      # the key is itself a headword: its entry already answers it
            if len(targets) == 1:
                f.write(f"{key}\n@@@LINK={targets[0]}\n</>\n")
            else:
                items = "".join(f'<li><a href="entry://{html.escape(t, quote=True)}">{html.escape(t)}</a></li>'
                                for t in targets)
                f.write(f'{key}\n{link}<h1 class="hw">{html.escape(key)}</h1><ul class="refs">{items}</ul>\n</>\n')
    (out / "title.html").write_text(TITLE, encoding="utf-8")
    (out / "description.html").write_text(DESCRIPTION, encoding="utf-8")
    res = out / "res"
    res.mkdir(exist_ok=True)
    shutil.copy(CSS, res / "LinderWalberg.css")
    tool = shutil.which("mdict") or str(Path(sys.executable).parent / "mdict")
    for args in (["-a", str(src), "--title", str(out / "title.html"), "--description",
                  str(out / "description.html"), str(out / "LinderWalberg.mdx")],
                 ["-a", str(res), str(out / "LinderWalberg.mdd")]):
        subprocess.run([tool, *args], check=True, stdout=subprocess.DEVNULL)
    for f in (src, out / "title.html", out / "description.html"):
        f.unlink()
    shutil.rmtree(res)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    args = ap.parse_args()
    records = compile_entries(ROOT / "text/corrected/entries.jsonl", ROOT / "text/corrected/pages")
    titles = {r["id"]: r["title"] for r in records}
    stardict(records, titles, args.out / "stardict/LinderWalberg")
    mdict(records, titles, args.out / "mdict")
    print("written", *sorted(str(p.relative_to(args.out)) for p in args.out.rglob("*") if p.is_file()), sep="\n  ")


if __name__ == "__main__":
    main()
