"""The pixel-maths effects layer - what a phone app does with a slider, done on her own file.

Auto tone, keystone, the stretch below a line, background cutout, colour splash, duotone,
mosaic brush, light leak, honest enlargement, portrait bloom. Every one of them is
arithmetic on the pixels the camera already recorded: none of them rebuilds a person or
invents detail that was never there, and the ones that cannot deliver what they promise
say so where the code is.

The recipe contract is shared with the tone and brush engines: a recipe is a list of
[name, arg, ...] entries, positions are fractions of the frame as it stands after earlier
geometry, and size is a fraction of the shorter edge. SHAPE, CLAMP and LIMITS describe
what each op takes; an op only ever sees numbers it can trust.
"""

import colorsys
import math

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFile, ImageFilter, ImageMath

ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_EDGE = 6000
MAX_UPSCALE_EDGE = 4000
WORK_EDGE = 128
FULL_SPREAD = 0.97
CUT_PERCENTILE = 0.005
MIRROR_FOLDS = 8        # the most panels one mirror fold can cut the frame into

# Each op's argument list at its own no-op: an entry that arrives short, or with a word
# where a number belongs, lands here and therefore does nothing rather than guessing.
DEFAULTS = {
    "auto": [0.0],
    "perspective": [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
    "stretch": [0.5, 0.0, 0.2],
    "cutout": [0.0, 0.2, 0.0, 0.0],
    "splash": [0.0, 0.0, 1.0, 0.0],
    "duotone": [0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0],
    "pixelate": [0.5, 0.5, 0.0, 0.0],
    "rays": [0.5, 0.0, 0.6, 0.0],
    "upscale": [1.0],
    "softfocus": [0.0, 0.0],
    "mirror": [0.0, 1.0, 0.0],
}

SHAPE = {
    "auto": ["list", ["f"]],
    "perspective": ["list", ["f"] * 8],
    "stretch": ["list", ["f"] * 3],
    "cutout": ["list", ["f"] * 4],
    "splash": ["list", ["f"] * 4],
    "duotone": ["list", ["f"] * 7],
    "pixelate": ["group", 4, 16],
    "rays": ["list", ["f"] * 4],
    "upscale": ["list", ["f"]],
    "softfocus": ["list", ["f"] * 2],
    "mirror": ["list", ["f"] * 3],
}

CLAMP = {
    "auto": [(0.0, 1.0)],
    "perspective": [(-0.4, 1.4)] * 8,
    "stretch": [(0.0, 1.0), (-0.75, 0.75), (0.02, 1.0)],
    "cutout": [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 360.0)],
    "splash": [(0.0, 360.0), (0.0, 180.0), (0.0, 1.0), (0.0, 1.0)],
    "duotone": [(0.0, 1.0)] * 7,
    "pixelate": [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 0.45)],
    "rays": [(0.0, 1.0), (0.0, 1.0), (0.05, 1.4), (0.0, 1.0)],
    "upscale": [(1.0, 4.0)],
    "softfocus": [(0.0, 1.0), (0.0, 1.0)],
    "mirror": [(0.0, 2.0), (1.0, float(MIRROR_FOLDS)), (0.0, 0.5)],
}

LIMITS = {
    "auto": 1,
    "perspective": 1,
    "stretch": 3,
    "cutout": 1,
    "splash": 1,
    "duotone": 2,
    "pixelate": 8,
    "rays": 6,
    "upscale": 1,
    "softfocus": 1,
    "mirror": 1,
}


def _byte(v: float) -> int:
    return int(round(min(255.0, max(0.0, v))))


def _curve(im, fn):
    return im.point([_byte(fn(i)) for i in range(256)] * 3)


def _smooth(u: float) -> float:
    """0 below, 1 above, and flat at both ends so a ramp never shows a knee."""
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _number(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


def _one(v, default, span):
    """A value that is not a finite number keeps its default, which is always the no-op
    for that position - that is what keeps a hand-edited recipe from raising."""
    if not _number(v):
        v = default
    return min(max(float(v), span[0]), span[1])


def _vals(args, name: str) -> list:
    args = list(args or [])
    defaults = DEFAULTS[name]
    shape = SHAPE[name]
    span = CLAMP[name]
    if shape[0] == "group":
        k, n = shape[1], shape[2]
        out = []
        for g in range(min(n, len(args) // k)):
            for p in range(k):
                out.append(_one(args[g * k + p], defaults[p], span[p]))
        return out
    out = []
    for i, kind in enumerate(shape[1]):
        v = args[i] if i < len(args) else None
        if kind == "s":
            out.append(v if isinstance(v, str) else defaults[i])
        else:
            out.append(_one(v, defaults[i], span[i]))
    return out


def _dab(size, cx, cy, radius, core=0.0):
    """1 out to `core` of the radius and feathered to 0 at the rim, built at 64x64 and
    stretched, so a brush dab costs the same whatever the frame is."""
    n = 64
    core = min(0.95, max(0.0, core))
    w, h = size
    if w < 2 or h < 2:
        return Image.new("L", size, 0)
    px = bytearray(n * n)
    for j in range(n):
        y = j / (n - 1) * h - cy
        for i in range(n):
            x = i / (n - 1) * w - cx
            d = math.hypot(x, y) / radius
            px[j * n + i] = _byte(255 if d <= core else 255 * (1.0 - _smooth((d - core) / (1.0 - core))))
    return Image.frombytes("L", (n, n), bytes(px)).resize(size, Image.BILINEAR)


def _ring(im):
    """The median colour of the outermost ring of pixels - what a backdrop calls background."""
    w, h = im.size
    raw = (im.crop((0, 0, w, 1)).tobytes() + im.crop((0, h - 1, w, h)).tobytes()
           + im.crop((0, 0, 1, h)).tobytes() + im.crop((w - 1, 0, w, h)).tobytes())
    vals = list(raw)
    return tuple(sorted(vals[i::3])[len(vals) // 6] for i in range(3))


def _bounded(im):
    if max(im.size) <= MAX_EDGE:
        return im
    scale = MAX_EDGE / max(im.size)
    return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BOX)


def _auto(im, args):
    grey = im.convert("L")
    hist = grey.histogram()
    total = sum(hist) or 1
    need = total * CUT_PERCENTILE
    lo = hi = 0
    run = 0
    for v, count in enumerate(hist):
        run += count
        if run >= need:
            lo = v
            break
    run = 0
    for v in range(255, -1, -1):
        run += hist[v]
        if run >= need:
            hi = v
            break
    if hi - lo >= FULL_SPREAD * 255:
        return im  # the frame already uses the whole ramp, so there is nothing to widen
    if hi - lo < 2:
        return im  # one flat tone has no range to stretch: leveling it would only invent one
    amount = args[0]
    gain = 255.0 / max(1.0, hi - lo)
    out = im.point([_byte(v + amount * (min(255.0, max(0.0, (v - lo) * gain)) - v))
                    for v in range(256)] * 3)
    lift = amount * (1.0 - (hi - lo) / 255.0)
    out = ImageEnhance.Contrast(out).enhance(1 + 0.45 * lift)
    return ImageEnhance.Color(out).enhance(1 + 0.5 * lift)


def _perspective(im, args):
    if all(abs(args[i] - DEFAULTS["perspective"][i]) < 1e-4 for i in range(8)):
        return im
    w, h = im.size
    pts = [(args[i] * w, args[i + 1] * h) for i in range(0, 8, 2)]
    # Pillow wants the source corners as top-left, bottom-left, bottom-right, top-right;
    # the recipe gives them in reading order around the frame.
    quad = (*pts[0], *pts[3], *pts[2], *pts[1])
    return im.transform((w, h), Image.QUAD, quad, Image.BICUBIC)


def _stretch(im, args):
    """Scale everything below one horizontal line away from it - the legs and torso tool.

    A mesh over the full width, with a vertex on the line itself, so the rows above it are
    read from exactly the pixels they already were.
    """
    y, amount, feather = args
    w, h = im.size
    if abs(amount) < 0.004:
        return im
    line = int(round(min(max(y, 0.0), 1.0) * (h - 1)))
    band = max(2, int(round(feather * min(w, h))))
    step = max(1, h // 72)
    ys = sorted(set(range(0, h + 1, step)) | {line, min(h, line + band), h})

    def source(v):
        if v <= line:
            return float(v)
        ramp = _smooth((v - line) / band)
        return min(float(h - 1), max(0.0, line + (v - line) / (1.0 + amount * ramp)))

    cells = []
    for j in range(len(ys) - 1):
        top, bottom = int(ys[j]), int(ys[j + 1])
        if bottom <= top:
            continue
        sy0, sy1 = source(top), source(bottom)
        cells.append(((0, top, w, bottom), (0.0, sy0, 0.0, sy1, float(w), sy1, float(w), sy0)))
    return im.transform((w, h), Image.MESH, cells, Image.BILINEAR)


def _fold(base: Image.Image, n: int, seam: float) -> Image.Image:
    """One vertical strip of the frame, then the same strip read backwards, tiled across."""
    wide, tall = base.size
    pw = max(1, wide // n)
    strip = base.crop((0, 0, pw, tall))
    back = strip.transpose(Image.FLIP_LEFT_RIGHT)
    out = Image.new(base.mode, (pw * n, tall))
    for i in range(n):
        out.paste(back if i % 2 else strip, (i * pw, 0))
    if out.width != wide:
        out = out.resize((wide, tall), Image.LANCZOS)
    if seam <= 0.0 or n < 2:
        return out
    band = max(1, int(seam * pw * 0.55))
    mask = Image.new("L", out.size, 0)
    draw = ImageDraw.Draw(mask)
    for i in range(1, n):
        x = int(i * out.width / n)
        draw.rectangle([x - band, 0, x + band, out.height], fill=255)
    soft = out.filter(ImageFilter.GaussianBlur(max(1.0, band / 2.0)))
    return Image.composite(soft, out, mask.filter(ImageFilter.GaussianBlur(band / 2.0)))


def _mirror(im, args):
    """The frame folded over itself: a strip of her own photo repeated in mirrored panels,
    down vertical seams, horizontal seams or the diagonal. Every panel is real pixels from
    the same strip - nothing here is generated."""
    axis, folds, seam = args
    n = int(round(min(float(MIRROR_FOLDS), max(1.0, folds))))
    if n <= 1:
        return im
    base = im if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    if axis >= 1.5:
        return _fold(base.transpose(Image.TRANSPOSE), n, seam).transpose(Image.TRANSPOSE)
    if axis >= 0.5:
        return _fold(base.transpose(Image.ROTATE_90), n, seam).transpose(Image.ROTATE_270)
    return _fold(base, n, seam)


def _cutout(im, args):
    # note: this is colour proximity grown from the four edges, not a trained mask. It is
    # clean on an even-lit wall or a studio backdrop and eats a subject on a busy street.
    tolerance, feather, fill, hue = args
    if tolerance <= 0.0:
        return im
    w, h = im.size
    scale = WORK_EDGE / max(w, h)
    sw, sh = max(8, int(w * scale)), max(8, int(h * scale))
    small = im.resize((sw, sh), Image.BOX)
    base = _ring(small)
    r, g, b = small.split()
    limit = _byte(24 + 231 * tolerance)
    dist = ImageMath.lambda_eval(
        lambda a: a["convert"](a["max"](a["max"](abs(a["r"] - base[0]), abs(a["g"] - base[1])),
                                        abs(a["b"] - base[2])), "L"), r=r, g=g, b=b)
    close = dist.point([255 if v <= limit else 0 for v in range(256)])
    ring = Image.new("L", (sw, sh), 0)
    for strip in ((0, 0, sw, 1), (0, sh - 1, sw, sh), (0, 0, 1, sh), (sw - 1, 0, sw, sh)):
        ring.paste(Image.new("L", (strip[2] - strip[0], strip[3] - strip[1]), 255), strip)
    filled = ImageChops.darker(close, ring)
    for _ in range(2 * (sw + sh)):
        grown = ImageChops.multiply(filled.filter(ImageFilter.MaxFilter(3)), close)
        if grown.tobytes() == filled.tobytes():
            break
        filled = grown
    alpha = ImageChops.invert(filled.resize((w, h), Image.BILINEAR))
    radius = feather * min(w, h) * 0.04
    if radius >= 0.5:
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius))
    if fill < 0.5:
        out = im.convert("RGB")
        out.putalpha(alpha)
        return out
    colour = base
    if hue > 0.0:
        # a hue she picked, at the backdrop's own saturation and brightness.
        _, sat, val = colorsys.rgb_to_hsv(*[c / 255.0 for c in base])
        colour = tuple(_byte(c * 255) for c in colorsys.hsv_to_rgb(hue / 360.0, sat, val))
    return Image.composite(im, Image.new("RGB", (w, h), colour), alpha)


def _splash(im, args):
    hue, band, keep, amount = args
    if amount <= 0.0 and keep >= 1.0:
        return im
    hsv = im.convert("HSV")
    h, s, v = hsv.split()
    target = hue * 255.0 / 360.0
    width = band * 255.0 / 360.0
    feather = max(3.0, 0.3 * width)
    lut = []
    for i in range(256):
        d = abs(i - target)
        d = min(d, 256 - d)
        inside = 1.0 if d <= width else max(0.0, 1.0 - (d - width) / feather)
        lut.append(_byte(255 * (keep * inside + (1.0 - amount) * (1.0 - inside))))
    return Image.merge("HSV", (h, ImageChops.multiply(s, h.point(lut)), v)).convert("RGB")


def _duotone(im, args):
    """The two endpoints arrive in the 0..1 scale the picker folds a hex into, so they are
    widened to bytes here rather than being read as bytes by the caller."""
    r1, g1, b1, r2, g2, b2, amount = args
    if amount <= 0.0:
        return im
    grey = im.convert("L")
    duo = Image.merge("RGB", [grey.point([_byte((a + (b - a) * i / 255.0) * 255) for i in range(256)])
                              for a, b in ((r1, r2), (g1, g2), (b1, b2))])
    return duo if amount >= 1.0 else Image.blend(im, duo, amount)


def _pixelate(im, args):
    if not args:
        return im
    w, h = im.size
    out = None
    for i in range(0, len(args) - 3, 4):
        x, y, size, block = args[i:i + 4]
        if size <= 0.0 or block <= 0.0:
            continue
        radius = size * min(w, h)
        cx, cy = x * w, y * h
        box = (max(0, int(cx - radius)), max(0, int(cy - radius)),
               min(w, int(math.ceil(cx + radius))), min(h, int(math.ceil(cy + radius))))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        region = im.crop(box)
        cell = max(2.0, block * radius)
        down = (max(1, int(round(region.width / cell))), max(1, int(round(region.height / cell))))
        mosaic = region.resize(down, Image.BOX).resize(region.size, Image.NEAREST)
        mask = _dab(region.size, cx - box[0], cy - box[1], radius, core=0.72)
        out = im.copy() if out is None else out
        out.paste(Image.composite(mosaic, region, mask), box)
    return im if out is None else out


def _rays(im, args):
    x, y, size, amount = args
    if amount <= 0.0:
        return im
    w, h = im.size
    glow = _dab((w, h), x * w, y * h, max(1.0, size * min(w, h)))
    # warm on purpose: a leak that is neutral grey reads as a smudge, not as sunlight.
    leak = ImageChops.multiply(Image.new("RGB", (w, h), (255, 224, 186)), glow.convert("RGB"))
    return Image.blend(im, ImageChops.screen(im, leak), min(1.0, amount))


def _upscale(im, args):
    # enlargement, not super-resolution: what is added is pixels, not detail the lens missed.
    w, h = im.size
    factor = min(args[0], MAX_UPSCALE_EDGE / w, MAX_UPSCALE_EDGE / h)
    if factor <= 1.001:
        return im
    # The denoise and the unsharp run on the frame she already has, because at 4x they
    # would otherwise cost more than the resize does - the sharpening scales with the factor
    # to survive the Lanczos that follows it.
    soft = im.filter(ImageFilter.BoxBlur(1))
    detail = ImageChops.difference(im, soft).convert("L")
    keep = detail.point([min(255, max(0, (v - 1) * 30)) for v in range(256)])
    clean = Image.composite(im, soft, keep)
    clean = clean.filter(ImageFilter.UnsharpMask(radius=1.6, percent=int(50 + 45 * factor),
                                                 threshold=3))
    return clean.resize((max(1, int(round(w * factor))), max(1, int(round(h * factor)))),
                        Image.LANCZOS)


def _softfocus(im, args):
    amount, glow = args
    if amount <= 0.0:
        return im
    # glow decides how far down the tonal range the bloom starts; amount decides how far
    # it spreads and how much of it is laid back over the frame.
    floor = 232.0 - 130.0 * glow
    span = max(1.0, 255.0 - floor)
    bright = _curve(im, lambda v: (v - floor) * 255.0 / span)
    lit = ImageChops.screen(im, bright.filter(ImageFilter.GaussianBlur(2.0 + 26.0 * amount)))
    return Image.blend(im, lit, min(1.0, amount))


def _guarded(name, fn):
    """Ops work on RGB. Any alpha the frame already had is put back afterwards, so an
    effect can sit after a cutout in the same recipe and still leave it transparent."""

    def run(im, args):
        alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
        base = im if im.mode == "RGB" and alpha is None else im.convert("RGB")
        out = fn(base, _vals(args, name))
        if alpha is None:
            return out
        if alpha.size != out.size:
            alpha = alpha.resize(out.size, Image.LANCZOS)
        rgba = out.convert("RGB")
        rgba.putalpha(alpha)
        return rgba

    return run


APPLIERS = {
    "auto": _guarded("auto", _auto),
    "perspective": _guarded("perspective", _perspective),
    "stretch": _guarded("stretch", _stretch),
    "cutout": _guarded("cutout", _cutout),
    "splash": _guarded("splash", _splash),
    "duotone": _guarded("duotone", _duotone),
    "mirror": _guarded("mirror", _mirror),
    "pixelate": _guarded("pixelate", _pixelate),
    "rays": _guarded("rays", _rays),
    "upscale": _guarded("upscale", _upscale),
    "softfocus": _guarded("softfocus", _softfocus),
}


def apply(im: Image.Image, recipe) -> Image.Image:
    """Run a recipe in the order it arrives, one entry per op up to its LIMITS."""
    out, used = im, {}
    for entry in recipe or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        name = str(entry[0])
        if name not in APPLIERS:
            continue
        used[name] = used.get(name, 0) + 1
        if used[name] > LIMITS[name]:
            continue
        out = _bounded(APPLIERS[name](out, list(entry[1:])))
    return out
