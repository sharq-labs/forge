"""Every tolerance used in this round, with where it came from.

Each entry names the preregistered case in VALIDATION_PLAN.json that fixed it.
Two entries are marked ``added_after_preregistration``: the plan committed to
making those two checks and did not print a number for either. Both numbers are
derived by a rule the plan had already stated for another case -- half of the
last printed digit of the source -- rather than chosen once the error was
visible. They are flagged here rather than quietly folded in with the rest.

No tolerance in this file was widened after a comparison was run. The round
report states that as a claim the reader can check against git history.
"""

from __future__ import annotations

TOLERANCES = {
    "dc_vs_ngspice": {
        "value": 2e-6,
        "absolute_floor_v": 1e-9,
        "plan_case": "DC node voltages against ngspice",
        "basis": "ngspice prints seven significant figures",
        "added_after_preregistration": False,
    },
    "dc_vs_hand_solve": {
        "value": 1e-9,
        "plan_case": "DC node voltages against a hand-written Gaussian elimination",
        "basis": "double-precision direct solve of a well-conditioned system",
        "added_after_preregistration": False,
    },
    "dc_conservation": {
        "value": 1e-9,
        "plan_case": "DC conservation",
        "basis": "charge conservation is exact for a lumped network",
        "added_after_preregistration": False,
    },
    "geometry_resistance": {
        "value": 1e-12,
        "plan_case": "Conductor resistance from geometry, R = rho L / A",
        "basis": "exact algebra on both sides",
        "added_after_preregistration": False,
    },
    "tcr_vs_iec60751": {
        "value": 0.05,
        "plan_case": "Linear TCR against IEC 60751 platinum",
        "basis": (
            "the observed deviation must equal the analytically predicted "
            "omitted quadratic term to within 5 percent of the prediction"
        ),
        "added_after_preregistration": False,
    },
    "iec60751_recitation": {
        "value": 3.6e-5,
        "plan_case": (
            "expected_limitations: cross-validated against the standard's own "
            "published ratio W(100) = 1.3851"
        ),
        "basis": (
            "half of the last printed digit of the published figure, "
            "0.00005/1.3851 = 3.61e-5 -- the same printed-precision rule the "
            "plan preregistered for ngspice"
        ),
        "added_after_preregistration": True,
    },
    "lumped_vs_rk4": {
        "value": 1e-9,
        "plan_case": "Lumped thermal transient against an independent RK4",
        "basis": "RK4 at 200k steps on a linear scalar ODE reaches round-off",
        "added_after_preregistration": False,
    },
    "lumped_energy_balance": {
        "value": 1e-10,
        "plan_case": "Lumped thermal energy balance",
        "basis": "the first law admits no tolerance beyond round-off",
        "added_after_preregistration": False,
    },
    "diffusion_error_ratio": {
        "low": 0.5,
        "high": 1.5,
        "plan_case": "1-D diffusion against the closed form",
        "basis": (
            "observed error divided by the error the declared scheme itself "
            "predicts"
        ),
        "added_after_preregistration": False,
    },
    "battery_algebra": {
        "value": 1e-12,
        "plan_case": "Battery state of charge, terminal voltage and runtime",
        "basis": "exact algebra through a chain of milli-prefixed units",
        "added_after_preregistration": False,
    },
    "battery_charge_conservation": {
        "value": 1e-12,
        "plan_case": "Battery charge conservation",
        "basis": (
            "relative, or below the cancellation floor 4 ulp(z0) eta Q when "
            "little charge moved"
        ),
        "added_after_preregistration": False,
    },
    "cstr_trajectory": {
        "value": 1e-6,
        "plan_case": "CSTR trajectory against an independent RK4",
        "basis": "the oracle's own resolution, evidenced by a refinement ladder",
        "added_after_preregistration": False,
    },
    "cstr_steady_state_k": {
        "value": 1e-5,
        "plan_case": "CSTR steady states against a hand-written bisection",
        "basis": "an algebraic route with no time integration",
        "added_after_preregistration": False,
    },
    "gas_constant": {
        "value": 1e-9,
        "plan_case": "CSTR gas constant against CODATA 2022",
        "basis": "admits the stored truncation of 1.8e-11 and refuses more",
        "added_after_preregistration": False,
    },
    "applicability_utilization": {
        "value": 1e-12,
        "plan_case": (
            "not separately preregistered; the utilizations are exact algebra "
            "and are held to the same round-off band every other exact "
            "algebraic case in the plan is held to"
        ),
        "basis": "exact algebra on both sides",
        "added_after_preregistration": True,
    },
    "peukert": {
        "value": 1e-12,
        "plan_case": (
            "Battery state of charge, terminal voltage and runtime -- the "
            "same exact-algebra band, applied to the capacity derating in the "
            "same declaration"
        ),
        "basis": "exact algebra on both sides",
        "added_after_preregistration": False,
    },
}


def value(name: str) -> float:
    return TOLERANCES[name]["value"]
