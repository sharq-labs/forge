"""When the ideal linear DC model stops describing the device.

Everything ``electrical/dc/models.py`` declares about a resistor and a source
is a **rating utilization** — how much of a published limit the operating point
consumes. Those are real conditions and they catch a real failure: a part used
past what it survives. None of them asks the other question, which is whether
the *relation* still describes the part while it is comfortably inside every
rating. A resistor at a tenth of its rated dissipation still has an element
hotter than its body, and the rating is written against the element; a supply
well inside its current limit still has an output impedance, and the terminal
voltage the solve imposed is not the terminal voltage it then holds.

Two conditions are declared here, over two model records that are the
falsifiable companions of two records in ``dc/models.py``. The base models are
unchanged and stay applicable exactly where they always were: this is the
``electrical.material.rated_linear_tcr_resistance`` relationship to
``electrical.material.linear_tcr_resistance``, one directory over — a narrower
claim beside a broader one, so that a caller can hold both answers at once and
neither can be mistaken for the other. Each is attached only when the caller
declares something it reads, the rule ``build_resistance_problem`` states as
*"widening the record only when the caller widened the declaration"*.

REMOVED: self_heating_resistance_drift_ratio
---------------------------------------------
This module declared a third condition, ``(|R_op - R_ref| / R_ref) /
resistance_tolerance <= 1``, on the argument that a self-heating drift larger
than the element's own tolerance band means the constant resistance the circuit
was designed with has stopped describing it.

**Wiring it into the electro-thermal boundary falsified it, and it is removed
rather than weakened.** The measurement: on this repository's own nominal
example the condition returns **17.85**, violated by a factor of eighteen, on a
design that is correct. The reason is that the coupled run does not solve the
circuit at ``R_ref``. It tears the temperature edge, iterates, and at
convergence the circuit is solved at ``R(T_converged)`` — 11.785 ohm against a
declared 10 ohm — so the drift this condition measures is exactly the effect
the composition **models**. Reporting a modelled effect as an unmodelled one is
a category error: a ``ValidityDomain`` condition says whether the model applies,
and here it applies.

Nor is there another regime that rescues it. Where the temperature is known the
condition is violated by construction; where it is not known — a standalone DC
solve, which carries no temperature at all — ``operating_resistance`` is
unavailable and the condition is UNKNOWN. There is no operating point at which
it says something true and useful about applicability.

What it was reaching for is real and is not lost: it is a statement about
*design intent* — a divider specified around a 10 ohm part is running an 11.79
ohm part — and that belongs somewhere a design review reads, not in a model's
validity domain. ``Damkoehler <= 10`` was removed rather than raised for the
same kind of reason, and this follows it.

Why a new module rather than more conditions on the existing records
---------------------------------------------------------------------
``src/engcore/domains/electrical/dc/`` is frozen by file name, and new material
belongs beside it. ``dc_consensus.py`` and ``dc_realizations.py`` already sit
here for the same reason.

NO NEW NUMERIC CONSTANT IS INTRODUCED BY EITHER
------------------------------------------------
Every bound below is **1, and definitional**: each quantity is constructed as
the fraction of a *declared* budget in use, so 1 is the budget and not a
threshold anybody chose. That is deliberate and it is the strongest form
available here. Three bounds in this repository have been checked against the
sources they cited and found unsupported, and the response is not to cite more
carefully but to stop needing a citation for a number — the physics is cited,
the number is the caller's.

What that costs is stated rather than hidden: a declared budget moves the
judgement to whoever declares it. A caller who declares a regulation band of
0.9 is told their source is inside it, and this module cannot tell them that
0.9 is an absurd band. What it can do, and does, is refuse to answer at all
until they say what the band is. UNKNOWN is the verdict for a part nobody
characterised, and neither of these has a default.

What was examined and rejected
-------------------------------
**A resistor's own high-frequency departure.** Real: above self-resonance a
resistor's impedance is not its resistance, and the discriminator is the ratio
of the operating frequency to that resonance. It is not declarable here.
``electrical.dc.kcl`` already carries the electrical-length argument, and it is
identically zero **by this domain's own scope** — ``f = 0`` is an assumption of
the record rather than a value anybody supplies. A resistor-specific copy would
be a second quantity that is zero for the same reason, from the same
assumption, with no circuit able to violate it. It would raise the condition
count by one and the falsifiability by nothing, which is the trade this module
exists to avoid.

**Contact and lead resistance against a low-value element.** Real, and it is
why four-terminal sensing exists: twenty milliohms of lead and joint resistance
against a 1 ohm element is a two-percent error before the part is powered,
outside the tolerance the element was specified to. Rejected on sourcing rather
than on physics. Contact resistance is a property of the *assembly* — the
solder joint, the socket, the trace — and not of any part; none of the 35
datasheets in ``benchmarks/ai_designs/components.json`` prints one, and nothing
in this repository computes one. The condition would be permanently UNKNOWN,
which is not a neutral outcome: an UNKNOWN condition degrades every verdict it
touches to INSUFFICIENT_EVIDENCE while never being able to say anything. The
contrast with ``output_resistance`` below is deliberate and is the reason that
one was kept: a source's internal resistance is a first-class published
characteristic of real supplies, and this repository already models one
directly in ``battery.cell.rint_ocv``.

**Current density in the element.** Rejected as not computable. The bound would
need the element's cross-section, and a film resistor's element is a
laser-trimmed helical track whose width and length no datasheet publishes; the
body dimensions that ``components.json`` does record are the package, not the
track, and deriving one from the other would be inventing a geometry. The limit
that would bound it is technology-specific — electromigration in a metal film
and fusing in a wire are different mechanisms with different numbers — and no
single sourceable value covers the parts this domain sees.

**Self-heating in the element rather than in the body** was the half of that
candidate worth keeping, and it is ``element_hot_spot_utilization`` below.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..derived_context import (
    DomainValidityContext,
    assembled_validity_context,
    assembler_namespace,
    caller_declared,
)
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.ir.variables import ScientificParameter
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
from ...scientific.units.quantity import Quantity
from .dc.models import ELECTRICAL_DC_LINEAR

__all__ = [
    "APPLICABILITY_MODELS",
    "ASSEMBLER_NAMESPACE",
    "BODY_TEMPERATURE",
    "DC_APPLICABILITY_VERSION",
    "DIMENSIONLESS",
    "DISSIPATED_POWER",
    "ELEMENT_HOT_SPOT_UTILIZATION",
    "ELEMENT_TEMPERATURE_LIMIT",
    "ELEMENT_TO_BODY_THERMAL_RESISTANCE",
    "OUTPUT_RESISTANCE",
    "PERMISSIBLE_ELEMENT_TEMPERATURE",
    "REGULATED_VOLTAGE_SOURCE_MODEL",
    "REGULATION_BAND",
    "REGULATION_BUDGET_LIMIT",
    "SELF_HEATED_RESISTOR_MODEL",
    "SOURCE_CURRENT",
    "SOURCE_REGULATION_UTILIZATION",
    "SOURCE_VOLTAGE",
    "assess_regulated_source_validity",
    "assess_self_heated_resistor_validity",
    "build_dc_applicability_registry",
    "element_hot_spot_utilization",
    "regulated_source_problem",
    "regulated_source_validity_context",
    "self_heated_resistor_problem",
    "self_heated_resistor_validity_context",
    "source_regulation_utilization",
]

DC_APPLICABILITY_VERSION = "0.1.0"

# --- units -------------------------------------------------------------------
VOLTAGE_UNIT = "volt"
CURRENT_UNIT = "ampere"
RESISTANCE_UNIT = "ohm"
POWER_UNIT = "watt"
TEMPERATURE_UNIT = "kelvin"
THERMAL_RESISTANCE_UNIT = "kelvin/watt"
DIMENSIONLESS = "dimensionless"

# --- names of the values a solve produces ------------------------------------
SOURCE_CURRENT = "source_current"
BODY_TEMPERATURE = "body_temperature"
DISSIPATED_POWER = "dissipated_power"

# --- names of the declarations these conditions read -------------------------
SOURCE_VOLTAGE = "source_voltage"
OUTPUT_RESISTANCE = "output_resistance"
REGULATION_BAND = "regulation_band"
ELEMENT_TO_BODY_THERMAL_RESISTANCE = "element_to_body_thermal_resistance"
PERMISSIBLE_ELEMENT_TEMPERATURE = "permissible_element_temperature"

# --- names of the derived groups the conditions are stated over --------------
SOURCE_REGULATION_UTILIZATION = "source_regulation_utilization"
ELEMENT_HOT_SPOT_UTILIZATION = "element_hot_spot_utilization"

#: **Definitional, not a threshold.** The quantity it bounds is the fraction of
#: the caller's own declared regulation band that the source's internal drop
#: consumes, so 1 *is* the band. There is no number here that a supply could
#: have printed and this module could have got wrong: how much droop a design
#: tolerates is the design's statement, and a supply's own load regulation is
#: published per part rather than being a value common to supplies. Any margin
#: belongs in the declared band, where it is visible, rather than in this
#: constant.
REGULATION_BUDGET_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: **Definitional.** The computed element temperature as a fraction of the
#: temperature the element is declared to permit, both on an absolute scale.
#: 1 is the permissible temperature. The same shape, and the same reason for
#: the bound, as ``operating_temperature_utilization`` in ``material.py``.
ELEMENT_TEMPERATURE_LIMIT = Quantity(1.0, DIMENSIONLESS)


# =====================================================================
# The two model records
# =====================================================================

REGULATED_VOLTAGE_SOURCE_MODEL = ScientificModelDefinition(
    exclusions=(
        "distributed and field effects; the circuit is lumped",
        "transients and reactive elements; steady-state DC only",
        "non-linear and time-varying elements",
        "the supply's behaviour outside the regulation band it was declared "
        "to hold",
        "any internal dynamics; the source is a Thevenin equivalent with one "
        "constant open-circuit voltage and one constant resistance",
    ),
    model_id="electrical.dc.regulated_voltage_source",
    version=DC_APPLICABILITY_VERSION,
    name="Ideal voltage source relation, inside a declared regulation band",
    domain="electrical",
    model_type=ModelType.APPROXIMATION,
    description=(
        "The same relation electrical.dc.ideal_voltage_source imposes — "
        "V(positive_node) - V(negative_node) = source_voltage irrespective of "
        "the current drawn — asserted only where the source's own internal "
        "drop stays inside the regulation band it was declared to hold. The "
        "companion record, not a replacement: the ideal model stays exactly as "
        "applicable as it was, and this one says where its zero-impedance "
        "assumption stops describing the supply."
    ),
    inputs=(
        ModelInputSpec(
            name=SOURCE_VOLTAGE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=VOLTAGE_UNIT,
            description="Imposed terminal voltage difference.",
        ),
        ModelInputSpec(
            name=SOURCE_CURRENT,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=CURRENT_UNIT,
            description=(
                "Branch current the network draws through the source. A "
                "VARIABLE: it is what the solve produced, never a declaration."
            ),
        ),
        ModelInputSpec(
            name=OUTPUT_RESISTANCE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=RESISTANCE_UNIT,
            required=False,
            description=(
                "The source's own series resistance — the R in the Thevenin "
                f"equivalent. Unlocks {SOURCE_REGULATION_UTILIZATION} together "
                f"with {REGULATION_BAND}."
            ),
        ),
        ModelInputSpec(
            name=REGULATION_BAND,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=DIMENSIONLESS,
            required=False,
            description=(
                "The fraction of the terminal voltage this design permits the "
                "source to droop by, strictly positive. A declaration about "
                "the design, not about the part: how much droop matters "
                "depends on what is downstream of it."
            ),
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="terminal_voltage",
            unit_exemplar=VOLTAGE_UNIT,
            description=(
                "V(positive_node) - V(negative_node), asserted equal to "
                "source_voltage."
            ),
        ),
    ),
    assumptions=(
        "lumped-element circuit (no distributed or field effects)",
        "steady-state DC operation (no transients, no reactive elements)",
        "linear, time-invariant elements",
        "the source is a Thevenin equivalent: one constant open-circuit "
        "voltage in series with one constant resistance",
        "the internal drop is small enough that the imposed terminal voltage "
        "is still the terminal voltage",
    ),
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=SOURCE_REGULATION_UTILIZATION,
                maximum=REGULATION_BUDGET_LIMIT,
                description=(
                    "(|I| * output_resistance / |source_voltage|) / "
                    "regulation_band <= 1. THE MODEL'S OWN ASSUMPTION IS ZERO "
                    "INTERNAL IMPEDANCE, and this is that assumption made "
                    "falsifiable. A real source is a Thevenin equivalent, one "
                    "open-circuit voltage in series with one resistance, so "
                    "the terminal voltage it actually holds is V_oc - I*R_out "
                    "and the fraction of the imposed voltage lost inside the "
                    "source is |I|*R_out / |V|. That fraction is what this "
                    "condition computes; the caller's regulation_band is what "
                    "it is measured against. DISTINCT FROM "
                    "source_current_utilization, which asks whether the source "
                    "can deliver the current at all: a supply an order of "
                    "magnitude inside its current limit still has an output "
                    "impedance, and the two conditions fail independently. "
                    "The bound of 1 is DEFINITIONAL, being the fraction of the "
                    "declared band in use, and this module introduces no "
                    "numeric constant for it: how much droop a design "
                    "tolerates is the design's statement and no datasheet "
                    "prints it. The physical form is the Thevenin equivalent; "
                    "the output resistance is the supply's own published "
                    "characteristic, and this repository already models a "
                    "source that has one in battery.cell.rint_ocv. UNKNOWN "
                    "unless both an output_resistance and a regulation_band "
                    "are declared, and unless the solve supplied a current. "
                    "**What this does not check**: that the declared output "
                    "resistance is the right one for this operating point. A "
                    "switching supply's is a function of load and of "
                    "frequency, and this domain fixes frequency at zero, so "
                    "what is bounded here is the DC droop and nothing about "
                    "the transient response to a load step."
                ),
            ),
        ),
        description=(
            "Applicable while the source's internal drop stays inside the "
            "regulation band declared for it. Not validated near or beyond "
            "that band, where the terminal voltage is set by the load."
        ),
        # Reserved. The utilization is computed here from a solved current and
        # two declarations; a caller parameter of this name would decide the
        # condition that reads it, which is a source with no characterisation
        # at all reporting IN_DOMAIN over a number nobody derived.
        derived_quantities=frozenset({SOURCE_REGULATION_UTILIZATION}),
    ),
    required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


SELF_HEATED_RESISTOR_MODEL = ScientificModelDefinition(
    exclusions=(
        "distributed and field effects; the circuit is lumped",
        "transients and reactive elements; steady-state DC only",
        "non-linear and time-varying elements",
        "temperature non-uniformity over the element, apart from the single "
        "element-to-body drop this record's own condition computes",
        "any change of resistance over the run; one resistance describes the "
        "element throughout",
    ),
    model_id="electrical.dc.self_heated_resistor",
    version=DC_APPLICABILITY_VERSION,
    name="Resistor constitutive relation for an element the run heats",
    domain="electrical",
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "V = I R for a real element, asserted only where the heat the element "
        "dissipates has not moved it out of the description the circuit was "
        "solved against. electrical.dc.resistor_ohm declares "
        "'temperature-independent resistance' among its assumptions; this "
        "record is where that assumption is checked against the temperature an "
        "electro-thermal run actually computes, and against the element's own "
        "temperature limit rather than its body's."
    ),
    inputs=(
        ModelInputSpec(
            name=BODY_TEMPERATURE,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=TEMPERATURE_UNIT,
            description=(
                "The body temperature the thermal model converged to. "
                "Absolute scale."
            ),
        ),
        ModelInputSpec(
            name=DISSIPATED_POWER,
            source_kind=InputSourceKind.VARIABLE,
            unit_exemplar=POWER_UNIT,
            description="Power absorbed by the element at the operating point.",
        ),
        ModelInputSpec(
            name=ELEMENT_TO_BODY_THERMAL_RESISTANCE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=THERMAL_RESISTANCE_UNIT,
            required=False,
            description=(
                "Thermal resistance from the resistive element to the body "
                "whose temperature the run computes — a datasheet's "
                "element-to-case or film-to-case figure. **An "
                "ambient-referenced thermal resistance is the wrong number "
                "here** and would double-count the body's own rise. That "
                "distinction is not academic and this repository has already "
                "hit it: nine parts in components.json print a thermal "
                "resistance and exactly one records which end it refers to "
                "(`thermal_resistance_kind` = junction-to-case, 6.5 K/W). The "
                "three others that also print a derating line print a figure "
                "of the same size as that line's own slope, "
                "(T_zero - T_rated) / P_rated -- 170 against 170, 200 against "
                "212.5, 150 against 170 -- which is an ambient-to-film "
                "quantity and not this one. The name of this input is long "
                "for that reason. Unlocks "
                f"{ELEMENT_HOT_SPOT_UTILIZATION} together with "
                f"{PERMISSIBLE_ELEMENT_TEMPERATURE}."
            ),
        ),
        ModelInputSpec(
            name=PERMISSIBLE_ELEMENT_TEMPERATURE,
            source_kind=InputSourceKind.PARAMETER,
            unit_exemplar=TEMPERATURE_UNIT,
            required=False,
            description=(
                "The highest temperature the resistive element itself is "
                "declared to permit — a film resistor's permissible film "
                "temperature. Absolute scale."
            ),
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric="current_through",
            unit_exemplar=CURRENT_UNIT,
            description="Current node_a -> node_b.",
        ),
        ModelOutputSpec(
            metric="dissipated_power",
            unit_exemplar=POWER_UNIT,
            description="Absorbed power, V*I = I^2 R (non-negative).",
        ),
    ),
    assumptions=(
        "lumped-element circuit (no distributed or field effects)",
        "steady-state DC operation (no transients, no reactive elements)",
        "linear, time-invariant elements",
        "the element's temperature is uniform over it, apart from the single "
        "element-to-body drop this record's own condition computes",
        "one resistance describes the element over the whole run",
    ),
    validity=ValidityDomain(
        conditions=(
            RangeCondition(
                name=ELEMENT_HOT_SPOT_UTILIZATION,
                maximum=ELEMENT_TEMPERATURE_LIMIT,
                description=(
                    "(T_body + |P| * element_to_body_thermal_resistance) / "
                    "permissible_element_temperature <= 1, both temperatures "
                    "absolute. THE ELEMENT IS NOT THE BODY. A lumped thermal "
                    "model assigns the part one temperature, and a resistive "
                    "element sits above it by its own dissipation times its "
                    "own thermal resistance -- the PWR220T-20 in "
                    "components.json prints 6.5 K/W junction-to-case, which is "
                    "13 K at 2 W. What the rating protects is the "
                    "element: IEC 60115-1 Clause 2 requires a derating "
                    "characteristic above the rated ambient precisely because "
                    "the film has a permissible temperature, and a datasheet "
                    "prints that temperature alongside a thermal resistance "
                    "for exactly this calculation. DISTINCT FROM "
                    "dissipated_power_utilization, which evaluates the same "
                    "derating line at the DECLARED AMBIENT: in a coupled run "
                    "the body is above the ambient by whatever rise the "
                    "thermal model computed, and reading the rating at the "
                    "ambient throws that rise away. This condition reads the "
                    "temperature the run produced. The bound of 1 is "
                    "DEFINITIONAL -- the computed temperature as a fraction of "
                    "the declared permissible one -- and no constant is "
                    "introduced. UNKNOWN unless both the thermal resistance "
                    "and the permissible temperature are declared and the run "
                    "supplied a body temperature and a dissipation."
                ),
            ),
        ),
        description=(
            "Ohm's law for an element inside its own tolerance band and below "
            "its own permissible temperature, at the operating point a coupled "
            "run actually reached."
        ),
        derived_quantities=frozenset({ELEMENT_HOT_SPOT_UTILIZATION}),
    ),
    required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
)


APPLICABILITY_MODELS = (
    REGULATED_VOLTAGE_SOURCE_MODEL,
    SELF_HEATED_RESISTOR_MODEL,
)

#: Every name these conditions read that no caller may supply.
ASSEMBLER_NAMESPACE = assembler_namespace(APPLICABILITY_MODELS)


# =====================================================================
# The derivations
# =====================================================================
#
# Pure functions. Each returns ``None`` when it was not given everything it
# needs, and the context builders drop the key rather than inventing a value,
# so a missing declaration reaches ``ValidityDomain.assess`` as UNKNOWN. There
# is no path here by which omitting an input yields IN_DOMAIN.


def _magnitude(value: Any, unit: str, label: str) -> float | None:
    """A supplied quantity's magnitude in ``unit``; ``None`` stays ``None``.

    A non-``Quantity`` that is not ``None`` is refused rather than skipped, the
    same rule ``dc/models.py`` applies: a caller who passed the wrong type
    declared something wrong, which is a different situation from a caller who
    declared nothing, and collapsing the two would turn a specification error
    into a silent UNKNOWN.
    """
    if value is None:
        return None
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    value.require_compatible(unit, context=label)
    return value.magnitude_in(unit)


def _positive(value: float | None, label: str) -> float | None:
    """A denominator that is zero or negative is a specification error.

    Not a silent ``None``: dividing by it would report an infinity as though it
    were a measurement, and clamping it would answer a question the caller did
    not ask. A band of zero is not a very tight band, it is a declaration that
    nothing is tolerable, which no operating point can satisfy and which the
    caller almost certainly did not mean.
    """
    if value is None:
        return None
    if value <= 0.0:
        raise InvalidScientificProblem(
            f"{label} must be strictly positive, got {value!r}"
        )
    return value


def source_regulation_utilization(
    *,
    source_current: Quantity | None = None,
    source_voltage: Quantity | None = None,
    output_resistance: Quantity | None = None,
    regulation_band: Quantity | None = None,
) -> Quantity | None:
    """``(|I| R_out / |V|) / band``, or ``None`` if anything is missing.

    The absolute value is taken on the current and on the voltage: a band is a
    magnitude and the signs are directions, so a source sinking 2 A departs
    from its imposed voltage exactly as far as one sourcing 2 A.
    """
    current = _magnitude(source_current, CURRENT_UNIT, SOURCE_CURRENT)
    voltage = _magnitude(source_voltage, VOLTAGE_UNIT, SOURCE_VOLTAGE)
    resistance = _magnitude(
        output_resistance, RESISTANCE_UNIT, OUTPUT_RESISTANCE
    )
    band = _positive(
        _magnitude(regulation_band, DIMENSIONLESS, REGULATION_BAND),
        REGULATION_BAND,
    )
    if current is None or voltage is None or resistance is None or band is None:
        return None
    magnitude = _positive(abs(voltage), f"|{SOURCE_VOLTAGE}|")
    return Quantity(
        (abs(current) * resistance / magnitude) / band, DIMENSIONLESS
    )


def element_hot_spot_utilization(
    *,
    body_temperature: Quantity | None = None,
    dissipated_power: Quantity | None = None,
    element_to_body_thermal_resistance: Quantity | None = None,
    permissible_element_temperature: Quantity | None = None,
) -> Quantity | None:
    """``(T_body + |P| R_th) / T_permissible``, or ``None``.

    Both temperatures are absolute, the convention every temperature
    utilization in this repository uses. The dissipation's magnitude is taken:
    the element absorbs power in either current direction.
    """
    body = _magnitude(body_temperature, TEMPERATURE_UNIT, BODY_TEMPERATURE)
    power = _magnitude(dissipated_power, POWER_UNIT, DISSIPATED_POWER)
    thermal = _magnitude(
        element_to_body_thermal_resistance,
        THERMAL_RESISTANCE_UNIT,
        ELEMENT_TO_BODY_THERMAL_RESISTANCE,
    )
    permissible = _positive(
        _magnitude(
            permissible_element_temperature,
            TEMPERATURE_UNIT,
            PERMISSIBLE_ELEMENT_TEMPERATURE,
        ),
        PERMISSIBLE_ELEMENT_TEMPERATURE,
    )
    if body is None or power is None or thermal is None or permissible is None:
        return None
    return Quantity((body + abs(power) * thermal) / permissible, DIMENSIONLESS)


# =====================================================================
# Contexts and assessments
# =====================================================================


def regulated_source_validity_context(
    problem: ScientificProblem,
    *,
    source_current: Quantity | None = None,
) -> DomainValidityContext:
    """The context :data:`REGULATED_VOLTAGE_SOURCE_MODEL` is assessed against.

    ``source_current`` arrives as an argument rather than out of the problem's
    parameters because it is a *result*: it is what the network solve produced,
    and the model record declares it a VARIABLE for that reason. The output
    resistance and the regulation band are declarations and are read from the
    problem, with every reserved name stripped first, so a caller cannot supply
    the utilization itself.
    """
    declared = caller_declared(
        problem.validity_context(reserved=ASSEMBLER_NAMESPACE),
        ASSEMBLER_NAMESPACE,
    )
    utilization = source_regulation_utilization(
        source_current=source_current,
        source_voltage=declared.get(SOURCE_VOLTAGE),
        output_resistance=declared.get(OUTPUT_RESISTANCE),
        regulation_band=declared.get(REGULATION_BAND),
    )
    return assembled_validity_context(
        declared=declared,
        assembled=(
            {}
            if utilization is None
            else {SOURCE_REGULATION_UTILIZATION: utilization}
        ),
        reserved=ASSEMBLER_NAMESPACE,
    )


def assess_regulated_source_validity(
    problem: ScientificProblem,
    *,
    source_current: Quantity | None = None,
) -> ValidityAssessment:
    """Did the ideal source relation still describe this supply at this current?

    The strong sibling of ``assess_voltage_source_validity`` in
    ``dc/models.py``. That one asks whether the source can deliver the current
    at all; this one asks whether, having delivered it, the source is still
    holding the voltage the solve imposed.
    """
    return regulated_source_validity_context(
        problem, source_current=source_current
    ).assess(REGULATED_VOLTAGE_SOURCE_MODEL)


def self_heated_resistor_validity_context(
    problem: ScientificProblem,
    *,
    body_temperature: Quantity | None = None,
    dissipated_power: Quantity | None = None,
) -> DomainValidityContext:
    """The context :data:`SELF_HEATED_RESISTOR_MODEL` is assessed against.

    Three arguments, all of them results: the resistance the material model
    computed at the converged temperature, the temperature the thermal model
    converged to, and the power the circuit solve dissipated. The reference
    resistance, the tolerance, the thermal resistance and the permissible
    element temperature are declarations and come from the problem.
    """
    declared = caller_declared(
        problem.validity_context(reserved=ASSEMBLER_NAMESPACE),
        ASSEMBLER_NAMESPACE,
    )
    derived: dict[str, Quantity | None] = {
        ELEMENT_HOT_SPOT_UTILIZATION: element_hot_spot_utilization(
            body_temperature=body_temperature,
            dissipated_power=dissipated_power,
            element_to_body_thermal_resistance=declared.get(
                ELEMENT_TO_BODY_THERMAL_RESISTANCE
            ),
            permissible_element_temperature=declared.get(
                PERMISSIBLE_ELEMENT_TEMPERATURE
            ),
        ),
    }
    return assembled_validity_context(
        declared=declared,
        assembled={
            name: value for name, value in derived.items() if value is not None
        },
        reserved=ASSEMBLER_NAMESPACE,
    )


def assess_self_heated_resistor_validity(
    problem: ScientificProblem,
    *,
    body_temperature: Quantity | None = None,
    dissipated_power: Quantity | None = None,
) -> ValidityAssessment:
    """Was Ohm's law with a constant R still describing this element, here?

    The strong sibling of ``assess_resistor_validity`` in ``dc/models.py``.
    That one asks whether the element survived the operating point; this one
    asks whether the element the circuit was solved with is still the element
    that was sitting there when it finished.
    """
    return self_heated_resistor_validity_context(
        problem,
        body_temperature=body_temperature,
        dissipated_power=dissipated_power,
    ).assess(SELF_HEATED_RESISTOR_MODEL)


def build_dc_applicability_registry() -> ModelRegistry:
    """A fresh registry holding the two companion records.

    Returns a new instance every call, for the reason
    ``build_dc_model_registry`` does: the platform has no global mutable model
    registry, so a caller's model set can never be mutated elsewhere.
    """
    return ModelRegistry(APPLICABILITY_MODELS)


# =====================================================================
# The problems these records are assessed against
# =====================================================================
#
# Both follow `material.build_resistance_problem` exactly, including its rule:
# a problem carries the companion `ModelReference` **only** when the caller
# declared something the companion reads. Widening the record only when the
# caller widened the declaration is what keeps the narrow claim and the broad
# one independently reportable — and it is why a caller who never characterised
# their element is not told their design is under-evidenced against a question
# they did not ask. What omission does *not* do is satisfy a condition: a
# companion that is attached and half-declared leaves its condition UNKNOWN,
# exactly as every rating condition does.


def _parameters(declared: Mapping[str, Any]) -> tuple[ScientificParameter, ...]:
    """The supplied declarations as typed parameters, in a fixed order.

    Absent entries are dropped rather than carried as ``None``: a parameter
    with no value is a declaration nobody made, and the assessment must see
    its absence rather than a null.

    A bare float becomes a dimensionless ``Quantity``, for the reason
    ``dc_models.rating_declarations`` does the same to ``derating_factor``: a
    payload carries a band as a plain number because it is a fraction rather
    than a measurement, and a condition comparing it against a bound needs the
    two to share a dimension.
    """
    return tuple(
        ScientificParameter(
            name=name,
            value=(
                Quantity(float(value), DIMENSIONLESS)
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else value
            ),
        )
        for name, value in sorted(declared.items())
        if value is not None
    )


def self_heated_resistor_problem(
    component_id: str, declared: Mapping[str, Any]
) -> ScientificProblem:
    """One element's companion problem.

    ``declared`` carries whatever of :data:`ELEMENT_TO_BODY_THERMAL_RESISTANCE`
    and :data:`PERMISSIBLE_ELEMENT_TEMPERATURE` the caller supplied. Supplying
    neither produces a problem with no companion model reference, which is how
    a caller who did not ask this question is not answered it.
    """
    parameters = _parameters(declared)
    return ScientificProblem(
        problem_id=f"electrical_dc_self_heated_resistor:{component_id}",
        name=f"Element applicability of resistor {component_id!r}",
        description=(
            "Whether the constant-resistance element relation still describes "
            "this part at the temperature the run put its element at."
        ),
        parameters=parameters,
        models=(
            (
                ModelReference(
                    SELF_HEATED_RESISTOR_MODEL.model_id,
                    SELF_HEATED_RESISTOR_MODEL.version,
                ),
            )
            if parameters
            else ()
        ),
        required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    )


def regulated_source_problem(
    component_id: str, declared: Mapping[str, Any]
) -> ScientificProblem:
    """One source's companion problem.

    ``declared`` carries :data:`SOURCE_VOLTAGE` — which the source always has —
    plus whatever of :data:`OUTPUT_RESISTANCE` and :data:`REGULATION_BAND` the
    caller supplied. The model reference is attached only when at least one of
    those two is present, so a source voltage on its own does not widen the
    record: the imposed voltage is what the *ideal* model already asserts, and
    the narrower claim needs something the caller said about the real supply.
    """
    parameters = _parameters(declared)
    widened = any(
        declared.get(name) is not None
        for name in (OUTPUT_RESISTANCE, REGULATION_BAND)
    )
    return ScientificProblem(
        problem_id=f"electrical_dc_regulated_source:{component_id}",
        name=f"Regulation applicability of source {component_id!r}",
        description=(
            "Whether the imposed terminal voltage is still the terminal "
            "voltage once the source's own internal drop is accounted for."
        ),
        parameters=parameters,
        models=(
            (
                ModelReference(
                    REGULATED_VOLTAGE_SOURCE_MODEL.model_id,
                    REGULATED_VOLTAGE_SOURCE_MODEL.version,
                ),
            )
            if widened
            else ()
        ),
        required_capabilities=frozenset({ELECTRICAL_DC_LINEAR.name}),
    )
