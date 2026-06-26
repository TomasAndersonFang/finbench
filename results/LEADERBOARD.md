# finbench Leaderboard

Benchmark: 28 tasks (`benchmark/`). Agent loop `finbench.agents.loop --max-steps 40`,
graded by `finbench.evaluator` (resolved = all F2P + P2P pass, no regressions).
All runs via local vLLM at `http://localhost:8001/v1`. No connection errors in any run.

| Rank | Model | Resolved | empty | apply-fail | tests-fail | collect-err |
|-----:|-------|---------:|------:|-----------:|-----------:|------------:|
| 1 | Qwen3.6-27B     | **10/28 (35.7%)** | 6 | 2 | 9 | 1 |
| 2 | Qwen3.6-35B-A3B | 6/28 (21.4%)      | 7 | 5 | 10 | 0 |
| 3 | Qwen3.5-9B      | 4/28 (14.3%)      | 13 | 6 | 4 | 1 |
| 4 | Qwen3.5-4B      | 3/28 (10.7%)      | 12 | 7 | 5 | 1 |

## Per-task resolved matrix

`Y` = resolved by that model.

| task | 27B | 35B-A3B | 9B | 4B |
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

## Observations

- **Dense > sparse here.** The dense 27B beats the 35B-A3B (a Mixture-of-Experts
  with ~3B active params/token) by 14 points: effective capacity for multi-step
  agentic coding tracks active params, not total.
- **Monotonic with size within a generation.** Qwen3.5: 9B (4) > 4B (3). Qwen3.6:
  27B (10) > 35B-A3B (6, sparse).
- **Two universally-solved tasks** (PyPortfolioOpt-pr-172, skfolio-pr-188) are the
  easy floor; **skfolio-pr-53 and the two extra PyPortfolioOpt tasks** are 27B-only,
  the current ceiling.
- **Failure mode shifts with size.** Smaller models fail by *not producing a usable
  diff* (empty + apply-fail dominate: 9B=19, 4B=19 of their failures); the 27B fails
  more often by *getting the logic wrong* (tests-fail=9), i.e. it at least attempts.
