from dataclasses import replace

import pytest

from engcore.scientific.discovery import (
    DiscoveryDataset, DiscoveryFeature, SparseDiscoveryPolicy, discover_sparse_equations,
    review_discovery_candidate, DiscoveryDecision,
)
from engcore.scientific.discovery.final_evaluation import FrozenDiscoverySelection, evaluate_final_test
from engcore.scientific.equations import Symbol, Constant
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def data(prefix="dev", expression=None, x=(1., 2., 3., 4., 5., 6.), evidence=("b" * 64,)):
    bindings = tuple({"x": Quantity(v, "1"), "other": Quantity(v, "1")} for v in x)
    return DiscoveryDataset(prefix, (DiscoveryFeature("feature", expression or Symbol("x"), x, bindings),),
        x, (0, 1, 2, 3), (4, 5), "a" * 64, evidence,
        tuple(f"{prefix}-{i}" for i in range(6)), (prefix,) * 6)


def final(expression=None):
    """Separate final data: new rows and new evidence, not the development data relabelled."""
    return data("final", expression, x=(7., 8., 9., 10., 11., 12.), evidence=("c" * 64,))


def selected(dataset=None, policy=None):
    return discover_sparse_equations(dataset or data(), policy or SparseDiscoveryPolicy())[0]


def test_inconsistent_expression_values_are_rejected():
    with pytest.raises(InvalidScientificProblem, match="do not match"):
        DiscoveryFeature("bad", Constant(Quantity(1, "1")), (1., 2.))


def test_valid_constant_and_zero_values_are_accepted():
    DiscoveryFeature("zero", Constant(Quantity(0, "1")), (0., 0.))


def test_expression_identity_changes_even_when_sample_values_coincide():
    assert selected(data(expression=Symbol("other"))).fingerprint != selected().fingerprint


@pytest.mark.parametrize("change", [
    {"target": (1., 2., 3., 4., 5.1, 6.)},
    {"calibration_indices": (0, 1, 2), "holdout_indices": (3, 4, 5)},
    {"group_ids": ("another-experiment",) * 6},
    {"evidence_digests": ("c" * 64,)},
])
def test_candidate_identity_binds_data_roles_lineage_and_evidence(change):
    assert selected(replace(data(), **change)).fingerprint != selected().fingerprint


def test_policy_identity_changes_even_when_fit_does_not():
    assert selected(policy=SparseDiscoveryPolicy(maximum_candidates=1)).fingerprint != selected().fingerprint


def test_feature_bindings_are_snapshotted():
    row = {"x": Quantity(1, "1")}
    feature = DiscoveryFeature("x", Symbol("x"), (1.,), (row,))
    row["x"] = Quantity(2, "1")
    assert feature.sample_bindings[0]["x"].magnitude == 1
    with pytest.raises(TypeError):
        feature.sample_bindings[0]["x"] = Quantity(3, "1")


def _verification(subject):
    from engcore.scientific.verification import (
        DependencyComponent, DependencyRole, RouteDependencyManifest, VerificationCandidate, VerificationObservation,
        VerificationPolicy, VerificationRoute, VerificationRouteKind, VerificationRunRecord, plan_verification,
    )
    plan = plan_verification(
        VerificationRoute("p", VerificationRouteKind.DIFFERENT_IMPLEMENTATION, "a" * 64),
        RouteDependencyManifest("p", (DependencyComponent("p-family", "a" * 64, DependencyRole.SOLVER),), "ours", False),
        (VerificationCandidate(VerificationRoute("v", VerificationRouteKind.EXTERNAL_SOLVER, "b" * 64),
                               RouteDependencyManifest("v", (DependencyComponent("v-family", "b" * 64, DependencyRole.SOLVER),),
                                                       "lab", True)),),
        VerificationPolicy())
    return VerificationRunRecord(plan, VerificationObservation("p", Quantity(300, "kelvin"), "1" * 64, True),
                                 (VerificationObservation("v", Quantity(300.2, "kelvin"), "2" * 64, True),),
                                 Quantity(1, "kelvin"), subject_digest=subject)


def test_selection_cannot_be_called_independent_even_with_a_verification_object():
    candidate = selected()
    assert candidate.evaluation_role == "selection"
    # a real, complete verification bound to this very candidate still does not lift a selection score
    verification = _verification(candidate.fingerprint)
    assert review_discovery_candidate(candidate, verification=verification).decision is DiscoveryDecision.CANDIDATE


def test_a_look_alike_verification_object_is_refused():
    with pytest.raises(InvalidScientificProblem, match="VerificationRunRecord"):
        review_discovery_candidate(selected(), verification=object())


def test_selection_review_does_not_complete_a_closed_loop_campaign():
    from engcore.scientific.discovery import ClosedLoopDiscoveryCampaign, FalsificationRecord, DiscoveryCampaignStage
    candidate = selected()
    campaign = ClosedLoopDiscoveryCampaign("synthetic", candidate.context_digest).with_candidates((candidate,))
    campaign = campaign.with_falsification(FalsificationRecord(candidate.fingerprint, "challenge", "b" * 64,
                                                             True, "synthetic challenge survived"))
    campaign = campaign.with_review(review_discovery_candidate(candidate))
    assert campaign.stage is DiscoveryCampaignStage.HOLDOUT_REVIEW


def test_final_labels_never_change_frozen_model_and_final_is_not_refit():
    frozen = FrozenDiscoverySelection(data(), SparseDiscoveryPolicy(), selected(), .05)
    original = frozen.fingerprint
    good = evaluate_final_test(frozen, final())
    bad = evaluate_final_test(frozen, replace(final(), target=(100.,) * 6))
    assert frozen.fingerprint == original
    assert good.coefficients == bad.coefficients == frozen.candidate.coefficients
    assert good.status.value == "survived_holdout"
    assert bad.status.value == "failed_holdout"
    assert good.evaluation_role == "final_test"
    assert good.fingerprint != bad.fingerprint
    assert review_discovery_candidate(good, final_selection=frozen,
                                      final_data=final()).decision is DiscoveryDecision.HOLDOUT_SURVIVOR


@pytest.mark.parametrize("change", [{"group_ids": ("dev",) * 6},
                                   {"sample_ids": tuple(f"dev-{i}" for i in range(6))},
                                   {"sample_ids": ()}, {"group_ids": ()}])
def test_final_lineage_cannot_overlap_or_be_missing(change):
    frozen = FrozenDiscoverySelection(data(), SparseDiscoveryPolicy(), selected(), .05)
    with pytest.raises(InvalidScientificProblem, match="lineage"):
        evaluate_final_test(frozen, replace(final(), **change))


def test_final_feature_reinterpretation_is_refused():
    frozen = FrozenDiscoverySelection(data(), SparseDiscoveryPolicy(), selected(), .05)
    with pytest.raises(InvalidScientificProblem, match="expressions differ"):
        evaluate_final_test(frozen, final(expression=Symbol("other")))


def test_changed_or_unselected_candidate_cannot_be_frozen():
    with pytest.raises(InvalidScientificProblem, match="selected surviving winner"):
        FrozenDiscoverySelection(data(), SparseDiscoveryPolicy(), replace(selected(), intercept=5.), .05)


@pytest.mark.parametrize("limit", [-1, float("nan"), float("inf")])
def test_final_threshold_is_finite_and_frozen_before_data(limit):
    with pytest.raises(InvalidScientificProblem, match="limit"):
        FrozenDiscoverySelection(data(), SparseDiscoveryPolicy(), selected(), limit)
