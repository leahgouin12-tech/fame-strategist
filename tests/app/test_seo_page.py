"""The discoverability page as she uses it: it reads the post the composer is holding, or the
one she pastes, and tells her which of her own phrases are on it and where they sit.

What is proved here is the page's behaviour rather than the module's: that the room is in the
rail where she would look for it, that an app with nothing on file shows an empty list instead of
a guessed keyword, that the post read is named so she knows which one was judged, that reading it
writes nothing, that a phrase living only in a tag is not presented as a phrase she wrote, and
that the words this app cannot know are printed on the page rather than quietly left off.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from src import accounts
from src.app import create_app
from src.config import Config

CAPTION = "thrifted tank again, worn to six places"
SAMPLES = ["obsessed with this thrifted tank", "the tank again and the tank", "thrifted and proud"]


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(html))


def empty_state(body: str) -> str:
    """The empty card alone, so a link in the navigation rail cannot pass for a way out of it."""
    start = body.index("There is no phrase to check against yet.")
    return body[start:body.index("Where the tag slots go")]


@pytest.fixture
def world(tmp_path):
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                 tmp_path / "seo.sqlite3"))


def stage(world, **over):
    fields = dict(caption=CAPTION, hashtags=["#thrifted", "#outfitandstyle"],
                  alt="a person in a worn thrifted tank top", platform="tiktok",
                  surface="Video post", source="a.jpg", file="outputs/a.mp4", lines="", music="")
    fields.update(over)
    world.app.state.db.save_staged(accounts.build(fields["platform"], fields["surface"],
                                                  caption=fields["caption"],
                                                  hashtags=fields["hashtags"], alt=fields["alt"],
                                                  lines=fields["lines"], music=fields["music"],
                                                  source=fields["source"],
                                                  file=fields["file"]).as_dict(), "2026-11-14")


def pasted(world, text=CAPTION + " #thrifted #outfitandstyle", alt="", platform="tiktok"):
    return flat(world.post("/seo/read", data={"text": text, "alt": alt,
                                              "platform": platform}).text)


def test_the_room_is_in_the_rail_where_she_would_look_for_it(world):
    assert 'href="/seo"' in world.get("/seo").text


def test_with_nothing_on_file_the_page_shows_no_phrases_rather_than_guessed_ones(world):
    body = flat(world.get("/seo").text)
    card = empty_state(body)
    assert "would have to invent words" in card, "it says why the list is empty, not just that it is"
    assert "all three places they come from are empty" in card
    for place in ('href="/numbers"', 'href="/write"', 'href="/plan"'):
        assert place in card, f"an empty page has to point at the {place} she can fill"


def test_the_post_being_read_is_named_so_she_knows_which_one_was_judged(world):
    stage(world)
    body = flat(world.get("/seo").text)
    assert "the post staged in the composer" in body
    assert CAPTION in body


def test_a_paste_answers_the_page_ahead_of_the_staged_post(world):
    stage(world)
    body = pasted(world, text="the latte is the post #latteart")
    assert "the text you pasted" in body
    assert "latte is the post" in body


def test_reading_a_post_writes_nothing_and_leaves_the_staged_package_alone(world):
    stage(world)
    before = world.app.state.db.get_staged()
    pasted(world)
    assert world.app.state.db.get_staged() == before, "the read button changed her staged post"


def test_a_phrase_only_in_a_tag_is_not_presented_as_one_she_wrote(world):
    world.app.state.db.save_voice(SAMPLES)
    body = pasted(world, text="worn to six places #thrifted")
    assert "only in a tag, never said in the caption" in body
    assert "Say the phrase in the first line" in body


def test_a_phrase_written_in_the_caption_reports_as_carried_with_its_source(world):
    world.app.state.db.save_voice(SAMPLES)
    body = pasted(world, text=CAPTION)
    assert "your captions" in body
    assert "it is in 2 of the 3 captions you pasted" in body
    assert "tank, thrifted appear inside the first 90 characters" in body


def test_the_alt_field_is_read_as_a_field_and_not_left_out(world):
    world.app.state.db.save_voice(SAMPLES)
    body = pasted(world, text=CAPTION, alt="tank tank tank tank thrifted")
    assert "alt field" in body
    assert "repeats itself" in body


def test_the_empty_alt_of_a_still_post_is_named_as_a_missing_field(world):
    stage(world, alt="")
    body = flat(world.get("/seo").text)
    assert "The alt field is empty" in body


def test_the_numbers_the_page_prints_are_its_own_readings_and_say_so(world):
    stage(world)
    body = flat(world.get("/seo", params={"platform": "tiktok"}).text)
    assert "5 is what this app reads as the most a tiktok post carries" in body
    assert "90 characters" in body
    assert "neither platform prints the number it uses" in body


def test_the_limits_are_on_the_page_instead_of_left_implied(world):
    body = flat(world.get("/seo").text)
    assert "What this page cannot know" in body
    for absent in ("how many people search a phrase", "indexed at all", "not theirs"):
        assert absent in body


def test_no_volume_rank_or_index_claim_appears_anywhere_on_the_page(world):
    stage(world)
    world.app.state.db.save_voice(SAMPLES)
    body = flat(world.get("/seo").text)
    assert not re.search(r"\d[\d,]*\s*(searches|queries|people search|searches a month)",
                         body.lower())
    assert "is ranked" not in body and "your rank" not in body


def test_the_cited_rules_that_speak_about_text_are_quoted_with_their_limit(world):
    body = flat(world.get("/seo").text)
    if "What the sourced library says about text" not in body:
        pytest.skip("the library holds no live claim about text on this machine")
    assert "Does not claim:" in body


def test_the_tag_slots_are_charged_and_the_over_full_line_is_counted(world):
    world.app.state.db.save_voice(SAMPLES)
    body = pasted(world, text=CAPTION + " #thrifted #fyp " +
                  " ".join(f"#tag{i}word" for i in range(4)))
    assert "chasing the feed" in body
    assert "restatement" in body
    assert "looks like a wall" in body
