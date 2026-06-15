"""CLI entrypoint for the finbench pipeline."""

from __future__ import annotations

import argparse
import sys

from .builder import docker_available
from .pipeline import run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="finbench",
        description="Synthesize and validate finance coding-agent tasks.",
    )
    p.add_argument("--registry", required=True, help="path to repos.yaml")
    p.add_argument("--authored", required=True, help="directory of authored task YAMLs")
    p.add_argument("--out", required=True, help="output benchmark directory")
    p.add_argument("--count", type=int, default=10, help="max tasks to attempt")
    p.add_argument(
        "--change-type",
        default=None,
        choices=["feature", "bugfix"],
        help="optional filter on change type",
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="force rebuild of base images (no docker cache)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not docker_available():
        print("error: docker is not available on PATH", file=sys.stderr)
        return 2

    outcomes = run(
        registry_path=args.registry,
        authored_dir=args.authored,
        out_dir=args.out,
        count=args.count,
        change_type=args.change_type,
        rebuild=args.rebuild,
    )

    validated = [o for o in outcomes if o.task is not None]
    print(f"\nattempted {len(outcomes)} task(s), validated {len(validated)}\n")
    for o in outcomes:
        if o.task is not None:
            print(
                f"  PASS {o.task.task_id}  "
                f"F2P={len(o.task.fail_to_pass)} P2P={len(o.task.pass_to_pass)}"
            )
        else:
            print(f"  FAIL {o.raw.task_id}  ({o.result.reason})")

    return 0 if validated else 1


if __name__ == "__main__":
    raise SystemExit(main())
