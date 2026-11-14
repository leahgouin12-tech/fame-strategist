"""Compositing: words on a photo, a second photo over it, mats, borders, signatures.

Tone sliders and a crop are only so much. This is the layer half of the editor, and it
is the reason a cover can be made here instead of in another app. Every measurement is a
fraction of the image, so the 900 px preview and the 4000 px export land in the same
place. A recipe entry is ["name", arg, arg...], the same shape edit.py and the other
media engines take.
"""

from pathlib import Path
import math

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)

# Set by the app at startup. Nothing in this module opens a file unless it is inside it.
ROOT: Path | None = None

MAX_EDGE = 6000          # no operation may hand back a frame wider or taller than this
SOURCE_EDGE = 2400       # a file from ROOT is read down to this, not in at full size
GRID_CELL = 1800         # a collage cell is a thumbnail, so it is not drawn bigger
MAX_CHARS = 600          # a longer string is a paste accident, not a caption
MAX_LINES = 24
MAX_TILES = 48           # one watermark signature repeats this many times at most
PROBE = 100              # face metrics are measured here, then scaled to her cap height
LEAD = 0.18              # gap between lines, as a fraction of one line

SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")

FONTS = {
    "display": [
        "C:/Windows/Fonts/ariblk.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "body": [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/corbel.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/micross.ttf",
    ],
    "mono": [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/lucon.ttf",
        "C:/Windows/Fonts/cour.ttf",
    ],
    "condensed": [
        "C:/Windows/Fonts/arialn.ttf",
        "C:/Windows/Fonts/bahnschrift.ttf",
        "C:/Windows/Fonts/segoeuil.ttf",
        "C:/Windows/Fonts/trebucbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
    "serif": [
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/constan.ttf",
        "C:/Windows/Fonts/pala.ttf",
    ],
}

LIMITS = {
    "text": 8,
    "overlay": 6,
    "frame": 1,
    "collage": 6,
    "watermark": 4,
}

SHAPE = {
    "text": ["group", 11, LIMITS["text"]],
    "overlay": ["group", 8, LIMITS["overlay"]],
    "frame": ["list", ["f", "f", "f", "f", "f", "f"]],
    "collage": ["list", ["s", "s", "f", "f", "f", "f"]],
    "watermark": ["group", 6, LIMITS["watermark"]],
}

CLAMP = {
    "text": [
        (0.0, 1.0), (0.0, 1.0), (0.01, 0.5),            # x, y, cap height
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),             # r, g, b
        (0.0, 0.5), (0.0, 1.0), (0.0, 2.0),             # stroke, shadow, align
        None, None,                                    # family, words
    ],
    "overlay": [
        None,                                          # name
        (0.0, 1.0), (0.0, 1.0), (0.02, 2.0),            # x, y, size
        (-360.0, 360.0), (0.0, 1.0), (0.0, 7.0), (0.0, 2.0),  # angle, opacity, blend, fit
    ],
    "frame": [
        (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),             # r, g, b
        (0.0, 0.4), (0.0, 0.25), (0.0, 0.5),            # mat, hairline, corner
    ],
    "collage": [
        None, None,                                    # first file, second file
        (1.0, 6.0), (0.0, 0.25), (0.0, 1.0), (0.0, 2.0),  # columns, gap, grey, fit
    ],
    "watermark": [
        None,                                          # words
        (0.0, 1.0), (0.0, 1.0), (0.01, 0.15),          # x, y, cap height
        (0.0, 1.0), (-60.0, 60.0),                     # opacity, tilt in degrees
    ],
}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _scaled(amount: float) -> list:
    """A whole-channel point table, because Image.point on a callable walks every pixel."""
    return [max(0, min(255, int(i * amount))) for i in range(256)]


def _one(a, slot) -> float | str:
    """One argument in its slot: text keeps its words, numbers keep their range."""
    if slot is None:
        return (a if isinstance(a, str) else "")[:MAX_CHARS]
    return min(max(_num(a), slot[0]), slot[1])


def _shape(name: str, args) -> list:
    """Trim a raw entry to this op's shape. Only whole groups survive, so a truncated
    tail cannot slide every later argument one slot to the left."""
    spec = SHAPE[name]
    slots = CLAMP[name]
    raw = list(args or [])
    if spec[0] == "group":
        k, n = spec[1], spec[2]
        out = []
        for i in range(0, k * n, k):
            if i + k > len(raw):
                break
            out += [_one(raw[i + j], slots[j % len(slots)]) for j in range(k)]
        return out
    return [_one(raw[i], slots[i]) for i in range(min(len(raw), len(slots)))]


def _groups(flat: list, k: int) -> list:
    return [flat[i:i + k] for i in range(0, len(flat) - k + 1, k)]


def _try_face(path: str, cap: int):
    try:
        probe = ImageFont.truetype(path, PROBE)
        box = probe.getbbox("H")
        tall = box[3] - box[1]
        size = int(round(PROBE * cap / tall)) if tall > 0 else cap
        return ImageFont.truetype(path, max(1, size))
    except (OSError, ValueError, ZeroDivisionError):
        return None


def _default_face(cap: int):
    try:
        return ImageFont.load_default(size=cap)
    except (OSError, TypeError, ValueError):
        return ImageFont.load_default()


_faces: dict = {}


def _font(family, cap) -> ImageFont.ImageFont:
    """The face she named for this role, sized so a capital letter is `cap` pixels tall.

    The size is asked for in cap height rather than points, so the same slider lands on
    the same optical size whether her caption is all caps or mixed case.
    """
    cap = int(max(4, min(_num(cap), MAX_EDGE)))
    key = (family if isinstance(family, str) else "", cap)
    hit = _faces.get(key)
    if hit is not None:
        return hit
    face = None
    for path in FONTS.get(key[0]) or FONTS["body"]:
        face = _try_face(path, cap)
        if face is not None:
            break
    if face is None:
        face = _default_face(cap)
    if len(_faces) > 128:  # previews stream new sizes, so the cache is not left to grow
        _faces.clear()
    _faces[key] = face
    return face


def _width(font, text: str) -> float:
    try:
        return float(font.getlength(text))
    except (AttributeError, ValueError):
        return 0.0


def _metrics(font):
    try:
        ascent, descent = font.getmetrics()
    except (AttributeError, ValueError):
        ascent, descent = 8, 2
    return max(1, int(ascent)), max(1, int(descent))


def _lines(text: str, font, max_w: float) -> list[str]:
    """Her hard breaks first, then any line that would run off the frame is wrapped."""
    out: list[str] = []
    for raw in str(text).split("\n")[:MAX_LINES]:
        words = raw.split()
        if not words:
            out.append("")
            continue
        line = words[0]
        for word in words[1:]:
            if line and _width(font, line + " " + word) > max_w:
                out.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        out.append(line)
    return out[:MAX_LINES]


def _ink(draw, xy, text, font, fill, stroke_px, stroke_fill):
    if stroke_px > 0:
        try:
            draw.text(xy, text, font=font, fill=fill,
                      stroke_width=stroke_px, stroke_fill=stroke_fill)
            return
        except ValueError:
            pass  # the last-resort built-in face cannot be outlined
    draw.text(xy, text, font=font, fill=fill)


def _tile(lines, font, align, fill, stroke_px, stroke_fill, extra=0):
    """The words as their own small RGBA tile, so a caption on a 4000 px frame costs
    the size of the caption and not the size of the frame."""
    ascent, descent = _metrics(font)
    line_h = ascent + descent
    lead = max(1, int(round(LEAD * line_h)))
    widths = [_width(font, t) for t in lines]
    block_w = max(1, int(round(max(widths))))
    block_h = line_h * len(lines) + lead * max(0, len(lines) - 1)
    margin = stroke_px + max(1, int(round(0.15 * line_h))) + max(0, int(extra))
    tile = Image.new("RGBA", (block_w + 2 * margin, block_h + 2 * margin), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    for i, text in enumerate(lines):
        if not text:
            continue
        if align == 0:
            x = margin
        elif align == 2:
            x = margin + block_w - widths[i]
        else:
            x = margin + (block_w - widths[i]) / 2.0
        _ink(draw, (x, margin + i * (line_h + lead)), text, font, fill, stroke_px, stroke_fill)
    return tile, margin


def _shade(tile, amount: float, cap: float):
    """The shadow is the glyph coverage itself, blackened, nudged and softened."""
    alpha = tile.getchannel("A").point(_scaled(0.85 * amount))
    shade = Image.new("RGBA", tile.size, (0, 0, 0, 0))
    shade.putalpha(alpha)
    off = max(1, int(round(0.14 * amount * cap)))
    return shade.filter(ImageFilter.GaussianBlur(max(1.0, 0.6 * off))), off


def _stamp(canvas, tile, left, top):
    """Over-composite a tile, clipping at the frame edge instead of complaining."""
    box = (int(round(left)), int(round(top)))
    if box[0] >= canvas.width or box[1] >= canvas.height:
        return
    if box[0] + tile.width <= 0 or box[1] + tile.height <= 0:
        return
    canvas.paste(tile, box, tile.getchannel("A"))


def _text(im: Image.Image, args) -> Image.Image:
    flat = _shape("text", args)
    wanted = [g for g in _groups(flat, 11) if g[10].strip()]
    if not wanted:
        return im
    work = im.copy() if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    for x, y, size, r, g, b, stroke, shadow, align, family, words in wanted:
        cap = max(4.0, size * im.height)  # the contract: size is a fraction of height here
        font = _font(family, cap)
        lines = _lines(words, font, im.width * 0.96)
        fill = (int(round(255 * r)), int(round(255 * g)), int(round(255 * b)), 255)
        stroke_px = int(round(stroke * cap))
        off = max(1, int(round(0.14 * shadow * cap))) if shadow > 0 else 0
        tile, _ = _tile(lines, font, int(align) % 3, fill, stroke_px, (0, 0, 0, 255), off)
        left, top = x * im.width - tile.width / 2.0, y * im.height - tile.height / 2.0
        if shadow > 0:
            shade, nudge = _shade(tile, shadow, cap)
            _stamp(work, shade, left + nudge, top + nudge)
        _stamp(work, tile, left, top)
    return work


def _asset(name):
    """A file inside ROOT, or nothing at all. The name is a bare file name: any
    separator, any "..", any drive, anything that resolves out of ROOT is refused."""
    if ROOT is None or not isinstance(name, str):
        return None
    text = name.strip()
    if not text or len(text) > MAX_CHARS or any(c in text for c in ("/", "\\", ":", "\x00")):
        return None
    if ".." in text or not text.lower().endswith(SUFFIXES):
        return None
    try:
        root = Path(ROOT).resolve()
        spot = (root / text).resolve()
    except (OSError, ValueError):
        return None
    if spot.parent != root or not spot.is_file():
        return None
    try:
        with Image.open(spot) as raw:
            keep = raw.mode in ("RGBA", "LA", "Pa") or raw.info.get("transparency") is not None
            frame = ImageOps.exif_transpose(raw)
            frame.load()
    except (OSError, ValueError, IndexError):
        return None
    if max(frame.size) > SOURCE_EDGE:
        scale = SOURCE_EDGE / max(frame.size)
        frame = _resize(frame, (frame.width * scale, frame.height * scale))
    return frame.convert("RGBA" if keep else "RGB")


def _resize(src, size):
    """LANCZOS when shrinking, since it is the only one that resamples honestly, and
    BILINEAR when growing, where it costs a fraction as much and looks the same."""
    if tuple(size) == src.size:
        return src
    shrinking = size[0] * size[1] < src.width * src.height
    return src.resize((max(1, int(size[0])), max(1, int(size[1]))),
                      Image.LANCZOS if shrinking else Image.BILINEAR)


def _project(src, canvas, cx, cy, size, angle, fit):
    """The file resampled once straight into the patch of canvas it will be seen on.

    Scale, rotation and crop are one map, so a full-bleed layer on a 4000 px export
    costs that patch instead of three whole frames of intermediates, and a stamp-sized
    sticker on a big file costs the sticker.
    """
    wide, tall = canvas
    crop = src if src.mode in ("RGB", "RGBA") else src.convert("RGB")
    sw, sh = max(1, crop.width), max(1, crop.height)
    # the contract holds here too: one size, measured off the short edge, so the box is
    # square and a landscape file simply loses its sides to the crop
    edge = max(2.0, size * min(wide, tall))
    bw, bh = edge, edge
    if fit == 2:
        fx, fy = sw / bw, sh / bh
    else:
        scale = max(bw / sw, bh / sh) if fit == 0 else min(bw / sw, bh / sh)
        if fit == 0:  # cover throws away the edges of the file that would not fit the box
            cw, ch = min(sw, bw / scale), min(sh, bh / scale)
            left, top = (sw - cw) / 2.0, (sh - ch) / 2.0
            crop = crop.crop((int(left), int(top), int(left + cw), int(top + ch)))
        fx = fy = 1.0 / scale
    if crop.width < 1 or crop.height < 1:
        return None
    sw, sh = crop.width, crop.height
    lw, lh = sw / fx, sh / fy
    rad = math.radians(angle)
    co, si = math.cos(rad), math.sin(rad)
    # the box the rotated layer lands in, clipped to what she can actually see
    x0, y0 = int(math.floor(cx - (lw * abs(co) + lh * abs(si)) / 2.0)), \
             int(math.floor(cy - (lw * abs(si) + lh * abs(co)) / 2.0))
    x1, y1 = int(math.ceil(x0 + lw * abs(co) + lh * abs(si))), \
             int(math.ceil(y0 + lw * abs(si) + lh * abs(co)))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(wide, x1), min(tall, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    if abs(si) < 1e-9 and co > 0.0:
        # square on, so one plain resample is the same map at a third of the cost
        u0 = min(1.0, max(0.0, (x0 - (cx - lw / 2.0)) / lw))
        u1 = min(1.0, max(0.0, (x1 - (cx - lw / 2.0)) / lw))
        v0 = min(1.0, max(0.0, (y0 - (cy - lh / 2.0)) / lh))
        v1 = min(1.0, max(0.0, (y1 - (cy - lh / 2.0)) / lh))
        box = (int(u0 * sw), int(v0 * sh), max(int(u0 * sw) + 1, int(math.ceil(u1 * sw))),
               max(int(v0 * sh) + 1, int(math.ceil(v1 * sh))))
        return _resize(crop.crop(box), (x1 - x0, y1 - y0)), x0, y0
    need = max(2.0, 1.2 * max(x1 - x0, y1 - y0))
    if max(sw, sh) > 2 * need:  # read the file down before resampling it into the patch
        k = need / max(sw, sh)
        crop = _resize(crop, (sw * k, sh * k))
        fx, fy = fx * k, fy * k
    ox, oy = x0 - cx, y0 - cy
    a, b = fx * co, -fx * si
    d, e = fy * si, fy * co
    region = crop.transform((x1 - x0, y1 - y0), Image.AFFINE, (
        a, b, crop.width / 2.0 + a * ox + b * oy,
        d, e, crop.height / 2.0 + d * ox + e * oy,
    ), resample=Image.BILINEAR)
    return region, x0, y0


def _overlay(im: Image.Image, args) -> Image.Image:
    flat = _shape("overlay", args)
    out = im if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    for name, x, y, size, angle, opacity, blend, fit in _groups(flat, 8):
        src = _asset(name)
        if src is None or opacity <= 0:
            continue
        got = _project(src, out.size, x * out.width, y * out.height, size, angle, int(fit) % 3)
        if got is None:
            continue
        region, left, top = got
        out = _blend_into(out, region, left, top, int(blend) % 8, opacity)
    return out


_MIX = {
    1: ImageChops.multiply,
    2: ImageChops.screen,
    3: ImageChops.overlay,
    4: ImageChops.soft_light,
    5: ImageChops.difference,
    6: ImageChops.lighter,
    7: ImageChops.darker,
}


def _mix(mode: int, base, layer):
    """image1 is always the print underneath, so the named modes read in one order.
    Pillow 13 covers seven of the eight in C; only a plain paste needs writing."""
    fn = _MIX.get(mode)
    return fn(base, layer) if fn else layer


def _coverage(piece, opacity: float):
    """How much of the print the layer is allowed to hide, or None when it hides all."""
    alpha = piece.getchannel("A") if "A" in piece.getbands() else None
    if alpha is not None:
        return alpha.point(_scaled(opacity)) if opacity < 1.0 else alpha
    return None if opacity >= 1.0 else Image.new("L", piece.size, int(round(255 * opacity)))


def _blend_into(base, layer, left: int, top: int, mode: int, opacity: float) -> Image.Image:
    """Lay the patch over the frame, but only work inside the box it actually covers, so
    a stamp-sized layer on a 4000 px export costs a stamp-sized calculation."""
    out = base.copy()
    box = (max(0, left), max(0, top),
           min(out.width, left + layer.width), min(out.height, top + layer.height))
    if box[2] <= box[0] or box[3] <= box[1]:
        return out
    piece = layer.crop((box[0] - left, box[1] - top, box[2] - left, box[3] - top))
    mask = _coverage(piece, opacity)
    under = out.crop(box)
    result = piece if mode == 0 else _mix(mode, under if under.mode == piece.mode
                                          else under.convert(piece.mode), piece)
    if out.mode == "RGBA":
        # a rounded frame keeps the corner it already cut, so only the colour is replaced
        result = Image.merge("RGBA", (*result.convert("RGB").split(), under.getchannel("A")))
    elif result.mode != "RGB":
        result = result.convert("RGB")
    out.paste(result, box, mask)
    return out


def _mat(size, pad, radius, alpha):
    """The alpha band a matted frame deserves: the rounded outline, the print's own cut,
    or the two multiplied. None means nothing is transparent and the frame stays RGB."""
    wide, tall = size
    rounded = None
    if radius >= 2:
        rounded = Image.new("L", size, 0)
        ImageDraw.Draw(rounded).rounded_rectangle([0, 0, wide - 1, tall - 1],
                                                  radius=min(radius, min(size) // 2), fill=255)
    if alpha is None:
        return rounded
    cut = Image.new("L", size, 255)
    cut.paste(alpha, (pad, pad))  # the mat is solid, the print keeps whatever it cut itself
    return ImageChops.darker(rounded, cut) if rounded is not None else cut


def _frame(im: Image.Image, args) -> Image.Image:
    flat = _shape("frame", args)
    if len(flat) < 6:
        return im
    r, g, b, pad, border, corner = flat
    base = im.convert("RGB")
    alpha = im.getchannel("A") if "A" in im.getbands() else None
    short = min(base.size)
    colour = tuple(int(round(255 * v)) for v in (r, g, b))
    room = max(0, (MAX_EDGE - max(base.size)) // 2)
    pad_px = min(int(round(pad * short)), room)
    line_px = min(int(round(border * short)), min(base.size) // 2)
    radius = int(round(corner * short))
    if pad_px <= 0 and line_px <= 0 and radius < 2:
        return im
    wide, tall = base.width + 2 * pad_px, base.height + 2 * pad_px
    out = Image.new("RGB", (wide, tall), colour)
    out.paste(base, (pad_px, pad_px))
    # The hairline sits in the mat, flush against the print; with no mat it lands on the
    # photo itself, which is the thin coloured border she actually uses.
    if line_px >= 1:
        draw = ImageDraw.Draw(out)
        inset = max(0, pad_px - line_px)
        draw.rectangle([inset, inset, wide - 1 - inset, tall - 1 - inset],
                       outline=colour, width=line_px)
    mask = _mat((wide, tall), pad_px, radius, alpha)
    if mask is None:
        return out
    out = out.convert("RGBA")
    out.putalpha(mask)
    return out


def _cell(src, size: int, fit: int, colour) -> Image.Image:
    """One tile, always exactly cell-sized, so the grid stays even whatever loaded."""
    sw, sh = max(1, src.width), max(1, src.height)
    if fit == 2:
        return _resize(src.convert("RGB"), (size, size))
    scale = max(size / sw, size / sh) if fit == 0 else min(size / sw, size / sh)
    wide, tall = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    got = _resize(src.convert("RGB"), (wide, tall))
    if fit == 0:
        left, top = (wide - size) // 2, (tall - size) // 2
        return got.crop((left, top, left + size, top + size))
    if (wide, tall) == (size, size):
        return got
    out = Image.new("RGB", (size, size), colour)
    out.paste(got, ((size - wide) // 2, (size - tall) // 2))
    return out


def _collage(im: Image.Image, args) -> Image.Image:
    flat = _shape("collage", args)
    if len(flat) < 6:
        return im
    first, second, cells, gap, bg, mode = flat
    picked = [got for got in (_asset(first), _asset(second)) if got is not None]
    if not picked:
        return im
    tiles = [im, *picked][: LIMITS["collage"]]
    cols = max(1, min(LIMITS["collage"], int(round(cells))))
    rows = int(math.ceil(len(tiles) / cols))
    short = min(im.size)
    # the gap is bounded first, so the cell floor below can never push the sheet past MAX_EDGE
    gap_px = max(0, min(int(round(gap * short)),
                        (MAX_EDGE - 16 * cols) // (cols + 1),
                        (MAX_EDGE - 16 * rows) // (rows + 1)))
    grey = int(round(255 * bg))
    cell = max(16, min(short, GRID_CELL,
                       (MAX_EDGE - (cols + 1) * gap_px) // cols,
                       (MAX_EDGE - (rows + 1) * gap_px) // rows))
    fit = int(mode) % 3
    out = Image.new("RGB", (cols * cell + (cols + 1) * gap_px,
                            rows * cell + (rows + 1) * gap_px), (grey, grey, grey))
    for i, tile in enumerate(tiles):
        col, row = i % cols, i // cols
        out.paste(_cell(tile, cell, fit, (grey, grey, grey)),
                  (gap_px + col * (cell + gap_px), gap_px + row * (cell + gap_px)))
    return out


def _watermark(im: Image.Image, args) -> Image.Image:
    flat = _shape("watermark", args)
    wanted = [g for g in _groups(flat, 6) if g[0].strip()]
    if not wanted:
        return im
    work = im.copy() if im.mode in ("RGB", "RGBA") else im.convert("RGB")
    wide, tall = work.size
    for words, x, y, size, opacity, tilt in wanted:
        cap = max(4.0, size * min(wide, tall))
        font = _font("body", cap)
        tile, _ = _tile(_lines(words, font, wide), font, 1, (255, 255, 255, 255), 0, None)
        if abs(tilt) > 0.5:  # the marks lean the way she asked for them to lean
            tile = tile.rotate(tilt, resample=Image.BICUBIC, expand=True)
        if opacity < 1.0:
            tile.putalpha(tile.getchannel("A").point(_scaled(opacity)))
        step_x = tile.width + max(1, int(round(cap)))
        step_y = tile.height + max(1, int(round(1.5 * cap)))
        cols = max(1, int(wide // step_x) + 1)
        rows = max(1, int(tall // step_y) + 1)
        while cols * rows > MAX_TILES:  # thin the grid rather than stop halfway across
            if cols >= rows:
                cols = max(1, cols // 2)
                step_x *= 2
            else:
                rows = max(1, rows // 2)
                step_y *= 2
        origin_x, origin_y = x * wide, y * tall
        half_w, half_h = tile.width / 2.0, tile.height / 2.0
        placed = 0
        for row in range(-(rows // 2), rows // 2 + 1):
            for col in range(-(cols // 2), cols // 2 + 1):
                if placed >= MAX_TILES:
                    break
                px = origin_x + col * step_x + row * step_x * 0.5  # the row shift is the diagonal
                py = origin_y + row * step_y
                if (px - half_w < 0.0 or py - half_h < 0.0
                        or px + half_w > wide or py + half_h > tall):
                    continue  # a stamp never hangs off the edge of the print
                _stamp(work, tile, px - half_w, py - half_h)
                placed += 1
            if placed >= MAX_TILES:
                break
    return work


APPLIERS = {
    "text": _text,
    "overlay": _overlay,
    "frame": _frame,
    "collage": _collage,
    "watermark": _watermark,
}
