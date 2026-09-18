"""The certified runner for the V4 guard-mutation population: one isolated copy, one named test (R-67).

    python -m tools.certification.mutation_v4_runner --scratch DIR [--index I --count N] [--ids FILE]

WHAT THIS MODULE IS FOR
-----------------------
The re-audit's finding 97: the batch runners mutated the shared checkout in place and treated ANY
non-zero pytest exit as KILLED. Exit 1 is "a test failed"; 2, 3, 4 and 5 are interrupted, internal
error, usage error and "no tests collected" -- and a mutation that breaks an import makes the target
module fail to collect, which under that rule was credited to the guard as a kill while proving
nothing about it.

So a kill here is one thing only: **the test the entry names failed.** Not "something failed", and
not "pytest exited non-zero". The run is done with ``--junitxml`` and the verdict is read from the
XML, because the nodeid is IN the XML: a terminal summary line proves that a failure happened, never
whose. :func:`verdict_from_junit` is that rule as a pure function of the report and the nodeid, so it
can be read -- and tested -- without running anything.

WHAT A ROUND DOES, PER ENTRY
----------------------------
1. copy the tree into a fresh directory OUTSIDE the repository (:func:`require_an_isolated_tree`
   refuses anything else, including the repository itself and any path inside it);
2. apply every edit through ``tests.mutation_guards._apply``, which refuses a mutation that changes
   no executable token or breaks the parse;
3. run ONLY the entry's target test in the copy, with a JUnit report;
4. classify with :func:`verdict_from_junit` and compare against the entry's declared expectation;
5. delete the copy. The checkout is never written to.

An unmutated control over the round's target tests runs last. A round whose control is not green
says nothing at all and is reported as a failed round.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Iterable, Sequence

#: What a copy needs to run the population's target suites: the package, the tests, the experiment
#: configurations some audit suites import, the pytest configuration, the certification helpers a few
#: guards read, and the committed JSON evidence the static guards compare against. Carried over from
#: the round's own runner, where each entry was added because a copy without it turned a CONTROL red
#: for a reason having nothing to do with any mutation.
COPY_TREES = ("src", "tests", "experiments", "tools", "certification")
COPY_FILES = ("pyproject.toml",)
COPY_GLOBS = ("benchmarks/core_v4_false_confidence/*.json", "benchmarks/core_v2_hybrid_uq/*.json")

#: Generous on purpose, and for the harness's own reason: a timeout is an absence of evidence and is
#: reported as one, so a tight budget buys nothing but mutations nobody checked.
TEST_TIMEOUT = 1800


class MutationRoundError(RuntimeError):
    """The round cannot produce evidence: not the same as a mutation surviving."""


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------
def _nodeid_of(case: ET.Element) -> str:
    """The pytest nodeid a JUnit ``<testcase>`` came from, as ``file::name``.

    pytest's default JUnit family writes ``classname`` as the dotted module (plus any class) and NO
    ``file`` attribute, so the path is rebuilt from it when that is all there is: the dotted parts up
    to the first class-looking name are the module path, and any class names belong to the nodeid's
    tail. This mattered immediately -- the first round read every real report as NOT_COLLECTED while
    the tests failed, which is the same shape of wrong answer as the audited rule and in the safe
    direction.

    A collection error is reported as a ``<testcase>`` whose ``name`` is the FILE and whose
    ``classname`` is empty; it therefore cannot equal a test's nodeid, which is exactly wanted.
    """
    path = (case.get("file") or "").replace("\\", "/")
    name = case.get("name") or ""
    if not path:
        parts = [part for part in (case.get("classname") or "").split(".") if part]
        classes: list[str] = []
        while parts and parts[-1][:1].isupper():
            classes.insert(0, parts.pop())
        path = "/".join(parts) + ".py" if parts else ""
        name = "::".join([*classes, name])
    return f"{path}::{name}"


def verdict_from_junit(report: str | bytes, nodeid: str) -> str:
    """The round's verdict for one mutation, read from the JUnit report of its own test.

    ``KILLED`` when the named nodeid is present and carries a ``<failure>``; ``SURVIVED`` when it is
    present and carries neither a failure nor an error. Everything else is named rather than
    counted:

    * ``NOT_COLLECTED`` -- the named test is not in the report at all, which is what a mutation that
      breaks an import looks like. Under the audited rule this was a kill;
    * ``ERRORED`` -- the named test is in the report and raised outside its own body (a fixture, a
      collection error), which is not the guard firing;
    * ``SKIPPED`` -- the run did not exercise the guard.

    A report that is not XML is ``REPORT_UNREADABLE``: a round cannot be scored on it.
    """
    text = report.decode("utf-8", "replace") if isinstance(report, bytes) else report
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return f"REPORT_UNREADABLE({exc})"
    wanted = nodeid.replace("\\", "/")
    for case in root.iter("testcase"):
        if _nodeid_of(case) != wanted:
            continue
        if case.find("failure") is not None:
            return "KILLED"
        if case.find("error") is not None:
            return "ERRORED"
        if case.find("skipped") is not None:
            return "SKIPPED"
        return "SURVIVED"
    return "NOT_COLLECTED"


def require_an_isolated_tree(root: pathlib.Path, work: pathlib.Path) -> None:
    """Refuse a work tree that is the repository, or anywhere inside it.

    Finding 97's other half. The batch-1..5 runners wrote the mutation into the checkout and restored
    it in a ``finally``: a crash or a Ctrl-C between the write and the restore leaves a mutated source
    tree behind, and every later run in that tree measures the wrong bytes without saying so.
    """
    root = pathlib.Path(root).resolve()
    work = pathlib.Path(work).resolve()
    if work == root or root in work.parents:
        raise MutationRoundError(
            f"{work} is inside the repository at {root}: a mutation is applied to an isolated copy, "
            f"never to the checkout, so that a round interrupted between the edit and the restore "
            f"cannot leave a mutated source tree behind")


# ---------------------------------------------------------------------------
# a round
# ---------------------------------------------------------------------------
def populate(root: pathlib.Path, destination: pathlib.Path) -> None:
    """A faithful copy: everything a target suite reads, and nothing stale."""
    require_an_isolated_tree(root, destination)
    destination.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for tree in COPY_TREES:
        shutil.copytree(root / tree, destination / tree, ignore=ignore)
    for name in COPY_FILES:
        shutil.copy2(root / name, destination / name)
    for pattern in COPY_GLOBS:
        for source in sorted(root.glob(pattern)):
            target = destination / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _pytest(work: pathlib.Path, arguments: Sequence[str], scratch: pathlib.Path, tag: str):
    # basetemp lives OUTSIDE the copy: pytest clears its basetemp, and a basetemp inside the rootdir
    # is a usage error (exit 4) rather than a test result.
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--runxfail",
         f"--junitxml={scratch / 'junit' / (tag + '.xml')}",
         f"--basetemp={scratch / 'basetemp' / tag}", *arguments],
        cwd=work, capture_output=True, text=True, timeout=TEST_TIMEOUT)


def run_one(root: pathlib.Path, entry: Sequence, scratch: pathlib.Path) -> tuple[str, str]:
    """``(verdict, one-line summary)`` for one population entry, in its own copy of the tree."""
    import mutation_guards as mg  # noqa: PLC0415 - the pinned harness applies the edit

    mid, spec, old, new, test, _expect, _note, also, _source = entry
    work = scratch / f"mut_{mid}"
    junit = scratch / "junit" / f"mut_{mid}.xml"
    if work.exists():
        shutil.rmtree(work)
    try:
        populate(root, work)
        for target_spec, target_old, target_new in ((spec, old, new), *tuple(also)):
            applied = mg._apply(work, target_spec, target_old, target_new)
            if isinstance(applied, str):
                return f"NOT_APPLIED({target_spec} -> {applied})", "no run"
        done = _pytest(work, [test], scratch, f"mut_{mid}")
        if not junit.is_file():
            return "NO_REPORT", f"pytest exited {done.returncode} and wrote no report"
        verdict = verdict_from_junit(junit.read_bytes(), test)
        lines = [line.strip() for line in (done.stdout + "\n" + done.stderr).splitlines() if line.strip()]
        return verdict, lines[-1] if lines else "(no output)"
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f"no verdict after {TEST_TIMEOUT}s, which is an absence of evidence"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def control_is_green(root: pathlib.Path, tests: Iterable[str], scratch: pathlib.Path) -> tuple[bool, str]:
    """Run the round's target tests unmutated. A round whose control is red says nothing at all."""
    work = scratch / "control"
    if work.exists():
        shutil.rmtree(work)
    try:
        populate(root, work)
        done = _pytest(work, sorted(set(tests)), scratch, "control")
        lines = [line.strip() for line in (done.stdout + "\n" + done.stderr).splitlines() if line.strip()]
        return done.returncode == 0, lines[-1] if lines else "(no output)"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def round_lines(root: pathlib.Path, entries: Sequence[Sequence], scratch: pathlib.Path,
                *, say=print) -> tuple[list[str], int]:
    """Run every entry, then the control. Returns ``(transcript lines, count of wrong verdicts)``."""
    lines: list[str] = []

    def record(text: str) -> None:
        say(text, flush=True) if say is print else say(text)
        lines.append(text)

    wrong = 0
    for entry in entries:
        mid, _spec, _old, _new, test, expect, note, _also, _source = entry
        verdict, summary = run_one(root, entry, scratch)
        mismatch = "" if verdict == expect else f"  <-- EXPECTED {expect}"
        record(f"{mid} {test.split('::')[-1]} -> {verdict}{mismatch} | {summary}"
               + (f" | {note}" if note else ""))
        if mismatch:
            wrong += 1
    green, summary = control_is_green(root, [e[4] for e in entries], scratch)
    record(f"CONTROL (unmutated, {len({e[4] for e in entries})} test(s)) "
           f"{'GREEN' if green else 'RED'} | {summary}")
    if not green:
        wrong += 1
    return lines, wrong


def _root() -> pathlib.Path:
    from tools.certification.core_certificate import repo_root

    return repo_root(pathlib.Path.cwd() / "x")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--scratch", required=True, help="a directory OUTSIDE the repository")
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--ids", default=None, help="a file of ids, one per line, instead of a shard")
    parser.add_argument("--log", default=None)
    args = parser.parse_args(argv)
    root = _root()
    sys.path.insert(0, str(root / "tests"))
    from tools.certification.mutation_population import v4_entries, v4_population

    entries = {entry[0]: entry for entry in v4_entries(root)}
    if args.ids:
        wanted = [line.strip() for line in pathlib.Path(args.ids).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
    elif args.index is not None and args.count is not None:
        wanted = list(v4_population(root).shard(args.index, args.count))
    else:
        wanted = list(entries)
    unknown = [mid for mid in wanted if mid not in entries]
    if unknown:
        print(f"MUTATION ROUND PROBLEM: ids outside the population: {unknown}", file=sys.stderr)
        return 1
    # NOT_MUTATED entries were excluded by the batch that declared them and are excluded here, with
    # their reason printed: a reader of the transcript should not have to wonder why they are absent.
    selected = []
    lines: list[str] = []
    for mid in wanted:
        entry = entries[mid]
        if entry[5] == "NOT_MUTATED":
            lines.append(f"NOT MUTATED: {mid} -- {entry[6]}")
            print(lines[-1], flush=True)
            continue
        selected.append(entry)
    scratch = pathlib.Path(args.scratch).resolve()
    try:
        require_an_isolated_tree(root, scratch)
    except MutationRoundError as exc:
        print(f"MUTATION ROUND PROBLEM: {exc}", file=sys.stderr)
        return 1
    scratch.mkdir(parents=True, exist_ok=True)
    ran, wrong = round_lines(root, selected, scratch)
    lines += ran
    if args.log:
        pathlib.Path(args.log).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.log}", flush=True)
    print(f"{len(selected) - wrong}/{len(selected)} entries reached their declared verdict", flush=True)
    return 1 if wrong else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
