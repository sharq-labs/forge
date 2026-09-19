from __future__ import annotations

import pytest

from engcore.scientific.equations import (
    Equation,
    EquationSymbol,
    LawDefinition,
    LawIdentityError,
    LawReference,
    Symbol,
)


def make_law(unit: str = "meter") -> LawDefinition:
    return LawDefinition(
        law_id="test.identity",
        name="Identity relation",
        equation=Equation(Symbol("left"), Symbol("right")),
        symbols=(
            EquationSymbol("left", unit),
            EquationSymbol("right", unit),
        ),
    )


def test_law_reference_round_trip_and_verification():
    law = make_law()
    reference = LawReference.from_law(law)
    rebuilt = LawReference.from_dict(reference.to_dict())
    assert rebuilt == reference
    rebuilt.verify(law)


def test_law_reference_rejects_changed_contract_under_same_id():
    reference = LawReference.from_law(make_law("meter"))
    with pytest.raises(LawIdentityError) as caught:
        reference.verify(make_law("second"))
    assert caught.value.code == "law_fingerprint_mismatch"


def test_law_reference_rejects_wrong_id():
    reference = LawReference.from_law(make_law())
    other = LawDefinition(
        law_id="other.identity",
        name="Identity relation",
        equation=Equation(Symbol("left"), Symbol("right")),
        symbols=(
            EquationSymbol("left", "meter"),
            EquationSymbol("right", "meter"),
        ),
    )
    with pytest.raises(LawIdentityError) as caught:
        reference.verify(other)
    assert caught.value.code == "law_id_mismatch"


def test_law_reference_refuses_non_digest_text():
    with pytest.raises(LawIdentityError) as caught:
        LawReference("x", "not-a-digest")
    assert caught.value.code == "invalid_law_reference"
