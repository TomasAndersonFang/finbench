#!/usr/bin/env python
"""Verify a mined/authored task by running it in its Docker base image.

It reproduces the two-phase soundness check by hand so you can watch it:

  phase 1  base_commit + test_patch                 -> the F2P tests should FAIL
  phase 2  base_commit + test_patch + gold_patch     -> the F2P tests should PASS

and the P2P tests should pass in both. The script prints the real pytest output
for each phase and a verdict comparing what happened against the F2P / P2P lists
recorded in task.json.

Usage (run through uv so the finbench package is importable):

  uv run python scripts/verify_in_docker.py PyPortfolioOpt-pr-22
  uv run python scripts/verify_in_docker.py benchmark/qlib-pr-1803/task.json
  uv run python scripts/verify_in_docker.py PyPortfolioOpt-pr-22 --shell   # interactive

Requires docker on PATH and the task's base image present locally
(e.g. finbench-pyportfolioopt:base). Exit code 0 means VALID, 1 means not.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Make the repo root importable when run directly (not just via uv).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finbench.diffutils import patch_paths  # noqa: E402

P1 = "===FINBENCH_PHASE1==="
P2 = "===FINBENCH_PHASE2==="
J1 = "===FINBENCH_JSON1==="
J2 = "===FINBENCH_JSON2==="


def resolve_task(arg: str) -> Path:
    p = Path(arg)
    if p.is_file():
        return p
    cand = Path("benchmark") / arg / "task.json"
    if cand.is_file():
        return cand
    sys.exit(f"error: cannot find task.json for {arg!r} (tried {p} and {cand})")


def image_present(image: str) -> bool:
    out = subprocess.run(
        ["docker", "images", "-q", image], capture_output=True, text=True
    ).stdout.strip()
    return bool(out)


def docker_cp_patches(cid: str, test_patch: str, gold_patch: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        tp, gp = Path(d) / "test.patch", Path(d) / "gold.patch"
        tp.write_text(test_patch)
        gp.write_text(gold_patch)
        subprocess.run(["docker", "cp", str(tp), f"{cid}:/tmp/test.patch"], check=True)
        subprocess.run(["docker", "cp", str(gp), f"{cid}:/tmp/gold.patch"], check=True)


def outcomes(payload: str) -> dict[str, str]:
    payload = payload.strip()
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return {t["nodeid"]: t.get("outcome", "") for t in data.get("tests", [])}


def report_mode(d: dict, cid: str, paths: str) -> int:
    base = d["base_commit"]
    # One scripted exec: both phases, then dump both JSON reports with markers.
    script = f"""
set -e
cd /workspace/repo
git checkout -f {base} >/dev/null 2>&1
git clean -fd >/dev/null 2>&1
git apply /tmp/test.patch
set +e
echo "{P1}"
python -m pytest {paths} -p no:cacheprovider -o addopts="" \
  --json-report --json-report-file=/tmp/p1.json -q
git apply /tmp/gold.patch
echo "{P2}"
python -m pytest {paths} -p no:cacheprovider -o addopts="" \
  --json-report --json-report-file=/tmp/p2.json -q
echo "{J1}"; cat /tmp/p1.json 2>/dev/null
echo "{J2}"; cat /tmp/p2.json 2>/dev/null
"""
    proc = subprocess.run(
        ["docker", "exec", "-i", cid, "bash", "-s"],
        input=script,
        capture_output=True,
        text=True,
    )
    out = proc.stdout

    # Human-readable pytest output for each phase.
    def between(a: str, b: str) -> str:
        if a not in out:
            return ""
        seg = out.split(a, 1)[1]
        return seg.split(b, 1)[0] if b in seg else seg

    print("\n========== PHASE 1: base + test_patch (F2P should FAIL) ==========")
    print(between(P1, P2).strip())
    print("\n========== PHASE 2: + gold_patch (F2P should PASS) ==========")
    print(between(P2, J1).strip())

    o1 = outcomes(between(J1, J2))
    o2 = outcomes(out.split(J2, 1)[1] if J2 in out else "")
    if not o1 and not o2:
        print("\n--- raw stderr (no JSON parsed) ---")
        print(proc.stderr[-1500:])
        print("\nVERDICT: ERROR (could not read test results)")
        return 1

    f2p, p2p = d.get("fail_to_pass", []), d.get("pass_to_pass", [])
    print("\n========== VERDICT ==========")
    ok = True

    print("F2P (want: not-passed  ->  passed):")
    for n in f2p:
        before, after = o1.get(n, "absent"), o2.get(n, "absent")
        good = after == "passed" and before != "passed"
        ok &= good
        print(f"  [{'OK ' if good else 'BAD'}] {before:>8}  ->  {after:<8}  {n}")

    if p2p:
        print("P2P (want: passed  ->  passed):")
        bad_p2p = [n for n in p2p if not (o1.get(n) == "passed" == o2.get(n))]
        for n in p2p:
            before, after = o1.get(n, "absent"), o2.get(n, "absent")
            good = before == "passed" == after
            ok &= good
            if not good:
                print(f"  [BAD] {before:>8}  ->  {after:<8}  {n}")
        print(f"  {len(p2p) - len(bad_p2p)}/{len(p2p)} pass->pass"
              + ("" if not bad_p2p else f"  ({len(bad_p2p)} regressed)"))

    print(f"\nVERDICT: {'VALID' if ok else 'INVALID'}  "
          f"(task {d['task_id']}, image {d['image']})")
    return 0 if ok else 1


def shell_mode(d: dict, cid: str, paths: str) -> int:
    base = d["base_commit"]
    setup = f"""
cd /workspace/repo
git checkout -f {base} >/dev/null 2>&1
git clean -fd >/dev/null 2>&1
git apply /tmp/test.patch
echo "Prepared: base_commit checked out, test_patch applied."
"""
    subprocess.run(["docker", "exec", "-i", cid, "bash", "-lc", setup], check=True)
    print("=" * 70)
    print("Interactive shell. You are at /workspace/repo (base + test_patch).")
    print("Run the tests BEFORE the gold patch (expect failures):")
    print(f"  python -m pytest {paths} -o addopts=\"\" -v")
    print("Then apply the gold patch and re-run (expect pass):")
    print("  git apply /tmp/gold.patch")
    print(f"  python -m pytest {paths} -o addopts=\"\" -v")
    print("Type 'exit' to leave; the container is then removed.")
    print("=" * 70)
    return subprocess.run(["docker", "exec", "-it", cid, "bash"]).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a task in its docker base image.")
    ap.add_argument("task", help="task id (folder under benchmark/) or path to task.json")
    ap.add_argument("--shell", action="store_true", help="drop into an interactive shell")
    ap.add_argument("--keep", action="store_true", help="do not remove the container")
    args = ap.parse_args()

    task_path = resolve_task(args.task)
    d = json.loads(task_path.read_text())
    image = d["image"]
    if not image_present(image):
        sys.exit(
            f"error: base image {image!r} not found locally. Build it first, e.g.\n"
            f"  uv run python -c \"from finbench.pipeline import load_registry; "
            f"from finbench.builder import ensure_base_image; "
            f"ensure_base_image(load_registry('finbench/repos.yaml')['{d['repo']}'])\""
        )

    paths = " ".join(patch_paths(d["test_patch"]))
    if not paths:
        sys.exit("error: test_patch touches no files")

    cid = subprocess.run(
        ["docker", "run", "-d", image, "sleep", "infinity"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        docker_cp_patches(cid, d["test_patch"], d["gold_patch"])
        if args.shell:
            return shell_mode(d, cid, paths)
        return report_mode(d, cid, paths)
    finally:
        if args.keep:
            print(f"\n(container kept: {cid}  -- remove with: docker rm -f {cid})")
        else:
            subprocess.run(["docker", "rm", "-f", cid],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    raise SystemExit(main())
