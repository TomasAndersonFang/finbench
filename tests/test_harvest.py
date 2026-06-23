from finbench.harvest import _RELEASE_RE, existing_pr_numbers, infer_tags


def test_release_titles_are_detected():
    for t in ["v1.5.4", "V0.4.4 - Update", "REL: v0.4.3", "release 0.2.0", "bump version"]:
        assert _RELEASE_RE.match(t), t
    for t in ["Add Black-Litterman model", "Fix TSDataSampler slicing", "CVaR optimization"]:
        assert not _RELEASE_RE.match(t), t


def test_infer_tags_keywords():
    assert "cross_sectional" in infer_tags("Add Black-Litterman model", ["pypfopt/black_litterman.py"])
    assert "precision" in infer_tags("CVaR optimization", ["pypfopt/efficient_frontier/efficient_cvar.py"])
    assert infer_tags("Refactor base module", ["pypfopt/base_optimizer.py"]) == ["precision"]  # default
    assert "annualization" in infer_tags("Use appropriate return compounding", ["pypfopt/expected_returns.py"])


def test_existing_pr_numbers_parses_ids(tmp_path):
    for name in ["PyPortfolioOpt-pr-22", "PyPortfolioOpt-pr-174", "qlib-pr-1803", "empyrical-annualized-sharpe"]:
        d = tmp_path / name
        d.mkdir()
        (d / "task.json").write_text("{}")
    nums = existing_pr_numbers(tmp_path, "PyPortfolioOpt")
    assert nums == {22, 174}
    assert existing_pr_numbers(tmp_path, "qlib") == {1803}
