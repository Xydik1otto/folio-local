// folio-local service worker: offline shell for the PWA.
// Cache-first for static assets and the app shell, network-first for API
// (portfolio data must be fresh); API responses are never served stale.
const CACHE = "folio-static-v1";
const SHELL = [
  "/",
  "/static/index.html",
  "/static/favicon.svg",
  "/static/manifest.webmanifest",
  "/static/i18n/uk.json",
  "/static/i18n/en.json",
  "https://cdn.jsdelivr.net/npm/chart.js@4",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) =>
      // allSettled: a missing optional asset (e.g. i18n file) must not
      // abort the whole shell install.
      Promise.allSettled(SHELL.map((u) =>
        fetch(u, { cache: "no-cache" }).then((r) =>
          r.ok ? c.put(u, r) : Promise.reject(new Error(u))))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) return; // never cache portfolio data
  if (event.request.method !== "GET") return;

  event.respondWith(
    caches.match(event.request, { ignoreSearch: true }).then((hit) => {
      const network = fetch(event.request)
        .then((res) => {
          if (res.ok && url.origin === self.location.origin ||
              res.ok && url.hostname.endsWith("jsdelivr.net")) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(event.request, copy));
          }
          return res;
        })
        .catch(() => hit); // offline: fall back to the cached copy
      return hit || network;
    })
  );
});
