from datetime import date

from src.media.aesthetic import WEIGHTS
from src.metrics import correlate
from src.metrics.ingest import MetricRow

COMPONENTS = list(WEIGHTS)


def row(ref, views=1000, watch=30.0, follows=8):
    return MetricRow("tiktok", ref, date(2026, 11, 1), views, views, watch, follows, 3, 1)


def entry(ref, score, parts=None, band=None):
    return (ref, {"kind": "photo", "score": score,
                  "band": band or ("strong" if score >= 7 else "workable" if score >= 5 else "weak"),
                  "parts": parts if parts is not None else {c: 0.5 for c in COMPONENTS},
                  "judged_at": "2026-11-01"})


def library(n, follows, score=None, parts=None):
    """n paired posts whose follows come from `follows(i)` and whose scores from `score(i)`."""
    return dict(entry(f"p{i}", (score or (lambda i: 4 + i * 0.5))(i),
                      parts(i) if parts else None) for i in range(n))


def posts(n, follows, views=None, watch=None):
    """The same posts with all three outcome columns moving, because a flat column is
    reported as nothing to correlate and a test should not trip over that by accident."""
    return [row(f"p{i}.jpg", views=(views or (lambda i: 500 + i * 50))(i),
                watch=(watch or (lambda i: 20 + i))(i), follows=follows(i)) for i in range(n)]


def test_a_reference_finds_the_score_written_for_that_file():
    pairs = correlate.pair(dict([entry("clip-0042", 6.0)]), [row("CLIP-0042.JPG")])
    assert len(pairs) == 1 and pairs[0].score == 6.0, "the file name is the only shared key"


def test_a_post_named_something_else_is_counted_and_not_guessed():
    rep = correlate.report(dict([entry("look", 6.0)]), [row("other"), row("look")])
    assert not rep.measured
    assert "1 of the 2 imported posts" in rep.note and "not in your folders" in rep.note


def test_no_scores_at_all_is_a_different_answer_from_no_pairs():
    rep = correlate.report({}, [row("a")])
    assert "Nothing scored yet" in rep.note and not rep.measured


def test_rank_correlation_reads_direction_not_size():
    assert correlate.rho([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert correlate.rho([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert correlate.rho([1, 2, 3, 4], [7, 7, 7, 7]) is None, "a column that never moves"


def test_tied_numbers_share_a_rank():
    assert correlate.rank([10, 10, 20]) == [1.5, 1.5, 3.0]


def test_the_chance_test_answers_the_same_way_every_time():
    xs, ys = [1, 2, 3, 4, 5, 6, 7, 8], [8, 7, 6, 5, 4, 3, 2, 1]
    r = correlate.rho(xs, ys)
    assert correlate.chance(xs, ys, r) == correlate.chance(xs, ys, r)
    assert correlate.chance(xs, ys, r) < 0.05, "a perfect reversal is not what noise looks like"
    noise = [3, 1, 8, 2, 7, 4, 5, 6]
    assert correlate.chance(xs, noise, correlate.rho(xs, noise)) > 0.05


def test_the_page_refuses_below_the_floor_and_says_the_number():
    rep = correlate.report(library(6, lambda i: i), posts(6, lambda i: i))
    assert not rep.measured and rep.need == 2
    assert "8 paired posts is the floor this page will speak at" in rep.note


def test_a_real_link_is_reported_on_every_measure():
    rep = correlate.report(library(8, lambda i: i), posts(8, lambda i: i))
    assert rep.measured and len(rep.links) == 3
    assert all(l["rho"] == 1.0 for l in rep.links)
    assert "move together" in rep.links[0]["words"]
    assert "reshuffles" in rep.links[0]["words"]


def test_a_link_the_rubric_did_not_predict_is_said_out_loud():
    scores = dict(entry(f"p{i}", 4 + i * 0.5) for i in range(8))
    rep = correlate.report(scores, [row(f"p{i}.jpg", follows=30 - i * 3) for i in range(8)])
    assert "not buying what the rubric rewards" in rep.inversion
    assert "paid less attention" in rep.inversion
    assert "placement, at 30%" in rep.inversion, "the sentence names where the belief sits"


def test_a_narrow_gap_is_not_promoted_to_an_inversion():
    rep = correlate.report(dict(entry(f"p{i}", 4 + i * 0.5) for i in range(8)),
                           [row(f"p{i}.jpg", follows=[10, 11, 10, 12, 11, 12, 11, 12][i])
                            for i in range(8)])
    assert rep.measured and rep.inversion == ""


def test_posting_a_frame_the_app_called_weak_reads_as_her_override():
    scores = dict(entry(f"p{i}", 4 + i * 0.5, band="weak" if i < 2 else "workable")
                  for i in range(8))
    rep = correlate.report(scores, posts(8, lambda i: i))
    assert "you posted 1 of these" in rep.overrides or "you posted 2 of these" in rep.overrides


def test_a_reweight_waits_for_twelve_posts_not_eight():
    rep = correlate.report(library(8, lambda i: i), posts(8, lambda i: i))
    assert rep.suggestions == []
    assert "A reweight waits for 12 paired posts" in rep.weight_note


def test_a_reweight_moves_only_the_parts_the_data_actually_read():
    def parts(i):
        return {"placement": round(i / 7, 3), "level": round((7 - i) / 7, 3),
                "breathing": 0.5, "palette": 0.5, "focus": 0.5}

    scores = dict(entry(f"p{i}", 4 + i * 0.5, parts(i)) for i in range(14))
    rep = correlate.report(scores, [row(f"p{i}.jpg", follows=i) for i in range(14)])
    vector = correlate.accept_vector(list(rep.pairs))
    assert [s.component for s in rep.suggestions][:2] == ["placement", "level"]
    assert vector["placement"] > WEIGHTS["placement"] > vector["level"], "toward what paid"
    assert vector["breathing"] == WEIGHTS["breathing"], "a flat component keeps its weight"
    assert sum(vector.values()) == 1.0


def test_a_component_that_never_varied_earns_no_proposal():
    rep = correlate.report(library(14, lambda i: i), posts(14, lambda i: i))
    assert rep.suggestions == [] and correlate.accept_vector(list(rep.pairs)) is None
    assert "no component varied" in rep.weight_note


def test_the_measured_note_claims_nothing_about_sequence():
    rep = correlate.report(library(8, lambda i: i), posts(8, lambda i: i))
    assert "carry both halves of the loop" in rep.note
    assert "before you posted" not in rep.note, "this app cannot know when she actually posted"


def test_reading_the_loop_never_writes_a_weight():
    before = dict(WEIGHTS)
    correlate.report(library(14, lambda i: i), posts(14, lambda i: i))
    correlate.reweight([], {"placement": 0.5})
    assert WEIGHTS == before, "the shipped rubric is a constant, not a scratchpad"
