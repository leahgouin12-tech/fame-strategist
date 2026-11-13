"""The clip engine is measured against a real encoded file, not a mock.

Two clips are synthesised once per session with the bundled ffmpeg: one that keeps
moving and carries a tone, one that is a flat red frame with silence in it. Every number
the judge prints is asserted against those two, so a threshold that drifts shows up as a
failed test rather than a confident wrong verdict.
"""

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from src.media import clip as clipmod
from src.media import clipjudge

pytestmark = pytest.mark.skipif(not clipmod.available(), reason="the bundled ffmpeg is missing")

LIVELY = ["-f", "lavfi", "-i",
          "testsrc2=size=1080x1920:rate=30:duration=8,scale=2160x3840,"
          "zoompan=z='min(zoom+0.0015,1.5)':d=240:s=1080x1920:fps=30",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-shortest",
          "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-c:a", "aac"]
FLAT = ["-f", "lavfi", "-i", "color=c=red:size=540x960:rate=30:duration=6",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=6",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "34", "-c:a", "aac"]


def _encode(tmp: Path, name: str, args: list[str]) -> Path:
    dst = tmp / name
    subprocess.run([clipmod.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args,
                    str(dst)], check=True, capture_output=True, text=True, timeout=600)
    assert dst.is_file()
    return dst


@pytest.fixture(scope="session")
def lively(tmp_path_factory) -> Path:
    return _encode(tmp_path_factory.mktemp("clips"), "lively.mp4", LIVELY)


@pytest.fixture(scope="session")
def flat(tmp_path_factory) -> Path:
    return _encode(tmp_path_factory.mktemp("clips2"), "flat.mp4", FLAT)


def test_the_header_is_read_from_the_file_itself(lively):
    c = clipmod.probe(lively)
    assert c.ok and not c.error
    assert c.duration == pytest.approx(8.0, abs=0.3)
    assert (c.width, c.height) == (1080, 1920)
    assert c.portrait and c.fps == pytest.approx(30, abs=1)
    assert c.has_audio and not c.silent
    assert "1080×1920" in c.line


def test_a_file_that_is_not_a_video_is_reported_not_raised(tmp_path):
    junk = tmp_path / "notes.mp4"
    junk.write_bytes(b"not a video at all")
    c = clipmod.probe(junk)
    assert not c.ok and c.error and c.flags == ["unreadable"]


def test_sample_times_stay_off_the_ends():
    times = clipmod.sample_times(10.0, 5)
    assert len(times) == 5
    assert times == sorted(times)
    assert times[0] > 0 and times[-1] < 10.0
    assert clipmod.sample_times(0.0) == []


def test_frames_are_real_pictures_of_the_right_size(lively, tmp_path):
    got = clipmod.frames(lively, 3, tmp_path)
    assert len(got) == 3
    for p in got:
        with Image.open(p) as im:
            assert im.size == (1080, 1920)


def test_a_recipe_is_clamped_ordered_and_stripped_of_noops():
    out = clipmod.normalize([["brightness", 99], ["mute", 1], ["rotate", -40], ["nonsense", 0.5],
                             ["speed", 1.0], ["trim", 1.0, 1.4]])
    assert [e[0] for e in out] == ["rotate", "brightness", "mute"], "geometry, tone, finish"
    assert out[0][1] == -clipmod.MAX_TILT
    assert out[1][1] == clipmod.TONE_OPS["brightness"][1]
    assert "trim" not in [e[0] for e in out], "a 0.4s cut is below the floor it must respect"


def test_the_cut_and_the_speed_agree_on_the_output_length():
    entries = clipmod.normalize([["trim", 2.0, 6.0], ["speed", 2.0]])
    assert clipmod.span(entries, 10.0) == (2.0, 6.0, 2.0)
    assert clipmod.span([], 10.0) == (0.0, 10.0, 10.0)


def test_a_ratio_after_a_straighten_fits_what_is_left(lively):
    c = clipmod.probe(lively)
    _, _, chain = clipmod.build([["rotate", 6.0], ["ratio", 4 / 5]], c)
    crops = [part for part in chain.split(",") if part.startswith("crop=")]
    assert len(crops) == 2
    after = [int(v) for v in crops[0][len("crop="):].split(":")[:2]]
    final = [int(v) for v in crops[1][len("crop="):].split(":")[:2]]
    assert all(v % 2 == 0 for v in after + final), "yuv420p needs even edges"
    assert after[0] < 1080 and after[1] < 1920, "the rotate trims the corners off"
    assert final[0] / final[1] == pytest.approx(0.8, abs=0.01)
    assert final[0] <= after[0] and final[1] <= after[1]
    _, _, other = clipmod.build([["ratio", 4 / 5], ["rotate", 6.0]], c)
    assert other == chain, "the engine fixes the order inside a group, not the page"


FORBIDDEN = ("slim", "reshape", "warp", "liquify", "smooth", "skin", "face", "body",
             "beautif", "inpaint", "generat", "dnn")


def test_no_clip_operation_can_beautify_a_person(lively):
    c = clipmod.probe(lively)
    names = " ".join(clipmod.OPS)
    _, _, chain = clipmod.build([["rotate", 3], ["ratio", 0.5625], ["flip", 1], ["brightness", 0.2],
                                 ["contrast", 1.2], ["saturation", 1.4], ["warmth", 0.5],
                                 ["sharpen", 0.8], ["vignette", 0.3], ["fade", 0.6], ["speed", 1.5]], c)
    for word in FORBIDDEN:
        assert word not in names, f"{word} would change how a person looks"
        assert word not in chain, f"{word} would change how a person looks"
    assert "crop=" in chain and "eq=" in chain and "setpts=" in chain


def test_a_filename_is_a_file_and_never_a_command(lively, tmp_path):
    tricky = tmp_path / "trick & ; $name (1).mp4"
    tricky.write_bytes(lively.read_bytes())
    c = clipmod.probe(tricky)
    assert c.ok and c.duration == pytest.approx(8.0, abs=0.3)
    out = clipmod.export(tricky, tmp_path / "out.mp4", [["trim", 1.0, 4.0]], c)
    assert out.ok and out.duration == pytest.approx(3.0, abs=0.4)


def test_exporting_writes_a_copy_and_leaves_the_original_alone(lively, tmp_path):
    before = lively.stat().st_size
    dst = tmp_path / "cut.mp4"
    out = clipmod.export(lively, dst, [["trim", 2.0, 5.0]])
    assert dst.is_file()
    assert out.duration == pytest.approx(3.0, abs=0.4)
    assert lively.stat().st_size == before, "the original is never rewritten"


def test_speed_changes_the_length_it_promises(lively, tmp_path):
    out = clipmod.export(lively, tmp_path / "fast.mp4", [["speed", 2.0]])
    assert out.duration == pytest.approx(4.0, abs=0.6)


def test_muting_removes_the_track_and_says_so(lively, tmp_path):
    out = clipmod.export(lively, tmp_path / "quiet.mp4", [["mute", 1]])
    assert not out.has_audio


def test_a_cover_still_lands_in_the_photo_folder(lively, tmp_path):
    dst = tmp_path / "cover.jpg"
    clipmod.cover(lively, 3.0, dst)
    assert dst.is_file() and not (tmp_path / "cover.png").exists()
    with Image.open(dst) as im:
        assert im.format == "JPEG" and im.size == (1080, 1920)


def test_the_judge_reads_a_moving_clip_as_a_moving_one(lively, tmp_path):
    v = clipjudge.judge_clip(lively, tmp_path)
    by = {c.name: c for c in v.components}
    assert len(v.frames) == clipmod.SAMPLE_FRAMES
    assert by["hook"].score > 0.7, "this clip changes inside the first two seconds"
    assert by["movement"].score > 0.7, "and keeps changing after that"
    assert by["sound"].score == 1.0
    assert by["length"].score == 1.0, "8s is inside the band"
    assert 0 <= v.score <= 10 and v.band in ("strong", "workable", "weak")


def test_a_clip_already_measured_is_not_decoded_again(lively, tmp_path):
    work = tmp_path / "frames"
    first = clipjudge.judge_clip(lively, work)
    stamps = {f.name: f.stat().st_mtime_ns for f in work.glob("*.png")}
    again = clipjudge.judge_clip(lively, work)
    assert len(stamps) == clipmod.SAMPLE_FRAMES + 2, "five samples plus the two hook frames"
    assert all(f.stat().st_mtime_ns == stamps[f.name] for f in work.glob("*.png")), \
        "the second read must reuse the frames the first one decoded"
    assert again.score == first.score and len(again.frames) == len(first.frames)


def test_reexporting_over_a_clip_name_invalidates_every_cached_frame(lively, tmp_path):
    work = tmp_path / "frames"
    clipjudge.judge_clip(lively, work)
    png = sorted(work.glob("*.png"))[0]
    stamp = png.stat().st_mtime_ns
    lively.touch()  # the usual thing a phone or an editor does: same name, new bytes
    clipjudge.judge_clip(lively, work)
    assert png.stat().st_mtime_ns != stamp, "a newer clip must never be judged by old frames"


def test_a_preview_state_already_rendered_is_read_back_from_disk(lively, tmp_path):
    one = clipmod.preview_frame(lively, 1.0, [["brightness", 0.2]], tmp_path / "p.png")
    stamp = one.stat().st_mtime_ns
    assert clipmod.preview_frame(lively, 1.0, [["brightness", 0.2]], one) == one
    assert one.stat().st_mtime_ns == stamp, "same clip, same controls, same picture"
    assert clipmod.preview_frame(lively, 1.0, [["brightness", 0.9]], tmp_path / "q.png") != one
    assert (tmp_path / "q.png").is_file(), "a different state gets its own file"


def test_a_frame_with_no_line_is_reported_as_unmeasurable(lively, tmp_path):
    v = clipjudge.judge_clip(lively, tmp_path)
    by = {c.name: c for c in v.components}
    assert by["stability"].score == 0.7, "neutral, not a invented pass"
    assert "no frame has a line" in by["stability"].why


def test_the_judge_calls_a_still_frame_still_and_says_what_to_do(flat, tmp_path):
    v = clipjudge.judge_clip(flat, tmp_path)
    by = {c.name: c for c in v.components}
    assert by["hook"].score == 0.0 and by["movement"].score == 0.0
    assert by["sound"].score == 0.4, "the track is there but inaudible"
    assert v.band == "weak"
    assert v.ideas, "a clip it dislikes must come with a plan, not only a verdict"
    assert all(idea != by["hook"].why for idea in v.ideas), "advice is not a second copy of the number"
    assert clipjudge.suggest(v) == [["mute", 1]]


def test_the_weights_are_the_ones_printed_on_the_page():
    assert sum(clipjudge.CLIP_WEIGHTS.values()) == pytest.approx(1.0)
    assert set(clipjudge.CLIP_WEIGHTS) <= set(clipjudge.CLIP_LABELS), "every score has a name"


def test_suggestions_only_reach_for_operations_the_engine_has():
    v = clipjudge.ClipVerdict(clip=clipmod.Clip(ok=True, duration=52.0, width=1080, height=1920,
                                                has_audio=False))
    v.drift = 3.4
    v.measured = True
    recipe = clipjudge.suggest(v)
    assert [e[0] for e in recipe] == ["trim", "rotate", "mute"]
    for entry in clipmod.normalize(recipe):
        assert entry[0] in clipmod.OPS
    assert clipmod.span(recipe, 52.0)[1] == clipjudge.BAND_SECONDS


def test_every_slider_starts_where_the_engine_writes_nothing():
    """The page renders its controls from CONTROLS; if a neutral position were not a real
    no-op, opening a clip would already carry an edit she never asked for."""
    for ctrl in clipmod.CONTROLS:
        assert clipmod.OPS[ctrl.name] == (ctrl.lo, ctrl.hi), f"{ctrl.name} range drifts"
        assert ctrl.lo <= ctrl.neutral <= ctrl.hi
        assert ctrl.step > 0 and ctrl.label and ctrl.group in clipmod.GROUPS
        assert not clipmod.normalize([[ctrl.name, ctrl.neutral]])
    # trim, ratio, flip and mute have their own widgets - a span, chips and two switches
    assert set(clipmod.OPS) - {c.name for c in clipmod.CONTROLS} == {"trim", "ratio", "flip",
                                                                    "mute"}
