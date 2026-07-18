/* Shiori — service worker
   Rend l'app installable (PWA) et utilisable hors-ligne.
   Stratégie :
   - navigations : réseau d'abord, puis repli sur la coquille en cache (offline).
   - assets (icônes, manifest, JSZip CDN) : cache d'abord + rafraîchissement en tâche de fond.
   - Google (auth GSI / API Drive) : jamais interceptés (toujours réseau).
   Bump VERSION pour invalider le cache lors d'une mise à jour. */
const VERSION = "shiori-v3";

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

/* Cible de partage Android : « Partager → Shiori » envoie les fichiers en POST
   sur /share ; on les range dans IndexedDB puis on ouvre l'app, qui les
   récupère au chargement. */
function openShioriDB() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open("shiori", 2);
    r.onupgradeneeded = () => {
      const db = r.result;
      if (!db.objectStoreNames.contains("queue"))  db.createObjectStore("queue",  { keyPath: "id" });
      if (!db.objectStoreNames.contains("shared")) db.createObjectStore("shared", { autoIncrement: true });
    };
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function handleShare(event) {
  try {
    const form = await event.request.formData();
    const files = form.getAll("files").filter(f => f && typeof f.name === "string");
    if (files.length) {
      const db = await openShioriDB();
      await new Promise((res, rej) => {
        const tx = db.transaction("shared", "readwrite");
        files.forEach(f => tx.objectStore("shared").add(f));
        tx.oncomplete = res; tx.onerror = () => rej(tx.error);
      });
    }
  } catch (e) { /* au pire, l'app s'ouvre sans les fichiers */ }
  return Response.redirect("/?shared=1", 303);
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  let shareUrl;
  try { shareUrl = new URL(req.url); } catch { shareUrl = null; }
  if (req.method === "POST" && shareUrl && shareUrl.pathname === "/share") {
    event.respondWith(handleShare(event));
    return;
  }
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
