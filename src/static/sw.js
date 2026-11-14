/* The app already runs on this machine, so this worker is not here to make it fast.
   It is here so the browser is willing to install it as an app, and so the shell still
   opens when the engine is not running.
   Only pages and the static shell are stored: her photos, the preview renders and every
   POST go straight through, because a cached picture is a stale picture. */

const KEEP = "fame-strategist-v1";
const SHELL = "/today";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(KEEP)
      .then((cache) => cache.add(new Request(SHELL, { cache: "reload" })))
      .catch(() => {})
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== KEEP).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function worthKeeping(request, response) {
  if (request.method !== "GET" || !response.ok) return false;
  const path = new URL(request.url).pathname;
  if (path.startsWith("/static/")) return true;
  return (response.headers.get("content-type") || "").includes("text/html");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (worthKeeping(request, response)) {
          const copy = response.clone();
          caches.open(KEEP).then((cache) => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() =>
        caches.match(request).then((hit) => hit || caches.match(SHELL)).then((hit) =>
          hit || new Response(
            "<!doctype html><meta charset=utf-8><body style='background:#131417;" +
            "color:#e8e6e2;font:15px system-ui;padding:40px'>" +
            "<b>Fame Strategist</b><p>The engine behind this app is not running. Start it with " +
            "<i>Fame Strategist.cmd</i>, then reload.</p>",
            { headers: { "content-type": "text/html; charset=utf-8" } })))
  );
});
