// Service worker: only shows a friendly offline page when the server can't be reached.
// Pages are never cached (they hold your finances); only the offline page and its icon are.
// Browsers run service workers on HTTPS (or localhost) only; elsewhere this file is unused.
const VERSION = "{{ v }}";
const CACHE = "savings-offline-" + VERSION;
const SHELL = ["/offline", "/static/icons/icon-192.png?v=" + VERSION];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("savings-") && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;          // everything else goes straight to the network
  event.respondWith(fetch(event.request).catch(() => caches.match("/offline")));
});
