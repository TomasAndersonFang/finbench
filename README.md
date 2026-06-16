# finbench

Automated pipeline that synthesizes and validates finance (equity-quant)
coding-agent tasks, SWE-bench style. See `CLAUDE.md` for the always-on rules and
`PORJECT.md` for the full plan.

## Setup

This project uses [uv](https://docs.astral.sh/uv/). Do not call bare `pip` or
`python` for the harness.

```bash
uv sync          # create / sync the environment
uv run pytest    # run the unit tests
```

## Run the pipeline

Building base images and validating tasks needs `docker` on PATH.

```bash
uv run python -m finbench.cli \
  --registry finbench/repos.yaml \
  --authored finbench/authored_tasks \
  --out benchmark \
  --count 1
```

Each validated task is written to `benchmark/<task_id>/task.json`. A task is
written only if it passes the soundness gate: at least one test fails on
`base_commit + test_patch` and passes once the gold patch is applied.

## Verify a task by hand

To watch a task's two-phase check run in its Docker base image (the code before
and after the gold patch), use the helper script. It checks out `base_commit`,
applies `test_patch`, runs the tests (the F2P tests should fail), then applies
`gold_patch` and runs again (they should pass), and prints a verdict against the
recorded F2P / P2P lists.

```bash
# report mode: run both phases and print a VALID / INVALID verdict
uv run python scripts/verify_in_docker.py PyPortfolioOpt-pr-22

# interactive: drop into the prepared container (base + test_patch applied)
uv run python scripts/verify_in_docker.py qlib-pr-1803 --shell
```

Needs docker on PATH and the task's base image present locally. Exit code 0 means
VALID. Pass a path to a `task.json` instead of an id if you prefer.

## Anatomy of a task

Every `benchmark/<task_id>/task.json` is the serialized `Task` from
`schema.py`. Below is each field, grouped by role, using
`benchmark/PyPortfolioOpt-pr-22/task.json` (mined from PR #22, which adds two
covariance risk models) as the running example.

### Identity and environment

* `task_id` (`"PyPortfolioOpt-pr-22"`): unique name and folder. Mined tasks use
  `<repo-short-name>-pr-<number>`, so it points back to the source PR.
* `repo` (`"PyPortfolio/PyPortfolioOpt"`): the GitHub `owner/name`. The base
  image is a clone of this repo.
* `base_commit` (`"58007196..."`): the repo state the task starts from, i.e. the
  commit just before the PR merged (first parent of the merge commit). The
  validator runs `git checkout -f <base_commit>`, so every run starts from the
  same pinned snapshot. This is the per-task isolation (one image per repo, no
  per-task images).
* `image` (`"finbench-pyportfolioopt:base"`): the base image used to validate.

### What the agent sees

* `instruction`: the task prompt. For mined tasks this is the PR title plus body,
  natural language only. It is built without the patches, so it never leaks the
  solution or the tests. At evaluation the agent gets exactly `repo` at
  `base_commit` plus `instruction`, and nothing else from this file.

### Grading material (never shown to the agent)

* `gold_patch`: the reference solution, a unified diff that touches only source
  files (here, the two new classes in `pypfopt/risk_models.py`).
* `test_patch`: the tests that grade the task, a diff that touches only test
  files (here, two new tests in `tests/test_risk_models.py`).
* `gold_patch` and `test_patch` never touch the same file: the split is by path,
  so they apply independently.

The soundness gate uses both: checkout `base_commit`, apply `test_patch`, run
tests (the new tests fail); then apply `gold_patch`, run again (they pass). The
fail-to-pass transition is what proves the tests measure the feature. No
transition means the task is rejected and never written.

### The verifier verdict (discovered, not trusted)

* `fail_to_pass` (F2P): tests that failed at base but pass once the gold patch is
  applied. These are the success criterion a candidate solution must satisfy
  (here, `test_constant_correlation` and `test_single_index`).
* `pass_to_pass` (P2P): tests that passed both before and after the gold patch.
  These are the regression guard: a solution must add the new behavior without
  breaking existing tests (here, the 15 other covariance tests).

Both lists are discovered by the validator by diffing the two test runs, not
copied from the PR.

### Metadata for analysis

* `change_type`: `"feature"` or `"bugfix"`.
* `source`: `"mined"` (from a real PR) or `"authored"` (hand-written).
* `finance_tags`: finance-specific failure modes from a fixed vocabulary
  (lookahead, survivorship, corporate_action, calendar, cross_sectional,
  annualization, precision). PR-22 is `["precision", "cross_sectional"]`.

### Evaluation flow (future)

An agent receives `repo` at `base_commit` plus `instruction`. Its patch is
applied, then `test_patch` is applied, and it is scored on whether all F2P and
all P2P tests pass. `gold_patch` is only the reference and is never shown.

## Layout

```
finbench/schema.py        RawTask / Task data model
finbench/diffutils.py     build new-file diffs; split a PR diff by path
finbench/github_client.py GitHub REST client (token from $GITHUB_TOKEN)
finbench/providers.py     AuthoredProvider + GitHubPRProvider
finbench/builder.py       one base image per repo, built lazily
finbench/validator.py     discover F2P/P2P in a container, enforce soundness
finbench/mutation.py      mutation check: perturb gold, confirm tests turn red
finbench/pipeline.py      collect -> build -> validate -> finalize
finbench/cli.py           CLI entrypoint
finbench/repos.yaml       equity-quant repo registry
finbench/authored_tasks/  authored value-based task YAMLs
scripts/verify_in_docker.py  run a task's before/after check by hand
tests/                    unit tests
```
