"""The tag list, proved as an evidence list rather than a trending widget.

No platform publishes a hashtag feed this app can read, so the only honest tag list is one where
every line names what put it there - her own numbers, her own captions, her own words for the
shot, or the format this week's arm carries. What is proved here: the order (the evidence that
actually ranks comes first), the per-placement count, the tags that are never allowed on the page
even when she wrote them herself, and that with nothing behind it the list comes back empty with
the three named gaps instead of a filler hashtag.
"""

import datetime

from src.captions import tags
from src.metrics.ingest import MetricRow
from src.strategist.voice import learn

TODAY = datetime.date(2026, 11, 14)
ARM = "outfit-and-style"


def posts(arm=ARM, count=4, platform="instagram"):
    return [MetricRow(platform, f"{platform}{i}", TODAY, 1000, 1000, 40.0, 9, 3, 2, arm)
            for i in range(count)]


HERS = learn(["love this fit #outfit #thrifted", "wore it twice already"])


def sources(got):
    return [g["source"] for g in got]


def test_every_tag_on_the_list_names_where_it_came_from():
    got = tags.candidates("instagram", "black ribbed tank", HERS, posts(), ARM)
    assert got
    for g in got:
        assert g["tag"].startswith("#") and g["source"] and g["evidence"], g
        assert g["source"] in ("your numbers", "your captions", "your words", "the format"), g


def test_the_ranking_of_the_evidence_is_strongest_first():
    got = tags.candidates("instagram", "black ribbed tank", HERS, posts(), ARM)
    assert got[0]["source"] == "your numbers", "her own ranked posts have to lead"
    assert sources(got)[:3] == ["your numbers", "your captions", "your captions"], sources(got)
    assert "the format" in sources(got)
    assert "4 of your posts ran under it" in got[0]["evidence"], got[0]["evidence"]


def test_an_arm_with_too_few_posts_is_not_a_signal_and_says_so():
    got = tags.candidates("instagram", "boots", HERS, posts(count=2), ARM)
    assert "your numbers" not in sources(got)
    said = " ".join(tags.missing(posts(count=2), HERS, "boots"))
    assert "2 posts on it" in said and "not a signal" in said, said


def test_each_placement_gets_its_own_count_and_nothing_more():
    for place, cap in (("instagram", 6), ("tiktok", 5), ("youtube", 3), ("pinterest", 4),
                       ("x", 1), ("threads", 3), ("something-else", tags.DEFAULT_LIMIT)):
        assert tags.limit_for(place) == cap
        got = tags.candidates(place, "black ribbed tank in the thrift shop", HERS, posts(), ARM)
        assert len(got) <= cap, (place, got)
    assert len(tags.candidates("x", "boots", HERS, posts(), ARM)) == 1


def test_the_worse_evidence_is_still_labelled_as_the_worse_evidence():
    """The last two sources are guesses with a traceable origin, and the page has to be able to
    say which is which - the difference between a tag list and a trend feed."""
    from_words = tags.candidates("instagram", "", HERS, [], "")
    assert set(sources(from_words)) == {"your captions"}, from_words
    from_shot = tags.candidates("instagram", "the new thrifted coat", learn([]), [], "")
    assert set(sources(from_shot)) == {"your words"}, from_shot
    assert from_shot[0]["tag"] == "#newthriftedcoat", from_shot


def test_nothing_is_invented_when_there_is_no_evidence():
    got = tags.candidates("instagram", "", learn([]), [], "")
    assert got == []
    gaps = tags.missing([], learn([]), "")
    assert len(gaps) == 3, gaps
    assert any("The Lab files them" in g for g in gaps)


def test_the_tags_that_cost_reach_are_never_shown_even_when_she_wrote_them():
    """#fyp is the one tag a fake trending widget always offers. It is banned here by the same
    list the daily writer uses, and it is dropped out of her own pasted captions too."""
    loud = learn(["great day #fyp #viral #foryou #xyzbca #thrifted"])
    assert "#fyp" not in loud.tags, "the voice learner should already have dropped it"
    got = tags.candidates("instagram", "boots", loud, [], "")
    text = " ".join(g["tag"] for g in got)
    for banned in ("#fyp", "#viral", "#foryou", "#xyzbca"):
        assert banned not in text, (banned, got)
    assert tags.usable("#fyp") is False


def test_a_tag_that_cannot_be_a_link_is_never_built():
    assert tags.usable("#ab") is False and tags.usable("#1234") is False
    assert tags.usable("#abc") is True, "three letters is a word, not a number"
    assert tags.slug("black ribbed tank") == "#blackribbedtank"
    assert tags.slug("thrifted in Leeds!") == "#thriftedinleeds"
    assert len(tags.slug("a" * 60)) <= 26, "a tag longer than the slug is a broken link"
    assert tags.candidates("instagram", "in the 2008", learn([]), [], "") == []


def test_the_block_she_copies_is_capped_at_the_placement_count():
    got = tags.candidates("instagram", "boots", HERS, posts(), ARM)
    assert tags.block("instagram", got) == " ".join(g["tag"] for g in got[:6])
    assert len(tags.block("x", got).split()) == 1
    assert "  " not in tags.block("tiktok", got)
