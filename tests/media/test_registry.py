"""The registry is the editor's only description of itself, so it has to agree with the
engines it drives. A control whose slider writes slot 5 into an op that reads 4 arguments
does not fail loudly - it silently does nothing, which is the worst thing a photo editor
can do to somebody retouching her own face."""

import json
import re

import pytest
from PIL import Image, ImageDraw

from src.media import edit
from src.media.registry import CUTSHAPES, EDGES, FITS, ORDER, RAILS, RAIL, STICKERS, TITLES, Tool

SIZE = (500, 700)


def frame():
    im = Image.new("RGB", SIZE, (120, 110, 105))
    d = ImageDraw.Draw(im)
    d.ellipse([120, 150, 380, 500], fill=(215, 180, 155))
    d.rectangle([60, 560, 440, 600], fill=(240, 240, 240))
    return im


def test_every_rail_has_a_title_and_only_known_tools():
    assert set(ORDER) == set(RAILS)
    assert set(TITLES) == set(RAILS)
    for rail, names in ORDER.items():
        assert names, rail
        for name in names:
            assert RAIL[name] == rail, f"{name} is filed twice"


def test_no_tool_is_offered_that_no_engine_can_run():
    """Everything on the page has to actually run. The two exceptions are the controls
    apply() runs itself because they need the frame from before the brushes, and the ones
    the page drives through its own crop and flip handles."""
    for tool in edit.TOOLS:
        assert tool.op in edit.APPLIERS or tool.op in edit.RUNTIME_OPS, \
            f"{tool.op} is on the page but nothing implements it"


def test_two_rails_never_show_the_same_control():
    names = [tool.op for tool in edit.TOOLS]
    assert len(names) == len(set(names))


def test_everything_an_engine_can_run_is_filed_on_a_rail():
    """normalize() ignores an entry whose name is not on a rail, so an op nobody filed is
    worse than a missing button: a hand-written recipe would say it applied and nothing
    would change."""
    for name in edit.ENGINE:
        assert name in RAIL, f"{name} runs but no rail shows it"


def test_the_lists_the_page_numbers_match_the_ones_the_engine_indexes():
    """A select writes an index, and the engine looks that index up in its own tuple.
    The two lists are worded differently on purpose; they may not differ in length."""
    from src.media import design

    assert len(STICKERS) == len(design.KINDS)
    assert len(CUTSHAPES) == len(design.CUTS)
    assert len(EDGES) == len(design.EDGES)
    assert len(FITS) == len(design.FITS)


def test_every_control_lands_on_a_slot_the_engine_actually_reads():
    for tool in edit.TOOLS:
        arity = edit.ARITY[tool.op]
        assert arity == edit.arity_of(tool.op)
        for f in tool.fields:
            span = 3 if f.kind == "colour" else 1
            assert f.at + span <= arity, \
                f"{tool.op}: {f.label} writes slots {f.at}..{f.at + span - 1}, arity is {arity}"
        if tool.stroke:
            for p in tool.points:
                assert p + 1 <= arity, f"{tool.op} paints into a slot past its arity"


def test_the_slots_a_control_writes_are_the_ones_the_page_thinks_it_writes():
    for tool in edit.TOOLS:
        assert edit.slots(tool) == edit.ARITY[tool.op], f"{tool.op} declares {edit.slots(tool)}"


def test_a_field_range_never_asks_for_more_than_the_engine_clamps():
    """A slider that can reach 0.6 into an op that clamps at 0.25 is a control that stops
    working halfway along its own track, with no message."""
    for tool in edit.TOOLS:
        bounds = edit.CLAMP.get(tool.op)
        if not bounds:
            continue
        for f in tool.fields:
            for at in range(f.at, f.at + (3 if f.kind == "colour" else 1)):
                if at >= len(bounds) or bounds[at] is None:
                    continue
                lo, hi = bounds[at]
                assert f.lo >= lo - 1e-9 and f.hi <= hi + 1e-9, \
                    f"{tool.op}/{f.label}: UI {f.lo}..{f.hi} outside engine {lo}..{hi}"


@pytest.mark.parametrize("rail", RAILS)
def test_the_page_payload_describes_every_rail_it_shows(rail):
    payload = json.loads(edit.tools_json())
    by_rail = {block["rail"]: block for block in payload}
    assert set(by_rail) == set(RAILS)
    assert [t["op"] for t in by_rail[rail]["tools"]] == \
           [t.op for t in edit.RAIL_TOOLS[rail]]
    for t in by_rail[rail]["tools"]:
        assert t["arity"] == edit.ARITY[t["op"]]
        assert t["fields"], t["op"]


def test_repeated_strokes_fold_into_one_entry_in_the_order_she_made_them():
    recipe = edit.normalize([["smooth", 0.2, 0.3, 0.1, 0.4], ["smooth", 0.6, 0.7, 0.1, 0.4]])
    assert len(recipe) == 1
    assert recipe[0] == ["smooth", 0.2, 0.3, 0.1, 0.4, 0.6, 0.7, 0.1, 0.4]


def test_a_single_position_control_keeps_only_the_last_tap():
    recipe = edit.normalize([["lens_blur", 0.4, 0.2, 0.2, 0.5], ["lens_blur", 0.4, 0.8, 0.9, 0.5]])
    assert len(recipe) == 1 and recipe[0][2:4] == [0.8, 0.9]


def test_the_rails_run_in_pipeline_order_whatever_order_they_arrived_in():
    recipe = edit.normalize([["text", 0.1, 0.1, 0.05, 1, 1, 1, 0, 0, 1, 0, 0, "hi"],
                            ["rotate", 4.0], ["exposure", 0.3], ["smooth", 0.5, 0.5, 0.1, 0.5]])
    names = [e[0] for e in recipe]
    assert names == sorted(names, key=lambda n: RAILS.index(RAIL[n]))
    assert names[0] == "rotate", "geometry must run before anything measured in fractions"


def test_a_hand_written_recipe_cannot_blow_past_an_engines_own_limits():
    recipe = edit.normalize([["warp", 0.5, 0.5, 40.0, 900.0, 7, 900.0, 720.0]])
    assert recipe[0][1:] == [0.5, 0.5, 0.8, 1.0, 2.0, 1.0, 360.0]


def test_a_word_slot_stays_a_word_and_is_never_turned_into_a_number():
    recipe = edit.normalize([["text", 0.2, 0.2, 0.06, 1, 1, 1, 0, 0.2, 1, "display",
                              "follow the light"]])
    assert recipe[0][10] == "display" and recipe[0][11] == "follow the light"


def test_a_runaway_string_is_cut_down_instead_of_crashing_the_export():
    recipe = edit.normalize([["text", 0.2, 0.2, 0.06, 1, 1, 1, 0, 0.2, 1, "display",
                              "x" * 5000]])
    assert len(recipe[0][11]) == 800


def test_a_recipe_the_page_sends_actually_paints_the_picture():
    im = frame()
    recipe = edit.normalize([
        ["rotate", 3.0], ["crop", 4 / 5], ["exposure", 0.2], ["temperature", -0.3],
        ["smooth", 0.43, 0.61, 0.3, 0.6], ["texture", 0.43, 0.61, 0.3, 0.5],
        ["warp", 0.43, 0.61, 0.24, -0.5, 0, 0.4, 90.0], ["matte", 0.62, 0.3, 0.2, 0.7],
        ["whiten", 0.53, 0.45, 0.06, 0.8], ["eyes", 0.53, 0.45, 0.08, 0.6],
        ["makeup", 0.55, 0.72, 0.12, 0.8, 350.0, 0.7],
        ["brighten", 0.5, 0.5, 0.4, 0.5, 0.8], ["heal", 0.3, 0.3, 0.04],
        ["lens_blur", 0.4, 0.5, 0.5, 0.4], ["rays", 0.8, 0.1, 0.6, 0.4],
        ["duotone", 0.04, 0.1, 0.2, 0.9, 0.8, 0.6, 0.5],
        ["text", 0.5, 0.9, 0.05, 1, 1, 1, 0, 0.2, 1, "display", "the glow lab"],
        ["frame", 0.07, 0.07, 0.07, 0.04, 0.005, 0.03],
    ])
    out = edit.apply(im, recipe)
    assert out.mode in ("RGB", "RGBA")
    assert out.width > 0 and out.height > 0
    assert out.getbbox() is not None


def test_a_colour_field_travels_in_the_scale_the_engine_clamps_it_in():
    """The page folds a colour into three numbers divided by 255, so a slot that declares
    0..255 on the engine side reads every colour she picks as black. That is not a wrong
    colour, it is a tool that looks switched off - so the two scales may not disagree."""
    for tool in edit.TOOLS:
        bounds = edit.CLAMP.get(tool.op)
        if bounds is None:
            continue
        shape = edit.SHAPE.get(tool.op)
        per = shape[1] if shape and shape[0] == "group" else len(bounds)
        for f in tool.fields:
            if f.kind != "colour":
                continue
            for slot in (f.at, f.at + 1, f.at + 2):
                bound = bounds[slot % per]
                assert bound[1] <= 1.0 + 1e-9, \
                    f"{tool.op} slot {slot}: page writes 0..1, engine clamps {bound}"


def test_an_entry_for_something_the_engines_do_not_have_is_dropped_not_run():
    assert edit.normalize([["face_slim", 0.9], ["nonsense", 1.0], ["heal"]]) == []


def test_a_colour_default_is_a_hex_the_picker_can_hold():
    """The page keeps a colour as one hex in slot `at` and folds it out into three
    numbers on the way to the engine. A default left as a number gets read back as a
    hex, which paints a colour nobody picked."""
    for tool in edit.TOOLS:
        for f in tool.fields:
            if f.kind != "colour":
                continue
            assert re.fullmatch(r"#[0-9a-fA-F]{6}", str(f.value)), \
                f"{tool.op} / {f.label} defaults to {f.value!r}"


def test_nothing_on_the_page_is_still_wrapped_in_a_moral_refusal():
    """She lifted the identity rule herself. The editor may reshape a face; these tests
    keep the removal honest - the copy and the controls have to actually match."""
    for tool in edit.TOOLS:
        assert "cannot" not in tool.note or "cannot" in (tool.label + tool.note), tool.op
    blob = json.dumps(json.loads(edit.tools_json())) + " ".join(t.note for t in edit.TOOLS)
    for phrase in ("is not offered", "I won't", "will not change", "refuse", "identity zone"):
        assert phrase not in blob, phrase
