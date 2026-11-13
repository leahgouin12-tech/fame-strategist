"""The fortnightly coach: receipts first, then proposals. It has no hands.

Every line here is computed from evidence already on this machine - the plan, the days
she marked posted, the files that landed, the last metrics import, the playbook the
slots were built from. Nothing in this module sends, posts, edits, applies or schedules.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from src.metrics.adapt import DATA_FLOOR, analyse

# Spec §10: fortnightly, not weekly - a week would mostly re-measure the same posts.
CADENCE_DAYS = 14
# Spec §7.7: below this many posts the coach is generic, and says so instead of dressing
# up guesswork as insight.
GENERIC_UNDER = 25
# A rate computed from two frames is not a rate.
RATE_UNDER = 3


@dataclass
class Coverage:
    planned: int
    posted: int
    missed: list[str]
    landed: list[str]
    weak: list[str]
    note: str


@dataclass
class Performance:
    posts: int
    generic: bool
    top: dict
    bottom: dict
    gap: str
    note: str


@dataclass
class SelfCheck:
    chosen: str
    best: str
    agreed: bool | None
    note: str


@dataclass
class Move:
    kind: str
    text: str
    basis: str


@dataclass
class Research:
    used: list[dict]
    stale: list[str]
    pending: list[str]
    note: str


@dataclass
class Spend:
    credits: str
    local: str
    next_time: str


@dataclass
class Agenda:
    start: str
    end: str
    cadence_days: int
    coverage: Coverage
    performance: Performance
    self_check: SelfCheck
    moves: list[Move]
    next_week: dict | None
    research: Research
    spend: Spend
    proposals: list[str]

    @property
    def window(self) -> str:
        return f"{self.start} to {self.end}"


def _brief(row) -> dict:
    return {
        "post_ref": row.post_ref,
        "views": row.views,
        "watch": row.avg_watch_pct,
        "follows": row.follows_gained,
        "rate": row.follow_rate_per_1000,
        "hypothesis": row.hypothesis or "not labelled",
    }


def _follow_rate(rows) -> float:
    views = sum(r.views for r in rows)
    return round(sum(r.follows_gained for r in rows) / max(views, 1) * 1000, 2)


def _planned_posts(plan, start: date, end: date) -> int:
    """The plan's own target, prorated across the weeks the window actually touches."""
    if not plan or not plan.weeks or not plan.start_date:
        return 0
    origin = date.fromisoformat(plan.start_date)
    total = 0.0
    for week in plan.weeks:
        first = origin + timedelta(days=7 * (week.week_no - 1))
        last = first + timedelta(days=6)
        overlap = (min(end, last) - max(start, first)).days + 1
        if overlap > 0:
            total += week.target_posts * overlap / 7
    return round(total)


def _coverage(plan, days, landed, weak, start: date, end: date) -> Coverage:
    posted = len([d for d in days if d.get("done")])
    missed = [d["date"] for d in days if not d.get("done")]
    planned = _planned_posts(plan, start, end)
    if not landed:
        note = ("Nothing landed in your folders in these two weeks, so there is no "
                "rejection rate to talk about - only the posting count below.")
    elif len(landed) < RATE_UNDER:
        note = (f"{len(landed)} frame in two weeks is not a rate. The count is real; any "
                "percentage from it would be noise.")
    else:
        share = round(100 * len(weak) / len(landed))
        if share >= 80:
            note = (f"{len(weak)} of {len(landed)} frames ({share}%) came in weak on the "
                    "app's own weights. Either the light is the problem or the weights are - "
                    "only you can say which, and the app will not guess.")
        elif share <= 20:
            note = (f"{len(weak)} of {len(landed)} frames ({share}%) came in weak. That is a "
                    "sane strike rate: the judge is not rejecting everything, and you are not "
                    "posting everything either.")
        else:
            note = (f"{len(weak)} of {len(landed)} frames ({share}%) came in weak - in the "
                    "middle, which is where a real working process usually sits.")
    return Coverage(planned=planned, posted=posted, missed=missed, landed=landed,
                    weak=weak, note=note)


def _performance(rows) -> Performance:
    generic = len(rows) < GENERIC_UNDER
    if not rows:
        return Performance(0, True, {}, {}, "",
                           "No metrics imported yet, so there is no top and no bottom. This "
                           "app will not describe a performance it has never seen.")
    ranked = sorted(rows, key=lambda r: r.follow_rate_per_1000)
    bottom, top = ranked[0], ranked[-1]
    if len(ranked) == 1:
        return Performance(1, generic, _brief(top), {},
                           f"{top.post_ref} is the only post measured, so nothing compares to it.",
                           "One post is a data point, not a trend. Keep importing and this "
                           "line gets honest.")
    d_rate = round(top.follow_rate_per_1000 - bottom.follow_rate_per_1000, 2)
    d_watch = round(top.avg_watch_pct - bottom.avg_watch_pct, 2)
    gap = (f"{top.post_ref} converted {top.follow_rate_per_1000} follows per 1000 views at "
           f"{top.avg_watch_pct}% watch. {bottom.post_ref} did {bottom.follow_rate_per_1000} "
           f"at {bottom.avg_watch_pct}%. The difference is {d_rate} follows per 1000 views "
           f"and {d_watch} points of watch time"
           + (f", and the top one ran {top.hypothesis or 'an unlabelled'} while the bottom "
              f"ran {bottom.hypothesis or 'an unlabelled'}."
              if top.hypothesis != bottom.hypothesis else "."))
    note = ("Under "
            f"{GENERIC_UNDER} posts this is a description of what happened, not a rule. "
            "The app is generic here and would rather say so than invent an insight."
            if generic else
            f"{len(rows)} posts read - enough to compare, not enough to be certain.")
    return Performance(len(rows), generic, _brief(top), _brief(bottom), gap, note)


def _self_check(plan, rows) -> SelfCheck:
    chosen = plan.chosen if plan else ""
    labelled = [r for r in rows if r.hypothesis]
    if len(rows) < DATA_FLOOR or len({r.hypothesis for r in labelled}) < 2:
        return SelfCheck(chosen, "", None,
                         f"This app ranked {chosen or 'your niches'} first. It cannot audit "
                         f"that call yet: {len(rows)} posts read, and the ranking is only "
                         f"wrong or right once at least {DATA_FLOOR} posts carry the "
                         "hypothesis they were run under.")
    by: dict[str, list] = {}
    for r in labelled:
        by.setdefault(r.hypothesis, []).append(r)
    best = max(by.items(), key=lambda kv: _follow_rate(kv[1]))[0]
    agreed = best == chosen
    note = (f"It said {chosen} would convert best; your numbers say {best}. "
            + ("So far it has been right." if agreed else
               f"{chosen} converts {_follow_rate(by[chosen]) if chosen in by else 0} follows "
               f"per 1000 views against {_follow_rate(by[best])} for {best}. The ranking was "
               "wrong on your account, and the plan should bend to that rather than the "
               "other way round.")
            )
    return SelfCheck(chosen, best, agreed, note)


def _moves(plan, rows, next_week) -> list[Move]:
    out = []
    for a in analyse(rows, plan):
        kind = {"stop": "stop", "adjust": "start", "amplify": "more"}.get(a.kind, "hold")
        out.append(Move(kind, a.reason, ", ".join(a.evidence_ids) or "your own numbers"))
    if not any(m.kind == "start" for m in out) and next_week:
        out.append(Move("start", next_week["experiment"],
                        ", ".join(next_week["focus_entry_ids"][:3]) or "the plan"))
    return out


def _research(entries, week, today: date) -> Research:
    focus = set(week.focus_entry_ids) if week else set()
    picked = [e for e in entries if e.id in focus]
    used = [{"id": e.id, "claim": e.claim, "confidence": e.confidence.value,
             "as_of": e.as_of.isoformat(), "does_not_claim": e.does_not_claim,
             "sources": [{"title": s.title, "url": s.url, "tier": s.tier.value} for s in e.sources]}
            for e in picked]
    stale = [e.id for e in picked if e.is_stale(today)]
    pending = [e.id for e in picked if e.has_placeholder_source()]
    note = ("No live trend research has run - that layer is not built, and this page will not "
            "pretend it has. What sits behind your slots is the playbook you already have, "
            "with the date each claim was checked and the address it was checked at.")
    return Research(used=used, stale=stale, pending=pending, note=note)


def _n(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _spend(rows, landed, engine_name: str, offline: bool) -> Spend:
    credits = ("0 model credits, 0 API calls. This page was computed from files and rows "
               "already on this machine."
               if offline else
               f"Engine: {engine_name}. The coach itself made no call; only hook lines would.")
    return Spend(credits,
                 f"{_n(len(landed), 'frame')} scored and {_n(len(rows), 'post')} read, "
                 "all local CPU.",
                  "The next run costs the same unless you ask for trend research, which does "
                  "not exist yet - so the honest forecast is zero.")


def _week_at(plan, day: date):
    if not plan or not plan.start_date or not plan.weeks:
        return None
    origin = date.fromisoformat(plan.start_date)
    if day < origin:
        return plan.weeks[0]
    return plan.weeks[min((day - origin).days // 7, len(plan.weeks) - 1)]


def build_agenda(*, plan, days, rows, landed, weak, entries, today=None,
                 engine_name="offline", offline=True) -> Agenda:
    today = today or date.today()
    start, end = today - timedelta(days=CADENCE_DAYS - 1), today
    window = [d for d in days if start.isoformat() <= d["date"] <= end.isoformat()]
    week = _week_at(plan, today)
    next_week = None
    if plan and week and week.week_no < len(plan.weeks):
        w = plan.weeks[week.week_no]
        next_week = {"week_no": w.week_no, "goal": w.goal, "target_posts": w.target_posts,
                     "experiment": w.experiment, "success_test": w.success_test,
                     "focus_entry_ids": list(w.focus_entry_ids)}
    coverage = _coverage(plan, window, landed, weak, start, end)
    performance = _performance(rows)
    moves = _moves(plan, rows, next_week)
    agenda = Agenda(start.isoformat(), end.isoformat(), CADENCE_DAYS, coverage, performance,
                    _self_check(plan, rows), moves, next_week,
                    _research(entries, week, today), _spend(rows, landed, engine_name, offline), [])
    agenda.proposals = _proposals(agenda)
    return agenda


def _proposals(a: Agenda) -> list[str]:
    out = []
    if a.coverage.missed:
        out.append(f"Days in this window with a slot and no post: {', '.join(a.coverage.missed)}. "
                   "Propose you post the nearest one or cut it - keeping both is how a plan "
                   "becomes decoration.")
    if a.coverage.planned and a.coverage.posted < a.coverage.planned:
        out.append(f"The plan asked for {a.coverage.planned} posts in these two weeks; "
                   f"{a.coverage.posted} are marked posted. Propose the target drops to what "
                   "you actually did, then rises once a week. A target you miss is not a plan.")
    for m in a.moves:
        out.append(f"Proposed {m.kind}: {m.text} (basis: {m.basis}).")
    if a.self_check.agreed is False:
        out.append("Proposed: change the leading hypothesis. The app's ranking lost to your own "
                   "numbers, and the Numbers page is where you apply that - not this page.")
    if a.research.pending:
        out.append(f"Proposed: re-check {', '.join(a.research.pending)} before it goes in another "
                   "slot - those claims still carry an unverified address.")
    if not out:
        out.append("Nothing to propose yet: no receipts have accumulated. Keep posting and "
                   "importing numbers, and this page will have something to say.")
    return out
