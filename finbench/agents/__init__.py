"""Agent runners that produce candidate patches for the evaluator.

The runner is provider-agnostic: it drives an LLM through a bash tool loop inside
the task's container and emits a unified diff. Swapping models is a config change
(provider base_url + api_key + model), so Claude, GPT, Gemini, DeepSeek, or a
local open-weights model can all be benchmarked through the same loop. The
grading (finbench.evaluator) never sees which model produced the patch.
"""
