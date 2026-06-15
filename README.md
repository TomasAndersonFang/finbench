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

## Layout

```
finbench/schema.py        RawTask / Task data model
finbench/diffutils.py     build new-file diffs; split a PR diff by path
finbench/github_client.py GitHub REST client (token from $GITHUB_TOKEN)
finbench/providers.py     AuthoredProvider + GitHubPRProvider
finbench/builder.py       one base image per repo, built lazily
finbench/validator.py     discover F2P/P2P in a container, enforce soundness
finbench/pipeline.py      collect -> build -> validate -> finalize
finbench/cli.py           CLI entrypoint
finbench/repos.yaml       equity-quant repo registry
finbench/authored_tasks/  authored value-based task YAMLs
tests/                    unit tests
```
