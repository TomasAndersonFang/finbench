import json

from finbench.evaluator import _outcomes, _resolved, load_predictions


def test_load_predictions_dict(tmp_path):
    p = tmp_path / "preds.json"
    p.write_text(json.dumps({"task-a": "PATCH_A", "task-b": "PATCH_B"}))
    preds = load_predictions(p)
    assert preds == {"task-a": "PATCH_A", "task-b": "PATCH_B"}


def test_load_predictions_swebench_list(tmp_path):
    p = tmp_path / "preds.json"
    p.write_text(
        json.dumps(
            [
                {"instance_id": "task-a", "model_patch": "PATCH_A"},
                {"task_id": "task-b", "patch": "PATCH_B"},
            ]
        )
    )
    preds = load_predictions(p)
    assert preds == {"task-a": "PATCH_A", "task-b": "PATCH_B"}


def test_resolved_requires_all_f2p_and_p2p():
    f2p = ["t::a", "t::b"]
    p2p = ["t::c"]
    all_pass = {"t::a": "passed", "t::b": "passed", "t::c": "passed"}
    assert _resolved(all_pass, f2p, p2p)

    # one F2P failing -> not resolved
    f2p_fail = {"t::a": "passed", "t::b": "failed", "t::c": "passed"}
    assert not _resolved(f2p_fail, f2p, p2p)

    # a P2P regression -> not resolved (no free regressions)
    p2p_fail = {"t::a": "passed", "t::b": "passed", "t::c": "failed"}
    assert not _resolved(p2p_fail, f2p, p2p)

    # empty outcomes (collection error) -> not resolved
    assert not _resolved({}, f2p, p2p)


def test_outcomes_parses_json_report():
    payload = json.dumps(
        {"tests": [{"nodeid": "t::a", "outcome": "passed"}, {"nodeid": "t::b", "outcome": "failed"}]}
    )
    assert _outcomes(payload) == {"t::a": "passed", "t::b": "failed"}
    assert _outcomes("") == {}
    assert _outcomes("not json") == {}
