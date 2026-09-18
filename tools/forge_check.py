"""Fast targeted test selector for Forge scientific changes.

This is a developer convenience gate, not a replacement for FAST, SCIENTIFIC
or hardened recertification. It never triggers GitHub workflows.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "scientific_regression" / "manifest.json"

ARCHITECTURE_TESTS = (
    "tests/test_repository_architecture.py",
    "tests/test_core_api_layering.py",
    "tests/test_scientific_regression_manifest.py",
    "tests/test_forge_check.py",
    "tests/test_agent_workflow_contract.py",
)

ALL_SCIENTIFIC_TAGS = frozenset({
    "verdict", "evidence", "vnv", "applicability", "compiler", "selection",
    "context", "uq", "policy", "external", "gaps", "challenge", "replay",
    "provenance",
})


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def tags_for_paths(paths: Iterable[str]) -> set[str]:
    paths = {str(p).replace("\\", "/") for p in paths}
    tags: set[str] = set()

    if any(p.startswith("src/engcore/claims/") for p in paths):
        return set(ALL_SCIENTIFIC_TAGS)

    if any(p.startswith("src/engcore/credibility/") for p in paths):
        tags |= {"verdict", "evidence", "context", "uq", "external", "vnv"}

    if any(p.startswith("src/engcore/sria/") for p in paths):
        tags |= {"verdict", "evidence", "context", "policy", "uq", "external"}

    if any(p.startswith("src/engcore/mcp/") for p in paths):
        tags |= {"verdict", "evidence", "context"}

    if any(p.startswith("src/engcore/scientific/results/") for p in paths):
        tags |= {"verdict", "vnv", "uq", "provenance"}

    if any(p.startswith("src/engcore/scientific/models/") for p in paths):
        tags |= {"applicability", "compiler", "selection"}

    if any(p.startswith("src/engcore/uq/") or p.startswith("src/engcore/hybrid_uq/") for p in paths):
        tags |= {"uq", "verdict"}

    return tags


def cases_for_tags(tags: set[str]) -> list[str]:
    data = load_manifest()
    nodeids: list[str] = []
    for case in data["cases"]:
        if tags.intersection(case["tags"]):
            nodeids.append(case["nodeid"])
    return nodeids


def changed_files(base: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"git diff against {base!r} failed:\n{proc.stderr.strip()}\n"
            "Pass --base <ref> naming a locally available base ref."
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def build_targets(paths: Iterable[str], *, regression: bool = False) -> list[str]:
    targets = list(ARCHITECTURE_TESTS)
    if regression:
        targets.extend(case["nodeid"] for case in load_manifest()["cases"])
    else:
        tags = tags_for_paths(paths)
        targets.extend(cases_for_tags(tags))

    # Stable order, no duplicate node IDs.
    return list(dict.fromkeys(targets))


def build_command(targets: Iterable[str], workers: int) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if workers:
        cmd += ["-n", str(workers), "--dist", "loadfile"]
    cmd += list(targets)
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--changed", action="store_true", help="select tests from changed files (default)")
    mode.add_argument("--regression", action="store_true", help="run the complete fixed scientific regression pack")
    parser.add_argument("--base", default=os.environ.get("FORGE_BASE", "main"), help="base ref for --changed")
    parser.add_argument("--workers", type=int, default=0, help="pytest-xdist workers; 0 runs serially")
    parser.add_argument("--dry-run", action="store_true", help="print selection without executing pytest")
    parser.add_argument("--list", action="store_true", help="print selected test targets")
    args = parser.parse_args(argv)

    if args.workers < 0:
        parser.error("--workers must be >= 0")

    paths: list[str] = []
    if not args.regression:
        paths = changed_files(args.base)

    targets = build_targets(paths, regression=args.regression)

    if args.list:
        if paths:
            print("changed files:")
            for path in paths:
                print(f"  {path}")
        print("selected tests:")
        for target in targets:
            print(f"  {target}")

    cmd = build_command(targets, args.workers)
    print("$ " + shlex.join(cmd))

    if args.dry_run:
        return 0

    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
