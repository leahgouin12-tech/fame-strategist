from src.strategist.engage import (
    PRIORITY, bio_review, classify, draft, parse, plan, queue_note, series_rows, watch_rows)
from src.strategist.voice import learn

LOWS = ["i did this thing today and it went badly lol 😂 #outfit #fitcheck",
        "honestly nobody tells you about the lighting 😭 #fitcheck",
        "wait why is this so hard? #outfit"]
FORMAL = ["I filmed this in one take. It is not my best work.",
          "Do you dress like this too? Tell me below.",
          "The lighting was wrong, but the outfit carried it."]
LOW = learn(LOWS)


def test_a_question_is_a_question():
    assert classify("wait what jacket is this") == "demand"
    assert classify("how did you get the lighting so flat?") == "question"
    assert classify("does this come in a size 12?") == "demand"


def test_a_link_is_not_a_conversation():
    assert classify("check my page for free followers") == "spam"
    assert classify("nice video, visit www.spam.com") == "spam"
    assert classify("AMAZING OFFER CLICK NOW") == "spam"


def test_the_critic_and_the_fan_are_told_apart():
    assert classify("this is so cringe, done following") == "criticism"
    assert classify("I hate that I clicked on this") == "criticism"
    assert classify("ok obsessed with this fit") == "praise"
    assert classify("my mum had the same day") == "human"


def test_short_flags_do_not_fire_inside_an_unrelated_word():
    assert classify("that would work for both of us") == "human", "not every both is a bot"
    assert classify("I love the middle part best") == "praise", "not every middle is mid"


def test_pasting_off_a_screen_survives_the_parse():
    rows = parse("maria: what pants are those?\n\n@jules - obsessed\nplain line with no name")
    assert [r["author"] for r in rows] == ["maria", "jules", "someone"]
    assert rows[2]["text"] == "plain line with no name"


def test_every_reply_leaves_the_only_she_knows_part_blank():
    for text in ("how much was it?", "what jacket is that?", "my mum had the same day",
                 "obsessed with this", "this is cringe", "is it worth it?"):
        d = draft({"author": "x", "text": text}, LOW)
        assert "____" in d.line, text
        assert d.fills, text
        assert not d.refused


def test_a_spam_comment_is_refused_with_a_reason_not_a_reply():
    d = draft({"author": "x", "text": "follow back and check my page"}, LOW)
    assert d.refused and d.line == "" and "No reply, on purpose" in d.why


def test_the_queue_is_ordered_by_what_actually_converts():
    drafts = plan(parse("maria: obsessed\nsam: what pants are those?\n"
                        "kim: follow back please\nlee: this is cringe\nada: how do you do it?"),
                  LOW)
    ordered = [d.intent for d in drafts]
    assert ordered[:3] == ["demand", "question", "praise"]
    assert ordered[-1] == "spam", "the refused one goes to the bottom, not the top"
    assert "spam" not in PRIORITY


def test_the_drafts_are_written_the_way_she_writes():
    formal = plan(parse("maria: what jacket is this?"), learn(FORMAL))
    low = plan(parse("maria: what jacket is this?"), LOW)
    assert formal[0].line[0].isupper()
    assert low[0].line[0].islower()


def test_the_queue_says_what_it_found_in_plain_numbers():
    assert queue_note([]).startswith("Nothing pasted yet")
    note = queue_note(plan(parse("a: obsessed\nb: check my link .com"), LOW))
    assert "2 comments read" in note and "1 worth a reply" in note and "1 refused" in note


def test_the_bio_is_checked_from_its_own_words():
    rows = bio_review("outfits | link in bio | shop my store | new every day", target_posts=4)
    asks = [r for r in rows if r["name"] == "one ask, or none"][0]
    assert asks["passed"] == 0 and "2 calls to action" in asks["note"]
    assert [r for r in rows if r["name"] == "a cadence you can actually keep"][0]["passed"] == 1


def test_a_bio_that_names_nobody_is_said_so():
    rows = bio_review("just vibes and stuff")
    assert [r for r in rows if r["name"] == "who it is for"][0]["passed"] == 0
    assert [r for r in rows if r["name"] == "length against the platform limit"][0]["passed"] == 1


def test_the_bio_says_the_real_platform_limits():
    note = [r for r in bio_review("x" * 200) if r["name"] == "length against the platform limit"][0]
    assert note["passed"] == 0 and "200 characters" in note["note"] and "80" in note["note"]


def test_continuations_come_from_her_own_best_post():
    rows = series_rows({"post_ref": "clip-0042", "hypothesis": "outfit-and-style"}, LOW)
    assert len(rows) == 3
    assert any("clip-0042" in r["title"] for r in rows)
    assert any("outfit-and-style" in r["title"] for r in rows)
    assert all(r["why"] for r in rows)


def test_the_watch_list_is_hers_and_the_detail_stays_hers():
    rows = watch_rows("noor: she posted a rack of thrifted blazers\n@sam", LOW)
    assert len(rows) == 2
    assert all("____" in r["line"] for r in rows)
    assert [r["who"] for r in rows] == ["noor", "sam"]
    assert rows[1]["note"] == "", "a handle with no note is not invented into one"
    assert "you listed" in rows[0]["why"].lower()
    assert any("no login" in r["why"].lower() for r in rows), "it says it did not find them"
    assert watch_rows("", LOW) == []
