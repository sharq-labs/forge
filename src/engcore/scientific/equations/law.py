"""Domain-neutral scientific law contract built on the equation IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, UnitCompatibilityError
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension, require_unit
from .ast import Equation
from .dimensions import DimensionReport, assess_equation_dimensions, require_equation_dimensions
from .errors import EquationEvaluationError
from .evaluation import EquationEvaluation, evaluate_equation

EQUATION_SYMBOL_SPEC_SCHEMA = schema_string("equation_symbol_spec")
LAW_ASSUMPTION_SCHEMA = schema_string("law_assumption")
LAW_DEFINITION_SCHEMA = schema_string("scientific_law_definition")


@dataclass(frozen=True)
class EquationSymbol:
    name: str
    unit: str
    description: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem("law symbol name must be non-empty")
        object.__setattr__(self, "name", name)
        object.__setattr__(
            self,
            "unit",
            require_unit(self.unit, context=f"law symbol {name!r}"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EQUATION_SYMBOL_SPEC_SCHEMA,
            "name": self.name,
            "unit": self.unit,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EquationSymbol":
        require_schema(payload, EQUATION_SYMBOL_SPEC_SCHEMA)
        return cls(
            name=payload["name"],
            unit=payload["unit"],
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class LawAssumption:
    assumption_id: str
    statement: str

    def __post_init__(self) -> None:
        identifier = str(self.assumption_id).strip()
        statement = str(self.statement).strip()
        if not identifier:
            raise InvalidScientificProblem("law assumption id must be non-empty")
        if not statement:
            raise InvalidScientificProblem("law assumption statement must be non-empty")
        object.__setattr__(self, "assumption_id", identifier)
        object.__setattr__(self, "statement", statement)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LAW_ASSUMPTION_SCHEMA,
            "assumption_id": self.assumption_id,
            "statement": self.statement,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LawAssumption":
        require_schema(payload, LAW_ASSUMPTION_SCHEMA)
        return cls(
            assumption_id=payload["assumption_id"],
            statement=payload["statement"],
        )


@dataclass(frozen=True)
class LawDefinition:
    law_id: str
    name: str
    equation: Equation
    symbols: tuple[EquationSymbol, ...]
    assumptions: tuple[LawAssumption, ...] = ()
    description: str = ""
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        law_id = str(self.law_id).strip()
        name = str(self.name).strip()
        if not law_id or not name:
            raise InvalidScientificProblem("scientific law requires non-empty id and name")
        if not isinstance(self.equation, Equation):
            raise InvalidScientificProblem("scientific law requires a typed Equation")
        object.__setattr__(self, "law_id", law_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "symbols", tuple(self.symbols))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        refs = tuple(str(ref).strip() for ref in self.references)
        if any(not ref for ref in refs):
            raise InvalidScientificProblem("law references must be non-empty strings")
        if len(set(refs)) != len(refs):
            raise InvalidScientificProblem("law references contain duplicates")
        object.__setattr__(self, "references", refs)

        names = [symbol.name for symbol in self.symbols]
        if len(set(names)) != len(names):
            raise InvalidScientificProblem("scientific law declares duplicate symbols")

        assumption_ids = [item.assumption_id for item in self.assumptions]
        if len(set(assumption_ids)) != len(assumption_ids):
            raise InvalidScientificProblem("scientific law declares duplicate assumption ids")

        declared = set(names)
        referenced = set(self.equation.symbols)
        missing = sorted(referenced - declared)
        unused = sorted(declared - referenced)
        if missing:
            raise InvalidScientificProblem(
                f"scientific law references undeclared symbols {missing}"
            )
        if unused:
            raise InvalidScientificProblem(
                f"scientific law declares symbols unused by its equation {unused}"
            )

        require_equation_dimensions(self.equation, self.symbol_units)

    @property
    def symbol_units(self) -> dict[str, str]:
        return {symbol.name: symbol.unit for symbol in self.symbols}

    def dimension_report(self) -> DimensionReport:
        return assess_equation_dimensions(self.equation, self.symbol_units)

    def evaluate(self, bindings: Mapping[str, Quantity]) -> EquationEvaluation:
        required = set(self.symbol_units)
        provided = set(bindings)
        if required != provided:
            raise EquationEvaluationError(
                "binding_set_mismatch",
                f"law {self.law_id!r} requires bindings {sorted(required)}, "
                f"received {sorted(provided)}",
            )
        for name, expected_unit in self.symbol_units.items():
            value = bindings[name]
            if not isinstance(value, Quantity):
                raise EquationEvaluationError(
                    "untyped_binding",
                    f"law symbol {name!r} requires Quantity, got {type(value).__name__}",
                )
            try:
                require_same_dimension(
                    value,
                    expected_unit,
                    context=f"law {self.law_id!r} symbol {name!r}",
                )
            except UnitCompatibilityError as exc:
                raise EquationEvaluationError("binding_dimension_mismatch", str(exc)) from exc
        return evaluate_equation(self.equation, bindings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LAW_DEFINITION_SCHEMA,
            "law_id": self.law_id,
            "name": self.name,
            "equation": self.equation.to_dict(),
            "symbols": [symbol.to_dict() for symbol in self.symbols],
            "assumptions": [item.to_dict() for item in self.assumptions],
            "description": self.description,
            "references": list(self.references),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LawDefinition":
        require_schema(payload, LAW_DEFINITION_SCHEMA)
        return cls(
            law_id=payload["law_id"],
            name=payload["name"],
            equation=Equation.from_dict(payload["equation"]),
            symbols=tuple(
                EquationSymbol.from_dict(item) for item in payload.get("symbols", ())
            ),
            assumptions=tuple(
                LawAssumption.from_dict(item)
                for item in payload.get("assumptions", ())
            ),
            description=payload.get("description", ""),
            references=tuple(payload.get("references", ())),
        )
