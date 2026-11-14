"""The tone generator, proved on the rules it claims.

The page can look alive with templates and still be a lie, so what is proved here is the
specific honesty of each rule: the line is built out of the sentence she typed rather than a
persona, a shape with no detail behind it is skipped and counted instead of padded with the word
"mirror", a number and a weekday only appear when she gave one or a date was handed over, the word
for the post follows what she is posting, a video hook never leaves a caption cut off
mid-sentence, the caps wait for evidence from her own samples, and an adult line is written with
the watched word named beside it rather than softened or refused.
"""

import datetime
import re

from src.captions import tone
from src.strategist.voice import _ORPHANS, learn

SHOT = "mirror selfie in the black ribbed tank"
LOW = learn(["the tank again lol", "i wore it twice and nobody noticed #outfit"])
CAPS = learn(["Wore the tank again. Loved it", "Nobody asked for this but ok"])
NEITHER = learn([])
REELS = tone.PLATFORM_RULES["reels"]["words"]


def says(word: str, text: str) -> bool:
    """Whole word only: a line about clips has not called the post a clip."""
    return bool(re.search(r"\b" + word + r"\b", text))


def last_word(text: str) -> str:
    return text.split()[-1].lower().strip(".,;:!?") if text.split() else ""


def test_every_tone_writes_something_from_a_real_sentence():
    for got in tone.TONES:
        made = tone.lines(got.id, SHOT, LOW, "reels", "photo")
        assert made, f"{got.id} wrote nothing for a sentence that carries a thing, a part and a "
        for c in made:
            assert c.text.strip(), f"{got.id} returned a blank line"
            assert "{" not in c.text and "}" not in c.text, c.text
            assert c.words <= REELS, f"{got.id} ran {c.words} words past the reels budget"


def test_the_words_in_the_lines_are_her_words_not_a_persona():
    """Every card has to point at the thing she named - that is the whole claim of the module."""
    for got in tone.TONES:
        made = tone.lines(got.id, SHOT, LOW, "reels", "photo")
        assert any("tank" in c.text for c in made), f"{got.id} never used her own words"


def test_no_line_ends_on_a_word_that_cannot_close_a_sentence():
    for got in tone.TONES:
        for media in ("photo", "video"):
            for place in ("tiktok", "reels", "x"):
                for c in tone.lines(got.id, SHOT, LOW, place, media):
                    assert last_word(c.text) not in _ORPHANS, f"{got.id}/{place}: {c.text}"


def test_the_detail_slot_looks_past_how_the_photo_was_taken():
    """"mirror" is not a detail of the tank. A generator that fills the slot with it is
    describing the camera, which is the tell this split exists to kill."""
    fills = tone.slots("mirror selfie")
    assert fills["thing"] == "mirror selfie" and fills["detail"] == ""
    for c in tone.lines("niche", "mirror selfie", LOW, "reels", "photo"):
        assert not c.text.endswith("that is why it sits like that"), c.text
        assert "ask for a detail" in " ".join(c.notes), c.notes


def test_a_shape_that_could_not_be_filled_is_counted_out_loud():
    made = tone.lines("niche", "boots", LOW, "reels", "photo")
    assert any("1 of this tone's shapes ask for a detail" in " ".join(c.notes) for c in made)


def test_a_video_gets_a_spoken_hook_and_never_says_the_thing_twice():
    made = tone.lines("lit", SHOT, LOW, "tiktok", "video")
    assert made
    for c in made:
        assert c.text.lower().count("black ribbed tank") <= 1, f"template doubled: {c.text}"
        budget = max(9, int(tone.PLATFORM_RULES["tiktok"]["words"] * 0.75))
        assert c.words <= budget, f"{c.words} words over a {budget}-word hook-and-line"
    assert any("stop." in c.text for c in made), "no hook in front of the video line"


def test_the_line_calls_the_post_by_the_name_she_gave_it():
    """A Story line that says "a photo of it" is the tell this slot exists to kill: the shape is
    right and the word is wrong, and only one of them is in her sentence."""
    for media, word in (("photo", "photo"), ("video", "video"), ("story", "story"),
                        ("reel", "reel"), ("clip", "clip")):
        made = tone.lines("cunty", SHOT, LOW, "reels", media, n=6)
        assert made, media
        for c in made:
            for other in ("photo", "video", "story", "reel", "clip"):
                if other != word:
                    assert not says(other, c.text), f"a {media} said {other}: {c.text}"
        assert any(says(word, c.text) for c in made), [c.text for c in made]


def test_a_count_in_a_hook_is_a_count_she_gave():
    """The two hooks that used to count for her. "You are about to see it four times" over a
    three-clip post is a wrong fact in her own caption, so both now read from her sentence."""
    for tone_id, tail in (("cunty", "times"), ("aesthetic", "frames")):
        made = tone.lines(tone_id, "three clips of the same latte", LOW, "tiktok", "video", n=6)
        assert made, tone_id
        said = " ".join(c.text for c in made)
        assert "four" not in said, (tone_id, said)
        assert any(f"3 {tail}" in c.text for c in made), (tone_id, [c.text for c in made])
        quiet = tone.lines(tone_id, "clips of the same latte", LOW, "tiktok", "video", n=6)
        assert not any(tail in c.text for c in quiet), [c.text for c in quiet]


def test_the_shout_waits_for_evidence_from_her_own_samples():
    loud = tone.lines("lit", "the white linen shirt", CAPS, "reels", "photo")
    quiet = tone.lines("lit", "the white linen shirt", LOW, "reels", "photo")
    blank = tone.lines("lit", "the white linen shirt", NEITHER, "reels", "photo")
    assert all(c.text == c.text.upper() for c in loud), [c.text for c in loud]
    assert all(c.text == c.text.lower() for c in quiet), [c.text for c in quiet]
    assert all(c.text == c.text.lower() for c in blank), \
        "an unlearned voice must not be shouted - the caps are the app's guess, not hers"


def test_the_same_ask_twice_gives_the_same_lines():
    once = [c.text for c in tone.lines("cunty", SHOT, LOW, "reels", "photo")]
    twice = [c.text for c in tone.lines("cunty", SHOT, LOW, "reels", "photo")]
    assert once == twice, "reload is not a slot machine"


def test_a_real_day_and_a_real_number_beat_an_invented_one():
    """The two slots the app could quietly make up. A spelled number is still a number she said,
    and a weekday only appears when a date was actually handed over."""
    fills = tone.slots("3 clips of the same latte", datetime.date(2026, 11, 14))
    assert fills["count"] == "3" and fills["day"] == "saturday"
    spelled = tone.slots("three clips of the same latte")
    assert spelled["count"] == "3", spelled
    plain = tone.slots("clips of the same latte")
    assert plain["count"] == "" and plain["day"] == ""
    dated = tone.lines("lit", "clips of the same latte", LOW, "reels", "photo",
                       today=datetime.date(2026, 11, 14), n=6)
    assert any("saturday" in c.text for c in dated), [c.text for c in dated]
    assert not any("tries" in c.text for c in dated), [c.text for c in dated]
    counted = tone.lines("lit", "three clips of the same latte", LOW, "reels", "photo", n=6)
    assert any("3 tries" in c.text for c in counted), [c.text for c in counted]
    undated = tone.lines("lit", "clips of the same latte", LOW, "reels", "photo", n=6)
    assert not any(word in c.text for c in undated for word in tone.DAYS), \
        [c.text for c in undated]


def test_an_adult_line_is_written_and_the_watched_word_is_named_beside_it():
    """The ask was explicit: not limited to SFW. Nothing here filters - it writes the line and
    prints the word a caption filter is likely to look at, which is a note about reach."""
    made = tone.lines("cunty", "black ribbed tank from the sex shop", LOW, "reels", "photo", n=6)
    flagged = [c for c in made if c.watched]
    assert flagged, [c.text for c in made]
    for c in flagged:
        assert "sex" in c.text.lower(), c.text
        assert c.watched == ["sex"], c.watched
        assert "caption filter" in " ".join(c.explain(LOW)), c.explain(LOW)
    assert all(c.text.strip() for c in made), "a watched word suppressed a line"


def test_every_line_carries_the_grammar_it_came_from_and_what_the_tone_costs():
    for got in tone.TONES:
        for c in tone.lines(got.id, SHOT, LOW, "reels", "photo"):
            said = c.explain(LOW)
            assert got.cost in said, f"{got.id} hid what the tone costs"
            assert said[0].startswith(got.name), said


def test_a_tone_this_app_does_not_have_writes_nothing_rather_than_something_else():
    assert tone.lines("rude", SHOT, LOW, "reels", "photo") == []
    assert tone.tone("CUNTY").id == "cunty" and tone.tone("nonsense") is None
