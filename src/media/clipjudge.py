"""How judgy this app is about a clip.

Five frames are pulled out of her own file and each one is measured by the same photo
judge she already sees on the Photos page, so a frame that is crooked reads crooked in
both places. On top of that sit four things a still photo cannot show: whether anything
happens in the first two seconds, whether the clip moves at all, whether the frame drifts
while she holds it, and whether there is usable sound.

The weights are the app's own opinion, added up below and printed on the page. They are a
ranking of her clips against each other, not a promise about reach.
"""

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from src.media import clip as clipmod
from src.media.aesthetic import Component, judge_photo
from src.media.judge import measure

CLIP_WEIGHTS = {"look": 0.30, "hook": 0.20, "movement": 0.15, "stability": 0.15,
                "length": 0.10, "sound": 0.10}

CLIP_LABELS = {
    "look": "how the frames read",
    "hook": "something happens at once",
    "movement": "the clip moves",
    "stability": "the frame holds level",
    "length": "it is short enough",
    "sound": "there is something to hear",
    "readable": "the file could be read",
}

BAND_SECONDS = 30.0
HOOK_SECONDS = 2.0
GLUED_AT = 0.012
MOVING_AT = 0.06
DRIFT_FLOOR = 1.2
DRIFT_ZERO = 4.2
SILENT_DB = -35.0


@dataclass
class Frame:
    at: float
    path: Path
    judgement: object

    @property
    def score(self) -> float:
        return self.judgement.score


@dataclass
class ClipVerdict:
    clip: clipmod.Clip
    frames: list[Frame] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    drift: float = 0.0
    measured: bool = False
    change: list[float] = field(default_factory=list)

    @property
    def score(self) -> float:
        total = sum(CLIP_WEIGHTS[c.name] * c.score for c in self.components)
        return round(total * 10, 1)

    @property
    def band(self) -> str:
        return "strong" if self.score >= 7 else "workable" if self.score >= 5 else "weak"

    @property
    def ideas(self) -> list[str]:
        return [c.idea for c in sorted(self.components, key=lambda c: c.score)
                if c.idea and c.score < 0.72]

    @property
    def worst(self) -> list[Component]:
        return sorted(self.components, key=lambda c: c.score)

    @property
    def limit(self) -> str:
        return self.clip.limit


def _difference(a: Path, b: Path) -> float:
    """Mean absolute grey difference between two frames, 0 to 1."""
    with Image.open(a) as raw_a, Image.open(b) as raw_b:
        ga = ImageOps.exif_transpose(raw_a).convert("L").resize((96, 96), Image.BILINEAR)
        gb = ImageOps.exif_transpose(raw_b).convert("L").resize((96, 96), Image.BILINEAR)
    hist = ImageChops.difference(ga, gb).histogram()
    total = sum(hist) or 1
    return sum(i * v for i, v in enumerate(hist)) / total / 255


def _ramp(value: float, floor: float, ceiling: float) -> float:
    """0 at `floor`, 1 at `ceiling`, clamped - so a bigger number always reads better."""
    if ceiling == floor:
        return 0.0
    return max(0.0, min(1.0, (value - floor) / (ceiling - floor)))


def judge_clip(path: Path, workdir: Path, n: int = clipmod.SAMPLE_FRAMES) -> ClipVerdict:
    info = clipmod.loudness(path, clipmod.probe(path))
    verdict = ClipVerdict(clip=info)
    if not info.ok:
        verdict.components = [Component(
            "readable", 0.0, info.error,
            idea="Export it again as an mp4 from the phone or the editor.")]
        return verdict

    workdir.mkdir(parents=True, exist_ok=True)
    stem = (path.stem.replace(" ", "-")[:40] or "clip")
    times = clipmod.sample_times(info.duration, n)
    for i, t in enumerate(times):
        try:
            frame = clipmod.seek(path, t, workdir / f"{stem}-{i}.png", clipmod.DECODE_EDGE)
        except RuntimeError:
            continue
        reading = measure(frame)
        if reading.error:
            continue
        verdict.frames.append(Frame(at=t, path=frame, judgement=judge_photo(frame, reading)))

    if not verdict.frames:
        verdict.components = [Component(
            "readable", 0.0, "no frame could be decoded from this clip",
            idea="Try exporting it again as an mp4.")]
        return verdict

    scores = sorted(f.score for f in verdict.frames)
    median = scores[len(scores) // 2] / 10
    changes = [round(_difference(a.path, b.path), 4)
               for a, b in zip(verdict.frames, verdict.frames[1:])]
    verdict.change = changes
    early = _early_change(path, workdir, stem, info.duration)
    tilts = [abs(f.judgement.tilt) for f in verdict.frames]
    verdict.drift = round(max(tilts), 2)
    levels = [comp.score for f in verdict.frames for comp in f.judgement.components
              if comp.name == "level"]
    verdict.measured = any(abs(s - 0.7) > 0.01 for s in levels)
    repeated = [i for i, d in enumerate(changes) if d < GLUED_AT]

    c = verdict.components
    c.append(Component(
        "look", round(median, 3),
        f"the middle frame scores {round(median * 10, 1)} / 10 on the same judge as your "
        f"photos ({len(scores)} frames read)",
        idea="Finish the strongest frame in the photo editor and use it as the cover."
        if median < 0.6 else ""))
    c.append(Component(
        "hook", round(_ramp(early, GLUED_AT, 0.09), 3),
        f"the picture changes by {early:.3f} in the first two seconds"
        + (" - that is the same shot twice" if early < GLUED_AT else ""),
        idea=f"Start the clip at {times[min(1, len(times) - 1)]:.1f}s - the editor can cut "
        "the flat opening off." if early < GLUED_AT else ""))
    typical = sorted(changes)[len(changes) // 2] if changes else 0.0
    c.append(Component(
        "movement", round(_ramp(typical, GLUED_AT, MOVING_AT), 3) if changes else 0.5,
        f"the sampled frames change by {typical:.3f} on average and {max(changes):.3f} at most"
        if changes else "only one frame could be compared",
        idea=f"{len(repeated)} of the {len(changes)} gaps between sampled frames are the same "
        "shot - cut the stretch that does not move."
        if changes and len(repeated) >= len(changes) - 1 else ""))
    if not verdict.measured:
        stable, lean_why = 0.7, "no frame has a line strong enough to measure against"
    elif verdict.drift < DRIFT_FLOOR:
        stable, lean_why = 1.0, f"the strongest line holds within {verdict.drift}°"
    else:
        stable = _ramp(DRIFT_ZERO, verdict.drift, DRIFT_FLOOR)
        lean_why = f"the strongest line leans up to {verdict.drift}°"
    c.append(Component(
        "stability", round(stable, 3), lean_why,
        idea=f"Straighten it by {verdict.drift:.1f}° - the editor does this exactly."
        if verdict.measured and verdict.drift >= DRIFT_FLOOR else ""))
    c.append(Component(
        "length", round(1.0 if info.duration <= BAND_SECONDS else
                        _ramp(BAND_SECONDS * 3, info.duration, BAND_SECONDS), 3),
        f"{info.duration:.1f}s, against the {BAND_SECONDS:.0f}s band this app sets for itself",
        idea=f"Cut it to {BAND_SECONDS:.0f}s - keep the part where it moves."
        if info.duration > BAND_SECONDS else ""))
    if not info.has_audio:
        sound, why = 0.2, "there is no sound track in the file at all"
    elif info.max_db is None:
        sound, why = 0.6, "there is a sound track; its level was not readable"
    elif info.max_db < SILENT_DB:
        sound, why = 0.4, f"the track peaks at {info.max_db:.0f} dB - near silence"
    else:
        sound, why = 1.0, f"the track peaks at {info.max_db:.0f} dB"
    c.append(Component(
        "sound", sound, why,
        idea="Mute it and put the line on the cover, or record over it - a silent clip reads "
        "as a mistake." if sound < 0.72 else ""))
    return verdict


def _early_change(path: Path, workdir: Path, stem: str, duration: float) -> float:
    """How much the picture moves between the first beat and the second."""
    if duration <= 0.4:
        return 1.0
    a = clipmod.seek(path, 0.05, workdir / f"{stem}-hook-a.png", clipmod.DECODE_EDGE)
    b = clipmod.seek(path, min(HOOK_SECONDS, duration * 0.6), workdir / f"{stem}-hook-b.png",
                     clipmod.DECODE_EDGE)
    return round(_difference(a, b), 4)


def suggest(verdict: ClipVerdict) -> list:
    """The recipe the measurements justify - offered as a starting point, never applied
    behind her back."""
    out = []
    if verdict.clip.duration > BAND_SECONDS:
        out.append(["trim", 0.0, BAND_SECONDS])
    if verdict.measured and verdict.drift >= DRIFT_FLOOR:
        out.append(["rotate", -verdict.drift])
    if verdict.clip.silent:
        out.append(["mute", 1])
    return out
