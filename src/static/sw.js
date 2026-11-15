/* The copy of this app that lives on the phone.

   It used to keep only the text, on the reasoning that a cached picture is a stale picture. That
   reasoning is reversed here on purpose: she asked for the whole app to work with no network, and a
   plan she can read whose photos are broken is not "everything". The answer to staleness is not to
   hide the copy - it is to label it. Every stored response carries the moment it went in, and any
   page served out of storage says so with that timestamp instead of pretending to be live.

   Two jobs. `pack` walks the manifest the laptop derives from its own routes (src/offline.py) and
   stores every page plus every file those pages reference, so what travels is what the app actually
   shows rather than a hand-picked shortlist. Serving is network-first with storage as the fallback,
   so being online always wins and only a genuine failure reads from the phone.

   What this cannot do is make the engine run on the phone. A new edit, a rendered preview, a clip
   cut, a fresh number, an agent answer - all computed work that lives on the laptop. Those come
   back as missing, and the packing page names them, instead of a dead button implying otherwise.
 */

const KEEP = "fame-strategist-v4";
const MANIFEST = "/offline/manifest";
const STAMP = "x-fame-stored";
const MAX_TOTAL = 220 * 1024 * 1024;   // a cache iOS will not evict on sight
const MAX_FILE = 64 * 1024 * 1024;     // one clip this big is not worth the eviction risk
const MEDIA_PREFIXES = ["/inbox/", "/outputs/", "/frames/", "/edit/preview", "/clip/preview"];

/* Which moment a page left the laptop, written into the page itself.

   The obvious mechanism - keep the answer per client and let the page ask for it - does not work:
   `FetchEvent.resultClientId` is missing in Safari (and was missing in the browser this feature was
   tested in), so the record is stored under `undefined` and every page loads without its label. The
   timestamp travels in the document instead, which no browser can decline to deliver. */
async function stamped(hit) {
  const html = await hit.text();
  const mark = `<meta name="fame:stored" content="${hit.headers.get(STAMP) || "0"}">`;
  const headers = new Headers(hit.headers);
  headers.set("content-type", "text/html; charset=utf-8");
  return new Response(/<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, (m) => m + mark)
                                                   : mark + html,
                      { status: 200, headers });
}

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== KEEP).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function isMedia(path) {
  return MEDIA_PREFIXES.some((p) => path.startsWith(p));
}

/** Put one response in the phone's copy, marked with the moment it went in. */
async function store(url, body, type) {
  const headers = new Headers({ "content-type": type || "application/octet-stream" });
  headers.set(STAMP, String(Date.now()));
  const book = await caches.open(KEEP);
  await book.put(new Request(url, { credentials: "include" }), new Response(body, { status: 200, headers }));
  return body ? body.byteLength : 0;
}

/** The file URLs a page really shows, query strings and all, so generated previews travel too.
    Scanned with a pattern rather than parsed with DOMParser, which a service worker does not have -
    a mistake that looks like the laptop being unreachable, because it throws inside the same try. */
const REF = /(?:src|poster)\s*=\s*["']([^"']+)["']/g;

function referenced(html, base) {
  const origin = new URL(base).origin;
  const out = [];
  let hit;
  REF.lastIndex = 0;
  while ((hit = REF.exec(html))) {
    try {
      const url = new URL(hit[1], base);
      if (url.origin === origin && isMedia(url.pathname)) out.push(url.pathname + url.search);
    } catch (e) { /* a junk src does not travel, and is not worth failing the pack over */ }
  }
  return out;
}

async function tell(client, message) {
  if (!client) return;
  try { client.postMessage(message); } catch (e) { /* the page closed mid-pack */ }
}

async function get(path) {
  return fetch(path, { credentials: "include", cache: "reload" });
}

async function pack(client) {
  const out = { pages: [], files: [], skipped: [], bytes: 0, error: "", counts: {} };
  let man;
  try {
    const got = await get(MANIFEST);
    if (!got.ok) throw new Error("answered " + got.status);
    const text = await got.text();
    man = JSON.parse(text);
    await store(MANIFEST, new TextEncoder().encode(text).buffer, "application/json");
  } catch (e) {
    out.error = "The laptop did not give up its list (" + e.message + "). Pack this while the phone " +
      "can reach it, and after you have entered the PIN here once.";
    await tell(client, { type: "fame:pack:done", summary: out });
    return out;
  }

  // Ask iOS to treat this as data she chose to keep, not as cache to drop when storage gets tight.
  try { await navigator.storage.persist(); } catch (e) { /* best effort, never a reason to stop */ }

  const extra = new Set();
  const total = man.pages.length + man.media.length;
  let done = 0;

  for (const path of man.pages) {
    done += 1;
    let state = "fail", why = "", bytes = 0;
    try {
      const got = await get(path);
      if (!got.ok) {
        why = "answered " + got.status + (got.status === 401 ? " - the PIN has not been entered here" : "");
      } else {
        const html = await got.text();
        bytes = await store(path, new TextEncoder().encode(html).buffer,
                            got.headers.get("content-type") || "text/html");
        referenced(html, self.location.origin + path).forEach((u) => extra.add(u));
        state = "ok";
      }
    } catch (e) { why = e && e.message ? ("failed: " + e.message) : "nothing to reach"; }
    out.pages.push({ path, state, why, bytes });
    out.bytes += bytes;
    await tell(client, { type: "fame:pack:progress", done, total, path, state, why });
  }

  const urls = new Set(man.media.map((m) => m.url));
  extra.forEach((u) => urls.add(u));

  for (const url of urls) {
    done += 1;
    let state = "fail", why = "", bytes = 0;
    try {
      const got = await get(url);
      if (!got.ok) { why = "answered " + got.status; }
      else {
        const body = await got.arrayBuffer();
        if (body.byteLength > MAX_FILE) { why = "too big for a phone"; state = "skip"; }
        else if (out.bytes + body.byteLength > MAX_TOTAL) { why = "cache ceiling reached"; state = "skip"; }
        else {
          bytes = await store(url, body, got.headers.get("content-type"));
          state = "ok";
        }
      }
    } catch (e) { why = "the laptop did not answer"; }
    if (state === "ok") { out.files.push({ url, bytes }); out.bytes += bytes; }
    else out.skipped.push({ url, why });
    await tell(client, { type: "fame:pack:progress", done, total, path: url, state, why });
  }

  out.counts = {
    pages: out.pages.filter((p) => p.state === "ok").length,
    failed: out.pages.filter((p) => p.state !== "ok").length,
    files: out.files.length, skipped: out.skipped.length,
  };
  await tell(client, { type: "fame:pack:done", summary: out });
  return out;
}

async function status(client) {
  const book = await caches.open(KEEP);
  const entries = [];
  for (const request of await book.keys()) {
    const got = await book.match(request);
    if (!got) continue;
    const path = new URL(request.url).pathname;
    entries.push({
      url: path + new URL(request.url).search,
      // Three kinds, because the chips have to answer "what of mine is on here": the stylesheet and
      // the list itself are neither a page she reads nor a picture she took.
      kind: isMedia(path) ? "file" : (path.startsWith("/static") || path === MANIFEST
        ? "asset" : "page"),
      bytes: (await got.clone().arrayBuffer()).byteLength,
      stored: Number(got.headers.get(STAMP) || 0),
    });
  }
  entries.sort((a, b) => a.url.localeCompare(b.url));
  const body = { entries, count: entries.length, bytes: entries.reduce((n, e) => n + e.bytes, 0) };
  await tell(client, { type: "fame:status", ...body });
  return body;
}

self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type === "fame:pack") event.waitUntil(pack(event.source));
  if (data.type === "fame:status") event.waitUntil(status(event.source));
  if (data.type === "fame:erase") {
    event.waitUntil(caches.delete(KEEP).then(() => tell(event.source, { type: "fame:erased" })));
  }
});

/* Network first, always. This copy exists for when there is no network - it is not a way to show
   her yesterday while today is one request away. */
self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(request).then((response) => {
      // Write-through, so a page she happened to look at travels too. The ceiling still applies:
      // one clip watched online must not be the thing that gets the whole copy evicted.
      if (response.ok && url.pathname !== MANIFEST) {
        const claimed = Number(response.headers.get("content-length") || 0);
        if (claimed <= MAX_FILE) {
          const copy = response.clone();
          event.waitUntil(copy.arrayBuffer().then((body) => {
            if (body.byteLength <= MAX_FILE) {
              return store(url.pathname + url.search, body,
                           response.headers.get("content-type"));
            }
          }).catch(() => {}));
        }
      }
      return response;
    }).catch(async () => {
      const book = await caches.open(KEEP);
      const hit = await book.match(request);
      if (hit) {
        return (hit.headers.get("content-type") || "").indexOf("html") >= 0
          ? stamped(hit) : hit;
      }
      return new Response(lost_page(await book.keys()),
                          { headers: { "content-type": "text/html; charset=utf-8" } });
    })
  );
});

/* Out of range and never stored: name the situation and list what the phone does hold, instead of
   dumping her on a half-drawn page or a spinner. */
function lost_page(keys) {
  const held = keys.map((r) => new URL(r.url).pathname)
    .filter((p) => !isMedia(p) && !p.startsWith("/static") && p !== MANIFEST)
    .sort();
  const links = held.map((p) => `<p><a href="${p}">${p}</a></p>`).join("") ||
    "<p><em>Nothing yet.</em> Open the Phone page and pack while you still have signal.</p>";
  return `<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<body style="background:#131417;color:#e8e6e2;font:15px/1.6 system-ui;padding:28px">
<b style="font-size:19px">No signal, and this page is not on your phone yet</b>
<p style="opacity:.8">Pages you packed or opened while the laptop was reachable do work here.
Anything that has to be computed - a new edit, a clip cut, fresh numbers, an agent answer - needs
the laptop awake and on the same network.</p>
<h3 style="font-size:14px;opacity:.7">Stored on this phone</h3>${links}</body></html>`;
}
