from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..conservation import BalanceTerm, ConservationBalance
from ..errors import InvalidScientificProblem
from ..units.quantity import Quantity
from .ast import Expression
from .dimensions import DimensionVector, infer_dimension
from .evaluation import evaluate_expression


@dataclass(frozen=True)
class SymbolicBalanceTerm:
    name: str
    expression: Expression
    evidence: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem(
                "symbolic conservation term requires a name"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "evidence", str(self.evidence).strip())


@dataclass(frozen=True)
class SymbolicConservationBalance:
    balance_id: str
    left: tuple[SymbolicBalanceTerm, ...]
    right: tuple[SymbolicBalanceTerm, ...]
    tolerance: Quantity
    symbol_units: Mapping[str, str]
    description: str = ""
    reference: str = ""

    def __post_init__(self) -> None:
        balance_id = str(self.balance_id).strip()
        left = tuple(self.left)
        right = tuple(self.right)
        if not balance_id or not (left or right):
            raise InvalidScientificProblem(
                "symbolic conservation balance requires id and terms"
            )
        if any(
            not isinstance(term, SymbolicBalanceTerm)
            for term in left + right
        ):
            raise InvalidScientificProblem(
                "symbolic conservation terms must be typed"
            )
        names = [term.name for term in left + right]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem(
                "symbolic conservation term names must be unique"
            )
        units = dict(self.symbol_units)
        dimensions = [
            infer_dimension(term.expression, units)
            for term in left + right
        ]
        tolerance_dimension = DimensionVector.from_unit(self.tolerance.units)
        if any(dimension != tolerance_dimension for dimension in dimensions):
            raise InvalidScientificProblem(
                "symbolic conservation terms and tolerance must share one dimension"
            )
        object.__setattr__(self, "balance_id", balance_id)
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)
        object.__setattr__(self, "symbol_units", units)

    def evaluate(
        self,
        bindings: Mapping[str, Quantity],
        *,
        derivative_bindings: Mapping[str, Quantity] | None = None,
    ) -> ConservationBalance:
        def evaluated(
            terms: tuple[SymbolicBalanceTerm, ...],
        ) -> tuple[BalanceTerm, ...]:
            return tuple(
                BalanceTerm(
                    term.name,
                    evaluate_expression(
                        term.expression,
                        bindings,
                        derivative_bindings=derivative_bindings,
                    ),
                    term.evidence,
                )
                for term in terms
            )

        return ConservationBalance(
            self.balance_id,
            evaluated(self.left),
            evaluated(self.right),
            self.tolerance,
            self.description,
            self.reference,
        )
