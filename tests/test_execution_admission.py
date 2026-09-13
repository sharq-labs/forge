"""Cross-layer claim/capability admission must fail before execution."""

from __future__ import annotations

import pytest

from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ModelReference, ScientificProblem
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.realizations.admission import (
    AdmissionIssueKind,
    assess_execution_admission,
    require_execution_admission,
)
from engcore.scientific.realizations.definition import (
    ModelFormulation,
    ModelRealizationDefinition,
)
from engcore.scientific.solvers.capability import SolverCapability, SolverCapabilityId
from engcore.scientific.solvers.protocol import DeclaredSupport, SolverIdentity


class _Solver(DeclaredSupport):
    serves_capabilities = frozenset({"core:algebraic"})

    def __init__(
        self,
        *,
        capabilities=("core:algebraic",),
        served_model: ModelReference | None = None,
    ) -> None:
        self._capabilities = frozenset(SolverCapability(name) for name in capabilities)
        self.served_models = (served_model,) if served_model is not None else ()

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity("test_solver", "1", backend="python")

    @property
    def capabilities(self):
        return self._capabilities


def _model(*, version: str = "1") -> ScientificModelDefinition:
    return ScientificModelDefinition(
        model_id="physics.model",
        version=version,
        exclusions=("does not model secondary physics",),
        required_capabilities=frozenset({"core:algebraic"}),
    )


def _realization(
    model: ScientificModelDefinition,
    *,
    model_version: str | None = None,
    requires_science=(),
) -> ModelRealizationDefinition:
    return ModelRealizationDefinition(
        realization_id="physics.model.closed_form",
        version="1",
        model=ModelReference(model.model_id, model_version or model.version),
        formulation=ModelFormulation.ALGEBRAIC,
        provided_capabilities=frozenset({"physics:evaluate"}),
        required_capabilities=frozenset(requires_science),
        required_solver_capabilities=frozenset({SolverCapabilityId("core:algebraic")}),
    )


def _problem(model: ScientificModelDefinition, *, capabilities=("core:algebraic",)):
    return ScientificProblem(
        problem_id="case",
        models=(ModelReference(model.model_id, model.version),),
        required_capabilities=frozenset(capabilities),
    )


def _solver(model: ScientificModelDefinition, *, capabilities=("core:algebraic",)):
    return _Solver(
        capabilities=capabilities,
        served_model=ModelReference(model.model_id, model.version),
    )


def test_coherent_model_realization_solver_problem_stack_is_admitted():
    model = _model()
    report = assess_execution_admission(
        problem=_problem(model),
        model=model,
        realization=_realization(model),
        solver=_solver(model),
    )
    assert report.admitted
    assert report.issues == ()
    assert require_execution_admission(
        problem=_problem(model),
        model=model,
        realization=_realization(model),
        solver=_solver(model),
    ) == report


def test_problem_must_name_the_exact_model_version_selected():
    model = _model(version="2")
    problem = ScientificProblem(
        problem_id="case",
        models=(ModelReference(model.model_id, "1"),),
        required_capabilities=frozenset({"core:algebraic"}),
    )
    report = assess_execution_admission(
        problem=problem,
        model=model,
        realization=_realization(model),
        solver=_solver(model),
    )
    assert report.of_kind(AdmissionIssueKind.MODEL_NOT_REQUESTED)


def test_realization_cannot_silently_compute_another_model_version():
    model = _model(version="2")
    report = assess_execution_admission(
        problem=_problem(model),
        model=model,
        realization=_realization(model, model_version="1"),
        solver=_solver(model),
    )
    assert report.of_kind(AdmissionIssueKind.REALIZATION_MODEL_MISMATCH)


def test_problem_cannot_weaken_a_models_computational_requirements():
    model = _model()
    report = assess_execution_admission(
        problem=_problem(model, capabilities=()),
        model=model,
        realization=_realization(model),
        solver=_solver(model),
    )
    gaps = report.of_kind(AdmissionIssueKind.PROBLEM_UNDERDECLARES_MODEL_CAPABILITY)
    assert [gap.subject for gap in gaps] == ["core:algebraic"]


def test_solver_must_cover_requirements_of_both_model_and_realization():
    model = _model()
    report = assess_execution_admission(
        problem=_problem(model),
        model=model,
        realization=_realization(model),
        solver=_solver(model, capabilities=("core:ode",)),
    )
    gaps = report.of_kind(AdmissionIssueKind.SOLVER_CAPABILITY_GAP)
    assert [gap.subject for gap in gaps] == ["core:algebraic"]
    assert report.of_kind(AdmissionIssueKind.SOLVER_SUPPORT_REFUSAL)


def test_realization_scientific_dependencies_are_not_equated_with_solver_caps():
    model = _model()
    realization = _realization(model, requires_science=("material:conductivity",))
    missing = assess_execution_admission(
        problem=_problem(model),
        model=model,
        realization=realization,
        solver=_solver(model),
    )
    gaps = missing.of_kind(AdmissionIssueKind.SCIENTIFIC_CAPABILITY_GAP)
    assert [gap.subject for gap in gaps] == ["material:conductivity"]

    supplied = assess_execution_admission(
        problem=_problem(model),
        model=model,
        realization=realization,
        solver=_solver(model),
        available_scientific_capabilities=("material:conductivity",),
    )
    assert supplied.admitted


def test_require_gate_reports_all_cross_layer_failures_together():
    model = _model(version="2")
    problem = ScientificProblem(problem_id="case")
    realization = _realization(
        model, model_version="1", requires_science=("material:conductivity",)
    )
    solver = _Solver(capabilities=("core:ode",))

    report = assess_execution_admission(
        problem=problem,
        model=model,
        realization=realization,
        solver=solver,
    )
    kinds = {issue.kind for issue in report.issues}
    assert AdmissionIssueKind.MODEL_NOT_REQUESTED in kinds
    assert AdmissionIssueKind.REALIZATION_MODEL_MISMATCH in kinds
    assert AdmissionIssueKind.PROBLEM_UNDERDECLARES_MODEL_CAPABILITY in kinds
    assert AdmissionIssueKind.SOLVER_CAPABILITY_GAP in kinds
    assert AdmissionIssueKind.SOLVER_SUPPORT_REFUSAL in kinds
    assert AdmissionIssueKind.SCIENTIFIC_CAPABILITY_GAP in kinds

    with pytest.raises(ScientificCoreError, match="not admissible"):
        report.require()
