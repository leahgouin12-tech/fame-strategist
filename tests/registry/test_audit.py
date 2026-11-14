"""The audit is a claim about this repository, so it is tested against this repository.

Nothing here is mocked: the entries come from parsing the real files, and the assertions
name things that are really in them. If somebody deletes a route the audit notices, which
is the whole point of generating it instead of typing it.
"""

from src.registry import audit as a


def test_every_kind_of_real_thing_is_registered():
    entries = a.audit()
    kinds = {e.kind for e in entries}
    assert {"route", "action", "control", "module"} <= kinds
    assert len(entries) > 100, f"the tree has more than this: {len(entries)}"


def test_routes_are_read_off_the_file_not_a_list_somebody_kept():
    got = {e.key for e in a.routes()}
    assert "route:GET /bench" in got
    assert "route:POST /bench/paste" in got
    assert "route:GET /registry" in got


def test_a_route_records_the_fields_it_reads_and_the_page_it_renders():
    row = [e for e in a.routes() if e.key == "route:POST /bench/paste"][0]
    assert any("lines" in i for i in row.inputs)
    assert row.where.startswith("src/app.py:")


def test_a_route_that_hands_off_to_a_view_helper_still_reports_its_page():
    """bench_page() is one line that calls bench_view(), which is where page(...) actually
    is. Reading only the handler would say the page renders nothing."""
    row = [e for e in a.routes() if e.key == "route:GET /bench"][0]
    assert "renders bench.html" in row.outputs


def test_a_route_that_hands_back_a_picture_says_so_instead_of_claiming_no_page():
    """The two preview endpoints return JPEG bytes for an <img> tag. 'no page' is true of
    the html and misses the point of the endpoint."""
    rows = {e.key: e.outputs for e in a.routes()}
    assert rows["route:GET /edit/preview"] == ["serves image/jpeg"]
    assert rows["route:GET /clip/preview"] == ["serves image/jpeg"]
    assert not [k for k, v in rows.items() if v == ["no page"]], "every endpoint does something"


def test_the_edit_controls_are_registered_with_their_fields():
    controls = [e for e in a.controls()]
    smooth = [e for e in controls if e.key == "control:smooth"][0]
    assert smooth.dept == "Editing"
    assert any("brush" in i for i in smooth.inputs)


def test_agent_actions_come_from_the_tools_own_registry():
    from src.agent.tools import catalogue

    keys = {e.key for e in a.actions()}
    assert keys == {f"action:{t['id']}" for t in catalogue()}


def test_modules_are_registered_by_path_with_their_header():
    mods = {e.key: e for e in a.modules()}
    assert "module:src/metrics/bench.py" in mods
    assert "benchmark" in mods["module:src/metrics/bench.py"].describe.lower()


def test_provenance_names_a_real_test_file_and_its_absence_is_said_out_loud():
    entries = a.audit()
    bench = [e for e in entries if e.key == "route:GET /bench"][0]
    assert "tests/app/test_bench_page.py" in bench.acceptance
    assert bench.status == "live"
    # An unproven entry is the one with no test file to name, and it must not borrow proof.
    naked = a.Entry(key="route:GET /never-named", name="never_named()", kind="route",
                    dept="Interface", describe="Nothing tests this.", purpose="A made-up hole.")
    assert a.prove(naked, a.test_bodies()) == []
    for e in entries:
        assert bool(e.acceptance) == (e.status != "unproven"), e.key


def test_departments_come_from_the_words_in_a_thing_not_a_hardcoded_table():
    assert a.department("/bench", "views") == "Analytics"
    assert a.department("/trends") == "Research"
    assert a.department("/weekly", "coach") == "Analytics"
    assert a.department("Editing", "skin", "smooth") == "Editing"
    assert a.department("/nothing-matches-this") == "Interface"


def test_the_backlog_is_derived_from_gaps_the_audit_can_see():
    """The gap list is a reading of the tree, not a stored list: it holds exactly what the
    audit can see right now, so closing the last hole empties it instead of leaving a stub."""
    entries = a.audit()
    ups = a.upgrades(entries)
    unproven = [e for e in entries if e.status == "unproven"
                and e.kind in ("route", "control", "action")]
    assert {u.key for u in ups if u.key.startswith("upgrade:prove-")} == {
        f"upgrade:prove-{a.slug(e.key)}" for e in unproven}
    assert len(ups) >= len(unproven)
    hole = a.Entry(key="route:GET /has-no-test", name="untested()", kind="route",
                   dept="Interface", describe="A made-up hole, to see it noticed.",
                   purpose="Nothing real depends on it.")
    hole.status, hole.reach = "unproven", "linked from a page"
    keys = {u.key for u in a.upgrades(entries + [hole])}
    assert f"upgrade:prove-{a.slug(hole.key)}" in keys
    for u in ups:
        assert u.status == "open"
        assert u.acceptance, f"{u.key} says how it closes"


def test_a_form_endpoint_is_reached_even_though_the_rail_never_shows_it():
    """The rail lists pages, not the posts that write to them. Counting only the rail would
    put every form on the gap list, so a POST that a page posts to must read as reachable."""
    by_key = {e.key: e for e in a.audit()}
    posted = [k for k in by_key if k.startswith("route:POST ")]
    assert posted, "the app has form endpoints to check"
    assert any(by_key[k].reach == "linked from a page" for k in posted), posted
    rail = {k: e for k, e in by_key.items() if e.reach == "in the rail"}
    assert "route:GET /bench" in rail


def test_only_an_endpoint_no_page_points_at_becomes_a_reach_gap():
    entries = a.audit()
    by_key = {e.key: e for e in entries}
    # The editor redraws its preview from script, not from an href. An audit that only reads
    # links in markup would call that endpoint orphaned and invent a gap about it.
    for k in ("route:GET /edit/preview", "route:GET /clip/preview"):
        assert by_key[k].reach == "linked from a page", k
    hidden = [e for e in entries if e.kind == "route" and e.reach == "nothing links to it"]
    ups = {u.key for u in a.upgrades(entries)}
    for e in hidden:
        assert f"upgrade:reach-{a.slug(e.key)}" in ups
    for e in entries:
        if e.kind == "route" and e.reach != "nothing links to it":
            assert f"upgrade:reach-{a.slug(e.key)}" not in ups, e.key
    orphan = a.Entry(key="route:GET /nowhere-at-all", name="nowhere()", kind="route",
                     dept="Interface", describe="Nothing links here.",
                     purpose="A made-up gap, not a real endpoint.")
    orphan.reach = "nothing links to it"
    assert "upgrade:reach-route-get-nowhere-at-all" in {u.key for u in a.upgrades([orphan])}


def test_the_coverage_figure_rounds_down_because_100_is_a_claim():
    """211 of 212 rounds to 100, and the page then says every feature has a test naming it
    while one of them does not. The number she reads has to be the number it can prove."""
    entries = [a.Entry(key=f"route:GET /p{i}", name=f"p{i}()", kind="route",
                       dept="Interface", describe="x", purpose="y") for i in range(212)]
    for e in entries:
        e.status = "proven"
    entries[-1].status = "unproven"
    assert a.summary(entries, [])["percent"] == 99


def test_the_summary_counts_what_it_was_given_and_adds_nothing():
    entries = a.audit()
    ups = a.upgrades(entries)
    got = a.summary(entries, ups)
    assert got["features"] == len(entries)
    assert got["upgrades"] == len(ups)
    assert got["proven"] + got["unproven"] == len(entries)
    assert sum(got["kinds"].values()) == len(entries)


def test_slugs_survive_paths_and_colons():
    assert a.slug("route:GET /bench/paste") == "route-get-bench-paste"
    assert a.slug("") == "root"


def test_keys_are_unique_across_the_whole_registry():
    entries = a.audit() + a.upgrades(a.audit())
    keys = [e.key for e in entries]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]
