"""Seven tone and detail controls the registry listed as named by no test.

Each one is checked the only way that means anything for a picture: a known image goes in,
and the number that describes the effect comes out. The thresholds are the ones this
machine actually produced on a 160x160 frame that is dark on the left and bright on the
right, with a hard edge down the middle - so a control that silently stopped doing
something would fail here rather than look fine in a log.
"""

import pytest
from PIL import Image

from src.media.edit import edit_file

EDGE = 0.8


@pytest.fixture
def frame(tmp_path):
    """Half dark, half bright, a hard vertical seam, and colour in both halves so that a
    black-and-white control has something to remove."""
    src = tmp_path / "edge.jpg"
    im = Image.new("RGB", (160, 160))
    for y in range(160):
        for x in range(160):
            v = 40 if x < 80 else 210
            im.putpixel((x, y), (v, v // 2 + 20, 250 - v))
    im.save(src, "JPEG", quality=98)
    return src


def read(img):
    return img.convert("RGB").load()


def mean(px, box):
    x0, x1 = box
    got = [px[x, y] for y in range(160) for x in range(x0, x1)]
    return sum(sum(p) for p in got) / (len(got) * 3)


def channel_spread(px):
    """How far each pixel's red and blue sit from each other - what desaturating moves."""
    return sum(abs(px[x, y][0] - px[x, y][2])
               for y in range(160) for x in range(160)) / (160 * 160)


def edge_step(px):
    return sum(abs(sum(px[80, y]) - sum(px[79, y])) for y in range(160)) / 160


def neighbour_noise(px):
    row = [px[x, y] for y in range(160) for x in range(160)]
    return sum(abs(p[0] - q[0]) for p, q in zip(row, row[1:])) / (len(row) - 1)


def look(frame, recipe):
    px = read(edit_file(frame, recipe))
    return {"dark": mean(px, (0, 80)), "bright": mean(px, (80, 160)),
            "spread": channel_spread(px), "step": edge_step(px),
            "noise": neighbour_noise(px)}


def test_the_untouched_frame_is_the_number_every_other_claim_is_measured_against(frame):
    base = look(frame, [])
    assert 90 < base["dark"] < 105 and 118 < base["bright"] < 133, base
    assert base["spread"] > 150, "the test picture needs colour in it or blackwhite proves nothing"


@pytest.mark.parametrize("op", ["blackwhite", "gamma", "grain", "highlights",
                                "shadows", "sharpness", "structure"])
def test_a_slider_at_zero_leaves_the_picture_alone(frame, op):
    base = look(frame, [])
    got = look(frame, [[op, 0]])
    assert abs(got["dark"] - base["dark"]) < 2.5, (op, got)
    assert abs(got["bright"] - base["bright"]) < 2.5, (op, got)
    assert abs(got["step"] - base["step"]) < 12, (op, got)


def test_blackwhite_actually_removes_the_colour(frame):
    base, got = look(frame, []), look(frame, [["blackwhite", EDGE]])
    assert got["spread"] < base["spread"] / 3, (base["spread"], got["spread"])


def test_gamma_lifts_the_middle_of_the_tone_rather_than_flattening_it(frame):
    base, got = look(frame, []), look(frame, [["gamma", EDGE]])
    assert got["dark"] > base["dark"] + 20, (base["dark"], got["dark"])
    assert got["spread"] < base["spread"], "gamma pulls the channels in, it does not add colour"


def test_grain_adds_grain_and_nothing_else(frame):
    base, got = look(frame, []), look(frame, [["grain", EDGE]])
    assert got["noise"] > base["noise"] * 4, (base["noise"], got["noise"])
    assert abs(got["dark"] - base["dark"]) < 6, "grain should not brighten the picture"
    assert abs(got["step"] - base["step"]) < 20, "grain should not sharpen the edge"


def test_one_recipe_two_runs_is_one_picture(frame):
    """The grain used to come from an unseeded generator, so the preview, the save and the
    re-opened chain were three different images and none of them matched the recipe on file.
    Reproducibility is what the edit chain claims, so it is measured here in bytes."""
    once = edit_file(frame, [["grain", EDGE]]).tobytes()
    assert edit_file(frame, [["grain", EDGE]]).tobytes() == once
    assert edit_file(frame, [["grain", EDGE / 2]]).tobytes() != once, \
        "a different amount has to be a different picture"


def test_highlights_move_the_bright_half_more_than_the_dark_half(frame):
    base, got = look(frame, []), look(frame, [["highlights", EDGE]])
    up_bright, up_dark = got["bright"] - base["bright"], got["dark"] - base["dark"]
    assert up_bright > 20, (base["bright"], got["bright"])
    assert up_bright > up_dark, "a highlights control that lifts shadows is mislabelled"


def test_shadows_lift_the_dark_half_and_close_the_gap(frame):
    base, got = look(frame, []), look(frame, [["shadows", EDGE]])
    up_dark, up_bright = got["dark"] - base["dark"], got["bright"] - base["bright"]
    assert up_dark > 40, (base["dark"], got["dark"])
    assert up_dark > up_bright, "a shadows control that lifts highlights is mislabelled"
    assert got["step"] < base["step"], "lifting the dark half must soften the seam"


def test_sharpness_bites_the_edge_it_is_pointed_at(frame):
    base, got = look(frame, []), look(frame, [["sharpness", EDGE]])
    assert got["step"] > base["step"] * 1.8, (base["step"], got["step"])
    assert abs(got["dark"] - base["dark"]) < 6, "sharpening is not a brightness control"


def test_structure_raises_local_contrast_without_the_halo_of_sharpness(frame):
    base, sharp, got = (look(frame, []), look(frame, [["sharpness", EDGE]]),
                        look(frame, [["structure", EDGE]]))
    assert got["step"] > base["step"], "structure must do something to the edge"
    assert got["step"] < sharp["step"], (
        f"structure came out harder than sharpness: {got['step']} vs {sharp['step']}")
    assert got["spread"] > base["spread"], "structure is meant to deepen the tone spread"
