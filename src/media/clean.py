"""The editor this app is willing to run: geometry and global tone, nothing else.

Straighten, crop, even the tone, lift colour. All four move or brighten what the camera
already recorded - none of them can add detail, remove an object, or change a person.
Originals are never opened for writing; every result is a separate copy beside them.
"""

from pathlib import Path
import math

from PIL import Image, ImageEnhance, ImageOps

from src.media.judge import nearest_target

CLEAN_SUFFIX = "-clean"
QUALITY = 92
MAX_TILT = 8.0


def clean(src: Path, out_dir: Path) -> Path:
    return fix(src, out_dir, ["exposure", "contrast", "crop"])


def fix(src: Path, out_dir: Path, fixes: list[str], tilt: float = 0.0,
        focus: tuple[float, float] = (0.5, 0.5)) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")

    if "straighten" in fixes and 0.5 <= abs(tilt) <= MAX_TILT:
        # tilt is the correction angle the search already found, so it is applied as-is.
        w0, h0 = im.size
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0))
        # Keep the largest centred rectangle that is wholly inside the rotated frame, so
        # no filled corner wedges survive to be mistaken for content.
        rad = math.radians(abs(tilt))
        cw = int(w0 * math.cos(rad) - h0 * math.sin(rad))
        ch = int(h0 * math.cos(rad) - w0 * math.sin(rad))
        if cw > w0 * 0.5 and ch > h0 * 0.5:
            left, top = (im.width - cw) // 2, (im.height - ch) // 2
            im = im.crop((left, top, left + cw, top + ch))

    if "exposure" in fixes or "contrast" in fixes:
        im = ImageOps.autocontrast(im, cutoff=1)

    if "lift colour" in fixes:
        im = ImageEnhance.Color(im).enhance(1.18)

    if "crop to the thirds point" in fixes:
        im = _crop_to_thirds(im, focus)
    else:
        im = _crop_to_target(im)

    dst = _free_name(out_dir, src.stem)
    im.save(dst, "JPEG", quality=QUALITY)
    return dst


def _target_box(width: int, height: int) -> tuple[int, int]:
    _, ratio = nearest_target(width, height)
    if width / height > ratio:
        return int(round(height * ratio)), height
    return width, int(round(width / ratio))


def _crop_to_target(im: Image.Image) -> Image.Image:
    cw, ch = _target_box(im.width, im.height)
    left, top = (im.width - cw) // 2, (im.height - ch) // 2
    return im.crop((left, top, left + cw, top + ch))


def _crop_to_thirds(im: Image.Image, focus: tuple[float, float]) -> Image.Image:
    """Keep the target shape but slide the window so the measured subject lands on a thirds line."""
    cw, ch = _target_box(im.width, im.height)
    span_x, span_y = im.width - cw, im.height - ch
    left = top = 0
    if span_x:
        best = min((1 / 3, 2 / 3), key=lambda t: abs(focus[0] - t))
        left = int(max(0, min(span_x, focus[0] * im.width - best * cw)))
    if span_y:
        best = min((1 / 3, 2 / 3), key=lambda t: abs(focus[1] - t))
        top = int(max(0, min(span_y, focus[1] * im.height - best * ch)))
    return im.crop((left, top, left + cw, top + ch))


def _free_name(out_dir: Path, stem: str) -> Path:
    dst = out_dir / f"{stem}{CLEAN_SUFFIX}.jpg"
    n = 2
    while dst.exists():
        dst = out_dir / f"{stem}{CLEAN_SUFFIX}-{n}.jpg"
        n += 1
    return dst
