from __future__ import annotations

from engcore.scientific.equations import (
    BinaryExpression,
    BinaryOperator,
    Equation,
    EquationSymbol,
    LawDefinition,
    Symbol,
    equation_fingerprint,
    law_fingerprint,
)


def make_law(resistance_unit: str = "ohm") -> LawDefinition:
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
            EquationSymbol("resistance", resistance_unit),
        ),
    )


def test_equation_fingerprint_is_stable_across_round_trip():
    law = make_law()
    rebuilt = Equation.from_dict(law.equation.to_dict())
    assert equation_fingerprint(rebuilt) == equation_fingerprint(law.equation)


def test_law_fingerprint_is_stable_across_round_trip():
    law = make_law()
    assert law_fingerprint(LawDefinition.from_dict(law.to_dict())) == law_fingerprint(law)


def test_law_fingerprint_changes_when_declared_scientific_contract_changes():
    baseline = make_law()
    changed = LawDefinition(
        law_id=baseline.law_id,
        name=baseline.name,
        equation=baseline.equation,
        symbols=(
            EquationSymbol("voltage", "millivolt"),
            EquationSymbol("current", "ampere"),
            EquationSymbol("resistance", "ohm"),
        ),
    )
    assert law_fingerprint(changed) != law_fingerprint(baseline)
