# Evaluation: Qwen/Qwen3.6-35B-A3B on finbench

**Date:** 2026-06-25
**Model:** `Qwen/Qwen3.6-35B-A3B` (served by local vLLM at `http://localhost:8001/v1`)
**Benchmark:** 28 tasks (`benchmark/`)
**Agent loop:** `finbench.agents.loop`, `--max-steps 40`
**Grader:** `finbench.evaluator` (F2P + P2P, resolved = all pass, no regressions)

## Headline

**Resolved 6/28 (21.4%)**

## Outcome breakdown

| Outcome | Count | Note |
|---------|-------|------|
| RESOLVED | 6 | all F2P + P2P pass |
| tests not all passing | 10 | patch applied & ran but failed F2P (wrong impl) |
| empty prediction | 7 | model made no edits / ran out of steps (genuine, not connection errors) |
| candidate patch failed to apply | 5 | malformed/non-applyable diff |

## Resolved tasks

- PyPortfolioOpt-pr-172 (3/3 F2P, 1/1 P2P)
- PyPortfolioOpt-pr-261 (1/1, 8/8)
- ffn-pr-285 (1/1, 43/43)
- qlib-pr-1803 (1/1, 1/1)
- skfolio-pr-188 (1/1, 11/11)
- skfolio-pr-212 (1/1, 214/214)

## Close misses

- skfolio-pr-132: 6/7 F2P
- skfolio-pr-221: 2/3 F2P

## Notes

- The 7 empty predictions were verified as genuine model failures (agent declared
  "done" without editing, or hit max_steps), not vLLM connection drops. Score is fair.
- Every RESOLVED task passed 100% of P2P, so wins introduced no regressions.
- Reproduce: set FINBENCH_BASE_URL / FINBENCH_MODEL / FINBENCH_API_KEY (and unset
  ALL_PROXY / set NO_PROXY for the local tunnel), then
  `uv run python -m finbench.agents.loop --benchmark benchmark --out preds.json --max-steps 40`
  followed by `uv run python -m finbench.evaluator --predictions preds.json`.

## Files

- `predictions.json` - the agent's candidate patch per task (input to the grader)
- `scoreboard.txt` - raw per-task grading table
- `README.md` - this summary
