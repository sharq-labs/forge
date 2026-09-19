"""Universal equation and scientific-law IR."""

from .ast import (
    BinaryExpression,
    BinaryOperator,
    Constant,
    DerivativeExpression,
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
from .errors import (
    EquationDimensionError,
    EquationEvaluationError,
    EquationIRError,
    LawIdentityError,
)
from .evaluation import EquationEvaluation, evaluate_equation, evaluate_expression
from .fingerprint import equation_fingerprint, law_fingerprint
from .law import EquationSymbol, LawAssumption, LawDefinition
from .reference import LawReference
from .registry import LawRegistry

__all__ = [
    "EquationIRError",
    "EquationDimensionError",
    "EquationEvaluationError",
    "LawIdentityError",
    "Symbol",
    "Constant",
    "DerivativeExpression",
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
    "equation_fingerprint",
    "law_fingerprint",
    "EquationSymbol",
    "LawAssumption",
    "LawDefinition",
    "LawReference",
    "LawRegistry",
]

from .constraints import (
    ConstraintEvaluation, ExpressionConstraint, RelationOperator, evaluate_constraint,
)
from .assumptions import (
    AssumptionAssessment, AssumptionSet, AssumptionStatus, CheckableAssumption,
    assess_assumption,
)
from .conditions import ConditionBinding, ConditionKind, EquationCondition, evaluate_condition
from .residuals import ResidualDefinition, residual_expression
from .transformations import (
    TransformationCondition, TransformationPredicate, TransformationResult,
    canonicalize, canonicalize_equation, isolate_symbol, scale_equation,
    structurally_equivalent, substitute, substitute_equation,
)
from .nondimensional import (
    NondimensionalizationResult, VariableScale, nondimensionalize_equation,
)
from .differential import (
    DifferentialProblem, DifferentialProblemKind, derivative, laplacian,
    ordinary_derivative, partial_derivative,
)
from .law_system import ScientificLawSystem

__all__ += [
    "RelationOperator","ExpressionConstraint","ConstraintEvaluation","evaluate_constraint",
    "AssumptionStatus","CheckableAssumption","AssumptionAssessment","AssumptionSet",
    "assess_assumption","ConditionKind","ConditionBinding","EquationCondition",
    "evaluate_condition","ResidualDefinition","residual_expression",
    "TransformationPredicate","TransformationCondition","TransformationResult",
    "canonicalize","canonicalize_equation","structurally_equivalent","substitute",
    "substitute_equation","isolate_symbol","scale_equation","VariableScale",
    "NondimensionalizationResult","nondimensionalize_equation","DifferentialProblemKind",
    "DifferentialProblem","derivative","ordinary_derivative","partial_derivative",
    "laplacian","ScientificLawSystem",
]
