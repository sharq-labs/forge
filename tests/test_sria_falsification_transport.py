"""SRIA falsification phase â€” transport-aware stopping.

Runs under pytest, and standalone via
``python -m tests.test_sria_falsification_transport``.

The claim under test, and the only one permitted:

    Under a deliberately misspecified synthetic problem, low model-based EVSI
    can incorrectly support stopping outside the empirically justified support
    region. A separate transport/support requirement prevents scientific
    certification of that stop.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np

from experiments.falsification import DECISION_PATH_MODULES
from experiments.falsification.benchmark import (
    SEED,
    control_scenario,
    informative_scenario,
    justified_transport_scenario,
    run_all,
    run_scenario,
    trap_scenario,
)
from experiments.falsification.decision import (
    DecisionIrrelevantAction,
    PointObservationAction,
    TerminalDecisionSpec,
    best_decision,
    evpi,
    evsi,
)
from experiments.falsification.inference import (
    Observation,
    ParameterGrid,
    posterior,
)
from experiments.falsification.support import (
    StopReasonCode,
    StopVerdict,
    SupportRule,
    SupportStatus,
    assess_support,
)
from experiments.falsification.truth import (
    ALTERNATIVE_OUT_OF_SUPPORT_TRUTH,
    DEFAULT_TRUTH,
    generate_observations,
)

TOL = 1e-9

#: The scenarios are deterministic, so running them once and sharing the result
#: is equivalent to re-running and keeps the suite fast.
_SCENARIO_CACHE: dict[tuple[str, int], dict] = {}


def cached_run(factory, truth=DEFAULT_TRUTH):
    key = (factory.__name__, id(truth))
    if key not in _SCENARIO_CACHE:
        _SCENARIO_CACHE[key] = run_scenario(factory(), truth)
    return _SCENARIO_CACHE[key]


def _observations(scenario, truth=DEFAULT_TRUTH):
    xs = np.array(scenario.observation_xs, dtype=float)
    ys = generate_observations(truth, xs, scenario.observation_sigma, SEED)
    return [
        Observation(x=float(x), y=float(y), sigma=scenario.observation_sigma)
        for x, y in zip(xs, ys)
    ]


# =====================================================================
# 1. The posterior reconstructs deterministically
# =====================================================================

def test_posterior_reconstructs_deterministically():
    grid = ParameterGrid.default()
    scenario = trap_scenario()
    observations = _observations(scenario)

    first = posterior(grid, observations, grid.uniform_prior())
    second = posterior(grid, observations, grid.uniform_prior())
    assert np.array_equal(first, second)

    # It is a function of (prior, observations, likelihood) only â€” assimilation
    # order cannot matter, because the log-likelihood is a sum.
    reordered = posterior(grid, list(reversed(observations)), grid.uniform_prior())
    assert np.allclose(first, reordered, atol=1e-15, rtol=0.0)

    # Sequential assimilation equals batch assimilation.
    running = grid.uniform_prior()
    for observation in observations:
        running = posterior(grid, [observation], running)
    assert np.allclose(first, running, atol=1e-12, rtol=0.0)

    assert abs(float(first.sum()) - 1.0) < 1e-12


# =====================================================================
# 2. The truth generator is unreachable from the decision path
# =====================================================================

def _module_imports(path: Path) -> tuple[set[str], set[str]]:
    """(absolute module names, sibling module names) imported by a file.

    Imported *symbols* are deliberately ignored â€” only the modules a file pulls
    in matter for reachability.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute: set[str] = set()
    siblings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if node.module:
                    siblings.add(node.module.split(".")[0])
                else:
                    # `from . import x` â€” the names are sibling modules.
                    siblings.update(alias.name for alias in node.names)
            elif node.module:
                absolute.add(node.module)
    return absolute, siblings


def test_truth_generator_is_inaccessible_from_the_decision_path():
    """Parsed, not trusted: no decision-path module may reach the truth.

    Checked transitively â€” a decision-path module may import only other
    decision-path modules, so no indirect route exists either.
    """
    import experiments.falsification as package

    root = Path(package.__file__).resolve().parent
    allowed = set(DECISION_PATH_MODULES)

    for name in DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert "truth" not in siblings, (name, siblings)
        assert not any(
            "truth" in candidate.split(".") for candidate in absolute
        ), (name, absolute)
        # Every sibling it reaches is itself a decision-path module, so the
        # closure of what it can see never contains the truth.
        assert siblings <= allowed, (name, siblings - allowed)

    # The harness, by contrast, is expected to see it â€” otherwise the test
    # would pass simply because nothing anywhere imports the truth.
    _abs, harness_siblings = _module_imports(root / "benchmark.py")
    assert "truth" in harness_siblings

    # And the loaded decision-path modules hold no attribute bound to it.
    for name in DECISION_PATH_MODULES:
        module = sys.modules[f"experiments.falsification.{name}"]
        for attribute, value in vars(module).items():
            assert "truth" not in attribute.lower(), (name, attribute)
            assert getattr(value, "__name__", "") != "HiddenTruth", (
                name, attribute
            )


# =====================================================================
# 3-5. EVSI is real, non-negative, and bounded by EVPI
# =====================================================================

def test_evsi_is_computed_from_predictive_outcomes():
    """A genuinely uncertain case must return a non-zero EVSI.

    If the implementation were a stub returning zero, this fails; if it were a
    hand-authored delta, it would not track the predictive.
    """
    scenario = informative_scenario()
    grid = ParameterGrid.default()
    weights = posterior(grid, _observations(scenario), grid.uniform_prior())
    action = scenario.actions[0]

    value = evsi(grid, weights, scenario.spec, action)
    assert value > 1e-3, value

    # Sharpen the measurement and the value must not fall: a more precise
    # instrument cannot be worth less than a noisier one.
    sharper = PointObservationAction(
        action_id=action.action_id, x=action.x, sigma=action.sigma / 4.0,
        cost=action.cost,
    )
    assert evsi(grid, weights, scenario.spec, sharper) >= value - TOL

    # Blunt it far enough and the value must fall towards zero.
    blunter = PointObservationAction(
        action_id=action.action_id, x=action.x, sigma=action.sigma * 200.0,
        cost=action.cost,
    )
    assert evsi(grid, weights, scenario.spec, blunter) < value


def test_evsi_is_non_negative_and_bounded_by_evpi():
    grid = ParameterGrid.default()
    for factory in (trap_scenario, control_scenario, informative_scenario):
        scenario = factory()
        weights = posterior(grid, _observations(scenario), grid.uniform_prior())
        ceiling = evpi(grid, weights, scenario.spec)
        assert ceiling >= -TOL, (scenario.name, ceiling)
        for action in scenario.actions:
            value = evsi(grid, weights, scenario.spec, action)
            assert value >= -TOL, (scenario.name, action.action_id, value)
            assert value <= ceiling + TOL, (
                scenario.name, action.action_id, value, ceiling
            )


# =====================================================================
# 6. A decision-irrelevant experiment is worth nothing
# =====================================================================

def test_decision_irrelevant_experiment_has_zero_evsi():
    """Identifiability, concretely: this observation cannot answer the question.

    Distinct from "we need more data" â€” no quantity of these observations would
    move the posterior, because the likelihood does not depend on theta.
    """
    scenario = informative_scenario()          # genuinely uncertain to start
    grid = ParameterGrid.default()
    weights = posterior(grid, _observations(scenario), grid.uniform_prior())

    informative = evsi(grid, weights, scenario.spec, scenario.actions[0])
    assert informative > 1e-3

    irrelevant = DecisionIrrelevantAction(
        action_id="null", sigma=0.5, cost=0.0
    )
    assert abs(evsi(grid, weights, scenario.spec, irrelevant)) < 1e-12


# =====================================================================
# 7-8. The trap, and the guard
# =====================================================================

def test_naive_policy_reproduces_the_extrapolation_trap():
    result = cached_run(trap_scenario)

    # The inference is not broken: it is confident, and confidently wrong.
    assert result["predictive_at_decision"]["p_above_threshold"] > 0.999
    assert result["terminal_decision"]["decision"] == "A"
    assert result["truth_known_to_grader"]["correct_decision"] == "B"

    # Every action looks worthless under the assumed model.
    assert all(entry["net"] <= 0.0 for entry in result["evsi"].values())

    naive = result["naive_policy"]
    assert naive["verdict"] == StopVerdict.STOP_ALLOWED.value
    assert naive["reason"] == StopReasonCode.NO_ACTION_WORTH_BUYING.value
    assert result["outcome"]["naive_certified_stop"] is True
    assert result["outcome"]["naive_decision_correct_if_stopped"] is False


def test_transport_aware_policy_refuses_certification():
    result = cached_run(trap_scenario)

    assert result["support"]["status"] == SupportStatus.UNSUPPORTED.value
    aware = result["transport_aware_policy"]
    assert aware["verdict"] == StopVerdict.STOP_NOT_CERTIFIABLE.value
    assert aware["reason"] == StopReasonCode.UNSUPPORTED_TRANSPORT.value
    assert result["outcome"]["aware_certified_stop"] is False
    # The refusal explains itself in terms of support, not of probability.
    assert "reach" in aware["detail"]


# =====================================================================
# 9. The in-domain control â€” the guard must not simply refuse everything
# =====================================================================

def test_in_domain_control_allows_legitimate_stopping():
    result = cached_run(control_scenario)

    assert result["support"]["status"] == SupportStatus.SUPPORTED.value
    assert result["naive_policy"]["verdict"] == StopVerdict.STOP_ALLOWED.value
    assert (
        result["transport_aware_policy"]["verdict"] == StopVerdict.STOP_ALLOWED.value
    )
    # ...and the stop it permits is the scientifically correct one.
    assert result["outcome"]["aware_certified_stop"] is True
    assert result["outcome"]["aware_decision_correct_if_stopped"] is True
    assert result["terminal_decision"]["decision"] == (
        result["truth_known_to_grader"]["correct_decision"]
    )


def test_a_declared_transport_justification_restores_certifiability():
    """The escape hatch is explicit, owned, and recorded â€” not inferred."""
    result = cached_run(justified_transport_scenario)
    assert result["support"]["status"] == SupportStatus.JUSTIFIED_TRANSPORT.value
    assert result["support"]["justification_id"] == "linear_regime_to_12"
    assert (
        result["transport_aware_policy"]["verdict"] == StopVerdict.STOP_ALLOWED.value
    )
    # And it is still the wrong scientific answer: the guard requires ownership
    # of an extrapolation claim, it does not make the claim true.
    assert result["outcome"]["aware_decision_correct_if_stopped"] is False


# =====================================================================
# 10. No oracle leakage
# =====================================================================

def test_changing_the_hidden_truth_out_of_support_changes_nothing():
    """SRIA must not see past its data.

    The alternative truth differs from the default only beyond x = 8.5, which
    is beyond every observation. Posterior, predictive, EVPI and every EVSI
    must therefore be bit-identical: nothing SRIA has been shown distinguishes
    the two worlds.
    """
    grid = ParameterGrid.default()
    scenario = trap_scenario()

    # The two truths genuinely differ where the decision is taken...
    assert DEFAULT_TRUTH.qoi(10.0) != ALTERNATIVE_OUT_OF_SUPPORT_TRUTH.qoi(10.0)
    # ...and agree exactly everywhere SRIA has looked.
    for x in scenario.observation_xs:
        assert DEFAULT_TRUTH.qoi(x) == ALTERNATIVE_OUT_OF_SUPPORT_TRUTH.qoi(x)

    default_run = cached_run(trap_scenario, DEFAULT_TRUTH)
    alternative_run = cached_run(trap_scenario, ALTERNATIVE_OUT_OF_SUPPORT_TRUTH)

    assert default_run["posterior"] == alternative_run["posterior"]
    assert default_run["predictive_at_decision"] == (
        alternative_run["predictive_at_decision"]
    )
    assert default_run["evpi"] == alternative_run["evpi"]
    assert default_run["evsi"] == alternative_run["evsi"]
    assert default_run["terminal_decision"] == alternative_run["terminal_decision"]
    assert default_run["support"] == alternative_run["support"]
    assert default_run["naive_policy"] == alternative_run["naive_policy"]

    # Only the grader's view changed.
    assert default_run["truth_known_to_grader"] != (
        alternative_run["truth_known_to_grader"]
    )


# =====================================================================
# Supporting properties
# =====================================================================

def test_support_rule_is_declared_and_inspectable():
    observations = [Observation(x=float(x), y=0.0, sigma=0.1) for x in range(9)]
    rule = SupportRule(margin=0.5)

    inside = assess_support(4.0, observations, rule)
    assert inside.status is SupportStatus.SUPPORTED
    assert inside.region == (-0.5, 8.5)

    outside = assess_support(10.0, observations, rule)
    assert outside.status is SupportStatus.UNSUPPORTED

    # The margin is a declared parameter, not a derived constant.
    widened = assess_support(10.0, observations, SupportRule(margin=2.5))
    assert widened.status is SupportStatus.SUPPORTED

    empty = assess_support(4.0, [], rule)
    assert empty.status is SupportStatus.NO_OBSERVATIONS
    assert empty.is_supported is False


def test_asymmetric_loss_actually_governs_the_decision():
    """A 0.909 indifference point, not 0.5 â€” the utility is doing work."""
    spec = TerminalDecisionSpec(
        decision_id="d", x_star=10.0, threshold=5.0
    )
    assert abs(spec.indifference_probability() - 10.0 / 11.0) < 1e-12

    grid = ParameterGrid.default()
    # A posterior that is 80% "above" still must not choose A.
    predicted = grid.predict(10.0)
    weights = np.where(predicted > 5.0, 1.0, 0.0)
    weights = weights / weights.sum() * 0.8
    below = np.where(predicted <= 5.0, 1.0, 0.0)
    weights = weights + below / below.sum() * 0.2
    decision, _ = best_decision(grid, weights, spec)
    assert decision == "B"


def test_benchmark_payload_is_machine_readable_and_complete():
    import json

    payload = run_all()
    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped["benchmark"] == "sria_falsification_transport_v1"
    assert len(round_tripped["scenarios"]) == 4

    required = {
        "prior", "observations", "posterior", "predictive_at_decision",
        "evpi", "evsi", "acquisition_costs", "terminal_decision",
        "truth_known_to_grader", "support", "naive_policy",
        "transport_aware_policy", "outcome",
    }
    for result in round_tripped["scenarios"]:
        assert required <= set(result), set(result)


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA falsification â€” transport-aware stopping")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"falsification: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"falsification: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

