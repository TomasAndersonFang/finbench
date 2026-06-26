# Evaluation: Qwen/Qwen3.6-27B on finbench

**Date:** 2026-06-26
**Model:** `Qwen/Qwen3.6-27B` (served by local vLLM at `http://localhost:8001/v1`)
**Benchmark:** 28 tasks (`benchmark/`)
**Agent loop:** `finbench.agents.loop`, `--max-steps 40`
**Grader:** `finbench.evaluator` (F2P + P2P, resolved = all pass, no regressions)

## Headline

**Resolved 10/28 (35.7%)** - best of the models benchmarked so far.

## Outcome breakdown

| Outcome | Count |
|---------|-------|
| RESOLVED | 10 |
| tests not all passing | 9 |
| empty prediction | 6 |
| candidate patch failed to apply | 2 |
| no test results (collection error) | 1 |

## Resolved tasks

- PyPortfolioOpt-pr-172 (3/3 F2P, 1/1 P2P)
- PyPortfolioOpt-pr-174 (2/2, 13/13)
- PyPortfolioOpt-pr-22 (2/2, 15/15)
- PyPortfolioOpt-pr-228 (2/2, 69/69)
- PyPortfolioOpt-pr-261 (1/1, 8/8)
- ffn-pr-285 (1/1, 43/43)
- qlib-pr-1803 (1/1, 1/1)
- skfolio-pr-188 (1/1, 11/11)
- skfolio-pr-212 (1/1, 214/214)
- skfolio-pr-53 (8/8, 0/0)

## Notes

- No vLLM connection errors during the run; failures are genuine model failures.
- Far fewer empty predictions (6) and apply-failures (2) than the 35B-A3B and 9B
  runs, and more "tests not all passing" - i.e. it produces real, applyable
  attempts more often, then succeeds on more of them.
- Reproduce: set FINBENCH_BASE_URL / FINBENCH_MODEL=Qwen/Qwen3.6-27B / FINBENCH_API_KEY
  (unset ALL_PROXY, set NO_PROXY for the local tunnel), then
  `uv run python -m finbench.agents.loop --benchmark benchmark --out preds_27b.json --max-steps 40`
  followed by `uv run python -m finbench.evaluator --predictions preds_27b.json`.

## Files

- `predictions.json` - the agent's candidate patch per task
- `scoreboard.txt` - raw per-task grading table
- `README.md` - this summary
