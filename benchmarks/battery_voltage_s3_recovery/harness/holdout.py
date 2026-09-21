"""R12, R13, R18: open the new locked holdout once, and score Gate A.

This script is the only thing in the recovery that reads B0041's measured
voltage. It refuses to run unless the freeze commit's artifacts are on disk and
their digests match the ones the preregistration recorded, so it cannot be run
against a model that moved after the freeze.

The flow is the Sprint 2 holdout authority's:

    frozen model -> frozen parameters -> frozen Gate A policy
      -> ReferenceDataset -> ValidationCampaign -> HoldoutOpening
        -> run_campaign -> comparisons -> Gate A

Exactly one opening. The ledger records it, and a second call against the same
evaluation id is the ledger's to refuse.

    python benchmarks/battery_voltage_s3_recovery/harness/holdout.py --open
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
REPO = os.path.dirname(os.path.dirname(BENCH))
sys.path.insert(0, HERE)
sys.path.insert(
    0, os.path.join(REPO, "benchmarks", "battery_thermal_flagship_s3", "harness")
)

import candidates as cd  # noqa: E402
import corpus as cp  # noqa: E402
import predict as pr  # noqa: E402
from engcore.domains.battery import flagship_ocv_v2 as ocv_v2  # noqa: E402
from engcore.domains.battery import flagship_v2 as model_v2  # noqa: E402
from engcore.domains.battery import measurement as ms  # noqa: E402
from engcore.scientific.corpus import (  # noqa: E402
    Applicability,
    CoverageDimension,
    DatasetSplit,
    HoldoutRelease,
    InMemoryHoldoutLedger,
    PredictedValue,
    PredictionRefusal,
    RefusalKind,
    ToleranceBasis,
    ToleranceSpec,
    ValidationCampaign,
    ValidationRegion,
    build_coverage,
    run_campaign,
)
from engcore.scientific.corpus.source import ReferenceSource, SourceSnapshot  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402

GATE_A_SCHEMA = "battery_voltage_s3_recovery_gate_a/1"

DATASET_ID = "battery.electrothermal.s3_recovery"
DATASET_VERSION = "1"
CAMPAIGN_ID = "battery.electrothermal.s3_recovery"
CAMPAIGN_VERSION = 1
EVALUATION_ID = "battery.electrothermal.s3_recovery.holdout.v1"

#: One case per this many measured instants. Sprint 3's stride, unchanged. The
#: first sample of a trajectory is the initial condition and is never scored.
SAMPLE_STRIDE = 4

SOURCE = ReferenceSource(
    source_id="nasa.pcoe.battery_aging",
    authority=(
        "NASA Ames Prognostics Center of Excellence, Li-ion Battery Aging Data "
        "Set (B. Saha and K. Goebel), NASA Prognostics Data Repository"
    ),
    domain="battery",
    source_version="2022-09-18",
    landing_url="https://www.nasa.gov/intelligent-systems-division/",
    allowed_hosts=("phm-datasets.s3.amazonaws.com", "www.nasa.gov"),
    license_note=(
        "US Government work, NASA Prognostics Data Repository; cite the "
        "repository and the data set authors"
    ),
    scale_note=(
        "commercial 18650 Li-ion cells, 2 Ah rated, cycled to end of life in a "
        "temperature-controlled chamber"
    ),
)

#: Coverage grids. Sprint 3's dimensions and edges, with the cell-temperature
#: axis extended downward because this round brought evidence below 288 K. The
#: edges are declared, not fitted to where the evidence fell.
VOLTAGE_REGION = ValidationRegion(
    "battery.terminal_voltage.recovery",
    (
        CoverageDimension(
            ms.DEPTH_OF_DISCHARGE, "dimensionless", (0.0, 0.2, 0.4, 0.6, 0.8)
        ),
        CoverageDimension(
            ms.MEASURED_CELL_TEMPERATURE,
            "kelvin",
            (273.15, 288.15, 303.15, 318.15, 333.15),
        ),
        CoverageDimension(ms.C_RATE, "1/hour", (0.0, 0.25, 1.25, 2.5)),
    ),
    minimum_supporting_cases=2,
)

TEMPERATURE_REGION = ValidationRegion(
    "battery.cell_temperature.recovery",
    (
        CoverageDimension(
            ms.AMBIENT_TEMPERATURE, "kelvin", (273.15, 288.15, 296.15, 300.15)
        ),
        CoverageDimension(ms.C_RATE, "1/hour", (0.0, 0.25, 1.25, 2.5)),
        CoverageDimension(ms.ELAPSED_TIME, "second", (0.0, 600.0, 1800.0, 3600.0)),
    ),
    minimum_supporting_cases=2,
)


def sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load(name: str):
    with open(os.path.join(EVIDENCE, name), encoding="utf-8") as handle:
        return json.load(handle)


def verify_freeze() -> dict[str, Any]:
    """Refuse to run against anything the preregistration did not freeze."""
    prereg = load("NEW_GATE_A_PREREGISTRATION.json")
    for name, key in (
        ("SELECTION.json", "selection_sha256"),
        ("BATTERY_STATE_AUTHORITY.json", "state_authority_sha256"),
        ("MODEL_CANDIDATES.json", "candidates_sha256"),
    ):
        actual = sha256_file(os.path.join(EVIDENCE, name))
        expected = prereg["holdout"][key]
        if actual != expected:
            raise SystemExit(
                f"{name} has changed since the freeze: {actual} against the "
                f"recorded {expected}. The holdout is scored against the frozen "
                "state or not at all"
            )
    if ocv_v2.OCV_V2_SOURCE_SHA256 != sha256_file(
        os.path.join(EVIDENCE, "OCV_AUTHORITY_V2.json")
    ):
        raise SystemExit(
            "the emitted open-circuit voltage module does not match its source "
            "record; regenerate it and re-freeze"
        )
    if prereg["model"]["version"] != model_v2.MODEL_VERSION:
        raise SystemExit(
            f"the preregistration froze model version "
            f"{prereg['model']['version']} and the tree carries "
            f"{model_v2.MODEL_VERSION}"
        )
    return prereg


def acceptance_policies(prereg) -> list[ms.MetricPolicy]:
    acceptance = prereg["gate_a_policy"]["acceptance"]
    return [
        ms.MetricPolicy(
            ms.TERMINAL_VOLTAGE_METRIC,
            ToleranceSpec(
                Quantity(
                    acceptance["terminal_voltage"]["per_sample_tolerance_v"], "volt"
                ),
                ToleranceBasis.REVIEWED_ACCEPTANCE,
                acceptance["terminal_voltage"]["rationale"],
            ),
        ),
        ms.MetricPolicy(
            ms.CELL_TEMPERATURE_METRIC,
            ToleranceSpec(
                Quantity(
                    acceptance["cell_temperature"]["per_sample_tolerance_k"], "kelvin"
                ),
                ToleranceBasis.REVIEWED_ACCEPTANCE,
                acceptance["cell_temperature"]["rationale"],
            ),
        ),
    ]


def vendor_holdout(selection) -> dict[str, Any]:
    """Write the holdout's measured channels to disk. This is the opening."""
    wanted = set(selection["new_locked_holdout_trajectories"])
    rows = [
        item
        for item in cp.normalized_trajectories()
        if item["trajectory_id"] in wanted
    ]
    missing = sorted(wanted - {item["trajectory_id"] for item in rows})
    if missing:
        raise SystemExit(f"holdout trajectories not in the corpus: {missing}")
    record = {
        "schema": "battery_voltage_s3_recovery_holdout_channels/1",
        "what_this_is": (
            "the measured channels of the locked holdout. This file does not "
            "exist until the holdout is opened, which is what stops a model "
            "being selected against it"
        ),
        "opened_at_freeze_commit": None,
        "trajectories": rows,
    }
    path = os.path.join(EVIDENCE, "selected_trajectories_holdout.json")
    text = json.dumps(record, indent=1, allow_nan=False)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")
    return record


def build_dataset(selection, state, channels, splits):
    """One immutable reference dataset over the requested splits."""
    states = {row["trajectory_id"]: row for row in state["trajectories"]}
    snapshot = SourceSnapshot(
        source_id=SOURCE.source_id,
        source_version=SOURCE.source_version,
        snapshot_sha256=state["archive_sha256"],
        snapshot_url=(
            "https://phm-datasets.s3.amazonaws.com/NASA/5.%2BBattery%2BData%2BSet.zip"
        ),
        byte_length=209708670,
        retrieved_at_utc="2026-09-21T00:00:00+00:00",
        content_type="application/zip",
    )

    trajectories: list[ms.MeasuredTrajectory] = []
    placements: dict[str, ms.TrajectoryPlacement] = {}
    bands: dict[str, str] = {}
    floors: dict[str, float] = {}
    for row in selection["selected"]:
        if row["split"] not in splits:
            continue
        if row.get("applicability") != "inside":
            continue
        record = states.get(row["trajectory_id"])
        raw = channels.get(row["trajectory_id"])
        if record is None or raw is None:
            continue
        if record["capacity"]["basis"] == "unknown":
            continue
        if record["initial_state"]["basis"] == "unknown":
            continue
        basis = float(record["capacity"]["initial_available_charge_ah"])
        z0 = float(record["initial_state"]["initial_state_of_charge"])
        band = ocv_v2.band_for(
            float(row["ambient_temperature_c"]), float(row["load_current_a"])
        )
        bands[row["trajectory_id"]] = band
        floors[row["trajectory_id"]] = ocv_v2.OCV_V2_CURVES[band].lower

        ch = raw["channels"]
        samples = tuple(
            ms.TrajectorySample(
                Quantity(float(t), "second"),
                Quantity(float(i), "ampere"),
                Quantity(float(v), "volt"),
                Quantity(float(c) + 273.15, "kelvin"),
            )
            for t, i, v, c in zip(
                ch["time_s"], ch["current_a"], ch["voltage_v"], ch["temperature_c"]
            )
        )
        trajectories.append(
            ms.MeasuredTrajectory(
                trajectory_id=row["trajectory_id"],
                cell_id=row["cell"],
                cycle_index=row["cycle_index"],
                ambient_temperature=Quantity(
                    row["ambient_temperature_c"] + 273.15, "kelvin"
                ),
                # The charge-state coordinate this corpus locates evidence on is
                # the MEASURED available charge, not the rating. That is the
                # whole point of the round and it has to be true of the corpus
                # as well as of the model, or the coordinates disagree.
                rated_capacity=Quantity(basis, "ampere_hour"),
                samples=samples,
                source_sign=ms.CurrentSign.NEGATIVE_DISCHARGE,
                initial_state_of_charge=Quantity(z0, "dimensionless"),
                provenance=ms.FileProvenance(
                    raw["member"], raw["member_sha256"], raw["member_bytes"]
                ),
                conditions_note=raw["profile"],
                tags=(
                    f"group:{row['group']}",
                    f"corner:{row['corner']}",
                    f"band:{band}",
                ),
            )
        )
        placements[row["trajectory_id"]] = ms.TrajectoryPlacement(
            trajectory_id=row["trajectory_id"],
            split=DatasetSplit(row["split"]),
            independence_group=f"cell:{row['cell']}",
            applicability=Applicability.INSIDE,
            note=f"{row['group']} {row['corner']} band {band}",
        )

    def applicability_of(trajectory, index, coordinates):
        """INSIDE only where the run's own band curve has evidence.

        The floor is the band's curve floor, which the authority derived from
        its own interquartile spread against the frozen acceptance tolerance.
        An instant below it is OUTSIDE, and the model refuses there rather than
        being scored on an extrapolation.
        """
        floor = floors[trajectory.trajectory_id]
        depth = coordinates[ms.DEPTH_OF_DISCHARGE].magnitude_in("dimensionless")
        return (
            Applicability.INSIDE if (1.0 - depth) >= floor else Applicability.OUTSIDE
        )

    prereg = load("NEW_GATE_A_PREREGISTRATION.json")
    dataset = ms.build_reference_dataset(
        dataset_id=DATASET_ID,
        version=DATASET_VERSION,
        source=SOURCE,
        snapshot=snapshot,
        trajectories=trajectories,
        placements=placements,
        metrics=acceptance_policies(prereg),
        stride=SAMPLE_STRIDE,
        skip_initial=True,
        per_sample_applicability=applicability_of,
        metadata={
            "campaign_id": CAMPAIGN_ID,
            "campaign_version": CAMPAIGN_VERSION,
            "charge_state_basis": (
                "measured available charge per trajectory, from "
                "engcore.domains.battery.capacity"
            ),
            "applicability": prereg["applicability"]["inside"],
            "measurement_uncertainty": (
                "UNKNOWN. This archive states no accuracy for any channel"
            ),
        },
    )
    return dataset, bands, floors


def predict(dataset, selection, prereg, bands, channels, state):
    """One march per trajectory; predictions read off its instants.

    Cases are addressed the way the corpus addresses them -- by
    ``ms.case_id_for(trajectory_id, sample_index)`` and a metric -- so a
    prediction offered for a case the campaign was not permitted to see is
    refused by Core rather than quietly matched.
    """
    states = {row["trajectory_id"]: row for row in state["trajectories"]}
    rows = {row["trajectory_id"]: row for row in selection["selected"]}
    parameters = prereg["frozen_parameters"]
    metrics = (ms.TERMINAL_VOLTAGE_METRIC, ms.CELL_TEMPERATURE_METRIC)
    case_ids = {case.case_id for case in dataset.cases}

    predictions: dict[tuple[str, str], Any] = {}
    runs: list[dict[str, Any]] = []

    scored_trajectories = sorted(
        {
            tid
            for tid in channels
            if any(
                ms.case_id_for(tid, index) in case_ids
                for index in range(1, len(channels[tid]["channels"]["time_s"]), SAMPLE_STRIDE)
            )
        }
    )

    for tid in scored_trajectories:
        row = rows[tid]
        record = states[tid]
        band = bands[tid]
        unit = (
            f"{row['group']}|{row['corner']}|"
            f"{round(abs(float(row['load_current_a'])) * 2.0) / 2.0:g}A"
        )
        fitted = parameters.get(unit, {}).get("fitted")
        ch = channels[tid]["channels"]
        times = ch["time_s"]
        currents = [-x for x in ch["current_a"]]
        voltages = ch["voltage_v"]
        temperatures = [x + 273.15 for x in ch["temperature_c"]]
        admissible = [
            cd.channel_consistent(currents, voltages, index)
            for index in range(len(voltages))
        ]
        indices = [index for index in range(1, len(times), SAMPLE_STRIDE)]

        def decline(kind, reason: str) -> None:
            for index in indices:
                case_id = ms.case_id_for(tid, index)
                if case_id not in case_ids:
                    continue
                for metric in metrics:
                    predictions.setdefault(
                        (case_id, metric), PredictionRefusal(kind, reason)
                    )

        if fitted is None:
            # No frozen parameter set for this operating block: the model has no
            # instance for it, which is a declared refusal and not a bad answer.
            decline(
                RefusalKind.APPLICABILITY,
                f"no frozen parameter set for operating block {unit}; the model "
                "has no instance for it",
            )
            runs.append(
                {"trajectory_id": tid, "unit": unit, "outcome": "no_parameters"}
            )
            continue

        instants, voltage, temperature, charge, refusal = pr.march(
            cell_id=row["cell"],
            band=band,
            times_s=times,
            currents_a=currents,
            ambient_k=float(row["ambient_temperature_c"]) + 273.15,
            initial_temperature_k=temperatures[0],
            parameters=fitted,
            available_charge_ah=float(
                record["capacity"]["initial_available_charge_ah"]
            ),
            initial_state_of_charge=float(
                record["initial_state"]["initial_state_of_charge"]
            ),
        )
        reached = {offset + 1: offset for offset in range(len(instants))}

        for index in indices:
            case_id = ms.case_id_for(tid, index)
            if case_id not in case_ids:
                continue
            offset = reached.get(index)
            if offset is None:
                for metric in metrics:
                    predictions[(case_id, metric)] = PredictionRefusal(
                        RefusalKind.APPLICABILITY
                        if refusal is not None
                        else RefusalKind.INSUFFICIENT_DATA,
                        (
                            refusal.reason[:400]
                            if refusal is not None
                            else "the march did not reach this instant"
                        ),
                    )
                continue
            if not admissible[index]:
                for metric in metrics:
                    predictions[(case_id, metric)] = PredictionRefusal(
                        RefusalKind.INSUFFICIENT_DATA,
                        "the measurement's current and voltage channels "
                        "contradict each other at this instant; it is not an "
                        "admissible observation",
                    )
                continue
            predictions[(case_id, ms.TERMINAL_VOLTAGE_METRIC)] = PredictedValue(
                value=Quantity(voltage[offset], "volt")
            )
            predictions[(case_id, ms.CELL_TEMPERATURE_METRIC)] = PredictedValue(
                value=Quantity(temperature[offset], "kelvin")
            )

        runs.append(
            {
                "trajectory_id": tid,
                "cell": row["cell"],
                "split": row["split"],
                "band": band,
                "unit": unit,
                "instants": len(instants),
                "available_charge_ah": record["capacity"][
                    "initial_available_charge_ah"
                ],
                "initial_state_basis": record["initial_state"]["basis"],
                "refused_at": None if refusal is None else refusal.index,
                "refusal_reason": None if refusal is None else refusal.reason[:400],
            }
        )
    return predictions, runs


def statistics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    count = len(ordered)
    index = min(count - 1, int(math.ceil(0.95 * count)) - 1)
    return {
        "n": count,
        "mae": sum(ordered) / count,
        "rmse": math.sqrt(sum(x * x for x in ordered) / count),
        "p95": ordered[max(index, 0)],
        "max": ordered[-1],
    }


def score(report, dataset, split: str, predictions=None) -> dict[str, Any]:
    """Residual statistics per metric, per cell and aggregated.

    ``ValidationComparison.residual`` is ``abs(observed - expected)`` by
    construction -- Core reports a magnitude, because a verdict is about
    whether agreement holds and not about which way it fails. So the SIGNED
    bias cannot be read off it, and averaging it would report the mean absolute
    error twice under two names. The bias below is computed from the prediction
    and the observation directly, as ``predicted - observed``, and it is
    reported and not gated.
    """
    cases = {case.case_id: case for case in dataset.cases}
    expected = {
        (item.case_id, item.metric): item.expected for item in dataset.observations
    }
    predictions = predictions or {}
    out: dict[str, Any] = {}
    for metric in (ms.TERMINAL_VOLTAGE_METRIC, ms.CELL_TEMPERATURE_METRIC):
        unit = "volt" if metric == ms.TERMINAL_VOLTAGE_METRIC else "kelvin"
        absolute: list[float] = []
        signed: list[float] = []
        by_cell: dict[str, list[float]] = collections.defaultdict(list)
        by_cell_signed: dict[str, list[float]] = collections.defaultdict(list)
        for item in report.comparisons:
            if item.split is not DatasetSplit(split) or item.metric != metric:
                continue
            if not item.verdict.is_scored or item.residual is None:
                continue
            case = cases[item.case_id]
            if case.applicability is not Applicability.INSIDE:
                continue
            residual = float(item.residual)
            absolute.append(abs(residual))
            offered = predictions.get((item.case_id, item.metric))
            observed = expected.get((item.case_id, item.metric))
            if (
                offered is not None
                and observed is not None
                and isinstance(offered, PredictedValue)
            ):
                signed.append(
                    offered.value.magnitude_in(unit) - observed.magnitude_in(unit)
                )
            cell = next(
                (t.split(":", 1)[1] for t in case.tags if t.startswith("cell:")),
                case.independence_group.split(":", 1)[-1],
            )
            by_cell[cell].append(abs(residual))
            if signed:
                by_cell_signed[cell].append(signed[-1])
        aggregate = statistics(absolute)
        aggregate["bias"] = (sum(signed) / len(signed)) if signed else None
        aggregate["bias_samples"] = len(signed)
        aggregate["bias_note"] = (
            "predicted minus observed, computed from the prediction and the "
            "observation. Core's residual is a magnitude, so the sign is not "
            "available from it"
        )
        per_cell = {}
        for cell, values in sorted(by_cell.items()):
            entry = statistics(values)
            entry["bias"] = (
                sum(by_cell_signed[cell]) / len(by_cell_signed[cell])
                if by_cell_signed[cell]
                else None
            )
            per_cell[cell] = entry
        out[metric] = {"aggregate": aggregate, "per_cell": per_cell}
    return out


def gate_a(prereg, scored) -> dict[str, Any]:
    """Compare the aggregate against the frozen limits. Nothing is adjusted."""
    gate = prereg["gate_a_policy"]["gate_a"]
    keys = {
        ms.TERMINAL_VOLTAGE_METRIC: (
            ("mae", "mae_v", "mV", 1000.0),
            ("rmse", "rmse_v", "mV", 1000.0),
            ("p95", "p95_abs_v", "mV", 1000.0),
        ),
        ms.CELL_TEMPERATURE_METRIC: (
            ("mae", "mae_k", "K", 1.0),
            ("rmse", "rmse_k", "K", 1.0),
            ("p95", "p95_abs_k", "K", 1.0),
        ),
    }
    results: dict[str, Any] = {}
    verdicts: list[str] = []
    for metric, checks in keys.items():
        measured = scored[metric]["aggregate"]
        rows = []
        for statistic, key, unit, scale in checks:
            limit = gate[metric][key]
            value = measured.get(statistic)
            passed = value is not None and value <= limit
            verdicts.append(f"{metric}.{statistic}:{'PASS' if passed else 'FAIL'}")
            rows.append(
                {
                    "statistic": statistic,
                    "value": value,
                    "value_display": (
                        "no scored case" if value is None
                        else f"{value * scale:.2f} {unit}"
                    ),
                    "limit": limit,
                    "limit_display": f"{limit * scale:.2f} {unit}",
                    "passed": passed,
                }
            )
        results[metric] = {
            "n": measured.get("n", 0),
            "checks": rows,
            "max_abs": measured.get("max"),
            "bias": measured.get("bias"),
            "max_policy": gate["max_error_policy"],
            "per_cell": scored[metric]["per_cell"],
            "passed": all(row["passed"] for row in rows),
        }
    return {
        "metrics": results,
        "verdicts": verdicts,
        "gate_a_passed": all(item["passed"] for item in results.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the locked holdout. Without it nothing is scored.",
    )
    parser.add_argument("--out", default="NEW_GATE_A_RESULT.json")
    parser.add_argument("--splits", nargs="*", default=None)
    parser.add_argument("--evaluation-id", default=EVALUATION_ID)
    parser.add_argument("--label", default="new_locked_holdout")
    args = parser.parse_args()

    prereg = verify_freeze()
    selection = load("SELECTION.json")
    state = load("BATTERY_STATE_AUTHORITY.json")

    splits = set(args.splits) if args.splits else {
        "calibration",
        "validation",
        "locked_holdout",
    }
    opening_split = "locked_holdout" in splits
    if opening_split and not args.open:
        raise SystemExit(
            "this run would score the locked holdout. Pass --open, which is the "
            "point at which the ledger records an opening"
        )

    channels = dict(cp.load_development_corpus(selection))
    if opening_split:
        vendored = vendor_holdout(selection)
        for item in vendored["trajectories"]:
            channels[item["trajectory_id"]] = item

    dataset, bands, floors = build_dataset(selection, state, channels, splits)
    predictions, runs = predict(dataset, selection, prereg, bands, channels, state)

    release = None
    if opening_split:
        release = HoldoutRelease(
            # The evaluation identity carries the campaign version, so a
            # corrected model is a new evaluation and not a second opening of
            # this one.
            evaluation_id=args.evaluation_id,
            campaign_id=CAMPAIGN_ID,
            campaign_version=CAMPAIGN_VERSION,
            dataset_digest=dataset.normalized_digest,
            registered_at_utc="2026-09-21T00:00:00+00:00",
            reason=(
                "one scientific evaluation of the frozen recovery model "
                f"{model_v2.MODEL_ID}@{model_v2.MODEL_VERSION} against B0041, "
                "the only cell in this archive that appears in no Sprint 3 "
                "split. Registered after the model, its parameters, the "
                "applicability contract and the Gate A policy were frozen and "
                "committed, and bound to this dataset's normalized digest so it "
                "cannot carry over to a corpus that changed"
            ),
        )
    campaign = ValidationCampaign(
        campaign_id=CAMPAIGN_ID,
        version=CAMPAIGN_VERSION,
        dataset=dataset,
        splits=tuple(
            sorted((DatasetSplit(s) for s in splits), key=lambda x: x.value)
        ),
        holdout_release=release,
        description=(
            "Sprint 3 battery voltage recovery: the frozen "
            f"{model_v2.MODEL_ID}@{model_v2.MODEL_VERSION} against the new "
            "locked holdout"
        ),
    )
    ledger = InMemoryHoldoutLedger(clock=lambda: "2026-09-21T00:00:00+00:00")
    opened = campaign.open_holdout(ledger) if opening_split else campaign
    report = run_campaign(opened, predictions)

    scored = {
        split: score(report, dataset, split, predictions)
        for split in sorted(splits)
    }
    verdict = gate_a(prereg, scored["locked_holdout"]) if opening_split else None

    # One grid per metric: `build_coverage` takes a single region, and a shared
    # grid across two metrics would report a cell as covered because the other
    # metric reached it.
    coverage = {
        ms.TERMINAL_VOLTAGE_METRIC: build_coverage(
            report, dataset, VOLTAGE_REGION, metric=ms.TERMINAL_VOLTAGE_METRIC
        ),
        ms.CELL_TEMPERATURE_METRIC: build_coverage(
            report, dataset, TEMPERATURE_REGION, metric=ms.CELL_TEMPERATURE_METRIC
        ),
    }

    record = {
        "schema": GATE_A_SCHEMA,
        "what_this_is": (
            "one scientific evaluation of the frozen recovery model against the "
            "new locked holdout, scored against thresholds this recovery cannot "
            "edit"
        ),
        "label": args.label,
        "frozen_at": prereg["holdout"],
        "model": prereg["model"],
        "selected_candidate": prereg["selected_candidate"],
        "evaluation_id": args.evaluation_id,
        "holdout_opened": opening_split,
        "holdout_opening_digest": (
            opened.opening.digest if opening_split else None
        ),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "version": dataset.version,
            "normalized_digest": dataset.normalized_digest,
            "cases": len(dataset.cases),
            "observations": len(dataset.observations),
            "trajectories": len({c.case_id.rsplit("@", 1)[0] for c in dataset.cases}),
        },
        "report_digest": report.digest,
        "counts": {name: int(value) for name, value in report.counts.items()},
        "pass_fraction": report.pass_fraction,
        "refusal_accuracy": report.refusal_accuracy,
        "gate_a_policy": prereg["gate_a_policy"],
        "gate_a": verdict,
        "scored": scored,
        "coverage": {
            metric: value.to_dict() for metric, value in sorted(coverage.items())
        },
        "runs": runs,
        "what_was_not_produced": prereg["what_this_round_does_not_produce"],
    }

    text = json.dumps(record, indent=1, allow_nan=False)
    payload = text.encode("utf-8") + b"\n"
    path = os.path.join(EVIDENCE, args.out)
    with open(path, "wb") as handle:
        handle.write(payload)

    print(f"wrote {path}")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    print(f"dataset digest {dataset.normalized_digest}")
    print(f"counts {record['counts']}")
    print(f"refusal accuracy {report.refusal_accuracy}")
    if verdict is None:
        for split in sorted(splits):
            v = scored[split][ms.TERMINAL_VOLTAGE_METRIC]["aggregate"]
            if v.get("n"):
                print(
                    f"  {split:16} voltage n={v['n']:5d} MAE {v['mae']*1000:7.2f} "
                    f"RMSE {v['rmse']*1000:7.2f} P95 {v['p95']*1000:7.2f} mV"
                )
        return 0

    print()
    print(f"GATE A -- {args.label}, cases inside declared applicability")
    for metric, result in verdict["metrics"].items():
        print(f"\n{metric}  n={result['n']}")
        for row in result["checks"]:
            print(
                f"  {row['statistic'].upper():5} {row['value_display']:>14} "
                f"limit {row['limit_display']:>14}   "
                f"{'PASS' if row['passed'] else 'FAIL'}"
            )
        scale = 1000.0 if metric == ms.TERMINAL_VOLTAGE_METRIC else 1.0
        unit = "mV" if scale > 1 else "K"
        if result["max_abs"] is not None:
            print(f"  MAX   {result['max_abs']*scale:>10.2f} {unit}   reported, not gated")
        if result["bias"] is not None:
            print(f"  BIAS  {result['bias']*scale:>10.2f} {unit}   reported, not gated")
        for cell, values in result["per_cell"].items():
            print(
                f"    {cell:7} n={values['n']:5d} MAE {values['mae']*scale:8.2f} "
                f"RMSE {values['rmse']*scale:8.2f} P95 {values['p95']*scale:8.2f} "
                f"max {values['max']*scale:8.2f} bias {values['bias']*scale:8.2f} {unit}"
            )
    print(f"\nGATE A PASSED: {verdict['gate_a_passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
