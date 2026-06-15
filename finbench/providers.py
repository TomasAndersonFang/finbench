"""Task providers: where RawTasks come from.

* AuthoredProvider reads hand-written value-based tasks from a directory of
  YAML files. Each YAML declares the new source file(s) and the new test
  file(s) as full contents; we turn those into new-file diffs. This keeps the
  author from having to hand-write fragile unified diffs and guarantees the
  gold/test patches never overlap by file (invariant 3).
* GitHubPRProvider mines merged PRs and splits their diff by path.

Both emit the same RawTask schema.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

import yaml

from .diffutils import make_new_file_patch, split_patch
from .github_client import GitHubClient
from .schema import RawTask


def _patch_from_files(files: dict[str, str]) -> str:
    return "".join(make_new_file_patch(path, content) for path, content in files.items())


class AuthoredProvider:
    """Yield RawTasks from authored YAML files."""

    def __init__(self, directory: str | os.PathLike):
        self.directory = Path(directory)

    def _load_one(self, path: Path) -> RawTask:
        data = yaml.safe_load(path.read_text())

        # Patches may be given directly, or built from full file contents.
        gold_patch = data.get("gold_patch")
        if gold_patch is None:
            gold_patch = _patch_from_files(data["gold_files"])
        test_patch = data.get("test_patch")
        if test_patch is None:
            test_patch = _patch_from_files(data["test_files"])

        return RawTask(
            task_id=data["id"],
            repo=data["repo"],
            base_commit=str(data["base_commit"]),
            instruction=data["instruction"],
            gold_patch=gold_patch,
            test_patch=test_patch,
            change_type=data.get("change_type", "feature"),
            source="authored",
            finance_tags=list(data.get("finance_tags", [])),
            expected_fail_to_pass=data.get("expected_fail_to_pass"),
        )

    def tasks(self) -> Iterator[RawTask]:
        for path in sorted(self.directory.glob("*.yaml")):
            yield self._load_one(path)


def build_instruction(title: str, body: str | None) -> str:
    """Turn a PR title/body into an agent instruction.

    Only the natural-language description is used. The gold and test patches are
    never included (invariant 2); the PR body does not contain them. Body is
    truncated to keep the instruction focused.
    """
    title = (title or "").strip()
    body = (body or "").strip()
    if not body:
        return title
    if len(body) > 1500:
        body = body[:1500].rstrip() + "\n..."
    return f"{title}\n\n{body}"


class GitHubPRProvider:
    """Mine merged PRs into RawTasks (split diff by path)."""

    def __init__(self, repo: str, client: GitHubClient | None = None):
        self.repo = repo
        self.client = client or GitHubClient()

    def task_from_pr(
        self,
        number: int,
        instruction: str,
        base_commit: str,
        finance_tags: list[str] | None = None,
    ) -> RawTask:
        diff = self.client.get_pull_diff(self.repo, number)
        test_patch, gold_patch = split_patch(diff)
        if not test_patch.strip():
            raise ValueError(f"PR #{number} touches no test files; skip")
        if not gold_patch.strip():
            raise ValueError(f"PR #{number} touches no source files; skip")
        return RawTask(
            task_id=f"{self.repo.split('/')[-1]}-pr-{number}",
            repo=self.repo,
            base_commit=base_commit,
            instruction=instruction,
            gold_patch=gold_patch,
            test_patch=test_patch,
            change_type="feature",
            source="mined",
            finance_tags=list(finance_tags or []),
        )

    def task_from_pull(self, pull: dict, finance_tags: list[str] | None = None) -> RawTask:
        """Build a RawTask straight from a PR object, resolving the base commit."""
        base_commit = self.client.base_commit_for_pull(self.repo, pull)
        instruction = build_instruction(pull.get("title", ""), pull.get("body"))
        return self.task_from_pr(
            pull["number"], instruction, base_commit, finance_tags=finance_tags
        )


def collect_authored(directory: str | os.PathLike) -> list[RawTask]:
    return list(AuthoredProvider(directory).tasks())
