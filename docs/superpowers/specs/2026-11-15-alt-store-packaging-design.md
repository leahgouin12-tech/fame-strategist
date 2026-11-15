# Alt-store packaging — design

Date: 2026-11-15. Chosen by her after being offered three readings of "make this an alt store app":
she picked **get it into an alt app store** — a real installable package pushed through an
alternative store, not a storefront for her brands and not a hosted shop link.

## What the app is, from a store's point of view

Fame Strategist is a Python/FastAPI server that runs on her Windows PC (`run.py`, port 8756),
keeps its one SQLite file in `data/`, and is *used* from her iPhone over the same wifi. The phone
half already exists and works: `src/net.py` binds the wifi adapter and hands out the LAN address
plus a PIN door, `src/templates/phone.html` walks her through Add to Home Screen, and
`src/static/manifest.webmanifest` + `sw.js` make that install a standalone app with icons and
shortcuts.

The consequence that decides everything below: **the product's brain is the PC.** An image edit
runs Pillow + a mesh warp in-process; captions, metrics and the planner all read the local
database. A phone cannot run any of it. So every store package is a *shell* whose job is to reach
her LAN server. That single fact is what makes public store distribution awkward and is stated in
the product rather than hidden.

## Facts read from the source today (2026-11-15)

These four were opened and quoted in this session, and the implementation depends on them.

1. **iOS alternative app distribution is closed to the United States.** Apple's own support article
   ([117767](https://support.apple.com/en-us/117767), published 2026-10-26): "Alternative app
   distribution is available in Brazil, Japan, and the countries or regions of the European Union"
   and "Only users based in Brazil, Japan, or the European Union are able to install apps through
   alternative app distribution. The country or region of your Apple Account must be set to one of
   those countries or regions, and you must physically be located there." Her Apple Account is US.
2. **AltStore Classic distributes a self-hosted JSON file plus `.ipa` binaries, and takes no cut.**
   [Distribute with AltStore Classic](https://faq.altstore.io/developers/distribute-with-altstore-classic.md):
   "you can distribute apps to anyone for free, without a paid Apple Developer account … no review
   by Apple necessary. By simply hosting a Source, which is just a JSON file … along with your apps'
   compiled app (.ipa) files". [Fees](https://faq.altstore.io/developers/fees.md): AltStore Classic
   commission 0%; AltStore PAL (the EU marketplace) is where Apple's 5% Core Technology Fee applies.
3. **Two rules of that JSON shape, straight from the same pages.** The order of `versions` is what
   AltStore reads as newest-first, and `appPermissions` (its entitlements and privacy strings) is
   compared against the downloaded `.ipa` - a mismatch is an install that refuses to happen. The
   documented shape has **no checksum field**: nothing in a source validates a hash, so the source
   generator does not invent one and the checksum lives on the screen instead, where she can compare
   it with `certutil`.
4. **The catch on iOS is the build, not the store.** A `.ipa` still has to be compiled with Apple's
   toolchain. Her machine has no macOS; a 2026 vendor comparison
   ([code2native](https://code2native.com/blog/build-ios-app-without-mac-2026)) states it plainly:
   "You can start an iOS build from Windows or Linux without owning a Mac. A native iOS build still
   uses Apple's toolchain on a Mac somewhere," and its own website→IPA route requires "a deployed
   HTTPS website" - which she has chosen not to have.
5. **Signing does not need that Mac.** AltStore's own [How to Install (Windows)](https://faq.altstore.io/getting-started/installing-altstore-windows.md)
   has AltServer run on Windows and sign with her Apple ID: it wants iTunes *and* iCloud installed
   directly from Apple (not the Microsoft Store builds), wifi sync enabled, her Apple ID email and
   password typed into AltServer by her, a Trust tap under Settings → Profiles & Device Management,
   and Developer Mode on iOS 16+. So the route splits cleanly - compile on somebody else's macOS,
   sign on hers. That page says nothing about regions, which is consistent with Classic being
   personal signing rather than one of Apple's alt marketplaces.
6. **The whole source schema, read in full.** [Make a Source](https://faq.altstore.io/developers/make-a-source.md):
   `marketplaceID` is "Not required for non-notarized apps distributed with AltStore Classic";
   `category` must be one of eight listed values (`photo-video` is one, which is what
   `altsource.py` emits); `date` is ISO 8601; screenshots may be bare URLs only at the 9:19.5
   portrait ratio; and `appPermissions` "will be checked against the downloaded .ipa, and AltStore
   will refuse to install any app whose permissions do not match". **Nothing in it requires HTTPS** -
   every example URL is https, and the page never mentions a local address or a plain-http one, so it
   neither allows nor forbids the LAN source this design produces.

## The one open question, and it is load-bearing

AltStore Classic on her iPhone has to fetch `apps.json` and then the `.ipa`, both from
`http://192.168.x.x:8756/...` over her wifi. Apple's networking policy (App Transport Security)
refuses plain http by default and allows it only where an app asks - and the app asking here is
**AltStore's**, not hers, so her wrapper's `NSAllowsArbitraryLoadsInWebContent` has nothing to do
with it. The source specification read above is silent on the subject, which means the question is
unanswerable from the documentation available today.

What that decides: if AltStore will read a plain-http source, the whole iOS route works on her
network with zero hosting. If it will not, the fix is a publicly reachable https URL for two files,
which is exactly the hosting she has ruled out - and then the honest iPhone answer stays the PWA
install from `/phone`, which already works, with the wrapper and the source generator kept because
they are one config change from working. Nothing in the product claims the http case works.

## Reported, not verified here

Each of these was picked up from search results or general knowledge and is **not** confirmed by a
page opened in this session. None of them is load-bearing for the code; all of them are things to
check on the vendor's own site before she plans around them.

- How many apps a free Apple ID signs at once, and how long a personal signature lasts (AltStore
  re-signs in the background either way, so the wrapper is unaffected).
- The exact price of any Mac-in-the-cloud or Apple Developer membership quoted in the route table.
- itch.io's, Aptoide's and F-Droid's listing rules, review times and fees for an APK
  ([Aptoide's submission FAQ](https://docs.connect.aptoide.com/docs/app-submission-faqs) and
  [a Softonic round-up of alternatives to Google Play](https://developers.softonic.com/articles/alternatives-to-google-play-for-publishing-android-apps/)
  came up in search; neither was read line by line).

## Checked on this machine

No JDK, no Gradle, no Android SDK (`java`, `javac`, `gradle`, `sdkmanager`, `adb`, `keytool` all
missing; `node`/`npm` present). That toolchain was offered, downloaded to a scratch folder and then
deleted when she said iOS only - so there is now nothing half-installed on this PC, and the Android
package is source plus scripts with no build. The iOS side needs no toolchain here at all: the
compile happens on a macOS CI runner and the signing happens in AltServer, which is a Windows program
she installs herself. There is no git remote and no `gh` CLI, so neither workflow can run yet; both
are written so they are one `git push` away rather than one rewrite away.

## Ranked routes

She chose iOS ("i only care for ios"), which reorders this table from the one the first draft
published. The order below is what is true now, not what was tempting then.

| # | Route | Installs on her iPhone? | $0? | Verdict |
|---|-------|------------------------|-----|---------|
| 1 | **AltStore Classic: unsigned .ipa from a free macOS runner + AltServer signing on this PC** | Yes, in the US | yes, if the plain-http source is accepted (see the open question) | **This is the route.** Nothing about it needs a paid account, a Mac she owns, or hosting. The compile is a CI file, the signing is her Apple ID, and the listing is already generated from the bytes. |
| 2 | **Installed PWA (today's `/phone` + manifest)** | Yes | yes | Already real, works in every region, and is the fallback if route 1 dies on the http question. Keep it whatever happens. |
| 3 | **EU/Japan/Brazil alt marketplace (AltStore PAL etc.)** | Only if she moves Apple Account region and is physically there | 5% Apple CTC + $0 listing | Blocked by geography, not by effort. |
| 4 | **Android APK → handed out by `/store` itself** | No (iPhone) | yes, after a one-time SDK or a GitHub remote | Written and parked: `apk/`, two scripts, one Linux workflow, zero toolchain installed here. Not a step to do. |
| 5 | Enterprise-cert "no-computer" sideload stores (Esign/Scarlet/GBox class) | Yes, in the US | nominally free | Rejected: relies on resold/abused certificates that get revoked, needs a third party to hold a signing identity for her app, and publishes a private tool to strangers. |

**Recommendation, as chosen: route 1, with route 2 as the floor.** Produce the unsigned `.ipa` on a
free macOS runner, let her drop it in `data/packages` so `/store/apps.json` starts carrying it, and
have AltServer on this Windows PC sign it with her Apple ID. Say plainly, in the product, that the
one thing that cannot be checked on paper is whether AltStore will read a plain-http source over her
wifi - and that if it will not, this stays a PWA rather than becoming a hosted app.

## Package design (`apk/`) - as built, then parked

She narrowed the request to iOS before any of this was compiled, so it is finished work that is not
on the path: nothing installs it, no Android toolchain is left on this machine, and `/store` presents
it as one short card at the end of the page rather than as a step.

- Plain Gradle project, Kotlin, **no dependencies at all**: `app/build.gradle` has an empty
  `dependencies` block, because the entire surface is `android.webkit`. No Capacitor, no npm, no Play
  Services, no AppCompat. AGP 8.7.3 / Kotlin 2.0.21 / JDK 17 / minSdk 26 / target+compile 35,
  `versionName 1.0` and `versionCode 1` - the same pair `altsource.py` publishes for iOS.
- `MainActivity` is the setup screen and the only writer of the saved address (shared prefs);
  `BrowserActivity` is the WebView: DOM storage and cookies on so the PIN survives a relaunch,
  `onShowFileChooser` wired to the system picker so `<input type=file>` opens the gallery,
  `onPermissionRequest` + a runtime camera ask so a capture control works, a `DownloadManager`
  listener so an exported file lands in Downloads, back = history, off-machine links handed to the
  real browser, and an error panel that prints the address it tried with Try again / Change the
  address - the failure this design actually produces, not a blank page.
- `network_security_config.xml` allows cleartext on `10/8`, `172.16/12`, `192.168/16` and `.local`
  names, base-config refuses it everywhere else, and `Addresses.parse` rejects a non-private literal
  IP while she is still typing. The iOS side does the same job with `NSAppTransportSecurity`.
- `scripts/make_icons.py` cuts the mipmaps (48-192 px) and the iPhone `AppIcon.appiconset`
  (40-180 px) from `src/static/icon-512.png`.
- `scripts/build_apk.ps1` finds `apk/gradlew.bat` or `gradle`, checks for a JDK, builds
  `assembleRelease` (`-Debug` for a self-signed debug install), copies into `data/packages/`, prints
  size + SHA-256, and **refuses to publish an unsigned release** - it says the key is missing instead
  of handing over an APK Android will not install.
- `scripts/make_keystore.ps1` finds `keytool` (PATH or Android Studio's `jbr`), writes
  `keystore/fame.keystore` (git-ignored, never overwritten once it exists, because a new key means
  uninstall-first) and appends the four `fame*` properties to `%USERPROFILE%\.gradle\gradle.properties`
  so no password is ever on a command line or in the repo.
- `.github/workflows/apk.yml` builds the same project on `ubuntu-latest` and uploads the artifact,
  signing from `FAME_KEYSTORE_BASE64` + three more secrets through the same `~/.gradle` mechanism.
  It cannot run until the repository has a remote; the header of the file says so.

**Three ideas from the first draft were dropped, and why.** A "find my PC again" LAN probe was
written against a `/phone/hello` endpoint that does not exist - building it would have meant a new
route whose only answer is an IP the Phone page already prints. Pull-to-refresh needed a Material
dependency, and the canvas pages refresh themselves. A 1024 px iOS icon and an adaptive Android icon
would both have been upscales of a 512 px original, i.e. soft art presented as sharp; a self-hosted
`.ipa` installs fine on the classic sizes, and the 1024 slot only matters for an App Store
submission this app will not make.

## iOS wrapper design (`ios/`) - as built

`App.swift` (one `ServerViewController`: WKWebView, inline media playback, default data store so the
PIN cookie persists, back/forward/reload/address bar, the address kept in `UserDefaults`, and a
"the laptop did not answer" alert that offers Change address / Try again), `Info.plist` (the three
usage strings, ATS scoped to web content + local networking, version pair), `Fame.entitlements`
(empty, matching `ENTITLEMENTS = ()`), `Assets.xcassets` from the icon script, `project.yml` for
XcodeGen, and `.github/workflows/ipa.yml` - the file that actually makes the `.ipa`. The workflow
installs XcodeGen on `macos-14`, generates the project, runs `xcodebuild` for a real device with
`CODE_SIGNING_ALLOWED=NO`, zips the built `.app` under `Payload/` and uploads `FameStrategist.ipa`
as an artifact. Unsigned on purpose: a runner has no business holding her Apple ID, and AltServer
signs locally anyway.
Nothing here has been compiled yet, and that is the honest state of the whole iOS half - the first
green CI run is the first time this Swift meets a compiler.

## In-app distribution (`src/store/`)

- `data/packages/` holds whatever real artifacts exist (`*.apk`, `*.ipa`, plus her optional
  `store.json` copy file). `apps.json` is generated per request, never stored.
- `src/store/inventory.py` - `scan()` lists packages with size, sha256 and mtime newest-first;
  `resolve()` is the only door to the bytes and refuses empty names, separators, non-package
  suffixes, missing files, directories, and anything that lands outside the folder after symlinks
  are followed. An empty folder is the honest answer, not an error and not a "ready".
- `src/store/altsource.py` writes the AltStore Classic source: metadata, bundle id, icon URL, and one
  `versions[]` entry per real `.ipa` carrying its measured size and date. `apps` is `[]` until an
  `.ipa` exists. No checksum field, because the documented shape has none. `appPermissions` mirrors
  the plist and entitlements exactly, and the tests read both files to keep them in step.
- `GET /store` - the page: what is on disk, how to install it per device, the `apps.json` URL, the
  PIN exception explained, and the plain sentence about the PC having to be on.
- `GET /store/apps.json`, `GET /store/dl/{name}` - the hosting AltStore needs and the download an
  Android phone needs, both `no-store`, and both **allowed past the phone door without the PIN**
  because an installer app cannot carry her cookie. The door comment, the page and the tests all say
  why; the `/store` page itself stays gated.

## What is *not* being claimed

No `.ipa` is produced by this plan on this machine, and nothing in the UI pretends one exists. No
APK has been compiled here either - the toolchain is not installed, and `build_apk.ps1` stops with
the three ways to get it rather than faking a build. No store listing is created for her: any
public shop needs her account and her taps, so the deliverable is the artifact, the listing text and
the exact commands. Nothing here sends anything to any store automatically, follows anyone, or posts
anywhere. The unverified vendor specifics are listed above as unverified rather than smoothed over,
and the plain-http question is stated on `/store` itself as the thing that decides whether the route
works - the steps are not presented as a known-good path.

## Test surface - as written

`tests/store/test_store.py` (33 passing, 1 skipped where Windows will not make a symlink) covers:
`scan()` reporting nothing for an empty folder and ignoring a stray `.txt`/`store.json`; size and
sha256 equal to the bytes actually written; newest-first ordering; `resolve()` refusing nine ways out
of the folder plus a directory named `fake.apk` plus a symlink escape; `source()` emitting
`apps: []` and `news: []` with nothing on disk, and with a real `.ipa` emitting its measured size, an
absolute `downloadURL`, newest-first `versions`, `appPermissions.privacy == PRIVACY` and empty
entitlements; `listing_for()` overriding the four copy fields while `bundle_id` and `version` stay
with the build, and a malformed `store.json` leaving defaults; the plist's three usage strings,
version and build equal to `altsource`; `Fame.entitlements` parsing to `{}`; `project.yml` publishing
the same bundle id and iOS floor; `build.gradle` claiming the same `versionName`/`versionCode` and
namespace; every `AppIcon.appiconset` entry pointing at a PNG that exists at the pixel size it
declares, and every Android mipmap at its density size; `/store` gated for a phone and open on the
laptop; `/store/apps.json` and `/store/dl/<name>` answering a phone that never typed the PIN, with
the served bytes identical to the file; a 404 with a plain sentence for a name that is not a package;
and the page naming a real file's name and megabytes when one exists and saying "Nothing here yet"
with no download link when none does.
