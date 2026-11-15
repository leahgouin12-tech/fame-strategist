"""The multilingual page as she uses it, offline and with a model connected.

The page exists to be honest in a category that is mostly not. So what is proved here is the
refusal as much as the feature: that with no model it prints the brief and the reason instead of a
sentence, that the budget beside each language is the same number the brief is cut against (the
two are rendered from different dicts, and they drifted once), that a version which loses her
hashtag is still shown with the loss named, and that saving her defaults stores a choice she made
rather than a language the app guessed for her.
"""

import re
from pathlib import Path
from urllib.parse import unquote_plus
from html import unescape

import pytest
from fastapi.testclient import TestClient

from src import accounts
from src.app import create_app
from src.config import Config
from src.engines.base import Engine
from src.language import localise

LINE = "thrifted fits all week, all in the same bag #thriftflip"
GOOD = "los outfits que me puse esta semana, todos con la misma bolsa para el #thriftflip"
LOST = "los outfits de esta semana, todos en la misma bolsa"
NOVEL = "que me puse esta semana con la bolsa para el outfit"


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(html))


class Fake(Engine):
    name = "fake-model"

    def __init__(self, versions=None, raises=None):
        self.versions = [{"text": GOOD, "note": "kept the tag"},
                         {"text": LOST, "note": "dropped the tag"}] if versions is None \
            else versions
        self.raises = raises
        self.asked = []

    def complete_json(self, system, user, schema, images=None):
        self.asked.append((system, user, schema))
        if self.raises:
            raise self.raises
        return self.check({"versions": self.versions}, schema)


@pytest.fixture
def world(tmp_path):
    return TestClient(create_app(Config(api_key=None, engine_name="offline", model=""),
                                 tmp_path / "languages.sqlite3"))


def connect(world, fake):
    world.app.state.engine.engine = fake


def ask(world, text=LINE, codes=("es",), platform="tiktok", media="photo", keep=""):
    return flat(world.post("/languages/run", data={
        "text": text, "platform": platform, "media": media, "keep": keep,
        "codes": list(codes)}).text)


def stage(world, caption=LINE):
    world.app.state.db.save_staged(accounts.build(
        "tiktok", "Video post", caption=caption, hashtags=["#thriftflip"], alt="",
        lines="", music="", source="a.jpg", file="outputs/a.mp4").as_dict(), "2026-11-14")


# ---------------------------------------------------------------------------- the room itself


def test_the_room_is_in_the_rail_and_says_up_front_what_it_will_not_do(world):
    body = flat(world.get("/languages").text)
    assert 'href="/languages"' in body
    assert "This page does not translate." in body
    assert "no dictionary" in body


def test_offline_it_points_at_the_machine_page_instead_of_bluffing(world):
    body = flat(world.get("/languages").text)
    assert "No model is connected, so" in body
    assert 'href="/engine"' in body
    assert "What a version has to fit" not in body, "no result yet, so no brief either"


def test_the_four_limits_are_on_the_page_not_only_in_the_code(world):
    body = flat(world.get("/languages").text)
    assert "What this page cannot do" in body
    for claim in ("dictionary", "sounds native", "kept its numbers", "after you post"):
        assert claim in body, claim


def test_the_budget_beside_a_language_is_the_budget_its_brief_is_cut_against(world):
    """The chip on the checkbox and the heading on the brief are rendered from two different
    dicts. They showed different numbers once, and a page that promises 16 words then refuses a
    22-word version is the app's arithmetic charged to her."""
    body = ask(world, codes=("es", "fr"))
    assert re.search(r"Spanish ·.*?(\d+) words", body).group(1) == \
        re.search(r"ES — (\d+) words", body).group(1) == "30"
    assert re.search(r"French ·.*?(\d+) words", body).group(1) == \
        re.search(r"FR — (\d+) words", body).group(1) == "31"


def test_a_video_line_shrinks_both_numbers_together(world):
    body = ask(world, media="video")
    assert re.search(r"Spanish ·.*?(\d+) words", body).group(1) == \
        re.search(r"ES — (\d+) words", body).group(1) == "22"
    assert "English gets 16." in body


# --------------------------------------------------------------------------------- refusing


def test_an_empty_box_is_not_an_invented_caption(world):
    body = ask(world, text="   ")
    assert "There was no caption in the box" in body
    assert "What a version has to fit" not in body


def test_it_will_not_pick_her_audience(world):
    body = ask(world, codes=())
    assert "No language is ticked, and this app will not pick one for you" in body
    assert "the default would be somebody else" in body


def test_a_code_that_is_not_one_of_the_four_is_dropped_not_defaulted(world):
    assert "No language is ticked" in ask(world, codes=("zz",))


def test_with_no_model_the_answer_is_the_brief_and_the_reason(world):
    body = ask(world, keep="GlucoLove")
    assert "What a version has to fit" in body
    assert "No model is connected, and this app keeps no dictionary of its own" in body
    assert "Copy this brief" in body
    assert "GlucoLove" in body, "the words she will not have translated are on the sheet"
    assert GOOD not in body, "nothing in Spanish was printed"


# ------------------------------------------------------------------------ which line it worked on


def test_it_carries_the_post_the_composer_is_holding(world):
    stage(world)
    body = flat(world.get("/languages").text)
    assert "Working from the post staged in the composer." in body
    assert LINE in body


def test_a_pasted_line_is_named_as_pasted(world):
    stage(world)
    body = flat(world.get("/languages?text=hola%20que%20tal%20amigo").text)
    assert "Working from the line you typed." in body


def test_it_says_when_the_line_is_already_another_language(world):
    body = flat(world.get("/languages?text=" + NOVEL.replace(" ", "%20") + "&platform=tiktok").text)
    assert "Spanish" in body and "marker words are in it" in body


# --------------------------------------------------------------------------- her own defaults


def test_saving_her_defaults_stores_only_what_she_ticked(world):
    response = world.post("/languages/save", data={"codes": ["es", "ht", "zz"],
                                                   "keep": "GlucoLove, mi AMA",
                                                   "platform": "tiktok", "media": "video",
                                                   "text": LINE},
                          follow_redirects=False)
    assert response.status_code == 303
    back = unquote_plus(response.headers["location"])
    assert back.startswith("/languages?") and "media=video" in back
    assert "Saved: Spanish, Haitian Creole" in back
    assert "3 word(s) it will not translate" in back
    saved = world.app.state.db.get_language()
    assert saved["targets"] == ["es", "ht"] and saved["keep"] == "GlucoLove mi AMA"


def test_saved_defaults_are_used_when_she_ticks_nothing(world):
    world.post("/languages/save", data={"codes": ["es"], "keep": "", "platform": "tiktok",
                                         "text": ""}, follow_redirects=False)
    body = ask(world, codes=())
    assert "What a version has to fit" in body
    assert "ES —" in body and "FR —" not in body, "only the language she saved"


def test_nothing_saved_means_nothing_assumed(world):
    assert world.app.state.db.get_language() == {"targets": [], "keep": ""}
    assert "No language is ticked" in ask(world, codes=())


# ---------------------------------------------------------------------------- a model connected


def test_every_version_comes_back_with_its_own_verdict(world):
    connect(world, Fake())
    body = ask(world)
    assert "Versions" in body
    assert "Written by <strong>fake-model</strong>." in body
    assert "1 of 2 versions passed the check." in body
    assert "passed the check" in body and "1 to look at" in body
    assert "#thriftflip is gone" in body, "the failure is named, not hidden"
    assert "The model says: kept the tag" in body
    assert f"{len(GOOD.split())}/30 words" in body


def test_a_version_is_cut_to_the_placement_she_picked(world):
    fake = Fake()
    connect(world, fake)
    ask(world, codes=("es", "ht"), media="video", platform="x")
    assert len(fake.asked) == 2, "one call per language, not one per version"
    assert any("Kreyòl" in user for _s, user, _sc in fake.asked)
    for system, _user, _schema in fake.asked:
        assert "12 words" in system, "x runs 9 in English and 12 in a longer language"


def test_a_model_that_throws_leaves_her_the_reason_not_a_half_sentence(world):
    connect(world, Fake(raises=RuntimeError("socket closed")))
    body = ask(world)
    assert "The ask did not come back (RuntimeError)" in body
    assert "nothing was made up instead" in body
    assert GOOD not in body


def test_the_page_offers_every_language_the_module_knows(world):
    body = flat(world.get("/languages").text)
    for lang in localise.languages():
        assert lang.name in body and f'value="{lang.code}"' in body


def test_a_token_she_wrote_is_shown_back_the_way_she_wrote_it(world):
    """The global chip style sets the whole app in small caps, and on this page that turns her tag
    into a different string: the lock list says #thriftflip must survive letter-for-letter and the
    check fails a version for capitalising her line. So quoted tokens opt out of the re-casing."""
    css = (Path(__file__).parents[2] / "src" / "static" / "app.css").read_text(encoding="utf-8")
    verbatim = re.search(r"\.chip\.verbatim\s*\{([^}]*)\}", css)
    assert verbatim and "text-transform: none" in verbatim.group(1), "no rule to stop re-casing"
    base = re.search(r"^\.chip\s*\{([^}]*)\}", css, re.M).group(1)
    assert "text-transform: uppercase" in base, "the rule this opts out of has to still be there"
    body = world.post("/languages/run", data={"text": LINE + " yk idc", "platform": "tiktok",
                                             "media": "photo", "keep": "", "codes": ["es"]}).text
    assert '<span class="chip verbatim">#thriftflip</span>' in body, "the tag is re-cased again"
    assert '<span class="chip verbatim">yk</span>' in body, "her shorthand is re-cased again"
    assert '<span class="chip">#thriftflip</span>' not in body
