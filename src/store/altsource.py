"""The AltStore Classic source file, written from the .ipa builds that really exist.

A "source" in AltStore is a self-hosted JSON file: metadata about the app plus one entry per
compiled `.ipa`. Her own PC can host it, which is the only $0 option for an app whose engine is a
local Python server. Every field name and every rule below was read off the full source
specification in AltStore's own developer documentation on 2026-11-15, not guessed. Three of those
readings decide what this file does and does not emit:

* there is no checksum field anywhere in the schema, so nothing here validates a hash and none is
  invented - the digest lives on `/store` instead, where she can compare it with `certutil`;
* `marketplaceID` is explicitly not required for a non-notarized app distributed with AltStore
  Classic, which is what this is, so it is omitted rather than faked;
* the specification never requires HTTPS. It shows secure example URLs and says nothing about a
  local address, so these URLs are plain http on her wifi - and whether the AltStore app is
  *allowed* to fetch one is iOS's and AltStore's decision, not this file's. That is the single
  unverified thing standing between this route and a working install, and it is stated on the
  screen rather than assumed here.

This module never invents a listing. If there is no `.ipa` in `data/packages`, `apps` comes back
empty and `/store` says so in plain words - an empty array is a true statement, a version entry for
a build that was never compiled would be the fake success this project forbids.

Two rules taken straight from the AltStore docs and kept visible in the code:

* the order of `versions` decides which one AltStore calls "latest", so newest goes first;
* `appPermissions` is checked against the downloaded `.ipa` and a mismatch means AltStore refuses to
  install, so the entitlements and privacy strings here must be the ones actually compiled into the
  wrapper - they mirror `ios/FameStrategist/Info.plist` and `ios/FameStrategist/Fame.entitlements`.

Anything she would want to word differently (the name on the listing, who published it, the copy)
comes from `data/packages/store.json` when that file exists, so editing the listing is an edit and
not a code change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

BUNDLE_ID = "com.fame.strategist"
VERSION = "1.0"
BUILD = "1"
MIN_OS = "16.0"          # the WKWebView APIs this wrapper uses are all available from iOS 16
CATEGORY = "photo-video"
TINT = "#E05C40"          # the vermillion from --vermillion in app.css, so the page matches the app

# Must match the wrapper's Info.plist usage descriptions exactly - AltStore compares them with the
# strings inside the .ipa and will not install an app whose permissions do not line up.
PRIVACY = {
    "NSPhotoLibraryUsageDescription":
        "Fame Strategist sends a photo from this iPhone to your own computer so it can be edited.",
    "NSCameraUsageDescription":
        "Fame Strategist opens the camera so you can shoot straight into an edit on your computer.",
    "NSLocalNetworkUsageDescription":
        "Fame Strategist looks for the computer running your app on the wifi you are joined to.",
}
ENTITLEMENTS: tuple[str, ...] = ()   # the wrapper asks for no entitlements beyond the defaults

EDITABLE = ("name", "developer", "subtitle", "description")


@dataclass(frozen=True)
class Listing:
    """The words on the store page, before the copy file is read."""

    name: str = "Fame Strategist"
    developer: str = "Self-hosted on this PC"
    subtitle: str = "Your editor, your planner and your numbers, on the computer that already runs them."
    description: str = (
        "The phone front end for a Fame Strategist server running on your own computer over the "
        "same wifi. Editing, captions, the shot list and the metrics all happen on that machine, so "
        "this app is only as live as the PC behind it: turn the server off and the app has nothing "
        "to talk to. Nothing is hosted, no account is needed, and no analytics leave the network."
    )
    bundle_id: str = BUNDLE_ID
    version: str = VERSION
    build: str = BUILD
    min_os: str = MIN_OS
    category: str = CATEGORY
    entitlements: tuple[str, ...] = ENTITLEMENTS
    privacy: dict = field(default_factory=lambda: dict(PRIVACY))


def listing_for(state_dir: Path | str, base: Listing = Listing()) -> Listing:
    """The listing, with `data/packages/store.json` applied over it if she wrote one.

    Only the four copy fields may be overridden; identity and version fields come from the build,
    because a source that disagrees with its own binary is a source that will not install.
    """
    raw = Path(state_dir) / "packages" / "store.json"
    if not raw.is_file():
        return base
    try:
        data = json.loads(raw.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return base
    if not isinstance(data, dict):
        return base
    changes = {key: str(data[key]) for key in EDITABLE if isinstance(data.get(key), str)
               and data[key].strip()}
    return replace(base, **changes) if changes else base


def _absolute(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def source(artifacts, state_dir: Path | str, base_url: str) -> dict:
    """The `apps.json` body for this machine, holding only the .ipa files that exist.

    `base_url` is the address a phone would type (scheme, LAN address and port, no trailing
    slash), because the URLs in a source have to be reachable from the device installing it.
    `inventory.scan` supplies the sizes.
    """
    listing = listing_for(state_dir)
    ipas = [item for item in artifacts if item.kind == "ios"]
    apps: list[dict] = []
    if ipas:
        versions = [{
            "version": listing.version,
            "buildVersion": listing.build,
            "date": item.modified,
            "localizedDescription": "Self-hosted build of the phone front end.",
            "downloadURL": _absolute(base_url, item.url),
            "size": item.size,
            "minOSVersion": listing.min_os,
        } for item in ipas]                     # scan() is newest-first and AltStore reads that as latest-first
        apps.append({
            "name": listing.name,
            "bundleIdentifier": listing.bundle_id,
            "developerName": listing.developer,
            "subtitle": listing.subtitle,
            "localizedDescription": listing.description,
            "iconURL": _absolute(base_url, "/static/icon-512.png"),
            "tintColor": TINT,
            "category": listing.category,
            "screenshots": [],
            "versions": versions,
            "appPermissions": {"entitlements": list(listing.entitlements),
                               "privacy": dict(listing.privacy)},
        })
    body = {
        "name": listing.name,
        "subtitle": listing.subtitle,
        "description": listing.description,
        "iconURL": _absolute(base_url, "/static/icon-512.png"),
        "website": _absolute(base_url, "/store"),
        "tintColor": TINT,
        "nsfw": False,
        "apps": apps,
        "news": [],
    }
    if apps:
        body["featuredApps"] = [app["bundleIdentifier"] for app in apps]
    return body
