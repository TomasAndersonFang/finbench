# Evaluation: Qwen/Qwen3.5-9B on finbench

**Date:** 2026-06-26
**Model:** `Qwen/Qwen3.5-9B` (served by local vLLM at `http://localhost:8001/v1`)
**Benchmark:** 28 tasks (`benchmark/`)
**Agent loop:** `finbench.agents.loop`, `--max-steps 40`
**Grader:** `finbench.evaluator` (F2P + P2P, resolved = all pass, no regressions)

## Headline

**Resolved 4/28 (14.3%)**

## Outcome breakdown

| Outcome | Count |
|---------|-------|
| RESOLVED | 4 |
| candidate patch failed to apply | 6 |
| tests not all passing | 4 |
| empty prediction | 13 |
| no test results (collection error) | 1 |

## Resolved tasks

- PyPortfolioOpt-pr-172 (3/3 F2P, 1/1 P2P)
- PyPortfolioOpt-pr-228 (2/2, 69/69)
- qlib-pr-1803 (1/1, 1/1)
- skfolio-pr-188 (1/1, 11/11)

## Notes

- No vLLM connection errors during the run; the 13 empty predictions are genuine
  model failures (agent stopped without editing, or hit max_steps with no diff).
- Smaller model than the 3.6-35B baseline; more empty predictions and apply
  failures, consistent with weaker tool-use / diff-formatting ability.
- Reproduce: set FINBENCH_BASE_URL / FINBENCH_MODEL=Qwen/Qwen3.5-9B / FINBENCH_API_KEY
  (unset ALL_PROXY, set NO_PROXY for the local tunnel), then
  `uv run python -m finbench.agents.loop --benchmark benchmark --out preds_9b.json --max-steps 40`
  followed by `uv run python -m finbench.evaluator --predictions preds_9b.json`.

## Files

- `predictions.json` - the agent's candidate patch per task
- `scoreboard.txt` - raw per-task grading table
- `README.md` - this summary
