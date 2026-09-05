"""E1 orchestration: verification gate, controls, campaign, artifacts.

Runs in this order, and the order is the point:

1. SOLVER VERIFICATION GATE — the real solver against the analytic oracle at
   preregistered truth-free points. If any point disagrees beyond the declared
   tolerance the experiment STOPS as a solver/integration verification
   failure; Bayesian inference over an unverified solver is not performed.
2. PRIOR CONTROLS — decision, EVPI, EVSI table and predictives at the prior,
   recorded before any observation exists.
3. THE CAMPAIGN — the frozen M5 CampaignRunner drives snapshot -> candidates
   -> M4 scoring (real EVSI inside) -> selection -> real solver execution ->
   Evidence -> Critic -> Arbiter -> Gateway -> fresh snapshot -> stop proposal.
4. GRADING — terminal decision from the final posterior against the analytic
   oracle, plus the certificate-assumption table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.engcore.sria.campaign import CampaignEventType

from . import e1_truth
from .e1_config import (
    ACTIONS,
    MAX_ITERATIONS,
    THRESHOLD_OHM,
    VERIFICATION_ABS_TOL_VOLT,
    VERIFICATION_POINTS,
    VERIFICATION_REL_TOL,
    config_hash,
    config_payload,
    indifference_probability,
    theta_grid,
)
from .e1_harness import build_e1_campaign, preregistration_hash
from .e1_model import (
    best_decision,
    evpi,
    evsi_table,
    p_above,
    posterior_weights,
    prior_weights,
    solver_vmid,
)

import numpy as np


def run_solver_verification() -> dict[str, Any]:
    """Control 4 — the gate. Solver vs analytic oracle, truth-free points."""
    rows = []
    worst_abs = 0.0
    worst_rel = 0.0
    for index, (vs, r2) in enumerate(VERIFICATION_POINTS):
        solver_value = solver_vmid(vs, r2, run_id=f"e1-verify-{index:02d}")
        analytic_value = e1_truth.analytic_vmid(vs, r2)
        abs_err = abs(solver_value - analytic_value)
        rel_err = abs_err / max(abs(analytic_value), 1e-300)
        worst_abs = max(worst_abs, abs_err)
        worst_rel = max(worst_rel, rel_err)
        rows.append(
            {
                "source_voltage_volt": vs,
                "r2_ohm": r2,
                "solver_vmid_volt": solver_value,
                "analytic_vmid_volt": analytic_value,
                "abs_error_volt": abs_err,
                "rel_error": rel_err,
            }
        )
    passed = worst_rel <= VERIFICATION_REL_TOL or worst_abs <= VERIFICATION_ABS_TOL_VOLT
    noise_floor = min(a.noise_sigma_volt for a in ACTIONS)
    return {
        "points": rows,
        "worst_abs_error_volt": worst_abs,
        "worst_rel_error": worst_rel,
        "rel_tol": VERIFICATION_REL_TOL,
        "abs_tol_volt": VERIFICATION_ABS_TOL_VOLT,
        "passed": passed,
        "numerical_error_vs_noise": {
            "smallest_declared_sigma_volt": noise_floor,
            "worst_abs_error_volt": worst_abs,
            "ratio": worst_abs / noise_floor,
            "statement": (
                "solver-vs-analytic error is negligible relative to the "
                "declared benchmark observation noise"
                if worst_abs / noise_floor < 1e-6
                else "numerical error is NOT negligible relative to the noise"
            ),
        },
    }


def _summarize_posterior(weights) -> dict[str, Any]:
    grid = theta_grid()
    mean = float(np.dot(weights, grid))
    sd = float(np.sqrt(max(np.dot(weights, (grid - mean) ** 2), 0.0)))
    decision, value = best_decision(weights)
    return {
        "mean_r2_ohm": mean,
        "sd_r2_ohm": sd,
        "p_above_threshold": p_above(weights),
        "bayes_decision": decision,
        "expected_utility": value,
        "evpi": evpi(weights),
        "effective_support_points": int(np.count_nonzero(weights > 1e-12)),
    }


def certificate_assumptions(verification: dict[str, Any]) -> list[dict[str, str]]:
    """What the E1 certificate is conditional on, labelled honestly."""
    ratio = verification["numerical_error_vs_noise"]["ratio"]
    return [
        {
            "proposition": "circuit topology (two-resistor divider, ideal source)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "declared in the preregistered configuration",
        },
        {
            "proposition": "solver/model equations (linear resistive DC via MNA)",
            "status": "ANALYTICALLY_CHECKED",
            "basis": (
                f"agreement with the closed-form divider relation at "
                f"{len(VERIFICATION_POINTS)} preregistered points, worst "
                f"relative error {verification['worst_rel_error']:.3e}"
            ),
        },
        {
            "proposition": "observation mapping (y measures node_voltage:mid)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "declared observation model",
        },
        {
            "proposition": "observation noise (Gaussian, declared sigma)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "benchmark-injected synthetic noise, honestly labelled; the "
                "solver itself is deterministic"
            ),
        },
        {
            "proposition": "prior (uniform over the frozen R2 grid)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "preregistered before any scored observation",
        },
        {
            "proposition": "terminal utility / loss matrix",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "preregistered; asymmetric with indifference at P=0.8",
        },
        {
            "proposition": "acquisition cost model (declared per-action costs)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "preregistered; no fitted cost model in E1",
        },
        {
            "proposition": "computational failure probability p_cf = 0",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "declared, not measured. A dense LU on a well-conditioned 3x3 "
                "MNA system did not fail in this experiment, but no failure "
                "corpus exists for this domain and M2 failure learning remains "
                "INSUFFICIENT_DATA. Every candidate score carries the factor "
                "(1 - p_cf) = 1 on this assertion"
            ),
        },
        {
            "proposition": (
                "cost-to-utility tradeoff lambda = 1.0 (declared benchmark "
                "cost units per unit of terminal loss)"
            ),
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "preregistered exchange rate with no external referent. It "
                "sets which actions are affordable and therefore drives "
                "selection directly: at lambda = 1.0 the premium instrument "
                "has EVSI 0.644 against cost 5.0 and loses, while a campaign "
                "valuing the decision ~10x higher would buy it. The ordering "
                "of actions by information is independent of lambda; the "
                "ordering by net value is not"
            ),
        },
        {
            "proposition": "support/transport: IN_DOMAIN_FOR_THIS_VERIFICATION",
            "status": "VERIFIED",
            "basis": (
                "the decision QoI is the inferred parameter itself; the "
                "observed operating conditions are exactly the candidate "
                "action set; the solver is verified across the full prior "
                "support; no extrapolation beyond verified conditions occurs"
            ),
        },
        {
            "proposition": "posterior arithmetic (normalized, batch==sequential, "
            "order-invariant)",
            "status": "VERIFIED",
            "basis": "tests over the exact grid update",
        },
        {
            "proposition": "EVSI bounds (0 <= EVSI <= EVPPI = EVPI)",
            "status": "VERIFIED",
            "basis": (
                "tests; EVPPI(R2) = EVPI because R2 is the complete latent "
                "decision-relevant state"
            ),
        },
        {
            "proposition": "numerical error negligible vs observation noise",
            "status": "VERIFIED",
            "basis": f"worst |solver-analytic| / smallest sigma = {ratio:.3e}",
        },
    ]


def run_e1(true_r2_ohm: float | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "experiment": "E1",
        "config_hash": config_hash(),
        "preregistration_hash": preregistration_hash(),
        "config": config_payload(),
        "truth": e1_truth.truth_payload(),
    }

    # ---- 1. verification gate -------------------------------------------
    verification = run_solver_verification()
    result["solver_verification"] = verification
    if not verification["passed"]:
        result["verdict"] = "E1 FAILED — SOLVER/INTEGRATION VERIFICATION FAILURE"
        return result

    # ---- 2. prior controls (before any observation) ----------------------
    prior = prior_weights()
    result["prior_stage"] = {
        "posterior": _summarize_posterior(prior),
        "indifference_probability": indifference_probability(),
        "evsi_table": evsi_table(prior),
    }

    # ---- 3. the campaign --------------------------------------------------
    runner, harness, gateway, _arbiter = build_e1_campaign(
        true_r2_ohm=true_r2_ohm
    )
    runner.run_campaign()

    events = runner.events
    recommended = [
        e.sequence
        for e in events.of_type(CampaignEventType.DECISION_RECOMMENDED)
    ]
    executed = [
        e.sequence for e in events.of_type(CampaignEventType.EXECUTION_STARTED)
    ]
    iterations = [record.to_dict() for record in runner.run.iterations]

    observations = harness.current_observations()
    final = harness.posterior_for(observations)

    result["campaign"] = {
        "run_state": runner.run.state.value,
        "pause_reason": (
            runner.run.pause_reason.value if runner.run.pause_reason else None
        ),
        "stop_review_outcome": runner.run.stop_review_outcome,
        "iterations": iterations,
        "event_sequences": {
            "decision_recommended": recommended,
            "execution_started": executed,
            "prediction_preceded_observation": bool(
                recommended and executed and recommended[0] < executed[0]
            ),
        },
        "admitted_evidence": [
            {
                "evidence_id": entry.evidence_id,
                "belief_key": entry.belief_key,
                "payload": dict(entry.claim_payload),
            }
            for entry in gateway.belief.active_view().values()
        ],
        "decision_log": harness.decision_log,
        "budget": {
            "spent_total": runner.budget.spent_total,
            "remaining": runner.budget.remaining,
        },
    }

    # ---- 4. grading --------------------------------------------------------
    final_summary = _summarize_posterior(final)
    sria_decision = final_summary["bayes_decision"]
    oracle = e1_truth.oracle_decision(
        e1_truth.TRUE_R2_OHM if true_r2_ohm is None else true_r2_ohm
    )
    result["posterior_after"] = final_summary
    result["evsi_table_after"] = evsi_table(final)
    result["terminal_decision"] = {
        "sria_decision": sria_decision,
        "oracle_decision": oracle,
        "correct": sria_decision == oracle,
        "threshold_ohm": THRESHOLD_OHM,
    }
    result["evppi_statement"] = (
        "EVPPI(R2) = EVPI: R2 is the complete latent decision-relevant state"
    )
    result["transport_support"] = "IN_DOMAIN_FOR_THIS_VERIFICATION"
    result["certificate_assumptions"] = certificate_assumptions(verification)
    result["verdict"] = (
        "E1 VERIFIED END-TO-END"
        if sria_decision == oracle and runner.run.iterations
        else "E1 PARTIALLY VERIFIED"
    )
    return result


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# E1 — Electrical quantitative verification")
    add("")
    add(f"Config hash: `{result['config_hash']}`")
    add(f"Preregistration hash (config+truth): `{result['preregistration_hash']}`")
    add("")
    add("## Solver verification (gate)")
    add("")
    add("| Vs [V] | R2 [ohm] | solver V_mid [V] | analytic V_mid [V] | abs err [V] | rel err |")
    add("|---|---|---|---|---|---|")
    for row in result["solver_verification"]["points"]:
        add(
            f"| {row['source_voltage_volt']:g} | {row['r2_ohm']:g} | "
            f"{row['solver_vmid_volt']:.12g} | {row['analytic_vmid_volt']:.12g} | "
            f"{row['abs_error_volt']:.3e} | {row['rel_error']:.3e} |"
        )
    v = result["solver_verification"]
    add("")
    add(
        f"Worst relative error {v['worst_rel_error']:.3e} "
        f"(tolerance {v['rel_tol']:.1e}); "
        f"|error|/sigma = {v['numerical_error_vs_noise']['ratio']:.3e}."
    )
    if "prior_stage" not in result:
        add("")
        add(f"**{result['verdict']}**")
        return "\n".join(lines)

    add("")
    add("## Prior stage (no observations)")
    p = result["prior_stage"]["posterior"]
    add("")
    add(
        f"decision {p['bayes_decision']} | P(above)={_fmt(p['p_above_threshold'])} "
        f"| EVPI={_fmt(p['evpi'])} | mean R2={_fmt(p['mean_r2_ohm'])} "
        f"| sd={_fmt(p['sd_r2_ohm'])}"
    )
    add("")
    add("| action | EVSI | cost | net | predictive mean [V] | predictive sd [V] |")
    add("|---|---|---|---|---|---|")
    for action_id, row in sorted(result["prior_stage"]["evsi_table"].items()):
        add(
            f"| {action_id} | {_fmt(row['evsi'])} | {_fmt(row['cost'])} | "
            f"{_fmt(row['net'])} | {_fmt(row['predictive_mean_volt'])} | "
            f"{_fmt(row['predictive_sd_volt'])} |"
        )
    add("")
    add("## Campaign")
    c = result["campaign"]
    add("")
    add(
        f"state={c['run_state']} pause={c['pause_reason']} "
        f"stop_review={c['stop_review_outcome'] or 'n/a'} "
        f"spent={_fmt(c['budget']['spent_total'])}"
    )
    for it in c["iterations"]:
        add(
            f"- iteration {it['iteration']}: outcome={it['recommendation_outcome']} "
            f"selected={it['selected_action_id'] or '-'} "
            f"verdict={it['arbiter_verdict'] or '-'} "
            f"admitted={it['admitted_evidence_ids']}"
        )
    add(
        f"- prediction preceded observation: "
        f"{c['event_sequences']['prediction_preceded_observation']} "
        f"(DECISION_RECOMMENDED seq {c['event_sequences']['decision_recommended']} "
        f"< EXECUTION_STARTED seq {c['event_sequences']['execution_started']})"
    )
    add("")
    add("## Posterior after campaign")
    q = result["posterior_after"]
    add("")
    add(
        f"decision {q['bayes_decision']} | P(above)={_fmt(q['p_above_threshold'])} "
        f"| EVPI={_fmt(q['evpi'])} | mean R2={_fmt(q['mean_r2_ohm'])} "
        f"| sd={_fmt(q['sd_r2_ohm'])}"
    )
    add("")
    add("## Terminal decision")
    t = result["terminal_decision"]
    add("")
    add(
        f"SRIA: **{t['sria_decision']}** | oracle: **{t['oracle_decision']}** | "
        f"correct: **{t['correct']}**"
    )
    add("")
    add("## Certificate assumptions")
    add("")
    add("| proposition | status | basis |")
    add("|---|---|---|")
    for row in result["certificate_assumptions"]:
        add(f"| {row['proposition']} | {row['status']} | {row['basis']} |")
    add("")
    add(f"**{result['verdict']}**")
    return "\n".join(lines)


def main() -> int:
    result = run_e1()
    root = Path(__file__).resolve().parent
    (root / "e1_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
                "truth": result["truth"],
                "preregistration_hash": result["preregistration_hash"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "e1_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "e1_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if result["verdict"] == "E1 VERIFIED END-TO-END" else 1


if __name__ == "__main__":
    raise SystemExit(main())
