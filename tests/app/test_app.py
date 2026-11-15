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


def test_the_app_can_be_installed_rather_than_visited(client):
    """An icon in the Start menu with its own window is what makes this a program to her,
    and the manifest is the only thing standing between a URL and that."""
    assert 'rel="manifest"' in client.get("/today").text
    manifest = json.loads(client.get("/static/manifest.webmanifest").text)
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/today"
    assert manifest["scope"] == "/"
    for icon in manifest["icons"]:
        got = client.get(icon["src"])
        assert got.status_code == 200, f"{icon['src']} is declared but not there to fetch"
        assert got.headers["content-type"].startswith("image/png")
        assert got.content[:8] == b"\x89PNG\r\n\x1a\n", "a manifest icon has to be a real image"
    worker = client.get("/static/sw.js")
    assert worker.status_code == 200, "the browser wants a worker before it offers to install"
    page = client.get("/today").text
    assert "/static/sw.js" in page, "a worker nobody registers installs nothing"
    assert "beforeinstallprompt" in page, "she has to be able to install it from inside the app"
    assert "text/html" in worker.text, "the worker keeps pages, not her photos"
    worker = client.get("/static/sw.js")
    assert worker.status_code == 200, "the browser needs a worker before it offers to install"
    page = client.get("/today").text
    assert "/static/sw.js" in page, "a worker that is never registered installs nothing"
    assert "beforeinstallprompt" in page, "she has to be able to install it from inside the app"
    assert "text/html" in worker.text, "the worker must keep pages, not her photos"


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


def test_a_one_tap_fix_can_be_picked_up_and_edited_again(tmp_path):
    """The clean copy used to land in a folder nothing listed: one click, then it was
    invisible and the editor refused to open it, so the fix was a dead end."""
    client = _tilted_inbox(tmp_path)
    client.post("/photos/clean", data={"name": "tilt.png"})
    body = client.get("/photos").text
    assert "/edit?name=clean/tilt-clean.jpg" in body, "the strip must link the folder it wrote"
    page = client.get("/edit", params={"name": "clean/tilt-clean.jpg"})
    assert page.status_code == 200 and "tilt-clean.jpg" in page.text
    assert client.get("/edit/preview",
                      params={"name": "clean/tilt-clean.jpg", "ops": '[["exposure",0.2]]'}
                      ).status_code == 200


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
    assert "Reshape" in page.text, "the studio must offer the mesh brush it claims to have"
    shot = client.get("/edit/preview", params={"name": "sharp.png",
                                               "ops": json.dumps([["exposure", 0.6],
                                                                  ["heal", 0.5, 0.5, 0.04]])})
    assert shot.status_code == 200
    assert shot.headers["content-type"] == "image/jpeg"


def test_the_page_is_told_where_the_strength_control_really_stops(tmp_path):
    """The slider ends on the number this route hands back, so it must be the same ceiling
    the engine applies to the stroke - and the page needs the slot to say it out loud."""
    from PIL import Image
    from src.media.retouch import reach

    client = _inbox_client(tmp_path)
    vals = [0.5, 0.5, 0.22, -3.0, 0.0, 0.55, 0.0, 2.6]
    got = client.get("/edit/reach", params={"name": "sharp.png", "op": "slim",
                                            "vals": json.dumps(vals)})
    assert got.status_code == 200
    with Image.open(tmp_path / "inbox" / "sharp.png") as handle:
        w, h = handle.size
    assert got.json()["max"] == pytest.approx(reach(vals, "slim", w, h), abs=0.005)
    assert "capnote" in client.get("/edit?name=sharp.png").text, \
        "the editor has nowhere to say where the brush stops"
    ungoverned = client.get("/edit/reach", params={"name": "sharp.png", "op": "exposure",
                                                   "vals": "[0.4]"})
    assert ungoverned.json()["max"] is None, "a control with no ceiling must not invent one"
    junk = client.get("/edit/reach", params={"name": "sharp.png", "op": "slim",
                                             "vals": "not json"})
    assert junk.json()["max"] is None
    assert client.get("/edit/reach", params={"name": "nope.png", "op": "slim",
                                             "vals": "[]"}).status_code == 404


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
    assert "not built" not in body, "the research layer exists; the coach must not claim otherwise"


def test_the_coach_shows_the_dated_sources_behind_the_current_slots(planned):
    body = planned.get("/weekly").text
    assert "checked 2026-" in body, "every claim the slots rest on carries its own date"
    assert re.search(r'<a href="https://[^"]+">[^<]+</a> \(', body), "and where it was checked"


def test_the_coach_costs_nothing_and_says_so(planned):
    body = planned.get("/weekly").text
    assert "0 model calls on record" in body and "all local CPU" in body


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


COMMENTS = ("maria: what pants are those?\n"
            "jules: obsessed with this fit\n"
            "check my page for free followers\n"
            "lee: this is so cringe")


def test_the_engage_page_is_empty_and_says_how_to_fill_it(planned):
    page = planned.get("/engage").text
    assert "Nothing pasted yet" in page
    assert "will not reply for you" in page
    assert "It will not invent the middle of a sentence" in page


def test_pasting_comments_gives_drafts_with_the_answer_left_blank(planned):
    page = planned.post("/engage/read", data={"comments": COMMENTS}).text
    assert "____" in page, "the price and the sizing stay hers"
    assert "refused" in page and "No reply, on purpose" in page
    assert "4 comments read, 3 worth a reply, 1 refused" in page
    assert "3 replies drafted" in page and "Nothing was sent" in page


def test_the_queue_starts_with_the_replies_that_convert(planned):
    planned.post("/engage/read", data={"comments": COMMENTS})
    page = planned.get("/engage").text
    order = [i for i in ("demand", "question", "praise", "criticism") if f'>{i}<' in page]
    assert order[0] == "demand", "the price question is the one that turns into a follow"


def test_the_reply_tick_is_kept_between_visits(planned):
    planned.post("/engage/read", data={"comments": COMMENTS, "bio": "", "targets": ""})
    key = "jules|obsessed with this fit"
    assert f'value="{key}"' in planned.get("/engage").text, "every draft carries its own handle"
    planned.post("/engage/replied", data={"key": key})
    stored = planned.app.state.db.get_engage()
    assert stored["replied"] == [key], "a tick is her list, not a platform action"
    assert "Re-mark as not replied" in planned.get("/engage").text
    planned.post("/engage/replied", data={"key": key})
    assert planned.app.state.db.get_engage()["replied"] == []


def test_the_bio_is_read_back_with_the_rules_it_applied(planned):
    planned.post("/engage/read", data={"comments": "", "targets": "",
                                       "bio": "outfits | link in bio | shop my store"})
    page = planned.get("/engage").text
    assert "2 calls to action found" in page
    assert "Nobody is named" in page
    assert "80" in page, "the real per-platform limits, not one vague length rule"


def test_the_watch_list_is_hers_with_the_detail_left_hers(planned):
    planned.post("/engage/read", data={"comments": "", "bio": "",
                                       "targets": "noor: she posted a rack of thrifted blazers"})
    page = planned.get("/engage").text
    assert "Fifteen minutes" in page and "noor" in page
    assert "not accounts the app found" in page.lower()


def test_the_follow_ups_come_from_the_post_she_actually_measured(planned):
    planned.post("/numbers", data={"quick": "clip-0042 1200 41 3\nclip-0099 900 12 1\n"})
    planned.post("/engage/read", data={"comments": "", "targets": "", "bio": ""})
    page = planned.get("/engage").text
    assert "part two" in page and "clip-0042" in page
    assert "is under the 8 this app needs" in page, "one winner is not a pattern yet"


def test_the_trends_page_shows_findings_with_their_age_and_address(planned):
    body = planned.get("/trends").text
    assert "as of 2026-" in body, "a finding without a date is just an opinion"
    assert re.search(r"(dated today|day old|days old|weeks old|months old)", body)
    assert "does not establish" in body.lower()
    assert re.search(r'<a href="https://[^"]+">[^<]+</a> <span class="chip">', body), \
        "each finding links what it was read at"


def test_the_trends_page_never_claims_a_live_trend_it_cannot_show(planned):
    body = planned.get("/trends").text
    live = "still standing" in body
    empty = "No trend research is live" in body
    assert live != empty, "exactly one of the two states is true on any given day"


def test_the_research_brief_is_paste_ready_and_holds_no_address(planned):
    body = planned.get("/trends").text
    block = re.search(r'id="brief"[^>]*>(.*?)</textarea>', body, re.S).group(1)
    assert "Run the trend research" in block
    assert "Do not give me a hashtag list." in block
    assert "http" not in block, "the app fetches nothing, so it hands over no URLs of its own"


def test_the_trends_page_states_its_own_limits(planned):
    body = planned.get("/trends").text
    assert "no browser" in body
    assert "posting time" in body


def test_the_today_page_names_no_window_while_it_is_still_guessing(planned):
    body = planned.get("/today").text
    assert "window you can hold for three weeks" in body
    assert "myth-best-time-to-post-chart" in body
    assert "20 more posts with a clock time on it" in body


def test_twenty_timed_posts_replace_the_default_with_her_own_windows(planned):
    lines = [f"clip-{i:02d} {900 + i} 41 3 19:40" for i in range(10)]
    lines += [f"clip-{i:02d}m {300 + i} 22 1 09:10" for i in range(10)]
    planned.post("/numbers", data={"quick": "\n".join(lines)})
    body = planned.get("/today").text
    assert "Replaced at 20 timed posts" in body, "the hour has to survive the round trip"
    assert "<th>Median views</th>" in body
    assert "evening against morning" in body
    assert "myth-best-time-to-post-chart" not in body, "the vendor refusal is the default, not the answer"


PARTS = ["placement", "level", "breathing", "palette", "focus"]


def _scored(planned, n=8, follows=None):
    """Files this app scored before she posted, plus the numbers their audiences left. The
    reference is the file name, because that is the only key the two sides share."""
    follows = follows or (lambda i: i + 1)
    for i in range(n):
        planned.app.state.db.save_score(
            f"p{i}", "photo", round(4 + i * 0.5, 1),
            "strong" if 4 + i * 0.5 >= 7 else "workable", {c: 0.5 for c in PARTS}, "2026-11-01")
    return "\n".join(f"p{i} {500 + i * 50} {20 + i} {follows(i)}" for i in range(n))


def test_the_numbers_page_compares_taste_with_receipts(planned):
    body = planned.post("/numbers", data={"quick": _scored(planned)}).text
    assert "carry both halves of the loop" in body
    assert "what this app liked" in body and "what it scored lower" in body
    assert "reshuffles of your own numbers" in body, "the size of the link is tested, not reported"


def test_below_the_pairing_floor_the_page_names_the_number_it_wants(planned):
    body = planned.post("/numbers", data={"quick": _scored(planned, 3)}).text
    assert "8 paired posts is the floor this page will speak at" in body
    assert "5 more" in body
    assert "nothing here guesses it for you" in body


def test_without_any_scores_the_loop_says_so_rather_than_blaming_planned(planned):
    body = planned.post("/numbers", data={"quick": "p1 900 30 4"}).text
    assert "Nothing scored yet" in body


def test_a_rubric_the_audience_disagrees_with_is_put_on_the_page(planned):
    body = planned.post("/numbers", data={"quick": _scored(planned, follows=lambda i: 30 - 3 * i)}).text
    assert "not buying what the rubric rewards" in body
    assert "paid less attention" in body


def test_a_reweight_is_a_proposal_until_she_presses_it(planned):
    parts = [{"placement": round(i / 7, 3), "level": round((7 - i) / 7, 3),
              "breathing": 0.5, "palette": 0.5, "focus": 0.5} for i in range(14)]
    for i, p in enumerate(parts):
        planned.app.state.db.save_score(f"p{i}", "photo", round(4 + i * 0.4, 1), "workable",
                                        p, "2026-11-01")
    lines = "\n".join(f"p{i} {500 + i * 50} {20 + i} {i + 1}" for i in range(14))
    body = planned.post("/numbers", data={"quick": lines}).text
    assert "Accept these weights" in body and "placement" in body
    assert "the opinion this app shipped with" in body, "nothing has moved yet"

    after = planned.post("/numbers/reweight").text
    assert "accepted from your own numbers" in after
    assert "Reset to the shipped weights" in after
    weights = planned.app.state.db.get_rubric()
    assert sum(weights.values()) == 1.0 and weights["placement"] > weights["level"]

    back = planned.post("/numbers/reset").text
    assert "the opinion this app shipped with" in back
    assert planned.app.state.db.get_rubric() is None


def test_accepting_without_a_live_proposal_changes_nothing(planned):
    body = planned.post("/numbers/reweight").text
    assert "There was nothing to accept" in body
    assert planned.app.state.db.get_rubric() is None


def test_credits_are_hers_to_state_and_hers_to_leave_empty(planned):
    body = planned.post("/numbers/credits", data={"credits": "12", "what_for": "3 cut edits"}).text
    assert "12 credits" in body and "Self-reported by you" in body
    cleared = planned.post("/numbers/credits", data={"credits": ""}).text
    assert "empty cell beats an invented zero" in cleared
    assert "not stated" in cleared


def test_the_model_quota_column_is_a_count_not_a_promise(planned):
    planned.app.state.db.add_model_call()
    planned.app.state.db.add_model_call()
    body = planned.post("/numbers", data={"quick": _scored(planned, 4)}).text
    assert "2 calls" in body and "Counted here" in body
    assert "0 model calls on record" not in planned.get("/weekly").text


def test_local_work_is_listed_and_refused_the_status_of_a_cost(planned):
    body = planned.get("/numbers").text
    assert "All local CPU" in body and "not a currency" in body
    assert "no posts to divide" in body, "nothing divides before there are posts"


def test_photos_writes_the_score_the_feedback_loop_needs(tmp_path):
    client = _inbox_client(tmp_path)
    client.get("/photos")
    stored = client.app.state.db.get_scores()
    assert "sharp" in stored, "the file name without its extension is the key she will type"
    assert len(stored["sharp"]["parts"]) == 5, "every component has to outlive the page"


def test_saving_an_edit_leaves_a_provenance_log_behind(tmp_path):
    client = _inbox_client(tmp_path)
    client.post("/edit/save", data={"name": "sharp.png",
                                    "recipe": json.dumps([["exposure", 0.2], ["contrast", 0.3]])})
    ops = client.app.state.db.edit_ops()
    assert [o["op"] for o in ops] == ["exposure", "contrast"], "the log answers the AI question"
    assert all(o["params"] and o["before_sha"] and o["after_sha"] for o in ops)
