"""Look for the Greek examples of Linder & Walberg in the AncientGreek corpus.

Each example (a Greek phrase of three or more words from the dictionary,
locorum/examples.jsonl) is matched against every record of
Ericu950/AncientGreek, both tiers, after reducing both sides to bare letters
(no accents or breathings, ς = σ, no punctuation). The lexicographers' stand-in
pronouns (τις, τι, τινά, τινί, τινός ...) match any word, since "χρῆταί τίς
τινι" stands for a phrase with real persons. A match must cover the whole
example, word for word.

Every example is anchored on the first three words of its longest run of
fixed words; the corpus is scanned once, in parallel, and each position whose
three words equal an anchor is checked against the whole example.

  locorum/matches.jsonl       up to a few passages per example and parallel
                              job, from the best-ranked sources (OGA texts with
                              TLG ids first): record id, position, context
  locorum/match_counts.json   every example's total number of matching records

    python find_sources.py --corpus <snapshot>/data --workers 32
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
WILD = {"τισ", "τι", "τινα", "τινι", "τινοσ", "τινεσ", "τινων", "τισι", "τισιν", "τινασ", "τινε",
        "τινοιν", "ουτινοσ"}
CONTEXT = 18          # words of context on each side of a match


def make_table() -> dict[int, str | None]:
    """Lower-case, bare-letter mapping for every character the corpus has."""
    table: dict[int, str | None] = {}
    for cp in list(range(0x0370, 0x0400)) + list(range(0x1F00, 0x2000)):
        ch = chr(cp)
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c)).lower()
        if base.isalpha():
            table[cp] = base.replace("ς", "σ")
        elif unicodedata.category(ch).startswith("M"):
            table[cp] = None
        else:
            table[cp] = " "
    for cp in range(0x0300, 0x0370):
        table[cp] = None
    for ch in "ς":
        table[ord(ch)] = "σ"
    for cp in range(0x2000, 0x2070):           # general punctuation
        table[cp] = " "
    for ch in ".,;:·!?()[]{}<>\"'’ʼ᾽‘“”«»—–-‐_/\\*†‡|=+0123456789\n\t\r":
        table[ord(ch)] = " "
    return table


TABLE = make_table()


def norm(text: str) -> list[str]:
    return text.lower().translate(TABLE).split()


def load_examples(path: Path) -> tuple[list[list[str | None]], dict[tuple[str, str, str], list[tuple[int, int]]]]:
    pats, anchors = [], {}
    for k, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        toks = norm(json.loads(line)["greek"])
        pat = [None if t in WILD else t for t in toks]
        pats.append(pat)
        best, run = (0, 0), 0                 # longest run of fixed words: (length, end)
        for i, t in enumerate(pat):
            run = run + 1 if t is not None else 0
            if run > best[0]:
                best = (run, i + 1)
        if best[0] >= 3:
            start = best[1] - best[0]
            anchors.setdefault(tuple(pat[start:start + 3]), []).append((k, start))
    return pats, anchors


def init(pats_, anchors_) -> None:
    global PATS, ANCHORS, FIRST
    PATS, ANCHORS = pats_, anchors_
    FIRST = {a[0] for a in anchors_}


RANK = {"oga": 0, "catholic": 1, "sblgnt": 1, "pg": 2, "gutenberg": 3, "greek_pd": 4, "ia": 5, "ddbdp": 6, "dclp": 6}
KEEP = 4              # passages kept per example per job (the best-ranked sources)


def scan(job: tuple[str, int, int, int]) -> tuple[dict[int, int], list[dict]]:
    """Count every full match per example; keep a few passages of each."""
    import pyarrow.parquet as pq
    path, rg, first, last = job
    counts: dict[int, int] = {}
    kept: dict[int, list[dict]] = {}
    t = pq.ParquetFile(path).read_row_group(rg, columns=["source", "id", "text"]).slice(first, last - first)
    if True:
        for row, (src, rid, text) in enumerate(zip(t["source"].to_pylist(), t["id"].to_pylist(),
                                                    t["text"].to_pylist()), start=first):
            toks = norm(text or "")
            seen = set()
            for i in range(len(toks) - 2):
                if toks[i] not in FIRST:
                    continue
                for k, off in ANCHORS.get((toks[i], toks[i + 1], toks[i + 2]), ()):
                    s = i - off
                    pat = PATS[k]
                    if s < 0 or s + len(pat) > len(toks) or k in seen:
                        continue
                    if all(p is None or p == toks[s + j] for j, p in enumerate(pat)):
                        seen.add(k)
                        counts[k] = counts.get(k, 0) + 1
                        bucket = kept.setdefault(k, [])
                        m = {"example": k, "source": src, "id": rid, "file": os.path.basename(path),
                             "row_group": rg, "row": row, "at": min(s, CONTEXT),
                             "context": " ".join(toks[max(0, s - CONTEXT):s + len(pat) + CONTEXT])}
                        if len(bucket) < KEEP:
                            bucket.append(m)
                        else:
                            worst = max(range(KEEP), key=lambda b: RANK.get(bucket[b]["source"], 9))
                            if RANK.get(src, 9) < RANK.get(bucket[worst]["source"], 9):
                                bucket[worst] = m
    return counts, [m for b in kept.values() for m in b]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, required=True, help="the dataset's data/ directory")
    ap.add_argument("--examples", type=Path, default=HERE / "examples.jsonl")
    ap.add_argument("--out", type=Path, default=HERE / "matches.jsonl")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    args = ap.parse_args()

    import pyarrow.parquet as pq
    pats, anchors = load_examples(args.examples)
    print(f"examples {len(pats)} anchored {sum(len(v) for v in anchors.values())} "
          f"distinct anchors {len(anchors)}", flush=True)
    jobs = []
    for f in sorted(args.corpus.glob("*/*.parquet")):
        meta = pq.ParquetFile(f).metadata
        for rg in range(meta.num_row_groups):
            n = meta.row_group(rg).num_rows
            jobs += [(str(f), rg, a, min(n, a + 20000)) for a in range(0, n, 20000)]
    print(f"jobs {len(jobs)} workers {args.workers}", flush=True)
    t0, done, found = time.time(), 0, 0
    total: dict[int, int] = {}
    with mp.Pool(args.workers, initializer=init, initargs=(pats, anchors)) as pool, \
            open(args.out, "w", encoding="utf-8") as out:
        for counts, res in pool.imap_unordered(scan, jobs):
            done += 1
            for k, c in counts.items():
                total[k] = total.get(k, 0) + c
            found += sum(counts.values())
            for m in res:
                out.write(json.dumps(m, ensure_ascii=False) + "\n")
            if done % 20 == 0 or done == len(jobs):
                el = time.time() - t0
                print(f"progress jobs={done}/{len(jobs)} matches={found} elapsed={el:.0f}s "
                      f"eta={el / done * (len(jobs) - done):.0f}s", flush=True)
    (args.out.parent / "match_counts.json").write_text(json.dumps(total))
    print(f"done matches={found} examples_matched={len(total)} seconds={time.time() - t0:.0f}", flush=True)


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
