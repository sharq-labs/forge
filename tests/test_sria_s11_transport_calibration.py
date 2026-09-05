"""S1.1 — transport guard calibration.

Runs under pytest, and standalone via
``python -m tests.test_sria_s11_transport_calibration``.

The claim under test, and the only one permitted:

    On a preregistered family of synthetic decision problems, a
    transport-support requirement reduced false certification under
    out-of-support model misspecification, with a measurable trade-off in false
    refusals as the support margin changed.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np

from experiments.falsification import DECISION_PATH_MODULES
from experiments.falsification.inference import (
    Observation,
    ParameterGrid,
    posterior,
)
from experiments.falsification.s11_config import (
    MARGIN_POLICIES,
    OBSERVATION_SIGMA,
    OBSERVATION_XS,
    SEEDS,
    X_STAR_GRID,
    config_hash,
    config_payload,
    scored_case_count,
    threshold_for,
)
from experiments.falsification.s11_sweep import (
    ScientificState,
    classify,
    compute_state,
    metrics,
    run_sweep,
    summarize,
    _grid,
)
from experiments.falsification.s11_truths import (
    FAMILY_BY_ID,
    TRUTH_FAMILIES,
    observations_for_seed,
)
from experiments.falsification.support import StopVerdict

#: The scored artifacts committed with this experiment. Aggregate assertions
#: read these rather than re-running the 111-second sweep, and
#: ``test_results_reproduce_exactly_under_the_frozen_configuration`` recomputes
#: a declared subset and compares it to them row by row. That is a stronger
#: traceability claim than recomputing everything and comparing to nothing: it
#: checks the committed record against fresh arithmetic.
_ARTIFACTS = None


def _artifact_root() -> Path:
    import experiments.falsification as package

    return Path(package.__file__).resolve().parent


def sweep():
    """(rows, summary) as scored and committed."""
    global _ARTIFACTS
    if _ARTIFACTS is None:
        import csv

        root = _artifact_root()
        with (root / "s11_results_full.csv").open(encoding="utf-8") as handle:
            rows = []
            for raw in csv.DictReader(handle):
                row = dict(raw)
                for key in (
                    "x_star", "threshold", "p_above", "predictive_mean",
                    "predictive_sd", "evpi", "max_evsi", "best_action_cost",
                    "best_net_value", "distance_beyond_observations",
                    "truth_qoi",
                ):
                    row[key] = float(row[key])
                row["seed"] = int(row["seed"])
                row["margin"] = float(row["margin"]) if row["margin"] else None
                rows.append(row)
        summary = json.loads(
            (root / "s11_summary.json").read_text(encoding="utf-8")
        )
        _ARTIFACTS = (type("R", (), {"rows": rows})(), summary)
    return _ARTIFACTS


# =====================================================================
# 1. The configuration is deterministic
# =====================================================================

def test_experiment_configuration_is_deterministic():
    first = config_hash()
    assert config_hash() == first
    assert len(first) == 64

    # The hash is over the content, so a changed value changes the hash.
    payload = config_payload()
    payload["x_star_grid"] = list(payload["x_star_grid"]) + [99.0]
    import hashlib

    mutated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert mutated != first

    assert scored_case_count() == (
        len(TRUTH_FAMILIES) * len(X_STAR_GRID) * len(SEEDS) * len(MARGIN_POLICIES)
    )
    assert scored_case_count() == 15000


# =====================================================================
# 2. The hidden truth remains inaccessible to the decision path
# =====================================================================

def _module_imports(path: Path) -> tuple[set[str], set[str]]:
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
                    siblings.update(alias.name for alias in node.names)
            elif node.module:
                absolute.add(node.module)
    return absolute, siblings


def test_hidden_truth_is_inaccessible_to_decision_modules():
    import experiments.falsification as package

    root = Path(package.__file__).resolve().parent
    forbidden = {"truth", "s11_truths"}

    for name in DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert not (siblings & forbidden), (name, siblings & forbidden)
        assert not any("truth" in c for c in absolute), (name, absolute)
        assert siblings <= set(DECISION_PATH_MODULES), (name, siblings)

    # The grader-only module must not be reachable from the decision path, but
    # the sweep harness is expected to import it — otherwise this test would
    # pass simply because nothing anywhere uses it.
    _abs, sweep_siblings = _module_imports(root / "s11_sweep.py")
    assert "s11_truths" in sweep_siblings


# =====================================================================
# 3. Same evidence -> same posterior/EVSI regardless of hidden truth family
# =====================================================================

def test_same_evidence_gives_same_state_regardless_of_truth_family():
    """Structural, not incidental.

    Every family agrees exactly on x <= 8, so the observations are a function
    of the seed alone. ``observations_for_seed`` does not even accept a family
    argument — there is no channel through which the hidden truth could reach
    the posterior.
    """
    xs = np.array(OBSERVATION_XS, dtype=float)
    for seed in (SEEDS[0], SEEDS[17], SEEDS[-1]):
        values = observations_for_seed(xs, OBSERVATION_SIGMA, seed)
        for family in TRUTH_FAMILIES:
            assert np.allclose(family.qoi(xs), FAMILY_BY_ID["linear_exact"].qoi(xs))
        assert np.array_equal(
            values, observations_for_seed(xs, OBSERVATION_SIGMA, seed)
        )

    # And the families genuinely differ where the decision is taken.
    assert FAMILY_BY_ID["regime_strong"].qoi(10.0) != (
        FAMILY_BY_ID["linear_exact"].qoi(10.0)
    )

    # The computed state carries no family information at all.
    state = compute_state(_grid(), SEEDS[0], 10.0)
    assert not any("truth" in field.lower() for field in vars(state))
    assert not any("family" in field.lower() for field in vars(state))


# =====================================================================
# 4. The classification logic distinguishes the four outcomes
# =====================================================================

def _state(decision: str, naive: StopVerdict) -> ScientificState:
    return ScientificState(
        seed=1, x_star=10.0, threshold=5.0, decision=decision, p_above=1.0,
        predictive_mean=6.0, predictive_sd=0.04, evpi=0.0, max_evsi=0.0,
        best_action_id="a", best_action_cost=0.5, best_net_value=-0.5,
        naive_verdict=naive.value, observations=(),
    )


def test_classification_logic_distinguishes_all_outcomes():
    certifying = _state("A", StopVerdict.STOP_ALLOWED)

    assert classify(certifying, "A", StopVerdict.STOP_ALLOWED) == "GOOD_ALLOW"
    assert classify(certifying, "B", StopVerdict.STOP_ALLOWED) == "DANGEROUS_MISS"
    assert (
        classify(certifying, "A", StopVerdict.STOP_NOT_CERTIFIABLE)
        == "FALSE_REFUSAL"
    )
    assert (
        classify(certifying, "B", StopVerdict.STOP_NOT_CERTIFIABLE) == "GOOD_BLOCK"
    )

    # A case where the economics itself said continue is not scored either way.
    continuing = _state("A", StopVerdict.CONTINUE)
    assert (
        classify(continuing, "B", StopVerdict.STOP_ALLOWED)
        == "NOT_APPLICABLE_CONTINUE"
    )


# =====================================================================
# 5-7. The three controls
# =====================================================================

def test_no_guard_policy_reproduces_the_s1_dangerous_stop():
    _result, summary = sweep()
    counts = summary["by_margin"]["no_guard"]["counts"]
    assert counts["DANGEROUS_MISS"] > 0
    assert counts["GOOD_BLOCK"] == 0
    assert counts["FALSE_REFUSAL"] == 0
    # Every scientifically wrong certification goes through.
    assert summary["by_margin"]["no_guard"]["dangerous_miss_rate"]["rate"] == 1.0


def test_strict_guard_blocks_the_canonical_s1_trap():
    """x* = 10 with a strong regime change is S1's trap, re-run here."""
    result, _summary = sweep()
    trap_rows = [
        row
        for row in result.rows
        if row["x_star"] == 10.0
        and row["truth_family"] == "regime_strong"
        and row["margin_policy"] in ("very_strict", "strict")
    ]
    assert trap_rows
    assert all(row["outcome"] == "GOOD_BLOCK" for row in trap_rows)
    assert all(row["correct_decision"] == "B" for row in trap_rows)
    assert all(row["sria_decision"] == "A" for row in trap_rows)


def test_in_domain_negative_control_is_not_systematically_refused():
    """The guard must not achieve safety by refusing legitimate stops."""
    _result, summary = sweep()
    for name, _margin in MARGIN_POLICIES:
        control = summary["in_domain_negative_control"][name]
        counts = control["counts"]
        assert counts["FALSE_REFUSAL"] == 0, (name, counts)
        assert counts["DANGEROUS_MISS"] == 0, (name, counts)
        assert counts["GOOD_ALLOW"] > 0, (name, counts)


# =====================================================================
# 8. The margin changes only support logic, never the science
# =====================================================================

def test_margin_changes_only_support_logic_not_posterior_or_evsi():
    result, _summary = sweep()
    by_key: dict[tuple, set] = {}
    for row in result.rows:
        key = (row["seed"], row["x_star"])
        by_key.setdefault(key, set()).add(
            (
                round(row["p_above"], 15),
                round(row["max_evsi"], 20),
                round(row["evpi"], 20),
                row["sria_decision"],
                row["naive_verdict"],
            )
        )
    # For every (seed, x*), the scientific state is identical across all five
    # margin policies and all six truth families.
    assert all(len(values) == 1 for values in by_key.values())
    assert len(by_key) == len(SEEDS) * len(X_STAR_GRID)

    # The support verdict, by contrast, does vary with margin.
    verdicts = {
        (row["margin_policy"], row["aware_verdict"])
        for row in result.rows
        if row["x_star"] == 12.0
    }
    assert len({v for _m, v in verdicts}) > 1


# =====================================================================
# 9. Exact reproduction under the frozen configuration
# =====================================================================

#: A declared subset, recomputed from scratch and compared against the
#: committed CSV. Spans in-support, boundary and far-extrapolation conditions.
REPRODUCTION_SUBSET_X = (4.0, 9.0, 12.0)
REPRODUCTION_SUBSET_SEEDS = (SEEDS[0], SEEDS[7], SEEDS[-1])


def test_results_reproduce_exactly_under_the_frozen_configuration():
    """Recompute a declared subset and match the committed artifacts exactly."""
    grid = _grid()
    result, _summary = sweep()
    indexed = {(row["seed"], row["x_star"]): row for row in result.rows}

    checked = 0
    for x_star in REPRODUCTION_SUBSET_X:
        for seed in REPRODUCTION_SUBSET_SEEDS:
            state = compute_state(grid, seed, x_star)
            # Determinism within this process.
            assert state == compute_state(grid, seed, x_star)

            recorded = indexed[(seed, x_star)]
            assert state.decision == recorded["sria_decision"]
            assert state.naive_verdict == recorded["naive_verdict"]
            assert state.best_action_id == recorded["best_action_id"]
            for attribute, column in (
                ("p_above", "p_above"),
                ("predictive_mean", "predictive_mean"),
                ("predictive_sd", "predictive_sd"),
                ("evpi", "evpi"),
                ("max_evsi", "max_evsi"),
                ("threshold", "threshold"),
            ):
                fresh = getattr(state, attribute)
                stored = recorded[column]
                assert abs(fresh - stored) <= 1e-12 * max(1.0, abs(stored)), (
                    seed, x_star, attribute, fresh, stored
                )
            checked += 1
    assert checked == len(REPRODUCTION_SUBSET_X) * len(REPRODUCTION_SUBSET_SEEDS)

    # And the posterior itself is bit-reproducible.
    xs = np.array(OBSERVATION_XS, dtype=float)
    observations = [
        Observation(x=float(x), y=float(y), sigma=OBSERVATION_SIGMA)
        for x, y in zip(xs, observations_for_seed(xs, OBSERVATION_SIGMA, SEEDS[3]))
    ]
    weights = posterior(grid, observations, grid.uniform_prior())
    assert np.array_equal(
        weights, posterior(grid, observations, grid.uniform_prior())
    )


# =====================================================================
# The trade-off, and the honesty checks on it
# =====================================================================

def test_the_tradeoff_is_monotone_in_the_margin():
    _result, summary = sweep()
    ordered = [
        entry
        for name in ("very_strict", "strict", "moderate", "permissive", "no_guard")
        for entry in summary["tradeoff"]
        if entry["margin_policy"] == name
    ]
    miss = [entry["dangerous_miss_rate"] for entry in ordered]
    refusal = [entry["false_refusal_rate"] for entry in ordered]

    # Loosening the guard trades misses for refusals, in both directions.
    assert miss == sorted(miss), miss
    assert refusal == sorted(refusal, reverse=True), refusal
    assert miss[0] < miss[-1]
    assert refusal[0] > refusal[-1]


def test_replication_degeneracy_is_measured_and_reported():
    """The 50 seeds turned out to add no independent information.

    Reported rather than buried: the point estimates are unaffected, but any
    interval computed on the 15000 rows would be far too narrow.
    """
    _result, summary = sweep()
    degeneracy = summary["replication_degeneracy"]
    assert degeneracy["cells"] == len(X_STAR_GRID) * len(MARGIN_POLICIES) * len(
        TRUTH_FAMILIES
    )
    assert degeneracy["cells_with_varying_outcome"] == 0
    assert degeneracy["seeds_are_degenerate"] is True

    # The cell-based rates carry the same point estimates on honest denominators.
    for name, _margin in MARGIN_POLICIES:
        rows_based = summary["by_margin"][name]["dangerous_miss_rate"]
        cells_based = summary["by_margin_effective_cells"][name][
            "dangerous_miss_rate"
        ]
        if rows_based["rate"] is not None:
            assert abs(rows_based["rate"] - cells_based["rate"]) < 1e-12
            assert cells_based["denominator"] < rows_based["denominator"]


def test_declared_transport_limitation_is_reported_separately():
    _result, summary = sweep()
    analysis = summary["declared_transport_limitation"]
    assert "attribution mechanism, not a safety mechanism" in (
        analysis["interpretation"]
    )
    assert analysis["dangerous_miss_rate_with_blanket_justification"]["rate"] == 1.0
    # It is not folded into the primary metrics.
    assert "declared_transport_limitation" not in summary["by_margin"]


def test_artifacts_are_written_and_traceable_to_the_config():
    import experiments.falsification as package

    root = Path(package.__file__).resolve().parent
    for name in (
        "s11_config_frozen.json",
        "s11_results_full.csv",
        "s11_summary.json",
        "s11_report.md",
    ):
        assert (root / name).exists(), name

    frozen = json.loads((root / "s11_config_frozen.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "s11_summary.json").read_text(encoding="utf-8"))
    assert frozen["config_hash"] == config_hash()
    assert summary["config_hash"] == config_hash()


def test_threshold_rule_matches_the_preregistered_formula():
    for x in X_STAR_GRID:
        assert abs(threshold_for(x) - (1.0 + 0.5 * x - 0.30)) < 1e-12


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA S1.1 — transport guard calibration")
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
        print(f"S1.1: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"S1.1: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
