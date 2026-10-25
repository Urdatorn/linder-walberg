// Offline: every file of the app and the whole dictionary is cached on install;
// a new build (new version) replaces the cache.
const VERSION = "lw-__VERSION__";
const FILES = "__FILES__";

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
