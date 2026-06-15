"""Orchestrate collect -> build -> validate -> finalize.

Base images are built lazily: a repo's image is built only the first time a
task for that repo is about to be validated. So a run that only contains
empyrical tasks never touches the qlib or zipline images (invariant 6 still
holds: one image per repo, cached across that repo's tasks).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .builder import ensure_base_image
from .providers import collect_authored
from .schema import RawTask, Task
from .validator import ValidationResult, validate


@dataclass
class PipelineOutcome:
    task: Optional[Task]
    result: ValidationResult
    raw: RawTask


def load_registry(path: str | Path) -> dict[str, dict]:
    data = yaml.safe_load(Path(path).read_text())
    registry: dict[str, dict] = {}
    for spec in data.get("repos", []):
        registry[spec["repo"]] = spec
    return registry


def write_task(out_dir: str | Path, task: Task) -> Path:
    task_dir = Path(out_dir) / task.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / "task.json"
    path.write_text(json.dumps(task.to_dict(), indent=2) + "\n")
    return path


def run(
    registry_path: str | Path,
    authored_dir: str | Path,
    out_dir: str | Path,
    count: int,
    change_type: Optional[str] = None,
    rebuild: bool = False,
) -> list[PipelineOutcome]:
    registry = load_registry(registry_path)

    candidates = collect_authored(authored_dir)
    if change_type:
        candidates = [c for c in candidates if c.change_type == change_type]
    candidates = candidates[:count]

    built: dict[str, str] = {}  # repo -> image tag (lazy cache)
    outcomes: list[PipelineOutcome] = []

    for raw in candidates:
        if raw.repo not in registry:
            outcomes.append(
                PipelineOutcome(
                    None,
                    ValidationResult(False, reason=f"repo {raw.repo} not in registry"),
                    raw,
                )
            )
            continue

        # LAZY: build this repo's base image only now, on first need.
        if raw.repo not in built:
            built[raw.repo] = ensure_base_image(registry[raw.repo], rebuild=rebuild)
        image = built[raw.repo]

        result = validate(raw, image)
        if result.ok:
            task = Task.from_raw(raw, result.fail_to_pass, result.pass_to_pass, image)
            write_task(out_dir, task)
            outcomes.append(PipelineOutcome(task, result, raw))
        else:
            outcomes.append(PipelineOutcome(None, result, raw))

    return outcomes
