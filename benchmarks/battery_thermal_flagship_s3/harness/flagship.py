"""The flagship run and everything Core needs to decide about it.

One authorized run, and around it: numerical evidence the Sprint 2 policy
requires, the uncertainty channels the campaign can and cannot quantify, an
actual computational replay, the validated envelope the validation campaign
produced, and the certification decision Core derives from all of it.

    python .../flagship.py

The trajectory is a VALIDATION cell. Nothing here touches the locked holdout,
which is opened once, separately, after this evidence is frozen.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
EVIDENCE = os.path.join(BENCH, "evidence")
sys.path.insert(0, HERE)

import campaign as cmp  # noqa: E402
import prereg  # noqa: E402
import simulate as sim  # noqa: E402
from engcore.assembly.certification import (  # noqa: E402
    COMPUTATIONAL_REPLAY_VERIFIED,
    MULTIPHYSICS_FULL_TRUST_POLICY,
    MULTIPHYSICS_PRODUCTION_POLICY,
    NUMERICAL_EVIDENCE_PRESENT,
    SERIALIZATION_ROUNDTRIP_VERIFIED,
    UQ_CHANNEL_COMPLETENESS,
    VALIDATION_ENVELOPE_SUPPORTED,
    VALIDATION_PROTOCOL_COMPLETENESS,
    assess_authorized_multiphysics_run,
    certify_authorized_multiphysics_run,
)
from engcore.assembly.domainpacks import (  # noqa: E402
    production_composition_packs,
    production_execution_packs,
)
from engcore.assembly.replay import (  # noqa: E402
    DEFAULT_REPLAY_POLICY,
    ReplayStatus,
    replay_authorized_graph_plan,
)
from engcore.assembly.trust import (  # noqa: E402
    UQCellState,
    assess_protocol_completeness,
    assess_uq_coverage,
    authorized_run_binding,
)
from engcore.compositionpacks.builtin_battery_electrothermal import (  # noqa: E402
    F_C1,
    F_CTH,
    F_EA0,
    F_EA1,
    F_HA,
    F_R0,
    F_R1,
)
from engcore.data import BulkDataResolver, InMemoryBulkStore  # noqa: E402
from engcore.domains.battery import measurement as ms  # noqa: E402
from engcore.scientific.certification_core.verifier import (  # noqa: E402
    verify_certification_record,
)
from engcore.scientific.corpus import (  # noqa: E402
    Applicability,
    CheckOutcome,
    NumericalCheck,
    NumericalCheckResult,
    NumericalEvidence,
    ValidationQueryPoint,
)
from engcore.scientific.multiphysics import PortRef  # noqa: E402
from engcore.scientific.results.uncertainty import (  # noqa: E402
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from engcore.scientific.units.quantity import Quantity  # noqa: E402

#: The trajectory the flagship evidence is produced on. A validation cell, so
#: producing this evidence reads nothing locked.
FLAGSHIP_TRAJECTORY = "B0006.d0001"

#: Refinement levels for the time-step study. The measured grid, then every
#: interval halved, then quartered. The current schedule is a held value and
#: does not change with the subdivision, so the only thing that moves is the
#: coupling window.
REFINEMENTS = (1, 2, 4)

#: The relative error the composition's own cross-domain balance checks must
#: stay inside. It is the composition's declared staggered-splitting band, not
#: a claim about the cell.
CONSERVATION_RELATIVE_BOUND = 5e-3

#: A refinement check is SATISFIED when the change from halving to quartering
#: is under this fraction of the metric's acceptance tolerance. A tenth: the
#: discretization must be small enough that it cannot decide a PASS/FAIL.
REFINEMENT_FRACTION = 0.1

#: Which fitted parameters carry a standard error into the parameter-UQ
#: channel, and the fact path each enters the run on.
UQ_PARAMETERS = {
    "ohmic_resistance_reference": (F_R0, "ohm"),
    "ohmic_activation_energy": (F_EA0, "joule/mole"),
    "polarization_resistance_reference": (F_R1, "ohm"),
    "polarization_activation_energy": (F_EA1, "joule/mole"),
    "polarization_capacitance": (F_C1, "farad"),
    "thermal_capacitance": (F_CTH, "joule/kelvin"),
    "thermal_conductance": (F_HA, "watt/kelvin"),
}


def _trajectory(selection, vendored, trajectory_id):
    item = next(
        x for x in selection["selected"] if x["trajectory_id"] == trajectory_id
    )
    raw = next(
        x for x in vendored["trajectories"] if x["trajectory_id"] == trajectory_id
    )
    return item, raw


def run_at(item, raw, parameters, *, refinement, run_id):
    channels = raw["channels"]
    return sim.run_trajectory(
        parameters=sim.parameter_quantities(parameters),
        times_s=channels["time_s"],
        currents_a=[-x for x in channels["current_a"]],
        ambient_k=item["ambient_temperature_c"] + 273.15,
        initial_temperature_k=channels["temperature_c"][0] + 273.15,
        run_id=run_id,
        scenario_id=run_id.replace("_", "-"),
        refinement=refinement,
        charge_state_floor=prereg.APPLICABILITY_CHARGE_STATE_FLOOR,
    )


def refinement_study(item, raw, parameters) -> dict[str, Any]:
    """Predicted voltage and temperature at the measured instants, refined."""
    series: dict[int, dict[float, dict[str, float]]] = {}
    for level in REFINEMENTS:
        started = time.perf_counter()
        authorized = run_at(
            item,
            raw,
            parameters,
            refinement=level,
            run_id=f"{prereg.CAMPAIGN_ID}.refine{level}.{item['trajectory_id']}",
        )
        rows = sim.trajectory_from_run(authorized)
        series[level] = {
            round(row["t"], 6): {
                "terminal_voltage": row["terminal_voltage"],
                "cell_temperature": row["cell_temperature"],
            }
            for row in rows
        }
        print(
            f"  refinement x{level}: {len(rows)} windows, "
            f"{time.perf_counter() - started:.1f}s",
            file=sys.stderr,
        )

    def compare(coarse: int, fine: int) -> dict[str, float]:
        shared = sorted(set(series[coarse]) & set(series[fine]))
        out = {"instants": len(shared)}
        for metric in ("terminal_voltage", "cell_temperature"):
            deltas = [
                abs(series[fine][t][metric] - series[coarse][t][metric])
                for t in shared
            ]
            out[metric] = max(deltas) if deltas else math.inf
        return out

    first = compare(REFINEMENTS[0], REFINEMENTS[1])
    second = compare(REFINEMENTS[1], REFINEMENTS[2])
    tolerances = {
        "terminal_voltage": prereg.ACCEPTANCE["terminal_voltage"][
            "per_sample_tolerance_v"
        ],
        "cell_temperature": prereg.ACCEPTANCE["cell_temperature"][
            "per_sample_tolerance_k"
        ],
    }
    verdicts = {}
    for metric, tolerance in tolerances.items():
        bound = REFINEMENT_FRACTION * tolerance
        verdicts[metric] = {
            "coarse_to_half": first[metric],
            "half_to_quarter": second[metric],
            "bound": bound,
            "satisfied": second[metric] <= bound,
            "converging": second[metric] <= first[metric],
        }
    return {
        "levels": list(REFINEMENTS),
        "shared_instants": second["instants"],
        "per_metric": verdicts,
        "satisfied": all(v["satisfied"] for v in verdicts.values()),
        "basis": (
            "the same scenario at the measured grid, at every interval halved, "
            "and at every interval quartered. The held current schedule is "
            "unchanged by the subdivision, so what moves is the coupling "
            "window and nothing else"
        ),
    }


def convergence_evidence(authorized) -> dict[str, Any]:
    """Every window's own outcome, from the run record."""
    outcomes: dict[str, int] = {}
    nonconverged: list[int] = []
    for window in authorized.run.windows:
        outcomes[window.outcome.value] = outcomes.get(window.outcome.value, 0) + 1
        for step in window.iterations[-1].participant_steps:
            if not step.internal_converged:
                nonconverged.append(window.index)
    return {
        "windows": len(authorized.run.windows),
        "window_outcomes": outcomes,
        "participant_steps_not_converged": nonconverged,
        "satisfied": not nonconverged,
    }


def conservation_evidence(authorized) -> dict[str, Any]:
    """The composition's own cross-domain checks, read off the authorized run."""
    checks: list[dict[str, Any]] = []
    for item in authorized.system_validation:
        for check in item.result.checks:
            checks.append(
                {
                    "protocol": item.protocol_id,
                    "check_id": check.check_id,
                    "passed": bool(check.passed),
                    "relative_error": float(check.relative_error),
                }
            )
    wanted = {"power_transfer_conservation", "coupled_energy_balance"}
    relevant = [item for item in checks if item["check_id"] in wanted]
    return {
        "checks": checks,
        "conservation_checks": relevant,
        "satisfied": bool(relevant) and all(item["passed"] for item in relevant),
    }


def uncertainty_inputs(calibration, group: str):
    """Standard errors from the fit, as STANDARD/PARAMETER external uncertainty.

    Only parameters whose fit produced a standard error contribute. One that
    did not is left UNKNOWN and contributes nothing, which is why the channel
    completeness matrix has something to report rather than a quiet zero.
    """
    record = next(item for item in calibration["groups"] if item["group"] == group)
    errors = record["standard_errors"]
    out: dict[PortRef, Uncertainty] = {}
    supplied: dict[str, float] = {}
    absent: list[str] = []
    for name, (path, unit) in sorted(UQ_PARAMETERS.items()):
        error = errors.get(name)
        if error is None:
            absent.append(name)
            continue
        supplied[name] = float(error)
        participant = "thermal" if path.startswith("thermal.") else "cell"
        port = path.split(".", 1)[1]
        out[PortRef(participant, port)] = Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(abs(float(error)), unit),
            source=(
                f"standard error of {name} from the calibration fit's own "
                f"Jacobian, on group {group}"
            ),
            method="least_squares_covariance",
            notes=(
                "a parameter standard error from the fit, not a measurement "
                "uncertainty; this source states no instrument accuracy"
            ),
            source_kind=UncertaintySource.PARAMETER,
        )
    return out, supplied, absent


def main() -> int:
    selection, vendored, calibration, inventory = cmp.load_inputs()
    item, raw = _trajectory(selection, vendored, FLAGSHIP_TRAJECTORY)
    if item["split"] != "validation":
        raise SystemExit(
            "the flagship evidence trajectory must be a validation cell; "
            "producing it on a locked case would open the holdout to build it"
        )
    group_parameters = cmp.parameters_for(calibration, item["group"])
    if group_parameters is None:
        raise SystemExit("the flagship trajectory's group produces no claim")
    vector = [group_parameters[name] for name in sim.PARAMETER_ORDER]

    print(f"flagship trajectory {FLAGSHIP_TRAJECTORY} ({item['group']})", file=sys.stderr)
    print("time-step refinement study:", file=sys.stderr)
    refinement = refinement_study(item, raw, vector)

    external_uncertainty, supplied, absent = uncertainty_inputs(
        calibration, item["group"]
    )
    print(
        f"parameter uncertainty: {len(supplied)} supplied, {len(absent)} unknown",
        file=sys.stderr,
    )

    authorized = run_at(
        item,
        raw,
        vector,
        refinement=1,
        run_id=f"{prereg.CAMPAIGN_ID}.flagship",
    )
    # The same run, with the fit's parameter uncertainties attached, so the
    # composition's own producer can propagate them.
    store = InMemoryBulkStore()
    from engcore.assembly.multiphysics import execute_authorized_graph_plan

    with_uq = execute_authorized_graph_plan(
        authorized.graph_plan,
        run_id=f"{prereg.CAMPAIGN_ID}.flagship.uq",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(store),
        store=store,
        external_uncertainty=external_uncertainty,
    )
    propagated = {
        f"{u.result.quantity}/{u.result.channel.value}": {
            "method": u.result.method_id,
            "standard_uncertainty": (
                None
                if u.result.uncertainty.standard_uncertainty is None
                else u.result.uncertainty.standard_uncertainty.to_dict()
            ),
            "notes": u.result.uncertainty.notes,
        }
        for u in with_uq.system_uncertainty
    }
    print(f"propagated uncertainty: {sorted(propagated)}", file=sys.stderr)

    target = authorized_run_binding(with_uq)
    convergence = convergence_evidence(with_uq)
    conservation = conservation_evidence(with_uq)
    numerical = NumericalEvidence(
        producer_id="battery_electrothermal.flagship",
        supported_checks=(
            NumericalCheck.CONVERGENCE,
            NumericalCheck.REFINEMENT,
            NumericalCheck.CONSERVATION,
        ),
        results=(
            NumericalCheckResult(
                NumericalCheck.CONVERGENCE,
                CheckOutcome.SATISFIED
                if convergence["satisfied"]
                else CheckOutcome.VIOLATED,
                (
                    f"{convergence['windows']} coupling windows, outcomes "
                    f"{convergence['window_outcomes']}; every participant step "
                    f"reported internal convergence"
                ),
                float(len(convergence["participant_steps_not_converged"])),
                0.0,
            ),
            NumericalCheckResult(
                NumericalCheck.REFINEMENT,
                CheckOutcome.SATISFIED
                if refinement["satisfied"]
                else CheckOutcome.VIOLATED,
                (
                    "halving then quartering every measured interval moves the "
                    "predicted voltage by at most "
                    f"{refinement['per_metric']['terminal_voltage']['half_to_quarter'] * 1000:.3f} mV "
                    "and the predicted temperature by at most "
                    f"{refinement['per_metric']['cell_temperature']['half_to_quarter']:.4f} K, "
                    "against a tenth of each acceptance tolerance"
                ),
                max(
                    refinement["per_metric"]["terminal_voltage"]["half_to_quarter"]
                    / refinement["per_metric"]["terminal_voltage"]["bound"],
                    refinement["per_metric"]["cell_temperature"]["half_to_quarter"]
                    / refinement["per_metric"]["cell_temperature"]["bound"],
                ),
                1.0,
            ),
            NumericalCheckResult(
                NumericalCheck.CONSERVATION,
                CheckOutcome.SATISFIED
                if conservation["satisfied"]
                else CheckOutcome.VIOLATED,
                (
                    "the heat the cell reported equals the heat the body "
                    "consumed in every window, and the energy deposited over "
                    "the run equals what the body stored plus what it rejected"
                ),
                max(
                    (item["relative_error"] for item in conservation["conservation_checks"]),
                    default=1.0,
                ),
                CONSERVATION_RELATIVE_BOUND,
            ),
        ),
        binding=target,
    )

    print("replaying the authorized run:", file=sys.stderr)
    replay_store = InMemoryBulkStore()
    replay = replay_authorized_graph_plan(
        with_uq,
        replay_run_id=f"{prereg.CAMPAIGN_ID}.flagship.replay",
        compositions=production_composition_packs(),
        executions=production_execution_packs(),
        resolver=BulkDataResolver(replay_store),
        store=replay_store,
        policy=DEFAULT_REPLAY_POLICY,
        external_uncertainty=external_uncertainty,
    )
    print(
        f"  {replay.status.value}, compared {replay.compared}, "
        f"verified {replay.verified}",
        file=sys.stderr,
    )

    # The envelope the validation campaign produced, rebound to this run.
    with open(
        os.path.join(EVIDENCE, "CAMPAIGN_VALIDATION.json"), encoding="utf-8"
    ) as fh:
        validation = json.load(fh)

    dataset = cmp.build_dataset(selection, vendored, inventory)
    from engcore.scientific.corpus import (
        ValidationEnvelope,
        build_coverage_by_metric,
        run_campaign,
    )

    predictions, _runs, _keep = cmp.predict(
        dataset,
        selection,
        calibration,
        splits=["calibration", "validation"],
    )
    from engcore.scientific.corpus import ValidationCampaign

    campaign_record = ValidationCampaign(
        campaign_id=prereg.CAMPAIGN_ID,
        version=prereg.CAMPAIGN_VERSION,
        dataset=dataset,
        splits=(
            cmp.DatasetSplit.CALIBRATION,
            cmp.DatasetSplit.VALIDATION,
        ),
        target=target,
        description="flagship envelope campaign, bound to the flagship run",
    )
    report = run_campaign(campaign_record, predictions)
    coverages = build_coverage_by_metric(report, dataset, cmp.VOLTAGE_REGION)
    voltage_coverage = coverages[ms.TERMINAL_VOLTAGE_METRIC]
    temperature_coverage = build_coverage_by_metric(
        report, dataset, cmp.TEMPERATURE_REGION
    )[ms.CELL_TEMPERATURE_METRIC]
    voltage_envelope = ValidationEnvelope(
        f"{prereg.CAMPAIGN_ID}.terminal_voltage",
        voltage_coverage,
        report.digest,
        target=target,
    )
    temperature_envelope = ValidationEnvelope(
        f"{prereg.CAMPAIGN_ID}.cell_temperature",
        temperature_coverage,
        report.digest,
        target=target,
    )

    # The point the flagship run makes a claim at, and it is deliberately a
    # point the envelope supports rather than the most interesting one: the
    # envelope's own answer is what decides, and asking it somewhere it says
    # no would be asking for a gate to be waived.
    query = ValidationQueryPoint(
        ms.TERMINAL_VOLTAGE_METRIC,
        {
            ms.DEPTH_OF_DISCHARGE: Quantity(0.1, "dimensionless"),
            ms.MEASURED_CELL_TEMPERATURE: Quantity(298.15, "kelvin"),
            ms.C_RATE: Quantity(1.0, "1/hour"),
        },
        declared=Applicability.INSIDE,
        label="10% discharged, 1C, cell at 25 degC",
    )

    # Two more points, classified and reported but NOT put to the gate. They
    # are where the envelope says no, and the report is more useful for naming
    # them than for leaving the boundary implicit.
    boundary = {
        "hot_at_1c": ValidationQueryPoint(
            ms.TERMINAL_VOLTAGE_METRIC,
            {
                ms.DEPTH_OF_DISCHARGE: Quantity(0.5, "dimensionless"),
                ms.MEASURED_CELL_TEMPERATURE: Quantity(308.15, "kelvin"),
                ms.C_RATE: Quantity(1.0, "1/hour"),
            },
            declared=Applicability.INSIDE,
            label="half discharged, 1C, cell at 35 degC",
        ),
        "two_c": ValidationQueryPoint(
            ms.TERMINAL_VOLTAGE_METRIC,
            {
                ms.DEPTH_OF_DISCHARGE: Quantity(0.3, "dimensionless"),
                ms.MEASURED_CELL_TEMPERATURE: Quantity(310.15, "kelvin"),
                ms.C_RATE: Quantity(2.0, "1/hour"),
            },
            declared=Applicability.INSIDE,
            label="30% discharged, 2C, cell at 37 degC",
        ),
    }

    assessment = assess_authorized_multiphysics_run(
        with_uq,
        policy=MULTIPHYSICS_PRODUCTION_POLICY,
        replay=replay,
        numerical=numerical,
        envelope=voltage_envelope,
        envelope_queries=(query,),
    )
    full_trust = assess_authorized_multiphysics_run(
        with_uq,
        policy=MULTIPHYSICS_FULL_TRUST_POLICY,
        replay=replay,
        numerical=numerical,
        envelope=voltage_envelope,
        envelope_queries=(query,),
    )
    record = certify_authorized_multiphysics_run(
        with_uq,
        commit_sha="0" * 40,
        policy=MULTIPHYSICS_PRODUCTION_POLICY,
        replay=replay,
        numerical=numerical,
        envelope=voltage_envelope,
        envelope_queries=(query,),
    )
    verification = verify_certification_record(record)

    blueprint = with_uq.graph_plan.blueprint_id
    snapshot = with_uq.composition_snapshot
    completeness = assess_protocol_completeness(
        snapshot,
        blueprint,
        "validation",
        tuple(
            (i.protocol_id, i.protocol_version) for i in with_uq.system_validation
        ),
    )
    uq_matrix = assess_uq_coverage(
        snapshot,
        blueprint,
        {
            (i.result.quantity, i.result.channel.value): (
                i.result.uncertainty,
                i.result.method_id,
            )
            for i in with_uq.system_uncertainty
        },
    )

    out = {
        "schema": "battery_thermal_flagship_s3_flagship/1",
        "campaign_id": prereg.CAMPAIGN_ID,
        "campaign_version": prereg.CAMPAIGN_VERSION,
        "trajectory": {
            "trajectory_id": FLAGSHIP_TRAJECTORY,
            "cell": item["cell"],
            "group": item["group"],
            "split": item["split"],
            "ambient_temperature_c": item["ambient_temperature_c"],
            "load_current_a": item["load_current_a"],
        },
        "run": {
            "run_id": with_uq.run.run_id,
            "windows": len(with_uq.run.windows),
            "scenario_digest": with_uq.run.scenario_digest,
            "blueprint_id": blueprint,
            "composition_pack": f"{snapshot.pack_id}@{snapshot.pack_version}",
            "composition_authority_digest": snapshot.authority_digest,
            "execution_pack": (
                f"{with_uq.execution_snapshot.pack_id}@"
                f"{with_uq.execution_snapshot.pack_version}"
            ),
            "terminated": (
                None
                if with_uq.run.termination is None
                else with_uq.run.termination.reason
            ),
        },
        "numerical": {
            "convergence": convergence,
            "refinement": refinement,
            "conservation": conservation,
            "evidence": numerical.to_dict(),
            "satisfied_checks": list(numerical.satisfied_checks),
            "violated_checks": list(numerical.violated_checks),
            "absent_checks": list(numerical.absent_checks),
        },
        "uncertainty": {
            "parameter_standard_errors_supplied": supplied,
            "parameters_without_a_standard_error": absent,
            "propagated": propagated,
            "channel_matrix": {
                "enforceable": uq_matrix.enforceable,
                "complete": uq_matrix.complete,
                "missing": [
                    f"{cell.quantity}/{cell.channel.value}"
                    for cell in uq_matrix.missing
                ],
            },
            "channels_not_quantified": {
                "measurement": prereg.SOURCE_MEASUREMENT_UNCERTAINTY["consequence"],
                "numerical": (
                    "bounded rather than quantified: the refinement study "
                    "measures how far the answer moves under subdivision and "
                    "the bound is reported, but no distribution is produced"
                ),
                "model_form": (
                    "UNKNOWN. The campaign's independent pass fraction exceeds "
                    "its calibration one and Core's diagnosis is "
                    "INSUFFICIENT_EVIDENCE, so no model-form inadequacy is "
                    "demonstrated -- which is not the same as a quantified "
                    "model-form uncertainty, and none is claimed"
                ),
            },
        },
        "replay": {
            "status": replay.status.value,
            "compared": replay.compared,
            "verified": replay.verified,
            "policy": replay.policy_id,
            "original_run_id": replay.original_run_id,
            "replay_run_id": replay.replay_run_id,
            "refusal_reason": replay.refusal_reason,
        },
        "envelope": {
            "terminal_voltage": voltage_envelope.to_dict(),
            "cell_temperature": temperature_envelope.to_dict(),
            "query_point": query.to_dict(),
            "classification": voltage_envelope.classify_point(query).to_dict(),
            "boundary_points": {
                name: {
                    "point": point.to_dict(),
                    "classification": voltage_envelope.classify_point(
                        point
                    ).to_dict(),
                }
                for name, point in boundary.items()
            },
            "supported_cells": [
                cell["label"]
                for cell in voltage_envelope.to_dict()["coverage"]["cells"]
                if cell["status"] == "supported"
            ],
            "failed_cells": [
                cell["label"]
                for cell in voltage_envelope.to_dict()["coverage"]["cells"]
                if cell["status"] == "failed"
            ],
        },
        "validation_protocol_completeness": {
            "enforceable": completeness.enforceable,
            "complete": completeness.complete,
        },
        "trust": {
            "production_policy": {
                "policy": MULTIPHYSICS_PRODUCTION_POLICY.policy_id,
                "satisfied": assessment.satisfied,
                "gates": {
                    item.gate_id: bool(item.passed)
                    for item in assessment.evaluations
                },
                "unmet_required": list(assessment.unmet_required),
                "recorded_gaps": list(assessment.recorded_gaps),
            },
            "full_trust_policy": {
                "policy": MULTIPHYSICS_FULL_TRUST_POLICY.policy_id,
                "satisfied": full_trust.satisfied,
                "unmet_required": list(full_trust.unmet_required),
            },
        },
        "certification": {
            "profile": record.profile.profile_id,
            "verified": verification.verified,
            "artifacts": sorted(a.name for a in record.artifacts),
        },
        "campaign_report_digest": report.digest,
    }
    text = json.dumps(out, indent=1, allow_nan=False)
    path = os.path.join(EVIDENCE, "FLAGSHIP.json")
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
        handle.write(b"\n")

    print()
    print(f"replay            {replay.status.value} (compared {replay.compared})")
    print(f"numerical         satisfied={list(numerical.satisfied_checks)}")
    print(f"production policy satisfied={assessment.satisfied}")
    print(f"  unmet required  {list(assessment.unmet_required)}")
    print(f"  recorded gaps   {list(assessment.recorded_gaps)}")
    print(f"full trust        satisfied={full_trust.satisfied}")
    print(f"  unmet required  {list(full_trust.unmet_required)}")
    print(f"certification     verified={verification.verified}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
