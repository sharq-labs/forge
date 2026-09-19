from __future__ import annotations

import pytest

from engcore.scientific import Quantity
from engcore.scientific.equations import (
    BinaryExpression,
    BinaryOperator,
    Equation,
    EquationEvaluationError,
    EquationSymbol,
    LawAssumption,
    LawDefinition,
    Symbol,
)
from engcore.scientific.errors import InvalidScientificProblem


def ohms_law() -> LawDefinition:
    return LawDefinition(
        law_id="electrical.ohm",
        name="Ohm relation",
        equation=Equation(
            Symbol("voltage"),
            BinaryExpression(
                BinaryOperator.MULTIPLY,
                Symbol("current"),
                Symbol("resistance"),
            ),
        ),
        symbols=(
            EquationSymbol("voltage", "volt"),
            EquationSymbol("current", "ampere"),
            EquationSymbol("resistance", "ohm"),
        ),
        assumptions=(
            LawAssumption(
                "declared_applicability",
                "Applicability must be established by the owning domain model.",
            ),
        ),
        references=("internal-test-fixture",),
    )


def test_law_is_dimensionally_valid_and_round_trips():
    law = ohms_law()
    assert law.dimension_report().valid
    assert LawDefinition.from_dict(law.to_dict()) == law


def test_law_rejects_undeclared_symbol():
    with pytest.raises(InvalidScientificProblem, match="undeclared symbols"):
        LawDefinition(
            law_id="bad",
            name="bad",
            equation=Equation(Symbol("x"), Symbol("y")),
            symbols=(EquationSymbol("x", "meter"),),
        )


def test_law_rejects_unused_declared_symbol():
    with pytest.raises(InvalidScientificProblem, match="unused"):
        LawDefinition(
            law_id="bad",
            name="bad",
            equation=Equation(Symbol("x"), Symbol("x")),
            symbols=(
                EquationSymbol("x", "meter"),
                EquationSymbol("unused", "second"),
            ),
        )


def test_law_rejects_wrong_binding_dimension():
    law = ohms_law()
    with pytest.raises(EquationEvaluationError) as caught:
        law.evaluate(
            {
                "voltage": Quantity(10, "volt"),
                "current": Quantity(2, "meter"),
                "resistance": Quantity(5, "ohm"),
            }
        )
    assert caught.value.code == "binding_dimension_mismatch"


def test_law_requires_exact_binding_set():
    law = ohms_law()
    with pytest.raises(EquationEvaluationError) as caught:
        law.evaluate(
            {
                "voltage": Quantity(10, "volt"),
                "current": Quantity(2, "ampere"),
            }
        )
    assert caught.value.code == "binding_set_mismatch"


def test_law_evaluation_does_not_claim_scientific_support():
    law = ohms_law()
    result = law.evaluate(
        {
            "voltage": Quantity(10, "volt"),
            "current": Quantity(2, "ampere"),
            "resistance": Quantity(5, "ohm"),
        }
    )
    payload = result.to_dict()
    assert set(payload) == {"schema", "left", "right", "residual"}
    assert "verdict" not in payload
    assert "validated" not in payload
