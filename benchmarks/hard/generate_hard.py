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

Two definitions this file got wrong once, recorded so they cannot be
reintroduced
-------------------------------------------------------------------------
**Fo is not t/tau.** Incropera, DeWitt, Bergman & Lavine, *Fundamentals of Heat
and Mass Transfer*, 6th ed., Sec. 5.2, Eq. 5.12 gives ``Bi * Fo = t / tau``, so
``Fo = (t / tau) / Bi``. `shape_horizon` and `verify_sound` used ``t / tau`` and
called it the Fourier number, which mislabelled 103 cases across `horizon_out`,
`compound:horizon+tmax` and `adv_unsound:brief_but_slow`. Because Bi is small
for any body the lumped model applies to, the two differ by orders of
magnitude. Measured on the first five `horizon_out` cases of that draw:

    U00028  t/tau = 0.198   Bi = 4.77e-05   Fo = 4151
    U00048  t/tau = 0.1996  Bi = 0.006224   Fo = 32.07
    U00079  t/tau = 0.1996  Bi = 2.579e-07  Fo = 773948
    U00110  t/tau = 0.198   Bi = 0.0002605  Fo = 760.0
    U00131  t/tau = 0.16    Bi = 0.07713    Fo = 2.074

Every one is far above the 0.2 bound, so the tool reported the condition
satisfied and was right in all 103. Use `fourier()`, never `dur / tau`.

**The linear TCR form has its own declared range**, 200-450 K, narrower than
any `maximum_operating_temperature` a case declares. See TCR_MIN_TEMPERATURE.

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


def fourier(p):
    """Fo = (t / tau) / Bi — the body's horizon in units of its diffusion time.

    **This is the correction to an earlier error in this file.** `shape_horizon`
    and `verify_sound` used `t / tau` and called it the Fourier number. They are
    not the same quantity: Incropera, DeWitt, Bergman & Lavine 6th ed., Sec. 5.2,
    Eq. 5.12 gives the identity `Bi * Fo = t / tau`, so `Fo = (t / tau) / Bi`.

    Because Bi is typically 1e-3 or smaller for a body the lumped model applies
    to, the two differ by orders of magnitude. Cases shaped to sit just below
    `t/tau = 0.2` had a true Fo between 2 and 8e5 — all far above the 0.2 bound
    — so the tool reported the condition satisfied and was right to. 103 cases
    across `horizon_out`, `compound:horizon+tmax` and `adv_unsound:brief_but_slow`
    were mislabelled by this, and the tool was right in every one of them.

    Placing a case below the real bound needs a Bi near its own limit as well as
    a short horizon, which is why `shape_horizon` now raises Bi first.
    """
    bi = biot(p["hA"], p["area"], p["lc"], p["k"])
    if bi <= 0:
        return None
    return (p["dur"] / p["_tau"]) / bi


# =====================================================================
# The convection correlations, computed here from first principles
# =====================================================================
#
# The tool now asks where `ambient_conductance` came from, so every case has
# to say. Three conditions follow: the fraction of the correlation's laminar
# range in use, the fraction of its property range in use, and whether the
# declared hA reproduces what the correlation predicts.
#
# HOW A CASE IS MADE CONSISTENT, AND WHAT IS SYNTHETIC ABOUT IT
# -------------------------------------------------------------
# `hA` and `surface_area` are drawn independently, so h = hA/A_s spans about
# six decades — from 0.06 to 1e5 W/m^2K. No real fluid produces that range at
# a sane length and velocity: 1e5 W/m^2K in air would need a supersonic free
# stream over a 0.1 mm plate. So the length, the velocity and the expansion
# coefficient are kept physical and the FLUID CONDUCTIVITY is solved for:
#
#     k_f = h L / Nu
#
# which makes the declared hA exactly what the correlation predicts. The
# resulting k_f is often not a real fluid's — it ranges from 1e-4 to about
# 2000 W/mK. That is deliberate and it is the same status the rest of this
# file's draws have: `r0` is 10^U(0, 3.5) ohms and `alpha` comes from a list,
# neither describing a part anyone stocks. THE TOOL HAS NO FLUID TABLE and
# makes no claim to check one, so a synthetic k_f tests exactly what these
# conditions are for — whether the three declared numbers are consistent with
# each other — and nothing it does not.
#
# A shaper that wants a disagreement divides k_f by the ratio it wants, which
# moves the agreement ratio and leaves Ra and Re untouched: neither contains
# k_f, so the flow range and the agreement are independent knobs.

#: Air near 300 K. Only the viscosity and the Prandtl number are used as
#: given; the conductivity is solved for (see above).
NU_AIR = 1.589e-5          # m^2/s
PR_AIR = 0.707             # dimensionless
G_STANDARD = 9.80665       # m/s^2, exact by definition

#: The ranges the correlations state. Churchill, S. W. and Chu, H. H. S.
#: (1975), Int. J. Heat Mass Transfer 18(11), 1323-1329, laminar vertical
#: plate, Ra_L <= 1e9 (Incropera, DeWitt, Bergman and Lavine, 6th ed.,
#: Sec. 9.6.1, Eq. 9.27). Flat plate in parallel laminar flow,
#: Nu = 0.664 Re^(1/2) Pr^(1/3) for Re_L <= 5e5 and Pr >= 0.6 (Sec. 7.1 and
#: Sec. 7.2, Eq. 7.30). Restated here rather than imported, because this file
#: never consults engcore.
RAYLEIGH_MAX = 1.0e9
REYNOLDS_MAX = 5.0e5
PRANDTL_MIN = 0.6

#: How far a declared hA may sit from the correlation: a factor of two either
#: way. A CONVENTION in the domain and restated as one here.
AGREEMENT_FACTOR = 2.0

#: How far the two routes to a characteristic length may disagree before the
#: domain calls them different objects: a factor of three either way, and the
#: bound is INCLUSIVE on both edges. Three is the sphere's shape factor -- for
#: a sphere L_c = r_o and V/A_s = r_o/3 -- so a body sitting exactly on the
#: bound is the shape the factor was derived from. Restated here rather than
#: imported, because this file never consults engcore.
GEOMETRY_AGREEMENT_FACTOR = 3.0

#: Disagreements a `geometry_conflict` case is drawn from, as the factor by
#: which the implied V/A_s is inflated. The ratio the domain judges is its
#: reciprocal, so these four sit strictly OUTSIDE the factor-of-3 tolerance --
#: two just past it, two an order beyond -- one pair on each side. See
#: :func:`shape_geometry_conflict` for why the boundary value itself is
#: excluded.
_GEOMETRY_NEAR = GEOMETRY_AGREEMENT_FACTOR * 1.05
_GEOMETRY_FAR = 30.0
GEOMETRY_CONFLICT_FACTORS = [
    _GEOMETRY_NEAR, 1.0 / _GEOMETRY_NEAR, _GEOMETRY_FAR, 1.0 / _GEOMETRY_FAR,
]

#: Comfortable defaults, far inside both ranges, so a case that is not about
#: convection is not accidentally about convection.
RAYLEIGH_DEFAULT = 1.0e6
REYNOLDS_DEFAULT = 1.0e4
FORCED_LENGTH_DEFAULT = 0.05      # m


def excursion(p):
    """max |T - T_amb| over the interval — the driving temperature difference."""
    return max(abs(p["t_init"] - p["t_amb"]), abs(p["_t_ss"] - p["t_amb"]))


def churchill_chu(ra, pr):
    """Nu = 0.68 + 0.670 Ra^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9)."""
    return 0.68 + 0.670 * ra ** 0.25 / (
        1.0 + (0.492 / pr) ** (9.0 / 16.0)
    ) ** (4.0 / 9.0)


def flat_plate(re, pr):
    """Nu = 0.664 Re^(1/2) Pr^(1/3)."""
    return 0.664 * re ** 0.5 * pr ** (1.0 / 3.0)


def convection(p):
    """The declared convection facts, and the numbers they imply.

    Deterministic in `p`, and called from `build` so it runs AFTER every
    shaper — `make_biot` moves the surface area, which moves h, so the fluid
    cannot be settled before the shaping is done.

    Reads the optional knobs a shaper may have set: `_ra_target`, `_re_target`,
    `_pr`, `_agree`, `_conv_length`. Returns a dict of the declared fields plus
    the derived numbers `verify_sound` re-checks.
    """
    dt = excursion(p)
    if dt <= 0.0:
        dt = 1e-6
    h = p["hA"] / p["area"]
    pr = p.get("_pr", PR_AIR)
    agree = p.get("_agree", 1.0)
    natural = p["regime"] == "natural"

    if natural:
        # beta = 1/T_film for an ideal gas, at the film temperature.
        beta = 2.0 / (p["_t_ss"] + p["t_amb"])
        ra = p.get("_ra_target", RAYLEIGH_DEFAULT)
        length = (ra * NU_AIR ** 2 / (G_STANDARD * beta * dt * pr)) ** (1.0 / 3.0)
        nu_number = churchill_chu(ra, pr)
        re = None
        velocity = None
    else:
        beta = None
        length = p.get("_conv_length", FORCED_LENGTH_DEFAULT)
        re = p.get("_re_target", REYNOLDS_DEFAULT)
        velocity = re * NU_AIR / length
        nu_number = flat_plate(re, pr)
        ra = None

    if not (0.0 < length < 1e4) or nu_number <= 0.0:
        return None
    k_f = h * length / nu_number / agree
    if not (0.0 < k_f < 1e9):
        return None

    declared = {
        "fluid_conductivity": k_f,
        "fluid_kinematic_viscosity": NU_AIR,
        "fluid_prandtl_number": pr,
        "convection_length": length,
    }
    if natural:
        declared["fluid_expansion_coefficient"] = beta
    else:
        declared["fluid_velocity"] = velocity
    return {
        "declared": declared,
        "natural": natural,
        "rayleigh": ra,
        "reynolds": re,
        "flow_utilization": (ra / RAYLEIGH_MAX) if natural else (re / REYNOLDS_MAX),
        "property_utilization": 0.0 if natural else (PRANDTL_MIN / pr),
        "agreement": agree,
    }


def q(x, u):
    return f"{x:.10g} {u}"


def build(p):
    conv = convection(p)
    if conv is None:                       # pragma: no cover - draw is rejected
        return None
    p["_conv"] = conv
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
                    # Where the ambient conductance came from. Exactly one of
                    # fluid_expansion_coefficient and fluid_velocity is
                    # present: declaring both is mixed convection and the
                    # domain refuses it.
                    "fluid_conductivity":
                        q(conv["declared"]["fluid_conductivity"],
                          "watt/meter/kelvin"),
                    "fluid_kinematic_viscosity":
                        q(conv["declared"]["fluid_kinematic_viscosity"],
                          "meter**2/second"),
                    "fluid_prandtl_number":
                        q(conv["declared"]["fluid_prandtl_number"],
                          "dimensionless"),
                    "convection_length":
                        q(conv["declared"]["convection_length"], "meter"),
                    **({"fluid_expansion_coefficient":
                        q(conv["declared"]["fluid_expansion_coefficient"],
                          "1/kelvin")}
                       if conv["natural"] else
                       {"fluid_velocity":
                        q(conv["declared"]["fluid_velocity"],
                          "meter/second")}),
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
    conv = convection(p)
    if conv is None:
        return False
    if conv["flow_utilization"] > 0.9 or conv["property_utilization"] > 0.9:
        return False
    if not (1.0 / AGREEMENT_FACTOR * 1.2 < conv["agreement"]
            < AGREEMENT_FACTOR * 0.8):
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
    fo = fourier(p)
    if fo is None:
        return False
    conv = convection(p)
    if conv is None:
        return False
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
        # Where the declared hA came from. The correlation is evaluated here
        # from first principles, exactly as every other condition in this
        # dict is, and never by asking engcore.
        "convection_flow_range_utilization": conv["flow_utilization"] < 1.0,
        "convection_property_range_utilization":
            conv["property_utilization"] < 1.0,
        "convection_conductance_agreement_ratio":
            1.0 / AGREEMENT_FACTOR < conv["agreement"] < AGREEMENT_FACTOR,
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
        "convection_flow_range_utilization": conv["flow_utilization"] < 0.9,
        "convection_property_range_utilization":
            conv["property_utilization"] < 0.9,
        "convection_conductance_agreement_ratio":
            1.0 / AGREEMENT_FACTOR * 1.2 < conv["agreement"]
            < AGREEMENT_FACTOR * 0.8,
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
    # Including the convection knobs: a shaper sets its own after this, and a
    # case that is not about convection must not accidentally be about it.
    for knob in ("_ra_target", "_re_target", "_pr", "_agree", "_conv_length"):
        p.pop(knob, None)
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
    """Place the *Fourier number* near its bound — not t/tau. See `fourier`.

    Bi is raised towards its own limit first, because Fo = (t/tau)/Bi and at a
    Bi of 1e-5 reaching Fo = 0.2 would need a horizon of 1e-6 tau: a duration
    no design would state, and a case that tested arithmetic rather than the
    condition. Near the Biot limit the two bounds are in the same regime and a
    horizon below the Fourier bound is a run somebody might really write down.
    """
    widen_all(p)
    if not make_biot(p, rng, BIOT_LIMIT * 0.8):
        return None
    bi = biot(p["hA"], p["area"], p["lc"], p["k"])
    target = FOURIER_MIN * (1 + margin) if inside else FOURIER_MIN * (1 - margin)
    p["dur"] = p["_tau"] * target * bi
    if p["dur"] <= 0 or not math.isfinite(p["dur"]):
        return None
    if inside:
        return ("valid", "SUPPORTED",
                f"Fo = {target:.5g}, above the {FOURIER_MIN} convention.",
                "internal_fourier_number", "horizon_in")
    return ("model_inapplicable", "INSUFFICIENT_EVIDENCE",
            f"Fo = {target:.5g}, below the {FOURIER_MIN} convention.",
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


def shape_convection_range(p, rng, margin, inside):
    """The declared operating point placed at a controlled distance from the
    edge of the correlation's own laminar range, on both sides.

    Ra_L against 1e9 for a free-convection declaration, Re_L against 5e5 for a
    forced one. Which route a case takes is drawn, because the two are
    genuinely different declarations and both have to be exercised: a body
    under free convection has no velocity and one in a duct has no buoyancy
    term, and the tool folds both into one utilization precisely so that
    neither is permanently UNKNOWN.

    A case outside the range is `model_inapplicable` rather than
    `limit_exceeded`: nothing about the part is over a rating. The coefficient
    was taken from a correlation being read outside where its source says it
    holds, so the number has nothing behind it.
    """
    widen_all(p)
    p["regime"] = rng.choice(["natural", "forced"])
    factor = (1 - margin) if inside else (1 + margin)
    if p["regime"] == "natural":
        p["_ra_target"] = RAYLEIGH_MAX * factor
        what = f"Ra = {p['_ra_target']:.4g} against the 1e9 laminar limit"
    else:
        p["_re_target"] = REYNOLDS_MAX * factor
        what = f"Re = {p['_re_target']:.4g} against the 5e5 transition"
    if inside:
        return ("valid", "SUPPORTED",
                f"{what}, {margin:.1%} inside. The correlation the declared "
                "coefficient came from is being read where its source says it "
                "holds, and the case must not be refused.",
                "convection_flow_range_utilization", "conv_range_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"{what}, {margin:.1%} outside. The coefficient came from a "
            "correlation read past its own stated range.",
            "convection_flow_range_utilization", "conv_range_out")


def shape_convection_property(p, rng, margin, inside):
    """Prandtl number placed at a controlled distance from the 0.6 floor.

    Forced convection only, and that is not an omission. Churchill-Chu states
    no Prandtl restriction — its (0.492/Pr)^(9/16) denominator exists so that
    one equation covers every Pr — so there is no property range for a
    free-convection case to leave, and a shaper that manufactured one would be
    testing a bound the source does not print.
    """
    widen_all(p)
    p["regime"] = "forced"
    # utilization = 0.6/Pr, so inside means utilization below 1, i.e. Pr above
    # the floor. Solve for Pr directly rather than nudging it.
    utilization = (1 - margin) if inside else (1 + margin)
    p["_pr"] = PRANDTL_MIN / utilization
    if not (0.05 < p["_pr"] < 1000.0):
        return None
    if inside:
        return ("valid", "SUPPORTED",
                f"Pr = {p['_pr']:.5g}, {margin:.1%} above the 0.6 floor the "
                "flat-plate correlation states.",
                "convection_property_range_utilization", "conv_prandtl_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"Pr = {p['_pr']:.5g}, below the 0.6 floor: the Pr^(1/3) factor is "
            "the constant-property Blasius result and does not hold there.",
            "convection_property_range_utilization", "conv_prandtl_out")


def shape_convection_agreement(p, rng, margin, inside):
    """The declared hA placed at a controlled distance from a factor of two
    away from what the correlation predicts, on both sides of both edges.

    This is the condition the whole convection group exists for. Everything
    else in this file is computed FROM hA, so an hA that its own stated basis
    does not reproduce moves Biot, both excursion budgets and the radiation
    share by the same factor, and until this condition existed nothing said so.

    Both edges are exercised. A declared hA far ABOVE the correlation predicts
    a cooler body and is the dangerous direction; far BELOW is conservative and
    still a broken declaration. The bound is two-sided and both sides get
    cases.
    """
    widen_all(p)
    p["regime"] = rng.choice(["natural", "forced"])
    high = rng.random() < 0.5
    if high:
        p["_agree"] = (AGREEMENT_FACTOR * (1 - margin) if inside
                       else AGREEMENT_FACTOR * (1 + margin))
        side = "above"
    else:
        p["_agree"] = ((1.0 / AGREEMENT_FACTOR) / (1 - margin) if inside
                       else (1.0 / AGREEMENT_FACTOR) * (1 - margin))
        side = "below"
    ratio = p["_agree"]
    if inside:
        return ("valid", "SUPPORTED",
                f"The declared hA is {ratio:.4g}x what the correlation "
                f"predicts, {margin:.1%} inside the factor-of-2 convention "
                f"({side}). A correlation is not a measurement and this much "
                "disagreement is what its own scatter allows.",
                "convection_conductance_agreement_ratio", "conv_agree_in")
    return ("model_inapplicable", "NOT_SUPPORTED",
            f"The declared hA is {ratio:.4g}x what the correlation predicts "
            f"({side} by more than the factor-of-2 convention). Every other "
            "condition here is computed from that hA.",
            "convection_conductance_agreement_ratio", "conv_agree_out")


THRESHOLD_SHAPERS = [
    shape_biot, shape_t_max, shape_band, shape_cond,
    shape_cap, shape_melt, shape_horizon, shape_rad, shape_debye,
    shape_rating,
    shape_convection_range, shape_convection_property,
    shape_convection_agreement,
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
        if not make_biot(p, rng, BIOT_LIMIT * 0.8):
            return None
        p["dur"] = (p["_tau"] * FOURIER_MIN * (1 - m)
                    * biot(p["hA"], p["area"], p["lc"], p["k"]))
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
    if not make_biot(p, rng, BIOT_LIMIT * 0.8):
        return None
    bi = biot(p["hA"], p["area"], p["lc"], p["k"])
    p["dur"] = p["_tau"] * FOURIER_MIN * 0.9 * bi
    return ("model_inapplicable", "INSUFFICIENT_EVIDENCE",
            f"A {p['dur']:.4g} s run looks ample until you notice the body's "
            f"own diffusion time: Fo = {FOURIER_MIN * 0.9:.4g}.",
            "internal_fourier_number", "adv_unsound:brief_but_slow")


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
    """Two routes to L_c that describe different bodies.

    **The boundary value is excluded on purpose and must stay excluded.** The
    domain admits a disagreement of up to a factor of
    `GEOMETRY_AGREEMENT_FACTOR` (3) either way, inclusive on both edges, and
    that inclusiveness is correct: a body whose V/A_s is exactly L_c/3 IS the
    sphere the factor was derived from -- L_c = r_o against V/A_s = r_o/3 --
    so it sits on the bound by construction and admitting it is the right
    reading, not a rounding accident. An earlier draw of this shaper picked the
    factor 3.0 itself and labelled the result `inconsistent_inputs`. The tool
    accepted 15 such cases and the benchmark counted every one as a false
    accept the tool had not committed: a sound sphere scored as a miss, and 15
    of the 26 headline false accepts were this label rather than this tool. A
    case at exactly 3x is a sphere. Reintroducing it would re-inflate the same
    number.

    The disagreement is therefore placed strictly outside the tolerance, on
    either side, with a margin -- the declared L_c too large by more than 3x or
    too small by more than 3x. Both sides get cases because the bound is
    two-sided and neither route is privileged: nothing here can tell which of
    the two numbers the caller got right, only that no standard shape
    reconciles them.
    """
    widen_all(p)
    factor = rng.choice(GEOMETRY_CONFLICT_FACTORS)
    p["vol"] = p["lc"] * p["area"] * factor
    # The domain judges L_c(declared) / (V/A_s), which is 1/factor here.
    ratio = 1.0 / factor
    return ("inconsistent_inputs", "NOT_SUPPORTED",
            f"Declared Lc = {p['lc']:.4g} m against an implied V/As of "
            f"{p['vol']/p['area']:.4g} m — the two routes disagree by "
            f"{ratio:.4g}x, past the factor of "
            f"{GEOMETRY_AGREEMENT_FACTOR:g} that a choice of shape convention "
            "can account for. Two routes to one quantity that disagree must "
            "not be silently reconciled.",
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
    # Where the ambient conductance came from. Omitting any one of these
    # leaves the correlation unevaluable, so all three convection conditions
    # report UNKNOWN and the case is INSUFFICIENT_EVIDENCE — never IN_DOMAIN.
    ("fluid_conductivity", "applicability",
     "convection_conductance_agreement_ratio"),
    ("fluid_kinematic_viscosity", "applicability",
     "convection_flow_range_utilization"),
    ("fluid_prandtl_number", "applicability",
     "convection_property_range_utilization"),
    ("convection_length", "applicability",
     "convection_flow_range_utilization"),
    ("fluid_expansion_coefficient", "applicability",
     "convection_flow_range_utilization"),
    ("fluid_velocity", "applicability", "convection_flow_range_utilization"),
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
