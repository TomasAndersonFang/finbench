"""Single source of truth for the task data model.

A RawTask is what a provider emits before validation: it carries the
instruction, the pinned base commit, and the two patches (gold + test).
A Task is the validated, finalized artifact that gets written to the
benchmark. The only fields the agent is ever allowed to see are
``instruction`` and the pre-PR repo state (``repo`` + ``base_commit``).
Everything else (gold_patch, test_patch, fail_to_pass, ...) is grading
material and must never leak into the instruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RawTask:
    """A candidate task, before the soundness gate has run."""

    task_id: str
    repo: str  # "owner/name"
    base_commit: str
    instruction: str
    gold_patch: str  # unified diff applied to source files
    test_patch: str  # unified diff applied to test files
    change_type: str = "feature"  # "feature" | "bugfix"
    source: str = "authored"  # "authored" | "mined"
    finance_tags: list[str] = field(default_factory=list)
    # Optional hint of node ids the author expects to be F2P. The validator
    # always discovers transitions itself; this is only a sanity cross-check.
    expected_fail_to_pass: Optional[list[str]] = None

    def __post_init__(self) -> None:
        # Invariant 3: test_patch and gold_patch must not overlap by file.
        from .diffutils import patch_paths

        gold = set(patch_paths(self.gold_patch))
        test = set(patch_paths(self.test_patch))
        overlap = gold & test
        if overlap:
            raise ValueError(
                f"gold_patch and test_patch overlap by file: {sorted(overlap)}"
            )


@dataclass
class Task:
    """A validated task, ready to write into the benchmark."""

    task_id: str
    repo: str
    base_commit: str
    instruction: str
    gold_patch: str
    test_patch: str
    change_type: str
    source: str
    finance_tags: list[str]
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    image: str  # base image tag used to validate

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_raw(
        cls,
        raw: RawTask,
        fail_to_pass: list[str],
        pass_to_pass: list[str],
        image: str,
    ) -> "Task":
        return cls(
            task_id=raw.task_id,
            repo=raw.repo,
            base_commit=raw.base_commit,
            instruction=raw.instruction,
            gold_patch=raw.gold_patch,
            test_patch=raw.test_patch,
            change_type=raw.change_type,
            source=raw.source,
            finance_tags=list(raw.finance_tags),
            fail_to_pass=list(fail_to_pass),
            pass_to_pass=list(pass_to_pass),
            image=image,
        )
