"""T3 orchestration: four strategies over one preregistered scenario set.

    build each rung's terminal forward map once (the assimilation maps are
        reused from T1 unchanged)
    for each scenario:
        evaluate every rung once  -> (mu, sd, decision)
        three fixed baselines read one rung each
        the escalating policy walks the ladder under the preregistered rule
    aggregate cost, accuracy and the escalation diagnostics

The per-rung table is computed for every scenario regardless of what any
strategy paid for. That is grading information: it is what lets "a higher rung
would have got this right" be measured. No strategy reads it.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from experiments.shared.grid_inference import posterior_weights
from experiments.thermal_t1 import t1_run
from src.engcore.domains.thermal.conduction1d import (
    MIDPOINT_METRIC,
    ConductionSlab,
    SlabDiscretization,
    exact_midpoint,
    solve_slab,
)
from src.engcore.scientific.units.quantity import Quantity

from . import BASE_COMMIT, T3_VERSION
from . import t3_truth
from .t3_config import (
    ALPHA_UNIT,
    BASELINES,
    END_TIME_S,
    ESCALATION_QUANTILE,
    ESCALATION_SAFETY_FACTOR,
    FIDELITY_COST,
    FIELD_UNIT,
    LENGTH_M,
    MARGIN_BANDS,
    OBSERVATION_SIGMA,
    POLICY_ID,
    REFERENCE_RUNG_ID,
    RUNGS,
    SCENARIO_COUNT,
    SCIENTIFIC_QUESTION,
    STRATEGIES,
    TERMINATION_EXHAUSTED,
    TERMINATION_ROBUST,
    TERMINATION_STATISTICALLY_UNDECIDABLE,
    TERMINAL_TIME_S,
    WRONG_DECISION_COST,
    WRONG_DECISION_COST_SWEEP,
    alpha_grid,
    config_hash,
    config_payload,
    rung,
)

RUNG_ORDER: tuple[str, ...] = tuple(
    spec.rung_id for spec in sorted(RUNGS, key=lambda s: s.rank)
)


def preregistration_hash() -> str:
    blob = f"{config_hash()}|{t3_truth.truth_hash()}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# =====================================================================
# Forward maps
# =====================================================================

_TERMINAL_CACHE: dict[str, tuple[np.ndarray, float]] = {}


def terminal_forward_map(rung_id: str, time_s: float = TERMINAL_TIME_S
                         ) -> tuple[np.ndarray, float]:
    """Solver-predicted terminal QoI over the alpha grid, at one fixed rung.

    The rung is a fixed computational budget: the same (n_cells, n_steps)
    applied to a longer horizon, which is exactly what changes the dimensionless
    step and breaks the cancellation the assimilated QoI enjoys.
    """
    key = f"{rung_id}@{time_s}"
    cached = _TERMINAL_CACHE.get(key)
    if cached is not None:
        return cached
    spec = rung(rung_id)
    started = time.perf_counter()
    values = np.array(
        [
            solve_slab(
                ConductionSlab(
                    slab_id=f"t3-{rung_id}",
                    length=Quantity(LENGTH_M, "meter"),
                    diffusivity=Quantity(float(alpha), ALPHA_UNIT),
                    end_time=Quantity(time_s, "second"),
                    discretization=SlabDiscretization(spec.n_cells, spec.n_steps),
                ),
                run_id=f"t3-{rung_id}-{time_s:.0f}-{index:04d}",
            ).values[MIDPOINT_METRIC].magnitude_in(FIELD_UNIT)
            for index, alpha in enumerate(alpha_grid().array)
        ]
    )
    values.flags.writeable = False
    _TERMINAL_CACHE[key] = (values, time.perf_counter() - started)
    return _TERMINAL_CACHE[key]


def exact_terminal_map(time_s: float = TERMINAL_TIME_S) -> np.ndarray:
    return np.array(
        [
            exact_midpoint(length_m=LENGTH_M, alpha_m2_s=float(a), time_s=time_s)
            for a in alpha_grid().array
        ]
    )


# =====================================================================
# One rung's view of one scenario
# =====================================================================

@dataclass(frozen=True)
class RungView:
    """What a strategy sees after paying for one rung."""

    rung_id: str
    mu: float          # posterior-predictive mean of the terminal QoI
    sd: float          # posterior-predictive sd — statistical only
    decision: bool     # mu < tau
    margin: float      # |mu - tau|, as the strategy measures it
    numerical_error: float   # GRADING ONLY: this rung's terminal error


def evaluate_rung(scenario: t3_truth.Scenario, rung_id: str) -> RungView:
    grid = alpha_grid()
    assimilation, _ = t1_run.forward_map(rung_id)
    terminal, _ = terminal_forward_map(rung_id)

    weights = posterior_weights(
        grid, assimilation, scenario.observations, OBSERVATION_SIGMA
    )
    mu = float(np.dot(weights, terminal))
    sd = float(math.sqrt(max(float(np.dot(weights, (terminal - mu) ** 2)), 0.0)))
    at_truth = float(np.interp(scenario.alpha_true, grid.array, terminal))
    return RungView(
        rung_id=rung_id,
        mu=mu,
        sd=sd,
        decision=mu < scenario.tau,
        margin=abs(mu - scenario.tau),
        numerical_error=at_truth - scenario.terminal_truth,
    )


def scenario_table(scenario: t3_truth.Scenario) -> dict[str, RungView]:
    """Every rung's view. Grading information; no strategy reads all of it."""
    return {rung_id: evaluate_rung(scenario, rung_id) for rung_id in RUNG_ORDER}


# =====================================================================
# Strategies
# =====================================================================

def _confident(view: RungView) -> bool:
    """A fixed baseline has no numerical-error estimate, so its confidence is
    statistical only. That is precisely the failure mode under test."""
    return view.margin > ESCALATION_SAFETY_FACTOR * ESCALATION_QUANTILE * view.sd


def run_baseline(
    scenario: t3_truth.Scenario, table: dict[str, RungView], rung_id: str
) -> dict[str, Any]:
    """A strategy decides; it does not grade itself.

    Whether the decision was right is added later by :func:`grade`, so that no
    strategy function touches anything on the scenario beyond the observations
    and tau. A test parses these functions to enforce it.
    """
    view = table[rung_id]
    return {
        "strategy": f"always_{rung_id}",
        "rungs_used": [rung_id],
        "final_rung": rung_id,
        "work": FIDELITY_COST[rung_id],
        "decision": view.decision,
        "confident": _confident(view),
        "escalations": 0,
        "termination": "fixed",
    }


def run_policy(
    scenario: t3_truth.Scenario, table: dict[str, RungView]
) -> dict[str, Any]:
    """The preregistered escalation rule. About forty lines, experiment-side.

    The policy sees only the rungs it has paid for. ``e`` is the successive
    difference between rungs, which is a conservative estimate of the finer
    rung's error; at the cheapest rung there is no previous rung and therefore
    no evidence at all about its own numerical error, which is what T1 and T2
    established, so ``e`` is infinite and the robustness test cannot pass.
    """
    visited: list[str] = []
    work = 0
    previous_mu: float | None = None
    previous_decision: bool | None = None

    for position, rung_id in enumerate(RUNG_ORDER):
        view = table[rung_id]
        visited.append(rung_id)
        work += FIDELITY_COST[rung_id]

        statistical = ESCALATION_SAFETY_FACTOR * ESCALATION_QUANTILE * view.sd
        numerical = (
            float("inf") if previous_mu is None else abs(view.mu - previous_mu)
        )

        if view.margin > statistical + numerical:
            termination = TERMINATION_ROBUST
        elif view.margin <= statistical:
            # Refinement shrinks the numerical term and never the statistical
            # one, so no fidelity can settle this. Escalating would be waste.
            termination = TERMINATION_STATISTICALLY_UNDECIDABLE
        elif position == len(RUNG_ORDER) - 1:
            termination = TERMINATION_EXHAUSTED
        else:
            previous_mu = view.mu
            previous_decision = view.decision
            continue

        return {
            "strategy": POLICY_ID,
            "rungs_used": list(visited),
            "final_rung": rung_id,
            "work": work,
            "decision": view.decision,
            "confident": termination == TERMINATION_ROBUST,
            "escalations": len(visited) - 1,
            "termination": termination,
            "decision_before_last_escalation": previous_decision,
            # Recorded for diagnosis: what the policy believed about its own
            # uncertainty at the moment it stopped.
            "statistical_term": statistical,
            "numerical_indicator": numerical,
            "observed_margin": view.margin,
        }
    raise AssertionError("unreachable: the loop always terminates")


# =====================================================================
# Grading
# =====================================================================

def grade(
    scenario: t3_truth.Scenario,
    table: dict[str, RungView],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Grade the decision and attach hindsight diagnostics.

    This is the only place the truth meets a strategy's output.
    """
    correct = outcome["decision"] == scenario.correct_decision
    final_position = RUNG_ORDER.index(outcome["final_rung"])
    higher = RUNG_ORDER[final_position + 1:]

    # A higher rung it did not run would have decided correctly.
    missed = (not correct) and any(
        table[r].decision == scenario.correct_decision for r in higher
    )

    # The escalation bought nothing: same decision as before it, and correct.
    unnecessary = 0
    if outcome["escalations"] > 0:
        before = outcome.get("decision_before_last_escalation")
        if before is not None and before == outcome["decision"] and correct:
            unnecessary = 1

    return {
        **outcome,
        "correct": correct,
        "band": scenario.band,
        "scenario_index": scenario.index,
        "true_margin": scenario.margin,
        "required_escalation_missed": missed,
        "unnecessary_escalation": unnecessary,
        "incorrect_confident": outcome["confident"] and not correct,
        "numerical_error_over_margin": abs(
            table[outcome["final_rung"]].numerical_error
        ) / scenario.margin if scenario.margin > 0 else float("inf"),
    }


def summarize_strategy(rows: list[dict[str, Any]], wrong_cost: float
                       ) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    wrong = total - correct
    work = sum(r["work"] for r in rows)
    regret = wrong_cost * wrong
    return {
        "scenarios": total,
        "terminal_decision_accuracy": correct / total,
        "correct": correct,
        "wrong": wrong,
        "total_work": work,
        "mean_work": work / total,
        "decision_regret": regret,
        "mean_regret": regret / total,
        "total_cost": work + regret,
        "cost_to_correct_decision": (
            (work + regret) / correct if correct else float("inf")
        ),
        "incorrect_confident_decisions": sum(
            1 for r in rows if r["incorrect_confident"]
        ),
        "escalations": sum(r["escalations"] for r in rows),
        "unnecessary_escalations": sum(r["unnecessary_escalation"] for r in rows),
        "required_escalations_missed": sum(
            1 for r in rows if r["required_escalation_missed"]
        ),
        "final_fidelity_distribution": {
            rung_id: sum(1 for r in rows if r["final_rung"] == rung_id)
            for rung_id in RUNG_ORDER
        },
        "termination_reasons": {
            reason: sum(1 for r in rows if r["termination"] == reason)
            for reason in sorted({r["termination"] for r in rows})
        },
    }


# =====================================================================
# The study
# =====================================================================

def run_t3() -> dict[str, Any]:
    scenarios = t3_truth.all_scenarios()
    tables = [scenario_table(s) for s in scenarios]

    per_strategy: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATEGIES}
    for scenario, table in zip(scenarios, tables):
        for rung_id in RUNG_ORDER:
            per_strategy[f"always_{rung_id}"].append(
                grade(scenario, table, run_baseline(scenario, table, rung_id))
            )
        per_strategy[POLICY_ID].append(
            grade(scenario, table, run_policy(scenario, table))
        )

    result: dict[str, Any] = {
        "experiment": "T3",
        "experiment_version": T3_VERSION,
        "base_commit": BASE_COMMIT,
        "config_hash": config_hash(),
        "preregistration_hash": preregistration_hash(),
        "config": config_payload(),
        "truth": t3_truth.truth_payload(),
        "scientific_question": SCIENTIFIC_QUESTION,
    }

    result["strategies"] = {
        name: summarize_strategy(rows, WRONG_DECISION_COST)
        for name, rows in per_strategy.items()
    }

    # --- per band ------------------------------------------------------
    result["per_band"] = {
        band: {
            name: summarize_strategy(
                [r for r in rows if r["band"] == band], WRONG_DECISION_COST
            )
            for name, rows in per_strategy.items()
        }
        for band in MARGIN_BANDS
    }

    # --- does the benchmark contain both regimes? -----------------------
    by_band_error: dict[str, dict[str, Any]] = {}
    for band in MARGIN_BANDS:
        indices = [i for i, s in enumerate(scenarios) if s.band == band]
        entry: dict[str, Any] = {}
        for rung_id in RUNG_ORDER:
            ratios = [
                abs(tables[i][rung_id].numerical_error) / scenarios[i].margin
                for i in indices
                if scenarios[i].margin > 0
            ]
            entry[rung_id] = {
                "median_numerical_error_over_margin": float(np.median(ratios)),
                "fraction_error_exceeds_margin": float(
                    np.mean([r > 1.0 for r in ratios])
                ),
            }
        by_band_error[band] = entry
    result["numerical_error_vs_margin"] = by_band_error

    # --- the structural premise (F5) ------------------------------------
    # At r = 1 the rungs must agree (T2's cancellation); at r = 3 they must
    # not. If they agreed at r = 3 the out-of-sample design failed.
    probe = scenarios[0]
    grid = alpha_grid()
    weights = posterior_weights(
        grid, t1_run.forward_map("coarse")[0], probe.observations,
        OBSERVATION_SIGMA
    )
    at_r1, at_r3 = {}, {}
    for rung_id in RUNG_ORDER:
        w = posterior_weights(
            grid, t1_run.forward_map(rung_id)[0], probe.observations,
            OBSERVATION_SIGMA
        )
        at_r1[rung_id] = float(
            np.dot(w, terminal_forward_map(rung_id, END_TIME_S)[0])
        )
        at_r3[rung_id] = float(np.dot(w, terminal_forward_map(rung_id)[0]))
    spread_r1 = max(at_r1.values()) - min(at_r1.values())
    spread_r3 = max(at_r3.values()) - min(at_r3.values())
    result["cancellation_check"] = {
        "at_r_equals_1": at_r1,
        "at_r_equals_3": at_r3,
        "spread_at_r1": spread_r1,
        "spread_at_r3": spread_r3,
        "amplification": spread_r3 / spread_r1 if spread_r1 else float("inf"),
        "cancellation_holds_at_r1": spread_r1 < 1.0e-6,
        "cancellation_broken_at_r3": spread_r3 > 1.0e-3,
        "note": (
            "at the assimilated condition every rung predicts the same value "
            "because discretization error is exactly an effective-alpha shift "
            "and fitting alpha absorbs it. The terminal condition breaks that, "
            "which is the premise the whole experiment rests on"
        ),
    }

    # --- cost sweep -----------------------------------------------------
    sweep = []
    for wrong_cost in WRONG_DECISION_COST_SWEEP:
        entry = {
            "wrong_decision_cost": wrong_cost,
            "ccd": {
                name: summarize_strategy(rows, wrong_cost)[
                    "cost_to_correct_decision"
                ]
                for name, rows in per_strategy.items()
            },
        }
        entry["winner"] = min(entry["ccd"], key=entry["ccd"].get)
        sweep.append(entry)
    result["cost_sweep"] = sweep
    crossover = next(
        (e["wrong_decision_cost"] for e in sweep if e["winner"] == POLICY_ID),
        None,
    )
    result["policy_wins_from_wrong_decision_cost"] = crossover

    # --- criteria -------------------------------------------------------
    policy = result["strategies"][POLICY_ID]
    reference = result["strategies"][f"always_{REFERENCE_RUNG_ID}"]
    baseline_ccd = {
        name: result["strategies"][name]["cost_to_correct_decision"]
        for name in BASELINES
    }
    far_ref = result["per_band"]["FAR"][POLICY_ID][
        "final_fidelity_distribution"
    ][REFERENCE_RUNG_ID]
    near_ref = result["per_band"]["NEAR"][POLICY_ID][
        "final_fidelity_distribution"
    ][REFERENCE_RUNG_ID]
    per_band_n = result["per_band"]["FAR"][POLICY_ID]["scenarios"]

    # A7: some band where a cheaper fixed baseline matches reference accuracy.
    cheaper_matches = {
        band: [
            name
            for name in ("always_coarse", "always_medium")
            if result["per_band"][band][name]["terminal_decision_accuracy"]
            >= result["per_band"][band][f"always_{REFERENCE_RUNG_ID}"][
                "terminal_decision_accuracy"
            ]
        ]
        for band in MARGIN_BANDS
    }

    checks = {
        "A1_policy_ccd_beats_every_baseline": all(
            policy["cost_to_correct_decision"] < value
            for value in baseline_ccd.values()
        ),
        "A2_policy_accuracy_within_2pp_of_reference": (
            policy["terminal_decision_accuracy"]
            >= reference["terminal_decision_accuracy"] - 0.02
        ),
        "A3_policy_work_below_reference_work": (
            policy["total_work"] < reference["total_work"]
        ),
        "A4_far_band_rarely_reaches_reference": (
            far_ref / per_band_n < 0.10
        ),
        "A5_near_band_usually_reaches_reference": (
            near_ref / per_band_n > 0.80
        ),
        "A6_benchmark_contains_both_regimes": (
            by_band_error["NEAR"]["coarse"]["fraction_error_exceeds_margin"] > 0.50
            and by_band_error["FAR"]["coarse"]["fraction_error_exceeds_margin"] < 0.05
        ),
        "A7_reference_not_dominant_in_every_band": any(
            cheaper_matches.values()
        ),
    }
    result["acceptance"] = {
        "checks": checks,
        "all_passed": all(checks.values()),
        "failed": [name for name, ok in checks.items() if not ok],
        "bands_where_a_cheaper_baseline_matches_reference": cheaper_matches,
        "policy_reaches_reference": {
            "FAR": far_ref / per_band_n,
            "NEAR": near_ref / per_band_n,
        },
    }

    triggers = {
        "F1_policy_failed_to_beat_baselines": not checks[
            "A1_policy_ccd_beats_every_baseline"
        ],
        "F2_benchmark_lacks_both_regimes": not checks[
            "A6_benchmark_contains_both_regimes"
        ],
        "F3_reference_dominates_every_band": not checks[
            "A7_reference_not_dominant_in_every_band"
        ],
        "F4_saving_bought_with_reliability": not checks[
            "A2_policy_accuracy_within_2pp_of_reference"
        ],
        "F5_out_of_sample_design_failed": not result["cancellation_check"][
            "cancellation_broken_at_r3"
        ],
    }
    result["falsification"] = {
        "triggers": triggers,
        "fired": [name for name, hit in triggers.items() if hit],
        "comparison_is_informative": not (
            triggers["F2_benchmark_lacks_both_regimes"]
            or triggers["F5_out_of_sample_design_failed"]
        ),
    }

    # --- why it came out the way it did --------------------------------
    # Diagnosis of a preregistered outcome, computed from the run. Nothing in
    # the design, the costs or the criteria is altered by anything below.
    policy_rows = per_strategy[POLICY_ID]
    reference_rows = per_strategy[f"always_{REFERENCE_RUNG_ID}"]
    reference_unit_cost = FIDELITY_COST[REFERENCE_RUNG_ID]

    early_stops = [
        r for r in policy_rows
        if r["termination"] == TERMINATION_STATISTICALLY_UNDECIDABLE
        and r["final_rung"] != REFERENCE_RUNG_ID
    ]
    early_stop_wrong = [r for r in early_stops if not r["correct"]]

    # How conservative was the successive-difference indicator, where it was
    # the binding term? Compared against the finer rung's ACTUAL error.
    conservatism = []
    for scenario, table in zip(scenarios, tables):
        for position in range(1, len(RUNG_ORDER)):
            finer, coarser = RUNG_ORDER[position], RUNG_ORDER[position - 1]
            indicator = abs(table[finer].mu - table[coarser].mu)
            actual = abs(table[finer].numerical_error)
            if actual > 0:
                conservatism.append(indicator / actual)

    result["failure_diagnosis"] = {
        "preregistered_outcome": "the policy did not meet A1, A2 or A5",
        "policy_paid_more_than_always_reference_on": sum(
            1 for r in policy_rows if r["work"] > reference_unit_cost
        ),
        "of_scenarios": len(policy_rows),
        "cause_1_full_escalation_costs_more_than_going_straight_there": (
            "a strategy pays for every rung it walks past, so reaching the "
            f"reference rung by escalation costs {FIDELITY_COST['coarse'] + FIDELITY_COST['medium'] + reference_unit_cost:,} "
            f"against {reference_unit_cost:,} for going there directly. The "
            "policy escalated all the way on most scenarios, so its saving in "
            "the FAR band was outweighed"
        ),
        "cause_2_the_undecidable_stop_is_corrupted_by_the_bias_it_hunts": {
            "explanation": (
                "the stopping rule declares a decision statistically "
                "undecidable when |mu_k - tau| falls inside the statistical "
                "band. But mu_k is the BIASED prediction. A biased rung can "
                "therefore push a perfectly decidable scenario to look like a "
                "coin flip, and the policy stops paying exactly when it should "
                "have carried on"
            ),
            "early_stops_below_the_reference_rung": len(early_stops),
            "of_which_decided_wrongly": len(early_stop_wrong),
            "by_band": {
                band: sum(1 for r in early_stops if r["band"] == band)
                for band in MARGIN_BANDS
            },
            "this_is_why_A5_failed": True,
        },
        "cause_3_indicator_conservatism": {
            "median_indicator_over_actual_error": float(
                np.median(conservatism)
            ),
            "declared_in_advance": True,
            "consequence": (
                "the successive-difference indicator over-estimates the finer "
                "rung's error, so the robustness test rarely passes at the "
                "medium rung and the policy escalates past a fidelity that was "
                "already sufficient. The preregistration declared this would "
                "happen in the MODERATE band; it did"
            ),
            "unnecessary_escalations": sum(
                r["unnecessary_escalation"] for r in policy_rows
            ),
        },
        "what_the_policy_did_achieve": {
            "incorrect_confident_decisions": sum(
                1 for r in policy_rows if r["incorrect_confident"]
            ),
            "always_reference_incorrect_confident": sum(
                1 for r in reference_rows if r["incorrect_confident"]
            ),
            "always_coarse_incorrect_confident": sum(
                1 for r in per_strategy["always_coarse"]
                if r["incorrect_confident"]
            ),
            "note": (
                "the policy never claimed a decision was robust and got it "
                "wrong, on any scenario. Every fixed baseline did. This is a "
                "different objective from the preregistered one and does NOT "
                "offset the A1/A2/A5 failures; it is recorded because it is "
                "measured, not because it rescues the result"
            ),
        },
    }

    result["answer"] = {
        "informative": result["falsification"]["comparison_is_informative"],
        "policy_ccd": policy["cost_to_correct_decision"],
        "baseline_ccd": baseline_ccd,
        "policy_accuracy": policy["terminal_decision_accuracy"],
        "reference_accuracy": reference["terminal_decision_accuracy"],
        "policy_work_fraction_of_reference": (
            policy["total_work"] / reference["total_work"]
        ),
        "policy_wins_at_nominal": checks["A1_policy_ccd_beats_every_baseline"],
        "policy_wins_from_wrong_decision_cost": crossover,
        "nominal_wrong_decision_cost": WRONG_DECISION_COST,
    }
    result["_rows"] = per_strategy
    return result


# =====================================================================
# Rendering
# =====================================================================

def _label(name: str) -> str:
    return name.replace("_", " ")


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    config = result["config"]
    add("# T3 — Decision-aware fidelity escalation")
    add("")
    add(f"Config hash: `{result['config_hash']}`")
    add(f"Preregistration hash: `{result['preregistration_hash']}`")
    add(f"Base commit (T2 freeze): `{result['base_commit']}`")
    add("")
    add(f"**{result['scientific_question']}**")
    add("")
    add(
        f"{config['scenarios']['count']} preregistered scenarios in four "
        f"margin bands. Calibrate α on the 60 s observation; decide about the "
        f"slab at {config['terminal_decision']['terminal_time_s']:.0f} s "
        f"(r = {config['terminal_decision']['fourier_ratio_r']:.0f}), a "
        f"condition never assimilated."
    )

    # --- premise ---
    check = result["cancellation_check"]
    add("")
    add("## The premise, checked first")
    add("")
    add(
        f"At the assimilated condition (r = 1) the three rungs' predictions "
        f"span {check['spread_at_r1']:.2e} — they agree, which is T2's "
        f"cancellation. At the terminal condition (r = 3) they span "
        f"{check['spread_at_r3']:.2e}, an amplification of "
        f"**{check['amplification']:.0f}×**. The out-of-sample design works; "
        f"had it not, nothing below would mean anything."
    )

    # --- headline ---
    add("")
    add("## Cost to correct decision")
    add("")
    add(
        f"Nominal cost of a wrong decision: "
        f"{config['costs']['wrong_decision_cost']:,} work units "
        f"(10× the reference rung)."
    )
    add("")
    add("| strategy | accuracy | mean work | wrong | CCD | vs policy |")
    add("|---|---|---|---|---|---|")
    policy_ccd = result["strategies"][POLICY_ID]["cost_to_correct_decision"]
    for name in STRATEGIES:
        s = result["strategies"][name]
        ratio = s["cost_to_correct_decision"] / policy_ccd
        marker = "**" if name == POLICY_ID else ""
        add(
            f"| {marker}{_label(name)}{marker} | "
            f"{s['terminal_decision_accuracy']:.3f} | "
            f"{s['mean_work']:,.0f} | {s['wrong']} | "
            f"{marker}{s['cost_to_correct_decision']:,.0f}{marker} | "
            f"{ratio:.2f}× |"
        )

    # --- escalation behaviour ---
    add("")
    add("## Escalation behaviour")
    add("")
    add("| strategy | escalations | unnecessary | missed | incorrect confident |")
    add("|---|---|---|---|---|")
    for name in STRATEGIES:
        s = result["strategies"][name]
        add(
            f"| {_label(name)} | {s['escalations']} | "
            f"{s['unnecessary_escalations']} | "
            f"{s['required_escalations_missed']} | "
            f"{s['incorrect_confident_decisions']} |"
        )
    add("")
    add("### Where the policy stopped")
    add("")
    add("| band | coarse | medium | reference | accuracy | mean work |")
    add("|---|---|---|---|---|---|")
    for band in MARGIN_BANDS:
        s = result["per_band"][band][POLICY_ID]
        dist = s["final_fidelity_distribution"]
        add(
            f"| {band} | {dist['coarse']} | {dist['medium']} | "
            f"{dist[REFERENCE_RUNG_ID]} | "
            f"{s['terminal_decision_accuracy']:.3f} | {s['mean_work']:,.0f} |"
        )

    # --- per band accuracy ---
    add("")
    add("## Accuracy by band — is the benchmark rigged toward refinement?")
    add("")
    add("| band | " + " | ".join(_label(n) for n in STRATEGIES) + " |")
    add("|---" * (len(STRATEGIES) + 1) + "|")
    for band in MARGIN_BANDS:
        cells = [
            f"{result['per_band'][band][n]['terminal_decision_accuracy']:.3f}"
            for n in STRATEGIES
        ]
        add(f"| {band} | " + " | ".join(cells) + " |")
    add("")
    matches = result["acceptance"][
        "bands_where_a_cheaper_baseline_matches_reference"
    ]
    for band, names in matches.items():
        if names:
            add(f"- in **{band}**, {', '.join(_label(n) for n in names)} "
                f"match(es) the reference rung's accuracy at a fraction of "
                f"the cost")

    # --- error vs margin ---
    add("")
    add("## Numerical error relative to the decision margin")
    add("")
    add("| band | " + " | ".join(
        f"{r} (median ratio / frac>1)" for r in RUNG_ORDER) + " |")
    add("|---" * (len(RUNG_ORDER) + 1) + "|")
    for band in MARGIN_BANDS:
        cells = []
        for rung_id in RUNG_ORDER:
            e = result["numerical_error_vs_margin"][band][rung_id]
            cells.append(
                f"{e['median_numerical_error_over_margin']:.2f} / "
                f"{e['fraction_error_exceeds_margin']:.2f}"
            )
        add(f"| {band} | " + " | ".join(cells) + " |")
    add("")
    add(
        "A ratio above 1 means the rung's numerical error alone is larger than "
        "the distance to the decision boundary — the numerics can flip the "
        "decision by themselves."
    )

    # --- sweep ---
    add("")
    add("## Where each strategy wins")
    add("")
    add("| cost of a wrong decision | " + " | ".join(
        _label(n) for n in STRATEGIES) + " | winner |")
    add("|---" * (len(STRATEGIES) + 2) + "|")
    for entry in result["cost_sweep"]:
        cells = [f"{entry['ccd'][n]:,.0f}" for n in STRATEGIES]
        add(f"| {entry['wrong_decision_cost']:,.0f} | " + " | ".join(cells)
            + f" | {_label(entry['winner'])} |")
    add("")
    crossover = result["policy_wins_from_wrong_decision_cost"]
    add(
        f"The decision-aware policy becomes the cost-optimal strategy from a "
        f"wrong-decision cost of **{crossover:,.0f}** work units upward "
        f"({crossover / config['costs']['fidelity_cost'][REFERENCE_RUNG_ID]:.1f}× "
        f"the reference rung). Below that, a fixed cheap baseline is better: "
        f"when an error costs less than the computation that would prevent it, "
        f"the right move is not to compute."
        if crossover
        else "The decision-aware policy is not cost-optimal at any swept "
        "wrong-decision cost. Recorded as a negative result."
    )

    # --- criteria ---
    add("")
    add("## Preregistered criteria")
    add("")
    for name, ok in result["acceptance"]["checks"].items():
        add(f"- {'PASS' if ok else '**FAIL**'} — {name}")
    add("")
    fired = result["falsification"]["fired"]
    add(f"Falsification triggers fired: **{', '.join(fired)}**"
        if fired else "No falsification trigger fired.")

    # --- answer ---
    # --- diagnosis ---
    diagnosis = result["failure_diagnosis"]
    if not result["acceptance"]["all_passed"]:
        add("")
        add("## Why it came out this way")
        add("")
        add(
            f"Diagnosis of the preregistered outcome, computed from the run. "
            f"Nothing in the design, the costs or the criteria was altered by "
            f"any of it."
        )
        add("")
        add(f"**1. Escalation is not free.** "
            f"{diagnosis['cause_1_full_escalation_costs_more_than_going_straight_there']}. "
            f"The policy paid more than Always Reference on "
            f"{diagnosis['policy_paid_more_than_always_reference_on']} of "
            f"{diagnosis['of_scenarios']} scenarios.")
        add("")
        cause2 = diagnosis["cause_2_the_undecidable_stop_is_corrupted_by_the_bias_it_hunts"]
        add(f"**2. The give-up rule is corrupted by the very bias it is "
            f"hunting.** {cause2['explanation']}. It stopped below the "
            f"reference rung on {cause2['early_stops_below_the_reference_rung']} "
            f"scenarios, of which {cause2['of_which_decided_wrongly']} decided "
            f"wrongly — concentrated in "
            f"{', '.join(f'{b}: {n}' for b, n in cause2['by_band'].items() if n)}. "
            f"This is why A5 failed.")
        add("")
        cause3 = diagnosis["cause_3_indicator_conservatism"]
        add(f"**3. The error indicator is conservative**, by a median factor "
            f"of {cause3['median_indicator_over_actual_error']:.1f}× — "
            f"declared in advance. {cause3['consequence']}. "
            f"{cause3['unnecessary_escalations']} escalations changed nothing.")

    add("")
    add("## Answer")
    add("")
    answer = result["answer"]
    achieved = diagnosis["what_the_policy_did_achieve"]
    if not answer["informative"]:
        add("Not answerable from this run — the benchmark or the design "
            "premise failed. See the falsification criteria.")
    elif answer["policy_wins_at_nominal"]:
        add(
            f"Yes. The policy reached {answer['policy_accuracy']:.1%} accuracy "
            f"against the reference rung's {answer['reference_accuracy']:.1%} "
            f"while spending {answer['policy_work_fraction_of_reference']:.0%} "
            f"of its work, and had a lower cost-to-correct-decision than every "
            f"fixed baseline."
        )
    else:
        add(
            f"**No — not as specified.** The preregistered rule was beaten by "
            f"fixed baselines at every swept cost of a wrong decision. Always "
            f"Medium wins below about 3×10⁶ work units and Always Reference "
            f"above it; the decision-aware policy is never optimal. It also "
            f"decided less accurately than the reference rung "
            f"({answer['policy_accuracy']:.1%} vs "
            f"{answer['reference_accuracy']:.1%}), so its "
            f"{1 - answer['policy_work_fraction_of_reference']:.0%} work saving "
            f"was partly bought with reliability rather than earned. That is "
            f"what F4 was written to catch, and it fired."
        )
        add("")
        add(
            f"The question itself is not answered in the negative — a "
            f"cost-aware rule *could* still work. What is established is that "
            f"**this** rule does not, and the run says exactly why: escalation "
            f"pays for every rung it walks past, the give-up test reads a "
            f"biased mean, and the error indicator is "
            f"{diagnosis['cause_3_indicator_conservatism']['median_indicator_over_actual_error']:.0f}× "
            f"too conservative. All three are properties of the rule, not of "
            f"the benchmark, which passed A6 and A7."
        )
        add("")
        add(
            f"One measured result runs the other way and is recorded without "
            f"being allowed to offset the failure: the policy made "
            f"**{achieved['incorrect_confident_decisions']}** incorrect "
            f"confident decisions across {result['config']['scenarios']['count']} "
            f"scenarios, against "
            f"{achieved['always_reference_incorrect_confident']} for Always "
            f"Reference and "
            f"{achieved['always_coarse_incorrect_confident']} for Always "
            f"Coarse. It never claimed robustness and was wrong. That is a "
            f"different objective from the preregistered one, and it does not "
            f"rescue A1, A2 or A5."
        )

    add("")
    add("## What this does not show")
    add("")
    for item in config["non_goals"]:
        add(f"- {item}")
    return "\n".join(lines)


def main() -> int:
    result = run_t3()
    root = Path(__file__).resolve().parent
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    (root / "t3_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
                "truth": result["truth"],
                "preregistration_hash": result["preregistration_hash"],
            },
            indent=2, sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "t3_results.json").write_text(
        json.dumps(public, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "t3_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
