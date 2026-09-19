"""Aleatoric uncertainty from independent physical replicates.

This producer is intentionally narrower than parameter propagation.  It accepts
only repeated observations of the same quantity, population and bound operating
context, with one independent specimen/run per observation and explicit
measurement uncertainty.  Missing replication stays UNKNOWN.

The interval is Wilks' distribution-free two-sided tolerance interval over the
replicate observations, conservatively widened by each observation's own
measurement interval.  It therefore bounds observed population variability
without pretending the measuring instrument had zero error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ..scientific.units.quantity import Quantity, dimensionality
from ._records import require_identifier, require_mapping, require_text, tagged_digest
from .parameter_uq import (
    TOLERANCE_CONFIDENCE,
    TOLERANCE_CONTENT,
    minimum_samples,
    wilks_confidence,
)

_TAG = "crafty.claims.aleatoric_replicates/1"
METHOD = "wilks_independent_replicate_tolerance"


@dataclass(frozen=True)
class ReplicateObservation:
    observation_id: str
    population_ref: str
    context_digest: str
    independence_group: str
    quantity: str
    value: Quantity
    measurement_uncertainty: Uncertainty

    def __post_init__(self) -> None:
        for label in (
            "observation_id",
            "population_ref",
            "context_digest",
            "independence_group",
        ):
            object.__setattr__(
                self, label, require_text(getattr(self, label), field=f"replicate.{label}")
            )
        object.__setattr__(
            self,
            "quantity",
            require_identifier(self.quantity, field="replicate.quantity"),
        )
        if not isinstance(self.value, Quantity):
            raise ValueError("replicate.value must be a Quantity")
        if not isinstance(self.measurement_uncertainty, Uncertainty):
            raise ValueError("replicate.measurement_uncertainty must be an Uncertainty")
        u = self.measurement_uncertainty
        if (
            u.kind is not UncertaintyKind.INTERVAL
            or UncertaintySource(u.source_kind) is not UncertaintySource.MEASUREMENT
        ):
            raise ValueError(
                "replicate measurement uncertainty must be an explicit MEASUREMENT interval"
            )
        low = u.lower.to(self.value.units).magnitude
        high = u.upper.to(self.value.units).magnitude
        if not low <= self.value.magnitude <= high:
            raise ValueError(
                "replicate measurement interval must contain the reported observation"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "population_ref": self.population_ref,
            "context_digest": self.context_digest,
            "independence_group": self.independence_group,
            "quantity": self.quantity,
            "value": self.value.to_dict(),
            "measurement_uncertainty": self.measurement_uncertainty.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReplicateObservation":
        payload = require_mapping(payload, field="replicate")
        return cls(
            payload["observation_id"],
            payload["population_ref"],
            payload["context_digest"],
            payload["independence_group"],
            payload["quantity"],
            Quantity.from_dict(payload["value"]),
            Uncertainty.from_dict(payload["measurement_uncertainty"]),
        )


@dataclass(frozen=True)
class AleatoricEstimate:
    quantified: bool
    quantity: str
    units: str
    population_ref: str
    context_digest: str
    nominal: float
    observations: tuple[ReplicateObservation, ...]
    content: float
    confidence: float | None
    lower: float | None
    upper: float | None
    failure_reason: str | None

    def to_uncertainty(self) -> Uncertainty:
        if not self.quantified:
            return Uncertainty.unknown(
                f"aleatoric uncertainty not quantified: {self.failure_reason}"
            )
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(self.lower, self.units),
            upper=Quantity(self.upper, self.units),
            confidence_level=self.confidence,
            source=f"replicate_population:{self.digest[:16]}",
            method=(
                f"{METHOD}: {len(self.observations)} independent replicates; "
                f"at least {self.content:.0%} population content at "
                f"{self.confidence:.4f} Wilks confidence"
            ),
            notes=(
                "Population/operating-context identities are exact. The range is "
                "conservatively widened by each replicate's calibrated measurement "
                "interval, so instrument error is not silently treated as zero."
            ),
            source_kind=UncertaintySource.MEASUREMENT,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": METHOD,
            "quantified": self.quantified,
            "quantity": self.quantity,
            "units": self.units,
            "population_ref": self.population_ref,
            "context_digest": self.context_digest,
            "nominal": self.nominal,
            "observations": [item.to_dict() for item in self.observations],
            "content": self.content,
            "confidence": self.confidence,
            "lower": self.lower,
            "upper": self.upper,
            "failure_reason": self.failure_reason,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


def estimate_aleatoric_replicates(
    observations: Sequence[ReplicateObservation],
    *,
    nominal: Quantity,
    content: float = TOLERANCE_CONTENT,
    required_confidence: float = TOLERANCE_CONFIDENCE,
) -> AleatoricEstimate:
    """Quantify population variability, or return an explicit UNKNOWN estimate."""
    items = tuple(observations)
    if not items:
        raise ValueError("aleatoric replicate study needs observations")
    if not isinstance(nominal, Quantity):
        raise ValueError("aleatoric nominal must be a Quantity")
    first = items[0]
    units = str(nominal.units)
    base = dict(
        quantity=first.quantity,
        units=units,
        population_ref=first.population_ref,
        context_digest=first.context_digest,
        nominal=nominal.magnitude,
        observations=items,
        content=float(content),
    )

    def unknown(reason: str, confidence: float | None = None) -> AleatoricEstimate:
        return AleatoricEstimate(
            quantified=False,
            confidence=confidence,
            lower=None,
            upper=None,
            failure_reason=reason,
            **base,
        )

    if not 0.0 < content < 1.0 or not 0.0 < required_confidence < 1.0:
        raise ValueError("aleatoric content/confidence must lie in (0,1)")
    if len({item.observation_id for item in items}) != len(items):
        return unknown("observation ids are not unique")
    if len({item.independence_group for item in items}) != len(items):
        return unknown(
            "replicates are not independent: an independence_group appears more than once"
        )
    for item in items:
        if item.quantity != first.quantity:
            return unknown("replicates do not measure one quantity")
        if item.population_ref != first.population_ref:
            return unknown("replicates do not belong to one declared population")
        if item.context_digest != first.context_digest:
            return unknown("replicates do not share one exact operating context")
        if dimensionality(item.value.units) != dimensionality(nominal.units):
            return unknown("replicate dimension does not match nominal quantity")

    floor = minimum_samples(content, required_confidence)
    if len(items) < floor:
        return unknown(
            f"{len(items)} independent replicates are insufficient; "
            f"{floor} are required for two-sided {content:.0%}/"
            f"{required_confidence:.0%} Wilks coverage"
        )

    gamma = wilks_confidence(len(items), content)
    lows: list[float] = []
    highs: list[float] = []
    for item in items:
        u = item.measurement_uncertainty
        try:
            lows.append(u.lower.to(units).magnitude)
            highs.append(u.upper.to(units).magnitude)
        except Exception:
            return unknown("a replicate measurement interval is dimensionally incompatible", gamma)
    lo, hi = min(lows), max(highs)
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return unknown("replicate envelope is not finite", gamma)
    nominal_value = nominal.magnitude
    if not lo <= nominal_value <= hi:
        return unknown(
            f"nominal value {nominal_value!r} {units} lies outside the "
            f"replicate envelope [{lo!r}, {hi!r}]",
            gamma,
        )

    return AleatoricEstimate(
        quantified=True,
        confidence=gamma,
        lower=lo,
        upper=hi,
        failure_reason=None,
        **base,
    )


__all__ = [
    "AleatoricEstimate",
    "METHOD",
    "ReplicateObservation",
    "estimate_aleatoric_replicates",
]
