"""S1.1 — transport guard calibration sweep.

Measures what the support guard buys and what it costs, across a preregistered
grid of terminal conditions, support margins, truth families and seeds.

Structure worth noting, because it is also the no-leakage argument: the
*scientific state* — posterior, predictive, EVPI, EVSI, decision, naive verdict
— is computed once per ``(seed, x*)`` pair and then reused across all six truth
families and all five margin policies. It literally cannot depend on the hidden
family, because the hidden family is not an input to the function that computes
it. The truth family enters only when the grader asks "was that decision
right?", and the margin enters only when the support rule is applied.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .decision import (
    DecisionIrrelevantAction,
    PointObservationAction,
    TerminalDecisionSpec,
    best_decision,
    evpi,
    evsi_report,
)
from .inference import (
    Observation,
    ParameterGrid,
    exceedance_probability,
    posterior,
    predictive_moments,
)
from .s11_config import (
    CHEAP_ACTION_X,
    CHEAP_COST,
    EXPENSIVE_COST,
    GRID_A_POINTS,
    GRID_A_RANGE,
    GRID_B_POINTS,
    GRID_B_RANGE,
    LOSS_A_ABOVE,
    LOSS_A_BELOW,
    LOSS_B_ABOVE,
    LOSS_B_BELOW,
    MARGIN_POLICIES,
    OBSERVATION_SIGMA,
    OBSERVATION_XS,
    SEEDS,
    X_STAR_GRID,
    config_hash,
    config_payload,
    threshold_for,
)
from .s11_truths import FAMILY_BY_ID, TRUTH_FAMILIES, observations_for_seed
from .support import (
    StopVerdict,
    SupportRule,
    SupportStatus,
    assess_support,
    naive_stop_policy,
    transport_aware_stop_policy,
)

OUTCOMES = (
    "GOOD_ALLOW",
    "GOOD_BLOCK",
    "FALSE_REFUSAL",
    "DANGEROUS_MISS",
    "NOT_APPLICABLE_CONTINUE",
)
CONFUSION_OUTCOMES = OUTCOMES[:4]


def _grid() -> ParameterGrid:
    return ParameterGrid(
        a_values=np.linspace(*GRID_A_RANGE, GRID_A_POINTS),
        b_values=np.linspace(*GRID_B_RANGE, GRID_B_POINTS),
    )


def _spec(x_star: float) -> TerminalDecisionSpec:
    return TerminalDecisionSpec(
        decision_id=f"qoi_at_{x_star:g}",
        x_star=float(x_star),
        threshold=threshold_for(x_star),
        loss_a_above=LOSS_A_ABOVE,
        loss_a_below=LOSS_A_BELOW,
        loss_b_above=LOSS_B_ABOVE,
        loss_b_below=LOSS_B_BELOW,
    )


@dataclass(frozen=True)
class ScientificState:
    """Everything the decision path concluded. No truth family involved."""

    seed: int
    x_star: float
    threshold: float
    decision: str
    p_above: float
    predictive_mean: float
    predictive_sd: float
    evpi: float
    max_evsi: float
    best_action_id: str
    best_action_cost: float
    best_net_value: float
    naive_verdict: str
    observations: tuple[Observation, ...]


def compute_state(grid: ParameterGrid, seed: int, x_star: float) -> ScientificState:
    xs = np.array(OBSERVATION_XS, dtype=float)
    ys = observations_for_seed(xs, OBSERVATION_SIGMA, seed)
    observations = tuple(
        Observation(x=float(x), y=float(y), sigma=OBSERVATION_SIGMA)
        for x, y in zip(xs, ys)
    )

    weights = posterior(grid, observations, grid.uniform_prior())
    spec = _spec(x_star)

    actions = (
        PointObservationAction(
            action_id="measure_at_x_star",
            x=float(x_star),
            sigma=OBSERVATION_SIGMA,
            cost=EXPENSIVE_COST,
        ),
        PointObservationAction(
            action_id="measure_in_support",
            x=CHEAP_ACTION_X,
            sigma=OBSERVATION_SIGMA,
            cost=CHEAP_COST,
        ),
        DecisionIrrelevantAction(
            action_id="measure_irrelevant",
            sigma=OBSERVATION_SIGMA,
            cost=CHEAP_COST,
        ),
    )
    table = evsi_report(grid, weights, spec, actions)
    decision, _ = best_decision(grid, weights, spec)
    naive = naive_stop_policy(table)
    mean, sd = predictive_moments(grid, weights, x_star)

    best_action_id = naive.best_action_id
    return ScientificState(
        seed=seed,
        x_star=float(x_star),
        threshold=spec.threshold,
        decision=decision,
        p_above=exceedance_probability(grid, weights, x_star, spec.threshold),
        predictive_mean=mean,
        predictive_sd=sd,
        evpi=evpi(grid, weights, spec),
        max_evsi=max(entry["evsi"] for entry in table.values()),
        best_action_id=best_action_id,
        best_action_cost=table[best_action_id]["cost"] if best_action_id else 0.0,
        best_net_value=naive.best_net_value,
        naive_verdict=naive.verdict.value,
        observations=observations,
    )


def classify(
    state: ScientificState,
    correct_decision: str,
    aware_verdict: StopVerdict,
) -> str:
    """Exactly one of the five declared outcomes.

    ``NOT_APPLICABLE_CONTINUE`` exists because the decision-theoretic condition
    can itself say "keep going", in which case neither policy sought
    certification and neither can be scored for it. Folding those cases into
    the confusion matrix would flatter whichever policy happened to be paired
    with them.
    """
    if state.naive_verdict != StopVerdict.STOP_ALLOWED.value:
        return "NOT_APPLICABLE_CONTINUE"
    decision_correct = state.decision == correct_decision
    allowed = aware_verdict is StopVerdict.STOP_ALLOWED
    if allowed:
        return "GOOD_ALLOW" if decision_correct else "DANGEROUS_MISS"
    return "FALSE_REFUSAL" if decision_correct else "GOOD_BLOCK"


@dataclass
class SweepResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    states: dict[tuple[int, float], ScientificState] = field(default_factory=dict)


def run_sweep(verbose: bool = False) -> SweepResult:
    grid = _grid()
    result = SweepResult()

    for x_star in X_STAR_GRID:
        for seed in SEEDS:
            state = compute_state(grid, seed, x_star)
            result.states[(seed, float(x_star))] = state

            for family in TRUTH_FAMILIES:
                truth_qoi = float(family.qoi(x_star))
                truth_above = truth_qoi > state.threshold
                correct = "A" if truth_above else "B"

                for policy_name, margin in MARGIN_POLICIES:
                    if margin is None:
                        support_status = SupportStatus.SUPPORTED
                        distance = float(x_star) - max(OBSERVATION_XS)
                        aware_verdict = (
                            StopVerdict.STOP_ALLOWED
                            if state.naive_verdict
                            == StopVerdict.STOP_ALLOWED.value
                            else StopVerdict.CONTINUE
                        )
                    else:
                        rule = SupportRule(margin=margin)
                        assessment = assess_support(
                            x_star, list(state.observations), rule
                        )
                        support_status = assessment.status
                        distance = float(x_star) - max(OBSERVATION_XS)
                        aware = transport_aware_stop_policy(
                            {
                                state.best_action_id: {
                                    "evsi": state.max_evsi,
                                    "cost": state.best_action_cost,
                                    "net": state.best_net_value,
                                }
                            },
                            assessment,
                        )
                        aware_verdict = aware.verdict

                    outcome = classify(state, correct, aware_verdict)
                    result.rows.append(
                        {
                            "seed": seed,
                            "x_star": float(x_star),
                            "threshold": state.threshold,
                            "truth_family": family.family_id,
                            "truth_class": family.truth_class,
                            "margin_policy": policy_name,
                            "margin": margin,
                            "sria_decision": state.decision,
                            "correct_decision": correct,
                            "truth_qoi": truth_qoi,
                            "p_above": state.p_above,
                            "predictive_mean": state.predictive_mean,
                            "predictive_sd": state.predictive_sd,
                            "evpi": state.evpi,
                            "max_evsi": state.max_evsi,
                            "best_action_id": state.best_action_id,
                            "best_action_cost": state.best_action_cost,
                            "best_net_value": state.best_net_value,
                            "naive_verdict": state.naive_verdict,
                            "aware_verdict": aware_verdict.value,
                            "support_status": support_status.value,
                            "distance_beyond_observations": distance,
                            "certification_correct": (
                                state.decision == correct
                                if aware_verdict is StopVerdict.STOP_ALLOWED
                                else None
                            ),
                            "outcome": outcome,
                        }
                    )
        if verbose:
            print(f"  x* = {x_star:g} done ({len(result.rows)} rows)")
    return result


# =====================================================================
# Metrics
# =====================================================================

def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Six lines, no dependency."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator == 0:
        return {
            "numerator": numerator,
            "denominator": 0,
            "rate": None,
            "ci95": None,
        }
    low, high = wilson_interval(numerator, denominator)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator,
        "ci95": [low, high],
    }


def confusion(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {outcome: 0 for outcome in OUTCOMES}
    for row in rows:
        counts[row["outcome"]] += 1
    return counts


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = confusion(rows)
    wrong_pool = counts["DANGEROUS_MISS"] + counts["GOOD_BLOCK"]
    right_pool = counts["FALSE_REFUSAL"] + counts["GOOD_ALLOW"]
    classified = sum(counts[o] for o in CONFUSION_OUTCOMES)
    return {
        "counts": counts,
        "classified_cases": classified,
        "dangerous_miss_rate": _rate(counts["DANGEROUS_MISS"], wrong_pool),
        "good_block_rate": _rate(counts["GOOD_BLOCK"], wrong_pool),
        "false_refusal_rate": _rate(counts["FALSE_REFUSAL"], right_pool),
        "good_allow_rate": _rate(counts["GOOD_ALLOW"], right_pool),
        "naive_wrong_stop_rate": _rate(wrong_pool, classified),
    }


def _filtered(rows, **conditions):
    return [
        row
        for row in rows
        if all(row[key] == value for key, value in conditions.items())
    ]


def replication_degeneracy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Do the seeds carry independent information about the outcome?

    Measured rather than assumed. If every seed in a ``(x*, margin, family)``
    cell produces the same outcome, the replications are degenerate: the point
    estimates are unaffected (each cell contributes the same proportion) but
    any interval computed on the row count is far too narrow, because it treats
    50 copies of one observation as 50 observations.
    """
    cells: dict[tuple[Any, ...], set[str]] = {}
    for row in rows:
        key = (row["x_star"], row["margin_policy"], row["truth_family"])
        cells.setdefault(key, set()).add(row["outcome"])
    varying = {k: sorted(v) for k, v in cells.items() if len(v) > 1}
    return {
        "cells": len(cells),
        "cells_with_varying_outcome": len(varying),
        "examples": [
            {"cell": list(k), "outcomes": v} for k, v in list(varying.items())[:5]
        ],
        "seeds_are_degenerate": len(varying) == 0,
        "note": (
            "Each cell is one (x*, margin, truth family) combination replicated "
            "over the 50 preregistered seeds. If no cell varies, the effective "
            "independent sample size is the number of cells, not the number of "
            "rows, and the row-based confidence intervals must not be quoted."
        ),
    }


def _cell_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Metrics on deduplicated cells — one vote per (x*, family)."""
    seen: dict[tuple[Any, ...], str] = {}
    for row in rows:
        key = (row["x_star"], row["truth_family"])
        seen[key] = row["outcome"]
    counts = {outcome: 0 for outcome in OUTCOMES}
    for outcome in seen.values():
        counts[outcome] += 1
    wrong_pool = counts["DANGEROUS_MISS"] + counts["GOOD_BLOCK"]
    right_pool = counts["FALSE_REFUSAL"] + counts["GOOD_ALLOW"]
    classified = sum(counts[o] for o in CONFUSION_OUTCOMES)
    return {
        "counts": counts,
        "classified_cells": classified,
        "dangerous_miss_rate": _rate(counts["DANGEROUS_MISS"], wrong_pool),
        "false_refusal_rate": _rate(counts["FALSE_REFUSAL"], right_pool),
        "naive_wrong_stop_rate": _rate(wrong_pool, classified),
    }


def declared_transport_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Labelled separately, and excluded from the primary metrics.

    A declared transport justification covering the whole extrapolation range
    makes every terminal condition "supported", so certification behaves
    exactly like the no-guard policy. Presence of a justification is therefore
    not evidence of its correctness — the mechanism buys attribution for an
    extrapolation claim, not truth.
    """
    no_guard = _cell_metrics(_filtered(rows, margin_policy="no_guard"))
    strict = _cell_metrics(_filtered(rows, margin_policy="strict"))
    return {
        "premise": (
            "A TransportJustification covering [8, 12] would mark every x* in "
            "this sweep as JUSTIFIED_TRANSPORT, which the transport-aware "
            "policy treats as supported."
        ),
        "consequence": (
            "Certification outcomes become identical to the no_guard policy."
        ),
        "no_guard_cells": no_guard["counts"],
        "strict_cells_for_contrast": strict["counts"],
        "dangerous_miss_rate_with_blanket_justification": (
            no_guard["dangerous_miss_rate"]
        ),
        "interpretation": (
            "presence of a declared justification != correctness of that "
            "justification; this is an attribution mechanism, not a safety "
            "mechanism, and it is excluded from the guard-calibration metrics"
        ),
    }


def summarize(result: SweepResult) -> dict[str, Any]:
    rows = result.rows
    by_margin = {
        name: metrics(_filtered(rows, margin_policy=name))
        for name, _ in MARGIN_POLICIES
    }
    by_margin_and_distance = {
        name: {
            f"{x:g}": metrics(_filtered(rows, margin_policy=name, x_star=float(x)))
            for x in X_STAR_GRID
        }
        for name, _ in MARGIN_POLICIES
    }
    by_margin_and_class = {
        name: {
            truth_class: metrics(
                _filtered(rows, margin_policy=name, truth_class=truth_class)
            )
            for truth_class in ("BENIGN", "REGIME_CHANGE")
        }
        for name, _ in MARGIN_POLICIES
    }
    tradeoff = []
    for name, margin in MARGIN_POLICIES:
        entry = by_margin[name]
        tradeoff.append(
            {
                "margin_policy": name,
                "margin": margin,
                "false_refusal_rate": entry["false_refusal_rate"]["rate"],
                "dangerous_miss_rate": entry["dangerous_miss_rate"]["rate"],
                "false_refusal_counts": [
                    entry["false_refusal_rate"]["numerator"],
                    entry["false_refusal_rate"]["denominator"],
                ],
                "dangerous_miss_counts": [
                    entry["dangerous_miss_rate"]["numerator"],
                    entry["dangerous_miss_rate"]["denominator"],
                ],
            }
        )

    in_domain = [row for row in rows if row["x_star"] <= 8.0]
    out_domain = [row for row in rows if row["x_star"] > 8.0]

    return {
        "experiment": "S1.1",
        "config_hash": config_hash(),
        "total_rows": len(rows),
        "replication_degeneracy": replication_degeneracy(rows),
        "by_margin_effective_cells": {
            name: _cell_metrics(_filtered(rows, margin_policy=name))
            for name, _ in MARGIN_POLICIES
        },
        "declared_transport_limitation": declared_transport_analysis(rows),
        "by_margin": by_margin,
        "by_margin_and_distance": by_margin_and_distance,
        "by_margin_and_truth_class": by_margin_and_class,
        "tradeoff": tradeoff,
        "in_domain_negative_control": {
            name: metrics(_filtered(in_domain, margin_policy=name))
            for name, _ in MARGIN_POLICIES
        },
        "out_of_domain_adversarial": {
            name: metrics(
                [
                    row
                    for row in out_domain
                    if row["margin_policy"] == name
                    and row["truth_class"] == "REGIME_CHANGE"
                ]
            )
            for name, _ in MARGIN_POLICIES
        },
    }


# =====================================================================
# Artifacts
# =====================================================================

def _here() -> Path:
    return Path(__file__).resolve().parent


def write_artifacts(result: SweepResult, summary: dict[str, Any]) -> dict[str, Path]:
    root = _here()
    paths = {
        "config": root / "s11_config_frozen.json",
        "full_csv": root / "s11_results_full.csv",
        "summary": root / "s11_summary.json",
        "report": root / "s11_report.md",
    }

    config = config_payload()
    config["config_hash"] = config_hash()
    paths["config"].write_text(
        json.dumps(config, indent=2, sort_keys=True), encoding="utf-8"
    )

    if result.rows:
        with paths["full_csv"].open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(result.rows[0]))
            writer.writeheader()
            writer.writerows(result.rows)

    paths["summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    paths["report"].write_text(render_markdown(summary), encoding="utf-8")
    return paths


def _pct(entry: dict[str, Any]) -> str:
    if entry["rate"] is None:
        return "n/a (0 cases)"
    low, high = entry["ci95"]
    return (
        f"{entry['numerator']}/{entry['denominator']} = "
        f"{entry['rate'] * 100:.1f}% [{low * 100:.1f}, {high * 100:.1f}]"
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# S1.1 — Transport guard calibration")
    add("")
    add(f"Config hash: `{summary['config_hash']}`")
    add(f"Scored rows: {summary['total_rows']}")
    add("")
    add("## Confusion counts by margin")
    add("")
    add("| margin policy | GOOD_ALLOW | GOOD_BLOCK | FALSE_REFUSAL | DANGEROUS_MISS | CONTINUE |")
    add("|---|---|---|---|---|---|")
    for name, _ in MARGIN_POLICIES:
        c = summary["by_margin"][name]["counts"]
        add(
            f"| {name} | {c['GOOD_ALLOW']} | {c['GOOD_BLOCK']} | "
            f"{c['FALSE_REFUSAL']} | {c['DANGEROUS_MISS']} | "
            f"{c['NOT_APPLICABLE_CONTINUE']} |"
        )
    add("")
    add("## Rates with explicit denominators")
    add("")
    add("| margin policy | dangerous miss rate | false refusal rate | naive wrong-stop rate |")
    add("|---|---|---|---|")
    for name, _ in MARGIN_POLICIES:
        m = summary["by_margin"][name]
        add(
            f"| {name} | {_pct(m['dangerous_miss_rate'])} | "
            f"{_pct(m['false_refusal_rate'])} | "
            f"{_pct(m['naive_wrong_stop_rate'])} |"
        )
    add("")
    add("Denominators: dangerous-miss rate is over cases where certification "
        "would be scientifically wrong; false-refusal rate is over cases where "
        "certification would be correct.")
    add("")
    degeneracy = summary["replication_degeneracy"]
    add("### Replication degeneracy — read before quoting the intervals above")
    add("")
    add(
        f"Cells (x* x margin x truth family): {degeneracy['cells']}. "
        f"Cells whose outcome varies across the 50 seeds: "
        f"**{degeneracy['cells_with_varying_outcome']}**."
    )
    add("")
    if degeneracy["seeds_are_degenerate"]:
        add(
            "The replications are **degenerate**: the observation noise never "
            "flips a decision, so all 50 seeds in a cell agree. Point estimates "
            "are unaffected, but the row-based intervals above are far too "
            "narrow and must not be quoted. The honest denominators are the "
            "cell counts below."
        )
        add("")
        add("| margin policy | dangerous miss rate (cells) | false refusal rate (cells) |")
        add("|---|---|---|")
        for name, _ in MARGIN_POLICIES:
            m = summary["by_margin_effective_cells"][name]
            add(
                f"| {name} | {_pct(m['dangerous_miss_rate'])} | "
                f"{_pct(m['false_refusal_rate'])} |"
            )
        add("")
    add("## Trade-off frontier")
    add("")
    add("| margin policy | margin | false refusal rate | dangerous miss rate |")
    add("|---|---|---|---|")
    for entry in summary["tradeoff"]:
        fr = entry["false_refusal_rate"]
        dm = entry["dangerous_miss_rate"]
        add(
            f"| {entry['margin_policy']} | {entry['margin']} | "
            f"{'n/a' if fr is None else f'{fr * 100:.1f}%'} | "
            f"{'n/a' if dm is None else f'{dm * 100:.1f}%'} |"
        )
    add("")
    add("## By truth class")
    add("")
    add("| margin policy | class | GOOD_ALLOW | GOOD_BLOCK | FALSE_REFUSAL | DANGEROUS_MISS |")
    add("|---|---|---|---|---|---|")
    for name, _ in MARGIN_POLICIES:
        for truth_class in ("BENIGN", "REGIME_CHANGE"):
            c = summary["by_margin_and_truth_class"][name][truth_class]["counts"]
            add(
                f"| {name} | {truth_class} | {c['GOOD_ALLOW']} | "
                f"{c['GOOD_BLOCK']} | {c['FALSE_REFUSAL']} | "
                f"{c['DANGEROUS_MISS']} |"
            )
    add("")
    return "\n".join(lines)


def main() -> int:
    print(f"S1.1 transport guard calibration — config {config_hash()[:16]}")
    result = run_sweep(verbose=True)
    summary = summarize(result)
    paths = write_artifacts(result, summary)
    print(render_markdown(summary))
    for name, path in paths.items():
        print(f"{name:>10}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
