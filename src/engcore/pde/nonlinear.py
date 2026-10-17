"""Nonlinear PDE execution: the admission contract a provider must meet (Phase 3 BR17, part A).

STATUS: contract only.  No Forge operator template is nonlinear
(:data:`NONLINEAR_TEMPLATES` is empty) and no provider in the repository
implements a nonlinear PDE solve (``forge_fenicsx`` assembles the four linear
templates of :mod:`.contracts` with a KSP solve).  Adding a nonlinear template
-- e.g. temperature-dependent conductivity -- is a new scientific capability
foundation under the active-epic policy and waits for an owner decision.
What exists here is what such a provider would be held to, so a later adapter
cannot define its own notion of convergence:

* the governing-equation class is a Forge template, never caller code
  (:func:`require_nonlinear_template` refuses everything today);
* the Newton-type method is declared in full (:class:`NonlinearSolveSpec`):
  absolute AND relative residual tolerances, iteration budget, line search,
  Jacobian kind -- nothing defaulted;
* the initial guess is a declared, sourced value or a provenance-carrying
  field on the problem's own mesh (:class:`InitialGuess`); "zero" is never
  assumed, and an initial guess is never evidence about the solution;
* convergence is re-derived from the recorded per-step Newton histories
  (:func:`admit_nonlinear_execution`): a record claiming CONVERGED whose
  histories do not meet the declared test is refused as false convergence; a
  failed record must expose no fields (``PDEExecutionRecord`` already
  enforces it).

A converged Newton solve establishes only that the discrete residual met the
declared test at each step: not uniqueness (a nonlinear problem may have
several solutions), not discretization accuracy, not model validity.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.solvers.protocol import ConvergenceState
from ..spatial import Location, Rank, SpatialField
from .contracts import OperatorTemplate, PDEProblem, PDERefusal, SourcedQuantity

#: Forge operator templates whose weak form is nonlinear in the unknown.  EMPTY: no
#: nonlinear template is authorized (owner decision OD-P3-3).
NONLINEAR_TEMPLATES: Mapping[str, OperatorTemplate] = {}

NONLINEAR_METHODS = ("newton", "newton_backtracking")
JACOBIAN_KINDS = ("exact_linearization", "finite_difference")


def require_nonlinear_template(template: OperatorTemplate) -> OperatorTemplate:
    """The template, if it is an authorized nonlinear Forge template; refused otherwise (all, today)."""
    if template.template_id not in NONLINEAR_TEMPLATES or NONLINEAR_TEMPLATES[template.template_id] != template:
        raise PDERefusal(
            f"operator {template.template_id!r} is not an authorized nonlinear Forge template; no nonlinear PDE "
            f"template exists (owner decision OD-P3-3: a nonlinear template is a new capability foundation)"
        )
    return template


@dataclass(frozen=True)
class NonlinearSolveSpec:
    """The declared Newton-type method.  Every acceptance-relevant value is explicit."""

    method: str
    residual_atol: float
    residual_rtol: float
    max_iterations: int
    jacobian: str
    max_backtracks: int = 0
    armijo_c1: float | None = None

    def __post_init__(self) -> None:
        if self.method not in NONLINEAR_METHODS:
            raise PDERefusal(f"nonlinear method must be one of {NONLINEAR_METHODS}")
        if self.jacobian not in JACOBIAN_KINDS:
            raise PDERefusal(f"jacobian must be one of {JACOBIAN_KINDS}")
        for label in ("residual_atol", "residual_rtol"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise PDERefusal(f"{label} must be a finite non-negative number")
        if self.residual_atol == 0.0 and self.residual_rtol == 0.0:
            raise PDERefusal("residual_atol and residual_rtol cannot both be zero: no finite iteration meets that test")
        if isinstance(self.max_iterations, bool) or not isinstance(self.max_iterations, int) or not 1 <= self.max_iterations <= 1000:
            raise PDERefusal("max_iterations must be an int in [1, 1000]")
        if self.method == "newton_backtracking":
            if isinstance(self.max_backtracks, bool) or not isinstance(self.max_backtracks, int) or not 1 <= self.max_backtracks <= 60:
                raise PDERefusal("newton_backtracking requires max_backtracks in [1, 60]")
            c1 = self.armijo_c1
            if isinstance(c1, bool) or not isinstance(c1, (int, float)) or not 0.0 < float(c1) < 0.5:
                raise PDERefusal("newton_backtracking requires armijo_c1 in (0, 0.5)")
        elif self.max_backtracks != 0 or self.armijo_c1 is not None:
            raise PDERefusal("line-search settings apply to newton_backtracking only")

    def accepts(self, initial: float, final: float) -> bool:
        """The declared test: ``final <= max(atol, rtol * initial)``."""
        return math.isfinite(final) and final <= max(self.residual_atol, self.residual_rtol * initial)

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "residual_atol": self.residual_atol, "residual_rtol": self.residual_rtol,
                "max_iterations": self.max_iterations, "jacobian": self.jacobian, "max_backtracks": self.max_backtracks,
                "armijo_c1": self.armijo_c1}


@dataclass(frozen=True)
class InitialGuess:
    """Where the Newton iteration starts: a sourced constant, or a provenance-carrying node field on the problem mesh."""

    constant: SourcedQuantity | None = None
    field: SpatialField | None = None

    def __post_init__(self) -> None:
        if (self.constant is None) == (self.field is None):
            raise PDERefusal("an initial guess is exactly one of a sourced constant or a field; none is assumed")
        if self.field is not None:
            if not self.field.provenance:
                raise PDERefusal("an initial-guess field without provenance is an anonymous field; refused")
            if self.field.definition.location is not Location.NODE:
                raise PDERefusal("an initial-guess field must be a node field (the unknown's location)")

    def check_against(self, problem: PDEProblem) -> None:
        """The guess must live on the problem's mesh, in the unknown's rank and dimension."""
        from ..scientific.units.quantity import dimensionality

        unit = problem.operator.unknown_unit
        if self.field is not None:
            if self.field.mesh.digest != problem.mesh.digest:
                raise PDERefusal("the initial-guess field is on another mesh; map it first")
            if self.field.definition.rank is not problem.unknown.rank:
                raise PDERefusal("the initial-guess field has another rank than the unknown")
            if dimensionality(self.field.definition.unit) != dimensionality(unit):
                raise PDERefusal("the initial-guess field has another dimension than the unknown")
        else:
            if problem.unknown.rank is not Rank.SCALAR:
                raise PDERefusal("a constant initial guess is defined for scalar unknowns only")
            if dimensionality(self.constant.value.units) != dimensionality(unit):
                raise PDERefusal("the constant initial guess has another dimension than the unknown")

    def to_dict(self) -> dict[str, Any]:
        return {"constant": None if self.constant is None else self.constant.to_dict(),
                "field_digest": None if self.field is None else self.field.digest,
                "field_provenance": None if self.field is None else list(self.field.provenance),
                "classification": "initial_guess_not_evidence"}


@dataclass(frozen=True)
class NewtonStepRecord:
    """One (time) step's Newton history as a provider reports it: residual norms r_0..r_k and line-search factors."""

    step: int
    residual_norms: tuple[float, ...]
    line_search_factors: tuple[float, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "residual_norms": list(self.residual_norms),
                "line_search_factors": list(self.line_search_factors)}


@dataclass(frozen=True)
class NonlinearAdmission:
    accepted: bool
    reason: str
    spec: NonlinearSolveSpec
    steps: tuple[NewtonStepRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "nonlinear_convergence_admission_not_evidence", "accepted": self.accepted,
                "reason": self.reason, "spec": self.spec.to_dict(), "steps": [s.to_dict() for s in self.steps],
                "digest": canonical_digest({"spec": self.spec.to_dict(), "steps": [s.to_dict() for s in self.steps]}),
                "notice": ("a met residual test is not uniqueness, discretization accuracy or model validity")}


def admit_nonlinear_execution(
    convergence: ConvergenceState,
    steps: tuple[NewtonStepRecord, ...],
    spec: NonlinearSolveSpec,
    *,
    expected_steps: int,
) -> NonlinearAdmission:
    """Re-derive convergence from the recorded Newton histories; refuse a CONVERGED claim they do not support.

    ``expected_steps`` is the number of (time) steps the problem declares (1 for a steady solve); a CONVERGED
    claim must carry exactly one history for each of the steps ``0 .. expected_steps - 1``, so a record that lists
    only the steps that converged is refused.
    """
    if isinstance(expected_steps, bool) or not isinstance(expected_steps, int) or expected_steps < 1:
        raise PDERefusal("expected_steps must be a positive int (1 for a steady solve)")
    convergence = ConvergenceState(convergence)
    if convergence is ConvergenceState.NOT_APPLICABLE:
        raise PDERefusal("a nonlinear solve converges or fails; NOT_APPLICABLE is not a nonlinear termination state")
    claimed = convergence is ConvergenceState.CONVERGED
    problems: list[str] = []
    if claimed and not steps:
        problems.append("no Newton history was recorded")
    indices = [record.step for record in steps]
    if claimed and sorted(indices) != list(range(expected_steps)):
        problems.append(f"the histories cover steps {sorted(indices)}, not exactly 0..{expected_steps - 1}")
    for record in steps:
        norms = record.residual_norms
        if not norms:
            problems.append(f"step {record.step}: empty residual history")
            continue
        if any(not math.isfinite(v) or v < 0.0 for v in norms):
            problems.append(f"step {record.step}: a residual norm is negative or not finite")
            continue
        iterations = len(norms) - 1
        factors = record.line_search_factors
        if (spec.method == "newton_backtracking" or factors) and len(factors) != iterations:
            problems.append(f"step {record.step}: {len(factors)} line-search factor(s) for {iterations} iteration(s)")
        if iterations > spec.max_iterations:
            problems.append(f"step {record.step}: {iterations} iterations exceed max_iterations {spec.max_iterations}")
        if spec.method == "newton" and record.line_search_factors and any(f != 1.0 for f in record.line_search_factors):
            problems.append(f"step {record.step}: damped steps recorded for an undamped newton method")
        if spec.method == "newton_backtracking" and any(not 0.0 < f <= 1.0 for f in record.line_search_factors):
            problems.append(f"step {record.step}: a line-search factor outside (0, 1]")
        if not spec.accepts(norms[0], norms[-1]):
            problems.append(f"step {record.step}: final residual {norms[-1]:.3e} does not meet "
                            f"max(atol {spec.residual_atol:g}, rtol {spec.residual_rtol:g} x initial {norms[0]:.3e})")
    if claimed and problems:
        raise PDERefusal("false convergence: the record claims CONVERGED but " + "; ".join(problems))
    if claimed:
        return NonlinearAdmission(True, f"every one of {len(steps)} step(s) met the declared residual test", spec, tuple(steps))
    return NonlinearAdmission(False, f"the provider reported {convergence.value}" + (f": {'; '.join(problems)}" if problems else ""),
                              spec, tuple(steps))


__all__ = [
    "InitialGuess",
    "JACOBIAN_KINDS",
    "NONLINEAR_METHODS",
    "NONLINEAR_TEMPLATES",
    "NewtonStepRecord",
    "NonlinearAdmission",
    "NonlinearSolveSpec",
    "admit_nonlinear_execution",
    "require_nonlinear_template",
]
