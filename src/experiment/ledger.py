"""Which arm each post ran under, and what the ledger is allowed to conclude from that.

A test needs two arms and a rule for calling it. The arms come from the plan: every week
carries the hypothesis it is testing, so a post filed in that week belongs to that arm
(`arm_for`). The rule lives here, and it borrows the app's one existing ratio - the same
`AMPLIFY_RATIO` that lets `metrics.adapt` propose an amplify - so the ledger and the
adjustment engine cannot ever disagree about what "separated" means.

Three numbers decide everything on this page: `MIN_PER_ARM` posts in each of two arms,
`AMPLIFY_RATIO` times the conversion, and `DATA_FLOOR` posts overall. Under any of them the
state is `thin` or `no test`, the page says exactly which is missing, and no winner is
named. That refusal is the feature: a conclusion drawn from two posts is how a year gets
wasted on noise.
"""
import re
from dataclasses import dataclass, field, replace
from datetime import date
from statistics import median

from src.metrics.adapt import AMPLIFY_RATIO, DATA_FLOOR, _rate
from src.strategist.coach import _week_at

MIN_PER_ARM = 3


@dataclass
class Arm:
    """One hypothesis and the posts filed under it."""
    label: str
    n: int
    rate: float
    watch: float
    refs: list[str] = field(default_factory=list)

    @property
    def rate_text(self) -> str:
        return f"{self.rate} per 1000 views"


@dataclass
class Ledger:
    """Everything the ledger can see in the stored numbers right now."""
    arms: list[Arm]
    unlabelled: int
    posts: int

    @property
    def labelled(self) -> int:
        return sum(a.n for a in self.arms)


@dataclass
class Verdict:
    """state is one of: no plan, no test, thin, flat, called."""
    state: str
    headline: str
    lines: list[str] = field(default_factory=list)
    winner: str = ""
    loser: str = ""
    missing: str = ""

    @property
    def decided(self) -> bool:
        return self.state == "called"


def arm_for(plan, day: date) -> str:
    """The hypothesis this week's plan says she is testing, or an empty string.

    An empty string is kept, not guessed at: a post from before the plan exists has no arm,
    and inventing one would put a number under a test nobody ran."""
    week = _week_at(plan, day)
    return week.experiment if week else ""


def tag(rows, label: str) -> list:
    """Fill in the arm for rows that have none; a row already labelled keeps its label.

    Re-tagging a row she already filed would rewrite history to match whatever the plan
    says this week, so this only ever writes into the empty cells."""
    if not label:
        return list(rows)
    return [r if r.hypothesis else replace(r, hypothesis=label) for r in rows]


def ledger(rows) -> Ledger:
    """Group the stored posts by the arm they were run under."""
    by: dict[str, list] = {}
    unlabelled = 0
    for r in rows:
        if r.hypothesis:
            by.setdefault(r.hypothesis, []).append(r)
        else:
            unlabelled += 1
    arms = sorted((Arm(label=label, n=len(group), rate=_rate(group),
                        watch=round(median(g.avg_watch_pct for g in group), 1),
                        refs=[g.post_ref for g in group])
                   for label, group in by.items()),
                  key=lambda a: (-a.rate, a.label))
    return Ledger(arms, unlabelled, len(rows))


def verdict(got: Ledger, plan) -> Verdict:
    """The one sentence the numbers support, or the reason there is no such sentence."""
    if plan is None:
        return Verdict("no plan",
                       "No plan, so nothing has an arm to belong to.",
                       missing="Build the eight weeks first - the weeks are what name the arms.")
    if got.posts < DATA_FLOOR:
        return Verdict(
            "thin",
            ("Nothing is stored yet, so there is no test to call." if not got.posts else
             f"Only {got.posts} posts are stored, under the floor of {DATA_FLOOR}, so this app "
             "will not call a test on them."),
            [f"{got.labelled} of those posts carry an arm label and {got.unlabelled} do not."]
            if got.posts else
            ["The numbers page is where a week's posts get in; each one is filed under the "
             "hypothesis the plan says is running."],
            missing=(f"{DATA_FLOOR} posts on the numbers page before any verdict is honest."
                     if not got.posts else
                     f"{DATA_FLOOR - got.posts} more posts before any verdict is honest."))
    if len(got.arms) < 2:
        only = got.arms[0].label if got.arms else ""
        return Verdict(
            "no test",
            "One arm is a habit, not a test." if got.arms else "No post carries an arm label.",
            [f"Everything labelled sits under {only}." if got.arms
             else f"{got.unlabelled} posts are stored without a hypothesis, so nothing can be "
                  "compared yet."],
            missing="Run the week's alternative and label those posts, or label the ones already "
                    "filed on the numbers page.")
    short = [a for a in got.arms if a.n < MIN_PER_ARM]
    if short:
        return Verdict(
            "thin",
            "Nothing is decided yet: an arm with two posts is two posts.",
            [f"{a.label} has {a.n} post{'' if a.n == 1 else 's'}; {MIN_PER_ARM} is the minimum "
             f"before it counts against another arm." for a in short],
            missing="; ".join(f"{MIN_PER_ARM - a.n} more under {a.label}" for a in short))
    best, worst = got.arms[0], got.arms[-1]
    if best.rate == worst.rate:
        return Verdict(
            "flat",
            f"{best.label} and {worst.label} convert at the same {best.rate} per 1000 views.",
            [f"{best.n} posts against {worst.n}, and no gap to read."],
            missing="More posts, or a wider difference between the arms.")
    if worst.rate > 0 and best.rate >= worst.rate * AMPLIFY_RATIO:
        return Verdict(
            "called",
            f"{best.label} beat {worst.label} by enough to keep.",
            [f"{best.rate} follows per 1000 views on {best.n} posts against {worst.rate} on "
             f"{worst.n} - a factor of {round(best.rate / worst.rate, 2)}.",
             f"Watch time: {best.watch}% against {worst.watch}% median."],
            winner=best.label, loser=worst.label)
    ratio = round(best.rate / worst.rate, 2) if worst.rate else 0
    return Verdict(
        "flat",
        f"{best.label} leads, by less than this app is allowed to act on.",
        [f"{best.rate} against {worst.rate} per 1000 views is a factor of {ratio}; the rule "
         f"needs {AMPLIFY_RATIO} before a drop is justified.",
         "Both arms stay in the plan."],
        missing=f"{best.label} needs to reach {round(worst.rate * AMPLIFY_RATIO, 2)} per 1000 "
                "views on the posts already filed.")


def decision_text(got: Verdict) -> str:
    """The line worth remembering: the verdict, the arms, and the numbers behind it."""
    if got.decided:
        return f"Kept {got.winner}, dropped {got.loser}. {got.lines[0]}"
    return f"No verdict ({got.state}): {got.headline} {got.missing}".strip()


DROPPED = re.compile(r"^Kept (\S+), dropped (\S+)\.")


def dropped(notes) -> list[str]:
    """The arms every remembered verdict put out of the plan, oldest first.

    This reads back the exact sentence `decision_text` writes, in this module, so the two
    cannot drift: the plan builder asks for a list of labels and gets one, which is what
    turns a written-down verdict into a different eight weeks instead of a note nobody uses.
    Anything that is not a kept/dropped line - a refusal, an older format - is skipped
    rather than guessed at."""
    out = []
    for note in sorted(notes, key=lambda n: (n.get("seen_at") or "", n.get("id") or 0)):
        match = DROPPED.match(note["body"])
        if match and match.group(2) not in out:
            out.append(match.group(2))
    return out
