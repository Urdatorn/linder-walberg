"""Author and work names for corpus record ids.

OGA records carry CTS ids ("tlg0018.tlg005.1st1K-grc1"); their names come
from the __cts__.xml catalogue files of PerseusDL/canonical-greekLit and
OpenGreekAndLatin/First1KGreek, fetched once and cached in names.json.
Internet Archive and Google Books scans get their title and creator from
archive.org's metadata API, also cached.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "names.json"
REPOS = ["https://raw.githubusercontent.com/PerseusDL/canonical-greekLit/master/data",
         "https://raw.githubusercontent.com/OpenGreekAndLatin/First1KGreek/master/data"]


def _get(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def _cts_name(xml: str | None, tag: str) -> str | None:
    if not xml:
        return None
    names = re.findall(rf"<(?:ti:)?{tag}[^>]*xml:lang=\"(\w+)\"[^>]*>([^<]+)<", xml)
    if not names:
        names = [("", n) for n in re.findall(rf"<(?:ti:)?{tag}[^>]*>([^<]+)<", xml)]
    if not names:
        return None
    pref = {"lat": 0, "eng": 1, "": 2, "grc": 3}
    return sorted(names, key=lambda x: pref.get(x[0], 4))[0][1].strip()


class Names:
    def __init__(self):
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    def save(self):
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1))

    def cts(self, group: str, work: str | None) -> tuple[str | None, str | None]:
        key = f"cts:{group}.{work}"
        if key not in self.cache:
            author = title = None
            for repo in REPOS:
                author = author or _cts_name(_get(f"{repo}/{group}/__cts__.xml"), "groupname")
                if work:
                    title = title or _cts_name(_get(f"{repo}/{group}/{work}/__cts__.xml"), "title")
                if author and (title or not work):
                    break
            self.cache[key] = [author, title]
        return tuple(self.cache[key])

    def archive(self, item: str) -> tuple[str | None, str | None]:
        key = f"ia:{item}"
        if key not in self.cache:
            meta = _get(f"https://archive.org/metadata/{item}/metadata")
            creator = title = None
            if meta:
                m = json.loads(meta).get("result", {})
                title = m.get("title")
                creator = m.get("creator")
                title = title[0] if isinstance(title, list) else title
                creator = creator[0] if isinstance(creator, list) else creator
            self.cache[key] = [creator, title]
        return tuple(self.cache[key])


    def prefetch(self, archive_items: list[str], cts_ids: list[tuple[str, str | None]], workers: int = 12) -> None:
        """Fetch many names at once (each fetch is one HTTP request)."""
        from concurrent.futures import ThreadPoolExecutor
        todo_a = [i for i in dict.fromkeys(archive_items) if f"ia:{i}" not in self.cache]
        todo_c = [c for c in dict.fromkeys(cts_ids) if f"cts:{c[0]}.{c[1]}" not in self.cache]
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(self.archive, todo_a))
            list(pool.map(lambda c: self.cts(*c), todo_c))
        self.save()
