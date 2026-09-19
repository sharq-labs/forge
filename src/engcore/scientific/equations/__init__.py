"""Universal equation and scientific-law IR."""

from .ast import (
    BinaryExpression,
    BinaryOperator,
    Constant,
    Equation,
    Expression,
    FunctionExpression,
    FunctionName,
    PowerExpression,
    Symbol,
    UnaryExpression,
    UnaryOperator,
    decode_expression,
    referenced_symbols,
)
from .dimensions import (
    DimensionReport,
    DimensionVector,
    assess_equation_dimensions,
    infer_dimension,
    require_equation_dimensions,
)
from .errors import EquationDimensionError, EquationEvaluationError, EquationIRError
from .evaluation import EquationEvaluation, evaluate_equation, evaluate_expression
from .law import EquationSymbol, LawAssumption, LawDefinition

__all__ = [
    "EquationIRError",
    "EquationDimensionError",
    "EquationEvaluationError",
    "Symbol",
    "Constant",
    "UnaryExpression",
    "BinaryExpression",
    "PowerExpression",
    "FunctionExpression",
    "Expression",
    "UnaryOperator",
    "BinaryOperator",
    "FunctionName",
    "Equation",
    "decode_expression",
    "referenced_symbols",
    "DimensionVector",
    "DimensionReport",
    "infer_dimension",
    "assess_equation_dimensions",
    "require_equation_dimensions",
    "EquationEvaluation",
    "evaluate_expression",
    "evaluate_equation",
    "EquationSymbol",
    "LawAssumption",
    "LawDefinition",
]
