from dataclasses import replace

import pytest

from engcore.scientific.discovery import (DiscoveryDataset, DiscoveryFeature, SparseDiscoveryPolicy,
    discover_sparse_equations, review_discovery_candidate, DiscoveryDecision)
from engcore.scientific.discovery.final_evaluation import FrozenDiscoverySelection, evaluate_final_test
from engcore.scientific.equations import Symbol
from engcore.scientific.units.quantity import Quantity


def data(prefix, values=(1., 2., 3., 4.), evidence=("b" * 64,)):
    f = DiscoveryFeature("x", Symbol("x"), values, tuple({"x": Quantity(v, "1")} for v in values))
    return DiscoveryDataset(prefix, (f,), values, (0, 1), (2, 3), "a" * 64, evidence,
                            tuple(f"{prefix}-{i}" for i in range(4)), (prefix,) * 4)


def final():
    """Separate final data: new rows and new evidence, not the development data relabelled."""
    return data("final", (5., 6., 7., 8.), ("c" * 64,))


@pytest.mark.parametrize("role,strip_binding", [("final_test", False), ("holdout", False), ("holdout", True)])
def test_role_or_legacy_relabel_alone_never_promotes(role, strip_binding):
    selected = discover_sparse_equations(data("dev"))[0]
    changed = replace(selected, evaluation_role=role,
                      discovery_binding_digest="" if strip_binding else selected.discovery_binding_digest)
    assert review_discovery_candidate(changed).decision is DiscoveryDecision.CANDIDATE


def test_bare_final_result_still_needs_its_replay_inputs():
    dev = data("dev")
    selection = FrozenDiscoverySelection(dev, SparseDiscoveryPolicy(), discover_sparse_equations(dev)[0], .05)
    result = evaluate_final_test(selection, final())
    assert review_discovery_candidate(result).decision is DiscoveryDecision.CANDIDATE


@pytest.mark.parametrize("change", [{"holdout_rmse": 0.}, {"discovery_binding_digest": "f" * 64},
                                   {"evaluation_role": "holdout"}, {"intercept": 10.}])
def test_changed_final_result_is_unresolved_never_promoted(change):
    dev, final_data = data("dev"), final()
    selection = FrozenDiscoverySelection(dev, SparseDiscoveryPolicy(), discover_sparse_equations(dev)[0], .05)
    result = evaluate_final_test(selection, final_data)
    if "holdout_rmse" in change:
        change = {"holdout_rmse": result.holdout_rmse + 1.0}
    assert review_discovery_candidate(result, final_selection=selection,
                                      final_data=final_data).decision is DiscoveryDecision.HOLDOUT_SURVIVOR
    # the replay does not bind the changed record: unresolved, never promoted and never a contradiction
    changed = review_discovery_candidate(replace(result, **change), final_selection=selection, final_data=final_data)
    assert changed.decision is DiscoveryDecision.CANDIDATE
    assert "not bound" in changed.reasons[0]
