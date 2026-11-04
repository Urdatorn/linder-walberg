// A hit counter, shown under Om: how many times the app has been opened, and on how
// many devices. The site is static, so the two numbers are kept by Abacus
// (https://abacus.jasoncameron.dev), a free counting service that needs no account:
// GET /hit/<namespace>/<key> adds one and answers {"value": n}, /get/… only reads.
//
// Each opening of the app (one browser session) counts once as a visit; a device
// counts once ever (a flag in localStorage). Nothing about the reader is sent, no
// cookie is set, and only the published site counts (not a local test server).
// Offline, or if the service is down, the line under Om simply stays empty.
"use strict";

const Hits = (() => {
  const API = "https://abacus.jasoncameron.dev";
  const NS = "linder-walberg-1862";
  const VISITS = "besok", DEVICES = "enheter";
  const SEEN_DEVICE = "lw-hits-device", SEEN_SESSION = "lw-hits-session";

  const counts = { [VISITS]: null, [DEVICES]: null };
  const listeners = [];
  const live = () => location.origin === "https://albinthorncleland.com" || !!window.LW_HITS_TEST;

  const flag = (storage, k) => { try { return storage.getItem(k) === "1"; } catch { return true; } };
  const setFlag = (storage, k) => { try { storage.setItem(k, "1"); } catch { /* private mode */ } };

  async function ask(verb, key) {
    try {
      const r = await fetch(`${API}/${verb}/${NS}/${key}`, { cache: "no-store" });
      if (!r.ok) return;
      const { value } = await r.json();
      if (Number.isFinite(value)) { counts[key] = value; listeners.forEach((f) => f()); }
    } catch { /* offline, or the service is gone */ }
  }

  // once at start: count this visit (and this device, the first time), which also
  // brings back the totals; a visit already counted in this session only reads them
  function init() {
    if (!live()) return;
    // a private window that refuses storage reads as already counted: read, don't count
    const newSession = !flag(sessionStorage, SEEN_SESSION);
    const newDevice = !flag(localStorage, SEEN_DEVICE);
    if (newSession) setFlag(sessionStorage, SEEN_SESSION);
    if (newDevice) setFlag(localStorage, SEEN_DEVICE);
    ask(newSession ? "hit" : "get", VISITS);
    ask(newDevice ? "hit" : "get", DEVICES);
  }

  return {
    init,
    visits: () => counts[VISITS],
    devices: () => counts[DEVICES],
    onChange: (f) => listeners.push(f),
  };
})();
