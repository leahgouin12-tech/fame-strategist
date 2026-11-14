"""Rebuild the posts the ledger already ranked for the frames they have never run in.

The lab works out which hypothesis is winning. This is what happens next: the posts under the
arm the numbers favoured are cut to the shape each placement actually wants and rewritten for
that placement from the samples she pasted, so one post that worked becomes several that
inherit the reason it worked.

Nothing here invents a picture. A crop is the same ratio chip the editor runs, a clip cut is
the clip engine's own ratio operation, and a caption comes from the voice writer. A post whose
file this app does not hold is named and skipped in so many words, because a variant made from
a number instead of the picture is a deliverable that does not exist."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.media import clip as clipmod
from src.media import edit
from src.media.judge import IMAGE_SUFFIXES
from src.metrics.adapt import _rate
from src.metrics.correlate import stem
from src.strategist import voice

MIN_EDGE = 600        # under this the platform upscales the frame, which is where a
#                      repurposed post starts looking cheap
SCAN = 12             # how far down the ranked list one pass looks before it gives up

# Width over height, which is the number edit's crop chip and clip's ratio op both take.
SHAPE = {"tiktok": 9 / 16, "reels": 9 / 16, "x": 1.0}
LABEL = {"tiktok": "9:16", "reels": "9:16", "x": "1:1"}
# The same shape for a file name. A colon cannot go there: on Windows "a1-9:16.jpg" is not a
# file, it is an alternate data stream hanging off a file called "a1-9", which is exactly the
# kind of deliverable that exists in the list and nowhere else.
TAG = {"tiktok": "9x16", "reels": "9x16", "x": "1x1"}


@dataclass
class Cut:
    """One rebuilt post: the file in the shape of the placement, and the copy written for it."""
    ref: str
    arm: str
    platform: str
    shape: str
    kind: str
    file: str
    hook: str = ""
    caption: str = ""
    tags: list = field(default_factory=list)
    why: list = field(default_factory=list)

    @property
    def block(self) -> str:
        return f"{self.hook}\n\n{self.caption}\n\n{' '.join(self.tags)}"


@dataclass
class Pass:
    """What one repurposing pass produced, and the posts it could not touch."""
    cuts: list
    skipped: list
    headline: str
    detail: list = field(default_factory=list)

    @property
    def made(self) -> int:
        return len(self.cuts)

    @property
    def posts(self) -> int:
        return len({c.ref for c in self.cuts})


def picks(got, rows, limit: int = SCAN) -> list:
    """(post, arm, its own rate) in the order worth rebuilding.

    The ledger's own arm order decides who goes first - the arm the numbers favoured is the
    one worth remaking - and inside an arm the posts sort by what each one did on its own.
    A post with no arm label is not a candidate at all: there would be no hypothesis to carry
    into the next frame, so it would be a crop with a reason attached afterwards."""
    own = {}
    for row in rows:
        own[row.post_ref] = _rate([row])
    out = []
    for arm in got.arms:
        for ref in sorted(arm.refs, key=lambda r: (-own.get(r, 0.0), r)):
            out.append((ref, arm.label, own.get(ref, 0.0)))
    return out[:int(limit)]


def source_for(ref: str, inbox: Path, clips: Path):
    """The file behind a stored post, or (None, None).

    Matched on the name she posted under, the same key the correlator uses, and searched only
    in the folders this app already reads. A post whose file is not here stays a number."""
    want = stem(ref)
    if not want:
        return None, None
    for folder, kind in ((inbox, "photo"), (inbox / "edited", "photo"),
                         (inbox / "clean", "photo"),
                         (clips, "clip"), (clips / "edited", "clip")):
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.iterdir()):
            if not candidate.is_file() or stem(candidate.name) != want:
                continue
            if kind == "photo" and candidate.suffix.lower() in IMAGE_SUFFIXES:
                return kind, candidate
            if kind == "clip" and candidate.suffix.lower() in clipmod.VIDEO_SUFFIXES:
                return kind, candidate
    return None, None


def _next_name(directory: Path, stem_name: str, suffix: str) -> Path:
    """Never overwrite what is already there; a repurposed post is an addition."""
    dst = directory / f"{stem_name}{suffix}"
    n = 2
    while dst.exists():
        dst = directory / f"{stem_name}-{n}{suffix}"
        n += 1
    return dst


def _missing(ref: str, arm: str) -> str:
    return (f"{ref} ran under {arm} and the numbers are stored, but this app does not hold "
            "the file. Put it in the inbox folder (or attach it to that day on Today) and the "
            "next pass cuts it.")


def _too_small(ref: str, platform: str, edge: int) -> str:
    return (f"{ref} has {edge} px on its short side after the {LABEL[platform]} crop, under "
            f"the {MIN_EDGE} this app will post, so that one is left out rather than "
            "upscaled.")


def _variants(subject: str, arm: str, day: date, profile):
    return {v.platform: v for v in voice.package(subject, arm, day, profile)}


def photo_cuts(ref: str, arm: str, src: Path, out_dir: Path, subject: str, day: date,
               profile) -> tuple:
    """The same ratio chip the editor uses, applied once per distinct shape.

    TikTok and reels want the same frame, so the crop is computed and written once and both
    cuts point at that file - two identical JPEGs with different names would be padding."""
    made, left_out = [], []
    variants = _variants(subject, arm, day, profile)
    image = edit.load(src)
    by_shape: dict = {}
    for platform in voice.PLATFORMS:
        ratio = SHAPE[platform]
        if ratio not in by_shape:
            cut = edit.APPLIERS["crop"](image, [ratio])
            if min(cut.size) < MIN_EDGE:
                by_shape[ratio] = (None, min(cut.size))
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = _next_name(out_dir, f"{src.stem}-{TAG[platform]}"[:70], ".jpg")
            cut.save(dst, "JPEG", quality=edit.SAVE_QUALITY)
            by_shape[ratio] = (dst, 0)
        dst, edge = by_shape[ratio]
        if dst is None:
            left_out.append(_too_small(ref, platform, edge))
            continue
        words = variants[platform]
        made.append(Cut(ref=ref, arm=arm, platform=platform, shape=LABEL[platform],
                        kind="photo", file=dst.name, hook=words.hook, caption=words.caption,
                        tags=list(words.tags), why=list(words.why)))
    return made, left_out


def clip_cuts(ref: str, arm: str, src: Path, out_dir: Path, subject: str, day: date,
              profile) -> tuple:
    """The clip engine's own ratio operation, one encode per distinct shape."""
    made, left_out = [], []
    variants = _variants(subject, arm, day, profile)
    info = clipmod.probe(src)
    if not info.ok:
        return [], [f"{ref} is here but this machine cannot read it: "
                    f"{info.error or 'ffmpeg said nothing'}"]
    by_shape: dict = {}
    for platform in voice.PLATFORMS:
        ratio = SHAPE[platform]
        if ratio not in by_shape:
            width, height = clipmod._ratio_pair(info.width, info.height, ratio)
            if min(width, height) < MIN_EDGE:
                by_shape[ratio] = (None, min(width, height))
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            dst = _next_name(out_dir, f"{src.stem}-{TAG[platform]}"[:70], ".mp4")
            clipmod.export(src, dst, clipmod.normalize([["ratio", ratio]]), info)
            by_shape[ratio] = (dst, 0)
        dst, edge = by_shape[ratio]
        if dst is None:
            left_out.append(_too_small(ref, platform, edge))
            continue
        words = variants[platform]
        made.append(Cut(ref=ref, arm=arm, platform=platform, shape=LABEL[platform],
                        kind="clip", file=dst.name, hook=words.hook, caption=words.caption,
                        tags=list(words.tags), why=list(words.why)))
    return made, left_out


def run(got, rows, profile, day: date, subject: str, inbox: Path, clips: Path, out_dir: Path,
        limit: int = 2, ffmpeg: bool | None = None) -> Pass:
    """Cut the ranked posts into the placements they have not run in.

    `limit` counts posts, not files: one post becomes a cut per placement. The scan goes
    further down the ranked list than that, so a winning arm whose files are missing does not
    empty the page - the next arm's posts are tried, and every post that could not be touched
    is still named."""
    if ffmpeg is None:
        ffmpeg = clipmod.available()
    if not got.arms:
        return Pass([], [], "Nothing is ranked yet, so there is no post to rebuild.",
                    detail=["The lab ranks the posts under each arm. Until at least two arms "
                            "have posts, there is no winner to remake."])
    wanted = picks(got, rows)
    made, skipped, done = [], [], 0
    for ref, arm, _own in wanted:
        if done >= int(limit):
            break
        kind, src = source_for(ref, inbox, clips)
        if src is None:
            skipped.append(_missing(ref, arm))
            continue
        if kind == "clip" and not ffmpeg:
            skipped.append(f"{ref} is a clip and this machine has no ffmpeg to cut it with, "
                           "so nothing was written for it.")
            continue
        try:
            cuts, left_out = (clip_cuts if kind == "clip" else photo_cuts)(
                ref, arm, src, out_dir, subject, day, profile)
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{ref} is here but could not be cut: {exc}")
            continue
        made += cuts
        skipped += left_out
        if cuts:
            done += 1
    if not made:
        return Pass([], skipped, f"This app holds none of the files behind the {got.labelled} "
                                 "ranked posts.",
                    detail=["Repurposing works on pictures it can actually open, so the posts "
                            "have to be in the inbox folder - the numbers alone are not a "
                            "source file."])
    posts = len({c.ref for c in made})
    return Pass(made, skipped,
                f"{len(made)} cut{'s' if len(made) != 1 else ''} from {posts} "
                f"post{'s' if posts != 1 else ''} the ledger already ranked.",
                detail=[f"Source: {c.ref} ({c.kind}), rebuilt for {c.platform} at {c.shape}."
                        for c in made])
