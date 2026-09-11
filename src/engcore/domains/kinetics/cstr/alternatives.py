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
from ....scientific.errors import InvalidScientificProblem
from ...derived_context import assembler_namespace
from .problem import (
    ADIABATIC_CEILING_TEMPERATURE,
    ASSEMBLER_NAMESPACE,
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
    exclusions=(
        "spatial gradients in concentration or temperature; the tank is "
        "perfectly mixed",
        "volume change; inflow and outflow volumetric rates are equal",
        "a second phase, boiling and a vapour space",
        "reverse and side reactions; one irreversible A -> B, first "
        "order in A",
        "temperature dependence of the density and the heat capacity",
        "jacket dynamics; a prescribed constant jacket temperature and a "
        "constant UA",
        "Arrhenius temperature dependence of the rate constant, which "
        "is approximated as temperature independent -- a comparison "
        "approximation, not a claim that it is absent in the physical "
        "system",
        "any change of reactor volume with time; the volume is constant",
    ),

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
            # The envelope ceiling, asked at the hottest state the declaration
            # can reach rather than at the one it starts from.
            #
            # THE RATE LAW CANCELS OUT OF THIS BOUND. Adding beta times the
            # species balance to the energy balance gives
            # dZ/dt = (Z_f - Z)/tau - gamma (T - T_c) for Z = T + beta C_A,
            # and the reaction term vanishes identically whatever k is. The
            # primary model's own record states the derivation; holding k
            # constant does not weaken it by one step. This record claims the
            # SAME single-phase envelope as that model, and without this
            # condition it claimed it without ever checking it: a declaration
            # whose contents can reach 2442 K came back IN_DOMAIN, on all four
            # of the conditions above, from a record whose own temperature
            # condition stops at 1000 K.
            RangeCondition(
                ADIABATIC_CEILING_TEMPERATURE,
                maximum=Quantity(MAX_VALID_TEMPERATURE_K, TEMPERATURE_UNIT),
                description=(
                    "max(T_0, T_f, T_c) + beta max(C_A0, C_Af) <= 1000 K, the "
                    "same envelope ceiling the primary model states and for "
                    "the same reason: Z = T + beta C_A is this reactor's exact "
                    "invariant and the reaction term cancels out of dZ/dt, so "
                    "the bound is independent of whether k is Arrhenius or "
                    "held constant. It introduces no new threshold -- it is "
                    "the temperature condition above, asked at the hottest "
                    "state the declaration can reach. UNKNOWN unless the "
                    "enthalpy, density, heat capacity, both concentrations "
                    "and all three temperatures are declared."
                ),
            ),
        ),
        description=(
            "Same single-phase CSTR envelope as the primary model, with a "
            "strictly positive constant reaction-rate approximation."
        ),
        # The reactor's own state, injected by the run's assembler rather than
        # declared as a parameter — the same two coordinates the primary model
        # reserves, for the same reason. A competitor model that left them
        # forgeable would be the easier of the two to fool, which is precisely
        # backwards for a model whose job is to lose a comparison honestly.
        derived_quantities=frozenset(
            {"temperature", "concentration", ADIABATIC_CEILING_TEMPERATURE}
        ),
    ),
    required_capabilities=frozenset({KINETICS_CSTR_NONISOTHERMAL.name}),
    validation_status=ModelValidationStatus.UNVALIDATED,
    references=(
        "K4 controlled comparison model: temperature-independent first-order rate approximation.",
    ),
)

# This model is assessed through ``ReactorRun.validity_context``, whose
# reserved namespace is fixed by the primary model. If this record ever
# reserves a name that assembler does not own, the name would arrive in the
# declared half and the core would refuse the assessment -- at the K4
# comparison, which is the worst possible place to find out. Checked here,
# at import, instead.
_UNOWNED = sorted(
    CONSTANT_RATE_CSTR_MODEL.derived_quantities - ASSEMBLER_NAMESPACE
)
if _UNOWNED:  # pragma: no cover - structural, fires only on a bad edit
    raise InvalidScientificProblem(
        f'the constant-rate CSTR model reserves {_UNOWNED}, which the CSTR '
        f'assembler does not own; a reserved name the assembler does not '
        f'strip arrives as a caller declaration and cannot be assessed. Add '
        f'it to the primary model, or stop reserving it here'
    )
