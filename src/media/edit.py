"""The editing engine behind the Edit screen.

Tone, geometry, lens blur, spot removal, looks - about twenty controls, all of them
computed on her own file, on this machine, in Pillow. Nothing here reshapes a face or
body, smooths skin, or regenerates a region: the app's own rule is that an edit which
changes how a person looks is not one it will offer, and tests/media/test_edit.py
fails the suite if an operation ever crosses that line.

A recipe is a plain list of ["name", arg, arg...] entries, so it can be shown to her,
saved beside the file, and re-applied to the original later without losing quality.
"""

from dataclasses import dataclass
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFile, ImageFilter, ImageOps

ImageFile.LOAD_TRUNCATED_IMAGES = True

PREVIEW_EDGE = 900
SAVE_QUALITY = 95
MAX_SPOT = 0.12
MAX_ROTATE = 15.0
RATIO_LO, RATIO_HI = 0.2, 5.0
GROUPS = ("frame", "tone", "lens", "heal")


@dataclass
class Op:
    name: str
    label: str
    group: str
    lo: float = -1.0
    hi: float = 1.0
    step: float = 0.05
    unit: str = ""
    note: str = ""


SLIDERS = [
    Op("rotate", "straighten", "frame", -MAX_ROTATE, MAX_ROTATE, 0.1, "°",
       "rotates the whole frame and crops in so no empty corner survives"),
    Op("exposure", "exposure", "tone", -1, 1, 0.02, " stops",
       "multiplies every pixel; pure white and pure black stay where they are"),
    Op("brightness", "brightness", "tone", -1, 1),
    Op("contrast", "contrast", "tone", -1, 1),
    Op("saturation", "saturation", "tone", -1, 1),
    Op("temperature", "warm / cool", "tone", -1, 1, 0.02, "",
       "shifts red against blue; it cannot add colour a channel never recorded"),
    Op("tint", "green / magenta", "tone", -1, 1, 0.02),
    Op("highlights", "highlights", "tone", -1, 1, 0.02, "",
       "recovers the bright end only where it is not already pure white"),
    Op("shadows", "shadows", "tone", -1, 1, 0.02, "",
       "opens the dark end only where it is not already pure black"),
    Op("gamma", "midtones", "tone", -1, 1, 0.02),
    Op("fade", "fade", "tone", 0, 1, 0.02),
    Op("blackwhite", "black & white", "tone", 0, 1, 0.05),
    Op("sharpness", "sharpness", "tone", -1, 1, 0.02, "",
       "sharpens what is there; it cannot rebuild detail the lens missed"),
    Op("structure", "structure", "tone", 0, 1, 0.02, "", "local contrast over wide areas"),
    Op("grain", "grain", "tone", 0, 1, 0.02),
    Op("vignette", "vignette", "tone", -1, 1, 0.02, "",
       "darkens toward the edge, or toward the centre when negative"),
    Op("blur", "whole-frame blur", "tone", 0, 1, 0.02),
    Op("lens_blur", "background blur", "lens", 0, 1, 0.02, "",
       "keeps one point sharp and softens away from it; the point is yours, not detected"),
]

OPS = {op.name: op for op in SLIDERS}
for _extra in (Op("crop", "crop", "frame", RATIO_LO, RATIO_HI, 0.01),
               Op("flip", "mirror", "frame", 0, 1, 1),
               Op("heal", "heal", "heal", 0, MAX_SPOT, 0.01)):
    OPS[_extra.name] = _extra


def load(path: Path) -> Image.Image:
    with Image.open(path) as raw:
        return ImageOps.exif_transpose(raw).convert("RGB")


def preview(im: Image.Image) -> Image.Image:
    scale = PREVIEW_EDGE / max(im.size)
    if scale >= 1:
        return im
    return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)


def _lut(fn):
    return [max(0, min(255, int(round(fn(i))))) for i in range(256)]


def _curve(im, fn):
    return im.point(_lut(fn) * 3)


def _rgb(im, rf=1.0, gf=1.0, bf=1.0):
    return im.point(_lut(lambda x: x * rf) + _lut(lambda x: x * gf) + _lut(lambda x: x * bf))


def _unit(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi > lo else 0.0


def _radial(size, cx, cy, inner, outer, bend=2.0):
    """A smooth 0-1 disc stretched over the frame, built once at 96x96."""
    n = 96
    px = bytearray(n * n)
    for y in range(n):
        for x in range(n):
            d = min(1.0, math.hypot((x / (n - 1) - cx) * 2, (y / (n - 1) - cy) * 2))
            px[y * n + x] = max(0, min(255, int(round(255 * (inner + (outer - inner) * d ** bend)))))
    return Image.frombytes("L", (n, n), bytes(px)).resize(size, Image.BILINEAR)


def _rotate(im, args):
    v = args[0]
    if abs(v) < 0.05:
        return im
    w0, h0 = im.size
    turned = im.rotate(v, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0))
    rad = math.radians(abs(v))
    cw = int(w0 * math.cos(rad) - h0 * math.sin(rad))
    ch = int(h0 * math.cos(rad) - w0 * math.sin(rad))
    if cw < 32 or ch < 32:
        return turned
    left, top = (turned.width - cw) // 2, (turned.height - ch) // 2
    return turned.crop((left, top, left + cw, top + ch))


def _crop(im, args):
    w, h = im.size
    if len(args) == 1:
        # A ratio chip, resolved here rather than in the page: the frame it is fitting
        # is whatever the straighten left behind, and only this function knows its size.
        cw, ch = (h * args[0], h) if h * args[0] <= w else (w, w / args[0])
        left, top = (w - cw) / 2.0, (h - ch) / 2.0
        args = [left / w, top / h, (left + cw) / w, (top + ch) / h]
    l, t, r, b = args[:4]
    w, h = im.size
    box = (max(0, int(l * w)), max(0, int(t * h)), min(w, int(r * w)), min(h, int(b * h)))
    if box[2] - box[0] < 32 or box[3] - box[1] < 32:
        return im
    return im.crop(box)


def _flip(im, args):
    return im.transpose(Image.FLIP_LEFT_RIGHT) if args[0] > 0 else im


def _heal(im, args):
    """Replace a small patch with the texture already around it.

    Two median passes then a light blur, feathered out to nothing at the edge of the
    patch. It borrows neighbouring pixels; it does not invent a new face, skin or object.
    """
    out = im
    w, h = im.size
    for i in range(0, len(args) - 2, 3):
        x = max(0.0, min(1.0, args[i]))
        y = max(0.0, min(1.0, args[i + 1]))
        pr = max(3, min(MAX_SPOT, max(0.005, args[i + 2])) * min(w, h))
        cx, cy = int(x * w), int(y * h)
        box = (max(0, cx - int(pr * 2.5)), max(0, cy - int(pr * 2.5)),
               min(w, cx + int(pr * 2.5)), min(h, cy + int(pr * 2.5)))
        patch = out.crop(box)
        if patch.width < 9 or patch.height < 9:
            continue
        filled = patch.filter(ImageFilter.MedianFilter(9)).filter(ImageFilter.MedianFilter(9))
        filled = filled.filter(ImageFilter.GaussianBlur(max(1, pr / 6)))
        disc = _radial(patch.size, (cx - box[0]) / patch.width, (cy - box[1]) / patch.height,
                       1.0, 0.0, bend=1.6)
        out = out.copy()
        out.paste(Image.composite(filled, patch, disc), box)
    return out


def _lens_blur(im, args):
    v, cx, cy, spread = args[0], args[1], args[2], args[3] if len(args) > 3 else 0.45
    if v <= 0:
        return im
    blurred = im.filter(ImageFilter.GaussianBlur(1 + 14 * v))
    keep = _radial(im.size, max(0.0, min(1.0, cx)), max(0.0, min(1.0, cy)),
                   1.0, 0.0, bend=1 + 4 * max(0.05, spread))
    return Image.composite(im, blurred, keep)


APPLIERS = {
    "rotate": _rotate,
    "crop": _crop,
    "flip": _flip,
    "heal": _heal,
    "lens_blur": _lens_blur,
    "exposure": lambda im, a: _curve(im, lambda x: x * (2 ** a[0])),
    "brightness": lambda im, a: _curve(im, lambda x: x + a[0] * 36),
    "contrast": lambda im, a: ImageEnhance.Contrast(im).enhance(1 + a[0] * 0.5),
    "saturation": lambda im, a: ImageEnhance.Color(im).enhance(max(0.0, 1 + a[0] * 0.8)),
    "temperature": lambda im, a: _rgb(im, 1 + 0.10 * a[0], 1, 1 - 0.10 * a[0]),
    "tint": lambda im, a: _rgb(im, 1 + 0.05 * a[0], 1 - 0.09 * a[0], 1 + 0.05 * a[0]),
    "highlights": lambda im, a: _curve(im, lambda x: 255 * (x / 255 + a[0] * 0.55 * (x / 255) ** 2)),
    "shadows": lambda im, a: _curve(im, lambda x: 255 * (x / 255 + a[0] * 0.55 * (1 - x / 255) ** 2)),
    "gamma": lambda im, a: _curve(im, lambda x: 255 * (x / 255) ** (1 / (1 + 0.7 * a[0]))),
    "fade": lambda im, a: _curve(im, lambda x: 255 * (x / 255 * (1 - 0.28 * a[0]) + 0.13 * a[0])),
    "blackwhite": lambda im, a: Image.blend(im, im.convert("L").convert("RGB"), a[0]),
    "sharpness": lambda im, a: (im.filter(ImageFilter.UnsharpMask(radius=2, percent=int(190 * a[0]), threshold=2))
                                if a[0] > 0 else im.filter(ImageFilter.GaussianBlur(-a[0] * 2.5))),
    "structure": lambda im, a: im.filter(ImageFilter.UnsharpMask(radius=16, percent=int(75 * a[0]), threshold=2)),
    "grain": lambda im, a: Image.blend(im, ImageChops.overlay(
        im, Image.effect_noise(im.size, int(10 + 90 * a[0])).convert("L").convert("RGB")), min(0.7, a[0])),
    "vignette": lambda im, a: ImageChops.multiply(im, _multiplier(im.size, a[0])),
    "blur": lambda im, a: im.filter(ImageFilter.GaussianBlur(a[0] * 10)),
}


def _multiplier(size, v):
    """255 in the middle falling to 255*(1-0.6|v|) at the edge, or the reverse."""
    if v > 0:
        return _radial(size, 0.5, 0.5, 1.0, 1 - 0.6 * v).convert("RGB")
    return _radial(size, 0.5, 0.5, 1 - 0.6 * abs(v), 1.0).convert("RGB")


def normalize(recipe) -> list:
    """Drop names this engine does not know, clamp each control to its own range,
    keep one entry per control, and always run geometry before tone."""
    seen: dict[str, list] = {}
    for entry in recipe or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        name = str(entry[0])
        if name not in APPLIERS:
            continue
        args = [float(a) for a in entry[1:] if isinstance(a, (int, float))]
        if not args:
            continue
        seen[name] = [name] + _clamp_args(name, args)
    ordered = sorted(seen.values(), key=lambda e: GROUPS.index(OPS[e[0]].group))
    return [e for e in ordered if not _is_noop(e)]


def _clamp_args(name: str, args: list[float]) -> list[float]:
    """Clamp each argument by what it means. A heal entry is x, y, radius triples, so the
    slider range of the brush must not be applied to the position - that would move the
    spot somewhere she never tapped."""
    if name == "heal":
        out = []
        for i in range(0, len(args) - 2, 3):
            out += [_unit01(args[i]), _unit01(args[i + 1]), min(max(args[i + 2], 0.0), MAX_SPOT)]
        return out
    if name == "crop":
        if len(args) == 1:
            return [min(max(args[0], RATIO_LO), RATIO_HI)]
        return [_unit01(a) for a in args[:4]]
    if name == "lens_blur":
        return [min(max(args[0], OPS[name].lo), OPS[name].hi)] + [_unit01(a) for a in args[1:]]
    op = OPS.get(name)
    return [min(max(args[0], op.lo), op.hi)] if op else args


def _unit01(v: float) -> float:
    return min(max(v, 0.0), 1.0)


def _is_noop(entry) -> bool:
    name = entry[0]
    if name == "heal":
        return len(entry) < 4
    if name == "crop":
        box = entry[1:]
        return not box or (len(box) == 4 and tuple(box) == (0.0, 0.0, 1.0, 1.0))
    if name == "rotate":
        return abs(entry[1]) < 0.05
    return entry[1] == 0


def apply(im: Image.Image, recipe) -> Image.Image:
    out = im
    for entry in normalize(recipe):
        out = APPLIERS[entry[0]](out, entry[1:])
    return out


def edit_file(path: Path, recipe, proxy: bool = False) -> Image.Image:
    im = preview(load(path)) if proxy else load(path)
    return apply(im, recipe)


PRESETS = {
    "clean": [["exposure", 0.06], ["contrast", 0.2], ["saturation", 0.12],
              ["shadows", 0.28], ["highlights", -0.22], ["structure", 0.22]],
    "warm": [["temperature", 0.38], ["exposure", 0.05], ["fade", 0.12], ["saturation", 0.1]],
    "moody": [["contrast", 0.32], ["shadows", -0.36], ["saturation", -0.22],
              ["vignette", 0.36], ["grain", 0.16]],
    "faded": [["fade", 0.45], ["contrast", -0.16], ["saturation", -0.12], ["temperature", 0.1]],
    "punchy": [["contrast", 0.36], ["saturation", 0.36], ["structure", 0.36],
               ["shadows", 0.16], ["highlights", -0.16]],
    "film": [["grain", 0.3], ["fade", 0.2], ["temperature", 0.16], ["contrast", 0.16]],
    "noir": [["blackwhite", 1.0], ["contrast", 0.4], ["grain", 0.2], ["vignette", 0.3]],
}


def group_of(name: str) -> str:
    return OPS[name].group if name in OPS else "heal"
