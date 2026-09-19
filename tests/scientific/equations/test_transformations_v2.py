import pytest

from engcore.scientific.equations import (
    BinaryExpression, BinaryOperator, Equation, Symbol, TransformationPredicate,
    TransformationResult, canonicalize_equation, isolate_symbol,
    structurally_equivalent,
)
from engcore.scientific.errors import InvalidScientificProblem


def test_commutative_canonicalization_proves_structural_equivalence():
    a=Equation(BinaryExpression(BinaryOperator.ADD,Symbol("a"),Symbol("b")),Symbol("c"))
    b=Equation(BinaryExpression(BinaryOperator.ADD,Symbol("b"),Symbol("a")),Symbol("c"))
    assert structurally_equivalent(a,b)
    assert canonicalize_equation(a)==canonicalize_equation(b)


def test_safe_symbol_isolation_records_nonzero_side_condition():
    equation=Equation(
        BinaryExpression(BinaryOperator.MULTIPLY,Symbol("R"),Symbol("I")),
        Symbol("V"),
    )
    result=isolate_symbol(equation,"I")
    assert result.equation.left==Symbol("I")
    assert result.conditions and result.conditions[0].predicate is TransformationPredicate.NONZERO
    assert TransformationResult.from_dict(result.to_dict())==result


def test_isolation_refuses_multiple_target_occurrences():
    equation=Equation(
        BinaryExpression(BinaryOperator.ADD,Symbol("x"),Symbol("x")),Symbol("y")
    )
    with pytest.raises(InvalidScientificProblem,match="exactly one"):
        isolate_symbol(equation,"x")
