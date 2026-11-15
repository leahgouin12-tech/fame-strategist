"""The list, the way it gets written and moved.

What is proved here is the storage layer's own two refusals, because both of them are the
product: an entry with no name is refused rather than filed under something usable, and a stage
this app cannot see is refused rather than guessed near enough - the funnel then counts what she
actually said happened. Also proved: the id survives a stage change (so a link she clicked half
a minute ago cannot move somebody else's entry), a form value that is not a number is a refusal
rather than a crash, and the page's empty state names which of the two ways it can be empty she
is in.
"""

import datetime

import pytest

from src.collab import pitch, store
from src.db import DB

TODAY = datetime.date(2026, 11, 14).isoformat()
WHY = "she answered a small account with a 90-second tutorial instead of a like"


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "collab-store.sqlite3")


def filed(db, **over):
    row = dict(name="@laurenmakesthefits", why=WHY,
               ask="a swap: I film the try-on in their jacket, they film mine",
               format="one reel each, cut together", platform="tiktok")
    row.update(over)
    made, reason = store.add(db, row, TODAY)
    assert made is not None, reason
    return made


def test_the_list_starts_empty_rather_than_seeded_with_somebody_she_never_mentioned(db):
    assert store.load(db) == []


def test_a_name_is_the_one_thing_a_candidate_cannot_be_saved_without(db):
    made, reason = store.add(db, {"name": "   ", "why": "nice account"}, TODAY)
    assert made is None
    assert "name" in reason.lower()
    assert "search" in reason.lower(), "it has to say this app cannot go and find a name"
    assert store.load(db) == []


def test_what_she_typed_is_trimmed_and_capped_instead_of_stored_at_any_length(db):
    filed(db, name="@" + "a" * 200, why="w" * 900)
    row = store.load(db)[0]
    assert len(row["name"]) == store.MAX["name"]
    assert len(row["why"]) == store.MAX["why"]
    assert row["name"].startswith("@")


def test_an_unknown_stage_on_the_way_in_becomes_the_first_one_rather_than_being_kept(db):
    filed(db, status="sent")
    assert store.load(db)[0]["status"] == pitch.STATUSES[0]


def test_every_field_she_typed_survives_the_round_trip(db):
    filed(db)
    row = store.load(db)[0]
    assert row["ask"].startswith("a swap")
    assert row["format"] == "one reel each, cut together"
    assert row["platform"] == "tiktok"
    assert row["made_at"] == TODAY
    assert row["moved_at"] == "", "nothing has been moved yet, so the page cannot claim a date"


def test_an_entry_keeps_its_id_while_only_the_stage_moves(db):
    kept = filed(db)
    other = filed(db, name="@other")
    assert store.move(db, kept, "replied", TODAY) == ""
    rows = {row["id"]: row for row in store.load(db)}
    assert rows[kept]["status"] == "replied"
    assert rows[kept]["moved_at"] == TODAY
    assert rows[kept]["why"] == WHY, "the reason is hers - a stage change must not rewrite it"
    assert rows[other]["status"] == pitch.STATUSES[0], "moving one ask moves one ask"


def test_a_stage_this_app_cannot_see_is_refused_with_the_five_it_does_know(db):
    kept = filed(db)
    reason = store.move(db, kept, "sent", TODAY)
    assert "not one of the stages" in reason
    for stage in pitch.STATUSES:
        assert stage in reason, "the refusal has to list what she can actually type"
    assert "you say it did" in reason, "and say why the app will not take a word for it"
    assert store.load(db)[0]["status"] == pitch.STATUSES[0]


def test_moving_an_entry_that_is_not_there_reports_rather_than_filing_a_new_one(db):
    filed(db)
    assert "not on the list any more" in store.move(db, 4242, "replied", TODAY)
    assert len(store.load(db)) == 1, "a wrong id must not add an entry"


def test_a_form_value_that_is_not_a_number_is_a_refusal_rather_than_a_crash(db):
    filed(db)
    assert store.move(db, "not-an-id", "replied", TODAY)
    assert store.drop(db, "not-an-id") is False
    assert len(store.load(db)) == 1


def test_taking_an_entry_off_removes_that_one_and_says_when_there_was_nothing_to_remove(db):
    first, second = filed(db), filed(db, name="@other")
    assert store.drop(db, first) is True
    left = store.load(db)
    assert [row["name"] for row in left] == ["@other"]
    assert store.drop(db, first) is False, "already gone, which is not the same as removed"
    assert store.drop(db, second) is True
    assert store.load(db) == []


def test_the_page_names_which_of_the_two_ways_it_is_empty_she_is_in(db):
    both = store.note([], [])
    assert "nobody is on the list" in both.lower()
    assert "Numbers page" in both, "an empty offer has to say where a number comes from"
    only_numbers = store.note([], [pitch.Offer("tiktok", 4, 1000, 41.0, 8.5, False)])
    assert "Numbers page" not in only_numbers
    assert "reason" in only_numbers.lower(), "the reason is the part only she can supply"
    assert store.note([{"name": "@other"}], []) == "", "a filled list has no empty state"
