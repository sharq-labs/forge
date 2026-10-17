"""Which coupling-induced numerical errors a run quantified, estimated, or left open.

``CouplingErrorBudget`` (``final_outputs["_coupling_error"]``) sums the
numerical errors the runtime QUANTIFIED -- today, field-mapping round-trip and
conservation residuals.  Read alone, its ``relative_bound`` can look like the
whole coupling error of a run that also staggered its participants explicitly
or stopped a window at its iteration limit.  This module derives, from an
existing :class:`MultiphysicsRunRecord` and without changing it, every
coupling error source the run carries and what is known about each:

``QUANTIFIED``
    a bound the runtime computed (mapping contributions);
``ESTIMATED``
    an a-posteriori estimate that is NOT a bound: the iteration error of a
    converged plain fixed-point window, ``q / (1 - q) * r_k`` with the
    contraction ``q`` estimated from the last two residuals;
``UNQUANTIFIED``
    present and not estimated (explicit splitting error unless an opt-in
    refinement estimate for THIS run is supplied; accelerated or
    single-iteration windows);
``UNBOUNDED``
    known not to be controlled (a window that ended at its iteration limit).

Estimates are never added to the quantified bound, and nothing UNQUANTIFIED is
ever read as zero.  This is coupling-numerical error only: not physical,
parameter, measurement or model-form uncertainty, and never validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TYPE_CHECKING, Any

from ...scenarios.timeline import canonical_digest
from ...scientific.errors import InvalidScientificProblem
from ...scientific.multiphysics import (
    CouplingScheme,
    MultiphysicsRunRecord,
    RelaxationKind,
    WindowOutcome,
)

if TYPE_CHECKING:
    from .splitting import SplittingErrorEstimate

ASSESSMENT_KIND = "coupling_numerical_error_assessment"

#: Window outcomes after which a window's coupled state is a solution of the
#: window; anything else (iteration limit, a refused participant or transfer)
#: is not controlled at all.
_COMPLETED_OUTCOMES = frozenset({
    WindowOutcome.CONVERGED,
    WindowOutcome.EXPLICIT_COMPLETED,
    WindowOutcome.EVENT_ALIGNED,
})


def run_digest(run: MultiphysicsRunRecord) -> str:
    """The digest coupling evidence binds to: canonical JSON of the run record."""
    return canonical_digest(run.to_dict())


class ErrorSourceStatus(str, Enum):
    QUANTIFIED = "quantified"
    ESTIMATED = "estimated"
    UNQUANTIFIED = "unquantified"
    UNBOUNDED = "unbounded"


class ErrorAccountingVerdict(str, Enum):
    #: every coupling error source carries a computed bound
    BOUNDED = "bounded"
    #: no source is open, but some are estimates rather than bounds
    ESTIMATED = "estimated"
    #: at least one source is present and not estimated
    INCOMPLETE = "incomplete"
    #: at least one window is known not to have converged
    UNBOUNDED = "unbounded"
    #: the run has no coupling edge, so no coupling error source
    NO_COUPLING = "no_coupling"


@dataclass(frozen=True)
class NumericalErrorSource:
    source: str
    kind: str
    status: ErrorSourceStatus
    relative: float | None
    method: str
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ErrorSourceStatus(self.status))
        if not str(self.source).strip() or not str(self.kind).strip() or not str(self.method).strip():
            raise InvalidScientificProblem("a numerical error source names its source, kind and method")
        carries_value = self.status in (ErrorSourceStatus.QUANTIFIED, ErrorSourceStatus.ESTIMATED)
        if carries_value:
            if self.relative is None or not math.isfinite(float(self.relative)) or float(self.relative) < 0.0:
                raise InvalidScientificProblem(
                    f"a {self.status.value} error source carries a finite non-negative relative value"
                )
            object.__setattr__(self, "relative", float(self.relative))
        elif self.relative is not None:
            raise InvalidScientificProblem(
                f"an {self.status.value} error source carries no value (it is never zero)"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "kind": self.kind, "status": self.status.value,
                "relative": self.relative, "method": self.method, "detail": self.detail}


@dataclass(frozen=True)
class CouplingNumericalErrorAssessment:
    """Produced by :func:`assess_coupling_numerical_error` from a run record, never assembled by hand.

    ``run_digest`` binds it to the exact run; ``coupled`` comes from the run's
    graph, so an empty source list can never pass for "no coupling".
    """

    run_id: str
    run_digest: str
    coupled: bool
    sources: tuple[NumericalErrorSource, ...]

    def __post_init__(self) -> None:
        digest = str(self.run_digest)
        if not str(self.run_id).strip() or len(digest) != 64 or set(digest) - set("0123456789abcdef"):
            raise InvalidScientificProblem("an assessment names its run and the run record's sha256 digest")
        if not isinstance(self.coupled, bool):
            raise InvalidScientificProblem("coupled must be a bool derived from the run graph")
        object.__setattr__(self, "sources", tuple(self.sources))
        if any(not isinstance(s, NumericalErrorSource) for s in self.sources):
            raise InvalidScientificProblem("assessment sources must be NumericalErrorSource records")
        if not self.coupled and self.sources:
            raise InvalidScientificProblem("a run without coupling edges has no coupling error source")

    def _total(self, status: ErrorSourceStatus) -> float | None:
        values = [s.relative for s in self.sources if s.status is status]
        return sum(values) if values else None  # type: ignore[arg-type]

    @property
    def quantified_relative_bound(self) -> float | None:
        """Linear sum of the QUANTIFIED sources only (no independence assumed)."""
        return self._total(ErrorSourceStatus.QUANTIFIED)

    @property
    def estimated_relative(self) -> float | None:
        """Linear sum of the ESTIMATED sources; an estimate, never a bound."""
        return self._total(ErrorSourceStatus.ESTIMATED)

    @property
    def verdict(self) -> ErrorAccountingVerdict:
        statuses = {s.status for s in self.sources}
        if not self.coupled:
            return ErrorAccountingVerdict.NO_COUPLING
        if not self.sources:
            # a coupled run always carries a coupling error source; none found is not "none"
            return ErrorAccountingVerdict.INCOMPLETE
        if ErrorSourceStatus.UNBOUNDED in statuses:
            return ErrorAccountingVerdict.UNBOUNDED
        if ErrorSourceStatus.UNQUANTIFIED in statuses:
            return ErrorAccountingVerdict.INCOMPLETE
        if ErrorSourceStatus.ESTIMATED in statuses:
            return ErrorAccountingVerdict.ESTIMATED
        return ErrorAccountingVerdict.BOUNDED

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": ASSESSMENT_KIND,
            "run_id": self.run_id,
            "run_digest": self.run_digest,
            "coupled": self.coupled,
            "verdict": self.verdict.value,
            "quantified_relative_bound": self.quantified_relative_bound,
            "estimated_relative": self.estimated_relative,
            "sources": [s.to_dict() for s in self.sources],
            "notice": (
                "Coupling-induced numerical error only. Estimates are not bounds and are never added to "
                "the quantified bound; an unquantified or unbounded source is open, never zero. Not "
                "physical, parameter, measurement or model-form uncertainty, and not validation."
            ),
        }


def _mapping_sources(run: MultiphysicsRunRecord) -> list[NumericalErrorSource]:
    """The budget's quantified mapping contributions, plus what the budget cannot see.

    The budget sums declared round-trip / conservation residuals only.  From
    the same last-iteration mapping diagnostics it is built from, two more
    sources are open: sites the mapping EXTRAPOLATED to (no residual covers
    them), and a field mapping declared with neither verification at all.
    """
    budget = run.final_outputs.get("_coupling_error") or {}
    sources = [
        NumericalErrorSource(
            source=str(item["source"]), kind="mapping", status=ErrorSourceStatus.QUANTIFIED,
            relative=float(item["relative_bound"]), method=str(item["method"]),
        )
        for item in budget.get("contributions", ())
    ]
    for window in run.windows:
        for item in (window.iterations[-1].mapping_diagnostics if window.iterations else ()):
            edge_id, mapping = item.get("edge_id"), item.get("mapping") or {}
            label = f"window:{window.index}:edge:{edge_id}"
            extrapolated = int(mapping.get("extrapolated_count") or 0)
            if extrapolated > 0:
                sources.append(NumericalErrorSource(
                    source=f"{label}:mapping_extrapolation", kind="mapping", status=ErrorSourceStatus.UNQUANTIFIED,
                    relative=None, method="mapping_extrapolation",
                    detail=(f"{extrapolated}/{mapping.get('target_count')} target sites lie outside the source support "
                            f"(coverage {mapping.get('coverage_fraction')!r}); no declared residual covers them"),
                ))
            if mapping.get("round_trip_relative_l2") is None and mapping.get("conservation_relative_error") is None:
                sources.append(NumericalErrorSource(
                    source=f"{label}:mapping_unverified", kind="mapping", status=ErrorSourceStatus.UNQUANTIFIED,
                    relative=None, method="mapping_unverified",
                    detail="the mapping declared neither a round-trip nor a conservation verification",
                ))
    return sources


def _iteration_sources(run: MultiphysicsRunRecord) -> list[NumericalErrorSource]:
    plan = run.plan
    sources: list[NumericalErrorSource] = []
    plain = plan.relaxation.kind is RelaxationKind.NONE
    for window in run.windows:
        if not window.iterations:
            continue
        label = f"window:{window.index}"
        if window.outcome not in _COMPLETED_OUTCOMES:
            last = window.iterations[-1]
            worst = max((r.relative for r in last.residuals), default=None)
            sources.append(NumericalErrorSource(
                source=f"{label}:iteration", kind="iteration", status=ErrorSourceStatus.UNBOUNDED, relative=None,
                method=f"window_{window.outcome.value}",
                detail=(f"window ended {window.outcome.value} after {len(window.iterations)} iteration(s); last "
                        f"relative residual {worst!r} is a residual, not an error bound"),
            ))
            continue
        if plan.scheme is not CouplingScheme.IMPLICIT:
            continue
        last = window.iterations[-1]
        previous = window.iterations[-2] if len(window.iterations) >= 2 else None
        before = {} if previous is None else {r.edge_id: r for r in previous.residuals}
        for residual in last.residuals:
            source = f"{label}:edge:{residual.edge_id}:iteration"
            prior = before.get(residual.edge_id)
            if not plain:
                sources.append(NumericalErrorSource(
                    source=source, kind="iteration", status=ErrorSourceStatus.UNQUANTIFIED, relative=None,
                    method="accelerated_iteration",
                    detail=(f"{plan.relaxation.kind.value} relaxation: the fixed-point contraction estimate "
                            f"does not apply to an accelerated iteration"),
                ))
                continue
            if prior is None:
                sources.append(NumericalErrorSource(
                    source=source, kind="iteration", status=ErrorSourceStatus.UNQUANTIFIED, relative=None,
                    method="single_iteration",
                    detail="converged at its first iteration: no contraction can be estimated",
                ))
                continue
            current_abs = residual.absolute.magnitude
            prior_abs = prior.absolute.magnitude_in(str(residual.absolute.units))
            if prior_abs <= 0.0:
                sources.append(NumericalErrorSource(
                    source=source, kind="iteration", status=ErrorSourceStatus.UNQUANTIFIED, relative=None,
                    method="fixed_point_contraction_estimate", detail="previous residual is zero",
                ))
                continue
            q = current_abs / prior_abs
            if not math.isfinite(q) or q >= 1.0:
                sources.append(NumericalErrorSource(
                    source=source, kind="iteration", status=ErrorSourceStatus.UNQUANTIFIED, relative=None,
                    method="fixed_point_contraction_estimate",
                    detail=f"observed residual ratio {q!r} is not a contraction",
                ))
                continue
            sources.append(NumericalErrorSource(
                source=source, kind="iteration", status=ErrorSourceStatus.ESTIMATED,
                relative=q / (1.0 - q) * residual.relative, method="fixed_point_contraction_estimate",
                detail=(f"a-posteriori estimate q/(1-q) * r_k with q = {q:.6g} observed from two residuals; "
                        f"an estimate, not a bound"),
            ))
    return sources


def _splitting_sources(
    run: MultiphysicsRunRecord, splitting: "SplittingErrorEstimate | None"
) -> list[NumericalErrorSource]:
    if run.plan.scheme is not CouplingScheme.EXPLICIT or not run.graph.edges:
        if splitting is not None:
            raise InvalidScientificProblem("a splitting estimate applies to an explicit coupled run only")
        return []
    if splitting is not None:
        from .splitting import SplittingErrorEstimate

        if not isinstance(splitting, SplittingErrorEstimate):
            raise InvalidScientificProblem("splitting must be a SplittingErrorEstimate")
        if splitting.base_run_digest != run_digest(run) or splitting.base_run_id != run.run_id:
            # evidence stays bound to the exact run it was produced with
            raise InvalidScientificProblem(
                "the splitting estimate was produced with another run; it does not describe this one"
            )
        return [
            NumericalErrorSource(
                source=f"run:splitting:{item.quantity}", kind="splitting",
                status=ErrorSourceStatus.ESTIMATED if item.estimated else ErrorSourceStatus.UNQUANTIFIED,
                relative=item.relative, method="window_refinement_richardson",
                detail=f"{item.detail}; order {splitting.order_basis}; windows {list(splitting.windows_s)} s",
            )
            for item in splitting.quantities
        ]
    return [NumericalErrorSource(
        source="run:splitting", kind="splitting", status=ErrorSourceStatus.UNQUANTIFIED, relative=None,
        method="explicit_staggering",
        detail=(f"explicit coupling over {len(run.windows)} window(s) staggers participants on lagged "
                f"coupling values; this run did not estimate the splitting error (a window-refinement "
                f"comparison would)"),
    )]


def assess_coupling_numerical_error(
    run: MultiphysicsRunRecord,
    *,
    splitting: "SplittingErrorEstimate | None" = None,
) -> CouplingNumericalErrorAssessment:
    """Every coupling numerical error source of ``run`` and its status (derived; the run is not changed).

    ``splitting``: an opt-in refinement estimate produced WITH this run
    (:func:`~engcore.execution.multiphysics.splitting.estimate_splitting_error`).
    It replaces the open splitting source by one source per estimated
    quantity; it only ever covers the quantities it names.
    """
    if not isinstance(run, MultiphysicsRunRecord):
        raise InvalidScientificProblem("assess_coupling_numerical_error takes a MultiphysicsRunRecord")
    digest = run_digest(run)
    if not run.graph.edges:
        if splitting is not None:
            raise InvalidScientificProblem("a run without coupling edges has no splitting error to estimate")
        return CouplingNumericalErrorAssessment(run.run_id, digest, False, ())
    sources = _mapping_sources(run) + _iteration_sources(run) + _splitting_sources(run, splitting)
    return CouplingNumericalErrorAssessment(run.run_id, digest, True, tuple(sources))
