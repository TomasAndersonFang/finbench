"""Mutation check for validated tasks (M4).

Goal: confirm each task's tests are actually sensitive to the gold patch. We
perturb the gold patch (a single added source line at a time), re-apply it in a
container, and re-run *only* the task's F2P tests. A mutant is KILLED if at least
one F2P test stops passing (the verifier turns red). A task is FLAGGED when no
behaviour-changing mutant is killed: its tests do not catch the perturbation.

Mutations are syntax-preserving and act only on ``+`` (added) source lines, never
on context or removed lines, so the unified diff still applies cleanly (line
counts are unchanged; only characters inside one added line are substituted).

This never weakens the soundness gate (invariant 1); it is an extra, read-only
audit on top of an already-validated benchmark.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
import subprocess
from dataclasses import dataclass, field

# Numeric literal not glued to an identifier or attribute (avoid x2, obj.5).
_NUM_RE = re.compile(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w.\d])")

# A quoted string literal with non-empty content (handles escapes).
_STR_RE = re.compile(r"""(["'])((?:\\.|(?!\1).)+?)\1""")

# Space-padded binary operators, so we never touch ** vs *, ->, or unary signs.
_OP_SWAPS = {
    " + ": " - ",
    " - ": " + ",
    " * ": " / ",
    " / ": " * ",
    " ** ": " * ",
    " == ": " != ",
    " != ": " == ",
    " >= ": " <= ",
    " <= ": " >= ",
    " < ": " > ",
    " > ": " < ",
    " is not ": " is ",
    " not in ": " in ",
    " and ": " or ",
    " or ": " and ",
}

# Lines that are prose, not executable code: skip so we do not count no-op mutants.
_PROSE_PREFIXES = (
    "#",
    '"""',
    "'''",
    '"',
    "'",
    ":param",
    ":type",
    ":return",
    ":rtype",
    ":raises",
    ">>>",
    "*",
    "-",
    ".. ",
)


@dataclass
class Mutant:
    label: str
    patch: str


@dataclass
class TaskMutationReport:
    task_id: str
    mutants_total: int = 0
    mutants_killed: int = 0
    identity_ok: bool = True
    survivors: list[str] = field(default_factory=list)  # labels of code mutants not killed
    error: str = ""

    @property
    def flagged(self) -> bool:
        # Flagged if the verifier never turned red, or could not be exercised.
        if self.error:
            return True
        if self.mutants_total == 0:
            return True
        return self.mutants_killed == 0


def _is_code_line(code: str) -> bool:
    s = code.strip()
    if not s:
        return False
    return not s.startswith(_PROSE_PREFIXES)


def _mutate_line(code: str) -> list[tuple[str, str]]:
    """Return (kind, mutated_code) variants for one source line."""
    out: list[tuple[str, str]] = []

    m = _NUM_RE.search(code)
    if m:
        tok = m.group(1)
        if "." in tok:
            new = repr(float(tok) + 1.0)
        else:
            new = str(int(tok) + 1)
        mutated = code[: m.start()] + new + code[m.end() :]
        if mutated != code:
            out.append(("num", mutated))

    for src, dst in _OP_SWAPS.items():
        if src in code:
            out.append(("op" + src.strip(), code.replace(src, dst, 1)))
            break  # one operator mutation per line is enough for diversity

    # String-literal mutation: change the value (append a marker before the
    # closing quote). Catches code that keys on a string default/enum/column
    # name, where numeric/operator mutations do not apply.
    sm = _STR_RE.search(code)
    if sm:
        quote, content = sm.group(1), sm.group(2)
        mutated = code[: sm.start()] + quote + content + "_MUT" + quote + code[sm.end() :]
        if mutated != code:
            out.append(("str", mutated))

    return out


def _docstring_indices(added: list[tuple[int, str]]) -> set[int]:
    """Indices of added lines that sit inside a triple-quoted docstring/string.

    Tracked as a state machine over the added lines in order, so multi-line
    docstring bodies (which do not start with a quote) are skipped too.
    """
    skip: set[int] = set()
    inside = False
    for idx, body in added:
        triples = body.count('"""') + body.count("'''")
        if inside:
            skip.add(idx)
            if triples % 2 == 1:
                inside = False
        else:
            if triples % 2 == 1:
                skip.add(idx)
                inside = True
            elif triples >= 2:
                skip.add(idx)  # single-line docstring
    return skip


def generate_mutants(gold_patch: str, cap: int = 30) -> list[Mutant]:
    """Build behaviour-changing mutants of a gold patch, one added line each.

    Only ``+`` source lines that look like code (not docstrings/comments) are
    touched. Computational mutations (numeric, arithmetic/comparison/logical
    operators) are prioritised over string-literal mutations, so on a large diff
    the cap still covers the logic core rather than getting consumed by string
    tweaks on signatures and messages. Within a priority, mutants are ordered by
    line for spread.
    """
    lines = gold_patch.splitlines(keepends=True)
    added = [
        (i, raw[1:].rstrip("\n"))
        for i, raw in enumerate(lines)
        if raw.startswith("+") and not raw.startswith("+++")
    ]
    doc_skip = _docstring_indices(added)

    cands: list[tuple[int, int, str, str]] = []  # (priority, line_idx, kind, full)
    for i, body in added:
        if i in doc_skip or not _is_code_line(body):
            continue
        nl = "\n" if lines[i].endswith("\n") else ""
        for kind, mutated_body in _mutate_line(body):
            priority = 1 if kind == "str" else 0  # computational mutants first
            cands.append((priority, i, kind, "+" + mutated_body + nl))

    cands.sort(key=lambda c: (c[0], c[1]))

    mutants: list[Mutant] = []
    for _prio, idx, kind, full in cands[:cap]:
        new_lines = list(lines)
        new_lines[idx] = full
        mutants.append(Mutant(label=f"L{idx}:{kind}", patch="".join(new_lines)))
    return mutants


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _build_script(base_commit: str, test_patch: str, f2p: list[str], mutants: list[Mutant]) -> str:
    nodes = " ".join(shlex.quote(n) for n in f2p)
    parts = [
        "set -e",
        "cd /workspace/repo",
        f"git checkout -f {base_commit} >/dev/null 2>&1",
        "git clean -fdq",
        f"echo {_b64(test_patch)} | base64 -d > /tmp/test.patch",
        "git apply --whitespace=nowarn /tmp/test.patch",
        "set +e",
    ]
    for k, mut in enumerate(mutants):
        parts.append(f"echo {_b64(mut.patch)} | base64 -d > /tmp/m{k}.patch")
        parts.append(f"if git apply --whitespace=nowarn /tmp/m{k}.patch 2>/tmp/ae{k}; then")
        parts.append(
            f"  python -m pytest {nodes} -p no:cacheprovider -o addopts='' "
            f"--json-report --json-report-file=/tmp/m{k}.json >/tmp/m{k}.log 2>&1"
        )
        parts.append(f"  git apply -R --whitespace=nowarn /tmp/m{k}.patch >/dev/null 2>&1")
        parts.append(f'  echo "===MUT {k} OK==="; cat /tmp/m{k}.json 2>/dev/null; echo')
        parts.append("else")
        parts.append(f'  echo "===MUT {k} APPLYFAIL==="')
        parts.append("fi")
    return "\n".join(parts) + "\n"


def _parse_outcomes(payload: str) -> dict[str, str]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return {t["nodeid"]: t.get("outcome", "") for t in data.get("tests", [])}


def _all_pass(outcomes: dict[str, str], f2p: list[str]) -> bool:
    return bool(outcomes) and all(outcomes.get(n) == "passed" for n in f2p)


def run_task_mutation_check(task: dict, image: str, cap: int = 30, timeout: int = 1800) -> TaskMutationReport:
    rep = TaskMutationReport(task_id=task["task_id"])
    f2p = task["fail_to_pass"]
    if not f2p:
        rep.error = "task has no F2P nodes"
        return rep

    gold = task["gold_patch"]
    generated = generate_mutants(gold, cap=cap)
    if not generated:
        rep.error = "no behaviour-changing mutants could be generated"
        return rep

    # Mutant 0 is the identity gold patch: a control that must NOT be killed.
    mutants = [Mutant(label="identity", patch=gold)] + generated
    script = _build_script(task["base_commit"], task["test_patch"], f2p, mutants)
    # Feed the script over stdin (bash -s), not argv: with many embedded base64
    # patches the command line otherwise blows past ARG_MAX ("argument list too
    # long") on the larger mined diffs.
    proc = subprocess.run(
        ["docker", "run", "--rm", "-i", image, "bash", "-s"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = proc.stdout

    for k, mut in enumerate(mutants):
        ok_mark = f"===MUT {k} OK==="
        fail_mark = f"===MUT {k} APPLYFAIL==="
        if fail_mark in out:
            # patch did not apply; ignore for identity, skip for others
            if k == 0:
                rep.identity_ok = False
                rep.error = "identity gold patch failed to re-apply"
            continue
        if ok_mark not in out:
            continue
        seg = out.split(ok_mark, 1)[1]
        # cut at the next marker if present
        nxt = re.search(r"===MUT \d+ (OK|APPLYFAIL)===", seg)
        if nxt:
            seg = seg[: nxt.start()]
        outcomes = _parse_outcomes(seg.strip())
        passes = _all_pass(outcomes, f2p)
        if k == 0:
            rep.identity_ok = passes
            if not passes:
                rep.error = "identity gold patch did not reproduce F2P pass"
            continue
        rep.mutants_total += 1
        if not passes:
            rep.mutants_killed += 1
        else:
            rep.survivors.append(mut.label)
    return rep


def _main() -> int:
    import argparse
    import glob
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Mutation check the benchmark (M4).")
    ap.add_argument("--benchmark", default="benchmark")
    ap.add_argument("--cap", type=int, default=30, help="max mutants per task")
    ap.add_argument("--task", default=None, help="only this task_id")
    args = ap.parse_args()

    paths = sorted(glob.glob(str(Path(args.benchmark) / "*" / "task.json")))
    reports: list[TaskMutationReport] = []
    for p in paths:
        task = json.loads(Path(p).read_text())
        if args.task and task["task_id"] != args.task:
            continue
        image = task["image"]
        print(f"[mutation] {task['task_id']} (F2P={len(task['fail_to_pass'])}) ...", flush=True)
        rep = run_task_mutation_check(task, image, cap=args.cap)
        reports.append(rep)
        status = "FLAGGED" if rep.flagged else "ok"
        extra = f" identity_ok={rep.identity_ok}" if not rep.identity_ok else ""
        print(
            f"  -> {status}  killed {rep.mutants_killed}/{rep.mutants_total}"
            f"{(' error=' + rep.error) if rep.error else ''}{extra}"
        )
        if rep.survivors:
            print(f"     surviving mutants: {', '.join(rep.survivors)}")

    flagged = [r for r in reports if r.flagged]
    print("\n=== mutation summary ===")
    for r in reports:
        print(
            f"  {'FLAG ' if r.flagged else 'pass '} {r.task_id:40s} "
            f"killed={r.mutants_killed}/{r.mutants_total} survivors={len(r.survivors)}"
            f"{(' ' + r.error) if r.error else ''}"
        )
    print(f"\n{len(reports)} tasks, {len(flagged)} flagged")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(_main())
