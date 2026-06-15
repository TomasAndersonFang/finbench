from finbench.validator import _outcomes, _split_reports, discover_transitions


def test_discover_fail_to_pass_and_pass_to_pass():
    base = {"t::a": "failed", "t::b": "passed"}
    gold = {"t::a": "passed", "t::b": "passed"}
    f2p, p2p = discover_transitions(base, gold)
    assert f2p == ["t::a"]
    assert p2p == ["t::b"]


def test_absent_in_base_counts_as_transition():
    # New test that errors at collection on base is absent -> treated as failing.
    base = {}
    gold = {"t::a": "passed"}
    f2p, p2p = discover_transitions(base, gold)
    assert f2p == ["t::a"]
    assert p2p == []


def test_errored_gold_node_is_neither():
    base = {"t::a": "failed"}
    gold = {"t::a": "error"}
    f2p, p2p = discover_transitions(base, gold)
    assert f2p == []
    assert p2p == []


def test_outcomes_parses_json_report():
    payload = '{"tests": [{"nodeid": "t::a", "outcome": "passed"}]}'
    assert _outcomes(payload) == {"t::a": "passed"}
    assert _outcomes("") == {}
    assert _outcomes("not json") == {}


def test_split_reports():
    stdout = (
        "noise\n===FINBENCH_BASE_JSON===\n{\"a\": 1}\n"
        "===FINBENCH_GOLD_JSON===\n{\"b\": 2}\n"
    )
    base, gold = _split_reports(stdout)
    assert base == '{"a": 1}'
    assert gold == '{"b": 2}'
