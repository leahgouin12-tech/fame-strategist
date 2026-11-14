"""The brush that moves pixels instead of painting them: swirl and inflate, the two
geometric warps a reshape brush is actually made of.

Both are the same machinery as retouch.py's warp - a coarse grid of quads read through
`Image.transform(size, Image.MESH, ...)`, with a displacement field that is exactly zero at
the rim of the brush and a hard feathered belt behind it. So the warp is real geometry
(nothing is cloned, nothing is invented, the background travels with the subject) and every
pixel outside the brush comes back byte for byte identical to the frame that went in.

Positions are fractions of the frame as it stands at that point in the recipe; the brush
diameter in slot 2 is a fraction of the short edge, which is what makes one stroke the same
size on a phone crop and on a print file. SHAPE, CLAMP and LIMITS are the recipe contract
shared with the registry, the routes and the studio page.
"""

import math

from PIL import Image

FEATHER = 0.45        # share of the radius over which the brush mask fades to nothing
INFLATE_K = 0.55      # how far a full inflate reaches, as a share of the radius
CELLS = 26            # mesh cells across a brush diameter - enough to curve, cheap to map

# Per-op, per-position min/max inside one group of args.
# swirl group   = x, y, brush, degrees, feather
# inflate group = x, y, brush, amount, feather (negative amount pinches instead of swelling)
CLAMP = {
    "swirl": [(0.0, 1.0), (0.0, 1.0), (0.02, 0.60), (-360.0, 360.0), (0.05, 1.0)],
    "inflate": [(0.0, 1.0), (0.0, 1.0), (0.02, 0.60), (-1.0, 1.0), (0.05, 1.0)],
}

# Max strokes per op, so a hand-edited recipe cannot freeze the machine.
LIMITS = {"swirl": 40, "inflate": 40}

SHAPE = {name: ["group", len(rng), LIMITS[name]] for name, rng in CLAMP.items()}

# How far outside the disc a stroke has to read pixels: a swirl stays on its own circle,
# an inflate at full strength reaches past the rim by INFLATE_K of the radius.
PAD = {"swirl": 0.0, "inflate": INFLATE_K}


def _rgb(im):
    return im if im.mode == "RGB" else im.convert("RGB")


def _fade(t):
    return t * t * (3.0 - 2.0 * t)


def _strokes(args, name):
    """One op's flat args -> complete clamped groups; junk, extras and tails vanish."""
    k, rng = len(CLAMP[name]), CLAMP[name]
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

    Built on a 96x96 grid and stretched: the weight is exactly 0 from q = 1 outward, which
    is what lets the warp leave every pixel outside the brush byte-identical.
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


def _swirl_field(dx, dy, r, degrees, feather):
    """Where a pixel came from: the same distance from the centre, turned back by an angle
    that dies out at the rim, so the twist shears rather than slides."""
    q = math.hypot(dx, dy) / r
    if q >= 1.0:
        return dx, dy
    a = math.radians(degrees) * _fade(min(1.0, (1.0 - q) / feather))
    c, s = math.cos(a), math.sin(a)
    return c * dx + s * dy, -s * dx + c * dy


def _inflate_field(dx, dy, r, amount, feather):
    """Where a pixel came from: the same bearing, pulled toward the centre so the centre
    reads large. Negative amount pushes the sample outward, which is the pinch."""
    q = math.hypot(dx, dy) / r
    if q >= 1.0:
        return dx, dy
    scale = 1.0 - amount * INFLATE_K * _fade(min(1.0, (1.0 - q) / feather))
    return dx * scale, dy * scale


def _warp(im, args, name, field):
    """One brush, one mesh. The grid is solved on the stroke's own box plus the reach of
    the field, and the result is laid back through a mask that is zero outside the disc."""
    out = _rgb(im)
    base = im
    pad_factor = PAD[name]
    for st in _strokes(args, name):
        if abs(st[3]) < 1e-4:
            continue
        d = _disc(st, out.width, out.height)
        if d is None:
            continue
        box, cx, cy, r = d
        feather = st[4]
        pad = int(round(pad_factor * r)) + 3
        pw_box = (max(0, box[0] - pad), max(0, box[1] - pad),
                  min(out.width, box[2] + pad), min(out.height, box[3] + pad))
        src = out.crop(pw_box)
        cell = max(4.0, 2.0 * r / CELLS)
        nx = max(3, min(40, int(round(src.width / cell))))
        ny = max(3, min(40, int(round(src.height / cell))))
        xs = [min(src.width, int(round(i * src.width / nx))) for i in range(nx + 1)]
        ys = [min(src.height, int(round(j * src.height / ny))) for j in range(ny + 1)]
        pts = []
        ox, oy = cx - pw_box[0], cy - pw_box[1]      # the brush centre inside this crop
        for j in range(ny + 1):
            row = []
            for i in range(nx + 1):
                gx, gy = xs[i], ys[j]
                # the field answers where a pixel came from, measured off the brush centre,
                # so the sample lands on the centre plus that answer
                sdx, sdy = field(gx - ox, gy - oy, r, st[3], feather)
                row.append((gx, gy, min(max(ox + sdx, 0.0), src.width - 1.0),
                            min(max(oy + sdy, 0.0), src.height - 1.0)))
            pts.append(row)
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
            continue
        warped = src.transform(src.size, Image.MESH, mesh, Image.BILINEAR)
        sub = (box[0] - pw_box[0], box[1] - pw_box[1], box[2] - pw_box[0], box[3] - pw_box[1])
        mask = _mask(box[2] - box[0], box[3] - box[1], cx - box[0], cy - box[1], r,
                     feather=0.12, amount=1.0)
        if mask is None:
            continue
        merged = Image.composite(warped.crop(sub), src.crop(sub), mask)
        out = base.copy() if out is base else out
        out.paste(merged, box)
    return out


def _swirl(im, args):
    return _warp(im, args, "swirl", _swirl_field)


def _inflate(im, args):
    return _warp(im, args, "inflate", _inflate_field)


def _guarded(fn):
    """The warp runs on the RGB part of the frame and lays the alpha it found back over the
    result, so a swirl after a cutout still leaves the cutout transparent."""

    def run(im, args):
        alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
        base = im if im.mode == "RGB" and alpha is None else im.convert("RGB")
        out = fn(base, args)
        if alpha is None:
            return out
        rgba = out.convert("RGB")
        rgba.putalpha(alpha)
        return rgba

    return run


APPLIERS = {
    "swirl": _guarded(_swirl),
    "inflate": _guarded(_inflate),
}


def apply(im: Image.Image, recipe) -> Image.Image:
    """Run a mesh recipe in the order it arrives, capping each brush at its limit."""
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
