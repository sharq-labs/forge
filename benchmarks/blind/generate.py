"""Generate the blind challenge corpus. Establishes NO truth and runs NO Forge.

This module writes payloads and design metadata. It never states a verdict, a
reason or a catcher: that is :mod:`build_truth`'s job, and it does it with the
independent oracle layer. Keeping the two apart is not tidiness — a generator
that also decided truth could place a case and label it in one step, and the
label would be the placement's *intention* rather than a measurement of where
the case actually landed.

**Intent is not truth.** Every family targets a stratum by solving for the
declaration that puts one condition at a chosen position against its bound.
What the case IS, is whatever the oracle measures afterwards. A case that
misses its intended stratum keeps its measured one and is reported as a miss in
the manifest.

**How a condition is placed exactly.** Most conditions are ratios of a computed
quantity to a DECLARED limit, so the limit can be solved for: to put
``operating_temperature_utilization`` at 1.01, declare
``maximum_operating_temperature = T / 1.01``. The ones that are not ratios to a
declared limit — the convection agreement, the geometry route, the Fourier
screen — are placed by solving for the fluid conductivity, the declared
characteristic length and the run duration respectively, which is the same
trick one layer down.

**Order matters, and an earlier draft had it wrong.** The Fourier screen is
placed by solving for the run's *duration*, and the duration changes the
operating point the whole case is sized against. So every quantity that moves
the fixed point is drawn first, the fixed point is solved once, and only then
are the declared limits sized against the state that solve reached. A generator
that sized limits against a state its own payload no longer produced would
write cases whose intent and content disagree.

Anti-overfitting
----------------

The parameter ranges here deliberately do not reproduce the existing Hard
benchmark's: a different master seed, different decades of resistance and
conductance, multi-stage circuits as the common case rather than the exception,
non-SI unit spellings throughout, and temperature regimes that include the cold
end the existing corpus barely visits. The comparison is measured and recorded
in the manifest rather than asserted here.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Callable

from .families import (
    ALL_FAMILIES,
    POSITION_LADDER,
    Family,
)

__all__ = [
    "MASTER_SEED",
    "GENERATOR_VERSION",
    "seed_for",
    "generate_corpus",
    "units_used",
]

MASTER_SEED = 20260909
GENERATOR_VERSION = "blind-generator/1.1.0"

STEFAN_BOLTZMANN = 5.670374419e-8
STANDARD_GRAVITY = 9.80665

#: Deliberately NOT the SI spelling everywhere. A representation variant is a
#: real test: the runtime canonicalises through pint and the oracle through its
#: own hand-written table, so a unit the two read differently is a defect
#: neither would find alone.
VOLT_UNITS = ["volt", "millivolt", "kilovolt"]
OHM_UNITS = ["ohm", "milliohm", "kilohm"]
TEMPERATURE_UNITS = ["kelvin", "degC"]

#: Every unit string this module can emit. Checked against the oracle's table
#: before the freeze by :func:`oracles.units.assert_vocabulary_closed`, so a
#: generator that grows a unit the oracle cannot read fails loudly at
#: generation rather than case-by-case at truth time.
_EMITTED: set[str] = set()


def units_used() -> set[str]:
    return set(_EMITTED)


def seed_for(system: str, family: str, index: int) -> int:
    """Per-case seed, derived rather than drawn from a shared stream.

    A single global RNG would make every case's draw depend on how many cases
    were generated before it, so adding one family would silently redraw every
    later family. Deriving the seed from the case's own identity makes each
    draw independent of the corpus around it, and makes a single case
    reproducible without replaying the whole generation.
    """
    material = f"{MASTER_SEED}:{system}:{family}:{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


_SCALE: dict[str, tuple[float, float]] = {
    # unit: (multiply the SI magnitude by, offset subtracted first)
    "millivolt": (1e3, 0.0), "kilovolt": (1e-3, 0.0),
    "milliohm": (1e3, 0.0), "kilohm": (1e3 ** -1, 0.0), "megohm": (1e-6, 0.0),
    "milliampere": (1e3, 0.0),
    "milliampere_hour": (1e3, 0.0),
    "minute": (1.0 / 60.0, 0.0), "hour": (1.0 / 3600.0, 0.0),
    "millisecond": (1e3, 0.0),
    "millimeter": (1e3, 0.0), "centimeter": (1e2, 0.0),
    "millimeter**2": (1e6, 0.0), "centimeter**3": (1e6, 0.0),
    "kilojoule/mole": (1e-3, 0.0), "mole/liter": (1e-3, 0.0),
    "milliwatt": (1e3, 0.0), "kilowatt": (1e-3, 0.0),
    "milliwatt/kelvin": (1e3, 0.0),
    "1/hour": (3600.0, 0.0), "1/minute": (60.0, 0.0),
    "percent": (100.0, 0.0),
    "degC": (1.0, 273.15),
}


def _quantity(value: float, unit: str) -> str:
    """A quantity as the payload spells it, in a unit that is not always SI.

    ``repr`` rather than a format string: a rounded magnitude would move a case
    off the position it was solved for, which is exactly the placement this
    generator exists to make exact.
    """
    _EMITTED.add(unit)
    factor, offset = _SCALE.get(unit, (1.0, 0.0))
    return f"{(value - offset) * factor!r} {unit}"


# =====================================================================
# electro-thermal
# =====================================================================

def _churchill_chu(rayleigh: float, prandtl: float) -> float:
    return 0.68 + 0.670 * rayleigh**0.25 / (
        (1.0 + (0.492 / prandtl) ** (9.0 / 16.0)) ** (4.0 / 9.0))


def _et_fixed_point(stages: list[dict], source_v: float
                    ) -> tuple[list[float], float, bool]:
    """The map the oracle solves, used here only to SIZE the declarations.

    This is the independent implementation, not the runtime's: the generator
    may use the oracle layer and nothing else. It finds the operating point a
    design settles at so that a limit can be placed relative to it; it decides
    nothing about the case.
    """
    temperatures = [s["t_0"] for s in stages]
    current = 0.0
    for _ in range(400):
        resistances = [s["r_ref"] * (1.0 + s["alpha"] * (t - s["t_ref"]))
                       for s, t in zip(stages, temperatures)]
        if any(r <= 0.0 or not math.isfinite(r) for r in resistances):
            return temperatures, float("nan"), False
        total = sum(resistances)
        if total <= 0.0:
            return temperatures, float("nan"), False
        current = source_v / total
        updated = []
        for stage, resistance in zip(stages, resistances):
            power = current * current * resistance
            asymptote = stage["t_amb"] + power / stage["g"]
            tau = stage["capacity"] / stage["g"]
            updated.append(asymptote + (stage["t_0"] - asymptote)
                           * math.exp(-stage["duration"] / tau))
        if not all(math.isfinite(t) for t in updated):
            return temperatures, current, False
        movement = max(abs(a - b) for a, b in zip(updated, temperatures))
        temperatures = updated
        if movement <= 1e-11:
            return temperatures, current, True
    return temperatures, current, False


def _shape_source_voltage(stages: list[dict], target_peak_k: float,
                          rng: random.Random) -> float | None:
    """Solve the source voltage that lands the hottest stage at a target.

    Without this the drawn decades put most designs either at ambient or past
    every ceiling at once, and a corpus of cases that are all violated by five
    conditions apiece cannot test which condition decides anything. Bisection
    on ``V``, because the peak temperature is monotone in the dissipated power
    for the conductors drawn here.

    Returns ``None`` when no voltage in the bracket reaches the target, which
    is a documented generation-time rejection rather than a silent retry.
    """
    def peak(voltage: float) -> float:
        temperatures, _current, converged = _et_fixed_point(stages, voltage)
        if not converged:
            return float("inf")
        return max(temperatures)

    low, high = 1e-6, 1.0
    for _ in range(200):
        if peak(high) >= target_peak_k:
            break
        high *= 2.0
        if high > 1e7:
            return None
    else:
        return None
    if peak(low) > target_peak_k:
        return None
    for _ in range(200):
        middle = math.sqrt(low * high)
        if peak(middle) < target_peak_k:
            low = middle
        else:
            high = middle
        if high / low < 1.0 + 1e-12:
            break
    return math.sqrt(low * high)


def _draw_electrothermal(rng: random.Random, position_for: Callable[[str, float], float]
                         ) -> tuple[list[dict], float] | None:
    """A physically sensible series design, drawn over wide decades.

    The decades are wide on purpose. The existing corpus lives near ohms and
    tens of volts; this one spans milliohms to tens of kilohms and 0.05 V to
    600 V, so a scale-dependent defect has somewhere to show.

    Everything that moves the fixed point is fixed here — including the run
    duration, which the Fourier screen solves for — so the caller can solve the
    fixed point ONCE and size every declared limit against the state it reached.
    """
    n_stages = rng.choice([1, 2, 2, 3, 3, 4])
    stages: list[dict] = []
    for index in range(n_stages):
        t_amb = rng.uniform(215.0, 340.0)
        capacity = 10.0 ** rng.uniform(-1.5, 2.5)
        conductance = 10.0 ** rng.uniform(-3.0, 0.7)
        route = position_for("geometry_route_ratio", rng.uniform(0.45, 2.4))
        # Bi = h Lc / k, and Lc is the DECLARED length when there is one. Only
        # the RATIO is fixed here; the lengths and the conductivity are solved
        # in the payload, because the surface area they need is itself solved
        # from the radiation ratio at the operating temperature.
        biot = 0.1 * position_for("biot_number", rng.uniform(0.05, 0.7))
        # Fo = (t/tau)/Bi, so the horizon is what places the screen. This is
        # why it is drawn HERE and not when the payload is assembled: it moves
        # the operating point. It needs Bi and tau, neither of which needs the
        # area, which is why the two can be separated at all.
        fourier = 0.2 / position_for("internal_fourier_number",
                                     1.0 / rng.uniform(1.5, 40.0))
        tau = capacity / conductance
        stages.append({
            "component_id": f"R{index + 1}",
            "r_ref": 10.0 ** rng.uniform(-2.5, 4.2),
            "alpha": rng.choice([0.0, 1.0, 1.0, 1.0, -1.0])
                     * 10.0 ** rng.uniform(-4.5, -2.8),
            "route": route,
            "biot": biot,
            "implied_length": 10.0 ** rng.uniform(-4.0, -1.5),
            # TIED TO AMBIENT, not drawn independently. `t_max` is solved from
            # the operating temperature to place
            # `operating_temperature_utilization`, and an independently drawn
            # `t_ref` above it violates `reference_temperature_utilization` --
            # a condition no family in this corpus targets. 23 cases refused
            # for that reason before this was tied down, each of them a case
            # whose family was asking about something else entirely. The upper
            # factor is 0.98 rather than 1.0 so the guarantee survives the
            # 0.999 rung of the ladder.
            "t_ref": t_amb * rng.uniform(0.75, 0.98),
            "g": conductance,
            "capacity": capacity,
            "t_amb": t_amb,
            "t_0": t_amb,
            "duration": fourier * biot * tau,
        })
    # Land the hottest stage inside the TCR envelope's comfortable interior,
    # unless a family is deliberately walking a temperature-shaped condition.
    target_peak = rng.uniform(235.0, 425.0)
    source_v = _shape_source_voltage(stages, target_peak, rng)
    if source_v is None:
        return None
    return stages, source_v


def _et_payload(rng: random.Random, stages: list[dict], source_v: float,
                temperatures: list[float], current: float,
                position_for: Callable[[str, float], float],
                withhold: str | None, target: str | None) -> dict[str, Any]:
    """Assemble a payload whose declarations put the target at its position.

    Everything not targeted is declared with a comfortable margin, so a case
    has the finding it was built to have and the causal analysis afterwards has
    something unambiguous to find. Whether it actually does is measured by the
    oracle, not assumed here.
    """
    volt_unit = rng.choice(VOLT_UNITS)
    ohm_unit = rng.choice(OHM_UNITS)
    temperature_unit = rng.choice(TEMPERATURE_UNITS)
    payload: dict[str, Any] = {
        "source_voltage": _quantity(source_v, volt_unit),
        "stages": [],
    }

    for stage, temperature in zip(stages, temperatures):
        resistance = stage["r_ref"] * (
            1.0 + stage["alpha"] * (temperature - stage["t_ref"]))
        power = current * current * resistance
        drop = current * resistance
        asymptote = stage["t_amb"] + power / stage["g"]
        peak = max(stage["t_0"], asymptote)
        excursion = max(abs(stage["t_0"] - stage["t_amb"]),
                        abs(asymptote - stage["t_amb"]))
        coldest = min(stage["t_0"], temperature)
        furthest = max((stage["t_0"], temperature),
                       key=lambda value: abs(value - stage["t_ref"]))

        # THE EMISSIVITY IS DRAWN, AND THE SURFACE AREA IS SOLVED.
        #
        # An emissivity is a fraction of the black-body emissive power, and
        # `LumpedApplicabilityDeclaration` refuses a value outside [0, 1] when
        # the body is BUILT -- a construction guard, not a validity condition.
        # Solving the radiation ratio through the emissivity, as an earlier
        # draft did, produced values up to 5.8 and would have had 118 of 207
        # electro-thermal cases refused at the boundary while their frozen
        # truth said SUPPORTED. Every one of those would have scored as a Forge
        # mismatch and measured nothing but this function.
        #
        # So the emissivity is drawn where a real surface lives, h_r follows
        # from it and the temperatures, and the ratio h_r/h is placed by
        # solving h -- and therefore the surface area, since h = (hA)/A_s and
        # the conductance is already fixed. The area moves no part of the fixed
        # point, which is what makes this legal here.
        emissivity = rng.uniform(0.02, 0.98)
        denominator = ((peak + stage["t_amb"])
                       * (peak * peak + stage["t_amb"] * stage["t_amb"]))
        radiation_coefficient = STEFAN_BOLTZMANN * emissivity * denominator
        ratio = 0.1 * position_for("radiation_to_convection_ratio",
                                   rng.uniform(0.05, 0.7))
        coefficient = radiation_coefficient / ratio
        area = stage["g"] / coefficient
        implied_length = stage["implied_length"]
        volume = implied_length * area
        declared_length = stage["route"] * implied_length
        conductivity = coefficient * declared_length / stage["biot"]

        conductance_bound = excursion / position_for(
            "conductance_excursion_ratio", rng.uniform(0.1, 0.7))
        capacity_bound = abs(asymptote - stage["t_0"]) / position_for(
            "capacity_excursion_ratio", rng.uniform(0.1, 0.7))
        melting = peak / position_for("melting_temperature_utilization",
                                      rng.uniform(0.2, 0.7))

        t_max = temperature / position_for("operating_temperature_utilization",
                                           rng.uniform(0.4, 0.85))
        # A part rated to operate at or above its own melting point is two
        # statements about one body that cannot both hold, and the oracle
        # emits a FAILED CHECK for it. Drawn independently these two collided
        # on 38 cases, every one of them acquiring a second, unrelated finding
        # on top of the one its family was built to place. So whichever of the
        # pair the family is NOT placing gives way.
        if target == "melting_temperature_utilization":
            t_max = min(t_max, melting / 1.02)
        else:
            melting = max(melting, t_max * 1.02)
        band = abs(furthest - stage["t_ref"]) / position_for(
            "linearization_excursion_ratio", rng.uniform(0.1, 0.7))
        # reduced_debye = T_cold / theta_D, floor 1/3, so a POSITION of p means
        # the ratio sits at (1/3)/p -- inside for p < 1.
        debye = coldest * position_for("reduced_debye_temperature",
                                       1.0 / rng.uniform(1.5, 6.0)) * 3.0

        rated_power = power / position_for("dissipated_power_utilization",
                                           rng.uniform(0.3, 0.8))
        max_voltage = drop / position_for("working_voltage_utilization",
                                          rng.uniform(0.3, 0.8))

        prandtl = rng.uniform(0.65, 7.0)
        viscosity = 10.0 ** rng.uniform(-6.2, -4.6)
        beta = 10.0 ** rng.uniform(-3.4, -2.3)
        rayleigh = 1.0e9 * position_for("convection_flow_range_utilization",
                                        rng.uniform(0.02, 0.6))
        cubed = rayleigh * viscosity * viscosity / (
            STANDARD_GRAVITY * beta * max(excursion, 1e-12) * prandtl)
        convection_length = cubed ** (1.0 / 3.0) if cubed > 0.0 else 1e-3
        nusselt = _churchill_chu(max(rayleigh, 1e-6), prandtl)
        # h_declared / h_correlated = agreement, solved through k_f. The bound
        # is two-sided [0.5, 2.0]; a POSITION of p is mapped onto the upper
        # side, which is the side a caller over-declaring a conductance hits.
        agreement = 2.0 * position_for("convection_conductance_agreement_ratio",
                                       rng.uniform(0.3, 0.9))
        fluid_conductivity = (coefficient * convection_length
                              / (nusselt * agreement))

        applicability = {
            "characteristic_length": _quantity(declared_length, "meter"),
            "body_volume": _quantity(volume, "meter**3"),
            "surface_area": _quantity(area, "meter**2"),
            "body_conductivity": _quantity(conductivity, "watt/meter/kelvin"),
            "surface_emissivity": _quantity(emissivity, "dimensionless"),
            "conductance_excursion_bound": _quantity(conductance_bound, "kelvin"),
            "capacity_excursion_bound": _quantity(capacity_bound, "kelvin"),
            "melting_temperature": _quantity(melting, "kelvin"),
            "fluid_conductivity": _quantity(fluid_conductivity, "watt/meter/kelvin"),
            "fluid_kinematic_viscosity": _quantity(viscosity, "meter**2/second"),
            "fluid_prandtl_number": _quantity(prandtl, "dimensionless"),
            "convection_length": _quantity(convection_length, "meter"),
            "fluid_expansion_coefficient": _quantity(beta, "1/kelvin"),
        }
        limits = {
            "linearization_band": _quantity(band, "kelvin"),
            "maximum_operating_temperature": _quantity(t_max, "kelvin"),
            "debye_temperature": _quantity(debye, "kelvin"),
        }
        ratings = {
            "rated_power": _quantity(rated_power, "watt"),
            "maximum_working_voltage": _quantity(max_voltage, "volt"),
        }
        for section in (applicability, limits, ratings):
            section.pop(withhold, None)

        payload["stages"].append({
            "component_id": stage["component_id"],
            "conductor": {
                "reference_resistance": _quantity(stage["r_ref"], ohm_unit),
                "temperature_coefficient": _quantity(stage["alpha"], "1/kelvin"),
                "reference_temperature": _quantity(stage["t_ref"], temperature_unit),
                "limits": limits,
                "ratings": ratings,
            },
            "body": {
                "heat_capacity": _quantity(stage["capacity"], "joule/kelvin"),
                "ambient_conductance": _quantity(stage["g"], "watt/kelvin"),
                "ambient_temperature": _quantity(stage["t_amb"], temperature_unit),
                "initial_temperature": _quantity(stage["t_0"], temperature_unit),
                "duration": _quantity(stage["duration"], "second"),
                "applicability": applicability,
            },
        })

    max_current = current / position_for("source_current_utilization",
                                         rng.uniform(0.3, 0.8))
    if withhold != "maximum_current":
        payload["source_ratings"] = {
            "maximum_current": _quantity(max_current, "ampere")}
    payload["coupling"] = {
        "seed_temperature": _quantity(stages[0]["t_amb"], "kelvin"),
        "tolerance": "1e-09 kelvin",
        "max_iterations": 300,
    }
    return payload


def _make_electrothermal(rng: random.Random, family: Family,
                         position: float | None) -> dict[str, Any] | None:
    target = family.target if family.kind == "threshold" else None
    withhold = family.target if family.kind == "missing" else None

    def position_for(name: str, clean: float) -> float:
        return position if (name == target and position is not None) else clean

    drawn = _draw_electrothermal(rng, position_for)
    if drawn is None:
        return None
    stages, source_v = drawn
    temperatures, current, converged = _et_fixed_point(stages, source_v)
    if not converged or not math.isfinite(current):
        return None
    return _et_payload(rng, stages, source_v, temperatures, current,
                       position_for, withhold, target)


# =====================================================================
# battery
# =====================================================================

def _make_battery(rng: random.Random, family: Family,
                  position: float | None) -> dict[str, Any] | None:
    """A cell and a duty, sized so the family's target is the only finding.

    **Everything here is sized against the state the march REACHES, not the
    state it starts in.** The cell self-heats and the state of charge falls,
    so a limit placed against the declared initial temperature is placed
    against a state the run leaves immediately. An earlier draft did exactly
    that and produced a corpus in which 112 of 120 cases were NOT_SUPPORTED --
    a tier that cannot detect a false reject because it has almost no
    admissible case in it. Four separate declarations were doing it:

    * ``polarization_time_constant`` drawn so the overpotential develops to
      2-22 % of its final value, which violates the 5 % neglect allowance at
      every value in that range except the bottom of it;
    * ``peukert_reference_current`` drawn on both sides of the operating
      current, so ``(I_ref/I)^(k-1)`` exceeded 1 whenever it was drawn above;
    * ``cutoff_voltage`` solved to sit EXACTLY at the cutoff state of charge,
      which lands the consistency margin at -2.2e-16 -- round-off, on the
      wrong side;
    * ``cell_thermal_conductance`` drawn independently of the dissipation, so
      the march climbed 699 K past a window declared 30 K wide.

    Each is now solved rather than drawn, and the case is refused by what its
    family placed.
    """
    target = family.target if family.kind == "threshold" else None
    withhold = family.target if family.kind == "missing" else None
    representation = family.kind == "representation"

    def place(name: str, clean: float) -> float:
        return position if (name == target and position is not None) else clean

    capacity = 10.0 ** rng.uniform(-1.0, 2.3)          # 0.1 Ah .. 200 Ah
    resistance = 10.0 ** rng.uniform(-3.3, -0.7)       # 0.5 mohm .. 200 mohm
    ocv_full = rng.uniform(3.4, 4.35)
    ocv_empty = ocv_full - rng.uniform(0.6, 1.6)
    efficiency = place("coulombic_efficiency", rng.uniform(0.90, 0.999))
    c_rate = 10.0 ** rng.uniform(-1.3, 0.7)            # 0.05 C .. 5 C
    current = c_rate * capacity
    steps = rng.choice([1, 4, 10, 25, 60])
    soc_0 = rng.uniform(0.55, 0.99)
    # THE DEPTH OF DISCHARGE IS CHOSEN AND THE STEP LENGTH IS SOLVED, not the
    # other way round. Drawn independently the march ran the state of charge
    # far below zero, and every declared window then had a negative lower edge
    # -- which `Load` refuses at construction, so 26 cases would have been
    # refused at the boundary against a truth that said otherwise.
    low_soc = soc_0 * rng.uniform(0.15, 0.90)
    drop_total = soc_0 - low_soc
    step_seconds = (drop_total * efficiency * capacity * 3600.0
                    / (current * steps))
    total_seconds = step_seconds * steps
    if not (1e-3 < step_seconds < 1e6):
        return None

    continuous_rating = c_rate / place("continuous_c_rate_utilization",
                                       rng.uniform(0.25, 0.8))

    # -- thermal: solve the conductance from a target rise ----------------
    # rise = I^2 R / G, so G is what places it. Drawn the other way round the
    # march leaves every declared temperature window at once.
    heat = current * current * resistance
    rise = rng.uniform(0.4, 12.0)
    rise_bound = rise / place("self_heating_rise_ratio", rng.uniform(0.15, 0.7))
    conductance = heat / rise
    heat_capacity = 10.0 ** rng.uniform(0.5, 3.2)
    temperature = rng.uniform(268.0, 318.0)
    # The march starts at ambient and approaches ambient + rise, so this is
    # the hottest state any condition is read at.
    tau_thermal = heat_capacity / conductance
    hottest = temperature + rise * (1.0 - math.exp(-total_seconds / tau_thermal))

    # -- the state-of-charge window ---------------------------------------
    #
    # `soc_window_margin` has a FLOOR at 0, not a ceiling at 1, so a position
    # on the ladder cannot be the value: position 3.0 would mean a margin of
    # 3, which is both impossible and *satisfied*, and the family would never
    # have refused anything. A floor is walked by mapping position p to
    # (1 - p) * scale, so p < 1 is a positive margin, p > 1 a negative one,
    # and p = 1 sits on the floor.
    drop_per_step = current * (step_seconds / 3600.0) / (efficiency * capacity)
    margin = (0.35 * (1.0 - position)
              if (target == "soc_window_margin" and position is not None)
              else rng.uniform(0.05, 0.40))
    margin = min(margin, 0.45)
    # margin = min(low - w_lo, w_hi - high) / (w_hi - w_lo). Putting the LOW
    # side on the minimum needs w_hi - high >= margin * span, which reduces to
    # span * (1 - 2 margin) >= drop. Below 0.5 that is solvable; at or above
    # it, it is not, which is why the cap above is 0.45.
    span = (drop_total / max(1.0 - 2.0 * margin, 1e-6)) * rng.uniform(1.1, 2.5)
    window_low = low_soc - margin * span
    window_high = window_low + span
    if not (0.0 <= window_low < window_high <= 1.0):
        return None

    # -- temperature-shaped limits, all against `hottest` -----------------
    t_low = temperature - rng.uniform(15.0, 45.0)
    t_span = (hottest - t_low) / place("discharge_temperature_position",
                                       rng.uniform(0.25, 0.8))
    t_high = t_low + t_span

    resistance_reference = temperature - rng.uniform(2.0, 30.0)
    resistance_span = (hottest - resistance_reference) / place(
        "internal_resistance_drift_ratio", rng.uniform(0.2, 0.8))
    capacity_reference = temperature - rng.uniform(2.0, 30.0)
    capacity_span = (hottest - capacity_reference) / place(
        "capacity_temperature_drift_ratio", rng.uniform(0.2, 0.8))
    peukert_reference_temperature = temperature - rng.uniform(2.0, 30.0)
    peukert_span = (hottest - peukert_reference_temperature) / place(
        "peukert_temperature_drift_ratio", rng.uniform(0.2, 0.8))

    # -- Peukert ----------------------------------------------------------
    # C_eff / C_ref = (I_ref / I)^(k-1) <= 1 requires I_ref <= I: the derating
    # law may not be read as PROMOTING capacity below the current its
    # reference was measured at. Drawn on both sides it violated on half the
    # corpus, and the violation said nothing about the case.
    decades_out = rng.uniform(0.05, 1.2)
    peukert_reference = current * 10.0 ** (-decades_out)
    decades = decades_out / place("peukert_extrapolation_ratio",
                                  rng.uniform(0.2, 0.75))

    # -- pulse, resolution, polarisation ----------------------------------
    pulse_seconds = 10.0 ** rng.uniform(0.0, 1.8)
    rated_pulse = pulse_seconds / place("pulse_duration_utilization",
                                        rng.uniform(0.2, 0.8))
    resolution = drop_per_step / place("soc_step_resolution_ratio",
                                       rng.uniform(0.2, 0.8))
    # min(developed, 1 - developed) <= 0.05 admits a barely-developed
    # overpotential and a fully-developed one. Only the first survives the
    # WHOLE march: a time constant short enough to finish developed passes
    # through 0.5 on the way, and the condition is read at every step.
    polarization_tau = total_seconds / rng.uniform(0.002, 0.045)

    ampere = "milliampere" if representation and rng.random() < 0.7 else "ampere"
    ah = ("milliampere_hour" if representation and rng.random() < 0.7
          else "ampere_hour")
    second = "minute" if representation and rng.random() < 0.5 else "second"
    kelvin = "degC" if representation and rng.random() < 0.7 else "kelvin"

    limits = {
        "continuous_discharge_c_rate": _quantity(continuous_rating / 3600.0, "1/hour"),
        "pulse_discharge_c_rate": _quantity(
            max(continuous_rating, c_rate) * rng.uniform(2.0, 8.0) / 3600.0, "1/hour"),
        "rated_pulse_duration": _quantity(rated_pulse, second),
        "usable_soc_minimum": _quantity(window_low, "dimensionless"),
        "usable_soc_maximum": _quantity(window_high, "dimensionless"),
        "minimum_discharge_temperature": _quantity(t_low, kelvin),
        "maximum_discharge_temperature": _quantity(t_high, kelvin),
        "resistance_reference_temperature": _quantity(resistance_reference, kelvin),
        "resistance_temperature_span": _quantity(resistance_span, "kelvin"),
        "cell_thermal_conductance": _quantity(conductance, "watt/kelvin"),
        "self_heating_rise_bound": _quantity(rise_bound, "kelvin"),
        "polarization_time_constant": _quantity(polarization_tau, second),
        "soc_step_resolution": _quantity(resolution, "dimensionless"),
        "capacity_reference_temperature": _quantity(capacity_reference, kelvin),
        "capacity_temperature_span": _quantity(capacity_span, "kelvin"),
        "peukert_exponent": _quantity(rng.uniform(1.0, 1.12), "dimensionless"),
        "peukert_reference_current": _quantity(peukert_reference, ampere),
        "peukert_fit_decades": _quantity(decades, "dimensionless"),
        "peukert_reference_temperature": _quantity(
            peukert_reference_temperature, kelvin),
        "peukert_temperature_span": _quantity(peukert_span, "kelvin"),
    }
    limits.pop(withhold, None)

    # cutoff_consistency_margin = z_declared - z_implied, and the oracle
    # inverts the same chord, so solving the voltage for a margin of exactly
    # zero lands it at -2.2e-16: round-off, on the wrong side of a floor. The
    # margin is therefore DRAWN and the voltage solved from it.
    cutoff_soc = max(0.0, window_low - rng.uniform(0.0, 0.05))
    consistency_margin = rng.uniform(0.01, 0.15)
    implied_soc = cutoff_soc - consistency_margin
    cutoff_voltage = (ocv_empty + (ocv_full - ocv_empty) * implied_soc
                      - current * resistance)
    return {
        "cell": {
            "cell_id": "C1",
            "nominal_capacity": _quantity(capacity, ah),
            "internal_resistance": _quantity(resistance, "ohm"),
            "open_circuit_voltage_at_full": _quantity(ocv_full, "volt"),
            "open_circuit_voltage_at_empty": _quantity(ocv_empty, "volt"),
            "coulombic_efficiency": _quantity(efficiency, "dimensionless"),
            "limits": limits,
        },
        "load": {
            "load_id": "L1",
            "discharge_current": _quantity(current, ampere),
            "state_of_charge": _quantity(soc_0, "dimensionless"),
            "cell_temperature": _quantity(temperature, kelvin),
            "duration": _quantity(step_seconds, second),
            "pulse_current": _quantity(current * rng.uniform(1.5, 4.0), ampere),
            "pulse_duration": _quantity(pulse_seconds, second),
            "cutoff_voltage": _quantity(cutoff_voltage, "volt"),
            "cutoff_state_of_charge": _quantity(cutoff_soc, "dimensionless"),
        },
        "thermal": {
            "heat_capacity": _quantity(heat_capacity, "joule/kelvin"),
            "ambient_temperature": _quantity(temperature, kelvin),
        },
        "march": {"steps": steps},
    }


# =====================================================================
# kinetics — CSTR model contract
# =====================================================================

MOLAR_GAS_CONSTANT = 8.314462618

_KINETICS_WITHHOLDABLE = (
    "heat_of_reaction", "density", "heat_capacity", "feed_concentration",
    "concentration", "feed_temperature", "coolant_temperature", "k0",
)


def _make_kinetics(rng: random.Random, family: Family,
                   position: float | None, index: int) -> dict[str, Any] | None:
    representation = family.kind == "representation"
    endothermic = family.family_id == "kin.endothermic"

    density = rng.uniform(600.0, 1600.0)
    heat_capacity = rng.uniform(150.0, 4200.0)
    feed_concentration = 10.0 ** rng.uniform(1.0, 3.4)
    concentration = 10.0 ** rng.uniform(1.0, 3.4)
    richest = max(feed_concentration, concentration)
    feed_temperature = rng.uniform(265.0, 420.0)
    coolant_temperature = rng.uniform(255.0, 400.0)
    temperature = rng.uniform(265.0, 430.0)
    k0 = 10.0 ** rng.uniform(4.0, 13.0)
    activation = rng.uniform(3.0e4, 1.3e5)
    residence = 10.0 ** rng.uniform(0.3, 4.0)

    if endothermic:
        enthalpy = 10.0 ** rng.uniform(3.0, 5.2)   # positive: absorbs heat
    else:
        # Solve the enthalpy that puts the derived ceiling at its position
        # against the 1000 K scope bound:  T_hot + beta C_max = 1000 * position
        hottest = max(temperature, feed_temperature, coolant_temperature)
        share = position if position is not None else rng.uniform(0.45, 0.85)
        rise = 1000.0 * share - hottest
        if rise <= 0.0:
            return None
        enthalpy = -rise * density * heat_capacity / richest

    if family.family_id == "kin.envelope" and position is not None:
        # Walk the DECLARED initial temperature across the [250, 1000] window's
        # lower edge. The constructor refuses before the condition can fire,
        # and that asymmetry is the point of the family.
        temperature = 250.0 * position
        hottest = max(temperature, feed_temperature, coolant_temperature)
        rise = 1000.0 * rng.uniform(0.4, 0.7) - hottest
        if rise <= 0.0:
            return None
        enthalpy = -rise * density * heat_capacity / richest

    if family.family_id == "kin.positivity":
        which = index % 4
        if which == 0:
            k0 = 0.0 if index < 4 else -abs(k0)
        elif which == 1:
            activation = -abs(activation)
        elif which == 2:
            residence = 0.0 if index < 4 else -abs(residence)
        else:
            concentration = -abs(concentration)

    energy = "kilojoule/mole" if representation else "joule/mole"
    conc = "mole/liter" if representation else "mole/meter**3"
    second = "minute" if representation else "second"
    kelvin = "degC" if representation else "kelvin"

    payload = {
        "temperature": _quantity(temperature, kelvin),
        "concentration": _quantity(concentration, conc),
        "k0": _quantity(k0, "1/second"),
        "activation_energy": _quantity(activation, energy),
        "heat_of_reaction": _quantity(enthalpy, energy),
        "density": _quantity(density, "kilogram/meter**3"),
        "heat_capacity": _quantity(heat_capacity, "joule/kilogram/kelvin"),
        "feed_concentration": _quantity(feed_concentration, conc),
        "feed_temperature": _quantity(feed_temperature, kelvin),
        "coolant_temperature": _quantity(coolant_temperature, kelvin),
        "residence_time": _quantity(residence, second),
        # Carried so the runner can rebuild the reactor; not read by any
        # condition, and the oracle never looks at it.
        "reactor_volume": _quantity(10.0 ** rng.uniform(-2.0, 0.6), "meter**3"),
        "ua": _quantity(rng.uniform(0.0, 2000.0), "watt/kelvin"),
        "end_time": _quantity(residence * rng.uniform(4.0, 30.0), "second"),
    }
    if family.kind == "missing":
        payload.pop(_KINETICS_WITHHOLDABLE[index % len(_KINETICS_WITHHOLDABLE)],
                    None)
    return payload


# =====================================================================
# conduction — realization applicability
# =====================================================================

def _make_conduction(rng: random.Random, family: Family,
                     position: float | None, index: int) -> dict[str, Any] | None:
    representation = family.kind == "representation"
    implicit = family.family_id == "cond.implicit"

    length = 10.0 ** rng.uniform(-3.0, 1.0)
    alpha = 10.0 ** rng.uniform(-8.0, -3.0)
    n_cells = [4, 8, 10, 16, 20, 32, 50, 64, 100][index % 9]
    n_steps = int(10.0 ** rng.uniform(0.3, 3.6))
    dx = length / n_cells

    if family.family_id == "cond.alpha":
        alpha = 0.0 if index % 2 == 0 else -abs(alpha)
        end_time = 10.0 ** rng.uniform(0.0, 3.0)
    else:
        # r = alpha dt / dx^2, and the FTCS limit is r <= 1/2, so a POSITION of
        # p means r = 0.5 p. Solve the end time.
        share = position if position is not None else rng.uniform(0.05, 0.8)
        end_time = 0.5 * share * dx * dx * n_steps / alpha

    metre = "millimeter" if representation else "meter"
    second = "minute" if representation else "second"
    return {
        "length": _quantity(length, metre),
        "diffusivity": _quantity(alpha, "meter**2/second"),
        "end_time": _quantity(end_time, second),
        "n_cells": n_cells,
        "n_steps": max(n_steps, 1),
        "realization": ("thermal.conduction1d.implicit_backward_euler" if implicit
                        else "thermal.conduction1d.explicit_forward_euler"),
    }


# =====================================================================
# malformed payloads — the boundary's own claim
# =====================================================================

_MALFORMATIONS = (
    ("absent_unit", "a magnitude with no unit is not a declaration"),
    ("wrong_dimension", "a resistance declared in volts"),
    ("unknown_field", "a field the schema does not name"),
    ("non_finite", "a magnitude that is not a number"),
    ("negative_absolute_temperature", "below absolute zero"),
    ("missing_required_field", "a required declaration removed entirely"),
    ("empty_stages", "a circuit with no components"),
    ("string_for_number", "prose where a magnitude belongs"),
)


def _malform(payload: dict[str, Any], kind: str, system: str) -> dict[str, Any]:
    """Break one thing about an otherwise valid payload."""
    if system == "electrothermal":
        stage = payload["stages"][0] if payload.get("stages") else None
        if kind == "absent_unit":
            payload["source_voltage"] = "12.0"
        elif kind == "wrong_dimension" and stage:
            stage["conductor"]["reference_resistance"] = "5.0 volt"
        elif kind == "unknown_field" and stage:
            stage["body"]["applicability"]["unsanctioned_group"] = "1.0 dimensionless"
        elif kind == "non_finite":
            payload["source_voltage"] = "nan volt"
        elif kind == "negative_absolute_temperature" and stage:
            stage["body"]["ambient_temperature"] = "-40.0 kelvin"
        elif kind == "missing_required_field" and stage:
            stage["body"].pop("heat_capacity", None)
        elif kind == "empty_stages":
            payload["stages"] = []
        elif kind == "string_for_number" and stage:
            stage["body"]["duration"] = "quite a while second"
        return payload
    # battery
    if kind == "absent_unit":
        payload["cell"]["nominal_capacity"] = "2.5"
    elif kind == "wrong_dimension":
        payload["cell"]["internal_resistance"] = "0.03 volt"
    elif kind == "unknown_field":
        payload["cell"]["limits"]["unsanctioned_limit"] = "1.0 dimensionless"
    elif kind == "non_finite":
        payload["load"]["discharge_current"] = "inf ampere"
    return payload


# =====================================================================
# the driver
# =====================================================================

_MAKERS: dict[str, Callable[..., dict[str, Any] | None]] = {
    "electrothermal": _make_electrothermal,
    "battery": _make_battery,
}


def generate_corpus() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Every case, and every rejection, in family order.

    Returns ``(cases, rejections)``. A case carries its payload, its family,
    its intended target and position, and NOTHING about what the answer is.
    A rejection carries the documented scientific reason it was not admitted;
    Phase 1E allows generation-time rejection only for an invalid sampled
    state, an oracle that does not converge, an ambiguous truth, or a
    declaration outside the current model definition — never because a case
    looked hard.
    """
    cases: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []

    for family in ALL_FAMILIES:
        for index in range(family.count):
            case_id = f"{family.system[:3].upper()}{len(cases):05d}"
            rng = random.Random(seed_for(family.system, family.family_id, index))
            position: float | None = None
            intended = ""
            if family.kind == "threshold" and family.target is not None:
                position, intended = POSITION_LADDER[index % len(POSITION_LADDER)]
            elif family.kind == "threshold":
                intended = "FAR_OUTSIDE"

            payload: dict[str, Any] | None
            attempts = 0
            while True:
                attempts += 1
                if family.system == "electrothermal":
                    payload = _make_electrothermal(rng, family, position)
                elif family.system == "battery":
                    payload = _make_battery(rng, family, position)
                elif family.system == "kinetics_cstr":
                    payload = _make_kinetics(rng, family, position, index)
                else:
                    payload = _make_conduction(rng, family, position, index)
                if payload is not None or attempts >= 40:
                    break

            if payload is None:
                rejections.append({
                    "family": family.family_id,
                    "index": index,
                    "reason": "invalid_sampled_state",
                    "detail": "no draw in 40 attempts produced a design whose "
                              "fixed point converges at the requested placement",
                })
                continue

            if family.kind == "malformed":
                kind, note = _MALFORMATIONS[index % len(_MALFORMATIONS)]
                payload = _malform(payload, kind, family.system)
                intended = "MALFORMED"

            cases.append({
                "id": case_id,
                "system": family.system,
                "family": family.family_id,
                "family_kind": family.kind,
                "target": family.target,
                "intended_position": position,
                "intended_stratum": intended,
                "payload": payload,
            })
    return cases, rejections
