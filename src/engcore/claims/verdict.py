"""The claim-level verdict: SUPPORTED, CONTRADICTED, or INSUFFICIENT_EVIDENCE.

This is the one place a claim is answered, and the rule is written down here
in full because it is a scientific decision, not a code decision
(``docs/scientific-core/scientific-claim-and-context-of-use.md`` §6 named it as
the missing piece). It derives from records that already carry their own
authority -- the credibility report's verdict, the SRIA Arbiter's assurance
decision, the uncertainty the report declares -- and adds nothing to them.

The distinction the rule exists to keep
---------------------------------------
**"The claim is false" is not "we cannot establish whether it is true."**

``CONTRADICTED``
    Evidence that meets the claim's *own* evidence bar says the comparison
    fails. Contradiction must clear exactly the bar support must clear: an
    admissible run -- a SUPPORTED credibility report, a VALID assurance
    decision for the claim's required levels and demanded uncertainty
    channels, and a supported discrepancy where one is demanded -- whose value
    violates the comparison over the whole uncertainty band.
``SUPPORTED``
    The same admissible evidence, and the comparison holds over the whole band.
``INSUFFICIENT_EVIDENCE``
    Everything else, and in particular:

    * the claim was not READY (missing input, ambiguity, no capability);
    * the only model was OUTSIDE its validated domain -- that shows *this
      execution* cannot bear on the claim, never that the claim is false;
    * a credibility report of NOT_SUPPORTED, whether from a violated validity
      condition or from a failed check -- an untrustworthy run is not evidence
      against the claim;
    * a credibility report of INSUFFICIENT_EVIDENCE (applicability UNKNOWN, a
      check not run, a solver that did not converge);
    * an assurance decision that is not VALID (a required level not attained,
      a demanded uncertainty channel UNKNOWN, a process critic not passed);
    * a demanded discrepancy that is not supported;
    * an uncertainty band that straddles the decision boundary.

The comparison rule
-------------------
Stated by the claim, never chosen here:

* **No channel demanded** -- a *point comparison*: the claim's
  :class:`~engcore.scientific.ir.constraints.ConstraintDefinition` checks the
  reported value. The uncertainty the report carries is shown, not used; using
  it only when it happens to be known would let *missing* uncertainty give a
  firmer answer than *known* uncertainty, which is the inversion this layer
  forbids.
* **Channels demanded** -- a *guard-banded conformity decision* over the
  demanded channels only: each channel's record must be quantified and
  attributed to that channel; a STANDARD record contributes ``k * u`` with the
  claim's declared coverage factor ``k`` (none declared: undecided, never a
  conventional 2), an INTERVAL record contributes its own bounds' distances
  from the value. The half-widths are **summed linearly** -- no independence
  assumption, so the band is conservative -- and the comparison must hold, or
  fail, at both ends of the band. A band that contains the boundary decides
  nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ..scientific.units.quantity import Quantity
from ..sria.uncertainty import CHANNEL_ACCEPTS_SOURCE, CHANNEL_OF_SOURCE, UncertaintyChannel
from .contract import ClaimKind, ScientificClaim


class ClaimVerdict(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ComparisonOutcome(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    #: The uncertainty band contains the decision boundary.
    UNDECIDED = "undecided"
    #: A demanded channel could not be used; nothing was compared.
    NOT_EVALUATED = "not_evaluated"


class DecisionRule(str, Enum):
    POINT = "point"
    GUARD_BAND = "guard_band_linear_sum"


@dataclass(frozen=True)
class ChannelUse:
    """How one demanded channel entered (or failed to enter) the band."""

    channel: UncertaintyChannel
    usable: bool
    lower_half_width: float | None
    upper_half_width: float | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "usable": self.usable,
            "lower_half_width": self.lower_half_width,
            "upper_half_width": self.upper_half_width,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ClaimComparison:
    """The claim's comparison applied to one reported value."""

    value: Quantity
    bound: Quantity
    rule: DecisionRule
    outcome: ComparisonOutcome
    point_satisfied: bool
    point_margin: Quantity
    band_lower: Quantity | None = None
    band_upper: Quantity | None = None
    channels: tuple[ChannelUse, ...] = ()
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value.to_dict(),
            "bound": self.bound.to_dict(),
            "rule": self.rule.value,
            "outcome": self.outcome.value,
            "point_satisfied": self.point_satisfied,
            "point_margin": self.point_margin.to_dict(),
            "band_lower": None if self.band_lower is None else self.band_lower.to_dict(),
            "band_upper": None if self.band_upper is None else self.band_upper.to_dict(),
            "channels": [c.to_dict() for c in self.channels],
            "detail": self.detail,
        }


def _channel_record(
    channel: UncertaintyChannel, record: Uncertainty | None, value: Quantity, k: float | None
) -> ChannelUse:
    if record is None or not record.is_quantified:
        return ChannelUse(channel, False, None, None, "UNKNOWN: an unquantified channel is not zero")
    source = UncertaintySource(record.source_kind)
    if source is UncertaintySource.COMBINED:
        return ChannelUse(channel, False, None, None, "COMBINED: a mixture of channels cannot stand for one")
    if source is UncertaintySource.UNSPECIFIED or CHANNEL_OF_SOURCE.get(source) is not channel:
        return ChannelUse(
            channel, False, None, None,
            f"declared source {source.value!r} does not attribute the record to {channel.value!r}",
        )
    if source not in CHANNEL_ACCEPTS_SOURCE[channel]:  # pragma: no cover - CHANNEL_OF_SOURCE already implies it
        return ChannelUse(channel, False, None, None, "source not accepted by the channel")
    if record.kind is UncertaintyKind.STANDARD:
        if k is None:
            return ChannelUse(
                channel, False, None, None,
                "a STANDARD uncertainty needs the claim's coverage factor, and none was declared",
            )
        half = k * record.standard_uncertainty.magnitude_as_spread_in(value.units)
        return ChannelUse(channel, True, half, half, f"STANDARD u x k={k}")
    lower = value.magnitude - record.lower.to(value.units).magnitude
    upper = record.upper.to(value.units).magnitude - value.magnitude
    if lower < 0.0 or upper < 0.0:
        return ChannelUse(channel, False, None, None, "the INTERVAL does not contain the reported value")
    return ChannelUse(channel, True, lower, upper, "INTERVAL bounds as declared")


def compare(
    claim: ScientificClaim,
    value: Quantity,
    bound: Quantity,
    uncertainty: Mapping[UncertaintyChannel, Uncertainty],
) -> ClaimComparison:
    """Apply the claim's decision rule to one value. Pure."""
    constraint = claim.constraint(bound)
    point = constraint.check(value)
    if not claim.uncertainty.demands_quantification:
        return ClaimComparison(
            value=value,
            bound=bound,
            rule=DecisionRule.POINT,
            outcome=ComparisonOutcome.SATISFIED if point.satisfied else ComparisonOutcome.VIOLATED,
            point_satisfied=point.satisfied,
            point_margin=point.margin,
            detail="point comparison: the claim demands no quantified uncertainty channel",
        )
    uses = tuple(
        _channel_record(channel, uncertainty.get(channel), value, claim.uncertainty.coverage_factor)
        for channel in claim.uncertainty.ordered_channels()
    )
    if not all(use.usable for use in uses):
        return ClaimComparison(
            value=value,
            bound=bound,
            rule=DecisionRule.GUARD_BAND,
            outcome=ComparisonOutcome.NOT_EVALUATED,
            point_satisfied=point.satisfied,
            point_margin=point.margin,
            channels=uses,
            detail="a demanded channel is unusable; no band can be formed",
        )
    lower = Quantity(value.magnitude - sum(u.lower_half_width for u in uses), value.units)
    upper = Quantity(value.magnitude + sum(u.upper_half_width for u in uses), value.units)
    at_lower = constraint.check(lower).satisfied
    at_upper = constraint.check(upper).satisfied
    if at_lower and at_upper:
        outcome = ComparisonOutcome.SATISFIED
    elif not at_lower and not at_upper and _entirely_outside(claim, constraint, lower, upper):
        outcome = ComparisonOutcome.VIOLATED
    else:
        outcome = ComparisonOutcome.UNDECIDED
    return ClaimComparison(
        value=value,
        bound=bound,
        rule=DecisionRule.GUARD_BAND,
        outcome=outcome,
        point_satisfied=point.satisfied,
        point_margin=point.margin,
        band_lower=lower,
        band_upper=upper,
        channels=uses,
        detail="linear sum of the demanded channels' half-widths; no independence assumed",
    )


def _entirely_outside(claim: ScientificClaim, constraint: Any, lower: Quantity, upper: Quantity) -> bool:
    """For a band, both ends failing means failing throughout -- unless the band spans the tolerance band."""
    if claim.kind is ClaimKind.THRESHOLD:
        return True  # an inequality fails on one side only; both ends failing is the whole band
    b = constraint.bound.magnitude
    tol = constraint.tolerance.magnitude_as_spread_in(constraint.bound.units)
    lo = lower.to(constraint.bound.units).magnitude
    hi = upper.to(constraint.bound.units).magnitude
    return hi < b - tol or lo > b + tol


# ---------------------------------------------------------------------------
# The derivation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictBasis:
    """Every lower-level fact the verdict reads, and nothing else."""

    ready: bool
    executed: bool
    bound: bool
    credibility: str | None  # CredibilityVerdict value
    assurance: str | None  # AssuranceVerdict value
    discrepancy_supported: bool | None  # None: not demanded
    comparison: ComparisonOutcome | None
    #: Phase 3: whether the decision context's policy requirements the claim cannot state
    #: (validation evidence, an independent route, applicability) are met. None: no context.
    policy_satisfied: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "executed": self.executed,
            "bound": self.bound,
            "credibility": self.credibility,
            "assurance": self.assurance,
            "discrepancy_supported": self.discrepancy_supported,
            "comparison": None if self.comparison is None else self.comparison.value,
            **({} if self.policy_satisfied is None else {"policy_satisfied": self.policy_satisfied}),
        }


def admissible(basis: VerdictBasis) -> bool:
    """Whether the run's evidence clears the claim's own bar. Support and contradiction share it."""
    return (
        basis.ready
        and basis.executed
        and basis.bound
        and basis.credibility == "supported"
        and basis.assurance == "valid"
        and basis.discrepancy_supported is not False
        and basis.policy_satisfied is not False
    )


def derive_claim_verdict(basis: VerdictBasis) -> ClaimVerdict:
    """The rule in the module docstring, as code. Pure and total."""
    if not admissible(basis):
        return ClaimVerdict.INSUFFICIENT_EVIDENCE
    if basis.comparison is ComparisonOutcome.SATISFIED:
        return ClaimVerdict.SUPPORTED
    if basis.comparison is ComparisonOutcome.VIOLATED:
        return ClaimVerdict.CONTRADICTED
    return ClaimVerdict.INSUFFICIENT_EVIDENCE


__all__ = [
    "ChannelUse",
    "ClaimComparison",
    "ClaimVerdict",
    "ComparisonOutcome",
    "DecisionRule",
    "VerdictBasis",
    "admissible",
    "compare",
    "derive_claim_verdict",
]
