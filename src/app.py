from datetime import date
from pathlib import Path
import io
import json
import shutil
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import Config
from src.db import DB
from src.engines.offline import OfflineEngine
from src.metrics.adapt import analyse, apply
from src.metrics.ingest import read_csv, read_quick
from src.media.aesthetic import WEIGHTS, judge_photo
from src.media.clean import fix
from src.media.edit import PRESETS, SAVE_QUALITY, SLIDERS, edit_file, normalize
from src.media.judge import IMAGE_SUFFIXES, inbox_files, judge, measure
from src.playbook.store import Store
from src.strategist.daily import build_day
from src.strategist.interview import Interview, InterviewAnswers
from src.strategist.niche import brief, rank, score_candidates
from src.strategist.plan import Plan, compose_plan

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
    engine = config.build_engine()
    db = DB(db_path or DATA_DIR / "app.sqlite3")
    state_dir = Path(db_path or DATA_DIR / "app.sqlite3").parent
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    app = FastAPI(title="Fame Strategist", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    inbox_dir = state_dir / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/inbox", StaticFiles(directory=str(inbox_dir)), name="inbox")
    app.state.engine = engine
    app.state.db = db
    app.state.config = config

    def page(request, name, **ctx):
        entries, pending = load_playbook()
        return templates.TemplateResponse(
            request,
            name,
            {
                "active": name.removesuffix(".html"),
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
        plan = compose_plan(entries, answers, hypotheses, OfflineEngine(), date.today())
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
        plan = compose_plan(entries, answers, hypotheses, OfflineEngine(), date.today())
        db.save_current_plan(plan.to_dict())
        return page(request, "plan.html", plan=plan, entries=entries)

    @app.get("/plan", response_class=HTMLResponse)
    def show_plan(request: Request):
        plan = plan_or_none()
        if plan is None:
            return niches(request)
        return page(request, "plan.html", plan=plan, entries=load_playbook()[0])

    @app.get("/today", response_class=HTMLResponse)
    def today(request: Request, on: str | None = None):
        answers, plan = db.get_interview(), plan_or_none()
        if not answers or not plan:
            return home(request)
        day = date.fromisoformat(on) if on else date.today()
        entries, _pending = load_playbook()
        d = build_day(plan, entries, answers, day, engine)
        logged = db.get_days(day.isoformat(), day.isoformat())
        return page(request, "today.html", today=d, plan=plan, answers=answers,
                    posted=bool(logged and logged[0]["done"]), day_iso=day.isoformat())

    @app.post("/today/done", response_class=HTMLResponse)
    def today_done(request: Request, on: str = Form(...)):
        db.save_day(on, {"posted": True})
        db.mark_done(on)
        return today(request, on=on)

    @app.get("/sources", response_class=HTMLResponse)
    def sources(request: Request, tier: str | None = None):
        entries, pending = load_playbook()
        counts = {t: len([e for e in entries if e.confidence.value == t])
                  for t in ["proven", "strong", "contested", "folklore"]}
        shown = [e for e in entries if e.confidence.value == tier] if tier in counts else entries
        return page(request, "sources.html", entries=shown, all_entries=entries, pending=pending,
                    counts=counts, tier=tier)

    def store_rows(rows) -> None:
        """Normalised to the app's own CSV so the apply step re-reads exactly what was read now."""
        state_dir.mkdir(exist_ok=True)
        lines = ["post_ref,views,avg_watch_pct,follows_gained,hypothesis"]
        lines += [
            f"{r.post_ref},{r.views},{r.avg_watch_pct},{r.follows_gained},{r.hypothesis}"
            for r in rows
        ]
        (state_dir / "metrics-last.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def numbers_page(request, rows=None, note=""):
        plan = plan_or_none()
        if rows is None:
            return page(request, "numbers.html", adjustments=[], plan=plan, note=note, rows=[])
        return page(
            request, "numbers.html", adjustments=analyse(rows, plan) if plan else [],
            plan=plan, note=note, rows=rows,
        )

    @app.get("/numbers", response_class=HTMLResponse)
    def numbers(request: Request):
        return numbers_page(request)

    @app.post("/numbers", response_class=HTMLResponse)
    async def numbers_input(request: Request):
        form = await request.form()
        if plan_or_none() is None:
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
        store_rows(rows)
        return numbers_page(request, rows=rows, note=f"{len(rows)} posts read.")

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

    edited_dir = inbox_dir / "edited"

    def inbox_file(name: str) -> Path | None:
        """Only her inbox folder or her saved edits - never a path somebody typed."""
        target = (inbox_dir / name).resolve()
        if target.parent not in (inbox_dir.resolve(), edited_dir.resolve()) or not target.is_file():
            return None
        return target

    def recipe_of(raw: str) -> list:
        try:
            data = json.loads(raw or "[]")
        except ValueError:
            return []
        return data if isinstance(data, list) else []

    def next_name(directory: Path, stem: str, suffix: str) -> Path:
        dst = directory / f"{stem}{suffix}"
        n = 2
        while dst.exists():
            dst = directory / f"{stem}-{n}{suffix}"
            n += 1
        return dst

    def preview_bytes(src: Path, recipe: list, edge: bool) -> bytes:
        buf = io.BytesIO()
        edit_file(src, recipe, proxy=edge).save(buf, "JPEG", quality=82 if edge else SAVE_QUALITY)
        return buf.getvalue()

    @app.get("/photos", response_class=HTMLResponse)
    def photos(request: Request, note: str = ""):
        rows = [{"r": r, "j": judge_photo(inbox_dir / r.name, r) if not r.error else None}
                for r in judge(inbox_files(inbox_dir))]
        saved = sorted(p for p in (edited_dir.glob("*") if edited_dir.is_dir() else [])
                       if p.suffix.lower() in IMAGE_SUFFIXES)
        return page(request, "photos.html", readings=rows, inbox=str(inbox_dir), note=note,
                    weights=WEIGHTS, saved=saved)

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
        judged = judge_photo(src, measure(src))
        fixes = judged.fixes or judged.reading.fixes
        if not fixes:
            return photos(request, note="Nothing left for the editor to do - that frame is already clean.")
        dst = fix(src, inbox_dir / "clean", fixes, tilt=judged.tilt, focus=judged.focus)
        after = judge_photo(dst, measure(dst))
        moved = (f"score {judged.score} to {after.score}" if after.score != judged.score
                 else f"score still {judged.score}")
        return photos(request, note=f"Wrote {dst.name} with {' + '.join(fixes)} - {moved}. "
                                    "The original was not touched.")

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
                    presets_json=json.dumps(PRESETS), recipe_json=json.dumps(carried),
                    judged=judge_photo(src, reading),
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
        png = str(form.get("format", "")) == "png"
        edited_dir.mkdir(parents=True, exist_ok=True)
        dst = next_name(edited_dir, src.stem[:60], ".png" if png else ".jpg")
        edit_file(src, recipe).save(dst, "PNG" if png else "JPEG", quality=SAVE_QUALITY)
        dst.with_suffix(".json").write_text(json.dumps(recipe, indent=1), encoding="utf-8")
        after = judge_photo(dst, measure(dst))
        return RedirectResponse(
            f"/edit?name={quote(f'edited/{dst.name}')}&note=Saved+{quote(dst.name)}+with+{len(recipe)}"
            "+edits.+Score+" + str(after.score) + ".+The+original+was+not+touched.", status_code=303)

    return app


app = create_app()
