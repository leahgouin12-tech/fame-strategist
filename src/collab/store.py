"""The list itself: who she wants to work with, and the stage she says each ask is at.

Two things make this file exist rather than letting a route write straight into the database.

A name is not optional. This app has no login, cannot search for creators and does not rank
strangers, so an entry with no name in it is not a person she wants to work with - it is a blank
row that would then be counted in "who answered me". A blank is refused with the reason, not
filed under something usable.

A stage is checked against the five words this module understands. "sent" and "waiting" are what
people actually type, and accepting them quietly would drop an ask into a bucket the funnel then
counts wrongly, so an unknown stage comes back as a refusal that lists the five.

The reason and the ask are not judged here at all: an entry with a thin reason still saves, and
it is the pitch that refuses to write itself rather than invent one. That split is deliberate -
losing what she typed because a sentence was short is the app deciding for her.
"""

from src.collab import pitch

FIELDS = ("name", "why", "ask", "format", "platform")
MAX = {"name": 60, "why": 400, "ask": 300, "format": 80, "platform": 30}

NO_NAME = ("A name first. Nothing here finds one for you: this app has no login on any platform, "
           "it does not search or rank creators, so every entry starts as somebody you already "
           "saw and decided you would rather work with than at.")


def clean(row: dict) -> dict:
    """Trim and cap what she typed, and give it a stage. The cutting happens in one place so a
    route cannot forget one field and let an unbounded string into the list."""
    out = {key: str(row.get(key, "") or "").strip()[:MAX[key]] for key in FIELDS}
    status = str(row.get("status", "") or "").strip().lower()
    out["status"] = status if pitch.usable(status) else pitch.STATUSES[0]
    return out


def add(db, row: dict, made_at: str):
    """File one candidate. Returns (id, candidate) when it worked, (None, reason) when it did
    not - the reason is the sentence she gets, because a refusal with no reason reads as a bug."""
    item = clean(row)
    if not item["name"]:
        return None, NO_NAME
    return int(db.add_collab(item, made_at)), item


def _id(value) -> int:
    """A form field is a string, and a string that is not a number is not an entry - which the
    callers already have a sentence for. Parsing here means no route has to remember to."""
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def move(db, collab_id, status: str, moved_at: str) -> str:
    """She says what happened to an ask; this records the word she used. Nothing here can see a
    reply, so a stage this module does not know is refused rather than filed near enough."""
    wanted = str(status or "").strip().lower()
    if not pitch.usable(wanted):
        return ("'" + str(status or "").strip() + "' is not one of the stages: "
                + ", ".join(pitch.STATUSES) + ". This app cannot see an answer arrive, so a "
                "stage only moves when you say it did.")
    if not db.move_collab(_id(collab_id), wanted, moved_at):
        return "That entry is not on the list any more, so nothing was moved."
    return ""


def drop(db, collab_id) -> bool:
    """Remove one candidate. Returns whether there was anything there to remove."""
    wanted = _id(collab_id)
    if not wanted or wanted not in {row["id"] for row in db.get_collab()}:
        return False
    db.forget_collab(wanted)
    return True


def load(db) -> list:
    return db.get_collab()


def note(candidates, offers) -> str:
    """What the page says about its own emptiness, which is different for each of the two ways
    this page can be blank - and neither of them is a reason to invent a name or a number.
    Plain sentences only: the page owns its own links."""
    if candidates:
        return ""
    held = ("Nobody is on the list yet. Add the name and the specific thing about their account "
            "that made you want to work with them, and the pitch writes itself out of those two "
            "plus your own numbers - the reason has to be yours, because a reason this app made "
            "up is a line you would have to send and then explain.")
    if not offers:
        held += (" Nothing has been imported either, so there is no number of yours to quote: "
                 "until the Numbers page has posts in it, a pitch leads with the work and says "
                 "that out loud instead.")
    return held
