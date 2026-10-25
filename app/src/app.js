// Svenskt-grekiskt lexikon (Linder & Walberg 1862) as a web app.
// Views by location.hash: "" or #s/<query> search, #e/<n> an entry,
// #fav favourites, #dag the day's word, #loci the Index locorum, #om about.
"use strict";

const $ = (s) => document.querySelector(s);
const view = $("#view"), q = $("#q");
let meta = null;
const keyFiles = new Map();
const chunks = new Map();

// ---------------------------------------------------------------- data

async function json(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
async function loadMeta() { meta = meta || await json("data/meta.json"); return meta; }
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

const FAV = "lw-favoriter";
function favs() { try { return JSON.parse(localStorage.getItem(FAV)) || []; } catch { return []; } }
function setFavs(list) { try { localStorage.setItem(FAV, JSON.stringify(list)); } catch { /* private mode */ } }
function isFav(n) { return favs().includes(n); }
function toggleFav(n) {
  const list = favs();
  const i = list.indexOf(n);
  if (i >= 0) list.splice(i, 1); else list.unshift(n);
  setFavs(list);
  return i < 0;
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
    view.innerHTML = `<div class="front-page"><div><img src="front.png" alt="Svenskt-grekiskt lexikon, utgifvet af C. W. Linder och C. A. Walberg"><p class="hint">Sök på svenska eller grekiska</p></div></div>`;
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
  setBar("entry", meta.titles[n], n);
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
  $("#bar-title").textContent = "Dagens ord";
}

function showFavs() {
  setBar("list", "Favoriter");
  const list = favs();
  view.innerHTML = list.length
    ? `<ul class="results">${list.map((n) => `<li><a href="#e/${n}"><span class="key">${esc(meta.titles[n] || "")}</span></a></li>`).join("")}</ul>`
    : `<p class="empty">Inga favoriter ännu.<br>Tryck på stjärnan i en artikel för att spara den här.</p>`;
}

async function showLoci() {
  const n = meta.special.lw_locorum;
  await showEntry(n);
  $("#back").hidden = true;
  $("#star").hidden = true;
  setTitle("Index locorum");
}
function setTitle(t) { $("#bar-title").textContent = t; }

function showAbout() {
  setBar("list", "Om");
  const s = meta.special;
  view.innerHTML = `<div class="about">
    <h1 class="hw">Svenskt-grekiskt lexikon</h1>
    <p>C. W. Linder och C. A. Walberg, <i>Svenskt-grekiskt lexikon</i>, Upsala 1862. Texten är tolkad ur sidbilderna,
    korrekturläst mot dem och rättad efter bokens tryckfelsförteckning och en granskning av grekiskan.</p>
    <p class="list-head">I boken</p>
    <ul class="links">
      <li><a href="#e/${s.lw_preface}">Förord</a></li>
      <li><a href="#e/${s.lw_abbr}">Förkortningar</a></li>
      <li><a href="#e/${s.lw_linder}">Carl Wilhelm Linder</a></li>
      <li><a href="#e/${s.lw_walberg}">Carl August Walberg</a></li>
    </ul>
    <p class="list-head">Källor och data</p>
    <ul class="links">
      <li><a href="https://github.com/Urdatorn/linder-walberg" target="_blank" rel="noopener">Källkod <span>GitHub</span></a></li>
      <li><a href="https://huggingface.co/datasets/Urdatorn/linder-walberg" target="_blank" rel="noopener">Sidbilder och text <span>Hugging Face</span></a></li>
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
window.addEventListener("hashchange", route);
route();
loadMeta().catch(() => {});

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
