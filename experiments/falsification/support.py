"""Support / transport status, and the two stopping policies.

DECISION-PATH MODULE. It must never import the hidden truth.

This implements invariant 13 of the scientific brain spec. The two policies
differ in exactly one clause:

    NAIVE            stop is allowed when no affordable action has positive
                     net value.

    TRANSPORT-AWARE  stop is *certifiable* only when that decision-theoretic
                     condition holds AND the terminal decision condition is
                     within the justified support region.

The support rule below is **declared, not derived**. For a 1-D benchmark the
justified region is the closed interval spanned by the assimilated observations
widened by a declared margin. There is no convex-hull theorem here and none is
claimed; a real domain would declare its own rule, and the architectural point
is only that *some* declared rule must gate certification.

The escape hatch is deliberate and auditable: a campaign may declare a
:class:`TransportJustification` covering a region, with a stated rationale and
an owner. Extrapolation then becomes a recorded scientific claim someone signed
for, rather than something inferred from a tight posterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .inference import Observation


class SupportStatus(str, Enum):
    """Whether the terminal decision condition is scientifically reachable."""

    #: Inside the region the assimilated observations actually constrain.
    SUPPORTED = "supported"
    #: Outside it, but covered by an explicitly declared transport claim.
    JUSTIFIED_TRANSPORT = "justified_transport"
    #: Outside it, with nothing declared. Extrapolation nobody owns.
    UNSUPPORTED = "unsupported"
    #: Nothing has been assimilated, so there is no support region at all.
    NO_OBSERVATIONS = "no_observations"


class StopVerdict(str, Enum):
    CONTINUE = "continue"
    STOP_ALLOWED = "stop_allowed"
    STOP_NOT_CERTIFIABLE = "stop_not_certifiable"


class StopReasonCode(str, Enum):
    NO_ACTION_WORTH_BUYING = "no_action_worth_buying"
    POSITIVE_NET_VALUE_AVAILABLE = "positive_net_value_available"
    UNSUPPORTED_TRANSPORT = "unsupported_transport"


@dataclass(frozen=True)
class TransportJustification:
    """A declared, owned claim that a model may be carried beyond the data."""

    justification_id: str
    lower: float
    upper: float
    rationale: str
    owner: str

    def __post_init__(self) -> None:
        if self.upper < self.lower:
            raise ValueError("transport justification bounds are inverted")
        for label in ("justification_id", "rationale", "owner"):
            if not str(getattr(self, label)).strip():
                raise ValueError(
                    f"a transport justification requires {label}; an "
                    f"unattributed extrapolation claim cannot be reviewed"
                )

    def covers(self, x: float) -> bool:
        return self.lower <= float(x) <= self.upper


@dataclass(frozen=True)
class SupportRule:
    """The declared 1-D support rule. Documented at the point of use."""

    rule_id: str = "interval_hull_with_margin/1"
    #: How far beyond the observed range the model is taken to remain
    #: constrained. Declared by the campaign, not derived.
    margin: float = 0.5

    def region(self, observations: Sequence[Observation]) -> tuple[float, float] | None:
        if not observations:
            return None
        xs = [float(o.x) for o in observations]
        return (min(xs) - self.margin, max(xs) + self.margin)


@dataclass(frozen=True)
class SupportAssessment:
    status: SupportStatus
    x_star: float
    region: tuple[float, float] | None
    rule_id: str
    margin: float
    justification_id: str = ""
    detail: str = ""

    @property
    def is_supported(self) -> bool:
        return self.status in (
            SupportStatus.SUPPORTED,
            SupportStatus.JUSTIFIED_TRANSPORT,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "x_star": self.x_star,
            "region": list(self.region) if self.region else None,
            "rule_id": self.rule_id,
            "margin": self.margin,
            "justification_id": self.justification_id,
            "detail": self.detail,
        }


def assess_support(
    x_star: float,
    observations: Sequence[Observation],
    rule: SupportRule | None = None,
    justifications: Sequence[TransportJustification] = (),
) -> SupportAssessment:
    rule = rule or SupportRule()
    region = rule.region(observations)
    if region is None:
        return SupportAssessment(
            status=SupportStatus.NO_OBSERVATIONS,
            x_star=float(x_star),
            region=None,
            rule_id=rule.rule_id,
            margin=rule.margin,
            detail="no observations have been assimilated",
        )
    lower, upper = region
    if lower <= float(x_star) <= upper:
        return SupportAssessment(
            status=SupportStatus.SUPPORTED,
            x_star=float(x_star),
            region=region,
            rule_id=rule.rule_id,
            margin=rule.margin,
            detail=(
                f"x*={x_star:g} lies inside the observed interval "
                f"[{lower:g}, {upper:g}]"
            ),
        )
    for justification in justifications:
        if justification.covers(float(x_star)):
            return SupportAssessment(
                status=SupportStatus.JUSTIFIED_TRANSPORT,
                x_star=float(x_star),
                region=region,
                rule_id=rule.rule_id,
                margin=rule.margin,
                justification_id=justification.justification_id,
                detail=(
                    f"x*={x_star:g} is outside [{lower:g}, {upper:g}] but is "
                    f"covered by declared transport justification "
                    f"{justification.justification_id!r} owned by "
                    f"{justification.owner!r}: {justification.rationale}"
                ),
            )
    return SupportAssessment(
        status=SupportStatus.UNSUPPORTED,
        x_star=float(x_star),
        region=region,
        rule_id=rule.rule_id,
        margin=rule.margin,
        detail=(
            f"x*={x_star:g} lies outside the observed interval "
            f"[{lower:g}, {upper:g}] and no transport justification covers it"
        ),
    )


@dataclass(frozen=True)
class StopDecision:
    verdict: StopVerdict
    reason: StopReasonCode
    policy: str
    best_net_value: float
    best_action_id: str = ""
    support: SupportAssessment | None = None
    detail: str = ""

    @property
    def certifies_stop(self) -> bool:
        return self.verdict is StopVerdict.STOP_ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "verdict": self.verdict.value,
            "reason": self.reason.value,
            "best_action_id": self.best_action_id,
            "best_net_value": self.best_net_value,
            "support": self.support.to_dict() if self.support else None,
            "detail": self.detail,
        }


def _best_net(evsi_table: Mapping[str, Mapping[str, float]]) -> tuple[str, float]:
    if not evsi_table:
        return "", float("-inf")
    action_id, entry = max(
        evsi_table.items(), key=lambda item: (item[1]["net"], item[0])
    )
    return action_id, float(entry["net"])


def naive_stop_policy(
    evsi_table: Mapping[str, Mapping[str, float]],
) -> StopDecision:
    """Stop when no affordable action has positive net value. Nothing else."""
    action_id, net = _best_net(evsi_table)
    if net > 0.0:
        return StopDecision(
            verdict=StopVerdict.CONTINUE,
            reason=StopReasonCode.POSITIVE_NET_VALUE_AVAILABLE,
            policy="naive_decision_theoretic",
            best_action_id=action_id,
            best_net_value=net,
            detail=f"action {action_id!r} has net value {net:.6g} > 0",
        )
    return StopDecision(
        verdict=StopVerdict.STOP_ALLOWED,
        reason=StopReasonCode.NO_ACTION_WORTH_BUYING,
        policy="naive_decision_theoretic",
        best_action_id=action_id,
        best_net_value=net,
        detail=(
            f"best net value {net:.6g} <= 0; under the assumed model no "
            f"experiment pays for itself"
        ),
    )


def transport_aware_stop_policy(
    evsi_table: Mapping[str, Mapping[str, float]],
    support: SupportAssessment,
) -> StopDecision:
    """The same economics, plus the support condition of invariant 13."""
    action_id, net = _best_net(evsi_table)
    if net > 0.0:
        return StopDecision(
            verdict=StopVerdict.CONTINUE,
            reason=StopReasonCode.POSITIVE_NET_VALUE_AVAILABLE,
            policy="transport_aware",
            best_action_id=action_id,
            best_net_value=net,
            support=support,
            detail=f"action {action_id!r} has net value {net:.6g} > 0",
        )
    if not support.is_supported:
        return StopDecision(
            verdict=StopVerdict.STOP_NOT_CERTIFIABLE,
            reason=StopReasonCode.UNSUPPORTED_TRANSPORT,
            policy="transport_aware",
            best_action_id=action_id,
            best_net_value=net,
            support=support,
            detail=(
                f"no experiment pays for itself under the assumed model, but "
                f"{support.detail}. A sharp posterior over an unobserved region "
                f"reflects the model's form, not the evidence's reach, so low "
                f"EVSI cannot certify this stop."
            ),
        )
    return StopDecision(
        verdict=StopVerdict.STOP_ALLOWED,
        reason=StopReasonCode.NO_ACTION_WORTH_BUYING,
        policy="transport_aware",
        best_action_id=action_id,
        best_net_value=net,
        support=support,
        detail=(
            f"best net value {net:.6g} <= 0 and {support.detail}; both "
            f"conditions for certifying a stop are met"
        ),
    )
