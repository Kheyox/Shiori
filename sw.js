/* Shiori — service worker
   Rend l'app installable (PWA) et utilisable hors-ligne.
   Stratégie :
   - navigations : réseau d'abord, puis repli sur la coquille en cache (offline).
   - assets (icônes, manifest, JSZip CDN) : cache d'abord + rafraîchissement en tâche de fond.
   - Google (auth GSI / API Drive) : jamais interceptés (toujours réseau).
   Bump VERSION pour invalider le cache lors d'une mise à jour. */
const VERSION = "shiori-v1";

const APP_SHELL = "/kobo-converter.html";
const CORE = [
  "/",
  APP_SHELL,
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/maskable-512.png",
  "/icons/apple-touch-icon.png",
  "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(VERSION);
    // allSettled : une seule URL injoignable ne fait pas échouer toute l'install
    await Promise.allSettled(CORE.map((u) => cache.add(new Request(u, { cache: "reload" }))));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

// Permet à la page de forcer l'activation d'une nouvelle version.
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

function isGoogle(url) {
  return /(^|\.)google\.com$/.test(url.hostname) ||
         /(^|\.)googleapis\.com$/.test(url.hostname) ||
         /(^|\.)gstatic\.com$/.test(url.hostname);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  let url;
  try { url = new URL(req.url); } catch { return; }
  if (url.protocol !== "http:" && url.protocol !== "https:") return;

  // Ne jamais toucher à l'auth Google / l'API Drive.
  if (isGoogle(url)) return;

  // Navigations : réseau d'abord, repli hors-ligne sur la coquille.
  if (req.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(VERSION);
        cache.put(APP_SHELL, fresh.clone());
        return fresh;
      } catch {
        const cache = await caches.open(VERSION);
        return (await cache.match(APP_SHELL)) ||
               (await cache.match("/")) ||
               new Response("Hors-ligne et aucune version en cache.", {
                 status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" },
               });
      }
    })());
    return;
  }

  // Reste (icônes, manifest, JSZip CDN) : cache d'abord, rafraîchi en arrière-plan.
  event.respondWith((async () => {
    const cache = await caches.open(VERSION);
    const cached = await cache.match(req);
    const network = fetch(req).then((res) => {
      if (res && (res.ok || res.type === "opaque")) cache.put(req, res.clone());
      return res;
    }).catch(() => null);
    return cached || (await network) || Response.error();
  })());
});
