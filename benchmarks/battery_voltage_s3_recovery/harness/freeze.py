"""R11: freeze the selected model, its parameters and its Gate A policy.

Everything a later step could otherwise tune is written here and committed
before the locked holdout is opened:

* the model version and the parameter strategy,
* the fitted parameters themselves, with a standard error and an
  identifiability verdict each,
* the open-circuit voltage authority and its digest,
* the capacity and initial-state methods,
* the applicability contract, derived from validation evidence,
* the numerical requirements,
* the uncertainty channels and what each of them is,
* the Gate A thresholds, carried unchanged from the Sprint 3 preregistration.

The Gate A thresholds are copied from ``PREREGISTRATION.json`` by reading that
file, not by retyping the numbers, and a mismatch stops this script. R14 says
they do not move, and the way to mean that is to not have a second copy of them.

    python benchmarks/battery_voltage_s3_recovery/harness/freeze.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
S3_EVIDENCE = os.path.join(
    REPO, "benchmarks", "battery_thermal_flagship_s3", "evidence"
)
sys.path.insert(0, HERE)

import candidates as cd  # noqa: E402
import corpus as cp  # noqa: E402
from engcore.domains.battery import flagship_ocv_v2 as ocv_v2  # noqa: E402
from engcore.domains.battery import flagship_v2 as model_v2  # noqa: E402

PREREGISTRATION_SCHEMA = "battery_voltage_s3_recovery_prereg/1"

#: The candidate this round selects, and why. Written here rather than computed
#: so that the selection is a decision on the record and not an argmax that
#: could quietly move when a number does.
SELECTED = "M11"
SELECTION_RATIONALE = (
    "M10 and M11 are indistinguishable on the Gate A statistics -- M11 is "
    "2.4 mV better on mean absolute error and 0.5 mV better on RMSE, M10 is "
    "2.1 mV better on the 95th percentile -- and they carry the SAME number of "
    "fitted parameters, because M11's charge-state shape on the ohmic "
    "resistance is a measurement and not a parameter. So the residual "
    "statistics do not choose between them and R6 does: identifiability before "
    "complexity. "
    "M10 leaves 10 of its 42 parameters unidentified and M11 leaves 2, and the "
    "difference is concentrated exactly where it matters. In M10 the cold "
    "parameter unit -- the only unit that will predict the locked holdout -- "
    "leaves the ohmic reference resistance, the polarization reference "
    "resistance and the polarization activation energy all unidentified, with a "
    "normal-matrix condition number of 1.6e20 and a correlation of -0.9999 "
    "between R0 and its own activation energy. That is a fitter absorbing a "
    "real charge-state trend into a constant and its temperature slope. Giving "
    "it the measured trend instead leaves that unit fully identified at a "
    "condition number four orders of magnitude lower. "
    "A model whose parameters are not identified in the regime it is about to "
    "be tested in is not the simpler model, it is the less determined one."
)

#: Rejected alternatives, each with the evidence that rejected it.
REJECTED = {
    "M0": "Sprint 3's model on this corpus: 116.4 mV validation RMSE. It is the "
          "baseline, not a candidate.",
    "M1": "the two state authorities alone, with parameters per experiment "
          "group as Sprint 3 had them: 60.7 mV validation RMSE. It is half of "
          "M0's error and it is the step that matters scientifically -- the "
          "failure was a state-identification failure -- but a parameter set "
          "asked to serve two rates still compromises between them.",
    "M1p": "one pooled open-circuit voltage curve. Its admissible charge-state "
           "interval collapses to [0.85, 1.0], so it answers 13 % of the "
           "split's admissible samples. Its residual statistics are the best "
           "in the table and they are a statement about a narrower claim.",
    "M2": "both activation energies fixed at zero: 105.8 mV validation RMSE "
          "against M1's 60.7. The Arrhenius terms are real even though Sprint "
          "3 reported them weakly identified.",
    "M3": "M1 plus the measured charge-state shape on R0, without the parameter "
          "unit change: 61.3 mV against M1's 60.7. No improvement.",
    "M4": "M3 plus a second RC branch: 61.4 mV. Two more parameters, nothing.",
    "M5": "M1 plus a second RC branch: 62.6 mV. Worse than M1.",
    "M6": "parameters per experiment group and cell-temperature band: 51.6 mV "
          "RMSE but 111.6 mV P95, and its cold unit leaves both reference "
          "resistances unidentified.",
    "M7": "M6 with the activation energies fixed at zero: 93.2 mV. Same finding "
          "as M2.",
    "M8": "M6 plus the measured shape: better identifiability than M6 and still "
          "103.5 mV P95. Superseded by the block parameter unit.",
    "M9": "M6 plus a second RC branch: 51.9 mV RMSE, 115.9 mV P95, and the "
          "second branch is unidentified in three of five units.",
    "M10": "one parameter set per declared operating block, without the "
           "measured charge-state shape. It is the largest single step in the "
           "matrix -- 60.7 to 39.6 mV validation RMSE -- and it is not "
           "selected: its cold parameter unit, the one that predicts the "
           "holdout, leaves three of seven parameters unidentified at a "
           "condition number of 1.6e20. See the rationale for M11.",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read())


def load(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def frozen_gate_a() -> dict[str, Any]:
    """Gate A, read from the Sprint 3 preregistration rather than retyped."""
    prereg = load(os.path.join(S3_EVIDENCE, "PREREGISTRATION.json"))
    gate = prereg["gate_a"]
    acceptance = prereg["acceptance"]
    for metric, keys in (
        ("terminal_voltage", ("mae_v", "rmse_v", "p95_abs_v")),
        ("cell_temperature", ("mae_k", "rmse_k", "p95_abs_k")),
    ):
        for key in keys:
            if gate[metric].get(key) is None:
                raise SystemExit(
                    f"the Sprint 3 preregistration has no {metric}.{key}; Gate A "
                    "cannot be carried forward from a record that does not "
                    "state it"
                )
    return {
        "source": "benchmarks/battery_thermal_flagship_s3/evidence/PREREGISTRATION.json",
        "source_sha256": sha256_file(
            os.path.join(S3_EVIDENCE, "PREREGISTRATION.json")
        ),
        "thresholds_frozen_at_commit": "1297648e",
        "unchanged": (
            "every threshold below is read from the Sprint 3 preregistration at "
            "run time. This recovery does not hold a second copy of them and "
            "cannot weaken one by editing a number here"
        ),
        "gate_a": gate,
        "acceptance": acceptance,
    }


def applicability_from_validation(candidate_record: dict[str, Any]) -> dict[str, Any]:
    """The applicability contract, derived from validation evidence only.

    Sprint 3's applicability was wider than its own validation envelope: it
    claimed 0.5-4.5 A while the envelope classified every 2C cell FAILED. This
    contract does not repeat that. Each dimension below is either carried
    unchanged from Sprint 3, narrowed to what validation evidence supports, or
    widened only where this recovery brought new calibration and validation
    evidence for it.
    """
    validation = candidate_record["validation"]
    curves = {
        band: {
            "charge_state_interval": [
                ocv_v2.OCV_V2_CURVES[band].lower,
                ocv_v2.OCV_V2_CURVES[band].upper,
            ],
            "digest": ocv_v2.OCV_V2_CURVES[band].fingerprint,
        }
        for band in sorted(ocv_v2.OCV_V2_CURVES)
    }
    return {
        "inside": {
            "cell_temperature_bands_c": [
                {"band": name, "low": low, "high": high}
                for name, low, high in ocv_v2.CELL_TEMPERATURE_BANDS
            ],
            "charge_state_floor_per_band": {
                band: value["charge_state_interval"][0]
                for band, value in curves.items()
            },
            "load_current_a": [0.5, 2.5],
            "direction": "discharge and rest only",
            "usable_capacity_ah": [0.9, 2.0],
            "requires": [
                "a capacity state with a basis other than UNKNOWN, from a prior "
                "like-for-like discharge of the same cell",
                "an initial state with a basis other than UNKNOWN",
                "a charge state inside the declared curve's own interval for the "
                "run's declared band",
            ],
        },
        "outside": {
            "load_current_a_above": 2.5,
            "why_the_rate_ceiling_narrowed": (
                "Sprint 3 declared 0.5-4.5 A while its own validation envelope "
                "classified every 2C cell FAILED. The measured branch "
                "resistance rises from 0.169 to 0.208 ohm between 2 A and 4 A "
                "and this model's polarization is linear in current, so a 4 A "
                "run is outside what the form can represent rather than merely "
                "poorly fitted. Narrowing the contract to match the envelope is "
                "the correction Sprint 3's own evidence asked for"
            ),
            "cell_temperature_between_bands": (
                "nothing is measured between 13 and 23 degC in this archive, so "
                "a run whose declared band is neither cold nor warm is refused "
                "rather than interpolated"
            ),
            "charge_state_below_the_band_floor": (
                "below its floor a band's curve disagrees with itself by more "
                "than the frozen acceptance tolerance, which is the same rule "
                "Sprint 3 used to place its floor"
            ),
            "capacity_or_initial_state_unknown": (
                "a cell whose usable capacity or starting state cannot be "
                "established from prior evidence has no charge-state basis, and "
                "a prediction without one is a prediction about the rating "
                "rather than the cell"
            ),
        },
        "undeclared": (
            "any other cell chemistry, format or fixture, and any experiment "
            "group with no calibration cell -- the thermal conductance is a "
            "fixture property and the electrical parameters are fitted per "
            "operating block, so a group with no calibration cell has no "
            "parameter set and the model cannot be instantiated for it"
        ),
        "open_circuit_voltage_authority": curves,
        "derived_from": {
            "split": "validation",
            "coverage": validation["coverage"],
            "per_cell_voltage": {
                cell: {k: v for k, v in stats.items()}
                for cell, stats in validation["per_cell_voltage"].items()
            },
            "why_validation_and_not_the_holdout": (
                "an applicability contract is a model-development decision and "
                "validation evidence is what model development is allowed to "
                "use. This contract is frozen in this commit, before the locked "
                "holdout is opened, so no holdout residual could have shaped it"
            ),
        },
        "known_limitation": (
            "the cold band has exactly one calibration cell. Every in-band cell "
            "of the room-ambient corner was consumed by Sprint 3's three "
            "splits, and of the four cells that ran the low-ambient protocol "
            "one is the new holdout, one was Sprint 3's holdout and has been "
            "read, one is the validation cell and one is the calibration cell. "
            "A single calibration cell carries no cell-to-cell spread, and this "
            "recovery's own validation evidence puts that spread at 20 to 35 mV "
            "against a 50 mV acceptance tolerance"
        ),
    }


def main() -> int:
    candidates = load(os.path.join(EVIDENCE, "MODEL_CANDIDATES.json"))
    chosen = next(
        (item for item in candidates["candidates"] if item["key"] == SELECTED), None
    )
    if chosen is None:
        raise SystemExit(f"candidate {SELECTED} is not in the candidate record")
    unknown = sorted(
        set(REJECTED)
        - {item["key"] for item in candidates["candidates"]}
    )
    if unknown:
        raise SystemExit(f"rejected candidates not in the record: {unknown}")
    missing = sorted(
        {item["key"] for item in candidates["candidates"]}
        - set(REJECTED)
        - {SELECTED}
    )
    if missing:
        raise SystemExit(
            f"these candidates were neither selected nor rejected with a "
            f"reason: {missing}"
        )

    state = load(os.path.join(EVIDENCE, "BATTERY_STATE_AUTHORITY.json"))
    selection = load(os.path.join(EVIDENCE, "SELECTION.json"))

    identifiability = {
        unit["group"]: {
            "cells": unit["cells"],
            "trajectories": unit["trajectories"],
            "fitted": unit["fitted"],
            "standard_errors": unit["standard_errors"],
            "identifiability": unit["identifiability"],
            "correlated_pairs_above_0p9": unit["correlated_pairs_above_0p9"],
            "normal_matrix_condition_number": unit[
                "normal_matrix_condition_number"
            ],
            "at_declared_bound": unit["at_declared_bound"],
        }
        for unit in chosen["groups"]
    }

    record = {
        "schema": PREREGISTRATION_SCHEMA,
        "what_this_is": (
            "the frozen state of the recovery model before the new locked "
            "holdout is opened. Everything a later step could otherwise tune "
            "is here, and the commit that carries this file is the one whose "
            "SHA the Gate A result cites"
        ),
        "model": {
            "model_id": model_v2.MODEL_ID,
            "version": model_v2.MODEL_VERSION,
            "realization_version": model_v2.REALIZATION_VERSION,
            "form": (
                "unchanged from battery.cell.electrothermal_1rc@0.1.0: one RC "
                "branch, Arrhenius on both resistances, irreversible heat only. "
                "No parameter was added"
            ),
            "what_changed": [
                "the charge state is a fraction of a measured available charge "
                "rather than of the manufacturer's 2 Ah rating",
                "the open-circuit voltage authority is re-derived on that axis "
                "and conditioned on a declared cell-temperature band",
                "one parameter set per declared operating block rather than per "
                "experiment group",
                "a model-free channel-consistency screen on the measurement",
            ],
        },
        "selected_candidate": SELECTED,
        "selection_rationale": SELECTION_RATIONALE,
        "selection_evidence": "validation split only; the locked holdout is not "
                              "readable by the candidate harness",
        "rejected_alternatives": REJECTED,
        "parameter_strategy": {
            "unit": chosen["configuration"]["parameter_unit"],
            "unit_definition": (
                "one parameter set per (experiment group, ambient corner, "
                "nominal load). The thermal pair is a fixture property, which "
                "is why Sprint 3 made it per group; the electrical parameters "
                "are asked to serve one rate because this model's polarization "
                "is linear in current and the measured resistance is not"
            ),
            "free_parameters_per_unit": chosen["free_parameters_per_group"],
            "free_parameters_total": chosen["free_parameters_total"],
            "parameter_names": chosen["parameter_names"],
            "bounds": candidates["parameter_specs"],
            "objective": candidates["weights"],
            "fitted_on": "calibration trajectories only",
        },
        "frozen_parameters": identifiability,
        "capacity_authority": {
            "module": "engcore.domains.battery.capacity",
            "basis": "prior_like_for_like_discharge",
            "rule": (
                "the delivered capacity of the most recent prior discharge of "
                "the same cell at the same load level and ambient. UNKNOWN when "
                "there is none, and UNKNOWN carries no capacity"
            ),
            "never": (
                "the delivered capacity of the trajectory being predicted. That "
                "would make every charge state right by construction"
            ),
            "estimator_spread": state["capacity_estimator"],
            "cycle_inventory_sha256": state["cycle_inventory_sha256"],
        },
        "initial_state_authority": {
            "module": "engcore.domains.battery.initial_state",
            "bases": [
                "charge_termination_and_rest_voltage",
                "reproducible_charge_termination",
                "charge_termination_only",
            ],
            "rule": (
                "two independent witnesses. Where the charger reached its "
                "declared taper the claim is an absolute full charge; where it "
                "was cut off early -- which is every low-ambient run in this "
                "archive -- the claim is only that the run starts from the same "
                "state as the cycle its capacity was measured on, and the "
                "record says so"
            ),
            "full_charge_anchor_v": state["full_charge_anchor_v"],
            "full_charge_band_v": state["full_charge_band_v"],
            "charge_termination_bands": state["charge_termination_bands"],
            "unknown_is_a_refusal": True,
        },
        "ocv_authority": {
            "module": "engcore.domains.battery.flagship_ocv_v2",
            "source_record": ocv_v2.OCV_V2_SOURCE_RECORD,
            "source_sha256": ocv_v2.OCV_V2_SOURCE_SHA256,
            "derived_from_split": "calibration",
            "calibration_cells": list(ocv_v2.OCV_V2_CALIBRATION_CELLS),
            "bands": {
                band: {
                    "digest": curve.fingerprint,
                    "interval": [curve.lower, curve.upper],
                    "knots": len(curve.form.samples),
                }
                for band, curve in sorted(ocv_v2.OCV_V2_CURVES.items())
            },
            "band_rule": candidates["band_rule"],
        },
        "measurement_screen": candidates["measurement_screen"],
        "applicability": applicability_from_validation(chosen),
        "numerical_requirements": {
            "scheme": (
                "the closed-form update of the 1-RC cell over each measured "
                "interval at the temperature the previous interval left, which "
                "is exact for the declared equations within an interval"
            ),
            "refinement": (
                "the prediction is re-run with every measured interval halved "
                "and quartered; the movement in the reported metrics is "
                "recorded and must stay below a tenth of each acceptance "
                "tolerance, which is the requirement Sprint 3 froze"
            ),
            "refinement_tolerance_voltage_v": 0.005,
            "refinement_tolerance_temperature_k": 0.3,
            "conservation": (
                "the heat the cell reports over an interval must equal the heat "
                "the lumped body consumes in it"
            ),
        },
        "uncertainty_channels": {
            "parameter": (
                "QUANTIFIED. A standard error per fitted parameter from the "
                "fit's own Jacobian, with an identifiability verdict, in "
                "frozen_parameters above"
            ),
            "capacity_basis": (
                "QUANTIFIED, and new in this round. The like-for-like "
                "estimator's own spread against the capacity it predicts, "
                "measured on calibration cells: "
                f"{state['capacity_estimator']['p68_absolute_relative_error']:.4f} "
                "relative at one sigma"
            ),
            "open_circuit_voltage": (
                "QUANTIFIED as the authority's own interquartile spread across "
                "calibration pairs at each knot. It is the authority's scatter "
                "and not a measurement uncertainty"
            ),
            "measurement": (
                "UNKNOWN. This archive states no accuracy for any channel and "
                "none is invented. No acceptance threshold here is a "
                "source-reported spread"
            ),
            "model_form": (
                "PARTIALLY BOUNDED, and the bound is not a distribution. The "
                "disagreement between the admissible candidates M6, M8, M9, M10 "
                "and M11 on the validation split is reported as a spread across "
                "scientifically admissible model forms. It is not a claim that "
                "ensemble spread equals model-form uncertainty: every candidate "
                "in it shares one kernel, one heat term and one relaxation "
                "mode, so the spread cannot see an error common to all of them"
            ),
            "numerical": (
                "BOUNDED, not distributed. The refinement study measures how far "
                "the answer moves under subdivision and the bound is reported"
            ),
        },
        "gate_a_policy": frozen_gate_a(),
        "holdout": {
            "trajectories": selection["new_locked_holdout_trajectories"],
            "cells": sorted(
                {
                    row["cell"]
                    for row in selection["selected"]
                    if row["split"] == "locked_holdout"
                }
            ),
            "selection_rule": (
                "the cells this archive contains that appear in no Sprint 3 "
                "split. The rule has exactly one solution, B0041, so no outcome "
                "could have steered it"
            ),
            "why_independent": (
                "B0041 appears in no Sprint 3 calibration, validation or "
                "holdout split, in no guardrail list, and in no analysis in "
                "this recovery. Its measured channels are not vendored: the "
                "development corpus loader refuses a holdout trajectory and the "
                "candidate harness calls that refusal on the set it loads"
            ),
            "what_was_read_before_the_freeze": (
                "its identity, cycle indices, ambient, nominal load, sample "
                "counts, and the first sample's voltage and current -- the two "
                "channels the initial-state authority needs. No voltage after "
                "the first sample, and no residual"
            ),
            "dataset_digest_source": "SELECTION.json",
            "selection_sha256": sha256_file(os.path.join(EVIDENCE, "SELECTION.json")),
            "state_authority_sha256": sha256_file(
                os.path.join(EVIDENCE, "BATTERY_STATE_AUTHORITY.json")
            ),
            "candidates_sha256": sha256_file(
                os.path.join(EVIDENCE, "MODEL_CANDIDATES.json")
            ),
        },
        "what_this_round_does_not_produce": [
            "a coupled multiphysics run through the authorized composition "
            "path. The composition pack's blueprint pins the participant's "
            "model version, so a new model version needs a parallel blueprint, "
            "composition pack and execution pack, which is a larger structural "
            "change than this recovery is scoped for. The consequence is stated "
            "rather than worked around: there is no replay of an authorized "
            "plan and no certification record for the recovery model, and the "
            "Gate A below is scored on the frozen model's own declared kernel "
            "through the Sprint 2 holdout authority",
            "an independently validated state of charge. The archive's "
            "per-cycle capacity is measured on the very discharge being "
            "predicted, and comparing a coulomb counter with a coulomb counter "
            "tests nothing",
        ],
    }

    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    out = os.path.join(EVIDENCE, "NEW_GATE_A_PREREGISTRATION.json")
    with open(out, "wb") as handle:
        handle.write(payload)
    print(f"wrote {out}")
    print(f"sha256 {sha256_bytes(payload)}")
    print(f"  selected            : {SELECTED}")
    print(f"  model               : {model_v2.MODEL_ID}@{model_v2.MODEL_VERSION}")
    print(f"  parameter units     : {len(identifiability)}")
    print(f"  holdout             : {record['holdout']['cells']} "
          f"({len(record['holdout']['trajectories'])} trajectories)")
    gate = record["gate_a_policy"]["gate_a"]
    print(f"  gate A voltage      : MAE {gate['terminal_voltage']['mae_v']*1000:.0f} "
          f"RMSE {gate['terminal_voltage']['rmse_v']*1000:.0f} "
          f"P95 {gate['terminal_voltage']['p95_abs_v']*1000:.0f} mV")
    print(f"  gate A temperature  : MAE {gate['cell_temperature']['mae_k']:.1f} "
          f"RMSE {gate['cell_temperature']['rmse_k']:.1f} "
          f"P95 {gate['cell_temperature']['p95_abs_k']:.1f} K")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
