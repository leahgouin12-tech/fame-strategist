"""Each tool run on its own, rather than only inside a plan somebody asked for.

The registry flagged fourteen of them as named by no test file. The pages cover the same
ground when a plan happens to reach for a tool, but nothing said what one tool returns, or
what it says when it has no business running at all - and the second half is where a fake
success would hide. Writing these found strategy.build and strategy.niches crashing on an
attribute the niche hypothesis does not have, which no page test could see because the
routes build the plan through their own code path.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.agent import orchestrator
from src.agent.tools import catalogue
from src.app import create_app
from src.config import Config
from src.metrics.ingest import MetricRow

COMPLETE = {
    "hours_per_week": "6",
    "existing_followers": "0",
    "what_you_actually_film": "outfits in my room and the odd street clip",
    "gear": "phone",
    "has_clips": "on",
    "on_camera": "on",
    "platforms": ["tiktok", "reels"],
    "comfort": ["talking", "text on screen"],
}

VOICE = ("I film in my room because the light there is the only light I can control. "
         "Nothing about this is polished and that is the point.")

QUICK = "clip-0042 1200 45 12\nclip-0043 2400 61 20\nclip-0044 900 30 4"


@pytest.fixture
def alone(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""),
                     tmp_path / "a.sqlite3")
    client = TestClient(app)
    return client, client.app.state.kit


def planned(kit):
    client, k = kit
    client.post("/interview", data=COMPLETE)
    return client, k


def with_plan(kit):
    client, k = planned(kit)
    client.post("/plan/build")
    return client, k


def with_numbers(kit):
    client, k = with_plan(kit)
    client.post("/numbers", data={"quick": QUICK})
    return client, k


def with_photo(kit):
    """A tool that reads the inbox is tested against a picture in it, not an empty folder."""
    client, k = kit
    folder = k.paths["inbox"]
    folder.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (240, 320), (180, 160, 140))
    im.save(folder / "one.jpg", "JPEG")
    return client, k


def test_an_empty_app_gets_a_reason_rather_than_a_result(alone):
    client, kit = alone
    for tool in catalogue():
        out = orchestrator.execute(kit, tool["id"], {})
        assert out.kind in ("did", "advised", "skipped"), f"{tool['id']}: {out.kind}"
        if tool["needs"]:
            assert out.kind == "skipped", f"{tool['id']} reported success with nothing ready"
            assert out.summary.startswith("Not run: "), tool["id"]
        else:
            assert out.summary.strip(), f"{tool['id']} ran silently"


def test_the_library_searches_the_real_playbook_and_shows_the_tiers(alone):
    client, kit = alone
    broad = orchestrator.execute(kit, "research.library", {})
    narrow = orchestrator.execute(kit, "research.library", {"topic": "posting"})
    assert broad.detail["picked"], "the shipped playbook has claims in it"
    assert len(narrow.detail["picked"]) < len(broad.detail["picked"])
    assert sum(narrow.detail["tiers"].values()) == len(narrow.detail["picked"])


def test_the_niche_ranking_names_each_hypothesis_with_what_it_rests_on(alone):
    client, kit = planned(alone)
    out = orchestrator.execute(kit, "strategy.niches", {"limit": 3})
    assert out.kind == "advised", out.summary
    rows = out.detail["ranked"]
    assert len(rows) == 3
    for row in rows:
        assert row["name"] and row["because"], f"{row} has no evidence behind it"
        assert 0 <= row["score"] <= 1


def test_building_the_plan_through_the_agent_writes_the_plan_the_app_reads(alone):
    client, kit = planned(alone)
    out = orchestrator.execute(kit, "strategy.build", {})
    assert out.kind == "did", out.summary
    assert kit.plan() is not None, "it said eight weeks and stored nothing"
    assert out.detail["weeks"] == len(kit.plan().weeks)
    assert "lifestyle" in out.summary or out.detail["experiments"], out.summary


def test_marking_a_day_writes_the_day_row_it_claims_to_have_written(alone):
    client, kit = with_plan(alone)
    iso = kit.build_day(datetime.date.today()).date.isoformat()
    out = orchestrator.execute(kit, "day.mark", {"on": iso})
    assert out.kind == "did", out.summary
    stored = kit.db.get_days(iso, iso)
    assert stored and stored[0]["done"], "the tool said posted and the day row says otherwise"


def test_judging_and_polishing_work_on_the_picture_that_is_actually_there(alone):
    client, kit = with_photo(alone)
    judged = orchestrator.execute(kit, "media.judge", {})
    assert judged.kind == "did", judged.summary
    assert judged.detail["ranked"], "a readable frame should produce a reading"
    assert judged.detail["best"] == judged.detail["ranked"][0]["file"]
    face = orchestrator.execute(kit, "media.face", {})
    assert face.kind == "did", face.summary
    assert "never a score" in face.summary, "the face tool must not pretend to rank a face"


def test_polishing_writes_a_file_into_edited_and_points_at_it(alone):
    client, kit = with_photo(alone)
    out = orchestrator.execute(kit, "media.polish", {"look": "warm"})
    assert out.kind == "did", out.summary
    written = kit.paths["edited"]
    files = [p for p in written.glob("*") if p.suffix.lower() in (".jpg", ".png")]
    assert files, "it reported a new file and left the folder empty"
    assert out.detail["written"] == files[0].name


def test_stored_numbers_are_readable_by_the_next_tool(alone):
    client, kit = with_numbers(alone)
    out = orchestrator.execute(kit, "metrics.take", {"text": "clip-0045 3100 58 22"})
    assert out.kind == "did", out.summary
    refs = [r.post_ref for r in kit.rows()]
    assert "clip-0045" in refs, "the ledger does not contain what the tool said it stored"
    assert out.detail["under_floor"] == (len(out.detail["posts"]) < out.detail["floor"])


def test_a_bad_block_is_named_not_stored(alone):
    client, kit = with_numbers(alone)
    out = orchestrator.execute(kit, "metrics.take", {"text": "just a note about today"})
    assert out.kind == "skipped", out.summary
    assert "views" in out.summary, "it should say which numbers were missing"


def test_the_window_and_the_adaptation_read_the_rows_she_imported(alone):
    client, kit = with_numbers(alone)
    window = orchestrator.execute(kit, "metrics.window", {})
    assert window.kind == "advised", window.summary
    assert window.detail["measured"] == 0, "these rows carry no hour, so no window is claimed"
    assert "hour" in window.summary.lower()
    adapt = orchestrator.execute(kit, "metrics.adapt", {})
    assert adapt.kind == "did", adapt.summary
    assert len(adapt.detail["adjustments"]) == int(
        adapt.summary.split()[0]), "the count in the sentence is the count in the detail"


def test_the_caption_packs_refuse_until_she_has_pasted_her_own_writing(alone):
    client, kit = with_plan(alone)
    empty = orchestrator.execute(kit, "copy.packs", {"platform": "tiktok"})
    assert empty.kind == "skipped", "with no voice stored this must not invent one"
    assert "pasted" in empty.summary
    client.post("/write/samples", data={"samples": VOICE})
    got = orchestrator.execute(kit, "copy.packs", {"platform": "tiktok"})
    assert got.kind == "advised", got.summary
    assert got.detail["variants"] and got.detail["learned"], got.detail


def test_the_reply_desk_writes_nothing_and_says_it_wrote_nothing(alone):
    client, kit = alone
    out = orchestrator.execute(kit, "community.drafts", {})
    assert out.kind == "advised", out.summary
    assert "Nothing was sent" in out.summary
    assert out.detail["drafts"] == []


def test_the_coach_proposes_from_the_days_that_actually_landed(alone):
    client, kit = with_numbers(alone)
    iso = kit.build_day(datetime.date.today()).date.isoformat()
    orchestrator.execute(kit, "day.mark", {"on": iso})
    out = orchestrator.execute(kit, "research.coach", {})
    assert out.kind == "advised", out.summary
    assert int(out.summary.split()[0]) == len(out.detail["moves"])
    assert "1 of 1 posted days" in out.summary, out.summary
    assert out.detail["posts"] == 3, "the numbers she typed are the posts it read"
    assert out.detail["generic"] is True, "three posts is under the floor and it has to say so"
    for move in out.detail["moves"]:
        assert move["text"] and move["basis"], f"advice with nothing behind it: {move}"
    stored = kit.db.recall("proposal")
    assert {n["body"] for n in stored} == {m["text"] for m in out.detail["moves"]}, \
        "a move it proposed but did not remember is a move nobody can accept later"


def test_the_memory_keeps_what_a_research_run_learned(alone):
    client, kit = with_plan(alone)
    before = orchestrator.execute(kit, "memory.recall", {"limit": 5})
    assert before.kind == "advised", before.summary
    assert before.detail["notes"] == [], "nothing has been read yet for it to remember"
    week = orchestrator.execute(kit, "research.week", {})
    assert week.kind == "did", week.summary
    after = orchestrator.execute(kit, "memory.recall", {"limit": 5})
    assert after.detail["notes"], "a research run writes what it read into the notes table"
    assert len(after.detail["notes"]) <= 5
    assert {n["kind"] for n in after.detail["notes"]} <= {"finding", "brief", "proposal"}


def post(ref, views, watch, follows, hypothesis=""):
    return MetricRow(platform="tiktok", post_ref=ref, published_at=datetime.date.today(),
                     reach=views, views=views, avg_watch_pct=watch, follows_gained=follows,
                     comments=0, saves=0, hypothesis=hypothesis)


def test_the_lab_files_the_posts_that_carry_no_hypothesis_and_no_others(alone):
    """The hole this tool exists to close: the numbers she types used to be stored with an
    empty hypothesis column, so the comparison in metrics.adapt had nothing to read."""
    client, kit = with_plan(alone)
    arm = kit.plan().weeks[0].experiment
    kit.save_rows([post(f"u{i}", 1000, 30.0, 9) for i in range(8)])
    filed = orchestrator.execute(kit, "experiment.file", {})
    assert filed.kind == "did", filed.summary
    assert filed.detail["filed"] == 8 and filed.detail["arm"] == arm, filed.detail
    assert all(r.hypothesis == arm for r in kit.rows()), "it said filed and stored otherwise"

    again = orchestrator.execute(kit, "experiment.file", {})
    assert again.detail["filed"] == 0, "re-running must not relabel history"
    assert all(r.hypothesis == arm for r in kit.rows())


def test_the_lab_names_a_winner_only_when_the_arms_separate(alone):
    client, kit = with_plan(alone)
    arms = [w.experiment for w in kit.plan().weeks]
    kit.save_rows([post(f"a{i}", 1000, 30.0, 14, arms[0]) for i in range(5)]
                  + [post(f"b{i}", 1000, 30.0, 5, arms[1]) for i in range(5)])
    separated = orchestrator.execute(kit, "experiment.arms", {})
    assert separated.kind == "advised", separated.summary
    assert separated.detail["state"] == "called", separated.detail
    assert separated.detail["kept"] == arms[0] and separated.detail["dropped"] == arms[1]

    kit.save_rows([post(f"a{i}", 1000, 30.0, 9, arms[0]) for i in range(5)]
                  + [post(f"b{i}", 1000, 30.0, 9, arms[1]) for i in range(5)])
    flat = orchestrator.execute(kit, "experiment.arms", {})
    assert flat.detail["state"] != "called", "two arms converting alike are not a result"
    assert flat.detail["kept"] == "", "a page that always finds a winner is how a year is wasted"


def test_the_lab_says_what_is_missing_instead_of_inventing_a_comparer(alone):
    client, kit = with_plan(alone)
    kit.save_rows([post(f"u{i}", 1000, 30.0, 9) for i in range(9)])
    out = orchestrator.execute(kit, "experiment.arms", {})
    assert out.kind == "advised", out.summary
    assert out.detail["unlabelled"] == 9 and out.detail["arms"] == []
    assert out.detail["missing"], "the refusal has to say what would change it"
    assert out.detail["where"] == "/lab", "advice that hides where to act is not actionable"


def test_the_repurpose_tool_reports_the_files_it_really_wrote(alone):
    """`repurpose.cuts` is the one tool whose deliverable is a file on disk, so the check is
    the disk: a `did` with nothing in the edited folder is exactly the fake success this app
    is told not to ship."""
    client, kit = with_plan(alone)
    arms = [w.experiment for w in kit.plan().weeks]
    kit.save_rows([post(f"w{i}.jpg", 1000, 30.0, 14, arms[0]) for i in range(5)]
                  + [post(f"l{i}.jpg", 1000, 30.0, 5, arms[1]) for i in range(5)])
    Image.new("RGB", (1200, 1600), (170, 140, 110)).save(kit.paths["inbox"] / "w0.jpg", "JPEG")
    got = orchestrator.execute(kit, "repurpose.cuts", {"limit": 1})
    assert got.kind == "did", got.summary
    assert got.detail["where"] == "/repurpose"
    assert got.detail["posts"] == 1 and len(got.detail["cuts"]) == 3, got.detail
    for cut in got.detail["cuts"]:
        assert (kit.paths["edited"] / cut["file"]).is_file(), f"reported and not written: {cut}"
        assert cut["from"] == "w0.jpg" and cut["arm"] == arms[0], cut
        assert cut["platform"] in ("tiktok", "reels", "x") and cut["shape"]


def test_the_repurpose_tool_advises_when_it_wrote_nothing(alone):
    """The numbers are stored and the pictures are not. `did` here would send her to a folder
    with no crops in it, so the tool reports the posts it could not open instead."""
    client, kit = with_plan(alone)
    arms = [w.experiment for w in kit.plan().weeks]
    kit.save_rows([post(f"w{i}.jpg", 1000, 30.0, 14, arms[0]) for i in range(5)]
                  + [post(f"l{i}.jpg", 1000, 30.0, 5, arms[1]) for i in range(5)])
    got = orchestrator.execute(kit, "repurpose.cuts", {})
    assert got.kind == "advised", got.summary
    assert got.detail["cuts"] == []
    assert len(got.detail["skipped"]) == 10, "every ranked post is named, not a silent zero"
    assert all("does not hold the file" in s for s in got.detail["skipped"])
    assert not kit.paths["edited"].exists() or list(kit.paths["edited"].iterdir()) == []


def test_the_repurpose_tool_needs_an_arm_before_it_looks_for_files(alone):
    client, kit = with_plan(alone)
    kit.save_rows([post(f"u{i}.jpg", 1000, 30.0, 9) for i in range(9)])
    got = orchestrator.execute(kit, "repurpose.cuts", {})
    assert got.kind == "skipped", got.summary
    assert "arm label" in got.summary, "the reason has to be the reason she can act on"
