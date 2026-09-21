"""The validation campaign: predictions from Forge, verdicts from Core.

Every prediction below comes from an authorized multiphysics run. Nothing is
recomputed here and nothing is compared here -- the comparison is
``run_campaign``'s, the coverage is ``build_coverage_by_metric``'s, the
clustering is ``cluster_failures``'s and the diagnosis is
``diagnose_campaign``'s. This module builds the corpus, drives the runs and
writes the record.

    python .../campaign.py --splits calibration validation
    python .../campaign.py --splits calibration validation locked_holdout --open-holdout

The locked holdout is unreachable without ``--open-holdout``, and opening it
goes through the Sprint 2 ledger, which records the opening and refuses a
second one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import prereg  # noqa: E402
import simulate as sim  # noqa: E402
from engcore.domains.battery import measurement as ms  # noqa: E402
from engcore.domains.battery.flagship_ocv import (  # noqa: E402
    CHARGE_STATE_BASIS_AH,
)
from engcore.scientific.corpus import (  # noqa: E402
    Applicability,
    CoverageDimension,
    DatasetSplit,
    HoldoutRelease,
    InMemoryHoldoutLedger,
    PredictedValue,
    PredictionRefusal,
    RefusalKind,
    ReferenceSource,
    SourceSnapshot,
    ToleranceBasis,
    ToleranceSpec,
    ValidationCampaign,
    ValidationEnvelope,
    ValidationRegion,
    build_coverage_by_metric,
    cluster_failures,
    diagnose_campaign,
    run_campaign,
)
from engcore.scientific.errors import InvalidScientificProblem  # noqa: E402
from engcore.scientific.units.quantity import Quantity  # noqa: E402

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

#: One coverage grid per metric. The edges are declared, not derived from where
#: the evidence happens to fall: a grid fitted to the data would have no cell
#: the model was never tested in, which is the thing coverage exists to report.
VOLTAGE_REGION = ValidationRegion(
    "battery.terminal_voltage",
    (
        CoverageDimension(
            ms.DEPTH_OF_DISCHARGE, "dimensionless", (0.0, 0.2, 0.4, 0.6, 0.8)
        ),
        CoverageDimension(
            ms.MEASURED_CELL_TEMPERATURE, "kelvin", (288.15, 303.15, 318.15, 333.15)
        ),
        CoverageDimension(ms.C_RATE, "1/hour", (0.0, 0.25, 1.25, 2.5)),
    ),
    minimum_supporting_cases=2,
)

TEMPERATURE_REGION = ValidationRegion(
    "battery.cell_temperature",
    (
        CoverageDimension(
            ms.AMBIENT_TEMPERATURE, "kelvin", (288.15, 296.15, 300.15)
        ),
        CoverageDimension(ms.C_RATE, "1/hour", (0.0, 0.25, 1.25, 2.5)),
        CoverageDimension(ms.ELAPSED_TIME, "second", (0.0, 600.0, 1800.0, 3600.0)),
    ),
    minimum_supporting_cases=2,
)


def acceptance_policies() -> list[ms.MetricPolicy]:
    return [
        ms.MetricPolicy(
            ms.TERMINAL_VOLTAGE_METRIC,
            ToleranceSpec(
                Quantity(
                    prereg.ACCEPTANCE["terminal_voltage"]["per_sample_tolerance_v"],
                    "volt",
                ),
                ToleranceBasis.REVIEWED_ACCEPTANCE,
                prereg.ACCEPTANCE["terminal_voltage"]["rationale"],
            ),
        ),
        ms.MetricPolicy(
            ms.CELL_TEMPERATURE_METRIC,
            ToleranceSpec(
                Quantity(
                    prereg.ACCEPTANCE["cell_temperature"]["per_sample_tolerance_k"],
                    "kelvin",
                ),
                ToleranceBasis.REVIEWED_ACCEPTANCE,
                prereg.ACCEPTANCE["cell_temperature"]["rationale"],
            ),
        ),
    ]


def load_inputs():
    def read(name):
        with open(os.path.join(EVIDENCE, name), encoding="utf-8") as fh:
            return json.load(fh)

    selection = read("DATA_SELECTION.json")
    vendored = read("selected_trajectories.json")
    calibration = read("CALIBRATION.json")
    inventory = read("INVENTORY.json")
    return selection, vendored, calibration, inventory


def build_dataset(selection, vendored, inventory):
    """Normalize every selected trajectory into one immutable reference dataset."""
    by_id = {item["trajectory_id"]: item for item in vendored["trajectories"]}
    snapshot = SourceSnapshot(
        source_id=SOURCE.source_id,
        source_version=SOURCE.source_version,
        snapshot_sha256=inventory["archive_sha256"],
        snapshot_url=inventory["archive_url"].replace("+", "%2B"),
        byte_length=inventory["archive_bytes"],
        retrieved_at_utc="2026-09-21T00:00:00+00:00",
        content_type="application/zip",
    )

    trajectories: list[ms.MeasuredTrajectory] = []
    placements: dict[str, ms.TrajectoryPlacement] = {}
    for item in selection["selected"]:
        if not item.get("in_campaign", True):
            continue
        raw = by_id[item["trajectory_id"]]
        channels = raw["channels"]
        admits = bool(item["admit_cell_temperature"])
        samples = tuple(
            ms.TrajectorySample(
                Quantity(float(t), "second"),
                Quantity(float(i), "ampere"),
                Quantity(float(v), "volt"),
                Quantity(float(c) + 273.15, "kelvin") if admits else None,
            )
            for t, i, v, c in zip(
                channels["time_s"],
                channels["current_a"],
                channels["voltage_v"],
                channels["temperature_c"],
            )
        )
        trajectories.append(
            ms.MeasuredTrajectory(
                trajectory_id=item["trajectory_id"],
                cell_id=item["cell"],
                cycle_index=item["cycle_index"],
                ambient_temperature=Quantity(
                    item["ambient_temperature_c"] + 273.15, "kelvin"
                ),
                rated_capacity=Quantity(CHARGE_STATE_BASIS_AH, "ampere_hour"),
                samples=samples,
                provenance=ms.FileProvenance(
                    raw["member"], raw["member_sha256"], raw["member_bytes"]
                ),
                source_sign=ms.CurrentSign.NEGATIVE_DISCHARGE,
                initial_state_of_charge=Quantity(1.0, "dimensionless"),
                conditions_note=raw["profile"],
                tags=(f"group:{item['group']}", f"ambient:{item['group']}"),
            )
        )
        placements[item["trajectory_id"]] = ms.TrajectoryPlacement(
            trajectory_id=item["trajectory_id"],
            split=DatasetSplit(item["split"]),
            independence_group=f"cell:{item['cell']}",
            applicability=Applicability(item["applicability"]),
            note=(
                item["thermal_exclusion"]
                or f"{item['group']} at {item['ambient_temperature_c']:.0f} degC"
            ),
        )

    floor = prereg.APPLICABILITY_CHARGE_STATE_FLOOR

    def applicability_of(trajectory, index, coordinates):
        """INSIDE only where the flagship says it goes.

        The trajectory-level declaration decides first: a run outside the
        declared ambient band is outside everywhere along it. Inside that band,
        an instant below the declared charge-state floor is still outside,
        because the floor is a bound on a coordinate that moves as the cell
        discharges.
        """
        declared = placements[trajectory.trajectory_id].applicability
        if declared is not Applicability.INSIDE:
            return declared
        depth = coordinates[ms.DEPTH_OF_DISCHARGE].magnitude_in("dimensionless")
        return (
            Applicability.INSIDE
            if (1.0 - depth) >= floor
            else Applicability.OUTSIDE
        )

    return ms.build_reference_dataset(
        dataset_id=prereg.DATASET_ID,
        version=prereg.DATASET_VERSION,
        source=SOURCE,
        snapshot=snapshot,
        trajectories=trajectories,
        placements=placements,
        metrics=acceptance_policies(),
        stride=prereg.SAMPLE_STRIDE,
        skip_initial=True,
        per_sample_applicability=applicability_of,
        metadata={
            "campaign_id": prereg.CAMPAIGN_ID,
            "campaign_version": prereg.CAMPAIGN_VERSION,
            "applicability": {
                "ambient_band_k": [
                    prereg.INSIDE_AMBIENT_C[0] + 273.15,
                    prereg.INSIDE_AMBIENT_C[1] + 273.15,
                ],
                "charge_state_floor": floor,
                "direction": "discharge and rest only",
                "max_cycle_index": prereg.INSIDE_MAX_CYCLE_INDEX,
            },
            "measurement_uncertainty": prereg.SOURCE_MEASUREMENT_UNCERTAINTY,
        },
    )


def parameters_for(calibration, group: str):
    for item in calibration["groups"]:
        if item["group"] == group:
            if not item["produces_a_claim"]:
                return None
            return item["fitted"]
    return None


def guardrail_parameters(calibration):
    """A parameter set for a trajectory the model is declared not to cover.

    The guardrail cases are cells in experiment groups with no calibration cell
    of their own, at ambients outside the pack's declared band. What is under
    test there is the composition's declared envelope, and that predicate reads
    the ambient temperature and the load current -- never a fitted value -- so
    any admissible parameter set exercises it identically. Handing the run one
    makes the refusal the **pack's**, for the reason the pack states, instead of
    a harness declining because it had no numbers.
    """
    for item in sorted(calibration["groups"], key=lambda x: x["group"]):
        if item["produces_a_claim"]:
            return item["group"], item["fitted"]
    raise SystemExit("no group produces a claim, so no guardrail run can be made")


def predict(dataset, selection, calibration, *, splits, refinement=1):
    """One authorized run per trajectory; predictions read off its windows.

    A trajectory whose composition refuses it at preflight produces a refusal
    for every one of its cases, and the refusal is the pack's: nothing here
    decides where the model may answer.
    """
    wanted = {DatasetSplit(item) for item in splits}
    rows = [
        item
        for item in selection["selected"]
        if DatasetSplit(item["split"]) in wanted and item.get("in_campaign", True)
    ]
    by_id = {}
    with open(
        os.path.join(EVIDENCE, "selected_trajectories.json"), encoding="utf-8"
    ) as fh:
        for item in json.load(fh)["trajectories"]:
            by_id[item["trajectory_id"]] = item

    case_ids = {case.case_id for case in dataset.cases}
    predictions: dict[tuple[str, str], Any] = {}
    runs: list[dict[str, Any]] = []
    keep_runs: dict[str, Any] = {}

    for item in sorted(rows, key=lambda x: x["trajectory_id"]):
        trajectory_id = item["trajectory_id"]
        channels = by_id[trajectory_id]["channels"]
        currents = [-x for x in channels["current_a"]]
        group_parameters = parameters_for(calibration, item["group"])
        borrowed_from = ""
        if group_parameters is None and item["applicability"] == "outside":
            borrowed_from, group_parameters = guardrail_parameters(calibration)
        indices = [
            index
            for index in range(1, len(channels["time_s"]), prereg.SAMPLE_STRIDE)
        ]
        metrics = (ms.TERMINAL_VOLTAGE_METRIC, ms.CELL_TEMPERATURE_METRIC)

        def decline(kind: RefusalKind, reason: str) -> None:
            for index in indices:
                case_id = ms.case_id_for(trajectory_id, index)
                for metric in metrics:
                    if (case_id, metric) in predictions:
                        continue
                    if case_id in case_ids:
                        predictions[(case_id, metric)] = PredictionRefusal(
                            kind, reason
                        )

        if group_parameters is None:
            decline(
                RefusalKind.INSUFFICIENT_DATA,
                (
                    f"experiment group {item['group']!r} has no independent cell, "
                    f"so no parameter set of its own is applied to it"
                ),
            )
            runs.append(
                {
                    "trajectory_id": trajectory_id,
                    "outcome": "no_parameter_authority",
                    "group": item["group"],
                }
            )
            continue

        vector = [group_parameters[name] for name in sim.PARAMETER_ORDER]
        started = time.perf_counter()
        try:
            authorized = sim.run_trajectory(
                parameters=sim.parameter_quantities(vector),
                times_s=channels["time_s"],
                currents_a=currents,
                ambient_k=item["ambient_temperature_c"] + 273.15,
                initial_temperature_k=channels["temperature_c"][0] + 273.15,
                run_id=f"{prereg.CAMPAIGN_ID}.{trajectory_id}",
                scenario_id=f"{prereg.CAMPAIGN_ID}.{trajectory_id}".replace(
                    "_", "-"
                ),
                refinement=refinement,
                charge_state_floor=prereg.APPLICABILITY_CHARGE_STATE_FLOOR,
            )
        except InvalidScientificProblem as exc:
            kind = (
                RefusalKind.APPLICABILITY
                if "applicability" in str(exc).lower()
                else RefusalKind.UNSUPPORTED_REGIME
            )
            decline(kind, str(exc)[:400])
            runs.append(
                {
                    "trajectory_id": trajectory_id,
                    "outcome": "refused",
                    "kind": kind.value,
                    "reason": str(exc)[:400],
                    "parameters_borrowed_from": borrowed_from,
                    "applicability": item["applicability"],
                    "seconds": time.perf_counter() - started,
                }
            )
            continue

        trajectory_rows = sim.trajectory_from_run(authorized)
        # A window ends at a measured instant, so the prediction for sample k is
        # the window whose end is that sample's time. Matched by index, because
        # the events were built from the same list.
        offset = float(channels["time_s"][0])
        by_time = {round(row["t"] + offset, 6): row for row in trajectory_rows}
        answered = 0
        for index in indices:
            case_id = ms.case_id_for(trajectory_id, index)
            if case_id not in case_ids:
                continue
            key = round(float(channels["time_s"][index]), 6)
            row = by_time.get(key)
            if row is None:
                for metric in metrics:
                    predictions[(case_id, metric)] = PredictionRefusal(
                        RefusalKind.UNSUPPORTED_REGIME,
                        (
                            "the run stopped before this instant: "
                            + (
                                authorized.run.termination.reason
                                if authorized.run.termination is not None
                                else "no window reached it"
                            )
                        )[:400],
                    )
                continue
            answered += 1
            predictions[(case_id, ms.TERMINAL_VOLTAGE_METRIC)] = PredictedValue(
                Quantity(row["terminal_voltage"], "volt")
            )
            predictions[(case_id, ms.CELL_TEMPERATURE_METRIC)] = PredictedValue(
                Quantity(row["cell_temperature"], "kelvin")
            )
        keep_runs[trajectory_id] = authorized
        runs.append(
            {
                "trajectory_id": trajectory_id,
                "outcome": "executed",
                "group": item["group"],
                "split": item["split"],
                "parameters_borrowed_from": borrowed_from,
                "windows": len(trajectory_rows),
                "answered_cases": answered,
                "terminated": (
                    None
                    if authorized.run.termination is None
                    else {
                        "condition_id": authorized.run.termination.condition_id,
                        "instant_s": authorized.run.termination.instant.magnitude_in(
                            "second"
                        ),
                        "reason": authorized.run.termination.reason,
                    }
                ),
                "system_validation": [
                    {"protocol": v.protocol_id, "valid": v.result.valid}
                    for v in authorized.system_validation
                ],
                "seconds": time.perf_counter() - started,
            }
        )
        print(
            f"  {trajectory_id:16} {item['split']:14} windows={len(trajectory_rows):4d} "
            f"cases={answered:4d} {time.perf_counter() - started:5.1f}s",
            file=sys.stderr,
        )
    return predictions, runs, keep_runs


def metrics_from(report, dataset, *, split, metric, applicability=Applicability.INSIDE):
    """MAE, RMSE, P95 and max over the scored comparisons of one metric.

    Scored means PASS or FAIL. A case recorded as outside applicability, or
    correctly refused, contributes nothing: those are statements about the
    guardrail, and summing them into an error metric would let a model improve
    its numbers by declining.
    """
    import math

    by_case = {case.case_id: case for case in dataset.cases}
    residuals = []
    for item in report.comparisons:
        if item.split is not DatasetSplit(split) or item.metric != metric:
            continue
        if not item.verdict.is_scored or item.residual is None:
            continue
        if by_case[item.case_id].applicability is not applicability:
            continue
        residuals.append(abs(float(item.residual)))
    if not residuals:
        return None
    residuals.sort()
    count = len(residuals)
    index = min(count - 1, int(math.ceil(0.95 * count)) - 1)
    return {
        "n": count,
        "mae": sum(residuals) / count,
        "rmse": math.sqrt(sum(x * x for x in residuals) / count),
        "p95": residuals[max(index, 0)],
        "max": residuals[-1],
    }


def holdout_release(dataset) -> HoldoutRelease:
    """Registered permission to open this dataset's locked holdout, once.

    Bound to the normalized dataset digest, so a release does not carry over to
    a corpus that changed, and to one evaluation id, so it cannot open another.
    """
    return HoldoutRelease(
        # The campaign version is part of the evaluation identity. A corrected
        # model is a new evaluation, not a second opening of the old one, and
        # the id says so without anybody having to remember.
        evaluation_id=f"{prereg.CAMPAIGN_ID}.holdout.v{prereg.CAMPAIGN_VERSION}",
        campaign_id=prereg.CAMPAIGN_ID,
        campaign_version=prereg.CAMPAIGN_VERSION,
        dataset_digest=dataset.normalized_digest,
        registered_at_utc="2026-09-21T00:00:00+00:00",
        reason=(
            f"registered locked-holdout evaluation v{prereg.CAMPAIGN_VERSION} of "
            "the Sprint 3 battery electrothermal flagship, opened after the "
            "parameter sets, the applicability declaration and the acceptance "
            "policy were frozen. Earlier evaluations, if any, are recorded in "
            "the preregistration's amendments with the reason a new one was "
            "governed rather than the old one reopened"
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--splits", nargs="+", default=["calibration", "validation"]
    )
    parser.add_argument("--open-holdout", action="store_true")
    parser.add_argument("--refinement", type=int, default=1)
    parser.add_argument("--out", default="CAMPAIGN.json")
    args = parser.parse_args()

    splits = [DatasetSplit(item) for item in args.splits]
    if DatasetSplit.LOCKED_HOLDOUT in splits and not args.open_holdout:
        raise SystemExit(
            "the locked holdout is not reachable without --open-holdout; a "
            "campaign that could read it by naming it would not be locked"
        )

    selection, vendored, calibration, inventory = load_inputs()
    dataset = build_dataset(selection, vendored, inventory)
    print(
        f"dataset {dataset.dataset_id}@{dataset.version} "
        f"digest {dataset.normalized_digest[:16]} "
        f"counts {dataset.split_counts}",
        file=sys.stderr,
    )

    release = holdout_release(dataset) if args.open_holdout else None
    campaign = ValidationCampaign(
        campaign_id=prereg.CAMPAIGN_ID,
        version=prereg.CAMPAIGN_VERSION,
        dataset=dataset,
        splits=tuple(splits),
        holdout_release=release,
        description=(
            "Sprint 3 battery electrothermal flagship: measured NASA PCoE "
            "discharge trajectories against authorized Forge multiphysics runs"
        ),
    )
    ledger = InMemoryHoldoutLedger(
        clock=lambda: datetime.now(timezone.utc).isoformat()
    )
    opened = campaign
    opening = None
    if args.open_holdout:
        opened = campaign.open_holdout(ledger)
        opening = ledger.openings[0]
        print(f"holdout opened: {opening.digest[:16]}", file=sys.stderr)

    print("running authorized trajectories:", file=sys.stderr)
    predictions, runs, keep = predict(
        dataset,
        selection,
        calibration,
        splits=args.splits,
        refinement=args.refinement,
    )
    report = run_campaign(opened, predictions)

    per_metric: dict[str, Any] = {}
    for metric in (ms.TERMINAL_VOLTAGE_METRIC, ms.CELL_TEMPERATURE_METRIC):
        per_metric[metric] = {
            split.value: metrics_from(
                report, dataset, split=split.value, metric=metric
            )
            for split in splits
        }

    regions = {
        ms.TERMINAL_VOLTAGE_METRIC: VOLTAGE_REGION,
        ms.CELL_TEMPERATURE_METRIC: TEMPERATURE_REGION,
    }
    coverages = build_coverage_by_metric(
        report, dataset, regions[ms.TERMINAL_VOLTAGE_METRIC]
    )
    voltage_coverage = coverages.get(ms.TERMINAL_VOLTAGE_METRIC)
    temperature_coverage = build_coverage_by_metric(
        report, dataset, regions[ms.CELL_TEMPERATURE_METRIC]
    ).get(ms.CELL_TEMPERATURE_METRIC)

    clusters = cluster_failures(
        report, dataset, regions[ms.TERMINAL_VOLTAGE_METRIC]
    )
    diagnosis = diagnose_campaign(report, clusters)

    envelopes = {}
    for metric, coverage in (
        (ms.TERMINAL_VOLTAGE_METRIC, voltage_coverage),
        (ms.CELL_TEMPERATURE_METRIC, temperature_coverage),
    ):
        if coverage is None:
            continue
        envelopes[metric] = ValidationEnvelope(
            f"{prereg.CAMPAIGN_ID}.{metric}", coverage, report.digest
        )

    record = {
        "schema": "battery_thermal_flagship_s3_campaign/1",
        "campaign_id": report.campaign_id,
        "campaign_version": report.campaign_version,
        "splits": [item.value for item in splits],
        "holdout_opened": bool(args.open_holdout),
        "holdout_opening_digest": report.holdout_opening_digest,
        "refinement": args.refinement,
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "version": dataset.version,
            "normalized_digest": dataset.normalized_digest,
            "snapshot_sha256": dataset.snapshot.snapshot_sha256,
            "counts": dataset.split_counts,
            "cases": len(dataset.cases),
            "observations": len(dataset.observations),
        },
        "report_digest": report.digest,
        "counts": report.counts,
        "pass_fraction": report.pass_fraction,
        "refusal_accuracy": report.refusal_accuracy,
        "guardrail_counts": report.guardrail_counts,
        "metrics": per_metric,
        "coverage": {
            metric: coverage.to_dict()
            for metric, coverage in (
                (ms.TERMINAL_VOLTAGE_METRIC, voltage_coverage),
                (ms.CELL_TEMPERATURE_METRIC, temperature_coverage),
            )
            if coverage is not None
        },
        "failure_clusters": [item.to_dict() for item in clusters],
        "model_form_diagnosis": diagnosis.to_dict(),
        "envelopes": {
            metric: envelope.to_dict() for metric, envelope in envelopes.items()
        },
        "runs": runs,
        "state_of_charge": prereg.GATE_A["state_of_charge"],
    }
    text = json.dumps(record, indent=1, allow_nan=False)
    out = os.path.join(EVIDENCE, args.out)
    with open(out, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")

    print()
    print(f"counts {report.counts}")
    for metric, splits_metrics in per_metric.items():
        for split, values in splits_metrics.items():
            if values is None:
                print(f"  {metric:18} {split:14} no scored case")
                continue
            unit = "mV" if metric == ms.TERMINAL_VOLTAGE_METRIC else "K"
            scale = 1000.0 if unit == "mV" else 1.0
            print(
                f"  {metric:18} {split:14} n={values['n']:5d} "
                f"MAE {values['mae'] * scale:8.2f} RMSE {values['rmse'] * scale:8.2f} "
                f"P95 {values['p95'] * scale:8.2f} max {values['max'] * scale:8.2f} {unit}"
            )
    print(f"diagnosis: {diagnosis.kind.value}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
