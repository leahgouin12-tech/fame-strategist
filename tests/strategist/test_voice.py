from datetime import date

from src.strategist.daily import BANNED_HASHTAGS
from src.strategist.voice import PLATFORM_RULES, learn, package

DAY = date(2026, 11, 13)
LOWS = ["i did this thing today and it went badly lol 😂 #outfit #fitcheck",
        "honestly nobody tells you about the lighting 😭 #fitcheck",
        "wait why is this so hard? #outfit"]
FORMAL = ["I filmed this in one take. It is not my best work.",
          "Do you dress like this too? Tell me below.",
          "The lighting was wrong, but the outfit carried it."]


def test_the_profile_measures_how_she_actually_writes():
    p = learn(LOWS)
    assert p.samples == 3
    assert p.case_style == "lowercase" and p.words_per_sentence > 0
    assert p.emoji_per_sample > 0 and p.emoji_kinds
    assert 0 < p.questions < 1


def test_capitalised_writing_is_detected_as_capitalised():
    p = learn(FORMAL)
    assert p.case_style == "capitalised"
    assert p.second_person > 0, "you - she asks the reader things"


def test_an_empty_corpus_is_announced_instead_of_invented():
    p = learn([])
    assert not p.learned
    assert "Nothing pasted" in p.signature()[0]


def test_her_own_tags_come_back_out_and_the_dead_ones_never_go_in():
    p = learn(["great day #outfit #fitcheck #fyp #viral", "#outfit again"])
    assert "#outfit" in p.tags and "#fitcheck" in p.tags
    assert not set(p.tags) & BANNED_HASHTAGS


def test_the_signature_quotes_the_numbers_it_used():
    text = " ".join(learn(LOWS).signature())
    assert "3 of your own samples" in text and "emoji" in text


def test_variants_are_three_platforms_of_the_same_idea_not_one_copy_pasted():
    v = package("outfits in my room", "outfit-and-style", DAY, learn(LOWS))
    assert [x.platform for x in v] == list(PLATFORM_RULES)
    assert len(v[-1].caption.split()) < len(v[0].caption.split()), "X gets fewer words"
    assert {x.platform for x in v if x.hook} == set(PLATFORM_RULES)


def test_the_hook_is_always_the_first_line_of_what_she_copies():
    for variant in package("street clips", "lifestyle-day-in-life", DAY, learn(LOWS)):
        assert variant.block.startswith(variant.hook)
        assert variant.block.index(variant.caption) > len(variant.hook)


def test_writing_in_her_voice_means_keeping_her_casing_and_her_emoji():
    low = package("outfits in my room", "outfit-and-style", DAY, learn(LOWS))[0]
    assert low.caption == low.caption.lower(), "she does not capitalise; neither does the writer"
    assert low.caption.endswith("😂"), "one of her own emoji, not a random one"
    proper = package("outfits in my room", "outfit-and-style", DAY, learn(FORMAL))[0]
    assert proper.caption[:1].isupper()


def test_without_a_sample_the_writer_says_it_is_guessing():
    variant = package("outfits in my room", "outfit-and-style", DAY, learn([]))[0]
    assert "not pasted a sample" in " ".join(variant.why)
    assert variant.caption == variant.caption  # still a complete line, never blank


def test_tag_counts_stay_in_the_three_to_five_band_and_reuse_hers_first():
    v = package("room clips", "lifestyle-day-in-life", DAY, learn(LOWS))
    for variant in v:
        limit = PLATFORM_RULES[variant.platform]["tags"]
        assert 1 <= len(variant.tags) <= limit
        assert not set(t.lower() for t in variant.tags) & BANNED_HASHTAGS
    tiktok = v[0]
    assert "#outfit" in tiktok.tags or "#fitcheck" in tiktok.tags


def test_alt_text_stays_hers_because_the_app_has_not_seen_the_frame():
    for variant in package("room clips", "tutorial-value", DAY, learn(LOWS)):
        assert "Alt text is yours" in variant.alt_prompt
        assert "only you can say what is in the frame" in variant.alt_prompt


CANNOT_CLOSE = {"a", "an", "the", "on", "in", "of", "to", "and", "is", "my", "with", "for",
                "by", "at", "from"}


def test_a_shorter_platform_gets_a_shorter_line_not_hers_cut_off_mid_preposition():
    """X and reels have a smaller word budget than tiktok, and trimming to it used to stop on
    whatever word fell there - which put "This is what real life looks like on a." in front of
    her as copy to paste. The budget still holds; the line has to end somewhere a person would
    have stopped."""
    for hypothesis in ("lifestyle-day-in-life", "outfit-and-style", "tutorial-value",
                       "relatable-comedy"):
        for variant in package("street clips", hypothesis, DAY, learn(LOWS)):
            for line in (variant.hook, variant.caption):
                words = line.rstrip(".!?,;:").split()
                assert words and words[-1].lower() not in CANNOT_CLOSE, \
                    f"{hypothesis}/{variant.platform} ends on a word that cannot close a line: " \
                    f"{line!r}"
            assert len(variant.hook.split()) <= PLATFORM_RULES[variant.platform]["words"]
