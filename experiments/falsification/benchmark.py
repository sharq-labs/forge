"""The falsification benchmark: predeclared scenarios, run and graded.

This is the harness and the grader. It is the only module that may touch
:mod:`truth`, and it does so in exactly two roles — generating the measurements
an instrument would have returned, and scoring the decision afterwards. The
values it hands to the decision path are plain numbers.

PREDECLARED PARAMETERS
----------------------
Fixed before scoring, and not adjusted afterwards:

    model space        f(x; a, b) = a + b*x, a in [0.5, 1.5], b in [0.40, 0.60]
                       201 x 201 uniform grid, uniform prior
    hidden truth       g(x) = 1.0 + 0.5x - 0.8 * max(0, x - 8.5)^2
    observation noise  sigma = 0.05, seed 20260807
    loss               L(A|below) = 10, L(B|above) = 1, else 0
                       -> A is chosen only when P(above) > 10/11 ~ 0.909

    TRAP        observations at x = 0..8; terminal condition x* = 10, tau = 5.0
                truth g(10) = 4.2  ->  BELOW  ->  correct decision is B
                model predicts ~6.0 ->  ABOVE  ->  naive decision is A
    CONTROL     observations at x = 0..8; terminal condition x* = 4, tau = 2.5
                truth g(4) = 3.0    ->  ABOVE  ->  correct decision is A
    INFORMATIVE two noisy observations only, so the posterior genuinely
                straddles the threshold and EVSI is measurably positive. This
                exists so the EVSI code cannot pass by always returning zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .decision import (
    DecisionIrrelevantAction,
    ObservationAction,
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
from .support import (
    SupportRule,
    TransportJustification,
    assess_support,
    naive_stop_policy,
    transport_aware_stop_policy,
)
from .truth import DEFAULT_TRUTH, HiddenTruth, generate_observations

OBSERVATION_SIGMA = 0.05
SEED = 20260807
EXPENSIVE_COST = 0.5
CHEAP_COST = 0.01


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    observation_xs: tuple[float, ...]
    observation_sigma: float
    spec: TerminalDecisionSpec
    actions: tuple[ObservationAction, ...]
    justifications: tuple[TransportJustification, ...] = ()
    support_rule: SupportRule = field(default_factory=SupportRule)


def trap_scenario() -> Scenario:
    return Scenario(
        name="TRAP_out_of_support",
        description=(
            "Cheap observations in [0, 8] pin the linear model tightly. The "
            "terminal decision is at x=10, outside the observed region, where "
            "the hidden truth changes regime."
        ),
        observation_xs=tuple(float(x) for x in range(9)),
        observation_sigma=OBSERVATION_SIGMA,
        spec=TerminalDecisionSpec(
            decision_id="qoi_at_10_above_5", x_star=10.0, threshold=5.0
        ),
        actions=(
            PointObservationAction(
                action_id="measure_at_10",
                x=10.0,
                sigma=OBSERVATION_SIGMA,
                cost=EXPENSIVE_COST,
            ),
            PointObservationAction(
                action_id="measure_at_8",
                x=8.0,
                sigma=OBSERVATION_SIGMA,
                cost=CHEAP_COST,
            ),
            DecisionIrrelevantAction(
                action_id="measure_irrelevant",
                sigma=OBSERVATION_SIGMA,
                cost=CHEAP_COST,
            ),
        ),
    )


def control_scenario() -> Scenario:
    return Scenario(
        name="CONTROL_in_support",
        description=(
            "Same evidence and same model, but the terminal decision is at "
            "x=4, inside the observed region. A legitimate stop must not be "
            "blocked merely because the support guard exists."
        ),
        observation_xs=tuple(float(x) for x in range(9)),
        observation_sigma=OBSERVATION_SIGMA,
        spec=TerminalDecisionSpec(
            decision_id="qoi_at_4_above_2p5", x_star=4.0, threshold=2.5
        ),
        actions=(
            PointObservationAction(
                action_id="measure_at_4",
                x=4.0,
                sigma=OBSERVATION_SIGMA,
                cost=EXPENSIVE_COST,
            ),
            DecisionIrrelevantAction(
                action_id="measure_irrelevant",
                sigma=OBSERVATION_SIGMA,
                cost=CHEAP_COST,
            ),
        ),
    )


def informative_scenario() -> Scenario:
    """Genuinely uncertain, so EVSI must be measurably positive."""
    return Scenario(
        name="INFORMATIVE_evsi_positive",
        description=(
            "Two noisy observations only. The posterior at x=4 straddles the "
            "threshold, so an additional measurement carries real value. This "
            "scenario exists to show the EVSI machinery returns non-zero "
            "numbers when the decision is actually uncertain."
        ),
        observation_xs=(0.0, 1.0),
        observation_sigma=0.5,
        spec=TerminalDecisionSpec(
            decision_id="qoi_at_4_above_3", x_star=4.0, threshold=3.0
        ),
        actions=(
            PointObservationAction(
                action_id="measure_at_4", x=4.0, sigma=0.5, cost=CHEAP_COST
            ),
            DecisionIrrelevantAction(
                action_id="measure_irrelevant", sigma=0.5, cost=CHEAP_COST
            ),
        ),
    )


def justified_transport_scenario() -> Scenario:
    """The trap, but with the extrapolation explicitly declared and owned."""
    base = trap_scenario()
    return Scenario(
        name="TRAP_with_declared_transport",
        description=(
            "Identical to the trap, except a transport justification covering "
            "x in [8, 12] has been declared. Certification becomes possible — "
            "and the claim is now attributable to a named owner."
        ),
        observation_xs=base.observation_xs,
        observation_sigma=base.observation_sigma,
        spec=base.spec,
        actions=base.actions,
        justifications=(
            TransportJustification(
                justification_id="linear_regime_to_12",
                lower=8.0,
                upper=12.0,
                rationale=(
                    "the governing mechanism is asserted to remain linear to "
                    "x=12 on theoretical grounds"
                ),
                owner="benchmark.declared_owner",
            ),
        ),
    )


def run_scenario(
    scenario: Scenario,
    truth: HiddenTruth = DEFAULT_TRUTH,
    grid: ParameterGrid | None = None,
) -> dict[str, Any]:
    """Run one scenario end to end and grade it against the hidden truth."""
    grid = grid or ParameterGrid.default()

    # --- grader side: what an instrument would have returned ---------------
    xs = np.array(scenario.observation_xs, dtype=float)
    ys = generate_observations(truth, xs, scenario.observation_sigma, SEED)
    observations = [
        Observation(x=float(x), y=float(y), sigma=scenario.observation_sigma)
        for x, y in zip(xs, ys)
    ]

    # --- decision path: plain numbers in, no access to the truth -----------
    prior = grid.uniform_prior()
    weights = posterior(grid, observations, prior)
    spec = scenario.spec

    decision, expected_value = best_decision(grid, weights, spec)
    p_above = exceedance_probability(grid, weights, spec.x_star, spec.threshold)
    pred_mean, pred_sd = predictive_moments(grid, weights, spec.x_star)
    information_value = evpi(grid, weights, spec)
    table = evsi_report(grid, weights, spec, scenario.actions)

    support = assess_support(
        spec.x_star,
        observations,
        scenario.support_rule,
        scenario.justifications,
    )
    naive = naive_stop_policy(table)
    aware = transport_aware_stop_policy(table, support)

    # --- grader side again: what was actually true -------------------------
    truth_qoi = float(truth.qoi(spec.x_star))
    truth_above = truth.is_above(spec.x_star, spec.threshold)
    correct_decision = "A" if truth_above else "B"

    naive_outcome_correct = (
        decision == correct_decision if naive.certifies_stop else None
    )
    aware_outcome_correct = (
        decision == correct_decision if aware.certifies_stop else None
    )

    return {
        "scenario": scenario.name,
        "description": scenario.description,
        "prior": {
            "grid_shape": list(grid.shape),
            "grid_points": grid.size,
            "kind": "uniform",
            "a_range": [float(grid.a_values[0]), float(grid.a_values[-1])],
            "b_range": [float(grid.b_values[0]), float(grid.b_values[-1])],
        },
        "observations": [
            {"x": o.x, "y": round(o.y, 9), "sigma": o.sigma} for o in observations
        ],
        "posterior": {
            "mean_a": float(np.dot(weights, grid.mesh()[0])),
            "mean_b": float(np.dot(weights, grid.mesh()[1])),
            "effective_support": int(np.count_nonzero(weights > 1e-12)),
        },
        "predictive_at_decision": {
            "x_star": spec.x_star,
            "mean": pred_mean,
            "sd": pred_sd,
            "p_above_threshold": p_above,
            "threshold": spec.threshold,
        },
        "evpi": information_value,
        "evsi": table,
        "acquisition_costs": {
            a.action_id: float(a.cost) for a in scenario.actions
        },
        "terminal_decision": {
            "decision": decision,
            "expected_utility": expected_value,
            "indifference_probability": spec.indifference_probability(),
        },
        "truth_known_to_grader": {
            "qoi_at_x_star": truth_qoi,
            "above_threshold": truth_above,
            "correct_decision": correct_decision,
        },
        "support": support.to_dict(),
        "naive_policy": naive.to_dict(),
        "transport_aware_policy": aware.to_dict(),
        "outcome": {
            "naive_certified_stop": naive.certifies_stop,
            "naive_decision_correct_if_stopped": naive_outcome_correct,
            "aware_certified_stop": aware.certifies_stop,
            "aware_decision_correct_if_stopped": aware_outcome_correct,
        },
    }


DEFAULT_SCENARIOS = (
    trap_scenario,
    control_scenario,
    informative_scenario,
    justified_transport_scenario,
)


def run_all(truth: HiddenTruth = DEFAULT_TRUTH) -> dict[str, Any]:
    results = [run_scenario(factory(), truth) for factory in DEFAULT_SCENARIOS]
    return {
        "benchmark": "sria_falsification_transport_v1",
        "base_commit": "793e8dbcafea0831ae3974c1a63c7593fc5c4a8b",
        "seed": SEED,
        "claim": (
            "Under a deliberately misspecified synthetic problem, low "
            "model-based EVSI can incorrectly support stopping outside the "
            "empirically justified support region. A separate "
            "transport/support requirement prevents scientific certification "
            "of that stop."
        ),
        "scenarios": results,
    }


def _fmt(value: float, places: int = 6) -> str:
    return f"{value:.{places}g}"


def render_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add("SRIA FALSIFICATION BENCHMARK — transport-aware stopping")
    add("=" * 78)
    add(f"base commit : {payload['base_commit']}")
    add(f"seed        : {payload['seed']}")

    for result in payload["scenarios"]:
        add("")
        add("-" * 78)
        add(f"SCENARIO: {result['scenario']}")
        add("-" * 78)
        prior = result["prior"]
        add(
            f"  1. prior           : {prior['kind']} over "
            f"{prior['grid_shape'][0]}x{prior['grid_shape'][1]} grid, "
            f"a in {prior['a_range']}, b in {prior['b_range']}"
        )
        obs = result["observations"]
        add(
            f"  2. observations    : n={len(obs)} at x="
            f"{[o['x'] for o in obs]}, sigma={obs[0]['sigma']}"
        )
        post = result["posterior"]
        add(
            f"  3. posterior       : E[a]={_fmt(post['mean_a'])}, "
            f"E[b]={_fmt(post['mean_b'])}, "
            f"support={post['effective_support']} grid points"
        )
        pred = result["predictive_at_decision"]
        add(
            f"  4. predictive @x*  : x*={_fmt(pred['x_star'])} "
            f"mean={_fmt(pred['mean'])} sd={_fmt(pred['sd'])} "
            f"P(>{_fmt(pred['threshold'])})={_fmt(pred['p_above_threshold'])}"
        )
        add(f"  5. EVPI            : {_fmt(result['evpi'])}")
        add("  6. EVSI per action :")
        for action_id, entry in sorted(result["evsi"].items()):
            add(
                f"        {action_id:<22} evsi={_fmt(entry['evsi']):>12} "
                f"cost={_fmt(entry['cost']):>8} net={_fmt(entry['net']):>12}"
            )
        add(f"  7. costs           : {result['acquisition_costs']}")
        term = result["terminal_decision"]
        add(
            f"  8. decision chosen : {term['decision']} "
            f"(E[u]={_fmt(term['expected_utility'])}, "
            f"indifference P={_fmt(term['indifference_probability'])})"
        )
        truth = result["truth_known_to_grader"]
        add(
            f"  9. truth (grader)  : QoI={_fmt(truth['qoi_at_x_star'])} "
            f"above={truth['above_threshold']} "
            f"correct={truth['correct_decision']}"
        )
        support = result["support"]
        add(
            f" 10. support status  : {support['status']} "
            f"region={support['region']} rule={support['rule_id']}"
        )
        naive = result["naive_policy"]
        aware = result["transport_aware_policy"]
        add(f" 11. naive policy    : {naive['verdict']} ({naive['reason']})")
        add(f" 12. transport-aware : {aware['verdict']} ({aware['reason']})")
        outcome = result["outcome"]
        add(
            f" 13. correct?        : naive_stop={outcome['naive_certified_stop']} "
            f"correct={outcome['naive_decision_correct_if_stopped']} | "
            f"aware_stop={outcome['aware_certified_stop']} "
            f"correct={outcome['aware_decision_correct_if_stopped']}"
        )
    add("")
    add("=" * 78)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    payload = run_all()
    print(render_report(payload))
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"machine-readable results: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
