"""Fast targeted test selector for Forge scientific changes.

This is a developer convenience gate, not a replacement for FAST, SCIENTIFIC
or hardened recertification. It never triggers GitHub workflows.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
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


#: pytest's default ``python_files`` -- the same rule tools/test_impact.is_test_module applies.
_TEST_FILE = re.compile(r"(?:test_[^/]*|[^/]*_test)\.py")


def changed_test_files(paths: Iterable[str]) -> list[str]:
    """Changed test modules that still exist, WHEREVER they live; a deleted test cannot be run.

    Hostile review F7: only root ``tests/`` used to count, so a changed provider-local or flagship
    test selected nothing at all.
    """
    out = []
    for p in sorted({_norm(p) for p in paths}):
        name = p.rsplit("/", 1)[-1]
        if _TEST_FILE.fullmatch(name) and not p.startswith(".forge/") and (ROOT / p).is_file():
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
    extra: Iterable[str] = (),
) -> list[str]:
    """Build the deterministic pytest command used by the developer/certification gate."""
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if workers:
        cmd += ["-n", str(workers), "--dist", "loadfile"]
    if junitxml:
        cmd += ["--junitxml", junitxml]
    for prefix in deselect:
        cmd += ["--deselect", prefix]
    cmd += list(extra)
    cmd += list(targets)
    return cmd


def _workers_arg(value: str) -> int | str:
    """An integer worker count, or ``safe-auto``."""
    if value == "safe-auto":
        return value
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer or 'safe-auto', got {value!r}") from None


def _report_impact(paths: list[str], *, with_expensive: bool,
                   details: dict | None = None) -> tuple[list[str], list[str], list[str]]:
    """``--changed`` only: the affected tests, the expensive ones left out, and unresolved paths -- printed.

    :mod:`tools.test_impact` is imported here and nowhere else, so the certified
    ``--regression`` path never loads it.
    """
    if str(ROOT) not in sys.path:  # run as a script, sys.path[0] is tools/, not the repository
        sys.path.insert(0, str(ROOT))
    from tools import test_impact

    graph = test_impact.build_graph(ROOT, cache=test_impact.default_cache_path(ROOT))
    impact = test_impact.impact_of(paths, graph)
    directly = set(changed_test_files(paths))
    reached = [m for m in impact.affected_modules if m not in directly]
    tiers = test_impact.load_tiers(ROOT)
    _, _, expensive = test_impact.split_by_tier(reached, tiers, graph.texts)
    if with_expensive:
        affected, deselect, left_out = reached, [], []
    else:
        affected, deselect, left_out = test_impact.split_by_tier(reached, tiers, graph.texts)
    if details is not None:
        details.update(
            classes=dict(impact.classes), reached=len(reached), expensive=list(expensive), left_out=list(left_out),
            narrowing=test_impact.scientific_narrowing(paths, impact),
            next_required=test_impact.next_required(paths, expensive_affected=len(expensive)),
        )

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
    parser.add_argument(
        "--workers",
        type=_workers_arg,
        default=None,
        help="pytest-xdist workers; 0 runs serially (the default, except --dev / --scientific: safe-auto); "
        "'safe-auto' picks 8/6/4/2/1 from CPUs and available memory (developer convenience, see tools/local_workers.py)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="one command after editing: --changed with safe-auto workers, a timing record outside the repository, "
        "and the gate still owed (developer aid; replaces nothing)",
    )
    parser.add_argument(
        "--scientific",
        action="store_true",
        help="developer aid: also run the affected expensive tests (SCIENTIFIC tier, not campaign) when the change "
        "can be narrowed; otherwise print the full SCIENTIFIC command. Never replaces the SCIENTIFIC tier",
    )
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
    if (args.dev or args.scientific) and args.regression:
        parser.error("--dev / --scientific select from changed files; they cannot be combined with --regression")
    if args.scientific:
        args.with_expensive = True
    if args.workers is None:
        args.workers = "safe-auto" if (args.dev or args.scientific) else 0

    if args.workers == "safe-auto":
        if str(ROOT) not in sys.path:  # run as a script, sys.path[0] is tools/, not the repository
            sys.path.insert(0, str(ROOT))
        from tools import local_workers

        per_worker = local_workers.MB_PER_WORKER_EXPENSIVE if args.with_expensive else local_workers.MB_PER_WORKER
        args.workers, reason = local_workers.choose(per_worker_mb=per_worker)
        print(f"safe-auto selected {args.workers} workers: {reason}")
    elif args.workers < 0:
        parser.error("--workers must be >= 0")

    paths: list[str] = []
    affected: list[str] = []
    deselect: list[str] = []
    unresolved: list[str] = []
    details: dict = {}
    if not args.regression:
        paths = changed_files(args.base, working_tree=not args.committed_only)
        affected, deselect, unresolved = _report_impact(paths, with_expensive=args.with_expensive, details=details)

    if args.scientific and details.get("narrowing"):
        print("selective SCIENTIFIC refused -- this change cannot be narrowed:")
        for reason in details["narrowing"]:
            print(f"  {reason}")
        print("run the whole SCIENTIFIC tier (docs/TESTING.md, Standard commands), e.g.:")
        print('  python -m pytest -m "not campaign" -q -n 4 --dist loadfile  (plus the CI deselects)')
        return 2

    targets = build_targets(paths, regression=args.regression, affected=affected, whole_pack=bool(unresolved))
    extra: list[str] = []
    if unresolved and not args.regression:
        # Hostile review F7: a change whose reach could not be established (a deleted module, a path no rule
        # reaches) is not narrowed at all -- a subset that passes would be a false negative. The whole tier runs.
        print("NARROWING REFUSED -- running the whole FAST tier (or SCIENTIFIC with --with-expensive), not a selection")
        targets, deselect = [], []
        extra += ["-m", "not campaign" if args.with_expensive else "not expensive"]
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

    if args.scientific and targets:
        extra += ["-m", "not campaign"]
    timing_report = None
    if args.dev and not args.dry_run:
        from tools import test_timing

        timing_report = test_timing.default_history_dir() / time.strftime("dev-%Y%m%dT%H%M%S.json", time.gmtime())
        extra += ["-p", "tools.test_timing", f"--timing-report={timing_report}"]
    cmd = build_command(targets, args.workers, junitxml=args.junitxml, deselect=deselect, extra=extra)
    print("$ " + shlex.join(cmd))

    if args.dry_run:
        if args.dev or args.scientific:
            _summary(details, targets, None, scientific=args.scientific)
        return 0

    code = subprocess.run(cmd, cwd=ROOT, check=False).returncode
    if args.dev or args.scientific:
        _summary(details, targets, code, scientific=args.scientific)
    if timing_report is not None:
        _timing_note(timing_report)
    return code


def _summary(details: dict, targets: list[str], code: int | None, *, scientific: bool) -> None:
    """The closing block of --dev / --scientific: what ran, and the gate still owed."""
    classes = details.get("classes", {})
    print("\n== forge_check summary (developer aid; replaces no gate) ==")
    order = ["certification_pinned", "trust_or_authority", "test_infrastructure", "unclassified", "scientific_shared",
             "domain_local", "local_nonscientific", "test_only", "doc_only"]
    present = sorted({c.value for c in classes.values()}, key=order.index)
    print(f"CHANGE CLASS: {', '.join(present) if present else 'no changed files'}")
    print(f"AFFECTED: {details.get('reached', 0)} test modules reached; {len(targets)} targets selected")
    run = "not run (dry run)" if code is None else ("PASS" if code == 0 else f"FAIL (exit {code})")
    print(f"RUN: {'selective SCIENTIFIC' if scientific else 'changed gate'} -> {run}")
    expensive = details.get("expensive", [])
    where = "run here" if scientific else f"{len(details.get('left_out', []))} not run"
    print(f"EXPENSIVE AFFECTED: {len(expensive)} ({where})")
    owed = details.get("next_required") or ()
    print(f"NEXT REQUIRED: {' + '.join(owed) if owed else 'none beyond this gate'}")


def _timing_note(report_path) -> None:
    """Compare this --dev run with the previous recorded one: a warning, never a failure."""
    from tools import test_timing

    reports = [p for p in test_timing.history(report_path.parent) if p != report_path]
    if not report_path.exists() or not reports:
        return
    try:
        found = test_timing.compare(test_timing._load(reports[-1]), test_timing._load(report_path))
    except (OSError, ValueError, SystemExit):
        return
    for line in found:
        print(f"timing warning (telemetry, not a result): {line}")


if __name__ == "__main__":
    raise SystemExit(main())
