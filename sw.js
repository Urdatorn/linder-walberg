// Offline: every file of the app and the whole dictionary is cached on install;
// a new build (new version) replaces the cache.
const VERSION = "lw-44ae1e82f2";
const FILES = [".nojekyll", "app.css", "app.js", "data/e/00.json", "data/e/01.json", "data/e/02.json", "data/e/03.json", "data/e/04.json", "data/e/05.json", "data/e/06.json", "data/e/07.json", "data/e/08.json", "data/e/09.json", "data/e/10.json", "data/e/11.json", "data/e/12.json", "data/e/13.json", "data/e/14.json", "data/e/15.json", "data/e/16.json", "data/e/17.json", "data/e/18.json", "data/e/19.json", "data/e/20.json", "data/e/21.json", "data/e/22.json", "data/e/23.json", "data/e/24.json", "data/e/25.json", "data/e/26.json", "data/k/2a.json", "data/k/375.json", "data/k/3b1.json", "data/k/3b2.json", "data/k/3b3.json", "data/k/3b4.json", "data/k/3b5.json", "data/k/3b6.json", "data/k/3b7.json", "data/k/3b8.json", "data/k/3b9.json", "data/k/3ba.json", "data/k/3bb.json", "data/k/3bc.json", "data/k/3bd.json", "data/k/3be.json", "data/k/3bf.json", "data/k/3c0.json", "data/k/3c1.json", "data/k/3c3.json", "data/k/3c4.json", "data/k/3c5.json", "data/k/3c6.json", "data/k/3c7.json", "data/k/3c8.json", "data/k/3c9.json", "data/k/61.json", "data/k/62.json", "data/k/63.json", "data/k/64.json", "data/k/65.json", "data/k/66.json", "data/k/67.json", "data/k/68.json", "data/k/69.json", "data/k/6a.json", "data/k/6b.json", "data/k/6c.json", "data/k/6d.json", "data/k/6e.json", "data/k/6f.json", "data/k/70.json", "data/k/71.json", "data/k/72.json", "data/k/73.json", "data/k/74.json", "data/k/75.json", "data/k/76.json", "data/k/77.json", "data/k/78.json", "data/k/79.json", "data/k/7a.json", "data/k/e4.json", "data/k/e5.json", "data/k/f6.json", "data/meta.json", "dictionary.css", "fonts/GFSPorson-OFL.txt", "fonts/fonts.css", "fonts/gentium-italic-400-latin-ext.woff2", "fonts/gentium-italic-400-latin.woff2", "fonts/gentium-normal-400-latin-ext.woff2", "fonts/gentium-normal-400-latin.woff2", "fonts/gentium-normal-700-latin-ext.woff2", "fonts/gentium-normal-700-latin.woff2", "fonts/gfs-porson.woff2", "front.png", "icons/UnifrakturMaguntia-OFL.txt", "icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png", "img/linder.png", "img/walberg.png", "index.html", "manifest.webmanifest", "sync.js"];

self.addEventListener("install", (e) => {
  // asked with the version, past any cache in front of the site; served for the plain URL (ignoreSearch)
  const v = VERSION.slice(3);
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(["./", ...FILES.map((f) => `${f}?v=${v}`)])).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((names) => Promise.all(names.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || fetch(e.request)));
});
