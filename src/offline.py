"""Everything the app can show, as one list a phone can pull down before it leaves the wifi.

The ask behind this file is blunt: the icon has to work with no network at all, not only the text
pages. That is only honest if the list is *derived*. A hand-written set of pages would drift the day
somebody adds a room, and "everything" would quietly become "most of it" - the kind of gap nobody
notices until they are standing somewhere without wifi. So the pages come from the registry's own
read of `src/app.py` (every GET route that renders a template of its own, no path parameters), and
the media comes from the three folders the app mounts as files.

What cannot be here: work that needs the engine. A new cut, a preview the editor renders on every
slider move, a fresh number, an agent run - all of those ask the laptop to compute something, so
they are named in the manifest as generated rather than stored, and the Phone page says so in plain
words instead of leaving a dead button to explain it. A cached JPEG of a preview the phone never
asked for is not the same achievement as making that preview, and pretending otherwise is exactly
the fake success state this project forbids.

Sizes are counted from disk so the phone can be told the truth *before* it downloads: the ceilings
are the worker's to enforce, but the numbers here let the page promise something it can keep.
Nothing in this module reads a photo's contents, deletes a file, or hands a path out - the URLs are
the mount prefix plus a relative name, which is the only form a browser can use anyway.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from src.registry import audit

# The folders StaticFiles is mounted on, with the URL prefix each one answers to. These three are
# the whole of the app's file surface; audio is written into outputs/story and served from there.
MOUNTS = (("inbox", "/inbox"), ("outputs", "/outputs"), ("frames", "/frames"))

# One file bigger than this is not worth putting on a phone: the pages that show it stream it from
# the laptop anyway, and a 200 MB clip would evict the whole cache on iOS.
MAX_FILE_BYTES = 64 * 1024 * 1024

# Endpoints that draw a picture when asked instead of serving a stored one. They cannot be packed
# ahead of time (the answer depends on the query), so the worker caches whatever it has already
# seen and the page says which previews need the laptop.
GENERATED = ("/edit/preview", "/clip/preview")


_PAGES: dict = {}


def pages() -> list:
    """Every GET route that renders a page of its own, straight out of the code.

    Routes with `{name}` in the path are left out on purpose: they need a real filename to answer,
    and one is already inside the page that links to it. A redirect-only route is left out for the
    same reason - it has no content of its own to store.

    The registry reads and parses the whole of `src/app.py`, which is worth doing once per edit and
    not once per Phone page, so the answer is held against the file's own timestamp.
    """
    key = (audit.APP_PY.stat().st_mtime_ns, audit.APP_PY.stat().st_size)
    if _PAGES.get("key") == key:
        return list(_PAGES["value"])

    out = []
    for entry in audit.routes():
        method, path = entry.key.removeprefix("route:").split(" ", 1)
        if method != "GET" or "{" in path:
            continue
        if not any(o.startswith("renders ") for o in entry.outputs):
            continue
        out.append(path)
    if "/offline/manifest" in out:
        out.remove("/offline/manifest")
    _PAGES.update({"key": key, "value": sorted(set(out))})
    return list(_PAGES["value"])


def _stamp(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def media(root) -> dict:
    """Every file the app can hand a browser, with its URL, size and modification time."""
    root = Path(root)
    items, skipped = [], []
    for folder, prefix in MOUNTS:
        base = root / folder
        if not base.is_dir():
            continue
        for spot in sorted(base.rglob("*")):
            if not spot.is_file() or spot.name.startswith("."):
                continue
            size = spot.stat().st_size
            url = f"{prefix}/{spot.relative_to(base).as_posix()}"
            if size > MAX_FILE_BYTES:
                skipped.append({"url": url, "bytes": size,
                                "why": f"bigger than {MAX_FILE_BYTES // 1024 // 1024} MB"})
                continue
            items.append({"url": url, "bytes": size, "mtime": _stamp(spot.stat().st_mtime)})
    return {"items": items, "skipped": skipped}


def manifest(root) -> dict:
    """The whole downloadable app: pages, files, totals, and what is deliberately not here."""
    got = pages()
    files = media(root)
    listing = {
        "pages": got,
        "media": files["items"],
        "too_big": files["skipped"],
        "generated": list(GENERATED),
        "bytes": sum(m["bytes"] for m in files["items"]),
        "built": _stamp(datetime.now(timezone.utc).timestamp()),
    }
    listing["counts"] = {"pages": len(got), "files": len(files["items"]),
                         "too_big": len(files["skipped"])}
    return listing


def as_json(root) -> str:
    return json.dumps(manifest(root), ensure_ascii=False)
