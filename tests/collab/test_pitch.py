"""The pitch module's own rules, tested as rules rather than as output.

Three things are worth proving here because they are the three ways this feature could lie: that
the numbers come only from her import and a median is a median (not a mean dressed up, not a
platform's published average, not a stranger's count); that a pitch with no reason in it is not
written at all rather than filled with an invented one; and that a reply rate is refused while
there are too few asks for the fraction to mean anything. The rest is arithmetic she could check
by hand.
"""

import datetime

from src.collab import pitch
from src.metrics.ingest import MetricRow

DAY = datetime.date(2026, 10, 1)


def row(platform, views, watch=41.0, follows=9, ref="p"):
    return MetricRow(platform, ref, DAY, views, views, watch, follows, 3, 2, "x")


def four_tiktok():
    return [row("tiktok", v, ref=f"t{i}") for i, v in enumerate([900, 1000, 1100, 4000])]


# ---- what she has to offer --------------------------------------------------

def test_the_offer_is_built_from_her_import_and_from_nothing_else():
    got = pitch.offers(four_tiktok())
    assert [o.platform for o in got] == ["tiktok"]
    assert got[0].posts == 4


def test_a_median_is_a_median_not_a_mean_wearing_its_clothes():
    got = pitch.offers(four_tiktok())
    assert got[0].median_views == 1050, "900 and 1100 either side of the middle, not the 1750 mean"


def test_a_platform_with_no_name_and_a_post_with_no_views_contribute_nothing():
    got = pitch.offers([row("unknown", 5000), row("", 3000), row("logged", 2000),
                        row("tiktok", 0)])
    assert got == [], "an anonymous row cannot be quoted to a brand as anyone's reach"


def test_one_post_is_quoted_as_one_afternoon_rather_than_as_a_rate():
    got = pitch.offers([row("reels", 400, watch=30.0, follows=4)])
    offer = got[0]
    assert offer.thin is True
    assert "one afternoon that went well, not a rate" in offer.line()
    assert "median" not in offer.line(), "a single number is not a median of anything"


def test_two_posts_is_enough_to_be_called_a_median_and_carries_its_own_roughness():
    got = pitch.offers([row("reels", 400), row("reels", 600, ref="b")])
    offer = got[0]
    assert offer.thin is False and offer.posts == 2
    line = offer.line()
    assert "a median of 500 views across 2 posts on reels" in line, line
    assert "41.0% watched through" in line and "follows per 1000 views" in line, line


def test_follows_per_thousand_is_her_whole_import_rather_than_the_best_post():
    got = pitch.offers([row("tiktok", 1000, follows=9), row("tiktok", 1000, follows=11, ref="b")])
    assert got[0].follows_per_1000 == 10.0


def test_the_platform_with_the_most_posts_behind_it_leads_when_she_does_not_name_one():
    got = pitch.offers(four_tiktok() + [row("reels", 9000), row("reels", 9500, ref="b")])
    assert pitch.best(got).platform == "tiktok"
    assert pitch.best(got, "reels").platform == "reels", "what she says beats the biggest number"
    assert pitch.best([]) is None


# ---- the message ------------------------------------------------------------

def test_a_pitch_with_no_reason_in_it_is_not_written_at_all():
    got = pitch.pitch("Nadia", "   ")
    assert got["lines"] == [], "an invented reason is a lie she would have to send"
    assert "made up" in got["held"][0]
    assert got["numbers"] == ""


def test_the_reason_she_gave_is_the_reason_that_goes_in_the_message():
    why = "the way you cut the fitting room into three beats"
    got = pitch.pitch("Nadia", why)
    assert got["lines"][0] == f"Here is the specific thing: {why}", got["lines"][0]


def test_a_pitch_without_an_ask_is_still_written_and_says_what_is_missing():
    got = pitch.pitch("Nadia", "your lighting")
    assert got["lines"], "the pitch is useful even without an ask, as long as it admits it"
    assert any("no ask" in h for h in got["held"]), got["held"]
    assert "tell me what would be easy to say yes to" in " ".join(got["lines"])


def test_the_ask_she_named_reaches_the_message_with_the_format_she_named():
    got = pitch.pitch("Nadia", "your lighting", ask="one swap each, filmed the same week",
                      format_="reel + a tiktok")
    said = " ".join(got["lines"])
    assert "one swap each, filmed the same week" in said and "reel + a tiktok" in said, said
    assert not any("no ask" in h for h in got["held"])


def test_the_only_number_in_the_pitch_is_the_one_her_import_produced():
    offer = pitch.offers(four_tiktok())[0]
    got = pitch.pitch("Nadia", "your lighting", offer=offer)
    assert f"On my side: {offer.line()}." in got["lines"], got["lines"]
    assert got["numbers"] == offer.line()


def test_with_nothing_imported_the_pitch_leads_with_the_work_instead_of_a_figure():
    got = pitch.pitch("Nadia", "your lighting")
    assert not any("views" in l for l in got["lines"]), got["lines"]
    assert "the work, because I would rather you judged it than a number" in " ".join(got["lines"])
    assert any("no number" in h for h in got["held"]), got["held"]


def test_a_thin_number_stays_in_the_pitch_and_is_flagged_rather_than_smoothed_out():
    offer = pitch.offers([row("reels", 400)])[0]
    got = pitch.pitch("Nadia", "your lighting", offer=offer)
    assert any("400 views" in l for l in got["lines"]), got["lines"]
    assert any("quoted as what it is" in h for h in got["held"]), got["held"]


def test_the_close_leaves_the_door_open_without_promising_anything():
    got = pitch.pitch("Nadia", "your lighting")
    assert got["lines"][-1] == ("If it is not a fit, no worries - I'll keep posting either way.")


def test_no_line_of_the_pitch_claims_anything_about_the_other_account():
    got = pitch.pitch("Nadia", "your lighting", ask="one swap each")
    said = " ".join(got["lines"]).lower()
    for forbidden in ("your followers", "your reach", "your audience is", "you have",
                      "your engagement"):
        assert forbidden not in said, said


# ---- where the asks got to --------------------------------------------------

def test_an_empty_list_is_a_list_of_people_to_want_not_a_reply_rate():
    got = pitch.funnel([])
    assert got["asked"] == 0 and got["rate"] is None
    assert "no reply rate" in got["meaning"]


def test_below_the_apps_own_floor_the_fraction_is_refused_as_an_anecdote():
    got = pitch.funnel([{"status": "pitched"}, {"status": "replied"}, {"status": "to pitch"}])
    assert got["asked"] == 2 and got["answered"] == 1 and got["rate"] == 50.0
    assert "not a rate yet" in got["meaning"], got["meaning"]
    assert got["waiting"] == 1, "an unsent ask is not a failed ask"


def test_enough_asks_before_the_number_is_allowed_to_look_like_a_number():
    got = pitch.funnel([{"status": "pitched"}] * 8 + [{"status": "replied"}] * 2
                       + [{"status": "made something"}])
    assert got["asked"] == 11 and got["answered"] == 3 and got["rate"] == 27.3
    assert "enough asks" in got["meaning"], got["meaning"]


def test_a_stage_the_app_does_not_know_about_is_ignored_rather_than_guessed():
    got = pitch.funnel([{"status": "sent"}, {"status": ""}, {"status": "replied"}])
    assert got["asked"] == 1 and got["answered"] == 1 and got["list_n"] == 3, got


def test_only_the_stages_this_app_knows_are_accepted():
    assert pitch.usable("Replied") and pitch.usable("  pitched ")
    for wrong in ("sent", "", "auto-sent", "dm"):
        assert not pitch.usable(wrong), wrong


def test_the_limits_travel_with_every_pitch_rather_than_being_left_implied():
    got = pitch.pitch("Nadia", "your lighting")
    joined = " ".join(got["cannot"]).lower()
    assert ("another account" in joined and "scrapes" in joined
            and "only when you say it did" in joined)
    assert list(pitch.CANNOT) == got["cannot"], "the same list every time, not a fresh excuse"
