"""Compile the index locorum from the corpus matches (find_sources.py).

An example is a locus when it occurs in at most MAX_RECORDS corpus records
(more means a stock phrase, not a quotation) and those records belong to at
most MAX_AUTHORS ancient authors. Authors and works are named as in LSJ
(H. G. Liddell & R. Scott, 9th ed.; list from logeion.uchicago.edu):

  OGA texts       by TLG number, through the LSJ citations of the Perseus LSJ,
                  which tag each citation with its TLG work (tlg_lsj.json)
  Loeb texts      by the author named in the record ("De bellis (Procopius)")
  scanned books   by the creator in archive.org's catalogue, when it is an
                  ancient author (editions of the classics); modern works
                  (lexica, grammars, commentaries) are left out

  locorum/index_locorum.json  authors in alphabetical order, their works and
                              loci, each locus with the entries that use it
  locorum/examples.tsv        every Greek example with its status

    python build_index.py
"""

from __future__ import annotations

import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

from names import Names

HERE = Path(__file__).resolve().parent
MAX_RECORDS = 10
# authors LSJ cites by number (speech, letter), which is also their TLG work number
NUMBERED = {"D.", "Lys.", "Isoc.", "Aeschin.", "Is.", "And.", "Antipho", "Din.", "Lycurg.", "Hyp.", "D.Chr.", "Lib."}
MAX_AUTHORS = 3


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))


class LSJ:
    """LSJ authors and works, and the TLG-to-LSJ table."""

    def __init__(self):
        self.authors = json.loads((HERE / "lsj_authors.json").read_text(encoding="utf-8"))
        tlg = json.loads((HERE / "tlg_lsj.json").read_text(encoding="utf-8"))
        self.tlg_group, self.tlg_work = tlg["group"], tlg["work"]
        self.by_abbr = collections.defaultdict(list)
        for a in self.authors:
            self.by_abbr[a["abbr"]].append(a)
        # Homer is cited by poem alone (Il., Od.); the Hymns as h.Ap. etc.
        homer = next(a for a in self.authors if a["name"] == "Homerus")
        homer["works"].update({"Il.": "Ilias", "Od.": "Odyssea"})
        self.by_abbr["Il."] = self.by_abbr["Od."] = [homer]

    def author(self, abbr: str | None, hint: str | None = None) -> dict | None:
        cands = self.by_abbr.get(abbr or "", [])
        if len(cands) > 1 and hint:
            cands = sorted(cands, key=lambda a: -len(set(fold(hint).split()) & set(fold(a["name"] + " " + a["desc"]).split())))
        return cands[0] if cands else None

    def by_name(self, name: str | None) -> dict | None:
        """An LSJ author from a modern catalogue name ("Plutarch", "Thucydides, 455-395 B.C.")."""
        if not name:
            return None
        n = fold(re.split(r"[,(;]| \d", name)[0]).strip()
        if len(n) < 4:
            return None
        best = None
        for a in self.authors:
            f = fold(a["name"])
            if f == n or (len(n) >= 5 and (f.startswith(n) or n.startswith(f)) and abs(len(f) - len(n)) <= 3):
                if best is None or len(a["works"]) > len(best["works"]):
                    best = a                  # of namesakes, the main author (most works)
        return best

    def work(self, author: dict, abbr: str | None, title: str | None = None) -> tuple[str, str]:
        if abbr:
            return abbr, author["works"].get(abbr, "")
        if title:
            t = fold(title)
            for w, full in author["works"].items():
                if fold(full) and (fold(full) in t or t in fold(full)):
                    return w, full
        return "", ""


def resolve(m: dict, lsj: LSJ, names: Names) -> tuple[dict, str, str] | None:
    src, rid = m["source"], m["id"]
    if src == "oga":
        parts = rid.split(".")
        if not parts[0].startswith("tlg") or len(parts) < 2:
            return None
        key = f"{parts[0]}.{parts[1]}"
        a_abbr, w_abbr = lsj.tlg_work.get(key, [lsj.tlg_group.get(parts[0]), ""])
        if a_abbr in ("Il.", "Od."):
            w_abbr = a_abbr
        author = lsj.author(a_abbr, names.cts(parts[0], None)[0])
        if not author:
            return None
        w, full = lsj.work(author, w_abbr)
        if not w and author["abbr"] in NUMBERED and len(parts) > 1:
            w = str(int(parts[1][3:]))            # LSJ cites the orators by speech: D. 18
        return author, w, full
    if src == "catholic":
        mm = re.search(r"/([^/(]+?)\s*\(([^)]+)\)", rid)
        if not mm:
            return None
        author = lsj.by_name(mm.group(2))
        if not author:
            return None
        w, full = lsj.work(author, None, mm.group(1))
        return author, w, full or mm.group(1).strip()
    if src in ("greek_pd", "ia"):
        creator, title = names.archive(rid.split("#")[0])
        author = lsj.by_name(creator)
        if not author:
            return None
        w, full = lsj.work(author, None, title)
        return author, w, full
    return None


def main() -> None:
    lsj, names = LSJ(), Names()
    examples = [json.loads(l) for l in (HERE / "examples.jsonl").read_text(encoding="utf-8").splitlines()]
    counts = {int(k): v for k, v in json.loads((HERE / "match_counts.json").read_text()).items()}
    by_ex = collections.defaultdict(list)
    for line in (HERE / "matches.jsonl").read_text(encoding="utf-8").splitlines():
        m = json.loads(line)
        if counts.get(m["example"], 0) <= MAX_RECORDS:
            by_ex[m["example"]].append(m)

    names.prefetch([m["id"].split("#")[0] for ms in by_ex.values() for m in ms if m["source"] in ("ia", "greek_pd")],
                   [(m["id"].split(".")[0], None) for ms in by_ex.values() for m in ms
                    if m["source"] == "oga" and m["id"].startswith("tlg")])
    print("names fetched", flush=True)
    loci = collections.defaultdict(lambda: collections.defaultdict(list))   # author name -> work -> loci
    status = {}
    done = 0
    for k, ms in by_ex.items():
        found = {}
        for m in ms:
            r = resolve(m, lsj, names)
            if r:
                author, w, full = r
                found.setdefault((author["name"], author["desc"], author["abbr"], w, full), m)
        done += 1
        if done % 200 == 0:
            names.save()
            print(f"resolved {done}/{len(by_ex)}", flush=True)
        if not found or len({f[:3] for f in found}) > MAX_AUTHORS:
            status[k] = "no ancient author" if not found else "several authors"
            continue
        status[k] = "locus"
        for (name, desc, abbr, w, full), m in found.items():
            loci[(name, desc, abbr)][(w, full)].append({"example": k, "context": m["context"], "record": m["id"]})
    names.save()

    # several examples can be the same Greek phrase from different entries: one locus, several entries
    out = []
    for (name, desc, abbr), works in sorted(loci.items(), key=lambda x: (fold(x[0][0]), x[0][1])):
        wl = []
        for (w, full), items in sorted(works.items(),
                                       key=lambda x: (not x[0][0], x[0][0].isdigit(), int(x[0][0]) if x[0][0].isdigit() else 0,
                                                      fold(x[0][0]))):
            phrases = collections.OrderedDict()
            for it in items:
                ex = examples[it["example"]]
                p = phrases.setdefault(ex["greek"], {"greek": ex["greek"], "entries": [], "context": it["context"]})
                e = {"headword": ex["headword"], "page": ex["page"]}
                if e not in p["entries"]:
                    p["entries"].append(e)
            wl.append({"abbr": w, "title": full, "loci": sorted(phrases.values(), key=lambda p: fold(p["greek"]))})
        out.append({"name": name, "desc": desc, "abbr": abbr, "works": wl})
    (HERE / "index_locorum.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(HERE / "examples.tsv", "w", encoding="utf-8") as f:
        f.write("n\theadword\tprinted_page\tswedish\tgreek\twords\tcorpus_records\tstatus\n")
        for ex in examples:
            k = ex["n"]
            st = status.get(k) or ("stock phrase" if counts.get(k, 0) > MAX_RECORDS else
                                   "not found" if k not in counts else "no ancient author")
            f.write(f"{k}\t{ex['headword']}\t{int(ex['page']) - 4}\t{ex['swedish']}\t{ex['greek']}\t"
                    f"{ex['words']}\t{counts.get(k, 0)}\t{st}\n")
    n_loci = sum(len(w["loci"]) for a in out for w in a["works"])
    print(f"authors {len(out)} works {sum(len(a['works']) for a in out)} loci {n_loci}",
          collections.Counter(status.values()))


if __name__ == "__main__":
    sys.exit(main())
