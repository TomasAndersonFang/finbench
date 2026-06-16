"""Provider-agnostic agentic loop that produces a candidate patch for one task.

It starts the task's base image, checks out ``base_commit``, and gives the model
a single ``bash`` tool whose commands run inside that container. The model reads
and edits the repo until it stops calling tools (or hits ``max_steps``); then we
capture ``git add -A && git diff`` against the base commit as the candidate patch
(this includes new files). The model is shown only the instruction and the repo
state, never the gold or test patches (invariant 2).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from .backends import Backend

BASH_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a bash command in the repository at /workspace/repo and get its "
                "stdout/stderr. Use it to explore, read, and edit files, and to run "
                "code. State persists between calls."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to run."}
                },
                "required": ["command"],
            },
        },
    }
]

SYSTEM_PROMPT = (
    "You are an autonomous software engineering agent working in a git repository "
    "at /workspace/repo, checked out at a specific commit. Implement the change "
    "described by the user. Use the bash tool to explore the code, make edits, and "
    "verify your work. Make the smallest change that fully satisfies the request. "
    "Do not edit test files; they are graded separately and your edits to them are "
    "discarded. When you are confident the change is complete, stop calling tools "
    "and reply with a short summary."
)

_MAX_OUTPUT = 6000  # truncate each tool result to keep context bounded


@dataclass
class AgentRun:
    task_id: str
    patch: str
    steps: int
    stopped: str  # "done" | "max_steps" | "error"


def _docker(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kw)


def _exec(cid: str, command: str, timeout: int = 120) -> str:
    try:
        p = subprocess.run(
            ["docker", "exec", cid, "bash", "-lc", command],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "[command timed out]"
    out = (p.stdout or "") + (p.stderr or "")
    if len(out) > _MAX_OUTPUT:
        out = out[:_MAX_OUTPUT] + f"\n[...truncated {len(out) - _MAX_OUTPUT} chars]"
    return out or "[no output]"


def run_agent(task: dict, backend: Backend, max_steps: int = 40, verbose: bool = False) -> AgentRun:
    image, base = task["image"], task["base_commit"]
    cid = _docker("run", "-d", image, "sleep", "infinity").stdout.strip()
    stopped = "done"
    steps = 0
    try:
        _exec(cid, f"cd /workspace/repo && git checkout -f {base} && git clean -fdq")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task:\n\n{task['instruction']}"},
        ]
        for steps in range(1, max_steps + 1):
            turn = backend.chat(messages, BASH_TOOL)
            if verbose and turn.text:
                print(f"  [{task['task_id']}] {turn.text[:200]}")
            messages.append(backend.assistant_message(turn))
            if not turn.tool_calls:
                stopped = "done"
                break
            for call in turn.tool_calls:
                cmd = call.arguments.get("command", "") if call.name == "bash" else ""
                result = _exec(cid, f"cd /workspace/repo && {cmd}") if cmd else "[no command]"
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )
        else:
            stopped = "max_steps"
        # Capture the candidate patch (staged diff includes new files).
        patch = _exec(
            cid,
            f"cd /workspace/repo && git add -A && git diff --cached {base}",
            timeout=60,
        )
        if patch.startswith("[no output]"):
            patch = ""
        return AgentRun(task_id=task["task_id"], patch=patch, steps=steps, stopped=stopped)
    except Exception as e:  # noqa: BLE001
        return AgentRun(task_id=task["task_id"], patch="", steps=steps, stopped=f"error: {e}")
    finally:
        _docker("rm", "-f", cid)


def _main() -> int:
    import argparse
    from pathlib import Path

    from .backends import backend_from_env

    ap = argparse.ArgumentParser(description="Run an LLM agent over the benchmark.")
    ap.add_argument("--benchmark", default="benchmark")
    ap.add_argument("--out", default="predictions.json", help="where to write task_id -> patch")
    ap.add_argument("--task", default=None, help="only run this task_id")
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    backend = backend_from_env()
    preds: dict[str, str] = {}
    for p in sorted(Path(args.benchmark).glob("*/task.json")):
        task = json.loads(p.read_text())
        if args.task and task["task_id"] != args.task:
            continue
        print(f"[agent] {task['task_id']} ...", flush=True)
        run = run_agent(task, backend, max_steps=args.max_steps, verbose=args.verbose)
        preds[task["task_id"]] = run.patch
        print(f"  -> {run.stopped} in {run.steps} steps, patch {len(run.patch)} chars")
        Path(args.out).write_text(json.dumps(preds, indent=2))  # checkpoint after each
    print(f"\nwrote {args.out} with {len(preds)} prediction(s)")
    print("grade with: uv run python -m finbench.evaluator --predictions " + args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
