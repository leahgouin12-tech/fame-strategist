"""The money module, tested the way she would be tested: with a brand's DM open in the other
window. Every number on this page has to trace back to a post she imported, a figure she typed,
or a playbook entry with a date on it - so the tests check the arithmetic line by line and, more
than once, check that the module refuses to say a number at all.
"""
import re
from datetime import date, timedelta

import pytest

from src.money import rate
from src.metrics.ingest import MetricRow
from src.playbook.schema import Confidence, PlaybookEntry


def post(platform, views, day="2026-11-01", ref="p"):
    return MetricRow(platform=platform, post_ref=ref, published_at=date.fromisoformat(day),
                     reach=views, views=views, avg_watch_pct=40.0, follows_gained=3,
                     comments=1, saves=1)


def rows(platform="tiktok", n=5, views=1000):
    return [post(platform, views + i, ref=f"{platform}{i}.jpg") for i in range(n)]


@pytest.fixture
def library():
    """The four claims money/rate.py is allowed to price from, loaded from the real folder."""
    from pathlib import Path
    from src.playbook.store import Store

    entries = Store().load(Path("data/playbook"), allow_pending=True)
    return [e for e in entries if e.id.startswith("money-")]


def test_posts_are_grouped_by_the_platform_they_ran_on():
    got = rate.priceable(rows("tiktok", 3) + rows("reels", 4, views=2000))
    assert got == {"tiktok": (3, 1001), "reels": (4, 2001)}


def test_the_app_s_own_placeholders_are_not_platforms():
    """Numbers typed quickly come back as `logged` and a CSV with no platform column as
    `unknown`. Blending those with a real import would invent a place that does not exist and
    price her TikTok views as though they ran there."""
    for name in ("logged", "unknown", ""):
        assert rate.priceable([post(name, 1000)] * 5) == {}, name
    mixed = rate.priceable(rows("unknown", 9) + rows("tiktok", 5))
    assert set(mixed) == {"tiktok"}, "the anonymous rows are left out, not averaged in"


def test_a_paste_with_no_platform_in_it_is_not_a_rate_for_any_platform():
    """A quick log records the number and nothing else; inventing a placement to price would
    put a tiktok number on an instagram quote."""
    loose = [MetricRow(platform="logged", post_ref="a", published_at=date(2026, 11, 1), reach=0,
                       views=5000, avg_watch_pct=30.0, follows_gained=2, comments=0, saves=0)]
    assert rate.priceable(loose) == {}
    assert rate.priceable(loose + rows("x", 6)) == {"x": (6, 1002)}


def test_zero_view_rows_do_not_drag_the_median_down():
    got = rate.priceable(rows("reels", 5, views=1000) + [post("reels", 0, ref="zero")])
    assert got["reels"] == (5, 1002)


def test_three_posts_is_refused_by_name_not_rounded_up(library):
    made, thin, uncited = rate.quotes(rows("tiktok", 3), library)
    assert made == ()
    assert len(thin) == 1 and "3 posts imported, 5 needed" in thin[0]
    assert uncited == ()


def test_the_number_is_her_median_views_times_the_published_bands(library):
    made, _, _ = rate.quotes(rows("tiktok", 5, views=1000), library)
    q = made[0]
    assert (q.posts, q.median_views) == (5, 1002)
    # median 1002 views: the benchmark band gives 15.49, the campaign band 4.47 to 25.76
    assert q.low == pytest.approx(4.47, abs=0.02)
    assert q.high == pytest.approx(25.76, abs=0.02)
    assert q.anchor == pytest.approx((15.49 + (4.47 + 25.76) / 2) / 2, abs=0.02)
    assert q.low < q.anchor < q.high, "the single number sits inside the published spread"


def test_youtube_priced_on_its_own_published_bands_reaches_higher(library):
    tt = rate.quotes(rows("tiktok", 5, views=8000), library)[0][0]
    yt = rate.quotes(rows("youtube", 5, views=8000), library)[0][0]
    assert len(yt.bands) == len(tt.bands) + 2
    assert yt.high > tt.high


def test_a_stale_entry_takes_its_number_with_it(library):
    old = [PlaybookEntry(
        id=e.id, claim=e.claim, mechanism=e.mechanism, confidence=e.confidence,
        sources=e.sources, applies_to=e.applies_to,
        as_of=date.today() - timedelta(days=800), does_not_claim=e.does_not_claim)
        for e in library]
    made, thin, uncited = rate.quotes(rows("tiktok", 5), old)
    assert made == ()
    assert uncited == ("tiktok",), "priced from nothing is worse than refusing to price"


def test_the_published_bands_are_not_invented_figures():
    """Every Band names a playbook entry that exists in the folder, so no rate on the page can
    come from a number somebody typed into this file and called research."""
    from pathlib import Path
    from src.playbook.store import Store

    ids = {e.id for e in Store().load(Path("data/playbook"), allow_pending=True)}
    for band in rate.SHORT_FORM + rate.YOUTUBE:
        assert band.entry in ids, band.label
    assert rate.TIER_BASIS in ids and rate.RIGHTS_BASIS in ids


def test_the_floor_is_her_time_times_her_hourly(library):
    made, _, _ = rate.quotes(rows("tiktok", 5, views=1000), library, hourly=20, minutes=90)
    q = made[0]
    assert q.floor == 30.0
    assert q.under_floor, "a 1k-view median does not clear thirty dollars of work"
    assert "never under $30" in q.line


def test_no_hourly_means_no_floor_and_no_invented_wage(library):
    made, _, _ = rate.quotes(rows("tiktok", 5, views=1000), library)
    q = made[0]
    assert q.floor == 0 and not q.under_floor
    assert "never under" not in q.line


def test_add_ons_price_off_a_base_that_exists(library):
    assert rate.addon_lines(0) == []
    lines = rate.addon_lines(200)
    usage = next(l for l in lines if l["name"].startswith("Usage rights"))
    assert usage["of_base"] == (40.0, 100.0)
    spend = [l for l in lines if l["of_base"] is None]
    assert len(spend) == 2, "the two shapes priced on their media, not on her fee"
    assert all(re.match(r"^\d+ to \d+ percent", l["range"]) for l in spend)


def test_a_line_of_advice_is_named_as_being_a_line_of_advice():
    """The disagreement between per-base and per-spend is the product, not a rounding error."""
    shapes = {l["shape"] for l in rate.addon_lines(200)}
    assert "of the base fee" in shapes and "of the ad spend" in shapes


# ---- the label check ---------------------------------------------------------

def test_a_plain_named_label_clears_at_the_front():
    d = rate.check_disclosure("Sponsored by Threadlight - the coat I wore twice.", "pinned")
    assert d.status == "clear" and d.found == ("sponsored",) and d.first_at == 0
    assert d.safe_to_post and not d.needs_video


def test_hashtag_ad_counts_as_the_word_not_as_something_else():
    d = rate.check_disclosure("#ad - they sent me the coat", "photo")
    assert d.status == "clear" and d.found == ("ad",)


def test_advertisement_is_reported_as_itself_not_truncated_to_ad():
    d = rate.check_disclosure("Advertisement: Threadlight paid for this.", "photo")
    assert d.found == ("advertisement",)


def test_a_label_buried_in_a_long_caption_is_flagged_as_behind_the_fold():
    body = "A " * 130 + "Sponsored. " + "and then the rest of the caption " * 10
    d = rate.check_disclosure(body, "photo")
    assert d.status == "clear" and d.behind_fold and not d.safe_to_post
    assert "the fold" in d.notes[0] and "125" in d.notes[0]


def test_a_word_that_only_appears_inside_a_sentence_is_not_taken_as_a_label():
    d = rate.check_disclosure("The ad on the bus stop had my coat in it.", "photo")
    assert d.status == "clear", "the word is there"
    assert any("inside a sentence" in n for n in d.notes), "but it is flagged as prose"


def test_nothing_in_the_text_means_nothing_says_it_is_an_ad():
    d = rate.check_disclosure("the coat again - third time this week", "photo")
    assert d.status == "missing" and not d.safe_to_post
    assert "advertisement, ad and sponsored" in d.line


def test_product_or_a_favour_is_compensation_even_with_no_fee_in_it():
    d = rate.check_disclosure("they sent me this dress and it is perfect", "photo")
    assert d.status == "missing" and d.compensated
    assert any("material connection" in n for n in d.notes)


def test_a_word_the_cited_guidance_does_not_name_is_accepted_and_marked():
    d = rate.check_disclosure("Paid partnership with the shop, link in bio", "photo")
    assert d.status == "unverified" and d.not_named == ("paid partnership",)
    assert "does not name" in d.line


def test_a_video_placement_owes_the_label_in_the_picture_not_the_caption():
    d = rate.check_disclosure("Sponsored - the coat.", "tiktok")
    assert d.needs_video and not d.safe_to_post
    assert any("in the video" in n for n in d.notes)
    assert rate.check_disclosure("Sponsored - the coat.", "tiktok", in_video=True).safe_to_post


def test_the_check_never_claims_to_have_seen_the_crop():
    d = rate.check_disclosure("Sponsored - the coat.", "photo")
    assert any("crop" in n for n in d.notes), "it says what it cannot see instead of passing it"


def test_the_label_rule_is_a_playbook_claim_too():
    """A legal requirement stated in this file with no citation would be the worst kind of
    advice this app can give, so the term list has to trace to a sourced entry."""
    from pathlib import Path
    from src.playbook.store import Store

    entry = next(e for e in Store().load(Path("data/playbook"), allow_pending=True)
                 if e.id == "money-disclosure-required")
    assert entry.confidence is Confidence.PROVEN
    for term in rate.NAMED_TERMS:
        assert term in entry.claim or term in entry.mechanism, term
