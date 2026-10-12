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
    "tests/test_capability_completion.py",
)

ALL_SCIENTIFIC_TAGS = frozenset({
    "verdict", "evidence", "vnv", "applicability", "compiler", "selection",
    "context", "uq", "policy", "external", "gaps", "challenge", "replay",
    "provenance", "diagnostics", "equation_ir", "knowledge",
})


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# (path prefix, tags) rules for scientific source. A path is *classified* when
# at least one prefix matches it. ``src/engcore/claims/`` selects everything.
_PREFIX_TAGS: tuple[tuple[str, frozenset[str]], ...] = (
    ("src/engcore/claims/", ALL_SCIENTIFIC_TAGS),
    ("src/engcore/credibility/", frozenset({"verdict", "evidence", "context", "uq", "external", "vnv", "diagnostics", "provenance", "replay"})),
    ("src/engcore/sria/", frozenset({"verdict", "evidence", "context", "policy", "uq", "external", "diagnostics"})),
    ("src/engcore/mcp/", frozenset({"verdict", "evidence", "context"})),
    ("src/engcore/domains/", frozenset({"verdict", "evidence", "applicability", "uq", "challenge"})),
    ("src/engcore/domainpacks/", frozenset({"selection", "context", "evidence", "provenance"})),
    ("src/engcore/scientific/results/", frozenset({"verdict", "vnv", "uq", "provenance", "diagnostics"})),
    ("src/engcore/scientific/models/", frozenset({"applicability", "compiler", "selection"})),
    ("src/engcore/scientific/equations/", frozenset({"equation_ir", "compiler", "applicability", "diagnostics", "provenance", "replay"})),
    ("src/engcore/scientific/knowledge/", frozenset({"knowledge", "evidence", "provenance", "replay", "applicability", "diagnostics", "policy"})),
    ("src/engcore/credibility/knowledge_evidence.py", frozenset({"knowledge", "evidence", "provenance", "replay", "applicability", "diagnostics"})),
    ("src/engcore/uq/", frozenset({"uq", "verdict", "diagnostics"})),
    ("src/engcore/hybrid_uq/", frozenset({"uq", "verdict", "diagnostics"})),
    ("src/engcore/scientific/validation_core/", frozenset({"verdict", "vnv", "applicability", "uq", "evidence", "diagnostics"})),
    ("src/engcore/scientific/replay_core/", frozenset({"replay", "provenance", "diagnostics"})),
    ("src/engcore/credibility/evidence_graph/", frozenset({"evidence", "provenance", "external", "diagnostics"})),
    ("src/engcore/scientific/verification/", frozenset({"vnv", "evidence", "provenance", "diagnostics"})),
    ("src/engcore/execution/orchestration/", frozenset({"vnv", "replay", "diagnostics"})),
    ("src/engcore/scientific/certification_core/", frozenset({"vnv", "replay", "provenance", "policy", "diagnostics"})),
    ("src/engcore/scientific/assurance_flow/", frozenset({"verdict", "vnv", "evidence", "replay", "provenance", "diagnostics"})),
)

# Files that change how every test runs or which cases exist. A change to one
# of them cannot be narrowed to a subset of the regression pack.
CONSERVATIVE_FILES = frozenset({
    "pyproject.toml",
    "tests/conftest.py",
    "tests/scientific_regression/manifest.json",
    "tools/forge_check.py",
})


def _norm(path: str) -> str:
    return str(path).replace("\\", "/")


def unclassified_paths(paths: Iterable[str]) -> list[str]:
    """Changed paths whose scientific reach this selector cannot narrow.

    A file under ``src/engcore/`` that no rule maps, and the files that
    configure every test run. Each one selects the whole regression pack: a
    developer gate must not report a narrow selection as if it covered them.
    """
    out = []
    for p in sorted({_norm(p) for p in paths}):
        if p in CONSERVATIVE_FILES:
            out.append(p)
        elif p.startswith("src/engcore/") and not any(p.startswith(prefix) for prefix, _ in _PREFIX_TAGS):
            out.append(p)
    return out


def tags_for_paths(paths: Iterable[str]) -> set[str]:
    paths = {_norm(p) for p in paths}
    if unclassified_paths(paths):
        return set(ALL_SCIENTIFIC_TAGS)
    tags: set[str] = set()
    for prefix, rule_tags in _PREFIX_TAGS:
        if any(p.startswith(prefix) for p in paths):
            tags |= rule_tags
    return tags


def changed_test_files(paths: Iterable[str]) -> list[str]:
    """Changed test modules that still exist; a deleted test cannot be run."""
    out = []
    for p in sorted({_norm(p) for p in paths}):
        name = p.rsplit("/", 1)[-1]
        if p.startswith("tests/") and name.startswith("test_") and name.endswith(".py") and (ROOT / p).is_file():
            out.append(p)
    return out


def cases_for_tags(tags: set[str]) -> list[str]:
    data = load_manifest()
    nodeids: list[str] = []
    for case in data["cases"]:
        if tags.intersection(case["tags"]):
            nodeids.append(case["nodeid"])
    return nodeids


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed:\n{proc.stderr.strip()}\n"
            "Pass --base <ref> naming a locally available base ref."
        )
    return proc.stdout


def _name_status_paths(output: str) -> list[str]:
    """Every path a ``--name-status`` listing names: both sides of a rename or copy."""
    paths = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and fields[0].strip():
            paths.extend(f.strip() for f in fields[1:] if f.strip())
    return paths


def changed_files(base: str, *, working_tree: bool = True) -> list[str]:
    """Paths changed since the merge base with ``base``.

    Committed changes (``base...HEAD``) always count. With ``working_tree``
    (the default) staged, unstaged and untracked files count too, so an
    uncommitted edit is never silently left out of the selection. Deleted
    files and both names of a rename are reported: a deletion or a move can
    change behaviour as much as an edit.
    """
    paths = _name_status_paths(_git("diff", "--name-status", "-M", f"{base}...HEAD"))
    if working_tree:
        paths += _name_status_paths(_git("diff", "--name-status", "-M", "HEAD"))
        paths += [line.strip() for line in _git("ls-files", "--others", "--exclude-standard").splitlines() if line.strip()]
    return sorted(set(paths))


def build_targets(paths: Iterable[str], *, regression: bool = False) -> list[str]:
    targets = list(ARCHITECTURE_TESTS)
    if regression:
        targets.extend(case["nodeid"] for case in load_manifest()["cases"])
    else:
        paths = list(paths)
        tags = tags_for_paths(paths)
        targets.extend(cases_for_tags(tags))
        targets.extend(changed_test_files(paths))

    # Stable order, no duplicate node IDs.
    return list(dict.fromkeys(targets))


def build_command(
    targets: Iterable[str],
    workers: int,
    *,
    junitxml: str | None = None,
) -> list[str]:
    """Build the deterministic pytest command used by the developer/certification gate."""
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if workers:
        cmd += ["-n", str(workers), "--dist", "loadfile"]
    if junitxml:
        cmd += ["--junitxml", junitxml]
    cmd += list(targets)
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--changed", action="store_true", help="select tests from changed files (default)")
    mode.add_argument("--regression", action="store_true", help="run the complete fixed scientific regression pack")
    parser.add_argument("--base", default=os.environ.get("FORGE_BASE", "main"), help="base ref for --changed")
    parser.add_argument(
        "--committed-only",
        action="store_true",
        help="--changed: consider only commits since the merge base, not staged, unstaged or untracked files",
    )
    parser.add_argument("--workers", type=int, default=0, help="pytest-xdist workers; 0 runs serially")
    parser.add_argument(
        "--junitxml",
        default=None,
        help="write pytest JUnit XML evidence to this path (used by certification)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print selection without executing pytest")
    parser.add_argument("--list", action="store_true", help="print selected test targets")
    args = parser.parse_args(argv)

    if args.workers < 0:
        parser.error("--workers must be >= 0")

    paths: list[str] = []
    if not args.regression:
        paths = changed_files(args.base, working_tree=not args.committed_only)

    targets = build_targets(paths, regression=args.regression)
    unclassified = [] if args.regression else unclassified_paths(paths)
    if unclassified:
        print("unclassified changes select the whole regression pack:")
        for path in unclassified:
            print(f"  {path}")

    if args.list:
        if paths:
            print("changed files:")
            for path in paths:
                print(f"  {path}")
        print("selected tests:")
        for target in targets:
            print(f"  {target}")

    cmd = build_command(targets, args.workers, junitxml=args.junitxml)
    print("$ " + shlex.join(cmd))

    if args.dry_run:
        return 0

    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
