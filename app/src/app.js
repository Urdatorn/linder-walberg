// Svenskt-grekiskt lexikon (Linder & Walberg 1862) as a web app.
// Views by location.hash: "" or #s/<query> search, #e/<n> an entry,
// #fav favourites, #dag the day's word, #loci the Index locorum, #om about.
"use strict";

const $ = (s) => document.querySelector(s);
// the build's version (index.html loads app.js?v=…): asked of every data file, so that a
// cache in front of the site (Cloudflare keeps .js and .json for hours) never mixes builds
const VERSION = new URL(document.currentScript.src).searchParams.get("v") || "";
const v = (url) => VERSION ? `${url}?v=${VERSION}` : url;
const view = $("#view"), q = $("#q");
let meta = null;
const keyFiles = new Map();
const chunks = new Map();

// ---------------------------------------------------------------- data

async function json(url) {
  const r = await fetch(v(url));
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
async function loadMeta() {
  if (!meta) {
    meta = await json("data/meta.json");
    // a favourite is kept by its headword (and its number among homographs), which stays
    // the same when the dictionary is rebuilt; entry numbers may not
    const seen = new Map();
    meta.favKey = meta.titles.map((t) => { const k = (seen.get(t) || 0) + 1; seen.set(t, k); return k > 1 ? `${t}#${k}` : t; });
    meta.byFavKey = new Map(meta.favKey.map((k, n) => [k, n]));
  }
  return meta;
}
// the search index, one file per first letter of the folded key
async function loadKeys(f) {
  const code = f.codePointAt(0).toString(16);
  if (!keyFiles.has(code)) keyFiles.set(code, json(`data/k/${code}.json`).catch(() => []));
  return keyFiles.get(code);
}
async function entryHtml(n) {
  const c = Math.floor(n / meta.chunk);
  if (!chunks.has(c)) chunks.set(c, json(`data/e/${String(c).padStart(2, "0")}.json`));
  return (await chunks.get(c))[String(n)];
}

// lower case, no accents or breathings, final sigma as sigma: as the index was built
function fold(s) {
  return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ς/g, "σ").replace(/’/g, "'").trim();
}
const isGreek = (s) => /[Ͱ-Ͽἀ-῿]/.test(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---------------------------------------------------------------- favourites (on this phone)

// {headword key: {on, at}}: removals are kept (on: false) so that they reach other devices (sync.js)
const FAV = "lw-favoriter-2", OLD_FAV = "lw-favoriter";
function favStore() { try { return JSON.parse(localStorage.getItem(FAV)) || {}; } catch { return {}; } }
function setFavStore(items) { try { localStorage.setItem(FAV, JSON.stringify(items)); } catch { /* private mode */ } }
function migrateFavs() {          // the first version kept a list of entry numbers
  try {
    const old = JSON.parse(localStorage.getItem(OLD_FAV));
    if (!Array.isArray(old)) return;
    const items = favStore(), now = Date.now();
    old.forEach((n, i) => { const k = meta.favKey[n]; if (k && !items[k]) items[k] = { on: true, at: now - i }; });
    setFavStore(items);
    localStorage.removeItem(OLD_FAV);
  } catch { /* nothing to move */ }
}
// favourites as entry numbers, the latest first
function favs() {
  return Object.entries(favStore()).filter(([k, v]) => v.on && meta.byFavKey.has(k))
    .sort((a, b) => b[1].at - a[1].at).map(([k]) => meta.byFavKey.get(k));
}
function isFav(n) { const v = favStore()[meta.favKey[n]]; return !!(v && v.on); }
function toggleFav(n) {
  const items = favStore(), on = !isFav(n);
  items[meta.favKey[n]] = { on, at: Date.now() };
  setFavStore(items);
  Sync.schedule();
  return on;
}

// ---------------------------------------------------------------- search

function lowerBound(arr, x) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid][0] < x) lo = mid + 1; else hi = mid; }
  return lo;
}

function search(keys, query, limit = 80) {
  const f = fold(query);
  if (!f) return [];
  const out = [], seen = new Set();
  for (let i = lowerBound(keys, f); i < keys.length && keys[i][0].startsWith(f); i++) {
    const [fk, key, n] = keys[i];
    if (seen.has(n)) continue;
    seen.add(n);
    out.push({ key, n, exact: fk === f, greek: isGreek(key) });
    if (out.length >= limit * 4) break;
  }
  // exact matches first, then Swedish before Greek, then shorter keys
  out.sort((a, b) => (b.exact - a.exact) || (a.greek - b.greek) || (a.key.length - b.key.length) || a.key.localeCompare(b.key, "sv"));
  return out.slice(0, limit);
}

let searchToken = 0;
async function showSearch(query) {
  setBar("search");
  if (q.value !== query) q.value = query;
  if (!query.trim()) {
    view.innerHTML = `<div class="front-page"><img src="${v("front.png")}" alt="Svenskt-grekiskt lexikon, utgifvet af C. W. Linder och C. A. Walberg"></div>`;
    return;
  }
  const token = ++searchToken;
  const keys = await loadKeys(fold(query) || " ");
  if (token !== searchToken) return;
  const hits = search(keys, query);
  if (!hits.length) { view.innerHTML = `<p class="empty">Inga träffar på ”${esc(query)}”.</p>`; return; }
  view.innerHTML = `<ul class="results">${hits.map((h) => {
    const title = meta.titles[h.n];
    const to = h.key === title ? "" : `<span class="to">${esc(title)}</span>`;
    return `<li><a href="#e/${h.n}"><span class="key${h.greek ? " greek" : ""}">${esc(h.key)}</span>${to}</a></li>`;
  }).join("")}</ul>`;
}

// ---------------------------------------------------------------- pages

function setBar(mode, title = "", n = null) {
  $("#search-row").hidden = mode !== "search";
  $("#title-row").hidden = mode === "search";
  $("#back").hidden = mode !== "entry";
  $("#bar-title").textContent = title;
  const star = $("#star");
  star.hidden = n === null;
  if (n !== null) {
    star.dataset.n = n;
    star.setAttribute("aria-pressed", String(isFav(n)));
    star.setAttribute("aria-label", isFav(n) ? "Ta bort från favoriter" : "Lägg till i favoriter");
  }
}

async function showEntry(n, { label = "" } = {}) {
  const html = await entryHtml(n);
  if (html === undefined) { view.innerHTML = `<p class="empty">Artikeln finns inte.</p>`; return; }
  setBar("entry", "", n);
  view.innerHTML = `<article class="entry-page">${label}${html}</article>`;
}

async function showDay() {
  const d = new Date();
  const day = Math.floor((Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
  // a fixed shuffle of the candidates, one a day, the same for everyone
  const n = meta.daily[(day * 7919) % meta.daily.length];
  const date = d.toLocaleDateString("sv-SE", { day: "numeric", month: "long" });
  await showEntry(n, { label: `<p class="day-label">Dagens ord · ${esc(date)}</p>` });
  $("#back").hidden = true;
}

// one line on the state of the sync, shown only to those who signed in
function syncLine() {
  if (!Sync.user()) return "";
  const s = Sync.status(), who = esc(Sync.user());
  const text = {
    syncing: `Synkar med ${who} på Hugging Face …`,
    ok: `Synkade med ${who} på Hugging Face ${s.at ? new Date(s.at).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" }) : ""}`,
    offline: "Ingen anslutning – synkar när du är online igen.",
    expired: `Inloggningen har gått ut. <a href="#om">Logga in igen</a>`,
    error: `Kunde inte synka med Hugging Face.`,
  }[s.state] || `Synkas med ${who} på Hugging Face`;
  return `<p class="sync-line">${text}</p>`;
}

function showFavs() {
  setBar("list", "Favoriter");
  const list = favs();
  view.innerHTML = syncLine() + (list.length
    ? `<ul class="results">${list.map((n) => `<li><a href="#e/${n}"><span class="key">${esc(meta.titles[n] || "")}</span></a></li>`).join("")}</ul>`
    : `<p class="empty">Inga favoriter ännu.<br>Tryck på stjärnan i en artikel för att spara den här.</p>`);
}

// the sign-in rows under Om; nothing at all where sign-in is not available (outside the Space)
function syncSection() {
  if (!Sync.available()) return "";
  const user = Sync.user();
  if (!user) return `<p class="list-head">Synkronisering</p>
    <ul class="links"><li><a href="#" id="hf-login">Logga in med Hugging Face</a></li></ul>
    <p class="small">Valfritt. Favoriterna sparas då i ett privat dataset på ditt Hugging Face-konto och följer med
    mellan dator och telefon. Appen kommer bara åt det datasetet.</p>`;
  const expired = Sync.status().state === "expired";
  return `<p class="list-head">Synkronisering</p>
    <ul class="links">
      ${expired ? `<li><a href="#" id="hf-login">Logga in igen <span>${esc(user)}</span></a></li>` : `<li><a href="#fav">Favoriterna synkas <span>${esc(user)}</span></a></li>`}
      <li><a href="#" id="hf-logout">Logga ut <span>favoriterna finns kvar här</span></a></li>
    </ul>`;
}

async function showLoci() {
  const n = meta.special.lw_locorum;
  await showEntry(n);
  $("#back").hidden = true;
  $("#star").hidden = true;
}
function setTitle(t) { $("#bar-title").textContent = t; }

function showAbout() {
  setBar("list", "Om");
  const s = meta.special;
  view.innerHTML = `<div class="about">
    <h1 class="hw">Svenskt-grekiskt lexikon</h1>
    <p>C. W. Linder och C. A. Walberg, <i>Svenskt-grekiskt lexikon</i>, Upsala 1862. Texten är tolkad ur sidbilderna,
    korrekturläst mot dem och rättad efter bokens tryckfelsförteckning och en granskning av grekiskan.
    Κῦδος till Johan Winge som ursprungligen digitaliserade boken i januari 2013 och gjorde en första ansats
    till OCR-tolkning i oktober samma år.</p>
    <p class="list-head">I boken</p>
    <ul class="links">
      <li><a href="#e/${s.lw_preface}">Förord</a></li>
      <li><a href="#e/${s.lw_abbr}">Förkortningar</a></li>
      <li><a href="#e/${s.lw_linder}">Carl Wilhelm Linder</a></li>
      <li><a href="#e/${s.lw_walberg}">Carl August Walberg</a></li>
    </ul>
    ${syncSection()}
    <p class="list-head">Källor och data</p>
    <ul class="links">
      <li><a href="https://github.com/Urdatorn/linder-walberg" target="_blank" rel="noopener">Källkod <span>GitHub</span></a></li>
      <li><a href="https://huggingface.co/datasets/Urdatorn/linder-walberg" target="_blank" rel="noopener">Ny OCR-data <span>Hugging Face</span></a></li>
      <li><a href="https://runeberg.org/svegrek/" target="_blank" rel="noopener">Första elektroniska utgåvan <span>Project Runeberg</span></a></li>
      <li><a href="https://albinthorncleland.com" target="_blank" rel="noopener">Albin Thörn Cleland <span>albinthorncleland.com</span></a></li>
    </ul>
    <p class="small">Utgåva och app: Albin Thörn Cleland. Sidbilderna kommer från Project Runeberg.
    Grekiskan är satt i GFS Porson (Greek Font Society), svenskan i Gentium Book Plus (SIL). ${meta.count - 6} artiklar.</p>
  </div>`;
}

// ---------------------------------------------------------------- routing

async function route() {
  await loadMeta();
  const h = decodeURIComponent(location.hash.slice(1));
  const tab = h.startsWith("e/") ? null : h === "fav" ? "fav" : h === "dag" ? "dag" : h === "loci" ? "loci" : h === "om" ? "om" : "sok";
  if (tab) document.querySelectorAll("#tabs a").forEach((a) => a.setAttribute("aria-current", a.dataset.tab === tab ? "page" : "false"));
  try {
    if (h.startsWith("e/")) await showEntry(Number(h.slice(2)));
    else if (h === "fav") showFavs();
    else if (h === "dag") await showDay();
    else if (h === "loci") await showLoci();
    else if (h === "om") showAbout();
    else await showSearch(h.startsWith("s/") ? h.slice(2) : "");
  } catch (e) {
    view.innerHTML = `<p class="empty">Det gick inte att läsa in sidan. Kontrollera anslutningen och försök igen.</p>`;
  }
  if (!h.startsWith("s/") && h !== "") window.scrollTo(0, 0);
}

q.addEventListener("input", () => {
  const target = q.value ? "#s/" + encodeURIComponent(q.value) : "#";
  history.replaceState(null, "", target === "#" ? location.pathname : target);
  showSearch(q.value);
});
q.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    q.blur();
    const first = view.querySelector(".results a");
    if (first) location.hash = first.getAttribute("href");
  }
});
$("#back").addEventListener("click", () => (history.length > 1 ? history.back() : (location.hash = "")));
$("#star").addEventListener("click", (e) => {
  const n = Number(e.currentTarget.dataset.n);
  const on = toggleFav(n);
  e.currentTarget.setAttribute("aria-pressed", String(on));
  e.currentTarget.setAttribute("aria-label", on ? "Ta bort från favoriter" : "Lägg till i favoriter");
});
// the search tab clears the search and opens the front page
document.querySelector('#tabs a[data-tab="sok"]').addEventListener("click", (e) => {
  e.preventDefault();
  history.pushState(null, "", location.pathname);
  q.value = "";
  route();
});
// the bars' real heights (safe areas, text size), for centring the title page between them
function measureBars() {
  const root = document.documentElement.style;
  root.setProperty("--bar-bottom", $("#bar").getBoundingClientRect().bottom + "px");
  root.setProperty("--tabs-height", (window.innerHeight - $("#tabs").getBoundingClientRect().top) + "px");
}
new ResizeObserver(measureBars).observe($("#bar"));
new ResizeObserver(measureBars).observe($("#tabs"));
window.addEventListener("resize", measureBars);
measureBars();
window.addEventListener("hashchange", route);
// a note for what has one (an abbreviation's full form, the headword behind its initial),
// shown on a tap, since phones have no hover
const note = document.createElement("div");
note.id = "note"; note.hidden = true; note.setAttribute("role", "tooltip");
document.body.append(note);
function showNote(el) {
  note.textContent = el.title;
  note.hidden = false;
  const r = el.getBoundingClientRect(), w = note.offsetWidth, h = note.offsetHeight;
  note.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
  note.style.top = (r.top - h - 8 > $("#bar").getBoundingClientRect().bottom ? r.top - h - 8 : r.bottom + 8) + "px";
}
const hideNote = () => { note.hidden = true; };
window.addEventListener("scroll", hideNote, { passive: true });
window.addEventListener("hashchange", hideNote);

// the Greek word under a tap, whole: letters with their accents, an elision mark inside
const GREEK_CHAR = /[\p{Script=Greek}\p{M}’'ʼ᾽]/u;
function greekWordAt(x, y) {
  let node, off;
  if (document.caretPositionFromPoint) {
    const p = document.caretPositionFromPoint(x, y); if (!p) return "";
    node = p.offsetNode; off = p.offset;
  } else if (document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(x, y); if (!r) return "";
    node = r.startContainer; off = r.startOffset;
  }
  if (!node || node.nodeType !== Node.TEXT_NODE) return "";
  const t = node.data;
  let a = off, b = off;
  while (a > 0 && GREEK_CHAR.test(t[a - 1])) a--;
  while (b < t.length && GREEK_CHAR.test(t[b])) b++;
  return t.slice(a, b).replace(/^['’ʼ᾽]+|['’ʼ᾽]+$/g, "");
}

view.addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (a && a.id === "hf-login") { e.preventDefault(); Sync.login(); return; }
  if (a && a.id === "hf-logout") { e.preventDefault(); Sync.logout(); showAbout(); return; }
  if (a) return;
  const titled = e.target.closest(".entry-page span[title]");
  if (titled) { if (note.hidden || note.textContent !== titled.title) showNote(titled); else hideNote(); return; }
  hideNote();
  // a Greek word: search for it
  if (e.target.closest(".entry-page .gk")) {
    const word = greekWordAt(e.clientX, e.clientY);
    if (word && /\p{Script=Greek}/u.test(word)) location.hash = "#s/" + encodeURIComponent(word);
  }
});
Sync.onStatus(() => {
  const h = location.hash;
  if (h === "#fav") showFavs();
  if (h === "#om") showAbout();
});
(async () => {
  try { await loadMeta(); migrateFavs(); } catch { /* route() reports it */ }
  await Sync.init({
    get: favStore, set: setFavStore,
    changed: () => {           // favourites arrived from another device
      const star = $("#star");
      if (!star.hidden) star.setAttribute("aria-pressed", String(isFav(Number(star.dataset.n))));
      if (location.hash === "#fav") showFavs();
    },
  });
  route();
})();

if ("serviceWorker" in navigator) navigator.serviceWorker.register(v("sw.js")).catch(() => {});
