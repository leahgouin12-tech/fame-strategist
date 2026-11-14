"""What the agent may do on its own, and what it must leave for her to press.

A mode is not a personality. It is two sets: which capabilities it is allowed to
reach for at all, and which of those it may carry out without stopping to ask.
"""
from dataclasses import dataclass

CAPS = ("research", "strategy", "make", "queue", "analyse")
CAP_LABEL = {
    "research": "Research",
    "strategy": "Strategy",
    "make": "Make assets",
    "queue": "Prepare posting",
    "analyse": "Read the numbers",
}


@dataclass(frozen=True)
class Mode:
    id: str
    label: str
    caps: tuple[str, ...]
    auto: tuple[str, ...]
    blurb: str

    def allows(self, cap: str) -> bool:
        return cap in self.caps

    def runs_alone(self, cap: str, granted=()) -> bool:
        """Auto-runs if the mode says so, or if she authorised this cap once already."""
        return self.allows(cap) and (cap in self.auto or cap in set(granted))


MODES = (
    Mode("researcher", "Researcher", ("research", "analyse"), ("research",),
         "Brings findings. Touches nothing."),
    Mode("strategist", "Strategist", ("research", "strategy", "analyse"), ("analyse",),
         "Ranks niches and rebuilds the eight weeks from your numbers."),
    Mode("creator", "Creator", ("research", "strategy", "make"), ("research",),
         "Writes the day out and edits the files. Does not decide what to post."),
    Mode("manager", "Manager", ("strategy", "queue", "analyse"), ("queue",),
         "Keeps the calendar, the queues and the records straight."),
    Mode("operator", "Growth Operator", CAPS, ("research", "analyse"),
         "Research, plan, make, stage, measure - the whole loop, one command."),
    Mode("agency", "Autonomous Agency", CAPS, CAPS,
         "Runs the whole permitted loop without stopping between steps. Reversible "
         "work only: nothing here reaches an account."),
)
BY_ID = {m.id: m for m in MODES}
DEFAULT = "operator"


def get(mode_id: str) -> Mode:
    return BY_ID.get(mode_id, BY_ID[DEFAULT])
