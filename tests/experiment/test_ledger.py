"""The lab's own arithmetic: which arm a post belongs to, and what two arms can prove.

Every verdict here is checked against the numbers that produced it, including the ones
where the honest answer is "not yet" - a ledger that always finds a winner is worse than no
ledger, so those refusals are the behaviour under test, not an empty case.
"""
from datetime import date

from src.engines.offline import OfflineEngine
from src.experiment import ledger as L
from src.metrics.adapt import AMPLIFY_RATIO, DATA_FLOOR, analyse
from src.metrics.ingest import MetricRow
from src.strategist.niche import rank, score_candidates
from src.strategist.plan import compose_plan
from tests.strategist.test_niche import ANSWERS, ENTRIES

START = date(2026, 11, 9)
PLAN = compose_plan(ENTRIES, ANSWERS, rank(score_candidates(ENTRIES, ANSWERS)),
                    OfflineEngine(), START)
A = PLAN.weeks[0].experiment
B = PLAN.weeks[1].experiment


def row(ref, watch, follows, views=1000, hypothesis=""):
    return MetricRow("logged", ref, START, views * 3, views, watch, follows, 4, 1,
                     hypothesis=hypothesis)


def arms(count, label, follows):
    """`count` posts under `label`, each converting `follows` on 1000 views."""
    return [row(f"{label[:3]}-{i}", 22.0, follows, hypothesis=label) for i in range(count)]


def test_the_arm_comes_from_the_week_the_plan_says_not_from_a_guess():
    assert L.arm_for(PLAN, START) == A
    assert L.arm_for(PLAN, START.replace(day=16)) == B
    assert L.arm_for(PLAN, date(2026, 12, 28)) == PLAN.weeks[-1].experiment


def test_no_plan_means_no_arm_rather_than_an_invented_one():
    assert L.arm_for(None, START) == ""


def test_tagging_only_fills_the_cells_that_are_empty():
    rows = [row("a", 20.0, 5, hypothesis=B), row("b", 20.0, 5)]
    got = L.tag(rows, A)
    assert [r.hypothesis for r in got] == [B, A], "a labelled post keeps what it ran under"
    assert L.tag(rows, "") == rows, "nothing to file under changes nothing"


def test_the_ledger_groups_by_arm_and_counts_what_it_cannot_place():
    rows = arms(3, A, 12) + arms(4, B, 3) + [row("x", 20.0, 2)]
    got = L.ledger(rows)
    assert [a.label for a in got.arms] == [A, B], "the better-converting arm leads"
    assert [a.n for a in got.arms] == [3, 4]
    assert (got.unlabelled, got.posts, got.labelled) == (1, 8, 7)
    assert got.arms[0].rate == 12.0 and got.arms[1].rate == 3.0


def test_a_test_with_no_plan_has_nothing_to_compare():
    got = L.verdict(L.ledger(arms(9, A, 12)), None)
    assert (got.state, got.winner) == ("no plan", "")
    assert "eight weeks" in got.missing.lower() or "plan" in got.missing.lower()


def test_below_the_floor_the_lab_refuses_instead_of_guessing():
    rows = arms(2, A, 12) + arms(2, B, 3)
    got = L.verdict(L.ledger(rows), PLAN)
    assert got.state == "thin"
    assert str(DATA_FLOOR - len(rows)) in got.missing, got.missing
    assert got.winner == "", "a winner named from four posts is the thing this app forbids"


def test_an_empty_ledger_says_so_in_words_that_fit_zero():
    """This is the state she meets first, and the sentence written for four posts reads as
    nonsense with none: `0 posts is under the floor of 8 ... 0 carry a label and 0 do not`."""
    got = L.verdict(L.ledger([]), PLAN)
    assert (got.state, got.winner) == ("thin", "")
    assert got.headline == "Nothing is stored yet, so there is no test to call."
    assert "0 " not in got.lines[0] and got.lines[0], got.lines
    assert str(DATA_FLOOR) in got.missing, got.missing


def test_one_arm_repeated_is_a_habit_not_a_test():
    rows = arms(DATA_FLOOR, A, 12)
    got = L.verdict(L.ledger(rows), PLAN)
    assert (got.state, got.winner) == ("no test", "")
    assert "habit" in got.headline
    assert any(A in line for line in got.lines)


def test_an_arm_with_two_posts_cannot_lose():
    rows = arms(6, A, 12) + arms(2, B, 3)
    got = L.verdict(L.ledger(rows), PLAN)
    assert got.state == "thin"
    assert B in got.missing
    assert str(L.MIN_PER_ARM - 2) in got.missing, got.missing
    assert any(B in line and "2 posts" in line for line in got.lines)


def test_a_gap_wider_than_the_ratio_calls_the_test_and_names_both_arms():
    rows = arms(5, A, 14) + arms(5, B, 5)
    got = L.verdict(L.ledger(rows), PLAN)
    assert (got.state, got.winner, got.loser) == ("called", A, B)
    assert str(round(14 / 5, 2)) in " ".join(got.lines), got.lines


def test_a_lead_under_the_ratio_keeps_both_arms_in_the_plan():
    rows = arms(5, A, 12) + arms(5, B, 10)
    got = L.verdict(L.ledger(rows), PLAN)
    assert got.state == "flat"
    assert (got.winner, got.loser) == ("", "")
    assert str(AMPLIFY_RATIO) in " ".join(got.lines), "the rule has to be quoted, not hidden"


def test_identical_arms_are_read_as_no_difference():
    rows = arms(5, A, 8) + arms(5, B, 8)
    got = L.verdict(L.ledger(rows), PLAN)
    assert (got.state, got.winner) == ("flat", "")
    assert "8.0" in got.headline or "8.0" in " ".join(got.lines), got


def test_the_lab_and_the_adjustment_engine_use_one_rule_not_two():
    """analyse() may propose an amplify for the best arm; the ledger may call the same test.
    Two thresholds for one question is how a page ends up contradicting itself."""
    rows = arms(5, A, 14) + arms(5, B, 5)
    called = L.verdict(L.ledger(rows), PLAN)
    amplify = [a for a in analyse(rows, PLAN) if a.kind == "amplify"]
    assert called.decided and amplify, (called, amplify)
    assert called.winner == amplify[0].target == A


def test_a_written_decision_carries_the_numbers_it_stands_on():
    rows = arms(5, A, 14) + arms(5, B, 5)
    got = L.verdict(L.ledger(rows), PLAN)
    text = L.decision_text(got)
    assert text.startswith(f"Kept {A}, dropped {B}.")
    assert "per 1000 views" in text
    thin = L.verdict(L.ledger(arms(2, A, 12) + arms(2, B, 3)), PLAN)
    assert L.decision_text(thin).startswith("No verdict (thin)")
