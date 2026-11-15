# The iPhone shell

It owns no logic. It remembers the address of the machine that does, shows that address in a box
she can change, and loads it in a full-screen `WKWebView`.

Why it is this thin: the image pipeline, the metrics and the captions all run in the Python server on
her laptop, and none of them fit on a phone. Anything this folder could invent locally - a cached
gallery, an offline edit, a second copy of the plan - would be a second implementation that can be
wrong on its own. So the only state an iPhone keeps is one URL and the cookie the server's PIN door
hands back.

## How it becomes an installable app

1. `.github/workflows/ipa.yml` compiles this folder on a free macOS runner and uploads an **unsigned**
   `FameStrategist.ipa`. Apple's toolchain only runs on macOS, which is the only reason a Mac is in
   the picture at all - and it is somebody else's.
2. The `.ipa` goes into `data/packages` on her PC. `/store` then lists it and
   `/store/apps.json` describes it, both generated from that file's actual bytes.
3. **AltServer on Windows signs it** with her own Apple ID - AltStore's own Windows instructions, so
   no paid developer account and no Mac for this half. AltStore on the phone installs it and keeps
   the signature alive in the background.

Neither the compile nor the install has happened yet. `ios/` has never met a compiler, and there is
no `.ipa` on this machine, which is why the listing is empty and the page says so.

One question is still open and cannot be settled by reading: the source and download URLs are plain
`http` on her wifi. AltStore's source documentation requires no HTTPS and never mentions a local
address, so whether the AltStore app is permitted to fetch one is AltStore's and iOS's decision. The
first attempt at step 3 answers it. If it refuses, the fix is public hosting - ruled out - so the
iPhone app stays the home-screen install from `/phone`.

## Two things the code depends on

* `<input type=file>` inside a `WKWebView` is served by WebKit's own picker (camera roll, Files), so
  the editor's upload button works with no delegate code here. That support is WebKit's, not ours.
* The server speaks plain http on a private address. `Info.plist` allows that for web content only;
  this app makes no `URLSession` request of its own, so nothing else can travel in the clear.

`Info.plist`'s three usage strings, the empty `Fame.entitlements`, the version pair here and
`project.yml`'s bundle id are all mirrored in `src/store/altsource.py`, and
`tests/store/test_store.py` reads these files and fails if they drift - because AltStore compares the
listing against the binary and refuses an app whose permissions do not line up.
