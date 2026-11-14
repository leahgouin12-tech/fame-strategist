"""The colour engine - the Adjust panel the studio did not have.

Curves, levels, vibrance, hue rotation, per-band HSL, split tone, clarity, dehaze,
negative and posterise. Every one of them is arithmetic on the 256 values a channel can
hold: a lookup table where the answer depends only on the pixel, one wide blur where it
depends on its neighbours, `ImageMath` where the two have to meet. Nothing here invents
colour the file never recorded, and where an op has nothing to work on - grey has no hue
to protect, a flat area has no local contrast to raise - it leaves those pixels
byte-identical instead of quietly re-rendering them.

The recipe contract is shared with the tone, brush and layer engines: a recipe is a list
of [name, arg, ...] entries, and SHAPE, CLAMP, LIMITS and DEFAULTS below describe what
each op takes. Nothing here moves a pixel, so the arguments are all numbers in the ranges
the panel can hold - no positions, no radii in metres, no mask. An op only ever sees
numbers it can trust, and every op keeps the mode it was given: RGB in, RGB out; RGBA in,
RGBA out, with the alpha channel untouched.
"""

import math

from PIL import (
    Image,
    ImageChops,
    ImageEnhance,
    ImageFile,
    ImageFilter,
    ImageMath,
    ImageOps,
)

ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_EDGE = 6000

CURVE_GAIN = 0.5      # a full-tilt region offset moves its own part of the ramp half a stop
LEVEL_GAMMA = 0.9     # how far the gamma slider tips the midtone power
VIBRANCE_GAIN = 0.85  # share of a pixel's remaining headroom that amount 1 is allowed to fill
SKIN_GUARD = 0.7      # how much of that is taken away inside the skin hue band
HUE_SWING = 40.0      # degrees an HSL hue slider at 1 rotates the middle of its band
SAT_SWING = 0.9       # multiplicative saturation range of the HSL band
LIGHT_SWING = 0.85    # how far toward white an HSL lightness slider at 1 goes
LIGHT_DEEP = 1.6      # how far toward black the same slider goes at -1
SPLIT_STRENGTH = 0.6  # how much of a pixel a split-tone colour is allowed to replace
CLARITY_GAIN = 2.0    # how hard the wide unsharp is laid back in at amount 1
DEHAZE_SPAN = 0.8     # share of the local minimum called haze at amount 1
DEHAZE_FLOOR = 0.35   # never pull a pixel through more than this much transmission
DEHAZE_LIFT = 45.0    # levels of black an amount-1, lift-1 recovery puts back under the toe

# The seven hue bands the picker offers, as (centre in degrees, half width in degrees),
# plus the skin band the masks in this app are always measured against.
HUE_BANDS = ((0.0, 26.0), (30.0, 26.0), (60.0, 26.0), (120.0, 26.0),
             (185.0, 26.0), (240.0, 26.0), (285.0, 26.0))
SKIN_BAND = (24.0, 34.0)

# Each op's argument list at its own no-op: an entry that arrives short, or with a word
# where a number belongs, lands here and therefore does nothing rather than guessing.
# `posterize` is the one op with no nothing to do - 16 levels is the gentlest setting it
# has, so a broken entry posterises mildly instead of raising or pretending to be clean.
DEFAULTS = {
    "curves": [0.0, 0.0, 0.0, 0.0],
    "levels": [0.0, 1.0, 0.0],
    "vibrance": [0.0],
    "hue_rotate": [0.0, 0.0],
    "hsl": [0.0, 0.0, 0.0, 0.0, 0.5],
    "split_tone": [0.42, 0.54, 0.78, 0.98, 0.84, 0.66, 0.0, 0.0],
    "clarity": [0.0, 0.03],
    "dehaze": [0.0, 0.3],
    "invert": [0.0],
    "posterize": [16.0],
}

SHAPE = {
    "curves": ["list", ["f"] * 4],
    "levels": ["list", ["f"] * 3],
    "vibrance": ["list", ["f"]],
    "hue_rotate": ["list", ["f"] * 2],
    "hsl": ["list", ["f"] * 5],
    "split_tone": ["list", ["f"] * 8],
    "clarity": ["list", ["f"] * 2],
    "dehaze": ["list", ["f"] * 2],
    "invert": ["list", ["f"]],
    "posterize": ["list", ["f"]],
}

CLAMP = {
    # curves: channel (0 rgb, 1 r, 2 g, 3 b), shadows, mids, highs
    "curves": [(0.0, 3.0), (-1.0, 1.0), (-1.0, 1.0), (-1.0, 1.0)],
    # levels: black point, white point, gamma
    "levels": [(0.0, 0.5), (0.5, 1.0), (-1.0, 1.0)],
    "vibrance": [(-1.0, 1.0)],
    # hue_rotate: degrees, band (0 is every hue, 1..7 are HUE_BANDS)
    "hue_rotate": [(-180.0, 180.0), (0.0, 7.0)],
    # hsl: band (0 red .. 6 purple, 7 skin), hue, saturation, lightness, band width
    "hsl": [(0.0, 7.0), (-1.0, 1.0), (-1.0, 1.0), (-1.0, 1.0), (0.1, 1.0)],
    # split_tone: shadow colour r,g,b then highlight colour r,g,b, balance, amount.
    # The six colour slots are 0..1, the way the page folds a hex picker out.
    "split_tone": [(0.0, 1.0)] * 6 + [(-1.0, 1.0), (0.0, 1.0)],
    # clarity: amount, radius as a fraction of the short edge
    "clarity": [(-1.0, 1.0), (0.005, 0.08)],
    # dehaze: amount, how much black to put back under the recovery
    "dehaze": [(0.0, 1.0), (0.0, 1.0)],
    "invert": [(0.0, 1.0)],
    "posterize": [(2.0, 16.0)],
}

# One entry per op: these are whole-frame colour edits, not brushes, and the pipeline
# keeps the last one she set anyway, so a second entry of the same name is not a thing.
LIMITS = {name: 1 for name in SHAPE}


def _byte(v: float) -> int:
    return int(round(min(255.0, max(0.0, v))))


def _lut(fn):
    return [_byte(fn(i)) for i in range(256)]


def _identity():
    return list(range(256))


def _smooth(u: float) -> float:
    """0 below, 1 above, and flat at both ends so a ramp never shows a knee."""
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _ramp(lo, hi):
    """LUT: 0 at or below lo, 255 at or above hi, smooth between."""
    return _lut(lambda v: 255.0 * _smooth((v - lo) / max(1e-3, hi - lo)))


def _fall(lo, hi):
    """LUT: 255 at or below lo, 0 at or above hi, smooth between."""
    return _lut(lambda v: 255.0 * (1.0 - _smooth((v - lo) / max(1e-3, hi - lo))))


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
    span = CLAMP[name]
    out = []
    for i in range(len(SHAPE[name][1])):
        v = args[i] if i < len(args) else None
        out.append(_one(v, defaults[i], span[i]))
    return out


def _bounded(im):
    if max(im.size) <= MAX_EDGE:
        return im
    scale = MAX_EDGE / max(im.size)
    return im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BOX)


def _curve_table(shadow, mid, high):
    """One LUT from three region offsets. The Bernstein weights sum to 1 at every input,
    so the shift at any pixel is a blend of the three sliders and - with the gain at 0.5
    - the curve can never turn back on itself, whatever combination they arrive in."""
    def shape(i):
        x = i / 255.0
        off = (shadow * (1.0 - x) ** 2 + mid * 2.0 * x * (1.0 - x) + high * x * x)
        return 255.0 * min(1.0, max(0.0, x + CURVE_GAIN * off))
    return _lut(shape)


def _apply_channel(im, lut, channel):
    """One LUT onto one band, or onto all three when channel is 0. The bands that are not
    named keep an identity table, so a red curve leaves green exactly as it was."""
    if channel == 0:
        return im.point(lut * 3)
    band = channel - 1
    tables = [lut if i == band else _identity() for i in range(3)]
    return im.point([v for table in tables for v in table])


def _curves(im, args):
    channel, shadow, mid, high = int(round(args[0])), args[1], args[2], args[3]
    if max(abs(shadow), abs(mid), abs(high)) < 0.004:
        return im
    return _apply_channel(im, _curve_table(shadow, mid, high), channel)


def _levels(im, args):
    black, white, gamma = args
    if black <= 1e-4 and white >= 1.0 - 1e-4 and abs(gamma) < 1e-4:
        return im
    span = max(1e-4, white - black)
    exp = 1.0 / (1.0 + LEVEL_GAMMA * gamma)
    lut = _lut(lambda v: 255.0 * min(1.0, max(0.0, (v / 255.0 - black) / span)) ** exp)
    return im.point(lut * 3)


def _guard_table():
    """Vibrance strength each hue is allowed, 0..255. Skin hues keep most of their colour
    where it is: a face pushed by the same amount as a jacket reads as a sunburn."""
    span = 34.0
    lut = []
    for i in range(256):
        deg = i * 360.0 / 256.0
        d = abs((deg - SKIN_BAND[0] + 180.0) % 360.0 - 180.0)
        lut.append(_byte(255.0 * (1.0 - SKIN_GUARD * (1.0 - _smooth(d / span)))))
    return lut


def _vibrance(im, args):
    amount = args[0]
    if abs(amount) < 1e-4:
        return im
    hsv = im.convert("HSV")
    h, s, v = hsv.split()
    # A pixel only gets a share of the headroom it still has, so the vivid ones barely
    # move; the second gate is what keeps a colourless pixel colourless, because a delta
    # measured against (255 - s) would otherwise pour colour straight into a grey wall.
    # All of it is 8-bit arithmetic - three multiplies is the cheapest honest way to say
    # "the dose is the product of three gates" without a float plane per channel.
    room = s.point(_ramp(4.0, 60.0))
    push = ImageChops.multiply(
        ImageChops.multiply(ImageChops.invert(s), h.point(_guard_table())), room)
    dose = push.point(_lut(lambda x: x * abs(amount) * VIBRANCE_GAIN))
    join = ImageChops.add if amount > 0 else ImageChops.subtract
    out = Image.merge("HSV", (h, join(s, dose), v)).convert("RGB")
    # Greys are pasted straight back rather than round-tripped through HSV.
    return Image.composite(out, im, s.point(_ramp(1.0, 10.0)))


def _band_table(centre, half, feather):
    """A hue LUT: 255 inside a band, 0 outside it, measured as the shortest arc on the
    wheel. Callers multiply it by a saturation ramp, because a pixel with no colour has
    no hue and therefore belongs in no band at all."""
    lut = []
    for i in range(256):
        deg = i * 360.0 / 256.0
        d = abs((deg - centre + 180.0) % 360.0 - 180.0)
        t = 0.0 if d <= half else min(1.0, (d - half) / max(1e-3, feather))
        lut.append(_byte(255.0 * (1.0 - _smooth(t))))
    return lut


def _rotate(h, w, degrees):
    """Shift H by `degrees`, through weight w (0..255), the short way round the wheel."""
    return ImageMath.unsafe_eval(
        "convert((h + c * (w / 255.0) + 512) % 256, 'L')",
        h=h.convert("F"), c=degrees * 256.0 / 360.0, w=w.convert("F"))


def _hue_rotate(im, args):
    degrees, band = args[0], int(round(args[1]))
    if abs(degrees) < 0.5:
        return im
    h, s, v = im.convert("HSV").split()
    if band <= 0:
        centre, half, feather = 0.0, 180.0, 1.0     # every hue on the wheel
    else:
        centre, half = HUE_BANDS[min(band, len(HUE_BANDS)) - 1]
        feather = max(6.0, 0.55 * half)
    w = ImageChops.multiply(h.point(_band_table(centre, half, feather)),
                            s.point(_ramp(6.0, 26.0)))
    if w.getbbox() is None:
        return im
    turned = Image.merge("HSV", (_rotate(h, w, degrees), s, v)).convert("RGB")
    return Image.composite(turned, im, w)


def _hsl(im, args):
    band, hue, sat, light, rng = int(round(args[0])), args[1], args[2], args[3], args[4]
    if max(abs(hue), abs(sat), abs(light)) < 0.004:
        return im
    centre, half0 = SKIN_BAND if band >= 7 else HUE_BANDS[max(0, min(6, band))]
    table = _band_table(centre, half0 * rng, max(3.0, 0.5 * half0 * rng))
    h, s, v = im.convert("HSV").split()
    w = ImageChops.multiply(h.point(table), s.point(_ramp(8.0, 30.0)))
    if w.getbbox() is None:
        return im
    wf = w.convert("F")
    new_h = _rotate(h, w, HUE_SWING * hue) if abs(hue) >= 0.004 else h
    if abs(sat) >= 0.004:
        new_s = ImageMath.unsafe_eval(
            "convert(min(s * (1.0 + a * (k / 255.0)), 255.0), 'L')",
            s=s.convert("F"), a=SAT_SWING * sat, k=wf)
    else:
        new_s = s
    if abs(light) >= 0.004:
        # Up leans on the headroom a pixel still has, down on what is already black, so
        # neither direction flattens the band into one colour the way a raw add would.
        if light > 0:
            new_v = ImageMath.unsafe_eval(
                "convert(min(v + (255.0 - v) * a * (k / 255.0), 255.0), 'L')",
                v=v.convert("F"), a=LIGHT_SWING * light, k=wf)
        else:
            new_v = ImageMath.unsafe_eval(
                "convert(max(v * (1.0 - a * (k / 255.0)), 0.0), 'L')",
                v=v.convert("F"), a=LIGHT_DEEP * abs(light), k=wf)
    else:
        new_v = v
    out = Image.merge("HSV", (new_h, new_s, new_v)).convert("RGB")
    return Image.composite(out, im, w)


def _split_tone(im, args):
    shadow, highlight, balance, amount = args[:3], args[3:6], args[6], args[7]
    if amount <= 0.004:
        return im
    mid = (0.5 + 0.45 * balance) * 255.0
    strength = SPLIT_STRENGTH * amount
    lum = im.convert("L")
    lo = lum.point(_fall(0.0, mid)).point(_lut(lambda t: t * strength))
    hi = lum.point(_ramp(mid, 255.0)).point(_lut(lambda t: t * strength))
    bands = []
    for ch, s_col, h_col in zip(im.split(), shadow, highlight):
        bands.append(ImageMath.unsafe_eval(
            "convert(max(min(c + (lo * (sv - c) + hi * (hv - c)) / 255.0, 255.0), 0.0), 'L')",
            c=ch.convert("F"), lo=lo.convert("F"), hi=hi.convert("F"),
            sv=s_col * 255.0, hv=h_col * 255.0))
    return Image.merge("RGB", bands)


def _clarity(im, args):
    amount, radius = args
    if abs(amount) < 0.004:
        return im
    w, h = im.size
    px = max(1.0, radius * min(w, h))
    soft = im.filter(ImageFilter.GaussianBlur(px))
    # Mid-tone weighted: clarity is local contrast, and local contrast in a highlight that
    # is already at the ceiling only produces a orange edge nobody asked for.
    weight = im.convert("L").point(
        _lut(lambda v: 255.0 * (0.35 + 0.65 * 4.0 * (v / 255.0) * (1.0 - v / 255.0))))
    wf = weight.convert("F")
    gain = CLARITY_GAIN * amount
    bands = []
    for sharp, blur in zip(im.split(), soft.split()):
        bands.append(ImageMath.unsafe_eval(
            "convert(max(min(c + (c - b) * g * (k / 255.0), 255.0), 0.0), 'L')",
            c=sharp.convert("F"), b=blur.convert("F"), g=gain, k=wf))
    return Image.merge("RGB", bands)


def _dehaze(im, args):
    amount, lift = args
    if amount <= 0.004:
        return im
    w, h = im.size
    r, g, b = im.split()
    # The darkest channel in each neighbourhood is what a hazy frame has the least of, so
    # how high that floor sits is the thickness of the air. Nothing is detected here: an
    # already-clean frame has a floor near nothing and this whole op then barely bites.
    floor = ImageChops.darker(ImageChops.darker(r, g), b)
    veil = floor.filter(ImageFilter.GaussianBlur(max(1.0, 0.03 * min(w, h))))
    top = max(40.0, float(veil.getextrema()[1]))
    t = ImageMath.unsafe_eval(
        "max(1.0 - a * (v / t0), f0)", v=veil.convert("F"), a=DEHAZE_SPAN * amount,
        t0=top, f0=DEHAZE_FLOOR)
    bands = []
    for ch in (r, g, b):
        bands.append(ImageMath.unsafe_eval(
            "convert(max(min((c - t0 * (1.0 - tt)) / tt, 255.0), 0.0), 'L')",
            c=ch.convert("F"), t0=top, tt=t))
    out = Image.merge("RGB", bands)
    if lift > 0.004:
        lut = _lut(lambda v: v + DEHAZE_LIFT * lift * amount * (1.0 - v / 255.0) ** 2)
        out = out.point(lut * 3)
    out = ImageEnhance.Contrast(out).enhance(1.0 + 0.3 * amount)
    return ImageEnhance.Color(out).enhance(1.0 + 0.25 * amount)


def _invert(im, args):
    amount = args[0]
    if amount <= 0.004:
        return im
    return Image.blend(im, ImageOps.invert(im), min(1.0, amount))


def _posterize(im, args):
    bits = max(1, min(4, int(round(math.log(max(2.0, args[0]), 2)))))
    return ImageOps.posterize(im, bits)


def _guarded(name, fn):
    """Ops work on RGB. Any alpha the frame already had is put back afterwards, so a
    colour edit can sit after a cutout in the same recipe and still leave it transparent."""

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
    "curves": _guarded("curves", _curves),
    "levels": _guarded("levels", _levels),
    "vibrance": _guarded("vibrance", _vibrance),
    "hue_rotate": _guarded("hue_rotate", _hue_rotate),
    "hsl": _guarded("hsl", _hsl),
    "split_tone": _guarded("split_tone", _split_tone),
    "clarity": _guarded("clarity", _clarity),
    "dehaze": _guarded("dehaze", _dehaze),
    "invert": _guarded("invert", _invert),
    "posterize": _guarded("posterize", _posterize),
}


def apply(im: Image.Image, recipe) -> Image.Image:
    """Run a colour recipe in the order it arrives, one entry per op."""
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
