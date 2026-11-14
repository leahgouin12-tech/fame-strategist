"""What the frame is doing to her face - measured, not ranked.

The photo judge already reads exposure, focus and placement. This reads the face
region itself: how evenly it is lit, how far the two halves drift apart, how even
the tone is, how sharp it is against the backdrop. Every number here is a property
of the picture, so every one of them can be changed by moving a light or stepping
closer - none of them is a verdict on the person, and the page says so in those
words rather than in a footnote.

No face-landmark library is used or needed: a skin-tone mask plus a bounding box
answers the questions this module is allowed to ask. Anything that needed to know
where her eyebrow ends would be a different, and much less honest, product.
"""

from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageFilter, ImageStat

CONTRACT = (
    "This describes what the frame does to your face. It does not score your face, "
    "and it cannot: every number below is a property of the lighting, the lens and "
    "the backdrop, not of you."
)

# Working small keeps a pure-Python flood fill honest about its time.
WORK = 160
# Skin is the one hue family where the red-difference channel sits clearly above the
# blue-difference channel. A grey sky sits the other way round (measured: Cr-Cb = -9),
# which is what makes this rule worth writing down instead of guessing a wide box.
CHROMA_MIN = 8.0     # Cr minus Cb
CR_MIN = 132.0
CB_MAX = 155.0
Y_MIN = 70.0
MIN_BLOB = 12        # work-scale pixels: smaller than this is noise, not a face


@dataclass
class FaceRead:
    """One face region and what was measured inside it. None means not measurable."""

    found: bool
    box: tuple = (0, 0, 0, 0)
    frame: tuple = (0, 0)
    share: float = 0.0
    placed: str = "auto"
    fill: float = 0.0
    band: float = 1.0
    confident: bool = False
    symmetry: float | None = None
    light_fall: float | None = None
    tone_evenness: float | None = None
    clarity: float | None = None
    backdrop: float | None = None
    words: list = field(default_factory=list)
    fixes: list = field(default_factory=list)
    model_says: str = ""
    model_source: str = "not asked"

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items()}


def _skin_mask(rgb: Image.Image) -> Image.Image:
    """A 1/0 mask of skin-coloured pixels, in a work-sized box."""
    lum, blue, red = (list(c.getdata()) for c in rgb.convert("YCbCr").split())
    bits = bytearray(
        1 if (r - b >= CHROMA_MIN and r >= CR_MIN and b <= CB_MAX and v >= Y_MIN) else 0
        for v, b, r in zip(lum, blue, red)
    )
    mask = Image.frombytes("L", rgb.size, bytes(bits))
    # A pass of a 3x3 max closes the pinholes a sensor's noise leaves in real skin.
    return mask.point(lambda p: 255 if p else 0).filter(ImageFilter.MaxFilter(3))


def _blobs(mask: Image.Image) -> list:
    """Every connected skin block big enough to matter, as (x0, y1, x1, y1, size)."""
    w, h = mask.size
    px = mask.load()
    seen = bytearray(w * h)
    out = []
    for start in range(w * h):
        if seen[start]:
            continue
        seen[start] = 1
        stack = [start]
        x0 = x1 = start % w
        y0 = y1 = start // w
        size = 0
        while stack:
            i = stack.pop()
            x, y = i % w, i // w
            if x < x0:
                x0 = x
            if x > x1:
                x1 = x
            if y < y0:
                y0 = y
            if y > y1:
                y1 = y
            size += 1
            for j in (i - 1, i + 1, i - w, i + w):
                if 0 <= j < w * h and not seen[j] and px[j % w, j // w]:
                    seen[j] = 1
                    stack.append(j)
        if size >= MIN_BLOB:
            out.append((x0, y0, x1, y1, size))
    return out


def _touch(a: tuple, b: tuple) -> bool:
    """Close enough that both could be parts of the same face."""
    gap_x = max(a[0] - b[2], b[0] - a[2])
    gap_y = max(a[1] - b[3], b[1] - a[3])
    reach = 0.6 * max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1], 2)
    return gap_x <= reach and gap_y <= reach


def _merge(blobs: list) -> list:
    """Single-linkage groups, because a face is usually split by its own shadows."""
    boxes = [b[:4] for b in blobs]
    groups = [[b] for b in boxes]
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if any(_touch(a, b) for a in groups[i] for b in groups[j]):
                    groups[i] += groups[j]
                    del groups[j]
                    changed = True
                    break
            if changed:
                break
    return [(min(b[0] for b in g), min(b[1] for b in g),
             max(b[2] for b in g), max(b[3] for b in g)) for g in groups]


def _score(rgb: Image.Image, box: tuple) -> float:
    """How face-like a skin region is. Higher is better; only used to rank."""
    fill, band = _confidence(rgb, box)
    w, h = rgb.size
    x0, y0, x1, y1 = box
    aspect = (x1 - x0) / float(max(1, y1 - y0))
    points = fill * 2.0 + (1.0 - min(1.0, band)) * 1.5
    points -= abs(aspect - 0.72) * 1.2
    # A face sits above the middle of a full-body frame; the ground does not.
    centre_y = (y0 + y1) / 2.0 / h
    points -= max(0.0, centre_y - 0.62) * 2.0
    # A region spanning the whole width is a wall or a road, never a face.
    if (x1 - x0) / float(w) > 0.75 or (y1 - y0) / float(h) > 0.75:
        points -= 1.5
    return points


def _plausible(rgb: Image.Image, box: tuple) -> bool:
    x0, y0, x1, y1 = box
    w, h = rgb.size
    area = ((x1 - x0) * (y1 - y0)) / float(w * h)
    if area > 0.62 or area < 0.006:
        return False
    ratio = (x1 - x0) / float(max(1, y1 - y0))
    return 0.28 <= ratio <= 2.2


def face_box(rgb: Image.Image) -> tuple | None:
    """The most face-like skin region in full-size pixels, or None when there is none."""
    best, best_score = None, None
    for box in _candidates(rgb):
        score = _score(rgb, box)
        if best_score is None or score > best_score:
            best, best_score = box, score
    return best


LIGHT_BAND = 0.62


def light_box(rgb: Image.Image) -> tuple | None:
    """The brightest compact thing in the top of the frame, when the colour rule found nothing.

    The chroma rule needs skin that reads warmer than its background. A cool, underexposed
    street frame does not offer that - her cheek and the asphalt measure the same grey - and
    the only signal left is light: in a portrait the face is what the photographer lit. This
    is a place to look, not a claim, so read_file labels it and the words say so.
    """
    small = _scaled(rgb).convert("L").filter(ImageFilter.GaussianBlur(1.6))
    w, h = small.size
    band = max(8, int(h * LIGHT_BAND))
    rows = sorted(small.crop((0, 0, w, band)).getdata())
    if len(rows) < 40:
        return None
    need = max(rows[int(len(rows) * 0.80)], rows[len(rows) // 2] + 18)
    px = small.load()
    mask = Image.frombytes("L", (w, band),
                           bytes(bytearray(255 if px[x, y] >= need else 0
                                           for y in range(band) for x in range(w))))
    blobs = _blobs(mask.point(lambda p: 255 if p else 0).filter(ImageFilter.MaxFilter(3)))
    best, best_score = None, None
    for box in _merge(blobs) + [b[:4] for b in blobs]:
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        area = (bw * bh) / float(w * h)
        if not (0.004 <= area <= 0.14) or not (0.3 <= bw / float(max(1, bh)) <= 2.0):
            continue
        cx = (box[0] + box[2]) / 2.0 / w
        cy = (box[1] + box[3]) / 2.0 / h
        score = 1.0 - abs(cx - 0.5) * 1.6 - cy * 1.2 + min(1.0, area * 14)
        if best_score is None or score > best_score:
            best, best_score = box, score
    if best is None:
        return None
    scale = w / float(rgb.size[0])
    x0, y0, x1, y1 = best
    return (max(0, int(x0 / scale)), max(0, int(y0 / scale)),
            min(rgb.size[0], int((x1 + 1) / scale)), min(rgb.size[1], int((y1 + 1) / scale)))


def _scaled(rgb: Image.Image) -> Image.Image:
    w, h = rgb.size
    scale = min(1.0, WORK / max(w, h))
    return rgb if scale == 1.0 else rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))))


def _candidates(rgb: Image.Image) -> list:
    """Every plausible skin region, merged groups and their parts, in full-size pixels."""
    small = _scaled(rgb)
    scale = small.size[0] / float(rgb.size[0])
    blobs = _blobs(_skin_mask(small))
    out, seen = [], set()
    for box in _merge(blobs) + [b[:4] for b in blobs]:
        full = (max(0, int(box[0] / scale)), max(0, int(box[1] / scale)),
                min(rgb.size[0], int((box[2] + 1) / scale)),
                min(rgb.size[1], int((box[3] + 1) / scale)))
        if full in seen or not _plausible(rgb, full):
            continue
        seen.add(full)
        out.append(full)
    return out


def tap_box(rgb: Image.Image, fx: float, fy: float, size: float = 0.22) -> tuple:
    """The box she asked for, tightened to the colour region inside it when there is one.

    Why this is a window and not a detection: on her own photos the wall behind her
    measures the same colour as her cheek (face Y/Cb/Cr 64/124/134 against the wall's
    57/129/127), so every version of "grow while the colour matches" that I tried -
    flood fill, then row-by-row growth - walked straight off her face and into the
    street. A box she placed is not a guess about her face, and `size` lets her say how
    much of the frame it is. When the automatic pass did find a region under her finger,
    that region is tighter than the window and is used instead.
    """
    w, h = rgb.size
    px, py = fx * w, fy * h
    inside = [b for b in _candidates(rgb) if b[0] <= px <= b[2] and b[1] <= py <= b[3]]
    if inside:
        # The tightest region under her finger, not the first one: the merge step also
        # hands back groups that swallowed a neighbouring wall, and a wall is not a face.
        return min(inside, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    side = int(size * h)
    cx, cy = int(px), int(py) + int(side * 0.10)
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    return (x0, y0, min(w, x0 + side), min(h, y0 + side))


def _confidence(rgb: Image.Image, box: tuple) -> tuple:
    """How much of the box is skin-coloured, and whether it holds a dark feature band.

    A face is mostly skin and has eyes, brows and hair pulling one band of it much
    darker. A brick wall passes the colour test and fails the second - and on a graded
    overcast frame it can pass both, which is exactly why a box she placed is trusted
    over a box this module guessed.
    """
    small = _scaled(rgb)
    scale = small.size[0] / float(rgb.size[0])
    sb = tuple(int(v * scale) for v in box)
    mask = _skin_mask(small).crop(sb)
    fill = sum(1 for p in mask.getdata() if p) / float(max(1, mask.size[0] * mask.size[1]))
    grey = rgb.crop(box).convert("L").resize((48, 64))
    rows = [ImageStat.Stat(grey.crop((0, y, 48, y + 8))).mean[0] for y in range(0, 57, 8)]
    median = sorted(rows)[len(rows) // 2] or 1.0
    band = round(min(rows) / median, 2)
    return round(fill, 2), band


CONFIDENT_FILL = 0.42
CONFIDENT_BAND = 0.78


def _edge_density(im: Image.Image) -> float:
    return ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]


def _read_box(rgb: Image.Image, box: tuple, frame_edges: float, placed: str = "auto") -> FaceRead:
    x0, y0, x1, y1 = box
    crop = rgb.crop(box)
    cw, ch = crop.size
    grey = crop.convert("L")

    left = ImageStat.Stat(grey.crop((0, 0, cw // 2, ch))).mean[0]
    right = ImageStat.Stat(grey.crop((cw // 2, 0, cw, ch))).mean[0]
    fall = round((right - left) / 255.0 * 100.0, 1)

    half = grey.resize((96, 96))
    mirror = half.transpose(Image.FLIP_LEFT_RIGHT)
    sym = round(ImageStat.Stat(ImageChops.difference(half, mirror)).mean[0] / 255.0 * 100.0, 1)

    ycc = ImageStat.Stat(crop.convert("YCbCr"))
    tone = round(ycc.stddev[1], 1)

    edges = _edge_density(crop)
    clarity = round(edges / frame_edges, 2) if frame_edges else None

    back = _outside(rgb, box)
    backdrop = round(_edge_density(back) / edges, 2) if edges else None

    fill, dark = _confidence(rgb, box)
    read = FaceRead(
        found=True, box=box, placed=placed, fill=fill, band=dark,
        frame=rgb.size,
        confident=(fill >= CONFIDENT_FILL and dark <= CONFIDENT_BAND),
        share=round((cw * ch) / float(rgb.size[0] * rgb.size[1]) * 100.0, 1),
        symmetry=sym, light_fall=fall, tone_evenness=tone,
        clarity=clarity, backdrop=backdrop,
    )
    read.words = _words(read)
    read.fixes = _fixes(read)
    return read


def _outside(rgb: Image.Image, box: tuple) -> Image.Image:
    """Everything but the face, tiled onto one square so a single measurement covers it."""
    w, h = rgb.size
    x0, y0, x1, y1 = box
    parts = []
    if y0 > 4:
        parts.append(rgb.crop((0, 0, w, y0)))
    if h - y1 > 4:
        parts.append(rgb.crop((0, y1, w, h)))
    if x0 > 4:
        parts.append(rgb.crop((0, y0, x0, y1)))
    if w - x1 > 4:
        parts.append(rgb.crop((x1, y0, w, y1)))
    if not parts:
        return rgb
    side = 160
    out = Image.new("RGB", (side, side), (128, 128, 128))
    rows = (len(parts) + 1) // 2
    cols = -(-len(parts) // rows)
    cw, ch = max(1, side // cols), max(1, side // rows)
    for i, part in enumerate(parts):
        out.paste(part.resize((cw, ch)), ((i % cols) * cw, (i // cols) * ch))
    return out


def _words(read: FaceRead) -> list:
    """Plain sentences, each tied to the number that produced it."""
    if read.placed == "you placed it":
        out = [f"Measured inside the box you placed - {read.share:.0f}% of the frame. "
               "Every number below is measured there and nowhere else."]
    elif read.placed == "guessed from the light":
        out = [f"Nothing in this frame measured as skin colour, so the box went to the "
               f"brightest compact region in its top - {read.share:.0f}% of the frame. The "
               "numbers are measured inside that box, which is a guess about where a face "
               "would be: tap the face if this is not it."]
    elif read.confident:
        out = [f"A region covering {read.share:.0f}% of the frame was found by colour: "
               f"{read.fill:.0%} of it is skin and its darkest band sits at "
               f"{read.band:.2f} of the middle, which is what a face looks like to these "
               "two numbers."]
    else:
        out = [f"A region covering {read.share:.0f}% of the frame matched skin colour, but only "
               f"{read.fill:.0%} of it is skin and its darkest band is {read.band:.2f} of the "
               "middle. That is not confident enough to call a face - tap the face and this "
               "measures the box you chose instead."]
    if read.light_fall is not None and abs(read.light_fall) >= 4:
        side = "right" if read.light_fall > 0 else "left"
        out.append(f"One side of the face is {abs(read.light_fall):.0f}% brighter than the "
                   f"other - the {side} reads as the lit side.")
    elif read.light_fall is not None:
        out.append("Both sides of the face are lit within "
                   f"{abs(read.light_fall):.0f}% of each other.")
    if read.symmetry is not None:
        out.append(f"The two halves of the face differ by {read.symmetry:.0f}% when mirrored. "
                   "Lighting causes most of this; check the number above before reading "
                   "anything into it.")
    if read.tone_evenness is not None:
        spread = "even" if read.tone_evenness < 12 else "uneven"
        out.append(f"Colour spread across the skin is {read.tone_evenness:.1f} ({spread}) - "
                   "mixed colour temperature, usually two light sources.")
    if read.clarity is not None:
        where = "sharper" if read.clarity >= 1.0 else "softer"
        out.append(f"The face is {read.clarity:.2f}x the edge detail of the whole frame, so it "
                   f"reads {where} than its surroundings.")
    if read.backdrop is not None:
        busy = "busier" if read.backdrop >= 1.0 else "quieter"
        out.append(f"The backdrop carries {read.backdrop:.2f}x the detail of the face, so it is "
                   f"{busy} than the subject.")
    return out


def _fixes(read: FaceRead) -> list:
    """Only things a person can change before the next shot."""
    out = []
    if read.light_fall is not None and abs(read.light_fall) >= 10:
        out.append("Turn to face the light, or move the light in front of you instead of beside.")
    if read.tone_evenness is not None and read.tone_evenness >= 14:
        out.append("Kill one of the two colour sources - window light plus a ceiling bulb is the "
                   "usual cause of uneven colour.")
    if read.clarity is not None and read.clarity < 0.85:
        out.append("Focus is landing somewhere other than the face. Tap the face before shooting.")
    if read.backdrop is not None and read.backdrop > 1.25:
        out.append("The backdrop is busier than you are. Step eight feet off it, or turn sideways "
                   "to a plain wall.")
    if read.share < 6:
        out.append("The face is a small part of the frame. Close the distance or crop in.")
    return out


def read_file(path, engine=None, tap: tuple | None = None, size: float | None = None) -> FaceRead:
    """Measure one file. `tap` is (fraction_x, fraction_y) and `size` how much of the
    frame height her face takes - both come from her finger, not from a guess.

    If an engine is live it also describes the crop, always labelled as the model's
    words next to the numbers that were actually measured.
    """
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        if tap:
            box, placed = tap_box(rgb, tap[0], tap[1], size or 0.22), "you placed it"
        else:
            box, placed = face_box(rgb), "found by colour"
            if box is None:
                box, placed = light_box(rgb), "guessed from the light"
        if box is None:
            return FaceRead(
                found=False,
                words=["No region in this frame looked like a face - not to a colour mask, "
                       "and not as the brightest thing in the top of it. That is usually a "
                       "back view, heavy shadow, or a very close crop - not an error. "
                       "Tap the face and this measures the box you chose instead."])
        read = _read_box(rgb, box, _edge_density(rgb), placed)
        if engine is not None and getattr(engine, "name", "offline") != "offline":
            _ask_engine(engine, rgb, box, read)
    return read


def _ask_engine(engine, rgb: Image.Image, box: tuple, read: FaceRead) -> None:
    """The model describes; the numbers above still decide. Never a score."""
    import io

    crop = rgb.crop(box)
    if crop.size[0] > 768:
        crop = crop.resize((768, int(crop.size[1] * 768 / crop.size[0])))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=82)
    schema = {
        "type": "object",
        "required": ["lighting", "framing", "what_changed_it", "refuses"],
        "properties": {
            "lighting": {"type": "string"},
            "framing": {"type": "string"},
            "what_changed_it": {"type": "array", "items": {"type": "string"}},
            "refuses": {"type": "string"},
        },
    }
    try:
        data = engine.complete_json(
            "You are describing a photograph of a face. Say what the light, the lens and the "
            "backdrop are doing to it. Do not rate attractiveness, do not guess age, do not "
            "diagnose anything. Name the changes a photographer could make.",
            "Describe this crop.", schema, images=[("image/jpeg", buf.getvalue())])
    except Exception as exc:
        read.model_source = f"asked, got nothing usable ({type(exc).__name__})"
        return
    if not data:
        read.model_source = "asked, answered empty"
        return
    read.model_source = f"{engine.name} - describing the same crop the numbers measured"
    lines = [data.get("lighting", ""), data.get("framing", "")]
    lines += [f"change: {c}" for c in data.get("what_changed_it", [])[:3]]
    if data.get("refuses"):
        lines.append(f"it will not say: {data['refuses']}")
    read.model_says = " | ".join(x for x in lines if x)
