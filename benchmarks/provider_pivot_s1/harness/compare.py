"""P7 and P14: the native baseline against two PyBaMM models, on identical splits.

Three routes, one corpus, one applicability window, one scoring function:

======================  =================================================
``native``              ``battery.cell.electrothermal_1rc@0.2.0``, at the
                        parameters the Sprint 3 recovery froze, marched by
                        that round's own kernel. Nothing is refitted.
``pybamm_thevenin_1rc`` PyBaMM's equivalent-circuit model under a Forge
                        parameter authority whose R0 and R1 were fitted by
                        PyBOP on the calibration split only.
``pybamm_spme``         PyBaMM's SPMe under ``Chen2020`` -- the only
                        published parameter set available for it. There is
                        no characterisation of these cells at electrode
                        level, and this route exists to show what Forge
                        does about that.
======================  =================================================

What is NOT scored, and why there is no Gate A here
-----------------------------------------------------
``locked_holdout`` and ``observed_holdout``. Both have been read -- the first
by the recovery round that opened B0041 and diagnosed a +128 mV bias as missing
impedance growth, the second by Sprint 3. A cell whose residuals have been read
is not independent evidence, and this round does not re-open either, does not
score either, and does not call anything here a Gate A.

**Independent Gate A for any of these three models requires new evidence.** The
numbers below are development and validation evidence and are labelled as such
throughout.

Two risk reports, and the difference between them
--------------------------------------------------
``risk_applicability_screen`` asks: of the trajectories Forge was willing to
predict, how many were within the preregistered RMSE limit, and of those it
declined, how many would have been? That is the guardrail measured on its own.

``risk_trust_path`` asks the same question of the full credibility verdict. Its
answer for both providers is coverage zero, and the reason is stated rather
than presented as a surprise: neither route has validation evidence bound to it
in this sprint, so neither reaches SUPPORTED. That is the correct verdict and
it is the one a wrapper could not produce.

Both are computed by the same ``engcore.credibility.risk_coverage.summarise``,
over records that cannot name which engine produced them.

    python benchmarks/provider_pivot_s1/harness/compare.py
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
from common import march  # noqa: E402

from engcore.credibility.evidence import (  # noqa: E402
    CredibilityEvidenceReport,
    CredibilityVerdict,
)
from engcore.credibility.risk_coverage import (  # noqa: E402
    GroundTruth,
    PredictionOutcome,
    TrustDecision,
    summarise,
)
from engcore.data import BulkDataResolver, InMemoryBulkStore  # noqa: E402
from engcore.providers import ExecutionOutcome, replay_provider_request  # noqa: E402
from engcore.providers import pybamm_provider as pp  # noqa: E402

#: The preregistered voltage limits, read at run time from the recovery's own
#: file. This round holds no second copy of them and invents none of its own.
def gate_limits() -> dict[str, float]:
    voltage = common.preregistration()["gate_a_policy"]["gate_a"]["terminal_voltage"]
    return {
        "mae_v": float(voltage["mae_v"]),
        "rmse_v": float(voltage["rmse_v"]),
        "p95_v": float(voltage["p95_abs_v"]),
    }


#: How many provider runs are re-executed to check replay. Every one would
#: double the benchmark's cost for no extra information: replay is a property
#: of the provider and the request, not of the corpus.
REPLAY_SAMPLE = 3


def native_prediction(trajectory) -> dict[str, Any]:
    """The frozen native model's voltage over the window, or a declared refusal."""
    blocks = common.preregistration()["frozen_parameters"]
    block = blocks.get(trajectory.native_unit)
    if block is None:
        return {
            "outcome": "forge_refused",
            "detail": (
                f"no frozen parameter set for operating block "
                f"{trajectory.native_unit!r}; the model has no instance for it"
            ),
        }
    clock = time.perf_counter()
    instants, voltages, _temperatures, _states, refusal = march(
        cell_id=trajectory.cell,
        band=trajectory.band,
        times_s=trajectory.time_s,
        currents_a=trajectory.current_a,
        ambient_k=trajectory.ambient_k,
        initial_temperature_k=trajectory.temperature_k[0],
        parameters=block["fitted"],
        available_charge_ah=trajectory.capacity_ah,
        initial_state_of_charge=trajectory.initial_soc,
    )
    elapsed = time.perf_counter() - clock
    if refusal is not None and not voltages:
        return {
            "outcome": "model_not_applicable",
            "detail": f"declared authority declined at index {refusal.index}: {refusal.reason}",
            "wall_seconds": elapsed,
        }
    return {
        "outcome": "ok",
        "times": list(instants),
        "voltages": list(voltages),
        "wall_seconds": elapsed,
        "declined_tail": None if refusal is None else refusal.reason,
    }


def provider_prediction(
    trajectory,
    *,
    model_key: str,
    authority,
    factory,
    store=None,
    initial_state_of_charge: float | None = None,
) -> dict[str, Any]:
    """One PyBaMM run through the adapter, resolved back to a voltage series."""
    store = store or InMemoryBulkStore()
    protocol = pp.CurrentProtocol(
        duration_s=trajectory.duration_s,
        times_s=tuple(trajectory.time_s),
        currents_a=tuple(trajectory.current_a),
    )
    cell = common.cell_under_test(trajectory)
    provider = pp.PyBaMMProvider(
        authority=authority,
        cell=cell,
        protocol=protocol,
        parameter_values_factory=factory,
        store=store,
    )
    request = pp.build_request(
        model_key=model_key,
        authority=authority,
        cell=cell,
        protocol=protocol,
        qois=("terminal_voltage", "time"),
        initial_state_of_charge=(
            common.ecm_initial_state_of_charge(trajectory)
            if initial_state_of_charge is None
            else initial_state_of_charge
        ),
    )
    outcome = provider.execute(request)
    row: dict[str, Any] = {
        "outcome": outcome.outcome.value,
        "detail": outcome.receipt.detail,
        "wall_seconds": outcome.receipt.wall_seconds,
        "provider": provider,
        "request": request,
        "provider_result": outcome,
    }
    if outcome.outcome is not ExecutionOutcome.OK or outcome.result is None:
        return row
    resolver = BulkDataResolver(store)
    series = {
        reference.name.rsplit(":", 1)[1]: resolver.resolve(reference)
        for reference in outcome.result.data_references
    }
    row["times"] = list(series["time"])
    row["voltages"] = list(series["terminal_voltage"])
    row["identity"] = outcome.receipt.identity.to_dict()
    row["result"] = outcome.result
    return row


def residuals_of(prediction: dict[str, Any], trajectory) -> list[float]:
    """Predicted minus measured at every measured instant the route covers."""
    if prediction.get("outcome") != "ok":
        return []
    predicted = common.interpolate(
        prediction["times"], prediction["voltages"], trajectory.time_s
    )
    return [
        p - m
        for p, m in zip(predicted, trajectory.voltage_v)
        if p is not None
    ]


def ecm_authorities() -> dict[str, Any]:
    """The fitted authorities, read from ``FIT.json``. Never refitted here."""
    path = os.path.join(common.EVIDENCE, "FIT.json")
    if not os.path.exists(path):
        raise SystemExit(
            "FIT.json is missing; run benchmarks/provider_pivot_s1/harness/fit.py first"
        )
    record = common.load_json(path)
    out = {}
    for unit, block in record["blocks"].items():
        if block.get("fits"):
            out[unit] = block
    return out


def main() -> int:
    started = time.perf_counter()
    limits = gate_limits()
    fitted_blocks = ecm_authorities()
    trajectories = [
        common.windowed(t) for t in common.development_trajectories()
    ]
    chen = pp.NAMED_AUTHORITIES["Chen2020"]

    routes = ("native", "pybamm_thevenin_1rc", "pybamm_spme")
    rows: list[dict[str, Any]] = []
    replayed: list[dict[str, Any]] = []

    for trajectory in trajectories:
        block = fitted_blocks.get(trajectory.native_unit)
        record: dict[str, Any] = {
            "trajectory_id": trajectory.trajectory_id,
            "cell": trajectory.cell,
            "split": trajectory.split,
            "band": trajectory.band,
            "operating_block": trajectory.native_unit,
            "scored_samples": trajectory.sample_count,
            "routes": {},
        }

        record["routes"]["native"] = dict(
            _scored(native_prediction(trajectory), trajectory, limits),
            route_produces_results=False,
        )

        if block is None:
            record["routes"]["pybamm_thevenin_1rc"] = {
                "outcome": "forge_refused",
                "detail": (
                    f"no calibration fit exists for operating block "
                    f"{trajectory.native_unit!r}, so no parameter authority "
                    f"governs a run here"
                ),
                "statistics": common.statistics([]),
            }
        else:
            authority = pp.ParameterAuthority(
                **_authority_fields(block["authority"])
            )
            prediction = provider_prediction(
                trajectory,
                model_key="thevenin_1rc",
                authority=authority,
                factory=common.ecm_factory(
                    trajectory.band,
                    capacity_ah=trajectory.capacity_ah,
                    ambient_k=trajectory.ambient_k,
                    initial_temperature_k=trajectory.temperature_k[0],
                    r0_ohm=float(authority.overrides["R0 [Ohm]"]),
                    r1_ohm=float(authority.overrides["R1 [Ohm]"]),
                    c1_farad=float(authority.overrides["C1 [F]"]),
                ),
            )
            record["routes"]["pybamm_thevenin_1rc"] = _scored(
                prediction, trajectory, limits
            )
            if (
                prediction.get("outcome") == "ok"
                and len(replayed) < REPLAY_SAMPLE
            ):
                report = replay_provider_request(
                    prediction["provider"],
                    prediction["request"],
                    prediction["provider_result"],
                    tolerance=0.0,
                )
                replayed.append(
                    dict(report.to_dict(), trajectory_id=trajectory.trajectory_id)
                )

        record["routes"]["pybamm_spme"] = _scored(
            provider_prediction(
                trajectory,
                model_key="spme",
                authority=chen,
                factory=None,
            ),
            trajectory,
            limits,
        )
        rows.append(record)

    # --- aggregate ----------------------------------------------------
    summary: dict[str, Any] = {}
    for route in routes:
        for split in ("calibration", "validation"):
            subset = [r for r in rows if r["split"] == split]
            offered = [
                r for r in subset if r["routes"][route]["outcome"] == "ok"
            ]
            residuals = [
                value
                for r in offered
                for value in r["routes"][route]["residuals"]
            ]
            runtime = sum(
                float(r["routes"][route].get("wall_seconds") or 0.0) for r in subset
            )
            summary[f"{route}|{split}"] = {
                "route": route,
                "split": split,
                "trajectories": len(subset),
                "offered": len(offered),
                "refused": len(subset) - len(offered),
                "refusal_rate": (
                    (len(subset) - len(offered)) / len(subset) if subset else None
                ),
                "coverage": (len(offered) / len(subset)) if subset else None,
                "scored_samples": len(residuals),
                "statistics_volts": common.statistics(residuals),
                "wall_seconds": runtime,
                "refusal_reasons": sorted(
                    {
                        r["routes"][route]["outcome"]
                        for r in subset
                        if r["routes"][route]["outcome"] != "ok"
                    }
                ),
            }

    # --- Is the declared state margin doing any work? -----------------
    #
    # `common.ECM_STATE_MARGIN` maps the measured full-charge state into the
    # ECM's open interval. Its promise is that the mapping is small enough not
    # to matter, and a promise about a number is worth what measuring it costs.
    # So the equivalent-circuit route is run again at a tenth of the margin and
    # the two metric sets are differenced.
    tighter: list[float] = []
    looser: list[float] = []
    for trajectory in trajectories:
        block = fitted_blocks.get(trajectory.native_unit)
        if block is None:
            continue
        authority = pp.ParameterAuthority(**_authority_fields(block["authority"]))
        for margin, sink in ((common.ECM_STATE_MARGIN, looser), (common.ECM_STATE_MARGIN / 10.0, tighter)):
            probe = provider_prediction(
                trajectory,
                model_key="thevenin_1rc",
                authority=authority,
                factory=common.ecm_factory(
                    trajectory.band,
                    capacity_ah=trajectory.capacity_ah,
                    ambient_k=trajectory.ambient_k,
                    initial_temperature_k=trajectory.temperature_k[0],
                    r0_ohm=float(authority.overrides["R0 [Ohm]"]),
                    r1_ohm=float(authority.overrides["R1 [Ohm]"]),
                    c1_farad=float(authority.overrides["C1 [F]"]),
                ),
                initial_state_of_charge=common.ecm_initial_state_of_charge(
                    trajectory, margin
                ),
            )
            sink.extend(residuals_of(probe, trajectory))
    margin_sensitivity = {
        "declared_margin": common.ECM_STATE_MARGIN,
        "tenth_margin": common.ECM_STATE_MARGIN / 10.0,
        "statistics_at_declared_margin": common.statistics(looser),
        "statistics_at_tenth_margin": common.statistics(tighter),
    }
    for key in ("mae", "rmse", "p95", "bias"):
        first = margin_sensitivity["statistics_at_declared_margin"].get(key)
        second = margin_sensitivity["statistics_at_tenth_margin"].get(key)
        margin_sensitivity[f"delta_{key}_volts"] = (
            None if first is None or second is None else second - first
        )

    # --- What the screen refused, and whether it was right ------------
    #
    # An over-refusal rate cannot be measured from refusals alone: the thing
    # being asked is what the model WOULD have said, and a refusal is exactly
    # the absence of that. So for every trajectory the equivalent-circuit
    # route declined, the run is repeated under a COUNTERFACTUAL authority --
    # the same fitted R0, R1 and C1, with the nominal capacity declared to be
    # this cell's own measured available charge, which is the field the screen
    # turned on.
    #
    # That authority is a measuring instrument and nothing else. It has its own
    # digest, it is never written to FIT.json, and no prediction made under it
    # is offered as a supported one. It exists so that "the screen was right"
    # is a measured statement rather than an assertion.
    counterfactual: list[dict[str, Any]] = []
    for row, trajectory in zip(rows, trajectories):
        entry = row["routes"]["pybamm_thevenin_1rc"]
        block = fitted_blocks.get(trajectory.native_unit)
        if entry["outcome"] == "ok" or block is None:
            continue
        fields = _authority_fields(block["authority"])
        overrides = dict(fields.pop("overrides"))
        parent = pp.ParameterAuthority(
            **dict(
                fields,
                overrides={},
                source="forge_declared",
                authority_id=fields["authority_id"] + "/counterfactual",
                nominal_capacity_ah=trajectory.capacity_ah,
                parent_authority_digest=None,
            )
        )
        probe = parent.derive(
            authority_id=fields["authority_id"] + "/counterfactual/fitted",
            overrides=overrides,
            notes=(
                "COUNTERFACTUAL. Declares this cell's own measured available "
                "charge so that the capacity screen passes, in order to measure "
                "what the refused run would have produced. Not a supported "
                "prediction and not an authority any decision may cite"
            ),
        )
        probed = _scored(
            provider_prediction(
                trajectory,
                model_key="thevenin_1rc",
                authority=probe,
                factory=common.ecm_factory(
                    trajectory.band,
                    capacity_ah=trajectory.capacity_ah,
                    ambient_k=trajectory.ambient_k,
                    initial_temperature_k=trajectory.temperature_k[0],
                    r0_ohm=float(overrides["R0 [Ohm]"]),
                    r1_ohm=float(overrides["R1 [Ohm]"]),
                    c1_farad=float(overrides["C1 [F]"]),
                ),
            ),
            trajectory,
            limits,
        )
        native_rmse = row["routes"]["native"]["statistics"].get("rmse")
        counterfactual.append(
            {
                "trajectory_id": trajectory.trajectory_id,
                "measured_capacity_ah": trajectory.capacity_ah,
                "declared_capacity_ah": float(
                    block["authority"]["nominal_capacity_ah"]
                ),
                "refusal_reason": entry["detail"],
                "counterfactual_outcome": probed["outcome"],
                "counterfactual_rmse_v": probed["statistics"].get("rmse"),
                "native_rmse_v": native_rmse,
                "counterfactual_authority_digest": probe.digest(),
            }
        )

    # --- P14: the same metric over both engines -----------------------
    probed_truth = {
        item["trajectory_id"]: (
            GroundTruth.UNKNOWN
            if item["counterfactual_rmse_v"] is None
            else (
                GroundTruth.WITHIN_TOLERANCE
                if item["counterfactual_rmse_v"] <= limits["rmse_v"]
                else GroundTruth.OUTSIDE_TOLERANCE
            )
        )
        for item in counterfactual
    }

    risk_screen: dict[str, Any] = {}
    risk_trust: dict[str, Any] = {}
    for route in routes:
        screen_cases = []
        trust_cases = []
        for r in rows:
            entry = r["routes"][route]
            truth = _truth_of(entry, limits)
            if (
                truth is GroundTruth.UNKNOWN
                and route == "pybamm_thevenin_1rc"
                and r["trajectory_id"] in probed_truth
            ):
                # The counterfactual above observed what this refusal hid.
                truth = probed_truth[r["trajectory_id"]]
            screen_cases.append(
                PredictionOutcome(
                    case_id=r["trajectory_id"],
                    decision=(
                        TrustDecision.SUPPORTED
                        if entry["outcome"] == "ok"
                        else TrustDecision.REFUSED
                    ),
                    truth=truth,
                    margin=entry.get("margin"),
                )
            )
            decision = _trust_decision(entry)
            if decision is not None:
                trust_cases.append(
                    PredictionOutcome(
                        case_id=r["trajectory_id"], decision=decision, truth=truth
                    )
                )
        risk_screen[route] = summarise(screen_cases).to_dict()
        risk_trust[route] = (
            summarise(trust_cases).to_dict()
            if len(trust_cases) == len(rows)
            else {
                "not_computed": (
                    "this route produces no ScientificResult, so there is "
                    "nothing for the credibility path to assemble. The Sprint 3 "
                    "recovery's own freeze record states the same limit for "
                    "this march: it produces no replay of an authorized plan "
                    "and no certification record. A result was NOT fabricated "
                    "here in order to fill this cell"
                ),
                "cases_with_a_result": len(trust_cases),
                "cases_total": len(rows),
            }
        )

    record = {
        "schema": "provider_pivot_s1_comparison/1",
        "what_this_is": (
            "development and validation evidence for three routes over one "
            "corpus. It is NOT a Gate A and no holdout was opened or scored"
        ),
        "independent_gate_a": (
            "requires new evidence. Every cell in this archive has had its "
            "residuals read -- B0041 by the Sprint 3 recovery and "
            "B0007/B0036/B0044 by Sprint 3 itself -- so no pristine holdout "
            "remains here and this round did not manufacture one"
        ),
        "gate_limits_volts": limits,
        "applicability_window": {
            "rule": "charge state at or above the band's OCV authority floor",
            "floors": {
                band: common.charge_state_floor(band) for band in ("warm", "cold")
            },
            "samples_inside": sum(t.sample_count for t in trajectories),
            "applies_to": "every route identically",
        },
        "state_margin_sensitivity": margin_sensitivity,
        "declared_approximations": {
            "ecm_state_margin": common.ECM_STATE_MARGIN,
            "why": (
                "the native model's charge state is closed at 1 and PyBaMM's "
                "ECM interval is open there; the measured full-charge state is "
                "mapped to the largest state the ECM can represent"
            ),
        },
        "routes": summary,
        "risk_applicability_screen": risk_screen,
        "risk_trust_path": risk_trust,
        "counterfactual_probe": {
            "what_it_is": (
                "every trajectory the equivalent-circuit route refused, re-run "
                "under an authority that declares this cell's own measured "
                "capacity, so that the screen's over-refusal rate is measured "
                "rather than left unmeasurable. No prediction here is offered "
                "as supported and no decision may cite these authorities"
            ),
            "cases": counterfactual,
        },
        "replay": replayed,
        "per_trajectory": [
            {
                key: value
                for key, value in r.items()
                if key != "routes"
            }
            | {
                "routes": {
                    name: {
                        k: v
                        for k, v in entry.items()
                        if k not in ("residuals", "times", "voltages", "provider",
                                     "request", "provider_result", "result")
                    }
                    for name, entry in r["routes"].items()
                }
            }
            for r in rows
        ],
        "wall_seconds": time.perf_counter() - started,
    }
    path = common.write_evidence("COMPARISON.json", record)

    print(f"{'route':22} {'split':11} {'n':>4} {'off':>4} {'ref%':>6} "
          f"{'MAE mV':>8} {'RMSE mV':>8} {'P95 mV':>8} {'bias mV':>8} {'s':>7}")
    for key in sorted(summary):
        s = summary[key]
        st = s["statistics_volts"]
        def mv(name):
            value = st.get(name)
            return f"{value * 1000:8.2f}" if value is not None else f"{'--':>8}"
        print(
            f"{s['route']:22} {s['split']:11} {s['trajectories']:4} "
            f"{s['offered']:4} {s['refusal_rate']:6.0%} "
            f"{mv('mae')} {mv('rmse')} {mv('p95')} {mv('bias')} "
            f"{s['wall_seconds']:7.2f}"
        )
    print()
    for route in routes:
        screen = risk_screen[route]
        trust = risk_trust[route]
        trust_text = (
            f"coverage={_pct(trust['coverage'])}"
            if "coverage" in trust
            else "not computed (route produces no ScientificResult)"
        )
        print(
            f"{route:22} screen: coverage={_pct(screen['coverage'])} "
            f"false_trust={_pct(screen['false_trust_rate'])} "
            f"over_refusal={_pct(screen['over_refusal_rate'])}  |  "
            f"trust path: {trust_text}"
        )
    print()
    for item in replayed:
        print(
            f"replay {item['trajectory_id']:16} executed={item['executed']} "
            f"identity_matched={item['identity_matched']} "
            f"reproduced={item['reproduced']} maxdiff={item['max_absolute_difference']}"
        )
    print(f"\nwrote {path} in {record['wall_seconds']:.1f}s")
    return 0


def _pct(value):
    return "  n/a" if value is None else f"{value:5.1%}"


def _authority_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields = dict(payload)
    band = fields.pop("temperature_validity_k")
    fields["temperature_validity_k"] = None if band is None else tuple(band)
    return fields


def _scored(prediction: dict[str, Any], trajectory, limits) -> dict[str, Any]:
    residuals = residuals_of(prediction, trajectory)
    statistics = common.statistics(residuals)
    entry = dict(prediction)
    entry["residuals"] = residuals
    entry["statistics"] = statistics
    rmse = statistics.get("rmse")
    entry["margin"] = (
        None if rmse is None else (limits["rmse_v"] - rmse) / limits["rmse_v"]
    )
    return entry


def _truth_of(entry: dict[str, Any], limits) -> GroundTruth:
    """Was this trajectory within the preregistered voltage limit?

    A route that offered no prediction has no residual, so its truth is UNKNOWN
    -- what the model *would* have said is not observable. That is why the
    over-refusal rate below is null for every route: this corpus cannot say
    whether a refusal was necessary without running the refused case, and
    running it would be the refusal not happening.
    """
    rmse = entry.get("statistics", {}).get("rmse")
    if rmse is None:
        return GroundTruth.UNKNOWN
    return (
        GroundTruth.WITHIN_TOLERANCE
        if rmse <= limits["rmse_v"]
        else GroundTruth.OUTSIDE_TOLERANCE
    )


def _trust_decision(entry: dict[str, Any]) -> "TrustDecision | None":
    """The credibility path's verdict for this run.

    ``None`` means this route produced no ``ScientificResult`` at all, which is
    different from producing one the path declined. The native march is that
    case -- it predates the result contract in this corpus -- and the caller
    reports the absence rather than scoring it as a refusal, because scoring it
    would credit the native route with a guardrail it did not exercise.
    """
    result = entry.get("result")
    if entry.get("outcome") != "ok":
        return (
            TrustDecision.REFUSED
            if entry.get("route_produces_results", True)
            else None
        )
    if result is None:
        return None
    report = CredibilityEvidenceReport.from_result(result)
    if report.verdict is CredibilityVerdict.SUPPORTED:
        return TrustDecision.SUPPORTED
    if report.verdict is CredibilityVerdict.NOT_SUPPORTED:
        return TrustDecision.NOT_SUPPORTED
    return TrustDecision.REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
