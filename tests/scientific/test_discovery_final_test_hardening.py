"""Review round 2 of the discovery final test (I-1..I-4): each counterexample must fail closed."""

import pytest

from engcore.scientific.discovery import (
    ClosedLoopDiscoveryCampaign, DiscoveryCampaignStage, DiscoveryDataset, DiscoveryDecision, DiscoveryFeature,
    FalsificationRecord, SparseDiscoveryPolicy, discover_sparse_equations, review_discovery_candidate,
)
from engcore.scientific.discovery.campaign import DiscoveryReview
from engcore.scientific.discovery.final_evaluation import FrozenDiscoverySelection, evaluate_final_test
from engcore.scientific.equations import Symbol
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity

DEV_X = (1., 2., 3., 4., 5., 6.)


def data(prefix, x=DEV_X, target=None, evidence=("b" * 64,)):
    feature = DiscoveryFeature("x", Symbol("x"), x, tuple({"x": Quantity(v, "1")} for v in x))
    n = len(x)
    return DiscoveryDataset(prefix, (feature,), target or x, (0, 1, 2, 3), (4, 5), "a" * 64, evidence,
                            tuple(f"{prefix}-{i}" for i in range(n)), (prefix,) * n)


def frozen(limit=.05, policy=None):
    dev = data("dev")
    policy = policy or SparseDiscoveryPolicy()
    return FrozenDiscoverySelection(dev, policy, discover_sparse_equations(dev, policy)[0], limit)


def fresh_final():
    return data("final", x=(7., 8., 9., 10., 11., 12.), evidence=("c" * 64,))


# I-1 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("limit", [.0500001, 1., 93.])
def test_final_limit_cannot_be_looser_than_the_frozen_policy(limit):
    with pytest.raises(InvalidScientificProblem, match="limit"):
        frozen(limit)


def test_final_limit_may_be_as_strict_as_the_policy():
    assert frozen(.05).final_rmse_limit == .05
    assert frozen(.01).final_rmse_limit == .01


def test_final_model_must_beat_the_frozen_development_baseline():
    # the development calibration mean is 2.5; a constant 2.5 target makes that baseline exact (RMSE 0), while the
    # frozen y = x model is off by ~0.014 -- inside the RMSE limit, but no better than predicting the mean
    near = (2.5, 2.51, 2.49, 2.52, 2.48, 2.5)
    final = data("final", x=near, target=(2.5,) * 6, evidence=("c" * 64,))
    result = evaluate_final_test(frozen(), final)
    assert result.holdout_rmse <= .05
    assert result.status.value == "failed_holdout"


# I-2 ------------------------------------------------------------------------------------------------------------------
def test_relabelled_development_data_is_refused_as_final():
    with pytest.raises(InvalidScientificProblem, match="evidence"):
        evaluate_final_test(frozen(), data("relabel"))


def test_final_rows_duplicating_development_rows_are_refused():
    with pytest.raises(InvalidScientificProblem, match="duplicate"):
        evaluate_final_test(frozen(), data("copy", evidence=("c" * 64,)))


def test_fresh_final_data_still_passes():
    selection, final = frozen(), fresh_final()
    result = evaluate_final_test(selection, final)
    assert result.status.value == "survived_holdout"
    review = review_discovery_candidate(result, final_selection=selection, final_data=final)
    assert review.decision is DiscoveryDecision.HOLDOUT_SURVIVOR


# I-3 ------------------------------------------------------------------------------------------------------------------
def _campaign(candidate):
    return (ClosedLoopDiscoveryCampaign("synthetic", candidate.context_digest).with_candidates((candidate,))
            .with_falsification(FalsificationRecord(candidate.fingerprint, "challenge", "b" * 64, True, "survived")))


@pytest.mark.parametrize("decision", [DiscoveryDecision.HOLDOUT_SURVIVOR, DiscoveryDecision.INDEPENDENTLY_REPRODUCED])
def test_hand_written_review_cannot_promote_a_selection_candidate(decision):
    winner = discover_sparse_equations(data("dev"))[0]
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(winner).with_review(DiscoveryReview(winner, decision, ("asserted",), "d" * 64))


def test_independent_reproduction_cannot_be_asserted_without_a_replay():
    result = evaluate_final_test(frozen(), fresh_final())
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(result).with_review(DiscoveryReview(result, DiscoveryDecision.INDEPENDENTLY_REPRODUCED, ("asserted",)))


# H-1 (review round 2): the campaign admits a promoting review only by replaying review_discovery_candidate -------------
def _bad_final():
    return data("bad", x=(7., 8., 9., 10., 11., 12.), target=(100.,) * 6, evidence=("c" * 64,))


def test_a_failed_final_record_cannot_be_promoted_by_a_hand_written_review():
    bad = evaluate_final_test(frozen(), _bad_final())
    assert bad.status.value == "failed_holdout" and bad.evaluation_role == "final_test"
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(bad).with_review(DiscoveryReview(bad, DiscoveryDecision.INDEPENDENTLY_REPRODUCED, ("asserted",), "d" * 64))


def test_a_selection_winner_relabelled_final_test_cannot_be_promoted():
    from dataclasses import replace
    relabelled = replace(discover_sparse_equations(data("dev"))[0], evaluation_role="final_test")
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(relabelled).with_review(DiscoveryReview(relabelled, DiscoveryDecision.HOLDOUT_SURVIVOR, ("asserted",)))


def test_a_genuine_survivor_still_needs_its_review_to_carry_the_replay_inputs():
    result = evaluate_final_test(frozen(), fresh_final())
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(result).with_review(DiscoveryReview(result, DiscoveryDecision.HOLDOUT_SURVIVOR, ("asserted",)))


def test_a_genuine_review_with_its_decision_raised_is_refused():
    from dataclasses import replace
    selection, final = frozen(), fresh_final()
    result = evaluate_final_test(selection, final)
    genuine = review_discovery_candidate(result, final_selection=selection, final_data=final)
    raised = replace(genuine, decision=DiscoveryDecision.INDEPENDENTLY_REPRODUCED, verification_digest="d" * 64)
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(result).with_review(raised)


def test_real_replay_inputs_do_not_launder_a_false_decision():
    selection, bad_final = frozen(), _bad_final()
    bad = evaluate_final_test(selection, bad_final)
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(bad).with_review(DiscoveryReview(bad, DiscoveryDecision.HOLDOUT_SURVIVOR, ("asserted",),
                                                   final_selection=selection, final_data=bad_final))


# M-1 (review round 2): a stored final-test status is never acted on before replay ------------------------------------
def test_a_forged_failed_status_on_a_genuine_survivor_is_unresolved_not_rejected():
    from dataclasses import replace
    from engcore.scientific.discovery.candidate import DiscoveryCandidateStatus
    selection, final = frozen(), fresh_final()
    forged = replace(evaluate_final_test(selection, final), status=DiscoveryCandidateStatus.FAILED_HOLDOUT)
    review = review_discovery_candidate(forged, final_selection=selection, final_data=final)
    assert review.decision is DiscoveryDecision.CANDIDATE
    assert "not bound" in review.reasons[0]


def test_a_final_failure_without_its_replay_inputs_is_not_rejected():
    bad = evaluate_final_test(frozen(), _bad_final())
    assert review_discovery_candidate(bad).decision is DiscoveryDecision.CANDIDATE


# L-1 (review round 2): pin the development-fixed baseline and a non-zero improvement bar ----------------------------
def test_the_baseline_is_fixed_by_development_not_by_the_final_targets():
    # final targets sit at 10, far from the development calibration mean 2.5: a final-mean baseline (RMSE 0) would
    # fail the model, the development-fixed baseline (RMSE 7.5) does not
    near = (10., 10.01, 9.99, 10.02, 9.98, 10.)
    result = evaluate_final_test(frozen(), data("final", x=near, target=(10.,) * 6, evidence=("c" * 64,)))
    assert result.status.value == "survived_holdout"


def test_a_non_zero_improvement_bar_is_applied_at_the_final_test():
    # selection survives an improvement bar of 1.0 (baseline RMSE ~3.04 on the selection rows); the final baseline is
    # only 0.5 above a 0.014 model error, so the same bar must fail it
    policy = SparseDiscoveryPolicy(minimum_holdout_improvement=1.0)
    near = (3.005, 3.01, 2.99, 3.02, 2.98, 2.995)       # no (3, 3) row: that would duplicate a development row
    result = evaluate_final_test(frozen(policy=policy), data("final", x=near, target=(3.,) * 6, evidence=("c" * 64,)))
    assert result.holdout_rmse <= .05
    assert result.status.value == "failed_holdout"


# M-A (review round 3): every review entering a campaign is replayed, whatever it decides -----------------------------
def _survivor():
    selection, final = frozen(), fresh_final()
    return selection, final, evaluate_final_test(selection, final)


@pytest.mark.parametrize("decision", [DiscoveryDecision.REJECTED, DiscoveryDecision.CANDIDATE])
def test_a_hand_written_non_promoting_review_is_refused(decision):
    _, _, result = _survivor()
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(result).with_review(DiscoveryReview(result, decision, ("asserted",)))


def test_a_genuine_replayed_rejection_is_still_admitted():
    selection, bad_final = frozen(), _bad_final()
    bad = evaluate_final_test(selection, bad_final)
    campaign = _campaign(bad).with_review(review_discovery_candidate(bad, final_selection=selection, final_data=bad_final))
    assert campaign.stage is DiscoveryCampaignStage.COMPLETE
    assert campaign.reviews[0].decision is DiscoveryDecision.REJECTED


# M-B (review round 3): the frozen selection is re-checked where it is used, and its identity covers its inputs -------
def test_a_subclass_cannot_skip_the_frozen_selection_checks():
    class Unchecked(FrozenDiscoverySelection):
        def __post_init__(self):
            pass

    final = fresh_final()
    fitted_to_final = discover_sparse_equations(final)[0]          # never selected on development data
    forged = Unchecked(data("dev"), SparseDiscoveryPolicy(), fitted_to_final, 1e6)
    with pytest.raises(InvalidScientificProblem, match="FrozenDiscoverySelection"):
        evaluate_final_test(forged, final)


@pytest.mark.parametrize("name,value", [("final_rmse_limit", 1e6), ("candidate", None)])
def test_a_selection_mutated_after_construction_is_refused(name, value):
    selection = frozen()
    if name == "candidate":
        value = discover_sparse_equations(fresh_final())[0]
    object.__setattr__(selection, name, value)
    with pytest.raises(InvalidScientificProblem):
        evaluate_final_test(selection, fresh_final())


def test_a_subclassed_final_dataset_is_refused():
    final = fresh_final()

    class Lookalike(DiscoveryDataset):
        pass

    lookalike = Lookalike(**{f: getattr(final, f) for f in DiscoveryDataset.__dataclass_fields__})
    with pytest.raises(InvalidScientificProblem, match="DiscoveryDataset"):
        evaluate_final_test(frozen(), lookalike)


@pytest.mark.parametrize("name", ["development", "policy"])
def test_the_selection_identity_covers_development_and_policy(name):
    selection = frozen()
    before = selection.fingerprint
    other = data("dev2", evidence=("f" * 64,)) if name == "development" else SparseDiscoveryPolicy(max_terms=2)
    object.__setattr__(selection, name, other)
    assert selection.fingerprint != before


# I-6: a verification must be a real VerificationRunRecord, never a look-alike ----------------------------------------
def _verification(subject, value=300.2):
    from engcore.scientific.verification import (
        DependencyComponent, DependencyRole, RouteDependencyManifest, VerificationCandidate, VerificationObservation,
        VerificationPolicy, VerificationRoute, VerificationRouteKind, VerificationRunRecord, plan_verification,
    )

    def route(rid, kind, digit):
        return VerificationRoute(rid, kind, digit * 64)

    def manifest(rid, family, digit, authority="ours", external=False):
        return RouteDependencyManifest(rid, (DependencyComponent(family, digit * 64, DependencyRole.SOLVER),),
                                       authority, external)

    plan = plan_verification(route("p", VerificationRouteKind.DIFFERENT_IMPLEMENTATION, "a"), manifest("p", "p-family", "a"),
                             (VerificationCandidate(route("v", VerificationRouteKind.EXTERNAL_SOLVER, "b"),
                                                    manifest("v", "v-family", "b", "lab", True)),),
                             VerificationPolicy())
    return VerificationRunRecord(plan, VerificationObservation("p", Quantity(300, "kelvin"), "1" * 64, True),
                                 (VerificationObservation("v", Quantity(value, "kelvin"), "2" * 64, True),),
                                 Quantity(1, "kelvin"), subject_digest=subject)


def test_a_look_alike_verification_is_refused():
    from engcore.scientific.verification import VerificationDecision
    selection, final, survivor = _survivor()
    bound_to = survivor.fingerprint

    class LookAlike:
        subject_digest = bound_to

        class result:  # noqa: N801 - mirrors the attribute the review reads
            complete = True

            class verification:  # noqa: N801
                decision = VerificationDecision.VERIFIED

        def to_dict(self):
            return {"subject_digest": self.subject_digest}

    with pytest.raises(InvalidScientificProblem, match="VerificationRunRecord"):
        review_discovery_candidate(survivor, verification=LookAlike(), final_selection=selection, final_data=final)


def test_a_real_bound_verification_reproduces_and_enters_the_campaign():
    selection, final, result = _survivor()
    review = review_discovery_candidate(result, verification=_verification(result.fingerprint),
                                        final_selection=selection, final_data=final)
    assert review.decision is DiscoveryDecision.INDEPENDENTLY_REPRODUCED
    assert _campaign(result).with_review(review).stage is DiscoveryCampaignStage.COMPLETE


def test_a_review_whose_verification_is_swapped_after_the_fact_is_refused():
    from dataclasses import replace
    selection, final, result = _survivor()
    review = review_discovery_candidate(result, verification=_verification(result.fingerprint),
                                        final_selection=selection, final_data=final)
    swapped = replace(review, verification=_verification(result.fingerprint, value=300.4))
    with pytest.raises(InvalidScientificProblem, match="review_discovery_candidate"):
        _campaign(result).with_review(swapped)


def test_a_replayed_final_survivor_still_enters_the_campaign():
    selection, final = frozen(), fresh_final()
    result = evaluate_final_test(selection, final)
    campaign = _campaign(result).with_review(
        review_discovery_candidate(result, final_selection=selection, final_data=final))
    assert campaign.stage is DiscoveryCampaignStage.INDEPENDENT_REPRODUCTION


# I-4 ------------------------------------------------------------------------------------------------------------------
def test_replay_inputs_that_do_not_bind_leave_the_candidate_unresolved():
    selection = frozen()
    first = fresh_final()
    other = data("other", x=(13., 14., 15., 16., 17., 18.), evidence=("e" * 64,))
    result = evaluate_final_test(selection, first)
    review = review_discovery_candidate(result, final_selection=selection, final_data=other)
    assert review.decision is DiscoveryDecision.CANDIDATE
    assert "not bound" in review.reasons[0]


def test_a_replayed_final_failure_is_still_rejected():
    selection = frozen()
    bad = data("bad", x=(7., 8., 9., 10., 11., 12.), target=(100.,) * 6, evidence=("c" * 64,))
    result = evaluate_final_test(selection, bad)
    assert review_discovery_candidate(result, final_selection=selection,
                                      final_data=bad).decision is DiscoveryDecision.REJECTED


# H-1 (review round 4): exact review and candidate types, checked before the replay equality ---------------------------
class _EqualToAnything(DiscoveryReview):
    def __eq__(self, other):
        return True


class _NeverUnequal(DiscoveryReview):
    def __ne__(self, other):
        return False


@pytest.mark.parametrize("cls", [_EqualToAnything, _NeverUnequal])
def test_a_review_subclass_cannot_fake_its_replay(cls):
    winner = discover_sparse_equations(data("dev"))[0]
    with pytest.raises(InvalidScientificProblem, match="exact DiscoveryReview"):
        _campaign(winner).with_review(cls(winner, DiscoveryDecision.INDEPENDENTLY_REPRODUCED, ("asserted",), "d" * 64))


# M-1 (review round 4): a candidate subclass cannot borrow a replayed verdict ------------------------------------------
def _shown(genuine, **change):
    from dataclasses import fields
    from engcore.scientific.discovery.candidate import DiscoveredEquationCandidate

    class Shown(DiscoveredEquationCandidate):
        fingerprint = property(lambda self: genuine.fingerprint)

    return Shown(**({f.name: getattr(genuine, f.name) for f in fields(DiscoveredEquationCandidate)} | change))


def test_a_candidate_subclass_cannot_borrow_a_replayed_verdict():
    selection, final, genuine = _survivor()
    shown = _shown(genuine, coefficients=(42.,))              # an equation that was never tested
    with pytest.raises(InvalidScientificProblem, match="exact DiscoveredEquationCandidate"):
        review_discovery_candidate(shown, verification=_verification(genuine.fingerprint),
                                   final_selection=selection, final_data=final)


def test_a_campaign_refuses_a_candidate_subclass():
    _, _, genuine = _survivor()
    with pytest.raises(InvalidScientificProblem, match="exact DiscoveredEquationCandidate"):
        ClosedLoopDiscoveryCampaign("synthetic", genuine.context_digest).with_candidates((_shown(genuine),))


# M-2 (review round 4): nested policy and datasets are rebuilt where they are used -------------------------------------
def test_a_policy_mutated_to_a_forbidden_bar_is_refused_at_use():
    selection = frozen()
    object.__setattr__(selection.policy, "minimum_holdout_improvement", -1.0)      # its constructor refuses this
    object.__setattr__(selection, "candidate", discover_sparse_equations(selection.development, selection.policy)[0])
    near = (2.5, 2.51, 2.49, 2.52, 2.48, 2.5)
    with pytest.raises(InvalidScientificProblem, match="policy"):
        evaluate_final_test(selection, data("final", x=near, target=(2.5,) * 6, evidence=("c" * 64,)))


def test_development_feature_values_mutated_off_their_expression_are_refused_at_use():
    selection = frozen()
    feature = selection.development.features[0]
    object.__setattr__(feature, "values", tuple(v + 1 for v in feature.values))   # no longer what the expression gives
    object.__setattr__(selection, "candidate", discover_sparse_equations(selection.development)[0])
    with pytest.raises(InvalidScientificProblem, match="do not match"):
        evaluate_final_test(selection, fresh_final())


def test_final_feature_values_mutated_off_their_expression_are_refused():
    final = fresh_final()
    object.__setattr__(final.features[0], "values", tuple(v * 2 for v in final.features[0].values))
    with pytest.raises(InvalidScientificProblem, match="do not match"):
        evaluate_final_test(frozen(), final)


# L-1 (review round 5): equal records must also have equal fingerprints (True == 1, 1 == 1.0, -0.0 == 0.0) ------------
def test_a_numeric_alias_of_the_replayed_record_is_not_bound():
    from dataclasses import replace
    selection, final, genuine = _survivor()
    alias = replace(genuine, complexity=True)                  # == genuine field by field, different fingerprint
    assert alias == genuine and alias.fingerprint != genuine.fingerprint
    review = review_discovery_candidate(alias, final_selection=selection, final_data=final)
    assert review.decision is DiscoveryDecision.CANDIDATE
    assert "not bound" in review.reasons[0]


def test_a_numeric_alias_of_the_winner_cannot_be_frozen():
    from dataclasses import replace
    dev = data("dev")
    winner = discover_sparse_equations(dev)[0]
    with pytest.raises(InvalidScientificProblem, match="selected surviving winner"):
        FrozenDiscoverySelection(dev, SparseDiscoveryPolicy(), replace(winner, complexity=True), .05)


# L-2 (review round 5): with_review checks the review's type before reading it --------------------------------------
@pytest.mark.parametrize("review", [object(), "a review",
                                    DiscoveryReview(None, DiscoveryDecision.CANDIDATE, ("asserted",)),
                                    DiscoveryReview(object(), DiscoveryDecision.CANDIDATE, ("asserted",))])
def test_with_review_refuses_a_non_review_with_the_scientific_error(review):
    _, _, genuine = _survivor()
    with pytest.raises(InvalidScientificProblem, match="exact DiscoveryReview"):
        _campaign(genuine).with_review(review)


# L-3 (review round 5): pin the guards no earlier test reached ----------------------------------------------------------
def test_a_final_dataset_changed_after_it_was_built_is_refused():
    # an upper-case digest is lower-cased by the constructor; set afterwards it would also slip past the evidence
    # overlap check against the development digest "c"*64 -- only the rebuild comparison catches it
    selection = frozen()
    object.__setattr__(selection.development, "evidence_digests", ("c" * 64,))
    object.__setattr__(selection, "candidate", discover_sparse_equations(selection.development)[0])
    final = fresh_final()
    object.__setattr__(final, "evidence_digests", ("C" * 64,))
    with pytest.raises(InvalidScientificProblem, match="changed after it was built"):
        evaluate_final_test(selection, final)


def test_a_policy_changed_after_it_was_built_is_refused():
    selection = frozen()
    object.__setattr__(selection.policy, "max_terms", 3.5)    # the constructor would make this 3
    with pytest.raises(InvalidScientificProblem, match="changed after it was built"):
        evaluate_final_test(selection, fresh_final())


def test_a_feature_subclass_in_the_final_data_is_refused():
    from dataclasses import replace

    class LookalikeFeature(DiscoveryFeature):
        pass

    final = fresh_final()
    f = final.features[0]
    lookalike = replace(final, features=(LookalikeFeature(f.name, f.expression, f.values, f.sample_bindings),))
    with pytest.raises(InvalidScientificProblem, match="exact DiscoveryFeatures"):
        evaluate_final_test(frozen(), lookalike)


def test_a_review_of_a_candidate_subclass_is_refused_by_the_campaign_itself():
    _, _, genuine = _survivor()
    review = DiscoveryReview(_shown(genuine), DiscoveryDecision.CANDIDATE, ("asserted",))
    with pytest.raises(InvalidScientificProblem, match="exact DiscoveryReview of an exact DiscoveredEquationCandidate"):
        _campaign(genuine).with_review(review)


def test_a_legacy_feature_without_bindings_still_freezes_and_evaluates():
    from engcore.scientific.equations import Constant

    def mixed(prefix, x, evidence):
        bound = DiscoveryFeature("x", Symbol("x"), x, tuple({"x": Quantity(v, "1")} for v in x))
        legacy = DiscoveryFeature("two", Constant(Quantity(2, "1")), (2.,) * len(x))        # no sample bindings
        n = len(x)
        return DiscoveryDataset(prefix, (bound, legacy), x, (0, 1, 2, 3), (4, 5), "a" * 64, evidence,
                                tuple(f"{prefix}-{i}" for i in range(n)), (prefix,) * n)

    dev = mixed("dev", DEV_X, ("b" * 64,))
    selection = FrozenDiscoverySelection(dev, SparseDiscoveryPolicy(), discover_sparse_equations(dev)[0], .05)
    final = mixed("final", (7., 8., 9., 10., 11., 12.), ("c" * 64,))
    assert evaluate_final_test(selection, final).status.value == "survived_holdout"
