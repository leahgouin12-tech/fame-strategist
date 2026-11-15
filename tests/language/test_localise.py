"""The multilingual contract: what a version is not allowed to lose, and what happens when
there is no model to write one.

Two failure modes are worth proving against. The first is a locked token that quietly vanished -
a dropped hashtag or a `3pm` that became `2 de la tarde` - which is a wrong post, not a rough one.
The second is the app answering anyway: with no model on this laptop there is nothing here that
knows Kreyòl, so the only honest output is the brief plus the reason. `ask` returns `ran=False`
and these tests read that flag rather than the prose, because prose can be rewritten into a lie
and a boolean cannot.
"""

from src.db import DB
from src.engines.base import Engine
from src import language
from src.language import localise

LINE = "thrifted fits all week, all in the same bag #thriftflip"
ES = "los outfits que me puse esta semana, todos con la misma bolsa para el #thriftflip"


class Fake(Engine):
    name = "fake-model"

    def __init__(self, versions=None):
        self.versions = [{"text": ES, "note": "kept the tag"}] if versions is None else versions
        self.asked = []

    def complete_json(self, system, user, schema, images=None):
        self.asked.append((system, user, schema))
        return self.check({"versions": self.versions}, schema)


def problems(source, version, code="es", platform="tiktok", media="photo", keep=""):
    return localise.check(source, version, code, platform, media, keep)


# ------------------------------------------------------------------- what a version must keep


def test_the_lock_list_is_only_ever_what_she_actually_wrote():
    locked = localise.locked(LINE)
    assert [t.token for t in locked] == ["#thriftflip"], "nothing is invented into her caption"
    assert locked[0].kind == "tag"

    mixed = localise.locked("the GLUCO BAG drops at 3pm for 100k, #drop @shop https://glu.co/x",
                            extra="GlucoLove, Mi AMA")
    assert [(t.kind, t.token) for t in mixed] == [
        ("tag", "#drop"), ("mention", "@shop"), ("link", "https://glu.co/x"),
        ("brand", "GLUCO"), ("brand", "BAG"), ("number", "3pm"), ("number", "100k"),
        ("keep", "GlucoLove"), ("keep", "Mi"), ("keep", "AMA")], list(
        (t.kind, t.token) for t in mixed)


def test_shouting_on_a_phone_is_not_a_brand():
    """`OMG` and `RN` come back from autocaps, and `rn` is shorthand she types on purpose.
    Locking either would demand it survive into Spanish, which flags every good translation."""
    assert localise.locked("OMG rn fr tbh USA") == ()
    assert localise.locked("the NF X SZN drop")[0].kind == "brand"


def test_a_repeated_token_is_listed_once_in_the_order_she_wrote_it():
    assert [t.token for t in localise.locked("#b #a #b 5pm and 5pm")] == ["#b", "#a", "5pm"]


def test_the_shorthand_she_types_travels_as_an_instruction_not_a_lock():
    voice = localise.voice_tokens("i'm lowkey obsessed rn fr, no cap yk")
    assert {t.token for t in voice} >= {"lowkey", "rn", "fr", "no cap", "yk"}
    assert {t.kind for t in voice} == {"voice"}
    assert localise.voice_tokens("a considered outfit in neutral tones") == ()
    # and none of them end up in the list a version has to pass unchanged
    assert not [t for t in localise.locked("rn fr no cap") if t.kind in localise.MUST_KINDS]


# -------------------------------------------------------------------------------- the budget


def test_the_ruler_is_the_one_the_caption_generator_already_cuts_against():
    assert localise.budget_for("tiktok") == 22
    assert localise.budget_for("instagram") == 16          # maps onto the reels rule
    assert localise.budget_for("x") == 11
    assert localise.budget_for("myspace") == 16            # a platform this app does not know
    assert localise.budget_for("tiktok", "zz") == 22       # an unknown language invents no slack


def test_a_line_for_a_video_gets_the_same_cut_english_gets():
    assert localise.budget_for("tiktok", "", "video") == 16
    assert localise.budget_for("x", "", "story") == 9


def test_a_translation_gets_more_room_and_never_less():
    """Spanish, French and Portuguese run longer than English for reasons about those languages.
    The slack is this app's own allowance, so what has to hold is that it only ever widens."""
    for code in ("es", "fr", "ht", "pt"):
        assert localise.budget_for("tiktok", code) >= localise.budget_for("tiktok")
    assert localise.budget_for("tiktok", "es") == 30
    assert localise.budget_for("tiktok", "fr") == 31
    assert localise.budget_for("tiktok", "fr", "video") == 22
    assert localise.tags_for("tiktok") == 5
    assert "hook" in localise.shape_for("tiktok")


# ------------------------------------------------------------------------- reading the language


def test_it_names_a_language_only_when_the_words_say_so():
    assert localise.detect(ES).code == "es"
    assert localise.detect(ES).hits >= 3
    english = localise.detect("i cannot believe this actually worked out")
    assert english.code == "" and "English" in english.why


def test_a_short_or_shared_line_stays_quiet():
    """`que` and `para` are in more than one of these languages and in a lot of English
    sentences. Naming a language off two shared words is how an app ends up checking a caption
    against Spanish, and a two-word line is not enough to name anything."""
    short = localise.detect("que para")
    assert short.code == "" and "not enough" in short.why
    shared = localise.detect("que para wow ok lol")
    assert shared.code == "" and "not a language" in shared.why
    assert localise.detect("").code == ""


def test_a_line_that_lands_on_two_languages_at_once_says_so(monkeypatch):
    """The four languages here share fewer than three marker words each, so a real tie needs a
    stood-in table - which is the point of the branch: if two languages ever score the same, the
    count cannot name one of them and says so instead of picking the first."""
    pair = (localise.Language("xx", "Alpha", "Álfa", 1.3, ("one", "two", "three", "go"), "watch"),
            localise.Language("yy", "Beta", "Bêta", 1.3, ("one", "two", "three", "so"), "watch"))
    monkeypatch.setattr(localise, "LANGUAGES", pair)
    monkeypatch.setattr(localise, "BY_CODE", {lang.code: lang for lang in pair})
    got = localise.detect("one two three go so")
    assert got.code == "" and "equally" in got.why
    assert localise.detect("one two three go go").code == "xx"


# ------------------------------------------------------------------------------- the check


def test_a_missing_tag_is_reported_not_hidden():
    got = problems(LINE, "los outfits de esta semana, todos en la misma bolsa")
    assert "#thriftflip is gone" in got


def test_a_number_that_moved_is_reported_and_a_number_reworded_is_not():
    assert any("3pm" in p for p in problems("the sale ends at 3pm", "la venta termina a las 2"))
    assert problems("the sale ends at 3pm", "la venta termina a las 3 de la tarde") == ()


def test_a_version_that_is_her_own_line_back_is_not_a_translation():
    got = problems(LINE, LINE)
    assert got == ("it is the same words you gave - nothing was translated",)


def test_the_budget_holds_in_the_other_language():
    got = problems(LINE, " ".join(["palabra"] * 30) + " #thriftflip")
    assert got == ("it is 31 words against the 30 this page allows for a Spanish line here",), got


def test_it_keeps_her_punctuation_and_her_casing():
    got = problems("que onda con la bolsa", "Qué onda con la bolsa que usé hoy.")
    assert "it ends in a full stop, which your line does not do" in got
    assert "it capitalises a line you type in lowercase" in got
    assert problems("Que onda con la bolsa.", "La bolsa que usé hoy.") == ()


def test_an_emoji_nobody_asked_for_is_named():
    assert problems(LINE, ES + " 🔥") == ("it added 🔥",)
    assert problems(LINE + " 🔥", ES + " 🔥") == ()


def test_an_empty_version_says_so():
    assert problems(LINE, "") == ("It came back empty.",)


def test_a_clean_version_passes_with_nothing_to_report():
    assert problems(LINE, ES) == ()


# --------------------------------------------------------------------------------- the ask


def test_with_no_model_it_refuses_and_hands_back_the_brief():
    """This is the whole offline branch: no canned Spanish, no half-sentence dressed as an answer."""
    got = localise.ask(None, LINE, ["es", "ht"], platform="tiktok")
    assert got.ran is False and got.versions == ()
    assert "No model is connected" in got.why and "no dictionary" in got.why
    assert [b.language for b in got.briefs] == ["es", "ht"]
    assert got.briefs[0].words == 30 and got.briefs[0].tags == 5
    assert [t.token for t in got.briefs[0].locked] == ["#thriftflip"]
    assert [t.token for t in got.briefs[0].voice] == []
    assert "hook" in got.briefs[0].shape and "phrasebook" in got.briefs[0].watch
    assert "accents" in got.briefs[1].watch


def test_an_offline_engine_named_offline_is_the_same_refusal():
    class Offline(Fake):
        name = "offline"

    assert localise.ask(Offline(), LINE, ["es"]).ran is False


def test_it_will_not_pick_her_audience():
    assert "No language was picked" in localise.ask(None, LINE, []).why
    assert "no caption to localise" in localise.ask(None, "   ", ["es"]).why
    assert localise.ask(None, LINE, ["zz"]).why.startswith("No language was picked")


def test_a_model_gets_her_lock_list_her_budget_and_her_shorthand():
    engine = Fake()
    localise.ask(engine, "rn fr no cap, all in the same bag #thriftflip", ["es"],
                 platform="tiktok", media="video", keep="GlucoLove")
    system, user, schema = engine.asked[0]
    assert "#thriftflip" in system and "GlucoLove" in user
    assert all(word in system for word in ("rn", "fr", "no cap"))
    assert "Do not spell that out" in system
    assert "22 words" in system                      # the Spanish video budget, not the photo one
    assert "Español" in user and "Kreyòl" not in user
    assert schema is localise.SCHEMA


def test_everything_a_model_returns_comes_back_checked():
    engine = Fake([{"text": ES, "note": "kept the tag"},
                   {"text": "los outfits de esta semana", "note": "dropped the tag"},
                   {"text": "   ", "note": "empty"},
                   {"text": ES, "note": "past the two asked for"}])
    got = localise.ask(engine, LINE, ["es", "ht"], platform="tiktok", n=2)
    assert got.ran is True and got.said_by == "fake-model"
    assert [(v.language, v.ok) for v in got.versions] == [
        ("es", True), ("es", False), ("ht", True), ("ht", False)]
    assert [v for v in got.versions if not v.ok][0].problems == ("#thriftflip is gone",)
    assert got.why == "2 of 4 versions passed the check."
    assert len(engine.asked) == 2, "one call per language, not one per version"


def test_a_model_that_answers_with_nothing_says_that():
    got = localise.ask(Fake([{"text": "", "note": ""}]), LINE, ["es"])
    assert got.ran is True and got.versions == ()
    assert got.why == "The model answered with nothing usable."


def test_a_draft_is_cut_to_a_caption_not_an_essay():
    got = localise.ask(Fake([{"text": "word " * 300, "note": "n" * 900}]), LINE, ["es"])
    assert len(got.versions[0].text) <= 400 and len(got.versions[0].note) <= 300


# ------------------------------------------------------------------------------ what to show


def test_the_limits_are_printed_in_full():
    assert len(localise.CANNOT) == 4
    assert "dictionary" in localise.CANNOT[0]
    assert "sounds native" in localise.CANNOT[1]
    assert "kept its numbers" in localise.CANNOT[2]
    assert "after you post" in localise.CANNOT[3]


def test_a_brief_for_a_code_that_is_not_one_of_these_is_empty():
    empty = localise.brief("tiktok", "photo", LINE, "zz")
    assert (empty.language, empty.words, empty.locked, empty.shape) == ("", 0, (), "")


def test_the_answer_is_flat_enough_to_render():
    data = localise.ask(Fake(), LINE, ["es"]).as_dict()
    assert data["briefs"][0]["locked"] == ["#thriftflip"]
    assert data["versions"][0]["words"] == len(ES.split())
    assert data["versions"][0]["problems"] == []
    assert data["versions"][0]["language"] == "es"
    assert localise.detect(ES).as_dict()["name"] == "Spanish"
    assert localise.get("ES").typed_as == "Español" and localise.get("") is None
    assert [lang.code for lang in localise.languages()] == ["es", "fr", "ht", "pt"]


# --------------------------------------------------------------------------- her own settings


def test_the_targets_are_what_she_ticked_or_what_she_saved(tmp_path):
    db = DB(tmp_path / "lang.sqlite3")
    assert language.targets(db) == [], "nobody has decided her audience for her"
    db.save_language({"targets": ["es", "zz", "ht"]})
    assert language.targets(db) == ["es", "ht"]
    assert language.targets(db, ["pt"]) == ["pt"]
    assert language.targets(db, ["zz"]) == ["es", "ht"], "a bad tick falls back, not to Spanish"


def test_the_words_she_won_t_translated_merge_and_do_not_repeat(tmp_path):
    db = DB(tmp_path / "lang2.sqlite3")
    assert db.get_language() == {"targets": [], "keep": ""}
    db.save_language({"keep": "GlucoLove, mi AMA"})
    assert language.keep(db) == "GlucoLove mi AMA"
    assert language.keep(db, "glucolove newyork") == "GlucoLove mi AMA newyork"
    assert language.keep(db, "") == "GlucoLove mi AMA"
