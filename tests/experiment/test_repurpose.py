"""The repurposing pass, checked against the files it actually writes.

What is under test is that a variant is a real deliverable: the crop exists on disk at the
ratio the placement wants, the copy for each platform comes from the samples she pasted, the
original is never touched, and a post this app cannot open is named as missing instead of
being represented by a file that was never written. The refusals are the feature - a pass that
reports three cuts from a number it has no picture for is the fake success this app is told not
to ship.
"""

from datetime import date

import pytest
from PIL import Image

from src.engines.offline import OfflineEngine
from src.experiment import ledger as L
from src.experiment import repurpose as R
from src.media import clip as clipmod
from src.metrics.ingest import MetricRow
from src.strategist import voice
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES

START = date(2026, 11, 9)
PLAN = compose_plan(ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)),
                    OfflineEngine(), START)
A = PLAN.weeks[0].experiment
B = PLAN.weeks[1].experiment

SAMPLES = ["i shot this at golden hour and it worked\n\n#goldenhour #ootd",
           "low light is fine honestly, just push it",
           "three takes, kept the second one"]


def row(ref, follows, arm, views=1000):
    return MetricRow("logged", ref, START, views * 3, views, 22.0, follows, 4, 1,
                     hypothesis=arm)


def two_arms(top_count=3, bottom_count=3):
    """`top_count` posts under the arm that converts well, `bottom_count` under the one that
    does not - the state the lab has already ranked."""
    rows = [row(f"win{i}.jpg", 40 - i, A) for i in range(top_count)]
    rows += [row(f"lose{i}.jpg", 5, B) for i in range(bottom_count)]
    return rows


@pytest.fixture
def shelf(tmp_path):
    """An inbox folder with real pictures in it, the way she would leave it."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    clips = tmp_path / "clips"
    clips.mkdir()
    out = inbox / "edited"
    return {"tmp": tmp_path, "inbox": inbox, "clips": clips, "out": out}


def put(shelf, name, size=(1200, 1600), colour=(180, 120, 90)):
    Image.new("RGB", size, colour).save(shelf["inbox"] / name)
    return shelf["inbox"] / name


def run(shelf, rows, limit=2, ffmpeg=False, profile=None):
    return R.run(L.ledger(rows), rows, profile or voice.learn(SAMPLES), START,
                 "the outfit test", shelf["inbox"], shelf["clips"], shelf["out"],
                 limit=limit, ffmpeg=ffmpeg)


def test_the_pass_starts_with_the_arm_the_ledger_ranks_first():
    rows = two_arms()
    got = L.ledger(rows)
    picked = R.picks(got, rows)
    assert {arm for _ref, arm, _own in picked} == {A, B}
    assert picked[0][1] == A, "the arm the numbers favoured goes first"
    assert picked[0][2] > picked[-1][2], "and inside it, the posts that did best on their own"


def test_a_post_with_no_arm_is_never_a_candidate():
    rows = two_arms() + [row("orphan.jpg", 90, "")]
    refs = [ref for ref, _arm, _own in R.picks(L.ledger(rows), rows)]
    assert "orphan.jpg" not in refs, "there would be no hypothesis to carry into the frame"


def test_a_photo_is_cut_to_the_shape_each_placement_wants(shelf):
    put(shelf, "win0.jpg", size=(1200, 1600))
    passed = run(shelf, two_arms(), limit=1)
    assert passed.made == 3, passed.skipped
    sizes = {}
    for cut in passed.cuts:
        with Image.open(shelf["out"] / cut.file) as im:
            sizes[cut.platform] = (im.width / im.height, im.size)
    assert round(sizes["tiktok"][0], 3) == round(9 / 16, 3)
    assert round(sizes["x"][0], 3) == 1.0
    assert sizes["tiktok"][1][1] >= R.MIN_EDGE, "a story frame she can actually post"


def test_the_original_is_never_touched(shelf):
    src = put(shelf, "win0.jpg")
    before = src.read_bytes()
    run(shelf, two_arms(), limit=1)
    assert src.read_bytes() == before
    assert src.name not in [c.file for c in run(shelf, two_arms(), limit=1).cuts]


def test_the_two_platforms_that_want_the_same_frame_share_one_file(shelf):
    put(shelf, "win0.jpg")
    passed = run(shelf, two_arms(), limit=1)
    by = {c.platform: c.file for c in passed.cuts}
    assert by["tiktok"] == by["reels"], "two names for identical pixels is padding"
    assert len(list(shelf["out"].iterdir())) == 2, "9:16 once and 1:1 once"


def test_no_file_names_with_a_colon_because_windows_reads_them_as_streams(shelf):
    """Measured on this machine: a file written as "a1-9:16.jpg" appears on disk as "a1-9"
    with the picture in an alternate data stream, so the deliverable exists in the list and
    nowhere else."""
    put(shelf, "win0.jpg")
    put(shelf, "win1.jpg")
    passed = run(shelf, two_arms(), limit=2)
    assert passed.cuts, "nothing to check if the pass wrote nothing"
    for cut in passed.cuts:
        assert ":" not in cut.file, cut.file
        assert (shelf["out"] / cut.file).is_file(), f"{cut.file} was reported and not written"


def test_a_missing_file_does_not_waste_the_pass(shelf):
    """win0 converted best and is not here; win1 is. A pass that stopped at the first miss
    would report nothing for a shelf that holds the picture, and one that invented a file for
    win0 would report something that does not exist."""
    put(shelf, "win1.jpg")
    passed = run(shelf, two_arms(top_count=3), limit=1)
    missing = [s for s in passed.skipped if "does not hold" in s]
    assert [s for s in missing if s.startswith("win0.jpg")], missing
    assert "Put it in the inbox folder" in missing[0], "the sentence has to carry the fix"
    assert passed.cuts and {c.ref for c in passed.cuts} == {"win1.jpg"}


def test_an_empty_shelf_names_the_posts_it_could_not_open(shelf):
    passed = run(shelf, two_arms(), limit=2)
    assert not passed.cuts
    assert "holds none of the files" in passed.headline
    assert len(passed.skipped) == 6, "every ranked post is accounted for, not a silent zero"
    assert all("does not hold" in s for s in passed.skipped)


def test_a_crop_under_the_floor_is_left_out_with_the_pixels_it_has(shelf):
    put(shelf, "win0.jpg", size=(1200, 700))
    passed = run(shelf, two_arms(), limit=1)
    small = [s for s in passed.skipped if "px on its short side" in s]
    assert small, "a 9:16 crop of a 700 px tall frame is 393 px wide"
    assert "600" in small[0]
    assert {c.platform for c in passed.cuts} == {"x"}, "the square survives, the story does not"


def test_nothing_ranked_means_nothing_to_rebuild(shelf):
    passed = run(shelf, [row("win0.jpg", 40, "")])
    assert passed.headline == "Nothing is ranked yet, so there is no post to rebuild."
    assert not passed.cuts and not passed.skipped


def test_the_copy_for_each_platform_is_written_in_her_own_voice(shelf):
    put(shelf, "win0.jpg")
    passed = run(shelf, two_arms(), limit=1)
    by = {c.platform: c for c in passed.cuts}
    learned = voice.learn(SAMPLES)
    assert learned.case_style == "lowercase", "the fixture is her, lowercase and all"
    for cut in by.values():
        assert cut.caption and cut.caption[0].islower(), cut.caption
        assert any("voice" in w or "words" in w for w in cut.why), cut.why
    assert len(by["x"].caption.split()) <= len(by["tiktok"].caption.split()), \
        "the short-form platform gets the shorter line, not the same line cut off"


def test_a_clip_is_refused_in_words_that_fit_when_there_is_no_ffmpeg(shelf):
    (shelf["clips"] / "win0.mp4").write_bytes(b"not really a clip")
    passed = run(shelf, two_arms(), limit=1, ffmpeg=False)
    assert not passed.cuts
    assert any("no ffmpeg" in s for s in passed.skipped), passed.skipped


def test_the_ratio_a_clip_would_get_is_the_one_the_clip_engine_accepts():
    """The clip half is the same engine the clips page drives, so the recipe has to survive
    its own normalise - a ratio op it dropped would export the untouched source and still
    report a cut."""
    for platform, ratio in R.SHAPE.items():
        recipe = clipmod.normalize([["ratio", ratio]])
        assert recipe == [["ratio", ratio]], f"{platform} lost its ratio op"


@pytest.mark.skipif(not clipmod.available(), reason="the bundled ffmpeg is missing")
def test_a_clip_is_actually_cut_when_the_machine_can_cut_it(shelf, tmp_path):
    """One real encode, because a clip path only ever tested with ffmpeg switched off is a
    claim about a file that was never made."""
    src = shelf["clips"] / "win0.mp4"
    clipmod._run([clipmod.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                  "-f", "lavfi", "-i", "color=c=teal:size=1080x1920:rate=25:duration=3",
                  "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=3", "-shortest",
                  "-pix_fmt", "yuv420p", str(src)])
    rows = [row("win0.mp4", 40, A), row("win1.mp4", 38, A), row("win2.mp4", 36, A),
            row("lose0.mp4", 5, B), row("lose1.mp4", 4, B), row("lose2.mp4", 3, B)]
    passed = run(shelf, rows, limit=1, ffmpeg=True)
    assert passed.cuts, passed.skipped
    for cut in passed.cuts:
        made = clipmod.probe(shelf["out"] / cut.file)
        assert made.ok, made.error
        want = R.SHAPE[cut.platform]
        assert abs(made.width / made.height - want) < 0.02, (cut.platform, made.width,
                                                             made.height)
