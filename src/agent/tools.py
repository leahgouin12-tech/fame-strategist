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
from src import accounts
from src.captions import tags as tag_tool
from src.captions import tone as tones
from src.captions import voice_register as caption_kit
from src.collab import pitch
from src.collab import store as collab_store
from src import language
from src.language import localise
from src.media.aesthetic import WEIGHTS, judge_photo
from src.media.edit import PRESETS, edit_file
from src.media.judge import measure
from src.media.appearance import read_file as read_face
from src.metrics import correlate
from src.metrics.adapt import DATA_FLOOR, analyse
from src.metrics.adapt import apply as apply_adapt
from src.metrics.ingest import read_quick
from src.money import rate as money
from src.seo import text as seo
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


# ---- captions ---------------------------------------------------------------

def _caption_platform(kit, platform: str) -> str:
    """The placement she named, or the one the composer is already holding, or the first one
    her interview says she posts to. Never a guess this app makes up."""
    if (platform or "").strip():
        return accounts.platform_id(platform)
    staged = kit.db.get_staged()
    if staged.get("platform"):
        return accounts.platform_id(staged["platform"])
    answers = kit.answers()
    named = (getattr(answers, "platforms", []) or []) if answers else []
    return accounts.platform_id(named[0]) if named else "instagram"


def copy_tone(kit, subject: str = "", tone_id: str = "", platform: str = "", media: str = ""):
    """The same shot in six temperatures, out of her own words and in her own typing.

    With no description of the frame it falls back to the footage line from the interview,
    because that is the only sentence this app holds about what she actually films.
    """
    profile, reg = caption_kit(kit.db)
    place = _caption_platform(kit, platform)
    key = accounts.caption_key(place)
    answers = kit.answers()
    asked = (subject or "").strip() or (subject_of(answers).strip() if answers else "")
    if not asked:
        return skipped("no description of the frame - nothing was typed and the interview does "
                       "not say what you film, so there are no words of yours to build a line "
                       "out of.")
    picked = [t for t in tones.TONES if not tone_id or t.id == tone_id.strip().lower()]
    if not picked:
        return skipped(f"{tone_id!r} is not one of the tones this app writes: "
                       + ", ".join(t.id for t in tones.TONES) + ".")
    today = date.today()
    refused = []
    cards = []
    for t in picked:
        rep = {}
        got = tones.lines(t.id, asked, profile, key, media, today=today, reg=reg, report=rep)
        refused.extend({"tone": t.id, **d} for d in rep.get("tells", []))
        cards.append({"tone": t.id, "name": t.name,
                      "lines": [{"text": c.text, "words": c.words, "shape": c.shape,
                                 "watched": c.watched, "why": c.explain(profile)} for c in got]})
    written = sum(len(c["lines"]) for c in cards)
    if not written:
        return advised("No line written: every shape those tones have asks for a detail of the "
                       f"thing itself or a count, and {asked!r} carries neither.",
                       subject=asked, platform=place, cards=[], where="/captions")
    return advised(
        f"{written} line{'s' if written != 1 else ''} for {len(cards)} tone"
        f"{'s' if len(cards) != 1 else ''} out of {asked!r} for {place}"
        + (f", typed the way {reg.source} show" if reg.learned
           else " - your voice is unlearned, so this is the app's own typing")
        + (f". {len(refused)} shape{'s' if len(refused) != 1 else ''} dropped for reading like a "
           "template rather than softened." if refused else "."),
        subject=asked, fills=tones.slots(asked, today, media), platform=place,
        media=media or "photo", voice=profile.samples, register=reg.source,
        cards=cards, dropped=refused, where="/captions")


def tags_pick(kit, subject: str = "", platform: str = "", limit: int = 0):
    """The tags this app can account for, each with the evidence that put it on the list.

    There is no trending feed behind this: no platform publishes a hashtag list the app can
    read, so a tag appears only from her own numbers, her own captions, her own words for the
    shot, or the format this week's arm carries.
    """
    rows = kit.rows()
    profile = voice.learn(kit.db.get_voice())
    plan = kit.plan()
    arm = experiment.arm_for(plan, date.today()) if plan else ""
    place = _caption_platform(kit, platform)
    answers = kit.answers()
    asked = (subject or "").strip() or (subject_of(answers).strip() if answers else "")
    got = tag_tool.candidates(place, asked, profile, rows, arm,
                              limit=int(limit) if limit else None)
    missing = tag_tool.missing(rows, profile, asked)
    if not got:
        return advised("No tag can be accounted for - nothing on this machine puts one on the "
                       "list, and an invented tag is the one thing worse than no tag.",
                       tags=[], missing=missing, platform=place, where="/captions")
    return advised(
        f"{len(got)} tag{'s' if len(got) != 1 else ''} for {place}, which carries "
        f"{tag_tool.limit_for(place)}: " + "; ".join(
            f"{t['tag']} from {t['source']}" for t in got),
        tags=got, missing=missing, platform=place, arm=arm or "unplanned",
        block=tag_tool.block(place, got), where="/captions")


# ---- discoverability --------------------------------------------------------

def seo_read(kit, text: str = "", platform: str = ""):
    """Read one post for the words a search could land on, and say what cannot be seen.

    The phrases are hers and only hers - the hypothesis her imported posts ran under, the words
    that repeat in the captions she pasted, the week her plan is running. The post is the text
    given, or the one the composer is holding. No search volume, rank or index status is ever
    returned, because nothing on this machine can produce one honestly; the limits come back in
    the payload instead of being left implied.
    """
    rows, samples, plan = kit.rows(), kit.db.get_voice(), kit.plan()
    week = _week_at(plan, date.today()) if plan else None
    found = seo.terms(rows, samples, plan, week)
    staged = kit.db.get_staged()
    alt = (staged.get("alt") or "").strip()
    cap, tags = seo.split(text)
    checked = "the text you gave"
    if not cap and not tags:
        cap = (staged.get("caption") or "").strip()
        tags = [t for t in (staged.get("hashtags") or []) if t]
        if cap or tags:
            checked = "the post staged in the composer"
    if not cap and not tags and not alt:
        return skipped("no post to read: nothing was pasted, the composer holds no staged "
                       "caption and there is no alt field either.")
    place = _caption_platform(kit, platform)
    got = seo.audit(caption=cap, hashtags=tags, alt=alt, found=found, platform=place,
                    shape=accounts.caption_key(place))
    held = [f["check"] for f in got["findings"] if f["verdict"] in ("missing", "weak",
                                                                    "unreadable")]
    return advised(
        f"Read {checked} against the {len(found)} phrase{'' if len(found) == 1 else 's'} this "
        f"app can account for: {len(got['carried'])} on it, {len(got['missed'])} not, "
        f"{len(got['front'])} in front of the fold. "
        + (f"{len(held)} check{'' if len(held) == 1 else 's'} came back short: "
           + ", ".join(held) + "." if held else "Nothing the app can check came back short."),
        checks=got["findings"], terms=[t.as_dict() for t in found], carried=got["carried"],
        missed=got["missed"], front=got["front"], late=got["late"], tag_only=got["tagOnly"],
        spent=got["spent"], alt=alt, platform=place, fold=seo.FRONT,
        rules=seo.rules(kit.entries()), why_short=seo.gaps(rows, samples, plan),
        cannot=seo.CANNOT, checked_from=checked, where="/seo")


# ---- collaboration ----------------------------------------------------------

def collab_offer(kit):
    """What she can put in a pitch, and how her own asks have gone.

    The names are never invented. This app has no login on any platform, does not search for
    creators and does not rank strangers, so the shortlist can only be the people she put on it,
    and the honest answer when that list is empty is that it is empty. The numbers are arithmetic
    on her import: a platform with one post behind it is still shown, labelled as the one
    afternoon it is, because refusing to say a median out loud would lose her the only number she
    has.
    """
    got = pitch.offers(kit.rows())
    stored = collab_store.load(kit.db)
    got_funnel = pitch.funnel(stored)
    lead = (f"Your import gives {len(got)} platform{'s' if len(got) != 1 else ''} to quote from: "
            + ", ".join(f"{o.platform} ({o.posts} post{'s' if o.posts != 1 else ''}, median "
                        f"{o.median_views:,} views)" for o in got)) if got else (
        "Nothing has been imported, so there is no number of yours a pitch can quote yet - each "
        "one leads with the work and says so")
    who = (f"{len(stored)} on your list: " + ", ".join(c["name"] for c in stored) if stored else
           "Nobody is on the list yet, and nothing here can find names for you")
    parts = [f"{lead}.", who + "."]
    if stored:
        # The funnel sentence already counts what was sent and what came back, so it is repeated
        # rather than paraphrased - a second set of numbers would only be a chance to disagree.
        meaning = got_funnel["meaning"]
        parts.append(meaning[0].upper() + meaning[1:] + ".")
    return advised(
        " ".join(parts),
        offers=[o.as_dict() for o in got],
        list=[{"name": c["name"], "status": c["status"], "why": c["why"],
               "platform": c["platform"]} for c in stored],
        funnel=got_funnel, thin=[o.platform for o in got if o.thin], floor=pitch.MIN_POSTS,
        min_asks=pitch.MIN_ASKS, cannot=pitch.CANNOT, where="/collab")


def collab_pitch(kit, name: str = "", why: str = "", ask: str = "", shape: str = "",
                 platform: str = ""):
    """The pitch for one name, built only out of her reason and her own numbers.

    What is already filed under that name is used unless she says something fresher now, and a
    name that is not on the list with no reason attached gets the refusal rather than an invented
    compliment - a reason this app made up is a sentence she would have to send and then explain.
    Nothing sends: the copy comes back for her to put in their inbox.
    """
    wanted = (name or "").strip()
    stored = collab_store.load(kit.db)
    on_file = next((c for c in stored
                    if (c.get("name") or "").strip().lower() == wanted.lower()), None)
    if not wanted:
        return skipped("no name to write it for"
                       + (" - on your list: " + ", ".join(c["name"] for c in stored) if stored
                          else ", and the list is empty"))
    chosen = (why or "").strip() or (on_file or {}).get("why", "")
    if not chosen:
        return skipped(
            f"{wanted} is not on the list and no reason came with the ask, so nothing was written. "
            "Say the specific thing you noticed about their account - a compliment this app "
            "guessed is a line you would have to send and then explain - or put them on the list "
            "first.")
    got = pitch.offers(kit.rows())
    place = (platform or "").strip() or (on_file or {}).get("platform", "")
    candidate = {"name": wanted, "why": chosen, "ask": (ask or "").strip()
                 or (on_file or {}).get("ask", ""), "format": (shape or "").strip()
                 or (on_file or {}).get("format", ""), "platform": place}
    got_pitch = pitch.brief_for(candidate, got)
    lines = got_pitch["lines"]
    held = got_pitch["held"]
    return advised(
        f"A pitch for {wanted} in {len(lines)} line{'s' if len(lines) != 1 else ''}, "
        + (f"led by your own numbers: {got_pitch['numbers']}." if got_pitch["numbers"]
           else "with no number in it, because nothing of yours has been imported for that "
                "platform - the work does the talking and the line says so.")
        + (f" {len(held)} thing{'s' if len(held) != 1 else ''} held back: "
           + "; ".join(held) + "." if held else " Nothing held back."),
        pitch=got_pitch, lines=lines, text=got_pitch["text"], held=held,
        platform=place or (got[0].platform if got else ""),
        from_list=on_file is not None, cannot=pitch.CANNOT, where="/collab")


# ---- other languages --------------------------------------------------------

def _codes(asked: str) -> list:
    return [c for c in (asked or "").replace(",", " ").split() if c]


def lang_localise(kit, text: str = "", codes: str = "", platform: str = "", media: str = "photo",
                  keep: str = ""):
    """The caption carried into another language, or the brief a person needs to carry it.

    The offline branch is why this is a tool and not a chat prompt: with no model connected it
    says that plainly, writes no sentence in another language, and hands back what a version has to
    fit. This app keeps no dictionary, and a translation assembled out of word lists would be a
    guess in a font that looks like an answer.
    """
    asked = (text or "").strip() or (kit.db.get_staged().get("caption") or "").strip()
    if not asked:
        return skipped("there is no caption to carry - nothing was typed and the composer is "
                       "holding no line, so there is nothing of yours to translate.")
    wanted = language.targets(kit.db, _codes(codes))
    if not wanted:
        return skipped("no language was picked, and this app will not choose your audience for "
                       "you. Pick from: "
                       + ", ".join(f"{one.code} ({one.name})" for one in localise.languages()) + ".")
    place = _caption_platform(kit, platform)
    got = localise.ask(kit.engine, asked, wanted, platform=place, media=media,
                       keep=language.keep(kit.db, keep))
    if not got.ran:
        return advised(f"Nothing was written in another language. {got.why}",
                       source=asked, platform=place, media=media,
                       briefs=[b.as_dict() for b in got.briefs], where="/languages")
    bad = [v for v in got.versions if not v.ok]
    return advised(
        f"{len(got.versions) - len(bad)} of {len(got.versions)} versions passed the check against "
        f"your line for {', '.join(wanted)}"
        + (f"; {len(bad)} came back with something to look at and are listed with it." if bad
           else "."),
        source=asked, platform=place, media=media, said_by=got.said_by,
        versions=[v.as_dict() for v in got.versions], where="/languages")


def lang_check(kit, text: str = "", version: str = "", code: str = "", platform: str = "",
               media: str = "photo", keep: str = ""):
    """Compare one version against her line, in front of her.

    The list is what this app can verify by reading two strings: a hashtag that vanished, a number
    that moved, a capital on a line she types lowercase, a full stop she does not use, an emoji she
    did not add, a line over the budget, and a version that quietly came back still in English. It
    is not a verdict on whether the sentence sounds native - nothing on this machine can say that,
    and the answer says so rather than clearing the line.
    """
    source = (text or "").strip() or (kit.db.get_staged().get("caption") or "").strip()
    if not source:
        return skipped("there is no line of yours to compare against.")
    if not (version or "").strip():
        return skipped("no version was given, so there was nothing to check.")
    picked = (code or "").strip().lower()
    if not localise.get(picked):
        found = localise.detect(source)
        picked = found.code
    place = _caption_platform(kit, platform)
    problems = localise.check(source, version.strip(), picked, place, media,
                              language.keep(kit.db, keep))
    named = localise.get(picked)
    budget = localise.budget_for(place, picked, media)
    if problems:
        return advised(f"{len(problems)} thing{'' if len(problems) == 1 else 's'} to look at in "
                       "that version: " + "; ".join(problems) + ".",
                       source=source, version=version.strip(), language=picked,
                       budget=budget, words=len(version.split()),
                       where="/languages")
    return advised(
        f"Nothing to report: the locked tokens are in it, it is inside the {budget} words this "
        f"page allows for {'a ' + named.name if named else 'a'} {media} on {place}, and it keeps "
        "your casing and your punctuation. That is a comparison with your line, not a native "
        "reader's opinion - nobody on this machine can give you that one.",
        source=source, version=version.strip(), language=picked, budget=budget,
        words=len(version.split()), where="/languages")


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
add("copy.tone", "Write the shot in six temperatures", "Make", "make",
    args=("subject", "tone_id", "platform", "media"),
    describe="Six temperatures on the same caption from her own words - cunty, lit, funny, "
             "detail, aesthetic, soft - in the casing her samples show. No model call, and "
             "nothing filtered.")(copy_tone)
add("copy.tags", "Pick the caption tags this app can name", "Make", "make",
    args=("subject", "platform", "limit"),
    describe="The tags that go under the caption, each with the evidence that put it there - "
             "her posts, her writing, her words for the shot, or the week's format. A tag nobody "
             "can point at is not shown.")(tags_pick)
add("seo.audit", "Read the post for what a search could land on", "SEO", "analyse",
    args=("text", "platform"),
    describe="Which phrases this app can account for are actually on the post, whether they sit "
             "in front of the fold or only inside a tag, what the alt field carries and which tag "
             "slots restate the caption. Search volume, rank and index status are reported as "
             "unknowable rather than guessed.")(seo_read)
add("collab.offer", "Say what you have to offer", "Collaboration", "analyse",
    describe="What your own import makes quotable on each platform, the names already on your "
             "list with the stage you left each one at, and how many asks came back. It never "
             "names a creator for you: nothing here searches, ranks or reads another "
             "account.")(collab_offer)
add("collab.pitch", "Write the pitch for one name", "Collaboration", "make",
    args=("name", "why", "ask", "shape", "platform"),
    describe="Four moves out of your reason, your ask and your own numbers. A name with no "
             "reason attached gets a refusal instead of an invented compliment, and the copy is "
             "yours to send - this app has no login on any platform.")(collab_pitch)
add("lang.localise", "Carry the caption into another language", "Multilingual", "make",
    args=("text", "codes", "platform", "media", "keep"),
    describe="Versions in her other languages, each one checked against her line for the hashtag, "
             "the handle, the number, the brand, the word budget, her casing and her punctuation. "
             "With no model connected it writes nothing in another language and returns the brief "
             "instead - this app has no dictionary and will not guess at one.")(lang_localise)
add("lang.check", "Compare a version against your line", "Multilingual", "analyse",
    args=("text", "version", "code", "platform", "media", "keep"),
    describe="What is wrong with one translation, and only what can be verified by reading two "
             "strings: a locked token that vanished, a number that moved, a full stop or a capital "
             "she does not use, an added emoji, a line over budget, a version that came back still "
             "in English. It never claims the sentence sounds native.")(lang_check)
add("community.drafts", "Draft the replies", "Make", "queue",
    describe="Writes replies to the comments she pasted in and refuses the ones needing a "
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
