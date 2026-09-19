"""Conservation declarations bound to actual coupling-edge transfers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity

CONSERVATION_TERM_BINDING_SCHEMA = schema_string("multiphysics_conservation_term_binding")
COUPLED_CONSERVATION_SCHEMA = schema_string("multiphysics_conservation")


class BalanceSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class TransferMeasure(str, Enum):
    SOURCE = "source"
    RECEIVED = "received"
    LOSS = "loss"


@dataclass(frozen=True)
class ConservationTermBinding:
    name: str
    edge_id: str
    side: BalanceSide
    measure: TransferMeasure
    loss_form: str = ""

    def __post_init__(self) -> None:
        for label in ("name", "edge_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"conservation term requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "side", BalanceSide(self.side))
        object.__setattr__(self, "measure", TransferMeasure(self.measure))
        object.__setattr__(self, "loss_form", str(self.loss_form).strip())
        if self.measure is TransferMeasure.LOSS and not self.loss_form:
            raise InvalidScientificProblem("LOSS conservation term requires loss_form")
        if self.measure is not TransferMeasure.LOSS and self.loss_form:
            raise InvalidScientificProblem("loss_form is valid only for LOSS terms")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONSERVATION_TERM_BINDING_SCHEMA,
            "name": self.name,
            "edge_id": self.edge_id,
            "side": self.side.value,
            "measure": self.measure.value,
            "loss_form": self.loss_form,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConservationTermBinding":
        require_schema(payload, CONSERVATION_TERM_BINDING_SCHEMA)
        return cls(
            payload["name"],
            payload["edge_id"],
            BalanceSide(payload["side"]),
            TransferMeasure(payload["measure"]),
            payload.get("loss_form", ""),
        )


@dataclass(frozen=True)
class CoupledConservation:
    balance_id: str
    terms: tuple[ConservationTermBinding, ...]
    tolerance: Quantity
    description: str = ""

    def __post_init__(self) -> None:
        balance_id = str(self.balance_id).strip()
        if not balance_id:
            raise InvalidScientificProblem("coupled conservation requires balance_id")
        terms = tuple(self.terms)
        if len(terms) < 2 or any(not isinstance(t, ConservationTermBinding) for t in terms):
            raise InvalidScientificProblem("coupled conservation requires at least two typed terms")
        names = [t.name for t in terms]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem("conservation term names must be unique")
        if not any(t.side is BalanceSide.LEFT for t in terms) or not any(
            t.side is BalanceSide.RIGHT for t in terms
        ):
            raise InvalidScientificProblem("conservation balance requires both left and right terms")
        if not isinstance(self.tolerance, Quantity) or self.tolerance.magnitude < 0.0:
            raise InvalidScientificProblem("conservation tolerance must be a non-negative Quantity")
        object.__setattr__(self, "balance_id", balance_id)
        object.__setattr__(self, "terms", tuple(sorted(terms, key=lambda t: t.name)))
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLED_CONSERVATION_SCHEMA,
            "balance_id": self.balance_id,
            "terms": [t.to_dict() for t in self.terms],
            "tolerance": self.tolerance.to_dict(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CoupledConservation":
        require_schema(payload, COUPLED_CONSERVATION_SCHEMA)
        return cls(
            balance_id=payload["balance_id"],
            terms=tuple(ConservationTermBinding.from_dict(t) for t in payload["terms"]),
            tolerance=Quantity.from_dict(payload["tolerance"]),
            description=payload.get("description", ""),
        )
