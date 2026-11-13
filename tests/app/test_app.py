from datetime import date
import json
import re

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import Config

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


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(api_key=None, engine_name="offline", model=""), tmp_path / "a.sqlite3")
    return TestClient(app)


@pytest.fixture
def planned(client):
    client.post("/interview", data=COMPLETE)
    client.post("/plan/build")
    return client


def test_the_app_states_what_it_cannot_promise(client):
    assert "cannot promise" in client.get("/").text.lower()


def test_offline_mode_is_announced_not_hidden(client):
    assert "without a model key" in client.get("/").text.lower()


def test_home_lists_the_loaded_evidence(client):
    body = client.get("/").text
    assert "claims" in body and "engine: offline" in body


def test_the_interview_refuses_an_unusable_answer_and_saves_nothing(client):
    body = client.post("/interview", data={**COMPLETE, "hours_per_week": "1"}).text
    assert "hours_per_week must be at least 2" in body
    assert "take the interview" in client.get("/niches").text.lower()


def test_a_blank_field_is_named_not_filled_in(client):
    body = client.post("/interview", data={**COMPLETE, "what_you_actually_film": ""}).text
    assert "what_you_actually_film" in body
    assert 'value="outfits in my room' not in body


def test_scoring_returns_ranked_hypotheses_with_numbers(planned):
    body = planned.get("/niches").text
    assert "total" in body and "saturation read" in body


def test_the_plan_shows_eight_weeks_and_their_sourced_basis(planned):
    body = planned.get("/plan").text
    assert body.count("<tr>") >= 9
    assert "Weeks 1-4 measure" in body


def test_today_shows_the_shot_list_and_says_who_wrote_the_copy(planned):
    body = planned.get("/today", params={"on": "2026-11-20"}).text
    assert "Say this first" in body
    assert "Shots" in body
    assert "copy written by: local" in body
    assert "engine: offline" in body
    assert "[" not in body.split("Say this first")[1][:220]


def test_one_click_replaces_the_whole_setup(client):
    """The interview is optional. One POST adopts the stated assumptions and lands on
    a day that is actually filmable."""
    assert "Assuming:" in client.get("/").text
    body = client.post("/start", data={"what_you_actually_film": "outfits in my room"}).text
    assert "Say this first" in body
    assert "outfits" in body.lower()
    assert "Week" in body and "copy written by" in body


def test_the_one_click_page_lists_every_assumption_it_is_making(client):
    body = client.get("/").text
    for line in ["hours a week", "on camera", "starting from 0 followers"]:
        assert line in body


def test_three_numbers_typed_off_the_phone_beat_a_csv_export(planned):
    lines = "\n".join(f"{1000 + i} {12 if i % 2 else 40} {1 if i % 2 else 9}" for i in range(9))
    body = planned.post("/numbers", data={"quick": lines}).text
    assert "9 posts read" in body
    assert "adjust" in body or "stop" in body or "amplify" in body
    assert planned.post("/numbers/apply").status_code == 200


def test_a_line_that_is_not_three_numbers_is_named_not_guessed(planned):
    body = planned.post("/numbers", data={"quick": "1200 41 3\ni forgot this one"}).text
    assert "line 2" in body


def test_marking_a_day_posted_persists(planned):
    planned.post("/today/done", data={"on": "2026-11-20"})
    assert "marked posted" in planned.get("/today", params={"on": "2026-11-20"}).text


def test_metrics_below_the_data_floor_are_met_with_an_admission(planned):
    csv = "post_ref,views,avg_watch_pct,follows_gained\na,500,30,2\nb,400,12,1\nc,900,44,4\n"
    body = planned.post("/numbers", files={"csv": ("m.csv", csv, "text/csv")}).text
    assert "below the floor" in body
    assert "amplify" not in body


def test_metrics_above_the_floor_produce_a_reading(planned):
    rows = "\n".join(f"p{i},1000,{12 if i % 2 else 40},{1 if i % 2 else 9}" for i in range(9))
    csv = "post_ref,views,avg_watch_pct,follows_gained\n" + rows
    body = planned.post("/numbers", files={"csv": ("m.csv", csv, "text/csv")}).text
    assert "adjust" in body or "stop" in body


def test_every_claim_page_shares_who_said_it_and_what_it_misses(client):
    body = client.get("/sources").text
    assert "Does not establish" in body
    assert 'href="https://' in body


def test_no_page_offers_the_forbidden_actions(planned):
    # /sources is excluded on purpose: it quotes the platforms' own policy text, which
    # names these behaviours in order to say they cost reach.
    pages = [planned.get(p).text for p in ["/", "/niches", "/plan", "/today", "/numbers"]]
    joined = " ".join(pages).lower()
    for verb in ["unfollow", "auto-follow", "buy followers", "mass follow", "public url", "dm"]:
        assert verb not in joined, verb


def test_no_form_or_endpoint_implements_account_automation(planned):
    import re

    html = " ".join(planned.get(p).text for p in ["/", "/niches", "/plan", "/today", "/numbers"])
    actions = re.findall(r'action="([^"]+)"', html)
    assert actions
    assert not any(re.search(r"follow|dm|message|publish|scrape", a) for a in actions)


def test_the_app_binds_nothing_public(client):
    paths = {getattr(r, "path", "") for r in client.app.routes}
    assert not any(p.startswith("/media") or "public" in p for p in paths)
    assert not any("follow" in p for p in paths)


def test_the_day_gives_one_block_to_copy_not_a_page_to_reread(planned):
    body = planned.get("/today", params={"on": "2026-11-20"}).text
    assert body.count("<textarea") == 1, "two blocks means two things to copy"
    block = re.search(r"<textarea[^>]*>(.*?)</textarea>", body, re.S).group(1)
    caption = re.search(r'<p class="claim">(.*?)</p>', body, re.S).group(1)
    tags = re.findall(r'<span class="chip">(#[^<]+)</span>', body)
    assert tags and all(t in block for t in tags)
    assert caption in block and "\n\n" in block.strip()


def test_the_picker_only_lists_files_she_actually_has(planned, tmp_path):
    _seed_media(tmp_path)
    body = planned.get("/today", params={"on": "2026-11-20"}).text
    options = re.findall(r'<option value="([^"]*)"', body)
    assert "look.png" in options and "edited/crop.jpg" in options
    assert "take.mp4" in options and "edited/cut.mp4" in options
    assert "notes.txt" not in options and "" in options, "an empty choice must exist"


def test_a_saved_cut_stays_tied_to_the_day_it_was_posted_for(planned, tmp_path):
    _seed_media(tmp_path)
    day = "2026-11-20"
    body = planned.post("/today/attach", data={"on": day, "file": "edited/cut.mp4"}).text
    assert "edited/cut.mp4" in body and "clip" in body
    assert "edited/cut.mp4" in planned.get("/today", params={"on": day}).text
    picker = re.search(r'<select name="file".*?</select>',
                       planned.get("/today", params={"on": day}).text, re.S).group(0)
    assert "selected" in picker, "the picker must reopen pointing at what that day used"
    assert planned.app.state.db.get_days(day, day)[0]["attach"] == {
        "file": "edited/cut.mp4", "kind": "clip"}


def test_the_attach_guard_refuses_a_path_that_is_not_hers(planned, tmp_path):
    _seed_media(tmp_path)
    (tmp_path / "outside.png").write_bytes(b"x")
    day = "2026-11-20"
    body = planned.post("/today/attach", data={"on": day, "file": "../outside.png"}).text
    assert "not in your folders" in body
    assert planned.app.state.db.get_days(day, day) == [], "a refused name records nothing"


def test_clearing_the_attachment_leaves_nothing_tied_to_the_day(planned, tmp_path):
    _seed_media(tmp_path)
    day = "2026-11-20"
    planned.post("/today/attach", data={"on": day, "file": "look.png"})
    planned.post("/today/attach", data={"on": day, "file": ""})
    assert planned.app.state.db.get_days(day, day)[0].get("attach") is None
    body = planned.get("/today", params={"on": day}).text
    assert "Nothing tied to this day yet" in body
    picker = re.search(r'<select name="file".*?</select>', body, re.S).group(0)
    assert "selected" not in picker, "the picker must not still point at the cleared file"


def test_marking_a_day_posted_keeps_the_file_attached_to_it(planned, tmp_path):
    """save_day replaces the whole payload, so anything that writes one piece of a
    day has to read the rest back first - otherwise the file silently un-ties itself."""
    _seed_media(tmp_path)
    day = "2026-11-20"
    planned.post("/today/attach", data={"on": day, "file": "take.mp4"})
    planned.post("/today/done", data={"on": day})
    logged = planned.app.state.db.get_days(day, day)[0]
    assert logged["done"] and logged["attach"]["file"] == "take.mp4"
    assert logged["posted"] is True


def test_the_app_never_claims_to_post_it_for_her(planned):
    body = planned.get("/today", params={"on": "2026-11-20"}).text.lower()
    assert "does not post for you" in body
    assert "nothing leaves this machine" in body


def test_a_date_she_could_not_have_typed_still_opens_a_day(planned):
    page = planned.get("/today", params={"on": "not-a-date"})
    assert page.status_code == 200
    assert "Say this first" in page.text


def test_the_tie_records_the_resolved_path_not_what_was_typed(planned, tmp_path):
    _seed_media(tmp_path)
    day = "2026-11-20"
    planned.post("/today/attach", data={"on": day, "file": "edited/../look.png"})
    assert planned.app.state.db.get_days(day, day)[0]["attach"] == {
        "file": "look.png", "kind": "photo"}


def test_the_handoff_refuses_a_magic_hour_and_a_written_alt_text(planned):
    body = planned.get("/today", params={"on": "2026-11-20"}).text
    assert "myth-best-time-to-post-chart" in body, "the refusal has to name its source"
    assert "only you can say what to" in body, "alt text is refused, and the reason is given"


def _seed_media(tmp_path):
    from PIL import Image

    inbox = tmp_path / "inbox"
    (inbox / "edited").mkdir(parents=True, exist_ok=True)
    (tmp_path / "clips" / "edited").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 1200), (200, 30, 90)).save(inbox / "look.png")
    Image.new("RGB", (720, 1280), (30, 90, 200)).save(inbox / "edited" / "crop.jpg")
    (inbox / "notes.txt").write_text("not media", encoding="utf-8")
    (tmp_path / "clips" / "take.mp4").write_bytes(b"a clip she named")
    (tmp_path / "clips" / "edited" / "cut.mp4").write_bytes(b"a saved cut")
    return inbox


def _inbox_client(tmp_path):
    from PIL import Image, ImageDraw

    app = create_app(Config(api_key=None, engine_name="offline", model=""), tmp_path / "a.sqlite3")
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    for name, size in [("sharp.png", (1080, 1920)), ("wide.png", (2000, 1200))]:
        im = Image.new("RGB", size, (240, 240, 240))
        ImageDraw.Draw(im).rectangle([40, 40, size[0] // 2, size[1] // 2], fill=(20, 20, 20))
        im.save(inbox / name)
    return TestClient(app)


def _tilted_inbox(tmp_path):
    """A tilted horizon in the inbox, so the one-click fix has something to straighten."""
    import math

    from PIL import Image, ImageDraw

    client = _inbox_client(tmp_path)
    inbox = tmp_path / "inbox"
    for stale in inbox.glob("*"):
        stale.unlink()
    im = Image.new("RGB", (1080, 1920), (122, 88, 52))
    drift = math.tan(math.radians(4)) * 1080 / 2
    ImageDraw.Draw(im).polygon([(0, 0), (1080, 0), (1080, 960 + drift), (0, 960 - drift)],
                               fill=(86, 148, 224))
    im.save(inbox / "tilt.png")
    return client


def test_photos_reads_the_folder_she_drops_files_into(tmp_path):
    client = _inbox_client(tmp_path)
    body = client.get("/photos").text
    assert client.get("/photos").status_code == 200
    assert "sharp.png" in body and "wide.png" in body
    assert "crop" in body, "the off-shape file must be offered a crop"
    assert "Does not establish" in body


def test_the_fix_button_writes_a_copy_and_reports_both_scores(tmp_path):
    client = _tilted_inbox(tmp_path)
    body = client.post("/photos/clean", data={"name": "tilt.png"}).text
    assert "tilt-clean.jpg" in body
    assert "score" in body, "she must see what the fix actually changed"
    assert (tmp_path / "inbox" / "clean" / "tilt-clean.jpg").is_file()
    assert (tmp_path / "inbox" / "tilt.png").is_file(), "the original stays put"


def test_photos_tells_her_where_to_drop_files_when_it_is_empty(client, tmp_path):
    body = client.get("/photos").text
    assert str(tmp_path / "inbox") in body
    assert "Nothing to read yet" in body


def test_the_clean_button_cannot_reach_outside_the_inbox(client, tmp_path):
    (tmp_path / "outside.png").write_bytes(b"x")
    body = client.post("/photos/clean", data={"name": "../outside.png"}).text
    assert "not in the inbox folder" in body


def test_the_editor_opens_a_file_and_previews_an_edit(tmp_path):
    client = _inbox_client(tmp_path)
    page = client.get("/edit?name=sharp.png")
    assert page.status_code == 200
    assert "Hold to see the original" in page.text
    assert "Save a copy" in page.text
    assert "slim" in page.text.lower(), "the page must say what the editor refuses to do"
    shot = client.get("/edit/preview", params={"name": "sharp.png",
                                               "ops": json.dumps([["exposure", 0.6],
                                                                  ["heal", 0.5, 0.5, 0.04]])})
    assert shot.status_code == 200
    assert shot.headers["content-type"] == "image/jpeg"


def test_saving_an_edit_writes_a_copy_and_its_recipe(tmp_path):
    client = _inbox_client(tmp_path)
    recipe = json.dumps([["exposure", 0.4], ["rotate", 2.5], ["nonsense", 1]])
    saved = client.post("/edit/save", data={"name": "sharp.png", "recipe": recipe, "format": "jpg"},
                        follow_redirects=False)
    assert saved.status_code == 303
    out = list((tmp_path / "inbox" / "edited").glob("*.jpg"))
    side = list((tmp_path / "inbox" / "edited").glob("*.json"))
    assert out and side, "the copy and its edit list belong together"
    assert [e[0] for e in json.loads(side[0].read_text(encoding="utf-8"))] == ["rotate", "exposure"]
    assert (tmp_path / "inbox" / "sharp.png").is_file(), "the original stays put"
    again = client.get(saved.headers["location"])
    assert again.status_code == 200 and "2.5" in again.text, "reopening restores the sliders"


def test_the_editor_cannot_be_pointed_at_a_file_outside_her_folders(tmp_path):
    client = _inbox_client(tmp_path)
    (tmp_path / "outside.png").write_bytes(b"x")
    assert "Pick a file first" in client.get("/edit", params={"name": "../outside.png"}).text
    assert client.get("/edit/preview", params={"name": "../outside.png"}).status_code == 404
    assert client.get("/edit/preview", params={"name": "nope.png", "ops": "not json"}).status_code == 404


def test_the_picker_accepts_a_picture_and_lands_in_the_editor(tmp_path):
    from PIL import Image

    client = _inbox_client(tmp_path)
    for stale in (tmp_path / "inbox").glob("*"):
        stale.unlink()
    probe = tmp_path / "probe.png"
    Image.new("RGB", (1200, 1600), (200, 30, 90)).save(probe)
    with probe.open("rb") as fh:
        landed = client.post("/photos/upload", files={"file": ("probe.png", fh.read(), "image/png")},
                             follow_redirects=False)
    assert landed.status_code == 303
    assert (tmp_path / "inbox" / "probe.png").is_file()
    assert client.get(landed.headers["location"]).status_code == 200
    refused = client.post("/photos/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert ".txt" in refused.text


def test_the_coach_arrives_with_receipts_and_no_claims_to_have_acted(planned):
    body = planned.get("/weekly").text
    assert "Two weeks counted" in body and "Proposals" in body
    assert "does not post, send, reply, schedule" in body
    assert "Nothing above has been applied" in body


def test_the_coach_needs_the_plan_before_it_opines(client):
    assert "Nothing to coach yet" in client.get("/weekly").text


def test_the_coach_counts_the_day_she_marked_posted(planned):
    planned.post("/today/done", data={"on": date.today().isoformat()})
    body = planned.get("/weekly").text
    assert re.search(r'<span class="big">1</span>\s*<span class="k"> marked posted', body), \
        "a day she posted has to reach the coach's count"


def test_the_coach_reads_the_last_numbers_import(planned):
    planned.post("/numbers", data={"quick": "a 1200 41 3\nb 900 12 1\n"})
    body = planned.get("/weekly").text
    assert "2 posts from your last import" in body
    assert "a" in body and "generic" in body, "under 25 posts the coach says it is generic"
    assert "No live trend research has run" in body


def test_the_coach_shows_the_dated_sources_behind_the_current_slots(planned):
    body = planned.get("/weekly").text
    assert "checked 2026-" in body, "every claim the slots rest on carries its own date"
    assert re.search(r'<a href="https://[^"]+">[^<]+</a> \(', body), "and where it was checked"


def test_the_coach_costs_nothing_and_says_so(planned):
    body = planned.get("/weekly").text
    assert "0 model credits" in body and "all local CPU" in body


SAMPLES = ("i did this thing today and it went badly lol #outfit\n\n"
           "wait why is the lighting like this")


def test_the_writer_learns_from_what_she_pasted_and_keeps_it(planned):
    page = planned.post("/write/samples", data={"samples": SAMPLES}).text
    assert planned.app.state.db.get_voice() == ["i did this thing today and it went badly lol #outfit",
                                                "wait why is the lighting like this"]
    assert "Learned from 2 things you actually wrote" in page
    assert "i did this thing today" in page, "the box reopens with her own words"
    assert "of sentences without a capital" in page, "the card quotes the measured habit"


def test_the_writer_cuts_three_platforms_of_the_same_line_not_one_copy_pasted(planned):
    planned.post("/write/samples", data={"samples": SAMPLES})
    page = planned.get("/write").text
    for platform in ("tiktok", "reels", "x"):
        assert f'id="copy-{platform}"' in page and f'id="btn-{platform}"' in page


def test_the_hook_is_the_first_line_of_what_she_copies(planned):
    planned.post("/write/samples", data={"samples": SAMPLES})
    page = planned.get("/write").text
    shown = re.search(r'<p class="claim" style="font-size:19px">(.*?)</p>', page).group(1)
    block = re.search(r'<textarea id="copy-tiktok" rows="4">(.*?)</textarea>', page, re.S).group(1)
    assert block.startswith(shown), "a hook under the caption is a hook nobody hears"


def test_the_writer_states_that_it_sent_nothing_anywhere(planned):
    page = planned.get("/write").text
    assert "no model\ncall" in page or "no model call" in page.replace("\n", " ")
    assert "never uploaded" in page.lower()


def test_the_writer_leaves_alt_text_to_the_person_who_took_the_shot(planned):
    page = planned.get("/write").text
    assert "Alt text is yours" in page


def test_the_writer_still_learns_before_a_plan_exists(client):
    client.post("/write/samples", data={"samples": SAMPLES})
    page = client.get("/write").text
    assert "No line to rewrite yet" in page and "2 samples" in page
