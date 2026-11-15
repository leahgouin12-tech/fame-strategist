"""Launcher icons for the two packages, cut from the one brand image the app already ships.

The input is `src/static/icon-512.png` - the same 512 px square the PWA installs from, and the
only finished brand art on this machine. Everything below is a downscale of it, which is why the
result is sharp: 48 to 192 px for Android, 40 to 180 px for iPhone.

Deliberately missing, for the same reason nothing else here is invented:

* **no 1024 px iOS slot.** The source is 512 px, so a 1024 would be an upscale presented as an
  original. That size is only mandatory for an App Store submission; a self-hosted `.ipa` that
  AltStore or a personal certificate installs runs on the classic iPhone sizes, so those are what
  get written. If she ever draws the mark larger, add the entry to `IOS_ICON_SIZES` and re-run.
* **no Android adaptive icon.** An adaptive icon is a 108 dp canvas with the artwork parked in a
  safe zone, and doing that properly means re-composing the mark rather than scaling it. The
  legacy `ic_launcher.png` mipmaps are a complete answer on their own - every version of Android
  installs them, and the shape mask is the launcher's to choose.

Re-run this after changing `src/static/icon-512.png`; the generated files are checked in so a
clone can build without Pillow.

    .venv/Scripts/python.exe scripts/make_icons.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "static" / "icon-512.png"
ANDROID_DIR = ROOT / "apk" / "app" / "src" / "main" / "res"
IOS_DIR = ROOT / "ios" / "FameStrategist" / "Assets.xcassets" / "AppIcon.appiconset"

# Android density buckets: the launcher picks one and never scales it up.
ANDROID_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

# iPhone only (TARGETED_DEVICE_FAMILY is "1"), so no iPad or Notification-Center idioms.
# (pixel size, idiom, scale) - the triple Xcode matches against, in the order it lists them.
IOS_SIZES = [
    (40, "iphone", "2x"),    # 20 pt @2x
    (60, "iphone", "3x"),    # 20 pt @3x
    (58, "iphone", "2x"),    # 29 pt @2x (Settings)
    (87, "iphone", "3x"),    # 29 pt @3x
    (80, "iphone", "2x"),    # 40 pt @2x (Spotlight)
    (120, "iphone", "3x"),   # 40 pt @3x
    (120, "iphone", "2x"),   # 60 pt @2x (the home-screen icon)
    (180, "iphone", "3x"),   # 60 pt @3x
]


def _square(source: Path) -> Image.Image:
    image = Image.open(source)
    if image.mode != "RGB":
        image = image.convert("RGB")
    if image.size[0] != image.size[1]:
        raise SystemExit(f"{source.name} is not square; crop it to one before generating icons")
    return image


def android(image: Image.Image) -> list[Path]:
    written: list[Path] = []
    for density, px in ANDROID_SIZES.items():
        folder = ANDROID_DIR / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / "ic_launcher.png"
        image.resize((px, px), Image.LANCZOS).save(out, optimize=True)
        written.append(out)
    return written


def ios(image: Image.Image) -> list[Path]:
    IOS_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    entries = []
    for px, idiom, scale in IOS_SIZES:
        name = f"AppIcon-{px}.png"
        out = IOS_DIR / name
        if not out.exists():                       # 120 px appears at both 2x and 3x
            image.resize((px, px), Image.LANCZOS).save(out, optimize=True)
        entries.append({"size": f"{px // int(scale[:-1])}x{px // int(scale[:-1])}",
                        "scale": scale, "idiom": idiom, "filename": name})
        written.append(out)
    (IOS_DIR / "Contents.json").write_text(
        json.dumps({"images": entries,
                    "info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
        encoding="utf-8")
    (IOS_DIR.parent / "Contents.json").write_text(
        json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2) + "\n",
        encoding="utf-8")
    return written


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f"no brand image at {SOURCE} - the icons cannot be cut from nothing")
    image = _square(SOURCE)
    if image.size[0] < max(list(ANDROID_SIZES.values()) + [px for px, _, _ in IOS_SIZES]):
        raise SystemExit(f"{SOURCE.name} is {image.size[0]} px, smaller than the biggest slot")
    for out in android(image) + ios(image):
        print(f"{out.relative_to(ROOT)}  {out.stat().st_size:,} bytes")
    pngs = len([p for p in IOS_DIR.glob("*.png")])
    print(f"\n{image.size[0]} px source -> {len(ANDROID_SIZES)} android + {pngs} ios pngs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
