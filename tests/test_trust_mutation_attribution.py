"""The trust-hardening mutation runner credits only attributed kills.

Main audit CERT-04. The runner used to count any pytest exit code 1 as KILLED,
with no unmutated control and no link between the mutation and the test that
guards it. A suite that already failed for an unrelated reason would have
"killed" every mutant, including the ones deciding CROSS_SOLVER_VALIDATED.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "_trust_mutation_runner", ROOT / "benchmarks" / "trust_hardening" / "audit" / "mutations.py"
)
runner = importlib.util.module_from_spec(_SPEC)
# dataclasses resolve string annotations through sys.modules[cls.__module__].
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)

SUITE = runner.TESTS[0]


def _mutation(expect: str = "") -> "runner.Mutation":
    return runner.Mutation("TRUST-X", "src/engcore/x.py", "a", "b", "p", expect=expect)


def test_exit_zero_is_a_survivor():
    assert runner.classify(_mutation(), 0, "")[0] == "SURVIVED"


def test_an_exit_code_without_a_failed_test_is_not_a_kill():
    status, reason = runner.classify(_mutation(), 1, "1 error in 0.1s\n")
    assert status == "INVALID"
    assert "no FAILED test" in reason


def test_a_failure_outside_the_declared_suites_is_not_a_kill():
    output = "FAILED tests/test_unrelated.py::test_other - AssertionError\n"
    assert runner.classify(_mutation(), 1, output)[0] == "INVALID"


def test_a_failure_of_another_test_is_not_the_guard():
    output = f"FAILED {SUITE}::test_something_else - AssertionError\n"
    status, reason = runner.classify(_mutation(expect="test_the_guard"), 1, output)
    assert status == "INVALID"
    assert "NOT THE GUARD" in reason


def test_the_named_guard_failing_is_a_kill():
    output = f"FAILED {SUITE}::test_the_guard - AssertionError\n"
    assert runner.classify(_mutation(expect="test_the_guard"), 1, output) == ("KILLED", "")


@pytest.mark.parametrize("code", [2, 3, 4, 5, 86, 87, None])
def test_infrastructure_exit_codes_are_never_kills(code):
    assert runner.classify(_mutation(), code, f"FAILED {SUITE}::test_x\n")[0] == "INVALID"


def test_every_trust_mutation_names_the_test_that_guards_it():
    """Attribution is only as good as the declared expectation."""
    missing = [m.mutation_id for m in runner.MUTATIONS if not m.expect]
    assert missing == []
