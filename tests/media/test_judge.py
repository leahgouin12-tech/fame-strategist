from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

from src.media.clean import clean
from src.media.judge import ALLOWED_FIXES, inbox_files, judge, measure


def checker(size, box=24):
    im = Image.new("L", size, 240)
    d = ImageDraw.Draw(im)
    for y in range(0, size[1], box * 2):
        for x in range(0, size[0], box * 2):
            d.rectangle([x, y, x + box, y + box], fill=20)
    return im.convert("RGB")


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "inbox"
    d.mkdir()
    return d


def save(inbox, name, im):
    path = inbox / name
    im.save(path)
    return path


def test_a_real_batch_is_what_makes_something_count_as_soft(inbox):
    base = checker((1440, 2560))
    save(inbox, "sharp.png", base)
    save(inbox, "fine.png", base.filter(ImageFilter.GaussianBlur(1)))
    save(inbox, "mush.png", base.filter(ImageFilter.GaussianBlur(12)))
    found = {r.name: r for r in judge(inbox_files(inbox))}
    assert found["mush.png"].soft and found["mush.png"].verdict == "skip"
    assert not found["sharp.png"].soft


def test_two_files_are_not_enough_to_call_anything_soft(inbox):
    base = checker((1440, 2560))
    save(inbox, "a.png", base)
    save(inbox, "b.png", base.filter(ImageFilter.GaussianBlur(14)))
    readings = judge(inbox_files(inbox))
    assert all(not r.baseline for r in readings)
    assert all(not r.soft for r in readings), "no baseline means no softness claim"


def test_pure_white_is_named_as_detail_that_is_gone(inbox):
    bright = Image.new("RGB", (1440, 2560), (253, 253, 253))
    ImageDraw.Draw(bright).rectangle([100, 100, 500, 500], fill=(20, 20, 20))
    save(inbox, "blown.png", bright)
    r = measure(inbox / "blown.png")
    assert r.blown > 0.5 and any("pure white" in f for f in r.flags)
    assert r.verdict == "fix" and "exposure" in r.fixes
    assert "no data left to recover" in r.limit


def test_an_off_shape_is_offered_a_crop_and_nothing_else(inbox):
    save(inbox, "wide.png", checker((2000, 1200)))
    r = measure(inbox / "wide.png")
    assert r.off_format and r.target == "16:9"
    assert r.fixes == ["crop"] and r.verdict == "fix"


def test_a_small_file_is_skipped_not_upscaled(inbox):
    save(inbox, "tiny.png", checker((720, 720), 12))
    r = measure(inbox / "tiny.png")
    assert r.small and r.verdict == "skip"
    assert r.fixes == [], "a skipped file must not also offer a fix"
    assert "cannot be added back" in r.limit


def test_a_file_that_is_not_a_picture_is_reported_not_raised(inbox):
    (inbox / "junk.jpg").write_bytes(b"this is not a jpeg")
    r = measure(inbox / "junk.jpg")
    assert r.verdict == "unreadable" and r.error and r.fixes == []


def test_a_clean_copy_lands_beside_an_untouched_original(inbox):
    src = save(inbox, "wide.png", checker((2000, 1200)))
    before = src.read_bytes()
    dst = clean(src, inbox / "clean")
    assert dst.exists() and dst.parent == inbox / "clean"
    assert src.read_bytes() == before, "the original must never be rewritten"
    with Image.open(dst) as out:
        assert abs(out.width / out.height - 16 / 9) < 0.01


def test_running_it_twice_does_not_eat_the_first_copy(inbox):
    src = save(inbox, "wide.png", checker((2000, 1200)))
    first = clean(src, inbox / "clean")
    second = clean(src, inbox / "clean")
    assert first.exists() and second != first


def test_the_only_offered_fixes_are_global_and_reversible():
    assert set(ALLOWED_FIXES) == {"exposure", "contrast", "crop"}
