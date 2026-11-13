from datetime import date, timedelta
from pathlib import Path
import hashlib
import io
import json
import shutil
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from src.config import Config
from src.db import DB
from src.engines.offline import OfflineEngine
from src.media import clip as clipmod
from src.media.clipjudge import CLIP_LABELS, CLIP_WEIGHTS, judge_clip, suggest
from src.metrics.adapt import analyse, apply
from src.metrics.ingest import read_csv, read_quick
from src.media.aesthetic import WEIGHTS, judge_photo
from src.media.clean import fix
from src.media.edit import PRESETS, SAVE_QUALITY, SLIDERS, edit_file, normalize
from src.media.judge import IMAGE_SUFFIXES, inbox_files, judge, measure
from src.playbook.store import Store
from src.strategist.coach import CADENCE_DAYS, build_agenda
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
        entries, _pending = load_playbook()
        d = build_day(plan, entries, answers, day, engine)
        logged = db.get_days(day.isoformat(), day.isoformat())
        return page(request, "today.html", today=d, plan=plan, answers=answers,
                    posted=bool(logged and logged[0]["done"]), day_iso=day.isoformat(),
                    attached=(logged[0].get("attach") if logged else None),
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
        rows = []
        path = state_dir / "metrics-last.csv"
        if path.is_file():
            try:
                rows = read_csv(path)
            except ValueError:
                rows = []
        landed, weak = frames_landed(start, end)
        agenda = build_agenda(
            plan=plan, days=db.get_days(start.isoformat(), end.isoformat()), rows=rows,
            landed=landed, weak=weak, entries=load_playbook()[0], today=end,
            engine_name=engine.name, offline=engine.name == "offline")
        return page(request, "weekly.html", agenda=agenda, plan=plan)

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

    return app


app = create_app()
