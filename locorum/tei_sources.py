"""Find the Greek examples in the ancient texts themselves: every Greek edition
of Perseus (canonical-greekLit) and First1KGreek, read with its citations
(passages.py), searched for every example the way find_sources.py searches
the corpus (bare letters, stand-in pronouns as wildcards, whole example).

Counting ancient texts rather than corpus records is what tells a quotation
from a stock phrase: a line of Xenophon recurs in every school edition and
commentary of Xenophon, but in only one ancient text.

  locorum/tei_matches.jsonl   one line per example and occurrence: TLG work,
                              passage, edition file

    python tei_sources.py --workers 8
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
from pathlib import Path

from find_sources import load_examples
from passages import TEI, edition

HERE = Path(__file__).resolve().parent


def init(pats_, anchors_) -> None:
    global PATS, ANCHORS, FIRST
    PATS, ANCHORS = pats_, anchors_
    FIRST = {a[0] for a in anchors_}


def scan(path: Path) -> list[dict]:
    toks, cites = edition(path)
    out = []
    for i in range(len(toks) - 2):
        if toks[i] not in FIRST:
            continue
        for k, off in ANCHORS.get((toks[i], toks[i + 1], toks[i + 2]), ()):
            s = i - off
            pat = PATS[k]
            if s < 0 or s + len(pat) > len(toks):
                continue
            if all(p is None or p == toks[s + j] for j, p in enumerate(pat)):
                parts = path.name.split(".")
                out.append({"example": k, "work": f"{parts[0]}.{parts[1]}", "cite": cites[s],
                            "file": path.name})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    pats, anchors = load_examples(HERE / "examples.jsonl")
    files = sorted(p for repo in ("canonical-greekLit", "First1KGreek")
                   for p in (TEI / repo / "data").glob("*/*/*grc*.xml"))
    print(f"editions {len(files)} examples {len(pats)}", flush=True)
    t0, n = time.time(), 0
    with mp.Pool(args.workers, initializer=init, initargs=(pats, anchors)) as pool, \
            open(HERE / "tei_matches.jsonl", "w", encoding="utf-8") as out:
        for k, res in enumerate(pool.imap_unordered(scan, files, chunksize=4), 1):
            n += len(res)
            for m in res:
                out.write(json.dumps(m, ensure_ascii=False) + "\n")
            if k % 200 == 0 or k == len(files):
                print(f"progress {k}/{len(files)} matches={n} elapsed={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
