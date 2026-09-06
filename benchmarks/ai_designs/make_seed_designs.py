"""Build 100 hand-written seed designs, so the harness is proven before any AI output exists.

Why seed cases exist
--------------------
No language model can be called from here, so the set that measures the product
claim cannot be produced yet. What *can* be produced is the machinery that will
measure it, run end to end on designs in the same format, drawn from the same
real components, with labels decided the same way. These 100 cases prove the
conversion, the runner and the scorer work and that the metrics move when the
physics does. **They are not AI output and no number computed from them is a
statement about any model.** ``RESULTS.md`` says so in its own words.

How a label is decided here
---------------------------
Each case is built with an intended defect, or with none. ``reference.py`` then
re-checks the physics from first principles and the case is kept only if:

* the intended violation is present, and
* no *unintended* violation is present, and
* the verdict does not depend on which of the two readings of "the operating
  temperature" is taken (``assess_robust``).

That is the same discipline ``benchmarks/hard/generate_hard.py`` records having
had to learn: a shaper that widens the limit it targets can leave another
condition broken, and a case labelled by intent rather than by re-checking is a
case that may be labelled wrong. Nothing here asks engcore anything.

How complete a design is
------------------------
Real AI designs declare almost nothing about the body or the fluid. If every
seed case were built that way, every case would be INSUFFICIENT_EVIDENCE and the
harness would be proven only against one answer. So the set is deliberately
mixed:

* ``full_declaration`` cases state the geometry, the surface, the spans and the
  fluid, as a thorough thermal note would. These are the only cases that can
  reach SUPPORTED, and they are what exercises false-reject.
* ``sparse_declaration`` cases state what an ordinary answer states -- a part, a
  voltage, an ambient -- and nothing else. These exercise the gap behaviour and
  the ``unconvertible`` path.

The split is recorded per case and reported separately, because a catch rate
computed over the second group would be the unearned kind.

Usage
-----
    python benchmarks/ai_designs/make_seed_designs.py [--out designs/seed]
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reference as ref  # noqa: E402

K = 273.15
LABELLER = "benchmark author (single reviewer)"

EXPECTED = {
    "physically_sound": "SUPPORTED",
    "model_inapplicable": "NOT_SUPPORTED",
    "limit_exceeded": "NOT_SUPPORTED",
    "unit_or_sign_error": "NOT_SUPPORTED",
    "inconsistent_inputs": "NOT_SUPPORTED",
    "insufficient_input": "INSUFFICIENT_EVIDENCE",
}


def load_components() -> dict:
    doc = json.loads((HERE / "components.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in doc["resistors"]}


def outline(part: dict) -> dict:
    """Surface area, volume and V/A_s from the datasheet outline."""
    d = part["dimensions_mm"]
    if d.get("shape") == "cylinder":
        r = d["body_diameter"] / 2000.0
        L = d["body_length"] / 1000.0
        area = 2 * math.pi * r * L + 2 * math.pi * r * r
        vol = math.pi * r * r * L
    else:
        L, W, H = (d[k] / 1000.0 for k in ("length", "width", "height"))
        area = 2 * (L * W + L * H + W * H)
        vol = L * W * H
    return {"area": area, "volume": vol, "lc": vol / area}


def tcr_of(part: dict, resistance: float) -> float:
    for band in part["temperature_coefficient_ppm_per_k"]:
        if band.get("value") is not None and band["from_ohm"] <= resistance <= band["to_ohm"]:
            return band["value"] * 1e-6
    return 100e-6


def solve_case(case: dict):
    return ref.assess_robust(case)


def fluid_for(*, natural: bool, h: float, length: float, excursion: float,
              t_amb: float, agreement: float = 1.0) -> dict | None:
    """Declare a fluid whose correlation reproduces the stated coefficient.

    ``h`` is what the design's stated thermal resistance and area imply. The
    length, the viscosity and the Prandtl number are air's; the CONDUCTIVITY is
    solved for, ``k_f = h L / Nu``, so the three declared numbers agree by
    ``agreement``. The resulting conductivity is often not air's, and that is
    the same status the frozen benchmark documents for its own fluid: **the tool
    has no fluid table and claims none**, so what these conditions test is
    whether the declared numbers are consistent with each other, and nothing
    else. A case that wants a disagreement passes ``agreement`` != 1.
    """
    pr = ref.AIR_PRANDTL
    nu_visc = ref.AIR_KINEMATIC_VISCOSITY
    if natural:
        beta = 1.0 / t_amb
        ra = (ref.G_STANDARD * beta * abs(excursion) * length ** 3) / (
            nu_visc * nu_visc) * pr
        if not (0 < ra <= ref.RAYLEIGH_MAX):
            return None
        nu_number = ref.churchill_chu(ra, pr)
        extra = {"airflow": "still"}
    else:
        velocity = 2.0
        re = velocity * length / nu_visc
        if re > ref.REYNOLDS_MAX:
            return None
        nu_number = ref.flat_plate(re, pr)
        extra = {"airflow": "forced", "fluid_velocity_m_per_s": velocity}
    k_f = h * length / nu_number * agreement
    if not (0 < k_f < 1e6):
        return None
    return {
        "fluid": "air",
        "convection_length_m": length,
        "fluid_conductivity_solved_w_per_m_k": k_f,
        **extra,
    }


def build(*, cid, part, resistance, voltage, ambient_c, duration_s, rth,
          components, defect, reason, full=True, rth_kind="body_to_ambient",
          overrides=None, ctx_overrides=None, limit_overrides=None,
          agreement=1.0, natural=True, declare_fluid=True,
          emissivity=0.85, conductivity=30.0,
          cond_span=None, cap_span=None, band=200.0, debye=400.0,
          melting_c=2072.0, declare_source_current=True, reasoning=None,
          confidence="high", basis="reference.py plus the part datasheet",
          reviewer_only=None):
    """One design record, and the reference physics that decides its label."""
    p = components[part]
    geo = outline(p)
    t_amb = ambient_c + K
    hA = 1.0 / rth
    alpha = tcr_of(p, resistance)
    mass_kg = (p.get("mass_mg") or (geo["volume"] * 3800.0 * 1e6)) * 1e-6
    heat_capacity = mass_kg * 850.0

    stated = {
        "part_id": part,
        "source_voltage_v": voltage,
        "resistance_ohm": resistance,
        "reference_temperature_c": 20.0,
        "temperature_coefficient_ppm_per_k": alpha * 1e6,
        "ambient_c": ambient_c,
        "duration_s": duration_s,
        "thermal_resistance_k_per_w": rth,
        "thermal_resistance_kind": rth_kind,
        "heat_capacity_j_per_k": heat_capacity,
    }
    stated.update(overrides or {})

    limits = {
        "rated_power_w": p["rated_power_w"],
        "maximum_working_voltage_v": p.get("maximum_working_voltage_v") or 1e6,
    }
    if p.get("operating_temperature_range_c"):
        limits["maximum_operating_temperature_c"] = p["operating_temperature_range_c"][1]
    limits.update(limit_overrides or {})

    # The reference solve, from the numbers the design actually states.
    core = {
        "source_voltage": stated["source_voltage_v"],
        "reference_resistance": stated["resistance_ohm"],
        "temperature_coefficient": stated["temperature_coefficient_ppm_per_k"] * 1e-6,
        "reference_temperature": stated["reference_temperature_c"] + K,
        "ambient_conductance": 1.0 / stated["thermal_resistance_k_per_w"],
        "ambient_temperature": stated["ambient_c"] + K,
        "initial_temperature": stated.get("initial_temperature_c", stated["ambient_c"]) + K,
        "heat_capacity": stated["heat_capacity_j_per_k"],
        "duration": stated["duration_s"],
    }
    probe = ref.solve(**{k: core[k] for k in (
        "source_voltage", "reference_resistance", "temperature_coefficient",
        "reference_temperature", "ambient_conductance", "ambient_temperature",
        "initial_temperature", "heat_capacity", "duration")})
    if probe is None:
        return None

    ctx: dict = {}
    if full:
        excursion = max(abs(core["initial_temperature"] - core["ambient_temperature"]),
                        abs(probe.t_steady - core["ambient_temperature"]))
        rise = abs(probe.t_steady - core["initial_temperature"])
        ctx = {
            "characteristic_length_m": geo["lc"],
            "surface_area_m2": geo["area"],
            "body_volume_m3": geo["volume"],
            "body_conductivity_w_per_m_k": conductivity,
            "surface_emissivity": emissivity,
            "melting_temperature_c": melting_c,
            "constant_conductance_span_k": cond_span or max(excursion * 2.5, 40.0),
            "constant_capacity_span_k": cap_span or max(rise * 2.5, 60.0),
            "linearization_band_k": band,
            "debye_temperature_k": debye,
        }
        if declare_fluid:
            fluid = fluid_for(natural=natural, h=hA / geo["area"],
                              length=math.sqrt(geo["area"]),
                              excursion=excursion,
                              t_amb=core["ambient_temperature"],
                              agreement=agreement)
            if fluid is None:
                return None
            ctx.update(fluid)
        if declare_source_current:
            limits["source_maximum_current_a"] = probe.current * 3.0
    ctx.update(ctx_overrides or {})
    if ctx:
        stated["declared_thermal_context"] = ctx
    stated["declared_limits"] = limits

    # what reference.py checks
    check = dict(core)
    check.update({
        "characteristic_length": ctx.get("characteristic_length_m"),
        "body_volume": ctx.get("body_volume_m3"),
        "surface_area": ctx.get("surface_area_m2"),
        "body_conductivity": ctx.get("body_conductivity_w_per_m_k"),
        "surface_emissivity": ctx.get("surface_emissivity"),
        "melting_temperature": (ctx["melting_temperature_c"] + K) if "melting_temperature_c" in ctx else None,
        "conductance_excursion_bound": ctx.get("constant_conductance_span_k"),
        "capacity_excursion_bound": ctx.get("constant_capacity_span_k"),
        "linearization_band": ctx.get("linearization_band_k"),
        "debye_temperature": ctx.get("debye_temperature_k"),
        "maximum_operating_temperature": (
            limits["maximum_operating_temperature_c"] + K
            if "maximum_operating_temperature_c" in limits else None),
        "rated_power": limits.get("rated_power_w"),
        "maximum_working_voltage": limits.get("maximum_working_voltage_v"),
        "derating_factor": limits.get("derating_factor"),
        "maximum_current": limits.get("source_maximum_current_a"),
        "fluid_conductivity": ctx.get("fluid_conductivity_solved_w_per_m_k"),
        "fluid_kinematic_viscosity": ref.AIR_KINEMATIC_VISCOSITY if ctx else None,
        "fluid_prandtl_number": ref.AIR_PRANDTL if ctx else None,
        "fluid_expansion_coefficient": (
            1.0 / core["ambient_temperature"] if ctx.get("airflow") == "still" else None),
        "fluid_velocity": ctx.get("fluid_velocity_m_per_s"),
        "convection_length": ctx.get("convection_length_m"),
    })
    assessment, stable = solve_case(check)

    record = {
        "id": cid,
        "prompt_id": "hand_built",
        "source": {"kind": "hand_built", "model_family": None, "model_id": None,
                   "note": "seed case; proves the harness, says nothing about any model"},
        "stated_design": stated,
        "reasoning": reasoning or {},
        "label": {
            "verdict": defect,
            "reason": reason,
            "labeller": LABELLER,
            "confidence": confidence,
            "ground_truth_basis": basis,
        },
        "expected_verdict": EXPECTED[defect],
    }
    return record, assessment, stable, probe, geo


def verify(defect: str, assessment: ref.Assessment, stable: bool,
           full: bool, reviewer_only: str | None = None) -> str | None:
    """Refuse a case whose physics does not match the label it was built for."""
    if not stable:
        return "verdict depends on which operating temperature is read"
    if assessment.solution is None:
        return "no converged solution"
    if defect == "physically_sound":
        if assessment.violated:
            return f"intended sound but violates {assessment.violated}"
        if full and assessment.unknown:
            return f"intended fully declared but leaves {assessment.unknown} unknown"
        return None
    if defect == "insufficient_input":
        return None                      # judged by what is absent, not by physics
    if reviewer_only:
        # A family whose defect is REAL but has no field in the payload to carry
        # it, so no condition can read it. The case is kept only if the physics
        # is otherwise clean: anything else violated would give the tool a
        # different reason to refuse and the probe would prove nothing.
        if assessment.violated:
            return (f"reviewer-only defect {reviewer_only!r} must stand alone, "
                    f"but {assessment.violated} is also violated")
        return None
    if not assessment.violated:
        return f"intended {defect} but nothing is violated"
    got = assessment.failure_class
    want = {"unit_or_sign_error": ("limit_exceeded", "model_inapplicable",
                                   "inconsistent_inputs"),
            "inconsistent_inputs": ("inconsistent_inputs", "model_inapplicable",
                                    "limit_exceeded"),
            "model_inapplicable": ("model_inapplicable",),
            "limit_exceeded": ("limit_exceeded",)}[defect]
    if got not in want:
        return f"intended {defect}, reference says {got} ({assessment.violated})"
    return None


# ---------------------------------------------------------------------------
# The 100 cases
# ---------------------------------------------------------------------------

#: Parts whose datasheets publish an outline, so a fully declared case can put
#: a documented geometry in front of the tool instead of an assumed one.
CHIPS = [
    "vishay-crcw0402", "vishay-crcw0603", "vishay-crcw0805", "vishay-crcw1206",
    "vishay-crcw1210", "vishay-crcw1218", "vishay-crcw2010", "vishay-crcw2512",
    "yageo-rc0402", "yageo-rc0603", "yageo-rc0805", "yageo-rc1206",
    "yageo-rc1210", "yageo-rc1218", "yageo-rc2010", "yageo-rc2512",
]
LEADED = ["vishay-sfr16s", "vishay-sfr25", "vishay-sfr25h"]
ALL_OUTLINE = CHIPS + LEADED


def _voltage_for(power, resistance):
    return math.sqrt(power * resistance)


def case_specs(components: dict) -> list[dict]:
    """Every seed case, as a spec the builder realises and the reference checks.

    Two knobs do most of the work. ``power_w`` is what the design dissipates,
    chosen against the part's own rating. ``rise_k`` is how far above ambient the
    body settles, and the thermal resistance follows from the pair,
    ``R_th = rise / power`` -- which is the direction a real thermal note works
    in, and which keeps a case from wandering past a limit it was not built to
    test. Where a case IS built to pass a limit, it passes exactly one.
    """
    specs: list[dict] = []
    n = [0]

    def cid():
        n[0] += 1
        return f"S{n[0]:03d}"

    def add(part, *, power_w, rise_k, defect, reason, r=100.0, ambient_c=25,
            duration_s=60.0, **kw):
        specs.append(dict(cid=cid(), part=part, resistance=r,
                          voltage=math.sqrt(power_w * r), ambient_c=ambient_c,
                          duration_s=duration_s, rth=rise_k / power_w,
                          defect=defect, reason=reason, **kw))

    # ---- 34 sound --------------------------------------------------------
    for i, part in enumerate(ALL_OUTLINE):
        p = components[part]
        frac, amb = (0.35, 25) if i % 2 == 0 else (0.5, 40)
        power = p["rated_power_w"] * frac
        add(part, power_w=power, rise_k=25.0, r=100.0 * (1 + i % 5),
            ambient_c=amb, defect="physically_sound",
            reason=(f"{p['part_number']} dissipates {power:.4g} W against a "
                    f"{p['rated_power_w']} W rating in {amb} C air, settling "
                    f"25 K above ambient, with every declared span clear of "
                    f"its bound."),
            full=True, natural=(i % 3 != 2), emissivity=0.05,
            cond_span=400.0, cap_span=400.0, band=900.0, debye=250.0)
    for i, part in enumerate(ALL_OUTLINE[:9]):
        p = components[part]
        power = p["rated_power_w"] * 0.6
        add(part, power_w=power, rise_k=30.0, r=47.0 * (1 + i % 4),
            ambient_c=55, duration_s=120.0, defect="physically_sound",
            reason=(f"{p['part_number']} at 60 % of its rating in a 55 C "
                    f"enclosure: tight, and inside every limit it declares."),
            full=True, natural=(i % 2 == 0), emissivity=0.05,
            cond_span=400.0, cap_span=400.0, band=900.0, debye=250.0)

    # ---- 20 limit_exceeded ----------------------------------------------
    for part in ALL_OUTLINE[:8]:
        p = components[part]
        power = p["rated_power_w"] * 2.5
        add(part, power_w=power, rise_k=30.0, defect="limit_exceeded",
            reason=(f"dissipates {power:.4g} W against the {p['part_number']}'s "
                    f"{p['rated_power_w']} W rating -- 2.5 times the number the "
                    f"datasheet prints."),
            full=True, natural=True, emissivity=0.05,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw0402", "vishay-crcw0603", "yageo-rc0402",
                 "yageo-rc0603", "vishay-crcw0805", "yageo-rc0805"]:
        p = components[part]
        vmax = p["maximum_working_voltage_v"]
        v = vmax * 1.6
        power = p["rated_power_w"] * 0.5
        r = v * v / power
        specs.append(dict(
            cid=cid(), part=part, resistance=r, voltage=v, ambient_c=25,
            duration_s=60.0, rth=25.0 / power, defect="limit_exceeded",
            reason=(f"{v:.0f} V across a part the datasheet limits to {vmax} V, "
                    f"while the dissipation stays at half the rating -- the "
                    f"binding limit here is not the one a power check finds."),
            full=True, natural=True, emissivity=0.05,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0))
    for part in ["vishay-crcw1206", "vishay-crcw2010", "yageo-rc1206",
                 "yageo-rc2010", "vishay-sfr25", "yageo-rc2512"]:
        p = components[part]
        tmax = p["operating_temperature_range_c"][1]
        power = p["rated_power_w"] * 0.5
        add(part, power_w=power, rise_k=12.0, r=220.0, ambient_c=tmax - 5,
            duration_s=90.0, defect="limit_exceeded",
            reason=(f"ambient is {tmax - 5} C and a 12 K rise carries the body "
                    f"past the {tmax} C category limit the datasheet states."),
            full=True, natural=True, emissivity=0.05,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)

    # ---- 6 limit_exceeded that no payload field can carry -----------------
    #
    # A rated dissipation is a pair: 0.25 W AT 70 C, falling linearly to zero at
    # the permissible film temperature. The payload's `rated_power` is a scalar
    # and carries no ambient, so a part run above the ambient its rating is
    # stated at has a lower real rating that nothing in the declaration can say.
    # These six sit BELOW the printed rating and ABOVE the derated one, with
    # every other condition clean, so the only thing that could refuse them is
    # the derating -- and there is no field for it. Ground truth is the
    # datasheet's own derating curve, computed by hand; reference.py cannot
    # reach it either, and does not pretend to.
    # Only parts whose datasheet prints a derating knee can be used here: the
    # eleven Yageo sizes draw their curve as an image and print no knee, so
    # `derating` is null for them in components.json and they are not eligible.
    # A family built to test a derating cannot fill in the derating it tests.
    for part in ["vishay-crcw0805", "vishay-crcw1206", "vishay-crcw2010",
                 "vishay-crcw1210", "vishay-crcw2512", "vishay-sfr25"]:
        p = components[part]
        knee = p["derating"]["knee_c"]
        zero = p["derating"]["zero_power_c"] or p["permissible_film_temperature_c"]
        amb = 120
        derated = p["rated_power_w"] * (zero - amb) / (zero - knee)
        power = min(p["rated_power_w"] * 0.85, derated * 2.0)
        add(part, power_w=power, rise_k=10.0, r=220.0, ambient_c=amb,
            duration_s=90.0, defect="limit_exceeded",
            reason=(f"{power:.3g} W at a {amb} C ambient is under the "
                    f"{p['rated_power_w']} W the datasheet prints but "
                    f"{power / derated:.2g} times the {derated:.3g} W that "
                    f"rating derates to at {amb} C, and no payload field "
                    f"carries the ambient a rating is stated at."),
            full=True, natural=True, emissivity=0.02,
            reviewer_only="rated power not derated to the ambient",
            confidence="high",
            basis=("the datasheet derating curve: P70 falling linearly to zero "
                   "at the permissible film temperature, computed by hand"),
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)

    # ---- 18 model_inapplicable ------------------------------------------
    for part in ["vishay-crcw2512", "vishay-crcw2010", "vishay-crcw1218",
                 "yageo-rc2512", "vishay-sfr25"]:
        add(part, power_w=0.03, rise_k=27.0, r=470.0, duration_s=120.0,
            defect="model_inapplicable",
            reason=("radiation carries more than a tenth of the heat off this "
                    "surface, so a convection-only balance is not the model "
                    "being solved."),
            full=True, natural=True, emissivity=0.9,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw1206", "vishay-crcw2512", "yageo-rc1206",
                 "yageo-rc2512"]:
        add(part, power_w=0.2, rise_k=12.0, r=330.0, duration_s=120.0,
            defect="model_inapplicable",
            reason=("the internal gradient is not small at this conductivity, "
                    "so one temperature for the whole body is not defensible."),
            full=True, natural=True, conductivity=0.30, emissivity=0.02,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw0805", "yageo-rc0805", "vishay-crcw1206"]:
        add(part, power_w=0.2, rise_k=12.0, r=220.0, duration_s=0.02,
            defect="model_inapplicable",
            reason=("the horizon is shorter than the body's own diffusion "
                    "time, so a single exponential is not the response."),
            full=True, declare_fluid=False, conductivity=0.30, emissivity=0.02,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw1210", "yageo-rc1210", "vishay-sfr25h"]:
        add(part, power_w=0.08, rise_k=25.0, r=150.0, duration_s=120.0,
            defect="model_inapplicable",
            reason=("the temperature swing is wider than the 3 K span over "
                    "which the design says its conductance is constant."),
            full=True, natural=True, emissivity=0.02,
            cond_span=3.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw1218", "yageo-rc1218", "vishay-sfr16s"]:
        add(part, power_w=0.08, rise_k=25.0, r=180.0, duration_s=120.0,
            defect="model_inapplicable",
            reason=("the body runs far outside the 2 K span over which the "
                    "linear temperature coefficient is declared."),
            full=True, natural=True, emissivity=0.02,
            band=2.0, cond_span=900.0, cap_span=900.0, debye=200.0)

    # ---- 10 unit_or_sign_error ------------------------------------------
    for part in ["vishay-crcw0603", "yageo-rc0603", "vishay-crcw0805",
                 "yageo-rc0805"]:
        specs.append(dict(
            cid=cid(), part=part, resistance=4.7, voltage=12.0, ambient_c=25,
            duration_s=60.0, rth=40.0, defect="unit_or_sign_error",
            reason=("4.7 kohm was entered as 4.7 ohm, so the same 12 V rail "
                    "delivers a thousand times the intended power."),
            full=True, natural=True, emissivity=0.02,
            cond_span=2000.0, cap_span=2000.0, band=4000.0, debye=200.0))
    for part in ["vishay-crcw1206", "yageo-rc1206", "vishay-sfr25"]:
        p = components[part]
        power = p["rated_power_w"] * 0.7
        add(part, power_w=power, rise_k=25.0, defect="unit_or_sign_error",
            reason=("the rating was written in milliwatts and read as watts, "
                    "so the design believes the part is a thousand times "
                    "stronger than it is."),
            full=True, natural=True, emissivity=0.02,
            limit_overrides={"rated_power_w": p["rated_power_w"] / 1000.0},
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw2010", "yageo-rc2010", "vishay-crcw2512"]:
        add(part, power_w=0.75, rise_k=150.0, r=68.0, duration_s=180.0,
            defect="unit_or_sign_error",
            reason=("the temperature coefficient's sign was flipped, so the "
                    "resistance falls as the part heats and the dissipation "
                    "climbs instead of settling."),
            full=True, natural=True, emissivity=0.02,
            overrides={"temperature_coefficient_ppm_per_k": -800.0},
            cond_span=2000.0, cap_span=2000.0, band=4000.0, debye=200.0)

    # ---- 10 inconsistent_inputs -----------------------------------------
    for part in ["vishay-crcw0805", "vishay-crcw1206", "yageo-rc0805",
                 "yageo-rc1206", "vishay-sfr25"]:
        geo = outline(components[part])
        add(part, power_w=0.1, rise_k=25.0, r=220.0, duration_s=90.0,
            defect="inconsistent_inputs",
            reason=("the declared characteristic length and the declared "
                    "volume over surface area describe two different bodies, "
                    "a factor of ten apart."),
            full=True, natural=True, emissivity=0.02,
            ctx_overrides={"characteristic_length_m": geo["lc"] * 10.0},
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)
    for part in ["vishay-crcw1210", "yageo-rc1210", "vishay-crcw2512",
                 "yageo-rc2512", "vishay-sfr25h"]:
        add(part, power_w=0.1, rise_k=25.0, r=330.0, duration_s=90.0,
            defect="inconsistent_inputs",
            reason=("the declared coefficient is five times what the declared "
                    "geometry and fluid produce, so two of those three numbers "
                    "cannot both be right."),
            full=True, natural=True, agreement=5.0, emissivity=0.02,
            cond_span=900.0, cap_span=900.0, band=2000.0, debye=200.0)

    # ---- 8 insufficient_input -------------------------------------------
    sparse = [
        ("vishay-crcw0805", 100.0, 12.0, 25),
        ("yageo-rc0603", 220.0, 9.0, 25),
        ("vishay-sfr25", 470.0, 24.0, 40),
        ("vishay-crcw1206", 47.0, 5.0, 25),
        ("yageo-rc1206", 1000.0, 24.0, 30),
        ("vishay-crcw2512", 10.0, 5.0, 25),
        ("yageo-rc2512", 33.0, 12.0, 45),
        ("vishay-sfr25h", 150.0, 15.0, 25),
    ]
    for part, r, v, amb in sparse:
        specs.append(dict(
            cid=cid(), part=part, resistance=r, voltage=v, ambient_c=amb,
            duration_s=60.0, rth=250.0, defect="insufficient_input",
            reason=("the design names a part, a rail and an ambient and "
                    "nothing else: no horizon, no thermal mass and no thermal "
                    "path, so no temperature follows from what it says."),
            full=False,
            sparse_drop=("duration_s", "heat_capacity_j_per_k",
                         "thermal_resistance_k_per_w"),
            basis="what the design omits, checked against convert.py REQUIRED"))
    return specs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE / "designs" / "seed"))
    args = ap.parse_args()
    components = load_components()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()

    kept, rejected = [], []
    for spec in case_specs(components):
        drop = spec.pop("sparse_drop", None)
        cid_ = spec.pop("cid")
        reviewer_only = spec.get("reviewer_only")
        built = build(cid=cid_, components=components, **spec)
        if built is None:
            rejected.append((cid_, spec["defect"], "no converged solution"))
            continue
        record, assessment, stable, probe, geo = built
        problem = verify(spec["defect"], assessment, stable,
                         spec.get("full", True), reviewer_only)
        if problem:
            rejected.append((cid_, spec["defect"], problem))
            continue
        if drop:
            for field_ in drop:
                record["stated_design"].pop(field_, None)
            record["stated_design"]["thermal_resistance_kind"] = "unstated"
            record["stated_design"].get("declared_limits", {}).pop(
                "source_maximum_current_a", None)
        record["label"]["reference_check"] = {
            "violated": assessment.violated,
            "unknown_count": len(assessment.unknown),
            "final_temperature_k": round(probe.t_final, 4),
            "steady_temperature_k": round(probe.t_steady, 4),
            "dissipated_power_w": round(probe.power, 6),
            "stable_under_both_temperature_readings": stable,
        }
        if reviewer_only:
            record["label"]["no_payload_field_carries"] = reviewer_only
        record["declaration_completeness"] = (
            "full_declaration" if spec.get("full", True) else "sparse_declaration"
        )
        kept.append(record)

    for record in kept:
        (out / f"{record['id']}.json").write_text(
            json.dumps(record, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")

    # The schema is load-bearing or it is decoration. Validate against it here,
    # where the files are written, so a field added to a record without being
    # added to `design_schema.json` fails now rather than in whatever reads the
    # records next. Skipped with a warning where jsonschema is not installed --
    # this benchmark is not worth a new hard dependency.
    try:
        import jsonschema
    except ImportError:
        print("NOTE: jsonschema not installed; records were not validated "
              "against design_schema.json")
    else:
        schema = json.loads(
            (HERE / "design_schema.json").read_text(encoding="utf-8"))
        invalid = 0
        for record in kept:
            try:
                jsonschema.validate(record, schema)
            except jsonschema.ValidationError as exc:
                invalid += 1
                print(f"  SCHEMA {record['id']}: {exc.message[:160]}")
        if invalid:
            print(f"{invalid} record(s) do not match design_schema.json")
            return 1
        print(f"all {len(kept)} records validate against design_schema.json")

    counts: dict[str, int] = {}
    for r in kept:
        counts[r["label"]["verdict"]] = counts.get(r["label"]["verdict"], 0) + 1
    print(f"kept {len(kept)}, rejected {len(rejected)}")
    print("composition:", json.dumps(counts, indent=1))
    for cid_, defect, why in rejected:
        print(f"  REJECTED {cid_} ({defect}): {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
