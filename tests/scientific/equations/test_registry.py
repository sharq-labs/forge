from __future__ import annotations

import pytest

from engcore.scientific.equations import (
    Equation,
    EquationSymbol,
    LawDefinition,
    LawIdentityError,
    LawRegistry,
    Symbol,
)
from engcore.scientific.errors import DuplicateRegistrationError


def law(law_id: str) -> LawDefinition:
    return LawDefinition(
        law_id=law_id,
        name=law_id,
        equation=Equation(Symbol("x"), Symbol("y")),
        symbols=(
            EquationSymbol("x", "meter"),
            EquationSymbol("y", "meter"),
        ),
    )


def test_registry_is_explicit_and_returns_stable_sorted_references():
    registry = LawRegistry([law("z"), law("a")])
    assert len(registry) == 2
    assert [item.law_id for item in registry.references()] == ["a", "z"]
    assert registry.reference("a").law_id == "a"


def test_registry_refuses_duplicate_identity_even_if_content_matches():
    registry = LawRegistry([law("same")])
    with pytest.raises(DuplicateRegistrationError):
        registry.register(law("same"))


def test_registry_missing_law_is_explicit_not_none():
    registry = LawRegistry()
    with pytest.raises(LawIdentityError) as caught:
        registry.get("missing")
    assert caught.value.code == "law_not_found"
