"""Explicit nondimensionalization by declared characteristic scales."""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidScientificProblem
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from .ast import BinaryExpression, BinaryOperator, Constant, Equation, Symbol
from .dimensions import infer_dimension, require_equation_dimensions, DimensionVector
from .transformations import substitute_equation


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


@dataclass(frozen=True)
class NondimensionalizationResult:
    equation: Equation
    symbol_units: dict[str,str]
    scales: tuple[VariableScale,...]
    equation_scale: Quantity


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
