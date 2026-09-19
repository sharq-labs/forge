"""Explicit nondimensionalization by declared characteristic scales."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .ast import BinaryExpression, BinaryOperator, Constant, Equation, Symbol
from .dimensions import infer_dimension, require_equation_dimensions, DimensionVector
from .transformations import substitute_equation

VARIABLE_SCALE_SCHEMA=schema_string("equation_variable_scale")
NONDIMENSIONALIZATION_SCHEMA=schema_string("equation_nondimensionalization")


@dataclass(frozen=True)
class VariableScale:
    symbol: str
    dimensionless_symbol: str
    scale: Quantity

    def __post_init__(self) -> None:
        symbol,hat=str(self.symbol).strip(),str(self.dimensionless_symbol).strip()
        if not symbol or not hat or symbol==hat or not isinstance(self.scale,Quantity):
            raise InvalidScientificProblem("variable scale requires distinct symbols and a Quantity scale")
        if self.scale.magnitude == 0:
            raise InvalidScientificProblem("nondimensional variable scale cannot be zero")
        object.__setattr__(self,"symbol",symbol)
        object.__setattr__(self,"dimensionless_symbol",hat)

    def to_dict(self)->dict[str,Any]:
        return {"schema":VARIABLE_SCALE_SCHEMA,"symbol":self.symbol,
                "dimensionless_symbol":self.dimensionless_symbol,"scale":self.scale.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"VariableScale":
        require_schema(payload,VARIABLE_SCALE_SCHEMA)
        return cls(payload["symbol"],payload["dimensionless_symbol"],Quantity.from_dict(payload["scale"]))


@dataclass(frozen=True)
class NondimensionalizationResult:
    equation: Equation
    symbol_units: Mapping[str,str]
    scales: tuple[VariableScale,...]
    equation_scale: Quantity

    def __post_init__(self)->None:
        if not isinstance(self.equation,Equation) or not isinstance(self.equation_scale,Quantity):
            raise InvalidScientificProblem("nondimensionalization result requires Equation and Quantity scale")
        scales=tuple(self.scales)
        if any(not isinstance(s,VariableScale) for s in scales):
            raise InvalidScientificProblem("nondimensionalization scales must be VariableScale records")
        units={str(k):str(v) for k,v in dict(self.symbol_units).items()}
        for scale in scales:
            if units.get(scale.dimensionless_symbol)!="dimensionless":
                raise InvalidScientificProblem(
                    f"dimensionless symbol {scale.dimensionless_symbol!r} is not declared dimensionless"
                )
        require_equation_dimensions(self.equation,units)
        left=infer_dimension(self.equation.left,units)
        if not left.is_dimensionless:
            raise InvalidScientificProblem("nondimensionalized equation must be dimensionless")
        object.__setattr__(self,"symbol_units",MappingProxyType(units))
        object.__setattr__(self,"scales",scales)

    def to_dict(self)->dict[str,Any]:
        return {"schema":NONDIMENSIONALIZATION_SCHEMA,"equation":self.equation.to_dict(),
                "symbol_units":dict(sorted(self.symbol_units.items())),
                "scales":[s.to_dict() for s in self.scales],
                "equation_scale":self.equation_scale.to_dict()}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"NondimensionalizationResult":
        require_schema(payload,NONDIMENSIONALIZATION_SCHEMA)
        return cls(Equation.from_dict(payload["equation"]),dict(payload["symbol_units"]),
                   tuple(VariableScale.from_dict(s) for s in payload.get("scales",())),
                   Quantity.from_dict(payload["equation_scale"]))


def nondimensionalize_equation(
    equation: Equation,
    symbol_units: dict[str,str],
    scales: tuple[VariableScale,...],
    equation_scale: Quantity,
) -> NondimensionalizationResult:
    require_equation_dimensions(equation,symbol_units)
    if not isinstance(equation_scale,Quantity) or equation_scale.magnitude==0:
        raise InvalidScientificProblem("nondimensional equation scale must be a nonzero Quantity")
    left_dim=infer_dimension(equation.left,symbol_units)
    if DimensionVector.from_unit(equation_scale.units)!=left_dim:
        raise InvalidScientificProblem("equation scale does not have the equation residual dimension")
    replacements={}
    new_units=dict(symbol_units)
    hats=set()
    for item in scales:
        if item.symbol not in symbol_units:
            raise InvalidScientificProblem(f"scale references undeclared symbol {item.symbol!r}")
        require_same_dimension(item.scale,symbol_units[item.symbol],context=f"scale for {item.symbol!r}")
        if item.dimensionless_symbol in new_units or item.dimensionless_symbol in hats:
            raise InvalidScientificProblem("dimensionless symbol collides with an existing/declaration symbol")
        hats.add(item.dimensionless_symbol)
        replacements[item.symbol]=BinaryExpression(
            BinaryOperator.MULTIPLY,Constant(item.scale),Symbol(item.dimensionless_symbol)
        )
        del new_units[item.symbol]
        new_units[item.dimensionless_symbol]="dimensionless"
    substituted=substitute_equation(equation,replacements)
    residual=BinaryExpression(BinaryOperator.SUBTRACT,substituted.left,substituted.right)
    normalized=BinaryExpression(BinaryOperator.DIVIDE,residual,Constant(equation_scale))
    result=Equation(normalized,Constant(Quantity.dimensionless(0.0)))
    require_equation_dimensions(result,new_units)
    return NondimensionalizationResult(result,new_units,tuple(scales),equation_scale)
