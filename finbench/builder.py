"""Two-layer Docker: exactly one base image per repo.

The base image clones the repo once and installs its dependencies. Per-task
isolation does NOT come from per-task images; it comes from checking out the
task's ``base_commit`` at validation time inside a container started from this
base image (see validator.py). Never build an image per task (invariant 6).

Building is *lazy*: this module only builds when asked. The pipeline decides
*when* to ask, and asks only for a repo that actually has a task about to be
validated, so an M1 run that only touches empyrical-reloaded never builds the
qlib or zipline images.

Determinism (invariant 5): the image pins numpy/pandas and forces every BLAS /
OpenMP thread pool to a single thread, so tight-tolerance financial tests do
not flip across machines.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any


def docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "version"],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _slug(repo: str) -> str:
    return repo.split("/")[-1].lower().replace("_", "-")


def image_tag(repo: str) -> str:
    return f"finbench-{_slug(repo)}:base"


def image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "images", "-q", tag],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def render_dockerfile(spec: dict[str, Any]) -> str:
    repo = spec["repo"]
    python = str(spec.get("python", "3.10"))
    install_steps = spec.get("install", ["pip install -e ."])
    numpy = spec.get("numpy")
    pandas = spec.get("pandas")

    lines = [
        f"FROM python:{python}-slim",
        # Invariant 5: single-thread the math libraries for determinism.
        "ENV OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 "
        "NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1",
        "RUN apt-get update && apt-get install -y --no-install-recommends "
        "git build-essential && rm -rf /var/lib/apt/lists/*",
        "WORKDIR /workspace",
        # Full clone (not shallow) so setuptools_scm can resolve a version
        # from tags, and so any base_commit can be checked out at run time.
        f"RUN git clone https://github.com/{repo}.git repo",
        "WORKDIR /workspace/repo",
        "RUN python -m pip install --upgrade pip",
    ]
    # Apply numpy/pandas pins as a GLOBAL pip constraint (invariant 5) so every
    # pip invocation below resolves once against the pins. Pinning after the
    # repo install instead makes pip install latest (e.g. numpy 2.x) and then
    # backtrack/downgrade, which can drag scipy into a source build and hang.
    pins = []
    if numpy:
        pins.append(f"numpy=={numpy}")
    if pandas:
        pins.append(f"pandas=={pandas}")
    if pins:
        constraint = "\\n".join(pins)
        lines.append(f"RUN printf '{constraint}\\n' > /constraints.txt")
        lines.append("ENV PIP_CONSTRAINT=/constraints.txt")
    for step in install_steps:
        lines.append(f"RUN {step}")
    # Test tooling used by the validator to read structured results.
    lines.append("RUN pip install pytest pytest-json-report")
    return "\n".join(lines) + "\n"


def build_base_image(spec: dict[str, Any], no_cache: bool = False) -> str:
    """Build the base image for one repo and return its tag."""
    repo = spec["repo"]
    tag = image_tag(repo)
    dockerfile = render_dockerfile(spec)
    with tempfile.TemporaryDirectory() as ctx:
        (Path(ctx) / "Dockerfile").write_text(dockerfile)
        cmd = ["docker", "build", "-t", tag, ctx]
        if no_cache:
            cmd.insert(2, "--no-cache")
        subprocess.run(cmd, check=True)
    return tag


def ensure_base_image(spec: dict[str, Any], rebuild: bool = False) -> str:
    """Build the image only if it is not already present (build cache)."""
    tag = image_tag(spec["repo"])
    if rebuild or not image_exists(tag):
        return build_base_image(spec, no_cache=rebuild)
    return tag
