"""RES-07: a TrustedExecutionRecord is built from parts that belong together.

The audit (probe ``agentA/r6_trusted.py``) constructed a record directly from an
admission for ``never-admitted``, a ``PreparedSolve`` with no problem and another
solver, a DIVERGED raw output, and a manifest for a different problem and a
third solver -- and ``record.trusted`` was True, because the property returned
True "by construction" and the constructor checked only the parts' types.

The rule these tests pin: the constructor verifies that the admission, the
prepared solve, the raw output and the manifest describe one execution -- the
same problem (id and content digest), the same solver, the same settings, the
same raw output and the admitted realization -- and ``trusted`` is False for an
output that did not converge or a validation that failed.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.execution.trusted import TrustedExecutionRecord, TrustedExecutionRuntime
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.results.execution_manifest import ExecutionManifest
from engcore.scientific.results.validation import ValidationCheck, ValidationOutcome, ValidationReport
from engcore.scientific.solvers.protocol import ConvergenceState, RawSolverOutput, SolverIdentity
from tests.test_trusted_execution_runtime import _RuntimeSolver, _model, _problem, _realization


def _record(**solver_kwargs):
    model = _model()
    return TrustedExecutionRuntime().run(
        problem=_problem(model), model=model, realization=_realization(model),
        solver=_RuntimeSolver(model, **solver_kwargs),
    )


def _parts(record):
    return dict(admission=record.admission, prepared=record.prepared, raw=record.raw,
                metrics=dict(record.metrics), validation=record.validation, manifest=record.manifest)


def test_the_runtime_record_is_trusted_and_rebuilds():
    record = _record()
    assert record.trusted
    assert TrustedExecutionRecord(**_parts(record)).trusted


def test_probe_an_admission_for_another_problem_is_refused():
    record = _record()
    parts = _parts(record)
    parts["admission"] = dataclasses.replace(record.admission, problem_id="never-admitted")
    with pytest.raises(ScientificCoreError, match="admission"):
        TrustedExecutionRecord(**parts)


def test_probe_an_admission_for_another_solver_is_refused():
    record = _record()
    parts = _parts(record)
    parts["admission"] = dataclasses.replace(record.admission, solver_key=("other_solver", "9"))
    with pytest.raises(ScientificCoreError, match="admission"):
        TrustedExecutionRecord(**parts)


def test_probe_a_prepared_solve_without_a_problem_is_refused():
    record = _record()
    parts = _parts(record)
    parts["prepared"] = dataclasses.replace(record.prepared, problem=None)
    with pytest.raises(ScientificCoreError, match="problem"):
        TrustedExecutionRecord(**parts)


@pytest.mark.parametrize(
    "field, value",
    [
        ("problem_id", "a-different-problem"),
        ("problem_digest", "0" * 64),
        ("solver", SolverIdentity("third_solver", "1")),
        ("settings_digest", "1" * 64),
        ("raw_output_digest", "2" * 64),
        ("realization_id", "another.realization@1"),
    ],
)
def test_probe_a_manifest_of_another_execution_is_refused(field, value):
    record = _record()
    parts = _parts(record)
    parts["manifest"] = dataclasses.replace(record.manifest, **{field: value})
    with pytest.raises(ScientificCoreError, match="manifest"):
        TrustedExecutionRecord(**parts)


def test_a_raw_output_the_manifest_does_not_attest_is_refused():
    record = _record()
    parts = _parts(record)
    parts["raw"] = RawSolverOutput(convergence=ConvergenceState.CONVERGED, values={"answer": 3.0})
    with pytest.raises(ScientificCoreError, match="manifest"):
        TrustedExecutionRecord(**parts)


@pytest.mark.parametrize(
    "state", [ConvergenceState.DIVERGED, ConvergenceState.FAILED, ConvergenceState.NOT_CONVERGED,
              ConvergenceState.MAX_ITERATIONS],
)
def test_probe_a_non_converged_output_is_not_trusted(state):
    record = _record()
    parts = _parts(record)
    raw = RawSolverOutput(convergence=state)
    parts["raw"] = raw
    parts["manifest"] = ExecutionManifest.from_execution(
        record.prepared, raw, realization_id=record.manifest.realization_id
    )
    assert TrustedExecutionRecord(**parts).trusted is False


def test_a_failed_validation_is_not_trusted():
    record = _record()
    parts = _parts(record)
    parts["validation"] = ValidationReport(checks=(ValidationCheck("kcl", ValidationOutcome.FAIL),))
    assert TrustedExecutionRecord(**parts).trusted is False
