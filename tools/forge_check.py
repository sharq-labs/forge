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
    "tools/test_impact.py",
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


def build_targets(
    paths: Iterable[str],
    *,
    regression: bool = False,
    affected: Iterable[str] = (),
    whole_pack: bool = False,
) -> list[str]:
    """Guards, then sentinels, then changed tests, then affected tests -- stable, without duplicates.

    ``affected`` comes from :mod:`tools.test_impact` in ``--changed`` mode only;
    ``whole_pack`` is set when a change's reach could not be established.
    """
    targets = list(ARCHITECTURE_TESTS)
    if regression or whole_pack:
        targets.extend(case["nodeid"] for case in load_manifest()["cases"])
    if not regression:
        paths = list(paths)
        if not whole_pack:
            targets.extend(cases_for_tags(tags_for_paths(paths)))
        targets.extend(changed_test_files(paths))
        targets.extend(affected)

    # Stable order, no duplicate node IDs, and no node ID inside a module that is
    # itself selected whole (pytest would run that test twice).
    targets = list(dict.fromkeys(targets))
    whole = {t for t in targets if "::" not in t}
    return [t for t in targets if "::" not in t or t.split("::", 1)[0] not in whole]


def build_command(
    targets: Iterable[str],
    workers: int,
    *,
    junitxml: str | None = None,
    deselect: Iterable[str] = (),
) -> list[str]:
    """Build the deterministic pytest command used by the developer/certification gate."""
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if workers:
        cmd += ["-n", str(workers), "--dist", "loadfile"]
    if junitxml:
        cmd += ["--junitxml", junitxml]
    for prefix in deselect:
        cmd += ["--deselect", prefix]
    cmd += list(targets)
    return cmd


def _report_impact(paths: list[str], *, with_expensive: bool) -> tuple[list[str], list[str], list[str]]:
    """``--changed`` only: the affected tests, the expensive ones left out, and unresolved paths -- printed.

    :mod:`tools.test_impact` is imported here and nowhere else, so the certified
    ``--regression`` path never loads it.
    """
    if str(ROOT) not in sys.path:  # run as a script, sys.path[0] is tools/, not the repository
        sys.path.insert(0, str(ROOT))
    from tools import test_impact

    graph = test_impact.build_graph(ROOT)
    impact = test_impact.impact_of(paths, graph)
    directly = set(changed_test_files(paths))
    reached = [m for m in impact.affected_modules if m not in directly]
    if with_expensive:
        affected, deselect, left_out = reached, [], []
    else:
        affected, deselect, left_out = test_impact.split_by_tier(reached, test_impact.load_tiers(ROOT), graph.texts)

    if paths:
        print("change classes (minimum gate beyond this one):")
        for path, cls in sorted(impact.classes.items()):
            print(f"  {cls.value:<22} {path} -- {test_impact.MINIMUM_GATE[cls]}")
        pinned = {p: test_impact.recertification_reasons(p) for p in paths}
        pinned = {p: r for p, r in pinned.items() if r}
        if pinned:
            print("RECERTIFICATION_REQUIRED (owner-run; this gate does not replace it):")
            for path, reasons in sorted(pinned.items()):
                print(f"  {path}: {', '.join(reasons)}")
    if reached:
        print(f"affected test modules: {len(reached)} reached by import, mention or source scan")
    if left_out:
        print("affected expensive tests NOT run here -- run SCIENTIFIC, or pass --with-expensive:")
        for item in left_out:
            print(f"  {item}")
    if impact.unresolved:
        print("changes whose reach could not be established select the whole regression pack:")
        for path in impact.unresolved:
            print(f"  {path}")
    return affected, deselect, list(impact.unresolved)


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
        "--with-expensive",
        action="store_true",
        help="--changed: also run affected tests marked expensive (by default they are listed, not run)",
    )
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
    affected: list[str] = []
    deselect: list[str] = []
    unresolved: list[str] = []
    if not args.regression:
        paths = changed_files(args.base, working_tree=not args.committed_only)
        affected, deselect, unresolved = _report_impact(paths, with_expensive=args.with_expensive)

    targets = build_targets(paths, regression=args.regression, affected=affected, whole_pack=bool(unresolved))
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

    cmd = build_command(targets, args.workers, junitxml=args.junitxml, deselect=deselect)
    print("$ " + shlex.join(cmd))

    if args.dry_run:
        return 0

    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
