// Optional: favourites kept in the reader's own Hugging Face account, so that they
// follow from desktop to phone. "Logga in med Hugging Face" (under Om) lets the app
// create one private dataset there, <user>/linder-walberg-favoriter, holding
// favoriter.json; the scope (contribute-repos) reaches only repositories this app
// created. Without signing in nothing here runs and favourites stay on the device.
//
// Sign-in is OAuth with PKCE as in huggingface.js (oauthLoginUrl, oauthHandleRedirect),
// through the OAuth app "Svenskt-grekiskt lexikon" (CLIENT_ID), whose redirect URL is
// the app's address, https://albinthorncleland.com/linder-walberg/.
"use strict";

const Sync = (() => {
  const HF = "https://huggingface.co";
  const REPO = window.LW_SYNC_REPO || "linder-walberg-favoriter";
  const FILE = "favoriter.json";
  const AUTH = "lw-hf", NONCE = "lw-hf-nonce", VERIFIER = "lw-hf-verifier";
  const CLIENT_ID = "d6886622-eead-4e4e-a6ca-56111f1773f0";    // public; PKCE, no secret
  const SCOPES = "openid profile contribute-repos";
  const APP = location.origin + location.pathname.replace(/index\.html$/, "");

  let store = null;                    // {get(), set(items), changed()} from app.js
  let status = { state: "off" };       // off | syncing | ok | offline | expired | error
  const listeners = [];

  // sign-in only where the OAuth app may send the reader back to (not on a local test server)
  const available = () => location.origin === "https://albinthorncleland.com" || !!window.LW_SYNC_TEST;
  const read = (k) => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } };
  const write = (k, v) => { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } };
  const account = () => read(AUTH);                                    // {token, expires, user}
  const signedIn = () => { const a = account(); return !!a && a.expires > Date.now(); };

  function setStatus(s) { status = s; listeners.forEach((f) => f(status)); }

  // ------------------------------------------------------------ sign in and out

  async function login() {
    const nonce = crypto.randomUUID(), verifier = crypto.randomUUID() + crypto.randomUUID();
    write(NONCE, nonce); write(VERIFIER, verifier);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
    const challenge = btoa(String.fromCharCode(...digest)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
    location.href = `${HF}/oauth/authorize?` + new URLSearchParams({
      client_id: CLIENT_ID, scope: SCOPES, response_type: "code",
      redirect_uri: APP, state: JSON.stringify({ nonce, back: location.hash }),
      code_challenge: challenge, code_challenge_method: "S256",
    });
  }

  // back from huggingface.co with ?code=…&state=…: exchange the code for a token
  async function handleRedirect() {
    const p = new URLSearchParams(location.search);
    if (!p.has("code") && !p.has("error")) return;
    let state = {};
    try { state = JSON.parse(p.get("state") || "{}"); } catch { /* checked below */ }
    history.replaceState(null, "", location.pathname + (state.back || "#om"));
    const nonce = read(NONCE), verifier = read(VERIFIER);
    write(NONCE, null); write(VERIFIER, null);
    if (p.has("error") || !nonce || state.nonce !== nonce) { setStatus({ state: "error", message: "Inloggningen avbröts." }); return; }
    try {
      const t = await fetch(`${HF}/oauth/token`, {
        method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ grant_type: "authorization_code", code: p.get("code"), redirect_uri: APP, code_verifier: verifier }).toString(),
      });
      if (!t.ok) throw new Error("token " + t.status);
      const token = await t.json();
      const u = await fetch(`${HF}/oauth/userinfo`, { headers: { Authorization: `Bearer ${token.access_token}` } });
      if (!u.ok) throw new Error("userinfo " + u.status);
      const info = await u.json();
      write(AUTH, { token: token.access_token, expires: Date.now() + token.expires_in * 1000, user: info.preferred_username });
    } catch (e) {
      setStatus({ state: "error", message: "Inloggningen misslyckades." });
    }
  }

  function logout() {
    write(AUTH, null);
    setStatus({ state: "off" });
  }

  // ------------------------------------------------------------ the file in the account

  const api = (path, opts = {}) => fetch(HF + path, {
    ...opts, cache: "no-store", headers: { Authorization: `Bearer ${account().token}`, ...(opts.headers || {}) },
  });

  class Expired extends Error {}
  function check(r, what) {
    if (r.status === 401) throw new Expired(what);
    if (!r.ok) throw new Error(`${what} ${r.status}`);
    return r;
  }

  // the items in the account, or null when there is no file (or no repository) yet
  async function pull() {
    const r = await api(`/datasets/${account().user}/${REPO}/resolve/main/${FILE}`);
    if (r.status === 404) return { items: null, repo: r.headers.get("X-Error-Code") !== "RepoNotFound" };
    const data = await check(r, "pull").json();
    return { items: data.items || {}, repo: true };
  }

  async function createRepo() {
    const r = await api("/api/repos/create", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: REPO, type: "dataset", visibility: "private" }),
    });
    if (r.status !== 409) check(r, "create");                            // 409: it is there already
  }

  const b64 = (s) => { const b = new TextEncoder().encode(s); let t = ""; for (const c of b) t += String.fromCharCode(c); return btoa(t); };

  async function push(items, first) {
    const file = (path, text) => ({ key: "file", value: { path, content: b64(text), encoding: "base64" } });
    const lines = [{ key: "header", value: { summary: "Favoriter" } },
                   file(FILE, JSON.stringify({ format: "linder-walberg favoriter 1", items }, null, 1))];
    if (first) lines.push(file("README.md",
      "Favoriter från Svenskt-grekiskt lexikon (Linder & Walberg 1862), sparade av appen\n" +
      "https://albinthorncleland.com/linder-walberg/ så att de följer med mellan enheter.\n" +
      "Datasetet kan raderas; favoriterna finns kvar på enheterna.\n"));
    const r = await api(`/api/datasets/${account().user}/${REPO}/commit/main`, {
      method: "POST", headers: { "Content-Type": "application/x-ndjson" },
      body: lines.map((l) => JSON.stringify(l)).join("\n"),
    });
    check(r, "push");
  }

  // each favourite is {on, at}: the later change wins, so a removal on one device
  // removes it everywhere and nothing is lost when two devices change different entries
  function merge(a, b) {
    const out = { ...a };
    for (const [k, v] of Object.entries(b || {})) if (!out[k] || v.at > out[k].at) out[k] = v;
    return out;
  }
  const same = (a, b) => JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b || {}).sort());

  // ------------------------------------------------------------ syncing

  let running = null, again = false, timer = null;

  async function once() {
    if (!signedIn()) { if (account()) setStatus({ state: "expired" }); return; }
    if (!navigator.onLine) { setStatus({ state: "offline" }); return; }
    setStatus({ state: "syncing" });
    try {
      const remote = await pull();
      const merged = merge(store.get(), remote.items);
      if (!same(merged, store.get())) { store.set(merged); store.changed(); }
      if (remote.items === null || !same(merged, remote.items)) {
        if (!remote.repo) await createRepo();
        await push(merged, remote.items === null);
      }
      setStatus({ state: "ok", at: Date.now() });
    } catch (e) {
      if (e instanceof Expired) { const a = account(); write(AUTH, { ...a, expires: 0 }); setStatus({ state: "expired" }); }
      else setStatus({ state: navigator.onLine ? "error" : "offline", message: String(e.message || e) });
    }
  }

  function sync() {
    if (running) { again = true; return running; }
    running = (async () => { do { again = false; await once(); } while (again); })().finally(() => { running = null; });
    return running;
  }

  // after a star is set or removed: wait for a pause, then sync
  function schedule() {
    if (!account()) return;
    clearTimeout(timer);
    timer = setTimeout(sync, 1200);
  }

  async function init(s) {
    store = s;
    await handleRedirect();
    if (account()) sync();
    window.addEventListener("online", () => account() && sync());
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && account()) sync(); });
  }

  return {
    available, signedIn, init, login, logout, sync, schedule,
    user: () => (account() || {}).user || null,
    status: () => status,
    onStatus: (f) => listeners.push(f),
  };
})();
