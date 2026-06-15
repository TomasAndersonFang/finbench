"""Utilities for building and splitting unified diffs.

Two jobs:

1. Build robust ``git apply``-compatible diffs for brand-new files. Authored
   tasks add new source/test files, so a new-file diff (against /dev/null) needs
   no context matching and applies cleanly at any base commit.
2. Split a mined PR diff into a test patch and a source patch, by path. The
   split is always by path so the two patches can never touch the same file
   (invariant 3).
"""

from __future__ import annotations

import re


_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+?)$")


def is_test_path(path: str) -> bool:
    """Heuristic: does this path belong to the test patch?"""
    parts = path.split("/")
    base = parts[-1]
    if "tests" in parts or "test" in parts:
        return True
    if base.startswith("test_") or base.endswith("_test.py"):
        return True
    if base == "conftest.py":
        return True
    return False


def make_new_file_patch(path: str, content: str) -> str:
    """Return a unified diff that creates ``path`` with ``content``.

    Uses the /dev/null new-file form. ``git apply`` does not require the
    ``index`` blob hashes for this, so we omit them; this keeps the diff
    reproducible without shelling out to git.
    """
    lines = content.splitlines()
    body = [f"+{line}" for line in lines]
    no_newline = not content.endswith("\n")
    header = [
        f"diff --git a/{path} b/{path}",
        "new file mode 100644",
        "--- /dev/null",
        f"+++ b/{path}",
        f"@@ -0,0 +1,{len(lines)} @@",
    ]
    out = header + body
    if no_newline and lines:
        out.append("\\ No newline at end of file")
    return "\n".join(out) + "\n"


def patch_paths(diff: str) -> list[str]:
    """Return the target (b/) paths touched by a unified diff."""
    paths: list[str] = []
    for line in diff.splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            paths.append(m.group("b"))
    return paths


def _split_into_file_blocks(diff: str) -> list[tuple[str, str]]:
    """Split a diff into (target_path, block_text) per file."""
    blocks: list[tuple[str, str]] = []
    current: list[str] = []
    current_path: str | None = None
    for line in diff.splitlines(keepends=True):
        m = _DIFF_GIT_RE.match(line.rstrip("\n"))
        if m:
            if current and current_path is not None:
                blocks.append((current_path, "".join(current)))
            current = [line]
            current_path = m.group("b")
        else:
            current.append(line)
    if current and current_path is not None:
        blocks.append((current_path, "".join(current)))
    return blocks


def split_patch(diff: str) -> tuple[str, str]:
    """Split a combined PR diff into (test_patch, source_patch) by path."""
    test_blocks: list[str] = []
    source_blocks: list[str] = []
    for path, block in _split_into_file_blocks(diff):
        if is_test_path(path):
            test_blocks.append(block)
        else:
            source_blocks.append(block)
    return "".join(test_blocks), "".join(source_blocks)
