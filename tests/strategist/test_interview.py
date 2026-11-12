import pytest

from src.db import DB
from src.strategist.interview import Interview, InterviewAnswers


def answer(**over):
    return InterviewAnswers(
        **{
            "hours_per_week": 5,
            "on_camera": True,
            "has_clips": True,
            "gear": "phone",
            "platforms": ["tiktok"],
            "comfort": ["talking"],
            "existing_followers": 0,
            "what_you_actually_film": "outfits and room clips",
            **over,
        }
    )


def test_missing_answers_are_rejected_not_assumed():
    with pytest.raises(ValueError):
        InterviewAnswers()


def test_checklist_names_only_what_is_missing():
    assert Interview.checklist(answer(what_you_actually_film="")) == ["what_you_actually_film"]


def test_a_full_answer_needs_nothing():
    assert Interview.checklist(answer()) == []


def test_zero_hours_is_not_a_valid_plan():
    assert "hours_per_week must be at least 2" in Interview.checklist(answer(hours_per_week=0))


def test_zero_existing_followers_is_a_real_answer_not_a_blank():
    assert "existing_followers" not in Interview.checklist(answer(existing_followers=0))


def test_no_platforms_is_missing_even_though_the_list_exists():
    assert "platforms" in Interview.checklist(answer(platforms=[]))


def test_roundtrip_through_db(tmp_path):
    db = DB(tmp_path / "t.sqlite3")
    db.save_interview(answer())
    assert db.get_interview() == answer()


def test_db_starts_empty(tmp_path):
    assert DB(tmp_path / "t.sqlite3").get_interview() is None


def test_complete_gate_blocks_the_planner(tmp_path):
    assert Interview.complete(answer()) is True
    assert Interview.complete(answer(comfort=[])) is False


def test_the_one_click_defaults_are_complete_and_admitted_as_assumptions():
    answers = Interview.defaults()
    assert Interview.complete(answers)
    assert answers.hours_per_week == 5
    assert Interview.assumptions(answers), "an assumption nobody can see is a guess"
    assert "phone" in " ".join(Interview.assumptions(answers))


def test_only_the_footage_line_is_asked_for_because_only_that_is_theirs():
    assert "sitting on your phone" in Interview.defaults().what_you_actually_film
    assert Interview.defaults("  outfits in my room ").what_you_actually_film == "outfits in my room"
