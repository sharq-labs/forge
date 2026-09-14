"""The trusted runtime must make admission/attestation impossible to skip."""

from __future__ import annotations

import pytest

from engcore.execution.trusted import TrustedExecutionRuntime
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.ir.problem import ModelReference, ScientificProblem
from engcore.scientific.models.definition import ScientificModelDefinition
from engcore.scientific.realizations.definition import (
    ModelFormulation,
    ModelRealizationDefinition,
)
from engcore.scientific.results.validation import ValidationReport
from engcore.scientific.solvers.capability import SolverCapability, SolverCapabilityId
from engcore.scientific.solvers.protocol import (
    ConvergenceState,
    DeclaredSupport,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from engcore.scientific.units.quantity import Quantity


class _RuntimeSolver(DeclaredSupport):
    serves_capabilities = frozenset({"core:algebraic"})

    def __init__(
        self,
        model: ScientificModelDefinition,
        *,
        prepared_problem: ScientificProblem | None = None,
        prepared_identity: SolverIdentity | None = None,
        artifacts: tuple[str, ...] = (),
        metric_value=Quantity(2.0, "volt"),
    ) -> None:
        self.served_models = (ModelReference(model.model_id, model.version),)
        self._prepared_problem = prepared_problem
        self._prepared_identity = prepared_identity
        self._artifacts = artifacts
        self._metric_value = metric_value
        self.calls: list[str] = []

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity("runtime.test", "1", backend="python")

    @property
    def capabilities(self):
        return frozenset({SolverCapability("core:algebraic")})

    def prepare(self, problem: ScientificProblem) -> PreparedSolve:
        self.calls.append("prepare")
        return PreparedSolve(
            problem=self._prepared_problem or problem,
            solver=self._prepared_identity or self.identity,
            settings=SolverSettings(options={"route": "unit-test"}),
            payload={"assembled": True},
            notes=("prepared by unit test",),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        self.calls.append("solve")
        return RawSolverOutput(
            convergence=ConvergenceState.CONVERGED,
            values={"answer": 2.0},
            artifacts=self._artifacts,
        )

    def extract_metrics(self, prepared: PreparedSolve, raw: RawSolverOutput):
        self.calls.append("extract")
        return {"answer": self._metric_value}

    def validate(self, prepared: PreparedSolve, raw: RawSolverOutput):
        self.calls.append("validate")
        return ValidationReport()


def _model() -> ScientificModelDefinition:
    return ScientificModelDefinition(
        model_id="demo.algebraic",
        version="1",
        exclusions=("not a general physical model",),
        required_capabilities=frozenset({"core:algebraic"}),
    )


def _problem(model: ScientificModelDefinition) -> ScientificProblem:
    return ScientificProblem(
        problem_id="case-1",
        models=(ModelReference(model.model_id, model.version),),
        required_capabilities=frozenset({"core:algebraic"}),
    )


def _realization(model: ScientificModelDefinition) -> ModelRealizationDefinition:
    return ModelRealizationDefinition(
        realization_id="demo.algebraic.closed_form",
        version="1",
        model=ModelReference(model.model_id, model.version),
        formulation=ModelFormulation.ALGEBRAIC,
        provided_capabilities=frozenset({"demo:evaluate"}),
        required_solver_capabilities=frozenset({SolverCapabilityId("core:algebraic")}),
    )


def test_coherent_stack_returns_one_attested_trusted_record():
    model = _model()
    problem = _problem(model)
    realization = _realization(model)
    solver = _RuntimeSolver(model)

    record = TrustedExecutionRuntime().run(
        problem=problem,
        model=model,
        realization=realization,
        solver=solver,
        prepared_payload_encoder=lambda prepared: b"canonical-prepared-payload",
        environment={"python": "3.12", "image": "sha256:test"},
    )

    assert record.trusted
    assert record.admission.admitted
    assert record.metrics["answer"] == Quantity(2.0, "volt")
    assert record.manifest.coverage == "control_plane+prepared_payload"
    assert record.manifest.realization_id == "demo.algebraic.closed_form@1"
    assert solver.calls == ["prepare", "solve", "extract", "validate"]


def test_failed_admission_prevents_prepare_and_solve():
    model = _model()
    # Deliberately omit the capability the selected model requires.
    problem = ScientificProblem(
        problem_id="case-1",
        models=(ModelReference(model.model_id, model.version),),
    )
    solver = _RuntimeSolver(model)

    with pytest.raises(ScientificCoreError, match="not admissible"):
        TrustedExecutionRuntime().run(
            problem=problem,
            model=model,
            realization=_realization(model),
            solver=solver,
        )
    assert solver.calls == []


def test_prepare_cannot_switch_the_admitted_problem_before_solve():
    model = _model()
    problem = _problem(model)
    replacement = ScientificProblem(
        problem_id=problem.problem_id,
        models=problem.models,
        required_capabilities=problem.required_capabilities,
        metadata={"silently": "changed"},
    )
    solver = _RuntimeSolver(model, prepared_problem=replacement)

    with pytest.raises(ScientificCoreError, match="changed or replaced"):
        TrustedExecutionRuntime().run(
            problem=problem,
            model=model,
            realization=_realization(model),
            solver=solver,
        )
    assert solver.calls == ["prepare"]


def test_prepare_cannot_switch_solver_identity_before_solve():
    model = _model()
    problem = _problem(model)
    solver = _RuntimeSolver(
        model,
        prepared_identity=SolverIdentity("different.solver", "9", backend="other"),
    )

    with pytest.raises(ScientificCoreError, match="identity does not match"):
        TrustedExecutionRuntime().run(
            problem=problem,
            model=model,
            realization=_realization(model),
            solver=solver,
        )
    assert solver.calls == ["prepare"]


def test_declared_artifact_without_byte_resolver_never_becomes_trusted():
    model = _model()
    solver = _RuntimeSolver(model, artifacts=("report.bin",))

    with pytest.raises(ScientificCoreError, match="no artifact_resolver"):
        TrustedExecutionRuntime().run(
            problem=_problem(model),
            model=model,
            realization=_realization(model),
            solver=solver,
        )
    # Attestation fails before derived metrics/validation can make the solve
    # look more complete than its evidence actually is.
    assert solver.calls == ["prepare", "solve"]


def test_artifact_resolver_must_cover_exactly_what_raw_output_declared():
    model = _model()
    solver = _RuntimeSolver(model, artifacts=("report.bin",))

    with pytest.raises(ScientificCoreError, match="missing=.*report.bin"):
        TrustedExecutionRuntime().run(
            problem=_problem(model),
            model=model,
            realization=_realization(model),
            solver=solver,
            artifact_resolver=lambda prepared, raw: {},
        )


def test_artifact_bytes_are_bound_into_the_returned_manifest():
    model = _model()
    solver = _RuntimeSolver(model, artifacts=("report.bin",))
    record = TrustedExecutionRuntime().run(
        problem=_problem(model),
        model=model,
        realization=_realization(model),
        solver=solver,
        artifact_resolver=lambda prepared, raw: {"report.bin": b"evidence-bytes"},
    )
    assert [artifact.name for artifact in record.manifest.artifacts] == ["report.bin"]
    assert len(record.manifest.artifacts[0].digest) == 64


def test_prepared_payload_encoder_must_return_explicit_bytes():
    model = _model()
    solver = _RuntimeSolver(model)
    with pytest.raises(ScientificCoreError, match="must return bytes"):
        TrustedExecutionRuntime().run(
            problem=_problem(model),
            model=model,
            realization=_realization(model),
            solver=solver,
            prepared_payload_encoder=lambda prepared: "implicit repr",  # type: ignore[return-value]
        )
    assert solver.calls == ["prepare", "solve"]


def test_raw_float_cannot_cross_the_metric_boundary_in_a_trusted_record():
    model = _model()
    solver = _RuntimeSolver(model, metric_value=2.0)
    with pytest.raises(ScientificCoreError, match="not a Quantity"):
        TrustedExecutionRuntime().run(
            problem=_problem(model),
            model=model,
            realization=_realization(model),
            solver=solver,
        )
    assert solver.calls == ["prepare", "solve", "extract", "validate"]
