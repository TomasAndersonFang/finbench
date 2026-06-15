"""Discover F2P / P2P in a container and enforce the soundness gate.

The gate is non-negotiable (invariant 1): a task is valid only if at least one
test goes from failing (base + test patch) to passing (base + test patch + gold
patch). We *discover* the transition rather than trust the author: we run the
test target in two phases inside a container started from the repo's base image
and diff the outcomes.

Phases, all inside one container (per-task isolation via checkout, invariant 6):
  1. checkout base_commit, apply test_patch, run tests  -> base outcomes
  2. apply gold_patch, run tests                         -> gold outcomes

F2P = node that passes in phase 2 but did not pass in phase 1 (failing, errored,
or absent; an absent/collection-erroring new test counts as failing per the
project's F2P rule). P2P = node passing in both. The agent never sees either
patch; only this validator does.
"""

from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass, field

from .diffutils import patch_paths
from .schema import RawTask

_BASE_MARK = "===FINBENCH_BASE_JSON==="
_GOLD_MARK = "===FINBENCH_GOLD_JSON==="


@dataclass
class ValidationResult:
    ok: bool
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    reason: str = ""
    logs: str = ""


def _test_target_paths(raw: RawTask) -> list[str]:
    paths = patch_paths(raw.test_patch)
    if not paths:
        raise ValueError(f"task {raw.task_id}: test_patch touches no files")
    return paths


def _build_script(raw: RawTask) -> str:
    test_b64 = base64.b64encode(raw.test_patch.encode()).decode()
    gold_b64 = base64.b64encode(raw.gold_patch.encode()).decode()
    paths = " ".join(_test_target_paths(raw))
    return f"""
set -e
cd /workspace/repo
git checkout -f {raw.base_commit}
git clean -fd
echo {test_b64} | base64 -d > /tmp/test.patch
echo {gold_b64} | base64 -d > /tmp/gold.patch
git apply --whitespace=nowarn /tmp/test.patch
set +e
python -m pytest {paths} -p no:cacheprovider -o addopts="" \
  --json-report --json-report-file=/tmp/base.json > /tmp/base.log 2>&1
git apply --whitespace=nowarn /tmp/gold.patch || echo FINBENCH_GOLD_APPLY_FAIL
python -m pytest {paths} -p no:cacheprovider -o addopts="" \
  --json-report --json-report-file=/tmp/gold.json > /tmp/gold.log 2>&1
echo "{_BASE_MARK}"
cat /tmp/base.json 2>/dev/null
echo "{_GOLD_MARK}"
cat /tmp/gold.json 2>/dev/null
"""


def _outcomes(report_json: str) -> dict[str, str]:
    """Map nodeid -> outcome from a pytest-json-report payload."""
    if not report_json.strip():
        return {}
    try:
        data = json.loads(report_json)
    except json.JSONDecodeError:
        return {}
    out: dict[str, str] = {}
    for test in data.get("tests", []):
        out[test["nodeid"]] = test.get("outcome", "")
    return out


def _split_reports(stdout: str) -> tuple[str, str]:
    if _BASE_MARK not in stdout or _GOLD_MARK not in stdout:
        return "", ""
    _, rest = stdout.split(_BASE_MARK, 1)
    base_part, gold_part = rest.split(_GOLD_MARK, 1)
    return base_part.strip(), gold_part.strip()


def discover_transitions(
    base: dict[str, str], gold: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Split gold-passing nodes into (fail_to_pass, pass_to_pass).

    A node is F2P if it passes under gold but did not pass under base (failing,
    errored, or absent). It is P2P if it passed under both.
    """
    fail_to_pass: list[str] = []
    pass_to_pass: list[str] = []
    for nodeid, outcome in gold.items():
        if outcome != "passed":
            continue
        if base.get(nodeid) == "passed":
            pass_to_pass.append(nodeid)
        else:
            fail_to_pass.append(nodeid)
    return sorted(fail_to_pass), sorted(pass_to_pass)


def validate(raw: RawTask, image: str, timeout: int = 1800) -> ValidationResult:
    """Run the two-phase soundness check for one task in a container."""
    script = _build_script(raw)
    proc = subprocess.run(
        ["docker", "run", "--rm", image, "bash", "-lc", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = proc.stdout
    logs = stdout + "\n--- STDERR ---\n" + proc.stderr

    if "FINBENCH_GOLD_APPLY_FAIL" in stdout:
        return ValidationResult(False, reason="gold_patch failed to apply", logs=logs)

    base_json, gold_json = _split_reports(stdout)
    base = _outcomes(base_json)
    gold = _outcomes(gold_json)

    if not gold:
        return ValidationResult(
            False, reason="no test results in gold phase (collection error?)", logs=logs
        )

    fail_to_pass, pass_to_pass = discover_transitions(base, gold)

    if not fail_to_pass:
        return ValidationResult(
            False,
            pass_to_pass=pass_to_pass,
            reason="soundness gate failed: no fail->pass transition",
            logs=logs,
        )

    return ValidationResult(
        ok=True,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
        reason="ok",
        logs=logs,
    )
