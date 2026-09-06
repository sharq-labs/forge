"""Temperature-dependent conductor resistance: model, realization, evaluator.

MIN-FOUNDATION-ET. The material half of the minimum electro-thermal consumer:

    R(T) = R_ref * (1 + alpha_TCR * (T - T_ref))

This is a real constitutive claim with a declared temperature validity range,
not a lookup table and not a placeholder.

Why there is no parallel property hierarchy
-------------------------------------------
There is no ``MaterialProperty``, ``PropertyModel``, ``PropertyRequirement`` or
``PropertyBinding`` type here, and none is needed. A property that requires
computation **is a scientific claim computed by a realization**, so it is
stated with the contracts that already exist:

===============================  =========================================
``ScientificModelDefinition``    the claim: what relation holds, when it is
                                 valid, what it needs, what it produces
``ModelInputSpec``               the property *requirement*, already typed:
                                 name, source kind, dimension, value kind,
                                 role, required-ness
``ModelOutputSpec``              the property *identity*: metric + dimension
``ModelRealizationDefinition``   how the claim is computed
``ProvenanceRecord.bindings``    which realization actually computed it
===============================  =========================================

Building a second hierarchy beside these would duplicate every one of those
facts and put the duplicate somewhere the existing validity, capability and
provenance machinery could not see it.

Why this module names a thermal capability but imports no thermal code
----------------------------------------------------------------------
The realization declares ``required_capabilities = {thermal:body_temperature}``
— a genuine scientific dependency, because R(T) is undefined without a
temperature. It declares it **by identifier**, never by importing the thermal
package. Capability identifiers are open and registry-free precisely so that
one domain can require another domain's science without acquiring a code
dependency on it. Nothing in this file imports anything thermal, and a test
asserts it stays that way.

Note the asymmetry, which is a result rather than an oversight: the *thermal*
model does **not** declare a matching requirement on electrical dissipation.
Any heat source satisfies a lumped balance, so a requirement there would be a
false claim. The capability layer can therefore express the
thermal-to-electrical direction and structurally cannot express the
electrical-to-thermal one.

Relationship to ``electrical.dc.resistor_ohm``
----------------------------------------------
That model is **unchanged**, including its declared assumption
``"temperature-independent resistance"``. This model is the falsifiable
alternative to that assumption, not a correction of it, and the two coexisting
is how the boundary of the claim gets recorded. Ohm's law still relates V and I
for the resistor; this model supplies the *value* of R that Ohm's law uses.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..derived_context import assembled_validity_context, caller_declared
from ...scientific.capabilities import ScientificCapability
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.ir.variables import (
    ScientificParameter,
    ScientificVariable,
    VariableRole,
)
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityAssessment,
    ValidityDomain,
)
from ...scientific.models.registry import ModelRegistry
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.realizations.registry import RealizationRegistry
from ...scientific.serialization import require_schema, schema_string
from ...scientific.results.validation import (
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from ...scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapability,
    SolverCapabilityId,
)
from ...scientific.solvers.protocol import (
    ConvergenceState,
    PreparedSolve,
    RawSolverOutput,
    SolverIdentity,
    SolverSettings,
)
from ...scientific.units.quantity import Quantity

__all__ = [
    "BLOCH_GRUENEISEN_LINEAR_FLOOR",
    "DEBYE_TEMPERATURE",
    "DIMENSIONLESS",
    "LINEARIZATION_BAND",
    "LINEARIZATION_BUDGET_LIMIT",
    "LINEARIZATION_EXCURSION_RATIO",
    "LINEAR_RESISTANCE_RATIO",
    "LINEAR_TCR_MODEL",
    "LINEAR_TCR_REALIZATION",
    "MATERIAL_LIMITS_SCHEMA",
    "MAXIMUM_OPERATING_TEMPERATURE",
    "MINIMUM_LINEAR_RESISTANCE_RATIO",
    "OPERATING_TEMPERATURE_LIMIT",
    "OPERATING_TEMPERATURE_UTILIZATION",
    "RATED_LINEAR_TCR_MODEL",
    "RATED_LINEAR_TCR_REALIZATION",
    "REDUCED_DEBYE_TEMPERATURE",
    "REFERENCE_RESISTANCE",
    "REFERENCE_TEMPERATURE",
    "RESISTANCE_METRIC",
    "RESISTANCE_UNIT",
    "TEMPERATURE",
    "TEMPERATURE_COEFFICIENT",
    "TEMPERATURE_UNIT",
    "TEMPERATURE_DEPENDENT_RESISTANCE",
    "REQUIRED_BODY_TEMPERATURE",
    "TCR_MAX_TEMPERATURE",
    "TCR_MIN_TEMPERATURE",
    "MaterialLimits",
    "TemperatureDependentConductor",
    "ResistancePropertySolver",
    "assess_rated_resistance_validity",
    "assess_resistance_validity",
    "build_resistance_problem",
    "ASSEMBLED_QUANTITIES",
    "derived_material_quantities",
    "linear_resistance_ratio",
    "linearization_excursion_ratio",
    "operating_temperature_utilization",
    "rated_resistance_validity_context",
    "resistance_validity_context",
    "reduced_debye_temperature",
    "resistance_model_registry",
    "resistance_realizations",
    "resistance_solver_capabilities",
]

# --- units -------------------------------------------------------------------
RESISTANCE_UNIT = "ohm"
TEMPERATURE_UNIT = "kelvin"
TCR_UNIT = "1/kelvin"
DIMENSIONLESS = "dimensionless"

# --- quantity names ----------------------------------------------------------
REFERENCE_RESISTANCE = "reference_resistance"
TEMPERATURE_COEFFICIENT = "temperature_coefficient"
REFERENCE_TEMPERATURE = "reference_temperature"
TEMPERATURE = "temperature"

RESISTANCE_METRIC = "resistance"

#: Optional, material-supplied limits. Each is a *declaration about this
#: material*, so none of them can be a constant of this module: two conductors
#: differ in exactly these numbers.
LINEARIZATION_BAND = "linearization_band"
MAXIMUM_OPERATING_TEMPERATURE = "maximum_operating_temperature"
DEBYE_TEMPERATURE = "debye_temperature"

#: Derived groups the rated model's conditions are stated over.
LINEARIZATION_EXCURSION_RATIO = "linearization_excursion_ratio"
OPERATING_TEMPERATURE_UTILIZATION = "operating_temperature_utilization"
REDUCED_DEBYE_TEMPERATURE = "reduced_debye_temperature"
LINEAR_RESISTANCE_RATIO = "linear_resistance_ratio"

MODEL_VERSION = "0.1.0"
MATERIAL_LIMITS_SCHEMA = schema_string("conductor_material_limits")

# --- capabilities ------------------------------------------------------------

#: What science this provides.
TEMPERATURE_DEPENDENT_RESISTANCE = ScientificCapability.parse(
    "electrical:temperature_dependent_resistance"
)

#: What science this *needs*. Declared by identifier; no thermal module is
#: imported anywhere in this file. This is the milestone's one exercised use of
#: ``required_capabilities``, which MODEL0-R left empty and unexercised.
REQUIRED_BODY_TEMPERATURE = ScientificCapability.parse("thermal:body_temperature")

#: The declared validity range of the linear TCR form. Outside it the linear
#: term is not evidence-backed; the model says so rather than extrapolating
#: silently.
TCR_MIN_TEMPERATURE = Quantity(200.0, TEMPERATURE_UNIT)
TCR_MAX_TEMPERATURE = Quantity(450.0, TEMPERATURE_UNIT)


_ASSUMPTIONS = (
    "linear first-order temperature coefficient about a reference state",
    "no self-heating term: T is supplied, never inferred from the resistance",
    "isotropic scalar resistance; no tensor conductivity",
    "no strain, ageing, frequency or magnetic-field dependence",
    "temperature is uniform over the conductor (consistent with a lumped body)",
)


LINEAR_TCR_MODEL = ScientificModelDefinition(
    model_id="electrical.material.linear_tcr_resistance",
    version=MODEL_VERSION,
    name="Linear temperature-coefficient conductor resistance",
    domain="electrical",
    # CONSTITUTIVE_MODEL: a material response relation, neither a conservation
    # law nor a fitted correlation of a specific device.
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "Resistance of a conductor as a linear function of its temperature: "
        "R(T) = R_ref (1 + alpha (T - T_ref))."
    ),
    inputs=(
        ModelInputSpec(
            name=REFERENCE_RESISTANCE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=RESISTANCE_UNIT,
            description="Resistance at the reference temperature; positive.",
        ),
        ModelInputSpec(
            name=TEMPERATURE_COEFFICIENT,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TCR_UNIT,
            description=(
                "Temperature coefficient of resistance. Positive for metals, "
                "negative for a thermistor; both are representable."
            ),
        ),
        ModelInputSpec(
            name=REFERENCE_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            description="Temperature at which the reference resistance holds.",
        ),
        # THE STATE COORDINATE THE PROPERTY DEPENDS ON.
        #
        # This one line is what makes "resistance depends on temperature" a
        # typed, deterministically inspectable fact. A reader holding only this
        # record knows: there is an input named `temperature`, it must come
        # from a VARIABLE rather than a configured parameter, it carries a
        # thermodynamic temperature, and it plays the role of an evolving
        # STATE. No metadata, no naming convention, no solver setting and no
        # branch in universal core carries any part of that.
        ModelInputSpec(
            name=TEMPERATURE,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=TEMPERATURE_UNIT,
            role=VariableRole.STATE,
            description=(
                "Conductor temperature. A state coordinate, supplied from "
                "outside this model; never inferred here."
            ),
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=RESISTANCE_METRIC,
            unit_exemplar=RESISTANCE_UNIT,
            description="Resistance at the supplied temperature.",
        ),
    ),
    assumptions=_ASSUMPTIONS,
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=TEMPERATURE,
                minimum=TCR_MIN_TEMPERATURE,
                maximum=TCR_MAX_TEMPERATURE,
                description=(
                    "Range over which the single linear coefficient is "
                    "declared to hold. Outside it the linear form is an "
                    "extrapolation with no evidence behind it."
                ),
            ),
            RangeCondition(
                name=REFERENCE_RESISTANCE,
                minimum=Quantity(0.0, RESISTANCE_UNIT),
                minimum_inclusive=False,
                description="Strictly positive reference resistance.",
            ),
        ),
        description="Linear TCR about a reference state, over a stated range.",
    ),
    required_capabilities=frozenset({CoreCapabilities.ALGEBRAIC.name}),
    # SELF_CONSISTENT and no more. The linear TCR form is standard, but this
    # repository has measured no conductor and curates no reference set, and a
    # citation will not be invented to dress that up.
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=(),
)


LINEAR_TCR_REALIZATION = ModelRealizationDefinition(
    realization_id="electrical.material.linear_tcr_resistance.closed_form",
    version="0.1.0",
    model=ModelReference(LINEAR_TCR_MODEL.model_id, LINEAR_TCR_MODEL.version),
    formulation=ModelFormulation.ALGEBRAIC,
    name="Direct evaluation of the linear TCR expression",
    description=(
        "Evaluates R_ref (1 + alpha (T - T_ref)) once, at a supplied "
        "temperature. No iteration and no system solve."
    ),
    provided_capabilities=frozenset({TEMPERATURE_DEPENDENT_RESISTANCE}),
    # A real, machine-checkable scientific dependency: this computation cannot
    # be planned unless something provides a body temperature.
    required_capabilities=frozenset({REQUIRED_BODY_TEMPERATURE}),
    # Arithmetic, and nothing more specific is declared.
    #
    # This module and ``thermal_models.lumped`` made *opposite* choices here, and the
    # milestone records that rather than forcing agreement: the thermal
    # realization declares a domain solver capability beside ``core:algebraic``
    # and matches on it, this one declares none and matches on the model
    # reference the problem carries. Both are defensible and no contract
    # decides between them — capability identity is exact-string with no
    # registry and no subsumption, so granularity is a judgement call with
    # nothing to appeal to. That is MODEL0-R finding D5, met again from a
    # second direction and carried forward, not resolved by guesswork here.
    required_solver_capabilities=frozenset(
        {SolverCapabilityId.coerce(CoreCapabilities.ALGEBRAIC)}
    ),
    assumptions=(
        "single evaluation at one supplied temperature; no self-consistency "
        "loop between resistance and dissipation is performed here",
        "exact for the declared linear form; no discretization error exists",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.electrical.material",
        version="0.1.0",
        reference="linear TCR closed form; see module docstring",
    ),
)


# =====================================================================
# The rated claim: the same relation, bounded by what the material can take
# =====================================================================
#
# Why a second model and not four more conditions on the first
# -------------------------------------------------------------
# ``LINEAR_TCR_MODEL`` version 0.1.0 is a **published record**: problems built
# by :func:`build_resistance_problem` carry a ``ModelReference`` to it, and
# results already attributed to it were assessed against the domain it declared
# at the time. Strengthening that domain in place would silently re-judge every
# such result — a run that recorded IN_DOMAIN would become UNKNOWN without its
# inputs, its solver or its numbers having changed, and nothing in the record
# would say why. A model's validity domain is part of its identity, so a
# stronger claim gets a new identity.
#
# It is also the more honest description. These are two different claims: "the
# linear coefficient holds over 200-450 K" and "the linear coefficient holds
# over the band this material declares, below the temperature this material is
# rated for, and above the temperature at which its resistivity stops being
# linear in T at all". The module docstring already argues that
# ``electrical.dc.resistor_ohm`` and this model coexist as falsifiable
# alternatives rather than one correcting the other; the same argument applies
# here one step further in.

#: Ratio <= 1 of the operating excursion to the material's declared
#: linearization band. Not a tolerance: the caller states the band over which a
#: single alpha is supported by evidence, and the condition asks whether the
#: operating point stays inside the caller's own statement. The linear law is
#: the first-order Taylor expansion of rho(T) about T_ref, so its truncation
#: error grows with |T - T_ref| and no fixed band serves every material.
LINEARIZATION_BUDGET_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: T / T_max <= 1. A hard limit, not a convention. Above its maximum operating
#: temperature a conductor is not described less accurately by this relation —
#: it is annealing, oxidising, de-laminating or open. Both temperatures are
#: absolute, so the ratio reaching 1 is exactly ``T >= T_max``.
OPERATING_TEMPERATURE_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: T / theta_D >= 1/3. Above roughly this fraction of the Debye temperature the
#: phonon population that scatters the conduction electrons is classical and
#: the resistivity of a metal is linear in T; well below it the Bloch-Grueneisen
#: result gives rho ~ T^5 and no single coefficient can describe the curve.
#: Ashcroft & Mermin, *Solid State Physics* (Holt-Saunders, 1976), Ch. 26,
#: Eq. 26.55 and the discussion following it; Kittel, *Introduction to Solid
#: State Physics*, 8th ed. (Wiley, 2005), Ch. 6. The **1/3 is the conventional
#: engineering reading of "T much greater than theta_D"**, not a number either
#: text prints as a threshold, and it is recorded here as a convention.
BLOCH_GRUENEISEN_LINEAR_FLOOR = Quantity(1.0 / 3.0, DIMENSIONLESS)

#: R(T) / R_ref > 0, strictly. The linear form is a straight line and every
#: straight line with a non-zero slope crosses zero; past that crossing it is
#: not an inaccurate conductor but a negative one. This bounds the
#: extrapolation by the physics of the quantity it computes rather than by a
#: tolerance, which is why the bound is exactly zero and needs no source.
MINIMUM_LINEAR_RESISTANCE_RATIO = Quantity(0.0, DIMENSIONLESS)


RATED_LINEAR_TCR_MODEL = ScientificModelDefinition(
    model_id="electrical.material.rated_linear_tcr_resistance",
    version=MODEL_VERSION,
    name="Linear-TCR conductor resistance within its material limits",
    domain="electrical",
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "The same relation as electrical.material.linear_tcr_resistance, "
        "R(T) = R_ref (1 + alpha (T - T_ref)), claimed only inside the "
        "linearization band, the maximum operating temperature and the "
        "low-temperature floor the material itself declares. A strictly "
        "stronger claim with a strictly smaller validity domain."
    ),
    inputs=(
        ModelInputSpec(
            name=REFERENCE_RESISTANCE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=RESISTANCE_UNIT,
            description="Resistance at the reference temperature; positive.",
        ),
        ModelInputSpec(
            name=TEMPERATURE_COEFFICIENT,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TCR_UNIT,
            description=(
                "Temperature coefficient of resistance. Positive for metals, "
                "negative for a thermistor; both are representable."
            ),
        ),
        ModelInputSpec(
            name=REFERENCE_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            description="Temperature at which the reference resistance holds.",
        ),
        ModelInputSpec(
            name=TEMPERATURE,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=TEMPERATURE_UNIT,
            role=VariableRole.STATE,
            description=(
                "Conductor temperature. A state coordinate, supplied from "
                "outside this model; never inferred here."
            ),
        ),
        # ---- optional, material-supplied limits -------------------------
        # Each is `required=False`, so a problem that omits it still binds;
        # and each condition that needs it is UNKNOWN without it, so omitting
        # it can never buy an IN_DOMAIN verdict.
        ModelInputSpec(
            name=LINEARIZATION_BAND,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "Half-width |T - T_ref| over which this material's single "
                "alpha is supported by evidence."
            ),
        ),
        ModelInputSpec(
            name=MAXIMUM_OPERATING_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "Absolute maximum operating temperature of the material, "
                "above which the conductor itself is not intact."
            ),
        ),
        ModelInputSpec(
            name=DEBYE_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "Debye temperature of the material, which sets the "
                "temperature below which resistivity stops being linear in T."
            ),
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=RESISTANCE_METRIC,
            unit_exemplar=RESISTANCE_UNIT,
            description="Resistance at the supplied temperature.",
        ),
    ),
    assumptions=_ASSUMPTIONS
    + (
        "the material's own declared limits bound the claim, and an "
        "undeclared limit leaves its condition UNKNOWN rather than satisfied",
    ),
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=TEMPERATURE,
                minimum=TCR_MIN_TEMPERATURE,
                maximum=TCR_MAX_TEMPERATURE,
                description=(
                    "The range this repository's linear TCR form is declared "
                    "over at all, inherited unchanged from "
                    "electrical.material.linear_tcr_resistance. The "
                    "material-specific limits below narrow it further; they "
                    "never widen it."
                ),
            ),
            RangeCondition(
                name=REFERENCE_RESISTANCE,
                minimum=Quantity(0.0, RESISTANCE_UNIT),
                minimum_inclusive=False,
                description="Strictly positive reference resistance.",
            ),
            RangeCondition(
                name=LINEARIZATION_EXCURSION_RATIO,
                maximum=LINEARIZATION_BUDGET_LIMIT,
                description=(
                    "|T - T_ref| / linearization_band <= 1. R(T) = R_ref "
                    "(1 + alpha (T - T_ref)) is the first-order Taylor "
                    "expansion of rho(T) about T_ref, so the neglected "
                    "curvature grows with the excursion and how far a single "
                    "alpha carries is a property of the material rather than "
                    "of the algebra. UNKNOWN unless the material declares "
                    "linearization_band."
                ),
            ),
            RangeCondition(
                name=OPERATING_TEMPERATURE_UTILIZATION,
                maximum=OPERATING_TEMPERATURE_LIMIT,
                description=(
                    "T / maximum_operating_temperature <= 1. A hard material "
                    "limit rather than a modelling tolerance: above it the "
                    "conductor is annealing, oxidising or open, and no "
                    "coefficient describes a component that is not intact. "
                    "UNKNOWN unless the material declares "
                    "maximum_operating_temperature."
                ),
            ),
            RangeCondition(
                name=REDUCED_DEBYE_TEMPERATURE,
                minimum=BLOCH_GRUENEISEN_LINEAR_FLOOR,
                description=(
                    "T / theta_D >= 1/3. Above roughly this fraction of the "
                    "Debye temperature a metal's resistivity is linear in T; "
                    "well below it Bloch-Grueneisen gives rho ~ T^5 and no "
                    "single coefficient fits. Ashcroft & Mermin, Solid State "
                    "Physics (1976), Ch. 26, Eq. 26.55; Kittel, Introduction "
                    "to Solid State Physics, 8th ed. (2005), Ch. 6. UNKNOWN "
                    "unless the material declares debye_temperature."
                ),
            ),
            RangeCondition(
                name=LINEAR_RESISTANCE_RATIO,
                minimum=MINIMUM_LINEAR_RESISTANCE_RATIO,
                minimum_inclusive=False,
                description=(
                    "1 + alpha (T - T_ref) > 0. Every straight line with a "
                    "non-zero slope crosses zero; past the crossing the form "
                    "does not describe a poor conductor but a negative one. "
                    "The bound is the physics of the quantity, not a "
                    "tolerance. UNKNOWN unless a temperature is supplied."
                ),
            ),
        ),
        description=(
            "Linear TCR about a reference state, inside the band, the maximum "
            "operating temperature and the low-temperature floor the material "
            "declares."
        ),
    ),
    required_capabilities=frozenset({CoreCapabilities.ALGEBRAIC.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=(),
)


RATED_LINEAR_TCR_REALIZATION = ModelRealizationDefinition(
    realization_id="electrical.material.rated_linear_tcr_resistance.closed_form",
    version="0.1.0",
    model=ModelReference(
        RATED_LINEAR_TCR_MODEL.model_id, RATED_LINEAR_TCR_MODEL.version
    ),
    formulation=ModelFormulation.ALGEBRAIC,
    name="Direct evaluation of the linear TCR expression, within material limits",
    description=(
        "The same single evaluation of R_ref (1 + alpha (T - T_ref)) as the "
        "unrated realization. Narrowing a validity domain changes what may be "
        "claimed about a number, never how the number is computed, and this "
        "record exists to say that the arithmetic did not change."
    ),
    provided_capabilities=frozenset({TEMPERATURE_DEPENDENT_RESISTANCE}),
    required_capabilities=frozenset({REQUIRED_BODY_TEMPERATURE}),
    required_solver_capabilities=frozenset(
        {SolverCapabilityId.coerce(CoreCapabilities.ALGEBRAIC)}
    ),
    assumptions=(
        "single evaluation at one supplied temperature; no self-consistency "
        "loop between resistance and dissipation is performed here",
        "exact for the declared linear form; no discretization error exists",
    ),
    implementation=ImplementationReference(
        implementation_id="engcore.domains.electrical.material",
        version="0.1.0",
        reference="linear TCR closed form; see module docstring",
    ),
)


def resistance_model_registry() -> ModelRegistry:
    """A fresh registry. No global singleton exists."""
    return ModelRegistry((LINEAR_TCR_MODEL, RATED_LINEAR_TCR_MODEL))


def resistance_realizations() -> RealizationRegistry:
    """A fresh registry. No global singleton exists."""
    return RealizationRegistry(
        (LINEAR_TCR_REALIZATION, RATED_LINEAR_TCR_REALIZATION)
    )


def resistance_solver_capabilities() -> frozenset[SolverCapability]:
    return frozenset({CoreCapabilities.ALGEBRAIC})


# =====================================================================
# Declaration
# =====================================================================

@dataclass(frozen=True)
class MaterialLimits:
    """What this material declares about where its own linear law stops.

    Every field is optional and defaults to ``None``, meaning *not declared*
    and never *typical for a metal*. A field left out removes the condition
    that needs it from IN_DOMAIN reach and leaves it UNKNOWN. Supplying more
    can only move a verdict away from UNKNOWN; it can never turn a violated
    condition into a satisfied one.

    Separate from :class:`TemperatureDependentConductor` because these are
    facts about the *material*, shared by every component made of it, while a
    conductor is one component with one reference resistance. Two 10-ohm and
    100-ohm resistors wound from the same alloy have the same limits and
    different conductors.
    """

    linearization_band: Quantity | None = None
    maximum_operating_temperature: Quantity | None = None
    debye_temperature: Quantity | None = None

    def __post_init__(self) -> None:
        for label in (
            "linearization_band",
            "maximum_operating_temperature",
            "debye_temperature",
        ):
            value = getattr(self, label)
            if value is None:
                continue
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"{label} must be a Quantity carrying "
                    f"{TEMPERATURE_UNIT!r}, got {type(value).__name__} — a "
                    f"bare number is not a declaration"
                )
            value.require_compatible(TEMPERATURE_UNIT, context=label)
            # A band, a rating and a Debye temperature are all strictly
            # positive spans or absolute temperatures. Zero is not a small
            # value in any of the three: it is a division by zero in the
            # first, an unusable component in the second, and not a solid in
            # the third.
            if value.magnitude_in(TEMPERATURE_UNIT) <= 0.0:
                raise InvalidScientificProblem(
                    f"{label} must be strictly positive, got {value}"
                )

        # The band is a *span*, unlike the other two, which are states. A
        # caller who writes Quantity(50.0, "degC") meaning "fifty degrees of
        # band" has declared 323.15 K, and the excursion ratio built on it is
        # then wrong by a factor of six with no dimension check able to notice.
        # The test is the published-contract one the electrothermal pack uses
        # for its comparison unit: does zero of this unit convert to zero
        # kelvin? kelvin, rankine and delta_degC pass; degC and degF do not.
        band = self.linearization_band
        if (
            band is not None
            and Quantity(0.0, band.units).magnitude_in(TEMPERATURE_UNIT) != 0.0
        ):
            raise InvalidScientificProblem(
                f"linearization_band is a temperature *span* and may not use "
                f"{band.units!r}: its zero is conventional, so a difference "
                f"expressed in it is not a value of that unit. Use kelvin, or "
                f"a delta scale such as 'delta_degC'"
            )

    @property
    def is_empty(self) -> bool:
        """True when nothing was declared — every rated condition is UNKNOWN."""
        return (
            self.linearization_band is None
            and self.maximum_operating_temperature is None
            and self.debye_temperature is None
        )

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Quantity | None) -> dict[str, Any] | None:
            return value.to_dict() if value is not None else None

        return {
            "schema": MATERIAL_LIMITS_SCHEMA,
            "linearization_band": encode(self.linearization_band),
            "maximum_operating_temperature": encode(
                self.maximum_operating_temperature
            ),
            "debye_temperature": encode(self.debye_temperature),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MaterialLimits":
        require_schema(payload, MATERIAL_LIMITS_SCHEMA)

        def decode(key: str) -> Quantity | None:
            raw = payload.get(key)
            return Quantity.from_dict(raw) if raw else None

        return cls(
            linearization_band=decode("linearization_band"),
            maximum_operating_temperature=decode("maximum_operating_temperature"),
            debye_temperature=decode("debye_temperature"),
        )


@dataclass(frozen=True)
class TemperatureDependentConductor:
    """One declared conductor whose resistance depends on its temperature.

    Carries the material declaration and the component id it belongs to. It
    carries no temperature: a temperature is a *state*, and freezing one into
    the declaration is precisely the configuration/state conflation this
    milestone exists to examine.

    ``limits`` is optional and defaults to an empty :class:`MaterialLimits`,
    which is the honest starting point: a conductor about which no material
    limit was stated supports no verdict on the rated claim except UNKNOWN.
    """

    component_id: str
    reference_resistance: Quantity
    temperature_coefficient: Quantity
    reference_temperature: Quantity
    limits: MaterialLimits = field(default_factory=MaterialLimits)

    def __post_init__(self) -> None:
        component_id = str(self.component_id).strip()
        if not component_id:
            raise InvalidScientificProblem("conductor requires a component_id")
        object.__setattr__(self, "component_id", component_id)
        if not isinstance(self.limits, MaterialLimits):
            raise InvalidScientificProblem(
                f"limits must be a MaterialLimits, got "
                f"{type(self.limits).__name__}"
            )

        for label, unit in (
            ("reference_resistance", RESISTANCE_UNIT),
            ("temperature_coefficient", TCR_UNIT),
            ("reference_temperature", TEMPERATURE_UNIT),
        ):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"{label} must be a Quantity carrying {unit!r}, got "
                    f"{type(value).__name__} — a bare number is not a "
                    f"declaration"
                )
            value.require_compatible(unit, context=f"conductor {label}")

        if self.reference_resistance.magnitude_in(RESISTANCE_UNIT) <= 0.0:
            raise InvalidScientificProblem(
                f"conductor {component_id!r} requires a strictly positive "
                f"reference resistance"
            )
        if self.reference_temperature.magnitude_in(TEMPERATURE_UNIT) <= 0.0:
            raise InvalidScientificProblem(
                f"conductor {component_id!r} requires a positive absolute "
                f"reference temperature"
            )

    @property
    def r_ref_ohm(self) -> float:
        return self.reference_resistance.magnitude_in(RESISTANCE_UNIT)

    @property
    def alpha_per_k(self) -> float:
        return self.temperature_coefficient.magnitude_in(TCR_UNIT)

    @property
    def t_ref_k(self) -> float:
        return self.reference_temperature.magnitude_in(TEMPERATURE_UNIT)


def _limit_parameters(
    limits: MaterialLimits,
) -> tuple[ScientificParameter, ...]:
    """The declared material limits as problem parameters, in fixed order.

    A limit left as ``None`` produces **no parameter**, which is how "not
    declared" survives to ``ValidityDomain.assess`` as UNKNOWN. There is no
    placeholder anywhere on this path, so no rated condition can be satisfied
    by an omission. Order is fixed so equal declarations serialize identically.
    """
    declared: tuple[tuple[str, Quantity | None, str], ...] = (
        (
            LINEARIZATION_BAND,
            limits.linearization_band,
            "Half-width over which a single alpha is supported by evidence.",
        ),
        (
            MAXIMUM_OPERATING_TEMPERATURE,
            limits.maximum_operating_temperature,
            "Absolute maximum operating temperature of the material.",
        ),
        (
            DEBYE_TEMPERATURE,
            limits.debye_temperature,
            "Debye temperature of the material.",
        ),
    )
    return tuple(
        ScientificParameter(name=name, value=value, description=description)
        for name, value, description in declared
        if value is not None
    )


def build_resistance_problem(
    conductor: TemperatureDependentConductor,
    *,
    problem_id: str | None = None,
) -> ScientificProblem:
    """The universal problem statement for one resistance evaluation.

    ``temperature`` is a **variable with role STATE** and carries no value: the
    problem states that a temperature is required and what dimension it has,
    without asserting which one. Where the value comes from is a separate fact
    and lives in a separate record.

    A conductor that declares material limits produces a problem that carries
    them **and** references :data:`RATED_LINEAR_TCR_MODEL` beside the unrated
    one, because such a problem states enough to answer the stronger claim. A
    conductor that declares none produces exactly the problem this function has
    always produced: same parameters, same single model reference, same bytes.
    Widening the record only when the caller widened the declaration is what
    keeps the two claims independently reportable.
    """
    limits = _limit_parameters(conductor.limits)
    models = (ModelReference(LINEAR_TCR_MODEL.model_id, LINEAR_TCR_MODEL.version),)
    if limits:
        models += (
            ModelReference(
                RATED_LINEAR_TCR_MODEL.model_id, RATED_LINEAR_TCR_MODEL.version
            ),
        )
    return ScientificProblem(
        problem_id=problem_id or f"resistance-tcr-{conductor.component_id}",
        name=f"Temperature-dependent resistance of {conductor.component_id}",
        description=(
            "Evaluate R(T) for one conductor at one supplied temperature."
        ),
        variables=(
            ScientificVariable(
                name=TEMPERATURE,
                unit=TEMPERATURE_UNIT,
                role=VariableRole.STATE,
                description="Conductor temperature; supplied, not chosen.",
            ),
        ),
        parameters=(
            ScientificParameter(
                name=REFERENCE_RESISTANCE,
                value=conductor.reference_resistance,
                description="Resistance at the reference temperature.",
            ),
            ScientificParameter(
                name=TEMPERATURE_COEFFICIENT,
                value=conductor.temperature_coefficient,
                description="Linear temperature coefficient of resistance.",
            ),
            ScientificParameter(
                name=REFERENCE_TEMPERATURE,
                value=conductor.reference_temperature,
                description="Temperature at which the reference value holds.",
            ),
        )
        + limits,
        models=models,
        required_capabilities=frozenset({CoreCapabilities.ALGEBRAIC.name}),
    )


def assess_resistance_validity(
    problem: ScientificProblem, temperature: Quantity
) -> ValidityAssessment:
    """Is the model applicable at this temperature? **Validity, not validation.**

    Kept as its own function, deliberately outside the solver's
    :class:`ValidationReport`. *Was this model applicable* and *was this result
    checked* are different questions, and the platform keeps them on different
    fields for exactly that reason.

    Note what has to happen for this to work at all: ``temperature`` is a
    **variable**, and :meth:`ScientificProblem.validity_context` is built from
    **parameters**, so the state value must be supplied explicitly through
    ``extra=``. A validity condition on a state coordinate is therefore never
    automatic — recorded as a finding, not worked around.
    """
    return LINEAR_TCR_MODEL.assess_validity(
        resistance_validity_context(problem, temperature)
    )


# =====================================================================
# Computed context for the rated claim
# =====================================================================
#
# The same shape as ``thermal_models.context``: pure functions, each returning
# ``None`` when it was not given what it needs, and an assembler that drops the
# key rather than inventing a value. Nothing here is known to
# ``engcore.scientific``; the core supplies ``validity_context(extra=...)`` and
# this is the electrical domain's use of it.


def resistance_validity_context(
    problem: ScientificProblem, temperature: Quantity
) -> dict[str, Any]:
    """The context :data:`LINEAR_TCR_MODEL` is assessed against.

    ``temperature`` is a state coordinate this model states a range condition
    over, and it reaches the context only from here. It is a **reserved** name
    for that reason: a caller parameter called ``temperature`` would otherwise
    sit in the same key and decide the same condition, which is the derived-
    quantity impersonation in its plainest form.
    """
    return assembled_validity_context(
        declared=caller_declared(
            problem.validity_context(), ASSEMBLED_QUANTITIES
        ),
        assembled={TEMPERATURE: temperature},
        reserved=ASSEMBLED_QUANTITIES,
    )


def _temperature_in_kelvin(value: Any, label: str) -> float | None:
    """A supplied temperature as kelvin; ``None`` stays ``None``.

    A non-``Quantity`` that is not ``None`` is refused rather than skipped: a
    caller who passed the wrong type declared something wrong, which is not the
    same situation as a caller who declared nothing, and collapsing the two
    would turn a specification error into a silent UNKNOWN.
    """
    if value is None:
        return None
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {TEMPERATURE_UNIT!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    value.require_compatible(TEMPERATURE_UNIT, context=label)
    return value.magnitude_in(TEMPERATURE_UNIT)


def linearization_excursion_ratio(
    *,
    temperature: Quantity | None,
    reference_temperature: Quantity | None,
    band: Quantity | None,
) -> Quantity | None:
    """|T - T_ref| / band — the share of the declared linear band in use.

    **Definition.** The operating excursion from the reference state, divided
    by the half-width over which the material declares one coefficient
    sufficient.

    **Why the band is supplied and not fixed.** ``R(T) = R_ref (1 + alpha
    (T - T_ref))`` is the first-order Taylor expansion of ``rho(T)`` about
    ``T_ref``; the term it drops is ``(1/2) rho''(T_ref) (T - T_ref)^2``, so
    the fractional error grows quadratically with the excursion and its
    coefficient is a property of the material's ``rho(T)`` curve. There is no
    material-independent number to hard-code, and inventing one would be
    exactly the unearned claim this repository refuses.
    """
    kelvin = _temperature_in_kelvin(temperature, TEMPERATURE)
    reference = _temperature_in_kelvin(
        reference_temperature, REFERENCE_TEMPERATURE
    )
    width = _temperature_in_kelvin(band, LINEARIZATION_BAND)
    if kelvin is None or reference is None or width is None:
        return None
    if width <= 0.0:
        raise InvalidScientificProblem(
            f"{LINEARIZATION_BAND} must be strictly positive, got {band}"
        )
    return Quantity(abs(kelvin - reference) / width, DIMENSIONLESS)


def operating_temperature_utilization(
    *,
    temperature: Quantity | None,
    maximum_temperature: Quantity | None,
) -> Quantity | None:
    """T / T_max — how much of the material's rated range is in use.

    **Definition.** The ratio of two absolute temperatures, so the ratio
    reaching 1 is exactly ``T >= T_max``. Expressed as a ratio rather than as a
    bound on ``T`` because the bound belongs to the *material*, and a
    :class:`RangeCondition` fixes its bounds when the model record is written —
    one model record has to serve every conductor.
    """
    kelvin = _temperature_in_kelvin(temperature, TEMPERATURE)
    maximum = _temperature_in_kelvin(
        maximum_temperature, MAXIMUM_OPERATING_TEMPERATURE
    )
    if kelvin is None or maximum is None:
        return None
    if maximum <= 0.0:
        raise InvalidScientificProblem(
            f"{MAXIMUM_OPERATING_TEMPERATURE} must be strictly positive, got "
            f"{maximum_temperature}"
        )
    return Quantity(kelvin / maximum, DIMENSIONLESS)


def reduced_debye_temperature(
    *,
    temperature: Quantity | None,
    debye_temperature: Quantity | None,
) -> Quantity | None:
    """T / theta_D — where the conductor sits on the Bloch-Grueneisen curve.

    **Definition.** The operating temperature in units of the material's Debye
    temperature. Ashcroft & Mermin, *Solid State Physics* (1976), Ch. 26,
    Eq. 26.55: the ideal resistivity of a metal is linear in ``T`` for
    ``T >> theta_D`` and goes as ``T^5`` for ``T << theta_D``, so this ratio is
    the coordinate that says which of the two regimes a linear coefficient is
    being asked to describe. See :data:`BLOCH_GRUENEISEN_LINEAR_FLOOR` for the
    threshold and for what is and is not cited about it.
    """
    kelvin = _temperature_in_kelvin(temperature, TEMPERATURE)
    debye = _temperature_in_kelvin(debye_temperature, DEBYE_TEMPERATURE)
    if kelvin is None or debye is None:
        return None
    if debye <= 0.0:
        raise InvalidScientificProblem(
            f"{DEBYE_TEMPERATURE} must be strictly positive, got "
            f"{debye_temperature}"
        )
    return Quantity(kelvin / debye, DIMENSIONLESS)


def linear_resistance_ratio(
    *,
    temperature: Quantity | None,
    reference_temperature: Quantity | None,
    temperature_coefficient: Quantity | None,
) -> Quantity | None:
    """1 + alpha (T - T_ref) — the linear form's own multiplier.

    **Definition.** ``R(T) / R_ref`` for this model, evaluated without needing
    ``R_ref``: the relation is multiplicative, so the reference resistance
    cancels and the applicability question is about the bracket alone.

    A straight line with a non-zero slope crosses zero. Past the crossing the
    expression does not describe a worse conductor, it describes a negative
    one, and the solver's admissibility check catches that *after* computing a
    number. This condition catches it before, which is the difference between
    "was this result checked" and "was this model applicable".
    """
    kelvin = _temperature_in_kelvin(temperature, TEMPERATURE)
    reference = _temperature_in_kelvin(
        reference_temperature, REFERENCE_TEMPERATURE
    )
    if temperature_coefficient is not None and not isinstance(
        temperature_coefficient, Quantity
    ):
        raise InvalidScientificProblem(
            f"{TEMPERATURE_COEFFICIENT} must be a Quantity carrying "
            f"{TCR_UNIT!r}, got {type(temperature_coefficient).__name__}"
        )
    if kelvin is None or reference is None or temperature_coefficient is None:
        return None
    temperature_coefficient.require_compatible(
        TCR_UNIT, context=TEMPERATURE_COEFFICIENT
    )
    alpha = temperature_coefficient.magnitude_in(TCR_UNIT)
    return Quantity(1.0 + alpha * (kelvin - reference), DIMENSIONLESS)


#: Every name this module assembles, and which a caller parameter may therefore
#: never occupy. See ``engcore.domains.derived_context`` for what reserving a
#: name means and why it is enforced at assembly rather than at problem
#: construction.
#:
#: It is the derived groups **and** the state coordinates the assembler
#: injects, because the two are in the same position: a condition reads either
#: one by name, and either one is absent when the assembler could not supply
#: it. Reserving only the derived groups would leave the state coordinates
#: forgeable in exactly the same way — ``temperature`` here is a condition of
#: both material models and is supplied by the coupling, so a caller parameter
#: of that name would otherwise decide the linear form's own range condition.
ASSEMBLED_QUANTITIES = frozenset(
    {
        TEMPERATURE,
        LINEARIZATION_EXCURSION_RATIO,
        OPERATING_TEMPERATURE_UTILIZATION,
        REDUCED_DEBYE_TEMPERATURE,
        LINEAR_RESISTANCE_RATIO,
    }
)


def derived_material_quantities(
    base: Mapping[str, Any],
    *,
    temperature: Quantity | None = None,
) -> dict[str, Quantity]:
    """Every rated group derivable from ``base`` and the supplied temperature.

    ``base`` is a problem's parameter-derived context. ``temperature`` is the
    state coordinate, which the core's parameter-built context structurally
    cannot reach — the same limitation :func:`assess_resistance_validity`
    records, met again and not worked around.

    **A key that could not be derived is absent.** No placeholder, no zero, no
    typical value, so a condition depending on it reaches
    ``ValidityDomain.assess`` as UNKNOWN.
    """
    reference_temperature = base.get(REFERENCE_TEMPERATURE)
    derived: dict[str, Quantity | None] = {
        LINEARIZATION_EXCURSION_RATIO: linearization_excursion_ratio(
            temperature=temperature,
            reference_temperature=reference_temperature,
            band=base.get(LINEARIZATION_BAND),
        ),
        OPERATING_TEMPERATURE_UTILIZATION: operating_temperature_utilization(
            temperature=temperature,
            maximum_temperature=base.get(MAXIMUM_OPERATING_TEMPERATURE),
        ),
        REDUCED_DEBYE_TEMPERATURE: reduced_debye_temperature(
            temperature=temperature,
            debye_temperature=base.get(DEBYE_TEMPERATURE),
        ),
        LINEAR_RESISTANCE_RATIO: linear_resistance_ratio(
            temperature=temperature,
            reference_temperature=reference_temperature,
            temperature_coefficient=base.get(TEMPERATURE_COEFFICIENT),
        ),
    }
    return {name: value for name, value in derived.items() if value is not None}


def rated_resistance_validity_context(
    problem: ScientificProblem, temperature: Quantity | None = None
) -> dict[str, Any]:
    """The full context :data:`RATED_LINEAR_TCR_MODEL` is assessed against.

    Assembled in two separated namespaces since F03. The caller's parameters
    arrive with every reserved name stripped, so a temperature or a rated group
    can only be here because this function put it here; the derivations are
    handed that stripped context too, so a forged value cannot even be read as
    an *input* to one. A group that could not be derived is absent, which is
    how a missing declaration reaches ``assess`` as UNKNOWN — the guarantee the
    old ``context.update(...)`` over the caller's own parameters quietly broke.
    """
    declared = caller_declared(problem.validity_context(), ASSEMBLED_QUANTITIES)
    state = {} if temperature is None else {TEMPERATURE: temperature}
    return assembled_validity_context(
        declared=declared,
        assembled={
            **state,
            **derived_material_quantities(
                {**declared, **state}, temperature=temperature
            ),
        },
        reserved=ASSEMBLED_QUANTITIES,
    )


def assess_rated_resistance_validity(
    problem: ScientificProblem, temperature: Quantity | None = None
) -> ValidityAssessment:
    """Is the *rated* claim applicable here? **Validity, not validation.**

    The strong sibling of :func:`assess_resistance_validity`. The two answer
    different questions about the same arithmetic — "is a linear TCR form
    declared over this temperature at all" and "does this material's own
    declared band, rating and low-temperature floor cover this operating
    point" — and they are deliberately separate functions over separate model
    records, so a caller can hold both answers at once and neither can be
    mistaken for the other.
    """
    return RATED_LINEAR_TCR_MODEL.assess_validity(
        rated_resistance_validity_context(problem, temperature)
    )


# =====================================================================
# Evaluator
# =====================================================================

SOLVER_ID = "engcore.electrical.linear_tcr_evaluator"
SOLVER_VERSION = "0.1.0"
BACKEND = "python.float"


@dataclass(frozen=True)
class PreparedResistanceEvaluation:
    """The conductor and the temperature this evaluation will use."""

    conductor: TemperatureDependentConductor
    realization: ModelRealizationDefinition
    temperature_k: float


class ResistancePropertySolver:
    """Evaluates R(T) for one conductor. Satisfies ScientificSolver.

    It is a solver in the platform's sense — something that takes a prepared
    problem, produces raw output, and can be named in provenance — even though
    the computation is one line of arithmetic. Making it a special case would
    have meant the property evaluation could not appear in an
    :class:`ExecutionBinding`, and "which realization computed this resistance"
    would have gone unrecorded.
    """

    def __init__(self, settings: SolverSettings | None = None) -> None:
        self._bound: dict[str, tuple[TemperatureDependentConductor, float]] = {}
        self.settings = settings or SolverSettings()

    @property
    def identity(self) -> SolverIdentity:
        return SolverIdentity(SOLVER_ID, SOLVER_VERSION, backend=BACKEND)

    @property
    def capabilities(self) -> frozenset[SolverCapability]:
        return resistance_solver_capabilities()

    def bind_conductor(
        self,
        conductor: TemperatureDependentConductor,
        problem_id: str,
        *,
        temperature: Quantity,
    ) -> None:
        """Associate a conductor and a supplied temperature with a problem id.

        Rebinding a **different temperature** under one problem id is allowed
        and is the normal case: one conductor evaluated at two temperatures is
        one system at two states, not two systems. Rebinding a different
        *conductor* is refused.
        """
        if not isinstance(conductor, TemperatureDependentConductor):
            raise InvalidScientificProblem(
                "bind_conductor expects a TemperatureDependentConductor"
            )
        kelvin = temperature.magnitude_in(TEMPERATURE_UNIT)
        if not math.isfinite(kelvin):
            raise InvalidScientificProblem("temperature must be finite")
        key = str(problem_id)
        existing = self._bound.get(key)
        if existing is not None and existing[0] != conductor:
            raise InvalidScientificProblem(
                f"problem {key!r} is already bound to a different conductor"
            )
        self._bound[key] = (conductor, kelvin)

    @staticmethod
    def verify_problem_matches_conductor(
        problem: ScientificProblem, conductor: TemperatureDependentConductor
    ) -> None:
        """Refuse a problem describing a different conductor than the bound one.

        A result whose provenance contradicts the declaration that produced it
        is worse than no result, which is why the sibling DC domain checks the
        same thing before it assembles anything.
        """
        for name, declared in (
            (REFERENCE_RESISTANCE, conductor.reference_resistance),
            (TEMPERATURE_COEFFICIENT, conductor.temperature_coefficient),
            (REFERENCE_TEMPERATURE, conductor.reference_temperature),
        ):
            stated = problem.parameter(name).value
            if not isinstance(stated, Quantity) or stated.compare(declared) != 0.0:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states {name} = {stated} "
                    f"but the bound conductor declares {declared}"
                )
        # The material limits are checked on the same terms. A problem stating
        # a rating the bound conductor does not have would produce a rated
        # validity verdict attributed to a material that never declared it —
        # the same provenance failure the three checks above refuse, one level
        # further out.
        stated_names = {p.name for p in problem.parameters}
        for parameter in _limit_parameters(conductor.limits):
            if parameter.name not in stated_names:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} omits {parameter.name}, "
                    f"which the bound conductor declares"
                )
            stated = problem.parameter(parameter.name).value
            if not isinstance(stated, Quantity) or stated.compare(
                parameter.value
            ) != 0.0:
                raise InvalidScientificProblem(
                    f"problem {problem.problem_id!r} states "
                    f"{parameter.name} = {stated} but the bound conductor "
                    f"declares {parameter.value}"
                )

    def supports(self, problem: ScientificProblem) -> bool:
        """Does this evaluator implement the science the problem asks for?

        Matched on the **model reference the problem carries**, not on a
        capability alone: ``core:algebraic`` says a closed-form evaluation is
        needed, which is true of countless unrelated relations.
        """
        wanted = (LINEAR_TCR_MODEL.model_id, LINEAR_TCR_MODEL.version)
        return any(model.key == wanted for model in problem.models)

    def prepare(
        self,
        problem: ScientificProblem,
        *,
        realization: ModelRealizationDefinition = LINEAR_TCR_REALIZATION,
    ) -> PreparedSolve:
        bound = self._bound.get(problem.problem_id)
        if bound is None:
            raise InvalidScientificProblem(
                f"no conductor is bound to problem {problem.problem_id!r}; "
                f"call bind_conductor first"
            )
        conductor, kelvin = bound
        # Refuse an inconsistent pairing before evaluating, not after
        # attributing. Same discipline as the sibling DC domain's
        # ``verify_problem_matches_circuit``.
        self.verify_problem_matches_conductor(problem, conductor)
        return PreparedSolve(
            problem=problem,
            solver=self.identity,
            settings=self.settings,
            payload=PreparedResistanceEvaluation(
                conductor=conductor,
                realization=realization,
                temperature_k=kelvin,
            ),
        )

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        evaluation: PreparedResistanceEvaluation = prepared.payload
        conductor = evaluation.conductor
        started = time.perf_counter()
        resistance = conductor.r_ref_ohm * (
            1.0
            + conductor.alpha_per_k * (evaluation.temperature_k - conductor.t_ref_k)
        )
        return RawSolverOutput(
            values={RESISTANCE_METRIC: resistance},
            # NOT_APPLICABLE, not CONVERGED: a direct evaluation neither
            # converges nor fails to, and conflating the two would overstate
            # what the backend reported.
            convergence=ConvergenceState.NOT_APPLICABLE,
            iterations=1,
            wall_seconds=time.perf_counter() - started,
            diagnostics={
                "temperature_k": evaluation.temperature_k,
                "delta_t_k": evaluation.temperature_k - conductor.t_ref_k,
            },
        )

    def extract_metrics(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> dict[str, Quantity]:
        if not raw.succeeded:
            return {}
        return {
            RESISTANCE_METRIC: Quantity(
                raw.values[RESISTANCE_METRIC], RESISTANCE_UNIT
            )
        }

    def validate(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationReport:
        """Two checks. One establishes a level; the other cannot, and says so.

        ``resistance_strictly_positive`` is an admissibility bound. A positive
        resistance is a precondition for the surrounding linear DC
        formulation, which refuses zero and negative resistances. It earns no
        ``ValidationLevel`` and could not: confirming that a number is in the
        physically admissible range is not verification against anything, and
        claiming a level for it would be exactly the unearned claim the result
        contract is built to refuse.

        ``metric_dimensions`` compares the emitted metric against the
        dimension its model record declares, on the pattern
        ``battery/solver.py`` already uses. That earns
        ``DIMENSIONALLY_VALID``, and the reason it is earned rather than
        asserted is that the ``ModelOutputSpec`` is a reference **outside this
        solver's arithmetic**: the solver did not write it, the model did, and
        a metric extracted into the wrong unit disagrees with it.

        Recorded in ``docs/domains/evidentiary-levels.md``. It is the smallest
        honest level this solver can attain, and until it existed every
        credibility package built on a resistance evaluation was
        ``INSUFFICIENT_EVIDENCE`` on the strength of one check that establishes
        nothing.
        """
        if not raw.succeeded:
            return ValidationReport(
                checks=(
                    ValidationCheck(
                        name="resistance_strictly_positive",
                        outcome=ValidationOutcome.FAIL,
                        detail="the evaluation did not succeed",
                    ),
                )
            )
        resistance = raw.values[RESISTANCE_METRIC]
        positive = resistance > 0.0
        return ValidationReport(
            checks=(
                ValidationCheck(
                    name="resistance_strictly_positive",
                    outcome=(
                        ValidationOutcome.PASS if positive else ValidationOutcome.FAIL
                    ),
                    establishes=None,
                    detail=(
                        f"R = {resistance:.6g} ohm. A linear TCR form crosses "
                        f"zero at a large enough negative excursion; a "
                        f"non-positive resistance is refused rather than "
                        f"passed downstream. Admissibility, not verification: "
                        f"this check establishes nothing and no rearrangement "
                        f"of it could."
                    ),
                ),
                self._dimension_check(prepared, raw),
            ),
            notes=(
                "Admissibility and dimensions. Whether the model was "
                "applicable at this temperature is a validity question and is "
                "answered by assess_resistance_validity, not here."
            ),
        )

    def _dimension_check(
        self, prepared: PreparedSolve, raw: RawSolverOutput
    ) -> ValidationCheck:
        """Every produced metric against the unit its model record declares."""
        declared = {
            spec.metric: spec.unit_exemplar
            for model in (LINEAR_TCR_MODEL, RATED_LINEAR_TCR_MODEL)
            for spec in model.outputs
        }
        produced = self.extract_metrics(prepared, raw)
        mismatched = [
            metric
            for metric, value in produced.items()
            if metric not in declared
            or not value.is_compatible_with(declared[metric])
        ]
        passed = not mismatched
        return ValidationCheck(
            name="metric_dimensions",
            outcome=(
                ValidationOutcome.PASS if passed else ValidationOutcome.FAIL
            ),
            # Conditional on the outcome, not attached unconditionally. A
            # report carrying `outcome: fail` beside `establishes:
            # dimensionally_valid` is a record that contradicts itself for any
            # reader who is not filtering on `passed` first.
            establishes=(
                ValidationLevel.DIMENSIONALLY_VALID if passed else None
            ),
            detail=(
                f"{len(produced)} produced metric(s) checked against the "
                f"dimensions their model records declare"
                + (f"; mismatched: {sorted(mismatched)}" if mismatched else "")
            ),
        )
