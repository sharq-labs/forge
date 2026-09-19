from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engcore.scientific.equations import (
    BinaryExpression,
    BinaryOperator,
    EquationDimensionError,
    FunctionExpression,
    FunctionName,
    Symbol,
    decode_expression,
    infer_dimension,
)

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src" / "engcore" / "scientific" / "equations"


def test_expression_payload_is_data_not_python_code():
    payload = {
        "schema": "equation_symbol/1",
        "name": "__import__('os').system('echo pwned')",
    }
    expression = decode_expression(payload)
    assert isinstance(expression, Symbol)
    with pytest.raises(EquationDimensionError) as caught:
        infer_dimension(expression, {})
    assert caught.value.code == "unknown_symbol"


def test_equation_package_contains_no_eval_or_exec_calls():
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec"}, path


def test_dimension_mismatch_cannot_be_hidden_inside_nested_addition():
    expression = BinaryExpression(
        BinaryOperator.MULTIPLY,
        Symbol("scale"),
        BinaryExpression(BinaryOperator.ADD, Symbol("length"), Symbol("time")),
    )
    with pytest.raises(EquationDimensionError) as caught:
        infer_dimension(
            expression,
            {"scale": "dimensionless", "length": "meter", "time": "second"},
        )
    assert caught.value.code == "dimension_mismatch"


def test_transcendental_dimension_rule_cannot_be_bypassed_by_nesting():
    expression = FunctionExpression(
        FunctionName.LOG,
        BinaryExpression(
            BinaryOperator.MULTIPLY,
            Symbol("length"),
            Symbol("scale"),
        ),
    )
    with pytest.raises(EquationDimensionError) as caught:
        infer_dimension(
            expression,
            {"length": "meter", "scale": "dimensionless"},
        )
    assert caught.value.code == "dimensionless_required"
