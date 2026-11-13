"""Spec 5.9: does this app's taste predict what her audience actually did?

Nothing here is a claim about cause. The rubric measures a frame; an audience answers the
frame, the hook, the topic and the hour at once, and her export cannot separate them. What
this page can honestly do is say whether the two numbers move together, whether chance is a
plausible explanation of the size of the movement, and - the finding worth more than the
app's own opinion - whether they move apart.

The chance test is a reshuffle, not a table: the outcome column is permuted a fixed number
of times from a fixed seed, so the same pairs always give the same answer and no statistical
library is needed to lie with authority.
"""

from dataclasses import dataclass, field
from statistics import median
import math
import random

from src.media.aesthetic import WEIGHTS
from src.metrics.adapt import DATA_FLOOR

PRIMARY = "follow_rate_per_1000"
MEASURES = [("views", "reach"), ("avg_watch_pct", "watched"), (PRIMARY, "follows per 1000")]
SHUFFLES = 2000
SEED = 20261113
NOISE = 0.20  # below this a rank correlation is not a direction, it is rounding
WEIGHT_FLOOR = 12  # a rubric change is a bigger claim than a reading
GAP_FLOOR = 0.20  # relative gap the inversion sentence waits for


@dataclass
class Pair:
    ref: str
    kind: str
    score: float
    band: str
    parts: dict
    row: object


@dataclass
class Suggestion:
    component: str
    current: float
    proposed: float
    why: str


@dataclass
class Report:
    scored: int
    posted: int
    pairs: list = field(default_factory=list)
    links: list = field(default_factory=list)
    halves: list = field(default_factory=list)
    inversion: str = ""
    overrides: str = ""
    suggestions: list = field(default_factory=list)
    weight_note: str = ""
    note: str = ""
    measured: bool = False

    @property
    def count(self) -> int:
        return len(self.pairs)

    @property
    def need(self) -> int:
        return max(0, DATA_FLOOR - self.count)


def rank(values) -> list[float]:
    """Average ranks, so two posts with the same view count share a rank instead of the
    app inventing an order between them."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = sum(range(i + 1, j + 2)) / (j - i + 1)
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
    return out


def rho(xs, ys):
    """Spearman's rank correlation, computed as Pearson on the ranks. None when a column
    never moves: there is no association to report if nothing varies."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (dx * dy), 3)


def chance(xs, ys, observed, shuffles: int = SHUFFLES, seed: int = SEED):
    """How often a reshuffle of her own numbers lands on a link this strong. Small means
    noise hardly explains it; large means a coin flip does this often."""
    if observed is None:
        return None
    rng = random.Random(seed)
    pool = list(ys)
    hits = sum(1 for _ in range(shuffles)
               if abs(rho(xs, rng.sample(pool, len(pool))) or 0.0) >= abs(observed) - 1e-9)
    return round(hits / shuffles, 4)


def stem(ref: str) -> str:
    """clip-0042.jpg, clip-0042 and data/inbox/clip-0042 all name the same post."""
    tail = str(ref).replace("\\", "/").split("/")[-1].strip().lower()
    return tail.rsplit(".", 1)[0] if "." in tail else tail


def pair(scores: dict, rows) -> list[Pair]:
    """Matched on the file name she posted under, because that is the only key both sides
    hold. A post that matches nothing stays unpaired and is counted, not dropped quietly."""
    out = []
    for row in rows:
        hit = scores.get(stem(row.post_ref))
        if hit is None:
            continue
        out.append(Pair(ref=stem(row.post_ref), kind=hit["kind"], score=float(hit["score"]),
                        band=hit["band"], parts=hit.get("parts") or {}, row=row))
    return out


def _words(value, p) -> str:
    if value is None:
        return "nothing to correlate: one of the two columns never moved across these posts"
    strength = ("no real relationship" if abs(value) < NOISE else
                "a weak lean" if abs(value) < 0.5 else
                "a strong lean" if abs(value) < 0.8 else "near lockstep")
    movement = "move together" if value > 0 else "move in opposite directions"
    if p is None:
        doubt = "not tested"
    elif p == 0:
        doubt = (f"chance never produced a link this big in {SHUFFLES} reshuffles of your own "
                 "numbers")
    else:
        doubt = (f"chance produced a link this big in {round(p * SHUFFLES)} of {SHUFFLES} "
                 "reshuffles of your own numbers")
    return f"{strength} - the two {movement}. {doubt}."


def _halves(pairs) -> list[dict]:
    ordered = sorted(pairs, key=lambda p: p.score)
    cut = len(ordered) // 2
    out = []
    for label, group in (("what this app liked", ordered[cut:]),
                         ("what it scored lower", ordered[:cut])):
        if not group:
            continue
        out.append({"label": label, "count": len(group),
                    "median_score": round(median(p.score for p in group), 1),
                    **{name: round(median(getattr(p.row, name) for p in group), 2)
                       for name, _ in MEASURES}})
    return out


def _inversion(halves, weights) -> str:
    liked = next((h for h in halves if h["label"] == "what this app liked"), None)
    lower = next((h for h in halves if h["label"] == "what it scored lower"), None)
    if not liked or not lower:
        return ""
    a, b = liked[PRIMARY], lower[PRIMARY]
    if a >= b or b <= 0 or (b - a) / b < GAP_FLOOR:
        return ""
    heaviest = sorted(weights.items(), key=lambda kw: -kw[1])[0]
    return (f"the posts this app scored {lower['median_score']}/10 converted {b} follows per "
            f"1000 against {a} for the ones it liked at {liked['median_score']}/10. The half "
            "this rubric preferred is the half your audience paid less attention to, so it is "
            f"not buying what the rubric rewards - and {heaviest[0]}, at {heaviest[1]:.0%} of "
            "the score, is where that rubric puts most of its belief. That is a finding about "
            "the rubric, not about you.")


def _overrides(pairs) -> str:
    weak = [p for p in pairs if p.band == "weak"]
    if not weak:
        return ""
    return (f"you posted {len(weak)} of these while this app still called the frame weak "
            f"({', '.join(p.ref for p in weak[:5])}). Those are the posts where your judgement "
            "already overrode the rubric, and they are in the numbers above.")


def reweight(pairs, current=None):
    """Returns (vector, suggestions, note), and applies nothing. The vector exists so the
    accept button can write exactly the numbers she was shown, and it exists only while her own
    data supports it. A component that carries no signal keeps the weight it already has, so a
    proposal never moves weight out of a part of the rubric it has not read."""
    base = dict(current or WEIGHTS)
    if len(pairs) < WEIGHT_FLOOR:
        return None, [], (f"A reweight waits for {WEIGHT_FLOOR} paired posts, because a weight "
                          f"moves every future score and not just this week's. There are {len(pairs)}.")
    scored = [p for p in pairs if all(c in p.parts for c in base)]
    if len(scored) < WEIGHT_FLOOR:
        return None, [], (f"{len(scored)} of the {len(pairs)} pairs carry every component this "
                          "rubric scores, and a reweight needs them all. The pairing is fine - "
                          "the older judgements were stored before every component was kept.")
    outcomes = [getattr(p.row, PRIMARY) for p in scored]
    usable = {c: v for c, v in ((c, rho([p.parts[c] for p in scored], outcomes)) for c in base)
              if v is not None}
    if not usable:
        return None, [], ("no component varied against your follows on these posts, so nothing "
                          "here has earned a weight change")
    ranked = sorted(usable.items(), key=lambda cv: -cv[1])
    best, worst = ranked[0], ranked[-1]
    if best[1] < 0.35 or worst[1] > -0.2:
        return None, [], (f"on {len(scored)} paired posts every part of the rubric moves about "
                          "the same against your follows, so a reweight would be moving numbers "
                          "that have not earned it.")
    positives = {c: max(v, 0.05) for c, v in usable.items()}
    scale = sum(base[c] for c in usable) / sum(positives.values())
    vector = dict(base)
    for c in usable:
        candidate = positives[c] * scale
        vector[c] = base[c] if abs(candidate - base[c]) < 0.05 else round(candidate, 2)
    changed = [c for c in usable if abs(vector[c] - base[c]) >= 0.01]
    if not changed:
        return None, [], ("your own numbers currently agree with the weights in use, so there is "
                          "nothing here worth changing")
    top = max(changed, key=lambda c: vector[c])
    vector[top] = round(vector[top] + 1.0 - sum(vector.values()), 2)
    why = (f"{best[0]} moves with your follows (rank {best[1]:+.2f}) while {worst[0]} moves "
           f"against them (rank {worst[1]:+.2f})")
    out = [Suggestion(c, base[c], vector[c], f"{base[c]:.0%} to {vector[c]:.0%} - {why}.")
           for c in sorted(changed, key=lambda k: -vector[k])]
    return vector, out, ("This is a proposal read off your own numbers. The weights in use are "
                         "still scoring until you accept it, and accepting is reversible here.")


def accept_vector(pairs, current=None):
    """The vector behind the live proposal, recomputed from her own rows when the button is
    pressed, so a form on the page never carries a number this app would write without earning."""
    vector, suggestions, _ = reweight(pairs, current)
    return vector if suggestions else None


def report(scores: dict, rows, weights=None) -> Report:
    """The whole reading in one call: pairs, links, halves, the inversion, and the reweight
    proposal it does not apply."""
    weights = dict(weights or WEIGHTS)
    pairs = pair(scores, rows)
    r = Report(scored=len(scores), posted=len(rows), pairs=pairs)
    if not scores:
        r.note = ("Nothing scored yet, so there is nothing to compare. The Photos and Clips "
                  "pages write a score the moment they read a file; a post only enters this "
                  "table once its numbers are on the Numbers page under the same name.")
        return r
    if len(pairs) < DATA_FLOOR:
        unmatched = len(rows) - len(pairs)
        r.note = (f"{len(pairs)} of the {len(rows)} imported posts have a score this app "
                  f"measured from the file itself"
                  f"{f' ({unmatched} named something not in your folders)' if unmatched else ''}. "
                  f"{DATA_FLOOR} paired posts is the floor this page will speak at, so "
                  f"{r.need} more. Type the file name you posted as the reference - that is the "
                  "whole link between a frame and its numbers, and nothing here guesses it for you.")
        return r
    r.measured = True
    outcomes = {name: [getattr(p.row, name) for p in pairs] for name, _ in MEASURES}
    scores_col = [p.score for p in pairs]
    for name, label in MEASURES:
        value = rho(scores_col, outcomes[name])
        p = chance(scores_col, outcomes[name], value)
        r.links.append({"key": name, "label": label, "rho": value, "chance": p,
                        "words": _words(value, p)})
    r.halves = _halves(pairs)
    r.inversion = _inversion(r.halves, weights)
    r.overrides = _overrides(pairs)
    _, r.suggestions, r.weight_note = reweight(pairs, weights)
    r.note = (f"{len(pairs)} posts carry both halves of the loop: a score this app measured "
              "from the file itself, and the numbers your audience left behind.")
    return r
