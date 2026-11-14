"""What a remembered verdict does to the next eight weeks.

The lab writes "Kept X, dropped Y" into agent memory, and the page tells her the dropped arm
does not get a week back. That sentence is only worth printing if the plan builder actually
reads the note, so these tests build the plan from the memory rows and check the weeks,
the concentration phase, and the two cases where the honest answer is "that changes nothing
yet" or "there is nothing else to run".
"""

from datetime import date

from src.engines.offline import OfflineEngine
from src.experiment import ledger as L
from src.metrics.ingest import MetricRow
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES

START = date(2026, 11, 9)
H = rank(score_candidates(ENTRIES, ANSWERS))
NAMES = [h.name for h in H]
PLAIN = compose_plan(ENTRIES, ANSWERS, H, OfflineEngine(), START)


def build(dropped):
    return compose_plan(ENTRIES, ANSWERS, H, OfflineEngine(), START, dropped=dropped)


def row(ref, watch, follows, hypothesis, views=1000):
    return MetricRow("logged", ref, START, views * 3, views, watch, follows, 4, 1,
                     hypothesis=hypothesis)


def test_a_dropped_arm_loses_its_experiment_week_to_the_next_one():
    got = build([NAMES[1]])
    assert [w.experiment for w in got.weeks[:4]] == [NAMES[0], NAMES[2], NAMES[3], NAMES[4]], \
        "each surviving arm moves up one week, in ranking order"
    assert any(NAMES[1] in n and NAMES[2] in n for n in got.verdict_notes), got.verdict_notes


def test_a_plan_with_nothing_dropped_is_the_plan_it_always_was():
    """The verdict loop must not shift a single word for anybody who has not run a test."""
    assert build([]).to_dict() == PLAIN.to_dict()
    assert build(["a-hypothesis-that-was-never-ranked"]).to_dict() == PLAIN.to_dict()


def test_the_concentration_phase_follows_the_verdict_too():
    """Weeks 5-8 double down on the top hypothesis. If the lab dropped the top one, keeping
    it there would spend four weeks on the arm the numbers just retired."""
    got = build([NAMES[0]])
    assert got.chosen == NAMES[1], got.chosen
    assert NAMES[0] not in " ".join(w.goal for w in got.weeks[4:]), "it still names the loser"


def test_dropping_an_arm_below_the_experiment_weeks_changes_no_week():
    got = build([NAMES[4]])
    assert [w.experiment for w in got.weeks[:4]] == [w.experiment for w in PLAIN.weeks[:4]]
    assert any("below the four experiment weeks" in n for n in got.verdict_notes), \
        "a verdict that cannot move a week has to say so rather than look ignored"


def test_when_every_hypothesis_is_dropped_the_plan_says_there_is_nothing_else():
    got = build(NAMES)
    assert [w.experiment for w in got.weeks[:4]] == [w.experiment for w in PLAIN.weeks[:4]], \
        "it still has to produce eight weeks, not crash or blank out"
    assert len(got.verdict_notes) == 1
    assert "nothing else" in got.verdict_notes[0], got.verdict_notes


def test_the_verdict_sentence_and_the_plan_input_are_one_format():
    """`dropped()` reads back exactly what `decision_text()` writes, so the lab page and the
    plan builder cannot drift into two formats - which is how a written verdict stops
    counting without anybody noticing."""
    rows = [row(f"a{i}", 30.0, 14, NAMES[0]) for i in range(5)] \
        + [row(f"b{i}", 30.0, 5, NAMES[1]) for i in range(5)]
    called = L.verdict(L.ledger(rows), PLAIN)
    assert called.decided, called
    note = {"body": L.decision_text(called), "seen_at": "2026-11-14", "id": 1}
    assert L.dropped([note]) == [NAMES[1]]
    assert build(L.dropped([note])).weeks[1].experiment == NAMES[2]


def test_a_refusal_in_memory_is_not_read_as_a_verdict():
    """The lab also stores the not-yet lines. Treating one of those as a dropped arm would
    take a week away from a hypothesis that was never tested against anything."""
    refused = L.verdict(L.ledger([row(f"a{i}", 30.0, 14, NAMES[0]) for i in range(5)]), PLAIN)
    assert not refused.decided
    note = {"body": L.decision_text(refused), "seen_at": "2026-11-14", "id": 2}
    assert L.dropped([note]) == []
    assert build(L.dropped([note])).to_dict() == PLAIN.to_dict()
