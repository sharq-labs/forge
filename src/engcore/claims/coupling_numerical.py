"""Coupling-numerical error as a CONDITION on a claim's NUMERICAL uncertainty -- never as its value.

A claim's NUMERICAL channel carries the numerical uncertainty of the reported
value as a whole: a refinement study (:mod:`.uq_studies`, estimated by
:mod:`.numerical_uq`).  When that value comes from a coupled multiphysics run,
the coupling contributes numerical error the study may not have exercised:
field-mapping error, the iteration error of implicit windows, the splitting
error of explicit staggering, and -- worst -- windows that never completed.
:func:`~engcore.execution.multiphysics.numerical_error.assess_coupling_numerical_error`
says which of those the run quantified, estimated, left open, or knows to be
unbounded.  This module applies that assessment to the study's NUMERICAL record:

1. **It never quantifies or widens anything.**  A coupling bound is not a bound
   on the claim's quantity (a mapping residual is a relative FIELD norm, and a
   diagnostic rather than a bound) and an
   estimate is not a bound, so no number moves from the assessment into the
   channel.  The study's record passes unchanged or the channel is UNKNOWN.
2. **UNKNOWN never improves**: an UNKNOWN study record stays UNKNOWN.
3. **Every coupling error source vetoes** unless it is QUANTIFIED as exactly
   zero.  A DIAGNOSTIC (a mapping round-trip or conservation residual) is not
   an error source: it bounds nothing, so it can neither close a source nor
   pass the channel -- the forward error of the mapping it describes is its
   own UNQUANTIFIED source (Phase 1 BR3).  Before BR3 a conservation residual
   of 0.0 was read as a QUANTIFIED zero and passed a field-mapped run.
   Nothing a caller says can cover a source.  Declared coverage by the
   study's own ladder (a capability declaration bound into the plan digest and
   checked against the ladder) is a deferred design item, not supported here.
4. **Nothing is taken on trust.**  The assessment is computed here from the
   run record (never passed in), the study record is re-derived through
   :func:`.numerical_uq.estimate_from_dict`, and the study's level 0 must be the
   run named by the coupled run's id (``<run_id>~numerical~0``).

Not enforced here: that EVERY claim built on a coupled run is conditioned.  No
claims capability produces a multiphysics run record yet; wiring that rule into
the claim path, and deciding whether the electrothermal fixed point's
``CouplingEvidence`` reports must also be conditioned, are owner decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping

from ..execution.multiphysics.numerical_error import (
    ErrorAccountingVerdict,
    ErrorSourceStatus,
    assess_coupling_numerical_error,
)
from ..scientific.multiphysics import MultiphysicsRunRecord
from ..scientific.results.uncertainty import Uncertainty, UncertaintySource
from ..sria.uncertainty import UncertaintyChannel
from .errors import ClaimLayerError
from .numerical_uq import NumericalUQError, estimate_from_dict

if TYPE_CHECKING:
    from ..execution.multiphysics.splitting import SplittingErrorEstimate


class CouplingConditionError(ClaimLayerError):
    """The inputs cannot be combined without misattributing evidence."""


class CouplingConditionAction(str, Enum):
    #: the study's NUMERICAL record was already UNKNOWN; nothing here can improve it
    UNCHANGED_UNKNOWN = "unchanged_unknown"
    #: every coupling error source is absent or quantified as exactly zero
    PASSED = "passed"
    #: a coupling error source is unbounded, open, estimated or non-zero: the channel is UNKNOWN
    VETOED = "vetoed"


@dataclass(frozen=True)
class CoupledNumericalUncertainty:
    """What the NUMERICAL channel may carry for a value from a coupled run, and why."""

    uncertainty: Uncertainty
    action: CouplingConditionAction
    reason: str
    assessment: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "coupled_numerical_uncertainty_condition",
            "action": self.action.value,
            "reason": self.reason,
            "uncertainty": self.uncertainty.to_dict(),
            "assessment": dict(self.assessment),
            "notice": ("the coupling assessment conditions the NUMERICAL channel; it never supplies or widens a "
                       "value, and an estimate never counts as a bound"),
        }


def _study_uncertainty(study_record: Mapping[str, Any], run_id: str) -> Uncertainty:
    """The NUMERICAL record a refinement study legitimately produced for ``run_id``."""
    if not isinstance(study_record, Mapping):
        raise CouplingConditionError("the refinement study record must be a mapping (uq_studies record)")
    if study_record.get("kind") != "refinement" or study_record.get("channel") != UncertaintyChannel.NUMERICAL.value:
        raise CouplingConditionError("only a NUMERICAL refinement-study record is conditioned by coupling error")
    runs = study_record.get("runs") or ()
    expected = f"{run_id}~numerical~0"
    if not runs or runs[0].get("run_id") != expected:
        raise CouplingConditionError(
            f"the study's level 0 is {None if not runs else runs[0].get('run_id')!r}, not {expected!r}; the study "
            f"is not about this coupled run"
        )
    if study_record.get("problem") is not None:
        return Uncertainty.unknown(f"numerical uncertainty not quantified: {study_record['problem']}")
    try:
        estimate = estimate_from_dict(dict(study_record["estimate"]))
    except (KeyError, NumericalUQError) as exc:
        raise CouplingConditionError(f"the refinement study record does not re-derive: {exc}") from exc
    # every level the estimate was computed from is a run of THIS study, about THIS run, with the recorded value
    expected_ids = [f"{run_id}~numerical~{k}" for k in range(len(estimate.levels))]
    if (
        [level.run_id for level in estimate.levels] != expected_ids
        or [r.get("run_id") for r in runs] != expected_ids
        or [level.value for level in estimate.levels] != [r.get("value") for r in runs]
    ):
        raise CouplingConditionError(
            "the study's runs and the levels its estimate was computed from are not the same runs of this coupled "
            "run; the study is not about this coupled run"
        )
    numerical = estimate.to_uncertainty()
    if numerical.to_dict() != dict(study_record.get("uncertainty") or {}):
        raise CouplingConditionError("the study record's uncertainty is not the one its estimate derives")
    if numerical.is_quantified and UncertaintySource(numerical.source_kind) is not UncertaintySource.NUMERICAL:
        raise CouplingConditionError("a refinement study must yield a NUMERICAL record")
    return numerical


def condition_numerical_uncertainty(
    study_record: Mapping[str, Any],
    run: MultiphysicsRunRecord,
    *,
    splitting: "SplittingErrorEstimate | None" = None,
) -> CoupledNumericalUncertainty:
    """Apply the module rules to a refinement-study record and the coupled run it is about.

    Pure; a veto is a result, not an exception.  ``splitting`` is an optional
    BR4 estimate bound to ``run``; being an estimate, it never prevents a veto.
    """
    if not isinstance(run, MultiphysicsRunRecord):
        raise CouplingConditionError("run must be the MultiphysicsRunRecord that produced the reported value")
    numerical = _study_uncertainty(study_record, run.run_id)
    assessment = assess_coupling_numerical_error(run, splitting=splitting)
    record = assessment.to_dict()

    def result(uncertainty: Uncertainty, action: CouplingConditionAction, reason: str) -> CoupledNumericalUncertainty:
        return CoupledNumericalUncertainty(uncertainty, action, reason, record)

    if not numerical.is_quantified:
        return result(numerical, CouplingConditionAction.UNCHANGED_UNKNOWN,
                      "the study's NUMERICAL record is UNKNOWN; coupling evidence cannot improve it")
    if assessment.verdict is ErrorAccountingVerdict.NO_COUPLING:
        return result(numerical, CouplingConditionAction.PASSED, "the run has no coupling edge")
    if assessment.verdict is ErrorAccountingVerdict.UNBOUNDED:
        unbounded = [s.source for s in assessment.sources if s.status is ErrorSourceStatus.UNBOUNDED]
        return result(
            Uncertainty.unknown(f"numerical uncertainty not quantified: coupled run did not complete ({unbounded})"),
            CouplingConditionAction.VETOED,
            f"unbounded coupling error: {unbounded}",
        )
    error_sources = [s for s in assessment.sources if s.status is not ErrorSourceStatus.DIAGNOSTIC]
    open_sources = [
        f"{s.source} ({s.status.value})"
        for s in error_sources
        if not (s.status is ErrorSourceStatus.QUANTIFIED and s.relative == 0.0)
    ]
    if open_sources or not error_sources:
        return result(
            Uncertainty.unknown(
                f"numerical uncertainty not quantified: coupling error not shown to be zero ({open_sources or 'none assessed'})"
            ),
            CouplingConditionAction.VETOED,
            f"coupling error sources not quantified as zero: {open_sources or 'a coupled run with no assessed source'}",
        )
    return result(numerical, CouplingConditionAction.PASSED, "every coupling error source is quantified as exactly zero")


__all__ = [
    "CoupledNumericalUncertainty",
    "CouplingConditionAction",
    "CouplingConditionError",
    "condition_numerical_uncertainty",
]
