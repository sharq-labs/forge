"""Battery 1RC cross-cell evaluation on Kirkaldy 2024 LG M50T: the preregistration, committed BEFORE any fit.

``python -m benchmarks.battery_1rc_crosscell.prereg --receipts <bol25.sha256>`` writes PREREGISTRATION.json (+ .sha256).
The NASA closure and the LG HG2 identifiability experiment are preserved and not re-evaluated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = HERE / "PREREGISTRATION.json"

CAL_CELLS = ["Expt 3/D", "Expt 3/E", "Expt 3/F", "Expt 4/D", "Expt 4/E", "Expt 5/D", "Expt 5/E"]
HELD_CELLS = ["Expt 1/D", "Expt 1/E", "Expt 1/F", "Expt 2,2/C", "Expt 2,2/D"]


def build(receipts: dict[str, str]) -> dict:
    return {
        "schema": "forge.battery_1rc_crosscell.preregistration/1",
        "preregistration_id": "battery_1rc_crosscell.kirkaldy2024_m50t_25c_bol.v1",
        "capability": "battery.thevenin_1rc",
        "frozen_before": "any parameter fit and any comparison on these data",
        "inspected_before_freeze": "the step structure (currents, durations, sampling, voltage and temperature ranges) "
                                   "of cell Expt 5/D's RPT0 files only, a CALIBRATION cell; no voltage was compared "
                                   "with any model",
        "preserved": ["benchmarks/battery_1rc_closure (NASA)", "benchmarks/battery_1rc_identifiability (LG HG2)"],
        "data": {
            "dataset": "Kirkaldy et al. 2024, 'Lithium-ion battery degradation: comprehensive cycle ageing data and "
                       "analysis for commercial 21700 cells', Zenodo 10.5281/zenodo.10637534 (CC BY 4.0); J. Power "
                       "Sources (2024) 234185",
            "cells": "LG M50T (LG GBM50T2170) 21700, base-cooled at 25 degC; 12 cells, beginning of life (RPT0, before "
                     "any ageing set)",
            "retrieval": "HTTP range requests on the five experiment archives: the zip central directory, then only the "
                         "selected members, each CRC32-checked against the directory (owner-approved partial download, "
                         "2026-10-15)",
            "files_sha256": receipts,
            "channels": "Time (s), Voltage (V), Current (mA; negative = discharge), Charge (mA.h), Temperature (degC)",
            "measurement_uncertainty": "UNKNOWN: the record does not state the BioLogic cycler's accuracy (not read from "
                                       "the paper); never set to zero",
        },
        "roles": {
            "calibration_cells": CAL_CELLS, "heldout_cells": HELD_CELLS,
            "independence_unit": "cell; the held-out cells are other physical cells from other experiments' rigs",
            "split_rule": "by experiment number, fixed before any fit: experiments 3-5 calibrate, 1-2 are held out",
        },
        "construction": {
            "sign": "Forge current [A] = -Current[mA] / 1000",
            "rest_band_A": 0.05,
            "rest_band_basis": "the protocol has only 0 or |I| >= 0.5 A in these tests; 50 mA separates them",
            "temperature_dropouts": "a Temperature sample outside [15, 40] degC in a 25 degC base-cooled test is a sensor "
                                    "dropout: it is excluded from the applicability check and counted; a window with any "
                                    "dropout inside its pulse is excluded",
            "hold": "BACKWARD; forward hold is a sensitivity only",
            "soc": "per cell, z = 1 at the end of the post-charge rest (the first discharge-pulse step's preceding rest) "
                   "and z decreases by the integrated discharge over Q",
            "q_basis": "Q_cal = the mean, over the CALIBRATION cells, of each cell's net 25-pulse-GITT discharge to its "
                       "cutoff; used for every cell in the primary evaluation",
            "ocv": "measured: the last sample of every rest >= 3000 s in each calibration cell's 25-pulse GITT (and of "
                   "the post-charge rest at z = 1), z on Q_cal; the calibration OCV is the mean, knot by knot, over "
                   "the calibration cells that reach that knot; linear between knots; never extrapolated",
            "gitt25_window": "the last 60 s of the rest before a 2.5 A discharge pulse, the pulse (~288 s, 0.1 s "
                             "sampling) and the first 600 s of the rest after it",
            "gitt5_window": "the same for the 5-pulse GITT (~1440 s pulses)",
            "initial_state": "z from the coulomb count; v_p0 = 0 with basis: the preceding rest is >= 3000 s; screen: "
                             "the voltage moves <= 1 mV over the last 60 s of that rest, otherwise excluded",
            "soc_scope": "windows whose z stays in [max(0.10, lowest knot), 1]; others are excluded and counted",
        },
        "models": {
            "rint": "calibration OCV + R0", "1rc": "calibration OCV + R0 + R1 + C1 (engcore thevenin_route)",
            "bounds": {"R0_ohm": [0.001, 0.2], "R1_ohm": [0.0001, 0.2], "C1_F": [1.0, 1.0e7]},
            "objective": "sum of squared voltage residuals over every scored calibration sample",
            "optimizer": "scipy least_squares (trf), log-parameters, 8 fixed starts",
            "parameter_set_temperature_range": "min and max of the valid (non-dropout) calibration temperature samples; "
                                               "NOT widened (no admitted sensor accuracy)",
            "parameter_set_max_current": "the largest calibration current",
        },
        "identifiability": {
            "parameter_identified_if": "profile rise >= 10 % within a factor of 3 on both sides, AND cell-block bootstrap "
                                       "(B = 200, seed 0, resampling calibration CELLS) CV <= 0.25, AND not on a bound, "
                                       "AND the hold-convention shift <= 10 %",
            "decision": "IDENTIFIABLE if R0, R1 and C1 are each identified; WEAKLY_IDENTIFIABLE if tau or R0 is but R1 or "
                        "C1 is not; NOT_IDENTIFIABLE otherwise",
        },
        "validation": {
            "primary": "held-out cells' 25-pulse GITT windows, STRICT TRANSFER (calibration OCV, Q_cal, parameters)",
            "secondary": "held-out cells' 5-pulse GITT windows (long constant-current pulses), strict transfer",
            "descriptive_only": "the same held-out windows with each held-out cell's own measured OCV and own Q "
                                "(parameter transfer only)",
            "acceptance": {
                "primary": {"RMSE_mV_max": 15.0, "P95_abs_mV_max": 30.0, "also_load_only": True},
                "secondary": {"RMSE_mV_max": 25.0, "P95_abs_mV_max": 50.0, "also_load_only": True},
                "basis": "the LG HG2 limits, kept; and since the LG HG2 review showed that pooling rest samples can hide a "
                         "load miss, the load-only samples must meet the same limits",
                "applicability": "a set holding any window outside the validated domain is NOT_ASSESSABLE in both "
                                 "directions",
            },
            "comparison": "cell-block paired bootstrap over held-out cells (B = 2000, seed 0) of RMSE_Rint - RMSE_1RC; "
                          "fewer than 2 units: NOT_ASSESSABLE",
        },
        "outcome_mapping": {
            "MODEL_VALIDATION_SUPPORTED": "IDENTIFIABLE, and the primary and secondary sets PASS for the 1RC",
            "IDENTIFIABILITY_SUPPORTED": "IDENTIFIABLE, no set FAILS, and a set is NOT_ASSESSABLE",
            "MODEL_REJECTED": "IDENTIFIABLE and the primary or secondary set FAILS for the 1RC",
            "INSUFFICIENT_MEASUREMENT_EVIDENCE": "WEAKLY_IDENTIFIABLE or NOT_IDENTIFIABLE",
            "ledger_rule": "an outcome is a report, not a promotion. independent_validation may PASS only on "
                           "MODEL_VALIDATION_SUPPORTED AND with an admitted measurement uncertainty for THIS dataset; "
                           "Kirkaldy's is UNKNOWN, so the gate stays MISSING unless the owner admits one",
        },
    }


def canonical(doc) -> bytes:
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True).encode() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", required=True, type=pathlib.Path)
    receipts = {}
    for line in parser.parse_args().receipts.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        receipts[name] = digest
    data = canonical(build(receipts))
    PREREG_PATH.write_bytes(data)
    PREREG_PATH.with_suffix(".sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(hashlib.sha256(data).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
