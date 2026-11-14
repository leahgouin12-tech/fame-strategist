"""Repair: fix what is in the frame using only what is already in the frame.

Five brush tools (patch, conceal, red_eye, dewy, flyaway) and two whole-frame tools
(tan, skin_tone). The brushes take the same slots retouch.py takes: position 0 and 1
are the point she tapped, position 2 is the brush diameter as a fraction of the short
edge, and every one of them works inside that disc's bounding box, so a pixel outside
it comes back byte-identical. patch is the honest version of a clone brush: it moves
real pixels from an offset she sets with two sliders and matches their brightness
spread to the ring around the destination. Nothing here is a model - no face is
located, no background is invented - and the two frame tools select by a colour window
in YCbCr, which also catches a wall, a sleeve or a table of the same colour. That is
what their notes say.

The recipe contract is the one the other engines share: an entry is
["name", arg, ...], SHAPE says how the args are grouped, CLAMP gives the legal range of
each slot and LIMITS how many groups a hand-written entry may carry.
"""

import math

from PIL import Image, ImageChops, ImageFilter, ImageMath

FEATHER = 0.45          # share of the radius over which a brush mask fades to nothing
DODGE_GAIN = 0.45       # widest multiplicative swing of the conceal lift at 1.0
BAND = 44.0             # half-width of the narrow dodge band, in luma steps
RING_OUT = 1.9          # tone-match ring outer radius, in patch radii
RING_IN = 1.06          # ... and where it starts, so the pasted disc is never its own reference
GAIN_LO, GAIN_HI = 0.55, 1.85   # how far a tone match may change the source's contrast
SKIN_CR = (141.0, 169.0)        # the colour window, wide setting
SKIN_CB = (95.0, 125.0)
SKIN_Y = 38.0                   # below this nothing is skin, it is shadow

# Per-op, per-position limits inside one group of args. patch: x, y, brush, radius,
# dx, dy, feather, tone match. The sample point is an offset from the tap, in fractions
# of the short edge, so one tap and two sliders is a complete clone request.
CLAMP = {
    "patch": [(0.0, 1.0), (0.0, 1.0), (0.005, 0.40), (0.20, 1.00),
              (-0.50, 0.50), (-0.50, 0.50), (0.05, 1.00), (0.0, 1.00)],
    "conceal": [(0.0, 1.0), (0.0, 1.0), (0.010, 0.30), (0.0, 1.0), (-1.0, 1.0)],
    "red_eye": [(0.0, 1.0), (0.0, 1.0), (0.005, 0.12), (0.0, 1.0)],
    "dewy": [(0.0, 1.0), (0.0, 1.0), (0.010, 0.40), (0.0, 1.0)],
    "flyaway": [(0.0, 1.0), (0.0, 1.0), (0.020, 0.35), (0.0, 1.0)],
    "tan": [(0.0, 1.0), (20.0, 45.0), (0.0, 1.0), (0.0, 1.0)],
    "skin_tone": [(-1.0, 1.0), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0)],
}

# Max stroke groups per op name, so a hand-edited recipe cannot freeze the machine.
# These caps are set by cost, not by patience: each number is the count of the op's
# WIDEST brush that still finishes inside the ~1.5 s the rest of the editor keeps to on
# a 900 px preview (patch measures a source disc and a ring, so eight of them is already
# 1.4 s; flyaway smears two directions, so sixteen; red_eye and dewy are cheap enough to
# allow twelve and twenty). At an everyday brush the same caps cost a fifth of that.
LIMITS = {
    "patch": 8, "conceal": 12, "red_eye": 12, "dewy": 20, "flyaway": 16,
    "tan": 1, "skin_tone": 1,
}

GROUPED = ("patch", "conceal", "red_eye", "dewy", "flyaway")
WHOLE = ("tan", "skin_tone")

# Each frame tool's argument list at its own no-op: a short entry, or a word where a
# number belongs, lands here and therefore does nothing instead of guessing.
DEFAULTS = {
    "tan": [0.0, 33.0, 0.45, 0.35],
    "skin_tone": [0.0, 0.0, 0.0, 0.35],
}

SHAPE = {name: ["group", len(CLAMP[name]), LIMITS[name]] for name in GROUPED}
SHAPE.update({name: ["list", ["f"] * len(CLAMP[name])] for name in WHOLE})


# ---------------------------------------------------------------- shape and plumbing

def _fade(t):
    return t * t * (3.0 - 2.0 * t)


def _lut(fn):
    return [max(0, min(255, int(round(fn(i))))) for i in range(256)]


def _ramp(lo, hi):
    """LUT: 0 below lo, 255 above hi, smooth between."""
    return _lut(lambda v: 255.0 * _fade(max(0.0, min(1.0, (v - lo) / (hi - lo)))))


def _fall(lo, hi):
    """LUT: 255 below lo, 0 above hi, smooth between."""
    return _lut(lambda v: 255.0 * (1.0 - _fade(max(0.0, min(1.0, (v - lo) / (hi - lo))))))


def _band(centre, half):
    """LUT: 255 at centre, 0 outside centre +/- half - the narrow dodge window."""
    return _lut(lambda v: 255.0 * _fade(max(0.0, 1.0 - abs(v - centre) / half)))


def _split(im):
    """The RGB this module works on, and the alpha that has to come back with it."""
    if im.mode == "RGB":
        return im, None
    if im.mode == "RGBA":
        r, g, b, a = im.split()
        return Image.merge("RGB", (r, g, b)), a
    return im.convert("RGB"), None


def _join(rgb, alpha):
    return rgb if alpha is None else Image.merge("RGBA", (*rgb.convert("RGB").split(), alpha))


def _op(fn):
    """Run an RGB op and hand back the mode it was given, untouched at the edges."""
    def wrapped(im, args):
        rgb, alpha = _split(im)
        return _join(fn(rgb, args), alpha)
    return wrapped


def _number(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _strokes(args, name):
    """One op's flat args -> complete clamped groups; junk, extras and tails vanish."""
    rng = CLAMP[name]
    k = len(rng)
    n = len(args or [])
    out = []
    for i in range(0, min(n, k * LIMITS[name]) - k + 1, k):
        vals, ok = [], True
        for j in range(k):
            f = _number(args[i + j])
            if f is None:
                ok = False
                break
            lo, hi = rng[j]
            vals.append(min(max(f, lo), hi))
        if ok:
            out.append(vals)
    return out


def _vals(args, name):
    """A frame tool's args -> its clamped slots, defaults standing in for what is missing."""
    args = list(args or [])
    out = []
    for j, (lo, hi) in enumerate(CLAMP[name]):
        f = _number(args[j]) if j < len(args) else None
        v = DEFAULTS[name][j] if f is None else f
        out.append(min(max(float(v), lo), hi))
    return out


def _disc(stroke, w, h):
    """Centre, radius and crop box of one brush, or None when it is nonsense."""
    r = 0.5 * stroke[2] * min(w, h)
    if r < 2.0:
        return None
    cx, cy = stroke[0] * w, stroke[1] * h
    box = (max(0, int(math.floor(cx - r))), max(0, int(math.floor(cy - r))),
           min(w, int(math.ceil(cx + r))), min(h, int(math.ceil(cy + r))))
    if box[2] - box[0] < 3 or box[3] - box[1] < 3:
        return None
    return box, cx, cy, r


_GRID = 96          # the lattice the brush disc is drawn on, once per process
_UNIT_Q = None      # its normalised radius, byte-quantised at 1/128 of the radius
_UNIT_LUTS = {}     # (feather, amount) -> the point LUT that turns that radius into a weight


def _unit_q():
    """A 96x96 map of q = distance / radius for a centred disc of radius 48, built once.

    Holding the geometry and the falloff apart is what makes a brush cheap: the circle is
    drawn a single time, and every stroke afterwards is a point LUT, a resize and a paste
    - all of them Pillow's own C loops, no Python walking the pixels again.
    """
    global _UNIT_Q
    if _UNIT_Q is None:
        n, c, half = _GRID, (_GRID - 1) / 2.0, _GRID / 2.0
        px = bytearray(n * n)
        for j in range(n):
            dy = j - c
            row = j * n
            for i in range(n):
                px[row + i] = min(255, int(round(128.0 * math.hypot(i - c, dy) / half)))
        _UNIT_Q = Image.frombytes("L", (n, n), bytes(px))
    return _UNIT_Q


def _unit_lut(feather, amount):
    return _lut(lambda q: 255.0 * amount * _fade(max(0.0, min(1.0, (1.0 - q / 128.0) / feather))))


def _mask(bw, bh, cx, cy, r, feather=FEATHER, amount=1.0):
    """Feathered disc as an L image the size of the brush box; None if all zero.

    The weight is exactly 0 from q = 1 outward, which is what lets every op leave
    untouched pixels byte-identical; the centre rounds to the nearest pixel, so the
    disc can sit at most half a pixel off the tap.
    """
    if bw < 1 or bh < 1 or r < 1.0 or amount <= 0.0:
        return None
    key = (round(float(feather), 3), round(float(amount), 3))
    lut = _UNIT_LUTS.get(key)
    if lut is None:
        lut = _UNIT_LUTS[key] = _unit_lut(*key)
    side = max(1, int(round(2.0 * r)))
    disc = _unit_q().point(lut)
    if side != _GRID:
        disc = disc.resize((side, side), Image.BILINEAR)
    mask = Image.new("L", (bw, bh), 0)
    mask.paste(disc, (int(round(cx - r)), int(round(cy - r))))
    return None if mask.getextrema()[1] == 0 else mask


def _hard(mask):
    """The same disc as a yes/no selection, for counting statistics inside it."""
    return mask.point(lambda v: 255 if v > 128 else 0)


_CUT_LUT = [255 if i <= 128 else 0 for i in range(256)]


def _disc_mask(bw, bh, cx, cy, r):
    """The brush as a yes/no disc, for counting what is actually inside it."""
    if bw < 1 or bh < 1 or r < 1.0:
        return None
    side = max(1, int(round(2.0 * r)))
    disc = _unit_q().point(_CUT_LUT)
    if side != _GRID:
        disc = disc.resize((side, side), Image.BILINEAR)
    mask = Image.new("L", (bw, bh), 0)
    mask.paste(disc, (int(round(cx - r)), int(round(cy - r))))
    return _hard(mask)


def _median_in_disc(lum, cx, cy, r):
    """Median luma of the disc, read off its histogram instead of walked pixel by pixel.

    Pixels outside the circle are parked in the 255 bin and subtracted out of it, so the
    median is of the brush alone; a 4000 px tap then costs the same handful of
    milliseconds as a 40 px one, which is what keeps the limit honest.
    """
    w, h = lum.size
    box = (max(0, int(math.floor(cx - r))), max(0, int(math.floor(cy - r))),
           min(w, int(math.ceil(cx + r))), min(h, int(math.ceil(cy + r))))
    if box[2] <= box[0] or box[3] <= box[1]:
        return 128
    tile = lum.crop(box)
    m = _disc_mask(tile.width, tile.height, cx - box[0], cy - box[1], r)
    inside = sum(m.histogram()[128:])
    if inside < 4:
        return 128
    hist = Image.composite(tile, Image.new("L", tile.size, 255), m).histogram()
    hist[255] = max(0, hist[255] - (tile.width * tile.height - inside))
    want = inside / 2.0
    seen = 0
    for i in range(256):
        seen += hist[i]
        if seen >= want:
            return i
    return 255


def _fit(w, h, cx, cy, half):
    """Top-left of a 2*half square centred as near the point as the frame allows."""
    if 2 * half < 6 or 2 * half > min(w, h):
        return None
    return (int(min(max(cx, half), w - half)) - half,
            int(min(max(cy, half), h - half)) - half)


def _stats(im, mask):
    """Mean and spread of each band, counted only where the mask is on, histogram only.

    Pixels the mask rejects are set to 255 and then subtracted out of that bin, which
    is the whole trick: no numpy, no per-pixel Python loop over the frame.
    """
    out = sum(mask.histogram()[:128])
    res = []
    for ch in im.split():
        h = Image.composite(ch, Image.new("L", ch.size, 255), mask).histogram()
        h[255] = max(0, h[255] - out)
        n = sum(h)
        if n < 12:
            return None
        mean = sum(i * h[i] for i in range(256)) / n
        var = sum((i - mean) ** 2 * h[i] for i in range(256)) / n
        res.append((mean, math.sqrt(max(var, 0.0))))
    return res


# ------------------------------------------------------------------------- the brushes

def _patch(im, args):
    """Clone a disc of real pixels from an offset, toned to what sits around the landing.

    The source disc is measured (mean and spread per channel), the ring around the
    destination is measured, and the source is rescaled to the ring before it is pasted
    through a feathered mask. The pixels are the frame's own, moved; none are invented.
    """
    out, base = im, im
    w, h = im.size
    m = min(w, h)
    for st in _strokes(args, "patch"):
        brush, rad, dx, dy, feather, tone = st[2], st[3], st[4], st[5], st[6], st[7]
        r = 0.5 * brush * rad * m
        if r < 3.0:
            continue
        half = max(3, int(r))
        side = 2 * half
        tap = _fit(w, h, st[0] * w, st[1] * h, half)
        src_at = _fit(w, h, st[0] * w + dx * m, st[1] * h + dy * m, half)
        if tap is None or src_at is None:
            continue
        tbox = (tap[0], tap[1], tap[0] + side, tap[1] + side)
        sbox = (src_at[0], src_at[1], src_at[0] + side, src_at[1] + side)
        if tbox == sbox:                      # sampling the destination onto itself
            continue
        tgt, src = out.crop(tbox), out.crop(sbox)
        mask = _mask(side, side, half, half, r, feather=feather)
        if mask is None:
            continue

        # what the destination's surroundings actually look like
        ring = None
        rhalf = max(half + 2, min(int(RING_OUT * r) + 1, (min(w, h) - 1) // 2))
        ro = _fit(w, h, st[0] * w, st[1] * h, rhalf)
        if ro is not None and tone > 0:
            rbox = (ro[0], ro[1], ro[0] + 2 * rhalf, ro[1] + 2 * rhalf)
            lc = st[0] * w - rbox[0], st[1] * h - rbox[1]
            big = _mask(rbox[2] - rbox[0], rbox[3] - rbox[1], lc[0], lc[1],
                        RING_OUT * r, feather=0.30)
            small = _mask(rbox[2] - rbox[0], rbox[3] - rbox[1], lc[0], lc[1],
                          RING_IN * r, feather=0.30)
            if big is not None and small is not None:
                ring = _stats(out.crop(rbox),
                              ImageChops.subtract(_hard(big), _hard(small)))

        # ... and what the source disc looks like now, so the correction is measured
        # against the pixels about to be moved rather than guessed at.
        sd = _mask(side, side, half, half, r, feather=0.25)
        smeans = _stats(src, _hard(sd)) if ring is not None and sd is not None else None

        chans = list(src.split())
        if smeans is not None:
            fixed = []
            for i, ch in enumerate(chans):
                mu_s, sg_s = smeans[i]
                mu_t, sg_t = ring[i]
                g = 1.0
                if sg_s > 3.0:
                    g = max(GAIN_LO, min(GAIN_HI, sg_t / sg_s))
                a = 1.0 + tone * (g - 1.0)
                b = tone * (mu_t - mu_s * g)
                fixed.append(ImageMath.lambda_eval(
                    lambda d, a=a, b=b: d["convert"](d["I"] * a + b, "L"), I=ch.convert("I")))
            chans = fixed
        pasted = Image.composite(Image.merge("RGB", tuple(chans)), tgt, mask)
        out = base.copy() if out is base else out
        out.paste(pasted, tbox)
    return out


def _conceal(im, args):
    """Under-eye: a finer smooth than the skin brush, then a lift in one narrow band."""
    out, base = im, im
    for st in _strokes(args, "conceal"):
        amount, lift = st[3], st[4]
        if amount <= 0:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        lx, ly = cx - box[0], cy - box[1]
        mask = _mask(crop.width, crop.height, lx, ly, r, amount=amount)
        if mask is None:
            continue
        # half the radius smooth uses: the crease softens, the grain around it survives
        soft = crop.filter(ImageFilter.MedianFilter(3))
        soft = soft.filter(ImageFilter.GaussianBlur(min(2.0, max(0.5, r / 220.0))))
        body = Image.composite(soft, crop, mask)
        if abs(lift) < 1e-4:
            out = base.copy() if out is base else out
            out.paste(body, box)
            continue
        lum = body.convert("L")
        med = _median_in_disc(lum, lx, ly, r)
        gate = ImageChops.multiply(mask, lum.point(_band(med, BAND)))
        f = gate.point(_lut(lambda v: v * DODGE_GAIN * abs(lift)))
        chans = []
        for ch in body.split():
            delta = ImageChops.multiply(ch, f)
            chans.append(ImageChops.add(ch, delta) if lift > 0 else ImageChops.subtract(ch, delta))
        out = base.copy() if out is base else out
        out.paste(Image.merge("RGB", tuple(chans)), box)
    return out


def _red_eye(im, args):
    """Only the small dark-red cluster goes grey and down; white, skin and iris stay."""
    out, base = im, im
    for st in _strokes(args, "red_eye"):
        amount = st[3]
        if amount <= 0:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r)
        if mask is None:
            continue
        h_, s_, v_ = crop.convert("HSV").split()
        red = ImageChops.lighter(h_.point(_fall(6.0, 17.0)), h_.point(_ramp(239.0, 250.0)))
        alpha = ImageChops.multiply(mask, red)
        alpha = ImageChops.multiply(alpha, s_.point(_ramp(40.0, 120.0)))
        alpha = ImageChops.multiply(alpha, v_.point(_fall(140.0, 195.0)))
        alpha = alpha.point(_lut(lambda v: v * amount))
        if alpha.getbbox() is None:
            continue
        grey = crop.convert("L").point(
            _lut(lambda v: v * (1.0 - 0.60 * amount) + 4.0 * amount))
        cool = grey.point(_lut(lambda v: min(255.0, v + 12.0 * amount)))
        out = base.copy() if out is base else out
        out.paste(Image.composite(Image.merge("RGB", (grey, grey, cool)), crop, alpha), box)
    return out


def _dewy(im, args):
    """The inverse of matte: the bright, nearly colourless pixels go up, not down."""
    out, base = im, im
    for st in _strokes(args, "dewy"):
        amount = st[3]
        if amount <= 0:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        lx, ly = cx - box[0], cy - box[1]
        mask = _mask(crop.width, crop.height, lx, ly, r)
        if mask is None:
            continue
        lum = crop.convert("L")
        sat = crop.convert("HSV").split()[1]
        gate = ImageChops.multiply(mask, lum.point(_ramp(120.0, 200.0)))
        gate = ImageChops.multiply(gate, sat.point(_fall(50.0, 140.0)))
        gate = gate.point(_lut(lambda v: v * amount))
        if gate.getbbox() is None:
            continue
        med = _median_in_disc(lum, lx, ly, r)
        up = ImageChops.subtract(lum, Image.new("L", crop.size, med))
        delta = ImageChops.multiply(gate, up).point(_lut(lambda v: v * 0.42))
        floor_ = gate.point(_lut(lambda v: v * 0.05))
        lit = ImageChops.add(delta, floor_)
        out = base.copy() if out is base else out
        out.paste(Image.merge("RGB", tuple(ImageChops.add(c, lit) for c in crop.split())), box)
    return out


GX = ImageFilter.Kernel((3, 3), [-1.0, 0.0, 1.0, -2.0, 0.0, 2.0, -1.0, 0.0, 1.0], 4.0, 128.0)
GY = ImageFilter.Kernel((3, 3), [-1.0, -2.0, -1.0, 0.0, 0.0, 0.0, 1.0, 2.0, 1.0], 4.0, 128.0)


def _smear(crop, f, across):
    """Directional smoothing by averaging one axis: Pillow 13 only takes square kernels,
    so a box downscale along the axis and a bilinear back up is the wide version of it.
    `across` averages left-to-right, which is what collapses a strand that runs up and
    down; the other axis does the same for a strand lying sideways."""
    w, h = crop.size
    if across:
        if w <= 2 * f:
            return crop
        return crop.resize((max(1, w // f), h), Image.BOX).resize((w, h), Image.BILINEAR)
    if h <= 2 * f:
        return crop
    return crop.resize((w, max(1, h // f)), Image.BOX).resize((w, h), Image.BILINEAR)


def _flyaway(im, args):
    """Smear a strand along the axis it lies on, but only where dark sits against light.

    Two directional smears, one across and one down, mixed per pixel by which way the
    local gradient runs; the result replaces the original only where a median pass says
    the pixel is darker than its own neighbourhood, so a wide dark area, a light strand
    on a dark background and everything outside the brush are left exactly as they were.
    """
    out, base = im, im
    for st in _strokes(args, "flyaway"):
        amount = st[3]
        if amount <= 0:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        lx, ly = cx - box[0], cy - box[1]
        mask = _mask(crop.width, crop.height, lx, ly, r)
        if mask is None:
            continue
        lum = crop.convert("L")
        dark = ImageChops.subtract(lum.filter(ImageFilter.MedianFilter(5)), lum)
        gate = ImageChops.multiply(mask, dark.point(_ramp(10.0, 45.0)))
        gate = gate.point(_lut(lambda v: v * amount))
        if gate.getbbox() is None:
            continue
        mid = Image.new("L", crop.size, 128)
        ax = ImageChops.difference(lum.filter(GX), mid)
        ay = ImageChops.difference(lum.filter(GY), mid)
        along = ImageMath.lambda_eval(
            lambda d: d["convert"](255.0 * d["x"] / (d["x"] + d["y"] + 8.0), "L"),
            x=ax.convert("I"), y=ay.convert("I"))
        f = max(2, min(6, int(round(r / 24.0))))
        smooth = Image.composite(_smear(crop, f, True), _smear(crop, f, False), along)
        out = base.copy() if out is base else out
        out.paste(Image.composite(smooth, crop, gate), box)
    return out


# ------------------------------------------------------------------- the colour windows

def _skin_window(im, band):
    """How much of this frame sits in the skin-tone window, as an L mask.

    A rectangle in Cr/Cb plus a floor on luma, softened by a margin that grows with the
    band slider. It is a colour choice and nothing more: a terracotta wall, a beige
    sleeve or a wooden table inside the window is selected with the same confidence
    as a cheek, and narrowing the band is the only lever she has against that.
    """
    y, cb, cr = im.convert("YCbCr").split()
    b = min(max(band, 0.0), 1.0)
    soft = 6.0 + 16.0 * b
    cr_lo, cr_hi = SKIN_CR[0] - 10.0 * b, SKIN_CR[1] + 10.0 * b
    cb_lo, cb_hi = SKIN_CB[0] - 12.0 * b, SKIN_CB[1] + 12.0 * b
    m = y.point(_ramp(SKIN_Y, SKIN_Y + 34.0 + 22.0 * b))
    m = ImageChops.multiply(m, cr.point(_ramp(cr_lo, cr_lo + soft)))
    m = ImageChops.multiply(m, cr.point(_fall(cr_hi - soft, cr_hi)))
    m = ImageChops.multiply(m, cb.point(_ramp(cb_lo, cb_lo + soft)))
    return ImageChops.multiply(m, cb.point(_fall(cb_hi - soft, cb_hi)))


def _gain(mask, k):
    """A per-pixel gain written as an L image: ImageChops.multiply divides by 255, so
    this is what does arithmetic on a band without numpy."""
    return mask.point(_lut(lambda v: v * abs(k)))


def _scale(ch, mask, k):
    """ch * (1 + k * mask/255), exactly, and byte-identical where the mask is 0."""
    if abs(k) < 1e-4:
        return ch
    delta = ImageChops.multiply(ch, _gain(mask, k))
    return ImageChops.add(ch, delta) if k > 0 else ImageChops.subtract(ch, delta)


def _tan(im, args):
    """Warm and darken everything inside the colour window, hue and all."""
    amount, hue_deg, warmth, band = _vals(args, "tan")
    if amount <= 0:
        return im
    full = _skin_window(im, band)
    box = full.getbbox()
    if box is None:                     # the window holds nothing: not one pixel moves
        return im
    alpha = full.crop(box).point(_lut(lambda v: v * amount))
    sub = im.crop(box)
    h_, s_, v_ = sub.convert("HSV").split()
    th = int(round(hue_deg / 360.0 * 255.0))
    # shortest arc toward the tan hue; +384 is one full 256-turn plus half the wheel, so
    # the modulo never sees a negative and the wheel is not crossed the long way.
    new_h = ImageMath.lambda_eval(
        lambda d: d["convert"]((d["h"] + (((d["th"] - d["h"] + 384) % 256) - 128)
                               * (d["a"] / 255.0) * 0.70 + 256) % 256, "L"),
        h=h_.convert("I"), th=th, a=alpha)
    new_s = _scale(s_, alpha, 0.22 + 0.55 * warmth)
    new_v = _scale(v_, alpha, -(0.03 + 0.09 * warmth))
    r_, g_, b_ = Image.merge("HSV", (new_h, new_s, new_v)).convert("RGB").split()
    result = Image.merge("RGB", (_scale(r_, alpha, 0.07 * warmth), g_,
                                 _scale(b_, alpha, -0.09 * warmth)))
    out = im.copy()
    out.paste(Image.composite(result, sub, alpha), box)
    return out


def _skin_tone(im, args):
    """One lever on hue, one on colour amount, inside the same window."""
    dh, ds, amount, band = _vals(args, "skin_tone")
    if amount <= 0 or (abs(dh) < 1e-4 and abs(ds) < 1e-4):
        return im
    full = _skin_window(im, band)
    box = full.getbbox()
    if box is None:
        return im
    alpha = full.crop(box).point(_lut(lambda v: v * amount))
    sub = im.crop(box)
    h_, s_, v_ = sub.convert("HSV").split()
    shift = dh * 11.5                   # +-16 degrees, on a 256-step wheel
    new_h = ImageMath.lambda_eval(
        lambda d: d["convert"]((d["h"] + d["e"] * (d["a"] / 255.0) + 256) % 256, "L"),
        h=h_.convert("I"), e=shift, a=alpha)
    result = Image.merge("HSV", (new_h, _scale(s_, alpha, 0.65 * ds), v_)).convert("RGB")
    out = im.copy()
    out.paste(Image.composite(result, sub, alpha), box)
    return out


APPLIERS = {
    "patch": _op(_patch),
    "conceal": _op(_conceal),
    "red_eye": _op(_red_eye),
    "dewy": _op(_dewy),
    "flyaway": _op(_flyaway),
    "tan": _op(_tan),
    "skin_tone": _op(_skin_tone),
}


def apply(im: Image.Image, recipe) -> Image.Image:
    """Run a repair recipe in the order it arrived, capping each brush at its limit."""
    rgb, alpha = _split(im)
    out, used = rgb, {}
    for entry in recipe or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        name = str(entry[0])
        if name not in APPLIERS:
            continue
        used[name] = used.get(name, 0) + 1
        if used[name] > LIMITS[name]:
            continue
        out = APPLIERS[name](out, list(entry[1:]))
    return _join(out, alpha)
