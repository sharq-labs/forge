"""Risk against coverage: what the trust layer asserted, and how often it was wrong.

The question a buyer asks is not "how accurate is the model". It is:

    Of the predictions this system was willing to stand behind, how many were
    wrong -- and how much did it refuse in order to get there?

Those two numbers move against each other. A system that refuses everything has
a false-trust rate of zero and is worthless; a system that supports everything
has full coverage and no guardrail. Reporting either alone is the oldest way to
make an assurance layer look good, so this module reports both and never
summarises them into one score.

The 2x2 that matters
--------------------
Two axes, kept apart: what Forge **decided**, and what the world **said**.

==================  ==========================  ==========================
                    truth: within tolerance     truth: outside tolerance
==================  ==========================  ==========================
SUPPORTED           correct support             **false trust**
REFUSED             **over-refusal**            correct refusal
==================  ==========================  ==========================

*False trust* is the expensive cell: a number that was relied on and was wrong.
*Over-refusal* is the cheap one: a number that would have been right and was
declined. They are not symmetric in cost and are never netted against each
other.

THE THIRD COLUMN, WHICH HAS TO EXIST
-------------------------------------
``GroundTruth.UNKNOWN``. A case with no reviewed acceptance tolerance, or no
measurement, has no truth to compare against. It is counted, it is reported,
and it enters **no rate** -- not as a pass, not as a failure. A metric that
resolved unknown truth in either direction would be inventing the evidence the
whole system exists to require.

WHY THIS RECORD CANNOT NAME A PROVIDER
---------------------------------------
:class:`PredictionOutcome` has three fields and none of them is a provider, a
solver, a model or a backend. That is not an omission -- it is the enforcement
mechanism for P14's requirement that these metrics work "regardless of whether
the prediction came from Forge native, PyBaMM, or a future provider". A metric
that *could* record which engine produced a number would eventually be sliced
by it, and a provider whose numbers were scored on a different scale would stop
being comparable. The type makes the slice unexpressible.

``engcore.credibility`` does not import ``engcore.providers``, and a test
asserts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence


class TrustDecision(str, Enum):
    """What the trust layer decided about one prediction.

    ``NOT_SUPPORTED`` is separate from ``REFUSED``: the first is a claim the
    evidence contradicts, the second is a claim the system declined to make.
    Folding them together would count a working guardrail as a failed claim.
    """

    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    REFUSED = "refused"


class GroundTruth(str, Enum):
    """What the world said, for the cases where the world said anything."""

    WITHIN_TOLERANCE = "within_tolerance"
    OUTSIDE_TOLERANCE = "outside_tolerance"
    #: No reviewed tolerance, or no measurement. Enters no rate.
    UNKNOWN = "unknown"

    @property
    def is_known(self) -> bool:
        return self is not GroundTruth.UNKNOWN


@dataclass(frozen=True)
class PredictionOutcome:
    """One case: what was decided, what was true, and how close the call was.

    ``margin`` is optional and is used only to order cases for
    :func:`risk_coverage_curve`. It is deliberately *not* used by
    :func:`summarise`: a rate computed from a margin would be a rate computed
    from the system's own confidence in itself.
    """

    case_id: str
    decision: TrustDecision
    truth: GroundTruth
    margin: float | None = None

    def __post_init__(self) -> None:
        if not str(self.case_id).strip():
            raise ValueError("a prediction outcome requires a case_id")
        if not isinstance(self.decision, TrustDecision):
            raise ValueError("decision must be a TrustDecision")
        if not isinstance(self.truth, GroundTruth):
            raise ValueError("truth must be a GroundTruth")


def _rate(numerator: int, denominator: int) -> float | None:
    """``None`` when nothing was measured. Never ``0.0`` standing in for it.

    A system that refused nothing has an *unmeasured* over-refusal rate, not a
    zero one, and the difference is the whole point: zero reads as "we checked
    and it never happens".
    """
    if denominator <= 0:
        return None
    return numerator / denominator


@dataclass(frozen=True)
class RiskCoverageReport:
    """The 2x2, the counts beside it, and the three derived rates."""

    total: int
    supported: int
    not_supported: int
    refused: int
    correct_support: int
    false_trust: int
    correct_refusal: int
    over_refusal: int
    #: Decided, but with no truth to compare against. In no rate.
    truth_unknown: int

    @property
    def coverage(self) -> float | None:
        """Fraction of asked cases the system was willing to stand behind."""
        return _rate(self.supported, self.total)

    @property
    def false_trust_rate(self) -> float | None:
        """Of the supported predictions with known truth, how many were wrong."""
        return _rate(self.false_trust, self.correct_support + self.false_trust)

    @property
    def over_refusal_rate(self) -> float | None:
        """Of the refusals with known truth, how many were unnecessary."""
        return _rate(self.over_refusal, self.correct_refusal + self.over_refusal)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "supported": self.supported,
            "not_supported": self.not_supported,
            "refused": self.refused,
            "correct_support": self.correct_support,
            "false_trust": self.false_trust,
            "correct_refusal": self.correct_refusal,
            "over_refusal": self.over_refusal,
            "truth_unknown": self.truth_unknown,
            "coverage": self.coverage,
            "false_trust_rate": self.false_trust_rate,
            "over_refusal_rate": self.over_refusal_rate,
            "rate_note": (
                "a null rate means the denominator was empty -- nothing was "
                "measured -- and is not zero"
            ),
        }


def summarise(outcomes: Iterable[PredictionOutcome]) -> RiskCoverageReport:
    """Tally the 2x2. No weighting, no netting, no single score."""
    items = list(outcomes)
    seen: set[str] = set()
    for item in items:
        if item.case_id in seen:
            raise ValueError(
                f"case {item.case_id!r} appears twice; a case counted twice "
                f"moves every rate it touches"
            )
        seen.add(item.case_id)

    supported = [o for o in items if o.decision is TrustDecision.SUPPORTED]
    refused = [o for o in items if o.decision is TrustDecision.REFUSED]
    not_supported = [o for o in items if o.decision is TrustDecision.NOT_SUPPORTED]
    return RiskCoverageReport(
        total=len(items),
        supported=len(supported),
        not_supported=len(not_supported),
        refused=len(refused),
        correct_support=sum(
            1 for o in supported if o.truth is GroundTruth.WITHIN_TOLERANCE
        ),
        false_trust=sum(
            1 for o in supported if o.truth is GroundTruth.OUTSIDE_TOLERANCE
        ),
        correct_refusal=sum(
            1 for o in refused if o.truth is GroundTruth.OUTSIDE_TOLERANCE
        ),
        over_refusal=sum(
            1 for o in refused if o.truth is GroundTruth.WITHIN_TOLERANCE
        ),
        truth_unknown=sum(1 for o in items if not o.truth.is_known),
    )


@dataclass(frozen=True)
class RiskCoveragePoint:
    """One operating point of the curve: how much was accepted, and at what risk."""

    threshold: float
    coverage: float | None
    false_trust_rate: float | None
    supported: int
    false_trust: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "coverage": self.coverage,
            "false_trust_rate": self.false_trust_rate,
            "supported": self.supported,
            "false_trust": self.false_trust,
        }


def risk_coverage_curve(
    outcomes: Sequence[PredictionOutcome], thresholds: Sequence[float]
) -> tuple[RiskCoveragePoint, ...]:
    """Sweep an acceptance threshold over the declared margin and tally each point.

    A case is *accepted* at threshold ``t`` when it was SUPPORTED and its
    margin is at least ``t``. Cases with no margin are never accepted at any
    positive threshold: an absent margin is not a large one.

    The curve answers the commercial question directly -- how much coverage is
    bought by tolerating a given false-trust rate -- and it is a curve rather
    than a number because the trade is the product decision, not ours.
    """
    points: list[RiskCoveragePoint] = []
    total = len(outcomes)
    for threshold in thresholds:
        accepted = [
            o
            for o in outcomes
            if o.decision is TrustDecision.SUPPORTED
            and o.margin is not None
            and o.margin >= threshold
        ]
        wrong = sum(1 for o in accepted if o.truth is GroundTruth.OUTSIDE_TOLERANCE)
        right = sum(1 for o in accepted if o.truth is GroundTruth.WITHIN_TOLERANCE)
        points.append(
            RiskCoveragePoint(
                threshold=float(threshold),
                coverage=_rate(len(accepted), total),
                false_trust_rate=_rate(wrong, right + wrong),
                supported=len(accepted),
                false_trust=wrong,
            )
        )
    return tuple(points)


__all__ = [
    "GroundTruth",
    "PredictionOutcome",
    "RiskCoveragePoint",
    "RiskCoverageReport",
    "TrustDecision",
    "risk_coverage_curve",
    "summarise",
]
