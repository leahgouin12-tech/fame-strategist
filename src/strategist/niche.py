"""Scoring seven candidate formats against her answers and whatever evidence exists.

Each CANDIDATES row is a name, the tags whose evidence supports it, a base appeal and
whether it needs her face. score_candidates gives it three numbers: fit, the base appeal
times the average confidence, read through WEIGHT, of the playbook entries sharing its
tags and halved by FACE_PENALTY when the format needs a face and on_camera was
refused; saturation, which is only how well sourced our own read of crowding is; and
supply, from the hours per week and the clips she said she has. rank keeps the top six,
and brief writes the arithmetic out instead of smoothing it, with a risk line naming the
weakest part.

No engine is consulted anywhere in this file, and a saturation_score of 0 means this app
has no sourced idea about how crowded that space is - not that the space is open.
"""

from dataclasses import dataclass, field

WEIGHT = {"proven": 1.0, "strong": 0.7, "contested": 0.35, "folklore": 0.1}

# name, tags whose evidence supports it, base appeal, does it require showing your face
CANDIDATES = [
    ("lifestyle-day-in-life", ["format", "retention", "conversion"], 0.9, True),
    ("outfit-and-style", ["format", "conversion"], 0.8, False),
    ("beauty-glam", ["format", "retention"], 0.6, True),
    ("opinion-and-hottake", ["hook", "engagement", "algorithm"], 0.75, True),
    ("tutorial-value", ["retention", "conversion", "series"], 0.7, False),
    ("build-in-public-devlog", ["series", "engagement", "conversion"], 0.5, False),
    ("comedy-sketch-pov", ["hook", "retention", "series"], 0.45, True),
]

FACE_PENALTY = 0.5


@dataclass
class NicheHypothesis:
    """A testable claim about where this person should post, not a personality verdict.

    fit = does the evidence-backed format suit the answers given
    saturation = how well-sourced our read of crowding in that space is (0 = no idea)
    supply = can this person actually keep producing it at their hours and gear
    """

    name: str
    evidence_ids: list[str]
    fit_score: float
    saturation_score: float
    supply_score: float
    why: str
    risk: str
    total: float = 0.0
    tags: list[str] = field(default_factory=list)

    def compute_total(self) -> float:
        self.total = round(
            0.4 * self.fit_score + 0.3 * self.saturation_score + 0.3 * self.supply_score, 3
        )
        return self.total


@dataclass
class HypothesisBrief:
    name: str
    headline: str
    why: str
    risk: str
    evidence_ids: list[str]
    scores: dict


def _evidence(entries, tags):
    hits = [e for e in entries if set(e.tags) & set(tags)]
    strength = round(sum(WEIGHT[h.confidence.value] for h in hits) / max(len(hits), 1), 3)
    return hits, strength if hits else 0.0


def score_candidates(entries, answers) -> list[NicheHypothesis]:
    niche_hits, niche_strength = _evidence(entries, ["niche"])
    out = []
    for name, tags, base, needs_face in CANDIDATES:
        hits, strength = _evidence(entries, tags)
        face_fit = 1.0 if (not needs_face or answers.on_camera) else FACE_PENALTY
        supply = min(
            1.0,
            base
            * (0.6 + 0.1 * answers.hours_per_week)
            * (1.1 if answers.has_clips else 0.8),
        )
        cited = sorted({h.id for h in hits} | {h.id for h in niche_hits})
        out.append(
            NicheHypothesis(
                name=name,
                evidence_ids=cited,
                fit_score=round(base * strength * face_fit, 3),
                saturation_score=round(niche_strength, 3),
                supply_score=round(supply, 3),
                why="",
                risk="",
                tags=tags,
            )
        )
    for h in out:
        h.compute_total()
    return out


def rank(hypotheses, limit=6) -> list[NicheHypothesis]:
    return sorted(hypotheses, key=lambda h: (-h.total, h.name))[:limit]


def brief(h: NicheHypothesis) -> HypothesisBrief:
    """The audit trail in one object. Arithmetic first; an engine can rewrite `why`
    later, but nothing is ever said that is not backed by these numbers."""
    return HypothesisBrief(
        name=h.name,
        headline=f"{h.name}: {h.total}",
        why=(
            f"fit {h.fit_score} (format evidence x your answers), "
            f"saturation {h.saturation_score} (how well sourced the crowding read is), "
            f"supply {h.supply_score} (hours and footage you actually have)."
        ),
        risk=h.risk
        or (
            "no playbook entry tagged niche supports this yet"
            if h.saturation_score == 0
            else "evidence is weaker than proven; treat as a test, not a fact"
        ),
        evidence_ids=h.evidence_ids,
        scores={"fit": h.fit_score, "saturation": h.saturation_score, "supply": h.supply_score,
                "total": h.total},
    )
