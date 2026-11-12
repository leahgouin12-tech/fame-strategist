from datetime import date

from src.playbook.schema import Confidence, PlaybookEntry, Source, SourceTier
from src.strategist.interview import InterviewAnswers
from src.strategist.niche import CANDIDATES, brief, rank, score_candidates


def entry(id_, tags, confidence=Confidence.STRONG):
    return PlaybookEntry(
        id_,
        "x" * 25,
        "m",
        confidence,
        [Source("https://e.com", "t", SourceTier.PLATFORM_OFFICIAL)],
        ["tiktok"],
        date(2026, 9, 1),
        "limit",
        tags,
    )


ANSWERS = InterviewAnswers(5, True, True, "phone", ["tiktok"], ["talking"], 0, "outfits and room clips")
ENTRIES = [
    entry("niche-low-saturation", ["niche"], Confidence.PROVEN),
    entry("format-need-face", ["format", "hook"]),
    entry("conversion-series", ["conversion", "series"]),
    entry("algorithm-retention", ["algorithm", "retention"]),
]


def test_scores_are_bounded_zero_to_one():
    for h in score_candidates(ENTRIES, ANSWERS):
        assert 0 <= h.fit_score <= 1
        assert 0 <= h.saturation_score <= 1
        assert 0 <= h.supply_score <= 1


def test_proven_evidence_outranks_contested():
    weak = [entry("niche-weak", ["niche"], Confidence.FOLKLORE)] + ENTRIES
    with_proven_only = score_candidates(ENTRIES, ANSWERS)
    with_folklore_too = score_candidates(weak, ANSWERS)
    assert max(h.saturation_score for h in with_proven_only) > max(
        h.saturation_score for h in with_folklore_too
    )


def test_no_niche_evidence_means_no_saturation_claim():
    bare = [e for e in ENTRIES if "niche" not in e.tags]
    assert all(h.saturation_score == 0 for h in score_candidates(bare, ANSWERS))


def test_every_hypothesis_cites_the_entries_that_produced_it():
    for h in rank(score_candidates(ENTRIES, ANSWERS)):
        assert h.evidence_ids, "an unexplained hypothesis is not advice"


def test_four_to_six_hypotheses_are_returned():
    assert 4 <= len(rank(score_candidates(ENTRIES, ANSWERS))) <= 6


def test_ranking_is_stable_and_reproducible():
    a = [h.name for h in rank(score_candidates(ENTRIES, ANSWERS))]
    b = [h.name for h in rank(score_candidates(ENTRIES, ANSWERS))]
    assert a == b


def test_total_is_the_documented_weighted_sum():
    for h in score_candidates(ENTRIES, ANSWERS):
        assert h.total == round(
            0.4 * h.fit_score + 0.3 * h.saturation_score + 0.3 * h.supply_score, 3
        )


def test_off_camera_user_is_penalised_on_face_required_hypotheses():
    on = {h.name: h.fit_score for h in score_candidates(ENTRIES, ANSWERS)}
    off = {
        h.name: h.fit_score
        for h in score_candidates(
            ENTRIES, InterviewAnswers(5, False, True, "phone", ["tiktok"], [], 0, "clips")
        )
    }
    face = [name for name, _t, _b, needs_face in CANDIDATES if needs_face]
    assert face, "at least one hypothesis should require being on camera"
    assert all(off[n] < on[n] for n in face)


def test_more_hours_raises_supply_but_not_above_one():
    low = {h.name: h.supply_score for h in score_candidates(ENTRIES, ANSWERS)}
    high = {
        h.name: h.supply_score
        for h in score_candidates(
            ENTRIES, InterviewAnswers(20, True, True, "phone", ["tiktok"], [], 0, "clips")
        )
    }
    assert all(v <= 1.0 for v in high.values())
    assert sum(high.values()) > sum(low.values())


def test_brief_states_the_numbers_and_the_evidence_ids():
    b = brief(rank(score_candidates(ENTRIES, ANSWERS))[0])
    assert b.evidence_ids
    assert "fit" in b.why and "saturation" in b.why


def test_ranking_survives_an_empty_playbook_without_crashing():
    hs = rank(score_candidates([], ANSWERS))
    assert len(hs) == 6
    assert all(h.total == 0 or h.total >= 0 for h in hs)
