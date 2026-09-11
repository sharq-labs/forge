"""Scientific model records for the equivalent-circuit battery cell.

Four models are declared, each a versioned scientific claim with typed inputs
and outputs, declared assumptions and a validity domain. They are
*representations*: nothing here executes, and execution belongs to
``solver.py``.

Why four records and not one
----------------------------
A caller can accept or reject each of these independently, and merging them
would take that away:

- ``battery.cell.rint_ocv`` claims that one series resistance and an affine
  open-circuit voltage describe the terminal behaviour.
- ``battery.cell.coulomb_counting`` claims that integrating current against a
  nominal capacity tracks the state of charge. It is true of cells whose
  terminal behaviour the Rint model gets badly wrong.
- ``battery.cell.constant_current_runtime`` claims that the time to a declared
  cutoff follows from the two above. It adds the consistency of the *two*
  cutoffs, which neither of the others can see.
- ``battery.cell.peukert_capacity_derating`` claims a fitted power law between
  discharge current and deliverable charge. It is an empirical correlation, its
  exponent is not a constant of the cell, and a caller who wants the first
  three has no obligation to take it. It is emphatically **not** a correction
  bolted onto coulomb counting: it is a separate claim with its own domain, and
  a study may run the counter and refuse the derating.

Honesty notes
-------------
* ``validation_status`` is ``SELF_CONSISTENT`` on the three closed forms, and
  ``UNVALIDATED`` on the Peukert record. Nothing here was measured. The solver
  checks each closed form against the relation it solves and against its own
  dimensions, and the checks say exactly which level that establishes.
* The Peukert record is ``UNVALIDATED`` rather than ``SELF_CONSISTENT``
  because there is no differential balance to check it against: it is a fitted
  correlation, and evaluating it correctly establishes nothing about whether it
  holds. Self-consistency is available to a closed form that solves an
  equation; it is not available to a curve fit.
* ``references`` carry the sources the conditions rest on. A source that
  belongs to one *condition* rather than to the model as a whole is cited in
  that condition's ``description``, which is where a reader auditing the bound
  will look.

The thresholds
--------------
Every number below is a named constant with a stated basis, and every one is a
bound on a quantity *derived* in ``context.py``, never on a number the caller
wrote down. Fifteen of the sixteen are 1 or 0 — "you have consumed all of the
budget you declared", or "you are on the edge of the interval you declared" —
which is definitional and needs no citation. Exactly one is a real number,
:data:`POLARIZATION_UNMODELLED_CEILING`, and it is labelled a **convention** in
the constant, in the condition description, in the documentation row and in the
test that pins it. It is not dressed as a citation.
"""

from __future__ import annotations

from ...scientific.capabilities import ScientificCapability
from ...scientific.ir.problem import ModelReference
from ...scientific.ir.variables import VariableRole
from ...scientific.models.definition import (
    InputSourceKind,
    ModelInputSpec,
    ModelOutputSpec,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
)
from ...scientific.models.registry import ModelRegistry
from ...scientific.realizations.definition import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
)
from ...scientific.realizations.registry import RealizationRegistry
from ...scientific.solvers.capability import (
    CoreCapabilities,
    SolverCapability,
    SolverCapabilityId,
)
from ...scientific.units.quantity import Quantity
from .context import (
    CAPACITY_REFERENCE_TEMPERATURE,
    CAPACITY_TEMPERATURE_DRIFT_RATIO,
    CAPACITY_TEMPERATURE_SPAN,
    CAPACITY_UNIT,
    CELL_TEMPERATURE,
    CELL_THERMAL_CONDUCTANCE,
    CONDUCTANCE_UNIT,
    CONTINUOUS_C_RATE_UTILIZATION,
    CONTINUOUS_DISCHARGE_C_RATE,
    COULOMBIC_EFFICIENCY,
    CURRENT_UNIT,
    CUTOFF_CONSISTENCY_MARGIN,
    CUTOFF_REACHABILITY_MARGIN,
    CUTOFF_STATE_OF_CHARGE,
    CUTOFF_VOLTAGE,
    C_RATE_UNIT,
    DIMENSIONLESS,
    DISCHARGE_CURRENT,
    DISCHARGE_TEMPERATURE_POSITION,
    DURATION,
    INTERNAL_RESISTANCE,
    INTERNAL_RESISTANCE_DRIFT_RATIO,
    MAXIMUM_DISCHARGE_TEMPERATURE,
    MINIMUM_DISCHARGE_TEMPERATURE,
    NOMINAL_CAPACITY,
    OCV_AT_EMPTY,
    OCV_AT_FULL,
    OCV_CURVE,
    PEUKERT_CAPACITY_RATIO,
    PEUKERT_EXPONENT,
    PEUKERT_EXTRAPOLATION_RATIO,
    PEUKERT_FIT_DECADES,
    PEUKERT_REFERENCE_CURRENT,
    PEUKERT_REFERENCE_TEMPERATURE,
    PEUKERT_TEMPERATURE_DRIFT_RATIO,
    PEUKERT_TEMPERATURE_SPAN,
    POLARIZATION_TIME_CONSTANT,
    POLARIZATION_UNMODELLED_FRACTION,
    PULSE_CURRENT,
    PULSE_C_RATE_UTILIZATION,
    PULSE_DISCHARGE_C_RATE,
    PULSE_DURATION,
    PULSE_DURATION_UTILIZATION,
    RATED_PULSE_DURATION,
    RESISTANCE_REFERENCE_TEMPERATURE,
    RESISTANCE_TEMPERATURE_SPAN,
    RESISTANCE_UNIT,
    SELF_HEATING_RISE_BOUND,
    SELF_HEATING_RISE_RATIO,
    SOC_STEP_RESOLUTION,
    SOC_STEP_RESOLUTION_RATIO,
    SOC_WINDOW_MARGIN,
    STATE_OF_CHARGE,
    TEMPERATURE_UNIT,
    TERMINAL_VOLTAGE_RATIO,
    TIME_UNIT,
    USABLE_SOC_MAXIMUM,
    USABLE_SOC_MINIMUM,
    VOLTAGE_UNIT,
)

MODEL_VERSION = "0.1.0"
REALIZATION_VERSION = "0.1.0"

# --- metric names ------------------------------------------------------------
# Distinct from the declaration names, and deliberately so. ``state_of_charge``
# the STATE variable is the cell's charge at the start of the interval;
# ``final_state_of_charge`` the metric is its charge at the end. Both are
# dimensionless, so a shared name would let one identifier denote two time
# levels of the same physical quantity with nothing — not even a dimension
# check — able to notice.
TERMINAL_VOLTAGE_METRIC = "terminal_voltage"
OPEN_CIRCUIT_VOLTAGE_METRIC = "open_circuit_voltage"
HEAT_GENERATION_METRIC = "heat_generation"
FINAL_STATE_OF_CHARGE_METRIC = "final_state_of_charge"
RUNTIME_METRIC = "runtime_to_cutoff"
EFFECTIVE_CAPACITY_METRIC = "effective_capacity"

# --- capabilities, declared here and nowhere else ----------------------------

#: What science this provides. A *scientific* capability: which physical
#: operation is available, not which computational operation a backend runs.
#:
#: Deliberately ``battery:cell_terminal_state`` and not
#: ``battery:rint_terminal_state``. A consumer that needs a cell's terminal
#: voltage and heat needs those quantities; whether they came from a single
#: series resistance or from a resolved electrochemical model is a property of
#: *this* realization, stated in its ``formulation`` and ``assumptions``.
CELL_TERMINAL_STATE = ScientificCapability.parse("battery:cell_terminal_state")

#: What science this *needs* to place a temperature-dependent condition. It is
#: declared by identifier and no thermal module is imported by this file: the
#: dependency is a machine-checkable fact, not a code coupling. The sibling
#: electrical material model declares the same identifier for the same reason.
REQUIRED_BODY_TEMPERATURE = ScientificCapability.parse("thermal:body_temperature")

#: What a backend must be able to do.
CELL_DISCHARGE_STEP = SolverCapability(
    "battery:cell_discharge_step",
    "One interval of constant-current discharge of an equivalent-circuit cell",
)


# =====================================================================
# Thresholds
# =====================================================================

#: Utilization <= 1 for any rating the caller declared. Not a tolerance and not
#: a safety factor: the ratio is *defined* as "fraction of the declared rating
#: in use", so 1 is the rating. Any margin a caller wants belongs in the
#: rating they declare, where it is visible, and not in a number buried here.
#: Used by the continuous C-rate, pulse C-rate and pulse duration conditions.
RATING_UTILIZATION_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: Ratio <= 1 for any property span the caller declared. Same definitional
#: reading: the caller states the span over which one measured value may be
#: treated as carrying, and the condition asks whether the operating point
#: stayed inside the caller's own statement. Used by the internal-resistance
#: drift, capacity drift, self-heating and Peukert conditions.
DECLARED_BUDGET_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: Margin >= 0 for the declared state-of-charge window. Definitional: the
#: margin is the run's distance from the nearest edge, so 0 is the edge and
#: negative is outside. Touching an edge is inside the window the caller
#: declared, so the bound is inclusive.
WINDOW_MARGIN_FLOOR = Quantity(0.0, DIMENSIONLESS)

#: Position within [0, 1] of the declared discharge temperature range. Both
#: bounds are definitional: 0 is the low edge the caller declared and 1 the
#: high edge, and the position is constructed to make it so.
TEMPERATURE_POSITION_FLOOR = Quantity(0.0, DIMENSIONLESS)
TEMPERATURE_POSITION_CEILING = Quantity(1.0, DIMENSIONLESS)

#: V / OCV > 0, strictly. A hard physical bound rather than a tolerance, and
#: the exact analogue of the sibling electrical domain's
#: ``MINIMUM_LINEAR_RESISTANCE_RATIO``: ``V = OCV - I R`` is a straight line in
#: I and every straight line with a non-zero slope crosses zero. Past the
#: crossing the expression does not describe a deeply loaded cell but one
#: sourcing current at a negative terminal voltage, which the Rint circuit has
#: no basis to assert. The bound is the physics of the computed quantity, so it
#: is exactly zero and needs no source.
MINIMUM_TERMINAL_VOLTAGE_RATIO = Quantity(0.0, DIMENSIONLESS)

#: Step span <= the declared state-of-charge resolution. Definitional in the
#: same way as the rating utilizations: the caller states how far one step may
#: walk down the charge axis before the once-per-step evaluation of OCV and
#: terminal voltage stops representing it, and the condition asks whether the
#: step stayed inside that.
STEP_RESOLUTION_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: Margin >= 0 between the two declared cutoffs. Definitional: the margin is
#: the declared state-of-charge cutoff minus the state of charge at which the
#: terminal voltage reaches the declared voltage cutoff, so 0 is the case where
#: the two coincide and negative is the case where the voltage limit stops the
#: run before the requested depth of discharge is reached. Zero is admissible:
#: the two cutoffs meeting exactly is consistent, not a violation.
CUTOFF_CONSISTENCY_FLOOR = Quantity(0.0, DIMENSIONLESS)

#: Q_eff / Q_nom <= 1. Definitional and directional rather than a tolerance:
#: Peukert's law describes capacity *lost* to rate. Above the reference current
#: it derates, which is its content; below the reference current the same
#: expression predicts a cell delivering more than the capacity it is rated
#: for, which is the formula read outside the direction it means anything in.
#: Peukert (1897); Doerffel & Sharkh, J. Power Sources 155 (2006), 395-400.
PEUKERT_DERATING_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: Ceiling on ``min(f, 1 - f)``, the fraction of the diffusion overpotential
#: still in motion at the end of the interval, for ``f = 1 - exp(-t/tau_pol)``.
#:
#: **The physics is cited; the number is not.** Plett, *Battery Management
#: Systems, Volume I: Battery Modeling* (Artech House, 2015), Ch. 3, adds a
#: series RC branch to the Rint model, which is what establishes that the
#: omitted overpotential relaxes as ``1 - exp(-t/tau)``. Plett prints no
#: threshold for this quantity, and neither does any other text in this
#: repository's bibliography.
#:
#: **0.05 is one convention read from both ends.** Five per cent is the
#: universal engineering reading of "done" for a first-order response — it is
#: the same reading that makes "three time constants" mean settled, since
#: ``exp(-3) = 0.050``. Applied to ``min(f, 1 - f)`` it admits two regimes and
#: excludes the band between them:
#:
#: * settled, ``f >= 0.95``, i.e. ``t >= 3.0 tau_pol``;
#: * undeveloped, ``f <= 0.05``, i.e. ``t <= 0.051 tau_pol``.
#:
#: **Both of those bounds are conventions**, not citations, and a study that
#: wants a different reading of "done" should say so rather than find either
#: number wearing a citation.
#:
#: **What this bound does not check.** Which regime is admissible depends on
#: how the caller's ``R_int`` was characterised — a settled-interval
#: measurement contains the diffusion contribution, a short-pulse measurement
#: does not — and this domain has no declaration for that. The condition
#: screens the timescale only. Recorded in ``NEEDS.md``.
POLARIZATION_UNMODELLED_CEILING = Quantity(0.05, DIMENSIONLESS)


# =====================================================================
# Shared input specs and assumptions
# =====================================================================

_CELL_PARAMETERS = (
    ModelInputSpec(
        name=NOMINAL_CAPACITY,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=CAPACITY_UNIT,
        description=(
            "Total charge the cell is rated to deliver; strictly positive. "
            "Rated under stated conditions — see the capacity drift condition."
        ),
    ),
    ModelInputSpec(
        name=INTERNAL_RESISTANCE,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=RESISTANCE_UNIT,
        description=(
            "Series resistance of the Rint circuit; strictly positive. A "
            "single value measured at one temperature over one interval."
        ),
    ),
    ModelInputSpec(
        name=OCV_AT_FULL,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=VOLTAGE_UNIT,
        description="Open-circuit voltage at a state of charge of 1.",
    ),
    ModelInputSpec(
        name=OCV_AT_EMPTY,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=VOLTAGE_UNIT,
        description="Open-circuit voltage at a state of charge of 0.",
    ),
)

#: The same open-circuit voltage the two endpoints above approximate, declared
#: instead as a curve against state of charge.
#:
#: ``varies_with`` is what makes this input curve-valued, and it names the axis
#: rather than leaving a consumer to infer it from a table's shape. A caller
#: declaring a measured OCV curve supplies this and omits the two endpoints,
#: which are then derived from the curve's ends; a caller declaring neither
#: gets the chord, which is what every cell in this repository does today.
#:
#: ``required=False``, so this widens what may be declared and requires
#: nothing. Omitting it changes no verdict: the chord answers exactly as it
#: did before this input existed.
_OCV_CURVE_SPEC = ModelInputSpec(
    name=OCV_CURVE,
    source_kind=InputSourceKind.PARAMETER,
    unit_exemplar=VOLTAGE_UNIT,
    required=False,
    varies_with=STATE_OF_CHARGE,
    description=(
        "Open-circuit voltage as a declared function of state of charge, in "
        "volts over a stated interval of z. Supersedes the two endpoint "
        "voltages. Outside its declared interval it yields "
        "OUTSIDE_VALIDATED_DOMAIN and no voltage rather than an extrapolation."
    ),
)

_COULOMBIC_EFFICIENCY_SPEC = ModelInputSpec(
    name=COULOMBIC_EFFICIENCY,
    source_kind=InputSourceKind.PARAMETER,
    unit_exemplar=DIMENSIONLESS,
    description=(
        "Fraction of the charge drawn from the terminals that is debited "
        "from the cell's stored charge, in (0, 1]. Plett's convention takes "
        "it as 1 on discharge; a caller declaring less is stating a measured "
        "discharge-direction efficiency for this cell."
    ),
)

_DURATION_SPEC = ModelInputSpec(
    name=DURATION,
    source_kind=InputSourceKind.PARAMETER,
    unit_exemplar=TIME_UNIT,
    description="Length of the interval over which the current is constant.",
)

_STATE_VARIABLES = (
    ModelInputSpec(
        name=STATE_OF_CHARGE,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=DIMENSIONLESS,
        role=VariableRole.STATE,
        description="Cell state of charge; the evolving state, in [0, 1].",
    ),
    ModelInputSpec(
        name=DISCHARGE_CURRENT,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=CURRENT_UNIT,
        role=VariableRole.CONTROL,
        description=(
            "Current drawn from the cell, positive out. Imposed externally; "
            "what draws it is not part of this model's claim."
        ),
    ),
    ModelInputSpec(
        name=CELL_TEMPERATURE,
        source_kind=InputSourceKind.VARIABLE,
        unit_exemplar=TEMPERATURE_UNIT,
        role=VariableRole.STATE,
        description=(
            "Cell temperature. A state coordinate supplied from outside this "
            "model, never inferred here; the coupling module supplies it from "
            "a thermal solve."
        ),
    ),
)


def _optional(name: str, unit: str, description: str) -> ModelInputSpec:
    """An optional declaration that unlocks one condition.

    ``required=False``, so a problem omitting it still binds cleanly, and every
    condition needing it is UNKNOWN without it — so omitting it can never buy
    an IN_DOMAIN verdict. Declaring these on the model record rather than
    leaving them as an undocumented calling convention is what makes "which
    declaration unlocks which condition" recoverable from the record alone.
    """
    return ModelInputSpec(
        name=name,
        source_kind=InputSourceKind.PARAMETER,
        unit_exemplar=unit,
        required=False,
        description=description,
    )


_SHARED_ASSUMPTIONS = (
    "one cell, or a series string treated as one lumped cell with no "
    "cell-to-cell variation and no balancing",
    "discharge only; charging is not modelled and no condition here would "
    "catch it",
    "one uniform cell temperature, supplied from outside and never inferred",
    "no diffusion or double-layer dynamics: no RC branch, no hysteresis",
    "no ageing, no cycle life, no capacity fade, no resistance growth",
    "no thermal runaway, no abuse response, no gas generation",
    "no reversible (entropic) heat; the irreversible Joule term only",
)


#: What every battery cell model here does NOT represent, taken from the same
#: source as _SHARED_ASSUMPTIONS: the exclusion-shaped half of that tuple,
#: separated because a condition can be checked against a run and an exclusion
#: cannot. Nobody will be warned about a phenomenon no condition can detect,
#: which is exactly why it has to be stated where a report can carry it.
_SHARED_EXCLUSIONS = (
    "cell-to-cell variation and balancing; a series string is treated as one "
    "lumped cell",
    "charging; discharge only, and no condition here would catch a charge",
    "diffusion and double-layer dynamics: no RC branch, no hysteresis",
    "ageing: no cycle life, no capacity fade, no resistance growth",
    "thermal runaway, abuse response and gas generation",
    "reversible (entropic) heat; the irreversible Joule term only",
    "any inference of the cell temperature, which is supplied from outside",
)

# =====================================================================
# Model 1 — Rint terminal behaviour and irreversible heat
# =====================================================================

RINT_OCV_MODEL = ScientificModelDefinition(
    exclusions=_SHARED_EXCLUSIONS
    + (
        "the overpotential beyond one constant series resistance",
        "the reversible term -I T dU/dT in the heat, which is of the same "
        "order at low rate and changes sign with current direction and state "
        "of charge",
        "any dependence of the internal resistance on temperature or state of "
        "charge; one measured value stands for the whole run",
    ),
    model_id="battery.cell.rint_ocv",
    version=MODEL_VERSION,
    name="Rint equivalent-circuit cell with affine open-circuit voltage",
    domain="battery",
    # CONSTITUTIVE_MODEL: a device response relation. It is neither a
    # conservation law nor a fit to one specific cell's measured curve; it is
    # the simplest circuit that stands for a cell's terminal behaviour.
    model_type=ModelType.CONSTITUTIVE_MODEL,
    description=(
        "Terminal voltage and irreversible heat of a cell represented as one "
        "ideal source at OCV(z) in series with one constant resistance: "
        "V = OCV(z) - I R_int, OCV(z) = V_empty + (V_full - V_empty) z, "
        "Q = I^2 R_int."
    ),
    inputs=_CELL_PARAMETERS
    + (_COULOMBIC_EFFICIENCY_SPEC, _DURATION_SPEC, _OCV_CURVE_SPEC)
    + _STATE_VARIABLES
    + (
        _optional(
            PULSE_CURRENT,
            CURRENT_UNIT,
            "Peak current the declared duty reaches, if it is pulsed.",
        ),
        _optional(
            PULSE_DURATION,
            TIME_UNIT,
            "Length of that pulse.",
        ),
        _optional(
            CONTINUOUS_DISCHARGE_C_RATE,
            C_RATE_UNIT,
            "Continuous discharge rating of the cell, as a C-rate.",
        ),
        _optional(
            PULSE_DISCHARGE_C_RATE,
            C_RATE_UNIT,
            "Peak discharge rating of the cell over its rated pulse.",
        ),
        _optional(
            RATED_PULSE_DURATION,
            TIME_UNIT,
            "Pulse length that peak rating is published for.",
        ),
        _optional(
            USABLE_SOC_MINIMUM,
            DIMENSIONLESS,
            "Lower edge of the state-of-charge window the cell is used over.",
        ),
        _optional(
            USABLE_SOC_MAXIMUM,
            DIMENSIONLESS,
            "Upper edge of that window.",
        ),
        _optional(
            MINIMUM_DISCHARGE_TEMPERATURE,
            TEMPERATURE_UNIT,
            "Lowest cell temperature the discharge rating is declared over.",
        ),
        _optional(
            MAXIMUM_DISCHARGE_TEMPERATURE,
            TEMPERATURE_UNIT,
            "Highest cell temperature the discharge rating is declared over.",
        ),
        _optional(
            RESISTANCE_REFERENCE_TEMPERATURE,
            TEMPERATURE_UNIT,
            "Temperature at which the declared R_int was measured.",
        ),
        _optional(
            RESISTANCE_TEMPERATURE_SPAN,
            TEMPERATURE_UNIT,
            "Half-width about it over which one R_int is supported.",
        ),
        _optional(
            CELL_THERMAL_CONDUCTANCE,
            CONDUCTANCE_UNIT,
            "Conductance hA from the cell to its ambient.",
        ),
        _optional(
            SELF_HEATING_RISE_BOUND,
            TEMPERATURE_UNIT,
            "Rise over which the cell may be treated as one temperature.",
        ),
        _optional(
            POLARIZATION_TIME_CONSTANT,
            TIME_UNIT,
            "Time constant of the diffusion overpotential this model omits.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=TERMINAL_VOLTAGE_METRIC,
            unit_exemplar=VOLTAGE_UNIT,
            description=(
                "Terminal voltage at the end of the interval, which is the "
                "worst point of a monotone discharge."
            ),
        ),
        ModelOutputSpec(
            metric=OPEN_CIRCUIT_VOLTAGE_METRIC,
            unit_exemplar=VOLTAGE_UNIT,
            description="OCV on the declared chord at that state of charge.",
        ),
        ModelOutputSpec(
            metric=HEAT_GENERATION_METRIC,
            unit_exemplar="watt",
            description=(
                "I^2 R_int — the irreversible term only. The reversible "
                "entropic heat is excluded and is not small at low rate."
            ),
        ),
    ),
    assumptions=_SHARED_ASSUMPTIONS
    + (
        "one constant series resistance stands for the whole overpotential",
        "the open-circuit voltage is an affine chord between two declared "
        "endpoints unless the cell declares a curve for it, in which case "
        "the curve governs and is evidence only over its declared interval",
        "the heat generated is I^2 R_int; the reversible term -I T dU/dT is "
        "omitted, is of the same order at low rate, and changes sign with "
        "current direction and state of charge",
    ),
    validity=ValidityDomain(
        derived_quantities=frozenset(
            {
                CONTINUOUS_C_RATE_UTILIZATION,
                DISCHARGE_TEMPERATURE_POSITION,
                INTERNAL_RESISTANCE_DRIFT_RATIO,
                POLARIZATION_UNMODELLED_FRACTION,
                PULSE_C_RATE_UTILIZATION,
                PULSE_DURATION_UTILIZATION,
                SELF_HEATING_RISE_RATIO,
                SOC_WINDOW_MARGIN,
                TERMINAL_VOLTAGE_RATIO,
            }
        ),
        conditions=(
            # ---- the declaration is well formed --------------------------
            # These two say nothing about whether the model applies; they say
            # the numbers are numbers. They are not counted among the
            # applicability conditions and never stand in for one.
            RangeCondition(
                name=NOMINAL_CAPACITY,
                minimum=Quantity(0.0, CAPACITY_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive; a cell of zero capacity has no state "
                    "of charge to be in."
                ),
            ),
            RangeCondition(
                name=INTERNAL_RESISTANCE,
                minimum=Quantity(0.0, RESISTANCE_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive; zero resistance is a cell with no "
                    "loss and no self-heating, which this model's heat term "
                    "and every condition built on it would then describe as "
                    "trivially safe."
                ),
            ),
            # ---- applicability of the Rint representation ----------------
            #
            # Each of the eight below is a bound on a group derived in
            # ``context.py`` from what the caller declared, never on a number
            # the caller wrote down. Every one is UNKNOWN until the declaration
            # it needs is supplied: none can be satisfied by leaving something
            # out, and none consults a declared category.
            RangeCondition(
                name=CONTINUOUS_C_RATE_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "|I/Q_nom| / continuous_discharge_c_rate <= 1. The single "
                    "most common way a cell sizing is wrong: a current that "
                    "the arithmetic delivers and the cell does not. Above its "
                    "continuous rating a cell is not described less "
                    "accurately by this circuit — it is outside the "
                    "conditions its resistance, its capacity and its "
                    "temperature limits were all specified under. The rating "
                    "is a property of the cell and is declared per cell; the "
                    "bound of 1 is definitional, being the fraction of that "
                    "rating in use. UNKNOWN unless the rating is declared."
                ),
            ),
            RangeCondition(
                name=PULSE_C_RATE_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "|I_peak/Q_nom| / pulse_discharge_c_rate <= 1. A second "
                    "and independent limit: a cell rated 1C continuous is "
                    "commonly rated several C for a short pulse, because the "
                    "continuous constraint is thermal and accumulates while "
                    "the pulse constraint does not. Definitional bound. "
                    "UNKNOWN unless the duty declares a pulse current and the "
                    "cell declares a pulse rating — a duty with no declared "
                    "pulse leaves this unanswered rather than satisfied."
                ),
            ),
            RangeCondition(
                name=PULSE_DURATION_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "pulse_duration / rated_pulse_duration <= 1. A peak "
                    "rating is meaningless without the duration it was "
                    "measured over: the same cell's 10 s and 30 s pulse "
                    "ratings differ, because what a pulse rating bounds is "
                    "the heat deposited and the overpotential reached during "
                    "the pulse and both grow with its length. Separate from "
                    "the peak-current condition because the two fail "
                    "independently. Definitional bound. UNKNOWN unless both "
                    "durations are declared."
                ),
            ),
            RangeCondition(
                name=SOC_WINDOW_MARGIN,
                minimum=WINDOW_MARGIN_FLOOR,
                description=(
                    "min(z_min - w_lo, w_hi - z_max) / (w_hi - w_lo) >= 0: "
                    "the whole trajectory stays inside the declared "
                    "state-of-charge window. Both of this model's shortcuts "
                    "fail at the ends of the charge axis — the affine OCV is "
                    "a chord across a curve with a knee near empty and a "
                    "plateau near full (Plett, Battery Management Systems "
                    "Vol. I, Artech House 2015, Ch. 3, which treats OCV as "
                    "tabulated data for that reason), and a constant R_int is "
                    "least defensible near empty where charge-transfer and "
                    "diffusion resistance rise. The window is the caller's "
                    "statement of where they hold; the bound of 0 is "
                    "definitional, being the edge of that window. The "
                    "trajectory is monotone under a constant current, so its "
                    "endpoints bound it exactly. UNKNOWN unless both edges "
                    "are declared."
                ),
            ),
            RangeCondition(
                name=DISCHARGE_TEMPERATURE_POSITION,
                minimum=TEMPERATURE_POSITION_FLOOR,
                maximum=TEMPERATURE_POSITION_CEILING,
                description=(
                    "(T - T_min)/(T_max - T_min) in [0, 1]: the cell sits "
                    "inside the discharge temperature range declared for it. "
                    "Both bounds are definitional, the position being "
                    "constructed so that 0 and 1 are the declared edges. "
                    "DISCHARGE ONLY: a cell's charge temperature range is "
                    "narrower, most sharply at the cold end where charging "
                    "plates lithium rather than intercalating it. This domain "
                    "models discharge, declares only the discharge range, and "
                    "no condition here would catch a caller charging the "
                    "cell. UNKNOWN unless both edges are declared."
                ),
            ),
            RangeCondition(
                name=INTERNAL_RESISTANCE_DRIFT_RATIO,
                maximum=DECLARED_BUDGET_LIMIT,
                description=(
                    "|T - T_R,ref| / resistance_temperature_span <= 1. A "
                    "cell's internal resistance is dominated by electrolyte "
                    "conductivity and charge-transfer kinetics, both "
                    "thermally activated, and can more than double between "
                    "room temperature and freezing (Plett, Battery Management "
                    "Systems Vol. I, 2015, Ch. 3, on measuring "
                    "equivalent-circuit resistances and their dependence on "
                    "operating conditions). A single declared R_int is a "
                    "claim about one temperature. No functional form is "
                    "fitted here: the reference and the span are the cell's "
                    "to declare and the bound of 1 is the fraction of the "
                    "caller's own declared span consumed. UNKNOWN unless both "
                    "are declared."
                ),
            ),
            RangeCondition(
                name=SELF_HEATING_RISE_RATIO,
                maximum=DECLARED_BUDGET_LIMIT,
                description=(
                    "(I^2 R_int / hA) / self_heating_rise_bound <= 1. The "
                    "steady rise the dissipation implies against the cooling "
                    "the caller declared, from the lumped balance's asymptote "
                    "T_ss - T_amb = Q/hA (Incropera, DeWitt, Bergman & "
                    "Lavine, Fundamentals of Heat and Mass Transfer, 6th ed., "
                    "Wiley 2007, Sec. 5.3, Eq. 5.25). Every model in this "
                    "domain assigns the cell ONE temperature; a cell tens of "
                    "kelvin above its ambient is not at one temperature, and "
                    "the R_int and capacity that matter are the ones at its "
                    "core. The asymptote rather than the end-of-interval rise "
                    "because a short horizon defers an excursion rather than "
                    "avoiding it. Definitional bound. UNKNOWN unless both the "
                    "conductance and the budget are declared."
                ),
            ),
            RangeCondition(
                name=POLARIZATION_UNMODELLED_FRACTION,
                maximum=POLARIZATION_UNMODELLED_CEILING,
                description=(
                    "min(f, 1 - f) <= 0.05 for f = 1 - exp(-t/tau_pol), THE "
                    "0.05 BEING A CONVENTION AND NOT A CITED THRESHOLD. TWO "
                    "REGIMES ARE ADMISSIBLE AND THE BAND BETWEEN THEM IS NOT. "
                    "Settled (f >= 0.95, t >= 3.0 tau_pol): the diffusion "
                    "branch has finished moving and contributes a constant "
                    "I R_diff that an R_int measured over a comparable "
                    "interval already contains. Undeveloped (f <= 0.05, "
                    "t <= 0.051 tau_pol): the branch has barely begun and the "
                    "terminal voltage is essentially the instantaneous ohmic "
                    "drop a short-pulse R_int represents. Between them, around "
                    "t ~ tau_pol, the branch is slewing through the interval "
                    "and no constant resistance reproduces the terminal "
                    "voltage; that is the band this condition excludes. The "
                    "physics is cited: Plett (Battery Management Systems Vol. "
                    "I, Artech House 2015, Ch. 3) adds the series RC branch to "
                    "the Rint model, which is what establishes the "
                    "1 - exp(-t/tau) form. Plett prints no threshold for this "
                    "quantity and no source in this repository does either. "
                    "The 0.05 is the engineering reading of 'done' for a "
                    "first-order response, the same reading that makes three "
                    "time constants mean settled, and BOTH resulting bounds "
                    "are conventions. THIS IS A VALIDATED APPLICABILITY BOUND, "
                    "NOT A CONSERVATIVE SCREEN, and `conservative_screen` is "
                    "deliberately not set. An earlier revision of this text "
                    "called it a screen -- \"inside the band the model is not "
                    "shown to be wrong\" -- which was wrong about what the "
                    "band is. Inside it the branch is slewing and NO constant "
                    "resistance reproduces the terminal voltage: the model's "
                    "own constitutive assumption is observed to fail. That is "
                    "a finding against applying it here, not an absence of "
                    "evidence, so a value past this bound reports "
                    "OUTSIDE_VALIDATED_DOMAIN. Contrast "
                    "`internal_fourier_number` in the lumped thermal model, "
                    "which IS a screen: there the horizon runs out before the "
                    "criterion can observe anything, so nothing is seen to "
                    "fail. It does not check that R_int was "
                    "characterised in the regime it is being used in, which "
                    "this domain cannot declare. UNKNOWN unless a "
                    "polarization time constant is declared."
                ),
            ),
            RangeCondition(
                name=TERMINAL_VOLTAGE_RATIO,
                minimum=MINIMUM_TERMINAL_VOLTAGE_RATIO,
                minimum_inclusive=False,
                description=(
                    "V/OCV = 1 - I R_int/OCV > 0 at the end of the interval. "
                    "Every straight line with a non-zero slope crosses zero; "
                    "past the crossing this expression does not describe a "
                    "deeply loaded cell but one sourcing current at a "
                    "negative terminal voltage. The bound is the physics of "
                    "the computed quantity, not a tolerance, which is why it "
                    "is exactly zero and needs no source. A consistency "
                    "condition rather than an applicability one, and not "
                    "counted among the eight above. UNKNOWN unless the "
                    "operating point is supplied."
                ),
            ),
        ),
        description=(
            "One series resistance and an affine open-circuit voltage, "
            "applicable while the cell stays inside its declared continuous "
            "and pulse ratings, inside the state-of-charge window and "
            "temperature range it was specified over, inside the property "
            "spans the caller declared for its resistance, cool enough that "
            "one temperature describes it, and observed over intervals long "
            "enough that the omitted diffusion overpotential has settled."
        ),
    ),
    required_capabilities=frozenset({CELL_DISCHARGE_STEP.name}),
    # SELF_CONSISTENT: the closed form is checked against the circuit relation
    # it states and against its own dimensions. Nothing physical was measured;
    # no cell in this repository has been discharged.
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=(
        "Plett, G. L., Battery Management Systems, Volume I: Battery "
        "Modeling, Artech House (2015), Ch. 3 (equivalent-circuit cell "
        "models: the Rint model, the OCV relationship, and the RC diffusion "
        "branches it omits)",
        "Incropera, F. P., DeWitt, D. P., Bergman, T. L. & Lavine, A. S., "
        "Fundamentals of Heat and Mass Transfer, 6th ed., Wiley (2007), "
        "Sec. 5.3, Eq. 5.25 (lumped body with internal generation)",
    ),
)


# =====================================================================
# Model 2 — coulomb counting
# =====================================================================

COULOMB_COUNTING_MODEL = ScientificModelDefinition(
    exclusions=_SHARED_EXCLUSIONS
    + (
        "self-discharge, and coulombic loss beyond the declared efficiency",
        "any feedback: no voltage-based correction, so an error in the "
        "starting state of charge persists undiminished",
        "rate derating; the nominal capacity is taken as the charge available "
        "at this temperature and rate",
    ),
    model_id="battery.cell.coulomb_counting",
    version=MODEL_VERSION,
    name="State of charge by coulomb counting",
    domain="battery",
    # FUNDAMENTAL_RELATION: a charge balance on the cell. The approximation is
    # in what the counter divides by — a nominal capacity that is itself a
    # measurement under stated conditions — and that is declared in the
    # assumptions and bounded by the capacity drift condition.
    model_type=ModelType.FUNDAMENTAL_RELATION,
    description=(
        "Charge balance on the cell: z(t) = z_0 - I t / (eta Q_nom) for a "
        "current constant over the interval. Exact integration of "
        "dz/dt = -I / (eta Q_nom)."
    ),
    inputs=(
        _CELL_PARAMETERS[0],  # nominal capacity
        _COULOMBIC_EFFICIENCY_SPEC,
        _DURATION_SPEC,
        _STATE_VARIABLES[0],  # state of charge
        _STATE_VARIABLES[1],  # discharge current
        _STATE_VARIABLES[2],  # cell temperature
        _optional(
            SOC_STEP_RESOLUTION,
            DIMENSIONLESS,
            "Largest state-of-charge span one integration step may traverse.",
        ),
        _optional(
            CAPACITY_REFERENCE_TEMPERATURE,
            TEMPERATURE_UNIT,
            "Temperature at which the nominal capacity was rated.",
        ),
        _optional(
            CAPACITY_TEMPERATURE_SPAN,
            TEMPERATURE_UNIT,
            "Half-width about it over which one capacity is supported.",
        ),
        _optional(
            USABLE_SOC_MINIMUM,
            DIMENSIONLESS,
            "Lower edge of the state-of-charge window the cell is used over.",
        ),
        _optional(
            USABLE_SOC_MAXIMUM,
            DIMENSIONLESS,
            "Upper edge of that window.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=FINAL_STATE_OF_CHARGE_METRIC,
            unit_exemplar=DIMENSIONLESS,
            description=(
                "State of charge at the end of the interval. Named distinctly "
                "from the `state_of_charge` state variable, which is its "
                "value at the start."
            ),
        ),
    ),
    assumptions=_SHARED_ASSUMPTIONS
    + (
        "the current is constant over the interval, which makes the integral "
        "exact rather than approximated",
        "the nominal capacity is the charge actually available at this "
        "temperature and rate; no rate derating is applied here, and any is "
        "a separate model with its own validity domain",
        "no self-discharge and no coulombic loss beyond the declared "
        "efficiency",
        "the counter has no feedback: an error in z_0 persists undiminished, "
        "and no voltage-based correction is applied",
    ),
    validity=ValidityDomain(
        derived_quantities=frozenset(
            {
                CAPACITY_TEMPERATURE_DRIFT_RATIO,
                SOC_STEP_RESOLUTION_RATIO,
                SOC_WINDOW_MARGIN,
            }
        ),
        conditions=(
            RangeCondition(
                name=NOMINAL_CAPACITY,
                minimum=Quantity(0.0, CAPACITY_UNIT),
                minimum_inclusive=False,
                description=(
                    "Strictly positive; the counter divides by it."
                ),
            ),
            RangeCondition(
                name=COULOMBIC_EFFICIENCY,
                minimum=Quantity(0.0, DIMENSIONLESS),
                maximum=Quantity(1.0, DIMENSIONLESS),
                minimum_inclusive=False,
                description=(
                    "In (0, 1]. Above 1 the counter would credit the cell "
                    "with more charge than crossed its terminals; at 0 no "
                    "current changes the state of charge at all. Plett, "
                    "Battery Management Systems Vol. I (2015), Ch. 2."
                ),
            ),
            RangeCondition(
                name=SOC_STEP_RESOLUTION_RATIO,
                maximum=STEP_RESOLUTION_LIMIT,
                description=(
                    "|z_0 - z_end| / soc_step_resolution <= 1: one step does "
                    "not walk further down the charge axis than the caller "
                    "declared a step may. The integration itself is exact for "
                    "a constant current, so this bounds not the integral but "
                    "everything the step holds fixed while z moves: the OCV "
                    "and terminal voltage are evaluated once per step, at one "
                    "state of charge, and both are functions of it. A load "
                    "that varies within the step must be resolved by steps "
                    "short enough to sample it, which is the same requirement "
                    "seen from the load's side. How much OCV movement is "
                    "tolerable depends on that cell's curve and on what the "
                    "answer is for, so the resolution is declared and the "
                    "bound of 1 is definitional. UNKNOWN unless a resolution "
                    "is declared."
                ),
            ),
            RangeCondition(
                name=CAPACITY_TEMPERATURE_DRIFT_RATIO,
                maximum=DECLARED_BUDGET_LIMIT,
                description=(
                    "|T - T_Q,ref| / capacity_temperature_span <= 1. The "
                    "counter divides by Q_nom, and Q_nom is a measurement "
                    "under stated conditions: IEC 61960-3:2017, Secondary "
                    "cells and batteries containing alkaline or other "
                    "non-acid electrolytes - Secondary lithium cells and "
                    "batteries for portable applications, Clause 7, specifies "
                    "the discharge performance tests and the ambient "
                    "temperature rated capacity is measured at, and "
                    "separately specifies low- and high-temperature discharge "
                    "performance because the deliverable charge is not the "
                    "same there. Distinct from the resistance drift condition "
                    "— different property, different reference, different "
                    "span — and the two must be able to disagree. "
                    "Definitional bound. UNKNOWN unless both are declared."
                ),
            ),
            RangeCondition(
                name=SOC_WINDOW_MARGIN,
                minimum=WINDOW_MARGIN_FLOOR,
                description=(
                    "The trajectory stays inside the declared state-of-charge "
                    "window. Shared with the Rint model, for a reason of this "
                    "model's own: outside the window the nominal capacity is "
                    "not the charge the cell will actually give up, so the "
                    "counter's denominator stops meaning what it divides. "
                    "This is also where a counter driven below empty or above "
                    "full is caught. Definitional bound. UNKNOWN unless both "
                    "edges are declared."
                ),
            ),
        ),
        description=(
            "Exact charge integration for a constant current, applicable "
            "while the step resolves the state-of-charge movement it "
            "represents, the cell is near the temperature its capacity was "
            "rated at, and the trajectory stays inside the declared window."
        ),
    ),
    required_capabilities=frozenset({CELL_DISCHARGE_STEP.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=(
        "Plett, G. L., Battery Management Systems, Volume I: Battery "
        "Modeling, Artech House (2015), Ch. 2 (state of charge, capacity and "
        "the coulomb-counting integral)",
        "IEC 61960-3:2017, Secondary cells and batteries containing alkaline "
        "or other non-acid electrolytes - Secondary lithium cells and "
        "batteries for portable applications, Clause 7 (discharge "
        "performance and the conditions rated capacity is measured under)",
    ),
)


# =====================================================================
# Model 3 — runtime to a declared cutoff
# =====================================================================

CONSTANT_CURRENT_RUNTIME_MODEL = ScientificModelDefinition(
    exclusions=_SHARED_EXCLUSIONS
    + (
        "a varying load; the current is held constant for the whole run, not "
        "merely for one step",
        "anything beyond the first cutoff reached",
    ),
    model_id="battery.cell.constant_current_runtime",
    version=MODEL_VERSION,
    name="Runtime to a declared cutoff under a constant current",
    domain="battery",
    model_type=ModelType.APPROXIMATION,
    description=(
        "Time to the first of a declared state-of-charge cutoff and a "
        "declared terminal-voltage cutoff, under a constant discharge "
        "current: t = (z_0 - z_stop) eta Q_nom / I, with z_stop the higher "
        "of the two cutoffs expressed as a state of charge."
    ),
    inputs=_CELL_PARAMETERS
    + (_COULOMBIC_EFFICIENCY_SPEC,)
    + _STATE_VARIABLES
    + (
        _optional(
            CUTOFF_VOLTAGE,
            VOLTAGE_UNIT,
            "Terminal voltage at which the run is declared to stop.",
        ),
        _optional(
            CUTOFF_STATE_OF_CHARGE,
            DIMENSIONLESS,
            "State of charge at which the run is declared to stop.",
        ),
        _optional(
            CONTINUOUS_DISCHARGE_C_RATE,
            C_RATE_UNIT,
            "Continuous discharge rating of the cell, as a C-rate.",
        ),
        _optional(
            USABLE_SOC_MINIMUM,
            DIMENSIONLESS,
            "Lower edge of the state-of-charge window the cell is used over.",
        ),
        _optional(
            USABLE_SOC_MAXIMUM,
            DIMENSIONLESS,
            "Upper edge of that window.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=RUNTIME_METRIC,
            unit_exemplar=TIME_UNIT,
            description=(
                "Time to the first cutoff reached. Absent from a result when "
                "no cutoff was declared: a runtime to nothing is not a "
                "number this model produces."
            ),
        ),
    ),
    assumptions=_SHARED_ASSUMPTIONS
    + (
        "the current is held constant for the whole run, not merely for one "
        "step",
        "the run stops at the first cutoff reached and nothing beyond it is "
        "claimed",
        "the runtime inherits every assumption of the Rint and "
        "coulomb-counting models, which is why those are separate records "
        "that a caller may reject independently",
    ),
    validity=ValidityDomain(
        derived_quantities=frozenset(
            {
                CONTINUOUS_C_RATE_UTILIZATION,
                CUTOFF_CONSISTENCY_MARGIN,
                CUTOFF_REACHABILITY_MARGIN,
                SOC_WINDOW_MARGIN,
            }
        ),
        conditions=(
            RangeCondition(
                name=CUTOFF_CONSISTENCY_MARGIN,
                minimum=CUTOFF_CONSISTENCY_FLOOR,
                description=(
                    "z_cut,declared - z_cut,voltage >= 0: the depth of "
                    "discharge the caller asked for is reachable before the "
                    "declared voltage cutoff stops the run. At high current "
                    "I R_int is subtracted from every point of the OCV curve, "
                    "so the voltage cutoff bites at a HIGHER state of charge "
                    "and the requested depth is never reached — a runtime "
                    "computed to it is over-reported, silently, by whatever "
                    "fraction of the capacity lies between the two. The two "
                    "cutoffs are independent declarations and this is the "
                    "only place their consistency is checked. The bound of 0 "
                    "is definitional: the two meeting exactly is consistent. "
                    "UNKNOWN unless both cutoffs are declared — declaring one "
                    "leaves the question unasked, not answered."
                ),
            ),
            RangeCondition(
                name=CUTOFF_REACHABILITY_MARGIN,
                minimum=CUTOFF_CONSISTENCY_FLOOR,
                description=(
                    "z_0 - z_stop >= 0: the binding cutoff is ahead of "
                    "where the run starts. The condition above compares "
                    "the two cutoffs WITH EACH OTHER and answers which of "
                    "them stops the run first; neither is compared with "
                    "the start, and that is a different question. A "
                    "discharge at constant current walks the state of "
                    "charge monotonically DOWN — 'discharge only' is "
                    "this record's own first assumption — so a cutoff "
                    "declared ABOVE the starting state is never reached. "
                    "The published equation returns the time to reach it "
                    "anyway and that time is NEGATIVE, which is not a "
                    "runtime. The bound of 0 is definitional: a run "
                    "already at its cutoff has a runtime of zero. "
                    "UNKNOWN unless the starting state of charge and at "
                    "least one cutoff are declared — with no cutoff "
                    "there is no runtime to bound."
                ),
            ),
            RangeCondition(
                name=CONTINUOUS_C_RATE_UTILIZATION,
                maximum=RATING_UTILIZATION_LIMIT,
                description=(
                    "The run's current stays inside the cell's declared "
                    "continuous rating. Shared with the Rint model, and "
                    "load-bearing here for a reason of this model's own: a "
                    "runtime is by construction a claim about a current held "
                    "for a long time, which is exactly what a continuous "
                    "rating bounds. Definitional bound. UNKNOWN unless the "
                    "rating is declared."
                ),
            ),
            RangeCondition(
                name=SOC_WINDOW_MARGIN,
                minimum=WINDOW_MARGIN_FLOOR,
                description=(
                    "The trajectory over the declared interval stays inside "
                    "the declared state-of-charge window, so the OCV chord "
                    "and constant R_int the runtime rests on are being used "
                    "where the caller declared they hold. Definitional bound. "
                    "UNKNOWN unless both edges are declared."
                ),
            ),
        ),
        description=(
            "Time to the first declared cutoff, applicable while that "
            "cutoff is ahead of where the run starts, the two cutoffs are "
            "mutually consistent at this load, the current is inside the "
            "continuous rating, and the trajectory stays inside the "
            "declared state-of-charge window."
        ),
    ),
    required_capabilities=frozenset({CELL_DISCHARGE_STEP.name}),
    validation_status=ModelValidationStatus.SELF_CONSISTENT,
    references=(
        "Plett, G. L., Battery Management Systems, Volume I: Battery "
        "Modeling, Artech House (2015), Ch. 2 and Ch. 3",
    ),
)


# =====================================================================
# Model 4 — Peukert rate-capacity derating
# =====================================================================

PEUKERT_DERATING_MODEL = ScientificModelDefinition(
    exclusions=_SHARED_EXCLUSIONS
    + (
        "a varying load; the law is defined over a constant-current discharge "
        "and says nothing about one that varies",
        "any derivation of the exponent, which is a fit and is treated as "
        "constant over the declared current and temperature range only",
    ),
    model_id="battery.cell.peukert_capacity_derating",
    version=MODEL_VERSION,
    name="Peukert rate-capacity derating",
    domain="battery",
    # EMPIRICAL_CORRELATION, and not anything stronger. The exponent is fitted
    # to a cell over a range of currents; nothing derives it.
    model_type=ModelType.EMPIRICAL_CORRELATION,
    description=(
        "Deliverable charge as a fitted power law of discharge current: "
        "Q_eff = Q_nom (I_ref / I)^(k-1), the rearrangement of Peukert's "
        "I^k t = constant referred to the current the nominal capacity was "
        "measured at."
    ),
    inputs=(
        _CELL_PARAMETERS[0],  # nominal capacity
        _STATE_VARIABLES[1],  # discharge current
        _STATE_VARIABLES[2],  # cell temperature
        _optional(
            PEUKERT_EXPONENT,
            DIMENSIONLESS,
            "Peukert exponent k fitted for this cell; at least 1.",
        ),
        _optional(
            PEUKERT_REFERENCE_CURRENT,
            CURRENT_UNIT,
            "Current the nominal capacity and the exponent were fitted at.",
        ),
        _optional(
            PEUKERT_FIT_DECADES,
            DIMENSIONLESS,
            "Decades of current either side of the reference the fit covers.",
        ),
        _optional(
            PEUKERT_REFERENCE_TEMPERATURE,
            TEMPERATURE_UNIT,
            "Temperature the exponent was fitted at.",
        ),
        _optional(
            PEUKERT_TEMPERATURE_SPAN,
            TEMPERATURE_UNIT,
            "Half-width about it over which one exponent is supported.",
        ),
    ),
    outputs=(
        ModelOutputSpec(
            metric=EFFECTIVE_CAPACITY_METRIC,
            unit_exemplar=CAPACITY_UNIT,
            description=(
                "Charge the cell is predicted to deliver at this current. "
                "Absent from a result when no exponent was declared."
            ),
        ),
    ),
    assumptions=_SHARED_ASSUMPTIONS
    + (
        "the exponent is a fit, not a derivation, and is treated as constant "
        "over the declared current and temperature range only",
        "the law was established for lead-acid cells and its applicability "
        "to lithium-ion is contested in the source cited below",
        "constant current: the law is defined over a constant-current "
        "discharge and says nothing about a varying load",
        "this is a separate claim from coulomb counting and is never applied "
        "to it automatically; a caller may run the counter and refuse this",
    ),
    validity=ValidityDomain(
        derived_quantities=frozenset(
            {
                PEUKERT_CAPACITY_RATIO,
                PEUKERT_EXTRAPOLATION_RATIO,
                PEUKERT_TEMPERATURE_DRIFT_RATIO,
            }
        ),
        conditions=(
            RangeCondition(
                name=PEUKERT_EXTRAPOLATION_RATIO,
                maximum=DECLARED_BUDGET_LIMIT,
                description=(
                    "|log10(I/I_ref)| / peukert_fit_decades <= 1: the "
                    "operating current is inside the range the exponent was "
                    "fitted over. Doerffel, D. & Sharkh, S. A., 'A critical "
                    "review of using the Peukert equation for determining the "
                    "remaining capacity of lead-acid and lithium-ion "
                    "batteries', Journal of Power Sources 155 (2006), "
                    "395-400, show the extracted exponent is not a constant "
                    "of the cell but varies with the discharge current it is "
                    "measured over. The law is therefore an interpolation "
                    "across the currents it was fitted on, and using it far "
                    "outside them extrapolates a fit whose own parameter has "
                    "moved. Decades rather than a ratio because the law is "
                    "linear in log I. Definitional bound. UNKNOWN unless the "
                    "reference current and the declared reach are supplied."
                ),
            ),
            RangeCondition(
                name=PEUKERT_CAPACITY_RATIO,
                maximum=PEUKERT_DERATING_LIMIT,
                description=(
                    "Q_eff/Q_nom <= 1: the derating reduces and never raises. "
                    "Peukert's law describes capacity lost to rate; below the "
                    "reference current the same expression predicts a cell "
                    "delivering more than the capacity it is rated for, which "
                    "is not a conservative error but the formula read outside "
                    "the direction it means anything in. Peukert, W., "
                    "Elektrotechnische Zeitschrift 20 (1897), 287-288. "
                    "Definitional and directional, not a tolerance. UNKNOWN "
                    "unless the exponent and the reference current are "
                    "declared."
                ),
            ),
            RangeCondition(
                name=PEUKERT_TEMPERATURE_DRIFT_RATIO,
                maximum=DECLARED_BUDGET_LIMIT,
                description=(
                    "|T - T_k,ref| / peukert_temperature_span <= 1: the cell "
                    "is near the temperature the exponent was fitted at. "
                    "Doerffel & Sharkh (2006), J. Power Sources 155, 395-400, "
                    "name temperature alongside current as a variable the "
                    "extracted exponent depends on, which is the substance of "
                    "their objection to using the equation as a general "
                    "remaining-capacity model. Distinct from the capacity and "
                    "resistance drift conditions: a different fitted object "
                    "with its own reference and its own declared reach. "
                    "Definitional bound. UNKNOWN unless both are declared."
                ),
            ),
        ),
        description=(
            "A fitted power law between discharge current and deliverable "
            "charge, applicable inside the currents and the temperature the "
            "exponent was fitted over, and only in the direction in which it "
            "derates."
        ),
    ),
    required_capabilities=frozenset({CELL_DISCHARGE_STEP.name}),
    # UNVALIDATED, and not SELF_CONSISTENT. There is no differential balance
    # for this to be consistent *with*: it is a curve fit, and evaluating a
    # curve fit correctly establishes nothing about whether the curve holds.
    # Self-consistency is a claim available to a closed form that solves an
    # equation, and awarding it here would be the strongest word this
    # repository has for the weakest evidence it holds.
    validation_status=ModelValidationStatus.UNVALIDATED,
    references=(
        "Peukert, W., 'Ueber die Abhaengigkeit der Kapacitaet von der "
        "Entladestromstaerke bei Bleiakkumulatoren', Elektrotechnische "
        "Zeitschrift 20 (1897), 287-288",
        "Doerffel, D. & Sharkh, S. A., 'A critical review of using the "
        "Peukert equation for determining the remaining capacity of "
        "lead-acid and lithium-ion batteries', Journal of Power Sources 155 "
        "(2006), 395-400",
    ),
)


BATTERY_MODELS = (
    RINT_OCV_MODEL,
    COULOMB_COUNTING_MODEL,
    CONSTANT_CURRENT_RUNTIME_MODEL,
    PEUKERT_DERATING_MODEL,
)


# =====================================================================
# Realizations
# =====================================================================

def _realization(
    model: ScientificModelDefinition,
    suffix: str,
    formulation: ModelFormulation,
    name: str,
    description: str,
    assumptions: tuple[str, ...],
) -> ModelRealizationDefinition:
    """One closed-form realization of one model.

    All four are discharged by the same evaluator and all four say so through
    the same :class:`ImplementationReference`. They stay four records because
    they realize four models: a realization points *at* a model and a shared
    implementation does not merge the claims it computes.
    """
    return ModelRealizationDefinition(
        realization_id=f"{model.model_id}.{suffix}",
        version=REALIZATION_VERSION,
        model=ModelReference(model.model_id, model.version),
        formulation=formulation,
        name=name,
        description=description,
        provided_capabilities=frozenset({CELL_TERMINAL_STATE}),
        # A real, machine-checkable scientific dependency: every one of these
        # carries a temperature-dependent condition, so none can be planned
        # unless something provides a body temperature. Declared by
        # identifier; no thermal module is imported here.
        required_capabilities=frozenset({REQUIRED_BODY_TEMPERATURE}),
        required_solver_capabilities=frozenset(
            {
                SolverCapabilityId.coerce(CELL_DISCHARGE_STEP),
                SolverCapabilityId.coerce(CoreCapabilities.ALGEBRAIC),
            }
        ),
        assumptions=assumptions,
        implementation=ImplementationReference(
            implementation_id="engcore.domains.battery.solver",
            version=REALIZATION_VERSION,
            reference="closed-form cell discharge step; see module docstring",
        ),
    )


RINT_OCV_REALIZATION = _realization(
    RINT_OCV_MODEL,
    "closed_form",
    # ALGEBRAIC: the Rint circuit poses no differential equation. Its terminal
    # voltage is an algebraic function of the state of charge it is handed.
    ModelFormulation.ALGEBRAIC,
    "Direct evaluation of the Rint circuit at one state of charge",
    (
        "Evaluates OCV(z) - I R_int and I^2 R_int once, at the state of "
        "charge supplied. No iteration and no system solve."
    ),
    (
        "exact for the declared circuit; no discretization error exists",
        "evaluated at one state of charge per interval, which is what the "
        "step-resolution condition of the coulomb-counting model bounds",
    ),
)

COULOMB_COUNTING_REALIZATION = _realization(
    COULOMB_COUNTING_MODEL,
    "exact_constant_current",
    # ODE: the model poses dz/dt = -I / (eta Q_nom). That is what `formulation`
    # records — the mathematical form of the claim, not how it is discharged.
    # This realization discharges it with no integrator at all, which is
    # exactly the separation the realization contract exists to express.
    ModelFormulation.ODE,
    "Exact integration of the charge balance over one constant-current step",
    (
        "Integrates dz/dt = -I / (eta Q_nom) in closed form over one interval "
        "of constant current: z(t) = z_0 - I t / (eta Q_nom)."
    ),
    (
        "the current is constant over the integrated interval",
        "exact for the linear balance; no time-discretization error",
        "no linear system is solved; the update is one multiplication",
    ),
)

CONSTANT_CURRENT_RUNTIME_REALIZATION = _realization(
    CONSTANT_CURRENT_RUNTIME_MODEL,
    "closed_form",
    ModelFormulation.ALGEBRAIC,
    "Direct inversion of the charge balance at the binding cutoff",
    (
        "Solves z(t) = z_stop for t, with z_stop the higher of the declared "
        "state-of-charge cutoff and the state of charge at which the terminal "
        "voltage reaches the declared voltage cutoff."
    ),
    (
        "the binding cutoff is selected by comparison, never by iteration",
        "exact for the declared affine OCV chord; a tabulated OCV would make "
        "the inversion numerical and this realization would not serve it",
    ),
)

PEUKERT_DERATING_REALIZATION = _realization(
    PEUKERT_DERATING_MODEL,
    "closed_form",
    ModelFormulation.ALGEBRAIC,
    "Direct evaluation of the Peukert power law",
    (
        "Evaluates Q_nom (I_ref/I)^(k-1) once. One exponentiation; no fit is "
        "performed here and the exponent is taken as declared."
    ),
    (
        "the exponent is an input, not an output: nothing here fits it",
        "exact evaluation of a correlation whose own accuracy is not "
        "established by evaluating it",
    ),
)


BATTERY_REALIZATIONS = (
    RINT_OCV_REALIZATION,
    COULOMB_COUNTING_REALIZATION,
    CONSTANT_CURRENT_RUNTIME_REALIZATION,
    PEUKERT_DERATING_REALIZATION,
)


def battery_model_registry() -> ModelRegistry:
    """A fresh registry. No global singleton exists."""
    return ModelRegistry(BATTERY_MODELS)


def battery_realizations() -> RealizationRegistry:
    """A fresh registry. No global singleton exists."""
    return RealizationRegistry(BATTERY_REALIZATIONS)


def battery_solver_capabilities() -> frozenset[SolverCapability]:
    """What a battery cell solver declares it can do.

    Both the domain capability and the mathematical shape it reduces to, which
    is what makes the solver discoverable to a planner reasoning about problem
    form rather than about domain.
    """
    return frozenset({CELL_DISCHARGE_STEP, CoreCapabilities.ALGEBRAIC})
