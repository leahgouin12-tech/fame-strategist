from src.metrics import spend as spendmod


def tally(**over):
    args = dict(spend={"model_calls": 0, "credits": None, "credits_note": ""}, ops=[],
                judged=0, posts=0, engine_name="offline", offline=True)
    args.update(over)
    return spendmod.tally(**args)


def quota(result):
    return next(c for c in result.currencies if c.name == "model quota")


def credits(result):
    return next(c for c in result.currencies if c.name == "agent credits")


def test_an_offline_app_reports_zero_and_says_why():
    r = tally(posts=4)
    assert quota(r).total == "0 calls" and "has not been possible" in quota(r).basis
    assert credits(r).total == "not stated"
    assert "invented zero" in credits(r).basis, "an empty cell is not a receipt"


def test_a_key_with_no_calls_yet_is_zero_without_an_excuse():
    basis = quota(tally(posts=2, engine_name="gemini", offline=False)).basis
    assert basis.startswith("Zero calls recorded with the engine at gemini")


def test_nothing_divides_before_there_are_posts():
    r = tally()
    assert not r.measured
    assert quota(r).per_post == "no posts to divide"
    assert "nothing divides" in r.note


def test_a_counted_call_is_per_post_arithmetic_anybody_can_check():
    r = tally(spend={"model_calls": 3, "credits": None}, posts=6,
              engine_name="gemini", offline=False)
    assert quota(r).total == "3 calls" and quota(r).per_post == "0.5 calls"
    assert "engine is gemini" in quota(r).basis


def test_one_call_is_one_call_not_one_calls():
    assert tally(spend={"model_calls": 1}, posts=1).currencies[0].total == "1 call"


def test_stated_credits_stay_marked_as_her_statement():
    r = tally(spend={"model_calls": 0, "credits": 12,
                     "credits_note": "three cut edits through the agent"}, posts=6)
    assert credits(r).total == "12 credits" and credits(r).per_post == "2 credits"
    assert "Self-reported by you" in credits(r).basis
    assert "three cut edits through the agent" in credits(r).basis
    assert "receipt from this machine" in r.note and "what you told it" in r.note


def test_a_fractional_statement_survives_the_round_trip():
    assert tally(spend={"credits": 0.5}, posts=1).currencies[1].total == "0.5 credits"


def test_local_work_is_listed_and_refused_the_status_of_a_currency():
    ops = [{"file": "a.jpg", "op": "crop"}, {"file": "a.jpg", "op": "rotate"},
           {"file": "b.jpg", "op": "exposure"}]
    r = tally(ops=ops, judged=5, posts=2)
    assert r.local.startswith("3 edit operations logged across 2 saved files, 5 scores")
    assert "not a currency" in r.local


def test_a_counted_zero_and_an_empty_cell_are_told_apart():
    note = tally(posts=3).note
    assert "counted zero" in note and "the credits column is empty" in note
    assert "3 imported posts" in note
