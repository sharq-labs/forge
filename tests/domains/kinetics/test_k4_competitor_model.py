from __future__ import annotations

import pytest

from src.engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL
from src.engcore.scientific import ModelType, ModelValidationStatus, Quantity, ValidityStatus
from src.engcore.scientific.errors import ModelValidityError


def test_constant_rate_competitor_has_distinct_identity_and_epistemic_type() -> None:
    assert CONSTANT_RATE_CSTR_MODEL.model_id == "kinetics.cstr.nonisothermal_first_order_constant_rate"
    assert CONSTANT_RATE_CSTR_MODEL.version == "0.1.0"
    assert CONSTANT_RATE_CSTR_MODEL.model_type is ModelType.APPROXIMATION
    assert CONSTANT_RATE_CSTR_MODEL.validation_status is ModelValidationStatus.UNVALIDATED


def test_constant_rate_competitor_declares_constant_rate_input_not_arrhenius_pair() -> None:
    names = tuple(item.name for item in CONSTANT_RATE_CSTR_MODEL.inputs)
    assert "k_const" in names
    assert "k0" not in names
    assert "activation_energy" not in names


def test_constant_rate_competitor_validity_is_not_unbounded() -> None:
    """The state coordinates arrive as assembled, because they are.

    ``temperature`` and ``concentration`` are the reactor's own state, injected
    by the run rather than declared as parameters, and this record reserves
    them. Handing them in as caller declarations is refused -- which is the
    point of the reservation, and is why this test states the split explicitly
    rather than passing one merged mapping.
    """
    def assess(k_const: Quantity):
        return CONSTANT_RATE_CSTR_MODEL.assess_validity(
            declared={
                "k_const": k_const,
                "residence_time": Quantity(100.0, "second"),
            },
            assembled={
                "temperature": Quantity(320.0, "kelvin"),
                "concentration": Quantity(1000.0, "mol/m**3"),
            },
        )

    assert assess(Quantity(0.01, "1/s")).status is ValidityStatus.IN_DOMAIN
    assert (
        assess(Quantity(0.0, "1/s")).status
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


def test_constant_rate_competitor_refuses_a_declared_state_coordinate() -> None:
    """A caller cannot hand this model its own operating temperature."""
    with pytest.raises(ModelValidityError):
        CONSTANT_RATE_CSTR_MODEL.assess_validity(
            {
                "temperature": Quantity(320.0, "kelvin"),
                "concentration": Quantity(1000.0, "mol/m**3"),
                "k_const": Quantity(0.01, "1/s"),
                "residence_time": Quantity(100.0, "second"),
            }
        )
