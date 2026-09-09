"""What independent science says a benchmark case should be.

WHAT THIS IS
------------
A second, standalone evaluator for the electro-thermal benchmark payloads. It
reads a case's ``payload`` and nothing else, computes every applicability
condition from physics written out here, and derives a verdict from the
governed contract -- then stops. It never learns what the benchmark expected or
what Forge answered.

THE INDEPENDENCE CLAIM, AND HOW IT IS STRUCTURAL
------------------------------------------------
**This module imports nothing from ``engcore``.** Not the applicability
evaluator, not the validity assessment, not ``derive_verdict``, not the solvers,
and not even the unit registry -- payload strings are parsed here into SI by a
small table below. That is a stronger claim than "does not call the function
under test", and it is checkable by reading the imports, which
``tests/oracles/test_independent_truth_noleak.py`` does mechanically.

The physics comes from the same places the oracle suite draws on: textbook
definitions, closed forms, and the two published convection correlations. The
*semantics* -- which operating point a condition is read at, what a conservative
screen does -- come from the governed contract as written in
``docs/assurance/SCIENTIFIC_BOUND_REGISTER.md`` and the adjudication log, which
is the answer key's own definition of the question rather than an answer to it.

WHAT IT DELIBERATELY WILL NOT DO
--------------------------------
Guess. A condition whose inputs the payload does not carry is ``UNKNOWN``; a
condition this module cannot reconstruct without inventing a convention is
``UNRESOLVED``, and a case carrying one is not counted as independently
evaluated. Preferring an honest gap to a confident reconstruction is the whole
value of a second evaluator -- one that always produces an answer would just be
a second implementation to be wrong in parallel.

TRUTH CLASSES
-------------
A verdict is only as independent as the weakest bound it rests on, so every
result carries what it depended on:

``INDEPENDENT_SCIENTIFIC``   every deciding bound is sourced or derived
``POLICY_DEPENDENT``         the arithmetic is verified, the deciding bound is
                             an explicit INTERNAL_POLICY number
``MIXED_SCIENCE_AND_POLICY`` several conditions decide it and they differ
``CONTRACT_ONLY``            nothing physical decides it -- the verdict follows
                             from the contract alone (e.g. every condition
                             satisfied on declarations the payload supplies)
``UNRESOLVED``               truth cannot be established without guessing
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# =====================================================================
# Units. Parsed here so this module does not touch Forge's registry.
# =====================================================================

#: Multiplier into SI base for every unit string the electro-thermal payloads
#: use. Deliberately a closed table: an unrecognised unit raises rather than
#: being guessed at, because a silently mis-scaled input would produce a
#: confident wrong truth, which is the one outcome worse than no truth.
_TO_SI = {
    "volt": 1.0, "ohm": 1.0, "ampere": 1.0, "watt": 1.0,
    "kelvin": 1.0, "second": 1.0, "meter": 1.0, "dimensionless": 1.0,
    "1/kelvin": 1.0, "joule/kelvin": 1.0, "watt/kelvin": 1.0,
    "meter**2": 1.0, "meter**3": 1.0,
    "watt/meter/kelvin": 1.0, "meter**2/second": 1.0,
    "meter/second": 1.0, "watt/meter**2/kelvin": 1.0,
    "millimeter": 1e-3, "centimeter": 1e-2, "kilometer": 1e3,
    "millivolt": 1e-3, "kilovolt": 1e3,
    "milliohm": 1e-3, "kiloohm": 1e3, "megaohm": 1e6,
    "milliampere": 1e-3, "milliwatt": 1e-3, "kilowatt": 1e3,
    "millisecond": 1e-3, "minute": 60.0, "hour": 3600.0,
}


class UnresolvedInput(Exception):
    """The payload said something this evaluator will not guess about."""


def si(text):
    """``"19.6 volt"`` -> 19.6, in SI base units. Raises on anything else."""
    if text is None:
        return None
    parts = str(text).split(None, 1)
    if len(parts) != 2:
        raise UnresolvedInput(f"not a value-and-unit string: {text!r}")
    value, unit = parts
    unit = unit.strip()
    if unit not in _TO_SI:
        raise UnresolvedInput(f"unit {unit!r} is not in this evaluator's table")
    return float(value) * _TO_SI[unit]


# =====================================================================
# Constants, written here from their sources
# =====================================================================

STEFAN_BOLTZMANN = 5.670374419e-8      # CODATA 2018, W m^-2 K^-4
STANDARD_GRAVITY = 9.80665             # SI definition, m/s^2


# =====================================================================
# Bounds, with the class each one carries
# =====================================================================

SOURCED = "SOURCED_OR_DERIVED"
POLICY = "INTERNAL_POLICY"
DEFINITIONAL = "DEFINITIONAL"

#: name -> (low, high, class). None means unbounded on that side. Every entry
#: is transcribed from docs/assurance/SCIENTIFIC_BOUND_REGISTER.md, which is
#: the governed statement of the bound, not a reading of the implementation.
BOUNDS = {
    "biot_number": (None, 0.1, SOURCED),
    "internal_fourier_number": (0.2, None, SOURCED),
    "geometry_route_ratio": (1.0 / 3.0, 3.0, SOURCED),
    "convection_conductance_agreement_ratio": (0.5, 2.0, SOURCED),
    "radiation_to_convection_ratio": (None, 0.1, POLICY),
    "reduced_debye_temperature": (1.0 / 3.0, None, POLICY),
    "reference_reduced_debye_temperature": (0.2, None, SOURCED),
    "ceiling_reduced_debye_temperature": (0.2, None, SOURCED),
    "temperature": (200.0, 450.0, POLICY),
    "conductance_excursion_ratio": (None, 1.0, DEFINITIONAL),
    "capacity_excursion_ratio": (None, 1.0, DEFINITIONAL),
    "melting_temperature_utilization": (None, 1.0, DEFINITIONAL),
    "operating_temperature_utilization": (None, 1.0, DEFINITIONAL),
    "linearization_excursion_ratio": (None, 1.0, DEFINITIONAL),
    "reference_temperature_utilization": (None, 1.0, DEFINITIONAL),
    "dissipated_power_utilization": (None, 1.0, DEFINITIONAL),
    "working_voltage_utilization": (None, 1.0, DEFINITIONAL),
    "source_current_utilization": (None, 1.0, DEFINITIONAL),
    "convection_flow_range_utilization": (None, 1.0, DEFINITIONAL),
    "convection_property_range_utilization": (None, 1.0, DEFINITIONAL),
    "linear_resistance_ratio": (0.0, None, DEFINITIONAL),
    # melt/T_max > 1: a self-contradictory pair of declarations.
    "declared_limits_are_mutually_consistent": (1.0, None, DEFINITIONAL),
}

#: What each model in play declares, so a condition whose input is missing
#: can be reported as UNKNOWN rather than quietly dropped. Transcribed from the
#: model records' condition lists, which are the contract's own statement of
#: what a model asks about.
THERMAL_CONDITIONS = (
    "biot_number", "internal_fourier_number", "conductance_excursion_ratio",
    "capacity_excursion_ratio", "radiation_to_convection_ratio",
    "convection_flow_range_utilization", "convection_property_range_utilization",
    "convection_conductance_agreement_ratio", "geometry_route_ratio",
    "melting_temperature_utilization",
)
RATED_MATERIAL_CONDITIONS = (
    "temperature", "linearization_excursion_ratio",
    "operating_temperature_utilization", "reduced_debye_temperature",
    "reference_temperature_utilization", "reference_reduced_debye_temperature",
    "ceiling_reduced_debye_temperature", "linear_resistance_ratio",
)

#: The one declared conservative screen in the tree. Under its floor the
#: criterion observed nothing, so it reports a GAP rather than a finding --
#: established by adjudication 2026-09-09.internal-fourier-number.screen.
CONSERVATIVE_SCREENS = {"internal_fourier_number"}

#: Which oracle from tests/oracles backs each condition's arithmetic.
ORACLES = {
    "biot_number": "ORA-DIM-GROUPS",
    "internal_fourier_number": "ORA-DIM-GROUPS",
    "radiation_to_convection_ratio": "ORA-RAD-LINEARIZATION",
    "convection_conductance_agreement_ratio": "ORA-FREE-CONVECTION-CROSS",
    "convection_flow_range_utilization": "ORA-FREE-CONVECTION-CROSS",
    "convection_property_range_utilization": "ORA-FREE-CONVECTION-CROSS",
    "operating_temperature_utilization": "ORA-LUMPED-ODE",
    "linearization_excursion_ratio": "ORA-TCR-LIMITS",
    "linear_resistance_ratio": "ORA-TCR-LIMITS",
    "reduced_debye_temperature": "ORA-TCR-LIMITS",
    "dissipated_power_utilization": "ORA-NGSPICE-DC",
    "working_voltage_utilization": "ORA-NGSPICE-DC",
    "source_current_utilization": "ORA-NGSPICE-DC",
}


# =====================================================================
# The result
# =====================================================================

@dataclass(frozen=True)
class IndependentCaseTruth:
    case_id: str
    domain: str
    values: dict            # condition -> independently computed value
    satisfied: tuple
    violated: tuple
    unknown: tuple
    unknown_reasons: dict
    independent_verdict: str
    truth_class: str
    oracle_ids: tuple
    policy_bound_ids: tuple
    unresolved_dependencies: tuple
    reason: str
    confidence_basis: str

    def to_dict(self):
        return {
            "case_id": self.case_id,
            "domain": self.domain,
            "independent_verdict": self.independent_verdict,
            "truth_class": self.truth_class,
            "satisfied": list(self.satisfied),
            "violated": list(self.violated),
            "unknown": list(self.unknown),
            "unknown_reasons": dict(sorted(self.unknown_reasons.items())),
            "values": {k: self.values[k] for k in sorted(self.values)},
            "oracle_ids": list(self.oracle_ids),
            "policy_bound_ids": list(self.policy_bound_ids),
            "unresolved_dependencies": list(self.unresolved_dependencies),
            "reason": self.reason,
            "confidence_basis": self.confidence_basis,
        }


# =====================================================================
# The physics, written out
# =====================================================================

class NoOperatingPoint(Exception):
    """The coupled loop admits no physical steady state.

    Carries the condition the failure corresponds to, because the two ways it
    happens are different physics about different designs and collapsing them
    into one label would report a conductor that has left its linear region as
    though it were a runaway.
    """

    def __init__(self, condition, detail):
        super().__init__(detail)
        self.condition = condition
        self.detail = detail


def _coupled_operating_point(*, voltage, r_ref, alpha, t_ref, hA, t_amb,
                             t_init, capacity, duration):
    """The self-consistent end-of-interval state of the coupled loop.

    The electrical side sets the dissipation from the conductor's resistance at
    the body's temperature; the thermal side marches a first-order lumped body
    to its declared horizon under that dissipation. The coupled state is the
    fixed point of

        T = T_amb + (V^2 / R(T)) / hA * reach + (T_0 - T_amb) * decay

    with ``decay = exp(-duration/tau)`` and ``reach = 1 - decay``.

    Solved in CLOSED FORM. Writing ``u = 1 + alpha (T - T_ref)`` so that
    ``R = R_ref u`` and ``T = T_ref + (u - 1)/alpha``, and letting ``T_off`` be
    the constant part of the balance and ``S`` its scale, the fixed point is

        u^2 + u (alpha T_ref - 1 - alpha T_off) - alpha S V^2 / (hA R_ref) = 0

    which decides EXISTENCE outright. That matters: this function previously
    used a damped iteration, and on five DEV cases it reported that no
    operating point existed when the quadratic shows a positive root plainly
    does. Those cases still came out NOT_SUPPORTED, so a verdict comparison
    could not see the defect -- only asking for the mechanism exposed it.

    Root selection is a REACHABILITY question, not just a sign question. A root
    with u > 0 is a state the conductor could hold, but only a root the body
    can actually arrive at from ``t_init`` describes this run.

    * The linear form must describe a conductor at the initial state. If
      ``R(t_init) <= 0`` the body begins where the model has already failed --
      note that this happens for a POSITIVE alpha whenever ``t_init`` falls
      below ``T_ref - 1/alpha``, which is easy to miss -- and no trajectory
      exists to follow. U01031 is exactly this: alpha = +0.05/K about a 293.15 K
      reference makes R negative below 273.15 K, and its body starts at 255.9 K.
    * For ``alpha > 0`` the constant term is negative, so exactly one root has
      u > 0 and there is nothing further to choose.
    * For ``alpha < 0`` both roots share a sign. Two positive roots are the two
      steady states of an NTC conductor: the lower-temperature one is stable --
      above it the loss term grows faster than the dissipation, below it the
      reverse -- and the upper is the ignition point. A body starting below the
      upper root settles on the lower one; a body starting above it runs away,
      even though steady states exist.

    Returns ``(endpoint, asymptote, tau)``.
    """
    if hA <= 0 or capacity <= 0 or duration <= 0:
        raise UnresolvedInput("non-positive thermal declaration")
    if 1.0 + alpha * (t_init - t_ref) <= 0.0:
        raise NoOperatingPoint(
            "linear_resistance_ratio",
            "the linear form gives R <= 0 at the initial temperature",
        )
    tau = capacity / hA
    decay = math.exp(-duration / tau)
    reach = 1.0 - decay
    drive = voltage * voltage / (hA * r_ref)

    def settle(scale, offset, start):
        t_off = t_amb + offset
        if alpha == 0.0:
            return t_off + scale * drive
        b = alpha * t_ref - 1.0 - alpha * t_off
        c = -alpha * scale * drive
        discriminant = b * b - 4.0 * c
        if discriminant < 0.0:
            raise NoOperatingPoint(
                "thermal_runaway_no_steady_state",
                "dissipation outruns the loss term at every temperature",
            )
        root = math.sqrt(discriminant)
        states = sorted(
            t_ref + (u - 1.0) / alpha
            for u in ((-b + root) / 2.0, (-b - root) / 2.0)
            if u > 0.0
        )
        if not states:
            raise NoOperatingPoint(
                "linear_resistance_ratio",
                "every steady state of the loop requires R <= 0",
            )
        if len(states) == 2 and start > states[1]:
            raise NoOperatingPoint(
                "thermal_runaway_no_steady_state",
                "the body starts above the ignition point and does not return",
            )
        return states[0]

    endpoint = settle(reach, (t_init - t_amb) * decay, t_init)
    asymptote = settle(1.0, 0.0, t_init)
    return endpoint, asymptote, tau


def _churchill_chu(rayleigh, prandtl):
    """Nu = 0.68 + 0.670 Ra^(1/4)/[1+(0.492/Pr)^(9/16)]^(4/9). CC 1975."""
    return 0.68 + 0.670 * rayleigh ** 0.25 / (
        1.0 + (0.492 / prandtl) ** (9.0 / 16.0)
    ) ** (4.0 / 9.0)


def _flat_plate_nusselt(reynolds, prandtl):
    """Nu = 0.664 Re^(1/2) Pr^(1/3), laminar parallel flow over a flat plate.

    Incropera, DeWitt, Bergman & Lavine 6th ed. Eq. 7.30, declared for
    Re_L <= 5e5 and Pr >= 0.6. Transcribed from the citation, as the natural
    route's correlation was.
    """
    return 0.664 * math.sqrt(reynolds) * prandtl ** (1.0 / 3.0)


def _radiation_coefficient(emissivity, t_surface, t_surroundings):
    """h_r = eps sigma (Ts+Tsur)(Ts^2+Tsur^2) -- exact, not linearised."""
    return (
        STEFAN_BOLTZMANN * emissivity
        * (t_surface + t_surroundings)
        * (t_surface * t_surface + t_surroundings * t_surroundings)
    )


# =====================================================================
# The evaluator
# =====================================================================

def evaluate_electrothermal(case_id, payload):
    """Independent truth for one electro-thermal payload."""
    values = {}
    unknown_reasons = {}
    unresolved = []

    stages = payload.get("stages") or []
    if len(stages) != 1:
        return _unresolved(case_id, "electrothermal",
                           ["only single-stage payloads are reconstructed"])
    stage = stages[0]
    conductor = stage["conductor"]
    body = stage["body"]
    app = body.get("applicability") or {}
    limits = conductor.get("limits") or {}
    ratings = conductor.get("ratings") or {}
    source_ratings = payload.get("source_ratings") or {}

    try:
        voltage = si(payload["source_voltage"])
        r_ref = si(conductor["reference_resistance"])
        alpha = si(conductor["temperature_coefficient"])
        t_ref = si(conductor["reference_temperature"])
        hA = si(body["ambient_conductance"])
        t_amb = si(body["ambient_temperature"])
        t_init = si(body["initial_temperature"])
        capacity = si(body["heat_capacity"])
        duration = si(body["duration"])
    except (UnresolvedInput, KeyError) as exc:
        return _unresolved(case_id, "electrothermal", [str(exc)])

    # --- the operating point ------------------------------------------
    try:
        endpoint, asymptote, tau = _coupled_operating_point(
            voltage=voltage, r_ref=r_ref, alpha=alpha, t_ref=t_ref, hA=hA,
            t_amb=t_amb, t_init=t_init, capacity=capacity, duration=duration,
        )
    except NoOperatingPoint as exc:
        # No physical operating point: the design has no state the lumped
        # linear-TCR composition can describe. That is a finding about the
        # design, and it is the one place this evaluator returns a verdict
        # without evaluating conditions. The condition NAME comes from the
        # root structure, not from which numerical path gave out.
        return IndependentCaseTruth(
            case_id=case_id, domain="electrothermal", values={},
            satisfied=(), violated=(exc.condition,), unknown=(),
            unknown_reasons={}, independent_verdict="NOT_SUPPORTED",
            truth_class="INDEPENDENT_SCIENTIFIC",
            oracle_ids=("ORA-LUMPED-ODE",), policy_bound_ids=(),
            unresolved_dependencies=(),
            reason=f"no physical coupled operating point exists: {exc.detail}",
            confidence_basis="closed-form roots of the coupled fixed point",
        )
    except UnresolvedInput as exc:
        return _unresolved(case_id, "electrothermal", [str(exc)])

    peak = max(t_init, asymptote)
    coldest = min(t_init, endpoint)
    furthest = max((t_init, endpoint), key=lambda t: abs(t - t_ref))
    rise = max(abs(t_init - t_amb), abs(asymptote - t_amb))
    resistance_at_end = r_ref * (1.0 + alpha * (endpoint - t_ref))
    power = voltage * voltage / resistance_at_end
    current = voltage / resistance_at_end

    values["endpoint_temperature"] = endpoint
    values["asymptote_temperature"] = asymptote
    values["time_constant"] = tau
    values["dissipated_power"] = power

    # --- material conditions ------------------------------------------
    values["temperature"] = endpoint
    # The WORST state the run occupies, not the final one. A conductor whose
    # linear form goes non-positive part-way through has left the region the
    # model describes, and a body that recovers by the horizon has still been
    # somewhere the composition cannot represent. u is linear in T, so the
    # minimum over the excursion sits at whichever end the sign of alpha picks.
    extreme = coldest if alpha > 0.0 else peak
    values["linear_resistance_ratio"] = 1.0 + alpha * (extreme - t_ref)

    band = si(limits.get("linearization_band")) if limits.get("linearization_band") else None
    if band:
        values["linearization_excursion_ratio"] = abs(furthest - t_ref) / band
    t_max = si(limits.get("maximum_operating_temperature")) if limits.get("maximum_operating_temperature") else None
    if t_max:
        # The GOVERNED operating point is the state the declared run occupies,
        # settled by the U01001 adjudication: reading the asymptote instead
        # fixes one dev case and breaks eighteen a landed decision requires.
        values["operating_temperature_utilization"] = endpoint / t_max
        values["reference_temperature_utilization"] = t_ref / t_max
    debye = si(limits.get("debye_temperature")) if limits.get("debye_temperature") else None
    if debye:
        values["reduced_debye_temperature"] = coldest / debye
        values["reference_reduced_debye_temperature"] = t_ref / debye
        if t_max:
            values["ceiling_reduced_debye_temperature"] = t_max / debye

    # --- electrical conditions ----------------------------------------
    rated_power = si(ratings.get("rated_power")) if ratings.get("rated_power") else None
    if rated_power:
        values["dissipated_power_utilization"] = power / rated_power
    max_voltage = si(ratings.get("maximum_working_voltage")) if ratings.get("maximum_working_voltage") else None
    if max_voltage:
        values["working_voltage_utilization"] = voltage / max_voltage
    max_current = si(source_ratings.get("maximum_current")) if source_ratings.get("maximum_current") else None
    if max_current:
        values["source_current_utilization"] = current / max_current

    # --- thermal / geometry conditions --------------------------------
    area = si(app.get("surface_area")) if app.get("surface_area") else None
    volume = si(app.get("body_volume")) if app.get("body_volume") else None
    declared_length = si(app.get("characteristic_length")) if app.get("characteristic_length") else None
    conductivity = si(app.get("body_conductivity")) if app.get("body_conductivity") else None

    length = declared_length
    if length is None and volume is not None and area:
        length = volume / area
    if declared_length is not None and volume is not None and area:
        values["geometry_route_ratio"] = declared_length / (volume / area)

    coefficient = (hA / area) if area else None
    if coefficient is not None and length is not None and conductivity:
        values["biot_number"] = coefficient * length / conductivity
        values["internal_fourier_number"] = (
            (duration / tau) / (coefficient * length / conductivity)
        )

    emissivity = si(app.get("surface_emissivity")) if app.get("surface_emissivity") is not None else None
    if emissivity is not None and coefficient:
        values["radiation_to_convection_ratio"] = (
            _radiation_coefficient(emissivity, peak, t_amb) / coefficient
        )

    for key, name in (
        ("conductance_excursion_bound", "conductance_excursion_ratio"),
        ("capacity_excursion_bound", "capacity_excursion_ratio"),
    ):
        bound = si(app.get(key)) if app.get(key) else None
        if bound:
            values[name] = rise / bound

    melt = si(app.get("melting_temperature")) if app.get("melting_temperature") else None
    if melt:
        values["melting_temperature_utilization"] = peak / melt
        if t_max is not None:
            # Two DECLARATIONS compared with each other, needing no run: a
            # material whose melting point sits below the operating ceiling it
            # is declared to respect has contradicted itself, and no state of
            # the body can rescue that. Independent of everything else here.
            values["declared_limits_are_mutually_consistent"] = melt / t_max

    # --- convection correlation ---------------------------------------
    regime = app.get("convection_regime")
    conv_length = si(app.get("convection_length")) if app.get("convection_length") else None
    fluid_k = si(app.get("fluid_conductivity")) if app.get("fluid_conductivity") else None
    nu_visc = si(app.get("fluid_kinematic_viscosity")) if app.get("fluid_kinematic_viscosity") else None
    prandtl = si(app.get("fluid_prandtl_number")) if app.get("fluid_prandtl_number") is not None else None
    expansion = si(app.get("fluid_expansion_coefficient")) if app.get("fluid_expansion_coefficient") else None

    # Each of the three conditions is formed from EXACTLY the declarations it
    # needs. An earlier draft gated all three behind the whole property set,
    # so a case missing only the fluid conductivity reported two gaps it did
    # not have -- the flow range is a Reynolds or Rayleigh number and never
    # needs k, and the property range is 0.6/Pr and needs nothing else at all.
    # Over-reporting a gap is not the safe direction it looks like: it claims
    # the payload settles less than it does, and on a `missing:*` case it
    # spreads one omission across conditions the omission does not touch.
    #
    # The Prandtl floor belongs to both correlations, so it is formed once
    # here rather than inside either route.
    if prandtl:
        values["convection_property_range_utilization"] = 0.6 / prandtl

    nusselt = None
    if regime == "natural" and None not in (conv_length, nu_visc, prandtl,
                                            expansion):
        delta = abs(peak - t_amb)
        rayleigh = (
            STANDARD_GRAVITY * expansion * delta * conv_length ** 3
            * prandtl / (nu_visc * nu_visc)
        )
        values["rayleigh_number"] = rayleigh
        # Declared for Ra <= 1e9 (Churchill & Chu 1975 / Incropera Eq. 9.27).
        values["convection_flow_range_utilization"] = rayleigh / 1.0e9
        if rayleigh > 0.0:
            nusselt = _churchill_chu(rayleigh, prandtl)
    elif regime == "forced":
        velocity = si(app.get("fluid_velocity")) if app.get("fluid_velocity") else None
        if None not in (conv_length, nu_visc, velocity):
            reynolds = velocity * conv_length / nu_visc
            values["reynolds_number"] = reynolds
            # Declared for Re <= 5e5 (Incropera Eq. 7.30).
            values["convection_flow_range_utilization"] = reynolds / 5.0e5
            if reynolds > 0.0 and prandtl:
                nusselt = _flat_plate_nusselt(reynolds, prandtl)
    elif regime not in (None, "natural", "forced"):
        unresolved.append(
            f"convection regime {regime!r} is not reconstructed"
        )

    # The agreement ratio is the only one of the three that needs the fluid
    # conductivity, because it is the only one that reconstructs a coefficient.
    if nusselt is not None and fluid_k and conv_length and coefficient:
        values["convection_conductance_agreement_ratio"] = (
            coefficient / (nusselt * fluid_k / conv_length)
        )
    # A declared regime whose fluid properties are incomplete leaves the three
    # convection conditions undecidable -- which the missing-declaration pass
    # below records. It does NOT make the case unreconstructable: every other
    # condition is still computable, and calling the whole case unresolved
    # would hide a verdict the payload fully determines.

    # A declaration the payload does not carry leaves its condition
    # UNDECIDABLE, not absent. That is the governed contract and it is the
    # entire content of the `missing:*` families: an omitted input must
    # produce a GAP, never a silent pass and never a finding against the
    # design. Skipping the condition -- which an earlier draft of this module
    # did -- turns those cases into whatever else happens to be wrong.
    expected = set(THERMAL_CONDITIONS)
    if limits:
        expected |= set(RATED_MATERIAL_CONDITIONS)
    # `geometry_route_ratio` compares TWO routes to the characteristic length.
    # With only one declared there is nothing to compare, so the condition is
    # vacuous rather than undecidable -- a body described one way cannot
    # contradict itself. This is the `(alt route remains)` semantics: omitting
    # the declared length while V/A_s survives must NOT refuse.
    if declared_length is None or volume is None or not area:
        expected.discard("geometry_route_ratio")
    for name in sorted(expected):
        if name not in values:
            unknown_reasons[name] = "not_supplied"

    return _classify(case_id, "electrothermal", values, unknown_reasons, unresolved)


def _classify(case_id, domain, values, unknown_reasons, unresolved):
    """Apply the bounds, then the verdict rules. No Forge anywhere."""
    satisfied, violated, unknown = [], [], []
    oracles, policies = set(), set()

    # Conditions whose input was missing arrive already marked.
    for name in sorted(unknown_reasons):
        if unknown_reasons[name] == "not_supplied" and name not in values:
            unknown.append(name)

    for name in sorted(BOUNDS):
        low, high, bound_class = BOUNDS[name]
        if name not in values:
            continue
        value = values[name]
        outside = (low is not None and value < low) or (
            high is not None and value > high
        )
        if outside and name in CONSERVATIVE_SCREENS:
            # A screen observed nothing: a gap, not a finding. Adjudicated.
            unknown.append(name)
            unknown_reasons[name] = "conservative_screen"
        elif outside:
            violated.append(name)
        else:
            satisfied.append(name)
        if bound_class == POLICY:
            policies.add(name)
        if name in ORACLES:
            oracles.add(ORACLES[name])

    if unresolved:
        return _unresolved(case_id, domain, unresolved, values=values)

    if violated:
        verdict = "NOT_SUPPORTED"
        deciding = violated
    elif unknown:
        verdict = "INSUFFICIENT_EVIDENCE"
        deciding = unknown
    else:
        verdict = "SUPPORTED"
        deciding = satisfied

    deciding_policy = sorted(p for p in policies if p in deciding)
    deciding_sourced = [
        d for d in deciding if BOUNDS.get(d, (None, None, ""))[2] == SOURCED
    ]

    if verdict == "SUPPORTED":
        # Nothing physical decided it: every declaration held. The conclusion
        # validates the contract rather than establishing a scientific claim.
        truth_class = "CONTRACT_ONLY"
    elif deciding_policy and deciding_sourced:
        truth_class = "MIXED_SCIENCE_AND_POLICY"
    elif deciding_policy:
        truth_class = "POLICY_DEPENDENT"
    elif deciding_sourced:
        truth_class = "INDEPENDENT_SCIENTIFIC"
    else:
        # Decided by a definitional bound against a caller-declared limit --
        # the arithmetic is independent, the limit is the caller's.
        truth_class = "CONTRACT_ONLY"

    return IndependentCaseTruth(
        case_id=case_id, domain=domain, values=values,
        satisfied=tuple(satisfied), violated=tuple(violated),
        unknown=tuple(unknown), unknown_reasons=unknown_reasons,
        independent_verdict=verdict, truth_class=truth_class,
        oracle_ids=tuple(sorted(oracles)),
        policy_bound_ids=tuple(deciding_policy),
        unresolved_dependencies=(),
        reason="; ".join(
            f"{name}={values[name]:.6g}" for name in deciding if name in values
        ) or "every evaluated condition held",
        confidence_basis=(
            "conditions computed from payload declarations by this module; "
            "bounds transcribed from SCIENTIFIC_BOUND_REGISTER.md"
        ),
    )


def _unresolved(case_id, domain, reasons, values=None):
    return IndependentCaseTruth(
        case_id=case_id, domain=domain, values=values or {}, satisfied=(),
        violated=(), unknown=(), unknown_reasons={},
        independent_verdict="UNRESOLVED", truth_class="UNRESOLVED",
        oracle_ids=(), policy_bound_ids=(),
        unresolved_dependencies=tuple(reasons),
        reason="; ".join(reasons),
        confidence_basis="not evaluated: an input would have to be guessed",
    )


def evaluate(case_id, payload, system="electrothermal"):
    """Entry point. Only the payload is ever read."""
    if system == "electrothermal":
        return evaluate_electrothermal(case_id, payload)
    return _unresolved(case_id, system, [f"system {system!r} not reconstructed"])
