from pathlib import Path

from finbench.diffutils import make_new_file_patch, patch_paths
from finbench.github_client import GitHubClient
from finbench.providers import AuthoredProvider, GitHubPRProvider, build_instruction

AUTHORED_DIR = Path(__file__).resolve().parents[1] / "finbench" / "authored_tasks"


def test_authored_provider_loads_sharpe_task():
    tasks = list(AuthoredProvider(AUTHORED_DIR).tasks())
    by_id = {t.task_id: t for t in tasks}
    raw = by_id["empyrical-annualized-sharpe"]

    assert raw.repo == "stefan-jansen/empyrical-reloaded"
    # base_commit must be a real pinned SHA, not HEAD.
    assert raw.base_commit != "HEAD"
    assert len(raw.base_commit) == 40

    # Patches build to non-overlapping, expected paths.
    assert patch_paths(raw.gold_patch) == ["src/empyrical/annual_metrics.py"]
    assert patch_paths(raw.test_patch) == ["tests/test_annual_sharpe.py"]

    # Invariant 2: the instruction must not leak the reference value or test code.
    assert "5.784660325547838" not in raw.instruction
    assert "REFERENCE_DAILY_SHARPE" not in raw.instruction


class _FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, diff):
        self._diff = diff

    def get(self, url, headers=None, params=None):
        return _FakeResp(self._diff)


def test_github_pr_provider_splits_diff():
    diff = make_new_file_patch("src/pkg/mod.py", "a = 1\n") + make_new_file_patch(
        "tests/test_mod.py", "def test_a():\n    assert True\n"
    )
    client = GitHubClient(token="x", session=_FakeSession(diff))
    provider = GitHubPRProvider("owner/name", client=client)
    raw = provider.task_from_pr(7, instruction="do it", base_commit="deadbeef")

    assert raw.source == "mined"
    assert raw.task_id == "name-pr-7"
    assert patch_paths(raw.test_patch) == ["tests/test_mod.py"]
    assert patch_paths(raw.gold_patch) == ["src/pkg/mod.py"]


def test_build_instruction_combines_title_and_body():
    assert build_instruction("Add CVaR", "") == "Add CVaR"
    out = build_instruction("Add CVaR", "Implements conditional value at risk.")
    assert out.startswith("Add CVaR")
    assert "conditional value at risk" in out


class _JsonResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _RoutingSession:
    """Return canned JSON keyed by a substring of the requested URL."""

    def __init__(self, routes):
        self._routes = routes

    def get(self, url, headers=None, params=None):
        for key, payload in self._routes.items():
            if key in url:
                return _JsonResp(payload)
        raise AssertionError(f"no route for {url}")


def test_base_commit_uses_merge_commit_first_parent():
    # merge_commit_sha resolves to its first parent (the pre-merge base state).
    session = _RoutingSession(
        {"/commits/mergesha": {"parents": [{"sha": "parent0"}, {"sha": "parent1"}]}}
    )
    client = GitHubClient(token="x", session=session)
    pull = {"merge_commit_sha": "mergesha", "base": {"sha": "basetip"}}
    assert client.base_commit_for_pull("o/n", pull) == "parent0"


def test_base_commit_falls_back_to_base_sha():
    session = _RoutingSession({"/commits/mergesha": {"parents": []}})
    client = GitHubClient(token="x", session=session)
    pull = {"merge_commit_sha": "mergesha", "base": {"sha": "basetip"}}
    assert client.base_commit_for_pull("o/n", pull) == "basetip"
