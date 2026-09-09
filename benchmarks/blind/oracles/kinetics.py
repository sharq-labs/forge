"""Independent oracle for the non-isothermal CSTR. No Forge code is reached.

The reactor is

    dC/dt = a (C_f - C) - k(T) C,          k(T) = k0 exp(-E / R T)
    dT/dt = a (T_f - T) + beta k(T) C - gamma (T - T_c)

with ``a = 1 / residence_time``, ``beta = (-dH) / (rho cp)`` the adiabatic
temperature rise per unit concentration, and ``gamma`` the jacket coupling.

**Two oracles, and they answer different questions.**

``evaluate`` is the analytic one: it forms the model's six declared conditions
in closed form, including the adiabatic ceiling, whose derivation is reproduced
below rather than taken on trust.

``integrate_ceiling`` is the second, independent one: it integrates the system
with a fixed-step RK4 written here and reports the hottest temperature the
trajectory actually reaches. It exists to falsify the analytic ceiling. The
ceiling is an upper bound, so the only outcome that convicts it is a
trajectory that EXCEEDS it -- a trajectory that stays well below is the bound
being conservative, which is what it claims to be. That asymmetry is why the
two are not averaged and why a disagreement is recorded rather than resolved.

Sources: Fogler, *Elements of Chemical Reaction Engineering*, 4th ed., Ch. 8-9
for the non-isothermal CSTR energy balance; the ceiling derivation is the
invariant ``Z = T + beta C`` argument stated in the model record.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .electrothermal import ConditionValue, OracleUnresolved
from .units import to_si

__all__ = ["ORACLE_ID", "ORACLE_VERSION", "SECOND_ORACLE_ID", "BOUNDS",
           "CSTRTruth", "evaluate", "integrate_ceiling",
           "construction_refusal"]

ORACLE_ID = "blind.oracle.kinetics.cstr.analytic"
SECOND_ORACLE_ID = "blind.oracle.kinetics.cstr.rk4"
ORACLE_VERSION = "1.0.0"

#: CODATA 2018, written out rather than shared with the runtime.
MOLAR_GAS_CONSTANT = 8.314462618  # J mol^-1 K^-1

MODEL_ID = "kinetics.cstr.nonisothermal_first_order"

BOUNDS: dict[str, tuple[float | None, float | None, bool, bool]] = {
    "temperature": (250.0, 1000.0, True, True),
    "concentration": (0.0, None, True, True),
    "k0": (0.0, None, False, True),
    "activation_energy": (0.0, None, True, True),
    "residence_time": (0.0, None, False, True),
    "adiabatic_ceiling_temperature": (None, 1000.0, True, True),
}

CONDITION_DOMAIN = {name: "kinetics" for name in BOUNDS}


@dataclass(frozen=True)
class CSTRTruth:
    verdict: str
    conditions: tuple[ConditionValue, ...]
    state: dict

    @property
    def satisfied(self) -> tuple[str, ...]:
        return tuple(f"{c.model_id}::{c.name}" for c in self.conditions
                     if c.status == "satisfied")

    @property
    def violated(self) -> tuple[str, ...]:
        return tuple(f"{c.model_id}::{c.name}" for c in self.conditions
                     if c.status == "violated")

    @property
    def unknown(self) -> tuple[str, ...]:
        return tuple(f"{c.model_id}::{c.name}" for c in self.conditions
                     if c.status == "unknown")

    @property
    def primary_domain(self) -> str:
        return "kinetics"

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return ()


def _classify(name: str, value: float | None) -> ConditionValue:
    if value is None:
        return ConditionValue(name, MODEL_ID, None, "unknown", None, None,
                              "not_supplied")
    if not math.isfinite(value):
        return ConditionValue(name, MODEL_ID, value, "violated", None, None)
    minimum, maximum, min_incl, max_incl = BOUNDS[name]
    ok = True
    margin = position = None
    if minimum is not None:
        ok = ok and (value >= minimum if min_incl else value > minimum)
        margin = value - minimum
        position = value / minimum if minimum else value
    if maximum is not None:
        ok = ok and (value <= maximum if max_incl else value < maximum)
        upper = maximum - value
        margin = upper if margin is None else min(margin, upper)
        upper_position = value / maximum if maximum else value
        position = upper_position if position is None else max(position, upper_position)
    return ConditionValue(name, MODEL_ID, value,
                          "satisfied" if ok else "violated", margin, position)


def _q(payload: dict, key: str, dimension: str) -> float | None:
    raw = payload.get(key)
    return None if raw is None else to_si(raw, dimension)


def adiabatic_ceiling(declared: dict) -> float | None:
    """``T_ceiling = max(T_0, T_f, T_c) + beta max(C_A0, C_Af)``.

    **Why it is an upper bound.** The reactor has the exact invariant
    ``Z = T + beta C``, obeying ``dZ/dt = a (Z_f - Z) - gamma (T - T_c)``.
    With ``gamma = 0`` this integrates exactly and ``Z`` stays between ``Z_0``
    and ``Z_f``; since ``C >= 0`` and ``beta > 0`` for an exothermic reaction,
    ``T = Z - beta C <= Z``, so ``T <= max(Z_0, Z_f)``. With cooling, bounding
    the jacket term by ``gamma (T_c + beta C_max - Z)`` gives
    ``dZ/dt <= (a + gamma)(U - Z)`` with ``U = max(Z_f, T_c + beta C_max)``,
    hence ``T <= Z <= max(Z_0, Z_f, T_c + beta C_max)``. Each of those three is
    at most ``max(T_0, T_f, T_c) + beta C_max``, which is what is returned, and
    ``C <= C_max = max(C_A0, C_Af)`` follows from the species balance directly.

    Returns ``None`` when any term is undeclared -- never a zero, never a
    typical value, so the condition reading it is UNKNOWN rather than clean.
    """
    heat_of_reaction = declared.get("heat_of_reaction")
    density = declared.get("density")
    heat_capacity = declared.get("heat_capacity")
    if heat_of_reaction is None or not density or not heat_capacity:
        return None
    # EVERY term, or nothing. The bound is a maximum over three declared
    # temperatures and two declared concentrations, and a maximum taken over a
    # subset is not a smaller bound -- it is a bound on a different reactor.
    # An absent term therefore makes the ceiling underivable, which is what
    # leaves its condition UNKNOWN. Taking the max over whatever happened to be
    # declared would manufacture a ceiling that could be exceeded by the very
    # state the missing declaration names.
    temperatures = [declared.get(name) for name in
                    ("temperature", "feed_temperature", "coolant_temperature")]
    concentrations = [declared.get(name) for name in
                      ("concentration", "feed_concentration")]
    if any(t is None for t in temperatures):
        return None
    if any(c is None for c in concentrations):
        return None
    beta = (-heat_of_reaction) / (density * heat_capacity)
    # An ENDOTHERMIC reaction has beta <= 0 and can only cool the tank, so the
    # rise term is clamped at zero rather than allowed to pull the ceiling
    # below a temperature the reactor is demonstrably fed at. A ceiling under
    # the feed temperature would be a bound the initial state already breaks.
    rise = beta * max(concentrations)
    return max(temperatures) + max(rise, 0.0)


#: The reactor's declared construction envelope, transcribed from the record's
#: own guards. These are NOT validity conditions: a declaration outside them is
#: refused when the reactor is BUILT, so the case never reaches an assessment
#: and its truth is a rejection rather than a verdict.
#:
#: This distinction is the whole reason the channel exists. ``temperature`` is
#: a declared condition of the model with a [250, 1000] K range, and the
#: constructor rejects all three declared temperatures against that same range
#: first -- so the condition can never be VIOLATED through the ordinary
#: construction path. An oracle that only knew the condition would predict
#: NOT_SUPPORTED for every out-of-envelope reactor and be wrong about every one
#: of them.
CONSTRUCTION_MIN_TEMPERATURE_K = 250.0
CONSTRUCTION_MAX_TEMPERATURE_K = 1000.0


def construction_refusal(payload: dict) -> str | None:
    """Why this declaration cannot be built into a reactor, or ``None``.

    A CONTRACT_ONLY truth: it follows from the declared envelope and the
    record's own guards, not from the world. Order matters and is the record's
    order -- chemistry, then operation, then the run -- because the first
    refusal is the one a caller sees.
    """
    def q(key, dimension):
        raw = payload.get(key)
        return None if raw is None else to_si(raw, dimension)

    # -- chemistry -----------------------------------------------------
    k0 = q("k0", "1/s")
    if k0 is not None and not (k0 > 0.0):
        return "k0_not_positive"
    activation = q("activation_energy", "J/mol")
    if activation is not None and activation < 0.0:
        return "activation_energy_negative"
    enthalpy = q("heat_of_reaction", "J/mol")
    if enthalpy is not None and not math.isfinite(enthalpy):
        return "heat_of_reaction_not_finite"
    density = q("density", "kg/m3")
    if density is not None and not (density > 0.0):
        return "density_not_positive"
    heat_capacity = q("heat_capacity", "J/kg/K")
    if heat_capacity is not None and not (heat_capacity > 0.0):
        return "heat_capacity_not_positive"

    # -- operation -----------------------------------------------------
    residence = q("residence_time", "s")
    if residence is not None and not (residence > 0.0):
        return "residence_time_not_positive"
    feed_concentration = q("feed_concentration", "mol/m3")
    if feed_concentration is not None and feed_concentration < 0.0:
        return "feed_concentration_negative"
    for key, label in (("feed_temperature", "feed_temperature"),
                       ("coolant_temperature", "coolant_temperature"),
                       ("temperature", "initial_temperature")):
        value = q(key, "K")
        if value is None:
            continue
        if not math.isfinite(value):
            return f"{label}_not_finite"
        if value <= 0.0:
            return f"{label}_not_absolute"
        if not (CONSTRUCTION_MIN_TEMPERATURE_K <= value
                <= CONSTRUCTION_MAX_TEMPERATURE_K):
            return f"{label}_outside_envelope"
    concentration = q("concentration", "mol/m3")
    if concentration is not None and concentration < 0.0:
        return "initial_concentration_negative"
    return None


def evaluate(payload: dict) -> CSTRTruth:
    """Independent truth for one CSTR declaration."""
    declared = {
        "temperature": _q(payload, "temperature", "K"),
        "concentration": _q(payload, "concentration", "mol/m3"),
        "k0": _q(payload, "k0", "1/s"),
        "activation_energy": _q(payload, "activation_energy", "J/mol"),
        "heat_of_reaction": _q(payload, "heat_of_reaction", "J/mol"),
        "density": _q(payload, "density", "kg/m3"),
        "heat_capacity": _q(payload, "heat_capacity", "J/kg/K"),
        "feed_concentration": _q(payload, "feed_concentration", "mol/m3"),
        "feed_temperature": _q(payload, "feed_temperature", "K"),
        "coolant_temperature": _q(payload, "coolant_temperature", "K"),
        "residence_time": _q(payload, "residence_time", "s"),
    }
    refusal = construction_refusal(payload)
    if refusal is not None:
        # The declaration never becomes a reactor, so no condition is assessed
        # and the truth is the refusal itself. Reported as a verdict of its own
        # rather than folded into NOT_SUPPORTED: a refused declaration and an
        # assessed-and-rejected one are different findings with different
        # repairs, and a comparison that merged them could not tell a boundary
        # that held from a condition that fired.
        return CSTRTruth(verdict="REJECTED_AT_BOUNDARY", conditions=(),
                         state={"construction_refusal": refusal})
    ceiling = adiabatic_ceiling(declared)
    conditions = tuple(
        _classify(name, ceiling if name == "adiabatic_ceiling_temperature"
                  else declared.get(name))
        for name in BOUNDS
    )
    if any(c.status == "violated" for c in conditions):
        verdict = "NOT_SUPPORTED"
    elif any(c.status == "unknown" for c in conditions):
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "SUPPORTED"
    beta = None
    if (declared["heat_of_reaction"] is not None and declared["density"]
            and declared["heat_capacity"]):
        beta = (-declared["heat_of_reaction"]) / (declared["density"]
                                                  * declared["heat_capacity"])
    return CSTRTruth(verdict=verdict, conditions=conditions, state={
        "adiabatic_ceiling_k": ceiling, "beta_k_per_mol_m3": beta,
    })


def integrate_ceiling(payload: dict, *, steps: int = 20000,
                      horizon_residence_times: float = 40.0) -> dict:
    """SECOND ORACLE. Integrate the reactor and report the hottest state.

    Fixed-step RK4, written here, sharing nothing with the analytic bound above
    except the equations it is a bound on. Returns the peak temperature reached
    and whether it exceeded the analytic ceiling -- which is the only way the
    ceiling can be shown wrong.

    The horizon is a multiple of the residence time rather than a fixed number
    of seconds: the reactor's own relaxation is what sets when the trajectory
    has stopped moving, and a fixed horizon would be long for one draw and
    short for the next.
    """
    declared = {
        "temperature": _q(payload, "temperature", "K"),
        "concentration": _q(payload, "concentration", "mol/m3"),
        "k0": _q(payload, "k0", "1/s"),
        "activation_energy": _q(payload, "activation_energy", "J/mol"),
        "heat_of_reaction": _q(payload, "heat_of_reaction", "J/mol"),
        "density": _q(payload, "density", "kg/m3"),
        "heat_capacity": _q(payload, "heat_capacity", "J/kg/K"),
        "feed_concentration": _q(payload, "feed_concentration", "mol/m3"),
        "feed_temperature": _q(payload, "feed_temperature", "K"),
        "coolant_temperature": _q(payload, "coolant_temperature", "K"),
        "residence_time": _q(payload, "residence_time", "s"),
    }
    needed = ("temperature", "concentration", "k0", "activation_energy",
              "heat_of_reaction", "density", "heat_capacity",
              "feed_concentration", "feed_temperature", "residence_time")
    if any(declared[name] is None for name in needed):
        return {"status": "not_integrable",
                "missing": [n for n in needed if declared[n] is None]}
    if not declared["residence_time"] or declared["residence_time"] <= 0.0:
        return {"status": "not_integrable", "missing": ["residence_time"]}

    a = 1.0 / declared["residence_time"]
    beta = (-declared["heat_of_reaction"]) / (declared["density"]
                                              * declared["heat_capacity"])
    e_over_r = declared["activation_energy"] / MOLAR_GAS_CONSTANT
    k0 = declared["k0"]
    c_feed = declared["feed_concentration"]
    t_feed = declared["feed_temperature"]
    t_cool = declared.get("coolant_temperature")
    # No jacket is declared in this challenge's reactors, so gamma is zero and
    # the trajectory is the adiabatic-with-flow case the bound is tightest on.
    gamma = 0.0

    def derivative(c: float, t: float) -> tuple[float, float]:
        rate = k0 * math.exp(-e_over_r / t) * c if t > 0.0 else 0.0
        dc = a * (c_feed - c) - rate
        dt = a * (t_feed - t) + beta * rate
        if t_cool is not None:
            dt -= gamma * (t - t_cool)
        return dc, dt

    horizon = horizon_residence_times * declared["residence_time"]
    h = horizon / steps
    c, t = declared["concentration"], declared["temperature"]
    peak = t
    for _ in range(steps):
        k1c, k1t = derivative(c, t)
        k2c, k2t = derivative(c + 0.5 * h * k1c, t + 0.5 * h * k1t)
        k3c, k3t = derivative(c + 0.5 * h * k2c, t + 0.5 * h * k2t)
        k4c, k4t = derivative(c + h * k3c, t + h * k3t)
        c = c + (h / 6.0) * (k1c + 2 * k2c + 2 * k3c + k4c)
        t = t + (h / 6.0) * (k1t + 2 * k2t + 2 * k3t + k4t)
        if not (math.isfinite(c) and math.isfinite(t)):
            return {"status": "diverged", "peak_temperature_k": peak}
        # A FIXED-STEP EXPLICIT INTEGRATOR ON A STIFF EXOTHERMIC REACTOR
        # OVERSHOOTS, and the overshoot leaves the region the bound was proved
        # over: the proof needs C >= 0, and an RK4 step that drives the
        # concentration negative or the temperature through absolute zero has
        # left the reactor rather than found a hotter one. Reporting such a
        # trajectory as a ceiling violation would convict a theorem with a
        # numerical artefact, so the march says it diverged and the analytic
        # bound stands. A REAL counterexample is a trajectory that stays
        # physical and still goes past the ceiling.
        if t <= 0.0 or c < -1e-9 * max(abs(c_feed), 1.0):
            return {"status": "diverged",
                    "why": "the explicit march left the physical region the "
                           "analytic bound is proved over",
                    "peak_temperature_k": peak,
                    "concentration_at_exit_mol_m3": c,
                    "temperature_at_exit_k": t}
        peak = max(peak, t)
    ceiling = adiabatic_ceiling(declared)
    return {
        "status": "integrated",
        "peak_temperature_k": peak,
        "final_temperature_k": t,
        "final_concentration_mol_m3": c,
        "analytic_ceiling_k": ceiling,
        "ceiling_respected": None if ceiling is None else peak <= ceiling + 1e-6,
    }
