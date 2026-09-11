"""Computed validity context for the battery cell models.

Why this module exists
----------------------
``ScientificProblem.validity_context`` is built from **typed parameters**. A
C-rate is not a parameter: nobody declares a C-rate, they declare a current and
a nominal capacity and the rate *follows*. The core provides exactly one
sanctioned way to close that gap — ``validity_context(extra=...)``, whose
docstring names "a Reynolds number, a detected regime" as the intended content
— and this module is the battery domain's supplier of that ``extra``.

Nothing here is registered with, imported by, or known to
``engcore.scientific``. The core knows ranges, categories and flags; it does
not know what a C-rate is, and after this module it still does not.

Four rules every function below obeys
-------------------------------------
1. **A missing input omits its key.** Every function returns ``None`` when it
   was not given what it needs, and :func:`derived_cell_quantities` drops the
   key rather than inventing a value. A dropped key reaches
   ``ValidityDomain.assess`` as UNKNOWN, which is the honest verdict: absence
   of information is not evidence of validity. No function here has a physical
   default, and there is no path through this module by which omitting an
   input yields IN_DOMAIN.
2. **No caller-declared category reaches any computation.** ``chemistry``,
   ``cooling_mode`` and ``duty_type`` are recorded on the declaration records,
   validated against their vocabularies and serialized — and read by nothing.
   A verdict must rest on a measured or declared *quantity*, never on a string
   the assessed party asserts about itself. The sibling thermal domain shipped
   a condition that could be satisfied by asserting ``convection_regime`` and
   had to remove it; this domain does not repeat that.
3. **Every derivation is unit-checked.** Inputs travel as :class:`Quantity` and
   are converted through ``to``/``magnitude_in``, so a capacity handed in as
   ampere-hours and one handed in as coulombs produce the same number, and a
   current handed in where a capacity belongs raises instead of producing a
   plausible-looking wrong answer.
4. **Pure.** No state, no registry, no I/O, no mutation of an argument.

Sources
-------
Equivalent-circuit cell modelling, the state-of-charge definition and the
coulomb-counting relation follow Plett, Gregg L., *Battery Management Systems,
Volume I: Battery Modeling* (Artech House, 2015) — Ch. 2 for state of charge,
capacity and the coulomb-counting integral, and Ch. 3 for equivalent-circuit
cell models, the open-circuit-voltage relationship, the Rint model and the RC
diffusion branches it omits. The rate-capacity relation is Peukert, W., "Ueber
die Abhaengigkeit der Kapacitaet von der Entladestromstaerke bei
Bleiakkumulatoren", *Elektrotechnische Zeitschrift* 20 (1897), 287-288, read
through the critical review of Doerffel, D. & Sharkh, S. A., "A critical review
of using the Peukert equation for determining the remaining capacity of
lead-acid and lithium-ion batteries", *Journal of Power Sources* 155 (2006),
395-400. Rated-capacity measurement conditions are IEC 61960-3:2017,
*Secondary cells and batteries containing alkaline or other non-acid
electrolytes - Secondary lithium cells and batteries for portable
applications*, Clause 7 (discharge performance). Section numbers are cited on
each function that rests on one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.models.curves import CurveEvaluation, DeclaredCurve
from ...scientific.models.definition import ValidityStatus
from ...scientific.serialization import require_schema, schema_string
from ...scientific.units.quantity import Quantity

CELL_LIMITS_SCHEMA = schema_string("battery_cell_limits")

# --- units -------------------------------------------------------------------
CAPACITY_UNIT = "ampere_hour"
CURRENT_UNIT = "ampere"
VOLTAGE_UNIT = "volt"
RESISTANCE_UNIT = "ohm"
C_RATE_UNIT = "1/hour"
TEMPERATURE_UNIT = "kelvin"
CONDUCTANCE_UNIT = "watt/kelvin"
POWER_UNIT = "watt"
TIME_UNIT = "second"
DIMENSIONLESS = "dimensionless"

# --- names of the cell's required declarations -------------------------------
# Names, not conventions: each is enumerated by a model record's
# ``ModelInputSpec`` and emitted by the problem builder as a parameter, so a
# reader holding only the records can see what the claim needs. Nothing
# anywhere parses their internal structure.
NOMINAL_CAPACITY = "nominal_capacity"
INTERNAL_RESISTANCE = "internal_resistance"
OCV_AT_FULL = "open_circuit_voltage_at_full"
OCV_AT_EMPTY = "open_circuit_voltage_at_empty"
#: The optional curve-valued declaration that supersedes the two endpoints
#: above. Named here with them because it is the same physical quantity
#: declared to a different depth, not a different one.
OCV_CURVE = "open_circuit_voltage_curve"
COULOMBIC_EFFICIENCY = "coulombic_efficiency"

# --- names of the load's declarations ----------------------------------------
DURATION = "duration"
PULSE_CURRENT = "pulse_current"
PULSE_DURATION = "pulse_duration"
CUTOFF_VOLTAGE = "cutoff_voltage"
CUTOFF_STATE_OF_CHARGE = "cutoff_state_of_charge"

# --- names of the optional limits a caller may declare -----------------------
CONTINUOUS_DISCHARGE_C_RATE = "continuous_discharge_c_rate"
PULSE_DISCHARGE_C_RATE = "pulse_discharge_c_rate"
RATED_PULSE_DURATION = "rated_pulse_duration"
USABLE_SOC_MINIMUM = "usable_soc_minimum"
USABLE_SOC_MAXIMUM = "usable_soc_maximum"
MINIMUM_DISCHARGE_TEMPERATURE = "minimum_discharge_temperature"
MAXIMUM_DISCHARGE_TEMPERATURE = "maximum_discharge_temperature"
RESISTANCE_REFERENCE_TEMPERATURE = "resistance_reference_temperature"
RESISTANCE_TEMPERATURE_SPAN = "resistance_temperature_span"
CELL_THERMAL_CONDUCTANCE = "cell_thermal_conductance"
SELF_HEATING_RISE_BOUND = "self_heating_rise_bound"
POLARIZATION_TIME_CONSTANT = "polarization_time_constant"
SOC_STEP_RESOLUTION = "soc_step_resolution"
CAPACITY_REFERENCE_TEMPERATURE = "capacity_reference_temperature"
CAPACITY_TEMPERATURE_SPAN = "capacity_temperature_span"
PEUKERT_EXPONENT = "peukert_exponent"
PEUKERT_REFERENCE_CURRENT = "peukert_reference_current"
PEUKERT_FIT_DECADES = "peukert_fit_decades"
PEUKERT_REFERENCE_TEMPERATURE = "peukert_reference_temperature"
PEUKERT_TEMPERATURE_SPAN = "peukert_temperature_span"

# --- names of the state and controls an assessment must be given -------------
STATE_OF_CHARGE = "state_of_charge"
DISCHARGE_CURRENT = "discharge_current"
CELL_TEMPERATURE = "cell_temperature"

# --- names of the quantities this module derives -----------------------------
# Every validity condition in ``models.py`` is stated over one of these. None
# of them can be declared by a caller: they exist only as the output of a
# function below.
C_RATE = "c_rate"
CONTINUOUS_C_RATE_UTILIZATION = "continuous_c_rate_utilization"
PULSE_C_RATE_UTILIZATION = "pulse_c_rate_utilization"
PULSE_DURATION_UTILIZATION = "pulse_duration_utilization"
FINAL_STATE_OF_CHARGE = "final_state_of_charge"
SOC_WINDOW_MARGIN = "soc_window_margin"
DISCHARGE_TEMPERATURE_POSITION = "discharge_temperature_position"
INTERNAL_RESISTANCE_DRIFT_RATIO = "internal_resistance_drift_ratio"
SELF_HEATING_RISE = "self_heating_rise"
SELF_HEATING_RISE_RATIO = "self_heating_rise_ratio"
POLARIZATION_SETTLING_RATIO = "polarization_settling_ratio"
POLARIZATION_UNMODELLED_FRACTION = "polarization_unmodelled_fraction"
TERMINAL_VOLTAGE_RATIO = "terminal_voltage_ratio"
SOC_STEP_RESOLUTION_RATIO = "soc_step_resolution_ratio"
CAPACITY_TEMPERATURE_DRIFT_RATIO = "capacity_temperature_drift_ratio"
CUTOFF_CONSISTENCY_MARGIN = "cutoff_consistency_margin"
CUTOFF_REACHABILITY_MARGIN = "cutoff_reachability_margin"
PEUKERT_EXTRAPOLATION_RATIO = "peukert_extrapolation_ratio"
PEUKERT_CAPACITY_RATIO = "peukert_capacity_ratio"
PEUKERT_TEMPERATURE_DRIFT_RATIO = "peukert_temperature_drift_ratio"

# --- inert vocabularies -------------------------------------------------------
#: The caller may state which chemistry, which cooling arrangement and which
#: duty the cell is in. All three are **declarations, never inferences**, and
#: all three are **inert**: they are validated against these vocabularies,
#: serialized with their record, and read by no derivation in this module. They
#: record *why* a caller believes their declared numbers are credible — a 3C
#: continuous rating is plausible for a power cell and not for an energy cell —
#: and they never substitute for those numbers. See rule 2 in the module
#: docstring for why this separation is absolute.
LITHIUM_ION = "lithium_ion"
LEAD_ACID = "lead_acid"
NICKEL_METAL_HYDRIDE = "nickel_metal_hydride"
CHEMISTRY_VOCABULARY = (LITHIUM_ION, LEAD_ACID, NICKEL_METAL_HYDRIDE)

PASSIVE_COOLING = "passive"
FORCED_AIR_COOLING = "forced_air"
LIQUID_COOLING = "liquid"
COOLING_MODE_VOCABULARY = (PASSIVE_COOLING, FORCED_AIR_COOLING, LIQUID_COOLING)

CONTINUOUS_DUTY = "continuous"
PULSED_DUTY = "pulsed"
DUTY_TYPE_VOCABULARY = (CONTINUOUS_DUTY, PULSED_DUTY)


# =====================================================================
# Checking helpers
# =====================================================================

def _checked(
    value: Any,
    unit: str,
    label: str,
    *,
    positive: bool = False,
    span: bool = False,
) -> Quantity | None:
    """A supplied value, checked against ``unit``; ``None`` stays ``None``.

    One helper rather than the nested ``_positive(_as_quantity(...))`` pair the
    sibling thermal domain uses, which the applicability review recorded as
    repeating the unit and the label twice at every call site.

    A non-``Quantity`` that is not ``None`` is a *specification error* rather
    than missing data, and is refused instead of being silently skipped: the
    two cases must not collapse, because one means UNKNOWN and the other means
    the caller declared something wrong.

    ``positive`` refuses zero as well as negatives. Every quantity this module
    divides by is a capacity, a rating, a span or a conductance; zero is not a
    small value there but a different situation, and dividing by it would
    report infinity as though it were a measurement.

    ``span`` refuses an affine temperature scale where a *difference* is meant.
    A caller who writes ``Quantity(15.0, "degC")`` meaning "fifteen degrees of
    span" has declared 288.15 K, and every ratio built on it is wrong by a
    factor of nineteen with no dimension check able to notice. The test is the
    published-contract one the sibling domains already use: does zero of this
    unit convert to zero of the target? ``kelvin``, ``rankine`` and
    ``delta_degC`` pass; ``degC`` and ``degF`` do not.
    """
    if value is None:
        return None
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    value.require_compatible(unit, context=label)
    if span and Quantity(0.0, value.units).magnitude_in(unit) != 0.0:
        raise InvalidScientificProblem(
            f"{label} is a temperature *span* and may not use "
            f"{value.units!r}: its zero is conventional, so a difference "
            f"expressed in it is not a value of that unit. Use kelvin, or a "
            f"delta scale such as 'delta_degC'"
        )
    if positive and value.magnitude_in(unit) <= 0.0:
        raise InvalidScientificProblem(
            f"{label} must be strictly positive, got {value}"
        )
    return value


def _fraction(numerator: float, denominator: float) -> Quantity:
    """A dimensionless ratio built from two already-checked magnitudes."""
    return Quantity(numerator / denominator, DIMENSIONLESS)


def _ohmic_drop(current: Quantity, resistance: Quantity) -> Quantity:
    """I R as a voltage.

    Both inputs pass through :func:`_checked` before they reach here, so the
    product is between a current and a resistance and nothing else; the
    conversion to volts is what states the result is a voltage.
    """
    return (current * resistance).to(VOLTAGE_UNIT)


# =====================================================================
# The declared limits
# =====================================================================

@dataclass(frozen=True)
class _LimitSpec:
    """How one optional limit is checked, serialized and described.

    A single table drives ``__post_init__``, ``is_empty``, ``to_dict``,
    ``from_dict`` and the problem builder's parameter emission. The sibling
    thermal domain enumerates its nine fields in four separate places, which
    the applicability review flagged as the real risk of a tenth field reaching
    three of the four. Twenty fields make that risk a certainty, so the
    enumeration happens once.
    """

    name: str
    unit: str
    positive: bool
    span: bool
    description: str


#: Every optional declaration, in a fixed order. Order is fixed rather than
#: derived from a dict so that equal declarations always serialize identically
#: and always emit the same parameter sequence.
LIMIT_SPECS: tuple[_LimitSpec, ...] = (
    _LimitSpec(
        CONTINUOUS_DISCHARGE_C_RATE, C_RATE_UNIT, True, False,
        "Continuous discharge rating of the cell, as a C-rate.",
    ),
    _LimitSpec(
        PULSE_DISCHARGE_C_RATE, C_RATE_UNIT, True, False,
        "Peak discharge rating of the cell over a rated pulse, as a C-rate.",
    ),
    _LimitSpec(
        RATED_PULSE_DURATION, TIME_UNIT, True, False,
        "Pulse length the peak rating is published for.",
    ),
    _LimitSpec(
        USABLE_SOC_MINIMUM, DIMENSIONLESS, False, False,
        "Lower edge of the state-of-charge window this cell is used over.",
    ),
    _LimitSpec(
        USABLE_SOC_MAXIMUM, DIMENSIONLESS, False, False,
        "Upper edge of the state-of-charge window this cell is used over.",
    ),
    _LimitSpec(
        MINIMUM_DISCHARGE_TEMPERATURE, TEMPERATURE_UNIT, True, False,
        "Lowest cell temperature the discharge rating is declared over.",
    ),
    _LimitSpec(
        MAXIMUM_DISCHARGE_TEMPERATURE, TEMPERATURE_UNIT, True, False,
        "Highest cell temperature the discharge rating is declared over.",
    ),
    _LimitSpec(
        RESISTANCE_REFERENCE_TEMPERATURE, TEMPERATURE_UNIT, True, False,
        "Temperature at which the declared internal resistance was measured.",
    ),
    _LimitSpec(
        RESISTANCE_TEMPERATURE_SPAN, TEMPERATURE_UNIT, True, True,
        "Half-width about that reference over which one R_int is supported.",
    ),
    _LimitSpec(
        CELL_THERMAL_CONDUCTANCE, CONDUCTANCE_UNIT, True, False,
        "Conductance from the cell to its ambient, hA.",
    ),
    _LimitSpec(
        SELF_HEATING_RISE_BOUND, TEMPERATURE_UNIT, True, True,
        "Self-heating rise over which the cell may be treated as isothermal.",
    ),
    _LimitSpec(
        POLARIZATION_TIME_CONSTANT, TIME_UNIT, True, False,
        "Time constant of the diffusion overpotential the Rint model omits.",
    ),
    _LimitSpec(
        SOC_STEP_RESOLUTION, DIMENSIONLESS, True, False,
        "Largest state-of-charge span one integration step may traverse.",
    ),
    _LimitSpec(
        CAPACITY_REFERENCE_TEMPERATURE, TEMPERATURE_UNIT, True, False,
        "Temperature at which the declared nominal capacity was rated.",
    ),
    _LimitSpec(
        CAPACITY_TEMPERATURE_SPAN, TEMPERATURE_UNIT, True, True,
        "Half-width about that reference over which one capacity is supported.",
    ),
    _LimitSpec(
        PEUKERT_EXPONENT, DIMENSIONLESS, True, False,
        "Peukert exponent k fitted for this cell.",
    ),
    _LimitSpec(
        PEUKERT_REFERENCE_CURRENT, CURRENT_UNIT, True, False,
        "Current at which the nominal capacity and the exponent were fitted.",
    ),
    _LimitSpec(
        PEUKERT_FIT_DECADES, DIMENSIONLESS, True, False,
        "Decades of current either side of the reference the fit covers.",
    ),
    _LimitSpec(
        PEUKERT_REFERENCE_TEMPERATURE, TEMPERATURE_UNIT, True, False,
        "Temperature at which the Peukert exponent was fitted.",
    ),
    _LimitSpec(
        PEUKERT_TEMPERATURE_SPAN, TEMPERATURE_UNIT, True, True,
        "Half-width about that reference over which one exponent is supported.",
    ),
)

LIMIT_NAMES: tuple[str, ...] = tuple(spec.name for spec in LIMIT_SPECS)

#: Peukert's exponent is at least 1 by construction: ``k = 1`` is the ideal
#: cell whose deliverable charge does not depend on rate, and ``k > 1`` is the
#: rate-capacity effect the law describes. A value below 1 asserts that a cell
#: delivers *more* charge the harder it is discharged, which is not a poorly
#: fitted exponent but a different claim about the world. Peukert (1897);
#: Doerffel & Sharkh, J. Power Sources 155 (2006), 395-400, §2.
MINIMUM_PEUKERT_EXPONENT = 1.0


@dataclass(frozen=True)
class CellLimits:
    """What a caller declares about where this cell's own models stop.

    Every field is optional and defaults to ``None``, meaning *not declared*
    and never *typical for a cell of this kind*. A field left out removes the
    conditions that depend on it from IN_DOMAIN reach and leaves them UNKNOWN.
    That asymmetry is the point: supplying more information can only ever move
    a verdict away from UNKNOWN, and never turns a violated condition into a
    satisfied one.

    Kept separate from :class:`~engcore.domains.battery.cell.CellSpecification`
    because these are *evidence about the modelling assumptions*, not the five
    numbers that make a cell that cell. A cell declared with a Peukert exponent
    and one declared without are the same cell known to different depth.

    **Twenty of the twenty-one fields are Quantities that feed a derivation.**
    ``cooling_mode`` is the exception and is deliberately inert: it is
    validated against :data:`COOLING_MODE_VOCABULARY`, serialized with the rest
    of the record, and read by nothing. It records *why* the caller believes
    their ``cell_thermal_conductance`` and ``self_heating_rise_bound`` are
    credible; it never substitutes for either, and no condition consults it.
    """

    continuous_discharge_c_rate: Quantity | None = None
    pulse_discharge_c_rate: Quantity | None = None
    rated_pulse_duration: Quantity | None = None
    usable_soc_minimum: Quantity | None = None
    usable_soc_maximum: Quantity | None = None
    minimum_discharge_temperature: Quantity | None = None
    maximum_discharge_temperature: Quantity | None = None
    resistance_reference_temperature: Quantity | None = None
    resistance_temperature_span: Quantity | None = None
    cell_thermal_conductance: Quantity | None = None
    self_heating_rise_bound: Quantity | None = None
    polarization_time_constant: Quantity | None = None
    soc_step_resolution: Quantity | None = None
    capacity_reference_temperature: Quantity | None = None
    capacity_temperature_span: Quantity | None = None
    peukert_exponent: Quantity | None = None
    peukert_reference_current: Quantity | None = None
    peukert_fit_decades: Quantity | None = None
    peukert_reference_temperature: Quantity | None = None
    peukert_temperature_span: Quantity | None = None
    cooling_mode: str | None = None

    def __post_init__(self) -> None:
        for spec in LIMIT_SPECS:
            object.__setattr__(
                self,
                spec.name,
                _checked(
                    getattr(self, spec.name),
                    spec.unit,
                    spec.name,
                    positive=spec.positive,
                    span=spec.span,
                ),
            )

        # A state of charge is a fraction of the cell's charge, bounded by its
        # own definition (Plett Vol. I, Ch. 2: z = 1 is fully charged, z = 0
        # fully discharged). A window edge outside [0, 1] is not an extreme
        # setting, it is not a state of charge.
        for label in (USABLE_SOC_MINIMUM, USABLE_SOC_MAXIMUM, SOC_STEP_RESOLUTION):
            value = getattr(self, label)
            if value is None:
                continue
            fraction = value.magnitude_in(DIMENSIONLESS)
            if not 0.0 <= fraction <= 1.0:
                raise InvalidScientificProblem(
                    f"{label} must lie in [0, 1], got {fraction!r}"
                )
        if self.soc_step_resolution is not None:
            # ``_checked`` already refused zero; restated here because a
            # resolution of zero would demand infinitely many steps rather
            # than being a strict requirement.
            if self.soc_step_resolution.magnitude_in(DIMENSIONLESS) <= 0.0:
                raise InvalidScientificProblem(
                    f"{SOC_STEP_RESOLUTION} must be strictly positive"
                )

        self._require_ordered_pair(
            USABLE_SOC_MINIMUM, USABLE_SOC_MAXIMUM, DIMENSIONLESS,
            "a usable state-of-charge window",
        )
        self._require_ordered_pair(
            MINIMUM_DISCHARGE_TEMPERATURE, MAXIMUM_DISCHARGE_TEMPERATURE,
            TEMPERATURE_UNIT, "a discharge temperature range",
        )

        if self.peukert_exponent is not None:
            exponent = self.peukert_exponent.magnitude_in(DIMENSIONLESS)
            if exponent < MINIMUM_PEUKERT_EXPONENT:
                raise InvalidScientificProblem(
                    f"{PEUKERT_EXPONENT} must be at least "
                    f"{MINIMUM_PEUKERT_EXPONENT}, got {exponent!r}: an "
                    f"exponent below 1 asserts that a cell delivers more "
                    f"charge the harder it is discharged"
                )

        if self.cooling_mode is not None:
            mode = str(self.cooling_mode).strip()
            if mode not in COOLING_MODE_VOCABULARY:
                raise InvalidScientificProblem(
                    f"cooling_mode must be one of "
                    f"{list(COOLING_MODE_VOCABULARY)}, got {mode!r}"
                )
            object.__setattr__(self, "cooling_mode", mode)

    def _require_ordered_pair(
        self, lower_name: str, upper_name: str, unit: str, what: str
    ) -> None:
        """Refuse a declared interval whose upper edge is not above its lower.

        Both derived positions divide by ``upper - lower``. An inverted or
        degenerate pair would either divide by zero or silently flip the sense
        of the condition, which is worse than refusing the declaration.
        """
        lower = getattr(self, lower_name)
        upper = getattr(self, upper_name)
        if lower is None or upper is None:
            return
        if upper.magnitude_in(unit) <= lower.magnitude_in(unit):
            raise InvalidScientificProblem(
                f"{what} needs {upper_name} strictly above {lower_name}, got "
                f"{upper} and {lower}"
            )

    @property
    def is_empty(self) -> bool:
        """True when nothing was declared — every condition here is UNKNOWN."""
        return all(getattr(self, name) is None for name in LIMIT_NAMES)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"schema": CELL_LIMITS_SCHEMA}
        for name in LIMIT_NAMES:
            value = getattr(self, name)
            payload[name] = value.to_dict() if value is not None else None
        payload["cooling_mode"] = self.cooling_mode
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CellLimits":
        require_schema(payload, CELL_LIMITS_SCHEMA)
        fields: dict[str, Any] = {}
        for name in LIMIT_NAMES:
            raw = payload.get(name)
            fields[name] = Quantity.from_dict(raw) if raw else None
        fields["cooling_mode"] = payload.get("cooling_mode")
        return cls(**fields)


# =====================================================================
# Rate
# =====================================================================

def c_rate(
    *,
    current: Quantity | None,
    nominal_capacity: Quantity | None,
) -> Quantity | None:
    """C = I / Q_nom — the discharge current in units of the cell's capacity.

    **Definition.** The C-rate is the current normalized by the nominal
    capacity, so 1C discharges the nominal capacity in one hour. Plett,
    *Battery Management Systems, Volume I: Battery Modeling* (Artech House,
    2015), Ch. 2, which defines capacity in ampere-hours and rate as a multiple
    of it.

    Carries reciprocal-time dimension and is returned in ``1/hour``, which is
    what makes "3C" a checkable quantity rather than a naming habit: a rating
    declared in ``1/hour`` and a current-over-capacity computed from amperes
    and coulombs meet in the same dimension or they raise.

    Returns ``None`` if either input is absent.
    """
    checked_current = _checked(current, CURRENT_UNIT, DISCHARGE_CURRENT)
    capacity = _checked(
        nominal_capacity, CAPACITY_UNIT, NOMINAL_CAPACITY, positive=True
    )
    if checked_current is None or capacity is None:
        return None
    return (checked_current / capacity).to(C_RATE_UNIT)


def continuous_c_rate_utilization(
    *,
    rate: Quantity | None,
    rating: Quantity | None,
) -> Quantity | None:
    """|C| / C_continuous — the share of the continuous rating in use.

    **Definition.** The magnitude of the operating C-rate over the cell's
    declared continuous discharge rating. The absolute value is taken on the
    numerator only: a rating is a magnitude and the sign of a current is a
    direction.

    **Why the rating is declared and not fixed.** A continuous discharge
    rating is a property of the *cell*, set by its electrode area, its tab
    design and its thermal path, and published on its datasheet. One model
    record has to serve every cell, so the number belongs to the caller's
    declaration and the condition is stated over the dimensionless fraction of
    it in use. UNKNOWN unless the rating is declared.
    """
    checked_rate = _checked(rate, C_RATE_UNIT, C_RATE)
    checked_rating = _checked(
        rating, C_RATE_UNIT, CONTINUOUS_DISCHARGE_C_RATE, positive=True
    )
    if checked_rate is None or checked_rating is None:
        return None
    return _fraction(
        abs(checked_rate.magnitude_in(C_RATE_UNIT)),
        checked_rating.magnitude_in(C_RATE_UNIT),
    )


def pulse_c_rate_utilization(
    *,
    pulse_current: Quantity | None,
    nominal_capacity: Quantity | None,
    rating: Quantity | None,
) -> Quantity | None:
    """|C_peak| / C_pulse — the share of the pulse rating in use.

    **Definition.** The peak C-rate the declared duty reaches, over the cell's
    declared pulse discharge rating. A separate and independent limit from the
    continuous one: a cell rated 1C continuous is commonly rated several C for
    a short pulse, because the constraint on the continuous number is thermal
    and accumulates while the constraint on the pulse number is not.

    UNKNOWN unless the duty declares a pulse current *and* the cell declares a
    pulse rating. A duty with no declared pulse does not thereby satisfy the
    pulse condition — it leaves it unanswered.
    """
    peak = c_rate(current=pulse_current, nominal_capacity=nominal_capacity)
    checked_rating = _checked(
        rating, C_RATE_UNIT, PULSE_DISCHARGE_C_RATE, positive=True
    )
    if peak is None or checked_rating is None:
        return None
    return _fraction(
        abs(peak.magnitude_in(C_RATE_UNIT)),
        checked_rating.magnitude_in(C_RATE_UNIT),
    )


def pulse_duration_utilization(
    *,
    pulse_duration: Quantity | None,
    rated_duration: Quantity | None,
) -> Quantity | None:
    """t_pulse / t_rated — the share of the rated pulse length in use.

    **Definition.** The declared pulse length over the length the peak rating
    is published for. A peak rating is meaningless without the duration it was
    measured over: the same cell's 10 s and 30 s pulse ratings differ, because
    what the pulse rating bounds is the heat deposited and the overpotential
    reached during the pulse, and both grow with its length.

    Separate from :func:`pulse_c_rate_utilization` because the two fail
    independently: a duty may sit inside the peak current and outside the
    duration it was rated over, and a single combined number could not say
    which. UNKNOWN unless both are declared.
    """
    checked_duration = _checked(
        pulse_duration, TIME_UNIT, PULSE_DURATION, positive=True
    )
    checked_rated = _checked(
        rated_duration, TIME_UNIT, RATED_PULSE_DURATION, positive=True
    )
    if checked_duration is None or checked_rated is None:
        return None
    return _fraction(
        checked_duration.magnitude_in(TIME_UNIT),
        checked_rated.magnitude_in(TIME_UNIT),
    )


# =====================================================================
# State of charge
# =====================================================================

def final_state_of_charge(
    *,
    initial_state_of_charge: Quantity | None,
    current: Quantity | None,
    duration: Quantity | None,
    coulombic_efficiency: Quantity | None,
    nominal_capacity: Quantity | None,
) -> Quantity | None:
    """SoC(t) = SoC_0 - I t / (eta Q_nom), for constant discharge current.

    **Definition.** The coulomb-counting relation, Plett, *Battery Management
    Systems, Volume I: Battery Modeling* (Artech House, 2015), Ch. 2: the state
    of charge is the initial state minus the charge removed divided by the
    cell's usable charge, with discharge-direction coulombic efficiency reducing
    the nominal capacity available to the external load.
    For a current held constant over the interval the integral is exact and the
    expression above is the closed form of it.

    **Direction.** ``current`` is positive out of the cell, so a positive
    current lowers the state of charge. This domain models discharge; the sign
    convention is stated rather than defended, and a negative current is
    representable but is not what any validity domain here is declared over.

    Returns ``None`` if any input is absent. Note that the result may lie
    outside [0, 1]: that is not clipped here, because a state of charge the
    counter drives below zero is exactly the situation
    :func:`soc_window_margin` exists to report.
    """
    initial = _checked(
        initial_state_of_charge, DIMENSIONLESS, STATE_OF_CHARGE
    )
    checked_current = _checked(current, CURRENT_UNIT, DISCHARGE_CURRENT)
    checked_duration = _checked(duration, TIME_UNIT, DURATION, positive=True)
    efficiency = _checked(
        coulombic_efficiency, DIMENSIONLESS, COULOMBIC_EFFICIENCY, positive=True
    )
    capacity = _checked(
        nominal_capacity, CAPACITY_UNIT, NOMINAL_CAPACITY, positive=True
    )
    if (
        initial is None
        or checked_current is None
        or checked_duration is None
        or efficiency is None
        or capacity is None
    ):
        return None
    removed = (
        checked_current
        * checked_duration
        / efficiency.magnitude_in(DIMENSIONLESS)
        / capacity
    ).to(DIMENSIONLESS)
    return Quantity(
        initial.magnitude_in(DIMENSIONLESS) - removed.magnitude_in(DIMENSIONLESS),
        DIMENSIONLESS,
    )


def soc_window_margin(
    *,
    initial_state_of_charge: Quantity | None,
    final_soc: Quantity | None,
    window_minimum: Quantity | None,
    window_maximum: Quantity | None,
) -> Quantity | None:
    """The run's distance from the nearest edge of the declared SoC window.

    **Definition.** ``min(SoC_min - w_lo, w_hi - SoC_max) / (w_hi - w_lo)``,
    where ``SoC_min`` and ``SoC_max`` are the extremes of the trajectory and
    ``[w_lo, w_hi]`` is the window the caller declares the cell is used over.
    Negative when the run leaves the window; zero exactly on an edge.

    **Why the endpoints bound the trajectory exactly.** For a current constant
    over the interval the coulomb-counting relation is affine in ``t``, so the
    state of charge is monotone and its extremes over any interval are its
    endpoints. No interior sampling is needed and none is done.

    **What the window is for.** Both this domain's constitutive shortcuts fail
    at the ends of the charge axis. The affine OCV of :func:`open_circuit_
    voltage` is a chord: a real OCV curve has a knee near empty and a plateau
    near full, so a straight line fitted across the middle is worst exactly at
    the extremes (Plett, Ch. 3, on the OCV relationship and its measurement).
    A constant ``R_int`` is likewise least defensible near empty, where charge
    transfer and diffusion resistance rise sharply. The window is the caller's
    statement of where those two approximations are supported, and this margin
    is whether the run respected it.

    Returns ``None`` unless the trajectory and both edges are all available.
    """
    initial = _checked(initial_state_of_charge, DIMENSIONLESS, STATE_OF_CHARGE)
    final = _checked(final_soc, DIMENSIONLESS, FINAL_STATE_OF_CHARGE)
    lower = _checked(window_minimum, DIMENSIONLESS, USABLE_SOC_MINIMUM)
    upper = _checked(window_maximum, DIMENSIONLESS, USABLE_SOC_MAXIMUM)
    if initial is None or final is None or lower is None or upper is None:
        return None
    low = lower.magnitude_in(DIMENSIONLESS)
    high = upper.magnitude_in(DIMENSIONLESS)
    if high <= low:
        raise InvalidScientificProblem(
            f"the declared state-of-charge window needs "
            f"{USABLE_SOC_MAXIMUM} above {USABLE_SOC_MINIMUM}, got "
            f"{high!r} and {low!r}"
        )
    start = initial.magnitude_in(DIMENSIONLESS)
    end = final.magnitude_in(DIMENSIONLESS)
    return _fraction(
        min(min(start, end) - low, high - max(start, end)), high - low
    )


def soc_step_resolution_ratio(
    *,
    initial_state_of_charge: Quantity | None,
    final_soc: Quantity | None,
    resolution: Quantity | None,
) -> Quantity | None:
    """|SoC_0 - SoC_end| / declared step resolution — how coarse one step is.

    **Definition.** The state-of-charge span one integration step traverses,
    over the largest span the caller declares a single step may cover.

    **What the model actually needs, which is what this encodes.** Coulomb
    counting itself is exact for a current constant over the step, so the
    requirement is not on the integration. It is on everything the step holds
    *fixed while the state of charge moves*: this domain evaluates the
    open-circuit voltage and the terminal voltage once per step, at one state
    of charge, and both are functions of it. A step that walks a long way down
    the charge axis reports a terminal voltage that was true at one end of it
    and at no other point, and reports a runtime built on that voltage. The
    declared resolution is how much of that the caller will accept; a load that
    varies within the step must be resolved by steps short enough to sample it,
    which is the same statement seen from the load's side.

    **Why the resolution is declared and not fixed.** How much OCV movement is
    tolerable inside one step depends on the slope of that cell's OCV curve and
    on what the answer is for. There is no cell-independent number and none is
    invented. UNKNOWN unless the caller declares one.
    """
    initial = _checked(initial_state_of_charge, DIMENSIONLESS, STATE_OF_CHARGE)
    final = _checked(final_soc, DIMENSIONLESS, FINAL_STATE_OF_CHARGE)
    step = _checked(
        resolution, DIMENSIONLESS, SOC_STEP_RESOLUTION, positive=True
    )
    if initial is None or final is None or step is None:
        return None
    return _fraction(
        abs(
            initial.magnitude_in(DIMENSIONLESS)
            - final.magnitude_in(DIMENSIONLESS)
        ),
        step.magnitude_in(DIMENSIONLESS),
    )


# =====================================================================
# Voltage
# =====================================================================

def open_circuit_voltage_evaluation(
    *,
    state_of_charge: Quantity | None,
    ocv_at_empty: Quantity | None,
    ocv_at_full: Quantity | None,
    curve: DeclaredCurve | None = None,
) -> CurveEvaluation:
    """OCV(z), with the status under which it was answered.

    **Two declarations, one of which is a curve.** Without ``curve`` this is
    the affine chord ``OCV(z) = V_empty + (V_full - V_empty) z`` between the
    two open-circuit voltages the caller declares at the ends of the charge
    axis. That is a *linearisation* and is declared as one: a real cell's
    OCV(z) is a measured curve with a plateau and a knee, and Plett, *Battery
    Management Systems, Volume I* (2015), Ch. 3 treats it as tabulated data
    precisely because no two-point line reproduces it everywhere. An alkaline
    cell falls from about 1.6 V to about 0.9 V across a discharge and does
    almost none of it linearly.

    With ``curve``, the caller has declared that measured curve, and it
    governs. The chord is then not consulted at all: there is one source of
    truth for what this cell's OCV is, and a cell carrying a curve derives its
    chord endpoints *from* the curve rather than alongside it.

    **Three statuses, and only one carries a number.** A curve is evidence
    over the interval it was declared across; asked outside it, this returns
    ``OUTSIDE_VALIDATED_DOMAIN`` and no value rather than extrapolating. The
    chord has no such interval and answers everywhere it is given three
    numbers, which is exactly the wider claim the curve exists to narrow.
    """
    charge = _checked(state_of_charge, DIMENSIONLESS, STATE_OF_CHARGE)
    if curve is not None:
        return curve.evaluate(charge)
    empty = _checked(ocv_at_empty, VOLTAGE_UNIT, OCV_AT_EMPTY)
    full = _checked(ocv_at_full, VOLTAGE_UNIT, OCV_AT_FULL)
    if charge is None or empty is None or full is None:
        return CurveEvaluation(
            ValidityStatus.UNKNOWN,
            None,
            "the affine chord needs a state of charge and both endpoint "
            "voltages, and at least one was not declared",
        )
    low = empty.magnitude_in(VOLTAGE_UNIT)
    high = full.magnitude_in(VOLTAGE_UNIT)
    return CurveEvaluation(
        ValidityStatus.IN_DOMAIN,
        Quantity(
            low + (high - low) * charge.magnitude_in(DIMENSIONLESS), VOLTAGE_UNIT
        ),
        "",
    )


def open_circuit_voltage(
    *,
    state_of_charge: Quantity | None,
    ocv_at_empty: Quantity | None,
    ocv_at_full: Quantity | None,
    curve: DeclaredCurve | None = None,
) -> Quantity | None:
    """The value :func:`open_circuit_voltage_evaluation` produced, or ``None``.

    The shape every other derivation in this module has, kept so that a
    caller who does not care *why* there is no number does not have to learn
    a new one. ``None`` covers both "not declared" and "outside the curve's
    interval"; a caller who needs to tell those apart reads the evaluation.
    """
    return open_circuit_voltage_evaluation(
        state_of_charge=state_of_charge,
        ocv_at_empty=ocv_at_empty,
        ocv_at_full=ocv_at_full,
        curve=curve,
    ).value


def terminal_voltage(
    *,
    open_circuit: Quantity | None,
    current: Quantity | None,
    internal_resistance: Quantity | None,
) -> Quantity | None:
    """V = OCV(z) - I R_int — the Rint model's terminal voltage.

    **Definition.** The whole of the Rint equivalent circuit: one ideal source
    at the open-circuit voltage in series with one constant resistance. Plett,
    *Battery Management Systems, Volume I* (2015), Ch. 3, which introduces it
    as the simplest equivalent-circuit cell model and immediately names what it
    omits — the diffusion voltages that a series RC branch represents.

    ``current`` is positive out of the cell, so discharge lowers the terminal
    voltage below the open-circuit value.
    """
    ocv = _checked(open_circuit, VOLTAGE_UNIT, "open_circuit_voltage")
    checked_current = _checked(current, CURRENT_UNIT, DISCHARGE_CURRENT)
    resistance = _checked(
        internal_resistance, RESISTANCE_UNIT, INTERNAL_RESISTANCE, positive=True
    )
    if ocv is None or checked_current is None or resistance is None:
        return None
    drop = _ohmic_drop(checked_current, resistance)
    return Quantity(
        ocv.magnitude_in(VOLTAGE_UNIT) - drop.magnitude_in(VOLTAGE_UNIT),
        VOLTAGE_UNIT,
    )


def terminal_voltage_ratio(
    *,
    terminal: Quantity | None,
    open_circuit: Quantity | None,
) -> Quantity | None:
    """V / OCV = 1 - I R_int / OCV — the model's own admissibility.

    **Definition.** The terminal voltage as a fraction of the open-circuit
    voltage at the same state of charge, evaluated at the worst point of the
    interval.

    ``V = OCV - I R`` is a straight line in ``I`` and every straight line with
    a non-zero slope crosses zero. Past the crossing the expression does not
    describe a deeply-loaded cell, it describes one delivering current at a
    negative terminal voltage, which the model has no basis to assert. The
    bound is therefore the physics of the computed quantity rather than a
    tolerance, exactly as the sibling electrical domain's
    ``linear_resistance_ratio`` is.

    Requires a positive open-circuit voltage: at ``OCV <= 0`` the ratio is not
    a fraction of anything, and the declaration that produced it is refused
    rather than divided by.
    """
    checked_terminal = _checked(terminal, VOLTAGE_UNIT, "terminal_voltage")
    ocv = _checked(
        open_circuit, VOLTAGE_UNIT, "open_circuit_voltage", positive=True
    )
    if checked_terminal is None or ocv is None:
        return None
    return _fraction(
        checked_terminal.magnitude_in(VOLTAGE_UNIT),
        ocv.magnitude_in(VOLTAGE_UNIT),
    )


def voltage_cutoff_state_of_charge(
    *,
    cutoff_voltage: Quantity | None,
    current: Quantity | None,
    internal_resistance: Quantity | None,
    ocv_at_empty: Quantity | None,
    ocv_at_full: Quantity | None,
) -> Quantity | None:
    """The state of charge at which V(z) - I R reaches the declared cutoff.

    **Definition.** Inverting ``V_cut = OCV(z) - I R_int`` on the affine chord
    of :func:`open_circuit_voltage`::

        z_cut = (V_cut + I R_int - V_empty) / (V_full - V_empty)

    This is the state of charge a *loaded* cell is at when its terminal voltage
    hits the cutoff, and it rises with current: the harder the discharge, the
    more charge is still in the cell when the voltage limit stops the run. That
    is the mechanism behind the usable-capacity loss at high rate that
    :data:`PEUKERT_CAPACITY_RATIO` describes empirically, seen here from the
    circuit rather than from a fitted exponent.

    Requires a non-degenerate OCV chord (``V_full > V_empty``): a flat chord
    has no invertible relation between voltage and charge, so a voltage cutoff
    names no state of charge.
    """
    cutoff = _checked(cutoff_voltage, VOLTAGE_UNIT, CUTOFF_VOLTAGE)
    checked_current = _checked(current, CURRENT_UNIT, DISCHARGE_CURRENT)
    resistance = _checked(
        internal_resistance, RESISTANCE_UNIT, INTERNAL_RESISTANCE, positive=True
    )
    empty = _checked(ocv_at_empty, VOLTAGE_UNIT, OCV_AT_EMPTY)
    full = _checked(ocv_at_full, VOLTAGE_UNIT, OCV_AT_FULL)
    if (
        cutoff is None
        or checked_current is None
        or resistance is None
        or empty is None
        or full is None
    ):
        return None
    low = empty.magnitude_in(VOLTAGE_UNIT)
    high = full.magnitude_in(VOLTAGE_UNIT)
    if high <= low:
        raise InvalidScientificProblem(
            f"{OCV_AT_FULL} must exceed {OCV_AT_EMPTY} for a cutoff voltage "
            f"to name a state of charge, got {high!r} and {low!r}"
        )
    drop = _ohmic_drop(checked_current, resistance)
    return Quantity(
        (cutoff.magnitude_in(VOLTAGE_UNIT) + drop.magnitude_in(VOLTAGE_UNIT) - low)
        / (high - low),
        DIMENSIONLESS,
    )


def cutoff_consistency_margin(
    *,
    cutoff_state_of_charge: Quantity | None,
    voltage_cutoff_soc: Quantity | None,
) -> Quantity | None:
    """z_cut,declared - z_cut,voltage — do the two declared cutoffs agree?

    **Definition.** The declared state-of-charge cutoff minus the state of
    charge at which the terminal voltage reaches the declared voltage cutoff,
    at this load. Non-negative exactly when the depth of discharge the caller
    asked for is reachable before the voltage limit stops the run.

    **Why this is the condition that catches a wrong sizing.** A runtime
    computed to a declared depth of discharge is only that runtime if the cell
    can actually get there. At high current ``I R_int`` is subtracted from
    every point of the OCV curve, so the voltage cutoff bites at a *higher*
    state of charge and the declared depth is never reached: the answer is
    over-reported, silently, by whatever fraction of the capacity lies between
    the two. The two cutoffs are independent declarations and this is the only
    place their consistency is checked.

    UNKNOWN unless both cutoffs are declared. Declaring only one does not make
    them consistent — it leaves the question unasked.
    """
    declared = _checked(
        cutoff_state_of_charge, DIMENSIONLESS, CUTOFF_STATE_OF_CHARGE
    )
    from_voltage = _checked(
        voltage_cutoff_soc, DIMENSIONLESS, "voltage_cutoff_state_of_charge"
    )
    if declared is None or from_voltage is None:
        return None
    return Quantity(
        declared.magnitude_in(DIMENSIONLESS)
        - from_voltage.magnitude_in(DIMENSIONLESS),
        DIMENSIONLESS,
    )


def cutoff_reachability_margin(
    *,
    state_of_charge: Quantity | None,
    cutoff_state_of_charge: Quantity | None,
    voltage_cutoff_soc: Quantity | None,
) -> Quantity | None:
    """z_0 - z_stop — is the cutoff ahead of the run, or behind it?

    **Definition.** The starting state of charge minus the binding cutoff,
    where the binding cutoff is the HIGHER of the two declared cutoffs, exactly
    as the runtime model's published equation defines ``z_stop``.

    **Why this is a separate question from consistency.**
    :func:`cutoff_consistency_margin` compares the two cutoffs *with each
    other* and answers "which of them stops the run first". Neither is compared
    with where the run *starts*, and a discharge at constant current walks the
    state of charge monotonically DOWN -- "discharge only" is the model's own
    first assumption -- so a cutoff declared ABOVE the starting state is never
    reached at all. The published runtime ``t = (z_0 - z_stop) eta Q_nom / I``
    returns the time to reach it anyway, and that time is negative. An elapsed
    time to an event that does not occur is not an answer, and until this
    condition existed the model reported IN_DOMAIN while the solver emitted it.

    The bound of 0 is definitional: the two meeting exactly is a run that is
    already at its cutoff, whose runtime is zero.

    UNKNOWN unless the starting state of charge and at least one cutoff are
    declared. A run with no cutoff at all computes no runtime, so there is
    nothing to bound.
    """
    start = _checked(state_of_charge, DIMENSIONLESS, STATE_OF_CHARGE)
    if start is None:
        return None
    declared = _checked(
        cutoff_state_of_charge, DIMENSIONLESS, CUTOFF_STATE_OF_CHARGE
    )
    from_voltage = _checked(
        voltage_cutoff_soc, DIMENSIONLESS, "voltage_cutoff_state_of_charge"
    )
    candidates = [
        value.magnitude_in(DIMENSIONLESS)
        for value in (declared, from_voltage)
        if value is not None
    ]
    if not candidates:
        return None
    return Quantity(
        start.magnitude_in(DIMENSIONLESS) - max(candidates), DIMENSIONLESS
    )


# =====================================================================
# Heat and temperature
# =====================================================================

def heat_generation(
    *,
    current: Quantity | None,
    internal_resistance: Quantity | None,
) -> Quantity | None:
    """Q = I^2 R_int — the irreversible heat, and only that.

    **Definition.** The Joule dissipation in the series resistance of the Rint
    circuit. Plett, *Battery Management Systems, Volume I* (2015), Ch. 3, for
    the circuit; the dissipation in a series resistance is Joule's law.

    **What is deliberately excluded.** The reversible (entropic) heat
    ``-I T dU/dT``, which follows from the temperature coefficient of the
    open-circuit voltage, is not computed here and no term stands in for it. It
    is not negligible: near room temperature it is of the same order as the
    Joule term at low rate, and it changes *sign* with the direction of current
    and with state of charge, so a cell can absorb heat while discharging. This
    domain therefore reports a heat that is systematically wrong at low rate,
    by an amount it cannot bound, and the honest consequence is stated in the
    model's assumptions rather than absorbed into a fudge factor. Computing it
    would require ``dU/dT(z)`` for the cell, which is a measurement this
    repository does not have.

    Returns ``None`` if either input is absent.
    """
    checked_current = _checked(current, CURRENT_UNIT, DISCHARGE_CURRENT)
    resistance = _checked(
        internal_resistance, RESISTANCE_UNIT, INTERNAL_RESISTANCE, positive=True
    )
    if checked_current is None or resistance is None:
        return None
    return (checked_current * checked_current * resistance).to(POWER_UNIT)


def self_heating_rise(
    *,
    heat: Quantity | None,
    thermal_conductance: Quantity | None,
) -> Quantity | None:
    """dT_ss = Q / hA — the steady rise the declared dissipation implies.

    **Definition.** Setting ``dT/dt = 0`` in the lumped balance
    ``C dT/dt = Q - hA (T - T_amb)`` gives ``T_ss - T_amb = Q / hA``. Incropera,
    DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass Transfer*, 6th ed.
    (Wiley, 2007), §5.3, Eq. 5.25, for the lumped body with generation.

    This is the *asymptote*, not the rise at the end of the interval, and that
    is the right quantity for an applicability question: a horizon shorter than
    the thermal time constant does not make the assumption safer, it only
    defers the excursion. The sibling thermal domain's
    ``steady_state_temperature`` takes the same position for the same reason.

    Returns a temperature *span* in kelvin. UNKNOWN unless the caller declares
    the cell's conductance to its ambient.
    """
    checked_heat = _checked(heat, POWER_UNIT, "heat_generation")
    conductance = _checked(
        thermal_conductance,
        CONDUCTANCE_UNIT,
        CELL_THERMAL_CONDUCTANCE,
        positive=True,
    )
    if checked_heat is None or conductance is None:
        return None
    return (checked_heat / conductance).to(TEMPERATURE_UNIT)


def self_heating_rise_ratio(
    *,
    rise: Quantity | None,
    bound: Quantity | None,
) -> Quantity | None:
    """dT_ss / declared isothermal-cell budget — is the cell one temperature?

    **Definition.** The implied steady self-heating rise over the span the
    caller declares the cell may be treated as a single temperature across.

    **What this condition is really about.** Every model in this domain assigns
    the cell *one* temperature: the Rint model evaluates one ``R_int``, the
    capacity is one number, and the conditions on both are stated against one
    reference. A cell dissipating enough to sit tens of kelvin above its
    ambient is not at one temperature — its core is hotter than its can, and
    the resistance and capacity that matter are the ones at the core. This
    ratio is that assumption made falsifiable from the two things the caller
    already declared: how much heat the discharge makes, and how well the cell
    is cooled.

    **Why the budget is declared and not fixed.** How much rise is tolerable
    depends on how steeply that cell's properties move with temperature and on
    what the answer is for. No cell-independent number exists and none is
    invented. UNKNOWN unless the caller declares one.
    """
    checked_rise = _checked(rise, TEMPERATURE_UNIT, SELF_HEATING_RISE, span=True)
    checked_bound = _checked(
        bound,
        TEMPERATURE_UNIT,
        SELF_HEATING_RISE_BOUND,
        positive=True,
        span=True,
    )
    if checked_rise is None or checked_bound is None:
        return None
    return _fraction(
        checked_rise.magnitude_in(TEMPERATURE_UNIT),
        checked_bound.magnitude_in(TEMPERATURE_UNIT),
    )


def discharge_temperature_position(
    *,
    temperature: Quantity | None,
    minimum: Quantity | None,
    maximum: Quantity | None,
) -> Quantity | None:
    """(T - T_min) / (T_max - T_min) — where in the rated range the cell sits.

    **Definition.** The cell temperature as a normalized position inside the
    discharge temperature range the caller declares, so 0 is the low edge and 1
    the high edge and anything outside [0, 1] is outside the range.

    **Discharge only, and said so.** A cell's charge temperature range is
    narrower than its discharge range — most notably at the cold end, where
    charging plates lithium metal rather than intercalating it. This domain
    models discharge and declares only the discharge range; a caller charging
    the cell is outside the whole domain, not merely outside this condition,
    and no condition here would catch it.

    **Why a position rather than two bounds on the temperature itself.** The
    edges belong to the *cell*, and a ``RangeCondition`` fixes its bounds when
    the model record is written — one record has to serve every cell. The same
    reasoning the sibling electrical domain gives for stating its rating limits
    over utilizations. UNKNOWN unless both edges are declared.
    """
    checked = _checked(temperature, TEMPERATURE_UNIT, CELL_TEMPERATURE)
    low = _checked(
        minimum, TEMPERATURE_UNIT, MINIMUM_DISCHARGE_TEMPERATURE, positive=True
    )
    high = _checked(
        maximum, TEMPERATURE_UNIT, MAXIMUM_DISCHARGE_TEMPERATURE, positive=True
    )
    if checked is None or low is None or high is None:
        return None
    low_k = low.magnitude_in(TEMPERATURE_UNIT)
    high_k = high.magnitude_in(TEMPERATURE_UNIT)
    if high_k <= low_k:
        raise InvalidScientificProblem(
            f"the declared discharge temperature range needs "
            f"{MAXIMUM_DISCHARGE_TEMPERATURE} above "
            f"{MINIMUM_DISCHARGE_TEMPERATURE}, got {high_k!r} and {low_k!r}"
        )
    return _fraction(
        checked.magnitude_in(TEMPERATURE_UNIT) - low_k, high_k - low_k
    )


def _temperature_drift_ratio(
    temperature: Quantity | None,
    reference: Quantity | None,
    span: Quantity | None,
    *,
    reference_label: str,
    span_label: str,
) -> Quantity | None:
    """|T - T_ref| / declared span. Shared by the two drift conditions.

    Both conditions have the same shape — a property measured at one
    temperature, claimed over a half-width the caller declares — and differ
    only in which property and which declaration. Sharing the arithmetic keeps
    them one line each; they stay two separate conditions over two separate
    derived names because they fail independently and a caller must be able to
    see which one did.
    """
    checked = _checked(temperature, TEMPERATURE_UNIT, CELL_TEMPERATURE)
    checked_reference = _checked(
        reference, TEMPERATURE_UNIT, reference_label, positive=True
    )
    checked_span = _checked(
        span, TEMPERATURE_UNIT, span_label, positive=True, span=True
    )
    if checked is None or checked_reference is None or checked_span is None:
        return None
    return _fraction(
        abs(
            checked.magnitude_in(TEMPERATURE_UNIT)
            - checked_reference.magnitude_in(TEMPERATURE_UNIT)
        ),
        checked_span.magnitude_in(TEMPERATURE_UNIT),
    )


def internal_resistance_drift_ratio(
    *,
    temperature: Quantity | None,
    reference_temperature: Quantity | None,
    span: Quantity | None,
) -> Quantity | None:
    """|T - T_R,ref| / declared span — is the measured R_int still the R_int?

    **Definition.** The operating excursion from the temperature at which the
    declared internal resistance was measured, over the half-width the caller
    declares one value carries.

    **Why this is not optional physics.** A cell's internal resistance is
    strongly temperature dependent — it is dominated by electrolyte
    conductivity and charge-transfer kinetics, both thermally activated, and it
    can more than double between room temperature and freezing (Plett,
    *Battery Management Systems, Volume I* (2015), Ch. 3, on the measurement of
    equivalent-circuit resistances and their operating-condition dependence).
    A single declared ``R_int`` is a claim about one temperature, and this is
    the condition that says so. It is the same treatment the sibling electrical
    domain gives ``alpha(T)``: the reference and the span are the material's to
    declare, and the condition asks only whether the operating point stayed
    inside the caller's own statement.

    **The bound is not the temperature dependence itself.** No functional form
    is fitted here and none is claimed. UNKNOWN unless both the reference
    temperature and the span are declared.
    """
    return _temperature_drift_ratio(
        temperature,
        reference_temperature,
        span,
        reference_label=RESISTANCE_REFERENCE_TEMPERATURE,
        span_label=RESISTANCE_TEMPERATURE_SPAN,
    )


def capacity_temperature_drift_ratio(
    *,
    temperature: Quantity | None,
    reference_temperature: Quantity | None,
    span: Quantity | None,
) -> Quantity | None:
    """|T - T_Q,ref| / declared span — is the rated capacity still the capacity?

    **Definition.** The operating excursion from the temperature at which the
    declared nominal capacity was rated, over the half-width the caller
    declares one value carries.

    **Why a rated capacity carries a temperature with it.** Coulomb counting
    divides by ``Q_nom``, and ``Q_nom`` is a measurement taken under stated
    conditions: IEC 61960-3:2017, *Secondary cells and batteries containing
    alkaline or other non-acid electrolytes - Secondary lithium cells and
    batteries for portable applications*, Clause 7, specifies the discharge
    performance tests and the ambient temperature the rated capacity is
    measured at, and separately specifies low- and high-temperature discharge
    performance because the deliverable charge is not the same there. A counter
    normalizing by a 20 degC rating while the cell sits near freezing reports a
    state of charge against a capacity the cell does not have.

    **Distinct from** :func:`internal_resistance_drift_ratio`: different
    property, different reference, different span. A cell may declare a wide
    span for its capacity and a narrow one for its resistance, and the two
    conditions must be able to disagree. UNKNOWN unless both are declared.
    """
    return _temperature_drift_ratio(
        temperature,
        reference_temperature,
        span,
        reference_label=CAPACITY_REFERENCE_TEMPERATURE,
        span_label=CAPACITY_TEMPERATURE_SPAN,
    )


# =====================================================================
# Time scale
# =====================================================================

def polarization_settling_ratio(
    *,
    duration: Quantity | None,
    time_constant: Quantity | None,
) -> Quantity | None:
    """t / tau_pol — the interval measured in the relaxation the model omits.

    **Definition.** The length of the interval the Rint model is applied over,
    divided by the time constant of the diffusion overpotential the caller
    declares for this cell.

    **Reported, not conditioned.** No bound is placed on this ratio, because
    the admissible set is not an interval in it: the Rint form is defensible
    both far above and far below 1, and inadmissible in between. The bound
    lives on :func:`polarization_unmodelled_fraction`, which folds those two
    regimes into one. This ratio is carried because it is the number a reader
    who has just been told the fraction is too large will want next.

    UNKNOWN unless the caller declares a polarization time constant.
    """
    checked_duration = _checked(duration, TIME_UNIT, DURATION, positive=True)
    tau = _checked(
        time_constant, TIME_UNIT, POLARIZATION_TIME_CONSTANT, positive=True
    )
    if checked_duration is None or tau is None:
        return None
    return _fraction(
        checked_duration.magnitude_in(TIME_UNIT), tau.magnitude_in(TIME_UNIT)
    )


def polarization_unmodelled_fraction(
    *,
    duration: Quantity | None,
    time_constant: Quantity | None,
) -> Quantity | None:
    """min(f, 1 - f) for f = 1 - exp(-t/tau_pol) — the part still in motion.

    **Definition.** ``f`` is the fraction of the diffusion overpotential that
    has developed by the end of the interval; a first-order relaxation reaches
    ``1 - exp(-t/tau)`` after a current step. This quantity is the smaller of
    ``f`` and ``1 - f``, and it is small at *both* ends of the transition.

    **Why the fold, and what each half means.** The Rint circuit represents
    the whole overpotential as one instantaneous ohmic drop with no dynamics.
    Two regimes let a constant resistance stand in for that:

    * **Settled** (``f`` near 1, i.e. ``t`` many tau). The RC branch has
      finished moving and contributes a constant ``I R_diff``, which an
      effective ``R_int`` measured over a comparable interval already
      contains. Here ``1 - f`` — the part still to come — is the leftover.
    * **Undeveloped** (``f`` near 0, i.e. ``t`` a small fraction of tau). The
      branch has barely begun, and the terminal voltage is essentially the
      instantaneous ohmic drop that a short-pulse ``R_int`` represents. Here
      ``f`` itself — the part that has appeared and is in no constant
      resistance — is the leftover.

    In both cases the leftover is ``min(f, 1 - f)``, so one ceiling on it
    states both regimes. **The excluded region is the middle**: around
    ``t ~ tau`` the branch is slewing through the interval and no constant
    resistance reproduces the terminal voltage. That is the band this
    condition removes, and the previous floor on ``t/tau`` removed the whole
    short-pulse regime with it.

    See :data:`~engcore.domains.battery.models.POLARIZATION_UNMODELLED_CEILING`
    for the bound, which is a **convention** and is recorded as one. UNKNOWN
    unless the caller declares a polarization time constant.
    """
    checked_duration = _checked(duration, TIME_UNIT, DURATION, positive=True)
    tau = _checked(
        time_constant, TIME_UNIT, POLARIZATION_TIME_CONSTANT, positive=True
    )
    if checked_duration is None or tau is None:
        return None
    developed = 1.0 - math.exp(
        -checked_duration.magnitude_in(TIME_UNIT) / tau.magnitude_in(TIME_UNIT)
    )
    return Quantity(min(developed, 1.0 - developed), DIMENSIONLESS)


# =====================================================================
# Peukert rate-capacity derating
# =====================================================================

def peukert_effective_capacity(
    *,
    nominal_capacity: Quantity | None,
    current: Quantity | None,
    reference_current: Quantity | None,
    exponent: Quantity | None,
) -> Quantity | None:
    """Q_eff = Q_nom (I_ref / I)^(k-1) — the rate-derated deliverable charge.

    **Definition.** Peukert's law, ``I^k t = constant``, written as a capacity
    referred to the current at which the nominal capacity was measured.
    Peukert, W., "Ueber die Abhaengigkeit der Kapacitaet von der
    Entladestromstaerke bei Bleiakkumulatoren", *Elektrotechnische Zeitschrift*
    20 (1897), 287-288. With ``Q = I t`` the original form rearranges to
    ``Q(I) = Q(I_ref) (I_ref/I)^(k-1)``, which is the expression above; at
    ``k = 1`` it is the rate-independent ideal.

    **This is a separate model, not a correction to coulomb counting.** It is
    kept as its own record with its own validity domain because a caller may
    reasonably accept the coulomb-counting claim and reject this one — the
    exponent is a fit, not a derivation, and Doerffel & Sharkh, "A critical
    review of using the Peukert equation for determining the remaining capacity
    of lead-acid and lithium-ion batteries", *J. Power Sources* 155 (2006),
    395-400, show it is not even a constant for one cell. Bolting it onto the
    counter as a correction would make the two inseparable.

    Returns ``None`` unless all four are available.
    """
    capacity = _checked(
        nominal_capacity, CAPACITY_UNIT, NOMINAL_CAPACITY, positive=True
    )
    checked_current = _checked(
        current, CURRENT_UNIT, DISCHARGE_CURRENT, positive=True
    )
    reference = _checked(
        reference_current, CURRENT_UNIT, PEUKERT_REFERENCE_CURRENT, positive=True
    )
    checked_exponent = _checked(
        exponent, DIMENSIONLESS, PEUKERT_EXPONENT, positive=True
    )
    if (
        capacity is None
        or checked_current is None
        or reference is None
        or checked_exponent is None
    ):
        return None
    ratio = reference.magnitude_in(CURRENT_UNIT) / checked_current.magnitude_in(
        CURRENT_UNIT
    )
    k = checked_exponent.magnitude_in(DIMENSIONLESS)
    return Quantity(
        capacity.magnitude_in(CAPACITY_UNIT) * ratio ** (k - 1.0), CAPACITY_UNIT
    )


def peukert_capacity_ratio(
    *,
    effective_capacity: Quantity | None,
    nominal_capacity: Quantity | None,
) -> Quantity | None:
    """Q_eff / Q_nom — the derating, which may reduce and never raise.

    **Definition.** The Peukert-derated capacity as a fraction of the nominal
    one. Below 1 at currents above the reference, which is the rate-capacity
    effect the law describes; above 1 at currents *below* the reference, which
    is the law extrapolated to a place it was not fitted and where it predicts
    a cell delivering more than its rating.

    That is the whole content of the bound: the derating is a reduction. A
    predicted capacity above the rating is not a conservative error, it is the
    formula being read outside the direction it means anything in.
    """
    effective = _checked(
        effective_capacity, CAPACITY_UNIT, "peukert_effective_capacity"
    )
    nominal = _checked(
        nominal_capacity, CAPACITY_UNIT, NOMINAL_CAPACITY, positive=True
    )
    if effective is None or nominal is None:
        return None
    return _fraction(
        effective.magnitude_in(CAPACITY_UNIT),
        nominal.magnitude_in(CAPACITY_UNIT),
    )


def peukert_extrapolation_ratio(
    *,
    current: Quantity | None,
    reference_current: Quantity | None,
    fit_decades: Quantity | None,
) -> Quantity | None:
    """|log10(I / I_ref)| / declared decades — how far outside the fit we are.

    **Definition.** The distance of the operating current from the current the
    exponent was fitted at, measured in decades, over the number of decades the
    caller declares the fit covers.

    **Why the exponent has a range of validity at all.** Doerffel & Sharkh, "A
    critical review of using the Peukert equation for determining the remaining
    capacity of lead-acid and lithium-ion batteries", *Journal of Power
    Sources* 155 (2006), 395-400, show that the Peukert exponent extracted from
    a cell is not a constant of the cell: it varies with the discharge current
    over which it is measured, and with temperature. The law is therefore an
    interpolation over the currents it was fitted across, and using it far
    outside them is extrapolating a fit whose own parameter has moved.

    **Decades rather than a ratio**, because the law is a power law: it is
    linear in ``log I``, so a fit's reach is naturally symmetric in decades and
    not in amperes. UNKNOWN unless the reference current and the declared reach
    are both supplied.
    """
    checked_current = _checked(
        current, CURRENT_UNIT, DISCHARGE_CURRENT, positive=True
    )
    reference = _checked(
        reference_current, CURRENT_UNIT, PEUKERT_REFERENCE_CURRENT, positive=True
    )
    decades = _checked(
        fit_decades, DIMENSIONLESS, PEUKERT_FIT_DECADES, positive=True
    )
    if checked_current is None or reference is None or decades is None:
        return None
    return _fraction(
        abs(
            math.log10(
                checked_current.magnitude_in(CURRENT_UNIT)
                / reference.magnitude_in(CURRENT_UNIT)
            )
        ),
        decades.magnitude_in(DIMENSIONLESS),
    )


def peukert_temperature_drift_ratio(
    *,
    temperature: Quantity | None,
    reference_temperature: Quantity | None,
    span: Quantity | None,
) -> Quantity | None:
    """|T - T_k,ref| / declared span — is the fitted exponent still the exponent?

    **Definition.** The operating excursion from the temperature at which the
    Peukert exponent was fitted, over the half-width the caller declares one
    exponent carries.

    Doerffel & Sharkh (2006), *J. Power Sources* 155, 395-400, name temperature
    alongside current as a variable the extracted exponent depends on, which is
    the substance of their objection to using the equation as a general
    remaining-capacity model. A fit taken at one temperature is a claim about
    that temperature, and this condition is where that is said. Distinct from
    the capacity and resistance drift conditions: a different fitted object,
    with its own reference and its own declared reach.
    """
    return _temperature_drift_ratio(
        temperature,
        reference_temperature,
        span,
        reference_label=PEUKERT_REFERENCE_TEMPERATURE,
        span_label=PEUKERT_TEMPERATURE_SPAN,
    )


# =====================================================================
# Assembly
# =====================================================================

#: Every name this module assembles, and which a caller parameter may therefore
#: never occupy. See ``engcore.domains.derived_context`` for what reserving a
#: name means and why it is enforced at assembly rather than at problem
#: construction.
#:
#: It is the derived groups **and** the state coordinates the assembler
#: injects, because the two are in the same position: a condition reads either
#: one by name, and either one is absent when the assembler could not supply
#: it. Reserving only the derived groups would leave the state coordinates
#: forgeable in exactly the same way — the three here are what every
#: temperature-, current- and charge-dependent group is computed from, so a
#: caller parameter of one of those names would decide a whole family of
#: conditions at once.
ASSEMBLED_QUANTITIES = frozenset(
    {
        STATE_OF_CHARGE,
        DISCHARGE_CURRENT,
        CELL_TEMPERATURE,
        C_RATE,
        CONTINUOUS_C_RATE_UTILIZATION,
        PULSE_C_RATE_UTILIZATION,
        PULSE_DURATION_UTILIZATION,
        FINAL_STATE_OF_CHARGE,
        SOC_WINDOW_MARGIN,
        DISCHARGE_TEMPERATURE_POSITION,
        INTERNAL_RESISTANCE_DRIFT_RATIO,
        SELF_HEATING_RISE,
        SELF_HEATING_RISE_RATIO,
        POLARIZATION_SETTLING_RATIO,
        POLARIZATION_UNMODELLED_FRACTION,
        TERMINAL_VOLTAGE_RATIO,
        SOC_STEP_RESOLUTION_RATIO,
        CAPACITY_TEMPERATURE_DRIFT_RATIO,
        CUTOFF_CONSISTENCY_MARGIN,
        CUTOFF_REACHABILITY_MARGIN,
        PEUKERT_EXTRAPOLATION_RATIO,
        PEUKERT_CAPACITY_RATIO,
        PEUKERT_TEMPERATURE_DRIFT_RATIO,
    }
)


def derived_cell_quantities(
    base: Mapping[str, Any],
    *,
    state_of_charge: Quantity | None = None,
    discharge_current: Quantity | None = None,
    cell_temperature: Quantity | None = None,
    elapsed_time_under_load: Quantity | None = None,
    open_circuit_voltage_curve: DeclaredCurve | None = None,
) -> dict[str, Quantity]:
    """Every quantity a validity condition in this domain is stated over.

    ``base`` is a problem's parameter-derived context: the cell's five required
    parameters, the load's duration and whichever optional declarations the
    caller supplied. The three keyword arguments are the *state and controls* —
    a state of charge, a discharge current and a cell temperature are variables,
    not parameters, so the core's parameter-built context structurally cannot
    reach them and they must be handed in explicitly. That is the same
    limitation the sibling electrical and thermal domains record, met again and
    not worked around.

    **Every input to every group here is a Quantity**, and every one either
    travels as a problem parameter or is a declared state value. No categorical
    declaration reaches this function: ``chemistry``, ``cooling_mode`` and
    ``duty_type`` are not read here and are not emitted as parameters, so
    nothing that decides a verdict is invisible to ``ProvenanceRecord``, which
    admits only Quantity-valued inputs.

    **A key that could not be derived is absent from the result.** It is never
    present with a placeholder, a zero or a typical value, so a condition that
    depends on it reaches ``ValidityDomain.assess`` as UNKNOWN. There is no
    path through this function by which omitting an input yields IN_DOMAIN.
    """
    capacity = base.get(NOMINAL_CAPACITY)
    resistance = base.get(INTERNAL_RESISTANCE)
    ocv_empty = base.get(OCV_AT_EMPTY)
    ocv_full = base.get(OCV_AT_FULL)
    duration = base.get(DURATION)
    polarization_duration = (
        duration if elapsed_time_under_load is None else elapsed_time_under_load
    )

    rate = c_rate(current=discharge_current, nominal_capacity=capacity)
    final_soc = final_state_of_charge(
        initial_state_of_charge=state_of_charge,
        current=discharge_current,
        duration=duration,
        coulombic_efficiency=base.get(COULOMBIC_EFFICIENCY),
        nominal_capacity=capacity,
    )
    # The worst point of a monotone discharge is its end, so the terminal
    # voltage admissibility is evaluated there and nowhere else.
    worst_ocv = open_circuit_voltage(
        state_of_charge=final_soc,
        ocv_at_empty=ocv_empty,
        ocv_at_full=ocv_full,
        curve=open_circuit_voltage_curve,
    )
    worst_terminal = terminal_voltage(
        open_circuit=worst_ocv,
        current=discharge_current,
        internal_resistance=resistance,
    )
    heat = heat_generation(
        current=discharge_current, internal_resistance=resistance
    )
    rise = self_heating_rise(
        heat=heat, thermal_conductance=base.get(CELL_THERMAL_CONDUCTANCE)
    )
    effective_capacity = peukert_effective_capacity(
        nominal_capacity=capacity,
        current=discharge_current,
        reference_current=base.get(PEUKERT_REFERENCE_CURRENT),
        exponent=base.get(PEUKERT_EXPONENT),
    )

    derived: dict[str, Quantity | None] = {
        C_RATE: rate,
        FINAL_STATE_OF_CHARGE: final_soc,
        SELF_HEATING_RISE: rise,
        CONTINUOUS_C_RATE_UTILIZATION: continuous_c_rate_utilization(
            rate=rate, rating=base.get(CONTINUOUS_DISCHARGE_C_RATE)
        ),
        PULSE_C_RATE_UTILIZATION: pulse_c_rate_utilization(
            pulse_current=base.get(PULSE_CURRENT),
            nominal_capacity=capacity,
            rating=base.get(PULSE_DISCHARGE_C_RATE),
        ),
        PULSE_DURATION_UTILIZATION: pulse_duration_utilization(
            pulse_duration=base.get(PULSE_DURATION),
            rated_duration=base.get(RATED_PULSE_DURATION),
        ),
        SOC_WINDOW_MARGIN: soc_window_margin(
            initial_state_of_charge=state_of_charge,
            final_soc=final_soc,
            window_minimum=base.get(USABLE_SOC_MINIMUM),
            window_maximum=base.get(USABLE_SOC_MAXIMUM),
        ),
        SOC_STEP_RESOLUTION_RATIO: soc_step_resolution_ratio(
            initial_state_of_charge=state_of_charge,
            final_soc=final_soc,
            resolution=base.get(SOC_STEP_RESOLUTION),
        ),
        TERMINAL_VOLTAGE_RATIO: terminal_voltage_ratio(
            terminal=worst_terminal, open_circuit=worst_ocv
        ),
        CUTOFF_CONSISTENCY_MARGIN: cutoff_consistency_margin(
            cutoff_state_of_charge=base.get(CUTOFF_STATE_OF_CHARGE),
            voltage_cutoff_soc=voltage_cutoff_state_of_charge(
                cutoff_voltage=base.get(CUTOFF_VOLTAGE),
                current=discharge_current,
                internal_resistance=resistance,
                ocv_at_empty=ocv_empty,
                ocv_at_full=ocv_full,
            ),
        ),
        CUTOFF_REACHABILITY_MARGIN: cutoff_reachability_margin(
            state_of_charge=state_of_charge,
            cutoff_state_of_charge=base.get(CUTOFF_STATE_OF_CHARGE),
            voltage_cutoff_soc=voltage_cutoff_state_of_charge(
                cutoff_voltage=base.get(CUTOFF_VOLTAGE),
                current=discharge_current,
                internal_resistance=resistance,
                ocv_at_empty=ocv_empty,
                ocv_at_full=ocv_full,
            ),
        ),
        SELF_HEATING_RISE_RATIO: self_heating_rise_ratio(
            rise=rise, bound=base.get(SELF_HEATING_RISE_BOUND)
        ),
        DISCHARGE_TEMPERATURE_POSITION: discharge_temperature_position(
            temperature=cell_temperature,
            minimum=base.get(MINIMUM_DISCHARGE_TEMPERATURE),
            maximum=base.get(MAXIMUM_DISCHARGE_TEMPERATURE),
        ),
        INTERNAL_RESISTANCE_DRIFT_RATIO: internal_resistance_drift_ratio(
            temperature=cell_temperature,
            reference_temperature=base.get(RESISTANCE_REFERENCE_TEMPERATURE),
            span=base.get(RESISTANCE_TEMPERATURE_SPAN),
        ),
        CAPACITY_TEMPERATURE_DRIFT_RATIO: capacity_temperature_drift_ratio(
            temperature=cell_temperature,
            reference_temperature=base.get(CAPACITY_REFERENCE_TEMPERATURE),
            span=base.get(CAPACITY_TEMPERATURE_SPAN),
        ),
        POLARIZATION_SETTLING_RATIO: polarization_settling_ratio(
            duration=polarization_duration,
            time_constant=base.get(POLARIZATION_TIME_CONSTANT),
        ),
        POLARIZATION_UNMODELLED_FRACTION: polarization_unmodelled_fraction(
            duration=polarization_duration,
            time_constant=base.get(POLARIZATION_TIME_CONSTANT),
        ),
        PEUKERT_CAPACITY_RATIO: peukert_capacity_ratio(
            effective_capacity=effective_capacity, nominal_capacity=capacity
        ),
        PEUKERT_EXTRAPOLATION_RATIO: peukert_extrapolation_ratio(
            current=discharge_current,
            reference_current=base.get(PEUKERT_REFERENCE_CURRENT),
            fit_decades=base.get(PEUKERT_FIT_DECADES),
        ),
        PEUKERT_TEMPERATURE_DRIFT_RATIO: peukert_temperature_drift_ratio(
            temperature=cell_temperature,
            reference_temperature=base.get(PEUKERT_REFERENCE_TEMPERATURE),
            span=base.get(PEUKERT_TEMPERATURE_SPAN),
        ),
    }
    return {name: value for name, value in derived.items() if value is not None}
