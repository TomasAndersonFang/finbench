"""Mine a repo for as many validated tasks as possible (scale the benchmark).

For one repo it: lists merged PRs, keeps those that touch both a test file and a
source file, skips PRs already in the benchmark (and an optional reject list and,
by default, version-release PRs), then for each candidate runs the soundness gate
and the mutation check. A candidate is written to the benchmark only if it passes
the gate AND is not mutation-flagged (kills >= 1) -- the same quality bar used for
the existing tasks. Stops when the benchmark reaches ``target`` or candidates run
out. Smaller diffs are tried first (more focused tasks).

This automates collect -> validate -> mutation -> write so the benchmark can be
grown to N tasks without hand-running each PR.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .builder import image_tag
from .diffutils import is_test_path
from .github_client import GitHubClient
from .mutation import run_task_mutation_check
from .pipeline import write_task
from .providers import GitHubPRProvider
from .schema import Task
from .validator import validate

# Title patterns for version-release PRs (bundle many changes; poor single-feature
# tasks). Skipped by default.
_RELEASE_RE = re.compile(r"^\s*(v?\d+\.\d+|rel[:\s]|release\b|bump\b)", re.IGNORECASE)

# Keyword -> finance tag inference from the PR title and touched source paths.
_TAG_KEYWORDS = {
    "lookahead": ["lookahead", "look-ahead", "forward return", "horizon", "shift"],
    "annualization": ["annualiz", "annualis", "compound", "per year", "frequency"],
    "calendar": ["calendar", "datetime", "date", "timezone", "resample", "trading day"],
    "cross_sectional": [
        "cross-sectional", "cross sectional", "black-litterman", "black litterman",
        "hrp", "hierarchical", "cluster", "single-index", "single index",
        "constant-correlation", "constant correlation", "market",
    ],
    "corporate_action": ["dividend", "split", "corporate action", "adjust"],
    "survivorship": ["survivorship", "delist"],
    "precision": [
        "covariance", "cov", "shrink", "semivariance", "cvar", "var", "risk model",
        "precision", "tolerance", "numeric", "rounding", "optimiz", "solver", "weights",
    ],
}


@dataclass
class HarvestOutcome:
    number: int
    title: str
    status: str  # "added" | "reject:<reason>"
    f2p: int = 0
    p2p: int = 0
    killed: int = 0
    mutants: int = 0
    tags: tuple[str, ...] = ()


def existing_pr_numbers(benchmark_dir: str | Path, repo_short: str) -> set[int]:
    """PR numbers already in the benchmark for this repo (from <short>-pr-<n> ids)."""
    nums: set[int] = set()
    pat = re.compile(rf"^{re.escape(repo_short)}-pr-(\d+)$")
    for p in Path(benchmark_dir).glob("*/task.json"):
        m = pat.match(p.parent.name)
        if m:
            nums.add(int(m.group(1)))
    return nums


def infer_tags(title: str, src_files: list[str]) -> list[str]:
    """Best-effort finance tags from the title + source paths (default precision)."""
    hay = (title + " " + " ".join(src_files)).lower()
    tags = [tag for tag, kws in _TAG_KEYWORDS.items() if any(k in hay for k in kws)]
    return tags or ["precision"]


def _candidates(client: GitHubClient, repo: str, max_pages: int, skip_releases: bool):
    out = []
    for p in client.list_merged_pulls(repo, max_pages=max_pages):
        title = p.get("title", "")
        if skip_releases and _RELEASE_RE.match(title):
            continue
        files = client.list_pull_files(repo, p["number"])
        if not isinstance(files, list):
            continue
        names = [f["filename"] for f in files]
        tests = [n for n in names if is_test_path(n) and n.endswith(".py")]
        src = [n for n in names if not is_test_path(n) and n.endswith(".py")]
        if tests and src:
            changes = sum(f.get("changes", 0) for f in files)
            out.append((changes, p, src))
    out.sort(key=lambda x: x[0])  # smallest diffs first
    return out


def harvest(
    repo: str,
    target: int,
    benchmark_dir: str | Path = "benchmark",
    max_pages: int = 4,
    skip: set[int] | None = None,
    skip_releases: bool = True,
    mutation_cap: int = 20,
    max_f2p: int = 40,
    write: bool = True,
) -> list[HarvestOutcome]:
    client = GitHubClient()
    image = image_tag(repo)
    provider = GitHubPRProvider(repo, client=client)
    short = repo.split("/")[-1]
    skip = set(skip or set())
    used = existing_pr_numbers(benchmark_dir, short) | skip

    current = len(list(Path(benchmark_dir).glob("*/task.json")))
    print(f"[{repo}] benchmark has {current} tasks; target {target}; image {image}")

    outcomes: list[HarvestOutcome] = []
    for changes, pull, src in _candidates(client, repo, max_pages, skip_releases):
        if current >= target:
            print(f"[{repo}] reached target {target}; stopping")
            break
        num = pull["number"]
        if num in used:
            continue
        title = pull.get("title", "")[:60]
        tags = infer_tags(pull.get("title", ""), src)
        try:
            raw = provider.task_from_pull(pull, finance_tags=tags)
        except Exception as e:  # noqa: BLE001
            outcomes.append(HarvestOutcome(num, title, f"reject:build ({e})"))
            continue

        res = validate(raw, image)
        if not res.ok:
            outcomes.append(HarvestOutcome(num, title, f"reject:gate ({res.reason})"))
            print(f"  #{num} reject gate: {res.reason}  | {title}")
            continue

        # Reject sprawling verifiers: a huge F2P set usually means a base-commit
        # collection cascade (a whole test module errors on import, so every test
        # in it counts as failing) rather than a focused feature. Such tasks pad
        # the verifier with tests unrelated to the gold source. Keep tasks focused.
        if len(res.fail_to_pass) > max_f2p:
            outcomes.append(
                HarvestOutcome(num, title, f"reject:too_broad (F2P={len(res.fail_to_pass)})",
                               len(res.fail_to_pass), len(res.pass_to_pass), tags=tuple(tags))
            )
            print(f"  #{num} reject too_broad: F2P={len(res.fail_to_pass)} > {max_f2p}  | {title}")
            continue

        task_dict = {
            "task_id": raw.task_id, "base_commit": raw.base_commit,
            "gold_patch": raw.gold_patch, "test_patch": raw.test_patch,
            "fail_to_pass": res.fail_to_pass, "image": image,
        }
        mr = run_task_mutation_check(task_dict, image, cap=mutation_cap)
        if mr.flagged:
            outcomes.append(
                HarvestOutcome(num, title, "reject:mutation",
                               len(res.fail_to_pass), len(res.pass_to_pass),
                               mr.mutants_killed, mr.mutants_total, tuple(tags))
            )
            print(f"  #{num} reject mutation ({mr.mutants_killed}/{mr.mutants_total} {mr.error})  | {title}")
            continue

        if write:
            task = Task.from_raw(raw, res.fail_to_pass, res.pass_to_pass, image)
            write_task(benchmark_dir, task)
        current += 1
        outcomes.append(
            HarvestOutcome(num, title, "added",
                           len(res.fail_to_pass), len(res.pass_to_pass),
                           mr.mutants_killed, mr.mutants_total, tuple(tags))
        )
        print(f"  #{num} ADDED  F2P={len(res.fail_to_pass)} P2P={len(res.pass_to_pass)} "
              f"kills={mr.mutants_killed}/{mr.mutants_total} tags={tags}  | {title}  [{current}/{target}]")
    return outcomes


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Harvest validated tasks from a repo.")
    ap.add_argument("--repo", required=True, help="owner/name (canonical)")
    ap.add_argument("--target", type=int, required=True, help="total benchmark size to reach")
    ap.add_argument("--benchmark", default="benchmark")
    ap.add_argument("--max-pages", type=int, default=4, help="pages of merged PRs to scan (100 each)")
    ap.add_argument("--max-f2p", type=int, default=40, help="reject candidates whose F2P set exceeds this (collection-cascade guard)")
    ap.add_argument("--skip", default="", help="comma-separated PR numbers to skip")
    ap.add_argument("--include-releases", action="store_true", help="do not skip version-release PRs")
    ap.add_argument("--dry-run", action="store_true", help="validate but do not write")
    args = ap.parse_args()

    skip = {int(x) for x in args.skip.split(",") if x.strip()}
    outs = harvest(
        args.repo, args.target, args.benchmark, max_pages=args.max_pages,
        skip=skip, skip_releases=not args.include_releases, max_f2p=args.max_f2p,
        write=not args.dry_run,
    )
    added = [o for o in outs if o.status == "added"]
    print(f"\n=== {args.repo}: added {len(added)} task(s) ===")
    for o in added:
        print(f"  #{o.number} F2P={o.f2p} P2P={o.p2p} kills={o.killed}/{o.mutants} {list(o.tags)}  {o.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
