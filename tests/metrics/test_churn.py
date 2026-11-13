import json

from src.metrics.churn import churn_report, parse_export

IG_FOLLOWERS = json.dumps([{"value": "111", "username": "Noor_A"},
                           {"value": "222", "username": "sam.b"},
                           {"value": "333", "username": "lee"}])
IG_LATER = json.dumps([{"value": "111", "username": "Noor_A"},
                       {"value": "444", "username": "new.person"}])
TT_FOLLOWING = json.dumps({"following": [
    {"id": "1", "username": "@noor_a", "addTimestamp": 1730000000000},
    {"id": "2", "username": "@sam.b", "addTimestamp": 1700000000}]})
DAYS = [{"date": "2026-11-08", "done": True, "hypothesis": "outfit-and-style"},
        {"date": "2026-11-10", "done": False, "hypothesis": "beauty-glam"}]


def test_an_instagram_export_becomes_a_list_of_handles():
    snap = parse_export(IG_FOLLOWERS, taken="2026-11-01", source="followers_1.json")
    assert not snap.error
    assert snap.names == ("noor_a", "sam.b", "lee")


def test_a_tiktok_export_carries_its_own_dates():
    snap = parse_export(TT_FOLLOWING, taken="2026-11-01", source="following.json")
    assert snap.names == ("noor_a", "sam.b")
    assert snap.added["noor_a"].startswith("2024-10") or snap.added["noor_a"].startswith("2025-10")
    assert len(snap.added["sam.b"]) == 10, "seconds and milliseconds both appear in real exports"


def test_a_pasted_list_of_names_is_enough():
    snap = parse_export("@Noor_A\nsam.b\n\nnoor_a", taken="2026-11-01")
    assert snap.names == ("noor_a", "sam.b"), "deduped, lowercased, order kept"


def test_junk_is_named_not_guessed():
    assert parse_export("total nonsense {{", taken="2026-11-01").error
    assert parse_export("{}", taken="2026-11-01").error


def test_one_snapshot_cannot_tell_a_story():
    a = parse_export(IG_FOLLOWERS, taken="2026-11-01")
    report = churn_report([a], DAYS)
    assert report["diffs"] == []
    assert "second export" in report["note"].lower()


def test_the_diff_names_who_left_and_who_arrived():
    report = churn_report([parse_export(IG_FOLLOWERS, taken="2026-11-01"),
                           parse_export(IG_LATER, taken="2026-11-12")], DAYS)
    d = report["diffs"][0]
    assert d["lost"] == ["sam.b", "lee"] and d["gained"] == ["new.person"]
    assert d["kept"] == 1, "a 400-name list is not going to be printed in full"
    assert d["window"]["start"] == "2026-11-01" and d["window"]["end"] == "2026-11-12"


def test_the_churn_window_is_placed_against_the_days_she_posted():
    report = churn_report([parse_export(IG_FOLLOWERS, taken="2026-11-01"),
                           parse_export(IG_LATER, taken="2026-11-12")], DAYS)
    w = report["diffs"][0]["window"]
    assert w["posted"] == ["2026-11-08"] and w["missed"] == ["2026-11-10"]
    assert "2 accounts left" in w["note"] and "1 of 2 slots" in w["note"]
    assert "outfit-and-style" in w["note"] and "beauty-glam" in w["note"]


def test_an_empty_list_is_a_failed_export_not_a_mass_unfollow():
    report = churn_report([parse_export(IG_FOLLOWERS, taken="2026-11-01"),
                           parse_export("[]", taken="2026-11-12")], DAYS)
    assert report["diffs"] == []
    assert "0 names" in report["note"]


def test_the_report_says_it_took_no_action():
    report = churn_report([parse_export(IG_FOLLOWERS, taken="2026-11-01"),
                           parse_export(IG_LATER, taken="2026-11-12")], DAYS)
    assert report["stance"], "the page must state the boundary in its own words"
    assert "insight" in report["stance"].lower() and "no action" in report["stance"].lower()
