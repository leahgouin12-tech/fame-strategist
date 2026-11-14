"""The phrase list, the fold and the stated limits - proved with no network and no keyword tool.

What this module is usually accused of being is a list of invented keywords with a fake volume
figure beside each one, so the tests aim at exactly that: nothing reaches the list without
something on this machine putting it there, a tag is not allowed to report itself as a sentence,
the three positions a phrase can sit in are told apart instead of flattened into one warning, and
the words this app cannot know stay named rather than implied.
"""
import json
import re
from datetime import date
from types import SimpleNamespace

from src.metrics.ingest import MetricRow
from src.playbook.schema import Confidence, PlaybookEntry, Source, SourceTier
from src.seo import text as seo

TODAY = date(2026, 11, 14)
CAP = "thrifted tank again, worn to six places"
# Two of these a post could carry and one it cannot, so every branch of the fold check has a
# phrase to fall into.
FOUND = [seo.Term("thrifted", "your captions", "it is in 2 of the 3 captions you pasted"),
         seo.Term("tank", "your captions", "it is in 2 of the 3 captions you pasted"),
         seo.Term("latte", "your posts", "3 of your posts ran under 'latte', median 900 views")]
LATE = "ramble " * 20 + "the thrifted tank"


def row(ref, hypothesis, views=1200):
    return MetricRow("tiktok", ref, date(2026, 10, 1), views, views, 41.0, 3, 11, 4,
                     hypothesis=hypothesis, posted_hour=18)


def find(got, check):
    hits = [f for f in got["findings"] if f["check"] == check]
    assert hits, f"{check} is not on the page: {[f['check'] for f in got['findings']]}"
    return hits[0]


def fold(got):
    return find(got, "said before the fold")


def entry(eid, claim, confidence=Confidence.STRONG, as_of=date(2026, 9, 1)):
    return PlaybookEntry(
        eid, claim, "the mechanism, as written by the source", confidence,
        [Source("https://example.org/a", "A platform post", SourceTier.PLATFORM_OFFICIAL)],
        ["tiktok", "reels"], as_of, "this does not cover every account size")


# ---- where the phrases come in ------------------------------------------------

def test_the_list_is_empty_when_nothing_on_this_machine_has_put_a_word_in_it():
    assert seo.terms([], [], None) == []


def test_a_hypothesis_her_own_posts_ran_under_is_first_and_brings_its_median():
    got = seo.terms([row("p1", "thrifted-tank"), row("p2", "thrifted-tank"),
                     row("p3", "street-clip")], [], None)
    assert got[0].phrase == "thrifted tank" and got[0].source == "your posts"
    assert "2 of your posts ran under 'thrifted-tank'" in got[0].evidence
    assert "median 1,200 views" in got[0].evidence, "views is the column every import carries"


def test_a_post_with_no_hypothesis_and_one_that_was_never_named_contribute_nothing():
    assert [t for t in seo.terms([row("p1", ""), row("p2", "logged")], [], None)
            if t.source == "your posts"] == []


def test_a_word_is_counted_once_per_caption_rather_than_once_per_appearance():
    got = seo.terms([], ["the tank, the tank, the tank again", "tank day", "over and done"], None)
    tank = [t for t in got if t.phrase == "tank"]
    assert len(tank) == 1
    assert "in 2 of the 3 captions you pasted" in tank[0].evidence


def test_a_word_used_once_is_not_called_her_wording():
    assert seo.terms([], ["only one caption says latte here", "over and done"], None) == []


def test_the_hypothesis_the_plan_is_running_lends_its_name_and_the_niche_lends_its_own():
    week = SimpleNamespace(week_no=3, experiment="lifestyle day in life",
                           goal="Experiment: run hypothesis 1 of 6 - lifestyle day in life")
    plan = SimpleNamespace(hypotheses=["thrifted flip", "lifestyle day in life"],
                           chosen="thrifted streetwear")
    got = seo.terms([], [], plan, week)
    assert [t.phrase for t in got] == ["lifestyle day in life", "thrifted streetwear"], got
    assert all(t.source == "your plan" for t in got)
    assert "week 3 of the eight weeks is running it as the hypothesis" in got[0].evidence
    assert "the eight weeks were built on it" in got[1].evidence


def test_a_week_that_is_not_testing_lends_no_instruction_sentence_as_a_phrase():
    week = SimpleNamespace(
        week_no=6, experiment="hold format and cadence constant; compare against weeks 1-4",
        goal="Concentrate: double down on thrifted streetwear and the runner-up, cutting what "
             "week 1-4 data did not reward")
    plan = SimpleNamespace(hypotheses=["lifestyle day in life"], chosen="thrifted streetwear")
    got = seo.terms([], [], plan, week)
    assert [t.phrase for t in got] == ["thrifted streetwear"], got
    assert all(";" not in t.phrase and ":" not in t.phrase for t in got), \
        "an instruction is not something a search lands on"


def test_a_niche_spelled_with_hyphens_is_the_same_phrase_as_the_hypothesis_it_became():
    week = SimpleNamespace(week_no=1, experiment="lifestyle day in life", goal="")
    plan = SimpleNamespace(hypotheses=["lifestyle day in life"], chosen="lifestyle-day-in-life")
    got = seo.terms([], [], plan, week)
    assert [t.phrase for t in got] == ["lifestyle day in life"], got
    assert "running it as the hypothesis" in got[0].evidence, "the stronger evidence keeps the row"


def test_split_keeps_the_tags_out_of_the_sentence_it_is_about_to_read():
    cap, tags = seo.split("worn to six places #thrifted #fyp")
    assert cap == "worn to six places"
    assert tags == ["#thrifted", "#fyp"]


# ---- what the post carries ----------------------------------------------------

def test_a_phrase_only_in_a_tag_is_not_reported_as_said_in_the_caption():
    got = seo.audit(caption="worn to six places", hashtags=["#thrifted"], found=FOUND,
                    platform="tiktok")
    assert got["tagOnly"] == ["thrifted"] and not got["front"] and not got["late"]
    assert fold(got)["verdict"] == "weak" and "only in a tag" in fold(got)["line"]
    assert "not only inside a tag" in fold(got)["fix"]


def test_a_phrase_written_behind_the_fold_is_a_different_problem_from_one_absent():
    got = seo.audit(caption=LATE, found=FOUND, platform="tiktok")
    assert got["front"] == [] and got["late"] == ["thrifted", "tank"]
    assert "written in the caption but after" in fold(got)["line"]
    assert fold(got)["fix"].startswith("Move the phrase up")


def test_a_phrase_in_front_of_the_fold_and_one_nowhere_on_the_post_read_differently():
    early = seo.audit(caption=CAP, found=FOUND, platform="tiktok")
    absent = seo.audit(caption="worn to six places", found=FOUND, platform="tiktok")
    assert early["front"] == ["thrifted", "tank"] and early["missed"][0]["phrase"] == "latte"
    assert fold(early)["verdict"] == "carried" and fold(absent)["verdict"] == "missing"
    assert fold(early)["line"] != fold(absent)["line"]
    assert find(absent, "words a search could land on")["verdict"] == "missing"


def test_the_fold_sentence_agrees_with_the_number_of_phrases_in_front_of_it():
    assert "thrifted, tank appear inside" in fold(
        seo.audit(caption=CAP, found=FOUND, platform="tiktok"))["line"]
    assert "tank appears inside" in fold(
        seo.audit(caption="the tank", found=FOUND[:2], platform="tiktok"))["line"]


def test_one_phrase_is_reported_in_english_rather_than_as_a_plural():
    held = seo.audit(caption="thrifted and proud", found=FOUND[:1], platform="tiktok")
    line = find(held, "words a search could land on")["line"]
    assert line == "The one phrase this app can account for is on the post: thrifted.", line
    missed = seo.audit(caption="a latte this morning", found=FOUND[:1], platform="tiktok")
    lost = find(missed, "words a search could land on")["line"]
    assert "The one phrase this app can account for is not in the text you wrote." in lost, lost
    for got in (held, missed):
        assert "1 phrases" not in find(got, "words a search could land on")["line"]
    assert find(missed, "words a search could land on")["verdict"] == "missing"


def test_a_post_with_no_words_says_so_once_and_still_prints_its_limits():
    got = seo.audit(caption="", found=FOUND)
    assert [f["check"] for f in got["findings"]] == ["text on the post"]
    assert got["findings"][0]["verdict"] == "unreadable"
    assert got["cannot"] == seo.CANNOT


def test_with_no_phrase_to_check_against_the_page_refuses_the_verdict():
    got = seo.audit(caption=CAP, hashtags=["#thrifted"])
    check = find(got, "words a search could land on")
    assert check["verdict"] == "unreadable"
    assert "no phrase to check against" in check["line"].lower()


# ---- the alt field and the slots ----------------------------------------------

def test_an_empty_alt_field_is_a_missing_field_not_a_note():
    assert find(seo.audit(caption=CAP, found=FOUND), "alt field")["verdict"] == "missing"


def test_an_alt_written_as_a_keyword_list_is_refused_a_pass():
    alt = find(seo.audit(caption=CAP, found=FOUND, alt="tank tank tank tank thrifted tank"),
               "alt field")
    assert alt["verdict"] == "weak" and "repeats itself" in alt["line"]


def test_a_descriptive_alt_that_carries_one_of_the_phrases_passes():
    alt = find(seo.audit(caption=CAP, found=FOUND, alt="a person in a worn thrifted tank top"),
               "alt field")
    assert alt["verdict"] == "carried" and "thrifted" in alt["line"]


def test_each_tag_slot_is_charged_for_what_it_actually_does():
    got = seo.audit(caption=CAP, found=FOUND, platform="tiktok",
                    hashtags=["#fyp", "#thrifted", "#sustainableslowfashion"])
    why = {s["tag"]: s["why"] for s in got["spent"]}
    assert "chasing the feed" in why["#fyp"]
    assert "restatement" in why["#thrifted"]
    assert "cannot split" in why["#sustainableslowfashion"]


def test_a_tag_line_longer_than_the_placement_holds_is_counted_as_over():
    got = seo.audit(caption=CAP, platform="tiktok", hashtags=[f"#tag{i}word" for i in range(6)])
    assert any("looks like a wall" in s["why"] for s in got["spent"])


def test_a_caption_past_the_word_budget_this_app_reads_is_named_as_past_it():
    got = seo.audit(caption=CAP + " " + " ".join(f"filler{i}" for i in range(24)),
                    platform="tiktok", shape="tiktok")
    assert find(got, "caption length")["verdict"] == "weak"
    assert "22" in find(got, "caption length")["line"]


def test_a_caption_inside_the_budget_is_not_called_over_it():
    assert not [f for f in seo.audit(caption=CAP, platform="tiktok", shape="tiktok")["findings"]
                if f["check"] == "caption length"]


def test_the_head_the_page_shows_is_cut_where_the_fold_is_read():
    got = seo.audit(caption=LATE, found=FOUND, platform="tiktok", alt="a tank")
    assert "ramble" in got["head"] and "thrifted" not in got["head"]


# ---- honesty of the output ----------------------------------------------------

def test_nothing_the_audit_returns_claims_a_volume_a_rank_or_an_index_it_cannot_see():
    blob = json.dumps({k: v for k, v in seo.audit(caption=CAP, alt="a thrifted tank",
                                                 found=FOUND, platform="tiktok").items()
                       if k != "cannot"}).lower()
    assert "volume" not in blob
    assert not re.search(r"\d[\d,]*\s*(searches|queries|people search)", blob)
    assert "indexed" not in blob


def test_the_limits_are_printed_rather_than_left_out():
    joined = " ".join(seo.CANNOT).lower()
    assert len(seo.CANNOT) >= 4
    for absent in ("volume", "indexed", "sits for any phrase", "not theirs", "exports"):
        assert absent in joined


def test_the_gaps_say_why_the_list_is_short():
    got = seo.gaps([], [], None)
    assert len(got) == 3
    assert "nothing has been imported" in got[0].lower(), got[0]
    assert "eight-week plan" in got[2]


def test_posts_that_arrived_without_a_hypothesis_are_not_reported_as_never_imported():
    got = seo.gaps([row("p1", "")], ["the thrifted tank"], None)
    assert "none of the posts you imported carries a hypothesis" in got[0].lower(), got[0]
    assert "lab" in got[0].lower(), "it has to say where a hypothesis gets filed"


def test_a_gap_closes_only_when_the_thing_that_fills_it_arrives():
    got = seo.gaps([row("p1", "thrifted-tank")], ["the thrifted tank"], None)
    assert not any("hypothesis" in g.lower() or "pasted" in g.lower() for g in got)
    assert any("eight-week plan" in g for g in got)


# ---- the library's own words --------------------------------------------------

def test_only_live_sourced_claims_about_text_are_quoted_with_their_citation():
    entries = [
        entry("keywords-in-the-first-line", "Put the search phrase in the first line of the "
              "caption, where the fold leaves it readable."),
        entry("posting-frequency", "Post more often to grow faster, says nobody in particular."),
        entry("alt-is-decorative", "Alt text is decorative and can be skipped entirely.",
              confidence=Confidence.FOLKLORE),
        entry("old-caption-advice", "Hashtags written in the caption hurt search reach.",
              as_of=date(2021, 1, 1)),
    ]
    got = seo.rules(entries, TODAY)
    assert [r["claim"] for r in got] == [entries[0].claim]
    assert got[0]["source"] == "A platform post"
    assert got[0]["tier"] == "platform_official"
    assert got[0]["does_not_claim"] == "this does not cover every account size"


def test_a_text_claim_with_no_source_still_names_the_source_that_is_not_there():
    bare = PlaybookEntry("no-source", "The first line is where a search reads the caption.",
                         "the fold hides the rest", Confidence.CONTESTED, [], ["tiktok"], TODAY,
                         "no volume figure is implied")
    got = seo.rules([bare], TODAY)
    assert got[0]["where"] == "" and got[0]["source"] == ""
