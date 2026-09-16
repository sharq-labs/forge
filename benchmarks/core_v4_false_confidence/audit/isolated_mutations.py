"""Run guard mutations in an ISOLATED copy of the tree, and count a kill only when a test actually failed.

This is the shared runner the re-audit batches use, and it exists because of R-67: the batch-1..5 runners
mutated the shared checkout in place -- restoring it in a ``finally``, but a crash or a Ctrl-C between the
write and the restore leaves a mutated source tree behind -- and they treated ANY non-zero pytest exit as
KILLED. Exit code 1 is "a test failed"; 2, 3, 4 and 5 are interrupted, internal error, usage error and
"no tests collected", and a collection or import error the mutation caused reads as a kill under the old
rule while proving nothing about the guard.

What a run does, per mutation:

1. copy ``src``, ``tests``, ``pyproject.toml`` and the JSON evidence the suites read into a fresh directory;
2. apply the mutation there, through ``tests.mutation_guards._apply``, which refuses a mutation that changes
   no executable token or breaks the parse;
3. collect the named test in the copy (``--collect-only``). A mutation that stops the test from being
   collected at all is reported COLLECTION_BROKEN, never KILLED;
4. run the named test. KILLED only when pytest exits 1 AND its summary reports at least one ``failed`` and
   no ``error``;
5. delete the copy. The checkout is never written to.

An unmutated control over the same tests runs last: a runner whose control is red says nothing at all.

Used as::

    from isolated_mutations import Mutation, run

    run([Mutation("B6a", "src/...py::scope", old, new, "tests/...py::test_name")],
        label="BATCH6", scratch=pathlib.Path(os.environ["SCRATCH"]))
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

#: What a copy needs to run the hybrid-UQ and audit suites: the package, the tests, the pytest configuration
#: and the committed JSON evidence the static guards read. Nothing else, and no ``__pycache__``.
_COPY_TREES = ("src", "tests")
_COPY_FILES = ("pyproject.toml",)
_COPY_GLOBS = ("benchmarks/core_v4_false_confidence/*.json", "benchmarks/core_v2_hybrid_uq/*.json")

_SUMMARY = re.compile(r"^=+ .*(passed|failed|error|no tests ran).* =+$|^\d+ (passed|failed|error)")


@dataclasses.dataclass(frozen=True)
class Mutation:
    """One guard, removed as if it had never been written, and the test that must notice."""

    id: str
    spec: str          # "path/to/file.py" or "path/to/file.py::Class.method"
    old: str
    new: str
    test: str          # "tests/....py::test_name", the ONE test whose failure counts as the kill
    note: str = ""
    #: What the run must report. "KILLED" for every real guard; "SURVIVED" only for a mutation kept on
    #: purpose to record that one rule of a disjunction is NOT on its own what protects an invariant. A
    #: mutation whose expectation is SURVIVED must say so here, and then a kill is the failure.
    expect: str = "KILLED"
    #: Further ``(spec, old, new)`` edits applied together with the first, for an invariant a DISJUNCTION of
    #: rules protects: there, removing any one rule leaves the invariant standing, and a single-edit mutation
    #: that SURVIVES says nothing about whether the invariant is load-bearing. Every edit must apply.
    also: tuple[tuple[str, str, str], ...] = ()

    @property
    def edits(self):
        return ((self.spec, self.old, self.new), *self.also)


def _populate(destination: pathlib.Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for tree in _COPY_TREES:
        shutil.copytree(ROOT / tree, destination / tree, ignore=ignore)
    for name in _COPY_FILES:
        shutil.copy2(ROOT / name, destination / name)
    for pattern in _COPY_GLOBS:
        for source in sorted(ROOT.glob(pattern)):
            target = destination / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _summary(done_or_text) -> str:
    """The last non-empty line of a run's output, stderr included: a usage error never reaches stdout."""
    text = done_or_text if isinstance(done_or_text, str) else (done_or_text.stdout + "\n" + done_or_text.stderr)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "(no output)"


def _pytest(work: pathlib.Path, arguments, scratch: pathlib.Path, tag: str):
    # basetemp lives OUTSIDE the copy: pytest clears its basetemp, and a basetemp inside the rootdir is a
    # usage error (exit 4), which the first run of this runner produced for every mutation and control alike.
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--runxfail",
         f"--basetemp={scratch / 'basetemp' / tag}", *arguments],
        cwd=work, capture_output=True, text=True, timeout=getattr(M, "TEST_TIMEOUT", 1800))


def _verdict(work: pathlib.Path, test: str, scratch: pathlib.Path, tag: str) -> tuple[str, str]:
    """``(verdict, summary)``. KILLED needs a collected test that then failed, and nothing else does."""
    collected = _pytest(work, ["--collect-only", test], scratch, tag + "_collect")
    if collected.returncode != 0:
        return "COLLECTION_BROKEN", _summary(collected)
    done = _pytest(work, [test], scratch, tag)
    summary = _summary(done)
    if done.returncode == 0:
        return "SURVIVED", summary
    if done.returncode != 1:
        # 2 interrupted, 3 internal error, 4 usage error, 5 nothing collected: not a test failure.
        return f"NOT_A_TEST_FAILURE(exit {done.returncode})", summary
    if "error" in summary or "failed" not in summary:
        return "NOT_A_TEST_FAILURE(no failure in the summary)", summary
    return "KILLED", summary


def run(mutations, *, label: str, scratch: pathlib.Path, log: pathlib.Path | None = None) -> int:
    """Run every mutation in its own copy, then an unmutated control. Returns a process exit code."""
    scratch.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def say(text: str) -> None:
        print(text, flush=True)
        lines.append(text)

    unacceptable = 0
    for mutation in mutations:
        work = scratch / f"{label.lower()}_{mutation.id}"
        if work.exists():
            shutil.rmtree(work)
        try:
            _populate(work)
            digests, refused = [], None
            for spec, old_text, new_text in mutation.edits:
                applied = M._apply(work, spec, old_text, new_text)
                if isinstance(applied, str):
                    refused = f"{spec} -> {applied}"
                    break
                digests.append(applied)
            if refused is not None:
                say(f"{mutation.id} {refused}")
                unacceptable += 1
                continue
            before = "+".join(d[0] for d in digests)
            after = "+".join(d[1] for d in digests)
            verdict, summary = _verdict(work, mutation.test, scratch, f"{label.lower()}_{mutation.id}")
            mismatch = "" if verdict == mutation.expect else f"  <-- EXPECTED {mutation.expect}"
            say(f"{mutation.id} {mutation.test.split('::')[-1]} -> {verdict}{mismatch} | {summary} | "
                f"code {before}->{after}" + (f" | {mutation.note}" if mutation.note else ""))
            if mismatch:
                unacceptable += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)

    control = scratch / f"{label.lower()}_control"
    if control.exists():
        shutil.rmtree(control)
    try:
        _populate(control)
        tests = sorted({m.test for m in mutations})
        done = _pytest(control, tests, scratch, f"{label.lower()}_control")
        say(f"CONTROL (unmutated, {len(tests)} test(s)) "
            f"{'GREEN' if done.returncode == 0 else 'RED'} | {_summary(done)}")
        if done.returncode != 0:
            unacceptable += 1
    finally:
        shutil.rmtree(control, ignore_errors=True)

    assert not (ROOT / "src" / "engcore" / "hybrid_uq" / "router.py.orig").exists()
    if log is not None:
        log.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {log}", flush=True)
    return 0 if unacceptable == 0 else 1


def scratch_from_environment() -> pathlib.Path:
    return pathlib.Path(os.environ.get("SCRATCH") or (ROOT / ".mutation-scratch"))
