"""Plain HTML pages for search engines, beside the app (called by build_app.py).

The app shows everything at addresses after a '#' (#e/123), which search engines do
not see as pages of their own: to Google the whole app is a single page. So every
entry is also written as a page of its own, readable without JavaScript, at an
address made from its headword, and these pages are listed for Google in a sitemap:

  ord/<headword>/index.html   one page per entry: …/linder-walberg/ord/mörker/
  register/index.html         the letters, and the book's own sections
  register/<letter>/index.html  every headword under that letter, linked
  sitemap.xml                 the app, the registers and every entry page
  page.css                    the pages' look (with fonts/ and dictionary.css)

Each page links on to the app (the same entry there), to the entries before and
after it, and to the register, so that a search engine can walk the whole book.
The service worker leaves all of this out: it is for search engines and for
readers who arrive from them, not for the offline app.
"""

from __future__ import annotations

import html
import re
import shutil
import unicodedata
from pathlib import Path
from urllib.parse import quote

SITE = "https://albinthorncleland.com/linder-walberg/"
BOOK = "Linder & Walberg, Svenskt-grekiskt lexikon (1862)"
HERE = Path(__file__).resolve().parent


def slugify(title: str) -> str:
    """'Mörker' -> 'mörker', 'Partes orationis: Adjektiv' -> 'partes-orationis-adjektiv'."""
    s = unicodedata.normalize("NFC", title.lower())
    s = re.sub(r"[\s\-‐—–]+", "-", s)
    s = "".join(c for c in s if c.isalnum() or c == "-")
    return re.sub(r"-{2,}", "-", s).strip("-") or "ord"


def slugs_for(records: list[dict]) -> list[str]:
    """One address per entry; homographs and anything else that comes out alike get -2, -3 …"""
    seen: dict[str, int] = {}
    out = []
    for r in records:
        base = slugify(r["title"])
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append(base if n == 1 else f"{base}-{n}")
    assert len(set(out)) == len(out)
    return out


def plain(fragment: str) -> str:
    """The entry's text without its headword, page reference or markup, for the description."""
    fragment = re.sub(r"<h1[^>]*>.*?</h1>|<div class=\"src\">.*?</div>", " ", fragment, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    text = re.sub(r"\(\s+", "(", re.sub(r"\s+([.,;:)])", r"\1", re.sub(r"\s+", " ", text))).strip()
    return text


def clip(text: str, n: int = 150) -> str:
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",;:") + " …"


def url(slug: str) -> str:
    return f"{SITE}ord/{quote(slug)}/"


PAGE = """<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="Svenskt-grekiskt lexikon">
<meta property="og:locale" content="sv_SE">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{site}front.png">
<meta name="theme-color" content="#f6f2e9" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#17160f" media="(prefers-color-scheme: dark)">
<link rel="icon" href="{root}icons/icon-192.png">
<link rel="apple-touch-icon" href="{root}icons/icon-180.png">
<link rel="stylesheet" href="{root}fonts/fonts.css">
<link rel="stylesheet" href="{root}dictionary.css">
<link rel="stylesheet" href="{root}page.css">
</head>
<body>
<header>
  <a class="home" href="{root}">Svenskt-grekiskt lexikon <span>Linder &amp; Walberg 1862</span></a>
  <form action="{root}" role="search" onsubmit="location.href=this.action+'#s/'+encodeURIComponent(this.q.value.trim());return false">
    <input name="q" type="search" placeholder="Sök svenskt eller grekiskt ord" aria-label="Sök" autocomplete="off" autocapitalize="off" spellcheck="false">
  </form>
</header>
<main>
{body}
</main>
<footer>
{nav}
  <p><a href="{root}">Svenskt-grekiskt lexikon</a> av C. W. Linder och C. A. Walberg, Upsala 1862.
  Hela ordboken, sökbar på svenska och grekiska, fungerar även utan nät och kan sparas som app på hemskärmen.
  · <a href="{root}register/">Alla ord</a> · <a href="https://github.com/Urdatorn/linder-walberg">Källkod och data</a></p>
</footer>
</body>
</html>
"""


def page(*, title: str, og_title: str, description: str, canonical: str, root: str, body: str, nav: str = "",
         og_type: str = "article") -> str:
    e = lambda s: html.escape(s, quote=True)  # noqa: E731
    return PAGE.format(title=e(title), og_title=e(og_title), description=e(description), canonical=e(canonical),
                       root=root, body=body, nav=nav, og_type=og_type, site=SITE)


def letter_of(title: str) -> str:
    c = unicodedata.normalize("NFC", title[:1].upper())
    return c if c.isalpha() else "#"


def write(dist: Path, records: list[dict], htmls: list[str], slugs: list[str], is_entry: list[bool]) -> list[str]:
    """Write the pages, from the entries' html as the app has it (links #e/<n>, #s/<word>, img/);
    returns their addresses, for the sitemap."""
    root = "../../"
    ordered = [i for i in range(len(records)) if is_entry[i]]       # the dictionary's own articles, in book order
    pos = {n: k for k, n in enumerate(ordered)}
    out = dist / "ord"
    urls = []

    def relink(fragment: str) -> str:
        # within the book: to the other entry's page; a search: in the app
        fragment = re.sub(r'href="#e/(\d+)"', lambda m: f'href="../{quote(slugs[int(m.group(1))])}/"', fragment)
        fragment = re.sub(r'href="#s/', f'href="{root}#s/', fragment)
        return fragment.replace('src="img/', f'src="{root}img/')

    for i, r in enumerate(records):
        text = plain(htmls[i])
        if is_entry[i]:
            title = f"{r['title']} på grekiska – {BOOK}"
            description = clip(f"{r['title']}: {text}" if text else r["title"]) + " Ur Linder & Walbergs svenskt-grekiska lexikon, 1862."
        else:
            title = f"{r['title']} – {BOOK}"
            description = clip(text or r["title"]) + f" {BOOK}."
        links = []
        if i in pos:
            k = pos[i]
            if k > 0:
                p = ordered[k - 1]
                links.append(f'<a rel="prev" href="../{quote(slugs[p])}/">← {html.escape(records[p]["title"])}</a>')
            if k + 1 < len(ordered):
                n = ordered[k + 1]
                links.append(f'<a rel="next" href="../{quote(slugs[n])}/">{html.escape(records[n]["title"])} →</a>')
        nav = (f'  <nav class="prevnext">{"".join(links)}</nav>\n' if links else "") + \
              f'  <p class="open"><a href="{root}#e/{i}">Öppna i appen</a> · ' \
              f'<a href="{root}register/{quote(letter_of(r["title"]))}/">Fler ord på {html.escape(letter_of(r["title"]))}</a></p>\n'
        body = f'<article class="entry-page">\n{relink(htmls[i])}\n</article>'
        d = out / slugs[i]
        d.mkdir(parents=True)
        (d / "index.html").write_text(page(title=title, og_title=r["title"], description=description,
                                           canonical=url(slugs[i]), root=root, body=body, nav=nav),
                                      encoding="utf-8")
        urls.append(url(slugs[i]))

    # the registers: the letters, then one page per letter
    letters: dict[str, list[int]] = {}
    for i in ordered:
        letters.setdefault(letter_of(records[i]["title"]), []).append(i)
    reg = dist / "register"
    for letter, items in letters.items():
        d = reg / letter
        d.mkdir(parents=True)
        lis = "\n".join(f'<li><a href="../../ord/{quote(slugs[i])}/">{html.escape(records[i]["title"])}</a></li>' for i in items)
        tabs = " ".join(f'<a href="../{quote(L)}/"{" aria-current=page" if L == letter else ""}>{html.escape(L)}</a>' for L in letters)
        body = f'<h1 class="hw">Ord på {html.escape(letter)}</h1>\n<nav class="letters">{tabs}</nav>\n<ul class="words">\n{lis}\n</ul>'
        first, last = records[items[0]]["title"], records[items[-1]]["title"]
        (d / "index.html").write_text(page(
            title=f"Ord på {letter} – {BOOK}", og_title=f"Ord på {letter}", og_type="website",
            description=f"De {len(items)} uppslagsorden på {letter}, från {first} till {last}, med sin grekiska. {BOOK}.",
            canonical=f"{SITE}register/{quote(letter)}/", root="../../", body=body), encoding="utf-8")
        urls.append(f"{SITE}register/{quote(letter)}/")
    sections = "\n".join(f'<li><a href="../ord/{quote(slugs[i])}/">{html.escape(records[i]["title"])}</a></li>'
                         for i in range(len(records)) if not is_entry[i] and ":" not in records[i]["title"])
    tabs = " ".join(f'<a href="{quote(L)}/">{html.escape(L)}</a>' for L in letters)
    count = f"{len(ordered):,}".replace(",", "\u00a0")
    body = (f'<h1 class="hw">Alla ord</h1>\n<p>{count} uppslagsord, svenska ord med sin grekiska, '
            f'i C. W. Linder och C. A. Walbergs <i>Svenskt-grekiskt lexikon</i> (Upsala 1862).</p>\n'
            + f'<nav class="letters">{tabs}</nav>\n<h2>I boken</h2>\n<ul class="words">\n{sections}\n</ul>')
    (reg / "index.html").write_text(page(
        title=f"Alla ord – {BOOK}", og_title="Alla ord", og_type="website", root="../",
        description=f"Alla {len(ordered)} uppslagsord i Linder och Walbergs svenskt-grekiska lexikon från 1862, i bokstavsordning.",
        canonical=f"{SITE}register/", body=body), encoding="utf-8")
    urls.insert(0, f"{SITE}register/")

    shutil.copy(HERE / "pages/page.css", dist / "page.css")
    sitemap = "".join(f"<url><loc>{html.escape(u)}</loc></url>\n" for u in [SITE] + urls)
    (dist / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      + sitemap + "</urlset>\n", encoding="utf-8")
    return urls
