"""Entry point: ``python -m experiments.electrical_v01_demo.run``

Writes three artifacts next to this module and prints a short console summary:

    demo_config_frozen.json   the declared scenario and its hashes
    demo_results.json         the machine-readable trace
    demo_report.md            the human-readable report

No CLI framework, no options. One command, one scenario, deterministic output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .demo_config import REQUIRED_ACTION_IDS, REQUIREMENT_ID
from .demo_run import PREDICTION_REF_LIMITATION, run_demo


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    a = result["world_a_model_adequate"]
    b = result["world_b_model_inadequate"]

    add("# Electrical V0.1 — end-to-end demonstration")
    add("")
    add(f"Base commit `{result['base_commit']}` · config hash "
        f"`{result['config_hash']}` · scenario hash `{result['scenario_hash']}`")
    add("")
    add("## What was asked")
    add("")
    add(result["scientific_question"])
    add("")
    add(
        "The campaign is allowed to assume the resistance is a single constant. "
        "That assumption is the thing on trial: it may not be certified until "
        "it has been tested at operating conditions the parameter measurement "
        "never visited."
    )

    add("")
    add("## What was assumed, and what was uncertain")
    add("")
    inherited = result["config"]["inherited_from_e2"]
    add(f"- **Model** — one constant unknown resistance `R2`, forward-mapped by "
        f"the real `ElectricalDCSolver`. The decision path never uses a formula.")
    add(f"- **Uncertain** — `R2` on a {inherited['grid']['points']}-point grid "
        f"from {inherited['grid']['min_ohm']:g} to "
        f"{inherited['grid']['max_ohm']:g} ohm, uniform prior "
        f"(sd {_fmt(a['posterior_prior']['sd_r2_ohm'])} ohm).")
    add(f"- **Decision** — A iff `R2` > {inherited['threshold_ohm']:g} ohm, with "
        f"asymmetric loss {inherited['loss']['A_when_below']:g} : "
        f"{inherited['loss']['B_when_above']:g}, so indifference sits at "
        f"P(above) = 0.8.")
    add(f"- **Instruments** — one precise parameter measurement at 10 V "
        f"(sigma 0.01 V, cost 0.10) and five validation probes at 16–28 V "
        f"(sigma 0.05 V, cost 0.15 each).")
    add(f"- **Certification requirement** — `{REQUIREMENT_ID}`, requiring "
        f"exactly {len(REQUIRED_ACTION_IDS)} of those probes: "
        f"{', '.join('`' + r + '`' for r in REQUIRED_ACTION_IDS)}. Two probes "
        f"exist and are never required, which is what makes it finite.")

    for title, world in (("World A — model adequate", a),
                         ("World B — model inadequate", b)):
        add("")
        add(f"## {title}")
        add("")
        add(f"Hidden truth: `{world['truth_spec_id']}` — inside the assumed "
            f"family: **{world['truth_in_assumed_family']}**. The decision path "
            f"is not told either way.")
        add("")
        add("### What it measured, and why")
        add("")
        add("| iter | action | family | reason | parameter EVSI | cost | net |")
        add("|---|---|---|---|---|---|---|")
        scores_by_iteration = {s["iteration"]: s for s in world["score_trace"]}
        for row in world["selection_trace"]:
            score = next(
                (
                    r
                    for r in scores_by_iteration.get(
                        row["iteration"], {"scores": []}
                    )["scores"]
                    if r["action_id"] == row["action_id"]
                ),
                None,
            )
            add(
                f"| {row['iteration']} | `{row['action_id']}` | "
                f"{row['action_family']} | `{row['execution_reason']}` | "
                f"{score['parameter_evsi']:.3e} | {_fmt(score['cost'])} | "
                f"{score['net_value']:+.4f} |"
                if score
                else f"| {row['iteration']} | `{row['action_id']}` | "
                f"{row['action_family']} | `{row['execution_reason']}` | - | - | - |"
            )
        add("")
        add(
            f"Iteration 1 bought parameter learning because it was worth its "
            f"price. From iteration 2 on, **every** action scored net-negative "
            f"— including the probes that were then executed anyway, for a "
            f"stated constraint reason."
        )
        add("")
        add("### What changed in the posterior")
        add("")
        p0, p1 = world["posterior_prior"], world["posterior_final"]
        add(f"| | mean [ohm] | sd [ohm] | P(above) | EVPI | decision |")
        add("|---|---|---|---|---|---|")
        add(f"| prior | {_fmt(p0['mean_r2_ohm'])} | {_fmt(p0['sd_r2_ohm'])} | "
            f"{_fmt(p0['p_above_threshold'])} | {p0['evpi']:.3e} | "
            f"{p0['bayes_decision']} |")
        add(f"| final | {_fmt(p1['mean_r2_ohm'])} | {_fmt(p1['sd_r2_ohm'])} | "
            f"{p1['p_above_threshold']:.8f} | {p1['evpi']:.3e} | "
            f"{p1['bayes_decision']} |")
        add("")
        add("### Did the model survive its own predictions?")
        add("")
        adequacy = world["adequacy"]
        if adequacy.get("scored"):
            add("| condition | Vs [V] | predicted [V] | observed [V] | z | "
                "two-sided tail | level |")
            add("|---|---|---|---|---|---|---|")
            for s in sorted(
                adequacy["surprises"], key=lambda r: r["source_voltage_volt"]
            ):
                add(
                    f"| `{s['action_id']}` | {s['source_voltage_volt']:g} | "
                    f"{s['predictive_mean_volt']:.5f} ± "
                    f"{s['predictive_sd_volt']:.5f} | "
                    f"{s['y_observed_volt']:.5f} | "
                    f"{s['standardized_residual']:+.3f} | "
                    f"{s['tail_probability']:.3e} | {s['level']} |"
                )
            agg = adequacy["aggregate"]
            add("")
            add(
                f"Joint log score {agg['joint_log_score']:.3f} against a "
                f"simulated null of {agg['null_mean']:.3f} ± "
                f"{agg['null_sd']:.3f} → p_joint = {agg['p_joint']:.3e}; "
                f"{agg['n_extreme']} of {agg['n_conditions']} conditions "
                f"individually extreme."
            )
        add("")
        t = world["terminal"]
        add("### Result")
        add("")
        add(f"```")
        add(f"POSTERIOR_DECISION        = {t['posterior_decision']}")
        add(f"PARAMETER_EVPI            = {t['parameter_evpi']:.3e}")
        add(f"PARAMETER_EVSI (best)     = {t['parameter_evsi_max']:.3e}")
        add(f"CERTIFICATION_REQUIREMENT = {t['certification_requirement'].upper()}")
        add(f"MODEL_ADEQUACY            = {t['model_adequacy'].upper()}")
        add(f"STOP                      = {str(t['stop']).upper()}")
        add(f"SCIENTIFIC_CERTIFICATION  = {t['scientific_certification'].upper()}")
        add(f"reason                    = {t['reason']}")
        add(f"disposition               = {t['disposition'].upper()}")
        add(f"```")
        add("")
        add(f"The decision is reported as what it is: {t['posterior_decision_reading']}.")

    add("")
    add("## Why STOP was approved in one world and rejected in the other")
    add("")
    add(
        "Both runs pause economically with `no_action_worth_buying`. That is a "
        "statement about prices. What decides is the registered stopping "
        "criterion, evaluated into an assessment and handed to the **Arbiter**:"
    )
    add("")
    add("| world | requirement | adequacy | Arbiter | stop review |")
    add("|---|---|---|---|---|")
    for name, world in (("A", a), ("B", b)):
        add(
            f"| {name} | {world['certification_requirement_status']} | "
            f"{world['terminal']['model_adequacy']} | "
            f"`{world['stop_review']['arbiter_verdict']}` | "
            f"**{world['stop_review']['outcome']}** |"
        )
    add("")
    add(
        "`STOP_APPROVED` is structurally unmintable without a genuine Arbiter "
        "decision, and neither review is a certificate of scientific "
        "completeness — approving a stop means one declared criterion was "
        "found satisfied."
    )

    add("")
    add("## The five distinctions this demo exists to show")
    add("")
    for item in result["critical_distinctions"]:
        add(f"- **{item['distinction']}** — {item['shown_by']}.")

    add("")
    add("## CampaignRunner routing proof")
    add("")
    add(
        "The routing is done by the frozen `CampaignRunner`, not by any "
        "experiment-local adapter. Trace for each required probe:"
    )
    add("")
    add("| world | action | ACTION_SELECTED seq | reason | prediction_ref | "
        "EXECUTION_STARTED seq | admitted |")
    add("|---|---|---|---|---|---|---|")
    for name, world in (("A", a), ("B", b)):
        for row in world["selection_trace"]:
            if row["action_id"] not in REQUIRED_ACTION_IDS:
                continue
            add(
                f"| {name} | `{row['action_id']}` | "
                f"{row['action_selected_sequence']} | "
                f"`{row['execution_reason']}` | "
                f"`{row['prediction_ref'][:12]}…` | "
                f"{row['execution_started_sequence']} | {row['admitted']} |"
            )

    add("")
    add("## EVSI integrity")
    add("")
    inv = result["evsi_invariance"]
    add(
        f"The same campaign was run with and without the certification "
        f"requirement declared. Across {inv['shared_score_points']} shared "
        f"score points the `(parameter EVSI, cost, net value)` triples are "
        f"**identical: {inv['identical_on_shared_points']}**. Without the "
        f"requirement the runner executed "
        f"`{inv['without_requirement_executed']}` and the review returned "
        f"`{inv['without_requirement_stop_review']}`."
    )
    add("")
    add("| certification action | parameter EVSI | cost | net value | execution reason |")
    add("|---|---|---|---|---|")
    for row in inv["certification_action_scores"]:
        add(
            f"| `{row['action_id']}` | {row['parameter_evsi']:.3e} | "
            f"{_fmt(row['cost'])} | {row['net_value']:+.4f} | "
            f"`{row['execution_reason']}` |"
        )
    add("")
    add(inv["statement"] + ".")

    add("")
    add("## Belief and admission")
    add("")
    add("| world | executions | evidence created | admitted | rejected | "
        "belief size | chain verified |")
    add("|---|---|---|---|---|---|---|")
    for name, world in (("A", a), ("B", b)):
        c = world["belief"]
        add(
            f"| {name} | {c['executions_completed']} | "
            f"{c['evidence_records_created']} | {c['evidence_admitted']} | "
            f"{c['evidence_rejected']} | {c['belief_size']} | "
            f"{c['event_chain_verified']} |"
        )
    add("")
    add(
        "After each world, one deliberately faulty execution was pushed through "
        "the same admission chain:"
    )
    add("")
    add("| world | critic | Arbiter | admitted | belief before → after | "
        "posterior unchanged |")
    add("|---|---|---|---|---|---|")
    for name, world in (("A", a), ("B", b)):
        g = world["belief_integrity_probe"]
        add(
            f"| {name} | `{g['critic_verdict']}` | `{g['arbiter_verdict']}` | "
            f"{g['admitted']} | {g['belief_size_before']} → "
            f"{g['belief_size_after']} | {g['posterior_unchanged']} |"
        )

    add("")
    add("## Budget")
    add("")
    add("| world | total | reserved for validation | parameter spend | "
        "validation spend | remaining |")
    add("|---|---|---|---|---|---|")
    for name, world in (("A", a), ("B", b)):
        bud = world["budget"]
        add(
            f"| {name} | {_fmt(bud['total'])} | "
            f"{_fmt(bud['reserved_validation'])} | "
            f"{_fmt(bud['spent_parameter_learning'])} | "
            f"{_fmt(bud['spent_validation'])} | {_fmt(bud['remaining'])} |"
        )
    add("")
    add(
        "The frozen `BudgetLedger` does the accounting. Validation spend is "
        "drawn from the reservation because the probes are declared VALIDATE; "
        "no demo-only budget logic exists."
    )

    add("")
    add("## What remains unproven")
    add("")
    add(f"**prediction_ref.** {PREDICTION_REF_LIMITATION}")
    add("")
    add(
        "This is a computational benchmark on a synthetic divider. Nothing here "
        "is validated against any physical electrical system, no hardware is "
        "involved, and the misspecification in World B is a declared synthetic "
        "construct rather than a claim about how any real component behaves."
    )

    add("")
    add(f"Result digest: `{result['result_digest']}`")
    add("")
    add(f"**{result['verdict']}**")
    return "\n".join(lines)


def main() -> int:
    result = run_demo()
    root = Path(__file__).resolve().parent
    (root / "demo_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
                "scenario_hash": result["scenario_hash"],
                "base_commit": result["base_commit"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "demo_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "demo_report.md").write_text(report, encoding="utf-8")

    a = result["world_a_model_adequate"]
    b = result["world_b_model_inadequate"]
    print("Electrical V0.1 demo")
    print("=" * 72)
    print(f"base commit    {result['base_commit']}")
    print(f"config hash    {result['config_hash']}")
    print(f"result digest  {result['result_digest']}")
    print("")
    for name, world in (("A  model adequate  ", a), ("B  model inadequate", b)):
        t = world["terminal"]
        print(f"world {name}")
        print(f"    routed by runner    "
              f"{world['routed_by_runner_for_certification']}")
        print(f"    posterior           sd="
              f"{world['posterior_final']['sd_r2_ohm']:.4f} ohm  "
              f"EVPI={t['parameter_evpi']:.3e}  best EVSI="
              f"{t['parameter_evsi_max']:.3e}  decision "
              f"{t['posterior_decision']}")
        print(f"    requirement         {t['certification_requirement']}")
        print(f"    model adequacy      {t['model_adequacy']}")
        print(f"    stop                {t['stop']}")
        print(f"    certification       {t['scientific_certification']} "
              f"({t['reason']})")
        print("")
    failed = [k for k, v in result["checks"].items() if not v]
    if failed:
        print(f"FAILED CHECKS: {failed}")
    print(result["verdict"])
    print(f"artifacts written to {root}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
