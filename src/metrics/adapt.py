"""Turning an imported metrics table into verbs, with a floor under it.

analyse reads the rows against the plan and returns Adjustments of kind adjust, stop,
amplify or hold, each stating its own reason in numbers and carrying the last week's
focus_entry_ids as evidence. Three constants do the deciding: DATA_FLOOR of 8 posts,
WEAK_WATCH_PCT of 15 percent held, and STRONG_FOLLOW_RATE of 10 follows per 1000 views,
with amplify firing only when the best hypothesis converts at AMPLIFY_RATIO times the
worst across at least two hypotheses.

Below eight rows it returns one insufficient_data adjustment and stops; apply has no
branch for that kind, so the plan comes back unchanged. apply rewrites only the final
week and never a week before it, because a week she already lived is evidence, not a
draft.
"""

from dataclasses import dataclass, replace
from statistics import median

DATA_FLOOR = 8
WEAK_WATCH_PCT = 15.0
STRONG_FOLLOW_RATE = 10.0
AMPLIFY_RATIO = 1.4


@dataclass
class Adjustment:
    kind: str
    target: str
    reason: str
    evidence_ids: list[str]


def _focus(plan) -> list[str]:
    return plan.weeks[-1].focus_entry_ids if plan.weeks else []


def analyse(rows, plan) -> list[Adjustment]:
    """Numbers first, verbs second. Below the floor it says so and stops, because a
    conclusion drawn from three posts is the fastest way to lose a year."""
    if len(rows) < DATA_FLOOR:
        return [
            Adjustment(
                "insufficient_data",
                "all",
                f"{len(rows)} posts is below the floor of {DATA_FLOOR}; this app will not invent "
                "a conclusion from noise. Keep posting and re-import.",
                [],
            )
        ]

    focus = _focus(plan)
    med = median(r.avg_watch_pct for r in rows)
    low = [r for r in rows if r.avg_watch_pct < WEAK_WATCH_PCT]
    out = []

    if len(low) >= max(3, len(rows) // 4):
        out.append(
            Adjustment(
                "adjust",
                "hook",
                f"{len(low)} of {len(rows)} posts held under {WEAK_WATCH_PCT}% watch "
                f"(median {med}%). The first second is the suspect, not the topic.",
                focus,
            )
        )

    weak = [r for r in low if r.follow_rate_per_1000 < STRONG_FOLLOW_RATE]
    if weak:
        worst = min(weak, key=lambda r: r.avg_watch_pct)
        out.append(
            Adjustment(
                "stop",
                f"{worst.hypothesis or worst.post_ref}",
                f"watch {worst.avg_watch_pct}% against a median of {med}%, and only "
                f"{worst.follow_rate_per_1000} follows per 1000 views.",
                focus,
            )
        )

    by_hypothesis: dict[str, list] = {}
    for r in rows:
        if r.hypothesis:
            by_hypothesis.setdefault(r.hypothesis, []).append(r)
    if len(by_hypothesis) >= 2:
        ranked = sorted(by_hypothesis.items(), key=lambda kv: -_rate(kv[1]))
        best_name, best = ranked[0]
        worst_name, worst_rows = ranked[-1]
        if _rate(best) >= _rate(worst_rows) * AMPLIFY_RATIO and _rate(worst_rows) > 0:
            out.append(
                Adjustment(
                    "amplify",
                    best_name,
                    f"{best_name} converts {_rate(best)} follows per 1000 views against "
                    f"{_rate(worst_rows)} for {worst_name} across {len(rows)} posts.",
                    focus,
                )
            )

    if not out:
        out.append(
            Adjustment(
                "hold",
                "plan",
                f"median watch {med}% across {len(rows)} posts, nothing separated by more than "
                "the noise floor. No change is justified yet.",
                focus,
            )
        )
    return out


def _rate(rows) -> float:
    views = sum(r.views for r in rows)
    return round(sum(r.follows_gained for r in rows) / max(views, 1) * 1000, 2)


def apply(plan, adjustments):
    """Applies to the remaining weeks only; a week already lived is evidence, not a draft."""
    weeks = list(plan.weeks)
    for a in adjustments:
        if not weeks:
            break
        w = weeks[-1]
        if a.kind == "stop":
            weeks[-1] = replace(
                w,
                goal=f"Drop {a.target}. {w.goal}",
                target_posts=max(1, w.target_posts - 1),
            )
        elif a.kind == "adjust":
            weeks[-1] = replace(w, goal=f"Week priority is the hook. {w.goal}")
        elif a.kind == "amplify":
            weeks[-1] = replace(w, goal=f"More {a.target}. {w.goal}")
    return replace(plan, weeks=weeks)
