"""Conservation declarations bound to executed multiphysics transfers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..semantics import ConservedQuantity, extend_payload, semantic_extension
from ..units.quantity import Quantity, require_spread_unit

CONSERVATION_TERM_BINDING_SCHEMA = schema_string(
    "multiphysics_conservation_term_binding"
)
COUPLED_CONSERVATION_SCHEMA = schema_string(
    "multiphysics_conservation"
)


class BalanceSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class TransferMeasure(str, Enum):
    SOURCE = "source"
    RECEIVED = "received"
    LOSS = "loss"


class ContributionKind(str, Enum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"
    SOURCE = "source"
    LOSS = "loss"
    ACCUMULATION = "accumulation"


@dataclass(frozen=True)
class ConservationTermBinding:
    """One term in a balance, read from a concrete coupling transfer."""

    name: str
    edge_id: str
    side: BalanceSide
    measure: TransferMeasure
    loss_form: str = ""
    contribution: ContributionKind | None = None

    def __post_init__(self) -> None:
        for label in ("name", "edge_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"conservation term requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(self, "side", BalanceSide(self.side))
        object.__setattr__(
            self, "measure", TransferMeasure(self.measure)
        )
        loss_form = str(self.loss_form).strip()
        object.__setattr__(self, "loss_form", loss_form)
        if self.measure is TransferMeasure.LOSS and not loss_form:
            raise InvalidScientificProblem(
                "LOSS conservation term requires loss_form"
            )
        if self.measure is not TransferMeasure.LOSS and loss_form:
            raise InvalidScientificProblem(
                "loss_form is valid only for LOSS terms"
            )
        if self.contribution is not None:
            kind = ContributionKind(self.contribution)
            object.__setattr__(self, "contribution", kind)
            expected = BalanceSide.LEFT if kind in (ContributionKind.INFLOW, ContributionKind.SOURCE) else BalanceSide.RIGHT
            if self.side is not expected:
                raise InvalidScientificProblem("conservation contribution is on the wrong equation side")
            if (kind is ContributionKind.LOSS) != (self.measure is TransferMeasure.LOSS):
                raise InvalidScientificProblem("a declared loss contribution requires the realized LOSS measure")

    def to_dict(self) -> dict[str, Any]:
        return extend_payload({
            "schema": CONSERVATION_TERM_BINDING_SCHEMA,
            "name": self.name,
            "edge_id": self.edge_id,
            "side": self.side.value,
            "measure": self.measure.value,
            "loss_form": self.loss_form,
        }, "contribution", self.contribution)

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ConservationTermBinding":
        raw_contribution = semantic_extension(payload, CONSERVATION_TERM_BINDING_SCHEMA, "contribution")
        return cls(
            name=payload["name"],
            edge_id=payload["edge_id"],
            side=BalanceSide(payload["side"]),
            measure=TransferMeasure(payload["measure"]),
            loss_form=payload.get("loss_form", ""),
            contribution=raw_contribution,
        )


@dataclass(frozen=True)
class CoupledConservation:
    """A domain-neutral balance whose terms are realized transfers."""

    balance_id: str
    terms: tuple[ConservationTermBinding, ...]
    tolerance: Quantity
    description: str = ""
    conserved_quantity: ConservedQuantity | None = None

    def __post_init__(self) -> None:
        balance_id = str(self.balance_id).strip()
        if not balance_id:
            raise InvalidScientificProblem(
                "coupled conservation requires balance_id"
            )
        terms = tuple(self.terms)
        if len(terms) < 2 or any(
            not isinstance(term, ConservationTermBinding)
            for term in terms
        ):
            raise InvalidScientificProblem(
                "coupled conservation requires at least two typed terms"
            )
        names = [term.name for term in terms]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem(
                "conservation term names must be unique"
            )
        if not any(
            term.side is BalanceSide.LEFT for term in terms
        ) or not any(
            term.side is BalanceSide.RIGHT for term in terms
        ):
            raise InvalidScientificProblem(
                "conservation balance requires both left and right terms"
            )
        if (
            not isinstance(self.tolerance, Quantity)
            or self.tolerance.magnitude < 0.0
        ):
            raise InvalidScientificProblem(
                "conservation tolerance must be a non-negative Quantity"
            )
        require_spread_unit(
            self.tolerance.units,
            context=f"coupled conservation {balance_id!r}",
        )
        object.__setattr__(self, "balance_id", balance_id)
        object.__setattr__(
            self,
            "terms",
            tuple(sorted(terms, key=lambda term: term.name)),
        )
        object.__setattr__(
            self, "description", str(self.description).strip()
        )
        if self.conserved_quantity is not None:
            if not isinstance(self.conserved_quantity, ConservedQuantity):
                raise InvalidScientificProblem("coupled balance requires a typed conserved quantity")
            if self.tolerance.dimensionality != Quantity(1, self.conserved_quantity.unit).dimensionality:
                raise InvalidScientificProblem("balance tolerance and conserved measure dimensions differ")
            if any(term.contribution is None for term in terms):
                raise InvalidScientificProblem("typed balances require explicit contribution kinds")
        elif any(term.contribution is not None for term in terms):
            raise InvalidScientificProblem("typed contributions require a typed conserved balance")

    def to_dict(self) -> dict[str, Any]:
        return extend_payload({
            "schema": COUPLED_CONSERVATION_SCHEMA,
            "balance_id": self.balance_id,
            "terms": [term.to_dict() for term in self.terms],
            "tolerance": self.tolerance.to_dict(),
            "description": self.description,
        }, "conserved_quantity", self.conserved_quantity)

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "CoupledConservation":
        raw_quantity = semantic_extension(payload, COUPLED_CONSERVATION_SCHEMA, "conserved_quantity")
        return cls(
            balance_id=payload["balance_id"],
            terms=tuple(
                ConservationTermBinding.from_dict(term)
                for term in payload["terms"]
            ),
            tolerance=Quantity.from_dict(payload["tolerance"]),
            description=payload.get("description", ""),
            conserved_quantity=None if raw_quantity is None else ConservedQuantity.from_dict(raw_quantity),
        )
