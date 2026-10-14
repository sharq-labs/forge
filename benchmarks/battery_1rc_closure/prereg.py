"""Battery 1RC scientific closure: the preregistration, written and committed BEFORE any parameter is fitted.

Run once: ``python -m benchmarks.battery_1rc_closure.prereg``. The JSON it writes is byte-pinned by its .sha256 and
by tests/benchmarks/test_battery_1rc_closure.py; every later step refuses to run against another preregistration.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = HERE / "PREREGISTRATION.json"
PREREG_ID = "battery_1rc_closure.nasa_pcoe_fy08q4.v1"

PREREG = {
    "schema": "forge.battery_1rc_closure.preregistration/1",
    "preregistration_id": PREREG_ID,
    "capability": "battery.thevenin_1rc",
    "frozen_before": "any parameter fit and any look at the validation cell's channels",
    "data": {
        "source": "NASA Ames Prognostics Center of Excellence, Li-ion Battery Aging Datasets",
        "catalog": "https://data.nasa.gov/dataset/li-ion-battery-aging-datasets",
        "archive_url": "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip",
        "archive_sha256": "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e",
        "archive_bytes": 209708670,
        "inner_archive": "5. Battery Data Set/1. BatteryAgingARC-FY08Q4.zip",
        "protocol_as_published": "room temperature; CC charge 1.5 A to 4.2 V then CV to 20 mA; CC discharge 2 A to "
                                 "2.7 / 2.5 / 2.2 / 2.5 V for cells 5 / 6 / 7 / 18; EIS sweeps between cycles",
        "ingestion": "tools.nasa_battery_aging (byte receipt + canonical record; no sign normalization, no SOC, no "
                     "segmentation, sensor uncertainty UNKNOWN)",
        "refused_cells": {"B0018": "the importer refuses the file: cycle[114].data.Voltage_measured[940] is NaN "
                                   "(fail closed; never repaired)"},
    },
    "roles": {
        "calibration": {"cells": ["B0005", "B0007"], "discharge_ordinals": [2, 20]},
        "within_cell_holdout": {"cells": ["B0005", "B0007"], "discharge_ordinals": [21, 30],
                                "claim": "NARROW: later cycles of the calibration cells (temporal holdout, same cells)"},
        "cross_cell_validation": {"cells": ["B0006"], "discharge_ordinals": [2, 30],
                                  "claim": "TRANSFER between cells of one batch and one protocol; B0006 was chosen "
                                           "from its published cutoff (2.5 V, inside the calibration cells' 2.7-2.2 V "
                                           "span) without opening its channels"},
        "capacity_source_only": "discharge ordinal 1 of every cell (no earlier capacity exists)",
        "ageing_window": "discharge ordinals 1-30 only (early life); ageing, capacity fade and resistance growth are "
                         "excluded by the model and not represented by these parameters",
    },
    "trajectory_construction": {
        "sign": "Forge current = -Current_measured (NASA reports discharge as negative). Verified per cycle by the "
                "passive step response: where the declared discharge current rises above the rest band, the terminal "
                "voltage must fall below the initial rest voltage; otherwise the cycle is refused",
        "rest_band_A": 0.010,
        "rest_rule": "|Current_measured| <= rest_band_A is rest (0 A); a charge-direction current beyond the band "
                     "refuses the cycle",
        "hold": "BACKWARD: the current reported at sample k is taken to have flowed over [t_(k-1), t_k]. The forward "
                "hold is run only as the switch-time sensitivity diagnostic",
        "scored_samples": "every sample after the first; sample 0 defines the initial rest state",
        "screen_initial_rest_voltage_min_V": 4.15,
        "initial_state_of_charge": "1 at sample 0, on the capacity basis below (protocol: CV charge to 20 mA, then "
                                   "rest)",
        "capacity_basis": "the largest delivered capacity among this cell's EARLIER discharge cycles (causal)",
        "initial_polarization_V": 0.0,
        "initial_polarization_basis": "the CV charge tapers to 20 mA and the record starts at rest (|I| <= 10 mA); "
                                      "the residual is at most 20 mA x R1, reported as an initial-state sensitivity",
        "coulombic_efficiency": 1.0,
        "efficiency_basis": "discharge only; no charge-direction throughput enters any trajectory",
    },
    "models": {
        "compared": ["battery.cell.rint_ocv (OCV table + R0)", "battery.cell.thevenin_1rc (OCV table + R0 + R1 + C1)"],
        "ocv_knots_soc": [0.0, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "ocv_bounds_V": [2.0, 4.5],
        "bounds": {"R0_ohm": [1e-4, 1.0], "R1_ohm": [1e-5, 1.0], "C1_F": [1.0, 1e6]},
        "objective": "sum of squared terminal-voltage residuals over every scored calibration sample; identical "
                     "data, initial state, capacity basis and cost for both models",
        "optimizer": "scipy.optimize.least_squares (trf), log-parameters for R0, R1, C1; 8 fixed starts",
        "parameter_set_temperature_range": "the minimum and maximum measured cell temperature over the calibration "
                                           "samples, fixed at fit time",
        "parameter_set_max_current": "the largest calibration current, fixed at fit time",
    },
    "identifiability": {
        "diagnostics": ["scaled Jacobian singular values and condition number",
                        "parameter correlation from the Gauss-Newton covariance",
                        "profile of the objective in log R0, log R1, log C1 and log tau (every other parameter "
                        "re-optimized)",
                        "cycle-block bootstrap of the calibration set (B = 40, seed 0)",
                        "dependence on the hold convention (forward vs backward) and on v_p0 = +20 mA x R1"],
        "parameter_identified_if": "the profile rises by >= 10 % of the optimal objective within a factor of 3 "
                                   "on BOTH sides, AND the bootstrap coefficient of variation is <= 0.25, AND the "
                                   "estimate is not on a bound",
        "decision": "IDENTIFIABLE if R0, R1 and C1 are each identified; WEAKLY_IDENTIFIABLE if tau or R0 is "
                    "identified but R1 or C1 is not; NOT_IDENTIFIABLE otherwise",
        "calibration_gate": "PASS only if the decision is IDENTIFIABLE",
        "note": "the 10 % / factor-3 rule is a declared practical rule, not a statistical interval: the residuals are "
                "autocorrelated, so a chi-square threshold would be unjustified",
    },
    "validation": {
        "metrics": ["RMSE", "MAE", "bias (mean of measured - predicted)", "max |error|", "P95 |error|",
                    "lag-1 residual autocorrelation", "per-cycle RMSE", "constant-current body and rest-tail "
                    "metrics separately", "calibration vs held-out gap", "execution seconds"],
        "acceptance_per_model": {"RMSE_mV_max": 50.0, "P95_abs_error_mV_max": 90.0,
                                 "basis": "the repository's earlier battery voltage Gate A limits (Sprint 3); "
                                          "engineering adequacy targets, NOT derived from a measurement uncertainty, "
                                          "which NASA does not state"},
        "comparison": "1RC is better than Rint on a held-out set iff the paired cycle-level bootstrap (B = 2000, "
                      "seed 0) 95 % interval of RMSE_Rint - RMSE_1RC lies above 0; Rint better iff it lies below 0; "
                      "otherwise NOT_DISTINGUISHED. Every outcome is reported",
        "predictions": "1RC through engcore.domains.battery.thevenin_route.run_thevenin_1rc; Rint through the "
                       "production Rint kernel engcore.domains.battery.solver.evaluate_step",
        "opened": "once, after the calibration and identifiability records are committed",
    },
    "uncertainty": {
        "measurement": "UNKNOWN unless an admissible calibrated sensor uncertainty is supplied; NASA states none",
        "parameter": "cycle-block bootstrap distribution, propagated jointly (no independence assumption)",
        "numerical": "NOT_APPLICABLE: the update is exact for piecewise-constant current (float rounding only)",
        "initial_state": "hold-convention and v_p0 sensitivity",
        "model_form": "held-out residuals beyond the propagated parameter spread; never set to zero",
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
