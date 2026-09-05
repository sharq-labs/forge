from __future__ import annotations

from src.engcore.domains.kinetics.cstr.alternatives import CONSTANT_RATE_CSTR_MODEL
from src.engcore.scientific import ModelType, ModelValidationStatus, Quantity, ValidityStatus


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
    in_domain = CONSTANT_RATE_CSTR_MODEL.validity.assess(
        {
            "temperature": Quantity(320.0, "kelvin"),
            "concentration": Quantity(1000.0, "mol/m**3"),
            "k_const": Quantity(0.01, "1/s"),
            "residence_time": Quantity(100.0, "second"),
        }
    )
    assert in_domain.status is ValidityStatus.IN_DOMAIN

    bad = CONSTANT_RATE_CSTR_MODEL.validity.assess(
        {
            "temperature": Quantity(320.0, "kelvin"),
            "concentration": Quantity(1000.0, "mol/m**3"),
            "k_const": Quantity(0.0, "1/s"),
            "residence_time": Quantity(100.0, "second"),
        }
    )
    assert bad.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
