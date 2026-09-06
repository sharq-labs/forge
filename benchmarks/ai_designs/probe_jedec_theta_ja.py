"""One design, three declarations: what the tool does with a JEDEC theta-JA.

    python benchmarks/ai_designs/probe_jedec_theta_ja.py --src src

The design is deliberately dull. A 220 ohm chip on a 3 V rail dissipates 41 mW.
Its thermal path is stated as **220.8 C/W, the OPA333 DBV theta-JA from the TI
datasheet**, used as if it were this body's conductance to ambient -- which is
the use JESD51-3 rules out, and which a design asked to "choose a package" makes
almost by reflex. Nothing else about the design is wrong: 41 mW against a
0.25 W rating, a 9 K rise off a 40 C ambient, every limit far away.

The question is whether the tool notices, and the answer depends entirely on
what else the design says. That is the finding, and this file is how it is
reproduced.

Three variants, run here in order:

1. **The fluid is not declared.** The design says nothing about the air. Three
   convection conditions come back UNKNOWN and the report is
   INSUFFICIENT_EVIDENCE. The tool does not accept the coefficient -- but it
   does not name the misuse either. It says it cannot tell.
2. **The fluid is declared, with real air.** k = 0.0263 W/(m K), Pr = 0.707,
   nu = 1.589e-5 m2/s, still air over the chip's own length. Now the tool can
   evaluate Churchill-Chu and compare. The declared coefficient is about 34
   times what the correlation gives, and the report is NOT_SUPPORTED on
   `convection_conductance_agreement_ratio` alone, with nothing unknown.
3. **The fluid is declared, and the conductance is a plausible board figure.**
   250 K/W instead of 220.8 -- numerically similar, physically a different
   claim, and equally unsupported by the geometry-and-fluid it sits beside.
   The tool refuses this one too, which is the honest behaviour: it is not
   detecting "a JEDEC number", it is detecting that a stated coefficient and a
   stated fluid do not agree.

The point of variant 3 is that the tool has no notion of JESD51 and claims
none. What it has is a consistency check, and the consistency check happens to
catch this misuse -- by a route a human reviewer, reading the datasheet and
checking the junction temperature, would not have taken.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import convert as conv  # noqa: E402

AREA = 8.25e-6          # m2, CRCW0805 outline, document 20035
LENGTH = 2.872e-3       # m, sqrt of that area


def design(*, declare_fluid: bool, rth: float, kind: str) -> dict:
    ctx = {
        "characteristic_length_m": 1.515e-4,
        "surface_area_m2": AREA,
        "body_volume_m3": 1.25e-9,
        "body_conductivity_w_per_m_k": 30.0,
        "surface_emissivity": 0.02,
        "melting_temperature_c": 2072.0,
        "constant_conductance_span_k": 900.0,
        "constant_capacity_span_k": 900.0,
        "linearization_band_k": 2000.0,
        "debye_temperature_k": 200.0,
    }
    if declare_fluid:
        ctx.update({
            "airflow": "still",
            "fluid": "air",
            "convection_length_m": LENGTH,
            # Dry air near 300 K, Incropera et al. 6th ed. Table A.4.
            "fluid_conductivity_solved_w_per_m_k": 0.0263,
        })
    return {
        "id": "X001",
        "prompt_id": "P06",
        "source": {"kind": "hand_built"},
        "stated_design": {
            "part_id": "vishay-crcw0805",
            "package_id": "ti-opa333-dbv-sot23-5",
            "source_voltage_v": 3.0,
            "resistance_ohm": 220.0,
            "reference_temperature_c": 20.0,
            "temperature_coefficient_ppm_per_k": 100.0,
            "ambient_c": 40,
            "duration_s": 300.0,
            "thermal_resistance_k_per_w": rth,
            "thermal_resistance_kind": kind,
            "heat_capacity_j_per_k": 0.005,
            "declared_limits": {
                "rated_power_w": 0.25,
                "maximum_working_voltage_v": 150,
                "maximum_operating_temperature_c": 155,
                "source_maximum_current_a": 0.1,
            },
            "declared_thermal_context": ctx,
        },
        "label": {"verdict": "model_inapplicable", "reason": "probe",
                  "labeller": "probe"},
    }


VARIANTS = (
    ("1. JEDEC theta-JA, fluid not declared",
     dict(declare_fluid=False, rth=220.8, kind="junction_to_ambient")),
    ("2. JEDEC theta-JA, real air declared",
     dict(declare_fluid=True, rth=220.8, kind="junction_to_ambient")),
    ("3. plausible board figure, real air declared",
     dict(declare_fluid=True, rth=250.0, kind="body_to_ambient")),
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    args = ap.parse_args()
    sys.path.insert(0, args.src)
    from engcore.mcp.problem import run_electrothermal_case

    components = conv.load_components()
    for title, kwargs in VARIANTS:
        c = conv.convert(design(**kwargs), components, "stated_only")
        if not c.ok:
            print(f"{title}\n  UNCONVERTIBLE: {c.unconvertible_because}\n")
            continue
        run = run_electrothermal_case(c.payload)
        violated = [x for rep in run.reports for rec in rep.validity
                    for x in rec.assessment.violated]
        unknown = sorted({x for rep in run.reports for rec in rep.validity
                          for x in rec.assessment.unknown})
        flagged = [n["field"] for n in c.notes if n["class"] == "invented"]
        print(title)
        print(f"  verdict   : {sorted({x.verdict.value for x in run.reports})}")
        print(f"  violated  : {violated or '-'}")
        print(f"  unknown   : {unknown or '-'}")
        print(f"  conversion flagged: {flagged or '-'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
