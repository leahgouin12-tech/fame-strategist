"""The hands. Every tool here calls code that already works elsewhere in the app -
nothing in this file pretends, and nothing in it reaches an account.

The kit is built in src/app.py and is the only way a tool touches the outside world:

    kit.db, kit.engine            storage and the live model (or the labelled stub)
    kit.entries()                 the playbook
    kit.answers() kit.plan()      her interview, her eight weeks
    kit.rows() kit.save_rows()    the last metrics import
    kit.build_day(date)           one day's shot list
    kit.day_payload(iso) kit.save_day(iso, payload)
    kit.photos()                  [(Path, kind, rel)] she could actually post
    kit.remember(path, kind, j)   store a score under its file name
    kit.save_edit(path, recipe)   write an edited file, returns the Path
    kit.frames_landed(start, end) (landed, weak) inside a window
    kit.paths                     {"root", "inbox", "edited", "clips", "staged"}
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from src.experiment import ledger as experiment
from src.experiment import repurpose
from src.media.aesthetic import WEIGHTS, judge_photo
from src.media.edit import PRESETS, edit_file
from src.media.judge import measure
from src.media.appearance import read_file as read_face
from src.metrics import correlate
from src.metrics.adapt import DATA_FLOOR, analyse
from src.metrics.adapt import apply as apply_adapt
from src.metrics.ingest import read_quick
from src.money import rate as money
from src.playbook import research
from src.strategist import engage, slots, voice
from src.strategist.coach import CADENCE_DAYS, _week_at, build_agenda
from src.strategist.daily import subject_of
from src.strategist.interview import Interview
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan


@dataclass
class Outcome:
    """kind is the whole honesty of this layer.

    did      - state changed: a row written, a file created, a plan replaced.
    advised  - the agent produced a recommendation and touched nothing.
    skipped  - it could not run, with the reason, rather than a fake success.
    """
    kind: str
    summary: str
    detail: dict = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.kind == "did"


def did(summary, **detail) -> Outcome:
    return Outcome("did", summary, detail)


def advised(summary, **detail) -> Outcome:
    return Outcome("advised", summary, detail)


def skipped(why) -> Outcome:
    return Outcome("skipped", why)


@dataclass(frozen=True)
class Kit:
    """The whole world a tool is allowed to touch, handed over by the app.

    The callables are the web layer's own functions, not copies of them. src/app.py
    already knows how to read a day, resolve a safe path and write an edited file, and a
    second implementation of any of those in here is how two versions of the truth get
    made - one of which is wrong when the file layout changes.
    """
    db: object
    engine: object
    paths: dict
    entries: object
    answers: object
    plan: object
    rows: object
    save_rows: object
    build_day: object
    day_payload: object
    save_day: object
    photos: object
    remember: object
    save_edit: object
    frames_landed: object


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    dept: str
    cap: str
    needs: tuple[str, ...]
    args: tuple[str, ...]
    describe: str
    run: object

    def blocked(self, kit) -> str:
        for need in self.needs:
            if need == "answers" and kit.answers() is None:
                return "the interview has not been answered"
            if need == "complete" and not _complete(kit):
                return "the interview is incomplete, so a plan built on it would be fiction"
            if need == "plan" and kit.plan() is None:
                return "there is no eight-week plan yet"
            if need == "rows" and not kit.rows():
                return "no numbers have been imported"
            if need == "photos" and not kit.photos():
                return "the inbox holds no readable picture"
            if need == "voice" and not kit.db.get_voice():
                return "she has not pasted anything she wrote, so the voice is a guess"
        return ""


def _complete(kit) -> bool:
    answers = kit.answers()
    return bool(answers and Interview.complete(answers))


# ---- research ---------------------------------------------------------------

def library(kit, topic: str = "", limit: int = 8):
    low = topic.strip().lower()
    hits = [e for e in kit.entries()
            if not low or low in " ".join([e.id, e.claim, e.mechanism] + e.tags).lower()]
    tiers: dict[str, int] = {}
    for e in hits:
        tiers[e.confidence.value] = tiers.get(e.confidence.value, 0) + 1
    picked = [{"id": e.id, "claim": e.claim, "tier": e.confidence.value, "as_of": e.as_of.isoformat(),
               "does_not_claim": e.does_not_claim} for e in hits[:limit]]
    for row in picked:
        kit.db.remember("finding", row["claim"], row["id"], row["as_of"])
    n = len(hits)
    return did(f"{n} sourced claim{'s' if n != 1 else ''} on {topic.strip() or 'the whole playbook'}.",
               tiers=tiers, picked=picked, contested=tiers.get("contested", 0))


def week_findings(kit):
    entries, plan = kit.entries(), kit.plan()
    week = _week_at(plan, date.today()) if plan else None
    run = research.run(entries, date.today(), week.focus_entry_ids if week else ())
    answers = kit.answers()
    text = research.brief(
        platforms=getattr(answers, "platforms", []) or [],
        hypotheses=plan.hypotheses if plan else [],
        chosen=week.experiment if week else "",
        hours_per_week=getattr(answers, "hours_per_week", 0) or 0)
    kit.db.remember("brief", text, "playbook", date.today().isoformat())
    old = [f.id for f in run.findings if f.days_old > 365]
    return did(f"{run.count} finding{'s' if run.count != 1 else ''} read against this week; "
               f"{len(old)} are more than a year old.",
               in_week=[f.id for f in run.findings if f.in_this_week], stale=old, note=run.note)


def coach(kit):
    end = date.today()
    start = end - timedelta(days=CADENCE_DAYS - 1)
    landed, weak = kit.frames_landed(start, end)
    agenda = build_agenda(
        plan=kit.plan(), days=kit.db.get_days(start.isoformat(), end.isoformat()), rows=kit.rows(),
        landed=landed, weak=weak, entries=kit.entries(), today=end,
        engine_name=kit.engine.name, offline=kit.engine.name == "offline",
        spend=kit.db.get_spend())
    for move in agenda.moves:
        kit.db.remember("proposal", move.text, move.basis, end.isoformat())
    return advised(
        f"{len(agenda.moves)} move proposed from {agenda.coverage.posted} of "
        f"{agenda.coverage.planned} posted days. Accepted ones are applied by her, not here.",
        window=agenda.window, moves=[{"kind": m.kind, "text": m.text, "basis": m.basis}
                                     for m in agenda.moves],
        missed=agenda.coverage.missed, generic=agenda.performance.generic,
        posts=agenda.performance.posts)


# ---- strategy ---------------------------------------------------------------

def niches(kit, limit: int = 5):
    top = rank(score_candidates(kit.entries(), kit.answers()))[:int(limit)]
    return advised("Ranked against her footage, hours, gear and comfort - not a trend page.",
                   ranked=[{"name": h.name, "score": round(h.compute_total(), 1),
                            "because": list(h.evidence_ids)[:6], "risk": h.risk}
                           for h in top])


def build_plan(kit):
    answers = kit.answers()
    hypotheses = rank(score_candidates(kit.entries(), answers))
    gone = experiment.dropped(kit.db.recall("verdict", limit=50))
    plan = compose_plan(kit.entries(), answers, hypotheses, kit.engine, date.today(),
                        dropped=gone)
    kit.db.save_current_plan(plan.to_dict())
    return did(f"Eight weeks built around {hypotheses[0].name if hypotheses else 'one '
                                        'unspecified test'}"
               + (f", with {len(gone)} arm{'s' if len(gone) != 1 else ''} the lab dropped kept "
                  "out of it." if gone else "."),
               weeks=len(plan.weeks), start=plan.start_date, dropped=gone,
               because=plan.verdict_notes,
               experiments=[w.experiment for w in plan.weeks])


def shot_list(kit, on: str = ""):
    iso = on or date.today().isoformat()
    day = kit.build_day(date.fromisoformat(iso))
    payload = kit.day_payload(iso)
    payload["planned"] = {"hypothesis": day.hypothesis, "format": day.format,
                          "shots": len(day.shots), "origin": day.copy_origin}
    kit.save_day(iso, payload)
    return did(f"{len(day.shots)} takes written for {iso}.", iso=iso, hook=day.hook,
               takes=[s.desc for s in day.shots], seconds=sum(s.seconds for s in day.shots),
               origin=day.copy_origin)


def mark_posted(kit, on: str = ""):
    iso = on or date.today().isoformat()
    payload = kit.day_payload(iso)
    payload["posted"] = True
    kit.save_day(iso, payload)
    kit.db.mark_done(iso)
    return did(f"{iso} is recorded as posted. That is evidence now, not an intention.", iso=iso)


# ---- making -----------------------------------------------------------------

def judge_photos(kit):
    out, seen = [], set()
    for path, kind, rel in kit.photos():
        if kind != "photo" or rel in seen:
            continue
        seen.add(rel)
        reading = measure(path)
        if reading.error:
            out.append({"file": rel, "error": reading.error})
            continue
        judged = judge_photo(path, reading, kit.db.get_rubric() or WEIGHTS)
        kit.remember(path, "photo", judged)
        out.append({"file": rel, "score": round(judged.score, 1), "band": judged.band,
                    "fixes": list(judged.fixes)[:3], "ideas": list(judged.ideas)[:2],
                    "cannot_see": reading.limit})
    scored = [o for o in out if "score" in o]
    ranked = sorted(scored, key=lambda o: -o["score"])
    return did(f"Read {len(ranked)} frame{'s' if len(ranked) != 1 else ''} on this machine, "
               f"and stored each score under its file name.",
               ranked=ranked, best=ranked and ranked[0]["file"],
               unreadable=[o for o in out if "error" in o])


def polish(kit, look: str = "clean"):
    look = str(look)
    if look not in PRESETS:
        return skipped(f"{look!r} is not one of the looks this app has: "
                       f"{', '.join(sorted(PRESETS))}.")
    photos = [(p, rel) for p, kind, rel in kit.photos() if kind == "photo"]
    if not photos:
        return skipped("nothing to polish: the inbox holds no picture.")
    by_rel = {rel: p for p, rel in photos}
    scores = kit.db.get_scores()
    target = None
    for ref, row in sorted(scores.items(), key=lambda kv: -kv[1]["score"]):
        for rel, path in by_rel.items():
            if correlate.stem(rel) == ref:
                target = (path, rel)
                break
        if target:
            break
    if target is None:
        target = photos[0]
    src, rel = target
    written = kit.save_edit(src, PRESETS[look])
    after = judge_photo(written, measure(written), kit.db.get_rubric() or WEIGHTS)
    kit.remember(written, "photo", after)
    return did(f"{rel} went through the {look} look and scored {round(after.score, 1)}.",
               source=rel, written=written.name, look=look, band=after.band)


def packs(kit, platform: str = ""):
    day = kit.build_day(date.today())
    profile = voice.learn(kit.db.get_voice())
    subject = subject_of(kit.answers())
    variants = voice.package(subject, day.hypothesis, date.today(), profile)
    if platform:
        variants = [v for v in variants if v.platform == platform] or variants
    return advised(f"{len(variants)} platform version{'s' if len(variants) != 1 else ''} of "
                   f"today's line, cut from her own samples.",
                   variants=[{"platform": v.platform, "block": v.block, "why": v.why,
                              "alt_prompt": v.alt_prompt} for v in variants],
                   learned=profile.learned)


# ---- numbers ----------------------------------------------------------------

def take_numbers(kit, text: str = ""):
    if not str(text).strip():
        return skipped("no numbers given. Three per post: reference, views, watched %, "
                       "follows gained.")
    try:
        rows = read_quick(str(text))
    except ValueError as exc:
        return skipped(f"that did not read as numbers: {exc}")
    if not rows:
        return skipped("nothing in that block parsed as a post with a view count.")
    kit.save_rows(rows)
    return did(f"{len(rows)} post{'s' if len(rows) != 1 else ''} stored as the app's own ledger.",
               posts=[{"ref": r.post_ref, "views": r.views, "platform": r.platform} for r in rows],
               under_floor=len(rows) < DATA_FLOOR, floor=DATA_FLOOR)


def adapt(kit):
    rows, plan = kit.rows(), kit.plan()
    found = analyse(rows, plan)
    if not found:
        return advised(f"{len(rows)} rows read, and nothing moved far enough to rewrite the "
                       f"plan. Below {DATA_FLOOR} posts this app declines to have an opinion.")
    changed = apply_adapt(plan, found)
    kit.db.save_current_plan(changed.to_dict())
    return did(f"{len(found)} change{'s' if len(found) != 1 else ''} applied to the weeks "
               f"still ahead of you.",
               adjustments=[{"kind": a.kind, "target": a.target, "reason": a.reason,
                             "evidence": a.evidence_ids} for a in found])


def lab_read(kit):
    """What the arms prove, in the ledger's words - it reads and reports and changes nothing,
    because a decision about which hypothesis to drop is hers until she says otherwise."""
    rows = kit.rows()
    if not rows:
        return skipped("no numbers are stored, so there is nothing to group into arms.")
    got = experiment.ledger(rows)
    call = experiment.verdict(got, kit.plan())
    return advised(f"{call.headline}",
                   state=call.state, arms=[{"label": a.label, "posts": a.n, "rate": a.rate,
                                            "watch": a.watch} for a in got.arms],
                   unlabelled=got.unlabelled, lines=call.lines, missing=call.missing,
                   kept=call.winner, dropped=call.loser, where="/lab")


def lab_file(kit):
    """Files the posts that carry no hypothesis under the arm the plan says is running now.

    This is the step that makes the comparison possible at all: the stored rows have an
    empty hypothesis column, and the ranking in metrics.adapt can only read a column that
    somebody filled in."""
    rows = kit.rows()
    if not rows:
        return skipped("no numbers are stored, so there is nothing to file.")
    arm = experiment.arm_for(kit.plan(), date.today())
    if not arm:
        return skipped("this week names no hypothesis, so there is no arm to file them under.")
    tagged = experiment.tag(rows, arm)
    moved = sum(1 for r, t in zip(rows, tagged) if r.hypothesis != t.hypothesis)
    if not moved:
        return did(f"Nothing to file: all {len(rows)} stored posts already carry an arm.",
                   filed=0, arm=arm, posts=len(rows))
    kit.save_rows(tagged)
    return did(f"Filed {moved} of {len(rows)} stored posts under {arm}.",
               filed=moved, arm=arm, posts=len(rows), where="/lab")


def repurpose_make(kit, limit: int = 2):
    """Rebuild the posts the ledger ranks best for the frames they have never run in.

    Files are written next to her saved edits and every post that could not be touched is
    named, so what comes back is a list of things that exist plus the reasons for the ones
    that do not - never a claim that a pass ran."""
    rows = kit.rows()
    if not rows:
        return skipped("no numbers are stored, so nothing has been ranked to rebuild.")
    got = experiment.ledger(rows)
    if not got.arms:
        return skipped("no stored post carries an arm label, so there is no winning arm to "
                       "remake. File them first.")
    answers = kit.answers()
    passed = repurpose.run(got, rows, voice.learn(kit.db.get_voice()), date.today(),
                           subject_of(answers) if answers else "",
                           Path(kit.paths["inbox"]), Path(kit.paths["clips"]),
                           Path(kit.paths["edited"]), limit=max(1, int(limit)))
    if not passed.cuts:
        return advised(passed.headline, cuts=[], skipped=passed.skipped, where="/repurpose")
    return did(passed.headline,
               cuts=[{"from": c.ref, "arm": c.arm, "platform": c.platform, "shape": c.shape,
                      "kind": c.kind, "file": c.file} for c in passed.cuts],
               skipped=passed.skipped, posts=passed.posts, where="/repurpose")


def best_window(kit):
    report = slots.report(kit.rows())
    if not report.measured:
        return advised(report.note, measured=False, need=report.need)
    top = report.windows[0]
    return advised(f"Your own {report.timed} timed posts put {top.hours} ahead "
                   f"(median {top.median_views} views over {top.posts} posts).",
                   measured=True,
                   windows=[{"hours": w.hours, "block": w.block, "posts": w.posts,
                             "median_views": w.median_views, "thin": w.thin}
                            for w in report.windows])


# ---- money ------------------------------------------------------------------

def money_quote(kit):
    """What a paid post would pay on her own numbers, and what it costs her before it pays.

    Three sources, each named in the result: the median comes from the posts she imported, the
    band from dated claims in the playbook, the floor from the two numbers she typed herself.
    Nothing here is in touch with a brand, and nothing here is a price anyone agreed to.
    """
    rows = kit.rows()
    if not rows:
        return skipped("no numbers are stored, so there are no median views to price.")
    terms = kit.db.get_terms()
    made, thin, uncited = money.quotes(rows, kit.entries(), terms["hourly"], terms["minutes"])
    if not made:
        why = thin or uncited
        return advised("Nothing here is priceable yet - " + "; ".join(why),
                       quotes=[], thin=thin, uncited=list(uncited), where="/money")
    top = max(made, key=lambda q: q.anchor)
    lines = [f"{q.platform}: {q.line}" for q in made]
    for note in thin:
        lines.append(f"Refused: {note}.")
    kit.db.remember("quote", " ".join(lines), "money/rate", date.today().isoformat())
    return advised(
        f"{len(made)} platform{'s' if len(made) != 1 else ''} priced from her own posts, with "
        f"{top.platform} at {money.UNIT}{top.anchor:,.0f} as the number to open on"
        + (" and no floor set yet" if not top.floor else "") + ".",
        quotes=[{"platform": q.platform, "posts": q.posts, "median_views": q.median_views,
                 "low": q.low, "high": q.high, "anchor": q.anchor, "floor": q.floor,
                 "under_floor": q.under_floor, "line": q.line,
                 "caveats": q.missing} for q in made],
        thin=thin, uncited=list(uncited), addons=money.addon_lines(top.anchor),
        where="/money")


def money_label(kit, text: str = ""):
    """Does the post say it is an ad - read off the caption, not off a hope.

    With no text it checks the post already staged in the composer, which is the one a brand
    would actually be liable for."""
    staged = kit.db.get_staged()
    body = text or (staged.get("caption") or "")
    surface = "" if text else (staged.get("surface") or staged.get("platform") or "")
    if not body.strip():
        return skipped("no caption to read - nothing is staged and no text came with the ask.")
    got = money.check_disclosure(body, surface)
    return advised(
        got.line, status=got.status, safe_to_post=got.safe_to_post, notes=got.notes,
        surface=surface or "unstated", checked="staged post" if not text else "the text given",
        needs_video=got.needs_video, in_video=got.in_video, where="/money")


# ---- community & queue ------------------------------------------------------

def reply_drafts(kit):
    store = kit.db.get_engage()
    drafts = engage.plan(engage.parse(store["comments"]), voice.learn(kit.db.get_voice()))
    worth = [d for d in drafts if not d.refused]
    return advised(f"{len(worth)} reply written; {len(drafts) - len(worth)} refused because "
                   f"they need a fact only she has. Nothing was sent.",
                   drafts=[{"to": d.author, "text": d.text, "why": d.why} for d in worth],
                   queue=engage.queue_note(drafts))


def stage(kit, on: str = ""):
    """The strongest thing possible without touching an account: everything for the day in
    one folder, so posting is a drag rather than six copies and four guesses."""
    iso = on or date.today().isoformat()
    when = date.fromisoformat(iso)
    day = kit.build_day(when)
    folder = kit.paths["staged"] / iso
    folder.mkdir(parents=True, exist_ok=True)
    tied = (kit.day_payload(iso).get("attach") or {}).get("file", "")
    report = slots.report(kit.rows())
    window = report.windows[0].hours if report.measured else "one you can hold for three weeks"
    rows = kit.rows()
    where = rows[0].platform if rows else ", ".join(getattr(kit.answers(), "platforms", []) or [])
    blocks = voice.package(subject_of(kit.answers()), day.hypothesis, when,
                           voice.learn(kit.db.get_voice()))
    (folder / "caption.txt").write_text(
        "\n\n".join([day.hook, day.caption, " ".join(day.hashtags)]), encoding="utf-8")
    (folder / "shot-list.txt").write_text("\n".join(day.as_checklist()), encoding="utf-8")
    (folder / "per-platform.txt").write_text(
        "\n\n---\n\n".join(v.block for v in blocks), encoding="utf-8")
    (folder / "this-day.md").write_text("\n".join([
        f"# {iso} - week {day.week_no} of 8",
        "",
        f"Testing **{day.hypothesis}**, as {day.format}, on {where or 'the platform you named'}.",
        f"Post inside: {window}.",
        f"File tied to this day: {tied or 'none picked yet - tick the takes, then tie one.'}",
        "",
        "## Drag these into the app",
        "",
        "- `caption.txt` - hook, caption and tags as one block.",
        "- `per-platform.txt` - the same line rewritten per platform.",
        "- `shot-list.txt` - the takes in filming order.",
        "",
        "## What this app did not do",
        "",
        "It did not post, and it cannot see your account: nothing here signed you in, and no "
        "scheduler uploads on its own. Alt text is yours - the app measures light, shape and "
        "steadiness, not what is in the frame.",
        "",
        f"Basis: {', '.join(day.sourced_from) or 'nothing sourced - treat this day as a draft.'}",
        f"{day.cost_note}",
    ]), encoding="utf-8")
    written = sorted(p.name for p in folder.iterdir() if p.is_file())
    return did(f"{iso} staged in data/staged/{iso}/ - {len(written)} files.",
               folder=f"data/staged/{iso}", files=written, window=window, tied=tied)


def recall(kit, limit: int = 12):
    rows = kit.db.recall(limit=int(limit))
    return advised(f"{len(rows)} thing{'s' if len(rows) != 1 else ''} this app already knows "
                   f"about you, with the date it was learned.", notes=rows)


REGISTRY: dict[str, Tool] = {}


def add(tool_id, name, dept, cap, needs=(), args=(), describe=""):
    def wrap(fn):
        REGISTRY[tool_id] = Tool(tool_id, name, dept, cap, tuple(needs), tuple(args),
                                 describe, fn)
        return fn
    return wrap


add("research.library", "Search the sourced library", "Research", "research", args=("topic",),
    describe="Finds documented claims on a topic with their tier, their date and what each "
             "one does not prove.")(library)
add("research.week", "Read the week's findings", "Research", "research", needs=("plan",),
    describe="Runs the playbook against the current week and states how much of it is out of "
             "date.")(week_findings)
add("research.coach", "Turn receipts into moves", "Measure", "analyse", needs=("plan",),
    describe="The coach reads posted days, landed frames and numbers, then proposes. "
             "A proposal is advice until she accepts it.")(coach)
add("strategy.niches", "Rank the niches", "Plan", "strategy", needs=("answers", "complete"),
    args=("limit",),
    describe="Scores every niche hypothesis against her own footage, hours, gear and "
             "comfort.")(niches)
add("strategy.build", "Build the eight weeks", "Plan", "strategy",
    needs=("answers", "complete"),
    describe="Composes the plan from the ranked hypotheses and makes it current.")(build_plan)
add("day.list", "Write the day's shot list", "Brief", "strategy", needs=("plan", "answers"),
    args=("on",),
    describe="One day's takes, beats and caption in filming order, saved under its "
             "date.")(shot_list)
add("day.mark", "Record a day as posted", "Brief", "queue", args=("on",),
    describe="Marks the day in the ledger - the only thing here that counts as "
             "evidence.")(mark_posted)
def read_faces(kit):
    """Describe what each frame does to the face in it.

    Deliberately no number that ranks a person, so there is nothing here to sort by and
    no "best" to hand back - the agent reports the sentences and the box it measured.
    """
    out, seen = [], set()
    for path, kind, rel in kit.photos():
        if kind != "photo" or rel in seen:
            continue
        seen.add(rel)
        read = read_face(path, kit.engine)
        out.append({"file": rel, "found": read.found, "where": read.placed,
                    "share": read.share, "words": read.words[:3],
                    "fixes": read.fixes[:2], "model": read.model_source})
    described = [o for o in out if o["found"]]
    return did(f"Described the face in {len(described)} frame"
               f"{'s' if len(described) != 1 else ''} - lighting, lens and backdrop, "
               f"never a score.",
               faces=out,
               not_measured=[o["file"] for o in out if not o["found"]])


add("media.judge", "Judge every picture in the inbox", "Make", "analyse", needs=("photos",),
    describe="Measures light, detail, placement and palette on this machine and stores every "
             "score under its file name.")(judge_photos)
add("media.face", "Describe what the frame does to the face", "Make", "analyse",
    needs=("photos",),
    describe="Measures the light fall, the mirror difference, the tone spread and the "
             "backdrop inside the face region. It reports sentences and fixes, not a "
             "score, and it never ranks a person.")(read_faces)
add("media.polish", "Export the best frame through a look", "Make", "make", needs=("photos",),
    args=("look",),
    describe="Runs the highest-scoring file through one of the saved looks and writes a new "
             "file. The source is never touched.")(polish)
add("copy.packs", "Cut the line for each platform", "Brief", "make",
    needs=("plan", "answers", "voice"), args=("platform",),
    describe="Rewrites today's hook and caption per platform from her own pasted "
             "writing.")(packs)
add("metrics.take", "Store numbers she typed", "Measure", "analyse", args=("text",),
    describe="Three numbers per post, parsed and kept as the app's own ledger.")(take_numbers)
add("metrics.adapt", "Let the numbers rewrite the plan", "Measure", "analyse",
    needs=("rows", "plan"),
    describe="Applies only the adjustments the data supports, and refuses under the "
             "floor.")(adapt)
add("metrics.window", "Name a posting window of her own", "Measure", "analyse",
    needs=("rows",),
    describe="Median views per block from her timed posts, or the honest refusal to "
             "guess.")(best_window)
add("experiment.arms", "Read what the arms prove", "Experimentation", "analyse",
    needs=("rows", "plan"),
    describe="Groups the stored posts by the hypothesis each ran under and states the verdict "
             "those numbers support, or exactly what is still missing.")(lab_read)
add("experiment.file", "File unlabelled posts under this week", "Experimentation", "queue",
    needs=("rows", "plan"),
    describe="Writes this week's hypothesis into the stored posts that carry no label, and "
             "leaves every labelled one alone.")(lab_file)
add("repurpose.cuts", "Rebuild the winning posts in other frames", "Repurposing", "make",
    needs=("rows",), args=("limit",),
    describe="Cuts the posts the ledger ranks best into the shape each placement wants and "
             "rewrites the copy for that placement from her own pasted samples. Names every "
             "post whose file this app does not hold instead of inventing one.")(repurpose_make)
add("money.quote", "Price a paid post", "Money", "analyse", needs=("rows",),
    describe="Median views from her own imported posts against the published cost per thousand, "
             "with the floor her time sets. It returns a band with the source and the source's "
             "own limit attached, and refuses a platform with too few posts to have a median.")(
    money_quote)
add("money.label", "Check the post says it is an ad", "Money", "analyse", args=("text",),
    describe="Reads the staged caption, or the text she gives, against the disclosure rule: "
             "whether the word is there, where it sits, whether the placement needs it in the "
             "video, and what no text check can see.")(money_label)
add("community.drafts", "Draft the replies", "Make", "queue",    describe="Writes replies to the comments she pasted in and refuses the ones needing a "
             "fact only she has. Nothing is sent.")(reply_drafts)
add("queue.stage", "Stage a day for posting", "Brief", "queue", needs=("plan", "answers"),
    args=("on",),
    describe="Writes the day's caption, per-platform lines, shot list and instructions into "
             "one folder.")(stage)
add("memory.recall", "Say what it already knows", "This machine", "research", args=("limit",),
    describe="The stored findings, briefs and proposals, newest first.")(recall)


def get(tool_id: str) -> Tool:
    return REGISTRY[tool_id]


def catalogue() -> list[dict]:
    return [{"id": t.id, "name": t.name, "dept": t.dept, "cap": t.cap, "needs": list(t.needs),
             "args": list(t.args), "describe": t.describe} for t in REGISTRY.values()]
