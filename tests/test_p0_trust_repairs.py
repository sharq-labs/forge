"""Regression tests for fail-closed P0 trust-boundary repairs."""

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ModelReference, ScientificProblem
from engcore.scientific.models.definition import ValidityAssessment, ValidityStatus
from engcore.scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.solvers.protocol import DeclaredSupport, SolverIdentity
from engcore.scientific.units.quantity import Quantity


MODEL_V1 = ModelReference("trust.model", "1")
MODEL_V2 = ModelReference("trust.model", "2")
SOLVER = SolverIdentity("trust.solver", "1")
OTHER_SOLVER = SolverIdentity("other.solver", "1")


class _VersionedDummySolver(DeclaredSupport):
    served_models = (MODEL_V1,)
    serves_capabilities = frozenset()
    capabilities = frozenset()


def _validity(status: ValidityStatus) -> ValidityAssessment:
    if status is ValidityStatus.IN_DOMAIN:
        return ValidityAssessment(status=status, satisfied=("declared-range",))
    if status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN:
        return ValidityAssessment(status=status, violated=("declared-range",))
    return ValidityAssessment(status=status)


def _result(
    *,
    model: ModelReference = MODEL_V1,
    provenance: ProvenanceRecord | None = None,
    solver: SolverIdentity | None = SOLVER,
    validity: ValidityStatus | None = ValidityStatus.IN_DOMAIN,
) -> ScientificResult:
    provenance = provenance or ProvenanceRecord(
        run_id="trust-run",
        models=(model.key,),
        solvers=(() if solver is None else (solver.key,)),
    )
    validity_kwargs = {}
    if validity is None:
        validity_kwargs["validity_not_assessed"] = {
            model.model_id: "not assessed in this regression fixture"
        }
    else:
        validity_kwargs["validity"] = {model.model_id: _validity(validity)}
    return ScientificResult(
        result_id="trust-result",
        values={"y": Quantity(1.0, "dimensionless")},
        provenance=provenance,
        models=(model.key,),
        solver=solver,
        **validity_kwargs,
    )


def test_result_is_usable_only_when_every_declared_model_is_in_domain():
    assert _result(validity=ValidityStatus.IN_DOMAIN).is_usable is True
    assert _result(validity=ValidityStatus.OUTSIDE_VALIDATED_DOMAIN).is_usable is False
    assert _result(validity=ValidityStatus.UNKNOWN).is_usable is False
    assert _result(validity=None).is_usable is False


def test_solver_support_is_model_version_aware():
    solver = _VersionedDummySolver()
    assert solver.supports(ScientificProblem(problem_id="v1", models=(MODEL_V1,))) is True
    mismatch = ScientificProblem(problem_id="v2", models=(MODEL_V2,))
    assert solver.supports(mismatch) is False
    gap = " ".join(solver.support_gap(mismatch))
    assert "trust.model@2" in gap
    assert "trust.model@1" in gap


def test_result_refuses_a_model_not_named_by_provenance():
    provenance = ProvenanceRecord(
        run_id="wrong-model",
        models=(MODEL_V2.key,),
        solvers=(SOLVER.key,),
    )
    with pytest.raises(ScientificCoreError, match="provenance does not name"):
        _result(model=MODEL_V1, provenance=provenance)


def test_result_refuses_a_solver_not_named_by_provenance():
    provenance = ProvenanceRecord(
        run_id="wrong-solver",
        models=(MODEL_V1.key,),
        solvers=(OTHER_SOLVER.key,),
    )
    with pytest.raises(ScientificCoreError, match="provenance does not name that solver"):
        _result(provenance=provenance, solver=SOLVER)


def test_result_binding_must_connect_its_solver_to_one_of_its_models():
    provenance = ProvenanceRecord(
        run_id="unbound-result-model",
        models=(MODEL_V1.key, MODEL_V2.key),
        bindings=(ExecutionBinding(model=MODEL_V1, solver=SOLVER),),
    )
    with pytest.raises(ScientificCoreError, match="no provenance execution binding connects"):
        _result(model=MODEL_V2, provenance=provenance, solver=SOLVER)
