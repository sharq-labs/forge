"""Independent oracle for the battery system. No Forge code is reached.

A second implementation of the four battery claims' validity conditions and of
the state they are evaluated at. Same discipline as
:mod:`oracles.electrothermal`: the contract (what each condition means, which
instant it is read at) is taken from the model records, the arithmetic is
written here from the cited sources, and nothing imports ``engcore``.

Sources:

* Plett, *Battery Management Systems, Volume I: Battery Modeling* (Artech
  House, 2015) — Ch. 2 (coulomb counting), Ch. 3 (the Rint equivalent circuit).
* Peukert, W. (1897) — ``I^k t = constant``, written here as a capacity
  referred to the current the nominal capacity was measured at.
* Doerffel & Sharkh (2006), *J. Power Sources* 155, 395-400 — the temperature
  dependence of an extracted Peukert exponent.
* Incropera, DeWitt, Bergman & Lavine, 6th ed. (2007), Sec. 5.3 — the steady
  lumped rise ``Q / hA`` behind the self-heating condition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .electrothermal import ConditionValue, OracleUnresolved, _deciding
from .units import to_si

__all__ = ["ORACLE_ID", "ORACLE_VERSION", "BatteryTruth", "evaluate", "BOUNDS"]

ORACLE_ID = "blind.oracle.battery.analytic"
ORACLE_VERSION = "1.0.0"

BOUNDS: dict[str, tuple[float | None, float | None, bool, bool]] = {
    "nominal_capacity": (0.0, None, False, True),
    "internal_resistance": (0.0, None, False, True),
    "coulombic_efficiency": (0.0, 1.0, False, True),
    "cutoff_consistency_margin": (0.0, None, True, True),
    "continuous_c_rate_utilization": (None, 1.0, True, True),
    "pulse_c_rate_utilization": (None, 1.0, True, True),
    "pulse_duration_utilization": (None, 1.0, True, True),
    "soc_window_margin": (0.0, None, True, True),
    "soc_step_resolution_ratio": (None, 1.0, True, True),
    "capacity_temperature_drift_ratio": (None, 1.0, True, True),
    "discharge_temperature_position": (0.0, 1.0, True, True),
    "internal_resistance_drift_ratio": (None, 1.0, True, True),
    "self_heating_rise_ratio": (None, 1.0, True, True),
    "polarization_unmodelled_fraction": (None, 0.05, True, True),
    "terminal_voltage_ratio": (0.0, None, False, True),
    "peukert_extrapolation_ratio": (None, 1.0, True, True),
    "peukert_capacity_ratio": (None, 1.0, True, True),
    "peukert_temperature_drift_ratio": (None, 1.0, True, True),
}

#: The four battery claims and the conditions each declares. A condition name
#: appearing under two models is assessed under both, exactly as the records do.
MODEL_CONDITIONS: dict[str, tuple[str, ...]] = {
    "battery.cell.constant_current_runtime": (
        "cutoff_consistency_margin", "continuous_c_rate_utilization",
        "soc_window_margin"),
    "battery.cell.coulomb_counting": (
        "nominal_capacity", "coulombic_efficiency", "soc_step_resolution_ratio",
        "capacity_temperature_drift_ratio", "soc_window_margin"),
    "battery.cell.peukert_capacity_derating": (
        "peukert_extrapolation_ratio", "peukert_capacity_ratio",
        "peukert_temperature_drift_ratio"),
    "battery.cell.rint_ocv": (
        "nominal_capacity", "internal_resistance",
        "continuous_c_rate_utilization", "pulse_c_rate_utilization",
        "pulse_duration_utilization", "soc_window_margin",
        "discharge_temperature_position", "internal_resistance_drift_ratio",
        "self_heating_rise_ratio", "polarization_unmodelled_fraction",
        "terminal_voltage_ratio"),
}

CONDITION_DOMAIN = {name: "battery" for names in MODEL_CONDITIONS.values()
                    for name in names}


@dataclass(frozen=True)
class BatteryTruth:
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
        return "battery"

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return ()


def _classify(name: str, value: float | None, model_id: str) -> ConditionValue:
    """As :func:`oracles.electrothermal._classify`, over this domain's bounds.

    No battery condition is a conservative screen, so outside is outside here
    and the branch that weakens one is deliberately absent rather than copied.
    """
    if value is None:
        return ConditionValue(name, model_id, None, "unknown", None, None,
                              "not_supplied")
    if not math.isfinite(value):
        return ConditionValue(name, model_id, value, "violated", None, None)
    minimum, maximum, min_incl, max_incl = BOUNDS[name]
    ok = True
    margin: float | None = None
    position: float | None = None
    if minimum is not None:
        ok = ok and (value >= minimum if min_incl else value > minimum)
        margin = value - minimum
        position = value / minimum if minimum != 0.0 else value
    if maximum is not None:
        ok = ok and (value <= maximum if max_incl else value < maximum)
        upper = maximum - value
        margin = upper if margin is None else min(margin, upper)
        upper_position = value / maximum if maximum != 0.0 else value
        position = upper_position if position is None else max(position, upper_position)
    return ConditionValue(name, model_id, value,
                          "satisfied" if ok else "violated", margin, position)


def _q(section: dict, key: str, dimension: str) -> float | None:
    raw = section.get(key)
    return None if raw is None else to_si(raw, dimension)


def evaluate(payload: dict) -> BatteryTruth:
    """Independent truth for one battery case."""
    cell = payload["cell"]
    load = payload["load"]
    thermal = payload.get("thermal", {})
    march = payload.get("march", {})
    limits = cell.get("limits", {})

    q_nom = _q(cell, "nominal_capacity", "Ah")
    r_int = _q(cell, "internal_resistance", "ohm")
    ocv_full = _q(cell, "open_circuit_voltage_at_full", "V")
    ocv_empty = _q(cell, "open_circuit_voltage_at_empty", "V")
    efficiency = _q(cell, "coulombic_efficiency", "1")

    current = _q(load, "discharge_current", "A")
    soc_0 = _q(load, "state_of_charge", "1")
    temperature = _q(load, "cell_temperature", "K")
    duration = _q(load, "duration", "s")
    pulse_current = _q(load, "pulse_current", "A")
    pulse_duration = _q(load, "pulse_duration", "s")
    cutoff_v = _q(load, "cutoff_voltage", "V")
    cutoff_soc = _q(load, "cutoff_state_of_charge", "1")

    if q_nom is None or q_nom <= 0.0:
        raise OracleUnresolved("invalid_sampled_state",
                               "nominal capacity is absent or non-positive")
    if current is None or duration is None or soc_0 is None:
        raise OracleUnresolved("outside_supported_model",
                               "the duty does not declare current, duration "
                               "and an initial state of charge")

    # ---- the march ----------------------------------------------------
    # The battery boundary does NOT evaluate one operating point. It marches
    # `steps` steps, each of length `load.duration`, and every condition is
    # asked at BOTH ends of every step. A condition violated at any instant of
    # any step is violated for the run.
    #
    # Getting this wrong is not a rounding difference. An oracle that assessed
    # only the declared initial state would miss the whole point of a
    # self-heating discharge: the state of charge falls monotonically and the
    # cell warms toward its own steady rise, so the conditions that bite are
    # the ones at the END of the march. An earlier form of this oracle did
    # exactly that and called 31 of the 400 calibration cases SUPPORTED that
    # are not.
    steps = int(march.get("steps", 1) or 1)
    conductance = _q(limits, "cell_thermal_conductance", "W/K")
    heat_capacity = _q(thermal, "heat_capacity", "J/K")
    ambient = _q(thermal, "ambient_temperature", "K")
    heat = None if r_int is None else current * current * r_int

    def ocv_at(z: float) -> float | None:
        """OCV(z) on the affine chord between the two declared endpoints."""
        if ocv_empty is None or ocv_full is None:
            return None
        return ocv_empty + (ocv_full - ocv_empty) * z

    def step_drop() -> float | None:
        if efficiency is None or efficiency <= 0.0:
            return None
        return (current * (duration / 3600.0)) / (efficiency * q_nom)

    drop = step_drop()

    def advance(temperature_k: float) -> float:
        """One lumped thermal step, integrated exactly (Incropera Eq. 5.6)."""
        if (heat is None or conductance is None or conductance <= 0.0
                or heat_capacity is None or heat_capacity <= 0.0
                or ambient is None):
            return temperature_k
        asymptote = ambient + heat / conductance
        tau_thermal = heat_capacity / conductance
        return asymptote + (temperature_k - asymptote) * math.exp(-duration / tau_thermal)

    def _values_at(soc: float, temp: float, elapsed_s: float) -> dict:
        """Every quantity a condition is stated over, at one instant.

        The state of charge is the step's START value at both instants -- only
        the temperature differs between them -- and ``final_soc`` is derived
        from it over ONE step's duration, which is what the step-local
        conditions are about. ``elapsed_s`` is cumulative and is what the
        polarization condition reads, because an overpotential develops over
        the whole time under load rather than over the current step.
        """
        out: dict[str, float | None] = {}
        final_soc = None if drop is None else soc - drop
        low = None if final_soc is None else min(soc, final_soc)
        high = None if final_soc is None else max(soc, final_soc)
        worst_ocv = None if low is None else ocv_at(low)
        terminal = (None if (worst_ocv is None or r_int is None)
                    else worst_ocv - current * r_int)

        out["nominal_capacity"] = q_nom
        out["internal_resistance"] = r_int
        out["coulombic_efficiency"] = efficiency

        rate = current / q_nom
        continuous_rating = _q(limits, "continuous_discharge_c_rate", "1/s")
        continuous_rating = (None if continuous_rating is None
                             else continuous_rating * 3600.0)
        out["continuous_c_rate_utilization"] = (
            None if not continuous_rating else abs(rate) / continuous_rating)

        pulse_rating = _q(limits, "pulse_discharge_c_rate", "1/s")
        pulse_rating = None if pulse_rating is None else pulse_rating * 3600.0
        out["pulse_c_rate_utilization"] = (
            None if (pulse_current is None or not pulse_rating)
            else abs(pulse_current / q_nom) / pulse_rating)

        rated_pulse = _q(limits, "rated_pulse_duration", "s")
        out["pulse_duration_utilization"] = (
            None if (pulse_duration is None or not rated_pulse)
            else pulse_duration / rated_pulse)

        w_lo = _q(limits, "usable_soc_minimum", "1")
        w_hi = _q(limits, "usable_soc_maximum", "1")
        out["soc_window_margin"] = (
            None if (low is None or w_lo is None or w_hi is None or w_hi <= w_lo)
            else min(low - w_lo, w_hi - high) / (w_hi - w_lo))

        resolution = _q(limits, "soc_step_resolution", "1")
        out["soc_step_resolution_ratio"] = (
            None if (final_soc is None or not resolution)
            else abs(soc - final_soc) / resolution)

        def drift(reference_key: str, span_key: str) -> float | None:
            reference = _q(limits, reference_key, "K")
            span = _q(limits, span_key, "K")
            if reference is None or span is None or span <= 0.0:
                return None
            return abs(temp - reference) / span

        out["capacity_temperature_drift_ratio"] = drift(
            "capacity_reference_temperature", "capacity_temperature_span")
        out["internal_resistance_drift_ratio"] = drift(
            "resistance_reference_temperature", "resistance_temperature_span")
        out["peukert_temperature_drift_ratio"] = drift(
            "peukert_reference_temperature", "peukert_temperature_span")

        t_lo = _q(limits, "minimum_discharge_temperature", "K")
        t_hi = _q(limits, "maximum_discharge_temperature", "K")
        out["discharge_temperature_position"] = (
            None if (t_lo is None or t_hi is None or t_hi <= t_lo)
            else (temp - t_lo) / (t_hi - t_lo))

        rise_bound = _q(limits, "self_heating_rise_bound", "K")
        rise = (None if (heat is None or not conductance) else heat / conductance)
        out["self_heating_rise_ratio"] = (
            None if (rise is None or not rise_bound) else rise / rise_bound)

        tau_polar = _q(limits, "polarization_time_constant", "s")
        if not tau_polar:
            out["polarization_unmodelled_fraction"] = None
        else:
            developed = 1.0 - math.exp(-elapsed_s / tau_polar)
            out["polarization_unmodelled_fraction"] = min(developed, 1.0 - developed)

        out["terminal_voltage_ratio"] = (
            None if (terminal is None or worst_ocv is None or worst_ocv <= 0.0)
            else terminal / worst_ocv)

        if (cutoff_v is None or r_int is None or ocv_empty is None
                or ocv_full is None or ocv_full == ocv_empty or cutoff_soc is None):
            out["cutoff_consistency_margin"] = None
        else:
            z_cut = (cutoff_v + current * r_int - ocv_empty) / (ocv_full - ocv_empty)
            out["cutoff_consistency_margin"] = cutoff_soc - z_cut

        exponent = _q(limits, "peukert_exponent", "1")
        i_ref = _q(limits, "peukert_reference_current", "A")
        decades = _q(limits, "peukert_fit_decades", "1")
        if exponent is None or not i_ref or current <= 0.0:
            out["peukert_capacity_ratio"] = None
        else:
            out["peukert_capacity_ratio"] = (i_ref / current) ** (exponent - 1.0)
        out["peukert_extrapolation_ratio"] = (
            None if (not i_ref or not decades or current <= 0.0)
            else abs(math.log10(current / i_ref)) / decades)
        return out

    # Every (state of charge, temperature, elapsed) triple the run visits, in
    # the order it visits them, with both instants of each step named.
    visits: list[tuple[float, float, float]] = []
    soc_walk = soc_0
    temperature_walk = temperature if temperature is not None else 0.0
    elapsed = 0.0
    for _ in range(max(steps, 1)):
        end_temperature = advance(temperature_walk)
        elapsed += duration
        visits.append((soc_walk, temperature_walk, elapsed))
        visits.append((soc_walk, end_temperature, elapsed))
        temperature_walk = end_temperature
        if drop is None:
            break
        soc_walk -= drop

    # One evaluation per visited instant, then the WORST classification per
    # condition: a condition that fails anywhere in the march fails, and one
    # that could not be assessed anywhere is unknown. `violated` outranks
    # `unknown` outranks `satisfied`, the same precedence the verdict uses.
    per_instant = [_values_at(soc, temp, elapsed) for soc, temp, elapsed in visits]
    order = {"satisfied": 0, "unknown": 1, "violated": 2}
    conditions_list: list[ConditionValue] = []
    for model_id, names in MODEL_CONDITIONS.items():
        for name in names:
            candidates = [_classify(name, snapshot.get(name), model_id)
                          for snapshot in per_instant]
            conditions_list.append(max(candidates, key=lambda c: order[c.status]))
    conditions = tuple(conditions_list)
    if any(c.status == "violated" for c in conditions):
        verdict = "NOT_SUPPORTED"
    elif any(c.status == "unknown" for c in conditions):
        verdict = "INSUFFICIENT_EVIDENCE"
    else:
        verdict = "SUPPORTED"
    return BatteryTruth(verdict=verdict, conditions=conditions, state={
        "soc_initial": soc_0,
        "soc_final": visits[-1][0] - (drop or 0.0) if visits else soc_0,
        "temperature_final_k": visits[-1][1] if visits else temperature,
        "c_rate_per_hour": current / q_nom,
        "steps": steps,
        "self_heating_rise_k": (None if (heat is None or not conductance)
                                else heat / conductance),
    })


# ---------------------------------------------------------------------------
# SECOND ORACLE. Coulomb counting checked against the charge that crossed, and
# the thermal march checked against an integrator rather than a closed form.
# ---------------------------------------------------------------------------

SECOND_ORACLE_ID = "blind.oracle.battery.rk4_and_charge_balance"


def second_oracle(payload: dict, truth: BatteryTruth) -> dict:
    """Two independent re-derivations of the state the conditions are read at.

    **Charge balance.** ``SoC`` after ``n`` steps is checked against the charge
    that actually crossed the terminals, ``n I t``, referred to the usable
    charge ``eta Q``. The primary oracle walks the same drop step by step; this
    forms it once from the total. The two share the definition and not the
    accumulation, so what this bounds is a step-accumulation error — including
    the classic one of applying efficiency once instead of per step.

    **Thermal march.** The primary oracle integrates ``C dT/dt = I^2 R -
    hA (T - T_amb)`` exactly, one closed form per step, because the heat is
    constant at constant current. This one marches the same balance with RK4.
    Here the two really should agree to round-off, because the balance is
    linear with constant coefficients — so a gap above round-off is a defect
    in one of them and not a modelling difference.
    """
    cell = payload["cell"]
    load = payload["load"]
    thermal = payload.get("thermal", {})
    limits = cell.get("limits", {})
    steps = int(payload.get("march", {}).get("steps", 1) or 1)

    q_nom = _q(cell, "nominal_capacity", "Ah")
    efficiency = _q(cell, "coulombic_efficiency", "1")
    resistance = _q(cell, "internal_resistance", "ohm")
    current = _q(load, "discharge_current", "A")
    duration = _q(load, "duration", "s")
    soc_0 = _q(load, "state_of_charge", "1")
    temperature = _q(load, "cell_temperature", "K")
    conductance = _q(limits, "cell_thermal_conductance", "W/K")
    capacity = _q(thermal, "heat_capacity", "J/K")
    ambient = _q(thermal, "ambient_temperature", "K")

    report: dict = {"status": "compared", "oracle_a": ORACLE_ID,
                    "oracle_b": SECOND_ORACLE_ID}

    if None not in (q_nom, efficiency, current, duration, soc_0) and (
            q_nom > 0.0 and efficiency > 0.0):
        crossed_ah = current * (duration / 3600.0) * steps
        from_balance = soc_0 - crossed_ah / (efficiency * q_nom)
        walked = truth.state.get("soc_final")
        if walked is not None:
            scale = max(abs(from_balance), abs(walked), 1e-12)
            report["soc_relative_gap"] = abs(from_balance - walked) / scale
            report["soc_from_charge_balance"] = from_balance
            report["soc_from_step_walk"] = walked
    else:
        report["soc_relative_gap"] = None

    if (None not in (resistance, current, duration, conductance, capacity,
                     ambient, temperature)
            and conductance > 0.0 and capacity > 0.0):
        heat = current * current * resistance
        substeps = 400

        def derivative(value: float) -> float:
            return (heat - conductance * (value - ambient)) / capacity

        marched = temperature
        step = duration / substeps
        for _ in range(steps * substeps):
            k1 = derivative(marched)
            k2 = derivative(marched + 0.5 * step * k1)
            k3 = derivative(marched + 0.5 * step * k2)
            k4 = derivative(marched + step * k3)
            marched += (step / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            if not math.isfinite(marched):
                break
        closed = truth.state.get("temperature_final_k")
        if closed is not None and math.isfinite(marched) and closed != 0.0:
            report["temperature_relative_gap"] = abs(marched - closed) / abs(closed)
            report["temperature_from_rk4"] = marched
            report["temperature_from_closed_form"] = closed
    else:
        report["temperature_relative_gap"] = None

    gaps = [value for key, value in report.items()
            if key.endswith("_relative_gap") and value is not None]
    report["worst_relative_gap"] = max(gaps) if gaps else None
    return report
