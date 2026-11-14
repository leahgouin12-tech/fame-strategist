"""The whole HTTP surface: one create_app(), every route she clicks, in one file.

The interview, /niches, the plan, /today, /weekly, /write, /engage, /graph, /trends,
/sources, /numbers, the photo and clip rails, /edit, /face, /bench, /story, /accounts,
/agent, /engine and /phone are all declared inside create_app, and every
screen answers through page(), which attaches DISCLAIMER, the engine name, the offline
flag and the playbook counts instead of trusting each template to remember them. The
same file owns the phone_door middleware: the laptop always sees its own app, another
machine gets in only past her PIN, and /static stays open because the PIN box has to
look like the app to be believed.

Nothing here logs into an account, schedules a post or calls a platform's API -
/accounts hands back a link and the tap is hers. Importing the module runs create_app()
at the bottom of the file, so config.toml and data/app.sqlite3 are read at import time,
and /engine/save can swap the Live engine every handler already holds without
rebuilding anything.
"""

from datetime import date, timedelta
from pathlib import Path
import hashlib
import io
import json
import re
import shutil
import time
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from src import net
from src import accounts
from src.agent import modes as agent_modes
from src.agent import orchestrator, tools as agent_tools
from src.agent import roster as agent_roster
from src.agent.tools import Kit
from src.config import DEFAULT_MODEL, Config
from src.db import DB
from src.engines.base import Live
from src.engines.offline import OfflineEngine
from src.media import clip as clipmod
from src.media import layers
from src.media import story
from src.media.clipjudge import CLIP_LABELS, CLIP_WEIGHTS, judge_clip, suggest
from src.experiment import ledger as experiment
from src.experiment import repurpose
from src.metrics import churn
from src.metrics import correlate
from src.metrics import spend as spendmod
from src.metrics import bench as benchmod
from src.money import rate as money
from src.registry import audit as regaudit
from src.metrics.adapt import DATA_FLOOR, analyse, apply
from src.metrics.ingest import read_csv, read_quick
from src.media.aesthetic import WEIGHTS, judge_photo
from src.media.appearance import CONTRACT as FACE_CONTRACT
from src.media.appearance import read_file as read_face
from src.media.clean import fix
from src.media.edit import (ARITY, PRESETS, RAILS, RAIL_TOOLS, SAVE_QUALITY, SLIDERS, TITLES,
                            edit_file, normalize, tools_json)
from src.media.judge import IMAGE_SUFFIXES, inbox_files, judge, measure
from src.playbook import live, research
from src.playbook.store import Store
from src.strategist.coach import CADENCE_DAYS, _week_at, build_agenda
from src.strategist.daily import build_day, subject_of
from src.strategist.interview import Interview, InterviewAnswers
from src.strategist.niche import brief, rank, score_candidates
from src.strategist import slots
from src.strategist.plan import Plan, compose_plan
from src.strategist import engage, voice

ROOT = Path(__file__).resolve().parent.parent
PLAYBOOK_DIR = ROOT / "data" / "playbook"
DATA_DIR = ROOT / "data"

DISCLAIMER = (
    "This cannot promise growth, followers, or reach. It states what is documented, what is "
    "contested, and what nobody has measured - then plans around your own numbers."
)


def load_playbook():
    entries = Store().load(PLAYBOOK_DIR, allow_pending=True)
    pending = [e.id for e in entries if e.has_placeholder_source()]
    return entries, pending


def iso_or_today(raw) -> str:
    """A date is how she asks for another day, not a way to make the page fall over."""
    try:
        return date.fromisoformat(str(raw)).isoformat()
    except (TypeError, ValueError):
        return date.today().isoformat()


def parse_answers(form) -> InterviewAnswers:
    def flag(name):
        return form.get(name) in ("on", "true", "1")

    followers = form.get("existing_followers", "")
    return InterviewAnswers(
        hours_per_week=int(form.get("hours_per_week", 0) or 0),
        on_camera=flag("on_camera"),
        has_clips=flag("has_clips"),
        gear=form.get("gear", ""),
        platforms=list(form.getlist("platforms")),
        comfort=list(form.getlist("comfort")),
        existing_followers=int(followers) if str(followers).strip() != "" else 0,
        what_you_actually_film=form.get("what_you_actually_film", ""),
    )


def create_app(config: Config | None = None, db_path: Path | None = None) -> FastAPI:
    config = config or Config.load()
    # Live is the indirection that lets the engine page change the model while the app
    # is running. Every call site holds the Live object and never has to be rebuilt.
    engine = Live(config.build_engine())
    db = DB(db_path or DATA_DIR / "app.sqlite3")
    state_dir = Path(db_path or DATA_DIR / "app.sqlite3").parent
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    app = FastAPI(title="Fame Strategist", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    inbox_dir = state_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    layers.ROOT = inbox_dir       # the only folder a second-photo layer may reach into
    app.mount("/inbox", StaticFiles(directory=str(inbox_dir)), name="inbox")
    app.state.engine = engine
    app.state.db = db
    app.state.config = config
    gate = net.PhoneGate(state_dir / "phone.json")
    app.state.gate = gate

    def from_phone(request: Request) -> bool:
        """Whether this request arrived from another machine at all."""
        return net.is_foreign(request.client.host if request.client else "")

    @app.middleware("http")
    async def phone_door(request: Request, call_next):
        """The laptop always sees its own app. A phone gets in only after it answers with her
        PIN, and until she sets one the door is shut from the outside - a wifi adapter is
        somebody else's network too, so opening it is her decision, not a side effect.

        /static stays open because the PIN box has to look like the app to be believed, and
        there is nothing in it worth stealing. Everything holding her files or her numbers is
        behind the cookie.
        """
        path = request.url.path
        if (not from_phone(request) or path.startswith("/static")
                or path in ("/phone/unlock", "/favicon.ico")):
            return await call_next(request)
        if gate.accepts(request.cookies.get(net.COOKIE, "")):
            return await call_next(request)
        blocked = templates.TemplateResponse(
            request, "gate.html",
            {"has_pin": gate.has_pin(), "back": path,
             "status": gate.status(), "note": "", "local": False}, status_code=401)
        return blocked

    def page(request, template, **ctx):
        """Every screen goes through here. The template argument is deliberately not called
        `name`, because half the pages pass a context key called `name` (the file she picked)
        and a positional parameter with that spelling swallows it before the call starts."""
        entries, pending = load_playbook()
        return templates.TemplateResponse(
            request,
            template,
            {
                "active": template.removesuffix(".html"),
                "engine_name": engine.name,
                "offline": engine.name == "offline",
                "disclaimer": DISCLAIMER,
                "entry_count": len(entries),
                "pending_count": len(pending),
                **ctx,
            },
        )

    def plan_or_none():
        raw = db.get_current_plan()
        return Plan.from_dict(raw) if raw else None

    def dropped_arms():
        """The hypotheses a lab verdict has already put out of the running, so rebuilding
        the eight weeks cannot quietly schedule a dropped arm as if it were new."""
        return experiment.dropped(db.recall("verdict", limit=50))

    def metrics_rows():
        """The last import, or nothing. An unreadable file is no data, not a broken page."""
        path = state_dir / "metrics-last.csv"
        if not path.is_file():
            return []
        try:
            return read_csv(path)
        except ValueError:
            return []

    def rubric_weights():
        """The shipped opinion, unless she has accepted a change from her own numbers."""
        return db.get_rubric() or WEIGHTS

    def remember(src: Path, kind: str, judged) -> None:
        """Spec 5.9 only works if the judgement written before posting outlives the day it
        was posted, so every score this app displays is also stored under its file name."""
        reading = getattr(judged, "reading", None)
        if reading is not None and reading.error:
            return
        parts = {c.name: round(c.score, 3) for c in getattr(judged, "components", [])}
        if not parts:
            return
        db.save_score(correlate.stem(src.stem), kind, judged.score, judged.band, parts,
                      date.today().isoformat())

    def day_for(answers, plan, day: date):
        d = build_day(plan, load_playbook()[0], answers, day, engine)
        if d.copy_origin == "model":
            db.add_model_call()
        return d

    def interview_view(answers=None, form=None):
        v = {
            "hours_per_week": "", "existing_followers": "", "what_you_actually_film": "",
            "gear": "phone", "has_clips": False, "on_camera": False, "platforms": [], "comfort": [],
        }
        if answers is not None:
            for key in v:
                v[key] = getattr(answers, key)
        if form is not None:
            try:
                a = parse_answers(form)
            except (ValueError, TypeError):
                return v
            v.update({"hours_per_week": a.hours_per_week, "existing_followers": a.existing_followers,
                      "what_you_actually_film": a.what_you_actually_film, "gear": a.gear,
                      "has_clips": a.has_clips, "on_camera": a.on_camera,
                      "platforms": a.platforms, "comfort": a.comfort})
        return v

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        answers = db.get_interview()
        plan = plan_or_none()
        today = build_day(plan, load_playbook()[0], answers, date.today(), engine) if plan and answers and Interview.complete(answers) else None
        return page(
            request, "home.html",
            has_interview=answers is not None and Interview.complete(answers),
            assumptions=Interview.assumptions(Interview.defaults()),
            plan=plan, today=today,
            inbox=str(inbox_dir), photo_count=len(inbox_files(inbox_dir)),
            posted_days=len([d for d in db.get_days("0000-01-01", "9999-12-31") if d["done"]]),
            next_step=("Take the interview" if not answers or not Interview.complete(answers)
                       else "Build the plan" if plan is None else "Open today"),
        )

    @app.post("/start", response_class=HTMLResponse)
    async def start(request: Request):
        """One click: adopt the stated assumptions, rank niches, build the 8 weeks,
        land on today. Nothing here is a secret - the card that offered it listed them."""
        form = await request.form()
        footage = str(form.get("what_you_actually_film", "") or "")
        answers = Interview.defaults(footage)
        db.save_interview(answers)
        entries, _pending = load_playbook()
        hypotheses = rank(score_candidates(entries, answers))
        plan = compose_plan(entries, answers, hypotheses, OfflineEngine(), date.today(),
                            dropped=dropped_arms())
        db.save_current_plan(plan.to_dict())
        return today(request)

    @app.get("/interview", response_class=HTMLResponse)
    def interview_form(request: Request):
        return page(request, "interview.html", v=interview_view(db.get_interview()), need=[])

    @app.post("/interview", response_class=HTMLResponse)
    async def interview_save(request: Request):
        form = await request.form()
        try:
            answers = parse_answers(form)
        except (ValueError, TypeError) as exc:
            return page(request, "interview.html", v=interview_view(), need=[str(exc)])
        need = Interview.checklist(answers)
        if need:
            return page(request, "interview.html", v=interview_view(form=form), need=need)
        db.save_interview(answers)
        return niches(request)

    @app.get("/niches", response_class=HTMLResponse)
    def niches(request: Request):
        answers = db.get_interview()
        if not answers or not Interview.complete(answers):
            return page(request, "interview.html", v=interview_view(),
                        need=["take the interview first"])
        entries, _pending = load_playbook()
        hypotheses = rank(score_candidates(entries, answers))
        return page(
            request, "niches.html", answers=answers, hypotheses=hypotheses,
            briefs=[brief(h) for h in hypotheses], chosen=None,
        )

    @app.post("/plan/build", response_class=HTMLResponse)
    def build_plan(request: Request):
        answers = db.get_interview()
        entries, _pending = load_playbook()
        hypotheses = rank(score_candidates(entries, answers))
        plan = compose_plan(entries, answers, hypotheses, OfflineEngine(), date.today(),
                            dropped=dropped_arms())
        db.save_current_plan(plan.to_dict())
        return page(request, "plan.html", plan=plan, entries=entries)

    @app.get("/plan", response_class=HTMLResponse)
    def show_plan(request: Request):
        plan = plan_or_none()
        if plan is None:
            return niches(request)
        return page(request, "plan.html", plan=plan, entries=load_playbook()[0])

    def day_payload(iso: str) -> dict:
        """A day is one JSON payload and save_day replaces it whole, so anything writing
        one piece of it reads the rest back first - or the pieces erase each other."""
        logged = db.get_days(iso, iso)
        return {k: v for k, v in (logged[0] if logged else {}).items()
                if k not in ("date", "done")}

    def postable_media() -> list[dict]:
        """What she could actually be posting today, straight out of the two folders the
        app writes to. Relative to their own root, which is what the guards resolve."""
        out = []
        for rel_root, folder, kind, suffixes in [
            ("", inbox_dir, "photo", IMAGE_SUFFIXES),
            ("edited/", edited_dir, "photo", IMAGE_SUFFIXES),
            ("", clips_dir, "clip", clipmod.VIDEO_SUFFIXES),
            ("edited/", clips_edited, "clip", clipmod.VIDEO_SUFFIXES),
        ]:
            if not folder.is_dir():
                continue
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix.lower() in suffixes:
                    out.append({"rel": rel_root + p.name, "kind": kind})
        return out

    @app.get("/today", response_class=HTMLResponse)
    def today(request: Request, on: str | None = None, note: str = ""):
        answers, plan = db.get_interview(), plan_or_none()
        if not answers or not plan:
            return home(request)
        day = date.fromisoformat(iso_or_today(on))
        d = day_for(answers, plan, day)
        logged = db.get_days(day.isoformat(), day.isoformat())
        return page(request, "today.html", today=d, plan=plan, answers=answers,
                    posted=bool(logged and logged[0]["done"]), day_iso=day.isoformat(),
                    attached=(logged[0].get("attach") if logged else None),
                    slot_report=slots.report(metrics_rows()),
                    postables=postable_media(), note=note)

    @app.post("/today/attach", response_class=HTMLResponse)
    def today_attach(request: Request, on: str = Form(""), file: str = Form("")):
        on = iso_or_today(on)
        wanted = file.strip()
        payload = day_payload(on)
        if not wanted:
            payload.pop("attach", None)
            db.save_day(on, payload)
            return today(request, on=on)
        found = None
        for root, finder, as_kind, suffixes in (
                (inbox_dir, inbox_file, "photo", IMAGE_SUFFIXES),
                (clips_dir, clip_file, "clip", clipmod.VIDEO_SUFFIXES)):
            hit = finder(wanted)
            if hit is not None and hit.suffix.lower() in suffixes:
                found = (hit, as_kind, root)
                break
        if found is None:
            return today(request, on=on,
                         note=f"{wanted} is not in your folders - pick from the list, or drop "
                              "the file into an inbox or clips folder first.")
        src, kind, root = found
        # The resolved path, not what was typed: this string comes back out of the row and
        # into an <img src>, so it is normalised once here rather than trusted twice later.
        rel = str(src.relative_to(root)).replace("\\", "/")
        payload["attach"] = {"file": rel, "kind": kind}
        db.save_day(on, payload)
        return today(request, on=on, note=f"{rel} is now tied to this day.")

    @app.post("/today/done", response_class=HTMLResponse)
    def today_done(request: Request, on: str = Form("")):
        on = iso_or_today(on)
        payload = day_payload(on)
        payload["posted"] = True
        db.save_day(on, payload)
        db.mark_done(on)
        return today(request, on=on)

    def frames_landed(start: date, end: date):
        """Frames that arrived inside the window, and the ones this app's own judge calls
        weak. Scored here on this CPU, from the two folders the editor writes to."""
        landed, weak = [], []
        for folder, root in ((inbox_dir, ""), (edited_dir, "edited/")):
            if not folder.is_dir():
                continue
            for p in sorted(folder.iterdir()):
                if not p.is_file() or p.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                if not start <= date.fromtimestamp(p.stat().st_mtime) <= end:
                    continue
                landed.append(root + p.name)
                reading = measure(p)
                if not reading.error and judge_photo(p, reading).band == "weak":
                    weak.append(root + p.name)
        return landed, weak

    @app.get("/weekly", response_class=HTMLResponse)
    def weekly(request: Request):
        """Spec 5.11. The coach reads receipts and brings proposals; it has no hands."""
        plan = plan_or_none()
        if plan is None:
            return page(request, "weekly.html", agenda=None, plan=None)
        end = date.today()
        start = end - timedelta(days=CADENCE_DAYS - 1)
        rows = metrics_rows()
        landed, weak = frames_landed(start, end)
        agenda = build_agenda(
            plan=plan, days=db.get_days(start.isoformat(), end.isoformat()), rows=rows,
            landed=landed, weak=weak, entries=load_playbook()[0], today=end,
            engine_name=engine.name, offline=engine.name == "offline",
            spend=db.get_spend())
        return page(request, "weekly.html", agenda=agenda, plan=plan)

    @app.get("/write", response_class=HTMLResponse)
    def writer(request: Request, note: str = ""):
        """Spec 5.6: the voice comes from what she pasted, never from a persona, and no
        sample ever leaves this machine because the writer makes no call."""
        answers, plan = db.get_interview(), plan_or_none()
        samples = db.get_voice()
        profile = voice.learn(samples)
        pasted = "\n\n".join(samples)
        if not answers or not plan or not Interview.complete(answers):
            return page(request, "write.html", profile=profile, variants=[], day=None,
                        samples_text=pasted,
                        note=note or "The writer cuts today&rsquo;s line into three platforms. "
                                     "It needs the interview and a plan before it has a line.")
        day = day_for(answers, plan, date.today())
        variants = voice.package(subject_of(answers), day.hypothesis, date.today(), profile)
        return page(request, "write.html", profile=profile, variants=variants, day=day,
                    samples_text=pasted, note=note)

    @app.post("/write/samples", response_class=HTMLResponse)
    async def writer_samples(request: Request):
        form = await request.form()
        blocks = [b.strip() for b in re.split(r"\n\s*\n", str(form.get("samples", "") or ""))
                  if b.strip()]
        db.save_voice(blocks)
        note = (f"Learned from {len(blocks)} thing{'s' if len(blocks) != 1 else ''} you "
                "actually wrote." if blocks else
                "Cleared. The writer is back to guessing, and it will say so on every line.")
        return RedirectResponse(f"/write?note={quote(note)}", status_code=303)

    @app.get("/engage", response_class=HTMLResponse)
    def engage_page(request: Request, note: str = ""):
        """Spec 5.13. The app takes the labour out of a reply and leaves the reply's facts to
        the person who knows them: drafts only, no login, nothing sent from here."""
        store = db.get_engage()
        profile = voice.learn(db.get_voice())
        drafts = engage.plan(engage.parse(store["comments"]), profile)
        for d in drafts:
            d.replied = d.key in set(store["replied"])
        rows = metrics_rows()
        best = None
        if rows:
            top = max(rows, key=lambda r: r.follow_rate_per_1000)
            best = {"post_ref": top.post_ref, "hypothesis": top.hypothesis,
                    "views": top.views}
        return page(
            request, "engage.html", profile=profile, drafts=drafts,
            queue=engage.queue_note(drafts), watch=engage.watch_rows(store["targets"], profile),
            series=engage.series_rows(best, profile) if best else [], best=best,
            checks=engage.bio_review(store["bio"]), posts=len(rows), floor=DATA_FLOOR,
            comments=store["comments"], targets=store["targets"], bio=store["bio"],
            note=note,
        )

    @app.post("/engage/read", response_class=HTMLResponse)
    async def engage_read(request: Request):
        form = await request.form()
        store = db.get_engage()
        for field in ("comments", "targets", "bio"):
            store[field] = str(form.get(field, "") or "")
        db.save_engage(store)
        worth = len([d for d in engage.plan(engage.parse(store["comments"]),
                                            voice.learn(db.get_voice())) if not d.refused])
        note = (f"Read here, on this machine: {worth} "
                f"{'reply' if worth == 1 else 'replies'} drafted. "
                "Nothing was sent, scheduled or logged into anywhere.")
        return RedirectResponse(f"/engage?note={quote(note)}", status_code=303)

    @app.post("/engage/replied", response_class=HTMLResponse)
    def engage_replied(key: str = Form("")):
        """A tick on her list, not a platform action - the app cannot see her inbox."""
        store = db.get_engage()
        marked = set(store["replied"])
        if key in marked:
            marked.remove(key)
        else:
            marked.add(key)
        store["replied"] = sorted(marked)
        db.save_engage(store)
        return RedirectResponse("/engage", status_code=303)

    @app.get("/graph", response_class=HTMLResponse)
    def graph(request: Request, note: str = ""):
        """Spec 5.12. Two official exports, one honest diff: who left, between which dates,
        and what the ledger says she was posting in that window. Insight, never action."""
        stored = db.get_graph()
        snaps = [churn.Snapshot(taken=s["taken"], source=s["source"], names=tuple(s["names"]),
                                added=s.get("added", {})) for s in stored]
        report = churn.churn_report(snaps, db.get_days("0001-01-01", "9999-12-31"))
        return page(request, "graph.html", report=report, stored=stored,
                    today=date.today().isoformat(), note=note)

    @app.post("/graph/read", response_class=HTMLResponse)
    async def graph_read(request: Request):
        form = await request.form()
        taken = iso_or_today(str(form.get("taken", "") or ""))
        source = str(form.get("source", "") or "pasted")[:40]
        upload = form.get("file")
        text = str(form.get("paste", "") or "")
        # Duck-typed on purpose: a multipart field comes back as Starlette's own UploadFile,
        # which is not an instance of the subclass FastAPI exports.
        if getattr(upload, "filename", ""):
            source = upload.filename.replace("\\", "/").rsplit("/", 1)[-1][:40]
            text = (await upload.read()).decode("utf-8", "replace")
        snap = churn.parse_export(text, taken=taken, source=source)
        if snap.error:
            return RedirectResponse(f"/graph?note={quote(snap.error)}", status_code=303)
        stored = db.get_graph() + [{"taken": snap.taken, "source": snap.source,
                                    "names": list(snap.names), "added": snap.added}]
        db.save_graph(stored[-12:])
        note = (f"{len(snap.names)} names read from {source} as the {taken} snapshot. "
                "Nothing was fetched and no account was touched.")
        return RedirectResponse(f"/graph?note={quote(note)}", status_code=303)

    @app.post("/graph/forget", response_class=HTMLResponse)
    def graph_forget():
        db.save_graph([])
        cleared = "Every handle forgotten. The diff is empty until you upload an export again."
        return RedirectResponse(f"/graph?note={quote(cleared)}", status_code=303)

    @app.get("/trends", response_class=HTMLResponse)
    def trends(request: Request, note: str = ""):
        """Spec 5.10: dated findings, or the plain statement that no research is live.

        The app fetches nothing, so a finding is only ever something an agent opened and wrote
        into the playbook with a date on it. The age is the product here, not a footnote.
        """
        plan = plan_or_none()
        entries, _pending = load_playbook()
        week = _week_at(plan, date.today()) if plan else None
        result = research.run(entries, date.today(), week.focus_entry_ids if week else ())
        answers = db.get_interview()
        the_brief = research.brief(
            platforms=getattr(answers, "platforms", []) or [],
            hypotheses=plan.hypotheses if plan else [],
            chosen=week.experiment if week else "",
            hours_per_week=getattr(answers, "hours_per_week", 0) or 0,
        )
        leads = live.load(db)
        return page(request, "trends.html", run=result, brief_text=the_brief, plan=plan,
                    week=week, library=len(entries), leads=leads,
                    lead_note=live.note(leads, live.ran(db)), note=note)

    @app.post("/trends/leads", response_class=HTMLResponse)
    async def trends_leads(request: Request):
        """Ask the model what it thinks is rising, and keep the answer out of the playbook.

        The playbook is citation-gated and that gate is the point: a model's recollection has no
        address on it, so it lands in the notes table labelled as what it is instead of becoming
        a finding. An ask that fails is reported as failed; nothing is invented to fill the page.
        """
        form = await request.form()
        if str(form.get("forget", "")) == "1":
            ids = [row["id"] for kind in (live.LEAD_KIND, *live.LEAD_PARTS, live.LEAD_RUN)
                   for row in db.recall(kind, limit=200)]
            for note_id in ids:
                db.forget(note_id)
            return RedirectResponse("/trends?note=" + quote(
                "Every lead cleared. The findings above are untouched - those have sources."),
                status_code=303)
        if engine.name == "offline":
            return RedirectResponse("/trends?note=" + quote(
                "There is nothing to ask. The machine page is where an engine key goes; until "
                "then this page only shows what somebody published."), status_code=303)
        plan = plan_or_none()
        week = _week_at(plan, date.today()) if plan else None
        answers = db.get_interview()
        try:
            found = live.ask(engine,
                             platforms=getattr(answers, "platforms", []) or [],
                             hypotheses=plan.hypotheses if plan else [],
                             chosen=week.experiment if week else "")
        except Exception as exc:
            return RedirectResponse("/trends?note=" + quote(
                f"The ask did not come back ({type(exc).__name__}). Nothing was saved and "
                "nothing was made up in its place."), status_code=303)
        live.save(db, found)
        return RedirectResponse("/trends?note=" + quote(
            f"{len(found)} lead{'' if len(found) == 1 else 's'} from {engine.name}, written down "
            "as a model's opinion. They are not findings and they did not enter the playbook."
            if found else f"{engine.name} was asked and defended nothing. That is recorded too."),
            status_code=303)

    @app.get("/sources", response_class=HTMLResponse)
    def sources(request: Request, tier: str | None = None):
        entries, pending = load_playbook()
        counts = {t: len([e for e in entries if e.confidence.value == t])
                  for t in ["proven", "strong", "contested", "folklore"]}
        shown = [e for e in entries if e.confidence.value == tier] if tier in counts else entries
        return page(request, "sources.html", entries=shown, all_entries=entries, pending=pending,
                    counts=counts, tier=tier)

    def store_rows(rows) -> None:
        """Normalised to the app's own CSV so the apply step re-reads exactly what was read now.
        The platform column rides along: an import that named its platforms and then went
        through a re-save must not come back as one anonymous median."""
        state_dir.mkdir(exist_ok=True)
        lines = ["platform,post_ref,views,avg_watch_pct,follows_gained,hypothesis,posted_at"]
        lines += [
            f"{getattr(r, 'platform', '') or ''},{r.post_ref},{r.views},{r.avg_watch_pct},"
            f"{r.follows_gained},{r.hypothesis},"
            f"{'' if r.posted_hour is None else r.posted_hour}"
            for r in rows
        ]
        (state_dir / "metrics-last.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def numbers_page(request, rows=None, note=""):
        plan = plan_or_none()
        stored = rows if rows is not None else metrics_rows()
        scores = db.get_scores()
        spent = db.get_spend()
        return page(
            request, "numbers.html",
            adjustments=analyse(stored, plan) if (plan and rows is not None) else [],
            plan=plan, note=note, rows=rows or [],
            report=correlate.report(scores, stored, rubric_weights()),
            cost=spendmod.tally(spend=spent, ops=db.edit_ops(), judged=len(scores),
                                 posts=len(stored), engine_name=engine.name,
                                 offline=engine.name == "offline"),
            credits=("" if spent.get("credits") is None else spent["credits"]),
            credits_note=spent.get("credits_note") or "",
            weights=rubric_weights(), custom=db.get_rubric() is not None,
        )

    @app.get("/numbers", response_class=HTMLResponse)
    def numbers(request: Request):
        return numbers_page(request)

    @app.post("/numbers/credits", response_class=HTMLResponse)
    async def numbers_credits(request: Request):
        """The credits column is hers, because nothing in this app can read a Qoder balance."""
        form = await request.form()
        raw = str(form.get("credits", "") or "").strip()
        spent = db.get_spend()
        if not raw:
            db.save_spend({**spent, "credits": None, "credits_note": ""})
            return numbers_page(request, note="Cleared. An empty cell beats an invented zero.")
        try:
            credits = float(raw)
        except ValueError:
            return numbers_page(request, note="Credits has to be a number, or blank to clear it.")
        db.save_spend({**spent, "credits": credits,
                       "credits_note": str(form.get("what_for", "") or "").strip()[:200]})
        return numbers_page(request, note=(
            f"Recorded {raw} credits as your statement, not this app's measurement. The per-post "
            "figure uses the posts on this page, so it moves as you import more."))

    @app.post("/numbers/reweight", response_class=HTMLResponse)
    def numbers_reweight(request: Request):
        vector = correlate.accept_vector(correlate.pair(db.get_scores(), metrics_rows()),
                                         rubric_weights())
        if vector is None:
            return numbers_page(request, note=(
                "There was nothing to accept: your numbers changed, or they still do not separate "
                "the components. The rubric scoring your frames is the one it had a moment ago."))
        db.save_rubric(vector)
        return numbers_page(request, note=(
            "Your rubric is now " + ", ".join(f"{k} {v:.0%}" for k, v in vector.items())
            + ". Future scores use it; the scores already stored stay as they were written, "
            "because they are what you posted under. Reset returns the shipped opinion."))

    @app.post("/numbers/reset", response_class=HTMLResponse)
    def numbers_reset(request: Request):
        db.save_rubric({})
        return numbers_page(request, note=(
            "Back to the weights this app shipped with: "
            + ", ".join(f"{k} {v:.0%}" for k, v in WEIGHTS.items())
            + ". Your own numbers are untouched and will propose again."))

    @app.post("/numbers", response_class=HTMLResponse)
    async def numbers_input(request: Request):
        form = await request.form()
        plan = plan_or_none()
        if plan is None:
            return numbers_page(request, note="Build a plan first, then the reading has something to change.")
        quick = str(form.get("quick", "") or "").strip()
        upload = form.get("csv")
        if quick:
            try:
                rows = read_quick(quick)
            except ValueError as exc:
                return numbers_page(request, note=str(exc))
        elif hasattr(upload, "read"):
            state_dir.mkdir(exist_ok=True)
            path = state_dir / "metrics-last.csv"
            path.write_bytes(await upload.read())
            try:
                rows = read_csv(path)
            except ValueError as exc:
                return numbers_page(request, note=str(exc))
        else:
            return numbers_page(request, note="Type the three numbers, or drop a CSV.")
        arm = experiment.arm_for(plan, date.today())
        rows = experiment.tag(rows, arm)
        store_rows(rows)
        return numbers_page(request, rows=rows, note=(
            f"{len(rows)} posts read."
            + (f" Each was filed under this week's arm - {arm} - because that is the hypothesis "
               "the plan says is running. Correct any row that ran under the other one on "
               "the lab page." if arm else "")))

    @app.post("/numbers/apply", response_class=HTMLResponse)
    async def numbers_apply(request: Request):
        plan = plan_or_none()
        path = state_dir / "metrics-last.csv"
        if plan is None or not path.exists():
            return page(request, "numbers.html", adjustments=[], plan=plan, note="Nothing to apply yet.", rows=[])
        adjustments = analyse(read_csv(path), plan)
        changed = apply(plan, adjustments)
        db.save_current_plan(changed.to_dict())
        return page(request, "plan.html", plan=changed, entries=load_playbook()[0])

    def lab_page(request, note=""):
        plan = plan_or_none()
        week = _week_at(plan, date.today()) if plan else None
        got = experiment.ledger(metrics_rows())
        return page(request, "lab.html", note=note, got=got,
                    week=None if week is None else {
                        "week_no": week.week_no, "total": len(plan.weeks),
                        "success_test": week.success_test},
                    arm=experiment.arm_for(plan, date.today()),
                    verdict=experiment.verdict(got, plan),
                    decisions=db.recall("verdict", limit=8))

    @app.get("/lab", response_class=HTMLResponse)
    def lab(request: Request, note: str = ""):
        """The experiment ledger: this week's hypothesis, the posts filed under each arm,
        and the verdict the stored posts actually support."""
        return lab_page(request, note)

    @app.post("/lab/tag", response_class=HTMLResponse)
    async def lab_tag(request: Request):
        """Files the unlabelled posts under the hypothesis the plan says is running this
        week, in the stored ledger, so the comparison has something to read."""
        arm = str((await request.form()).get("arm", "") or "").strip()
        rows = metrics_rows()
        if not arm or not rows:
            return lab_page(request, note="Nothing to file: "
                                          + ("no hypothesis was given." if not arm else
                                             "no posts are stored yet."))
        tagged = experiment.tag(rows, arm)
        moved = sum(1 for r, t in zip(rows, tagged) if r.hypothesis != t.hypothesis)
        if not moved:
            return lab_page(request, note="Every stored post already carries a hypothesis, so "
                                          "nothing was changed.")
        store_rows(tagged)
        return lab_page(request, note=f"Filed {moved} post{'s' if moved != 1 else ''} under "
                                      f"{arm}. The {len(rows) - moved} that already had a "
                                      "label kept it.")

    @app.post("/lab/decide", response_class=HTMLResponse)
    async def lab_decide(request: Request):
        """The ledger is re-read, not trusted from the form: writing a verdict that the
        stored posts do not support would put a fake conclusion in her agent's memory."""
        got = experiment.verdict(experiment.ledger(metrics_rows()), plan_or_none())
        if not got.decided:
            return lab_page(request, note=(
                f"Nothing was written. The ledger is {got.state}, so there is no decision to "
                f"remember yet - {got.missing.lower()}"))
        db.remember("verdict", experiment.decision_text(got), source="lab",
                    seen_at=date.today().isoformat())
        return lab_page(request, note=(
            f"Remembered: kept {got.winner}, dropped {got.loser}. The next plan this app builds "
            f"will not give {got.loser} a week."))

    def money_view(request, note="", checked=None, asked_text="", where=""):
        """The bookkeeping page, rebuilt from the three sources every number on it names.

        The median comes from the metrics import, the band from a dated playbook claim, the floor
        from two numbers she typed. A fourth thing is on the page and is not money: the label
        check, which reads a caption and stops short of claiming to see the crop or hear the
        audio. Nothing here is in touch with a brand, and the page says so where the numbers are
        friendly enough to be mistaken for an agreement.
        """
        terms = db.get_terms()
        rows = metrics_rows()
        entries, _ = load_playbook()
        made, thin, uncited = money.quotes(rows, entries, terms["hourly"], terms["minutes"])
        top = max(made, key=lambda q: q.anchor) if made else None
        priced = money.priceable(rows)
        cited = {e.id: e for e in entries if e.id.startswith("money-")}
        staged = db.get_staged()
        if checked is None and not asked_text and staged.get("caption"):
            asked_text = staged["caption"]
            where = "the post staged in the composer"
            surface = staged.get("surface") or staged.get("platform") or ""
            checked = money.check_disclosure(asked_text, surface)
        return page(request, "money.html", note=note, terms=terms, quotes=made, thin=thin,
                    uncited=uncited, top=top, priced=priced, cited=cited, staged=staged,
                    addons=money.addon_lines(top.anchor if top else 0), check=checked,
                    check_text=asked_text, check_from=where, fold=money.FOLD_CHARS,
                    unit=money.UNIT, least=money.MIN_POSTS,
                    video=money.VIDEO_SURFACES, named=money.NAMED_TERMS,
                    remembered=db.recall("quote", limit=4))

    @app.get("/money", response_class=HTMLResponse)
    def money_page(request: Request, note: str = ""):
        """What a paid post would pay on your own views, what it costs you in hours, and whether
        the caption says it is an ad."""
        return money_view(request, note)

    @app.post("/money/terms", response_class=HTMLResponse)
    async def money_terms(request: Request):
        """Her hours, stored as she typed them. Blank is zero, and zero means the app refuses to
        invent a wage rather than quietly adopting somebody else's."""
        form = await request.form()
        got = []
        for key in ("hourly", "minutes"):
            raw = str(form.get(key, "") or "").strip().replace(",", ".")
            try:
                got.append(max(0.0, float(raw or 0)))
            except ValueError:
                return money_view(request, note=f"{key} needs a number, not {raw!r}. Nothing was "
                                                "saved, so the floor on the page is still the one "
                                                "you had.",
                                  checked=None, asked_text="", where="")
        db.save_terms({"hourly": got[0], "minutes": got[1]})
        floor = round(got[0] * got[1] / 60.0, 2)
        tail = (f"costs {money.UNIT}{floor:.2f}, so nothing on this page will quote under it."
                if floor else "is no floor - the app will not price your time for you.")
        return money_view(
            request,
            note=f"Saved. A post at {got[1]:g} minutes of your time at {money.UNIT}"
                 f"{got[0]:g} an hour {tail}",
            checked=None, asked_text="", where="")

    @app.post("/money/label", response_class=HTMLResponse)
    async def money_label(request: Request):
        """The caption read against the words the cited guidance actually names. The checkbox is
        the only way this page can be told the label is in the video too - it cannot watch."""
        form = await request.form()
        text = str(form.get("text", "") or "")
        where = "the text you pasted" if text.strip() else ""
        staged = db.get_staged()
        if not text.strip() and staged.get("caption"):
            text = staged["caption"]
            where = "the post staged in the composer"
        if not text.strip():
            return money_view(request, note="Nothing to read: no text was pasted and no post is "
                                             "staged.", checked=None, asked_text="", where="")
        surface = (str(form.get("surface", "") or "") or
                   (staged.get("surface") or staged.get("platform") or ""))
        got = money.check_disclosure(text, surface, bool(form.get("in_video")))
        return money_view(request, note="", checked=got, asked_text=text, where=where)

    def repurpose_view(request, passed=None, note=""):
        """The page in either state: what it would rebuild, or what it did. The candidate list
        is computed without writing a file, so the run button is never a guess about what is
        behind it."""
        rows = metrics_rows()
        got = experiment.ledger(rows)
        wanted = []
        for ref, arm, own in repurpose.picks(got, rows):
            kind, src = repurpose.source_for(ref, inbox_dir, clips_dir)
            wanted.append({"ref": ref, "arm": arm, "rate": own, "kind": kind or "",
                           "file": src.name if src is not None else ""})
        return page(request, "repurpose.html", got=got, passed=passed, wanted=wanted,
                    n_shapes=len(set(repurpose.SHAPE.values())), note=note)

    @app.get("/repurpose", response_class=HTMLResponse)
    def repurpose_page(request: Request, note: str = ""):
        """The repurposing pass: the posts the lab already ranked, rebuilt for the frames they
        have never run in."""
        return repurpose_view(request, note=note)

    @app.post("/repurpose/run", response_class=HTMLResponse)
    def repurpose_run(request: Request):
        """Real files, written next to her saved edits, or the reason there are none. Nothing
        here is a success message: the page lists what was written and what was skipped."""
        answers = db.get_interview()
        passed = repurpose.run(experiment.ledger(metrics_rows()), metrics_rows(),
                               voice.learn(db.get_voice()), date.today(),
                               subject_of(answers) if answers else "",
                               inbox_dir, clips_dir, edited_dir)
        return repurpose_view(request, passed=passed,
                              note="" if passed.cuts else "Nothing was written.")

    edited_dir = inbox_dir / "edited"
    clean_dir = inbox_dir / "clean"

    def inbox_file(name: str) -> Path | None:
        """Only her inbox folder and the two folders this app writes results into -
        never a path somebody typed. The one-tap fix lands in clean/, so the editor has
        to be able to open it again or that copy is written and then lost."""
        target = (inbox_dir / name).resolve()
        allowed = (inbox_dir.resolve(), edited_dir.resolve(), clean_dir.resolve())
        if target.parent not in allowed or not target.is_file():
            return None
        return target

    def recipe_of(raw: str) -> list:
        try:
            data = json.loads(raw or "[]")
        except ValueError:
            return []
        return data if isinstance(data, list) else []

    def inbox_names() -> list[str]:
        """What the second-photo and grid pickers offer: her inbox plus what this app has
        already written, because a saved edit is the likeliest thing she wants to compare."""
        found = []
        for folder, prefix in ((inbox_dir, ""), (edited_dir, "edited/"), (clean_dir, "clean/")):
            if folder.is_dir():
                found += [prefix + p.name for p in sorted(folder.glob("*"))
                          if p.suffix.lower() in IMAGE_SUFFIXES]
        return found

    def next_name(directory: Path, stem: str, suffix: str) -> Path:
        dst = directory / f"{stem}{suffix}"
        n = 2
        while dst.exists():
            dst = directory / f"{stem}-{n}{suffix}"
            n += 1
        return dst

    def preview_bytes(src: Path, recipe: list, edge: bool) -> bytes:
        im = edit_file(src, recipe, proxy=edge)
        if im.mode != "RGB":
            # The preview has to be a JPEG, so a cutout reads against white here. The saved
            # file keeps its transparency; this is the one place the difference shows.
            flat = Image.new("RGB", im.size, (252, 252, 252))
            flat.paste(im, (0, 0), im)
            im = flat
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82 if edge else SAVE_QUALITY)
        return buf.getvalue()

    def log_ops(src: Path, dst: Path, recipe) -> None:
        """The chain table exists so "this is not an AI image" is a log rather than an
        assertion, and spec 5.9 counts from the same rows: every operation written into a
        saved file, with the digest of the file before and after it."""
        before = hashlib.sha1(src.read_bytes()).hexdigest()[:16]
        after = hashlib.sha1(dst.read_bytes()).hexdigest()[:16]
        for entry in recipe:
            db.log_edit(dst.name, entry[0], entry[1] if len(entry) > 1 else None,
                        before, after, date.today().isoformat())

    @app.get("/photos", response_class=HTMLResponse)
    def photos(request: Request, note: str = ""):
        custom = db.get_rubric()
        weights = custom or WEIGHTS
        rows = []
        for r in judge(inbox_files(inbox_dir)):
            j = None if r.error else judge_photo(inbox_dir / r.name, r, weights)
            if j is not None:
                remember(inbox_dir / r.name, "photo", j)
            rows.append({"r": r, "j": j})
        produced = [p for folder in (edited_dir, clean_dir) if folder.is_dir()
                    for p in folder.glob("*") if p.suffix.lower() in IMAGE_SUFFIXES]
        saved = [{"name": p.name, "href": quote(p.relative_to(inbox_dir).as_posix())}
                 for p in sorted(produced, key=lambda p: p.name)]
        return page(request, "photos.html", readings=rows, inbox=str(inbox_dir), note=note,
                    weights=weights, saved=saved, shipped=custom is None)

    @app.post("/photos/upload", response_class=HTMLResponse)
    async def photos_upload(request: Request, file: UploadFile = File(...)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            return photos(request, note=f"{suffix or 'That file'} is not a picture this app can read.")
        inbox_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(file.filename).name.rsplit(".", 1)[0][:60] or "photo"
        dst = next_name(inbox_dir, stem, suffix)
        with dst.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        return RedirectResponse(f"/edit?name={quote(dst.name)}", status_code=303)

    @app.post("/photos/clean", response_class=HTMLResponse)
    async def photos_clean(request: Request):
        form = await request.form()
        src = inbox_file(str(form.get("name", "")))
        if src is None:
            return photos(request, note="That file is not in the inbox folder.")
        weights = rubric_weights()
        judged = judge_photo(src, measure(src), weights)
        fixes = judged.fixes or judged.reading.fixes
        if not fixes:
            return photos(request, note="Nothing left for the editor to do - that frame is already clean.")
        dst = fix(src, clean_dir, fixes, tilt=judged.tilt, focus=judged.focus)
        after = judge_photo(dst, measure(dst), weights)
        remember(dst, "photo", after)
        log_ops(src, dst, [[f, None] for f in fixes])
        moved = (f"score {judged.score} to {after.score}" if after.score != judged.score
                 else f"score still {judged.score}")
        return photos(request, note=f"Wrote {dst.name} with {' + '.join(fixes)} - {moved}. "
                                    "The original was not touched.")

    @app.get("/face", response_class=HTMLResponse)
    def face(request: Request, name: str = "", fx: float = 0.0, fy: float = 0.0,
             size: float = 0.22, note: str = ""):
        """What the frame does to her face, measured inside a box she can move.

        There is no score here and the page says so. The detector is offered as a first
        guess and she is allowed to overrule it, because on a graded photo the colour of
        her cheek and the colour of the wall behind it are the same number.
        """
        src = inbox_file(name)
        if src is None:
            # The sentence follows the folder, not the query string: with photos in the inbox
            # the page must not claim it is empty just because no name was typed yet.
            hint = ("Nothing in the inbox yet. Put a photo on /photos."
                    if not inbox_files(inbox_dir) else "Pick a photo first.")
            return page(request, "face.html", src=None, read=None, name="", size=size,
                        files=[f.name for f in inbox_files(inbox_dir)],
                        contract=FACE_CONTRACT, note=note or hint)
        tap = (fx, fy) if fx and fy else None
        read = read_face(src, engine, tap=tap, size=size)
        pct = None
        if read.found and read.frame[0]:
            w, h = read.frame
            pct = {"left": read.box[0] / w * 100, "top": read.box[1] / h * 100,
                   "width": (read.box[2] - read.box[0]) / w * 100,
                   "height": (read.box[3] - read.box[1]) / h * 100}
        return page(request, "face.html", src=src, read=read, name=src.name, size=size,
                    fx=fx, fy=fy,
                    files=[f.name for f in inbox_files(inbox_dir)], pct=pct,
                    contract=FACE_CONTRACT, note=note)

    @app.get("/edit", response_class=HTMLResponse)
    def edit_page(request: Request, name: str = "", note: str = ""):
        src = inbox_file(name)
        if src is None:
            return photos(request, note="Pick a file first - the editor opens one at a time.")
        side = src.with_suffix(".json")
        carried = recipe_of(side.read_text(encoding="utf-8")) if side.is_file() else []
        reading = measure(src)
        return page(request, "edit.html", file_name=src.name,
                    rel=str(src.relative_to(inbox_dir)).replace("\\", "/"),
                    reading=reading, sliders=SLIDERS, presets=PRESETS,
                    rails=RAIL_TOOLS, rail_names=RAILS, titles=TITLES, arity=ARITY,
                    tools_json=tools_json(), files=inbox_names(),
                    presets_json=json.dumps(PRESETS), recipe_json=json.dumps(carried),
                    judged=judge_photo(src, reading, rubric_weights()),
                    note=note, edited=src.parent == edited_dir)

    @app.get("/edit/preview")
    def edit_preview(name: str = "", ops: str = "", full: int = 0):
        src = inbox_file(name)
        if src is None:
            raise HTTPException(status_code=404)
        return Response(content=preview_bytes(src, recipe_of(ops), not full),
                        media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/edit/save", response_class=HTMLResponse)
    async def edit_save(request: Request):
        form = await request.form()
        src = inbox_file(str(form.get("name", "")))
        if src is None:
            return photos(request, note="That file is not in the inbox folder.")
        recipe = normalize(recipe_of(str(form.get("recipe", ""))))
        image = edit_file(src, recipe)
        # A cutout or a rounded corner has alpha, and alpha cannot live in a JPEG. The
        # format she asked for wins right up until the edit itself demands otherwise.
        png = str(form.get("format", "")) == "png" or image.mode != "RGB"
        edited_dir.mkdir(parents=True, exist_ok=True)
        dst = next_name(edited_dir, src.stem[:60], ".png" if png else ".jpg")
        image.save(dst, "PNG" if png else "JPEG", quality=SAVE_QUALITY)
        dst.with_suffix(".json").write_text(json.dumps(recipe, indent=1), encoding="utf-8")
        after = judge_photo(dst, measure(dst), rubric_weights())
        remember(dst, "photo", after)
        log_ops(src, dst, recipe)
        return RedirectResponse(
            f"/edit?name={quote(f'edited/{dst.name}')}&note=Saved+{quote(dst.name)}+with+{len(recipe)}"
            "+edits.+Score+" + str(after.score) + ".+The+original+was+not+touched.", status_code=303)

    clips_dir = state_dir / "clips"
    clips_edited = clips_dir / "edited"
    frames_dir = state_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/frames", StaticFiles(directory=str(frames_dir)), name="frames")

    def clip_file(name: str) -> Path | None:
        """Only her clips folder or her saved cuts - never a path somebody typed."""
        target = (clips_dir / name).resolve()
        if target.parent not in (clips_dir.resolve(), clips_edited.resolve()):
            return None
        if not target.is_file() or target.suffix.lower() not in clipmod.VIDEO_SUFFIXES:
            return None
        return target

    def frame_key(src: Path) -> str:
        """A saved cut shares its name with the clip it came from, so the decoded frames
        of the two must never land on the same file."""
        return f"{src.parent.name}-{src.stem}"[:80].replace(" ", "-")

    def trim_previews(folder: Path, key: str, keep: int = 24) -> None:
        """Preview files are keyed by every control state, so one long session can leave
        hundreds behind. The newest few are what she is comparing; the rest are disk."""
        for stale in sorted(folder.glob(f"{key}-*.png"),
                            key=lambda p: p.stat().st_mtime)[:-keep]:
            stale.unlink(missing_ok=True)

    def clip_jpeg(png: Path, edge: int = 900) -> bytes:
        with Image.open(png) as im:
            scale = edge / max(im.size)
            if scale < 1:
                im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                               Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=82)
        return buf.getvalue()

    @app.get("/clips", response_class=HTMLResponse)
    def clips_page(request: Request, note: str = ""):
        clips_dir.mkdir(parents=True, exist_ok=True)
        rows = [clipmod.probe(p) for p in clipmod.clip_files(clips_dir)]
        saved = [clipmod.probe(p) for p in clipmod.clip_files(clips_edited)]
        return page(request, "clips.html", clips=rows, saved=saved, folder=str(clips_dir),
                    note=note, ffmpeg=clipmod.available(), weights=CLIP_WEIGHTS,
                    names=CLIP_LABELS)

    @app.post("/clips/upload", response_class=HTMLResponse)
    async def clips_upload(request: Request, file: UploadFile = File(...)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in clipmod.VIDEO_SUFFIXES:
            return clips_page(request, note=f"{suffix or 'That file'} is not a video this app can read.")
        clips_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(file.filename).name.rsplit(".", 1)[0][:60] or "clip"
        dst = next_name(clips_dir, stem, suffix)
        with dst.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        return RedirectResponse(f"/clip?name={quote(dst.name)}", status_code=303)

    @app.get("/clip", response_class=HTMLResponse)
    def clip_page(request: Request, name: str = "", note: str = ""):
        src = clip_file(name)
        if src is None:
            return clips_page(request, note="Pick a clip first - the editor opens one at a time.")
        side = src.with_suffix(".json")
        carried = clipmod.normalize(recipe_of(side.read_text(encoding="utf-8"))) if side.is_file() else []
        verdict = judge_clip(src, frames_dir / frame_key(src))
        remember(src, "clip", verdict)
        trim_previews(frames_dir / "preview", frame_key(src))
        tips = suggest(verdict)
        return page(request, "clip.html", file_name=src.name,
                    rel=str(src.relative_to(clips_dir)).replace("\\", "/"),
                    verdict=verdict, times=clipmod.sample_times(verdict.clip.duration),
                    frame_urls=[f.path.relative_to(frames_dir).as_posix() for f in verdict.frames],
                    recipe_json=json.dumps(carried),
                    initial_ops=quote(json.dumps(carried), safe=""),
                    labels=clipmod.LABELS,
                    controls=clipmod.CONTROLS, ranges=clipmod.RANGES,
                    frame_ops=clipmod.FRAME_OPS,
                    tone_ops=clipmod.TONE_OPS, finish_ops=clipmod.FINISH_OPS,
                    weights=CLIP_WEIGHTS, names=CLIP_LABELS, suggested=json.dumps(tips),
                    has_suggestions=bool(tips),
                    note=note, ffmpeg=clipmod.available())

    @app.get("/clip/preview")
    def clip_preview(name: str = "", ops: str = "", t: float = 0.0):
        src = clip_file(name)
        if src is None:
            raise HTTPException(status_code=404)
        try:
            entries = clipmod.normalize(recipe_of(ops))
            tag = hashlib.sha1(f"{json.dumps(entries)}|{round(t, 3)}".encode()).hexdigest()[:12]
            png = clipmod.preview_frame(src, t, entries,
                                        frames_dir / "preview" / f"{frame_key(src)}-{tag}.png",
                                        edge=clipmod.SHOW_EDGE)
            return Response(clip_jpeg(png), media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except RuntimeError:
            raise HTTPException(status_code=404)

    @app.post("/clip/save", response_class=HTMLResponse)
    async def clip_save(request: Request):
        form = await request.form()
        raw = str(form.get("name", ""))
        src = clip_file(raw)
        if src is None:
            return clips_page(request, note="That file is not in the clips folder.")
        recipe = clipmod.normalize(recipe_of(str(form.get("recipe", ""))))
        clips_edited.mkdir(parents=True, exist_ok=True)
        dst = next_name(clips_edited, src.stem[:60], ".mp4")
        try:
            after = clipmod.export(src, dst, recipe)
        except RuntimeError as exc:
            return clip_page(request, name=raw, note=f"ffmpeg refused it: {exc}")
        dst.with_suffix(".json").write_text(json.dumps(recipe, indent=1), encoding="utf-8")
        return RedirectResponse(
            f"/clip?name={quote(f'edited/{dst.name}')}&note=Saved+{quote(dst.name)}+as+"
            f"{after.width}x{after.height}+for+{after.duration:.1f}s.+The+original+was+not+touched.",
            status_code=303)

    @app.post("/clip/cover", response_class=HTMLResponse)
    async def clip_cover(request: Request):
        form = await request.form()
        raw = str(form.get("name", ""))
        src = clip_file(raw)
        if src is None:
            return clips_page(request, note="That file is not in the clips folder.")
        try:
            stamp = max(0.0, float(form.get("t", 0) or 0))
        except ValueError:
            stamp = 0.0
        inbox_dir.mkdir(parents=True, exist_ok=True)
        dst = next_name(inbox_dir, f"{src.stem[:40]}-cover", ".jpg")
        try:
            clipmod.cover(src, stamp, dst)
        except RuntimeError as exc:
            return clip_page(request, name=raw, note=f"No frame there: {exc}")
        return RedirectResponse(f"/edit?name={quote(dst.name)}", status_code=303)

    # ---- accounts and the composer ----------------------------------------------
    # These two pages exist because the same two questions keep arriving: what can this app
    # see about my accounts, and can it post for me. Both get answered with a file, a number
    # or a step list - never with a button that pretends.
    audio_dir = state_dir / "audio"
    outputs_dir = state_dir / "outputs"
    story_dir = outputs_dir / "story"
    links_path = state_dir / "accounts.json"
    for folder in (audio_dir, outputs_dir, story_dir):
        folder.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
    AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}
    STORY_FIELDS = ("name", "platform", "surface", "caption", "hashtags", "alt", "lines",
                    "music", "audio")

    def media_file(name: str) -> Path | None:
        """Every file she could post, through the two doors that already check the path."""
        return inbox_file(name) or clip_file(name)

    def audio_file(name: str) -> Path | None:
        target = (audio_dir / name).resolve()
        if target.parent != audio_dir.resolve() or not target.is_file():
            return None
        return target if target.suffix.lower() in AUDIO_SUFFIXES else None

    def postable_files() -> list[str]:
        return (inbox_names() + [p.name for p in clipmod.clip_files(clips_dir)]
                + ["edited/" + p.name for p in clipmod.clip_files(clips_edited)])

    def audio_names() -> list[str]:
        return sorted(p.name for p in audio_dir.iterdir()
                      if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES)

    def values_of(form) -> dict:
        """The composer's own fields, so a page can be redrawn with exactly what she typed
        after a render fails instead of making her write it out again."""
        raw = {key: str(form.get(key, "") or "") for key in STORY_FIELDS}
        raw["keep_audio"] = str(form.get("keep_audio", "")) == "on"
        return raw

    def staged_package() -> dict:
        """The last thing staged, or nothing. Clearing writes an empty payload, and a row of
        blanks is not a post waiting to happen."""
        st = db.get_staged()
        return st if st.get("platform") else {}

    def staged_values() -> dict:
        st = staged_package()
        if not st:
            return {}
        return {"name": st.get("source", ""), "platform": st.get("platform", ""),
                "surface": st.get("surface", ""), "caption": st.get("caption", ""),
                "hashtags": " ".join(st.get("hashtags", [])), "alt": st.get("alt", ""),
                "lines": st.get("lines", ""), "music": st.get("music", ""),
                "audio": "", "keep_audio": True}

    @app.get("/accounts", response_class=HTMLResponse)
    def accounts_page(request: Request, note: str = ""):
        """What the app can know about each account, and how, in her words as well as ours.

        There is no login box here on purpose. The tickbox says "I am signed in to this in my
        browser", which is a note about her machine, and every number the page can show came
        from a file she downloaded herself or a screen she typed from.
        """
        rows = accounts.state_rows(db.get_accounts(), accounts.load_links(links_path))
        imported = metrics_rows()
        return page(request, "accounts.html", rows=rows, note=note, methods=accounts.METHODS,
                    saved=db.get_accounts(), imported=len(imported),
                    metrics_path=str(state_dir / "metrics-last.csv"),
                    links=accounts.load_links(links_path),
                    staged=staged_package().get("file", ""))

    @app.post("/accounts/save", response_class=HTMLResponse)
    def accounts_save(request: Request, platform: str = Form(""), handle: str = Form(""),
                      method: str = Form("handoff"), last_export: str = Form(""),
                      connected: str = Form("")):
        key = accounts.platform_id(platform)
        picked = accounts.info(key)
        chosen = method if method in accounts.METHOD_IDS else "handoff"
        stamp = last_export.strip()
        db.save_account(key, {"handle": handle.strip()[:60], "method": chosen,
                              "connected": connected == "on",
                              "last_export": iso_or_today(stamp) if stamp else ""})
        how = next(m for m in accounts.METHODS if m[0] == chosen)
        return RedirectResponse("/accounts?note=" + quote(
            f"Saved for {picked['label']}: {how[1]}. Nothing was contacted and no login was "
            f"taken - {how[2].lower()}"), status_code=303)

    @app.post("/accounts/links", response_class=HTMLResponse)
    async def accounts_links(request: Request):
        """The handoff addresses, editable because a regional or a business account moves
        them. Stored as data, opened only by her own browser clicking a link."""
        form = await request.form()
        table = accounts.load_links(links_path)
        refused = []
        for key in accounts.WHITELIST:
            raw = str(form.get(f"link_{key}", "") or "").strip()
            if not raw:
                continue
            clean = accounts.valid_link(raw)
            if clean:
                table[key] = clean
            else:
                refused.append(accounts.info(key)["label"])
        accounts.save_links(table, links_path)
        tail = (f" Refused {', '.join(refused)} - an address has to be the whole thing, scheme "
                "and all." if refused else "")
        return RedirectResponse("/accounts?note=" + quote(
            "Addresses saved in data/accounts.json. The app never opens them itself - it hands "
            f"you a link and you are already signed in in that tab.{tail}"), status_code=303)

    @app.post("/accounts/forget", response_class=HTMLResponse)
    def accounts_forget(request: Request, platform: str = Form("")):
        key = accounts.platform_id(platform)
        db.save_account(key, {"handle": "", "method": "handoff", "connected": False,
                              "last_export": ""})
        return RedirectResponse("/accounts?note=" + quote(
            f"Forgotten what you told this app about {accounts.info(key)['label']}. "
            "Your actual account is untouched - it never held anything."), status_code=303)

    def bench_rows() -> list[benchmod.Row]:
        return [benchmod.Row.from_dict(d) for d in db.get_bench()]

    def bench_id_of(raw) -> int | None:
        """A row number, or None. None is not 0 and not -1: -1 is a real id here, so a blank
        box must never quietly aim the page at her newest exported post."""
        text = str(raw).strip()
        try:
            return int(text) if text else None
        except ValueError:
            return None

    def own_bench_rows() -> list[benchmod.Row]:
        """Her own exported posts, in benchmark shape. A file she downloaded is a real record of
        real numbers, so it joins the comparison without being retyped - and it keeps its post
        reference, so a row can never pass itself off as somebody else's hit.

        Numbered from -1 down: negative because no typed row can ever hold that id, and counted
        because the page has to be able to point at one row and say which one it read."""
        rows = [benchmod.Row(label=m.post_ref, platform=m.platform, origin="yours",
                             views=m.views, comments=m.comments, saves=m.saves,
                             follows=m.follows_gained)
                for m in metrics_rows()]
        for offset, row in enumerate(reversed(rows), start=1):
            row.id = -offset
        return rows

    def bench_view(request: Request, note: str = "", target=None, metric: str = "saves",
                   include_own: bool = True):
        """The list she typed, plus one reading of one post against it."""
        rows = bench_rows()
        mine = own_bench_rows()
        universe = rows + (mine if include_own else [])
        reading = None
        readings = []
        if target is not None:
            try:
                readings = [(key, benchmod.place(target, universe, key))
                            for key in benchmod.METRICS]
                reading = dict(readings).get(metric) or readings[0][1]
            except ValueError as exc:
                note = str(exc)
        return page(request, "bench.html", note=note, rows=rows, mine=mine, target=target,
                    metric=(reading.metric if reading else metric), readings=readings,
                    include_own=include_own, reading=reading,
                    metrics=benchmod.METRICS, floor=benchmod.MIN_VIEWS,
                    need=benchmod.MIN_COMPARABLE, columns=benchmod.PASTE_COLUMNS,
                    known=[(p["id"], p["label"]) for p in accounts.PLATFORMS])

    @app.get("/bench", response_class=HTMLResponse)
    def bench_page(request: Request, note: str = "", read: str = "", metric: str = "saves"):
        """Feed it what you saw; it tells you where yours sits among it."""
        wanted = bench_id_of(read)
        pool = bench_rows() + own_bench_rows()
        target = next((r for r in pool if r.id == wanted), None) if wanted is not None else None
        return bench_view(request, note=note, target=target, metric=metric)

    @app.post("/bench/add", response_class=HTMLResponse)
    async def bench_add(request: Request, label: str = Form(""), platform: str = Form(""),
                        origin: str = Form("saw it"), views: str = Form(""),
                        likes: str = Form(""), comments: str = Form(""),
                        saves: str = Form(""), shares: str = Form(""),
                        gained: str = Form("")):
        """One post, written down - saved first, then read, because the row she just typed is
        the row the page should tell her about and it has to survive closing the tab."""
        raw = {"views": views, "likes": likes, "comments": comments, "saves": saves,
               "shares": shares, "follows": gained}
        numbers, problems = {}, []
        for key, value in raw.items():
            try:
                numbers[key] = benchmod.count(value)
            except ValueError:
                problems.append(f"{key} ({value!r})")
        if problems:
            return bench_view(request, note="Those fields are not counts: " + ", ".join(problems)
                              + ". A blank box is fine; half a number is not.")
        name = label.strip()[:80]
        if not name:
            return bench_view(request, note="Give it something to be called - a file name, a "
                              "handle, the first line of the caption. A list of blank rows cannot "
                              "be read back a week later.")
        if numbers["views"] <= 0:
            return bench_view(request, note="Views has to be above zero. Every rate here is a "
                              "share of the view count, so with no views there is nothing to "
                              "take a share of.")
        made = date.today().isoformat()
        key = (platform or "").strip().lower()
        saved = {"label": name, "platform": key if key in accounts.WHITELIST else "",
                 "origin": "yours" if origin == "yours" else "saw it",
                 "views": numbers["views"], "likes": numbers["likes"],
                 "comments": numbers["comments"], "saves": numbers["saves"],
                 "shares": numbers["shares"], "follows": numbers["follows"]}
        saved_id = db.add_bench(saved, made)
        return bench_view(request, target=benchmod.Row.from_dict({**saved, "id": saved_id,
                                                                  "made_at": made}),
                          note=f"Wrote down {name}.")

    @app.post("/bench/paste", response_class=HTMLResponse)
    async def bench_paste(request: Request, lines: str = Form("")):
        """Several posts at once, which is how a list like this actually gets filled."""
        parsed, problems = benchmod.parse_lines(lines)
        made = date.today().isoformat()
        for row in parsed:
            db.add_bench(row.to_dict(), made)
        note = f"{len(parsed)} posts added." if parsed else "Nothing readable in that box."
        if problems:
            note += " Not added: " + " | ".join(problems[:4])
        last = bench_rows()
        return bench_view(request, target=last[-1] if parsed and last else None, note=note)

    @app.post("/bench/read", response_class=HTMLResponse)
    async def bench_read(request: Request, bench_id: str = Form(""),
                         metric: str = Form("saves")):
        """Any row in the list, on any of the five numbers."""
        wanted = bench_id_of(bench_id)
        pool = bench_rows() + own_bench_rows()
        target = next((r for r in pool if r.id == wanted), None) if wanted is not None else None
        if target is None:
            return bench_view(request, note="Pick one of the rows below and this will say where "
                              "it sits among the rest of the list.")
        return bench_view(request, target=target, metric=metric)

    @app.post("/bench/forget", response_class=HTMLResponse)
    async def bench_forget(request: Request, bench_id: str = Form("")):
        wanted = bench_id_of(bench_id)
        if wanted is None or wanted < 0:
            return bench_view(request, note=(
                "That row comes from the export on the Numbers page, so it is not this list's to "
                "forget: change the file and it goes." if wanted is not None else
                "No row was named, so nothing was removed."))
        db.forget_bench(wanted)
        return RedirectResponse("/bench?note=" + quote("Removed from the list."), status_code=303)

    @app.post("/bench/clear", response_class=HTMLResponse)
    def bench_clear(request: Request):
        db.clear_bench()
        return RedirectResponse("/bench?note=" + quote(
            "The typed list is empty. Your exported posts are untouched - that file lives on "
            "the Numbers page, and this only forgets the posts you wrote in by hand."),
            status_code=303)

    def registry_refresh() -> dict:
        """Re-reads the tree and replaces the registry. It parses every file in src, so it
        runs when she asks for it, not on every page view."""
        entries = regaudit.audit()
        ups = regaudit.upgrades(entries)
        db.save_registry([e.as_dict() for e in entries], [e.as_dict() for e in ups],
                         date.today().isoformat())
        return regaudit.summary(entries, ups)

    @app.get("/registry", response_class=HTMLResponse)
    def registry_page(request: Request, q: str = "", dept: str = "", kind: str = "feature",
                      status: str = "", note: str = ""):
        if kind not in ("feature", "upgrade"):
            kind = "feature"
        if not db.registry_totals()["feature_all"]:
            got = registry_refresh()
            note = (f"Read the repository: {got['features']} features and {got['upgrades']} "
                    f"open gaps, of which {got['proven']} have a test that names them.")
        totals = db.registry_totals()
        everything = db.search_registry("feature", limit=0)
        return page(request, "registry.html", q=q, dept=dept, kind=kind, status=status,
                    note=note, rows=db.search_registry(kind, q, dept, status),
                    totals=totals,
                    nfeat=totals["feature_all"], nup=totals["upgrade_all"],
                    counts={"kinds": {k: sum(1 for f in everything if f["kind"] == k)
                                      for k in regaudit.KINDS},
                            "unreachable": sum(1 for f in everything
                                               if f["reach"] == "nothing links to it"),
                            "features": len(everything),
                            "unproven": sum(1 for f in everything
                                            if f["status"] == "unproven"),
                            # Floored, never rounded: 211 of 212 must not print as 100%.
                            "percent": sum(1 for f in everything if f["status"] != "unproven")
                            * 100 // max(1, len(everything))},
                    departments=regaudit.departments(everything), kinds=regaudit.KINDS)

    @app.post("/registry/read", response_class=HTMLResponse)
    def registry_read(request: Request):
        got = registry_refresh()
        reach = (f", {got['unreachable']} endpoints no page points at"
                 if got["unreachable"] else "")
        proof = (f"{got['unproven']} with no test naming them" if got["unproven"]
                 else "every one of them named by a test")
        return RedirectResponse("/registry?note=" + quote(
            f"Re-read the tree just now: {got['features']} features, {proof}{reach}, "
            f"{got['upgrades']} open gaps."), status_code=303)

    def story_view(request: Request, note: str = "", v: dict | None = None,
                   rendered=None, pkg: dict | None = None, why=()):
        staged = pkg or staged_package()
        vals = {**staged_values(), **(v or {})}
        src = media_file(vals.get("name", ""))
        files = postable_files()
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        return page(request, "story.html", note=note, files=files, src=src,
                    picked=vals.get("name", ""), platforms=accounts.PLATFORMS,
                    platform=accounts.platform_id(vals.get("platform", "")),
                    surface=vals.get("surface", ""),
                    surfaces=accounts.surfaces(vals.get("platform", "")), caption=vals.get("caption", ""),
                    hashtags=vals.get("hashtags", ""), alt=vals.get("alt", ""),
                    lines=vals.get("lines", ""), music=vals.get("music", ""),
                    audio=vals.get("audio", ""), keep_audio=vals.get("keep_audio", True),
                    audios=audio_names(), has_ffmpeg=clipmod.available(),
                    is_video=bool(src and story.is_video(src)),
                    safe_top=story.SAFE_TOP, safe_bottom=story.SAFE_BOTTOM,
                    line_limit=story.LINE_LIMIT,
                    addresses=net.lan_addresses(), port=port,
                    rendered=rendered, staged=staged,
                    post=accounts.package_from(staged) if staged else None,
                    why=list(why),
                    inbox=str(inbox_dir), clips_folder=str(clips_dir))

    @app.get("/story", response_class=HTMLResponse)
    def story_page(request: Request, name: str = "", note: str = ""):
        """The one place a file becomes a post: pick it, word it, time the words, render,
        and take the block to the platform. Everything under this URL writes real files."""
        return story_view(request, note=note, v={"name": name} if name else None)

    @app.post("/story/audio", response_class=HTMLResponse)
    async def story_audio(request: Request, file: UploadFile = File(...)):
        """Audio she owns, kept on this machine for mixing under her own clip."""
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            return story_view(request, note=f"{suffix or 'That file'} is not an audio format "
                                            "ffmpeg can lay under a clip.")
        stem = Path(file.filename).name.rsplit(".", 1)[0][:60] or "audio"
        dst = next_name(audio_dir, stem, suffix)
        with dst.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        return story_view(request, note=f"Kept {dst.name}. It is only ever mixed in when you "
                                        "pick it - a song from a streaming service is not a "
                                        "file you own, and no upload path carries one.",
                          v={"audio": dst.name})

    @app.post("/story/caption", response_class=HTMLResponse)
    async def story_caption(request: Request):
        """Find a caption in the app: today's slot, cut for this platform, in her own voice.
        It fills the box and stops there - nothing is saved until she renders."""
        form = await request.form()
        v = values_of(form)
        answers, plan = db.get_interview(), plan_or_none()
        if not answers or not plan or not Interview.complete(answers):
            return story_view(request, v=v, note="The Writer needs the interview and a plan "
                                                 "before it has a line to cut. Write your own "
                                                 "in the box meanwhile.")
        day = day_for(answers, plan, date.today())
        variant = voice.package(subject_of(answers), day.hypothesis, date.today(),
                                 voice.learn(db.get_voice()),
                                 platforms=(accounts.caption_key(v.get("platform", "")),))[0]
        v["caption"] = variant.hook if "story" in (v.get("surface") or "").lower() else variant.block
        v["hashtags"] = ""
        return story_view(request, v=v, rendered=None, why=variant.why,
                          note=f"Written from today's slot ({day.hypothesis}) and the way you "
                               "actually write. Edit it - it is not saved yet.")

    @app.post("/story/ready", response_class=HTMLResponse)
    async def story_ready(request: Request):
        """Render, then stage. A package only ever describes a file this app really wrote."""
        form = await request.form()
        v = values_of(form)
        src = media_file(v["name"])
        if src is None:
            return story_view(request, v=v, note="Pick a file that is actually in your inbox "
                                                 "or clips folder - nothing was rendered.")
        if not clipmod.available() and story.is_video(src):
            return story_view(request, v=v, note="ffmpeg is not available on this machine, so "
                                                 "a video cannot be burned. A still renders.")
        bed = audio_file(v["audio"])
        if v["audio"] and bed is None:
            return story_view(request, v=v, note="That audio file is not in the audio folder "
                                                 "this app writes to.")
        if bed is not None and not story.is_video(src):
            return story_view(request, v=v, note="A photo has no timeline, so there is nothing "
                                                 "to lay audio under. Pick a clip or drop the "
                                                 "audio choice.")
        out = next_name(story_dir, f"{src.stem[:40]}-story",
                        ".mp4" if story.is_video(src) else ".jpg")
        got = story.render(src, out, v["lines"], audio=bed, keep_audio=v["keep_audio"])
        if not got.ok:
            return story_view(request, v=v, note=got.error)
        rel = out.relative_to(outputs_dir).as_posix()
        tags = [t for t in re.split(r"[,\s]+", v["hashtags"]) if t]
        pkg = accounts.build(v["platform"], v["surface"], caption=v["caption"], hashtags=tags,
                             alt=v["alt"], lines=v["lines"], music=v["music"],
                             source=v["name"], file=rel).as_dict()
        db.save_staged(pkg, date.today().isoformat())
        words = (f"{len(got.lines)} line{'' if len(got.lines) == 1 else 's'} baked in"
                 if got.lines else "no words baked in")
        return story_view(request, v=v, rendered=got, pkg=pkg,
                          note=f"Wrote {out.name} - {words}, carrying {got.audio}. "
                               "The source file was not touched.")

    @app.post("/story/clear", response_class=HTMLResponse)
    def story_clear(request: Request):
        db.save_staged({}, date.today().isoformat())
        return story_view(request, note="Cleared the staged post. The rendered files stay in "
                                        "outputs/story - they are on your disk, not in this app.")

    @app.get("/phone", response_class=HTMLResponse)
    def phone_page(request: Request, note: str = ""):
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        return page(request, "phone.html", addresses=net.lan_addresses(), port=port,
                    status=gate.status(), note=note, local=not from_phone(request),
                    pin_range=(net.MIN_PIN, net.MAX_PIN), cooldown=net.COOLDOWN_MINUTES)

    @app.post("/phone/pin", response_class=HTMLResponse)
    def phone_pin(request: Request, pin: str = Form("")):
        if from_phone(request):
            return phone_page(request, note="The PIN is set on the laptop, where the files live.")
        reason = gate.set_pin(pin)
        if reason:
            return phone_page(request, note=reason)
        gate.revoke()
        return phone_page(request, note="PIN saved. Every phone already paired has to type it "
                                        "again, so old ones cannot stay in by accident.")

    @app.post("/phone/unlock", response_class=HTMLResponse)
    def phone_unlock(request: Request, pin: str = Form(""), back: str = Form("/today")):
        token = gate.unlock(pin)
        if not token:
            status = gate.status()
            why = (f"Wrong PIN. {net.MAX_WRONG - status['wrong']} tries left before a "
                   f"{net.COOLDOWN_MINUTES}-minute wait." if not status["locked"] else
                   f"Too many wrong tries - the PIN box wakes up again in "
                   f"{status['locked_minutes']} minutes.")
            return templates.TemplateResponse(
                request, "gate.html",
                {"has_pin": True, "back": back, "status": status, "note": why, "local": False},
                status_code=401)
        # A relative path only, so a crafted ?back= can never send the phone somewhere else.
        target = back if back.startswith("/") and not back.startswith("//") else "/today"
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(net.COOKIE, token, max_age=60 * 60 * 24 * 365,
                            httponly=True, samesite="lax")
        return response

    @app.post("/phone/lock", response_class=HTMLResponse)
    def phone_lock(request: Request):
        gate.revoke()
        response = phone_page(request, note="Locked. Every phone has to answer with the PIN "
                                            "again, including one you no longer own.")
        response.delete_cookie(net.COOKIE)
        return response

    # ---- the agent ------------------------------------------------------------
    # Assembled here, at the end, because the point of the kit is that it hands the tools
    # the functions above instead of a second copy of them. Two ways to resolve a path or
    # write a day is two ways to be wrong.
    staged_dir = state_dir / "staged"

    def agent_photos():
        """(Path, kind, name) for every file she could genuinely post, read out of the
        folders themselves - a tool never gets to name a path it wants."""
        found = []
        for folder, root, kind, suffixes in (
                (inbox_dir, "", "photo", IMAGE_SUFFIXES),
                (edited_dir, "edited/", "photo", IMAGE_SUFFIXES),
                (clips_dir, "", "clip", clipmod.VIDEO_SUFFIXES),
                (clips_edited, "edited/", "clip", clipmod.VIDEO_SUFFIXES)):
            if folder.is_dir():
                found += [(p, kind, root + p.name) for p in sorted(folder.iterdir())
                          if p.is_file() and p.suffix.lower() in suffixes]
        return found

    def agent_edit(src: Path, recipe: list) -> Path:
        """The editor's own Save button as a call: a new file in edited/ plus its recipe
        sidecar and a line in the edit log. The source is never touched."""
        recipe = normalize(recipe)
        image = edit_file(src, recipe)
        png = image.mode != "RGB"
        edited_dir.mkdir(parents=True, exist_ok=True)
        dst = next_name(edited_dir, src.stem[:60], ".png" if png else ".jpg")
        image.save(dst, "PNG" if png else "JPEG", quality=SAVE_QUALITY)
        dst.with_suffix(".json").write_text(json.dumps(recipe, indent=1), encoding="utf-8")
        log_ops(src, dst, recipe)
        return dst

    kit = Kit(
        db=db, engine=engine,
        paths={"root": state_dir, "inbox": inbox_dir, "edited": edited_dir,
               "clips": clips_dir, "staged": staged_dir},
        entries=lambda: load_playbook()[0],
        answers=db.get_interview,
        plan=plan_or_none,
        rows=metrics_rows,
        save_rows=store_rows,
        build_day=lambda day: day_for(db.get_interview(), plan_or_none(), day),
        day_payload=day_payload,
        save_day=db.save_day,
        photos=agent_photos,
        remember=remember,
        save_edit=agent_edit,
        frames_landed=frames_landed,
    )
    app.state.kit = kit

    @app.get("/agent", response_class=HTMLResponse)
    def agent_page(request: Request, note: str = ""):
        grants = db.get_grants()
        mode = agent_modes.get(str(grants.get("mode", "")))
        open_ids = set(orchestrator.available(kit, mode))

        def tool_row(t):
            blocked = t.blocked(kit)
            return {"id": t.id, "name": t.name, "cap": t.cap, "describe": t.describe,
                    "ready": t.id in open_ids,
                    "why": (f"{mode.label} does not reach for {agent_modes.CAP_LABEL[t.cap]}"
                            if not mode.allows(t.cap) else
                            (f"not yet: {blocked}" if blocked else ""))}

        runs = db.recent_runs(5)
        worked = {agent_roster.owner(s["tool"]) for r in runs[:1] for s in r["steps"]
                  if s["kind"] == "did"}
        benches = []
        for desk in agent_roster.desks():
            rows = [tool_row(t) for t in desk.staffed()]
            benches.append({"id": desk.id, "name": desk.name, "line": desk.line, "tools": rows,
                            "ready": sum(1 for r in rows if r["ready"]),
                            "worked": desk.name in worked})
        for record in runs:
            for step in record["steps"]:
                tool = agent_tools.REGISTRY.get(step["tool"])
                step["name"] = tool.name if tool else step["tool"]
                step["desk"] = agent_roster.owner(step["tool"])
                step["lines"] = orchestrator.narrate(step["detail"])
        pending = db.pending_steps()
        for step in pending:
            tool = agent_tools.REGISTRY.get(step["tool"])
            step["name"] = tool.name if tool else step["tool"]
        return page(request, "agent.html", note=note, mode=mode, modes=agent_modes.MODES,
                    cap_label=agent_modes.CAP_LABEL, granted=grants["auto"],
                    runs=runs, pending=pending, next_move=orchestrator.next_move(kit),
                    benches=benches, tool_count=len(agent_tools.REGISTRY))

    @app.post("/agent/run", response_class=HTMLResponse)
    def agent_run(request: Request, asked: str = Form(""), mode: str = Form(""),
                  desk: str = Form("")):
        """One ask in, one recorded run out. The mode travels with the ask, and the last
        one she used is the box's default next time. Naming a desk is the same run with the
        bench already chosen: only that desk's tools are planned, and the history says she
        picked it rather than the sentence guessing."""
        chosen = agent_modes.get(mode or str(db.get_grants().get("mode", "")))
        db.save_grants(db.get_grants()["auto"], chosen.id)
        record = orchestrator.run(kit, asked.strip(), chosen.id, desk.strip())
        return agent_page(
            request, note=f"{asked.strip() or 'The growth loop'} - {record['summary']}, "
                          f"planned by {record['planner']}.")

    @app.post("/agent/step", response_class=HTMLResponse)
    def agent_step(request: Request, step: str = Form("")):
        """Her press is the authorisation. The step keeps its place in the history and its
        verdict changes from advised to whatever actually happened."""
        try:
            row = orchestrator.carry_out(kit, int(step))
        except (TypeError, ValueError):
            row = None
        note = ("That step is either already carried out or is refused by the mode you set - "
                "change the mode and ask again." if row is None else row["summary"])
        return agent_page(request, note=note)

    @app.get("/engine", response_class=HTMLResponse)
    def engine_page(request: Request, note: str = ""):
        """The key box. Nothing here is a mock: saving changes the object every other
        page already holds, and testing makes one real call and reports what came back."""
        return page(request, "engine.html", note=note, mask=config.mask,
                    model=config.model, live=engine.name != "offline",
                    default_model=DEFAULT_MODEL)

    @app.post("/engine/save", response_class=HTMLResponse)
    async def engine_save(request: Request):
        nonlocal config
        form = await request.form()
        key = str(form.get("api_key", "")).strip()
        model = str(form.get("model", "")).strip() or DEFAULT_MODEL
        # An empty box means "keep the key I already saved", not "delete it" - she is
        # changing the model, not signing out of her own account.
        keep = key or config.api_key
        cfg = Config(api_key=keep, engine_name="gemini" if keep else "offline", model=model,
                     path=config.path)
        cfg.write()
        engine.engine = cfg.build_engine()
        app.state.config = config = cfg
        if cfg.api_key:
            return engine_page(request, note=f"Saved. The app now asks {engine.name} "
                                             f"({cfg.model}) and the key on file ends "
                                             f"{cfg.mask}.")
        return engine_page(request, note="Saved. With no key the app runs offline: every "
                                         "page still works, and anything needing the model "
                                         "says it was not asked rather than inventing an answer.")

    @app.post("/engine/test", response_class=HTMLResponse)
    async def engine_test(request: Request):
        """One real call, timed, with whatever it said - including if it said nothing."""
        form = await request.form()
        key = str(form.get("api_key", "")).strip() or config.api_key
        model = str(form.get("model", "")).strip() or DEFAULT_MODEL
        if not key:
            return engine_page(request, note="There is no key to test yet - type one in first.")
        from src.engines.gemini import GeminiEngine

        probe = GeminiEngine(key=key, model=model)
        schema = {"type": "object", "required": ["said"], "properties": {"said": {"type": "string"}}}
        started = time.perf_counter()
        try:
            data = probe.complete_json("Answer in JSON only.", "Reply with the single word ready.",
                                       schema)
        except Exception as exc:
            return engine_page(request, note=f"{type(exc).__name__}: {exc} - the key was not "
                                             "saved and nothing was charged to it beyond this "
                                             "one attempt.")
        took = time.perf_counter() - started
        if not data:
            return engine_page(request, note=f"The call came back empty after {took:.1f}s. "
                                             "Nothing was saved.")
        return engine_page(request, note=f"{model} answered {data.get('said', '')!r} in "
                                         f"{took:.1f}s. The connection works; press Save to "
                                         "keep it.")

    @app.post("/grants", response_class=HTMLResponse)
    async def grants_save(request: Request):
        """Authorise a whole class of routine work once instead of approving every step."""
        form = await request.form()
        caps = [str(c) for c in form.getlist("cap") if str(c) in agent_modes.CAPS]
        chosen = agent_modes.get(str(form.get("mode", "")))
        db.save_grants(caps, chosen.id)
        return agent_page(request, note="Standing permission now covers " +
                                        (", ".join(agent_modes.CAP_LABEL[c] for c in caps)
                                         or "nothing") + ".")

    return app


app = create_app()
