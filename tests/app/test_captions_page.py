"""The captions page as she uses it: type the frame, get six temperatures and a tag list that
says where each tag came from.

What is proved here is the page's behaviour, not the generator's: that an empty box writes
nothing rather than a stock line, that the copy button carries the sentence it shows, that the
placement changes the word budget the card prints, that a value the app does not know falls back
to the one platform rather than an empty select, that pasting her own writing changes the casing
banner and adds a tag with her captions behind it, and that the adult words she asks for stay on
the page with the watch note beside them instead of a softened line.
"""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config

SHOT = "mirror selfie in the black ribbed tank"
SAMPLES = "wore the tank again lol\nnobody asked for this but ok #thrifted"


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(html))


@pytest.fixture
def world(tmp_path):
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                tmp_path / "captions.sqlite3"))


def page(world, subject=SHOT, platform="instagram", media="photo"):
    return flat(world.get("/captions", params={"subject": subject, "platform": platform,
                                                "media": media}).text)


def test_the_page_is_in_the_rail_where_she_would_look_for_it(world):
    assert 'href="/captions"' in world.get("/captions").text


def test_an_empty_box_writes_nothing_rather_than_a_stock_post(world):
    body = page(world, subject="")
    assert "Nothing is written yet, on purpose." in body
    assert 'class="cs-block"' not in body, "lines appeared for a frame she never described"
    assert "mirror selfie in the black ribbed tank" in body, "no example to start from"
    assert "subject=mirror%20selfie" in world.get("/captions", params={"subject": ""}).text


def test_all_six_temperatures_answer_the_same_shot(world):
    body = page(world)
    for tone_id in ("cunty", "lit", "funny", "niche", "aesthetic", "soft"):
        assert f'id="tone-{tone_id}"' in body, tone_id
    assert "black ribbed tank" in body
    assert "3 lines" in body, "every card should answer with its three candidates"


def test_the_copy_button_carries_the_line_it_shows(world):
    body = world.get("/captions", params={"subject": SHOT}).text
    shown = re.findall(r'<p class="captext">([^<]+)</p>', body)
    copied = re.findall(r'data-copy="([^"]+)"', body)
    assert shown and shown == [unescape(c) for c in copied], (shown, copied)


def test_the_placement_decides_the_word_budget_it_prints(world):
    assert "16 words" in page(world, platform="instagram")
    assert "22 words" not in page(world, platform="instagram")
    assert "11 words" in page(world, platform="x")
    assert "16 words" in page(world, platform="tiktok", media="video"), \
        "a tiktok video gets a hook and a line inside 75% of its budget"


def test_an_unknown_placement_falls_back_instead_of_an_empty_choice(world):
    body = page(world, platform="myspace")
    assert 'value="instagram" selected' in body
    assert "myspace" not in body.split('id="platform"')[1][:400], "a fake platform got adopted"


def test_every_account_she_connects_is_a_choice_here(world):
    body = world.get("/captions").text
    for place in ("instagram", "tiktok", "youtube", "pinterest", "x"):
        assert f'value="{place}"' in body, place


def test_a_video_and_a_story_get_the_spoken_hook_rule_explained(world):
    for media in ("video", "story"):
        body = page(world, platform="tiktok", media=media)
        assert f'value="{media}" selected' in body
        assert "the hook goes alone" in body


def test_the_unlearned_voice_is_announced_and_goes_when_she_pastes_world_class(world):
    body = page(world)
    assert "Your voice is unlearned" in body and 'href="/write"' in body
    world.post("/write/samples", data={"samples": SAMPLES})
    after = page(world)
    assert "Your voice is unlearned" not in after
    assert "Voice unlearned" not in after, "the per-line note should go with the banner"


def test_the_tags_are_a_table_of_evidence_not_a_trend_feed(world):
    body = page(world)
    assert "where it came from" in body and "the evidence" in body
    assert "your captions" not in body, "nothing is pasted yet, so that row cannot exist"
    assert "your words" in body and "#blackribbedtank" in body
    assert "made from the words you used for this shot" in body
    assert "There is no trending-tag feed here because there is nothing to read." in body


def test_a_description_with_no_taggable_word_shows_an_empty_list_and_the_gaps(world):
    body = page(world, subject="in the 2008")
    assert "No tag is on this list." in body
    assert "No hypothesis is attached" in body and "Nothing you have written is pasted" in body


def test_a_pasted_caption_becomes_a_tag_she_can_copy(world):
    world.post("/write/samples", data={"samples": SAMPLES})
    body = page(world)
    assert "#thrifted" in body and "your captions" in body
    assert "already in the writing you pasted" in body
    assert 'id="tagblock"' in body and "#thrifted" in re.search(
        r'<textarea id="tagblock"[^>]*>(.*?)</textarea>', body, re.S).group(1)


def test_an_adult_request_stays_on_the_page_with_the_word_named(world):
    body = page(world, subject="black ribbed tank from the sex shop")
    assert "sex shop" in body, "the line was softened instead of written"
    assert "watched word" in body
    assert "18 words in its own watch list" in body
    assert "What this page will not do" in body


def test_the_slots_it_filled_are_shown_so_she_can_see_what_it_used(world):
    body = page(world)
    assert "the thing" in body and "the part" in body and "the detail" in body
    assert "black ribbed" in body
    assert "nothing in your sentence names a number" in body
    assert "no date was given" not in body, "the page has today and should name the real weekday"


def test_a_number_she_wrote_becomes_the_count_instead_of_an_invented_one(world):
    body = page(world, subject="three clips of the same latte", media="video")
    assert "<td>the count</td><td>3</td>" in body
    assert "nothing in your sentence names a number" not in body


def test_the_lines_call_the_post_the_thing_she_said_she_is_posting(world):
    """The media select is not a label on the form - it changes the noun inside the sentences."""
    for media, word in (("photo", "photo"), ("video", "video"), ("story", "story")):
        body = page(world, platform="tiktok", media=media)
        assert re.search("the form</td><td>%s\\b" % word, body), media
        lines = re.findall(r'<p class="captext">([^<]+)</p>', body)
        assert lines, media
        for line in lines:
            for other in ("photo", "video", "story", "reel", "clip"):
                if other != word:
                    assert not re.search(r"\b" + other + r"\b", line), \
                        f"a {media} line said {other}: {line}"


def test_a_thin_description_says_which_shapes_it_had_to_drop(world):
    body = page(world, subject="boots")
    assert "you did not name one" in body
    assert "ask for a detail of the thing itself" in body


def test_the_staged_post_is_not_overwritten_by_a_copy(world):
    world.post("/story/stage", data={"caption": "the old line from the composer",
                                     "platform": "tiktok"})
    body = page(world)
    if "composer" in body and "currently holding" in body:
        assert 'href="/story"' in body
    assert "the old line from the composer" not in body.split("cs-block")[1], \
        "the staged caption was rendered as a new suggestion"
