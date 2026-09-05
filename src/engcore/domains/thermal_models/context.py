"""Computed validity context for the lumped thermal models.

Why this module exists
----------------------
``ScientificProblem.validity_context`` is built from **typed parameters**. A
dimensionless group is not a parameter: nobody declares a Biot number, they
declare a conductivity and a size and the number *follows*. The core provides
exactly one sanctioned way to close that gap — ``validity_context(extra=...)``,
whose docstring names "a Reynolds number, a detected regime" as the intended
content — and this module is the thermal domain's supplier of that ``extra``.

Nothing here is registered with, imported by, or known to
``engcore.scientific``. The core knows ranges, categories and flags; it does
not know what a Biot number is, and after this module it still does not.

Three rules the functions below all obey
----------------------------------------
1. **A missing input omits its key.** Every function returns ``None`` when it
   was not given what it needs, and :func:`derived_lumped_quantities` drops
   the key rather than inventing a value. A dropped key reaches
   ``ValidityDomain.assess`` as ``UNKNOWN``, which is the honest verdict:
   absence of information is not evidence of validity. No function in this
   module has a physical default.
2. **Every derivation is unit-checked.** Inputs are converted through
   :class:`Quantity` (``to``/``magnitude_in``), so a conductivity handed in as
   ``W/(m·K)`` and one handed in as ``W/(cm·K)`` produce the same number and a
   conductance handed in where a conductivity belongs raises instead of
   producing a plausible-looking wrong answer.
3. **Pure.** No state, no registry, no I/O, no mutation of an argument.

Sources
-------
Dimensionless-group definitions and the lumped-capacitance criterion follow
Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass Transfer*,
6th ed. (Wiley, 2007), Chapter 5. Section and equation numbers are cited on
each function. The Stefan-Boltzmann constant is the SI defining value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string
from ...scientific.units.quantity import Quantity

__all__ = [
    "APPLICABILITY_DECLARATION_SCHEMA",
    "BIOT_NUMBER",
    "BODY_CONDUCTIVITY",
    "BODY_VOLUME",
    "CAPACITY_EXCURSION_BOUND",
    "CAPACITY_EXCURSION_RATIO",
    "CHARACTERISTIC_LENGTH",
    "CONDUCTANCE_EXCURSION_BOUND",
    "CONDUCTANCE_EXCURSION_RATIO",
    "CONDUCTIVITY_UNIT",
    "CONVECTION_REGIME",
    "CONVECTION_REGIME_VOCABULARY",
    "COEFFICIENT_UNIT",
    "DIMENSIONLESS",
    "FORCED_CONVECTION",
    "INTERNAL_FOURIER_NUMBER",
    "LENGTH_UNIT",
    "MELTING_TEMPERATURE",
    "MELTING_TEMPERATURE_UTILIZATION",
    "NATURAL_CONVECTION",
    "RADIATION_TO_CONVECTION_RATIO",
    "STEFAN_BOLTZMANN",
    "SURFACE_AREA",
    "SURFACE_AREA_UNIT",
    "SURFACE_EMISSIVITY",
    "TRANSIENT_HORIZON_RATIO",
    "VOLUME_UNIT",
    "LumpedApplicabilityDeclaration",
    "biot_number",
    "capacity_excursion_ratio",
    "characteristic_length",
    "conductance_excursion_ratio",
    "derived_lumped_quantities",
    "internal_fourier_number",
    "linearized_radiation_coefficient",
    "melting_temperature_utilization",
    "peak_body_temperature",
    "radiation_to_convection_ratio",
    "steady_state_temperature",
    "surface_coefficient",
    "surface_temperature_excursion",
    "thermal_time_constant",
    "transient_horizon_ratio",
]

APPLICABILITY_DECLARATION_SCHEMA = schema_string("lumped_applicability_declaration")

# --- units -------------------------------------------------------------------
TEMPERATURE_UNIT = "kelvin"
POWER_UNIT = "watt"
CAPACITY_UNIT = "joule/kelvin"
CONDUCTANCE_UNIT = "watt/kelvin"
TIME_UNIT = "second"
LENGTH_UNIT = "meter"
SURFACE_AREA_UNIT = "meter**2"
VOLUME_UNIT = "meter**3"
CONDUCTIVITY_UNIT = "watt/meter/kelvin"
COEFFICIENT_UNIT = "watt/meter**2/kelvin"
DIMENSIONLESS = "dimensionless"

# --- names of the optional facts a caller may declare ------------------------
# Names, not conventions. Each is enumerated by the model record as an optional
# ``ModelInputSpec`` and emitted by the problem builder as a parameter, so a
# reader holding only the records can see which declaration unlocks which
# condition.
CHARACTERISTIC_LENGTH = "characteristic_length"
BODY_VOLUME = "body_volume"
SURFACE_AREA = "surface_area"
BODY_CONDUCTIVITY = "body_conductivity"
SURFACE_EMISSIVITY = "surface_emissivity"
CONVECTION_REGIME = "convection_regime"
CONDUCTANCE_EXCURSION_BOUND = "conductance_excursion_bound"
CAPACITY_EXCURSION_BOUND = "capacity_excursion_bound"
MELTING_TEMPERATURE = "melting_temperature"

# --- names of the quantities this module derives ------------------------------
BIOT_NUMBER = "biot_number"
TRANSIENT_HORIZON_RATIO = "transient_horizon_ratio"
INTERNAL_FOURIER_NUMBER = "internal_fourier_number"
CONDUCTANCE_EXCURSION_RATIO = "conductance_excursion_ratio"
CAPACITY_EXCURSION_RATIO = "capacity_excursion_ratio"
RADIATION_TO_CONVECTION_RATIO = "radiation_to_convection_ratio"
MELTING_TEMPERATURE_UTILIZATION = "melting_temperature_utilization"

# --- convection regimes -------------------------------------------------------
#: The caller states which mechanism sets the surface coefficient. This is a
#: *declaration*, never an inference: no correlation is evaluated anywhere in
#: this module and no regime is detected from the numbers.
NATURAL_CONVECTION = "natural"
FORCED_CONVECTION = "forced"
CONVECTION_REGIME_VOCABULARY = (NATURAL_CONVECTION, FORCED_CONVECTION)

#: Stefan-Boltzmann constant, exact in the SI as redefined in 2019: it follows
#: from the defining values of h, k_B and c. BIPM, *The International System of
#: Units (SI)*, 9th ed. (2019), §2.3.1. Also Incropera & DeWitt 6th ed.,
#: Eq. 1.5, which quotes 5.67e-8 W/(m^2 K^4).
STEFAN_BOLTZMANN = Quantity(5.670374419e-8, "watt/meter**2/kelvin**4")


def _as_quantity(value: Any, unit: str, label: str) -> Quantity | None:
    """A supplied value, checked against ``unit``; ``None`` stays ``None``.

    A non-``Quantity`` that is not ``None`` is a specification error rather
    than missing data, and is refused instead of being silently skipped: the
    two cases must not collapse, because one means UNKNOWN and the other means
    the caller declared something wrong.
    """
    if value is None:
        return None
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"{label} must be a Quantity carrying {unit!r}, got "
            f"{type(value).__name__} — a bare number is not a declaration"
        )
    value.require_compatible(unit, context=label)
    return value


def _require_span_scale(value: Quantity | None, label: str) -> Quantity | None:
    """Refuse an affine temperature scale where a *difference* is meant.

    ``conductance_excursion_bound`` and ``capacity_excursion_bound`` are spans,
    not states. A caller who writes ``Quantity(10.0, "degC")`` meaning "ten
    degrees of span" has declared 283.15 K, and every ratio built on it is
    wrong by a factor of thirty with no dimension check able to notice — the
    exact failure mode this whole module exists to prevent, one level down.

    The test is the published-contract one the electrothermal pack already uses
    for its coupling comparison unit: does zero of this unit convert to zero
    kelvin? ``kelvin``, ``rankine`` and ``delta_degC`` pass; ``degC`` and
    ``degF`` do not. No units-backend call is made here.
    """
    if value is None:
        return None
    if Quantity(0.0, value.units).magnitude_in(TEMPERATURE_UNIT) != 0.0:
        raise InvalidScientificProblem(
            f"{label} is a temperature *span* and may not use "
            f"{value.units!r}: its zero is conventional, so a difference "
            f"expressed in it is not a value of that unit. Use kelvin, or a "
            f"delta scale such as 'delta_degC'"
        )
    return value


def _positive(value: Quantity | None, unit: str, label: str) -> Quantity | None:
    """``value`` when it is strictly positive; refuses zero and negatives.

    Every quantity this module divides by is a size, an area, a conductivity or
    a conductance. Zero is not a small value there, it is a different physical
    situation (no surface, no conduction path), and dividing by it to obtain a
    dimensionless group would report infinity as though it were a measurement.
    """
    if value is None:
        return None
    if value.magnitude_in(unit) <= 0.0:
        raise InvalidScientificProblem(
            f"{label} must be strictly positive, got {value}"
        )
    return value


@dataclass(frozen=True)
class LumpedApplicabilityDeclaration:
    """The optional facts that let a lumped body's applicability be judged.

    Every field is optional and every field defaults to ``None``, which means
    *not declared* and never *zero* or *typical*. A field left out removes the
    conditions that depend on it from IN_DOMAIN reach: they become UNKNOWN.
    That asymmetry is the point — supplying more information can only ever move
    a verdict away from UNKNOWN, and never turns a violated condition into a
    satisfied one.

    Kept as a separate record rather than as nine more fields on
    :class:`~engcore.domains.thermal_models.lumped.ThermalBody` because these
    are *evidence about the modelling assumptions*, not the two properties
    (``C`` and ``hA``) that make a body that body. A body declared with a
    conductivity and one declared without are the same physical body known to
    different depth, and ``ThermalBody.physical_key`` must keep saying so.

    **Eight of the nine fields are Quantities that feed a derivation.**
    ``convection_regime`` is the exception and is deliberately inert: it is
    validated against :data:`CONVECTION_REGIME_VOCABULARY`, serialized with the
    rest of the record, and read by nothing. It records *why* the caller
    believes their ``conductance_excursion_bound`` is credible; it never
    substitutes for that bound, and no condition consults it. See
    :func:`conductance_excursion_ratio` for the history of that separation.
    """

    characteristic_length: Quantity | None = None
    volume: Quantity | None = None
    surface_area: Quantity | None = None
    body_conductivity: Quantity | None = None
    surface_emissivity: Quantity | None = None
    convection_regime: str | None = None
    conductance_excursion_bound: Quantity | None = None
    capacity_excursion_bound: Quantity | None = None
    melting_temperature: Quantity | None = None

    def __post_init__(self) -> None:
        for label, unit, positive in (
            ("characteristic_length", LENGTH_UNIT, True),
            ("volume", VOLUME_UNIT, True),
            ("surface_area", SURFACE_AREA_UNIT, True),
            ("body_conductivity", CONDUCTIVITY_UNIT, True),
            ("surface_emissivity", DIMENSIONLESS, False),
            ("conductance_excursion_bound", TEMPERATURE_UNIT, True),
            ("capacity_excursion_bound", TEMPERATURE_UNIT, True),
            ("melting_temperature", TEMPERATURE_UNIT, True),
        ):
            checked = _as_quantity(getattr(self, label), unit, label)
            if positive:
                _positive(checked, unit, label)
            if label.endswith("_excursion_bound"):
                _require_span_scale(checked, label)
            object.__setattr__(self, label, checked)

        # Emissivity is a fraction of the black-body emissive power, so it is
        # bounded by construction rather than by convention (Incropera & DeWitt
        # 6th ed., Eq. 12.37). A value outside [0, 1] is not an extreme case,
        # it is not an emissivity.
        if self.surface_emissivity is not None:
            epsilon = self.surface_emissivity.magnitude_in(DIMENSIONLESS)
            if not 0.0 <= epsilon <= 1.0:
                raise InvalidScientificProblem(
                    f"surface_emissivity must lie in [0, 1], got {epsilon!r}"
                )

        if self.convection_regime is not None:
            regime = str(self.convection_regime).strip()
            if regime not in CONVECTION_REGIME_VOCABULARY:
                raise InvalidScientificProblem(
                    f"convection_regime must be one of "
                    f"{list(CONVECTION_REGIME_VOCABULARY)}, got {regime!r}"
                )
            object.__setattr__(self, "convection_regime", regime)

    @property
    def is_empty(self) -> bool:
        """True when nothing was declared — every condition here is UNKNOWN."""
        return all(
            getattr(self, field) is None
            for field in (
                "characteristic_length",
                "volume",
                "surface_area",
                "body_conductivity",
                "surface_emissivity",
                "convection_regime",
                "conductance_excursion_bound",
                "capacity_excursion_bound",
                "melting_temperature",
            )
        )

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Quantity | None) -> dict[str, Any] | None:
            return value.to_dict() if value is not None else None

        return {
            "schema": APPLICABILITY_DECLARATION_SCHEMA,
            "characteristic_length": encode(self.characteristic_length),
            "volume": encode(self.volume),
            "surface_area": encode(self.surface_area),
            "body_conductivity": encode(self.body_conductivity),
            "surface_emissivity": encode(self.surface_emissivity),
            "convection_regime": self.convection_regime,
            "conductance_excursion_bound": encode(self.conductance_excursion_bound),
            "capacity_excursion_bound": encode(self.capacity_excursion_bound),
            "melting_temperature": encode(self.melting_temperature),
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "LumpedApplicabilityDeclaration":
        require_schema(payload, APPLICABILITY_DECLARATION_SCHEMA)

        def decode(key: str) -> Quantity | None:
            raw = payload.get(key)
            return Quantity.from_dict(raw) if raw else None

        return cls(
            characteristic_length=decode("characteristic_length"),
            volume=decode("volume"),
            surface_area=decode("surface_area"),
            body_conductivity=decode("body_conductivity"),
            surface_emissivity=decode("surface_emissivity"),
            convection_regime=payload.get("convection_regime"),
            conductance_excursion_bound=decode("conductance_excursion_bound"),
            capacity_excursion_bound=decode("capacity_excursion_bound"),
            melting_temperature=decode("melting_temperature"),
        )


# =====================================================================
# Geometry and the surface coefficient
# =====================================================================

def characteristic_length(
    *,
    declared: Quantity | None = None,
    volume: Quantity | None = None,
    surface_area: Quantity | None = None,
) -> Quantity | None:
    """L_c — the lumped body's characteristic length.

    **Definition.** ``L_c = V / A_s``, the ratio of the body's volume to the
    surface area across which it exchanges with the ambient. Incropera,
    DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass Transfer*, 6th ed.
    (2007), §5.1, immediately preceding Eq. 5.10.

    A directly ``declared`` value wins, because a caller who knows the body is
    a slab of thickness ``2L`` conducting from both faces knows that the
    conservative length is ``L`` rather than ``V/A_s``, and the text
    (§5.1) says exactly that. Returns ``None`` when neither route is available.
    """
    if declared is not None:
        return _positive(
            _as_quantity(declared, LENGTH_UNIT, CHARACTERISTIC_LENGTH),
            LENGTH_UNIT,
            CHARACTERISTIC_LENGTH,
        )
    checked_volume = _positive(
        _as_quantity(volume, VOLUME_UNIT, BODY_VOLUME), VOLUME_UNIT, BODY_VOLUME
    )
    checked_area = _positive(
        _as_quantity(surface_area, SURFACE_AREA_UNIT, SURFACE_AREA),
        SURFACE_AREA_UNIT,
        SURFACE_AREA,
    )
    if checked_volume is None or checked_area is None:
        return None
    return (checked_volume / checked_area).to(LENGTH_UNIT)


def surface_coefficient(
    *,
    ambient_conductance: Quantity | None,
    surface_area: Quantity | None,
) -> Quantity | None:
    """h — the convection coefficient, split out of the declared ``hA``.

    **Definition.** ``h = (hA) / A_s``. The lumped model declares only the
    *product* ``hA`` in W/K, because the product is all its own balance needs
    (Incropera 6th ed., Eq. 5.2). Every group below that involves ``h`` alone —
    the Biot number and the radiation comparison — therefore cannot be formed
    without the area, and returns ``None`` when it is absent. That is a real
    limitation of the declaration, not a gap to paper over with an assumed
    area.
    """
    conductance = _positive(
        _as_quantity(ambient_conductance, CONDUCTANCE_UNIT, "ambient_conductance"),
        CONDUCTANCE_UNIT,
        "ambient_conductance",
    )
    area = _positive(
        _as_quantity(surface_area, SURFACE_AREA_UNIT, SURFACE_AREA),
        SURFACE_AREA_UNIT,
        SURFACE_AREA,
    )
    if conductance is None or area is None:
        return None
    return (conductance / area).to(COEFFICIENT_UNIT)


def biot_number(
    *,
    coefficient: Quantity | None,
    length: Quantity | None,
    conductivity: Quantity | None,
) -> Quantity | None:
    """Bi = h L_c / k — internal conduction resistance over surface exchange.

    **Definition.** ``Bi = h L_c / k``, with ``k`` the conductivity of the body
    itself, not of the surrounding fluid. Incropera, DeWitt, Bergman & Lavine,
    *Fundamentals of Heat and Mass Transfer*, 6th ed. (2007), §5.1, Eq. 5.10.

    **What it means for this model.** Bi is the ratio of the temperature drop
    *inside* the body to the drop *across its surface layer*. The lumped model
    asserts the first is zero. Bi is therefore the direct measure of how wrong
    that assertion is, and the only one available without solving a field.

    Returns ``None`` if any of the three is absent.
    """
    checked_coefficient = _positive(
        _as_quantity(coefficient, COEFFICIENT_UNIT, "surface coefficient"),
        COEFFICIENT_UNIT,
        "surface coefficient",
    )
    checked_length = _positive(
        _as_quantity(length, LENGTH_UNIT, CHARACTERISTIC_LENGTH),
        LENGTH_UNIT,
        CHARACTERISTIC_LENGTH,
    )
    checked_conductivity = _positive(
        _as_quantity(conductivity, CONDUCTIVITY_UNIT, BODY_CONDUCTIVITY),
        CONDUCTIVITY_UNIT,
        BODY_CONDUCTIVITY,
    )
    if (
        checked_coefficient is None
        or checked_length is None
        or checked_conductivity is None
    ):
        return None
    return (
        checked_coefficient * checked_length / checked_conductivity
    ).to(DIMENSIONLESS)


# =====================================================================
# Time scales
# =====================================================================

def thermal_time_constant(
    *,
    heat_capacity: Quantity | None,
    ambient_conductance: Quantity | None,
) -> Quantity | None:
    """tau = C / hA — the lumped first-order time constant.

    **Definition.** ``tau_t = R_t C_t = (1 / h A_s) (rho V c) = C / (hA)``.
    Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), §5.1, Eq. 5.7.

    This restates what ``ThermalBody.time_constant_s`` already computes, in
    :class:`Quantity` form and without needing a body: the applicability
    context is derived from a *problem*, which may have been serialized,
    transported and rebuilt with no declaration object left anywhere.
    """
    capacity = _positive(
        _as_quantity(heat_capacity, CAPACITY_UNIT, "heat_capacity"),
        CAPACITY_UNIT,
        "heat_capacity",
    )
    conductance = _positive(
        _as_quantity(ambient_conductance, CONDUCTANCE_UNIT, "ambient_conductance"),
        CONDUCTANCE_UNIT,
        "ambient_conductance",
    )
    if capacity is None or conductance is None:
        return None
    return (capacity / conductance).to(TIME_UNIT)


def transient_horizon_ratio(
    *,
    duration: Quantity | None,
    time_constant: Quantity | None,
) -> Quantity | None:
    """t / tau — the requested horizon measured in time constants.

    **Definition.** ``t / tau_t``, the exponent of the closed-form solution
    ``theta / theta_i = exp(-t / tau_t)``. Incropera, DeWitt, Bergman & Lavine,
    6th ed. (2007), §5.1, Eq. 5.6.

    **Why no bound is placed on this number directly.** The realization
    integrates the linear balance *exactly*, so a long horizon introduces no
    error of its own and there is no upper bound to state; the long-horizon
    limitation is the constant-property one, and it is measured by
    :func:`conductance_excursion_ratio` and :func:`capacity_excursion_ratio`
    instead. The short-horizon limitation is real but is not a statement about
    ``t / tau`` alone — see :func:`internal_fourier_number`, which is what this
    ratio is used to build.
    """
    checked_duration = _positive(
        _as_quantity(duration, TIME_UNIT, "duration"), TIME_UNIT, "duration"
    )
    checked_tau = _positive(
        _as_quantity(time_constant, TIME_UNIT, "time_constant"),
        TIME_UNIT,
        "time_constant",
    )
    if checked_duration is None or checked_tau is None:
        return None
    return (checked_duration / checked_tau).to(DIMENSIONLESS)


def internal_fourier_number(
    *,
    horizon_ratio: Quantity | None,
    biot: Quantity | None,
) -> Quantity | None:
    """Fo = alpha t / L_c^2 — the horizon measured against internal diffusion.

    **Definition and derivation.** The Fourier number is ``Fo = alpha t /
    L_c^2``. Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), §5.2,
    Eq. 5.12, gives the identity that makes it computable here without any
    density or specific heat::

        Bi * Fo = (h L_c / k)(alpha t / L_c^2) = h A_s t / (rho V c) = t / tau

    so ``Fo = (t / tau) / Bi``. Every symbol on the right is already declared
    or already derived, which is why this module needs no separate diffusivity
    input.

    **What it means for this model.** ``Fo`` is the horizon expressed in units
    of the body's own internal diffusion time ``L_c^2 / alpha``. The exact
    series solution for a body cooling by convection has higher modes decaying
    like ``exp(-zeta_n^2 Fo)``; once they have died the body's response *is* a
    single exponential, which is the shape the lumped model computes. That is
    what the threshold on this number checks, and all it checks — see
    :data:`~engcore.domains.thermal_models.lumped.LUMPED_MIN_FOURIER_NUMBER`
    for what a low value does and does not establish. In particular, a small Fo
    does not by itself make a lumped description wrong: at small Bi the higher
    modes carry O(Bi) amplitude as well as decaying, so they may be negligible
    long before they have decayed.

    Returns ``None`` when either input is absent.
    """
    ratio = _as_quantity(horizon_ratio, DIMENSIONLESS, TRANSIENT_HORIZON_RATIO)
    number = _positive(
        _as_quantity(biot, DIMENSIONLESS, BIOT_NUMBER), DIMENSIONLESS, BIOT_NUMBER
    )
    if ratio is None or number is None:
        return None
    return (ratio / number).to(DIMENSIONLESS)


# =====================================================================
# Temperature excursions
# =====================================================================

def steady_state_temperature(
    *,
    ambient_temperature: Quantity | None,
    heat_input: Quantity | None,
    ambient_conductance: Quantity | None,
) -> Quantity | None:
    """T_ss = T_amb + Q / hA — the temperature the body approaches.

    **Definition.** Setting ``dT/dt = 0`` in ``C dT/dt = Q - hA (T - T_amb)``.
    Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), §5.3, Eq. 5.25, gives
    the same particular solution for a lumped body with generation.

    This is the *asymptote*, not the value at the end of the interval. It is
    the right quantity for an applicability question: every condition below
    asks how far the body could travel under the declared operating point, and
    a horizon shorter than the answer does not make the assumption safer, it
    only defers the excursion.
    """
    ambient = _as_quantity(
        ambient_temperature, TEMPERATURE_UNIT, "ambient_temperature"
    )
    power = _as_quantity(heat_input, POWER_UNIT, "heat_input")
    conductance = _positive(
        _as_quantity(ambient_conductance, CONDUCTANCE_UNIT, "ambient_conductance"),
        CONDUCTANCE_UNIT,
        "ambient_conductance",
    )
    if ambient is None or power is None or conductance is None:
        return None
    rise = (power / conductance).to(TEMPERATURE_UNIT)
    return Quantity(
        ambient.magnitude_in(TEMPERATURE_UNIT)
        + rise.magnitude_in(TEMPERATURE_UNIT),
        TEMPERATURE_UNIT,
    )


def peak_body_temperature(
    *,
    initial_temperature: Quantity | None,
    steady_temperature: Quantity | None,
) -> Quantity | None:
    """The hottest temperature the body reaches over the interval.

    **Why a maximum of two endpoints is exact.** With a constant heat input the
    closed form ``T(t) = T_ss + (T_0 - T_ss) exp(-t / tau)`` is monotone in
    ``t``: it approaches ``T_ss`` from ``T_0`` without overshoot, because the
    balance is first-order and linear with a single real pole (Incropera 6th
    ed., §5.1, Eq. 5.6). So the extremes over any interval are the endpoints,
    and ``max(T_0, T_ss)`` bounds the whole trajectory including horizons the
    caller has not yet asked for.
    """
    initial = _as_quantity(
        initial_temperature, TEMPERATURE_UNIT, "initial_temperature"
    )
    steady = _as_quantity(
        steady_temperature, TEMPERATURE_UNIT, "steady_state_temperature"
    )
    if initial is None or steady is None:
        return None
    return Quantity(
        max(
            initial.magnitude_in(TEMPERATURE_UNIT),
            steady.magnitude_in(TEMPERATURE_UNIT),
        ),
        TEMPERATURE_UNIT,
    )


def surface_temperature_excursion(
    *,
    initial_temperature: Quantity | None,
    ambient_temperature: Quantity | None,
    steady_temperature: Quantity | None,
) -> Quantity | None:
    """max |T - T_amb| over the interval — the driving temperature difference.

    **Definition.** ``max(|T_0 - T_amb|, |T_ss - T_amb|)``. Exact for the same
    monotonicity reason as :func:`peak_body_temperature`: the trajectory lies
    between its endpoints, so the largest surface-to-ambient difference is at
    one of them.

    This is the ``Delta T`` that a surface-exchange coefficient is a function
    of, which is why it — and not the body's own temperature span — is what the
    constant-``hA`` condition is measured against.
    """
    initial = _as_quantity(
        initial_temperature, TEMPERATURE_UNIT, "initial_temperature"
    )
    ambient = _as_quantity(
        ambient_temperature, TEMPERATURE_UNIT, "ambient_temperature"
    )
    steady = _as_quantity(
        steady_temperature, TEMPERATURE_UNIT, "steady_state_temperature"
    )
    if initial is None or ambient is None or steady is None:
        return None
    ambient_k = ambient.magnitude_in(TEMPERATURE_UNIT)
    return Quantity(
        max(
            abs(initial.magnitude_in(TEMPERATURE_UNIT) - ambient_k),
            abs(steady.magnitude_in(TEMPERATURE_UNIT) - ambient_k),
        ),
        TEMPERATURE_UNIT,
    )


def conductance_excursion_ratio(
    *,
    excursion: Quantity | None,
    bound: Quantity | None,
) -> Quantity | None:
    """How much of the declared constant-``hA`` budget the run consumes.

    **Definition.** ``Delta T / Delta T_bound``, where ``Delta T`` is
    :func:`surface_temperature_excursion` and ``Delta T_bound`` is the span the
    *caller declares* the coefficient may be treated as constant over. Both are
    required. There is no third argument and no branch: this ratio is formed
    one way or it is not formed at all.

    **Why a caller-supplied bound and not a fixed number.** Under free
    convection the coefficient is itself a function of the driving difference:
    for an external laminar boundary layer ``Nu ~ Ra^(1/4)`` and therefore
    ``h ~ Delta T^(1/4)`` (Incropera, DeWitt, Bergman & Lavine, 6th ed., §9.2,
    Eq. 9.19 ff.). A constant ``hA`` is then an approximation whose error grows
    with the excursion, and how much error is acceptable is a property of the
    study, not of the physics. No correlation is evaluated here and none is
    added in this round.

    **What a declared forced-convection regime buys the caller: nothing here.**

    An earlier version returned ``0.0`` on ``regime == 'forced'`` before reading
    either argument, on the reasoning that a flow-set coefficient has no
    ``Delta T`` dependence for the budget to bound. The reasoning is sound and
    the mechanism was not: it let a caller satisfy this condition by *asserting
    a regime* instead of by supplying evidence, and the assertion was a bare
    string that no part of the record could check and that never reached
    provenance. A validity domain whose strongest term is an unverifiable claim
    by the party being assessed is not a validity domain.

    So the regime no longer enters this computation at all.

    * It does **not** waive the bound. A forced regime with no
      ``conductance_excursion_bound`` yields ``None`` and the condition is
      UNKNOWN, exactly as a natural regime with no bound is.
    * It does **not** waive the operating point. No excursion, no ratio.
    * It does **not** widen the budget. The bound the caller declares is the
      whole budget under either mechanism.
    * It **is** still worth declaring, on
      :class:`LumpedApplicabilityDeclaration`, where it records *why* the
      caller believes the span they declared is credible — a wide span is
      defensible under forced flow and usually is not under free convection.
      That is context for a reader, not an input to a check, and this module
      draws no conclusion from it.
    """
    checked_excursion = _as_quantity(
        excursion, TEMPERATURE_UNIT, "temperature excursion"
    )
    checked_bound = _positive(
        _as_quantity(bound, TEMPERATURE_UNIT, CONDUCTANCE_EXCURSION_BOUND),
        TEMPERATURE_UNIT,
        CONDUCTANCE_EXCURSION_BOUND,
    )
    if checked_excursion is None or checked_bound is None:
        return None
    return Quantity(
        checked_excursion.magnitude_in(TEMPERATURE_UNIT)
        / checked_bound.magnitude_in(TEMPERATURE_UNIT),
        DIMENSIONLESS,
    )


def capacity_excursion_ratio(
    *,
    initial_temperature: Quantity | None,
    steady_temperature: Quantity | None,
    bound: Quantity | None,
) -> Quantity | None:
    """How much of the declared constant-``C`` budget the run consumes.

    **Definition.** ``|T_ss - T_0| / Delta T_bound``. The numerator is the full
    span of body temperature the trajectory can traverse (monotone, so the span
    is the endpoint difference); the denominator is the span the caller
    declares the total heat capacity may be treated as constant over.

    **Why a caller-supplied bound.** ``C = rho V c_p`` and the specific heat of
    a real solid rises with temperature over engineering ranges — an effect the
    Debye model predicts and tabulations show (Incropera, DeWitt, Bergman &
    Lavine, 6th ed., Table A.1, which lists ``c_p`` at several temperatures for
    each solid precisely because one number does not serve). How much drift is
    tolerable is a property of the study. Distinct from the ``hA`` bound: this
    one is about the body, that one about its surface.
    """
    initial = _as_quantity(
        initial_temperature, TEMPERATURE_UNIT, "initial_temperature"
    )
    steady = _as_quantity(
        steady_temperature, TEMPERATURE_UNIT, "steady_state_temperature"
    )
    checked_bound = _positive(
        _as_quantity(bound, TEMPERATURE_UNIT, CAPACITY_EXCURSION_BOUND),
        TEMPERATURE_UNIT,
        CAPACITY_EXCURSION_BOUND,
    )
    if initial is None or steady is None or checked_bound is None:
        return None
    span = abs(
        steady.magnitude_in(TEMPERATURE_UNIT)
        - initial.magnitude_in(TEMPERATURE_UNIT)
    )
    return Quantity(
        span / checked_bound.magnitude_in(TEMPERATURE_UNIT), DIMENSIONLESS
    )


# =====================================================================
# Radiation
# =====================================================================

def linearized_radiation_coefficient(
    *,
    emissivity: Quantity | None,
    surface_temperature: Quantity | None,
    surroundings_temperature: Quantity | None,
) -> Quantity | None:
    """h_r — the radiation exchange written as an equivalent coefficient.

    **Definition.** ``h_r = epsilon sigma (T_s + T_sur)(T_s^2 + T_sur^2)``.
    Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and Mass
    Transfer*, 6th ed. (2007), §1.2.3, Eq. 1.9. It is the exact factorisation
    of ``epsilon sigma (T_s^4 - T_sur^4)`` divided by ``(T_s - T_sur)``, so it
    is not itself an approximation — the approximation is treating it as
    constant, which is not done here: it is re-evaluated at the peak surface
    temperature the run reaches.

    Temperatures must be absolute; they are converted to kelvin before the
    fourth-power algebra, so a Celsius declaration cannot silently produce a
    fourth power of the wrong number.
    """
    checked_emissivity = _as_quantity(
        emissivity, DIMENSIONLESS, SURFACE_EMISSIVITY
    )
    surface = _as_quantity(
        surface_temperature, TEMPERATURE_UNIT, "surface temperature"
    )
    surroundings = _as_quantity(
        surroundings_temperature, TEMPERATURE_UNIT, "surroundings temperature"
    )
    if checked_emissivity is None or surface is None or surroundings is None:
        return None
    surface_k = surface.to(TEMPERATURE_UNIT)
    surroundings_k = surroundings.to(TEMPERATURE_UNIT)
    return (
        STEFAN_BOLTZMANN
        * checked_emissivity.magnitude_in(DIMENSIONLESS)
        * (surface_k + surroundings_k)
        * (surface_k * surface_k + surroundings_k * surroundings_k)
    ).to(COEFFICIENT_UNIT)


def radiation_to_convection_ratio(
    *,
    radiation_coefficient: Quantity | None,
    coefficient: Quantity | None,
) -> Quantity | None:
    """h_r / h — the share of surface exchange the model is throwing away.

    **Definition.** The ratio of the linearized radiation coefficient
    (Eq. 1.9) to the convection coefficient. Incropera, DeWitt, Bergman &
    Lavine, 6th ed. (2007), §1.2.3 notes that the two mechanisms act in
    parallel over the same surface, so their coefficients add and their ratio
    is the fractional error of dropping one.

    The lumped model declares "no radiation" as an assumption. This number is
    that assumption made falsifiable.
    """
    radiation = _as_quantity(
        radiation_coefficient, COEFFICIENT_UNIT, "radiation coefficient"
    )
    convection = _positive(
        _as_quantity(coefficient, COEFFICIENT_UNIT, "surface coefficient"),
        COEFFICIENT_UNIT,
        "surface coefficient",
    )
    if radiation is None or convection is None:
        return None
    return (radiation / convection).to(DIMENSIONLESS)


# =====================================================================
# Material limit
# =====================================================================

def melting_temperature_utilization(
    *,
    peak_temperature: Quantity | None,
    melting_temperature: Quantity | None,
) -> Quantity | None:
    """T_peak / T_melt — how close the run comes to a phase change.

    **Definition.** The ratio of the hottest absolute temperature the body
    reaches to the caller-declared melting (or other phase-change) temperature.
    Both are absolute, so the ratio reaching 1 is exactly the statement
    ``T_peak >= T_melt``.

    **Why the bound is 1 and needs no citation.** This is not a tolerance. The
    lumped balance ``C dT/dt = Q - hA (T - T_amb)`` carries no latent-heat term
    and no second phase, so at a phase change it is not inaccurate, it is
    describing something that is not there. Incropera, DeWitt, Bergman & Lavine,
    6th ed. (2007), §5.1, states the lumped formulation for a single-phase
    solid.
    """
    peak = _as_quantity(peak_temperature, TEMPERATURE_UNIT, "peak temperature")
    melting = _positive(
        _as_quantity(melting_temperature, TEMPERATURE_UNIT, MELTING_TEMPERATURE),
        TEMPERATURE_UNIT,
        MELTING_TEMPERATURE,
    )
    if peak is None or melting is None:
        return None
    return Quantity(
        peak.magnitude_in(TEMPERATURE_UNIT)
        / melting.magnitude_in(TEMPERATURE_UNIT),
        DIMENSIONLESS,
    )


# =====================================================================
# Assembly
# =====================================================================

def derived_lumped_quantities(
    base: Mapping[str, Any],
    *,
    initial_temperature: Quantity | None = None,
    ambient_temperature: Quantity | None = None,
    heat_input: Quantity | None = None,
) -> dict[str, Quantity]:
    """Every dimensionless group derivable from ``base`` and the state.

    ``base`` is a problem's parameter-derived context: the required parameters
    (``heat_capacity``, ``ambient_conductance``, ``duration``) plus whichever
    optional quantity-valued declarations the caller supplied. The three
    keyword arguments are the *state and controls* — a body temperature, an
    ambient and a heat input are variables, not parameters, so the core's
    parameter-built context cannot reach them and they must be handed in. That
    is the same explicit-``extra`` discipline ``assess_resistance_validity``
    already follows.

    **Every input to every group here is a Quantity**, and every one of them
    either travels as a problem parameter or is a declared state value. No
    categorical declaration reaches this function, so nothing that decides a
    verdict is invisible to ``ProvenanceRecord`` — which admits only
    Quantity-valued inputs. The convection regime used to be threaded in here
    and is no longer: see :func:`conductance_excursion_ratio`.

    **A key that could not be derived is absent from the result.** It is never
    present with a placeholder, a zero or a typical value, so a condition that
    depends on it reaches ``ValidityDomain.assess`` as UNKNOWN. There is no
    path through this function by which omitting an input yields IN_DOMAIN.
    """
    ambient_conductance = base.get("ambient_conductance")
    surface_area = base.get(SURFACE_AREA)

    length = characteristic_length(
        declared=base.get(CHARACTERISTIC_LENGTH),
        volume=base.get(BODY_VOLUME),
        surface_area=surface_area,
    )
    coefficient = surface_coefficient(
        ambient_conductance=ambient_conductance, surface_area=surface_area
    )
    biot = biot_number(
        coefficient=coefficient,
        length=length,
        conductivity=base.get(BODY_CONDUCTIVITY),
    )
    tau = thermal_time_constant(
        heat_capacity=base.get("heat_capacity"),
        ambient_conductance=ambient_conductance,
    )
    horizon = transient_horizon_ratio(
        duration=base.get("duration"), time_constant=tau
    )
    fourier = internal_fourier_number(horizon_ratio=horizon, biot=biot)

    steady = steady_state_temperature(
        ambient_temperature=ambient_temperature,
        heat_input=heat_input,
        ambient_conductance=ambient_conductance,
    )
    excursion = surface_temperature_excursion(
        initial_temperature=initial_temperature,
        ambient_temperature=ambient_temperature,
        steady_temperature=steady,
    )
    peak = peak_body_temperature(
        initial_temperature=initial_temperature, steady_temperature=steady
    )

    derived: dict[str, Quantity | None] = {
        BIOT_NUMBER: biot,
        TRANSIENT_HORIZON_RATIO: horizon,
        INTERNAL_FOURIER_NUMBER: fourier,
        CONDUCTANCE_EXCURSION_RATIO: conductance_excursion_ratio(
            excursion=excursion,
            bound=base.get(CONDUCTANCE_EXCURSION_BOUND),
        ),
        CAPACITY_EXCURSION_RATIO: capacity_excursion_ratio(
            initial_temperature=initial_temperature,
            steady_temperature=steady,
            bound=base.get(CAPACITY_EXCURSION_BOUND),
        ),
        RADIATION_TO_CONVECTION_RATIO: radiation_to_convection_ratio(
            radiation_coefficient=linearized_radiation_coefficient(
                emissivity=base.get(SURFACE_EMISSIVITY),
                surface_temperature=peak,
                surroundings_temperature=ambient_temperature,
            ),
            coefficient=coefficient,
        ),
        MELTING_TEMPERATURE_UTILIZATION: melting_temperature_utilization(
            peak_temperature=peak,
            melting_temperature=base.get(MELTING_TEMPERATURE),
        ),
    }
    return {name: value for name, value in derived.items() if value is not None}
