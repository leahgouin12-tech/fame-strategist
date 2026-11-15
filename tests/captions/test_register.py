"""The register: the difference between a line that is correct and a line that is typeable.

Nothing here is proved with a model, because nothing here calls one. What is proved is the
specific honesty of each pass - the noun a sentence actually says, the contraction that is always
allowed and the one that would strand a clause, the spelling that only appears because she typed it
or switched it on, the period that comes off the end of a line and not out of the middle of one, the
marker that has to be earned by the sentence it lands on, the correction she made once and the app
never ships without again, and the shapes that are refused for having circulated as templates.
"""

from src.captions import register
from src.strategist.voice import learn

HER_LINES = [
    "the tank again lol",
    "u cant be serious rn idc",
    "no body wat is this",
    "i wore it twice and nobody noticed",
]
PERIOD_LINES = ["Wore the tank again. Loved it.", "Nobody asked for this. But ok."]
HER = learn(HER_LINES)
PERIODS = learn(PERIOD_LINES)
BLANK = learn([])


def reg_for(lines, profile=None, **kw):
    return register.of(profile or learn(lines), lines, **kw)


def test_a_sentence_says_the_item_not_the_whole_description():
    """"the black ribbed tank" is what she typed so the generator would know what to point at. It
    is not a phrase anybody puts in a caption, and a line that recites it is the tell."""
    assert register.say("black ribbed tank", "tank") == "tank"
    assert register.say("white linen shirt", "shirt") == "shirt"
    assert register.say("the black ribbed tank", "tank") == "tank"
    assert register.say("tank", "tank") == "tank"


def test_a_compound_she_chose_keeps_both_words():
    """Taking the first half out of "sex shop" changes which shop it is, so the collapse only
    removes words that describe the thing rather than name it."""
    assert register.say("sex shop", "shop") == "sex shop"
    assert register.say("the sex shop", "shop") == "sex shop"  # the article is not the name


def test_the_line_is_contracted_even_with_nothing_pasted():
    """The app's own default still has to read like a person: "it is" in a caption is a form that
    belongs in an essay and nowhere else."""
    quiet = register.of(BLANK, [])
    text, said = register.flatten("it is unreal and i am not even exaggerating", quiet)
    assert "it's" in text and "it is" not in text, text
    assert "i'm" in text, text
    assert any("contracted" in s for s in said), said


def test_a_contraction_that_would_end_the_line_is_refused():
    """"more work than i am" is a sentence. "more work than i'm" is a clause with nothing after
    it, and a caption that reads half-finished is the failure this module was rebuilt to kill."""
    assert register.contracted("the tank is doing more work than i am").endswith("than i am")
    assert register.contracted("the tank is doing more work than i am.").endswith("than i am.")
    assert register.contracted("i am not answering where it is from") == \
        "i'm not answering where it's from"


def test_a_spelling_she_never_typed_stays_out():
    """An abbreviation the app guessed is a spelling she then has to own in her own caption, so
    without her samples or her explicit switch it does not appear."""
    line = "nobody asked what the tank is, but you would"
    untouched, _ = register.flatten(line, register.of(BLANK, []))
    assert untouched == line, untouched
    measured, said = register.flatten(line, reg_for(HER_LINES))
    assert "wat" in measured and " u " in measured, measured
    assert any("your own captions" in s for s in said), said
    switched, said2 = register.flatten(line, register.of(BLANK, [], want_abbrevs=True))
    assert "wat" in switched and " u " in switched, switched
    assert any("you switched on" in s for s in said2), said2


def test_shortening_never_breaks_a_word_that_is_already_contracted():
    """`\\byou\\b` matches the `you` inside `you'd`, and `u'd` is a spelling nobody has ever
    typed."""
    got = register.of(BLANK, [], want_abbrevs=True)
    assert "you'd" in register.abbreviate("you'd have to see it", got)
    assert register.abbreviate("you", got) == "u"


def test_only_the_period_at_the_end_of_the_line_comes_off():
    """The switch says her lines do not end on a period. It does not say the beat in the middle of
    a video caption - "stop. the tank." - was a mistake, and stripping it turns a hook into the
    order "stop the tank"."""
    quiet = reg_for(HER_LINES)
    assert not quiet.end_period
    assert register.punctuate("stop. the tank. i need it in every color.", quiet) == \
        "stop. the tank. i need it in every color"
    loud = reg_for(PERIOD_LINES)
    assert loud.end_period
    assert register.punctuate("the tank stays.", loud) == "the tank stays."


def test_a_marker_lands_only_on_a_line_that_earns_it():
    """`idc` on a line that does not say it does not care is the app writing her voice instead of
    using it, so the condition decides and nothing is added when her register has no markers."""
    got = reg_for(HER_LINES)
    assert "idc" in got.markers and "rn" in got.markers
    mark, why = register.marker_for("the tank again and i'm not even sorry", got)
    assert mark == "idc" and why
    assert register.marker_for("the tank stays, everything else goes", got) == (None, "")
    assert register.marker_for("the tank is unreal", register.of(BLANK, [])) == (None, "")


def test_the_marker_goes_where_it_is_a_real_word_in_that_sentence():
    """Glued to the front, "idc no it's not for you" reads like a translation. `fr` answers the
    claim from behind it and `tbh` opens."""
    assert register.place("the tank is unreal, i'm not even exaggerating", "fr") == \
        "the tank is unreal, i'm not even exaggerating fr"
    assert register.place("no it's not for you", "idc") == "no it's not for you, idc"
    assert register.place("i think the fit is fine", "tbh") == "tbh i think the fit is fine"


def test_a_booster_she_uses_strengthens_a_claim_and_nothing_else():
    """Nothing is added to a plain statement, and a line that already carries her word does not get
    a second one - two boosters in eight words is a generator overcorrecting."""
    got = reg_for(["actually the tank is unreal", "i wore it twice lol"])
    assert "actually" in got.emphasis
    said, word = register.emphasize("the tank is unreal", got)
    assert word == "actually" and said.startswith("the tank is actually unreal"), said
    plain, none = register.emphasize("the tank stays, everything else goes", got)
    assert none is None and plain == "the tank stays, everything else goes"
    once, twice = register.emphasize("actually the tank is unreal", got)
    assert twice is None, once


def test_a_correction_she_made_once_changes_every_later_line():
    """The arrow is the whole format: without it a note is a note, and guessing which half is
    which is how her wording gets inverted."""
    pairs = register.fixes([{"body": "unreal => insane"}, {"body": "just a note"},
                            {"body": "ok =>"}, {"body": "  => no"}])
    assert pairs == (("unreal", "insane"),)
    got = register.of(BLANK, [], corrections=pairs)
    assert register.corrected("the tank is unreal, i'm not even exaggerating", got) == \
        "the tank is insane, i'm not even exaggerating"
    assert register.corrected("the tank stays", got) == "the tank stays"


def test_the_same_word_she_rejected_comes_back_only_once_she_forgave_it():
    """Deleting the correction has to put the old wording back, or the app is arguing with her
    about a line she already changed on purpose."""
    line = "the tank is unreal"
    kept = register.of(BLANK, [], corrections=(("unreal", "insane"),))
    dropped = register.of(BLANK, [], corrections=())
    assert register.corrected(line, kept) != line
    assert register.corrected(line, dropped) == line


def test_every_token_is_traced_to_a_real_source():
    """The page says where each spelling came from, so "you type it" is only ever true of a word
    that is actually in her captions."""
    measured = reg_for(HER_LINES)
    assert measured.provenance("u") == "you type it"
    assert measured.provenance("lol") == "the app's default"
    switched = register.of(BLANK, [], want_markers=True)
    assert not switched.learned
    assert switched.provenance("fr") == "you switched it on"
    quiet = register.of(BLANK, [])
    assert quiet.source.startswith("the app's default")
    assert quiet.provenance("fr") == "the app's default"


def test_the_shapes_that_are_refused_are_named_with_a_reason():
    """Refusing a shape silently is how a page quietly runs out of lines; the reason is what she
    reads when a tone writes fewer than it should."""
    assert not register.tells("no it's not for you")
    assert not register.tells("the tank stays, everything else goes")
    for bad in ("that's the whole point", "this dress is a game changer",
                "me: also me: the tank again", "it's giving vintage",
                "bought the thing you'll ask about later",
                "the silk is elevated and must-have",
                "whether you like it or not one another will notice"):
        assert register.tells(bad), bad
    why = register.tells("that's the whole point")
    assert len(why) == 1, why


def test_the_register_reaches_the_lines_the_page_shows():
    """A register the writer ignores would be a settings page. This is the same call the page and
    the agent tool make, so what is switched on here is visible in the shipped text."""
    from src.captions import tone
    shot = "mirror selfie in the black ribbed tank"
    quiet = tone.lines("cunty", shot, BLANK, "reels", "photo",
                       reg=register.of(BLANK, []))
    hers = tone.lines("cunty", shot, HER, "reels", "photo", reg=reg_for(HER_LINES))
    assert all("wat" not in c.text for c in quiet), [c.text for c in quiet]
    assert any("u" in c.text or "wat" in c.text or "idc" in c.text or "rn" in c.text
               for c in hers), [c.text for c in hers]
    assert all(c.text == c.text.lower() for c in hers), [c.text for c in hers]
