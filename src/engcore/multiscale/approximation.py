"""Multi-timescale approximation ledger: separate components, never one score.

Every component is QUANTIFIED (with a bound and its basis), UNKNOWN (with a
reason) or NOT_APPLICABLE (with a reason).  A missing quantification is
UNKNOWN -- never zero.  A comparison against a more temporally resolved
numerical reference is recorded as an OBSERVATION for one scenario and
horizon; it is not a bound, not truth and not validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity


class ErrorComponent(str, Enum):
    NUMERICAL_SOLVER = "numerical_solver"
    TIME_INTEGRATION = "time_integration"
    MAPPING = "mapping"
    AGGREGATION = "aggregation"
    REPRESENTATIVE_WINDOW = "representative_window"
    MODEL_UNCERTAINTY = "model_uncertainty"
    MODEL_DISCREPANCY = "model_discrepancy"


class ComponentStatus(str, Enum):
    QUANTIFIED = "quantified"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ApproximationEntry:
    component: ErrorComponent
    status: ComponentStatus
    basis: str
    bound: Quantity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", ErrorComponent(self.component))
        object.__setattr__(self, "status", ComponentStatus(self.status))
        if (self.status is ComponentStatus.QUANTIFIED) != (self.bound is not None):
            raise InvalidScientificProblem("a bound is present exactly when a component is QUANTIFIED")
        if not str(self.basis or "").strip():
            raise InvalidScientificProblem("every approximation entry states its basis")

    def to_dict(self) -> dict[str, Any]:
        return {"component": self.component.value, "status": self.status.value, "basis": self.basis,
                "bound": None if self.bound is None else self.bound.to_dict()}


@dataclass(frozen=True)
class ReferenceDiscrepancy:
    """Observed difference against a MORE TEMPORALLY RESOLVED numerical reference."""

    quantity: str
    reference_value: Quantity
    multiscale_value: Quantity
    scope: str

    @property
    def absolute(self) -> float:
        return abs(self.multiscale_value.magnitude_in(self.reference_value.units) - self.reference_value.magnitude)

    @property
    def relative(self) -> float | None:
        ref = self.reference_value.magnitude
        return None if ref == 0 else self.absolute / abs(ref)

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "more_temporally_resolved_numerical_reference_comparison_not_validation",
                "quantity": self.quantity, "reference_value": self.reference_value.to_dict(),
                "multiscale_value": self.multiscale_value.to_dict(), "absolute": repr(self.absolute),
                "relative": None if self.relative is None else repr(self.relative), "scope": self.scope}


@dataclass(frozen=True)
class ApproximationLedger:
    entries: tuple[ApproximationEntry, ...]
    observations: tuple[ReferenceDiscrepancy, ...] = ()

    def __post_init__(self) -> None:
        got = sorted(e.component.value for e in self.entries)
        if got != sorted(c.value for c in ErrorComponent):
            raise InvalidScientificProblem("the approximation ledger carries exactly one entry per error component")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda e: e.component.value)))

    def entry(self, component: ErrorComponent) -> ApproximationEntry:
        return next(e for e in self.entries if e.component is ErrorComponent(component))

    def with_observation(self, observation: ReferenceDiscrepancy) -> "ApproximationLedger":
        # An observation never changes a component's status: one comparison
        # at one horizon is not a bound on the representative-window error.
        return ApproximationLedger(self.entries, self.observations + (observation,))

    def to_dict(self) -> dict[str, Any]:
        return {"classification": "approximation_ledger_components_not_a_confidence_score",
                "entries": [e.to_dict() for e in self.entries], "observations": [o.to_dict() for o in self.observations]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())
