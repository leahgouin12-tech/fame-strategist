"""The words-on-a-clock layer, tested against pixels and a real render.

A caption that is in the file but at the wrong second is the failure this module exists to
avoid, so the video tests look at frames at named times rather than trusting the return code.
"""

from pathlib import Path

import pytest
from PIL import Image

from src.media import clip as clipmod
from src.media import story

SRC = pytest.importorskip("imageio_ffmpeg").get_ffmpeg_exe()


def make_clip(path: Path, seconds: float = 3.0, tone: bool = True, flat: bool = False) -> Path:
    """A real clip to render onto. `flat` is a plain dark field, which is what the timing
    test needs: on a busy pattern there are already hundreds of bright pixels where the
    caption goes, and "is the text here" cannot be answered by counting them."""
    import subprocess

    video = (f"color=c=0x101014:size=540x960:rate=30:duration={seconds}" if flat else
             f"testsrc2=size=540x960:rate=30:duration={seconds}")
    args = [SRC, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", video]
    if tone:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac"]
    args += ["-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, check=True)
    return path


def make_photo(path: Path, colour=(40, 60, 90)) -> Path:
    Image.new("RGB", (600, 900), colour).save(path)
    return path


def white_pixels_in_band(path: Path, top: float, bottom: float) -> int:
    """Count the near-white pixels inside a horizontal band of the rendered frame."""
    im = Image.open(path).convert("L")
    w, h = im.size
    band = im.crop((0, int(h * top), w, int(h * bottom)))
    return sum(1 for p in band.getdata() if p > 215)


# ---- her text, and the clock she gave with it ----------------------------------------

def test_a_time_range_becomes_one_line_with_both_ends():
    got = story.parse_lines("0:03-0:07 I said the quiet part")
    assert got == [story.Line("I said the quiet part", 3.0, 7.0)]


def test_an_arrow_and_a_bare_second_both_parse():
    a = story.parse_lines("2.0 > 4.0   second line")
    b = story.parse_lines("1:30 timed by clock")
    assert (a[0].at, a[0].until) == (2.0, 4.0)
    assert (b[0].at, b[0].until) == (90.0, 0.0)


def test_untimed_words_arrive_marked_as_untimed_not_as_zero():
    """-1 is "she did not say when". 0.0 would be "start at the first frame", and the two
    get different answers, so they may not be the same number."""
    assert story.parse_lines("no clock here")[0].at == -1.0


def test_blank_rows_and_more_lines_than_a_story_can_hold_are_dealt_with():
    got = story.parse_lines("\n\n".join(f"line {i}" for i in range(60)))
    assert len(got) == story.MAX_LINES


def test_an_untimed_batch_is_spaced_across_the_whole_clip():
    got = story.auto_times(story.parse_lines("first line\nsecond line\nthird line"), 12.0)
    assert got[0].at == pytest.approx(0.4, abs=0.01)
    assert got[-1].until <= 12.0
    assert got[0].at < got[1].at < got[2].at


def test_her_own_timings_are_never_moved_to_make_room():
    lines = story.parse_lines("0:03-0:07 timed\nuntimed trailing line")
    got = story.auto_times(lines, 20.0)
    assert (got[0].at, got[0].until) == (3.0, 7.0)
    assert got[1].at >= 7.0, "the untimed line goes after hers, not inside them"


def test_a_line_starting_after_the_clip_ends_is_reported_not_hidden():
    """It renders, the file is fine, and nobody on earth sees it. That is the worst kind of
    success, so it has to be said out loud."""
    lines = story.auto_times(story.parse_lines("1:30 this is after a three second clip"), 3.0)
    assert story.off_clip(lines, 3.0)


def test_a_line_on_screen_for_a_third_of_a_second_is_called_a_flash():
    assert not story.Line("x", 1.0, 1.33).reads_in_time()
    assert story.Line("x", 1.0, 2.0).reads_in_time()


# ---- the subtitle file that carries them --------------------------------------------

def test_the_ass_time_is_the_shape_libass_reads():
    assert story._ass_time(3.075) == "0:00:03.08"
    assert story._ass_time(3725.5) == "1:02:05.50"


def test_the_style_puts_the_words_in_the_safe_band_not_the_middle():
    text = story.ass_text([story.Line("words", 0.5, 2.0)])
    assert "Alignment" in text
    row = [l for l in text.splitlines() if l.startswith("Style: Safe")][0].split(",")
    assert row[17] == "2", "alignment 2 is bottom-centre, which is where a Story caption goes"
    assert int(row[20]) > 0, "the bottom margin is the safe zone; zero means under the chrome"


def test_curly_braces_in_lyrics_cannot_become_subtitle_commands():
    """libass reads {…} as override tags, so a lyric with braces would otherwise restyle
    the caption - or swallow the line."""
    text = story.ass_text([story.Line("say {big} now", 0.0, 1.0)])
    assert "{" not in text.split("[Events]")[1]


def test_dialogue_rows_come_out_in_time_order_whatever_order_she_typed():
    text = story.ass_text([story.Line("later", 5.0, 6.0), story.Line("first", 1.0, 2.0)])
    rows = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert "first" in rows[0] and "later" in rows[1]


# ---- the image door -----------------------------------------------------------------

def test_an_image_story_is_a_real_vertical_file_with_the_words_in_it(tmp_path):
    photo = make_photo(tmp_path / "p.jpg")
    out = tmp_path / "story.png"
    got = story.burn_image(photo, [story.Line("I said the quiet part", 0, 1)], out)
    assert got.ok and out.is_file()
    assert Image.open(out).size == (1080, 1920)
    assert white_pixels_in_band(out, 0.60, 0.86) > 200, "the words are not in the picture"


def test_a_photo_that_will_not_open_is_said_so(tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a jpeg at all")
    got = story.burn_image(broken, [story.Line("words", 0, 1)], tmp_path / "o.png")
    assert not got.ok and "would not open" in got.error


def test_too_many_lines_tell_her_the_earliest_words_hit_the_top_chrome(tmp_path):
    photo = make_photo(tmp_path / "p.jpg")
    lines = [story.Line(f"line number {i}", 0, 1) for i in range(14)]
    got = story.burn_image(photo, lines, tmp_path / "o.png")
    assert any("safe line" in n for n in got.notes)


def test_an_empty_word_box_still_gives_her_the_story_frame(tmp_path):
    """No words is a choice, not an error: she may want the platform's own text sticker
    on top of the frame, which only works if nothing is baked in."""
    photo = make_photo(tmp_path / "p.jpg")
    out = tmp_path / "o.png"
    got = story.render(photo, out, "   ")
    assert got.ok and out.is_file()
    assert Image.open(out).size == (1080, 1920)
    assert white_pixels_in_band(out, 0.60, 0.86) < 40, "words appeared out of nowhere"
    assert any("nothing was written" in n.lower() for n in got.notes)


# ---- the video door, on a real ffmpeg ----------------------------------------------

def test_the_words_appear_at_the_second_she_asked_for_and_not_before(tmp_path):
    src = make_clip(tmp_path / "in.mp4", 4.0, tone=False, flat=True)
    out = tmp_path / "out.mp4"
    got = story.burn_video(src, story.parse_lines("0:02-0:03.5 on screen late"), out)
    assert got.ok, got.error
    early = clipmod.seek(out, 0.6, tmp_path / "early.png")
    late = clipmod.seek(out, 2.6, tmp_path / "late.png")
    assert white_pixels_in_band(late, 0.62, 0.86) > 150, "the line never showed up"
    assert white_pixels_in_band(early, 0.62, 0.86) < 40, "it was already up before its time"


def test_the_render_keeps_the_sound_the_clip_already_had(tmp_path):
    src = make_clip(tmp_path / "in.mp4", 2.0, tone=True)
    got = story.burn_video(src, story.parse_lines("keep my audio"), tmp_path / "out.mp4")
    assert got.ok and "already had" in got.audio
    probe = clipmod.probe(got.out)
    assert not probe.silent, "the audio track was dropped while the words went in"


def test_her_own_audio_file_becomes_the_bed(tmp_path):
    import subprocess

    src = make_clip(tmp_path / "in.mp4", 2.0, tone=True)
    bed = tmp_path / "her.mp3"
    subprocess.run([SRC, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=880:duration=2", str(bed)], check=True)
    got = story.burn_video(src, story.parse_lines("mine"), tmp_path / "out.mp4", audio=bed)
    assert got.ok and "your audio file" in got.audio, got.error
    assert not clipmod.probe(got.out).silent


def test_a_lyric_full_of_quotes_and_colons_cannot_break_the_filter(tmp_path):
    """The path is the only thing quoted into the filter graph, and her words go through
    the sidecar file - so this proves the words are not being used as shell."""
    src = make_clip(tmp_path / "in.mp4", 2.0, tone=False, flat=True)
    tricky = "0:00-0:01 say \"this\" now: and = > that"
    got = story.burn_video(src, story.parse_lines(tricky), tmp_path / "out.mp4")
    assert got.ok, got.error
    assert white_pixels_in_band(clipmod.seek(got.out, 0.5, tmp_path / "f.png"), 0.62, 0.86) > 100


def test_a_render_that_ffmpeg_refuses_says_why_instead_of_claiming_success(tmp_path):
    missing = tmp_path / "no-such-file.mp4"
    got = story.burn_video(missing, story.parse_lines("words"), tmp_path / "out.mp4")
    assert not got.ok and "refused" in got.error


def test_the_sidecar_is_not_left_sitting_beside_her_finished_story(tmp_path):
    src = make_clip(tmp_path / "in.mp4", 2.0, tone=False)
    got = story.burn_video(src, story.parse_lines("one line"), tmp_path / "out.mp4")
    assert got.ok and not (tmp_path / "out.ass").exists()


def test_the_one_door_picks_the_right_renderer_from_the_file(tmp_path):
    photo = make_photo(tmp_path / "p.jpg")
    assert story.render(photo, tmp_path / "o.png", "words").kind == "image"
    src = make_clip(tmp_path / "in.mp4", 2.0, tone=False)
    assert story.render(src, tmp_path / "o.mp4", "words").kind == "video"
