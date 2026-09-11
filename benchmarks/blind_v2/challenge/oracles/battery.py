"""Independent truth for the Rint / coulomb-counting cell.

The relations, written out:

* charge balance ``z(t) = z_0 - I t / (eta Q_nom)`` -- exact for a constant
  current, Plett, *Battery Management Systems, Volume I: Battery Modeling*
  (Artech House, 2015), Ch. 2;
* Rint terminal voltage ``V = OCV(z) - I R_int`` with the affine chord
  ``OCV(z) = V_empty + (V_full - V_empty) z``, Plett Ch. 3;
* irreversible heat ``Q = I^2 R_int`` (Joule);
* Peukert ``Q_eff = Q_nom (I_ref / I)^(k-1)``, the rearrangement of
  ``I^k t = const``, Peukert (1897).

Route two integrates ``dz/dt = -I/(eta Q_nom)`` with this challenge's own RK4
and evaluates the chord along the trajectory, so the state of charge at the end
of the interval, the worst-point terminal voltage and the window margin all
have a second derivation that never touches the closed form.
"""

from __future__ import annotations

import math

from .numeric import relative_gap, rk4_converged


def _final_soc_closed(z0, current, duration, efficiency, capacity_coulomb):
    if None in (z0, current, duration, efficiency, capacity_coulomb):
        return None
    if efficiency == 0.0 or capacity_coulomb == 0.0:
        return None
    return z0 - current * duration / (efficiency * capacity_coulomb)


def _final_soc_numeric(z0, current, duration, efficiency, capacity_coulomb):
    if None in (z0, current, duration, efficiency, capacity_coulomb):
        return None, None
    if efficiency == 0.0 or capacity_coulomb == 0.0:
        return None, None

    def rhs(_t, _y):
        return [-current / (efficiency * capacity_coulomb)]

    state, movement = rk4_converged(rhs, [z0], 0.0, duration, steps=128, refinements=2)
    return state[0], movement


def _ocv(z, empty, full):
    if None in (z, empty, full):
        return None
    return empty + (full - empty) * z


def evaluate(decl: dict, *, with_routes: bool = True) -> dict:
    """Every quantity the four cell models' declared conditions are stated over.

    SI throughout: capacity arrives in coulomb, current in ampere, duration in
    second, temperatures in kelvin, C-rates in inverse seconds.
    """
    capacity = decl.get("nominal_capacity")  # coulomb
    resistance = decl.get("internal_resistance")
    efficiency = decl.get("coulombic_efficiency")
    duration = decl.get("duration")
    current = decl.get("discharge_current")
    z0 = decl.get("state_of_charge")
    temperature = decl.get("cell_temperature")
    v_full = decl.get("open_circuit_voltage_at_full")
    v_empty = decl.get("open_circuit_voltage_at_empty")

    out: dict[str, float | None] = {
        "nominal_capacity": capacity,
        "internal_resistance": resistance,
        "coulombic_efficiency": efficiency,
    }
    routes: dict[str, dict] = {}

    z_end = _final_soc_closed(z0, current, duration, efficiency, capacity)
    z_end_num, movement = (
        _final_soc_numeric(z0, current, duration, efficiency, capacity)
        if with_routes
        else (None, None)
    )
    if z_end is not None and z_end_num is not None:
        routes["final_state_of_charge"] = {
            "analytic": z_end,
            "numerical": z_end_num,
            "gap": relative_gap(z_end, z_end_num),
            "refinement_movement": movement,
        }

    z_lo = None if z_end is None or z0 is None else min(z0, z_end)
    z_hi = None if z_end is None or z0 is None else max(z0, z_end)

    # ---- rate against the declared ratings -------------------------------
    c_rate = None
    if current is not None and capacity not in (None, 0.0):
        c_rate = current / capacity  # ampere / coulomb == 1/second
    continuous = decl.get("continuous_discharge_c_rate")
    out["continuous_c_rate_utilization"] = (
        None if (c_rate is None or continuous in (None, 0.0)) else abs(c_rate) / continuous
    )
    pulse_current = decl.get("pulse_current")
    pulse_rating = decl.get("pulse_discharge_c_rate")
    out["pulse_c_rate_utilization"] = (
        None
        if (pulse_current is None or capacity in (None, 0.0) or pulse_rating in (None, 0.0))
        else abs(pulse_current / capacity) / pulse_rating
    )
    pulse_duration = decl.get("pulse_duration")
    rated_pulse = decl.get("rated_pulse_duration")
    out["pulse_duration_utilization"] = (
        None
        if (pulse_duration is None or rated_pulse in (None, 0.0))
        else pulse_duration / rated_pulse
    )

    # ---- state-of-charge window -----------------------------------------
    w_lo = decl.get("usable_soc_minimum")
    w_hi = decl.get("usable_soc_maximum")
    if None in (z_lo, z_hi, w_lo, w_hi) or (w_hi is None or w_lo is None) or w_hi == w_lo:
        out["soc_window_margin"] = None
    else:
        out["soc_window_margin"] = min(z_lo - w_lo, w_hi - z_hi) / (w_hi - w_lo)

    resolution = decl.get("soc_step_resolution")
    out["soc_step_resolution_ratio"] = (
        None
        if (z_end is None or z0 is None or resolution in (None, 0.0))
        else abs(z0 - z_end) / resolution
    )

    # ---- temperature drifts ---------------------------------------------
    def drift(reference_key: str, span_key: str) -> float | None:
        reference = decl.get(reference_key)
        span = decl.get(span_key)
        if temperature is None or reference is None or span in (None, 0.0):
            return None
        return abs(temperature - reference) / span

    out["capacity_temperature_drift_ratio"] = drift(
        "capacity_reference_temperature", "capacity_temperature_span"
    )
    out["internal_resistance_drift_ratio"] = drift(
        "resistance_reference_temperature", "resistance_temperature_span"
    )
    out["peukert_temperature_drift_ratio"] = drift(
        "peukert_reference_temperature", "peukert_temperature_span"
    )

    t_min = decl.get("minimum_discharge_temperature")
    t_max = decl.get("maximum_discharge_temperature")
    out["discharge_temperature_position"] = (
        None
        if (temperature is None or t_min is None or t_max is None or t_max == t_min)
        else (temperature - t_min) / (t_max - t_min)
    )

    # ---- self heating and polarization ----------------------------------
    heat = None if None in (current, resistance) else current * current * resistance
    conductance = decl.get("cell_thermal_conductance")
    rise = None if (heat is None or conductance in (None, 0.0)) else heat / conductance
    bound = decl.get("self_heating_rise_bound")
    out["self_heating_rise_ratio"] = (
        None if (rise is None or bound in (None, 0.0)) else rise / bound
    )

    tau_pol = decl.get("polarization_time_constant")
    if duration is None or tau_pol in (None, 0.0):
        out["polarization_unmodelled_fraction"] = None
    else:
        developed = 1.0 - math.exp(-duration / tau_pol)
        out["polarization_unmodelled_fraction"] = min(developed, 1.0 - developed)

    # ---- terminal voltage, at the worst point of the interval ------------
    worst_z = z_lo
    ocv_worst = _ocv(worst_z, v_empty, v_full)
    terminal = (
        None
        if (ocv_worst is None or current is None or resistance is None)
        else ocv_worst - current * resistance
    )
    out["terminal_voltage_ratio"] = (
        None if (terminal is None or ocv_worst in (None, 0.0)) else terminal / ocv_worst
    )
    if terminal is not None and z_end_num is not None:
        worst_num = min(z0, z_end_num) if z0 is not None else z_end_num
        ocv_num = _ocv(worst_num, v_empty, v_full)
        terminal_num = None if ocv_num is None else ocv_num - current * resistance
        routes["terminal_voltage"] = {
            "analytic": terminal,
            "numerical": terminal_num,
            "gap": relative_gap(terminal, terminal_num),
        }

    # ---- the two declared cutoffs ---------------------------------------
    cutoff_voltage = decl.get("cutoff_voltage")
    cutoff_soc = decl.get("cutoff_state_of_charge")
    voltage_cutoff_soc = None
    if None not in (cutoff_voltage, current, resistance, v_empty, v_full) and v_full != v_empty:
        voltage_cutoff_soc = (
            cutoff_voltage + current * resistance - v_empty
        ) / (v_full - v_empty)
    out["cutoff_consistency_margin"] = (
        None
        if (cutoff_soc is None or voltage_cutoff_soc is None)
        else cutoff_soc - voltage_cutoff_soc
    )

    # ---- Peukert ---------------------------------------------------------
    exponent = decl.get("peukert_exponent")
    reference_current = decl.get("peukert_reference_current")
    decades = decl.get("peukert_fit_decades")
    effective = None
    if None not in (capacity, current, reference_current, exponent) and current > 0.0:
        effective = capacity * (reference_current / current) ** (exponent - 1.0)
    out["peukert_capacity_ratio"] = (
        None if (effective is None or capacity in (None, 0.0)) else effective / capacity
    )
    out["peukert_extrapolation_ratio"] = (
        None
        if (
            current in (None, 0.0)
            or reference_current in (None, 0.0)
            or decades in (None, 0.0)
        )
        else abs(math.log10(current / reference_current)) / decades
    )

    return {
        "quantities": out,
        "routes": routes,
        "intermediate": {
            "final_state_of_charge": z_end,
            "soc_low": z_lo,
            "soc_high": z_hi,
            "c_rate": c_rate,
            "heat_generation": heat,
            "terminal_voltage": terminal,
            "open_circuit_voltage_worst": ocv_worst,
            "peukert_effective_capacity": effective,
        },
    }
