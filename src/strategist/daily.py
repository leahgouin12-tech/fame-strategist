from dataclasses import dataclass
from datetime import date
import re

from src.strategist.interview import FALLBACK_FOOTAGE

# The one phrase allowed when she has not described her footage yet. It must read as a
# sentence a stranger would watch, never as the app describing its own placeholder.
GENERIC_SUBJECT = "real life"

BANNED_HASHTAGS = {"#fyp", "#viral", "#foryou", "#foryoupage", "#trending", "#xyzbca", "#foryoupage"}
MAX_SHOTS = 6
MAX_SHOT_SECONDS = 90
ROTATE_ACROSS = 3

# format label, narrative beats, (shot, framing, seconds, note), tags
FORMATS = {
    "lifestyle-day-in-life": (
        "day-in-life",
        ["where you are and why it matters today", "the one thing you did", "what changed because of it"],
        [
            ("Cold open on the activity already in progress", "vertical, chest-up, 3s in", 6,
             "no talking head intro, start mid-action"),
            ("Name the one thing today in one sentence", "same framing, jump cut", 12, "one breath, no preamble"),
            ("Show it happening", "hands and object, no face", 20, "keep the room sound"),
            ("Land the change", "closest crop", 10, "say the outcome, then stop"),
        ],
        ["#dayinlife", "#routine", "#minivlog"],
    ),
    "outfit-and-style": (
        "outfit breakdown",
        ["the constraint you are dressing for", "why each piece is there", "the one detail people miss"],
        [
            ("Full outfit in one static frame", "vertical, full body", 5, "natural light, no pose sequence"),
            ("Two pieces that make it work, explained", "waist-up, cut to detail", 20, "say the reason, not the brand"),
            ("The detail most people skip", "close crop on hands or hem", 12, "hold it still so the crop reads"),
        ],
        ["#outfit", "#styling", "#fitcheck"],
    ),
    "beauty-glam": (
        "process, not result",
        ["the problem this solves", "the two steps that matter", "how it looked hours later"],
        [
            ("Start on the unfinished side", "vertical, chest-up", 6, "no filter, real lighting"),
            ("The two steps that do the work", "tight crop, jump cut each step", 30, "skip the setup shots"),
            ("The result in the same light as the start", "same framing as shot 1", 10, "match the light or the claim is void"),
        ],
        ["#glam", "#howto", "#nomakeup"],
    ),
    "opinion-and-hottake": (
        "spoken claim",
        ["the claim in one sentence", "the strongest reason you hold it", "what would change your mind"],
        [
            ("The claim, no scene-set", "vertical, chest-up, eyes to lens", 8, "cut anything before the claim"),
            ("The reason", "same framing, jump cut", 25, "one example beats three adjectives"),
            ("What would change your mind", "same framing", 12, "this is the part that gets comments"),
        ],
        ["#opinion", "#hot_take", "#discussion"],
    ),
    "tutorial-value": (
        "one idea only",
        ["what you can do after watching", "the step people get wrong", "the check that it worked"],
        [
            ("State what they will be able to do", "vertical, chest-up", 6, "promise a result, not a topic"),
            ("Do the step people get wrong", "overhead or screen, tight", 30, "show the mistake for one second first"),
            ("Show the check", "same framing as the step", 12, "proof, not summary"),
        ],
        ["#learnontiktok", "#howto", "#tutorial"],
    ),
    "build-in-public-devlog": (
        "progress report",
        ["what was broken", "what you did about it", "what is still broken"],
        [
            ("The problem, shown on screen", "screen recording, no face", 8, "start on the error, not the intro"),
            ("What you changed", "same recording, jump cut", 30, "say the tradeoff you accepted"),
            ("What is still wrong", "chest-up", 12, "honesty here is the reason they follow"),
        ],
        ["#buildinpublic", "#devlog", "#indie"],
    ),
    "comedy-sketch-pov": (
        "one premise",
        ["the situation in one line", "the escalation", "the turn"],
        [
            ("Set the premise in text on screen", "vertical, chest-up", 5, "one line, then cut"),
            ("Escalate once, hard", "same framing, wider", 20, "two escalations is two videos"),
            ("The turn", "closest crop", 8, "end on it, do not tag a summary"),
        ],
        ["#pov", "#sketch", "#relatable"],
    ),
}
DEFAULT_FORMAT = FORMATS["tutorial-value"]

MAX_HOOK_CHARS = 90

# Spoken first lines that work with no model key. Each one only claims the video will
# show something, never that it worked - and {subject} always comes from their own words.
HOOK_FRAMES = {
    "lifestyle-day-in-life": [
        "One day of {subject}, unedited, starting mid-action.",
        "{subject} - the part I normally cut out is the actual point.",
        "This is what {subject} looks like on a day that isn't working.",
    ],
    "outfit-and-style": [
        "The thing about {subject} nobody explains out loud.",
        "{subject}: the one detail everyone skips.",
        "I'm going to say the quiet part about {subject}.",
    ],
    "beauty-glam": [
        "Before I touch {subject}, look at it in this light.",
        "{subject} is two steps, not eight.",
        "This is what {subject} looks like hours later, same light.",
    ],
    "opinion-and-hottake": [
        "Unpopular opinion about {subject}, and I'll give you the one reason.",
        "I think {subject} is being done wrong. Here's why.",
        "Tell me I'm wrong about {subject} - here's what would change my mind.",
    ],
    "tutorial-value": [
        "By the end of this you'll have {subject} working.",
        "The step everyone skips in {subject}.",
        "{subject}: one mistake, one fix, one check.",
    ],
    "build-in-public-devlog": [
        "What broke today in {subject}, and what I actually did about it.",
        "{subject} is still wrong. Here's the part that moved.",
        "I changed one thing in {subject} and it cost me another.",
    ],
    "comedy-sketch-pov": [
        "POV: {subject}.",
        "POV you're {subject} and it's first thing in the morning.",
        "Everyone has met {subject} at exactly the wrong moment.",
    ],
}
DEFAULT_FRAMES = HOOK_FRAMES["tutorial-value"]

CAPTION_ASKS = [
    "Which part is wrong for you?",
    "What would you have done instead?",
    "Tell me the version that actually works.",
    "Is this the normal thing or just my thing?",
]
# What the caption promises about the form of the video - never about its result.
CAPTION_TAILS = {
    "lifestyle-day-in-life": "no transitions, nothing cut",
    "outfit-and-style": "every piece has a reason",
    "beauty-glam": "same light at the start and the end",
    "opinion-and-hottake": "say it once, then let the comments argue",
    "tutorial-value": "one mistake, one fix, one check",
    "build-in-public-devlog": "the broken part stays in",
    "comedy-sketch-pov": "that's the whole joke",
}
DEFAULT_TAIL = "one idea, nothing else"


def _subject(answers, label: str) -> str:
    """Their own footage description, trimmed to one clause - the only specific detail
    the local writer is allowed to use."""
    raw = str(getattr(answers, "what_you_actually_film", "") or "").strip()
    if not raw or raw.lower() == FALLBACK_FOOTAGE.lower():
        return GENERIC_SUBJECT
    first = [p.strip() for p in re.split(r"[,;.]| and ", raw) if p.strip()]
    return (first[0] if first else raw)[:48].rstrip(" -")


def local_copy(hypothesis: str, subject: str, day: date) -> tuple[str, str]:
    frames = HOOK_FRAMES.get(hypothesis, DEFAULT_FRAMES)
    hook = frames[day.toordinal() % len(frames)].format(subject=subject)[:MAX_HOOK_CHARS]
    hook = hook[:1].upper() + hook[1:]
    tail = CAPTION_TAILS.get(hypothesis, DEFAULT_TAIL)
    ask = CAPTION_ASKS[(day.toordinal() // 2) % len(CAPTION_ASKS)]
    caption = f"{subject[:1].upper()}{subject[1:]}, {tail}. {ask}"[:200]
    return hook, caption



def subject_of(answers) -> str:
    """The one specific detail the local writer is allowed to use, for callers outside
    this module - the voice writer builds today's line in three platforms from it."""
    return _subject(answers, "")


@dataclass
class Shot:
    desc: str
    framing: str
    seconds: int
    note: str


@dataclass
class Day:
    date: date
    week_no: int
    hypothesis: str
    format: str
    hook: str
    beats: list[str]
    shots: list[Shot]
    caption: str
    hashtags: list[str]
    sourced_from: list[str]
    cost_note: str
    copy_origin: str = "local"

    def as_checklist(self) -> list[str]:
        items = [f"Hook: {self.hook}"]
        items += [
            f"Shot {i + 1}: {s.desc} ({s.framing}, {s.seconds}s)"
            for i, s in enumerate(self.shots)
        ]
        items.append(f"Caption: {self.caption}")
        items.append(f"Tags: {' '.join(self.hashtags)}")
        items.append(f"Basis: {', '.join(self.sourced_from) or 'none - this day is unsourced'}")
        return items


def _week_index(plan, day: date) -> int:
    start = date.fromisoformat(plan.start_date) if plan.start_date else day
    return max(0, min(len(plan.weeks) - 1, (day - start).days // 7))


def _hypothesis(plan, day: date, week_no: int) -> str:
    if not plan.hypotheses:
        return "unspecified"
    if week_no <= 4:
        start = date.fromisoformat(plan.start_date) if plan.start_date else day
        return plan.hypotheses[(day - start).days % min(ROTATE_ACROSS, len(plan.hypotheses))]
    return plan.hypotheses[0]


HOOK_SCHEMA = {
    "type": "object",
    "required": ["hook", "caption"],
    "properties": {"hook": {"type": "string"}, "caption": {"type": "string"}},
}


def build_day(plan, entries, answers, day: date, engine) -> Day:
    idx = _week_index(plan, day)
    week = plan.weeks[idx]
    hypothesis = _hypothesis(plan, day, week.week_no)
    label, beats, shot_specs, tags = FORMATS.get(hypothesis, DEFAULT_FORMAT)

    try:
        out = engine.complete_json(
            "You write one spoken hook line and one short caption for a growing personal account. "
            "Plain language, specific, no hype words. Never comment on the person's appearance. "
            "The hook must be sayable in one breath.",
            f"Hypothesis: {hypothesis}. Format: {label}. "
            f"Footage they actually have: {answers.what_you_actually_film}. "
            f"This week's objective: {week.goal}. Beats: {'; '.join(beats)}.",
            HOOK_SCHEMA,
        )
        hook = str(out.get("hook", "")).strip()
        caption = str(out.get("caption", "")).strip()
    except Exception:
        hook = caption = ""

    # A missing or half-answer from the model never leaves a blank line: the local
    # writer is a complete sentence built from their own footage description.
    local_hook, local_caption = local_copy(hypothesis, _subject(answers, label), day)
    origin = "model" if hook and caption else "local"
    hook = (hook or local_hook)[:MAX_HOOK_CHARS]
    caption = caption or local_caption

    shots = [Shot(d, f, s, n) for d, f, s, n in shot_specs[:MAX_SHOTS]]
    total = sum(s.seconds for s in shots)
    while total > MAX_SHOT_SECONDS and len(shots) > 1:
        total -= shots.pop().seconds

    hashtags = []
    for t in tags:
        if t.lower() not in BANNED_HASHTAGS and t not in hashtags:
            hashtags.append(t)
    stem = "#" + hypothesis.split("-")[0].replace("_", "")
    if stem not in hashtags and len(hashtags) < 5:
        hashtags.insert(0, stem)

    return Day(
        date=day,
        week_no=week.week_no,
        hypothesis=hypothesis,
        format=label,
        hook=hook,
        beats=beats,
        shots=shots,
        caption=caption,
        hashtags=hashtags[:5],
        sourced_from=list(week.focus_entry_ids),
        copy_origin=origin,
        cost_note=(
            f"copy written by: {origin}"
            + (" (no key needed - swap in your own detail where it reads flat)" if origin == "local" else "")
            + f"; engine: {engine.name}"
        ),
    )
