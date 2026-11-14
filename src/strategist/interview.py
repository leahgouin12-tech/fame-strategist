"""The eight questions the plan is built on, and the refusal to answer them for her.

InterviewAnswers defaults every field to None and __post_init__ raises naming whichever
one is still missing, because a plan built on a guessed answer is a plan she cannot
actually follow. Interview.checklist returns what is absent plus the MIN_HOURS floor of
2 hours a week, Interview.complete is what the routes ask before planning, and
Interview.REQUIRED is the field list itself.

defaults is the one-click start on the home screen, and it is an adoption rather than a
guess - 5 hours, on camera, phone only, clips already on the device, three platforms,
zero followers - spelled back out by Interview.assumptions so a single click accepts
stated assumptions she can see, not an invisible profile.
"""

from dataclasses import dataclass, fields

MIN_HOURS = 2
FALLBACK_FOOTAGE = "the clips already sitting on your phone"


@dataclass
class InterviewAnswers:
    """Defaults are None, and None is refused: a plan built on a guessed answer is
    a plan the user cannot actually follow."""

    hours_per_week: int | None = None
    on_camera: bool | None = None
    has_clips: bool | None = None
    gear: str | None = None
    platforms: list[str] | None = None
    comfort: list[str] | None = None
    existing_followers: int | None = None
    what_you_actually_film: str | None = None

    def __post_init__(self):
        for f in fields(self):
            if getattr(self, f.name) is None:
                raise ValueError(f"{f.name} is required; the planner will not guess it")


class Interview:
    REQUIRED = [f.name for f in fields(InterviewAnswers)]

    @staticmethod
    def defaults(footage: str = "") -> InterviewAnswers:
        """The one-click start. These are stated assumptions, not answers the app
        claims to know - the home screen shows each one so a single click adopts them."""
        return InterviewAnswers(
            hours_per_week=5,
            on_camera=True,
            has_clips=True,
            gear="phone",
            platforms=["tiktok", "reels", "x"],
            comfort=["talking", "text on screen"],
            existing_followers=0,
            what_you_actually_film=footage.strip() or FALLBACK_FOOTAGE,
        )

    @staticmethod
    def assumptions(answers: InterviewAnswers) -> list[str]:
        return [
            f"{answers.hours_per_week} hours a week of real work",
            "on camera, phone only, clips you already have",
            "posted to " + ", ".join(answers.platforms),
            f"starting from {answers.existing_followers} followers",
            f"footage described as: {answers.what_you_actually_film}",
        ]

    @staticmethod
    def checklist(answers: InterviewAnswers) -> list[str]:
        need = [
            k
            for k in Interview.REQUIRED
            if not getattr(answers, k) and getattr(answers, k) != 0
        ]
        if answers.hours_per_week < MIN_HOURS:
            need.append(f"hours_per_week must be at least {MIN_HOURS}")
        return need

    @staticmethod
    def complete(answers: InterviewAnswers) -> bool:
        return answers is not None and not Interview.checklist(answers)
