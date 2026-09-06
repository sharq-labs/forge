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
    "CHURCHILL_CHU_LAMINAR_RAYLEIGH_CEILING",
    "CONVECTION_AGREEMENT_FACTOR",
    "CONVECTION_AGREEMENT_RATIO",
    "CONVECTION_FLOW_RANGE",
    "CONVECTION_LENGTH",
    "CONVECTION_PROPERTY_RANGE",
    "CORRELATION_RANGE_LIMIT",
    "EXPANSION_UNIT",
    "FLAT_PLATE_LAMINAR_REYNOLDS_CEILING",
    "FLAT_PLATE_MINIMUM_PRANDTL",
    "FLUID_CONDUCTIVITY",
    "FLUID_EXPANSION_COEFFICIENT",
    "FLUID_PRANDTL_NUMBER",
    "FLUID_VELOCITY",
    "FLUID_VISCOSITY",
    "STANDARD_GRAVITY",
    "VELOCITY_UNIT",
    "VISCOSITY_UNIT",
    "churchill_chu_nusselt",
    "conductance_agreement_ratio",
    "convection_flow_range_utilization",
    "convection_property_range_utilization",
    "correlated_coefficient",
    "correlated_surface_coefficient",
    "flat_plate_nusselt",
    "rayleigh_number",
    "reynolds_number",
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
    "GEOMETRY_AGREEMENT_FACTOR",
    "GEOMETRY_ROUTE_RATIO",
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
    "geometry_route_ratio",
    "conductance_excursion_ratio",
    "ASSEMBLED_QUANTITIES",
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
VISCOSITY_UNIT = "meter**2/second"
VELOCITY_UNIT = "meter/second"
EXPANSION_UNIT = "1/kelvin"
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

# --- how the caller says where their coefficient came from --------------------
# Properties of the AMBIENT FLUID and of the surface the boundary layer grows
# along. ``FLUID_CONDUCTIVITY`` and ``BODY_CONDUCTIVITY`` carry the same
# dimension and mean opposite things; ``CONVECTION_LENGTH`` and
# ``CHARACTERISTIC_LENGTH`` likewise. Neither pair falls back to the other.
FLUID_CONDUCTIVITY = "fluid_conductivity"
FLUID_VISCOSITY = "fluid_kinematic_viscosity"
FLUID_PRANDTL_NUMBER = "fluid_prandtl_number"
FLUID_EXPANSION_COEFFICIENT = "fluid_expansion_coefficient"
FLUID_VELOCITY = "fluid_velocity"
CONVECTION_LENGTH = "convection_length"

# --- names of the quantities this module derives ------------------------------
BIOT_NUMBER = "biot_number"
TRANSIENT_HORIZON_RATIO = "transient_horizon_ratio"
INTERNAL_FOURIER_NUMBER = "internal_fourier_number"
CONDUCTANCE_EXCURSION_RATIO = "conductance_excursion_ratio"
CAPACITY_EXCURSION_RATIO = "capacity_excursion_ratio"
RADIATION_TO_CONVECTION_RATIO = "radiation_to_convection_ratio"
MELTING_TEMPERATURE_UTILIZATION = "melting_temperature_utilization"
GEOMETRY_ROUTE_RATIO = "geometry_route_ratio"
CONVECTION_FLOW_RANGE = "convection_flow_range_utilization"
CONVECTION_PROPERTY_RANGE = "convection_property_range_utilization"
CONVECTION_AGREEMENT_RATIO = "convection_conductance_agreement_ratio"

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

#: How far the two routes to a characteristic length may disagree: a **factor
#: of 3**, either way. It is a factor rather than a percentage because a body
#: is not a sphere and ``V/A_s`` is not exactly ``L_c`` for every shape, so the
#: admissible disagreement is set by the caller's choice of convention rather
#: than by measurement error. Three is the sphere's shape factor and the
#: largest of the three standard shapes — see :func:`geometry_route_ratio` for
#: the derivation and for why the bound is two-sided.
GEOMETRY_AGREEMENT_FACTOR = Quantity(3.0, DIMENSIONLESS)


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
    # --- how the surface coefficient was obtained ------------------------
    # Six more optional fields, all Quantities, all feeding a derivation.
    # Together they let a correlation be evaluated and compared against the
    # declared ``ambient_conductance``. Which correlation is selected by which
    # of them is present -- an expansion coefficient means the natural route,
    # a velocity the forced one -- and never by ``convection_regime``, which
    # remains as inert as it was.
    fluid_conductivity: Quantity | None = None
    fluid_kinematic_viscosity: Quantity | None = None
    fluid_prandtl_number: Quantity | None = None
    fluid_expansion_coefficient: Quantity | None = None
    fluid_velocity: Quantity | None = None
    convection_length: Quantity | None = None

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
            ("fluid_conductivity", CONDUCTIVITY_UNIT, True),
            ("fluid_kinematic_viscosity", VISCOSITY_UNIT, True),
            ("fluid_prandtl_number", DIMENSIONLESS, True),
            ("fluid_expansion_coefficient", EXPANSION_UNIT, True),
            ("fluid_velocity", VELOCITY_UNIT, True),
            ("convection_length", LENGTH_UNIT, True),
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

        # Both routes declared is MIXED CONVECTION, and neither correlation
        # in this module covers it: Churchill-Chu assumes the flow is driven
        # by buoyancy alone and the flat-plate result assumes it is driven by
        # the free stream alone. Incropera Sec. 9.9 treats the combination
        # with a rule this domain does not implement. Picking one of the two
        # silently would be the substitution this module exists to refuse, so
        # the over-declaration is refused instead -- it is a caller stating
        # something this domain cannot judge, not a caller who left something
        # out, and the two must not collapse into the same UNKNOWN.
        if (
            self.fluid_expansion_coefficient is not None
            and self.fluid_velocity is not None
        ):
            raise InvalidScientificProblem(
                "a body may declare fluid_expansion_coefficient (free "
                "convection) or fluid_velocity (forced convection), not both: "
                "that is mixed convection and neither the Churchill-Chu nor "
                "the flat-plate correlation covers it. Declare the mechanism "
                "that sets the coefficient, or neither and leave the "
                "correlation conditions UNKNOWN"
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
                "fluid_conductivity",
                "fluid_kinematic_viscosity",
                "fluid_prandtl_number",
                "fluid_expansion_coefficient",
                "fluid_velocity",
                "convection_length",
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
            "fluid_conductivity": encode(self.fluid_conductivity),
            "fluid_kinematic_viscosity": encode(self.fluid_kinematic_viscosity),
            "fluid_prandtl_number": encode(self.fluid_prandtl_number),
            "fluid_expansion_coefficient": encode(
                self.fluid_expansion_coefficient
            ),
            "fluid_velocity": encode(self.fluid_velocity),
            "convection_length": encode(self.convection_length),
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
            fluid_conductivity=decode("fluid_conductivity"),
            fluid_kinematic_viscosity=decode("fluid_kinematic_viscosity"),
            fluid_prandtl_number=decode("fluid_prandtl_number"),
            fluid_expansion_coefficient=decode("fluid_expansion_coefficient"),
            fluid_velocity=decode("fluid_velocity"),
            convection_length=decode("convection_length"),
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


def geometry_route_ratio(
    *,
    declared: Quantity | None = None,
    volume: Quantity | None = None,
    surface_area: Quantity | None = None,
) -> Quantity | None:
    """L_c(declared) / (V / A_s) — do the two routes describe one body?

    **Definition.** The declared characteristic length over the one implied by
    the declared volume and surface area. Both are routes to the same quantity,
    and :func:`characteristic_length` takes the declared one when it is there.
    Nothing compared them, so a body could be declared with a length and a
    volume that belong to different objects and the Biot number would be
    computed from one of them without remark.

    **Why the bound is a factor and not a percentage.** V/A_s is not the only
    convention. Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat and
    Mass Transfer*, 6th ed. (2007), §5.1 defines ``L_c = V / A_s`` for the
    lumped criterion, and §5.5 uses the shape's own dimension — ``r_o`` for a
    sphere or a long cylinder, the half-thickness ``L`` for a plane wall — in
    the one-term series solutions. For a given body those two differ by exactly
    the shape factor:

        plane wall      L_c = L,        V / A_s = L        ratio 1
        long cylinder   L_c = r_o,      V / A_s = r_o / 2  ratio 2
        sphere          L_c = r_o,      V / A_s = r_o / 3  ratio 3

    So a disagreement of up to **3** is what a caller's choice of convention
    can account for, and the sphere is the extreme case. That is why the bound
    is a factor: a body is not a sphere, and V/A_s is not exactly L_c for every
    shape, so a percentage would be a statement about a body this model does
    not know the shape of. Beyond a factor of 3 in either direction there is no
    standard shape that reconciles the two numbers, and the honest reading is
    that they describe different objects.

    **Two-sided, and not because both directions are equally defensible.** A
    declared length *above* V/A_s is the conservative convention: it raises the
    Biot number and makes the lumped criterion harder to pass. A declared
    length *below* V/A_s lowers Bi and makes the model look applicable when it
    may not be, which is the more dangerous of the two and has no shape
    argument at all. Both are bounded here because this module cannot tell
    which convention a caller used, and refusing only the dangerous direction
    would leave a 30x disagreement unremarked whenever it fell the other way.

    **With only one route the ratio is 1, and that is a true statement rather
    than an assumed one.** This condition asks whether the routes a caller
    supplied contradict each other. A caller who declared only a length, or
    only a volume and an area, has supplied one route; :func:`characteristic_
    length` resolves it to a single unambiguous value, that value is the one
    the Biot number is computed from, and nothing contradicts it. Reporting
    UNKNOWN there would not be caution — it would make every single-route
    declaration undecidable and demand all three fields for a model that has
    always accepted either route, which is a different and much larger claim
    than this condition is making.

    ``None`` only when neither route is available, which is the case where
    there is no characteristic length at all and ``biot_number`` is already
    UNKNOWN for the same reason.
    """
    checked_declared = _positive(
        _as_quantity(declared, LENGTH_UNIT, CHARACTERISTIC_LENGTH),
        LENGTH_UNIT,
        CHARACTERISTIC_LENGTH,
    )
    implied = characteristic_length(volume=volume, surface_area=surface_area)
    if checked_declared is None and implied is None:
        return None
    if checked_declared is None or implied is None:
        return Quantity(1.0, DIMENSIONLESS)
    return Quantity(
        checked_declared.magnitude_in(LENGTH_UNIT)
        / implied.magnitude_in(LENGTH_UNIT),
        DIMENSIONLESS,
    )


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
# Convection correlations
# =====================================================================
#
# WHY THIS SECTION EXISTS
# -----------------------
# ``ambient_conductance`` is a number the caller supplies and, until this
# section, nothing asked where it came from. In real thermal design that is
# the single largest source of error: a coefficient wrong by a factor of two
# destroys the calculation, and every condition above would have reported
# IN_DOMAIN while it did. Biot, both excursion budgets and the radiation ratio
# are all computed *from* ``hA``, so an ``hA`` wrong by 2x moves every one of
# them by 2x and none of them notices.
#
# WHAT IS AND IS NOT CHECKED
# --------------------------
# A correlation predicts ``h`` from fluid properties and a geometry. That is
# not a measurement of ``h`` and this section does not pretend it is: the
# correlations below are approximations with their own scatter and their own
# idealized surface. What they give is an *independent second route* to a
# number the caller asserted, and three conditions follow from it:
#
#   1. Is the declared operating point inside the flow range the correlation
#      is valid over?  **This is the most important of the three.** A caller
#      who obtained ``h`` from a laminar correlation at Ra = 1e11 has a number
#      with nothing behind it, and agreement between two unsupported numbers
#      repairs nothing.
#   2. Is it inside the correlation's property range?
#   3. Does the declared ``hA`` reproduce what the correlation predicts, to
#      within a stated factor?
#
# WHAT SELECTS A CORRELATION -- AND IT IS NOT ``convection_regime``
# -----------------------------------------------------------------
# ``convection_regime`` stays exactly as inert as
# :func:`conductance_excursion_ratio` made it. No line below reads it. The
# natural route activates on the presence of a **volumetric expansion
# coefficient** and the forced route on the presence of a **fluid velocity**,
# because those are the declarations each correlation actually needs. A caller
# cannot select a correlation, or satisfy any condition here, by asserting a
# category: each route demands strictly more evidence than the bare
# conductance did, and the absence of that evidence is UNKNOWN.
#
# Declaring **both** is refused at the declaration record. That is mixed
# convection, neither correlation covers it, and silently picking one would be
# the substitution this whole module exists to refuse. See
# :class:`LumpedApplicabilityDeclaration`.
#
# WHY THE THREE CONDITIONS ARE ROUTE-AGNOSTIC
# --------------------------------------------
# Every condition in a validity domain is evaluated on every assessment, and
# an UNKNOWN one makes the whole verdict UNKNOWN. A design with a Rayleigh
# condition and a Reynolds condition would therefore make **every** body
# UNKNOWN, because no body has both -- a natural declaration would fail the
# Reynolds condition for want of a velocity it correctly does not have.
#
# So the three groups below are each defined for both routes, and the route
# decides how the number is formed rather than whether it exists. Two of them
# are *utilizations*: the fraction of the correlation's own stated range that
# the declaration consumes, so the bound is 1 by construction and no new
# number enters. The cited numbers -- 1e9, 5e5, 0.6 -- live inside the
# derivations, where each belongs to the correlation that states it.
#
# EVERYTHING HERE IS OPTIONAL
# ---------------------------
# A caller who supplies only a conductance is where they were: every group
# below returns ``None``, every key drops, and all three conditions read
# UNKNOWN. Supplying more can move a verdict away from UNKNOWN and can never
# turn a violated condition into a satisfied one.
#
# SOURCES
# -------
# Equation numbers are those of Incropera, DeWitt, Bergman & Lavine,
# *Fundamentals of Heat and Mass Transfer*, 6th ed. (Wiley, 2007). Every
# correlation is also written out in full below, so a reader holding a
# different edition can check the form rather than the numbering.


#: Standard acceleration of free fall, exact by definition: 9.80665 m/s^2,
#: fixed by the 3rd CGPM (1901) and carried in BIPM, *The International System
#: of Units (SI)*, 9th ed. (2019). It enters the Grashof number and nothing
#: else here. Local gravity departs from it by a few parts in a thousand,
#: which enters Ra linearly and Nu as Ra^(1/4) -- a tenth of a percent, far
#: inside the correlations' own scatter, and not worth a declaration.
STANDARD_GRAVITY = Quantity(9.80665, "meter/second**2")

#: Ra_L <= 1e9 for the Churchill-Chu **laminar** vertical-plate equation.
#:
#: **Established, and printed as a threshold.** Churchill, S. W. and Chu,
#: H. H. S. (1975), "Correlating equations for laminar and turbulent free
#: convection from a vertical plate", *International Journal of Heat and Mass
#: Transfer* 18(11), 1323-1329, give two equations: one holding over the whole
#: range of Ra_L and a second, more accurate one restricted to laminar flow.
#: Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), Sec. 9.6.1 prints the
#: restricted form as Eq. 9.27 with the range ``Ra_L <= 1e9`` beside it. This
#: is **not a convention**: 1e9 is where the vertical free-convection boundary
#: layer transitions, and it is the number the source attaches to the equation
#: this module evaluates.
#:
#: Above it the laminar form is simply the wrong correlation. The unrestricted
#: Eq. 9.26 covers the turbulent range and is not implemented, so this domain
#: reports the excursion rather than evaluating a laminar form in a turbulent
#: layer.
#:
#: **No lower bound.** The 0.68 leading constant of Eq. 9.27 is the conduction
#: limit the equation is built to approach as Ra falls to zero, so a small
#: Rayleigh number is inside its design rather than outside it.
CHURCHILL_CHU_LAMINAR_RAYLEIGH_CEILING = Quantity(1.0e9, DIMENSIONLESS)

#: Re_L <= 5e5 for the laminar flat-plate correlation.
#:
#: **Established, and printed as a threshold.** The critical Reynolds number
#: at which a flat-plate boundary layer transitions is conventionally taken as
#: ``Re_x,c = 5e5``; Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007),
#: Sec. 7.1 states it and Sec. 7.2 restricts the laminar average-Nusselt
#: result to it. The source itself says the real transition point depends on
#: surface roughness and free-stream turbulence, so 5e5 is a representative
#: value -- but it is the value the source attaches to this equation, which
#: makes it a citation rather than a convention.
FLAT_PLATE_LAMINAR_REYNOLDS_CEILING = Quantity(5.0e5, DIMENSIONLESS)

#: Pr >= 0.6 for the laminar flat-plate correlation.
#:
#: **Established.** The ``Pr^(1/3)`` factor comes from the constant-property
#: Blasius similarity solution, and Incropera, DeWitt, Bergman & Lavine, 6th
#: ed. (2007), Sec. 7.2 prints the restriction ``Pr >~ 0.6`` with it. Below it
#: -- liquid metals -- the thermal boundary layer is far thicker than the
#: velocity one and the exponent is not 1/3. There is no upper bound.
#:
#: **Churchill-Chu carries no Prandtl restriction**, which is what its
#: ``[1 + (0.492/Pr)^(9/16)]^(4/9)`` denominator is for: covering all Pr with
#: one equation is what the 1975 paper set out to do. So the natural route's
#: property-range utilization is zero, and that is a statement about the
#: correlation rather than a favour to the caller.
FLAT_PLATE_MINIMUM_PRANDTL = Quantity(0.6, DIMENSIONLESS)

#: Both range utilizations are bounded by 1, and the 1 is definitional rather
#: than chosen: each is constructed as *the fraction of the correlation's own
#: stated range that the declaration consumes*, so 1 is exactly the edge the
#: source printed. The cited numbers live inside the derivations, each with
#: the correlation that states it, and no number enters here.
CORRELATION_RANGE_LIMIT = Quantity(1.0, DIMENSIONLESS)

#: How far a declared ``hA`` may sit from what the correlation predicts:
#: **a factor of 2**, either way. **THIS IS A CONVENTION**, recorded as one --
#: no source prints it as a threshold for this comparison.
#:
#: **What is established.** That the comparison is worth making, and that a
#: correlation is not a measurement. Three things legitimately move the two
#: numbers apart: the correlation's scatter against its own data; the
#: difference between the idealized isothermal plate it describes and whatever
#: shape the body actually is; and the film-temperature property evaluation,
#: which the caller performs and this module cannot check.
#:
#: **What is not established: the number.** 2 is where the disagreement stops
#: being attributable to those three and starts being attributable to a
#: mistake -- a coefficient read off the wrong chart, a length taken from the
#: wrong axis, an area counted once instead of twice. It is also the magnitude
#: at which a wrong coefficient destroys a calculation rather than degrading
#: it. Neither of those is a measurement, and this constant says so.
#:
#: **Two-sided, and not because both directions are equally suspicious.** A
#: declared ``hA`` far *below* the correlation is the conservative error: it
#: predicts a hotter body. Far *above* is the dangerous one. Both are bounded
#: because nothing here can tell which of the three legitimate causes is at
#: work, and a one-sided bound would leave a 30x disagreement unremarked
#: whenever it fell the safe way -- and a 30x conservative coefficient is
#: still a declaration nobody should be relying on.
CONVECTION_AGREEMENT_FACTOR = Quantity(2.0, DIMENSIONLESS)


def rayleigh_number(
    *,
    expansion_coefficient: Quantity | None,
    temperature_difference: Quantity | None,
    length: Quantity | None,
    kinematic_viscosity: Quantity | None,
    prandtl_number: Quantity | None,
) -> Quantity | None:
    """Ra_L = g beta dT L^3 / (nu alpha) -- buoyancy against diffusion.

    **Definition.** ``Ra_L = Gr_L Pr = g beta (T_s - T_inf) L^3 / (nu alpha)``,
    and since ``alpha = nu / Pr`` this module forms it as
    ``g beta dT L^3 Pr / nu^2``, which is the same number and needs one fewer
    declaration. Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat
    and Mass Transfer*, 6th ed. (2007), Sec. 9.2 gives the Grashof number and
    Sec. 9.6.1 the Rayleigh number in these terms.

    **``L`` is the correlation's length, not the Biot number's.** They are
    different lengths and this module keeps them in different fields on
    purpose. ``characteristic_length`` is a *conduction* length, ``V/A_s`` or
    the half-thickness of a slab; ``convection_length`` is the dimension the
    boundary layer grows along, which for a vertical plate is its height. For
    a cube of side ``a`` the first is ``a/6`` and the second is ``a``, and Ra
    goes as ``L^3``, so confusing them is a factor of 216. No fallback from
    one to the other is provided, deliberately.

    **``dT`` is the largest surface-to-ambient difference the run reaches**,
    :func:`surface_temperature_excursion` -- the same driving difference the
    constant-``hA`` budget is measured against. Because it is the largest, the
    Rayleigh number reported is the largest, so the range condition is the
    conservative one: a run flagged as leaving the laminar range really does
    leave it somewhere.

    Returns ``None`` if any of the five is absent, and refuses a non-positive
    viscosity, length, expansion coefficient or Prandtl number rather than
    dividing by it.
    """
    beta = _positive(
        _as_quantity(
            expansion_coefficient, EXPANSION_UNIT, FLUID_EXPANSION_COEFFICIENT
        ),
        EXPANSION_UNIT,
        FLUID_EXPANSION_COEFFICIENT,
    )
    difference = _as_quantity(
        temperature_difference, TEMPERATURE_UNIT, "temperature excursion"
    )
    scale = _positive(
        _as_quantity(length, LENGTH_UNIT, CONVECTION_LENGTH),
        LENGTH_UNIT,
        CONVECTION_LENGTH,
    )
    nu = _positive(
        _as_quantity(kinematic_viscosity, VISCOSITY_UNIT, FLUID_VISCOSITY),
        VISCOSITY_UNIT,
        FLUID_VISCOSITY,
    )
    prandtl = _positive(
        _as_quantity(prandtl_number, DIMENSIONLESS, FLUID_PRANDTL_NUMBER),
        DIMENSIONLESS,
        FLUID_PRANDTL_NUMBER,
    )
    if beta is None or difference is None or scale is None:
        return None
    if nu is None or prandtl is None:
        return None
    return (
        STANDARD_GRAVITY
        * beta
        * difference
        * scale
        * scale
        * scale
        * prandtl.magnitude_in(DIMENSIONLESS)
        / (nu * nu)
    ).to(DIMENSIONLESS)


def reynolds_number(
    *,
    velocity: Quantity | None,
    length: Quantity | None,
    kinematic_viscosity: Quantity | None,
) -> Quantity | None:
    """Re_L = u L / nu -- inertia against viscosity over the surface.

    **Definition.** ``Re_L = u_inf L / nu`` with ``L`` the streamwise length.
    Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), Sec. 6.5 introduces
    it as the governing similarity parameter for forced convection and Sec. 7.1
    uses it in this form for the flat plate.

    ``L`` is :data:`CONVECTION_LENGTH`, the same field the Rayleigh number
    reads and, for the same reason, not the Biot number's length: under forced
    flow the length that matters is the one the boundary layer develops along.

    Returns ``None`` if any of the three is absent.
    """
    speed = _positive(
        _as_quantity(velocity, VELOCITY_UNIT, FLUID_VELOCITY),
        VELOCITY_UNIT,
        FLUID_VELOCITY,
    )
    scale = _positive(
        _as_quantity(length, LENGTH_UNIT, CONVECTION_LENGTH),
        LENGTH_UNIT,
        CONVECTION_LENGTH,
    )
    nu = _positive(
        _as_quantity(kinematic_viscosity, VISCOSITY_UNIT, FLUID_VISCOSITY),
        VISCOSITY_UNIT,
        FLUID_VISCOSITY,
    )
    if speed is None or scale is None or nu is None:
        return None
    return (speed * scale / nu).to(DIMENSIONLESS)


def churchill_chu_nusselt(
    *,
    rayleigh: Quantity | None,
    prandtl_number: Quantity | None,
) -> Quantity | None:
    """Nu_L for laminar free convection from a **vertical plate**.

    **The correlation.**::

        Nu_L = 0.68 + 0.670 Ra_L^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9)
                                                        (Ra_L <= 1e9)

    Churchill, S. W. and Chu, H. H. S. (1975), "Correlating equations for
    laminar and turbulent free convection from a vertical plate",
    *International Journal of Heat and Mass Transfer* 18(11), 1323-1329;
    printed as Eq. 9.27 in Incropera, DeWitt, Bergman & Lavine, 6th ed.
    (2007), Sec. 9.6.1, with its range beside it.

    **THE ORIENTATION IS PART OF THE CORRELATION.** This one is for a vertical
    isothermal plate, where the buoyant flow runs *along* the surface and the
    boundary layer grows from the leading edge upward. A horizontal plate has
    different constants entirely -- Incropera Sec. 9.6.3 gives
    ``Nu = 0.54 Ra^(1/4)`` for a hot surface facing up and
    ``Nu = 0.27 Ra^(1/4)`` for one facing down, a factor of two between two
    orientations of the same plate -- and its characteristic length is
    ``A_s/P`` rather than the height. A caller whose surface is horizontal is
    using the wrong correlation here and **this module cannot detect it**: no
    declared quantity carries the orientation. That is a real limitation,
    stated on the condition rather than hidden, and what the agreement bound
    then catches is only a disagreement past a factor of two.

    This function does **not** enforce ``Ra <= 1e9``. Evaluating outside the
    range and letting the range condition report it separately is deliberate:
    a caller who is outside gets both facts -- how far out, and by how much the
    coefficients then disagree -- rather than one UNKNOWN hiding the other.

    Returns ``None`` if either input is absent.
    """
    ra = _as_quantity(rayleigh, DIMENSIONLESS, "rayleigh number")
    prandtl = _positive(
        _as_quantity(prandtl_number, DIMENSIONLESS, FLUID_PRANDTL_NUMBER),
        DIMENSIONLESS,
        FLUID_PRANDTL_NUMBER,
    )
    if ra is None or prandtl is None:
        return None
    ra_value = ra.magnitude_in(DIMENSIONLESS)
    if ra_value < 0.0:
        raise InvalidScientificProblem(
            f"rayleigh number must be non-negative, got {ra_value!r}"
        )
    pr_value = prandtl.magnitude_in(DIMENSIONLESS)
    denominator = (1.0 + (0.492 / pr_value) ** (9.0 / 16.0)) ** (4.0 / 9.0)
    return Quantity(
        0.68 + 0.670 * ra_value ** 0.25 / denominator, DIMENSIONLESS
    )


def flat_plate_nusselt(
    *,
    reynolds: Quantity | None,
    prandtl_number: Quantity | None,
) -> Quantity | None:
    """Average Nu_L for laminar forced flow over a **flat plate**.

    **The correlation.**::

        Nu_L = 0.664 Re_L^(1/2) Pr^(1/3)      (Re_L <= 5e5, Pr >= 0.6)

    The average Nusselt number from the Blasius similarity solution for an
    isothermal flat plate in parallel flow: Eq. 7.30 in Incropera, DeWitt,
    Bergman & Lavine, 6th ed. (2007), Sec. 7.2, where both restrictions are
    printed with it.

    **THE GEOMETRY IS PART OF THE CORRELATION**, exactly as orientation is for
    Churchill-Chu. This is parallel flow over a flat surface with no pressure
    gradient. Cross-flow over a cylinder is Hilpert or Zukauskas with entirely
    different constants (Incropera Sec. 7.4), and flow inside a duct is
    Dittus-Boelter over a hydraulic diameter (Sec. 8.5). Nothing declared
    carries the geometry, so this module cannot tell which one a caller has,
    and the condition says so.

    Like :func:`churchill_chu_nusselt` this evaluates outside its stated range
    and lets the range condition report the excursion separately.

    Returns ``None`` if either input is absent.
    """
    re = _as_quantity(reynolds, DIMENSIONLESS, "reynolds number")
    prandtl = _positive(
        _as_quantity(prandtl_number, DIMENSIONLESS, FLUID_PRANDTL_NUMBER),
        DIMENSIONLESS,
        FLUID_PRANDTL_NUMBER,
    )
    if re is None or prandtl is None:
        return None
    re_value = re.magnitude_in(DIMENSIONLESS)
    if re_value < 0.0:
        raise InvalidScientificProblem(
            f"reynolds number must be non-negative, got {re_value!r}"
        )
    return Quantity(
        0.664 * re_value ** 0.5
        * prandtl.magnitude_in(DIMENSIONLESS) ** (1.0 / 3.0),
        DIMENSIONLESS,
    )


def correlated_surface_coefficient(
    *,
    nusselt: Quantity | None,
    fluid_conductivity: Quantity | None,
    length: Quantity | None,
) -> Quantity | None:
    """h = Nu k_f / L -- the correlation's own prediction of the coefficient.

    **Definition.** The Nusselt number is the dimensionless temperature
    gradient at the surface, ``Nu = h L / k_f``, so inverting it is what turns
    a correlation into a coefficient. Incropera, DeWitt, Bergman & Lavine, 6th
    ed. (2007), Sec. 6.5.

    ``k_f`` is the conductivity of the **fluid**, not of the body.
    :data:`BODY_CONDUCTIVITY` is the body's and feeds the Biot number; the two
    carry the same dimension and mean opposite things, and a caller who
    interchanges them gets a Biot number and a coefficient both wrong by the
    ratio -- for aluminium in air, about 9000. Nothing dimensional can catch
    that, which is why they are named apart and why this says so.

    ``L`` is the same :data:`CONVECTION_LENGTH` the dimensionless group was
    formed with. It must be: ``Nu`` is defined over that length and no other.
    """
    nu = _as_quantity(nusselt, DIMENSIONLESS, "nusselt number")
    conductivity = _positive(
        _as_quantity(fluid_conductivity, CONDUCTIVITY_UNIT, FLUID_CONDUCTIVITY),
        CONDUCTIVITY_UNIT,
        FLUID_CONDUCTIVITY,
    )
    scale = _positive(
        _as_quantity(length, LENGTH_UNIT, CONVECTION_LENGTH),
        LENGTH_UNIT,
        CONVECTION_LENGTH,
    )
    if nu is None or conductivity is None or scale is None:
        return None
    return (nu * conductivity / scale).to(COEFFICIENT_UNIT)


def convection_flow_range_utilization(
    *,
    rayleigh: Quantity | None,
    reynolds: Quantity | None,
) -> Quantity | None:
    """The fraction of the correlation's flow range the declaration consumes.

    **Definition.** ``Ra_L / 1e9`` on the natural route, ``Re_L / 5e5`` on the
    forced one. Both correlations are restricted to laminar flow and each
    states its own transition point, so this is one quantity with two
    formulas: how far toward its own stated edge the declared operating point
    sits, as a fraction. Exceeding 1 is exceeding the range the source printed.

    **Why one group rather than a Rayleigh condition and a Reynolds
    condition.** Every condition in a validity domain is evaluated on every
    assessment, and one UNKNOWN condition makes the whole verdict UNKNOWN. A
    body under free convection has no velocity and a body in a duct has no
    buoyancy term, so a pair of route-specific conditions would leave every
    body permanently UNKNOWN on the one that does not apply to it. Normalizing
    to each correlation's own edge gives a quantity both routes possess.

    **The bound is 1 and is definitional**, so no number enters here. 1e9 and
    5e5 belong to :data:`CHURCHILL_CHU_LAMINAR_RAYLEIGH_CEILING` and
    :data:`FLAT_PLATE_LAMINAR_REYNOLDS_CEILING`, each cited with the
    correlation that states it.

    **No lower bound in either route**, and for different reasons.
    Churchill-Chu approaches the conduction limit as Ra falls, by
    construction. The flat-plate result has no stated lower Reynolds bound
    either, though the boundary-layer approximation behind it does degrade as
    Re falls toward unity -- the source states no number for that and neither
    does this.

    Exactly one of the two arguments is ever present, because a declaration
    carrying both an expansion coefficient and a velocity is refused at the
    record. Returns ``None`` when neither is.
    """
    if rayleigh is not None and reynolds is not None:  # pragma: no cover
        raise InvalidScientificProblem(
            "both a Rayleigh and a Reynolds number were derived for one body; "
            "that is mixed convection and neither correlation covers it. The "
            "declaration record refuses it, so reaching here means the record "
            "was bypassed"
        )
    if rayleigh is not None:
        return Quantity(
            rayleigh.magnitude_in(DIMENSIONLESS)
            / CHURCHILL_CHU_LAMINAR_RAYLEIGH_CEILING.magnitude_in(DIMENSIONLESS),
            DIMENSIONLESS,
        )
    if reynolds is not None:
        return Quantity(
            reynolds.magnitude_in(DIMENSIONLESS)
            / FLAT_PLATE_LAMINAR_REYNOLDS_CEILING.magnitude_in(DIMENSIONLESS),
            DIMENSIONLESS,
        )
    return None


def convection_property_range_utilization(
    *,
    rayleigh: Quantity | None,
    reynolds: Quantity | None,
    prandtl_number: Quantity | None,
) -> Quantity | None:
    """The fraction of the correlation's property range the declaration uses.

    **Definition.** ``0.6 / Pr`` on the forced route, so the condition
    ``<= 1`` is exactly ``Pr >= 0.6``, the restriction Incropera Sec. 7.2
    prints with Eq. 7.30. **Zero on the natural route**, because Churchill-Chu
    states no Prandtl restriction at all: its
    ``[1 + (0.492/Pr)^(9/16)]^(4/9)`` denominator exists precisely so that one
    equation covers every Prandtl number, which is what the 1975 paper set out
    to do.

    **Zero is a statement about the correlation, not a favour to the caller.**
    It is not reachable by omitting anything: the natural route requires an
    expansion coefficient, a viscosity, a Prandtl number, a convection length
    and an operating point before this returns anything at all, and a caller
    who supplies none of them gets ``None`` and UNKNOWN. What the zero says is
    that the equation being evaluated has no property range to leave -- and a
    caller on that route still has to clear the Rayleigh range and the
    agreement ratio, which are the harder two.

    Returns ``None`` when no route could be resolved or the Prandtl number is
    absent.
    """
    prandtl = _positive(
        _as_quantity(prandtl_number, DIMENSIONLESS, FLUID_PRANDTL_NUMBER),
        DIMENSIONLESS,
        FLUID_PRANDTL_NUMBER,
    )
    if prandtl is None:
        return None
    if rayleigh is not None:
        return Quantity(0.0, DIMENSIONLESS)
    if reynolds is not None:
        return Quantity(
            FLAT_PLATE_MINIMUM_PRANDTL.magnitude_in(DIMENSIONLESS)
            / prandtl.magnitude_in(DIMENSIONLESS),
            DIMENSIONLESS,
        )
    return None


def conductance_agreement_ratio(
    *,
    declared_coefficient: Quantity | None,
    correlated_coefficient: Quantity | None,
) -> Quantity | None:
    """h_declared / h_correlated -- do the two routes describe one surface?

    **Definition.** The coefficient implied by the caller's declared ``hA`` and
    surface area, over the coefficient their declared fluid properties and
    geometry predict. Both are routes to the same number, and until now only
    one of them existed, so a declared ``hA`` off by a factor was invisible.

    The direct analogue of :func:`geometry_route_ratio`, and it takes the same
    shape for the same reason: two routes to one quantity, a factor rather
    than a percentage as the bound, and two-sided because nothing here can
    tell which route the caller got right. One difference:
    ``geometry_route_ratio`` returns 1 when only one route is available,
    because a single unambiguous length contradicts nothing. Here a single
    route means the correlation could not be evaluated at all -- there was no
    second number -- so the honest return is ``None`` and the honest verdict
    is UNKNOWN.

    **A disagreement is a finding about the DECLARATION, not the run.** Nothing
    about the solve changes: it uses the declared ``hA`` and always did. What
    this reports is that the caller's stated basis for that number does not
    reproduce it, which is a fact about how the case was posed.

    Returns ``None`` if either coefficient is absent.
    """
    declared = _positive(
        _as_quantity(
            declared_coefficient,
            COEFFICIENT_UNIT,
            "declared surface coefficient",
        ),
        COEFFICIENT_UNIT,
        "declared surface coefficient",
    )
    correlated = _positive(
        _as_quantity(
            correlated_coefficient,
            COEFFICIENT_UNIT,
            "correlated surface coefficient",
        ),
        COEFFICIENT_UNIT,
        "correlated surface coefficient",
    )
    if declared is None or correlated is None:
        return None
    return (declared / correlated).to(DIMENSIONLESS)


def correlated_coefficient(
    base: Mapping[str, Any],
    *,
    excursion: Quantity | None,
) -> tuple[Quantity | None, Quantity | None, Quantity | None]:
    """``(Ra, Re, h_correlated)`` for whichever route ``base`` supports.

    One place where the route is resolved, so the three groups above cannot
    disagree about which correlation was used. The resolution reads only
    declared Quantities -- an expansion coefficient for the natural route, a
    velocity for the forced one -- and never ``convection_regime``.
    """
    length = base.get(CONVECTION_LENGTH)
    viscosity = base.get(FLUID_VISCOSITY)
    prandtl = base.get(FLUID_PRANDTL_NUMBER)
    rayleigh = rayleigh_number(
        expansion_coefficient=base.get(FLUID_EXPANSION_COEFFICIENT),
        temperature_difference=excursion,
        length=length,
        kinematic_viscosity=viscosity,
        prandtl_number=prandtl,
    )
    reynolds = reynolds_number(
        velocity=base.get(FLUID_VELOCITY),
        length=length,
        kinematic_viscosity=viscosity,
    )
    nusselt = (
        churchill_chu_nusselt(rayleigh=rayleigh, prandtl_number=prandtl)
        if rayleigh is not None
        else flat_plate_nusselt(reynolds=reynolds, prandtl_number=prandtl)
    )
    return (
        rayleigh,
        reynolds,
        correlated_surface_coefficient(
            nusselt=nusselt,
            fluid_conductivity=base.get(FLUID_CONDUCTIVITY),
            length=length,
        ),
    )


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

#: Every name this module assembles, and which a caller parameter may
#: therefore never occupy. See ``engcore.domains.derived_context`` for what
#: reserving a name means and why it is enforced at assembly rather than at
#: problem construction.
#:
#: It is the derived groups **and** the state coordinates the assembler
#: injects, because the two are in the same position: a condition reads either
#: one by name, and either one is absent when the assembler could not supply
#: it. A rule that reserved only the derived groups would leave the state
#: coordinates forgeable in exactly the same way, which is not a smaller
#: version of the defect but the same one.
ASSEMBLED_QUANTITIES = frozenset(
    {
        BIOT_NUMBER,
        TRANSIENT_HORIZON_RATIO,
        INTERNAL_FOURIER_NUMBER,
        CONDUCTANCE_EXCURSION_RATIO,
        CAPACITY_EXCURSION_RATIO,
        RADIATION_TO_CONVECTION_RATIO,
        MELTING_TEMPERATURE_UTILIZATION,
        GEOMETRY_ROUTE_RATIO,
        CONVECTION_FLOW_RANGE,
        CONVECTION_PROPERTY_RANGE,
        CONVECTION_AGREEMENT_RATIO,
    }
)


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

    # The convection correlations. The route is selected by the presence of
    # the declaration it needs -- an expansion coefficient for the natural
    # route, a velocity for the forced one -- and never by
    # ``convection_regime``, which no line here reads.
    rayleigh, reynolds, correlated = correlated_coefficient(
        base, excursion=excursion
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
        GEOMETRY_ROUTE_RATIO: geometry_route_ratio(
            declared=base.get(CHARACTERISTIC_LENGTH),
            volume=base.get(BODY_VOLUME),
            surface_area=base.get(SURFACE_AREA),
        ),
        MELTING_TEMPERATURE_UTILIZATION: melting_temperature_utilization(
            peak_temperature=peak,
            melting_temperature=base.get(MELTING_TEMPERATURE),
        ),
        CONVECTION_FLOW_RANGE: convection_flow_range_utilization(
            rayleigh=rayleigh, reynolds=reynolds
        ),
        CONVECTION_PROPERTY_RANGE: convection_property_range_utilization(
            rayleigh=rayleigh,
            reynolds=reynolds,
            prandtl_number=base.get(FLUID_PRANDTL_NUMBER),
        ),
        CONVECTION_AGREEMENT_RATIO: conductance_agreement_ratio(
            declared_coefficient=coefficient,
            correlated_coefficient=correlated,
        ),
    }
    return {name: value for name, value in derived.items() if value is not None}
