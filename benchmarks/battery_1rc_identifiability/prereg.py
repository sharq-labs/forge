"""Battery 1RC identifiability and independent evidence: the preregistration, committed BEFORE any parameter is fitted.

``python -m benchmarks.battery_1rc_identifiability.prereg`` writes PREREGISTRATION.json and its .sha256. The NASA
closure (benchmarks/battery_1rc_closure) is preserved unchanged and is not re-evaluated here.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = HERE / "PREREGISTRATION.json"

PREREG = {
    "schema": "forge.battery_1rc_identifiability.preregistration/1",
    "preregistration_id": "battery_1rc_identifiability.lg_hg2_25c.v1",
    "capability": "battery.thevenin_1rc",
    "frozen_before": "any parameter fit and any held-out comparison on these data",
    "nasa_closure_preserved": "benchmarks/battery_1rc_closure is not modified and not re-evaluated",
    "data": {
        "dataset": "LG 18650HG2 Li-ion Battery Data (Kollmeyer, Vidal, Naguib, Skells), McMaster University",
        "doi": "10.17632/cp3473x7xv.3", "licence": "CC BY 4.0 (Mendeley public API); cite the DOI",
        "cell": "ONE new 3 Ah LG HG2 18650 cell (readme: 'A brand new 3Ah LG HG2 cell'); serial in the CSV header",
        "files": {
            "549_HPPC.csv": "70ffb357511dd77e7c6bc14c642a095ddd51d6918b547987247100a3bd2ea29d",
            "549_C20DisCh.csv": "52eff1a8d273f353d557af8172139c2f23709499d36130ac24ffbbb820e8f232",
            "551_Cap_1C.csv": "d9b9dd9b9b842ee6ba91f79a85512d2306527103d2f1cef5ecec4f962a75d83e",
            "549_Dis_0p5C.csv": "85f6147f9bc21157e777a547229af5f252360c308a753672ef3eb1144b57fa75",
            "549_Dis_2C.csv": "87b77c00e18242b177bd7a2eac8faa46ad2139c15aa94c146388ae13eba92a06",
        },
        "identity_check": "every file's sha256 equals the sha256 Mendeley publishes for it (MENDELEY_MANIFEST.json of "
                          "branch claude/domain-real-data, read from the Mendeley public API)",
        "reader": "benchmarks/battery_1rc_identifiability/lghg2.py: bytes in; a Prog Time written twice is one sample "
                  "when V and I agree within the published accuracy (else the file is refused)",
        "measurement_uncertainty": {
            "status": "DECLARED_TYPE_B (publisher's instrument statement; no calibration certificate)",
            "voltage": "+/-5 mV (0.1 % of the 5 V full scale), uniform -> 2.89 mV standard",
            "current": "+/-75 mA (0.1 % of the 75 A full scale), uniform -> 43.3 mA standard",
            "case_temperature": "+/-1 degC (AD592)",
            "charge_counter": "UNKNOWN (never read: charge is integrated from the measured current)",
            "source": "dataset readme: 'Digatron Firing Circuits Universal Battery Tester channel with a voltage and "
                      "current accuracy of 0.1% of full scale'; 'AD592 +/-1degC accuracy'",
        },
        "temperature": "25 degC ambient block only; the model has no temperature dependence",
    },
    "excluded_with_reason": {
        "drive cycles (UDDS, HWFET, LA92, US06, Mixed)": "they contain regenerative CHARGE current; the 1RC route is "
                                                          "discharge/rest only and refuses charge; adding charge physics "
                                                          "is out of scope until evidence shows the need",
        "549_Dis_0p5C, 549_Dis_2C": "both files start 60 s into the load step (first Step Time 60 s): the initial "
                                    "polarization is not evidenced",
        "HPPC charge pulses": "charge is outside the model",
        "HPPC windows below SOC 0.10": "outside the declared applicability (strong low-SOC resistance dependence)",
        "truncated pulses": "a discharge pulse step shorter than 9.5 s, or whose median current differs from the "
                            "nearest commanded level (3, 6, 12, 18 A) by more than 1 %, was stopped by the tester",
    },
    "construction": {
        "sign": "Forge current = -Current (Digatron reports discharge as negative)",
        "rest_band_A": 0.075,
        "rest_band_basis": "the published current accuracy: a |current| within it is not distinguishable from rest",
        "hold": "BACKWARD (the current at sample k flowed over [t_(k-1), t_k]); forward hold is a sensitivity only",
        "soc": "z = 1 at the first HPPC sample, minus the net integrated charge over Q_HPPC = the net charge "
               "delivered by the whole HPPC record (100 % to the tester's 0 %); the same Q for every test",
        "ocv": "FIXED, not fitted: the last sample of the first rest and of every rest >= 3000 s in the HPPC record, "
               "as (z, V) knots, linear between; the window and test SOC ranges must lie inside the knot range",
        "pulse_window": "the rest step immediately before a discharge pulse step (~10 s), the pulse step (~10 s) and "
                        "the rest step after it (~40 s), ending before the charge pulse; 0.1 s sampling",
        "pulse_initial_state": "z from the coulomb count; v_p0 = 0 with basis: >= 590 s rest after the preceding "
                               "charge pulse or >= 3000 s after an SOC step; screen: the measured voltage moves by "
                               "<= 1 mV over the pre-pulse rest, otherwise the window is excluded",
        "cc_tests": "551_Cap_1C (starts at rest) and the discharge step of 549_C20DisCh (from its preceding rest): z0 = 1 "
                    "on Q_HPPC, v_p0 = 0 after the protocol rest; each profile is truncated where z first falls below "
                    "0.10 (declared scoring end)",
    },
    "roles": {
        "calibration": "HPPC discharge-pulse windows of the 3 A (1C) and 18 A (6C) pulses at every SOC level >= 0.10",
        "heldout_pulses": "HPPC discharge-pulse windows of the 6 A (2C) and 12 A (4C) pulses at the same levels "
                          "(current interpolation inside the calibrated range)",
        "heldout_cc": "551_Cap_1C and the C/20 discharge, separate tests on later or different days",
        "descriptive_only": "the 0.9 A SOC-step windows with their 1 h relaxation (a slower time scale than one RC "
                            "fitted to pulses can represent; reported, never accepted)",
        "independence": "ONE cell: every comparison is within-cell; no cross-cell transfer is tested",
    },
    "models": {
        "rint": "OCV table (fixed) + R0", "1rc": "OCV table (fixed) + R0 + R1 + C1 (engcore thevenin_route)",
        "bounds": {"R0_ohm": [0.001, 0.2], "R1_ohm": [0.0001, 0.2], "C1_F": [1.0, 1.0e6]},
        "bounds_basis": "R0, R1 within 0.05-10x the 20 mOhm impedance in the cell header; C1 spans tau from "
                        "1e-4 s to 2e5 s: wide, physical-sign bounds only",
        "objective": "sum of squared voltage residuals over every scored calibration sample",
        "optimizer": "scipy least_squares (trf) in log-parameters; 8 fixed starts",
        "parameter_set_temperature_range": "calibration case-temperature min and max, each widened by the 1 degC "
                                           "sensor accuracy (declared now, from the published accuracy)",
        "parameter_set_max_current": "18 A commanded maximum plus the 0.075 A current accuracy",
    },
    "identifiability": {
        "diagnostics": ["profiles of the objective in log R0, log R1, log C1 and log tau (others re-optimized)",
                        "window-block bootstrap of the calibration windows (B = 200, seed 0)",
                        "Gauss-Newton correlations and condition number",
                        "hold-convention (forward vs backward) shift",
                        "v_p0 sensitivity: -(preceding charge current) x R1 x exp(-590 s / tau)"],
        "parameter_identified_if": "profile rise >= 10 % within a factor of 3 on both sides, AND bootstrap CV <= "
                                   "0.25, AND not on a bound, AND the hold-convention shift <= 10 %",
        "decision": "IDENTIFIABLE if R0, R1 and C1 are each identified; WEAKLY_IDENTIFIABLE if tau or R0 is but R1 or "
                    "C1 is not; NOT_IDENTIFIABLE otherwise",
    },
    "validation": {
        "acceptance": {
            "heldout_pulses": {"RMSE_mV_max": 15.0, "P95_abs_mV_max": 30.0},
            "heldout_cc": {"RMSE_mV_max": 25.0, "P95_abs_mV_max": 50.0},
            "basis": "pulse windows: 3x / 6x the published 5 mV voltage accuracy; constant-current tests include "
                     "OCV-table interpolation and slow diffusion, so 5x / 10x. The earlier Gate A limits (50 / 90 mV) "
                     "are reported for continuity",
            "applicability": "a set holding any window or test the route judges outside its validated domain cannot "
                             "PASS (NOT_ASSESSABLE)",
        },
        "metrics": ["RMSE", "MAE", "bias", "max |error|", "P95 |error|", "lag-1 residual autocorrelation",
                    "per-window RMSE", "load vs relaxation split", "calibration vs held-out gap", "execution seconds"],
        "comparison": "paired bootstrap over windows (B = 2000, seed 0) of RMSE_Rint - RMSE_1RC: 1RC_BETTER if the "
                      "95 % interval is above 0, RINT_BETTER if below, NOT_DISTINGUISHED otherwise; one cell",
        "predictions": "1RC through thevenin_route.run_thevenin_1rc; Rint through the production kernel on loaded "
                       "intervals and V = OCV(z) at rest (the kernel refuses I = 0)",
    },
    "outcome_mapping": {
        "MODEL_VALIDATION_SUPPORTED": "IDENTIFIABLE and every held-out set PASSES for the 1RC",
        "IDENTIFIABILITY_SUPPORTED": "IDENTIFIABLE, and a held-out set is NOT_ASSESSABLE",
        "MODEL_REJECTED": "IDENTIFIABLE and a held-out set FAILS for the 1RC",
        "INSUFFICIENT_MEASUREMENT_EVIDENCE": "WEAKLY_IDENTIFIABLE or NOT_IDENTIFIABLE",
        "ledger_rule": "an outcome is a report, not a promotion. calibration may PASS only on IDENTIFIABLE; "
                       "independent_validation stays MISSING with one cell (no cross-cell transfer); measurement_uq "
                       "is decided by review of the Type B evidence, not by this script",
    },
}


def canonical(doc) -> bytes:
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True).encode() + b"\n"


def main() -> int:
    data = canonical(PREREG)
    PREREG_PATH.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    PREREG_PATH.with_suffix(".sha256").write_bytes((digest + "\n").encode())
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
