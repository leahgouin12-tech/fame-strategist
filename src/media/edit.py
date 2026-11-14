"""The editing engine behind the Edit screen.

Ten families of tools run through one pipeline. The tone and geometry controls live here;
the brush retouch (skin, shine, teeth, eyes, colour, liquify) lives in retouch.py; the
effects (auto, keystone, stretch, cutout, splash, upscale) live in effects.py; the layers
(text, a second photo, blend modes, frames, collage) live in layers.py; the colour rail
(curves, levels, one hue at a time) lives in colour.py; the glass (tilt-shift, the four
blurs, prism, glitch) lives in optics.py; the two push-pull warps live in mesh.py; the
repair brushes (clone, concealer, red eye, bronzer) live in repair.py; and the drawing kit
(brush, stickers, text on an arc, cut to shape, backdrop) lives in design.py.
Every one of them is computed on her own file, on this machine, in Pillow - no upload,
no model, no generative pixels that were never in the frame.

A recipe is a plain list of ["name", arg, arg...] entries, so it can be shown to her,
saved beside the file, and re-applied to the original later without losing quality.
Brush tools carry many strokes in one entry, which is why one name can repeat.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random

from PIL import Image, ImageChops, ImageEnhance, ImageFile, ImageFilter, ImageOps

from src.media import colour, design, effects, layers, mesh, optics, repair, retouch
from src.media.registry import (EFFECTS, F, COLOUR, DESIGN, LAYERS, MESH, ORDER, OPTICS,
                                RAILS, RAIL, REPAIR, SKIN, TITLES, Tool, tone)

ImageFile.LOAD_TRUNCATED_IMAGES = True

PREVIEW_EDGE = 900
SAVE_QUALITY = 95
MAX_SPOT = 0.12
MAX_ROTATE = 15.0
RATIO_LO, RATIO_HI = 0.2, 5.0


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
               Op("heal", "heal", "heal", 0, MAX_SPOT, 0.01),
               Op("restore", "restore", "heal", 0, retouch.MAX_UNDO, 0.01)):
    OPS[_extra.name] = _extra

# The rails whose brushes repaint her face or move her pixels, and the one control that
# reads the frame from before all of them. Because `restore` needs that history it cannot
# be a (image, args) applier like the rest, so apply() runs it itself - see RUNTIME_OPS.
RETOUCH_RAILS = ("skin", "face")
RUNTIME_OPS = ("restore",)


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


GRAIN_TILE = 256


def _grain(im, a):
    """Film grain, drawn from the picture rather than from the clock.

    Pillow's own effect_noise reads an unseeded generator, so the same file at the same
    amount came out different on every call - the preview, the save and the re-opened
    recipe were three different pictures, which makes the stored recipe a lie. Seeding from
    a thumbnail of the image and the amount keeps it stable per photo without making every
    photo grain in the same pattern."""
    sigma = int(10 + 90 * a[0])
    key = (im.convert("L").resize((8, 8), Image.BILINEAR).tobytes(), round(a[0], 4))
    seed = int.from_bytes(hashlib.sha256(key[0] + str(key[1]).encode()).digest()[:8], "big")
    rng = random.Random(seed)
    tile = bytes(min(255, max(0, round(rng.gauss(128, sigma))))
                 for _ in range(GRAIN_TILE * GRAIN_TILE))
    need = im.size[0] * im.size[1]
    layer = Image.frombytes("L", im.size, (tile * (1 + need // len(tile)))[:need])
    return Image.blend(im, ImageChops.overlay(im, layer.convert("RGB")), min(0.7, a[0]))


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
    "grain": _grain,
    "vignette": lambda im, a: ImageChops.multiply(im, _multiplier(im.size, a[0])),
    "blur": lambda im, a: im.filter(ImageFilter.GaussianBlur(a[0] * 10)),
}

# The three bolt-on engines register themselves here rather than each one editing this
# file, so a name clash is visible in one place: the tone rail already owns "tint".
RENAMED = {"tint": "makeup"}
ENGINE, SHAPE, CLAMP, CAP = {}, {}, {}, {}
for _module in (retouch, effects, layers, colour, optics, mesh, repair, design):
    for _name, _fn in _module.APPLIERS.items():
        _key = RENAMED.get(_name, _name)
        if _key in APPLIERS:
            raise RuntimeError(f"{_key} is claimed by two engines")
        ENGINE[_key] = _fn
        SHAPE[_key] = _module.SHAPE[_name]
        CLAMP[_key] = _module.CLAMP[_name]
        CAP[_key] = _module.LIMITS.get(_name, 24)
APPLIERS.update(ENGINE)


def _legacy_tool(name: str) -> Tool | None:
    """The controls that predate the registry, described in the same shape as the rest.
    Their ranges still come from OPS, so a limit is written down exactly once."""
    if name == "heal":
        return Tool("heal", "Zap",
                    (F(2, "brush", "slider", 0.01, MAX_SPOT, 0.005, 0.03),), stroke=True,
                    note="Borrows the texture a few pixels around the spot - a stray hair, a bin, "
                         "a reflection. The cap is there because a brush this blunt should not be "
                         "repainting half a person.")
    if name == "restore":
        return Tool("restore", "Undo brush",
                    (F(2, "brush", "slider", 0.01, retouch.MAX_UNDO, 0.005, 0.08),),
                    stroke=True,
                    note="Uncovers the pixels from before every brush stroke, right where you "
                         "paint. The grade and the crop stay, the retouch under the brush goes - "
                         "it reveals what was already in the file instead of smoothing again.")
    if name == "lens_blur":
        return Tool("lens_blur", "Fall-off",
                    (F(0, "amount", "slider", 0, 1, 0.02, 0.5),
                     F(1, "x", "slider", 0, 1, 0.01, 0.5),
                     F(2, "y", "slider", 0, 1, 0.01, 0.5),
                     F(3, "feather", "slider", 0.05, 1, 0.05, 0.45)),
                    repeats=False,
                    note="One point stays sharp and everything away from it softens. The point is "
                         "yours, not detected - a machine guessing the subject is how these fail.")
    if name in ("crop", "flip"):
        return None
    op = OPS[name]
    return tone(op.name, op.label, op.lo, op.hi, op.step, op.unit,
                op.note or f"{op.label} across the whole frame.")


ENGINE_TOOLS = {**SKIN, **EFFECTS, **LAYERS, **COLOUR, **OPTICS, **MESH, **REPAIR, **DESIGN}


def arity_of(name: str) -> int:
    """How many arguments one entry of this control carries. The page slices a painted
    stroke list by this number, and a slot layout that disagrees with it is a bug."""
    shape = SHAPE.get(name)
    if shape:
        return shape[1] if shape[0] == "group" else len(shape[1])
    return {"heal": 3, "restore": 3, "lens_blur": 4}.get(name, 1)


RAIL_TOOLS: dict[str, list[Tool]] = {}
for _rail in RAILS:
    _tools = []
    for _name in ORDER[_rail]:
        _tool = ENGINE_TOOLS.get(_name) or (_legacy_tool(_name) if _name in OPS else None)
        if _tool is not None:
            _tools.append(_tool)
    RAIL_TOOLS[_rail] = _tools

TOOLS = [tool for _rail in RAILS for tool in RAIL_TOOLS[_rail]]
TOOL_OF = {tool.op: tool for tool in TOOLS}
ARITY = {tool.op: arity_of(tool.op) for tool in TOOLS}


def slots(tool: Tool) -> int:
    """How many argument slots a control occupies, counting the three a colour picker
    writes and the two a painted position writes."""
    used = [f.at + (3 if f.kind == "colour" else 1) for f in tool.fields]
    used += [p + 1 for p in tool.points] if tool.stroke else []
    return max([ARITY.get(tool.op, 1)] + used)


def tools_json() -> str:
    """The page builds its rails out of this, so a control the engine can already run
    appears the moment it is named - nothing about the editor is written down twice."""
    return json.dumps([
        {"rail": rail, "title": TITLES[rail],
         "tools": [{"op": t.op, "label": t.label, "stroke": t.stroke, "repeats": t.repeats,
                    "points": list(t.points), "arity": ARITY[t.op], "note": t.note,
                    "fields": [{"at": f.at, "label": f.label, "kind": f.kind, "lo": f.lo,
                                "hi": f.hi, "step": f.step, "value": f.value, "unit": f.unit,
                                "hint": f.hint, "options": list(f.options)} for f in t.fields]}
                    for t in RAIL_TOOLS[rail]]}
        for rail in RAILS])


def _multiplier(size, v):
    """255 in the middle falling to 255*(1-0.6|v|) at the edge, or the reverse."""
    if v > 0:
        return _radial(size, 0.5, 0.5, 1.0, 1 - 0.6 * v).convert("RGB")
    return _radial(size, 0.5, 0.5, 1 - 0.6 * abs(v), 1.0).convert("RGB")


def normalize(recipe) -> list:
    """Drop names this engine does not know, clamp every argument to the range its own
    module declares, fold repeated strokes into the entry that already holds them, and
    run the rails in the order the pipeline needs - geometry, then tone, then the brush,
    then the composite layers on top."""
    seen: dict[str, list] = {}
    for entry in recipe or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        name = str(entry[0])
        if name in SHAPE:
            args = _clamp_engine(name, list(entry[1:]))
            if not args:
                continue
            if SHAPE[name][0] == "group":
                if name in seen:
                    seen[name].extend(args)
                else:
                    seen[name] = [name, *args]
            else:
                seen[name] = [name, *args]
            continue
        args = [float(a) for a in entry[1:] if isinstance(a, (int, float))]
        if args:
            seen[name] = [name] + _clamp_args(name, args)
    strokes = {name: _trim_groups(name, entry) for name, entry in seen.items()
               if name in RAIL}
    ordered = sorted((e for e in strokes.values() if e), key=_rank)
    return [e for e in ordered if not _is_noop(e)]


def _rank(entry) -> float:
    """Where an entry sits in the pipeline. The undo brush reads the frame from before the
    brushes, so it runs after every one of them no matter when she painted it - otherwise
    a stroke of undo laid down first would be buried by the smoothing painted after it."""
    base = float(RAILS.index(RAIL[entry[0]]))
    return base + 0.5 if entry[0] in RUNTIME_OPS else base


def _clamp_engine(name: str, args: list) -> list:
    """Every module declares its own ranges, so a hand-edited recipe cannot hand the
    engine a brush size of 40 or a font size of 9000. A None bound means that slot holds
    text, not a number."""
    shape, bounds = SHAPE[name], CLAMP[name]
    if shape[0] == "group":
        k, n = shape[1], shape[2]
        limit = max(1, min(n, CAP.get(name, n)))
        cells = [args[i:i + k] for i in range(0, len(args) - k + 1, k)][:limit]
        return [v for cell in cells for v in _slots(cell, bounds, k)]
    specs = shape[1]
    return _slots(args, bounds, len(specs), specs)


def _slots(values: list, bounds: list, k: int, specs: list | None = None) -> list:
    out = []
    for i in range(k):
        value = values[i] if i < len(values) else None
        bound = bounds[i] if i < len(bounds) else None
        if (specs[i] == "s") if specs else bound is None:
            out.append(str(value)[:800] if value is not None else "")
        else:
            lo, hi = bound if bound else (-1.0, 1.0)
            out.append(_num(value, lo, hi))
    return out


def _num(value, lo: float, hi: float) -> float:
    try:
        return min(max(float(value), lo), hi)
    except (TypeError, ValueError):
        return lo


def _trim_groups(name: str, entry: list) -> list:
    """A stroke whose controls are all zero is not an edit; it is wasted recomputation on
    every preview, so it goes. The last strokes are the ones she wants to keep."""
    shape = SHAPE.get(name)
    if not shape or shape[0] != "group":
        return entry
    k = shape[1]
    args = entry[1:]
    kept = [args[i:i + k] for i in range(0, len(args) - k + 1, k)
            if any(abs(v) > 1e-6 if isinstance(v, (int, float)) else v for v in args[i + 2:i + k])]
    return [name, *[a for group in kept for a in group]] if kept else []


def _clamp_args(name: str, args: list[float]) -> list[float]:
    """Clamp each argument by what it means. A heal entry is x, y, radius triples, so the
    slider range of the brush must not be applied to the position - that would move the
    spot somewhere she never tapped."""
    if name in ("heal", "restore"):
        cap = MAX_SPOT if name == "heal" else retouch.MAX_UNDO
        out = []
        for i in range(0, len(args) - 2, 3):
            out += [_unit01(args[i]), _unit01(args[i + 1]), min(max(args[i + 2], 0.0), cap)]
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
    shape = SHAPE.get(name)
    if shape:
        # A painted entry opens with the x she tapped, which is a position and not an
        # amount; a whole-frame entry opens with its single lever. Reading both from
        # slot 1 onwards threw away every one-argument control the engine had.
        args = entry[2:] if shape[0] == "group" else entry[1:]
        return not any(abs(v) > 1e-6 if isinstance(v, (int, float)) else str(v).strip()
                       for v in args)
    if name in ("heal", "restore"):
        return len(entry) < 4
    if name == "crop":
        box = entry[1:]
        return not box or (len(box) == 4 and tuple(box) == (0.0, 0.0, 1.0, 1.0))
    if name == "rotate":
        return abs(entry[1]) < 0.05
    return entry[1] == 0


def apply(im: Image.Image, recipe) -> Image.Image:
    """Run a recipe in pipeline order, holding on to the frame as it stood before the
    first brush stroke so the undo brush has something real to uncover.

    That snapshot is taken after the geometry and the grade, which is what makes an undo
    uncover her own skin instead of an unedited, unwarmed rectangle in the middle of a
    finished picture.
    """
    out, before_brushes, brushed = im, im, False
    for entry in normalize(recipe):
        name = entry[0]
        if name in RUNTIME_OPS:
            if brushed:
                out = retouch.restore_pixels(out, before_brushes, entry[1:])
            continue
        if not brushed and RAIL.get(name) in RETOUCH_RAILS:
            before_brushes, brushed = out, True
        out = APPLIERS[name](out, entry[1:])
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
