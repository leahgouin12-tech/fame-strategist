"""Spec 5.9's second half: the two currencies, kept apart because they are not the same kind
of number. Model quota is counted by this app from calls that actually produced text. Agent
credits cannot be read from here at all, so that column is hers to state and it says so.

Local work is listed too, and it is not a currency: CPU on a machine she already owns costs
nothing per post and never will.
"""

from dataclasses import dataclass, field


@dataclass
class Currency:
    name: str
    total: str
    per_post: str
    basis: str


@dataclass
class Spend:
    posts: int
    currencies: list = field(default_factory=list)
    local: str = ""
    note: str = ""

    @property
    def measured(self) -> bool:
        return self.posts > 0


def _n(count, word) -> str:
    plural = "" if float(count) == 1 else "s"
    return f"{count:g} {word}{plural}"


def _per(amount, posts, unit) -> str:
    if amount is None:
        return "not stated"
    if not posts:
        return "no posts to divide"
    value = round(amount / posts, 3)
    return f"{value:g} {unit}" if float(value) == 1 else f"{value:g} {unit}s"


def tally(*, spend: dict, ops: list, judged: int, posts: int,
          engine_name: str, offline: bool) -> Spend:
    calls = int(spend.get("model_calls") or 0)
    reported = spend.get("credits")
    credits = None if reported in (None, "") else float(reported)
    out = Spend(posts=posts)

    if calls:
        quota_basis = ("Counted here: one call each time the writer asked a model for a hook "
                       f"line and got text back. The engine is {engine_name} and this is "
                       "their total.")
    elif offline:
        quota_basis = ("The engine on this machine is offline, so a model call has not been "
                       "possible - 0 recorded, and none hiding somewhere else.")
    else:
        quota_basis = (f"Zero calls recorded with the engine at {engine_name}: the writer has "
                       "not needed a line from a model yet.")
    out.currencies.append(Currency("model quota", _n(calls, "call"),
                                   _per(calls, posts, "call"), quota_basis))

    if credits is None:
        out.currencies.append(Currency(
            "agent credits", "not stated", "not stated",
            "Nothing in this app can read a Qoder balance, so this number only exists if you "
            "type it. Until then the cell is empty rather than guessed - an invented zero "
            "would look like a receipt."))
    else:
        stated = f" {spend['credits_note']}." if spend.get("credits_note") else ""
        out.currencies.append(Currency(
            "agent credits", _n(credits, "credit"), _per(credits, posts, "credit"),
            "Self-reported by you, and it stays yours to correct." + stated))

    edits = len({row["file"] for row in ops})
    out.local = (f"{_n(len(ops), 'edit operation')} logged across {_n(edits, 'saved file')}, "
                 f"{_n(judged, 'score')} written by this machine. All local CPU, which costs "
                 "nothing per post and is not a currency.")

    if not posts:
        out.note = ("No imported posts yet, so nothing divides. Put your numbers on this page "
                    "and the same two currencies reappear per post instead of in total.")
    elif calls == 0 and credits is None:
        out.note = (f"Divided across {_n(posts, 'imported post')}. The quota column is a "
                    "counted zero and the credits column is empty, because you have not "
                    "stated any.")
    else:
        out.note = (f"Divided across {_n(posts, 'imported post')}. The quota column is a "
                    "receipt from this machine; the credits column is what you told it.")
    return out
