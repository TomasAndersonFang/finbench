# CLAUDE.md

Persistent instructions for Claude Code on the `finbench` project. Loaded every session. Keep this file short and specific. The full plan lives in `project.md`; usage details live in `README.md`. Read both when context is missing.

## What this project is

`finbench` is an automated pipeline that synthesizes and validates finance (equity-quant) coding-agent tasks, in the SWE-bench style. Near-term goal: 10 validated tasks. The architecture must stay scalable, because the task count will grow later.

## Environment: uv only

This project uses **uv** to manage the Python environment. Do not call `pip` or a bare `python` for the harness. Always go through uv.

* Create / sync the env: `uv sync`
* Add a runtime dependency: `uv add <pkg>`
* Add a dev dependency: `uv add --dev <pkg>`
* Run the pipeline: `uv run python -m finbench.cli --registry finbench/repos.yaml --authored finbench/authored_tasks --out benchmark --count 10 --change-type feature`
* Run tests: `uv run pytest`
* Run one module / script: `uv run python -m <module>`

`pyproject.toml` is the source of truth for dependencies. `requirements.txt` is kept only as a fallback mirror; if you change deps, change `pyproject.toml`.

Note: uv manages the harness env only. The target repos under test are installed with their own native tooling (usually `pip install -e .`) **inside the Docker images** built by `builder.py`. Do not try to make those repos use uv.

## Layout

```
finbench/schema.py        RawTask / Task data model (single source of truth)
finbench/diffutils.py     split a PR diff into test patch + source patch
finbench/github_client.py GitHub REST client (token from $GITHUB_TOKEN)
finbench/providers.py     GitHubPRProvider (mined) + AuthoredProvider (value)
finbench/builder.py       one base Docker image per repo
finbench/validator.py     discover F2P/P2P in a container, enforce soundness
finbench/pipeline.py      collect -> build -> validate -> finalize
finbench/cli.py           CLI entrypoint
finbench/repos.yaml       equity-quant repo registry
finbench/authored_tasks/  authored value-based task YAMLs
tests/                    unit tests
```

## Core invariants (do not violate)

1. **Verifier soundness gate is non-negotiable.** A task is valid only if at least one test goes from failing (base + test patch) to passing (base + test patch + gold patch). If nothing transitions, reject the task. Never weaken, bypass, or stub out this check in `validator.py`.
2. **The agent never sees the gold patch or the test patch contents.** It gets only the instruction and the pre-PR repo state. Do not leak either into the instruction.
3. **`test_patch` and `gold_patch` must not overlap by file.** The split in `diffutils.py` is by path. Keep it that way.
4. **Prefer value-based verifiers for authored finance tasks.** Check a reference numeric value within tolerance, not a specific API shape. This is why authored tasks exist: to probe finance-specific correctness without penalizing valid alternative implementations.
5. **Determinism.** Pin numpy and pandas in `repos.yaml`. The base image sets OMP/MKL/OPENBLAS/NUMEXPR thread counts to 1. Seed every RNG in authored tests. Tight-tolerance financial tests flip across environments otherwise.
6. **Two-layer Docker.** One base image per repo (deps installed once); per-task isolation comes from checking out `base_commit` at runtime. Never build a separate image per task.
7. **Tag finance difficulty.** Set `finance_tags` on authored tasks (lookahead, survivorship, corporate\_action, calendar, cross\_sectional, annualization, precision). These drive the failure-mode analysis later.

## Conventions

* No em-dashes anywhere in prose, comments, or docs. Keep writing concise.
* Code, comments, and docs in English.
* When you add a module, add a unit test for it under `tests/`.
* F2P detection treats a test that is absent in the base phase as failing, because a new test that errors at collection on the base commit is the expected signal. Do not "fix" this to require presence in base.

## Gotchas

* Mining needs `GITHUB_TOKEN` exported (higher rate limit, your own token).
* `builder.py` and `validator.py` need `docker` on PATH.
* `repos.yaml` owners and install steps are starting points. Verify the owner, default branch, and build deps against the live repo before a large run.
* Start the first 10 tasks on the pure-computation repos (empyrical-reloaded, alphalens-reloaded, PyPortfolioOpt). The engine repos (zipline-reloaded, qlib) need a frozen data bundle in the image before their data-dependent tests run.
