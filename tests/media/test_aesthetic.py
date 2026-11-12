import math

from PIL import Image, ImageDraw, ImageFilter

from src.media.aesthetic import judge_photo
from src.media.clean import fix
from src.media.judge import measure

SIZE = (1080, 1920)


def bands(size=SIZE, tilt=0.0, vivid=True):
    """Two flat regions split by one straight line, drawn rather than rotated so the
    frame edges stay clean."""
    sky = (150, 170, 190) if not vivid else (86, 148, 224)
    ground = (70, 68, 66) if not vivid else (122, 88, 52)
    im = Image.new("RGB", size, ground)
    d = ImageDraw.Draw(im)
    mid = size[1] * 0.5
    drift = math.tan(math.radians(tilt)) * size[0] / 2
    d.polygon([(0, 0), (size[0], 0), (size[0], mid + drift), (0, mid - drift)], fill=sky)
    return im


def with_subject(im, at):
    """One solid, high-contrast subject - the shape a real frame has when something in
    it owns the picture."""
    d = ImageDraw.Draw(im)
    cx, cy = at[0] * im.width, at[1] * im.height
    r = im.width * 0.13
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(248, 240, 228))
    d.rectangle([cx - r * 0.45, cy + r * 0.6, cx + r * 0.45, cy + r * 3.2], fill=(238, 226, 210))
    return im


def judge(tmp_path, name, im):
    path = tmp_path / name
    im.save(path)
    return judge_photo(path, measure(path)), path


def test_a_centred_subject_scores_below_a_thirds_one(tmp_path):
    centred, _ = judge(tmp_path, "c.png", with_subject(bands(), (0.5, 0.5)))
    thirds, _ = judge(tmp_path, "t.png", with_subject(bands(), (0.34, 0.63)))
    c = {x.name: x.score for x in centred.components}
    t = {x.name: x.score for x in thirds.components}
    assert t["placement"] > c["placement"]
    assert any("dead centre" in x.why for x in centred.components)


def test_a_tilted_horizon_is_measured_as_tilted_and_offered_a_straighten(tmp_path):
    tilted, _ = judge(tmp_path, "tilt.png", bands(tilt=4))
    level, _ = judge(tmp_path, "level.png", bands())
    assert abs(tilted.tilt) > 1.5, f"measured {tilted.tilt}"
    assert abs(level.tilt) <= 1.5
    assert "straighten" in tilted.fixes and "straighten" not in level.fixes


def test_a_flat_grey_frame_is_offered_colour_and_a_vivid_one_is_not(tmp_path):
    dull, _ = judge(tmp_path, "dull.png", with_subject(bands(vivid=False), (0.34, 0.63)))
    vivid, _ = judge(tmp_path, "vivid.png", with_subject(bands(), (0.34, 0.63)))
    assert "lift colour" in dull.fixes
    assert "lift colour" not in vivid.fixes
    part = lambda j: next(c.score for c in j.components if c.name == "palette")
    assert part(vivid) > part(dull), "the palette component must separate them"


def test_a_scattered_frame_loses_to_one_clear_subject(tmp_path):
    busy = bands()
    d = ImageDraw.Draw(busy)
    for y in range(2, 18, 2):
        for x in range(2, 8, 2):
            d.rectangle([x * busy.width / 9, y * busy.height / 20,
                         (x + 1) * busy.width / 9, (y + 1) * busy.height / 20],
                        fill=(240, 240, 240))
    scattered, _ = judge(tmp_path, "busy.png", busy.filter(ImageFilter.UnsharpMask(2, 180)))
    single, _ = judge(tmp_path, "single.png", with_subject(bands(), (0.34, 0.63)))
    assert scattered.score < single.score


def test_the_editor_straightens_without_touching_the_original(tmp_path):
    judged, src = judge(tmp_path, "tilt.png", bands(tilt=4))
    before = src.read_bytes()
    dst = fix(src, tmp_path / "clean", judged.fixes, tilt=judged.tilt, focus=judged.focus)
    assert dst.exists() and src.read_bytes() == before
    after = judge_photo(dst, measure(dst))
    assert abs(after.tilt) <= abs(judged.tilt) + 0.1
    assert "straighten" not in after.fixes


def test_the_score_is_bounded_and_named(tmp_path):
    judged, _ = judge(tmp_path, "v.png", with_subject(bands(), (0.34, 0.63)))
    assert 0 <= judged.score <= 10
    assert {c.name for c in judged.components} == {"placement", "level", "breathing", "palette", "focus"}
    assert judged.band in {"strong", "workable", "weak"}


def test_the_fix_list_says_what_to_do_rather_than_repeat_the_measurement(tmp_path):
    judged, _ = judge(tmp_path, "c.png", with_subject(bands(), (0.5, 0.5)))
    assert judged.ideas, "a weak frame must get directions, not only a score"
    for idea in judged.ideas:
        assert idea.endswith(".") and idea[0].isupper()
        assert "sits at" not in idea, "ideas are actions; the table already carries the measurements"
    flat, _ = judge(tmp_path, "f.png", bands())
    assert not any("not judged" in i for i in flat.ideas), "an unmeasurable horizon is a limit, not an idea"
