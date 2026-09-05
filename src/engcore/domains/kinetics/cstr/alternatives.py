"""Explicit alternative CSTR model families used for model competition.

These are scientific declarations, not aliases for the primary Arrhenius model.
K4 initially introduces a temperature-independent first-order rate approximation
so predictive evidence can compare two different model families on the same
held-out conditions.
"""

from __future__ import annotations

from ....scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ....scientific.units.quantity import Quantity
from .problem import (
    CONCENTRATION_UNIT,
    DIMENSIONLESS,
    KINETICS_CSTR_NONISOTHERMAL,
    MAX_VALID_TEMPERATURE_K,
    MIN_VALID_TEMPERATURE_K,
    MOLAR_ENERGY_UNIT,
    RATE_CONSTANT_UNIT,
    TEMPERATURE_UNIT,
    TIME_UNIT,
)

CONSTANT_RATE_MODEL_VERSION = "0.1.0"

CONSTANT_RATE_CSTR_MODEL = ScientificModelDefinition(
    model_id="kinetics.cstr.nonisothermal_first_order_constant_rate",
    version=CONSTANT_RATE_MODEL_VERSION,
    name="Non-isothermal CSTR with temperature-independent first-order rate",
    domain="kinetics",
    model_type=ModelType.APPROXIMATION,
    description=(
        "The same well-mixed species and energy balances as the primary CSTR "
        "model, but with a single temperature-independent first-order rate "
        "constant k_const instead of Arrhenius temperature dependence."
    ),
    inputs=(
        ModelInputSpec(
            name="k_const",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=RATE_CONSTANT_UNIT,
            description="Strictly positive temperature-independent first-order rate constant.",
        ),
        ModelInputSpec(
            name="heat_of_reaction",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=MOLAR_ENERGY_UNIT,
        ),
        ModelInputSpec(
            name="feed_concentration",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=CONCENTRATION_UNIT,
        ),
        ModelInputSpec(
            name="feed_temperature",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
        ),
        ModelInputSpec(
            name="coolant_temperature",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
        ),
        ModelInputSpec(
            name="residence_time",
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TIME_UNIT,
        ),
    ),
    outputs=(
        ModelOutputSpec("C_A", CONCENTRATION_UNIT),
        ModelOutputSpec("T", TEMPERATURE_UNIT),
        ModelOutputSpec("conversion", DIMENSIONLESS),
    ),
    assumptions=(
        "perfectly mixed constant-volume liquid-phase CSTR",
        "one irreversible first-order exothermic reaction A -> B",
        "reaction rate constant is approximated as temperature independent",
        "constant liquid density and heat capacity",
        "prescribed constant jacket temperature and constant UA",
        "single liquid phase with no boiling or phase change",
        "this restricted model is a K4 comparison approximation, not a claim that Arrhenius temperature dependence is absent in the physical system",
    ),
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                "temperature",
                minimum=Quantity(MIN_VALID_TEMPERATURE_K, TEMPERATURE_UNIT),
                maximum=Quantity(MAX_VALID_TEMPERATURE_K, TEMPERATURE_UNIT),
            ),
            RangeCondition(
                "concentration",
                minimum=Quantity(0.0, CONCENTRATION_UNIT),
            ),
            RangeCondition(
                "k_const",
                minimum=Quantity(0.0, RATE_CONSTANT_UNIT),
                minimum_inclusive=False,
            ),
            RangeCondition(
                "residence_time",
                minimum=Quantity(0.0, TIME_UNIT),
                minimum_inclusive=False,
            ),
        ),
        description=(
            "Same single-phase CSTR envelope as the primary model, with a "
            "strictly positive constant reaction-rate approximation."
        ),
    ),
    required_capabilities=frozenset({KINETICS_CSTR_NONISOTHERMAL.name}),
    validation_status=ModelValidationStatus.UNVALIDATED,
    references=(
        "K4 controlled comparison model: temperature-independent first-order rate approximation.",
    ),
)
