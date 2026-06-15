# finbench project plan

The full specification and roadmap. `CLAUDE.md` holds the short always-on rules; this file holds the reasoning and the staged plan.

## Goal and deliverables

Build a benchmark of 10 executable, verifiable coding-agent tasks for equity quant code, then run a small evaluation of common models on them.

Deliverables:

* A `benchmark/` directory with 10 tasks. Each task has a clear instruction, the starting code (a pinned `base_commit`), and a verifier (tests). The environment is reproducible via a per-repo Docker image.
* An evaluation of several common models, recording resolve rate, number of turns, test-pass fraction, and representative failure modes.
* An analysis of how equity-quant code development differs from general coding tasks.
* A report covering task construction, evaluation results, and extensions.

## Scope decision

Subdomain: equity quant. Chosen because its characteristic pitfalls (look-ahead bias, survivorship bias, corporate-action adjustment, trading calendars) are exactly what general coding benchmarks cannot probe, and many of them admit clean value-based verifiers.

Repos (see `finbench/repos.yaml`):

* Pure-computation, value-based-verifier friendly (primary): empyrical-reloaded, alphalens-reloaded, PyPortfolioOpt.
* Engine-level, richer but heavier (secondary): zipline-reloaded, qlib.

## Task design strategy

Lean toward feature tasks for comprehensive capability coverage, but protect grading validity, which matters more at n=10. The real axis is not bug-fix vs feature; it is whether the success criterion is unambiguous and the verifier is sound.

Two task sources, one schema:

* Mined (GitHubPRProvider): merged PRs that close an issue and touch tests. High ecological validity.
* Authored (AuthoredProvider): hand-written value-based tasks that probe finance-specific difficulty. Use these where a clean PR rarely exists.

Target mix for the first 10:

* 6 to 7 feature tasks, most on the pure-computation repos with value-based verifiers.
* 3 to 4 bug-fix tasks, including one or two finance-specific silent-correctness bugs (look-ahead or rounding) that run fine but compute the wrong thing.

### Finance-specific difficulty categories

These are both task seeds and the failure-mode taxonomy for the report.

* look-ahead / point-in-time leakage (forward returns, restated fundamentals, trading at the wrong bar).
* survivorship bias (delisted names, point-in-time universe).
* corporate actions (split / dividend adjustment, adjusted vs raw price).
* trading calendars (holidays, half-days, business-day shifting).
* cross-sectional vs time-series axis (factor ranking, neutralization, IC).
* annualization conventions (252-day, sqrt-time scaling).
* precision (rounding, decimal vs float).

## Milestones

* M1 Harness and environment. uv project set up, one repo green end to end: build base image, validate one authored task, write it to `benchmark/`.
* M2 Authored value tasks. Cover annualization, look-ahead, corporate action, cross-sectional. Each with a seeded, value-based verifier.
* M3 Mine feature PRs across the pure-computation repos to fill to 10.
* M4 Soundness audit. Confirm every task passes the soundness gate, and spot-check that the verifier actually catches a perturbed gold solution (mutation check) so no task is passable with wrong logic.
* M5 Evaluation harness. Fix one agent scaffold, run several models, collect metrics, and classify failures.
* M6 Report.

## Evaluation plan

* Models: one frontier, one mid-tier, one open code model. Fix the scaffold so models are comparable.
* Metrics: resolve rate (pass@1), turns / tool calls, token cost, test-pass fraction (partial credit), and the multi-run agreement rate. At n=10 statistical power is low, so run multiple seeds per task and report variance; the agreement rate doubles as a robustness signal.
* Failure modes: misused financial convention, introduced look-ahead, precision or rounding error, passed a weak test with wrong logic, could not navigate the repo, broke pass-to-pass.

## Report outline

1. Motivation and why equity quant.
2. Task construction: sources, the schema, the soundness gate, value-based verifiers, reproducibility and determinism.
3. The 10 tasks: a table with repo, change type, finance tags, F2P/P2P counts.
4. Evaluation: setup, metrics, results, variance across seeds.
5. Failure-mode analysis tied to the finance-specific categories.
6. How equity-quant tasks differ from general coding tasks.
7. Extensions and scaling.

## Scaling roadmap

* Add repos to `repos.yaml`; build and validate are unchanged.
* Auto-tag mined tasks with a classifier over the diff and issue text.
* Parallelize validation with a process pool over independent containers.
* Freeze small data bundles into engine-repo images for data-dependent tests.
* Optionally add property-based tests (hypothesis) or differential testing against a reference implementation to strengthen verifiers.
