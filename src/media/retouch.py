"""The brush maths for Facetune-class retouching: smooth, matte, dodge, tint, warp.

Classical Pillow only, and every stroke works inside its own disc's bounding box;
SHAPE, CLAMP and LIMITS below are the recipe contract shared with the registry,
the routes and the studio UI. A group of strokes is one flat list of floats.
"""

import math

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageMath

FEATHER = 0.45         # share of the radius over which the brush mask fades to nothing
WARP_K = 0.35          # fraction of the radius a full-strength warp moves a pixel
DODGE_GAIN = 0.55      # widest multiplicative swing of the dodge/burn brush at amount 1

# Per-op, per-position min/max inside one group of args.
# warp group = x, y, size, amount, mode, feather, angle: Pillow 13's MESH maps cell
# quads, so the disc's rim is held still by the smoothstep field, not by triangles.
# slim group = the same seven plus stretch, and three times the reach on slot 3.
CLAMP = {
    "smooth":   [(0.0, 1.0), (0.0, 1.0), (0.005, 0.60), (0.0, 1.0)],
    "texture":  [(0.0, 1.0), (0.0, 1.0), (0.005, 0.60), (0.0, 1.0)],
    "matte":    [(0.0, 1.0), (0.0, 1.0), (0.005, 0.50), (0.0, 1.0)],
    "whiten":   [(0.0, 1.0), (0.0, 1.0), (0.005, 0.25), (0.0, 1.0)],
    "brighten": [(0.0, 1.0), (0.0, 1.0), (0.005, 0.50), (-1.0, 1.0), (0.0, 1.0)],
    "tint":     [(0.0, 1.0), (0.0, 1.0), (0.005, 0.50), (0.0, 1.0), (0.0, 360.0), (0.0, 1.0)],
    "warp":     [(0.0, 1.0), (0.0, 1.0), (0.010, 0.80), (-1.0, 1.0), (0.0, 2.0), (0.05, 1.0), (0.0, 360.0)],
    "slim":     [(0.0, 1.0), (0.0, 1.0), (0.010, 0.90), (-3.0, 3.0), (0.0, 2.0), (0.05, 1.0),
                 (0.0, 360.0), (0.15, 6.0)],
    "eyes":     [(0.0, 1.0), (0.0, 1.0), (0.005, 0.12), (0.0, 1.0)],
}

# The narrowest a mesh quad may get under a guarded stroke, as a share of its rest width.
# Below this the warp is no longer moving pixels, it is laying them over each other.
HOLD = 0.15

# Max strokes per op name, so a hand-edited recipe cannot freeze the machine.
LIMITS = {
    "smooth": 60, "texture": 60, "matte": 60, "whiten": 60,
    "brighten": 60, "tint": 60, "warp": 40, "slim": 40, "eyes": 40,
}

SHAPE = {name: ["group", len(rng), LIMITS[name]] for name, rng in CLAMP.items()}


def _rgb(im):
    return im if im.mode == "RGB" else im.convert("RGB")


def _lut(fn):
    return [max(0, min(255, int(round(fn(i))))) for i in range(256)]


def _fade(t):
    return t * t * (3.0 - 2.0 * t)


def _ramp(lo, hi):
    """LUT: 0 below lo, 255 above hi, smooth between."""
    return _lut(lambda v: 255.0 * _fade(max(0.0, min(1.0, (v - lo) / (hi - lo)))))


def _fall(lo, hi):
    """LUT: 255 below lo, 0 above hi, smooth between."""
    return _lut(lambda v: 255.0 * (1.0 - _fade(max(0.0, min(1.0, (v - lo) / (hi - lo))))))


def _strokes(args, name):
    """One op's flat args -> complete clamped groups; junk, extras and tails vanish."""
    k = len(CLAMP[name])
    rng = CLAMP[name]
    try:
        n = min(len(args), k * LIMITS[name])
    except TypeError:
        return []
    out = []
    for i in range(0, n - k + 1, k):
        vals, ok = [], True
        for j in range(k):
            try:
                f = float(args[i + j])
            except (TypeError, ValueError):
                ok = False
                break
            if not math.isfinite(f):
                ok = False
                break
            lo, hi = rng[j]
            vals.append(min(max(f, lo), hi))
        if ok:
            out.append(vals)
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


def _mask(bw, bh, cx, cy, r, feather=FEATHER, amount=1.0):
    """Feathered disc as an L image the size of the brush box; None if all zero.

    Built on a 96x96 grid and stretched: the weight is exactly 0 from q = 1 outward,
    which is what lets every op leave untouched pixels byte-identical.
    """
    n = 96
    px = bytearray(n * n)
    top = 0
    for j in range(n):
        dy = (j / (n - 1)) * bh - cy
        for i in range(n):
            dx = (i / (n - 1)) * bw - cx
            q = math.hypot(dx, dy) / r
            t = max(0.0, min(1.0, (1.0 - q) / feather))
            px[top + i] = max(0, min(255, int(round(255.0 * amount * _fade(t)))))
        top += n
    if max(px) == 0:
        return None
    return Image.frombytes("L", (n, n), bytes(px)).resize((bw, bh), Image.BILINEAR)


def _median_in_disc(lum, cxl, cyl, r):
    """Median luma of the disc itself, on a subsample so a 4000 px brush stays quick."""
    pts = []
    step = max(1, int(r / 40))
    w, h = lum.size
    x_lo, x_hi = max(0, int(cxl - r)), min(w, int(cxl + r) + 1)
    rr = r * r
    for yy in range(max(0, int(cyl - r)), min(h, int(cyl + r) + 1), step):
        for xx in range(x_lo, x_hi, step):
            if (xx - cxl) ** 2 + (yy - cyl) ** 2 <= rr:
                pts.append(lum.getpixel((xx, yy)))
    if not pts:
        return 128
    pts.sort()
    return pts[len(pts) // 2]


def _smooth(im, args):
    out = _rgb(im)
    base = im
    for st in _strokes(args, "smooth"):
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r, amount=st[3])
        if mask is None:
            continue
        # Median holds the large shading and real edges; a small blur settles what it leaves.
        soft = crop.filter(ImageFilter.MedianFilter(5 if r < 140 else 7))
        soft = soft.filter(ImageFilter.GaussianBlur(min(4.0, max(0.6, r / 100.0))))
        out = base.copy() if out is base else out
        out.paste(Image.composite(soft, crop, mask), box)
    return out


def _texture(im, args):
    out = _rgb(im)
    base = im
    for st in _strokes(args, "texture"):
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r, amount=st[3])
        if mask is None:
            continue
        blur = crop.filter(ImageFilter.GaussianBlur(max(1.0, min(4.0, r / 80.0))))
        # add the positive high-pass then subtract the negative one: that is the signed
        # detail layer, since only one of the two can be non-zero at a pixel.
        up = ImageChops.add(crop, ImageChops.subtract(crop, blur))
        enh = ImageChops.subtract(up, ImageChops.subtract(blur, crop))
        out = base.copy() if out is base else out
        out.paste(Image.composite(enh, crop, mask), box)
    return out


def _matte(im, args):
    out = _rgb(im)
    base = im
    for st in _strokes(args, "matte"):
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r, amount=st[3])
        if mask is None:
            continue
        lum = crop.convert("L")
        sat = crop.convert("HSV").split()[1]
        gate = ImageChops.multiply(mask, lum.point(_ramp(120.0, 200.0)))
        gate = ImageChops.multiply(gate, sat.point(_fall(50.0, 140.0)))
        med = _median_in_disc(lum, cx - box[0], cy - box[1], r)
        up = ImageChops.subtract(Image.new("L", crop.size, med), lum)
        dn = ImageChops.subtract(lum, Image.new("L", crop.size, med))
        add = ImageChops.multiply(gate, up)
        cut = ImageChops.multiply(gate, dn)
        # the same delta on all three channels: brightness moves, hue stays put.
        out = base.copy() if out is base else out
        out.paste(Image.merge("RGB", tuple(
            ImageChops.subtract(ImageChops.add(c, add), cut) for c in crop.split())), box)
    return out


def _whiten(im, args):
    out = _rgb(im)
    base = im
    for st in _strokes(args, "whiten"):
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r, amount=st[3])
        if mask is None:
            continue
        gate = ImageChops.multiply(mask, crop.convert("L").point(_ramp(140.0, 225.0)))
        lift = gate.point(_lut(lambda v: v * 0.11))
        trim = gate.point(_lut(lambda v: v * 0.09))
        blue = gate.point(_lut(lambda v: v * 0.16))
        r_, g_, b_ = crop.split()
        out = base.copy() if out is base else out
        out.paste(Image.merge("RGB", (
            ImageChops.subtract(ImageChops.add(r_, gate.point(_lut(lambda v: v * 0.04))), trim),
            ImageChops.add(g_, lift),
            ImageChops.add(ImageChops.add(b_, lift), blue))), box)
    return out


def _brighten(im, args):
    out = _rgb(im)
    base = im
    for st in _strokes(args, "brighten"):
        amount, mid = st[3], st[4]
        if abs(amount) < 1e-4:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r)
        if mask is None:
            continue
        c, band = mid * 255.0, 78.0
        gate = ImageChops.multiply(
            mask, crop.convert("L").point(
                _lut(lambda v: 255.0 * _fade(max(0.0, 1.0 - abs(v - c) / band)))))
        f = gate.point(_lut(lambda v: v * DODGE_GAIN * abs(amount)))
        chs = []
        for ch in crop.split():
            delta = ImageChops.multiply(ch, f)
            chs.append(ImageChops.add(ch, delta) if amount > 0 else ImageChops.subtract(ch, delta))
        out = base.copy() if out is base else out
        out.paste(Image.merge("RGB", tuple(chs)), box)
    return out


def _tint(im, args):
    out = _rgb(im)
    base = im
    for st in _strokes(args, "tint"):
        amount, hue, sat = st[3], st[4], st[5]
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
        alpha = ImageChops.multiply(mask, s_.point(_ramp(25.0, 95.0))).point(
            _lut(lambda v: v * amount))
        if alpha.getbbox() is None:
            continue
        k = alpha.convert("F")
        ht = int(round(hue / 360.0 * 255.0))
        # Shortest arc toward the target hue. The wheel is 256 wide, so the offset has to
        # be shifted by half of it (+384 = one full turn plus that half) before the
        # modulo: with +256 instead, a 280° request took the long way round and came out
        # green. C's fmod then never sees a negative.
        new_h = ImageMath.unsafe_eval(
            "convert((h + ((((ht - h + 384) % 256) - 128) * (k / 255.0)) + 256) % 256, 'L')",
            h=h_.convert("I"), ht=ht, k=k)
        new_s = ImageMath.unsafe_eval(
            "convert(s * (1.0 + (k / 255.0) * (0.9 * s2)), 'L')", s=s_.convert("I"), k=k, s2=sat)
        tinted = Image.merge("HSV", (new_h, new_s, v_)).convert("RGB")
        out = base.copy() if out is base else out
        out.paste(Image.composite(tinted, crop, alpha), box)
    return out


def _warp_field(px, py, cx, cy, ra, rb, ca, sa, amount, mode, feather):
    """Where a pixel inside the brush came from.

    `ang` is the direction the move acts along; the oval runs across it, so a 0-degree
    axis on a tall brush is one drag down the side of a waist. With a round brush and
    ang = 0 this is the original horizontal pinch, slot for slot.
    """
    dx, dy = px - cx, py - cy
    a = dx * ca + dy * sa
    b = dy * ca - dx * sa
    q = math.hypot(a / ra, b / rb)
    if q >= 1.0:
        return 0.0, 0.0
    w = _fade(min(1.0, (1.0 - q) / feather))
    if mode == 2:
        s = amount * 0.3 * min(ra, rb) * w
        return s * ca, s * sa
    oa = amount * WARP_K * a * w
    ob = 0.0 if mode == 0 else amount * WARP_K * b * w
    return oa * ca - ob * sa, oa * sa + ob * ca


def _brush(stroke, w, h, stretch=1.0, ang=0.0):
    """Centre, semi-axes, rotation and the box a stroke has to read, or None if nonsense.

    The box is the axis-aligned bound of the rotated oval, so a brush turned 45 degrees
    still crops enough of the frame to cover itself.
    """
    r = 0.5 * stroke[2] * min(w, h)
    if r < 2.0:
        return None
    cx, cy = stroke[0] * w, stroke[1] * h
    st = max(0.05, stretch)
    ra, rb = r, r * st
    ca, sa = math.cos(ang), math.sin(ang)
    ex = math.hypot(ra * ca, rb * sa)
    ey = math.hypot(ra * sa, rb * ca)
    box = (max(0, int(math.floor(cx - ex))), max(0, int(math.floor(cy - ey))),
           min(w, int(math.ceil(cx + ex))), min(h, int(math.ceil(cy + ey))))
    if box[2] - box[0] < 3 or box[3] - box[1] < 3:
        return None
    return box, cx, cy, ra, rb, ca, sa


def _brush_mask(bw, bh, cx, cy, ra, rb, ca, sa, feather=0.12):
    """The feathered oval as an L image the size of the box; None if it is all zero.

    Weight is exactly 0 from q = 1 outward, which is what lets a reshape leave every
    pixel outside its own brush byte-identical.
    """
    n = 96
    px = bytearray(n * n)
    top = 0
    for j in range(n):
        dy = (j / (n - 1)) * bh - cy
        for i in range(n):
            dx = (i / (n - 1)) * bw - cx
            q = math.hypot((dx * ca + dy * sa) / ra, (dy * ca - dx * sa) / rb)
            t = max(0.0, min(1.0, (1.0 - q) / feather))
            px[top + i] = max(0, min(255, int(round(255.0 * _fade(t)))))
        top += n
    if max(px) == 0:
        return None
    return Image.frombytes("L", (n, n), bytes(px)).resize((bw, bh), Image.BILINEAR)


def _hold(amount, d, mode, feather):
    """Rein a stroke back to the strongest setting this brush can take without turning a
    mesh quad inside out.

    The field is linear in `amount`, so one measured pass at full strength says how steep
    it is, and past that the quad folds - the smear every body slider is famous for. So
    the stroke stops short of the fold instead of walking into it.

    The rein is a property of the brush, not of the number: a small or hard-edged brush
    cannot take what a big soft one can, so `reach` below reports the ceiling to the page
    and the slider stops there rather than travelling into a setting that does nothing.

    The steepness is measured in the brush's own axes over the whole oval, because the
    worst gradient is not in the soft middle: as the feather runs out the falloff reverses
    and the rim shears far harder than the core, so a guard that only samples the core
    clears a stroke that still folds.
    """
    cx, cy, ra, rb, ca, sa = d[1:7]

    def disp(a, b):
        """The move one unit of amount makes at brush coords (a, b)."""
        ox, oy = _warp_field(cx + a * ca - b * sa, cy + a * sa + b * ca,
                             cx, cy, ra, rb, ca, sa, 1.0, mode, feather)
        return ox * ca + oy * sa, -ox * sa + oy * ca

    e = max(0.5, 0.02 * min(ra, rb))
    steep = 0.0
    for a in (0.0, 0.2 * ra, 0.5 * ra, 0.7 * ra, 0.85 * ra, 0.95 * ra, 0.99 * ra):
        for b in (0.0, 0.2 * rb, 0.5 * rb, 0.7 * rb, 0.85 * rb, 0.95 * rb, 0.99 * rb):
            oa1, ob1 = disp(a + e, b)
            oa2, ob2 = disp(a - e, b)
            oa3, ob3 = disp(a, b + e)
            oa4, ob4 = disp(a, b - e)
            steep = max(steep,
                        (abs(oa1 - oa2) + abs(oa3 - oa4)) / (2 * e),
                        (abs(ob1 - ob2) + abs(ob3 - ob4)) / (2 * e))
    if steep <= 1e-6:
        return amount
    limit = (1.0 - HOLD) / steep
    return max(-limit, min(limit, amount))


# Which brushes rein themselves in, and which slot carries their oval stretch. A guarded
# op can only move so far before its mesh quads turn inside out, and that ceiling is the
# most the strength control may promise.
GUARDED = {"slim": 7}


def reach(args, name, w, h):
    """The biggest strength a brush of this shape can actually apply, or None if ungoverned.

    Measured the same way the engine measures it, so the page can stop the slider where
    the pixels stop moving instead of letting the last half of the travel change a digit
    and nothing else.
    """
    if name not in GUARDED:
        return None
    rng = CLAMP[name]
    vals = [min(max(float(v), lo), hi) for v, (lo, hi) in zip(list(args) + [0.0] * 16, rng)]
    d = _brush(vals, w, h, vals[GUARDED[name]], math.radians(vals[6]))
    if d is None:
        return None
    return _hold(1e9, d, int(round(vals[4])), vals[5])


def _reshape(im, groups, stretch_at=None, guard=False):
    """The one mesh engine behind both reshape brushes: coarse quads read through a
    displacement field that is exactly zero at the rim of the brush.

    A round brush with no rotation is byte-for-byte the move the Face rail has always
    made; the oval and the guard are what let the Body slider go far enough to show.
    """
    out = _rgb(im)
    base = im
    for st in groups:
        amount = st[3]
        if abs(amount) < 1e-4:
            continue
        stretch = st[stretch_at] if stretch_at is not None else 1.0
        d = _brush(st, out.width, out.height, stretch, math.radians(st[6]))
        if d is None:
            continue
        box, cx, cy, ra, rb, ca, sa = d
        mode, feather = int(round(st[4])), st[5]
        if guard:
            amount = _hold(amount, d, mode, feather)
        pad = int(WARP_K * max(ra, rb)) + 3
        pw_box = (max(0, box[0] - pad), max(0, box[1] - pad),
                  min(out.width, box[2] + pad), min(out.height, box[3] + pad))
        src = out.crop(pw_box)
        cell = max(4.0, 2.0 * max(ra, rb) / 20.0)
        nx = max(3, min(24, int(round(src.width / cell))))
        ny = max(3, min(24, int(round(src.height / cell))))
        xs = [int(round(i * src.width / nx)) for i in range(nx + 1)]
        ys = [int(round(j * src.height / ny)) for j in range(ny + 1)]
        pts = []
        for j in range(ny + 1):
            row = []
            for i in range(nx + 1):
                gx, gy = xs[i], ys[j]
                ox, oy = _warp_field(gx + pw_box[0], gy + pw_box[1], cx, cy, ra, rb,
                                     ca, sa, amount, mode, feather)
                row.append((gx, gy,
                            min(max(gx - ox, 0.0), src.width - 1.0),
                            min(max(gy - oy, 0.0), src.height - 1.0)))
            pts.append(row)
        mesh = []
        for j in range(ny):
            for i in range(nx):
                nw, ne, se, sw = pts[j][i], pts[j][i + 1], pts[j + 1][i + 1], pts[j + 1][i]
                mesh.append(((nw[0], nw[1], se[0], se[1]),
                             (nw[2], nw[3], sw[2], sw[3], se[2], se[3], ne[2], ne[3])))
        warped = src.transform(src.size, Image.MESH, mesh, Image.BILINEAR)
        sub = (box[0] - pw_box[0], box[1] - pw_box[1], box[2] - pw_box[0], box[3] - pw_box[1])
        # the field is already 0 at q = 1; this hard-edged feather is the belt that keeps
        # every pixel outside the brush byte-exact however the mesh resampler rounds.
        mask = _brush_mask(box[2] - box[0], box[3] - box[1], cx - box[0], cy - box[1],
                           ra, rb, ca, sa)
        if mask is None:
            continue
        merged = Image.composite(warped.crop(sub), src.crop(sub), mask)
        out = base.copy() if out is base else out
        out.paste(merged, box)
    return out


def _warp(im, args):
    return _reshape(im, _strokes(args, "warp"))


def _slim(im, args):
    return _reshape(im, _strokes(args, "slim"), stretch_at=7, guard=True)


def _iris(im, args):
    """Iris pop: colour and crispness back, only where colour already lives."""
    out = _rgb(im)
    base = im
    for st in _strokes(args, "eyes"):
        amount = st[3]
        if amount <= 0:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r, amount=amount)
        if mask is None:
            continue
        sat = crop.convert("HSV").split()[1]
        alpha = ImageChops.multiply(mask, sat.point(_ramp(20.0, 90.0)))
        if alpha.getbbox() is None:
            continue
        pop = ImageEnhance.Color(crop).enhance(1.0 + 0.9 * amount)
        pop = pop.filter(ImageFilter.UnsharpMask(radius=max(1.0, min(4.0, r / 30.0)),
                                                 percent=int(110 * amount), threshold=2))
        out = base.copy() if out is base else out
        out.paste(Image.composite(pop, crop, alpha), box)
    return out


def _eyes(im, args):
    out = _rgb(im)
    for st in _strokes(args, "eyes"):
        x, y, size, amount = st
        if amount <= 0:
            continue
        out = _whiten(out, [x, y, size, 0.9 * amount])
        out = _iris(out, [x, y, size, amount])
        out = _warp(out, [x, y, size * 0.75, 0.3 * amount, 1.0, 0.6, 0.0])
    return out


MAX_UNDO = 0.90        # the widest brush any stroke can have made (the slim oval at its
#                        full stretch), so an undo can always cover it whole - a narrower
#                        undo leaves a ring of retouch behind


def restore_pixels(image: Image.Image, source: Image.Image, args) -> Image.Image:
    """Paint the frame from before the brushes back wherever she strokes.

    This is Facetune's undo brush: it does not blur, it does not re-retouch, it uncovers
    her own pixels. Each stroke uses the same disc the smudge brushes use, so an undo
    fades out on exactly the curve that made the retouch fade out. `source` is the frame
    as it stood before the first stroke of the first brush, so an undo never uncovers
    ungraded pixels - the grade stays, the retouch goes.

    The result never aliases `source`: pasting into an image that is the source would
    quietly repaint the pixels being restored.
    """
    out = image
    for i in range(0, len(args) - 2, 3):
        found = _disc([args[i], args[i + 1], args[i + 2]], out.width, out.height)
        if found is None:
            continue
        box, cx, cy, r = found
        crop = out.crop(box)
        mask = _mask(crop.width, crop.height, cx - box[0], cy - box[1], r)
        if mask is None:
            continue
        if out is source:
            out = out.copy()
        out.paste(Image.composite(source.crop(box), crop, mask), box)
    return out


APPLIERS = {
    "smooth": _smooth,
    "texture": _texture,
    "matte": _matte,
    "whiten": _whiten,
    "brighten": _brighten,
    "tint": _tint,
    "warp": _warp,
    "slim": _slim,
    "eyes": _eyes,
}


def apply(im: Image.Image, recipe) -> Image.Image:
    """Run a retouch recipe in the order it arrives, capping each brush at its limit."""
    out, used = _rgb(im), {}
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
    return out
