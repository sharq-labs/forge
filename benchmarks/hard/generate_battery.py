"""Adversarial battery cases for the `run_battery` boundary.

The same discipline as `generate_hard.py` and the same rules:

* every threshold case sits at a controlled distance from its bound — 0.2 %,
  1 %, 5 %, 20 % — on **both** sides. A case 1 % inside must be accepted and
  1 % outside must be refused, which requires the bound to be implemented
  exactly rather than approximately;
* ground truth is computed **here, from first principles**, and never consults
  engcore;
* a case may be labelled sound only if `verify_sound()` re-checks every
  condition it covers and finds them all clear, with a margin on all but the
  one the shaper deliberately placed near its bound.

**If a case turns out to be labelled wrong and the tool right, say so
explicitly.** Do not quietly correct this generator.

Coverage, stated rather than implied
------------------------------------
Twelve of the battery domain's fourteen applicability conditions are shaped on
both sides here, and all fourteen are re-checked by `verify_sound()`. The two
not shaped are `terminal_voltage_ratio` and `peukert_capacity_ratio`: both are
strict inequalities against zero and one respectively with no declared bound to
place a case against — they are the physics of the computed quantity rather
than a threshold, so a "1 % outside" case for them is a different kind of case
and is not manufactured here.

The march, reimplemented
------------------------
`run_battery` marches `steps` intervals of `load.duration` each. The cell heats
itself and carries the new temperature into the next step, so the conditions
are evaluated at a moving temperature and a falling state of charge. This file
reimplements that march rather than assuming a single operating point:

    Q_gen  = I^2 R                       constant, since I is constant
    T_ss   = T_amb + Q_gen / hA          the asymptote the body approaches
    T_end  = T_ss + (T - T_ss) exp(-t / tau_th),   tau_th = C_th / hA
    z_end  = z - eta I t / Q_nom

The temperature rises monotonically toward `T_ss` and the state of charge falls
monotonically, so the extreme instants of the whole march are its endpoints:
the hottest is the last step's end and the emptiest is the last step's end.
Every temperature-facing condition is checked at the hottest instant and every
charge-facing one at the emptiest, which is what "satisfied over the interval"
means.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random

# --- the bounds, restated here because this file never imports engcore -------
#
# `RATING_UTILIZATION_LIMIT`, `DECLARED_BUDGET_LIMIT`, `STEP_RESOLUTION_LIMIT`,
# `WINDOW_MARGIN_FLOOR`, `CUTOFF_CONSISTENCY_FLOOR`, `TEMPERATURE_POSITION_*`
# and `POLARIZATION_UNMODELLED_CEILING` in
# src/engcore/domains/battery/models.py.
UTILIZATION_LIMIT = 1.0
WINDOW_MARGIN_FLOOR = 0.0
CUTOFF_FLOOR = 0.0
POSITION_FLOOR, POSITION_CEILING = 0.0, 1.0
POLARIZATION_CEILING = 0.05

MARGINS = [0.002, 0.01, 0.05, 0.20]

SECONDS_PER_HOUR = 3600.0


def q(x, u):
    return f"{x:.10g} {u}"


def nominal():
    """A declaration comfortably clear of every one of the fourteen bounds.

    Checked by `verify_sound()` on every case built from it, so "comfortably"
    is asserted rather than asserted-to-be. A shaper then moves exactly one
    declaration and leaves the rest here.
    """
    return {
        # cell
        "q_nom_ah": 2.5, "r_int": 0.03, "ocv_full": 4.2, "ocv_empty": 3.0,
        "eta": 0.99,
        # limits
        "c_cont": 3.0, "c_pulse": 10.0, "t_pulse_rated": 30.0,
        "w_lo": 0.10, "w_hi": 0.95,
        "t_min": 253.15, "t_max": 333.15,
        "t_r_ref": 298.15, "r_span": 25.0,
        "hA": 0.4, "rise_bound": 15.0,
        "tau_pol": 15.0, "soc_res": 0.05,
        "t_q_ref": 298.15, "q_span": 25.0,
        "k_peukert": 1.05, "i_ref": 1.0, "decades": 1.5,
        "t_k_ref": 298.15, "k_span": 25.0,
        # load
        "current": 1.5, "z0": 0.9, "t_cell": 298.15, "step_s": 60.0,
        "i_pulse": 4.0, "t_pulse": 10.0,
        "v_cutoff": 3.0, "z_cutoff": 0.15,
        # thermal + march
        "c_th": 60.0, "t_amb": 298.15, "steps": 10,
    }


# =====================================================================
# The march, and the extreme instants it reaches
# =====================================================================

def march(p):
    """`(T_hot, T_cold, z_start, z_end, per_step_dz)` for one declaration.

    Both temperature extremes, because the conditions are not all one-sided:
    `discharge_temperature_position` is bounded from above *and* below, and the
    drift ratios are bounded on |T - T_ref|, so the binding instant is whichever
    of the two endpoints is further from the reference.
    """
    heat = p["current"] ** 2 * p["r_int"]
    t_ss = p["t_amb"] + heat / p["hA"]
    tau_th = p["c_th"] / p["hA"]
    temperature = p["t_cell"]
    for _ in range(p["steps"]):
        temperature = t_ss + (temperature - t_ss) * math.exp(-p["step_s"] / tau_th)
    hot, cold = max(p["t_cell"], temperature), min(p["t_cell"], temperature)

    dz = p["eta"] * p["current"] * (p["step_s"] / SECONDS_PER_HOUR) / p["q_nom_ah"]
    return hot, cold, p["z0"], p["z0"] - dz * p["steps"], dz


def ocv(p, z):
    return p["ocv_empty"] + (p["ocv_full"] - p["ocv_empty"]) * z


def conditions(p):
    """Every condition this file covers, as a name -> value mapping.

    Each is the number the domain's own condition is stated over, computed
    here independently. The comparison against the bound is in
    :func:`verify_sound`.
    """
    hot, cold, z_start, z_end, dz = march(p)
    heat = p["current"] ** 2 * p["r_int"]
    # The temperature furthest from each reference, which is the binding one.
    def worst(reference):
        return max(abs(hot - reference), abs(cold - reference))

    # The state of charge at which the declared voltage cutoff actually bites,
    # inverting V = OCV(z) - I R.
    slope = p["ocv_full"] - p["ocv_empty"]
    z_at_v = (p["v_cutoff"] + p["current"] * p["r_int"] - p["ocv_empty"]) / slope
    worst_z = z_end
    return {
        "continuous_c_rate_utilization":
            (p["current"] / p["q_nom_ah"]) / p["c_cont"],
        "pulse_c_rate_utilization":
            (p["i_pulse"] / p["q_nom_ah"]) / p["c_pulse"],
        "pulse_duration_utilization": p["t_pulse"] / p["t_pulse_rated"],
        "soc_window_margin": min(
            z_end - p["w_lo"], p["w_hi"] - z_start
        ) / (p["w_hi"] - p["w_lo"]),
        # Both endpoints must sit inside the declared range, so the binding
        # ones are the hottest and the coldest instants of the march.
        "discharge_temperature_position_hot":
            (hot - p["t_min"]) / (p["t_max"] - p["t_min"]),
        "discharge_temperature_position_cold":
            (cold - p["t_min"]) / (p["t_max"] - p["t_min"]),
        "internal_resistance_drift_ratio": worst(p["t_r_ref"]) / p["r_span"],
        "self_heating_rise_ratio": (heat / p["hA"]) / p["rise_bound"],
        "polarization_unmodelled_fraction": (
            lambda f: min(f, 1.0 - f)
        )(1.0 - math.exp(-p["step_s"] / p["tau_pol"])),
        "terminal_voltage_ratio":
            (ocv(p, worst_z) - p["current"] * p["r_int"]) / ocv(p, worst_z),
        "soc_step_resolution_ratio": dz / p["soc_res"],
        "capacity_temperature_drift_ratio": worst(p["t_q_ref"]) / p["q_span"],
        "cutoff_consistency_margin": p["z_cutoff"] - z_at_v,
        "peukert_extrapolation_ratio":
            abs(math.log10(p["current"] / p["i_ref"])) / p["decades"],
        "peukert_capacity_ratio":
            (p["i_ref"] / p["current"]) ** (p["k_peukert"] - 1.0),
        "peukert_temperature_drift_ratio": worst(p["t_k_ref"]) / p["k_span"],
    }


#: name -> (comparison, bound). `le` is "value <= bound", `ge` is the reverse.
_RULES = {
    "continuous_c_rate_utilization": ("le", UTILIZATION_LIMIT),
    "pulse_c_rate_utilization": ("le", UTILIZATION_LIMIT),
    "pulse_duration_utilization": ("le", UTILIZATION_LIMIT),
    "soc_window_margin": ("ge", WINDOW_MARGIN_FLOOR),
    "discharge_temperature_position_hot": ("le", POSITION_CEILING),
    "discharge_temperature_position_cold": ("ge", POSITION_FLOOR),
    "internal_resistance_drift_ratio": ("le", UTILIZATION_LIMIT),
    "self_heating_rise_ratio": ("le", UTILIZATION_LIMIT),
    "polarization_unmodelled_fraction": ("le", POLARIZATION_CEILING),
    "terminal_voltage_ratio": ("gt", 0.0),
    "soc_step_resolution_ratio": ("le", UTILIZATION_LIMIT),
    "capacity_temperature_drift_ratio": ("le", UTILIZATION_LIMIT),
    "cutoff_consistency_margin": ("ge", CUTOFF_FLOOR),
    "peukert_extrapolation_ratio": ("le", UTILIZATION_LIMIT),
    "peukert_capacity_ratio": ("le", UTILIZATION_LIMIT),
    "peukert_temperature_drift_ratio": ("le", UTILIZATION_LIMIT),
}

#: The two derived names that map to one condition in the domain. Reported
#: under the domain's own name so a ground-truth label names a real condition.
_CONDITION_NAME = {
    "discharge_temperature_position_hot": "discharge_temperature_position",
    "discharge_temperature_position_cold": "discharge_temperature_position",
}


#: Two conditions are checked EXACTLY even on a sound case, with no margin
#: demanded. Both are directional statements rather than thresholds:
#: `peukert_capacity_ratio` is <= 1 for every current above the reference and
#: approaches 1 as the current approaches it, so a nominal case legitimately
#: sits at 0.98 and demanding ten per cent of headroom would reject every
#: realistic declaration. `terminal_voltage_ratio` is > 0 strictly, and there
#: is no margin to take against zero. Neither is shaped, for the same reason.
_NO_MARGIN = frozenset({"peukert_capacity_ratio", "terminal_voltage_ratio"})


def _holds(name, value, *, slack=1.0):
    """Does this condition hold? `slack` < 1 demands a margin."""
    how, bound = _RULES[name]
    if how == "le":
        return value <= bound * slack
    if how == "gt":
        return value > 0.0
    # A floor at zero cannot be scaled, so a margin is an absolute offset.
    return value >= bound + (0.0 if slack == 1.0 else 0.02)


def verify_sound(p, exempt=""):
    """Independent re-check of every covered condition, for a sound label.

    `exempt` names the condition the shaper deliberately placed near its bound:
    that one is checked against the true bound, the rest against a margin, so
    exactly one condition sits near an edge.
    """
    values = conditions(p)
    if p["w_hi"] <= p["w_lo"] or p["t_max"] <= p["t_min"]:
        return False
    for name, value in values.items():
        if not math.isfinite(value):
            return False
        target = _CONDITION_NAME.get(name, name)
        if target == exempt:
            if not _holds(name, value):
                return False
        elif not _holds(
            name, value, slack=1.0 if name in _NO_MARGIN else 0.9
        ):
            return False
    return True


# =====================================================================
# The payload
# =====================================================================

def build(p):
    return {
        "cell": {
            "cell_id": "C1",
            "nominal_capacity": q(p["q_nom_ah"], "ampere_hour"),
            "internal_resistance": q(p["r_int"], "ohm"),
            "open_circuit_voltage_at_full": q(p["ocv_full"], "volt"),
            "open_circuit_voltage_at_empty": q(p["ocv_empty"], "volt"),
            "coulombic_efficiency": q(p["eta"], "dimensionless"),
            "limits": {
                "continuous_discharge_c_rate": q(p["c_cont"], "1/hour"),
                "pulse_discharge_c_rate": q(p["c_pulse"], "1/hour"),
                "rated_pulse_duration": q(p["t_pulse_rated"], "second"),
                "usable_soc_minimum": q(p["w_lo"], "dimensionless"),
                "usable_soc_maximum": q(p["w_hi"], "dimensionless"),
                "minimum_discharge_temperature": q(p["t_min"], "kelvin"),
                "maximum_discharge_temperature": q(p["t_max"], "kelvin"),
                "resistance_reference_temperature": q(p["t_r_ref"], "kelvin"),
                "resistance_temperature_span": q(p["r_span"], "kelvin"),
                "cell_thermal_conductance": q(p["hA"], "watt/kelvin"),
                "self_heating_rise_bound": q(p["rise_bound"], "kelvin"),
                "polarization_time_constant": q(p["tau_pol"], "second"),
                "soc_step_resolution": q(p["soc_res"], "dimensionless"),
                "capacity_reference_temperature": q(p["t_q_ref"], "kelvin"),
                "capacity_temperature_span": q(p["q_span"], "kelvin"),
                "peukert_exponent": q(p["k_peukert"], "dimensionless"),
                "peukert_reference_current": q(p["i_ref"], "ampere"),
                "peukert_fit_decades": q(p["decades"], "dimensionless"),
                "peukert_reference_temperature": q(p["t_k_ref"], "kelvin"),
                "peukert_temperature_span": q(p["k_span"], "kelvin"),
            },
        },
        "load": {
            "load_id": "L1",
            "discharge_current": q(p["current"], "ampere"),
            "state_of_charge": q(p["z0"], "dimensionless"),
            "cell_temperature": q(p["t_cell"], "kelvin"),
            "duration": q(p["step_s"], "second"),
            "pulse_current": q(p["i_pulse"], "ampere"),
            "pulse_duration": q(p["t_pulse"], "second"),
            "cutoff_voltage": q(p["v_cutoff"], "volt"),
            "cutoff_state_of_charge": q(p["z_cutoff"], "dimensionless"),
        },
        "thermal": {
            "heat_capacity": q(p["c_th"], "joule/kelvin"),
            "ambient_temperature": q(p["t_amb"], "kelvin"),
        },
        "march": {"steps": p["steps"]},
    }


# =====================================================================
# The shapers: one declaration moved, both sides of its bound
# =====================================================================
#
# Each returns the key it moved and the condition that key decides, so the
# ground truth names a real condition and `verify_sound` can exempt exactly it.

def _scale_to(p, key, name, margin, inside, *, invert=False):
    """Move `key` so `name` lands at a controlled distance from its bound.

    `invert=False` means the condition's value is inversely proportional to
    the declaration -- a utilization over a rating, where raising the rating
    lowers the ratio. Every shaper here is of that shape, which is why the
    target factor is applied to the declaration rather than to the value.
    """
    current = conditions(p)[name]
    if current <= 0.0:
        return False
    target = UTILIZATION_LIMIT * ((1 - margin) if inside else (1 + margin))
    p[key] = p[key] * current / target
    return p[key] > 0.0


SHAPERS = {}


def shaper(condition, key):
    def register(fn):
        SHAPERS[fn.__name__] = (fn, condition, key)
        return fn
    return register


@shaper("continuous_c_rate_utilization", "c_cont")
def shape_continuous(p, m, inside):
    return _scale_to(p, "c_cont", "continuous_c_rate_utilization", m, inside)


@shaper("pulse_c_rate_utilization", "c_pulse")
def shape_pulse_rate(p, m, inside):
    return _scale_to(p, "c_pulse", "pulse_c_rate_utilization", m, inside)


@shaper("pulse_duration_utilization", "t_pulse_rated")
def shape_pulse_duration(p, m, inside):
    return _scale_to(
        p, "t_pulse_rated", "pulse_duration_utilization", m, inside
    )


@shaper("internal_resistance_drift_ratio", "t_r_ref")
def shape_resistance_drift(p, m, inside):
    """Move the reference temperature so |T - T_ref| lands on the span."""
    hot, cold, *_ = march(p)
    target = p["r_span"] * ((1 - m) if inside else (1 + m))
    p["t_r_ref"] = hot - target
    return p["t_r_ref"] > 0.0


@shaper("capacity_temperature_drift_ratio", "t_q_ref")
def shape_capacity_drift(p, m, inside):
    hot, cold, *_ = march(p)
    target = p["q_span"] * ((1 - m) if inside else (1 + m))
    p["t_q_ref"] = hot - target
    return p["t_q_ref"] > 0.0


@shaper("peukert_temperature_drift_ratio", "t_k_ref")
def shape_peukert_drift(p, m, inside):
    hot, cold, *_ = march(p)
    target = p["k_span"] * ((1 - m) if inside else (1 + m))
    p["t_k_ref"] = hot - target
    return p["t_k_ref"] > 0.0


@shaper("self_heating_rise_ratio", "rise_bound")
def shape_self_heating(p, m, inside):
    return _scale_to(p, "rise_bound", "self_heating_rise_ratio", m, inside)


@shaper("soc_step_resolution_ratio", "soc_res")
def shape_step_resolution(p, m, inside):
    return _scale_to(p, "soc_res", "soc_step_resolution_ratio", m, inside)


@shaper("peukert_extrapolation_ratio", "decades")
def shape_peukert_reach(p, m, inside):
    return _scale_to(p, "decades", "peukert_extrapolation_ratio", m, inside)


@shaper("discharge_temperature_position", "t_max")
def shape_temperature_ceiling(p, m, inside):
    """The hottest instant placed against the declared ceiling.

    Position = (T - T_min)/(T_max - T_min) <= 1 is exactly T <= T_max, so the
    ceiling is moved to sit a controlled distance above or below the hottest
    temperature the march reaches.
    """
    hot, *_ = march(p)
    span = hot - p["t_min"]
    if span <= 1.0:
        return False
    p["t_max"] = p["t_min"] + span * ((1 + m) if inside else (1 - m))
    return p["t_max"] > p["t_min"]


@shaper("soc_window_margin", "w_hi")
def shape_soc_window(p, m, inside):
    """The emptiest instant against the declared floor of the window.

    Margin >= 0 is exactly z_end >= w_lo, so the floor is placed a controlled
    fraction of the window below or above where the march actually ends.
    """
    _, _, z_start, z_end, _ = march(p)
    width = p["w_hi"] - p["w_lo"]
    offset = width * m
    p["w_lo"] = z_end - offset if inside else z_end + offset
    return 0.0 <= p["w_lo"] < p["w_hi"] and p["w_hi"] >= z_start


@shaper("cutoff_consistency_margin", "z_cutoff")
def shape_cutoff(p, m, inside):
    """The two declared cutoffs against each other.

    At this current the voltage cutoff bites at a higher state of charge than
    the open-circuit curve alone would say, so a requested depth of discharge
    below it is never reached and a runtime computed to it is over-reported.
    """
    slope = p["ocv_full"] - p["ocv_empty"]
    z_at_v = (p["v_cutoff"] + p["current"] * p["r_int"] - p["ocv_empty"]) / slope
    p["z_cutoff"] = z_at_v + (m if inside else -m)
    return 0.0 <= p["z_cutoff"] <= 1.0


@shaper("polarization_unmodelled_fraction", "tau_pol")
def shape_polarization(p, m, inside):
    """The step length against the diffusion time constant.

    min(f, 1 - f) <= 0.05 with f = 1 - exp(-t/tau). The settled branch is used
    -- 1 - f <= 0.05, i.e. t >= 3.0 tau -- so the time constant is moved to put
    the step a controlled distance past three of them.
    """
    target = POLARIZATION_CEILING * ((1 - m) if inside else (1 + m))
    if not 0.0 < target < 0.5:
        return False
    p["tau_pol"] = -p["step_s"] / math.log(target)
    return p["tau_pol"] > 0.0


# =====================================================================
# Omission
# =====================================================================

_OPTIONAL = [
    ("continuous_discharge_c_rate", "continuous_c_rate_utilization"),
    ("pulse_discharge_c_rate", "pulse_c_rate_utilization"),
    ("rated_pulse_duration", "pulse_duration_utilization"),
    ("usable_soc_minimum", "soc_window_margin"),
    ("minimum_discharge_temperature", "discharge_temperature_position"),
    ("resistance_temperature_span", "internal_resistance_drift_ratio"),
    ("self_heating_rise_bound", "self_heating_rise_ratio"),
    ("polarization_time_constant", "polarization_unmodelled_fraction"),
    ("soc_step_resolution", "soc_step_resolution_ratio"),
    ("capacity_temperature_span", "capacity_temperature_drift_ratio"),
    ("peukert_exponent", "peukert_capacity_ratio"),
    ("peukert_fit_decades", "peukert_extrapolation_ratio"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260906)
    ap.add_argument("--out", default="cases_battery")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    out = pathlib.Path(args.out)
    out.mkdir(exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()

    cases: list[dict] = []
    tags: dict[str, int] = {}
    guard = 0
    names = sorted(SHAPERS)

    while len(cases) < args.n and guard < args.n * 200:
        guard += 1
        roll = rng.random()
        p = nominal()

        if roll < 0.85:
            fn, condition, _key = SHAPERS[rng.choice(names)]
            margin = rng.choice(MARGINS)
            inside = rng.random() < 0.5
            if not fn(p, margin, inside):
                continue
            tag = f"{condition}_{'in' if inside else 'out'}@{margin:g}"
            label = "valid" if inside else "model_inapplicable"
            verdict = "SUPPORTED" if inside else "NOT_SUPPORTED"
            why = (
                f"{condition} placed {margin:.1%} "
                f"{'inside' if inside else 'outside'} its bound."
            )
            payload = build(p)
        else:
            field, condition = rng.choice(_OPTIONAL)
            payload = build(p)
            if field not in payload["cell"]["limits"]:
                continue
            payload["cell"]["limits"].pop(field)
            tag = f"missing:{field}"
            label, verdict = "insufficient_input", "INSUFFICIENT_EVIDENCE"
            condition = f"{condition} -> UNKNOWN"
            why = (
                f"'{field}' not supplied, so {condition} cannot be formed. A "
                f"missing declaration is UNKNOWN and never IN_DOMAIN."
            )

        if label == "valid" and not verify_sound(p, exempt=condition):
            continue

        n = len(cases) + 1
        prefix = "B" if label == "valid" else "X"
        tags[tag] = tags.get(tag, 0) + 1
        cases.append({
            "id": f"{prefix}{n:05d}",
            "title": tag,
            "system": "battery",
            "payload": payload,
            "ground_truth": {
                "label": label, "expected_verdict": verdict, "reason": why,
                "should_be_caught_by": condition, "defect": tag,
                "needs_review": False,
            },
        })

    for c in cases:
        (out / f"{c['id']}.json").write_text(
            json.dumps(c, ensure_ascii=False), encoding="utf-8")

    sound = sum(1 for c in cases if c["ground_truth"]["label"] == "valid")
    index = {
        "seed": args.seed, "system": "battery", "total": len(cases),
        "sound": sound, "unsound": len(cases) - sound,
        "by_defect": dict(sorted(tags.items(), key=lambda kv: -kv[1])),
    }
    pathlib.Path("index_battery.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(cases)} battery cases -> {out}/  "
          f"(sound {sound}, unsound {len(cases) - sound})")
    print(f"{len(tags)} distinct defect tags")


if __name__ == "__main__":
    main()
