"""Measure what a photo actually contains, then say what can honestly be fixed.

Every number is computed on her own file, on this machine. Nothing is sent anywhere and
nothing generative touches the picture: the only corrections described here are global
tone and a crop, because those cannot change who is in the frame.

Sharpness has no absolute floor. There is no published minimum and a single file cannot
be called soft without something to compare it to, so softness is a ranking inside her
own batch - and with fewer than three files the app says it has no baseline instead of
guessing.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MEASURE_EDGE = 512
MIN_BASELINE = 3

# Measured facts about the file itself, not platform numbers.
BLOWN_FLOOR = 0.02
CRUSHED_FLOOR = 0.02
SOFT_RATIO = 0.6
LONG_EDGE_FLOOR = 1080
ASPECT_TOLERANCE = 0.055

TARGETS = [("9:16", 9 / 16), ("4:5", 4 / 5), ("1:1", 1.0), ("16:9", 16 / 9), ("3:4", 3 / 4)]

# The only operations clean.py may perform. Anything else invents information the
# camera did not record.
ALLOWED_FIXES = ("exposure", "contrast", "crop")


@dataclass
class Reading:
    name: str
    width: int = 0
    height: int = 0
    edge: float = 0.0
    exposure: float = 0.0
    blown: float = 0.0
    crushed: float = 0.0
    target: str = ""
    off_format: bool = False
    error: str = ""
    soft: bool = False
    baseline: bool = False

    @property
    def long_edge(self) -> int:
        return max(self.width, self.height)

    @property
    def small(self) -> bool:
        return not self.error and self.long_edge < LONG_EDGE_FLOOR

    @property
    def tone(self) -> bool:
        return self.blown > BLOWN_FLOOR or self.crushed > BLOWN_FLOOR

    @property
    def flags(self) -> list[str]:
        if self.error:
            return ["unreadable"]
        out = []
        if self.soft:
            out.append("softer than your other shots")
        if self.blown > BLOWN_FLOOR:
            out.append(f"{round(self.blown * 100, 1)}% of it is pure white")
        if self.crushed > CRUSHED_FLOOR:
            out.append(f"{round(self.crushed * 100, 1)}% of it is pure black")
        if self.off_format:
            out.append(f"not a clean {self.target}")
        if self.small:
            out.append(f"{self.long_edge} px on the long edge")
        return out

    @property
    def verdict(self) -> str:
        if self.error:
            return "unreadable"
        if self.soft or self.small:
            return "skip"
        return "fix" if (self.tone or self.off_format) else "post"

    @property
    def fixes(self) -> list[str]:
        """A skip means the file is not worth posting, so no button contradicts it."""
        if self.error or self.verdict != "fix":
            return []
        out = []
        if self.tone:
            out += ["exposure", "contrast"]
        if self.off_format:
            out.append("crop")
        return out

    @property
    def limit(self) -> str:
        """What this verdict does not claim."""
        if self.verdict == "skip":
            return ("Detail that is not in the file cannot be added back. This is a ranking of "
                    "your own shots, not a platform rule.")
        if self.verdict == "fix":
            return ("Tone and crop only. Areas that are already pure white or pure black have no "
                    "data left to recover, and nothing here changes your face, skin or body.")
        if self.verdict == "post":
            return ("Nothing here is a promise about performance. It says the file is clean and "
                    "square, not that it will work.")
        return "The file could not be decoded, so nothing about its content is known."


def nearest_target(width: int, height: int) -> tuple[str, float]:
    ratio = width / height
    name, value = min(TARGETS, key=lambda t: abs(ratio - t[1]))
    return name, value


def measure(path: Path) -> Reading:
    r = Reading(name=path.name)
    try:
        with Image.open(path) as raw:
            im = ImageOps.exif_transpose(raw).convert("RGB")
    except Exception as exc:  # a broken file is a fact about the file, not a crash
        r.error = str(exc)[:120]
        return r
    r.width, r.height = im.size
    r.target, best = nearest_target(r.width, r.height)
    r.off_format = abs(r.width / r.height - best) / best > ASPECT_TOLERANCE

    grey = im.convert("L")
    scale = MEASURE_EDGE / max(r.width, r.height)
    small = grey.resize((max(1, int(r.width * scale)), max(1, int(r.height * scale))), Image.LANCZOS)
    r.edge = round(ImageStat.Stat(small.filter(ImageFilter.FIND_EDGES)).mean[0], 2)
    hist = grey.histogram()
    total = sum(hist) or 1
    r.exposure = round(sum(i * hist[i] for i in range(256)) / total / 255, 3)
    r.blown = round(sum(hist[250:]) / total, 4)
    r.crushed = round(sum(hist[:6]) / total, 4)
    return r


def judge(paths: list[Path]) -> list[Reading]:
    readings = [measure(p) for p in paths]
    good = [r for r in readings if not r.error]
    if len(good) >= MIN_BASELINE:
        ranked = sorted(r.edge for r in good)
        median = ranked[len(ranked) // 2]
        for r in good:
            r.baseline = True
            r.soft = r.edge < median * SOFT_RATIO
    return readings


def inbox_files(inbox: Path) -> list[Path]:
    if not inbox.is_dir():
        return []
    return sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
