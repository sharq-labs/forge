"""Generate 10,000 electro-thermal cases at maximum difficulty.

What makes this set hard
------------------------
The 1000-case set put its defects far from the thresholds: Biot 2.5 against a
0.1 limit, a ceiling 40 K below the answer. Anything that checks at all catches
those. This set is built the opposite way.

1. **Margin bands.** Every threshold case is placed at a controlled distance
   from its bound: 0.2%, 1%, 5% or 20%, on both sides. A case 1% inside a limit
   is sound and must be accepted; a case 1% outside is unsound and must be
   refused. Getting both right requires the bound to be implemented exactly,
   not approximately.

2. **Adversarial sound.** Sound cases that look alarming: 900 K bodies that are
   still 200 K below their melting point, thick blocks that are fine because the
   conductivity is high, 300 K excursions inside a declared 400 K budget. A tool
   that pattern-matches on "big number" fails these.

3. **Adversarial unsound.** Unsound cases that look tame: a 3 K rise that still
   breaks a 2 K budget, a Biot of 0.101, a ceiling missed by 0.3 K.

4. **Compound defects.** Two or three simultaneous defects with a stated
   precedence: an inapplicable model plus an exceeded limit computed *from* that
   model — applicability should lead, because the limit reading is meaningless
   if the model does not apply.

5. **Masking.** A defect placed where a different, passing condition might be
   mistaken for coverage of it.

6. **Near-miss units.** Not the 1000x prefix slip, but a factor of 2 or 3: a
   value that is dimensionally valid, plausible-looking, and wrong.

Ground truth is computed here from first principles and never consults engcore.

Usage:  python generate_10000.py [--n 10000] [--seed 20260906]
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random

SIGMA = 5.670374419e-8
BIOT_LIMIT = 0.1
RAD_SHARE_LIMIT = 0.1
FOURIER_MIN = 0.2

#: The declared range of the repository's linear TCR form itself, from
#: `electrical.material.linear_tcr_resistance` — TCR_MIN_TEMPERATURE and
#: TCR_MAX_TEMPERATURE in src/engcore/domains/electrical/material.py.
#:
#: This is a limit of the *model*, not of any material a case declares, and it
#: is narrower than the `maximum_operating_temperature` a case may state. An
#: earlier draw omitted it from `verify_sound()` and mislabelled 61 sound cases
#: as a result: they ran far above 450 K, the tool correctly reported
#: OUTSIDE_VALIDATED_DOMAIN on both material models, and the benchmark counted
#: that correct refusal as a false reject. The tool was right and the label was
#: wrong. Checked here rather than fixed in the domain — widening the model's
#: declared range to make cases pass would be relaxing a threshold to improve a
#: number.
TCR_MIN_TEMPERATURE = 200.0
TCR_MAX_TEMPERATURE = 450.0

#: How far a sound case's component ratings sit above the operating point.
#: Comfortably clear, so a sound case is never refused for a rating that only
#: just holds — the threshold shapers are where ratings are placed near a bound.
RATING_HEADROOM = 3.0

# Distances from a bound, as a fraction. The 0.002 band is where tools that
# round, clamp, or use a slightly different formula start disagreeing.
MARGINS = [0.002, 0.01, 0.05, 0.20]


def steady_temperature(v, r0, alpha, t_ref, hA, t_amb):
    t = t_amb
    for _ in range(2000):
        r = r0 * (1.0 + alpha * (t - t_ref))
        if r <= 0:
            return None
        nxt = t_amb + (v * v / r) / hA
        if not math.isfinite(nxt) or nxt > 1e6:
            return None
        if abs(nxt - t) < 1e-10:
            return nxt
        t = nxt
    return None


def biot(hA, area, lc, k):
    return (hA / area) * lc / k


def rad_share(eps, area, hA, t_hot, t_amb):
    if t_hot <= t_amb:
        return 0.0
    q_conv = hA * (t_hot - t_amb)
    if q_conv <= 0:
        return float("inf")
    return eps * SIGMA * area * (t_hot**4 - t_amb**4) / q_conv


def q(x, u):
    return f"{x:.10g} {u}"


def build(p):
    return {
        "source_voltage": q(p["v"], "volt"),
        "stages": [{
            "component_id": "R1",
            "conductor": {
                "reference_resistance": q(p["r0"], "ohm"),
                "temperature_coefficient": q(p["alpha"], "1/kelvin"),
                "reference_temperature": q(p["t_ref"], "kelvin"),
                "limits": {
                    "linearization_band": q(p["band"], "kelvin"),
                    "maximum_operating_temperature": q(p["t_max"], "kelvin"),
                    "debye_temperature": q(p["debye"], "kelvin"),
                },
                "ratings": {
                    "rated_power": q(p["rated_power"], "watt"),
                    "maximum_working_voltage": q(p["max_working_voltage"], "volt"),
                    **({"derating_factor": p["derating"]}
                       if p.get("derating") is not None else {}),
                },
            },
            "body": {
                "heat_capacity": q(p["cap"], "joule/kelvin"),
                "ambient_conductance": q(p["hA"], "watt/kelvin"),
                "ambient_temperature": q(p["t_amb"], "kelvin"),
                "initial_temperature": q(p["t_init"], "kelvin"),
                "duration": q(p["dur"], "second"),
                "applicability": {
                    "characteristic_length": q(p["lc"], "meter"),
                    "body_volume": q(p["vol"], "meter**3"),
                    "surface_area": q(p["area"], "meter**2"),
                    "body_conductivity": q(p["k"], "watt/meter/kelvin"),
                    "surface_emissivity": q(p["eps"], "dimensionless"),
                    "convection_regime": p["regime"],
                    "conductance_excursion_bound": q(p["cond_bound"], "kelvin"),
                    "capacity_excursion_bound": q(p["cap_bound"], "kelvin"),
                    "melting_temperature": q(p["t_melt"], "kelvin"),
                },
            },
        }],
        "source_ratings": {
            "maximum_current": q(p["max_current"], "ampere"),
            **({"derating_factor": p["derating"]}
               if p.get("derating") is not None else {}),
        },
        "coupling": {
            "seed_temperature": q(p["t_amb"], "kelvin"),
            "tolerance": "1e-06 kelvin",
            "max_iterations": 200,
        },
    }


def base_draw(rng, wide=False):
    """A physically coherent starting point. `wide` widens the operating range
    so that adversarial-but-sound extremes are reachable."""
    v = rng.uniform(0.5, 60.0) if wide else rng.uniform(0.8, 30.0)
    r0 = 10 ** rng.uniform(0.0, 3.5)
    alpha = rng.choice([0.0, 2e-5, 5e-5, 4e-4, 1.5e-3, 3.93e-3, -5e-4])
    t_ref = 293.15
    hA = 10 ** rng.uniform(-2.2, 1.0)
    t_amb = rng.uniform(220.0, 400.0) if wide else rng.uniform(250.0, 340.0)

    t_ss = steady_temperature(v, r0, alpha, t_ref, hA, t_amb)
    if t_ss is None:
        return None
    rise = t_ss - t_amb
    lo, hi = (0.2, 900.0) if wide else (0.5, 200.0)
    if not (lo < rise < hi):
        return None

    k = rng.choice([0.5, 2.0, 15.0, 45.0, 80.0, 150.0, 200.0, 400.0])
    lc = 10 ** rng.uniform(-4.5, -1.5)
    area = 10 ** rng.uniform(-4.0, -1.0)
    vol = lc * area
    eps = rng.uniform(0.01, 0.6)
    cap = 10 ** rng.uniform(-1.0, 3.0)
    tau = cap / hA
    dur = tau * rng.uniform(1.0, 10.0)

    p = {
        "v": v, "r0": r0, "alpha": alpha, "t_ref": t_ref, "hA": hA,
        "t_amb": t_amb, "t_init": t_amb, "dur": dur, "cap": cap,
        "lc": lc, "vol": vol, "area": area, "k": k, "eps": eps,
        "regime": rng.choice(["forced", "natural"]),
        "_t_ss": t_ss, "_rise": rise, "_tau": tau,
    }
    # limits are set by the shaping functions below
    p["cond_bound"] = rise * 3.0
    p["cap_bound"] = rise * 3.0
    p["band"] = max(abs(t_ss - t_ref), abs(t_amb - t_ref)) * 2.0 + 20.0
    p["t_max"] = t_ss + max(30.0, rise * 0.5)
    p["t_melt"] = p["t_max"] + 400.0
    p["debye"] = min(t_amb, t_ss) / 2.5

    # The electrical operating point the component ratings are stated against.
    # One resistor across one source, so the whole circuit is V, R(T_ss) and
    # the current they set. Computed here rather than in `build` so the shapers
    # can place a rating at a controlled distance from it.
    r_hot = r0 * (1.0 + alpha * (t_ss - t_ref))
    if r_hot <= 0:
        return None
    p["_r_hot"] = r_hot
    p["_i"] = v / r_hot
    p["_p_diss"] = v * v / r_hot
    p["rated_power"] = p["_p_diss"] * RATING_HEADROOM
    p["max_working_voltage"] = v * RATING_HEADROOM
    p["max_current"] = p["_i"] * RATING_HEADROOM
    p["derating"] = None
    return p


def make_biot(p, rng, target):
    """Set the geometry so Biot lands exactly on `target`."""
    p["k"] = rng.choice([0.5, 2.0, 15.0, 45.0, 150.0, 400.0])
    p["area"] = 10 ** rng.uniform(-3.5, -1.5)
    h = p["hA"] / p["area"]
    p["lc"] = target * p["k"] / h
    if not (1e-6 < p["lc"] < 1.0):
        return False
    p["vol"] = p["lc"] * p["area"]
    return True


def all_clear(p):
    """True when every declared limit is clear, so a single shaped defect is
    the only thing wrong (or, for sound cases, nothing is)."""
    t = p["_t_ss"]
    if biot(p["hA"], p["area"], p["lc"], p["k"]) > BIOT_LIMIT * 0.9:
        return False
    if rad_share(p["eps"], p["area"], p["hA"], t, p["t_amb"]) > RAD_SHARE_LIMIT * 0.9:
        return False
    if p["dur"] / p["_tau"] < 1.0:
        return False
    if t > p["t_max"] * 0.98 or t > p["t_melt"] * 0.9:
        return False
    if p["_rise"] > p["cond_bound"] * 0.9 or p["_rise"] > p["cap_bound"] * 0.9:
        return False
    if max(abs(t - p["t_ref"]), abs(p["t_amb"] - p["t_ref"])) > p["band"] * 0.9:
        return False
    if min(p["t_amb"], t) / p["debye"] < 1.3:
        return False
    return True


def verify_sound(p, exempt=""):
    """Independent re-check of EVERY condition for a case labelled sound.

    A shaper widens the limit it targets but can leave another condition
    violated by the base draw. A case counts as sound only if it clears all of
    them. `exempt` names the condition the shaper deliberately placed near its
    bound: that one is checked against the true bound, the rest against a
    margin, so exactly one condition sits near an edge.
    """
    t = p["_t_ss"]
    bi = biot(p["hA"], p["area"], p["lc"], p["k"])
    rs = rad_share(p["eps"], p["area"], p["hA"], t, p["t_amb"])
    fo = p["dur"] / p["_tau"]
    exc = max(abs(t - p["t_ref"]), abs(p["t_amb"] - p["t_ref"]))
    exact = {
        "biot_number": bi < BIOT_LIMIT,
        "radiation_to_convection_ratio": rs < RAD_SHARE_LIMIT,
        "internal_fourier_number": fo > FOURIER_MIN,
        "operating_temperature_utilization": t < p["t_max"],
        "melting_temperature_utilization": t < p["t_melt"],
        "conductance_excursion_ratio": p["_rise"] < p["cond_bound"],
        "capacity_excursion_ratio": p["_rise"] < p["cap_bound"],
        "linearization_excursion_ratio": exc < p["band"],
        "reduced_debye_temperature": min(p["t_amb"], t) / p["debye"] > 1.0 / 3.0,
        # The linear TCR form's own declared range — a limit of the model, not
        # of the material. See TCR_MIN_TEMPERATURE above for why it is here.
        "temperature": TCR_MIN_TEMPERATURE < t < TCR_MAX_TEMPERATURE,
        # The component ratings, against the operating point they are stated
        # against. A rating is a declared limit like any other and a sound case
        # must clear it.
        "dissipated_power_utilization":
            p["_p_diss"] < p["rated_power"] * (p.get("derating") or 1.0),
        "working_voltage_utilization":
            p["v"] < p["max_working_voltage"] * (p.get("derating") or 1.0),
        "source_current_utilization":
            p["_i"] < p["max_current"] * (p.get("derating") or 1.0),
    }
    margin = {
        "biot_number": bi < BIOT_LIMIT * 0.8,
        "radiation_to_convection_ratio": rs < RAD_SHARE_LIMIT * 0.8,
        "internal_fourier_number": fo > FOURIER_MIN * 1.25,
        "operating_temperature_utilization": t < p["t_max"] * 0.98,
        "melting_temperature_utilization": t < p["t_melt"] * 0.95,
        "conductance_excursion_ratio": p["_rise"] < p["cond_bound"] * 0.9,
        "capacity_excursion_ratio": p["_rise"] < p["cap_bound"] * 0.9,
        "linearization_excursion_ratio": exc < p["band"] * 0.9,
        "reduced_debye_temperature": min(p["t_amb"], t) / p["debye"] > 0.42,
        "temperature": (
            TCR_MIN_TEMPERATURE * 1.05 < t < TCR_MAX_TEMPERATURE * 0.95
        ),
        "dissipated_power_utilization":
            p["_p_diss"] < p["rated_power"] * (p.get("derating") or 1.0) * 0.9,
        "working_voltage_utilization":
            p["v"] < p["max_working_voltage"] * (p.get("derating") or 1.0) * 0.9,
        "source_current_utilization":
            p["_i"] < p["max_current"] * (p.get("derating") or 1.0) * 0.9,
    }
    for name, ok in exact.items():
        if name == exempt:
            if not ok:
                return False
        elif not margin[name]:
            return False
    if abs(p["vol"] / p["area"] - p["lc"]) > 1e-9 * max(1.0, p["lc"]):
        return False
    if p["t_melt"] <= p["t_max"] or p["t_ref"] > p["t_max"]:
        return False
    return True


def widen_all(p, factor=4.0):
    """Push every limit far clear so a shaped defect stands alone."""
    t = p["_t_ss"]
    p["cond_bound"] = max(p["_rise"] * factor, 10.0)
    p["cap_bound"] = max(p["_rise"] * factor, 10.0)
    p["band"] = max(abs(t - p["t_ref"]), abs(p["t_amb"] - p["t_ref"])) * factor + 50.0
    p["t_max"] = t + max(100.0, p["_rise"] * factor)
    p["t_melt"] = p["t_max"] + 800.0
    p["debye"] = min(p["t_amb"], t) / 4.0
    p["eps"] = min(p["eps"], 0.03)
    p["dur"] = p["_tau"] * 6.0
    return p


# ---------------------------------------------------------------------------
# Shapers. Each returns (label, verdict, reason, condition, tag) or None.
# `inside` True  -> the case is sound, placed `margin` inside the bound
# `inside` False -> the case is unsound, placed `margin` outside the bound
# ---------------------------------------------------------------------------

def shape_biot(p, rng, margin, inside):
    target = BIOT_LIMIT * (1 - margin) if inside else BIOT_LIMIT * (1 + margin)
    if not make_biot(p, rng, target):
        return None
    widen_all(p)
    if rad_share(p["eps"], p["area"], p["hA"], p["_t_ss"], p["t_amb"]) > RAD_SHARE_LIMIT:
        return None
    bi = biot(p["hA"], p["area"], p["lc"], p["k"])
    if inside:
        return ("valid", "SUPPORTED",
                f"Bi = {bi:.5g}, {margin:.1%} inside the {BIOT_LIMIT} convention. "
                "A lumped model is defensible here and must not be refused.",
                "biot_number", "biot_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"Bi = {bi:.5g}, {margin:.1%} outside the {BIOT_LIMIT} convention.",
            "biot_number", "biot_out")


def shape_t_max(p, rng, margin, inside):
    widen_all(p)
    t = p["_t_ss"]
    span = t - p["t_amb"]
    if span < 1.0:
        return None
    p["t_max"] = t * (1 + margin) if inside else t * (1 - margin)
    if p["t_max"] <= p["t_amb"]:
        return None
    p["t_melt"] = max(p["t_max"], t) + 500.0
    if inside:
        return ("valid", "SUPPORTED",
                f"Steady state {t:.6g} K against a {p['t_max']:.6g} K ceiling: "
                f"{margin:.1%} of margin, but margin nonetheless.",
                "operating_temperature_utilization", "tmax_in")
    return ("limit_exceeded", "NOT_SUPPORTED",
            f"Steady state {t:.6g} K exceeds the {p['t_max']:.6g} K ceiling by "
            f"{margin:.1%}.", "operating_temperature_utilization", "tmax_out")


def shape_band(p, rng, margin, inside):
    widen_all(p)
    exc = max(abs(p["_t_ss"] - p["t_ref"]), abs(p["t_amb"] - p["t_ref"]))
    if exc < 1.0:
        return None
    p["band"] = exc * (1 + margin) if inside else exc * (1 - margin)
    if inside:
        return ("valid", "SUPPORTED",
                f"A {exc:.5g} K excursion inside a {p['band']:.5g} K band.",
                "linearization_excursion_ratio", "band_in")
    return ("limit_exceeded", "NOT_SUPPORTED",
            f"A {exc:.5g} K excursion outside the {p['band']:.5g} K band.",
            "linearization_excursion_ratio", "band_out")


def shape_cond(p, rng, margin, inside):
    widen_all(p)
    p["regime"] = "natural"
    r = p["_rise"]
    if r < 1.0:
        return None
    p["cond_bound"] = r * (1 + margin) if inside else r * (1 - margin)
    if inside:
        return ("valid", "SUPPORTED",
                f"A {r:.5g} K excursion inside a {p['cond_bound']:.5g} K "
                "constant-hA budget.", "conductance_excursion_ratio", "cond_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"A {r:.5g} K excursion outside the {p['cond_bound']:.5g} K budget.",
            "conductance_excursion_ratio", "cond_out")


def shape_cap(p, rng, margin, inside):
    widen_all(p)
    r = p["_rise"]
    if r < 1.0:
        return None
    p["cap_bound"] = r * (1 + margin) if inside else r * (1 - margin)
    if inside:
        return ("valid", "SUPPORTED",
                f"A {r:.5g} K excursion inside a {p['cap_bound']:.5g} K "
                "constant-capacity budget.", "capacity_excursion_ratio", "cap_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"A {r:.5g} K excursion outside the {p['cap_bound']:.5g} K budget.",
            "capacity_excursion_ratio", "cap_out")


def shape_melt(p, rng, margin, inside):
    widen_all(p)
    t = p["_t_ss"]
    p["t_melt"] = t * (1 + margin) if inside else t * (1 - margin)
    if p["t_melt"] <= p["t_amb"]:
        return None
    p["t_max"] = max(p["t_max"], p["t_melt"] + 50.0)
    if inside:
        return ("valid", "SUPPORTED",
                f"{t:.6g} K against a {p['t_melt']:.6g} K melting point.",
                "melting_temperature_utilization", "melt_in")
    return ("limit_exceeded", "NOT_SUPPORTED",
            f"{t:.6g} K past a {p['t_melt']:.6g} K melting point.",
            "melting_temperature_utilization", "melt_out")


def shape_horizon(p, rng, margin, inside):
    widen_all(p)
    target = FOURIER_MIN * (1 + margin) if inside else FOURIER_MIN * (1 - margin)
    p["dur"] = p["_tau"] * target
    if inside:
        return ("valid", "SUPPORTED",
                f"Horizon is {target:.5g} tau, above the {FOURIER_MIN} convention.",
                "internal_fourier_number", "horizon_in")
    return ("model_inapplicable", "INSUFFICIENT_EVIDENCE",
            f"Horizon is {target:.5g} tau, below the {FOURIER_MIN} convention.",
            "internal_fourier_number", "horizon_out")


def shape_rad(p, rng, margin, inside):
    widen_all(p)
    t, ta, a, hA = p["_t_ss"], p["t_amb"], p["area"], p["hA"]
    if t - ta < 1.0:
        return None
    denom = SIGMA * a * (t**4 - ta**4)
    if denom <= 0:
        return None
    target = RAD_SHARE_LIMIT * (1 - margin) if inside else RAD_SHARE_LIMIT * (1 + margin)
    eps = target * hA * (t - ta) / denom
    if not (0.001 < eps < 1.0):
        return None
    p["eps"] = eps
    if inside:
        return ("valid", "SUPPORTED",
                f"Radiation is {target:.4g} of the convective load, inside the "
                f"{RAD_SHARE_LIMIT} convention.",
                "radiation_to_convection_ratio", "rad_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"Radiation is {target:.4g} of the convective load.",
            "radiation_to_convection_ratio", "rad_out")


def shape_debye(p, rng, margin, inside):
    widen_all(p)
    t_lo = min(p["t_amb"], p["_t_ss"])
    ratio = (1 / 3) * (1 + margin) if inside else (1 / 3) * (1 - margin)
    p["debye"] = t_lo / ratio
    if inside:
        return ("valid", "SUPPORTED",
                f"T/theta_D = {ratio:.5g}, inside the linear-resistivity regime.",
                "reduced_debye_temperature", "debye_in")
    return ("limit_exceeded", "NOT_SUPPORTED",
            f"T/theta_D = {ratio:.5g}, below the linear-resistivity regime.",
            "reduced_debye_temperature", "debye_out")


def shape_rating(p, rng, margin, inside):
    """A component rating placed at a controlled distance from its operating point.

    An exceeded rating is a `limit_exceeded` case like any other bound in this
    file: the part is being asked to do something its datasheet says it cannot,
    and the utilization is the fraction of the rating in use. Which of the three
    ratings is placed is drawn, because they are independent limits — a part can
    be inside its dissipation rating and outside its working voltage, and the
    conditions must be able to disagree.
    """
    which = rng.choice(["power", "voltage", "current"])
    factor = (1.0 - margin) if inside else (1.0 + margin)
    if which == "power":
        p["rated_power"] = p["_p_diss"] / factor
        cond, tag = "dissipated_power_utilization", "rating_power"
    elif which == "voltage":
        p["max_working_voltage"] = p["v"] / factor
        cond, tag = "working_voltage_utilization", "rating_voltage"
    else:
        p["max_current"] = p["_i"] / factor
        cond, tag = "source_current_utilization", "rating_current"
    if inside:
        return ("valid", "SUPPORTED",
                f"{which} at {factor:.3f} of its rating.", cond,
                f"{tag}_in")
    return ("limit_exceeded", "NOT_SUPPORTED",
            f"{which} at {factor:.3f} of its rating.", cond,
            f"{tag}_out")


THRESHOLD_SHAPERS = [
    shape_biot, shape_t_max, shape_band, shape_cond,
    shape_cap, shape_melt, shape_horizon, shape_rad, shape_debye,
    shape_rating,
]


# --- compound: two defects at once, with a stated precedence ---------------

def shape_compound(p, rng):
    widen_all(p)
    kind = rng.choice(["biot+tmax", "biot+band", "horizon+tmax", "cond+melt",
                       "rad+tmax", "biot+cond"])
    m = rng.choice([0.01, 0.05, 0.2])
    if kind.startswith("biot"):
        if not make_biot(p, rng, BIOT_LIMIT * (1 + m)):
            return None
    if kind == "biot+tmax":
        p["t_max"] = p["_t_ss"] * (1 - m)
        lead = "biot_number"
        why = ("The model does not apply AND the ceiling is exceeded — but the "
               "ceiling reading is computed from a model that does not apply, "
               "so applicability should lead.")
    elif kind == "biot+band":
        exc = max(abs(p["_t_ss"] - p["t_ref"]), abs(p["t_amb"] - p["t_ref"]))
        p["band"] = exc * (1 - m)
        lead = "biot_number"
        why = "Inapplicable model plus a linearization band exceeded."
    elif kind == "horizon+tmax":
        p["dur"] = p["_tau"] * FOURIER_MIN * (1 - m)
        p["t_max"] = p["_t_ss"] * (1 - m)
        lead = "internal_fourier_number"
        why = ("The horizon is too short to have reached the state whose ceiling "
               "is being judged.")
    elif kind == "cond+melt":
        p["regime"] = "natural"
        p["cond_bound"] = p["_rise"] * (1 - m)
        p["t_melt"] = p["_t_ss"] * (1 - m)
        lead = "conductance_excursion_ratio"
        why = "Constant-hA budget broken and the melting point passed."
    elif kind == "rad+tmax":
        t, ta, a, hA = p["_t_ss"], p["t_amb"], p["area"], p["hA"]
        denom = SIGMA * a * (t**4 - ta**4)
        if denom <= 0:
            return None
        eps = RAD_SHARE_LIMIT * 3 * hA * (t - ta) / denom
        if not (0.001 < eps < 1.0):
            return None
        p["eps"] = eps
        p["t_max"] = t * (1 - m)
        lead = "radiation_to_convection_ratio"
        why = "The dominant heat path is missing from the model AND the ceiling fails."
    else:  # biot+cond
        p["regime"] = "natural"
        p["cond_bound"] = p["_rise"] * (1 - m)
        lead = "biot_number"
        why = "Two independent modelling assumptions broken at once."
    return ("model_inapplicable", "NOT_SUPPORTED", why + " Both should be named.",
            lead, f"compound:{kind}")


# --- adversarial sound: looks alarming, is fine ----------------------------

def shape_adversarial_sound(p, rng):
    widen_all(p, factor=6.0)
    kind = rng.choice(["hot", "thick", "big_excursion", "cold", "tiny_margin_ok"])
    t = p["_t_ss"]
    if kind == "hot":
        if t < 500:
            return None
        why = (f"A {t:.4g} K body. Alarming to look at, but every declared limit "
               "is clear with margin. A tool that pattern-matches on magnitude "
               "fails this.")
    elif kind == "thick":
        if not make_biot(p, rng, BIOT_LIMIT * 0.4):
            return None
        if p["lc"] < 0.01:
            return None
        why = (f"A {p['lc']*1000:.3g} mm body — thick, yet Bi = "
               f"{biot(p['hA'], p['area'], p['lc'], p['k']):.4g} because the "
               "conductivity is high. Thickness alone is not a defect.")
    elif kind == "big_excursion":
        if p["_rise"] < 200:
            return None
        p["cond_bound"] = p["_rise"] * 5
        p["cap_bound"] = p["_rise"] * 5
        why = (f"A {p['_rise']:.4g} K excursion, declared and budgeted for. "
               "Large is not the same as outside.")
    elif kind == "cold":
        if p["t_amb"] > 260:
            return None
        p["debye"] = p["t_amb"] / 5.0
        why = f"Operation at {p['t_amb']:.4g} K, still well above theta_D/3."
    else:
        p["t_max"] = t * 1.002
        p["t_melt"] = p["t_max"] + 300
        why = ("Inside the ceiling by 0.2%. Sound, and a tool that rounds in the "
               "wrong direction will refuse it.")
    if not verify_sound(p):
        return None
    return ("valid", "SUPPORTED", why, "", f"adv_sound:{kind}")


# --- adversarial unsound: looks tame, is broken ---------------------------

def shape_adversarial_unsound(p, rng):
    widen_all(p)
    kind = rng.choice(["tiny_rise_tight_budget", "small_overshoot",
                       "cool_but_low_debye", "brief_but_slow"])
    if kind == "tiny_rise_tight_budget":
        if p["_rise"] > 5.0:
            return None
        p["regime"] = "natural"
        p["cond_bound"] = p["_rise"] * 0.8
        return ("model_inapplicable", "NOT_SUPPORTED",
                f"Only a {p['_rise']:.4g} K rise, but the declared constant-hA "
                f"budget is {p['cond_bound']:.4g} K. Small excursions can still "
                "leave a tight budget.", "conductance_excursion_ratio",
                "adv_unsound:tiny_rise_tight_budget")
    if kind == "small_overshoot":
        p["t_max"] = p["_t_ss"] - rng.uniform(0.1, 0.5)
        if p["t_max"] <= p["t_amb"]:
            return None
        return ("limit_exceeded", "NOT_SUPPORTED",
                f"Over the ceiling by {p['_t_ss'] - p['t_max']:.3g} K. Small, and "
                "still over.", "operating_temperature_utilization",
                "adv_unsound:small_overshoot")
    if kind == "cool_but_low_debye":
        p["debye"] = min(p["t_amb"], p["_t_ss"]) * 3.2
        return ("limit_exceeded", "NOT_SUPPORTED",
                "Room-temperature operation, but this material's theta_D puts it "
                "below the linear-resistivity regime.", "reduced_debye_temperature",
                "adv_unsound:cool_but_low_debye")
    p["dur"] = p["_tau"] * FOURIER_MIN * 0.9
    return ("model_inapplicable", "INSUFFICIENT_EVIDENCE",
            f"A {p['dur']:.4g} s run looks ample until you notice tau is "
            f"{p['_tau']:.4g} s.", "internal_fourier_number",
            "adv_unsound:brief_but_slow")


# --- near-miss units: a factor of 2-3, not 1000 ---------------------------

def shape_near_miss_units(p, rng):
    widen_all(p)
    factor = rng.choice([0.5, 2.0, 3.0, 0.33])
    what = rng.choice(["r0", "hA", "v"])
    p[what] = p[what] * factor
    t = steady_temperature(p["v"], p["r0"], p["alpha"], p["t_ref"], p["hA"], p["t_amb"])
    if t is None:
        return None
    p["_t_ss"], p["_rise"] = t, t - p["t_amb"]
    if t <= p["t_max"] * 1.02:
        return None
    return ("unit_or_sign_error", "NOT_SUPPORTED",
            f"'{what}' off by {factor:g}x — not a decade slip, a plausible "
            f"mistake. Steady state moves to {t:.5g} K, past the ceiling.",
            "operating_temperature_utilization", "near_miss_units")


# --- consistency defects, the three the 1000-case set exposed --------------

def shape_geometry_conflict(p, rng):
    widen_all(p)
    factor = rng.choice([3.0, 10.0, 0.1, 30.0])
    p["vol"] = p["lc"] * p["area"] * factor
    return ("inconsistent_inputs", "NOT_SUPPORTED",
            f"Declared Lc = {p['lc']:.4g} m against an implied V/As of "
            f"{p['vol']/p['area']:.4g} m ({factor:g}x apart). Two routes to one "
            "quantity that disagree must not be silently reconciled.",
            "biot_number", "geometry_conflict")


def shape_limit_conflict(p, rng):
    widen_all(p)
    kind = rng.choice(["melt_below_ceiling", "ref_above_ceiling", "band_vs_ceiling"])
    if kind == "melt_below_ceiling":
        p["t_melt"] = p["t_max"] - rng.uniform(5.0, 80.0)
        if p["t_melt"] <= p["_t_ss"]:
            return None
        why = (f"A {p['t_melt']:.5g} K melting point below a {p['t_max']:.5g} K "
               "operating ceiling: the declaration contradicts itself.")
    elif kind == "ref_above_ceiling":
        p["t_ref"] = p["t_max"] + rng.uniform(10.0, 150.0)
        why = (f"Characterised at {p['t_ref']:.5g} K, above the {p['t_max']:.5g} K "
               "ceiling it is declared to respect.")
    else:
        p["band"] = 1.0
        why = ("A 1 K linearization band with a ceiling hundreds of kelvin away: "
               "the material cannot be used across its own declared range.")
    return ("inconsistent_inputs", "NOT_SUPPORTED", why, "", f"limit_conflict:{kind}")


def shape_runaway(p, rng):
    widen_all(p)
    p["alpha"] = rng.choice([0.02, 0.03, 0.05, -0.02, -0.05])
    t = steady_temperature(p["v"], p["r0"], p["alpha"], p["t_ref"], p["hA"], p["t_amb"])
    if t is not None and abs(t - p["_t_ss"]) < 100:
        return None
    return ("inconsistent_inputs", "NOT_SUPPORTED",
            f"alpha = {p['alpha']:g} /K: the electro-thermal loop does not "
            "contract. A design that runs away is a finding about the design, "
            "and belongs in the report rather than in an exception.",
            "thermal runaway", "runaway")


# --- omission, at scale ---------------------------------------------------

_OPT = [
    ("body_conductivity", "applicability", "biot_number"),
    ("surface_emissivity", "applicability", "radiation_to_convection_ratio"),
    ("conductance_excursion_bound", "applicability", "conductance_excursion_ratio"),
    ("capacity_excursion_bound", "applicability", "capacity_excursion_ratio"),
    ("melting_temperature", "applicability", "melting_temperature_utilization"),
    ("characteristic_length", "applicability", "biot_number (alt route remains)"),
    ("maximum_operating_temperature", "limits", "operating_temperature_utilization"),
    ("linearization_band", "limits", "linearization_excursion_ratio"),
    ("debye_temperature", "limits", "reduced_debye_temperature"),
]


def shape_missing(p, rng):
    widen_all(p)
    payload = build(p)
    field, where, condition = rng.choice(_OPT)
    node = (payload["stages"][0]["body"]["applicability"] if where == "applicability"
            else payload["stages"][0]["conductor"]["limits"])
    if field not in node:
        return None
    node.pop(field)
    if field == "characteristic_length":
        return (payload, "valid", "SUPPORTED",
                "Lc omitted but V/As remains: an admissible alternative route "
                "that must not be refused.", condition, "missing:alt_route")
    return (payload, "insufficient_input", "INSUFFICIENT_EVIDENCE",
            f"'{field}' not supplied, so {condition} cannot be formed.",
            f"{condition} -> UNKNOWN", f"missing:{field}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260906)
    ap.add_argument("--out", default="cases_hard")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    out = pathlib.Path(args.out)
    out.mkdir(exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()

    cases: list[dict] = []
    guard = 0
    tag_counts: dict[str, int] = {}

    while len(cases) < args.n and guard < args.n * 300:
        guard += 1
        roll = rng.random()
        wide = roll < 0.25
        p = base_draw(rng, wide=wide)
        if p is None:
            continue

        made = None
        if roll < 0.44:                      # threshold bands, both sides
            shaper = rng.choice(THRESHOLD_SHAPERS)
            margin = rng.choice(MARGINS)
            inside = rng.random() < 0.5
            r = shaper(p, rng, margin, inside)
            if r:
                label, verdict, why, cond, tag = r
                made = (build(p), label, verdict, why, cond, f"{tag}@{margin:g}")
        elif roll < 0.58:
            r = shape_compound(p, rng)
            if r:
                made = (build(p), *r)
        elif roll < 0.70:
            r = shape_adversarial_sound(p, rng)
            if r:
                made = (build(p), *r)
        elif roll < 0.79:
            r = shape_adversarial_unsound(p, rng)
            if r:
                made = (build(p), *r)
        elif roll < 0.85:
            r = shape_missing(p, rng)
            if r:
                made = r
        elif roll < 0.90:
            r = shape_geometry_conflict(p, rng)
            if r:
                made = (build(p), *r)
        elif roll < 0.94:
            r = shape_limit_conflict(p, rng)
            if r:
                made = (build(p), *r)
        elif roll < 0.97:
            r = shape_near_miss_units(p, rng)
            if r:
                made = (build(p), *r)
        else:
            r = shape_runaway(p, rng)
            if r:
                made = (build(p), *r)

        if made is None:
            continue
        payload, label, verdict, why, cond, tag = made
        # A case may only be labelled sound if an independent re-check of every
        # condition agrees. This is the guard whose absence mislabelled 16% of
        # the first draw: a shaper widened its own target and left another
        # condition violated by the base draw.
        if label == "valid" and not verify_sound(p, exempt=cond.split()[0] if cond else ""):
            continue
        n = len(cases) + 1
        prefix = "S" if label == "valid" else "U"
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        cases.append({
            "id": f"{prefix}{n:05d}",
            "title": tag,
            "payload": payload,
            "ground_truth": {
                "label": label, "expected_verdict": verdict, "reason": why,
                "should_be_caught_by": cond, "defect": tag, "needs_review": False,
            },
        })

    for c in cases:
        (out / f"{c['id']}.json").write_text(
            json.dumps(c, ensure_ascii=False), encoding="utf-8")

    by_label: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    for c in cases:
        g = c["ground_truth"]
        by_label[g["label"]] = by_label.get(g["label"], 0) + 1
        by_verdict[g["expected_verdict"]] = by_verdict.get(g["expected_verdict"], 0) + 1

    index = {
        "seed": args.seed, "total": len(cases),
        "sound": by_label.get("valid", 0),
        "unsound": len(cases) - by_label.get("valid", 0),
        "by_label": by_label, "by_expected_verdict": by_verdict,
        "by_defect": dict(sorted(tag_counts.items(), key=lambda kv: -kv[1])),
        "cases": [{"id": c["id"], "label": c["ground_truth"]["label"],
                   "expected_verdict": c["ground_truth"]["expected_verdict"],
                   "defect": c["ground_truth"]["defect"]} for c in cases],
    }
    pathlib.Path("index_hard.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{len(cases)} cases -> {out}/  (sound {index['sound']}, "
          f"unsound {index['unsound']})")
    print("by verdict:", by_verdict)
    print(f"{len(tag_counts)} distinct defect tags")


if __name__ == "__main__":
    main()
