"""Grade agent predictions against the benchmark (provider-agnostic).

An agent produces a candidate patch per task (its attempt at the instruction).
This module applies that patch in the task's base image, then applies the
held-out ``test_patch``, runs the F2P + P2P tests, and reports whether the task
is RESOLVED. It is the scoring half of the harness and knows nothing about which
model produced the patch, so it grades Claude, GPT, Gemini, open/local models,
or a human identically.

Resolved = every F2P test passes AND every P2P test passes with the agent's
patch applied. The agent does not have to match the gold patch; it only has to
satisfy the tests. The agent never sees gold_patch or test_patch (invariant 2);
this grader is the only thing that applies them.

Anti-cheat: the candidate patch is applied first, then the official test files
are reset to ``base_commit`` and ``test_patch`` is applied on top, so any edits
the agent made to test files are discarded. The graded tests are always the
benchmark's own.
"""

from __future__ import annotations

import base64
import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .diffutils import patch_paths

_MARK = "===FINBENCH_EVAL_JSON==="
_APPLYFAIL = "===FINBENCH_CAND_APPLYFAIL==="


@dataclass
class EvalResult:
    task_id: str
    resolved: bool = False
    reason: str = ""
    f2p_passed: int = 0
    f2p_total: int = 0
    p2p_passed: int = 0
    p2p_total: int = 0
    logs: str = ""


def load_predictions(path: str | Path) -> dict[str, str]:
    """Load a predictions file into ``{task_id: patch}``.

    Accepts either a JSON object ``{task_id: patch}`` or a JSON list of objects
    with a task-id key (``task_id`` / ``instance_id``) and a patch key
    (``patch`` / ``model_patch`` / ``prediction``). The list form matches the
    SWE-bench predictions convention.
    """
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        return {str(k): (v or "") for k, v in data.items()}
    preds: dict[str, str] = {}
    for item in data:
        tid = item.get("task_id") or item.get("instance_id")
        patch = item.get("patch") or item.get("model_patch") or item.get("prediction") or ""
        if tid:
            preds[str(tid)] = patch
    return preds


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _build_script(base_commit: str, candidate: str, test_patch: str, test_paths: list[str]) -> str:
    paths = " ".join(shlex.quote(p) for p in test_paths)
    revert = " ".join(shlex.quote(p) for p in test_paths)
    return f"""
set -e
cd /workspace/repo
git checkout -f {base_commit} >/dev/null 2>&1
git clean -fdq
echo {_b64(candidate)} | base64 -d > /tmp/cand.patch
if [ -s /tmp/cand.patch ] && ! git apply --whitespace=nowarn /tmp/cand.patch 2>/tmp/cand.err; then
  echo "{_APPLYFAIL}"
  cat /tmp/cand.err
  exit 0
fi
# Discard any agent edits to the official test files, then apply the held-out tests.
git checkout -f {base_commit} -- {revert} 2>/dev/null || true
echo {_b64(test_patch)} | base64 -d > /tmp/test.patch
git apply --whitespace=nowarn /tmp/test.patch
set +e
python -m pytest {paths} -p no:cacheprovider -o addopts="" \
  --json-report --json-report-file=/tmp/r.json >/tmp/r.log 2>&1
echo "{_MARK}"
cat /tmp/r.json 2>/dev/null
"""


def _outcomes(payload: str) -> dict[str, str]:
    payload = payload.strip()
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return {t["nodeid"]: t.get("outcome", "") for t in data.get("tests", [])}


def _resolved(outcomes: dict[str, str], f2p: list[str], p2p: list[str]) -> bool:
    if not outcomes:
        return False
    if not all(outcomes.get(n) == "passed" for n in f2p):
        return False
    if not all(outcomes.get(n) == "passed" for n in p2p):
        return False
    return True


def evaluate_task(task: dict, candidate_patch: str, timeout: int = 1800) -> EvalResult:
    """Grade one task given the agent's candidate patch."""
    rep = EvalResult(task_id=task["task_id"])
    f2p, p2p = task["fail_to_pass"], task["pass_to_pass"]
    rep.f2p_total, rep.p2p_total = len(f2p), len(p2p)

    if not (candidate_patch or "").strip():
        rep.reason = "empty prediction"
        return rep

    test_paths = patch_paths(task["test_patch"])
    if not test_paths:
        rep.reason = "task test_patch touches no files"
        return rep

    script = _build_script(task["base_commit"], candidate_patch, task["test_patch"], test_paths)
    proc = subprocess.run(
        ["docker", "run", "--rm", "-i", task["image"], "bash", "-s"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = proc.stdout
    rep.logs = out + "\n--- STDERR ---\n" + proc.stderr

    if _APPLYFAIL in out:
        rep.reason = "candidate patch failed to apply"
        return rep

    payload = out.split(_MARK, 1)[1] if _MARK in out else ""
    outcomes = _outcomes(payload)
    if not outcomes:
        rep.reason = "no test results (collection error or crash)"
        return rep

    rep.f2p_passed = sum(1 for n in f2p if outcomes.get(n) == "passed")
    rep.p2p_passed = sum(1 for n in p2p if outcomes.get(n) == "passed")
    rep.resolved = _resolved(outcomes, f2p, p2p)
    rep.reason = "ok" if rep.resolved else "tests not all passing"
    return rep


def evaluate(
    predictions: dict[str, str],
    benchmark_dir: str | Path = "benchmark",
    only: Optional[str] = None,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for p in sorted(Path(benchmark_dir).glob("*/task.json")):
        task = json.loads(p.read_text())
        tid = task["task_id"]
        if only and tid != only:
            continue
        candidate = predictions.get(tid, "")
        results.append(evaluate_task(task, candidate))
    return results


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Grade agent predictions (provider-agnostic).")
    ap.add_argument("--predictions", required=True, help="predictions JSON (task_id -> patch)")
    ap.add_argument("--benchmark", default="benchmark")
    ap.add_argument("--task", default=None, help="only grade this task_id")
    args = ap.parse_args()

    preds = load_predictions(args.predictions)
    results = evaluate(preds, args.benchmark, only=args.task)

    print(f"\n{'task_id':40s} resolved  F2P    P2P    reason")
    print("-" * 78)
    for r in results:
        mark = "RESOLVED" if r.resolved else "  --    "
        print(
            f"{r.task_id:40s} {mark} {r.f2p_passed}/{r.f2p_total:<4} "
            f"{r.p2p_passed}/{r.p2p_total:<4} {r.reason}"
        )
    n = len(results)
    solved = sum(1 for r in results if r.resolved)
    pct = (100.0 * solved / n) if n else 0.0
    print(f"\nresolved {solved}/{n}  ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
