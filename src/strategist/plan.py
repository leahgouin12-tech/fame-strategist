import json
from dataclasses import asdict, dataclass
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
        )


def compose_plan(entries, answers, hypotheses, engine, start_date=None) -> Plan:
    """Structure comes from arithmetic and the playbook; the engine is not consulted
    here, because a plan whose shape changes with model output cannot be tested."""
    if answers.hours_per_week < MIN_HOURS:
        raise ValueError(
            f"cannot build a plan on {answers.hours_per_week} h/week; minimum {MIN_HOURS}"
        )
    if not hypotheses:
        raise ValueError("no hypotheses to plan against; run the scoring first")

    chosen = hypotheses[0]
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
        index = min(n, len(hypotheses)) - 1
        weeks.append(
            Week(
                week_no=n,
                goal=(
                    f"Experiment: run hypothesis {index + 1} of {len(hypotheses)} - "
                    f"{hypotheses[index].name}"
                    if testing
                    else f"Concentrate: double down on {chosen.name} and the runner-up, "
                    "cutting what week 1-4 data did not reward"
                ),
                focus_entry_ids=pool[:6],
                target_posts=target,
                experiment=(
                    hypotheses[index].name
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
    )


def dumps(plan: Plan) -> str:
    return json.dumps(plan.to_dict())
