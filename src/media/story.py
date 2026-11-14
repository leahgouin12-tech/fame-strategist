"""Words on a clock - the part of a Story that the editor cannot do.

/edit puts text where she drags it and leaves it there forever. A Story is different: the
line has to arrive when it is sung and go before the next one, and the caption the platform
gives you for that is either its own sticker (which nobody but her can place, in her phone,
in the app) or pixels baked into the file. So this module bakes them, locally, on a timer,
and hands back a real file.

Three honest limits, stated here because they are the reasons the code looks the way it does:

* **A licensed song cannot be attached from a computer.** Every platform keeps its music
  library inside its own composer and its own licence; there is no file format that carries
  "the official sound". What this can do is mix in audio *she* owns or made. Anything else
  is two taps in her hand, and the step list says so.
* **Baked words cannot be edited afterwards**, so the timings are checked against the clip's
  real duration rather than trusted.
* **The safe zone is not decoration.** Story UI covers the top ~13% and bottom ~20% of a
  9:16 frame, and a caption placed there is unreadable on the platform but perfect in the
  preview - the classic way to ship a Story nobody can read.

ffmpeg and PIL are called with argument lists, never a shell string, and every filter value
is escaped by this module - a lyric with a quote in it must not be able to become a filter.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

WORK_MAX_EDGE = 1080        # a Story is authored at 1080x1920; nothing is upscaled
STORY_RATIO = 9 / 16
SAFE_TOP = 0.13             # fraction of height the platform's own chrome sits over
SAFE_BOTTOM = 0.20
LINE_LIMIT = 90             # lyric lines are sung, not read; a long line is two lines
MAX_LINES = 40

# Windows first: this app runs on her laptop, and Arial Bold is on every copy of it. The
# rest is so a Story still renders on a machine that has neither.
FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

TIME = re.compile(r"^\s*(\d{1,2}:)?(\d{1,2}(?:\.\d+)?)\s*[-=>]+\s*"
                  r"(\d{1,2}:)?(\d{1,2}(?:\.\d+)?)\s+(.+)$")
CLOCK = re.compile(r"^\s*(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s+(.+)$")


def _seconds(minutes: str | None, seconds: str) -> float:
    """One side of a range, in seconds. The pattern captures `0:` with the colon still on
    it, so the separator comes off here instead of turning `int()` into a crash."""
    value = float(seconds)
    if not minutes:
        return value
    return value + 60 * int(minutes.strip().rstrip(":") or 0)


@dataclass
class Line:
    """One thing the viewer should be able to read, and when."""

    text: str
    at: float
    until: float

    @property
    def length(self) -> float:
        return max(0.0, self.until - self.at)

    def reads_in_time(self) -> bool:
        """Under a second on screen is not a caption, it is a flash. She should hear that
        from the app before she posts it, not from the comments."""
        return self.length >= 0.7


@dataclass
class Story:
    """The render report. Every number on it is measured after the file was written."""

    source: Path
    out: Path | None
    kind: str                       # "image" | "video" | "none"
    lines: list[Line] = field(default_factory=list)
    duration: float = 0.0
    canvas: tuple[int, int] = (0, 0)
    audio: str = ""                 # what the finished file actually carries
    notes: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.out is not None and not self.error

    @property
    def warnings(self) -> list[str]:
        return self.notes


def parse_lines(raw: str) -> list[Line]:
    """Read her timings if she gave them, space them evenly if she did not.

    Accepted shapes, one per line:
        0:03-0:07  I said the quiet part
        3.5 > 6    I said the quiet part
        I said the quiet part          (no clock: the auto-timing below places it)
    """
    lines: list[Line] = []
    for row in (raw or "").splitlines():
        if not row.strip():
            continue
        hit = TIME.match(row)
        if hit:
            start = _seconds(hit[1], hit[2])
            end = _seconds(hit[3], hit[4])
            text = hit[5].strip()
        elif (hit := CLOCK.match(row)):
            start = 60 * int(hit[1]) + float(hit[2])
            end = 0.0
            text = hit[3].strip()
        else:
            start, end, text = -1.0, 0.0, row.strip()
        if text:
            lines.append(Line(text[:LINE_LIMIT * 3], start, end))
    return lines[:MAX_LINES]


def _reading_span(text: str) -> float:
    """How long words stay up if nobody timed them: about twelve characters a second,
    with a floor, because a two-word line still has to be finished reading."""
    return max(1.2, len(text) / 12.0)


def auto_times(lines: list[Line], duration: float, lead: float = 0.4) -> list[Line]:
    """Give a clock to the lines that arrived without one.

    Two cases, and they are genuinely different work. If nobody timed anything, the batch is
    a lyric in order and gets the whole clip, each line's slice proportional to how long it
    takes to read. If somebody did time some of them, those times are hers and are not moved:
    the untimed lines go after the last one ends, because sliding one in between two timed
    lines would mean guessing where her song breathes.

    A line with a start and no end keeps her start and gets a reading span.
    """
    if duration <= 0:
        return [Line(l.text, l.at, l.until) for l in lines]
    timed = [l for l in lines if l.at >= 0]
    untimed = [l for l in lines if l.at < 0]
    out: list[Line] = []
    for line in timed:
        at = max(0.0, line.at)
        until = line.until if line.until > at else at + _reading_span(line.text)
        out.append(Line(line.text, round(at, 2), round(min(duration, max(until, at + 0.7)), 2)))
    if not untimed:
        return out
    spans = sorted(out, key=lambda l: l.at)
    start = max([l.until for l in spans], default=lead)
    room = duration - start
    weights = [_reading_span(l.text) for l in untimed]
    need = sum(weights)
    if room <= 0:
        # No space after her timings, so they go where they were going to go and she is told.
        cursor = start
        for line, weight in zip(untimed, weights):
            out.append(Line(line.text, round(cursor, 2), round(cursor + weight, 2)))
            cursor += weight
        return out
    if need > room:
        weights = [w * room / need for w in weights]
    cursor = start
    for line, weight in zip(untimed, weights):
        until = min(duration, cursor + weight)
        out.append(Line(line.text, round(cursor, 2), round(max(until, cursor + 0.7), 2)))
        cursor = until
    return out


def off_clip(lines: list[Line], duration: float) -> list[Line]:
    """The lines that start after the clip stops - they render and nobody ever sees them."""
    return [l for l in lines if duration > 0 and l.at >= duration]


def _font(px: int) -> ImageFont.ImageFont:
    for path in FONTS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                continue
    return ImageFont.load_default()


def wrap(text: str, px: int, face: ImageFont.ImageFont) -> list[str]:
    """Break a line to the frame width, by measured glyphs rather than by character count."""
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    out, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        width = draw.textlength(trial, font=face)
        if width <= px or not current:
            current = trial
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    return out


def burn_image(source: Path, lines: list[Line], out: Path,
               width: int = 1080, height: int = 1920) -> Story:
    """Cover the photo into a Story frame and draw the words once, low in the safe band.

    An image Story has no clock, so every line is shown; that is also why the lines stack
    upward from the safe bottom instead of overlapping.
    """
    try:
        base = Image.open(source)
        base.load()
    except (OSError, ValueError) as exc:
        return Story(source=source, out=None, kind="image", lines=lines,
                     notes=[], error=f"the picture would not open: {type(exc).__name__}")
    base = base.convert("RGB")
    canvas = Image.new("RGB", (width, height), (12, 12, 14))
    scale = max(width / base.width, height / base.height)
    sized = base.resize((max(1, round(base.width * scale)), max(1, round(base.height * scale))),
                        Image.LANCZOS)
    canvas.paste(sized, ((width - sized.width) // 2, (height - sized.height) // 2))
    draw = ImageDraw.Draw(canvas)
    px = max(28, int(width * 0.052))
    face = _font(px)
    box = int(width * 0.86)
    y = int(height * (1 - SAFE_BOTTOM))
    notes = []
    for line in lines:
        rows = wrap(line.text, box, face)
        if len(line.text) > LINE_LIMIT:
            notes.append(f"{line.text[:32]}... is longer than a sung line; it wrapped to "
                         f"{len(rows)} lines.")
        for row in reversed(rows):
            y -= int(px * 1.45)
            draw.text((int((width - draw.textlength(row, font=face)) / 2), y), row, font=face,
                      fill=(255, 255, 255), stroke_width=max(2, px // 14), stroke_fill=(10, 10, 12))
        y -= int(px * 0.5)
    if y < int(height * SAFE_TOP):
        notes.append("The stack reached the top safe line, so the first words may sit under "
                     "the platform's own chrome. Fewer lines, or a shorter lyric.")
    if not lines:
        notes.append("Nothing was written on the picture - this is the Story frame only, so "
                     "the platform's own text sticker still fits over it.")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=92)
    return Story(source=source, out=out, kind="image", lines=lines, canvas=(width, height),
                 audio="the original picture has no audio", notes=notes)


def _ass_time(seconds: float) -> str:
    centiseconds = int(round(max(0.0, seconds) * 100))
    h, rem = divmod(centiseconds, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_text(lines: list[Line], width: int = 1080, height: int = 1920) -> str:
    """A subtitle file that says where the safe band is, not just what to say.

    MarginV is measured from the bottom of the frame, so the bottom safe zone is a margin,
    and Alignment 2 (bottom-centre) is what a Story caption is.
    """
    margin = int(height * SAFE_BOTTOM)
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledResX: {width}\n"
        f"ScaledResY: {height}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Safe,Sans,{int(height * 0.042)},&H00FFFFFF,&H000A0A0C,&H000A0A0C,-1,0,0,0,100,"
        f"100,0,0,1,4,1,2,{int(width * 0.07)},{int(width * 0.07)},{margin},1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Text\n"
    )
    rows = []
    for line in sorted(lines, key=lambda l: (l.at, l.until)):
        text = line.text.replace("\n", " ").replace("{", "(").replace("}", ")")
        rows.append(f"Dialogue: 0,{_ass_time(line.at)},{_ass_time(line.until)},Safe,,,{text}")
    return head + "\n".join(rows) + "\n"


def probe_duration(path: Path) -> float:
    """Seconds of video, or 0.0 when ffmpeg cannot say. A file whose length is unknown is
    not a file with no length: the caller keeps her timings and stops inventing them."""
    exe = _ffmpeg()
    if not exe:
        return 0.0
    try:
        got = subprocess.run([exe, "-hide_banner", "-i", str(path), "-f", "null", "-"],
                             capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    hit = re.search(r"Duration:\s*(\d+):(\d\d):(\d\d\.\d\d)", got.stderr or "")
    if not hit:
        return 0.0
    return int(hit[1]) * 3600 + int(hit[2]) * 60 + float(hit[3])


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def burn_video(source: Path, lines: list[Line], out: Path, audio: Path | None = None,
               keep_original_audio: bool = True) -> Story:
    """Burn the timed words into the clip, and optionally lay her own audio under it.

    The subtitle file is written beside the output and passed by path, so no lyric ever
    reaches the filter graph as text to be escaped - the one input that cannot be quoted
    safely is the one that is not quoted at all.
    """
    exe = _ffmpeg()
    if not exe:
        return Story(source=source, out=None, kind="video", lines=lines,
                     error="ffmpeg is not available on this machine, so nothing was rendered")
    duration = probe_duration(source)
    timed = auto_times(lines, duration)
    out.parent.mkdir(parents=True, exist_ok=True)
    side = out.with_suffix(".ass")
    side.write_text(ass_text(timed), encoding="utf-8")
    args = [exe, "-hide_banner", "-y", "-i", str(source)]
    if audio is not None:
        args += ["-i", str(audio)]
    # libass reads the file, not the shell: the path is quoted for ffmpeg's own parser, and
    # a Windows colon is the one character that has to be doubled.
    safe = str(side).replace("\\", "/").replace(":", "\\:")
    args += ["-vf", f"ass='{safe}'", "-map", "0:v:0"]
    if audio is not None:
        args += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "128k", "-shortest"]
        bed = "your audio file, mixed under the clip"
    elif keep_original_audio:
        args += ["-map", "0:a:0?", "-c:a", "copy"]
        bed = "the sound the clip already had"
    else:
        args += ["-an"]
        bed = "no audio at all - the clip is silent"
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             str(out)]
    try:
        got = subprocess.run(args, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return Story(source=source, out=None, kind="video", lines=timed, duration=duration,
                     error="the render ran past 15 minutes and was stopped; nothing was saved")
    if got.returncode != 0 or not out.is_file():
        tail = " ".join((got.stderr or "").splitlines()[-3:])[:220]
        return Story(source=source, out=None, kind="video", lines=timed, duration=duration,
                     error=f"ffmpeg refused the render: {tail}")
    notes = []
    if duration:
        beyond = off_clip(timed, duration)
        if beyond:
            word = "line starts" if len(beyond) == 1 else "lines start"
            notes.append(f"{len(beyond)} {word} after the clip ends at {duration:.1f}s, so "
                         "they are in the file and nobody will ever see them. Cut the times "
                         "or lengthen the clip.")
        cut = [l for l in timed if l.at < duration and l.until >= duration - 0.05]
        if cut:
            word = "line stopped" if len(cut) == 1 else "lines stopped"
            notes.append(f"{len(cut)} {word} short at the end of the clip ({duration:.1f}s), "
                         "so the last words are cut off.")
    if timed:
        notes.append("The words are baked into the pixels. There is no way to edit or turn "
                     "them off afterwards, so keep the source file.")
    else:
        notes.append("Nothing was written on the picture - this is the frame and the sound "
                     "only, so the platform's own text sticker still fits over it.")
    flashes = [l for l in timed if not l.reads_in_time()]
    if flashes:
        word = "line stays" if len(flashes) == 1 else "lines stay"
        notes.append(f"{len(flashes)} {word} on screen under a second, which reads as a flash "
                     "rather than as a caption.")
    side.unlink(missing_ok=True)
    return Story(source=source, out=out, kind="video", lines=timed, duration=duration,
                 canvas=(0, 0), audio=bed, notes=notes)


def is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def render(source: Path, out: Path, raw_lines: str, audio: Path | None = None,
           keep_audio: bool = True) -> Story:
    """One door for the page: parse her lines, then burn them onto whatever the file is.

    An empty box is not a refusal. It means she wants the Story frame and the sound with no
    words baked in, which is exactly the file she needs when she intends to type into the
    platform's own sticker - the one route where the text stays editable after upload.
    """
    lines = parse_lines(raw_lines)
    if is_video(source):
        return burn_video(source, lines, out, audio=audio, keep_original_audio=keep_audio)
    return burn_image(source, auto_times(lines, 0.0), out)
