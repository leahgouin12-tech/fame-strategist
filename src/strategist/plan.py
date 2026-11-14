"""The eight weeks, decided by arithmetic and by nothing else.

compose_plan lays out PLAN_WEEKS 8 weeks: the first EXPERIMENT_WEEKS 4 rotate through
the ranked hypotheses one at a time, the rest concentrate on the chosen one against the
weeks 1-4 baseline. focus_entry_ids come from the playbook entries tagged hook,
retention, algorithm, conversion or format, target_posts is the hours she claimed capped
at 5 for experiment weeks and 4 after, and each week carries the success_test it will be
judged by. It raises outright under MIN_HOURS 2 and raises on an empty hypothesis list
rather than planning against nothing, and it never calls the engine, because a plan whose
shape changes with model output cannot be tested.

Plan and Week are plain dataclasses whose to_dict and from_dict are the only way they
cross into the plans table and back, and first_two_weeks_only_reason holds the argument
for why weeks 1-4 measure instead of committing: there is no data about her yet.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import date

MIN_HOURS = 2
EXPERIMENT_WEEKS = 4
PLAN_WEEKS = 8


@dataclass
class Week:
    week_no: int
    goal: str
    focus_entry_ids: list[str]
    target_posts: int
    experiment: str
    success_test: str


@dataclass
class Plan:
    hypotheses: list[str]
    chosen: str
    weeks: list[Week]
    first_two_weeks_only_reason: str = ""
    start_date: str = ""
    verdict_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        return cls(
            d["hypotheses"],
            d["chosen"],
            [Week(**w) for w in d["weeks"]],
            d.get("first_two_weeks_only_reason", ""),
            d.get("start_date", ""),
            d.get("verdict_notes", []),
        )


def compose_plan(entries, answers, hypotheses, engine, start_date=None,
                 dropped=()) -> Plan:
    """Structure comes from arithmetic and the playbook; the engine is not consulted
    here, because a plan whose shape changes with model output cannot be tested.

    `dropped` is the list of hypotheses a lab verdict already put out of the running. With
    it empty - every plan built before she has compared two arms - the eight weeks come out
    exactly as they always did. With a name in it, that hypothesis loses its experiment week
    to the next one in the ranking and the plan records why, so a verdict she wrote down
    cannot be quietly un-made by the next rebuild."""
    if answers.hours_per_week < MIN_HOURS:
        raise ValueError(
            f"cannot build a plan on {answers.hours_per_week} h/week; minimum {MIN_HOURS}"
        )
    if not hypotheses:
        raise ValueError("no hypotheses to plan against; run the scoring first")

    gone = {str(d) for d in dropped}
    run = [h for h in hypotheses if h.name not in gone]
    notes = []
    if not run:
        run = list(hypotheses)
        notes.append(
            "Every ranked hypothesis has been dropped by a verdict, so this plan runs them "
            "again because there is nothing else - score the niches again before the next one."
        )
    else:
        for name in sorted(gone):
            if name not in {h.name for h in hypotheses}:
                continue
            i = next(k for k, h in enumerate(hypotheses) if h.name == name)
            if i >= EXPERIMENT_WEEKS:
                notes.append(f"{name} sits below the four experiment weeks, so dropping it "
                             "changes no week in this plan.")
            else:
                notes.append(f"Week {i + 1} was {name}. The lab dropped it, so week {i + 1} "
                             f"tests {run[i].name} instead.")
    chosen = run[0]
    pool = sorted(
        {
            e.id
            for e in entries
            if set(e.tags) & {"hook", "retention", "algorithm", "conversion", "format"}
        }
    )
    weeks = []
    for n in range(1, PLAN_WEEKS + 1):
        testing = n <= EXPERIMENT_WEEKS
        target = min(max(1, answers.hours_per_week), 5 if testing else 4)
        pick = run[min(n, len(run)) - 1]
        rank = hypotheses.index(pick) + 1
        weeks.append(
            Week(
                week_no=n,
                goal=(
                    f"Experiment: run hypothesis {rank} of {len(hypotheses)} - "
                    f"{pick.name}"
                    if testing
                    else f"Concentrate: double down on {chosen.name} and the runner-up, "
                    "cutting what week 1-4 data did not reward"
                ),
                focus_entry_ids=pool[:6],
                target_posts=target,
                experiment=(
                    pick.name
                    if testing
                    else "hold format and cadence constant; compare against weeks 1-4"
                ),
                success_test=(
                    "at least half of this week's posts beat your own median watch-time by 20%"
                    if testing
                    else "follow-rate per 1000 views up 25% against week 4"
                ),
            )
        )
    return Plan(
        [h.name for h in hypotheses],
        chosen.name,
        weeks,
        "Weeks 1-4 measure which niche your own numbers reward. There is no data about you yet, "
        "so committing to one niche now would be guesswork dressed as strategy.",
        (start_date or date.today()).isoformat(),
        notes,
    )


def dumps(plan: Plan) -> str:
    return json.dumps(plan.to_dict())
