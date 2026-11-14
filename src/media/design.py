"""Design: the brush, the sticker, the words on an arc, and the shape the print is cut to.

The layer engine next door puts words and a second photo on a picture. This is the rest of
the drawing kit: a brush dab you can tap or drag, a procedural sticker, curved type, the
silhouette a cover is cut to, a backdrop dropped behind the subject, a rim of colour around
it, and a frame that grows into its own blurred edge. Nothing here invents a picture: the
stickers are polygons, the arc is arithmetic, and the two ops that need to know where the
subject is borrow the flood-fill cutout from effects.py and say so in their note.

The recipe contract is the one every engine here obeys: an entry is ["name", arg, ...], a
position is a fraction of the frame as it stands at that point in the pipeline, a size is a
fraction of the short edge, and SHAPE, CLAMP and LIMITS below are what the registry and the
clamping in edit.py read. Slots are laid out so the page's colour picker writes three
numbers starting at its own slot, exactly as the text tool does.
"""

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from src.media import effects, layers

SUPERSAMPLE = 4        # a sticker is drawn this many times bigger, then scaled down
TILE_CAP = 2048        # ... but the tile it is drawn on is never bigger than this
MASK_CAP = 1400        # a cut mask is drawn at this size or bigger, so its rim is smooth
MAX_EDGE = layers.MAX_EDGE
ARC_MIN = 1.0          # below one degree of sweep the arc is treated as a full ring
ARC_ROWS = 6           # lines an arc stacks before it stops
ARC_GLYPHS = 64        # letters an arc draws in one entry, whole lines first
ARC_EDGE = 240.0       # the width of the letter box an arc counts as one unit of work
ARC_RUNS = 33.0        # ... and how many of those units one entry is allowed
CUT_TOLERANCE = 0.22   # the cutout's own tolerance: the same one the Cut rail defaults to
FEATHER_K = 0.05       # a feather of 1.0 softens the cut over 5% of the short edge
EXPAND_K = 0.06        # an expand of 1.0 grows the subject 6% of the short edge outward

KINDS = ("arrow", "star", "ring", "bubble", "badge", "heart", "spark", "cross")
CUTS = ("circle", "hex", "rounded", "arch", "star")
FITS = ("cover", "contain", "stretch")
EDGES = ("all", "up", "down", "left", "right")
# The order the page's typeface select shows, so the index it writes means the same face.
FACES = ("display", "body", "serif", "condensed", "mono")

LIMITS = {
    "draw": 60,
    "sticker": 24,
    "curved_text": 8,
    "shape_crop": 1,
    "bg_replace": 1,
    "glow_edge": 1,
    "edge_expand": 1,
}

SHAPE = {
    "draw": ["group", 8, LIMITS["draw"]],
    "sticker": ["group", 9, LIMITS["sticker"]],
    "curved_text": ["group", 13, LIMITS["curved_text"]],
    "shape_crop": ["list", ["f"] * 7],
    "bg_replace": ["list", ["s"] + ["f"] * 6],
    "glow_edge": ["list", ["f"] * 5],
    "edge_expand": ["list", ["f"] * 4],
}

CLAMP = {
    "draw": [
        (0.0, 1.0), (0.0, 1.0), (0.005, 0.6),             # x, y, brush diameter
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),               # r, g, b
        (0.0, 1.0), (0.0, 1.0),                           # opacity, hardness
    ],
    "sticker": [
        (0.0, 1.0), (0.0, 1.0), (0.02, 1.0),              # x, y, size
        (0.0, 7.0),                                       # kind
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),               # r, g, b
        (-360.0, 360.0), (0.0, 0.2),                      # rotate, outline
    ],
    "curved_text": [
        # the cap stops at 0.2 where the text tool reaches 0.5: every letter on an arc is
        # drawn and turned on its own, so this one costs letters times area
        (0.0, 1.0), (0.0, 1.0), (0.01, 0.2),              # x, y, cap height
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),               # r, g, b
        (0.0, 0.5), (0.0, 1.0), (0.0, 2.0),               # stroke, shadow, align
        None, None,                                       # family, words
        (0.05, 1.0), (-360.0, 360.0),                     # arc radius, sweep
    ],
    "shape_crop": [
        (0.0, 4.0), (0.0, 0.2), (0.0, 0.2), (0.0, 2.0),   # shape, inset, corner, mode
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),               # r, g, b
    ],
    "bg_replace": [
        None,                                             # file
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),               # r, g, b
        (0.0, 1.0), (0.0, 1.0), (0.0, 2.0),               # feather, expand, fit
    ],
    "glow_edge": [
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),               # r, g, b
        (0.005, 0.5), (0.0, 1.0),                         # size, amount
    ],
    "edge_expand": [
        (0.0, 4.0), (0.0, 0.5), (0.0, 1.0), (0.0, 1.0),   # direction, amount, blur, fade
    ],
}


def _shape(name: str, args) -> list:
    """layers._shape's one trimming rule - only whole groups survive - run over this
    module's own tables, so a truncated tail cannot slide later arguments left."""
    spec, slots = SHAPE[name], CLAMP[name]
    raw = list(args or [])
    if spec[0] == "group":
        k, n = spec[1], spec[2]
        out = []
        for i in range(0, k * n, k):
            if i + k > len(raw):
                break
            out += [layers._one(raw[i + j], slots[j % len(slots)]) for j in range(k)]
        return out
    return [layers._one(raw[i], slots[i]) for i in range(min(len(raw), len(slots)))]


def _groups(flat: list, k: int) -> list:
    return layers._groups(flat, k)


def _byte(v: float) -> int:
    return int(round(min(255.0, max(0.0, 255.0 * v))))


def _rgb(centre):
    return (_byte(centre[0]), _byte(centre[1]), _byte(centre[2]))


def _tone(centre, keep: float):
    """The same colour pulled toward black - the edge a sticker is outlined with."""
    return tuple(_byte(c * keep) for c in centre)


def _canvas(im):
    """A copy to draw on, plus the alpha the finished frame has to keep: pasting a tile
    over an RGBA picture replaces its alpha band where the ink lands."""
    work = im.copy() if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    return work, (work.getchannel("A") if "A" in work.getbands() else None)


def _blank(mode: str, size) -> Image.Image:
    """An empty frame in the mode the work is in: black, and clear when it has opacity."""
    return Image.new(mode, size, (0, 0, 0) if mode == "RGB" else (0, 0, 0, 0))


def _tight(tile: Image.Image) -> Image.Image:
    """The tile cut to the ink it carries, padded evenly around its own centre so it
    still lands the same way. Turning or scaling a whole square of margins costs the
    same as turning the mark and shows nothing of it."""
    box = tile.getbbox()
    if box is None:
        return tile
    cx, cy = tile.width // 2, tile.height // 2
    half_x = max(cx - box[0], box[2] - cx) + 1
    half_y = max(cy - box[1], box[3] - cy) + 1
    return tile.crop((cx - half_x, cy - half_y, cx + half_x, cy + half_y))


def _face(value):
    """The typeface slot as the page sends it: a name, or the index of one."""
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text in layers.FONTS:
            return text
        try:
            value = int(float(text))
        except ValueError:
            return text
    try:
        return FACES[int(value) % len(FACES)]
    except (TypeError, ValueError, IndexError):
        return "body"


def _dilate(alpha: Image.Image, grow: float) -> Image.Image:
    """Push a matte outward by `grow` pixels, measured on the same small working scale
    the cutout itself runs at: a MaxFilter across a whole frame costs more than every
    other step in this module put together."""
    if grow < 0.5:
        return alpha
    wide, tall = alpha.size
    scale = effects.WORK_EDGE / max(wide, tall)
    small = alpha if scale >= 1.0 else layers._resize(alpha, (wide * scale, tall * scale))
    band = min(31, 2 * max(1, int(round(grow * scale))) + 1)
    small = small.filter(ImageFilter.MaxFilter(band))
    if small.size != alpha.size:
        small = small.resize(alpha.size, Image.BILINEAR)
    return ImageChops.lighter(alpha, small)


def _subject(im: Image.Image, feather: float, expand: float):
    """Where the subject is, as an L band. A frame that already carries an alpha keeps it;
    otherwise this is the flood-fill cutout's own mask, tolerance and all.

    Which means it is exactly as good as the Cut rail: clean on an even wall, eaten around
    hair and anything the backdrop matches in colour.
    """
    if "A" in im.getbands():
        alpha = im.getchannel("A")
    else:
        alpha = effects._cutout(im.convert("RGB"),
                                [CUT_TOLERANCE, 0.0, 0.0, 0.0]).getchannel("A")
    short = min(im.size)
    if expand > 0.0:
        alpha = _dilate(alpha, expand * EXPAND_K * short)
    if feather > 0.0:
        radius = feather * FEATHER_K * short
        if radius >= 0.5:
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius))
    return alpha


def _frame_band(size, width: int) -> Image.Image:
    """Opaque from the edge of the picture inward for `width`, clear behind it. The stand-in
    silhouette for a frame whose flood fill found no subject, so a rim glow still has a rim."""
    alpha = Image.new("L", size, 0)
    ImageDraw.Draw(alpha).rectangle((0, 0, size[0] - 1, size[1] - 1), outline=255, width=width)
    return alpha


# --------------------------------------------------------------------------- the brush


def _brush(radius: float, hardness: float, colour, opacity: float) -> Image.Image:
    """One dab as its own tile: solid out to the hardness it was given, then a Gaussian
    feather across the rest of the radius. The retouch brush builds its mask at 64 px and
    stretches it; here the taps are the work, so the disc is drawn at its own size once
    per brush and a stroke of one setting pays for it once."""
    side = max(3, int(round(2 * radius)) + 1)
    core = min(0.95, max(0.0, hardness))
    reach = radius * max(core, 0.3)
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse([side / 2.0 - reach, side / 2.0 - reach,
                                  side / 2.0 + reach, side / 2.0 + reach], fill=255)
    mask = _soften(mask, max(1.0, (radius - reach) / 2.5))
    if opacity < 1.0:
        mask = mask.point(layers._scaled(opacity))
    tile = Image.new("RGBA", (side, side), colour + (0,))
    tile.putalpha(mask)
    return tile


def _draw(im: Image.Image, args) -> Image.Image:
    """The brush: one entry per tap, so a drag is the taps the page records along it."""
    flat = _shape("draw", args)
    marks = [g for g in _groups(flat, 8) if g[2] > 0.0 and g[6] > 0.0]
    if not marks:
        return im
    work, keep = _canvas(im)
    short = min(work.size)
    wanted, tile = None, None
    for x, y, diameter, r, g, b, opacity, hardness in marks:
        radius = max(1.0, 0.5 * diameter * short)
        brush = (round(radius, 2), round(hardness, 4), round(opacity, 4), r, g, b)
        if brush != wanted:
            # the taps of one drag share their brush, so one tile carries the whole run
            tile = _brush(radius, hardness, _rgb((r, g, b)), opacity)
            wanted = brush
        layers._stamp(work, tile, x * work.width - radius, y * work.height - radius)
    if keep is not None:
        work.putalpha(keep)
    return work


# ------------------------------------------------------------------------- the stickers


def _unit(side: int, points) -> list:
    return [(x * side, y * side) for x, y in points]


def _star_points(arms: int, inner: float, offset: float = 0.0) -> list:
    out = []
    for i in range(arms * 2):
        reach = 0.48 if i % 2 == 0 else inner
        angle = math.radians(offset + i * 180.0 / arms)
        out.append((0.5 + reach * math.sin(angle), 0.5 - reach * math.cos(angle)))
    return out


def _heart_points() -> list:
    """The classic parametric heart, scaled to sit inside the tile."""
    out = []
    for i in range(72):
        t = math.pi * 2 * i / 72.0
        out.append((0.5 + 0.48 * math.sin(t) ** 3,
                    0.5 - 0.48 * (13 * math.cos(t) - 5 * math.cos(2 * t)
                                  - 2 * math.cos(3 * t) - math.cos(4 * t)) / 17.0))
    return out


def _arrow(draw, side, colour, stroke):
    _lobed(draw, side, [(0.50, 0.03), (0.97, 0.42), (0.70, 0.42), (0.70, 0.96),
                        (0.30, 0.96), (0.30, 0.42), (0.03, 0.42)], colour, stroke)


def _star(draw, side, colour, stroke):
    _lobed(draw, side, _star_points(5, 0.21), colour, stroke)


def _ring(draw, side, colour, stroke):
    band = stroke if stroke >= side // 16 else max(2, int(round(0.14 * side)))
    inset = band // 2 + 1
    draw.ellipse([inset, inset, side - 1 - inset, side - 1 - inset],
                 outline=colour, width=band)


def _bubble(draw, side, colour, stroke):
    pad = int(round(0.04 * side))
    draw.rounded_rectangle([pad, pad, side - pad, int(0.72 * side)],
                           radius=int(0.15 * side), fill=colour)
    draw.polygon(_unit(side, [(0.26, 0.68), (0.48, 0.68), (0.28, 0.97)]), fill=colour)


def _badge(draw, side, colour, stroke):
    """A seal: a shallow twelve-lobe disc with a ring struck inside it."""
    _lobed(draw, side, _star_points(12, 0.40, 15.0), colour, stroke)
    band = max(2, int(round(0.035 * side)))
    inset = int(round(0.28 * side))
    draw.ellipse([inset, inset, side - inset, side - inset],
                 outline=_tone(colour, 0.55), width=band)


def _heart(draw, side, colour, stroke):
    _lobed(draw, side, _heart_points(), colour, stroke)


def _spark(draw, side, colour, stroke):
    """Four long points and four almost-inward ones - the sparkle, not the star."""
    _lobed(draw, side, _star_points(4, 0.10), colour, stroke)


def _cross(draw, side, colour, stroke):
    _lobed(draw, side, [(0.36, 0.04), (0.64, 0.04), (0.64, 0.36), (0.96, 0.36),
                        (0.96, 0.64), (0.64, 0.64), (0.64, 0.96), (0.36, 0.96),
                        (0.36, 0.64), (0.04, 0.64), (0.04, 0.36), (0.36, 0.36)],
           colour, stroke)


def _lobed(draw, side, points, colour, stroke):
    """Filled shape, plus a darker edge when she asked for one."""
    pts = _unit(side, points)
    draw.polygon(pts, fill=colour)
    if stroke >= 2:
        draw.line(pts + [pts[0]], fill=_tone(colour, 0.5), width=stroke, joint="curve")


_STICKERS = (_arrow, _star, _ring, _bubble, _badge, _heart, _spark, _cross)


def _sticker_tile(edge: int, kind: int, centre, turn: float, outline: float) -> Image.Image:
    """The mark drawn `SUPERSAMPLE` times bigger than it is wanted and scaled back down,
    which is what keeps a diagonal edge from turning into a staircase."""
    side = max(edge, min(SUPERSAMPLE * edge, TILE_CAP))
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    colour = _rgb(centre) + (255,)
    _STICKERS[kind % len(_STICKERS)](ImageDraw.Draw(tile), side, colour,
                                     int(round(outline * side)))
    if side != edge:
        tile = tile.resize((edge, edge), Image.LANCZOS)
    if abs(turn) > 0.5:
        tile = _tight(tile).rotate(turn, resample=Image.BILINEAR, expand=True)
    return tile


def _sticker(im: Image.Image, args) -> Image.Image:
    flat = _shape("sticker", args)
    marks = [g for g in _groups(flat, 9) if g[2] > 0.0]
    if not marks:
        return im
    work, keep = _canvas(im)
    short = min(work.size)
    for x, y, size, kind, r, g, b, turn, outline in marks:
        edge = max(4, int(round(size * short)))
        tile = _sticker_tile(edge, int(kind), (r, g, b), turn, outline)
        layers._stamp(work, tile, x * work.width - tile.width / 2.0,
                      y * work.height - tile.height / 2.0)
    if keep is not None:
        work.putalpha(keep)
    return work


# ------------------------------------------------------------------------ the curved type


def _over(work, sheet, keep=None):
    """Lay a transparent sheet over the working frame, clipped to where it carries ink."""
    box = sheet.getbbox()
    if box is None:
        return work
    alpha = sheet.getchannel("A").crop(box)
    ink = sheet.crop(box)
    work.paste(ink.convert("RGB") if work.mode == "RGB" else ink, box, alpha)
    return work if keep is None else _restore(work, keep)


def _restore(work, keep):
    """The alpha a stamped frame leaves behind is the tile's own, so a paste over an
    already opaque picture dims it and a paste over a hole hides the ink. This keeps the
    more opaque of the two everywhere: the frame arrives with its cut-out intact and a
    stroke drawn on clear ground still shows up."""
    work.putalpha(ImageChops.lighter(keep, work.getchannel("A")))
    return work


def _drop(sheet, amount: float, cap: float) -> Image.Image:
    """The shadow of a whole run of letters: its coverage blackened, softened and nudged
    once. Doing it per letter costs one wide blur per letter, which is what a soft shadow
    on an arc is not."""
    off = max(1, int(round(0.14 * amount * cap)))
    alpha = sheet.getchannel("A").point(layers._scaled(0.85 * amount))
    alpha = _soften(alpha, max(1.0, 0.6 * off))
    spread = Image.new("L", sheet.size, 0)
    spread.paste(alpha, (off, off))
    shade = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
    shade.putalpha(spread)
    return shade


def _arc(im: Image.Image, args) -> Image.Image:
    """Words stepped along a circle whose centre is where she tapped.

    The arc runs through the middle of the letters. A positive sweep hangs them over the
    top of the circle, a negative one under the bottom, and each further line nests inside
    the one above it. The steps come from the font's own advances; the sweep only squeezes
    them when the words would run past the arc it was given.

    Turning every letter on its own is what this tool spends its time on, and a turned
    letter costs more than its area - so the cap height stops where the text tool would
    still be cheap, and an entry gets ARC_RUNS units of letter before it stops taking
    whole leading lines of the words it was given.
    """
    flat = _shape("curved_text", args)
    wanted = [g for g in _groups(flat, 13) if g[10].strip()]
    if not wanted:
        return im
    work, keep = _canvas(im)
    wide, tall = work.size
    short = min(wide, tall)
    for (x, y, size, r, g, b, stroke, shadow, align, family, words,
         radius, sweep) in wanted:
        cap = max(4.0, size * tall)
        font = layers._font(_face(family), cap)
        reach = max(0.05, radius) * short
        limit = abs(math.radians(sweep))
        if limit < math.radians(ARC_MIN):
            limit = math.radians(360.0)
        sign = 1.0 if sweep >= 0 else -1.0
        line_h, lead = layers._metrics(font)
        lead = max(1, int(round(layers.LEAD * line_h))) + int(round(0.12 * line_h))
        line_h += 2 * lead
        fill = _rgb((r, g, b)) + (255,)
        stroke_px = int(round(stroke * cap))
        box = cap + 2.0 * stroke_px + 2.0            # the square one letter fills
        budget = min(ARC_GLYPHS, max(4, int(ARC_RUNS * (ARC_EDGE / box) ** 3.2)))
        rows, seen = [], 0
        for line in layers._lines(words, font, max(1.0, reach * limit))[:ARC_ROWS]:
            if seen + len(line) > budget:
                if not rows:
                    rows.append(line[:budget])
                break
            rows.append(line)
            seen += len(line)
        centre_x, centre_y = x * wide, y * tall
        sheet = Image.new("RGBA", (wide, tall), (0, 0, 0, 0))
        for row, line in enumerate(rows):
            advances = [max(0.0, layers._width(font, ch)) for ch in line]
            total = sum(advances)
            if total <= 0.0:
                continue
            natural = total / reach
            squeeze = min(1.0, limit / natural) if natural > 0 else 1.0
            steps = [a / reach * squeeze for a in advances]
            block = sum(steps)
            if int(align) % 3 == 0:
                here = -limit / 2.0
            elif int(align) % 3 == 2:
                here = limit / 2.0 - block
            else:
                here = -block / 2.0
            arm = max(2.0, reach - row * line_h)
            for ch, step, advance in zip(line, steps, advances):
                middle = here + step / 2.0
                here += step
                if not ch.strip() or advance <= 0.0:
                    continue
                tile, _ = layers._tile([ch], font, 1, fill, stroke_px, (0, 0, 0, 255))
                turned = _tight(tile).rotate(sign * math.degrees(middle),
                                             resample=Image.BILINEAR, expand=True)
                px = centre_x + arm * math.sin(middle)
                py = centre_y - sign * arm * math.cos(middle)
                layers._stamp(sheet, turned, px - turned.width / 2.0,
                              py - turned.height / 2.0)
        if shadow > 0.0:
            work = _over(work, _drop(sheet, shadow, cap), keep)
        work = _over(work, sheet, keep)
    return work


# --------------------------------------------------------------------- the cut and the drop


def _cut_mask(kind: int, size, inset: int, corner: int) -> Image.Image:
    """The keep-out line, drawn bigger than the frame and scaled back so the rim is a
    curve and not a stair."""
    wide, tall = size
    scale = max(1, min(4, 1 + MASK_CAP // max(1, wide, tall)))
    tile = Image.new("L", (wide * scale, tall * scale), 0)
    draw = ImageDraw.Draw(tile)
    cell = [inset * scale, inset * scale, (wide - inset) * scale - 1,
            (tall - inset) * scale - 1]
    left, top, right, bottom = cell
    span = right - left, bottom - top
    if kind % len(CUTS) == 0:                       # circle: the biggest oval that fits
        draw.ellipse(cell, fill=255)
    elif kind % len(CUTS) == 1:                     # hex: flat top and bottom
        draw.polygon([(left + span[0] * 0.25, top), (right - span[0] * 0.25, top),
                      (right, top + span[1] * 0.5), (right - span[0] * 0.25, bottom),
                      (left + span[0] * 0.25, bottom), (left, top + span[1] * 0.5)],
                     fill=255)
    elif kind % len(CUTS) == 2:                     # rounded
        draw.rounded_rectangle(cell, radius=max(0, corner * scale), fill=255)
    elif kind % len(CUTS) == 3:                     # arch: a door, round head, flat feet
        reach = min(span[0] / 2.0, span[1])
        draw.rounded_rectangle([left, top, right, top + 2 * reach], radius=reach, fill=255)
        draw.rectangle([left, top + reach, right, bottom], fill=255)
    else:                                           # star: five points across the frame
        points = _star_points(5, 0.20)
        draw.polygon([(left + span[0] * f, top + span[1] * g) for f, g in points],
                     fill=255)
    return tile if scale == 1 else tile.resize(size, Image.LANCZOS)


def _shape_crop(im: Image.Image, args) -> Image.Image:
    flat = _shape("shape_crop", args)
    if len(flat) < 4:
        return im
    kind, inset, corner, mode = flat[:4]
    centre = flat[4:7] if len(flat) >= 7 else (0.0, 0.0, 0.0)
    base = im if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    short = min(base.size)
    box = _cut_mask(int(kind), base.size, int(round(inset * short)),
                    int(round(corner * short)))
    had = base.getchannel("A") if "A" in base.getbands() else None
    if had is not None:
        box = ImageChops.darker(box, had)
    if int(mode) >= 1:
        # a plate behind it rather than a hole in it, so the frame stays RGB
        colour = (255, 255, 255) if int(mode) == 1 else _rgb(centre)
        return Image.composite(base.convert("RGB"),
                              Image.new("RGB", base.size, colour), box)
    out = base.convert("RGBA")
    out.putalpha(box)
    return out


def _backdrop(src, size, colour, fit: int) -> Image.Image:
    """The plate the subject is dropped onto: a file from the inbox sized to the frame, or
    the flat colour when there is no file - and behind a contained file either way."""
    wide, tall = size
    colour = _rgb(colour)
    if src is None:
        return Image.new("RGB", size, colour)
    if fit % len(FITS) == 2:
        return layers._resize(src, size).convert("RGB")
    sw, sh = max(1, src.width), max(1, src.height)
    if fit % len(FITS) == 0:
        scale = max(wide / sw, tall / sh)
        got = layers._resize(src, (max(wide, sw * scale), max(tall, sh * scale)))
        left, top = (got.width - wide) // 2, (got.height - tall) // 2
        return got.convert("RGB").crop((left, top, left + wide, top + tall))
    scale = min(wide / sw, tall / sh)
    got = layers._resize(src, (max(1, sw * scale), max(1, sh * scale)))
    out = Image.new("RGB", size, colour)
    out.paste(got.convert("RGB"), ((wide - got.width) // 2, (tall - got.height) // 2))
    return out


def _bg_replace(im: Image.Image, args) -> Image.Image:
    flat = _shape("bg_replace", args)
    if len(flat) < 7:
        return im
    name, r, g, b, feather, expand, fit = flat
    base = im if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    alpha = _subject(base, feather, expand)
    plate = _backdrop(layers._asset(name), base.size, (r, g, b), int(fit))
    return Image.composite(base.convert("RGB"), plate, alpha)


def _glow_edge(im: Image.Image, args) -> Image.Image:
    """The subject's own silhouette, blurred, tinted and laid behind it.

    Needs the same cutout alpha as the backdrop swap, so on a busy frame the glow follows
    wherever the flood fill stopped. Where it stopped nowhere - an evenly lit photo with no
    silhouette to find - the glow goes round the inside edge of the picture instead of
    returning the frame untouched.
    """
    flat = _shape("glow_edge", args)
    if len(flat) < 5 or flat[4] <= 0.0:
        return im
    r, g, b, size, amount = flat
    base = im if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    short = min(base.size)
    alpha = _subject(base, 0.0, 0.0)
    subject = alpha.getbbox() is not None
    if not subject:
        alpha = _frame_band(base.size, max(2, int(size * short)))
    # size is the reach of the ring against the short edge, like every other size here
    halo = _soften(alpha, size * short).point(layers._scaled(min(1.0, amount)))
    colour = _rgb((r, g, b))
    if "A" in base.getbands() and subject:
        glow = Image.new("RGBA", base.size, colour + (0,))
        glow.putalpha(halo)
        kept = base.copy()
        kept.putalpha(alpha)
        return Image.alpha_composite(glow, kept)
    lit = ImageChops.screen(base.convert("RGB"), Image.new("RGB", base.size, colour))
    # the glow only lands where the subject is not, and only as strongly as its own
    # blurred edge reaches: a halo is a rim, not a wash over the whole frame
    rim = ImageChops.darker(halo, ImageChops.invert(alpha))
    out = Image.composite(lit, base.convert("RGB"), rim)
    if "A" in base.getbands():
        out.putalpha(base.getchannel("A"))
    return out


# ------------------------------------------------------------------- the frame that grows


def _mirror(src, left: int, top: int, right: int, bottom: int) -> Image.Image:
    """The frame surrounded by its own reflection, which is the material the new edge is
    made of: neighbouring background, blurred, and nothing else."""
    wide, tall = src.size
    first_x = int(math.floor(-left / float(wide)))
    last_x = int(math.floor((wide + right - 1) / float(wide)))
    first_y = int(math.floor(-top / float(tall)))
    last_y = int(math.floor((tall + bottom - 1) / float(tall)))
    if (last_x, last_y, first_x, first_y) == (0, 0, 0, 0):
        return src
    over = src.transpose(Image.FLIP_LEFT_RIGHT)
    cols, rows = last_x - first_x + 1, last_y - first_y + 1
    field = _blank(src.mode, (cols * wide, rows * tall))
    for j in range(first_y, last_y + 1):
        for i in range(first_x, last_x + 1):
            cell = src if i % 2 == 0 else over
            if j % 2:
                cell = cell.transpose(Image.FLIP_TOP_BOTTOM)
            field.paste(cell, ((i - first_x) * wide, (j - first_y) * tall))
    off_x, off_y = left - first_x * wide, top - first_y * tall
    return field.crop((off_x, off_y, off_x + left + wide + right,
                       off_y + top + tall + bottom))


def _soften(im: Image.Image, radius: float) -> Image.Image:
    """A wide blur done at a quarter of the size and scaled back: the mirrored edge is
    already continuous, so at these radii the two are indistinguishable and one of them
    costs a sixteenth of the arithmetic."""
    if radius < 0.5:
        return im
    if radius < 8.0:
        return im.filter(ImageFilter.GaussianBlur(radius))
    wide, tall = im.size
    small = im.resize((max(1, wide // 4), max(1, tall // 4)), Image.BOX)
    small = small.filter(ImageFilter.GaussianBlur(max(1.0, radius / 4.0)))
    return small.resize((wide, tall), Image.BILINEAR)


def _ramp(n: int, inner_from: int, inner_to: int, floor: int) -> Image.Image:
    """One row of a darkening ramp: 255 between the two seams, falling to `floor` outside."""
    n = max(1, n)
    values = bytearray(n)
    for i in range(n):
        if i < inner_from:
            span = max(1, inner_from)
            values[i] = int(round(floor + (255 - floor) * i / span))
        elif i >= inner_to:
            span = max(1, n - inner_to)
            values[i] = int(round(255 - (255 - floor) * (i - inner_to + 1) / span))
        else:
            values[i] = 255
    return Image.frombytes("L", (n, 1), bytes(values))


def _fade_mask(size, seams, floor: int) -> Image.Image:
    left, top, right, bottom = seams
    wide, tall = size
    inner_w, inner_h = wide - left - right, tall - top - bottom
    gain_x = _ramp(wide, left, left + inner_w, floor).resize((wide, tall), Image.NEAREST)
    gain_y = _ramp(tall, top, top + inner_h, floor).transpose(Image.TRANSPOSE)
    gain_y = gain_y.resize((wide, tall), Image.NEAREST)
    return ImageChops.darker(gain_x, gain_y)


def _edge_expand(im: Image.Image, args) -> Image.Image:
    """Grow the frame into its own edge. This is not outpainting: what arrives is the
    neighbouring background, mirrored, blurred and darkened, never new content."""
    flat = _shape("edge_expand", args)
    if len(flat) < 4:
        return im
    kind, amount, blur, fade = flat
    base = im if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    wide, tall = base.size
    pad = int(round(amount * min(wide, tall)))
    if pad <= 0:
        return im
    pad = min(pad, max(0, (MAX_EDGE - max(wide, tall)) // 2))
    if pad <= 0:
        return im
    side = int(kind) % len(EDGES)
    seams = {0: (pad, pad, pad, pad), 1: (0, pad, 0, 0), 2: (0, 0, 0, pad),
             3: (pad, 0, 0, 0), 4: (0, 0, pad, 0)}[side]
    left, top, right, bottom = seams
    final = (wide + left + right, tall + top + bottom)
    plate = _blank(base.mode, final)
    plate.paste(base, (left, top))
    keep = Image.new("L", final, 255)
    keep.paste(Image.new("L", (wide, tall), 0), (left, top))
    edge = _mirror(base, left, top, right, bottom)
    edge = _soften(edge, blur * 0.10 * min(wide, tall))
    body = edge.convert("RGB")
    if fade > 0.0:
        body = ImageChops.multiply(body,
                                   _fade_mask(final, seams, _byte(1.0 - fade)).convert("RGB"))
    out = Image.composite(body, plate.convert("RGB"), keep)
    if base.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(Image.composite(edge.getchannel("A"), plate.getchannel("A"), keep))
    return out


APPLIERS = {
    "draw": _draw,
    "sticker": _sticker,
    "curved_text": _arc,
    "shape_crop": _shape_crop,
    "bg_replace": _bg_replace,
    "glow_edge": _glow_edge,
    "edge_expand": _edge_expand,
}
