"""Thin GitHub REST client. Token comes from $GITHUB_TOKEN.

Only what the miner needs: fetch a merged PR, its unified diff, and the
issue it closes. Not exercised by the authored-task (M1) path, but kept
small and testable so the mined provider has a real backend.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: Optional[str] = None, session: Optional[requests.Session] = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.session = session or requests.Session()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        url = f"{API}/repos/{repo}/pulls/{number}"
        resp = self.session.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def list_merged_pulls(self, repo: str, max_pages: int = 4) -> list[dict[str, Any]]:
        """Return merged PRs (newest first). Closed-but-not-merged are dropped."""
        url = f"{API}/repos/{repo}/pulls"
        merged: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            resp = self.session.get(
                url,
                headers=self._headers(),
                params={
                    "state": "closed",
                    "per_page": 100,
                    "page": page,
                    "sort": "created",
                    "direction": "desc",
                },
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            merged.extend(p for p in batch if p.get("merged_at"))
        return merged

    def get_commit(self, repo: str, sha: str) -> dict[str, Any]:
        url = f"{API}/repos/{repo}/commits/{sha}"
        resp = self.session.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def base_commit_for_pull(self, repo: str, pull: dict[str, Any]) -> str:
        """Resolve the commit the PR diff applies to.

        The pulls .diff endpoint returns ``base...head`` (against the merge
        base). The first parent of the merge commit is that base state for all
        three merge styles (merge / squash / rebase), so it is the commit to
        check out before applying the patches. Falls back to base.sha.
        """
        merge_sha = pull.get("merge_commit_sha")
        if merge_sha:
            parents = self.get_commit(repo, merge_sha).get("parents", [])
            if parents:
                return parents[0]["sha"]
        return pull["base"]["sha"]

    def get_pull_diff(self, repo: str, number: int) -> str:
        url = f"{API}/repos/{repo}/pulls/{number}"
        resp = self.session.get(url, headers=self._headers("application/vnd.github.v3.diff"))
        resp.raise_for_status()
        return resp.text

    def list_pull_files(self, repo: str, number: int) -> list[dict[str, Any]]:
        url = f"{API}/repos/{repo}/pulls/{number}/files"
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = self.session.get(
                url, headers=self._headers(), params={"per_page": 100, "page": page}
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            files.extend(batch)
            page += 1
        return files
