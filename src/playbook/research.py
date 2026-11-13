"""Spec 5.10, the layer that is deliberately not an API.

Nothing in this module reaches the network, and the app cannot: the only address any code here
may contact is the model endpoint, and trend chasing by scraped hashtag is a permanent non-goal.
So the research is run by the agent, written into the playbook as dated entries, and this module
is the part that decides whether those entries are still worth calling a trend, plus the brief
she hands over to get the next run.

A finding is a claim with an as-of date on it. The date is the whole difference between this and
the rest of the library, so the age is computed, shown, and allowed to expire the finding.
"""

from dataclasses import dataclass, field
from datetime import date

TREND_TAG = "trend"

# Six weeks is roughly the length of the eight-week plan: past that, a "rising" format has had
# time to be adopted by everyone who read the same report, and reach is front-loaded.
FRESH_DAYS = 45

# Beyond this the entry stops being shown as a finding at all; it stays in the library, where a
# mechanism claim does not expire on a schedule.
DEAD_DAYS = 180

BRIEF_HEADER = "Run the trend research for my app (spec 5.10)."


@dataclass
class Finding:
    id: str
    claim: str
    why_now: str
    confidence: str
    as_of: str
    days_old: int
    age_words: str
    does_not_claim: str
    sources: list[dict] = field(default_factory=list)
    in_this_week: bool = False

    @property
    def tiers(self) -> list[str]:
        return sorted({s["tier"] for s in self.sources})


@dataclass
class ResearchRun:
    findings: list[Finding]
    settled: list[Finding]
    newest_days: int | None
    note: str
    ran: bool

    @property
    def count(self) -> int:
        return len(self.findings)


def age_words(days: int) -> str:
    if days <= 0:
        return "dated today"
    if days == 1:
        return "one day old"
    if days < 14:
        return f"{days} days old"
    if days < 90:
        return f"{days // 7} weeks old"
    return f"{days // 30} months old"


def _finding(entry, today: date, focus: set[str]) -> Finding:
    days = (today - entry.as_of).days
    return Finding(
        id=entry.id,
        claim=entry.claim,
        why_now=entry.mechanism,
        confidence=entry.confidence.value,
        as_of=entry.as_of.isoformat(),
        days_old=days,
        age_words=age_words(days),
        does_not_claim=entry.does_not_claim,
        sources=[{"title": s.title, "url": s.url, "tier": s.tier.value} for s in entry.sources],
        in_this_week=entry.id in focus,
    )


def run(entries, today: date | None = None, focus_ids=None) -> ResearchRun:
    """Split the playbook into what research is still standing and what has settled into it."""
    today = today or date.today()
    focus = set(focus_ids or ())
    trended = [e for e in entries if TREND_TAG in e.tags]
    fresh, settled = [], []
    for entry in sorted(trended, key=lambda e: e.as_of, reverse=True):
        finding = _finding(entry, today, focus)
        (fresh if finding.days_old <= FRESH_DAYS else settled).append(finding)

    if fresh:
        newest = fresh[0]
        note = (f"{len(fresh)} finding{'' if len(fresh) == 1 else 's'} still standing, newest "
                f"{newest.age_words}. Each one is a claim somebody published, with the address it "
                "was read at and the date it was read - not a hashtag list and not a forecast "
                "this app made up. Anything older than "
                f"{FRESH_DAYS} days has moved below, because a format everyone has already read "
                "about is not a head start any more.")
        return ResearchRun(findings=fresh, settled=settled, newest_days=newest.days_old,
                           note=note, ran=True)

    note = ("No trend research is live. The newest finding tagged as research is older than "
            f"{FRESH_DAYS} days, or none has been run, so what sits behind your slots is the "
            "library - mechanisms that do not expire on a schedule, checked against your own "
            "numbers. This page will not dress the library up as something found this week.")
    return ResearchRun(findings=[], settled=settled, newest_days=None, note=note, ran=False)


def brief(*, platforms, hypotheses, chosen, hours_per_week, today: date | None = None) -> str:
    """The instruction that gets the next run.

    The app cannot browse, so it says what a browsing agent needs to be told: which lanes, what
    evidence standard, and what shape the answer has to arrive in to be readable here.
    """
    today = today or date.today()
    lanes = ", ".join(platforms) if platforms else "the platforms in my plan"
    lines = [
        BRIEF_HEADER,
        "",
        f"As of {today.isoformat()}. My platforms are {lanes}.",
        f"I have {hours_per_week} hours a week and I film with a phone.",
        "",
        "Lanes I am testing: " + (", ".join(hypotheses) if hypotheses else "not chosen yet"),
        "Running this week: " + (chosen or "nothing chosen yet"),
        "",
        "Find formats and angles rising in those lanes right now. For each one give me:",
        "  - the format or angle, in one sentence I could film from",
        "  - who says so, with a real address you opened and a publication date",
        "  - an as-of date, and a confidence of proven, strong, contested or folklore",
        "  - what the source does NOT establish, in the same breath",
        "Then write each finding into data/playbook as one markdown file per finding, named after",
        "its id, with id starting trend-, the tag 'trend', and the front matter the other entries",
        "already use. Reject anything you could not open. If nothing is defensible this week, say",
        "that instead of filling the page - the app already tells me when research has not run.",
        "",
        "Do not give me a hashtag list. Do not give me a posting time. Do not touch my accounts.",
    ]
    return "\n".join(lines)
