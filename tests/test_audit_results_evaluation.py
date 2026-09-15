"""Audit stream "results": RES-06 -- an OK evaluation must carry a result it can stand on.

Written against the unfixed evaluation and seen failing first.

``ScientificEvaluation(status=OK)`` required only that a result be present. A DIVERGED, validation-FAILED result
whose model was assessed OUTSIDE its validated domain was an OK evaluation, both constructed and read back, and
``ScientificExperiment.best`` -- which filters on status alone -- would rank it. The objective values the ranking
reads were never compared with the result they claim to come from, so a result reporting 350 K could sit under an
OK evaluation whose objective of the same name said 1 K.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.validation import ValidationCheck, ValidationOutcome, ValidationReport
from engcore.scientific.solvers.protocol import ConvergenceState, SolverIdentity
from engcore.scientific.units.quantity import Quantity

MODEL = ModelReference("audit.evaluation.model", "1")
SOLVER = SolverIdentity("audit.evaluation.solver", "1")


def _result(
    *,
    convergence=ConvergenceState.CONVERGED,
    outcome=ValidationOutcome.PASS,
    status=ValidityStatus.IN_DOMAIN,
) -> ScientificResult:
    if status is ValidityStatus.IN_DOMAIN:
        assessment = ValidityAssessment(status=status, satisfied=("bound",))
    else:
        assessment = ValidityAssessment(status=status, violated=("bound",))
    return ScientificResult(
        result_id="evaluated",
        values={"T": Quantity(350.0, "K")},
        provenance=ProvenanceRecord(
            run_id="evaluated-run", bindings=(ExecutionBinding(model=MODEL, solver=SOLVER),)
        ),
        models=(MODEL.key,),
        solver=SOLVER,
        convergence=convergence,
        validation=ValidationReport(checks=(ValidationCheck(name="c", outcome=outcome),)),
        validity={MODEL.model_id: assessment},
    )


def _evaluation(result, *, status=EvaluationStatus.OK, objectives=None):
    return ScientificEvaluation(
        evaluation_id="e1",
        candidate={"x": Quantity(1.0, "m")},
        status=status,
        result=result,
        objective_values=objectives or {},
    )


def test_res06_the_control_is_accepted():
    evaluation = _evaluation(_result(), objectives={"T": Quantity(350.0, "K")})
    assert evaluation.status is EvaluationStatus.OK


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(dict(convergence=ConvergenceState.DIVERGED), id="diverged"),
        pytest.param(dict(outcome=ValidationOutcome.FAIL), id="validation-failed"),
        pytest.param(dict(status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN), id="outside-domain"),
    ],
)
def test_res06_ok_over_a_result_that_cannot_support_it_is_refused(result):
    with pytest.raises(ScientificCoreError, match="OK"):
        _evaluation(_result(**result))


def test_res06_the_probe_shape_is_refused_on_read_too():
    payload = json.loads(json.dumps(_evaluation(_result(), status=EvaluationStatus.NOT_CONVERGED).to_dict()))
    bad = _result(
        convergence=ConvergenceState.DIVERGED,
        outcome=ValidationOutcome.FAIL,
        status=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN,
    )
    payload["result"] = json.loads(json.dumps(bad.to_dict()))
    assert ScientificEvaluation.from_dict(payload).status is EvaluationStatus.NOT_CONVERGED
    payload["status"] = "ok"
    with pytest.raises(ScientificCoreError, match="OK"):
        ScientificEvaluation.from_dict(payload)


def test_res06_an_objective_that_contradicts_the_result_it_names_is_refused():
    with pytest.raises(ScientificCoreError, match="objective"):
        _evaluation(_result(), objectives={"T": Quantity(1.0, "K")})


def test_res06_an_objective_in_another_unit_that_agrees_is_accepted():
    evaluation = _evaluation(_result(), objectives={"T": Quantity(76.85, "degC")})
    assert evaluation.status is EvaluationStatus.OK


def test_res06_an_objective_of_the_wrong_dimension_is_refused():
    with pytest.raises(ScientificCoreError):
        _evaluation(_result(), objectives={"T": Quantity(350.0, "m")})


def test_res06_a_derived_objective_the_result_does_not_carry_is_not_cross_checked():
    evaluation = _evaluation(_result(), objectives={"cost": Quantity(3.0, "dimensionless")})
    assert evaluation.status is EvaluationStatus.OK


def test_res06_not_converged_may_still_carry_the_unusable_result():
    bad = _result(convergence=ConvergenceState.DIVERGED, outcome=ValidationOutcome.FAIL)
    assert _evaluation(bad, status=EvaluationStatus.NOT_CONVERGED).result is bad
