"""What the model says is rising - kept where it cannot be mistaken for the playbook.

The playbook is citation-gated on purpose: `validate_entry` refuses an entry without a real
address somebody published, and the store refuses to load a playbook that failed validation.
That gate is the only thing separating this app from a motivational poster, so a model's
opinion does not get to walk through it. A model has read a great deal and remembered very
little of it precisely, and it will name a format that peaked in 2023 as if it were news.

So leads go somewhere else: the notes table, tagged, dated, labelled with the model that said
them, and shown on /trends under "Fresh, unverified" next to the findings that carry sources.
She can promote one by going and checking it - which is the point of having it written down.
"""

from dataclasses import dataclass
from datetime import date

LEAD_KIND = "lead"
LEAD_PARTS = ("lead_why", "lead_test", "lead_wrong")
LEAD_RUN = "lead_run"
MAX_LEADS = 6

SCHEMA = {
    "type": "object",
    "required": ["leads"],
    "properties": {
        "leads": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["format", "why_now", "how_to_test", "what_it_could_be_wrong"],
                "properties": {
                    "format": {"type": "string"},
                    "why_now": {"type": "string"},
                    "how_to_test": {"type": "string"},
                    "what_it_could_be_wrong": {"type": "string"},
                },
            },
        }
    },
}


@dataclass
class Lead:
    """One thing a model said is rising, and the sentence that admits it might be wrong."""

    format: str
    why_now: str
    how_to_test: str
    could_be_wrong: str
    said_by: str
    asked_on: str

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items()}


def ask(engine, *, platforms, hypotheses, chosen, today: date | None = None) -> list[Lead]:
    """Ask the model for leads. Offline, this returns nothing rather than a made-up list."""
    today = today or date.today()
    if engine.name == "offline":
        return []
    lanes = ", ".join(platforms) if platforms else "the platforms in my plan"
    data = engine.complete_json(
        "You are helping a creator decide what to film this week on a phone. Name formats and "
        "angles you believe are rising in her lanes right now. For each one, also say what "
        "could make you wrong - a stale memory, a lane you are guessing at, a format that "
        "already peaked. Do not invent a statistic, a study, a platform announcement or a "
        "date. Do not name a hashtag as a strategy. If you have nothing defensible for a lane, "
        "say less rather than filling the space.",
        f"As of {today.isoformat()}. Lanes: {lanes}. "
        f"Testing: {', '.join(hypotheses) if hypotheses else 'not chosen yet'}. "
        f"Running this week: {chosen or 'nothing yet'}. "
        f"Give me at most {MAX_LEADS} leads.",
        SCHEMA,
    )
    out = []
    for item in (data.get("leads") or [])[:MAX_LEADS]:
        text = str(item.get("format", "")).strip()
        if not text:
            continue
        out.append(Lead(
            format=text[:300],
            why_now=str(item.get("why_now", "")).strip()[:400],
            how_to_test=str(item.get("how_to_test", "")).strip()[:400],
            could_be_wrong=str(item.get("what_it_could_be_wrong", "")).strip()[:400],
            said_by=engine.name,
            asked_on=today.isoformat(),
        ))
    return out


def save(db, leads, today: date | None = None) -> int:
    """Write the leads and the fact that an ask happened, even when it found nothing.

    The run marker is what lets the page tell "never asked" apart from "asked, and the model
    declined to name anything" - the second is an answer and the first is not.
    """
    today = today or date.today()
    for lead in leads:
        db.remember(LEAD_KIND, lead.format, source=f"{lead.said_by} {lead.asked_on}",
                    seen_at=lead.asked_on)
        for kind, text in zip(LEAD_PARTS,
                              (lead.why_now, lead.how_to_test, lead.could_be_wrong)):
            db.remember(kind, text, source=lead.format, seen_at=lead.asked_on)
    db.remember(LEAD_RUN, str(len(leads)), source="asked", seen_at=today.isoformat())
    return len(leads)


def ran(db) -> bool:
    return bool(db.recall(LEAD_RUN, limit=1))


def _newest_by_source(db, kind: str, limit: int) -> dict:
    """The most recent note per source. `recall` comes back newest-first, so the first
    row seen for a source is the one that belongs to the lead being read."""
    out = {}
    for row in db.recall(kind, limit=limit):
        out.setdefault(row["source"], row["body"])
    return out


def load(db, limit: int = MAX_LEADS) -> list[Lead]:
    """Read the leads back, with the three sentences that belong to each one.

    Each part gets its own note kind rather than sharing one, because a shared kind would
    have to be re-sorted into the right order after coming back newest-first, and the order
    here is the meaning: the sentence about how it could be wrong must not be read as the
    reason to try it.
    """
    heads = db.recall(LEAD_KIND, limit=limit)
    why = _newest_by_source(db, LEAD_PARTS[0], limit * 4)
    test = _newest_by_source(db, LEAD_PARTS[1], limit * 4)
    wrong = _newest_by_source(db, LEAD_PARTS[2], limit * 4)
    out = []
    for row in heads:
        said_by, _, asked_on = row["source"].rpartition(" ")
        out.append(Lead(
            format=row["body"],
            why_now=why.get(row["body"], ""),
            how_to_test=test.get(row["body"], ""),
            could_be_wrong=wrong.get(row["body"], ""),
            said_by=said_by,
            asked_on=asked_on or row["seen_at"],
        ))
    return out


def note(leads, ran: bool) -> str:
    if not ran:
        return ("No lead has been asked for yet. Ask for one and it appears here labelled for "
                "what it is - a model's recollection, dated, with the sentence that says how it "
                "could be wrong. It does not enter the playbook, and the playbook is the part "
                "of this app that has sources.")
    if not leads:
        return ("The model was asked and gave nothing it could defend. That is a usable answer: "
                "the findings above are the ones somebody published.")
    return (f"{len(leads)} lead{'' if len(leads) == 1 else 's'} from a model, not from a "
            "source. Each carries the date it was asked and the way it says it could be wrong. "
            "None of them is a finding, none of them has been promoted into the playbook, and "
            "the plan will not change on the strength of one - you film it, your own numbers "
            "decide.")
