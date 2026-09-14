"""Fail-closed admission across model claim, realization, solver and problem.

The repository already has strong declarations at each layer:

* a scientific model declares typed inputs/outputs and computational
  ``required_capabilities``;
* a realization points at one exact model, declares scientific capabilities it
  provides/requires, and solver capabilities it needs;
* a solver declares solver capabilities and (through ``DeclaredSupport``) which
  model/problem requests it serves;
* a problem names models and capabilities it asks to execute.

Before this module those declarations were checked mostly *within* their own
layer.  A caller could therefore assemble individually-valid records whose
links were incompatible and discover the mismatch in ``prepare`` or later.
This module makes the links one admission decision.  It does not infer missing
science and it does not mutate the problem to make a mismatch disappear.

``ScientificCapability`` and ``SolverCapability`` remain deliberately separate.
The former answers which science a realization supplies or consumes; the
latter answers which computation a backend can execute.  Admission checks both
sets but never equates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from ..capabilities import ScientificCapability, scientific_capabilities
from ..errors import ScientificCoreError
from ..ir.problem import ScientificProblem
from ..models.definition import ScientificModelDefinition
from ..solvers.capability import capability_names
from ..solvers.protocol import DeclaredSupport, ScientificSolver
from .definition import ModelRealizationDefinition


class AdmissionIssueKind(str, Enum):
    MODEL_NOT_REQUESTED = "model_not_requested"
    REALIZATION_MODEL_MISMATCH = "realization_model_mismatch"
    MODEL_BINDING = "model_binding"
    PROBLEM_UNDERDECLARES_MODEL_CAPABILITY = "problem_underdeclares_model_capability"
    SOLVER_CAPABILITY_GAP = "solver_capability_gap"
    SOLVER_SUPPORT_REFUSAL = "solver_support_refusal"
    SCIENTIFIC_CAPABILITY_GAP = "scientific_capability_gap"


@dataclass(frozen=True)
class AdmissionIssue:
    kind: AdmissionIssueKind
    subject: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", AdmissionIssueKind(self.kind))
        subject = str(self.subject).strip()
        detail = str(self.detail).strip()
        if not subject or not detail:
            raise ScientificCoreError("execution-admission issues require subject and detail")
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "detail", detail)


@dataclass(frozen=True)
class ExecutionAdmissionReport:
    """Deterministic explanation of whether one execution stack is coherent."""

    problem_id: str
    model_key: tuple[str, str]
    realization_key: tuple[str, str]
    solver_key: tuple[str, str]
    issues: tuple[AdmissionIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "problem_id", str(self.problem_id))
        object.__setattr__(self, "model_key", tuple(self.model_key))
        object.__setattr__(self, "realization_key", tuple(self.realization_key))
        object.__setattr__(self, "solver_key", tuple(self.solver_key))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def admitted(self) -> bool:
        return not self.issues

    def of_kind(self, kind: AdmissionIssueKind) -> tuple[AdmissionIssue, ...]:
        wanted = AdmissionIssueKind(kind)
        return tuple(issue for issue in self.issues if issue.kind is wanted)

    def require(self) -> None:
        """Raise once, with every incompatibility, instead of failing piecemeal later."""
        if self.admitted:
            return
        reasons = "; ".join(
            f"{issue.kind.value}:{issue.subject}: {issue.detail}"
            for issue in self.issues
        )
        raise ScientificCoreError(
            f"execution stack for problem {self.problem_id!r} is not admissible: {reasons}"
        )


def assess_execution_admission(
    *,
    problem: ScientificProblem,
    model: ScientificModelDefinition,
    realization: ModelRealizationDefinition,
    solver: ScientificSolver,
    available_scientific_capabilities: Iterable[ScientificCapability | str] = (),
) -> ExecutionAdmissionReport:
    """Check every cross-layer promise required before ``prepare`` may be trusted.

    No selection or inference occurs here.  The caller chose the model,
    realization and solver; admission only asks whether those choices satisfy
    the declarations they already made.
    """
    if not isinstance(problem, ScientificProblem):
        raise TypeError("problem must be a ScientificProblem")
    if not isinstance(model, ScientificModelDefinition):
        raise TypeError("model must be a ScientificModelDefinition")
    if not isinstance(realization, ModelRealizationDefinition):
        raise TypeError("realization must be a ModelRealizationDefinition")

    identity = getattr(solver, "identity", None)
    capabilities = getattr(solver, "capabilities", None)
    if identity is None or capabilities is None:
        raise TypeError("solver must satisfy the ScientificSolver declaration surface")

    issues: list[AdmissionIssue] = []

    # Exact identity, including version.  A problem asking for model@2 must not
    # be admitted through a realization of model@1 merely because the id matches.
    requested_model_keys = {reference.key for reference in problem.models}
    if model.key not in requested_model_keys:
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.MODEL_NOT_REQUESTED,
                f"{model.model_id}@{model.version}",
                f"problem names {sorted(requested_model_keys) or 'no models'}, not this exact model",
            )
        )

    if realization.model_key != model.key:
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.REALIZATION_MODEL_MISMATCH,
                f"{realization.realization_id}@{realization.version}",
                f"realizes {realization.model_key[0]}@{realization.model_key[1]}, not {model.model_id}@{model.version}",
            )
        )

    binding = model.check_against(problem)
    for issue in binding.issues:
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.MODEL_BINDING,
                issue.name,
                f"{issue.kind.value}: {issue.detail}",
            )
        )

    # ``ScientificModelDefinition.required_capabilities`` predates the
    # realization layer and contains solver/computational capability names.
    # A problem that names the model but omits those requirements weakens what
    # the solver registry sees.  Refuse rather than silently augment the request.
    model_solver_requirements = frozenset(model.required_capabilities)
    problem_solver_requirements = frozenset(problem.required_capabilities)
    undeclared_by_problem = sorted(model_solver_requirements - problem_solver_requirements)
    for name in undeclared_by_problem:
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.PROBLEM_UNDERDECLARES_MODEL_CAPABILITY,
                name,
                "the selected model requires this computational capability but the problem does not request it",
            )
        )

    solver_declared = capability_names(capabilities)
    realization_solver_requirements = frozenset(
        capability.name for capability in realization.required_solver_capabilities
    )
    required_by_stack = model_solver_requirements | realization_solver_requirements
    missing_solver = sorted(required_by_stack - solver_declared)
    for name in missing_solver:
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.SOLVER_CAPABILITY_GAP,
                name,
                f"model/realization requires it; solver declares {sorted(solver_declared)}",
            )
        )

    # Use the central support contract when available.  This catches served
    # model, serves-capability, and domain-specific support constraints that a
    # raw set-subtraction cannot express.
    if isinstance(solver, DeclaredSupport):
        for reason in solver.support_gap(problem):
            issues.append(
                AdmissionIssue(
                    AdmissionIssueKind.SOLVER_SUPPORT_REFUSAL,
                    f"{identity.solver_id}@{identity.version}",
                    reason,
                )
            )
    elif not solver.supports(problem):
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.SOLVER_SUPPORT_REFUSAL,
                f"{identity.solver_id}@{identity.version}",
                "solver.supports(problem) returned false",
            )
        )

    available_science = scientific_capabilities(available_scientific_capabilities)
    missing_science = sorted(
        realization.required_capabilities - available_science,
        key=lambda capability: capability.identifier,
    )
    for capability in missing_science:
        issues.append(
            AdmissionIssue(
                AdmissionIssueKind.SCIENTIFIC_CAPABILITY_GAP,
                capability.identifier,
                "the realization requires this scientific capability from the composed system, but it was not supplied",
            )
        )

    return ExecutionAdmissionReport(
        problem_id=problem.problem_id,
        model_key=model.key,
        realization_key=realization.key,
        solver_key=identity.key,
        issues=tuple(issues),
    )


def require_execution_admission(**kwargs) -> ExecutionAdmissionReport:
    """Assess, raise on any gap, and return the admitted report."""
    report = assess_execution_admission(**kwargs)
    report.require()
    return report


__all__ = [
    "AdmissionIssue",
    "AdmissionIssueKind",
    "ExecutionAdmissionReport",
    "assess_execution_admission",
    "require_execution_admission",
]
