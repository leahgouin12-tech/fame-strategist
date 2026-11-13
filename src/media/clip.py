"""The clip engine: read a video, cut it, filter it, write a copy - all on this machine.

imageio-ffmpeg ships a static ffmpeg binary inside the venv, so there is nothing to
install, nothing to pay for and no service to upload to. The file is decoded here,
filtered here, and the copy lands beside the original.

Two rules hold this together:

* ffmpeg is called with a list of arguments, never a shell string, and every filter in
  the chain is built from numbers this module clamps. A filename can never become a
  command, and a recipe can never smuggle in a filter the app did not choose.
* No face, body or skin filter is offered. ffmpeg has `dnn_processing` and friends that
  can beautify a person; they are not in the table below, and a test in
  tests/media/test_clip.py fails the suite if one ever is.
"""

from dataclasses import dataclass
import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

SAMPLE_FRAMES = 5
# A frame is decoded with its long edge capped here. The judge resamples to a smaller
# working picture anyway, and a full 4K decode for every sampled frame is the single
# slowest thing the clip page does; the numbers it prints are measured at this size.
DECODE_EDGE = 1280
# A frame the page shows is never wider or taller than this, so it is decoded at this
# size instead of at full size and shrunk afterwards.
SHOW_EDGE = 900
MIN_EDGE = 720
MIN_SECONDS = 1.0
MAX_SECONDS = 180.0
SPEED_LO, SPEED_HI = 0.5, 2.0
FADE_MAX = 2.0
MAX_TILT = 15.0
NEUTRAL_KELVIN = 6500

CRF = "22"
PRESET = "veryfast"

# A clip recipe is the same shape as a photo recipe: ["name", arg, ...], so it can be
# shown to her, saved beside the file and re-run later.
TIME_OPS = {"trim": (0.0, None), "speed": (SPEED_LO, SPEED_HI)}
FRAME_OPS = {"rotate": (-MAX_TILT, MAX_TILT), "ratio": (0.2, 5.0), "flip": (0.0, 1.0)}
TONE_OPS = {"brightness": (-0.5, 0.5), "contrast": (0.5, 1.8), "saturation": (0.0, 2.0),
            "warmth": (-1.0, 1.0), "sharpen": (0.0, 1.5), "vignette": (0.0, 0.5)}
FINISH_OPS = {"fade": (0.0, FADE_MAX), "mute": (0.0, 1.0)}
OPS: dict[str, tuple] = {}
for _table in (TIME_OPS, FRAME_OPS, TONE_OPS, FINISH_OPS):
    OPS.update(_table)

GROUPS = ("time", "frame", "tone", "finish")
_TABLES = {"time": TIME_OPS, "frame": FRAME_OPS, "tone": TONE_OPS, "finish": FINISH_OPS}
# Inside a group the order is fixed, not whatever the page happened to send: the aspect box
# is fitted to the frame the straighten left behind, so straightening always comes first.
ORDER = {"trim": 0, "speed": 1,
         "rotate": 0, "ratio": 1, "flip": 2,
         "brightness": 0, "contrast": 1, "saturation": 2, "warmth": 3, "sharpen": 4,
         "vignette": 5,
         "fade": 0, "mute": 1}
LABELS = {
    "trim": "cut", "speed": "speed", "rotate": "straighten", "ratio": "aspect",
    "flip": "mirror", "brightness": "brightness", "contrast": "contrast",
    "saturation": "colour", "warmth": "warm / cool", "sharpen": "sharpen",
    "vignette": "vignette", "fade": "fade in and out", "mute": "sound off",
}
RANGES = {
    "brightness": "darker to brighter, on every frame",
    "contrast": "how far apart the light and dark ends sit",
    "saturation": "colour strength; 1 is what the camera recorded",
    "warmth": "shifts the whole clip toward amber or toward blue",
    "sharpen": "edges only - it cannot rebuild detail the sensor missed",
    "vignette": "darkens toward the corners",
    "fade": "a short fade in and out at both ends",
}

STEPS = {"speed": 0.05, "rotate": 0.1, "brightness": 0.02, "contrast": 0.02,
         "saturation": 0.02, "warmth": 0.02, "sharpen": 0.02, "vignette": 0.02,
         "fade": 0.05}
UNITS = {"speed": "×", "rotate": "°", "fade": "s"}
# Where a slider sits when it is doing nothing. Most controls are additive, so zero;
# these three are multipliers, and zero would be black.
NEUTRAL = {"speed": 1.0, "contrast": 1.0, "saturation": 1.0}


@dataclass(frozen=True)
class Ctrl:
    name: str
    label: str
    group: str
    lo: float
    hi: float
    step: float
    unit: str
    neutral: float
    note: str


CONTROLS = [Ctrl(name, LABELS[name], next(g for g, table in _TABLES.items() if name in table),
                 OPS[name][0], OPS[name][1],
                 STEPS[name], UNITS.get(name, ""), NEUTRAL.get(name, 0.0),
                 RANGES.get(name, ""))
            for name in STEPS]


def _group(name: str) -> str:
    return next((g for g, table in _TABLES.items() if name in table), "tone")

_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #\d+:\d+.*?Video:\s*([a-z0-9_]+).*?,\s*(\d{2,5})x(\d{2,5})")
_FPS = re.compile(r"([\d.]+)\s*fps")
_AUDIO = re.compile(r"Stream #\d+:\d+.*?Audio:")
_LEVEL = re.compile(r"(mean_volume|max_volume):\s*(-?[\d.]+) dB")


@dataclass
class Clip:
    """What the file actually is - read from its own header, not from its name."""

    name: str = ""
    ok: bool = False
    error: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    has_audio: bool = False
    mean_db: float | None = None
    max_db: float | None = None
    bytes: int = 0

    @property
    def long_edge(self) -> int:
        return max(self.width, self.height)

    @property
    def short_edge(self) -> int:
        return min(self.width, self.height)

    @property
    def ratio(self) -> float:
        return self.width / self.height if self.height else 0.0

    @property
    def portrait(self) -> bool:
        return self.height > self.width

    @property
    def small(self) -> bool:
        return self.ok and self.short_edge < MIN_EDGE

    @property
    def silent(self) -> bool:
        return self.ok and (not self.has_audio or (self.max_db is not None and self.max_db < -35))

    @property
    def too_long(self) -> bool:
        return self.duration > MAX_SECONDS

    @property
    def mbytes(self) -> float:
        return self.bytes / 1_048_576

    @property
    def flags(self) -> list[str]:
        if not self.ok:
            return ["unreadable"]
        out = []
        if self.small:
            out.append(f"{self.short_edge} px on the short edge")
        if self.silent:
            out.append("no usable sound" if self.has_audio else "no sound track at all")
        if self.too_long:
            out.append(f"{self.duration:.0f} s long")
        if self.fps and self.fps < 24:
            out.append(f"{self.fps:g} fps")
        return out

    @property
    def line(self) -> str:
        return (f"{self.duration:.1f}s · {self.width}×{self.height} · {self.fps:g} fps · "
                f"{self.codec or '?'} · {self.mbytes:.1f} MB · "
                f"{'sound' if self.has_audio and not self.silent else 'no sound'}")

    @property
    def limit(self) -> str:
        if not self.ok:
            return ("The file could not be decoded, so nothing about it is known. Some phone "
                    "formats need a different export setting before they can be read at all.")
        return ("This reads the file's own header and a handful of frames from it. It cannot "
                "hear whether the audio is worth hearing, and it does not compare your clip "
                "with anyone else's - only with the numbers shown beside it.")


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def available() -> bool:
    return bool(ffmpeg_exe())


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, errors="replace",
                          encoding="utf-8", timeout=timeout)


def probe(path: Path) -> Clip:
    c = Clip(name=path.name, bytes=path.stat().st_size if path.is_file() else 0)
    exe = ffmpeg_exe()
    if not exe:
        c.error = "ffmpeg is not available on this machine"
        return c
    if not path.is_file():
        c.error = "the file is not here"
        return c
    # Header only: `-f null -` would decode the whole clip just to be told its length again,
    # and the clips list is exactly the place where that cost is felt - one read per file,
    # every time the page opens.
    found = _run([exe, "-hide_banner", "-nostdin", "-i", str(path)])
    text = found.stderr or ""
    m = _DUR.search(text)
    if not m:
        c.error = (text.strip().splitlines()[-1][:140] if text.strip() else "no header")
        return c
    c.duration = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 3)
    v = _VIDEO.search(text)
    if v:
        c.codec, c.width, c.height = v.group(1), int(v.group(2)), int(v.group(3))
        f = _FPS.search(text[v.end():v.end() + 400])
        if f:
            c.fps = round(float(f.group(1)), 3)
    c.has_audio = bool(_AUDIO.search(text))
    c.ok = bool(c.width and c.height and c.duration > 0)
    if not c.ok:
        c.error = "no video stream with a size in this file"
    return c


def loudness(path: Path, clip: Clip | None = None) -> Clip:
    """One decode pass with volumedetect: mean and peak level in dB.

    A clip whose track never rises above a whisper is reported as silent, because that is
    what the microphone actually recorded.
    """
    exe = ffmpeg_exe()
    c = clip or probe(path)
    if not exe or not c.ok or not c.has_audio:
        return c
    found = _run([exe, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                 timeout=240)
    for name, value in _LEVEL.findall(found.stderr or ""):
        if name == "mean_volume":
            c.mean_db = float(value)
        else:
            c.max_db = float(value)
    return c


def sample_times(duration: float, n: int = SAMPLE_FRAMES) -> list[float]:
    """Evenly spaced, but never on the first or last breath - those are often a fade."""
    if duration <= 0:
        return []
    n = max(1, min(int(n), 12))
    edge = min(0.08, duration * 0.05)
    span = max(0.01, duration - 2 * edge)
    return [round(edge + span * (i + 0.5) / n, 3) for i in range(n)]


def seek(path: Path, t: float, out: Path, edge: int = 0) -> Path:
    """One frame, decoded here. Input-side -ss has been accurate since ffmpeg 2.1.

    `edge` caps the long side while decoding: the judge and the page never look at more
    pixels than that, and a full 4K decode is what makes this page slow.
    """
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is not available on this machine")
    out.parent.mkdir(parents=True, exist_ok=True)
    # A frame already on disk that is newer than the clip it came from is the same frame.
    # The judge pulls seven of them out of every clip it reads, and re-decode-on-reopen is
    # what made the second visit to a clip as slow as the first.
    if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
        return out
    args = [exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t):.3f}",
            "-i", str(path)]
    if edge:
        args += ["-vf", _scale(edge)]
    found = _run([*args, "-frames:v", "1", str(out)])
    if not out.is_file():
        raise RuntimeError((found.stderr or "no frame").strip()[:160])
    return out


def _scale(edge: int) -> str:
    return (f"scale={edge}:{edge}:force_original_aspect_ratio=decrease:force_divisible_by=2")


def frames(path: Path, n: int = SAMPLE_FRAMES, workdir: Path | None = None,
           at: list[float] | None = None, edge: int = 0) -> list[Path]:
    times = at if at is not None else sample_times(probe(path).duration, n)
    where = workdir or Path(tempfile.mkdtemp(prefix="fs-frames-"))
    stem = (path.stem.replace(" ", "-")[:40] or "clip")
    out = []
    for i, t in enumerate(times):
        try:
            out.append(seek(path, t, where / f"{stem}-{i}.png", edge))
        except RuntimeError:
            continue
    return out


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def _rotate_pair(w: int, h: int, deg: float) -> tuple[int, int]:
    rad = math.radians(abs(deg))
    return _even(w * math.cos(rad) - h * math.sin(rad)), _even(h * math.cos(rad) - w * math.sin(rad))


def _ratio_pair(w: int, h: int, ratio: float) -> tuple[int, int]:
    cw, ch = (h * ratio, h) if h * ratio <= w else (w, w / ratio)
    return _even(cw), _even(ch)


def normalize(recipe) -> list:
    """Clamp every number to its own range, keep one entry per control, drop no-ops, and
    run time before geometry before tone before the finish."""
    seen: dict[str, list] = {}
    for entry in recipe or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        name = str(entry[0])
        if name not in OPS:
            continue
        lo, hi = OPS[name]
        args = []
        for raw in entry[1:]:
            if not isinstance(raw, (int, float)):
                continue
            v = float(raw)
            if not math.isfinite(v):
                v = 0.0
            args.append(max(v, lo) if hi is None else min(max(v, lo), hi))
        if name == "trim":
            if len(args) < 2 or args[1] - args[0] < MIN_SECONDS:
                continue
            args = [max(0.0, args[0]), max(0.0, args[1])]
        elif not args:
            continue
        seen[name] = [name] + args
    ordered = sorted(seen.values(), key=lambda e: (GROUPS.index(_group(e[0])), ORDER[e[0]]))
    return [e for e in ordered if not _is_noop(e)]


def _is_noop(entry) -> bool:
    name, args = entry[0], entry[1:]
    if name in ("trim", "ratio"):
        return False
    if name == "speed":
        return abs(args[0] - 1.0) < 0.01
    if name in ("contrast", "saturation"):
        return abs(args[0] - 1.0) < 0.01
    if name in ("mute", "flip"):
        return args[0] < 0.5
    if name == "fade":
        return args[0] < 0.05
    return abs(args[0]) < 0.01


def span(entries: list, duration: float) -> tuple[float, float, float]:
    """The part of the clip that survives the cut, and how long the file is after speed."""
    start, end = 0.0, duration
    speed = 1.0
    for name, *args in entries:
        if name == "trim":
            start, end = min(args[0], duration), min(args[1], duration)
        elif name == "speed":
            speed = args[0]
    end = min(end, start + MAX_SECONDS)
    return start, max(start + MIN_SECONDS, end), (end - start) / speed


def build(recipe, clip: Clip) -> tuple[list[str], list[str], str]:
    """Turn a clamped recipe into ffmpeg arguments and the filter text that made them.

    The running frame size is tracked, so a ratio chosen after a straighten fits what the
    straighten left behind - the same rule the photo engine follows.
    """
    entries = normalize(recipe)
    start, end, out_len = span(entries, clip.duration)
    in_args = ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}"]
    out_args: list[str] = []
    vf: list[str] = []
    speed, w, h, fade, mute = 1.0, clip.width, clip.height, 0.0, False
    tone: dict[str, float] = {}

    for name, *args in entries:
        if name == "speed":
            speed = args[0]
        elif name == "rotate":
            cw, ch = _rotate_pair(w, h, args[0])
            vf.append(f"rotate={args[0] * math.pi / 180:.5f}:ow={w}:oh={h}:fillcolor=black")
            vf.append(f"crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2")
            w, h = cw, ch
        elif name == "ratio":
            cw, ch = _ratio_pair(w, h, args[0])
            vf.append(f"crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2")
            w, h = cw, ch
        elif name == "flip":
            vf.append("hflip")
        elif name in TONE_OPS:
            tone[name] = args[0]
        elif name == "fade":
            fade = args[0]
        elif name == "mute":
            mute = args[0] >= 0.5

    if speed != 1.0:
        vf.append(f"setpts=PTS/{speed:.4f}")
    eq = [f"{key}={tone[key]:.4f}" for key in ("brightness", "contrast", "saturation") if key in tone]
    if eq:
        vf.append("eq=" + ":".join(eq))
    if "warmth" in tone:
        # ffmpeg takes kelvin; 6500 is the neutral daylight the picture was shot under.
        vf.append(f"colortemperature=temperature={NEUTRAL_KELVIN + tone['warmth'] * 2500:.0f}")
    if "sharpen" in tone:
        vf.append(f"unsharp=5:5:{tone['sharpen'] * 0.6:.3f}:5:5:0.0")
    if "vignette" in tone:
        vf.append(f"vignette=angle={math.pi / 5 + tone['vignette'] * 0.75:.4f}")
    if fade:
        vf.append(f"fade=t=in:st=0:d={fade:.2f}")
        vf.append(f"fade=t=out:st={max(0.0, out_len - fade):.2f}:d={fade:.2f}")

    chain = ",".join(vf)
    if chain:
        out_args += ["-vf", chain]
    out_args += ["-c:v", "libx264", "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart"]
    if mute or not clip.has_audio:
        out_args.append("-an")
    elif speed != 1.0:
        out_args += ["-af", f"atempo={speed:.4f}", "-c:a", "aac", "-b:a", "128k"]
    else:
        out_args += ["-c:a", "copy"]
    return in_args, out_args, chain


def export(src: Path, dst: Path, recipe, clip: Clip | None = None) -> Clip:
    """Write a copy. The original is opened read-only and never rewritten."""
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is not available on this machine")
    c = clip or probe(src)
    if not c.ok:
        raise RuntimeError(c.error or "this file cannot be read")
    in_args, out_args, _ = build(recipe, c)
    dst.parent.mkdir(parents=True, exist_ok=True)
    found = _run([exe, "-hide_banner", "-loglevel", "error", "-y", *in_args, "-i", str(src),
                  *out_args, str(dst)], timeout=900)
    if not dst.is_file():
        raise RuntimeError((found.stderr or "ffmpeg wrote nothing").strip()[-200:])
    return probe(dst)


def preview_frame(src: Path, t: float, recipe, dst: Path, clip: Clip | None = None,
                  edge: int = 0) -> Path:
    """One frame with the whole chain applied, so what she sees is what the export holds.

    The two filters that only exist in time are left out: `setpts` moves stamps without
    changing a picture, and a fade would show the first frame of a one-frame file as
    black. The readout next to the preview says so.
    """
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is not available on this machine")
    # The caller names this file after the exact state it holds, so a copy newer than the
    # clip is that state already rendered - scrubbing back to a frame she has just looked at
    # costs a disk read, not another decode.
    if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    c = clip or probe(src)
    if not c.ok:
        raise RuntimeError(c.error or "this file cannot be read")
    _, out_args, chain = build(recipe, c)
    vf = [part for part in chain.split(",") if part and not part.startswith(("setpts=", "fade="))]
    if edge:
        vf.append(_scale(edge))
    args = [exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t):.3f}",
            "-i", str(src)]
    if vf:
        args += ["-vf", ",".join(vf)]
    dst.parent.mkdir(parents=True, exist_ok=True)
    found = _run([*args, "-frames:v", "1", str(dst)])
    if not dst.is_file():
        raise RuntimeError((found.stderr or "no frame").strip()[-160:])
    return dst


def cover(src: Path, t: float, dst: Path) -> Path:
    """Pull one frame out as a still, so the photo editor can finish it as a cover."""
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg is not available on this machine")
    png = dst.with_suffix(".png")
    found = _run([exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t):.3f}",
                  "-i", str(src), "-frames:v", "1", str(png)], timeout=180)
    if not png.is_file():
        raise RuntimeError((found.stderr or "no frame").strip()[-160:])
    with Image.open(png) as im:
        im.convert("RGB").save(dst, quality=95)
    png.unlink(missing_ok=True)
    return dst


def clip_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES)
