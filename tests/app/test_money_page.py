"""The money page, driven the way a brand DM drives it: what do you want, and does the post
say it is an ad?

The arithmetic is proved in tests/money. What is proved here is the page's behaviour around it -
that it refuses rather than flatters, that it names where every band came from, that the two
numbers she types become a floor and a bad keystroke does not silently wipe it, and that the
caption check reads the post she actually staged instead of only the text a form handed it.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config

HEADERS = "platform,post_ref,views,avg_watch_pct,follows_gained,posted_at"


def lines(rows):
    return "\n".join(f"{p},{ref},{views},40,9," for p, ref, views in rows) + "\n"


@pytest.fixture
def world(tmp_path):
    client = TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                   tmp_path / "money.sqlite3"))
    client.folder = tmp_path
    return client


def store(client, rows):
    (client.folder / "metrics-last.csv").write_text(HEADERS + "\n" + lines(rows),
                                                    encoding="utf-8")


def flat(html: str) -> str:
    """The page as she reads it: the template wraps sentences across lines and escapes an
    apostrophe, so comparing raw html to a sentence checks the line length instead."""
    return re.sub(r"\s+", " ", unescape(html))


def test_the_page_is_in_the_rail_where_she_would_look_for_it(world):
    body = world.get("/money").text
    assert 'href="/money"' in body, "a page nothing links to is a page she never finds"


def test_with_no_import_it_names_the_way_out_not_an_empty_table(world):
    body = flat(world.get("/money").text)
    assert "Nothing is priceable yet." in body
    assert "no metrics are imported" in body.lower()
    assert "/numbers" in body, "the empty state has to point at the import it needs"


def test_five_posts_of_one_platform_get_a_number_and_its_two_bands(world):
    store(world, [("tiktok", v, m) for v, m in
                  [("a0", 900), ("a1", 1000), ("a2", 1000), ("a3", 1000), ("a4", 1100)]])
    body = flat(world.get("/money").text)
    assert "$15 to open on" in body, "the anchor is the mean of the two band midpoints"
    assert "benchmark median, first-month views" in body
    assert "executed campaigns by vertical" in body
    assert "$15.46" in body and "$4.46" in body and "$25.71" in body
    assert "money-per-view-basis" in body, "no figure on this page is allowed to be unsourced"


def test_three_posts_are_refused_by_name_rather_than_medied_anyway(world):
    store(world, [("reels", f"a{i}", 1000) for i in range(3)])
    body = flat(world.get("/money").text)
    assert "reels: 3 posts imported, 5 needed before a median means anything" in body
    assert "to open on" not in body, "a median struck from three posts is not a quote"


def test_a_platform_nobody_named_is_not_priced_on_another_s(world):
    store(world, [("logged", f"a{i}", 1000) for i in range(5)]
                + [("tiktok", f"b{i}", 800) for i in range(5)])
    body = flat(world.get("/money").text)
    assert "tiktok" in body
    assert "logged" in body.split("Your numbers, per platform")[1], \
        "the unpriced rows are still listed, so the omission is visible"
    assert "logged" not in body.split("The quote")[1].split("Your numbers")[0], \
        "but never as a platform with a quote of its own"


def test_youtube_gets_its_own_two_bands_and_a_higher_ceiling(world):
    store(world, [("youtube", f"a{i}", 4000) for i in range(5)])
    body = flat(world.get("/money").text)
    assert "YouTube, by niche" in body
    assert "channels over 50K subscribers" in body
    assert "$320.00" in body, "the niche band reaches, and the page shows the reach"
    assert "a subscriber floor this app cannot check for her" in body


def test_the_cited_claims_show_their_own_limits(world):
    store(world, [("tiktok", f"a{i}", 1000) for i in range(5)])
    body = flat(world.get("/money").text)
    assert "Does not claim:" in body
    assert "read as of" in body
    assert "contested" in body, "these sources disagree, and the page has to say so"


def test_the_two_hours_numbers_become_a_floor_the_page_quotes_against(world):
    store(world, [("tiktok", f"a{i}", 1000) for i in range(5)])
    body = flat(world.post("/money/terms", data={"hourly": "50", "minutes": "90"}).text)
    assert "A post costs you $75.00 before anybody pays anything." in body
    assert "never under $75" in body, "the floor belongs in the sentence she would copy"
    assert "under your own cost" in body, "$15.49 against a $75 floor is the whole point"


def test_a_typo_in_the_hours_box_saves_nothing_and_says_which_box(world):
    world.post("/money/terms", data={"hourly": "50", "minutes": "90"})
    body = flat(world.post("/money/terms", data={"hourly": "fifty", "minutes": "90"}).text)
    assert "hourly needs a number, not 'fifty'" in body
    assert world.app.state.kit.db.get_terms()["hourly"] == 50, "the old floor is still the floor"


def test_leaving_the_hours_blank_states_no_floor_at_all(world):
    store(world, [("tiktok", f"a{i}", 1000) for i in range(5)])
    body = flat(world.get("/money").text)
    assert "No floor set" in body
    assert "will not adopt a wage" in body.lower(), "silently borrowing a wage is the failure here"


def test_the_add_ons_are_priced_off_the_base_and_keep_the_two_shapes(world):
    store(world, [("tiktok", f"a{i}", 1000) for i in range(5)])
    body = flat(world.get("/money").text)
    assert "Usage rights" in body and "Whitelisting" in body
    assert "percent of their spend" in body, "a percent of ad spend is not a percent of her fee"
    assert "which they mean" in body, "the move is asking, not picking one"


def test_a_caption_that_opens_with_the_label_posts_as_it_is(world):
    body = flat(world.post("/money/label",
                           data={"text": "Sponsored by the gel that survived my shower",
                                 "surface": "feed"}).text)
    assert "posts as it is" in body
    assert "Carries 'sponsored'" in body, "the word the guidance names, in her text"


def test_a_label_tucked_past_the_fold_is_not_called_clear(world):
    caption = "the shower gel again " * 12 + "advertisement"
    body = flat(world.post("/money/label", data={"text": caption, "surface": "feed"}).text)
    assert "posts as it is" not in body
    assert "past the 125-character line" in body
    assert "Move it to the front." in body


def test_free_product_without_a_label_is_still_a_material_connection(world):
    body = flat(world.post("/money/label",
                           data={"text": "they sent me the whole set, obsessed",
                                 "surface": "feed"}).text)
    assert "missing" in body
    assert "material connection" in body
    assert "free product or a favour counts" in body


def test_a_video_placement_asks_for_the_label_in_the_video_not_just_the_caption(world):
    body = flat(world.post("/money/label",
                           data={"text": "Sponsored haul, three looks", "surface": "tiktok"}).text)
    assert "posts as it is" not in body
    assert "This is a video placement" in body
    again = flat(world.post("/money/label", data={"text": "Sponsored haul", "surface": "tiktok",
                                                  "in_video": "1"}).text)
    assert "posts as it is" in again, "with the label in the video the caption is enough"


def test_the_staged_caption_is_the_one_read_when_no_text_is_pasted(world):
    db = world.app.state.kit.db
    db.save_staged({"caption": "gifted from the brand, wear it out", "surface": "reels",
                    "platform": "instagram"}, "2026-11-14")
    body = flat(world.get("/money").text)
    assert "the post staged in the composer" in body
    assert "gifted from" in body, "the page opens on the post a brand would be liable for"
