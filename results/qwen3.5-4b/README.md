# Evaluation: Qwen/Qwen3.5-4B on finbench

**Date:** 2026-06-26
**Model:** `Qwen/Qwen3.5-4B` (served by local vLLM at `http://localhost:8001/v1`)
**Benchmark:** 28 tasks (`benchmark/`)
**Agent loop:** `finbench.agents.loop`, `--max-steps 40`
**Grader:** `finbench.evaluator` (F2P + P2P, resolved = all pass, no regressions)

## Headline

**Resolved 3/28 (10.7%)**

## Outcome breakdown

| Outcome | Count |
|---------|-------|
| RESOLVED | 3 |
| empty prediction | 12 |
| candidate patch failed to apply | 7 |
| tests not all passing | 5 |
| no test results (collection error) | 1 |

## Resolved tasks

- PyPortfolioOpt-pr-172 (3/3 F2P, 1/1 P2P)
- PyPortfolioOpt-pr-228 (2/2, 69/69)
- skfolio-pr-188 (1/1, 11/11)

## Notes

- No vLLM connection errors during the run; failures are genuine model failures.
- Smallest model benchmarked; dominated by empty predictions (12) and apply
  failures (7), i.e. it frequently fails to produce a usable diff at all.
- Reproduce: set FINBENCH_BASE_URL / FINBENCH_MODEL=Qwen/Qwen3.5-4B / FINBENCH_API_KEY
  (unset ALL_PROXY, set NO_PROXY for the local tunnel), then
  `uv run python -m finbench.agents.loop --benchmark benchmark --out preds_4b.json --max-steps 40`
  followed by `uv run python -m finbench.evaluator --predictions preds_4b.json`.

## Files

- `predictions.json` - the agent's candidate patch per task
- `scoreboard.txt` - raw per-task grading table
- `README.md` - this summary
