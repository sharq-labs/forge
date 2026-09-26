"""Bounded fluid-property records (BIG 11): fluid state -> provider-computed property.

Solid material semantics (:mod:`.properties`) are sourced claims with declared
applicability.  Fluid thermophysical properties from an equation-of-state
library are a different kind of datum: COMPUTED by a provider from an explicit
fluid identity and two independent state variables.  They enter Forge only as
:class:`FluidPropertyRecord` -- bound to the exact fluid state, the property
request and the provider execution identity -- classified
``provider_derived_property_not_measurement`` with UNKNOWN uncertainty unless the
provider supplies a stated one.  This module names no provider.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..scenarios.contracts import NamedQuantity
from ..scientific.errors import InvalidScientificProblem
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity

CLASSIFICATION = "provider_derived_property_not_measurement"


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class FluidIdentity:
    """An exact fluid: a pure substance id or a declared mixture with mole fractions."""

    fluid_id: str
    components: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not str(self.fluid_id or "").strip():
            raise InvalidScientificProblem("a fluid needs an identity")
        comps = tuple(self.components)
        if comps and abs(sum(x for _, x in comps) - 1.0) > 1e-12:
            raise InvalidScientificProblem("mixture mole fractions must sum to one; nothing is normalised silently")

    def to_dict(self) -> dict[str, Any]:
        return {"fluid_id": self.fluid_id, "components": [[c, repr(x)] for c, x in self.components]}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class FluidState:
    """Exactly two independent intensive state variables (e.g. temperature + pressure)."""

    fluid: FluidIdentity
    conditions: tuple[NamedQuantity, NamedQuantity]

    def __post_init__(self) -> None:
        conds = tuple(self.conditions)
        if len(conds) != 2 or len({c.quantity_id for c in conds}) != 2:
            raise InvalidScientificProblem("a fluid state needs exactly two distinct independent variables; none is defaulted")
        object.__setattr__(self, "conditions", tuple(sorted(conds, key=lambda c: c.quantity_id)))

    def condition(self, quantity_id: str) -> NamedQuantity | None:
        return next((c for c in self.conditions if c.quantity_id == quantity_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {"fluid": self.fluid.to_dict(), "conditions": [c.to_dict() for c in self.conditions]}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class FluidPropertyRecord:
    property_id: str
    state_digest: str
    status: str  # "known" | "unknown"
    value: Quantity | None
    provider_execution_identity: str
    provider: str
    provider_version: str
    request: Mapping[str, Any]
    reason: str = ""
    uncertainty: Uncertainty = Uncertainty.unknown("equation-of-state uncertainty is not propagated by the provider adapter")

    def __post_init__(self) -> None:
        if (self.status == "known") != (self.value is not None):
            raise InvalidScientificProblem("a known fluid property has a value; an unknown one has none")
        if len(self.provider_execution_identity) != 64:
            raise InvalidScientificProblem("a fluid property is bound to a provider execution identity")

    @property
    def classification(self) -> str:
        return CLASSIFICATION

    def named(self) -> NamedQuantity | None:
        return None if self.value is None else NamedQuantity(self.property_id, self.value, self.uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {"classification": CLASSIFICATION, "property_id": self.property_id, "state_digest": self.state_digest,
                "status": self.status, "value": None if self.value is None else self.value.to_dict(),
                "provider_execution_identity": self.provider_execution_identity, "provider": self.provider,
                "provider_version": self.provider_version, "request": dict(self.request), "reason": self.reason,
                "uncertainty": self.uncertainty.to_dict()}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())
