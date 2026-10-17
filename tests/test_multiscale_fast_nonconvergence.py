"""Opt-in macro-window rejection on numerical non-convergence of a fast execution (ERT V1, Big Rock 9).

With ``retry_fast_nonconvergence`` a fast execution that raises
``FastExecutionNotConverged`` (or a coupled fast run's
``CouplingWindowNotConverged``) rejects the macro window within the existing
divisor / minimum-window / rejection bounds and is recorded; without the flag
the run is refused exactly as before; any other refusal is never retried.
NOT YET EXECUTED (build phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import importlib.util
import pathlib
from dataclasses import replace

import pytest

from engcore.execution.multiphysics import CouplingWindowNotConverged
from engcore.multiscale import MultiTimescaleRuntime
from engcore.multiscale.fast import FastExecutionNotConverged
from engcore.scientific.errors import InvalidScientificProblem

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("multiscale_reference", str(HERE / "multiscale_reference.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def _failing_system(failures: int, error=FastExecutionNotConverged):
    class FailingFirst(R.ReferenceHeaterSystem):
        """The reference system, whose first ``failures`` executions fail with ``error``."""

        remaining = failures

        def execute(self, request):
            if type(self).remaining > 0:
                type(self).remaining -= 1
                raise error("synthetic fast solve failure (test)")
            return super().execute(request)

    return FailingFirst


def _runtime(system_cls, *, retry: bool, days=14):
    env = R.build_environment(days)[0]
    system = system_cls(env)
    policy = replace(R.policy(default_days=7, minimum_days=1, near_threshold=False), retry_fast_nonconvergence=retry)
    return MultiTimescaleRuntime(run_id=f"fast-nc-{retry}", hierarchy=R.hierarchy(), policy=policy, fast_system=system,
                                 environment=env, aggregations=R.aggregations(), lifecycle=R.lifecycle())


def test_policy_flag_is_absent_from_existing_policy_identity():
    base = R.policy()
    assert "retry_fast_nonconvergence" not in base.to_dict()
    flagged = replace(base, retry_fast_nonconvergence=True)
    assert flagged.to_dict()["retry_fast_nonconvergence"] is True and flagged.digest != base.digest


def test_policy_flag_must_be_a_bool():
    with pytest.raises(InvalidScientificProblem):
        replace(R.policy(), retry_fast_nonconvergence="yes")


def test_without_the_flag_a_fast_non_convergence_refuses_the_run_as_before():
    record = _runtime(_failing_system(1), retry=False).run(initial_slow_state=R.initial_slow())
    assert record.status == "refused" and "synthetic fast solve failure" in record.reason
    assert record.steps == ()


@pytest.mark.parametrize("error", [FastExecutionNotConverged, CouplingWindowNotConverged])
def test_with_the_flag_the_macro_window_is_rejected_halved_and_recorded(error):
    record = _runtime(_failing_system(1, error), retry=True).run(initial_slow_state=R.initial_slow())
    assert record.status == "completed", record.reason
    first = record.steps[0]
    kinds = [(r.kind, r.subject) for r in first.refinements]
    assert ("fast_nonconvergence", "fast_execution") in kinds
    # 7-day default window halved by the declared divisor (2)
    assert float(first.window.end.seconds - first.window.start.seconds) == pytest.approx(3.5 * 86400)
    assert any(r.kind == "fast_nonconvergence" and error.__name__ in r.detail for r in first.refinements)


def test_retry_stays_within_the_declared_rejection_bound():
    # far more failures than max_rejections_per_step (12) or the minimum window allow
    record = _runtime(_failing_system(1000), retry=True).run(initial_slow_state=R.initial_slow())
    assert record.status == "refused"
    assert "minimum macro window" in record.reason or "maximum number of rejections" in record.reason


def test_a_refusal_that_is_not_numerical_is_never_retried():
    record = _runtime(_failing_system(1, InvalidScientificProblem), retry=True).run(initial_slow_state=R.initial_slow())
    assert record.status == "refused" and record.steps == ()


def test_fast_non_convergence_adds_no_accounting_counter():
    record = _runtime(_failing_system(1), retry=True).run(initial_slow_state=R.initial_slow())
    assert set(record.accounting) == set(_runtime(R.ReferenceHeaterSystem, retry=False).run(
        initial_slow_state=R.initial_slow()).accounting)
