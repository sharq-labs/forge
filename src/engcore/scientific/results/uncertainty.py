"""Uncertainty representation — representation only, no UQ engine.

The governing rule: **do not pretend uncertainty exists when it was not
calculated.** ``UncertaintyKind.UNKNOWN`` is a first-class, explicitly
representable state, and it is the default. A missing uncertainty record and
a computed-but-zero uncertainty are different scientific statements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension

UNCERTAINTY_SCHEMA = schema_string("uncertainty")


class UncertaintyKind(str, Enum):
    UNKNOWN = "unknown"        # not evaluated — the honest default
    STANDARD = "standard"      # standard uncertainty (1-sigma style)
    INTERVAL = "interval"      # explicit lower/upper bounds


@dataclass(frozen=True)
class Uncertainty:
    """Uncertainty attached to one reported value."""

    kind: UncertaintyKind = UncertaintyKind.UNKNOWN
    standard_uncertainty: Quantity | None = None
    lower: Quantity | None = None
    upper: Quantity | None = None
    confidence_level: float | None = None
    source: str = ""
    method: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", UncertaintyKind(self.kind))

        for label in ("standard_uncertainty", "lower", "upper"):
            value = getattr(self, label)
            if value is not None and not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"uncertainty {label} must be a Quantity when given"
                )

        if self.confidence_level is not None:
            level = float(self.confidence_level)
            if not 0.0 < level < 1.0:
                raise ScientificCoreError(
                    "confidence_level must lie strictly between 0 and 1"
                )
            object.__setattr__(self, "confidence_level", level)

        if self.kind is UncertaintyKind.STANDARD:
            if self.standard_uncertainty is None:
                raise ScientificCoreError(
                    "STANDARD uncertainty requires standard_uncertainty"
                )
            if self.standard_uncertainty.magnitude < 0.0:
                raise ScientificCoreError(
                    "standard_uncertainty must be non-negative"
                )
            if not self.method:
                raise ScientificCoreError(
                    "STANDARD uncertainty must declare the method that "
                    "produced it — an unattributed estimate is not evidence"
                )
        elif self.kind is UncertaintyKind.INTERVAL:
            if self.lower is None or self.upper is None:
                raise ScientificCoreError(
                    "INTERVAL uncertainty requires both lower and upper"
                )
            require_same_dimension(
                self.lower, self.upper, context="uncertainty interval"
            )
            if self.upper.to(self.lower.units).magnitude < self.lower.magnitude:
                raise ScientificCoreError(
                    "uncertainty interval upper bound is below lower bound"
                )
            if not self.method:
                raise ScientificCoreError(
                    "INTERVAL uncertainty must declare its method"
                )
        else:  # UNKNOWN
            if any(
                v is not None
                for v in (self.standard_uncertainty, self.lower, self.upper)
            ):
                raise ScientificCoreError(
                    "UNKNOWN uncertainty must not carry values; use STANDARD "
                    "or INTERVAL when something was actually computed"
                )
            # `confidence_level` is a value too, and it was the one this rule
            # did not reach. The three checked above are the *estimates*; a
            # confidence level is the coverage probability attached to one, so
            # a record carrying it while carrying no interval states the
            # probability that a bound nobody computed contains the truth.
            #
            # That is exactly the shape this module exists to refuse. The
            # record round-trips, so the number reaches the wire beside
            # `"kind": "unknown"` and `"lower": null` -- and a consumer sizing
            # a coverage interval off the field reads 0.95 from a record whose
            # whole content is "nothing was evaluated". Nothing in this
            # repository does; the field is public and serialized, so the
            # refusal belongs at the constructor rather than in a convention
            # every future reader has to know.
            #
            # `source`, `method` and `notes` stay permitted: they are prose
            # about why nothing was computed, which is what an UNKNOWN record
            # is for. What is refused is a NUMBER that only means something
            # beside an estimate that is not there.
            if self.confidence_level is not None:
                raise ScientificCoreError(
                    f"UNKNOWN uncertainty carries confidence_level="
                    f"{self.confidence_level!r}. A confidence level is the "
                    f"coverage probability of an interval, and this record "
                    f"has none: it states the probability that a bound nobody "
                    f"computed contains the truth. Use INTERVAL with lower and "
                    f"upper when a bound was actually computed, or leave "
                    f"confidence_level unset -- `notes` is where an UNKNOWN "
                    f"record says why nothing was evaluated"
                )

    @property
    def is_quantified(self) -> bool:
        return self.kind is not UncertaintyKind.UNKNOWN

    @classmethod
    def unknown(cls, notes: str = "") -> "Uncertainty":
        return cls(kind=UncertaintyKind.UNKNOWN, notes=notes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNCERTAINTY_SCHEMA,
            "kind": self.kind.value,
            "standard_uncertainty": (
                self.standard_uncertainty.to_dict()
                if self.standard_uncertainty
                else None
            ),
            "lower": self.lower.to_dict() if self.lower else None,
            "upper": self.upper.to_dict() if self.upper else None,
            "confidence_level": self.confidence_level,
            "source": self.source,
            "method": self.method,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Uncertainty":
        require_schema(payload, UNCERTAINTY_SCHEMA)
        def _q(key):
            value = payload.get(key)
            return Quantity.from_dict(value) if value else None

        return cls(
            kind=UncertaintyKind(payload.get("kind", "unknown")),
            standard_uncertainty=_q("standard_uncertainty"),
            lower=_q("lower"),
            upper=_q("upper"),
            confidence_level=payload.get("confidence_level"),
            source=payload.get("source", ""),
            method=payload.get("method", ""),
            notes=payload.get("notes", ""),
        )
