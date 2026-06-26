# finbench: A Finance Coding-Agent Benchmark and an Evaluation of Open Qwen Models

**Date:** 2026-06-26

---

## 1. Introduction

`finbench` is an automated pipeline that synthesizes and validates finance
(equity-quant) coding-agent tasks in the SWE-bench style. Each task asks a coding
agent to implement a real change in a real quantitative-finance Python library,
and is graded by whether the agent's patch makes a held-out test suite pass.

This report documents (1) how the benchmark is built and the soundness filters
every task must pass, (2) the four open Qwen models we evaluated and the agent /
grading framework, and (3) a multi-dimensional comparison of their performance.

The benchmark currently holds **28 validated tasks** mined from 5 libraries:

| Library | Tasks | Domain |
|---------|------:|--------|
| PyPortfolioOpt | 10 | portfolio optimization (mean-variance, HRP, Black-Litterman) |
| skfolio | 8 | portfolio construction on scikit-learn |
| bt | 5 | backtesting framework |
| ffn | 4 | financial functions / performance stats |
| qlib | 1 | AI-oriented quant investment platform |

All are pure-computation, value-sensitive libraries, chosen so that correctness
turns on finance-specific numerics (risk models, annualization, calendars,
cross-sectional logic) rather than on I/O or external services.

---

## 2. The Benchmark

### 2.1 Task anatomy

Each task is a JSON record with these fields:

- `task_id` - e.g. `PyPortfolioOpt-pr-172` (`<repo>-pr-<n>`).
- `base_commit` - the pre-PR commit; the agent works from exactly this tree.
- `instruction` - the natural-language problem statement (the PR title + body /
  linked issue). This is the **only** task text the agent sees.
- `gold_patch` - the human reference source change (held out from the agent).
- `test_patch` - the test files added/changed by the PR (held out from the agent).
- `fail_to_pass` (F2P) - tests that fail on `base + test_patch` and pass once the
  fix is applied. These define "solved".
- `pass_to_pass` (P2P) - tests already green at base that must stay green
  (regression guard).
- `finance_tags`, `change_type`, `source`, `image`.

A task is **solved (RESOLVED)** only if, with the agent's patch applied, **every**
F2P test passes **and every** P2P test passes (no regressions).

### 2.2 How tasks are collected

Mining is automated (`finbench/harvest.py`). For each registered repo:

1. **List merged PRs** (GitHub API), newest pages first.
2. **Keep PRs that touch both a test file and a source file** (`.py` on each side).
   This is the signal that the PR adds a behavioral change *with* a test that pins
   it. Diffs are split by path into `test_patch` (test files) and `gold_patch`
   (source files); the two never overlap by file.
3. **Skip noise**: version-release / "bump" PRs (title regex), PRs already in the
   benchmark, and an explicit reject list.
4. **Sort candidates smallest-diff-first**, so focused, single-feature changes are
   tried before sprawling ones.

Each surviving candidate is then built into a task and put through the filters
below. Mining stops when the benchmark reaches its target size or candidates run
out.

### 2.3 Filter standards (the quality bar)

A candidate becomes a benchmark task **only if it passes all four gates**:

1. **Verifier soundness gate (non-negotiable).** In the task's Docker image we run
   the F2P tests in two phases: `base_commit + test_patch` (must FAIL) and
   `base_commit + test_patch + gold_patch` (must PASS). At least one test must make
   the fail to pass transition. If nothing transitions, the test does not actually
   verify the change and the task is rejected. (`finbench/validator.py`)

2. **Focus gate (`F2P <= 40`).** A very large F2P set almost always means a
   collection cascade (an entire test module errors on import at base, so every
   test in it counts as "failing") rather than one focused feature. Such tasks pad
   the verifier with tests unrelated to the gold change, so they are rejected to
   keep tasks tight.

3. **Mutation sensitivity check.** We confirm the test suite is actually sensitive
   to the gold logic, not just to its presence. We perturb the gold patch one added
   source line at a time with syntax-preserving mutations (numeric +/-1, arithmetic
   / comparison / logical operator swaps, string-literal edits), re-apply, and re-run
   only the F2P tests. A mutant is **killed** if at least one F2P test turns red. A
   task is **flagged and rejected** if no behavior-changing mutant is killed (the
   tests don't catch a corrupted implementation). An identity control (the unmodified
   gold patch) must remain green throughout. (`finbench/mutation.py`)

4. **Determinism.** numpy/pandas are pinned per repo; the base image forces single
   thread for OMP/MKL/OpenBLAS/NumExpr; tight-tolerance financial tests flip across
   environments otherwise.

Two invariants protect benchmark integrity: the agent **never** sees `gold_patch`
or `test_patch`, and at grading time any agent edits to test files are discarded
and the official `test_patch` is re-applied on top (anti-cheat).

### 2.4 Benchmark statistics

- F2P per task: min 1, max 10, **mean 3.0**.
- P2P per task: min 0, max 307, **mean 48.3** (substantial regression surface).
- Finance-tag distribution: precision 21, cross_sectional 4, calendar 2,
  annualization 1, corporate_action 1.
- All tasks are `change_type=feature`, `source=mined`.

---

## 3. Evaluation Framework

### 3.1 Models evaluated

Four open Qwen checkpoints, each served locally with **vLLM** behind an
OpenAI-compatible endpoint (`http://localhost:8001/v1`) and benchmarked through the
identical harness:

| Model | Params | Type |
|-------|--------|------|
| Qwen3.6-27B     | 27B dense | dense |
| Qwen3.6-35B-A3B | 35B total / ~3B active | Mixture-of-Experts |
| Qwen3.5-9B      | 9B dense | dense |
| Qwen3.5-4B      | 4B dense | dense |

The harness is provider-agnostic: switching models is just three env vars
(`FINBENCH_MODEL`, `FINBENCH_BASE_URL`, `FINBENCH_API_KEY`), so the grader is blind
to which model produced a patch.

### 3.2 Agent loop

For each task (`finbench/agents/loop.py`):

1. Start the task's base image and check out `base_commit` (`git checkout -f` +
   `git clean -fdq`).
2. Give the model a **single `bash` tool** whose commands run inside that
   container (`/workspace/repo`), with state persisting between calls. The model
   explores, reads, edits files, and runs code freely.
3. The loop runs until the model stops calling tools ("done") or hits
   **`max_steps = 40`**. Tool output is truncated to 6000 chars per call to bound
   context.
4. The candidate patch is captured as `git add -A && git diff` against
   `base_commit` (new files included). The model is shown **only** the instruction
   and the live repo, never the gold or test patch.

**System prompt (verbatim):**

> You are an autonomous software engineering agent working in a git repository at
> /workspace/repo, checked out at a specific commit. Implement the change described
> by the user. Use the bash tool to explore the code, make edits, and verify your
> work. Make the smallest change that fully satisfies the request. Do not edit test
> files; they are graded separately and your edits to them are discarded. When you
> are confident the change is complete, stop calling tools and reply with a short
> summary.

**User message:** `Task:\n\n{instruction}` (the mined PR/issue description).

**Tool schema:** one function, `bash(command: string)` - "Run a bash command in the
repository at /workspace/repo and get its stdout/stderr."

### 3.3 Grading

The grader (`finbench/evaluator.py`) is fully decoupled from the model. Per task it:

1. Checks out `base_commit`, applies the agent's candidate patch.
2. **Resets the test files to `base_commit`** and applies the held-out `test_patch`
   on top (so any agent tampering with tests is discarded).
3. Runs the F2P + P2P tests under pytest with a JSON report.
4. Marks **RESOLVED** iff all F2P and all P2P pass.

Every model was run once at `--max-steps 40`. All four runs completed with **zero
vLLM connection errors**, so every non-resolution is a genuine model failure.

### 3.4 Failure taxonomy

Non-resolved outcomes fall into four diagnostic buckets, which we use for the
multi-dimensional comparison:

- **empty** - the agent produced no patch (stopped without editing, or hit
  max_steps with no diff). A "gave up / never acted" failure.
- **apply-fail** - the agent produced a diff, but it did not apply cleanly
  (malformed hunk, touched files outside the repo). A tool-use / formatting failure.
- **tests-fail** - the patch applied and ran, but at least one F2P (or P2P) test
  failed. A *reasoning* failure: a real but wrong attempt.
- **collect-err** - tests could not be collected (import error / crash) after the
  patch.

---

## 4. Results

### 4.1 Headline leaderboard

| Rank | Model | Resolved | empty | apply-fail | tests-fail | collect-err |
|-----:|-------|---------:|------:|-----------:|-----------:|------------:|
| 1 | **Qwen3.6-27B**     | **10/28 (35.7%)** | 6  | 2 | 9  | 1 |
| 2 | Qwen3.6-35B-A3B     | 6/28 (21.4%)      | 7  | 5 | 10 | 0 |
| 3 | Qwen3.5-9B          | 4/28 (14.3%)      | 13 | 6 | 4  | 1 |
| 4 | Qwen3.5-4B          | 3/28 (10.7%)      | 12 | 7 | 5  | 1 |

(Each row sums to 28: Resolved + empty + apply-fail + tests-fail + collect-err.)

### 4.2 Multi-dimensional reading

The four buckets separate *capability axes*, not just a single score:

- **Action rate (empty + apply-fail = "failed to even submit a valid diff").**
  4B = 19, 9B = 19, 35B-A3B = 12, 27B = **8**. The smaller models fail primarily by
  *silence*: they explore and give up, or emit an unapplyable patch. Over two-thirds
  of the 4B/9B failures are of this kind.
- **Reasoning rate (tests-fail = "real attempt, wrong logic").** This bucket *rises*
  as models get more capable in relative terms (27B = 9, 35B-A3B = 10) because a
  capable model at least produces an applyable, runnable patch, then misses on the
  finance numerics. tests-fail is the "good failure": evidence the model engaged.
- **Resolved (end-to-end success).** Only the 27B clears more than a fifth of the
  benchmark.

A compact way to see the shift:

| Model | Resolved % | "didn't submit" (empty+apply) | "wrong logic" (tests-fail) |
|-------|-----------:|------------------------------:|---------------------------:|
| Qwen3.6-27B     | 35.7% | 8  (29%) | 9  (32%) |
| Qwen3.6-35B-A3B | 21.4% | 12 (43%) | 10 (36%) |
| Qwen3.5-9B      | 14.3% | 19 (68%) | 4  (14%) |
| Qwen3.5-4B      | 10.7% | 19 (68%) | 5  (18%) |

### 4.3 Per-task resolved matrix

| Task | 27B | 35B-A3B | 9B | 4B |
|------|:---:|:-------:|:--:|:--:|
| PyPortfolioOpt-pr-172 | Y | Y | Y | Y |
| PyPortfolioOpt-pr-174 | Y |   |   |   |
| PyPortfolioOpt-pr-22  | Y |   |   |   |
| PyPortfolioOpt-pr-228 | Y |   | Y | Y |
| PyPortfolioOpt-pr-261 | Y | Y |   |   |
| ffn-pr-285            | Y | Y |   |   |
| qlib-pr-1803          | Y | Y | Y |   |
| skfolio-pr-188        | Y | Y | Y | Y |
| skfolio-pr-212        | Y | Y |   |   |
| skfolio-pr-53         | Y |   |   |   |
| **Total** | **10** | **6** | **4** | **3** |

- **PyPortfolioOpt-pr-172** and **skfolio-pr-188** are solved by all four models -
  the benchmark's "easy floor."
- **Qwen3.6-27B's resolved set is a strict superset of Qwen3.6-35B-A3B's** and adds
  4 tasks (pr-174, pr-22, pr-228, skfolio-pr-53), the current ceiling.

---

## 5. Discussion

- **Dense beats sparse on agentic coding.** The dense 27B outscores the 35B-A3B MoE
  (~3B active params/token) by 14 points. Effective capacity for multi-step,
  tool-using coding tracks *active* parameters, not total parameter count.
- **Capability shows up as "produces a valid attempt," not just final accuracy.**
  As models improve, failures migrate from *empty/apply-fail* (didn't act) to
  *tests-fail* (acted, but wrong). The four-bucket view captures this transition
  that a single resolved-% would hide.
- **Headroom.** Even the best model leaves ~64% of tasks unsolved, and 9 of its
  failures are wrong-logic on finance numerics - exactly the cross-sectional /
  precision / annualization competencies the benchmark is designed to probe.

---

## 6. Reproducibility

```bash
# 1. Serve the model with vLLM (OpenAI-compatible) on :8001, then:
export FINBENCH_BASE_URL="http://localhost:8001/v1"
export FINBENCH_MODEL="<served-model-id>"
export FINBENCH_API_KEY="EMPTY"

# 2. Generate candidate patches (agent loop):
uv run python -m finbench.agents.loop --benchmark benchmark --out preds.json --max-steps 40

# 3. Grade (provider-agnostic):
uv run python -m finbench.evaluator --predictions preds.json --benchmark benchmark
```

Per-model artifacts (predictions + scoreboard + notes) are under
`results/<model-slug>/`; the live leaderboard is `results/LEADERBOARD.md`.
