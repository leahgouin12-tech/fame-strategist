"""The lens: everything a camera does on the way to the sensor, plus the damage people add
afterwards - tilt-shift, motion and radial blur, prism fringing, bokeh, Orton, a light leak
through a cracked case, glitch, fisheye.

Classical Pillow only. Nothing here invents a pixel: every op is a blur, a scale, a gradient
or a remap of what the file already recorded, so an argument list that arrives short, empty
or full of words lands on the no-op default and leaves the frame alone.

SHAPE, CLAMP, LIMITS and DEFAULTS below are the recipe contract shared with the registry and
the studio page, exactly as effects.py declares it: a flat list of numbers per entry,
positions as fractions of the frame as it stands, sizes as fractions of the short edge.
"""

import math
import random

from PIL import Image, ImageChops, ImageFile, ImageFilter

ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_EDGE = 6000
FIELD_EDGE = 176       # gradients are solved on this grid and stretched, never per pixel
STREAK_EDGE = 640      # a pure-blur pass is solved on this long edge and stretched back
TILT_SPREAD = 0.035    # tilt-shift blur radius as a share of the short edge at strength 1
MOTION_STEP = 4.0      # px between the taps a motion streak is sampled at
ZOOM_STEP = 0.02       # how far apart the taps of a zoom streak are, as a share of the frame
ZOOM_SPREAD = 0.5      # how far the outermost radial copy reaches past the frame
PRISM_SPREAD = 0.05    # band scale difference at amount 1
ORTON_SPREAD = 0.075   # Orton blur radius as a share of the short edge at softness 1
BOKEH_STREAK = 0.8     # anamorphic reach of a bokeh highlight, as a share of its radius
GLITCH_SLICES = 18     # horizontal bands at slices 1
GLITCH_REACH = 0.16    # how far a slice can jump, as a share of the width
SHIFT_REACH = 0.03     # channel offset at shift 1, as a share of the short edge
FISH_CELL = 20.0       # mesh cell size for the radial remap, in pixels

# Each op's argument list at its own no-op, so a hand-edited recipe does nothing rather
# than guessing.
DEFAULTS = {
    "tiltshift": [0.5, 0.22, 0.0, 0.0],
    "motion_blur": [0.0, 0.0],
    "radial_blur": [0.5, 0.5, 0.0, 0.4],
    "prism": [0.0, 0.5, 0.5],
    "bokeh": [0.7, 0.0, 0.05, 0.0],
    "orton": [0.0, 0.4],
    "lightleak": [0.0, 1.0, 0.58, 0.32, 0.0],
    "glitch": [0.0, 0.4, 0.0, 0.0],
    "fisheye": [0.0, 0.5, 0.5],
}

SHAPE = {name: ["list", ["f"] * len(vals)] for name, vals in DEFAULTS.items()}

CLAMP = {
    "tiltshift": [(0.0, 1.0), (0.02, 0.5), (0.0, 1.0), (-45.0, 45.0)],
    "motion_blur": [(0.0, 180.0), (0.0, 0.2)],
    "radial_blur": [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
    "prism": [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
    "bokeh": [(0.0, 1.0), (0.0, 1.0), (0.01, 0.15), (0.0, 360.0)],
    "orton": [(0.0, 1.0), (0.0, 1.0)],
    "lightleak": [(0.0, 360.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
    "glitch": [(0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
    "fisheye": [(-1.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
}

LIMITS = {name: 1 for name in DEFAULTS}


def _byte(v: float) -> int:
    return int(round(min(255.0, max(0.0, v))))


def _smooth(u: float) -> float:
    """0 below, 1 above, and flat at both ends so a ramp never shows a knee."""
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _one(v, default, span):
    if not _number(v):
        v = default
    return min(max(float(v), span[0]), span[1])


def _vals(args, name: str) -> list:
    args = list(args or [])
    defaults, span = DEFAULTS[name], CLAMP[name]
    out = []
    for i, _kind in enumerate(SHAPE[name][1]):
        out.append(_one(args[i] if i < len(args) else None, defaults[i], span[i]))
    return out


def _field(size, fn):
    """An L gradient solved on at most FIELD_EDGE cells and stretched to the frame. Every
    op here needs a smooth ramp across a thousand pixels; solving it per pixel in Python is
    what makes these filters slow, and the ramp is band-limited anyway."""
    w, h = size
    if w >= h:
        gw = min(w, FIELD_EDGE)
        gh = max(2, min(h, int(round(gw * h / max(1, w)))))
    else:
        gh = min(h, FIELD_EDGE)
        gw = max(2, min(w, int(round(gh * w / max(1, h)))))
    px = bytearray(gw * gh)
    for j in range(gh):
        v = (j + 0.5) / gh * h
        top = j * gw
        for i in range(gw):
            px[top + i] = _byte(255.0 * fn((i + 0.5) / gw * w, v))
    small = Image.frombytes("L", (gw, gh), bytes(px))
    return small if (gw, gh) == (w, h) else small.resize((w, h), Image.BILINEAR)


def _fold(taps):
    """Pairwise average of an even list of same-size copies, halving the count each level."""
    while len(taps) > 1:
        taps = [ImageChops.add(taps[i], taps[i + 1], scale=2.0)
                for i in range(0, len(taps) - 1, 2)]
    return taps[0]


def _mean(taps):
    """The average of a few copies in one pass per copy: (a + b) / 2 cannot clip, and the
    odd one out is folded in at its own weight."""
    if len(taps) < 2:
        return taps[0]
    tail = taps[-1] if len(taps) % 2 else None
    out = _fold(taps[:-1] if tail is not None else taps)
    return out if tail is None else Image.blend(out, tail, 1.0 / len(taps))


def _mirror_pad(im, px, py):
    """The frame with a mirrored skirt, so an offset copy samples its own edge instead of
    the other side of the picture. Returns (image, skirt width, skirt height)."""
    w, h = im.size
    px, py = min(max(px, 0), w - 1), min(max(py, 0), h - 1)
    if not px and not py:
        return im, 0, 0
    out = Image.new(im.mode, (w + 2 * px, h + 2 * py))
    out.paste(im, (px, py))
    if px:
        out.paste(im.crop((0, 0, px, h)).transpose(Image.FLIP_LEFT_RIGHT), (0, py))
        out.paste(im.crop((w - px, 0, w, h)).transpose(Image.FLIP_LEFT_RIGHT), (px + w, py))
    if py:
        out.paste(im.crop((0, 0, w, py)).transpose(Image.FLIP_TOP_BOTTOM), (px, 0))
        out.paste(im.crop((0, h - py, w, h)).transpose(Image.FLIP_TOP_BOTTOM), (px, py + h))
    if px and py:
        for src, dst in (((0, 0), (0, 0)), ((w - px, 0), (px + w, 0)),
                         ((0, h - py), (0, py + h)), ((w - px, h - py), (px + w, py + h))):
            corner = (src[0], src[1], src[0] + px, src[1] + py)
            flip = im.crop(corner).transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM)
            out.paste(flip, dst)
    return out, px, py


def _shift_copy(im, dx, dy):
    """A copy of the frame read through a mirror skirt at an integer offset."""
    w, h = im.size
    pad, px, py = _mirror_pad(im, abs(dx) + 1, abs(dy) + 1)
    return pad.crop((px + dx, py + dy, px + dx + w, py + dy + h))


def _soft_work(im):
    """The frame at the size a purely soft pass is solved at, and the size it goes back to.
    A zoom streak and a bokeh ball carry no detail the eye can resolve - they are blur by
    definition - so solving them on a 640 px plate and stretching the result costs a quarter
    of the passes and looks the same. Everything sharp in the frame is composited from the
    original, never from this."""
    w, h = im.size
    if max(w, h) <= STREAK_EDGE:
        return im, (w, h)
    scale = STREAK_EDGE / max(w, h)
    return im.resize((max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                     Image.BILINEAR), (w, h)


def _tiltshift(im, args):
    """One band stays in focus and the frame falls away above and below it, on a line the
    operator can tilt."""
    y, band, strength, angle = args
    if strength <= 0.0:
        return im
    w, h = im.size
    radius = max(0.6, strength * TILT_SPREAD * min(w, h))
    soft = im.filter(ImageFilter.GaussianBlur(radius))
    cy, half = y * h, 0.5 * band * h
    feather = max(2.0, half)
    ang = math.radians(angle)
    nx, ny = -math.sin(ang), math.cos(ang)

    def sharp(px, py):
        return 1.0 - _smooth((abs((px - w / 2.0) * nx + (py - cy) * ny) - half) / feather)

    return Image.composite(im, soft, _field((w, h), sharp))


def _motion_blur(im, args):
    """A streak along one direction: the frame averaged against copies of itself marched
    along that line. The copies fold two at a time, so a hundred and twenty eight taps of
    streak cost seven passes - which is the only reason a long one is affordable here."""
    angle, length = args
    w, h = im.size
    reach = length * min(w, h)
    if reach < 1.0:
        return im
    ang = math.radians(angle)
    dx, dy = reach * math.cos(ang), reach * math.sin(ang)
    stages = max(1, int(math.ceil(math.log2(max(2.0, 2.0 * reach / MOTION_STEP)))))
    out = _shift_copy(im, int(round(-dx)), int(round(-dy)))
    for k in range(stages):
        divisor = 2.0 ** (stages - k)
        out = ImageChops.add(out, _shift_copy(out, int(round(2.0 * dx / divisor)),
                                              int(round(2.0 * dy / divisor))), scale=2.0)
    return out


def _radial_blur(im, args):
    """A zoom streak: the frame averaged against copies of itself grown about one anchor,
    so the drag runs outward from wherever the point is. The copies fold by doubling, so
    thirty two taps of streak cost five resizes."""
    x, y, amount, falloff = args
    if amount <= 0.0:
        return im
    w, h = im.size
    ax, ay = x * w, y * h
    ratio = 1.0 + ZOOM_SPREAD * amount
    stages = max(1, int(math.ceil(math.log2(1.0 + ZOOM_SPREAD * amount / ZOOM_STEP))))
    taps = 2.0 ** stages
    work, back = _soft_work(im)
    streak = work
    for k in range(stages):
        streak = ImageChops.add(streak, _zoom(streak, ratio ** (2.0 ** k / taps), x, y),
                                scale=2.0)
    if back != work.size:
        streak = streak.resize(back, Image.BILINEAR)
    short = min(w, h)
    core, span = falloff * 0.5 * short, max(2.0, 0.35 * short)

    def far(px, py):
        return _smooth((math.hypot(px - ax, py - ay) - core) / span)

    return Image.composite(streak, im, _field((w, h), far))


def _zoom(img, factor, u, v):
    """The frame grown about the anchor (u, v, as fractions) and read back at its own size,
    so the anchor is the one point that never moves. Only factors of 1 or more are used
    here: growing a frame always reads pixels the file has, shrinking it would have to
    invent some."""
    w, h = img.size
    if abs(factor - 1.0) < 1e-4:
        return img
    ax, ay = u * w, v * h
    k = 1.0 / factor
    return img.transform((w, h), Image.AFFINE, (k, 0, ax - k * ax, 0, k, ay - k * ay),
                         Image.BILINEAR)


def _zoom_band(band, factor, u, v):
    """One channel of that, which is what a prism does to light."""
    return _zoom(band, factor, u, v)


def _prism(im, args):
    """Chromatic aberration: the three channels are magnified by three slightly different
    factors about one point, so colour splits along the edges and stays whole in the flat.
    All three grow, never shrink - a shrunk channel would have to read pixels the file
    never recorded."""
    amount, x, y = args
    if amount <= 0.0:
        return im
    spread = PRISM_SPREAD * amount
    r, g, b = im.split()
    return Image.merge("RGB", (_zoom_band(r, 1.0 + 2.0 * spread, x, y),
                               _zoom_band(g, 1.0 + spread, x, y),
                               b))


def _bokeh(im, args):
    """Points of light above a threshold are lifted, blurred into discs stretched along the
    operator's angle, and laid back in screen mode. Below the threshold nothing is lifted,
    so the shadows keep the pixels they came in with."""
    threshold, bloom, size, angle = args
    if bloom <= 0.0:
        return im
    w, h = im.size
    cut = int(round(threshold * 255))
    shoulder = max(1, 255 - cut)
    lut = [0 if v <= cut else _byte(255.0 * _smooth((v - cut) / float(shoulder)))
           for v in range(256)]
    mask = im.convert("L").point(lut)
    highlights = Image.composite(im, Image.new("RGB", (w, h), (0, 0, 0)), mask)
    work, back = _soft_work(highlights)
    radius = max(0.8, 0.5 * size * min(work.size))
    glow = work.filter(ImageFilter.GaussianBlur(radius))
    reach = BOKEH_STREAK * radius
    ang = math.radians(angle)
    taps = []
    for i in range(4):
        t = (i - 1.5) / 1.5
        taps.append(_shift_copy(glow, int(round(reach * math.cos(ang) * t)),
                                int(round(-reach * math.sin(ang) * t))))
    glow = _mean(taps)
    if glow.size != back:
        glow = glow.resize(back, Image.BILINEAR)
    return Image.blend(im, ImageChops.screen(im, glow), min(1.0, bloom))


def _orton(im, args):
    """The Orton plate: the frame screened against a soft copy of itself. Light spills into
    light and density goes out of the shadows; a true black stays a true black."""
    amount, softness = args
    if amount <= 0.0:
        return im
    radius = max(1.0, (0.012 + ORTON_SPREAD * softness) * min(im.size))
    glow = ImageChops.screen(im, im.filter(ImageFilter.GaussianBlur(radius)))
    return Image.blend(im, glow, min(1.0, amount))


def _lightleak(im, args):
    """A leak in from one edge, at an angle, in the colour she chose, screen-blended so it
    only ever adds. The far side of the frame is exactly zero and stays exactly itself.
    The colour arrives in the 0..1 scale the picker folds a hex into."""
    angle, r, g, b, amount = args
    if amount <= 0.0:
        return im
    w, h = im.size
    ox, oy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    cx, cy = w / 2.0, h / 2.0
    reach = max(1.0, abs(ox) * w / 2.0 + abs(oy) * h / 2.0)

    def leak(px, py):
        t = ((px - cx) * ox + (py - cy) * oy) / reach
        return _smooth((t + 0.3) / 1.3) ** 1.4

    veil = ImageChops.multiply(Image.new("RGB", (w, h),
                                         tuple(_byte(v * 255) for v in (r, g, b))),
                               _field((w, h), leak).convert("RGB"))
    return Image.blend(im, ImageChops.screen(im, veil), min(1.0, amount))


def _glitch(im, args):
    """Digital damage, and the same damage every time: the seed picks the slices, so two
    runs of one recipe export two identical files."""
    amount, slices, shift, seed = args
    if amount <= 0.0 and shift <= 0.0:
        return im
    w, h = im.size
    rnd = random.Random(int(round(seed * 1_000_000)) & 0x7FFFFFFF)
    out = im
    count = int(round(slices * GLITCH_SLICES))
    if count and amount > 0.0:
        out = im.copy()
        for _ in range(count):
            tall = max(2, int(round(h * (0.008 + 0.075 * rnd.random()))))
            tall = min(tall, h)
            top = int(rnd.random() * (h - tall + 1))
            jump = int(round(amount * GLITCH_REACH * w * (2.0 * rnd.random() - 1.0)))
            if not jump:
                continue
            strip = ImageChops.offset(im, jump, 0).crop((0, top, w, top + tall))
            out.paste(strip, (0, top))
    offset = int(round(shift * SHIFT_REACH * min(w, h)))
    if offset:
        r, g, b = out.split()
        out = Image.merge("RGB", (ImageChops.offset(r, offset, 0), g,
                                  ImageChops.offset(b, -offset, 0)))
    lines = max(0.0, amount - 0.5) * 0.44
    if lines > 0.0:
        # every third row comes down a little: three bytes per pixel-column, built as one
        # buffer rather than walked, which is the difference between a filter and a slideshow
        dim = _byte(255.0 * (1.0 - lines))
        strip = (bytes((255,)) * w + bytes((255,)) * w + bytes((dim,)) * w)
        comb = Image.frombytes("L", (w, 3 * (h // 3 + 1)), strip * (h // 3 + 1))
        out = ImageChops.multiply(out, comb.crop((0, 0, w, h)).convert("RGB"))
    return out


def _fisheye(im, args):
    """A radial remap: positive bulges the centre out at the cost of the rim, negative
    sucks it in. The corners are pinned, since the frame has to end where it started."""
    amount, x, y = args
    if abs(amount) < 1e-4:
        return im
    w, h = im.size
    ax, ay = x * w, y * h
    reach = max(math.hypot(ax, ay), math.hypot(w - ax, ay),
                math.hypot(ax, h - ay), math.hypot(w - ax, h - ay)) or 1.0
    nx = max(2, min(64, int(math.ceil(w / FISH_CELL))))
    ny = max(2, min(64, int(math.ceil(h / FISH_CELL))))
    xs = [min(w, int(round(i * w / nx))) for i in range(nx + 1)]
    ys = [min(h, int(round(j * h / ny))) for j in range(ny + 1)]
    xs[-1], ys[-1] = w, h

    def mapped(px, py):
        dx, dy = px - ax, py - ay
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return px, py
        q = min(1.0, dist / reach)
        scale = 1.0 - amount * (1.0 - q * q)
        return (min(max(ax + dx * scale, 0.0), w - 1.0),
                min(max(ay + dy * scale, 0.0), h - 1.0))

    pts = [[(*xy, *mapped(*xy)) for xy in ((xs[i], ys[j]) for i in range(nx + 1))]
           for j in range(ny + 1)]
    mesh = []
    for j in range(ny):
        for i in range(nx):
            nw, ne = pts[j][i], pts[j][i + 1]
            sw, se = pts[j + 1][i], pts[j + 1][i + 1]
            if se[0] <= nw[0] or se[1] <= nw[1]:
                continue
            mesh.append(((nw[0], nw[1], se[0], se[1]),
                         (nw[2], nw[3], sw[2], sw[3], se[2], se[3], ne[2], ne[3])))
    if not mesh:
        return im
    return im.transform((w, h), Image.MESH, mesh, Image.BILINEAR)


def _guarded(name, fn):
    """Ops work on RGB. Any alpha the frame already had goes round trip with it, so an
    optic can sit after a cutout in the same recipe and still leave it transparent."""

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
    "tiltshift": _guarded("tiltshift", _tiltshift),
    "motion_blur": _guarded("motion_blur", _motion_blur),
    "radial_blur": _guarded("radial_blur", _radial_blur),
    "prism": _guarded("prism", _prism),
    "bokeh": _guarded("bokeh", _bokeh),
    "orton": _guarded("orton", _orton),
    "lightleak": _guarded("lightleak", _lightleak),
    "glitch": _guarded("glitch", _glitch),
    "fisheye": _guarded("fisheye", _fisheye),
}


def _bounded(im):
    if max(im.size) <= MAX_EDGE:
        return im
    scale = MAX_EDGE / max(im.size)
    return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BOX)


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
