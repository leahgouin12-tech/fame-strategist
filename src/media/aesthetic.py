"""Score how deliberate a frame looks - and refuse to score the person in it.

Every component below is measured from pixels on this machine: where the detail sits,
whether the horizon is level, how busy the background is, how much of the palette the
file actually uses. The weights are this app's own opinion until her own numbers argue with
them - spec 5.9 proposes a change and she accepts it - and they stay stated on the page,
because no platform publishes an attractiveness score. This app does not rank a face or a
body either; /face describes what the light, the lens and the backdrop are doing to one, in
numbers a person can change before the next shot.
"""

from dataclasses import dataclass, field
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat

from src.media.judge import MEASURE_EDGE, Reading, nearest_target

GRID = 6
PROFILE_COLS = 48
PROFILE_ROWS = 64
STRAIGHTEN_FLOOR = 2.0
THIRDS = [(1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3)]

# The app's own weights. They add up to 1 and are shown to her, not hidden.
WEIGHTS = {"placement": 0.30, "level": 0.20, "breathing": 0.20, "palette": 0.15, "focus": 0.15}

SOBEL_V = ImageFilter.Kernel((3, 3), [-1, -2, -1, 0, 0, 0, 1, 2, 1], scale=4, offset=128)


@dataclass
class Component:
    name: str
    score: float
    why: str
    fix: str = ""
    idea: str = ""


@dataclass
class Judgement:
    reading: Reading
    components: list[Component] = field(default_factory=list)
    tilt: float = 0.0
    focus: tuple[float, float] = (0.5, 0.5)
    concentration: float = 0.0
    weights: dict = field(default_factory=lambda: dict(WEIGHTS))

    @property
    def score(self) -> float:
        total = sum(self.weights.get(c.name, 0.0) * c.score for c in self.components)
        return round(total * 10, 1)

    @property
    def fixes(self) -> list[str]:
        return sorted({c.fix for c in self.components if c.fix})

    @property
    def ideas(self) -> list[str]:
        """What to do about the weak components - not a second copy of what was measured."""
        return [c.idea for c in sorted(self.components, key=lambda c: c.score) if c.idea and c.score < 0.72]

    @property
    def band(self) -> str:
        return "strong" if self.score >= 7 else "workable" if self.score >= 5 else "weak"


def _detail_grid(grey: Image.Image) -> list[list[float]]:
    w, h = grey.size
    cw, ch = w // GRID, h // GRID
    rows = []
    for y in range(GRID):
        row = []
        for x in range(GRID):
            box = (x * cw, y * ch, w if x == GRID - 1 else (x + 1) * cw, h if y == GRID - 1 else (y + 1) * ch)
            cell = grey.crop(box).filter(ImageFilter.FIND_EDGES)
            row.append(ImageStat.Stat(cell).mean[0])
        rows.append(row)
    return rows


def _placement_and_focus(rows: list[list[float]]) -> tuple[tuple[float, float], float]:
    """Where the detail sits, and how much of it sits there."""
    flat = [v for r in rows for v in r]
    peak = max(flat) or 1.0
    weight = [[max(0.0, v / peak) for v in r] for r in rows]
    total = sum(sum(r) for r in weight) or 1.0
    cw, ch = 1.0 / GRID, 1.0 / GRID
    cx = sum((x + 0.5) * cw * weight[y][x] for y in range(GRID) for x in range(GRID)) / total
    cy = sum((y + 0.5) * ch * weight[y][x] for y in range(GRID) for x in range(GRID)) / total
    top3 = sorted(flat, reverse=True)[:3]
    concentration = sum(top3) / (sum(flat) or 1.0)
    return (round(cx, 3), round(cy, 3)), round(min(1.0, concentration), 3)


def _fit(pts: list[tuple[float, float]]):
    n = len(pts)
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    denom = n * sxx - sx * sx
    if not denom:
        return None
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def _horizon_line(grey: Image.Image):
    """Trace the strongest horizontal edge across the frame and fit a line to it.

    Returns (degrees, columns measured) or None when no single line is strong enough to
    claim - a frame with no horizon is reported as unmeasurable rather than as level.
    """
    edges = grey.filter(SOBEL_V).convert("L").point(lambda p: abs(p - 128))
    w, h = edges.size
    small = edges.reduce((max(1, math.ceil(w / PROFILE_COLS)), max(1, math.ceil(h / PROFILE_ROWS))))
    sw, sh = small.size
    data = small.tobytes()
    cell_w, cell_h = w / sw, h / sh
    traced = []
    # The outermost row and column are the frame's own edge: the filter answers harder
    # there than to any real line, so a level frame reads as a steep one.
    for x in range(1, sw - 1):
        col = [data[y * sw + x] for y in range(1, sh - 1)]
        traced.append((x, max(col), col.index(max(col)) + 1))
    if not traced:
        return None
    strongest = max(t[1] for t in traced) or 1
    # A column counts when it is close to the frame's own strongest line, so the test
    # follows the picture's contrast instead of a made-up absolute.
    pts = [(x * cell_w, r * cell_h) for x, m, r in traced if m >= strongest * 0.35]
    need = max(6, sw // 3)
    if len(pts) < need:
        return None
    line = _fit(pts)
    if line is None:
        return None
    # Then drop the columns the fitted line disagrees with: one stray edge in an
    # otherwise flat frame must not become the horizon.
    kept = [p for p in pts if abs(p[1] - (line[0] * p[0] + line[1])) <= 2 * cell_h]
    if len(kept) < need:
        return None
    line = _fit(kept)
    if line is None:
        return None
    deg = math.degrees(math.atan(line[0]))
    if abs(deg) > 15:  # nothing that runs 15 degrees off level is a horizon
        return None
    return deg, len(kept) / sw


def _tilt(grey: Image.Image) -> tuple[float, float, bool]:
    line = _horizon_line(grey)
    if line is None:
        return 0.0, 0.7, False
    deg, coverage = line
    if abs(deg) < 0.6:
        return 0.0, 1.0, True
    return deg, max(0.15, min(0.9, 1.0 - abs(deg) / 6.0) * (0.5 + coverage / 2)), True


def _palette(rgb: Image.Image) -> tuple[float, float]:
    hsv = rgb.convert("HSV")
    saturation = ImageStat.Stat(hsv).mean[1] / 255
    hue = hsv.split()[0].histogram()
    total = sum(hue) or 1
    top = sum(sorted(hue, reverse=True)[:24])
    return round(saturation, 3), round(top / total, 3)


def judge_photo(path: Path, reading: Reading, weights: dict | None = None) -> Judgement:
    j = Judgement(reading=reading, weights=dict(weights or WEIGHTS))
    if reading.error:
        return j
    with Image.open(path) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")
    scale = MEASURE_EDGE / max(im.size)
    small = im.resize((max(GRID, int(im.width * scale)), max(GRID, int(im.height * scale))), Image.LANCZOS)
    grey = small.convert("L")

    rows = _detail_grid(grey)
    focus, concentration = _placement_and_focus(rows)
    j.focus, j.concentration = focus, concentration

    peak = max(max(r) for r in rows) or 1.0
    hot = sum(1 for r in rows for v in r if v > peak * 0.55)
    outer = sum(1 for y in range(GRID) for x in range(GRID)
               if (y in (0, GRID - 1) or x in (0, GRID - 1)) and rows[y][x] > peak * 0.55)

    dist = min(((focus[0] - tx) ** 2 + (focus[1] - ty) ** 2) ** 0.5 for tx, ty in THIRDS)
    centred = ((focus[0] - 0.5) ** 2 + (focus[1] - 0.5) ** 2) ** 0.5
    placement = max(0.0, 1.0 - dist / 0.24)
    if centred < 0.06:
        placement *= 0.55

    tilt, level, measured = _tilt(grey)
    j.tilt = tilt

    saturation, harmony = _palette(small)
    breathing = max(0.0, 1.0 - outer / 9)
    focus_score = max(0.0, min(1.0, (concentration - 0.13) / 0.22))

    if hot >= GRID:
        j.components.append(Component("breathing", round(breathing * 0.7, 3),
                                      f"{hot} of {GRID * GRID} regions carry the same amount of detail, so nothing "
                                      "leads the eye", "",
                                      "Tighten the crop so the detail stops pressing on all four edges."))
    else:
        j.components.append(Component("breathing", round(breathing, 3),
                                      "the edges of the frame are quiet enough for one subject to hold it", "",
                                      "Leave one band of the frame quiet so the subject has room to breathe."))
    j.components.append(Component("placement", round(placement, 3),
                                  f"the busiest part of the frame sits at {focus[0]:.2f}, {focus[1]:.2f} - "
                                  + ("dead centre" if centred < 0.06 else
                                     "close to a thirds intersection" if dist < 0.1 else "off from any thirds line"),
                                  "crop to the thirds point" if placement < 0.6 else "",
                                  ("Slide the crop so the busiest part sits off-centre, on a thirds line."
                                   if centred < 0.06 else
                                   "Re-crop so the busiest part lands on a thirds line." if dist >= 0.1 else "")))
    if not measured:
        level_why = "no single horizontal line is strong enough to measure, so level is not judged"
        level_idea = ""
    elif abs(tilt) >= 0.6:
        level_why = f"the strongest horizontal line runs {abs(tilt):.1f} degrees off level"
        level_idea = (f"Rotate it by {abs(tilt):.1f} degrees - the editor can do this one exactly."
                      if abs(tilt) >= STRAIGHTEN_FLOOR else
                      "A small rotate would finish it, though it is barely off.")
    else:
        level_why = "the strongest horizontal line is level"
        level_idea = ""
    j.components.append(Component("level", round(level, 3), level_why,
                                  "straighten" if measured and abs(tilt) >= STRAIGHTEN_FLOOR else "",
                                  level_idea))
    palette_score = round(min(1.0, (0.55 * min(1.0, saturation / 0.42) + 0.45 * harmony)), 3)
    j.components.append(Component("palette", palette_score,
                                  f"colour covers {harmony:.0%} of the palette in two bands and sits at "
                                  f"{saturation:.0%} saturation", "lift colour" if saturation < 0.18 else "",
                                  "Lift the colour a notch - the file is sitting close to grey."
                                  if saturation < 0.18 else ""))
    j.components.append(Component("focus", round(focus_score, 3),
                                  f"the three busiest regions hold {concentration:.0%} of the frame's detail"
                                  + (" - one subject owns it" if focus_score > 0.6 else
                                     ", so the eye has nowhere to land"), "",
                                  "Cut down to the one subject that actually owns the frame."
                                  if focus_score < 0.55 else ""))
    return j


def overlay(path: Path, j: Judgement, out: Path) -> Path:
    """Draw the thirds grid and the measured focus point so she can see what it saw."""
    with Image.open(path) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")
    scale = 320 / max(im.size)
    im = im.resize((max(2, int(im.width * scale)), max(2, int(im.height * scale))))
    d = ImageDraw.Draw(im)
    w, h = im.size
    for i in (1, 2):
        d.line([(w * i / 3, 0), (w * i / 3, h)], fill=(255, 255, 255), width=1)
        d.line([(0, h * i / 3), (w, h * i / 3)], fill=(255, 255, 255), width=1)
    d.ellipse([j.focus[0] * w - 7, j.focus[1] * h - 7, j.focus[0] * w + 7, j.focus[1] * h + 7],
              outline=(255, 90, 90), width=3)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "JPEG", quality=90)
    return out
