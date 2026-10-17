"""Phase 1 BR5 -- verification requirements are typed evidence categories, not an ordinal ladder.

Before BR5 ``level < policy.minimum_level`` admitted every higher-numbered
route: an experiment (V6) or an independent reproduction (V7) satisfied a
code-verification requirement (V2), and an external solver (V5) satisfied an
analytical-reference requirement (V4).

NOT RUN (Phase 1 build phase): docs/work/DEFERRED_VALIDATION.md, DV-40.
"""

import pytest

from engcore.planning.verification import VerificationPlanningOption
from engcore.scientific.verification import *
from engcore.scientific.verification.ladder import provides


def route(rid, kind, digit):
    return VerificationRoute(rid, kind, digit * 64)


def manifest(rid, family, digit, authority="ours", external=False):
    return RouteDependencyManifest(rid, (DependencyComponent(family, digit * 64, DependencyRole.SOLVER),), authority, external)


PRIMARY = route("p", VerificationRouteKind.DIFFERENT_IMPLEMENTATION, "a")
PRIMARY_DEPS = manifest("p", "p-family", "a")


def candidate(rid, kind, digit):
    return VerificationCandidate(route(rid, kind, digit), manifest(rid, f"{rid}-family", digit))


def plan(policy, *candidates):
    return plan_verification(PRIMARY, PRIMARY_DEPS, candidates, policy)


# ---- the category table -------------------------------------------------------------------------


def test_every_level_names_a_category_and_its_own_route_kind_provides_it():
    for kind in VerificationRouteKind:
        assert provides(kind, category_for_route(kind))
    assert len({category_for_level(level) for level in VerificationLevel}) == len(VerificationLevel)


def test_experimental_validation_is_provided_only_by_measurement():
    assert CATEGORY_PROVIDERS[VerificationEvidenceCategory.EXPERIMENTAL_VALIDATION] == {
        VerificationRouteKind.EXPERIMENTAL_MEASUREMENT}


def test_code_verification_is_provided_by_code_to_code_and_exact_solution_comparison_only():
    assert CATEGORY_PROVIDERS[VerificationEvidenceCategory.CODE_VERIFICATION] == {
        VerificationRouteKind.DIFFERENT_IMPLEMENTATION, VerificationRouteKind.EXTERNAL_SOLVER,
        VerificationRouteKind.ANALYTICAL_REFERENCE}


# ---- no unrelated higher-numbered level satisfies a requirement -------------------------------


@pytest.mark.parametrize("kind", [VerificationRouteKind.DIFFERENT_MODEL, VerificationRouteKind.EXPERIMENTAL_MEASUREMENT,
                                  VerificationRouteKind.INDEPENDENT_REPRODUCTION])
def test_a_legacy_v2_requirement_is_not_met_by_validation_model_form_or_reproduction(kind):
    made = plan(VerificationPolicy(minimum_level=VerificationLevel.V2), candidate("c", kind, "b"))
    assert not made.complete
    assert [r[0] for r in made.rejected] == ["c"]
    assert "code_verification" in made.rejected[0][1]


def test_an_external_solver_does_not_satisfy_an_analytical_reference_requirement():
    made = plan(VerificationPolicy(minimum_level=VerificationLevel.V4),
                candidate("ext", VerificationRouteKind.EXTERNAL_SOLVER, "b"))
    assert not made.complete


def test_an_analytical_reference_does_not_satisfy_independent_solver_corroboration():
    made = plan(VerificationPolicy(required_categories=(VerificationEvidenceCategory.INDEPENDENT_SOLVER_CORROBORATION,)),
                candidate("exact", VerificationRouteKind.ANALYTICAL_REFERENCE, "b"))
    assert not made.complete


def test_a_rerun_is_repeatability_not_reproducibility():
    made = plan(VerificationPolicy(required_categories=(VerificationEvidenceCategory.REPRODUCIBILITY,)),
                candidate("rerun", VerificationRouteKind.SAME_SOLVER_RERUN, "b"))
    assert not made.complete


# ---- what legacy policies keep ----------------------------------------------------------------


@pytest.mark.parametrize("kind", [VerificationRouteKind.DIFFERENT_IMPLEMENTATION, VerificationRouteKind.EXTERNAL_SOLVER,
                                  VerificationRouteKind.ANALYTICAL_REFERENCE])
def test_a_legacy_v2_requirement_keeps_its_code_verification_routes(kind):
    assert plan(VerificationPolicy(minimum_level=VerificationLevel.V2), candidate("c", kind, "b")).complete


def test_the_builtin_pack_policies_keep_their_routes():
    # electrothermal: V1 with a different algorithm; thermal resistance: V4 with an analytical reference
    assert plan(VerificationPolicy(minimum_level=VerificationLevel.V1),
                candidate("alg", VerificationRouteKind.DIFFERENT_ALGORITHM, "b")).complete
    assert plan(VerificationPolicy(minimum_level=VerificationLevel.V4),
                candidate("exact", VerificationRouteKind.ANALYTICAL_REFERENCE, "b")).complete


def test_provider_independence_is_still_required():
    shared = VerificationCandidate(route("c", VerificationRouteKind.EXTERNAL_SOLVER, "b"), manifest("c", "p-family", "a"))
    made = plan(VerificationPolicy(minimum_level=VerificationLevel.V2), shared)
    assert not made.complete and "independence" in made.rejected[0][1]


# ---- several typed requirements -----------------------------------------------------------------


def test_every_required_category_must_be_covered():
    policy = VerificationPolicy(required_categories=(VerificationEvidenceCategory.CODE_VERIFICATION,
                                                     VerificationEvidenceCategory.EXPERIMENTAL_VALIDATION))
    code_only = plan(policy, candidate("ext", VerificationRouteKind.EXTERNAL_SOLVER, "b"))
    assert not code_only.complete
    both = plan(policy, candidate("ext", VerificationRouteKind.EXTERNAL_SOLVER, "b"),
                candidate("lab", VerificationRouteKind.EXPERIMENTAL_MEASUREMENT, "c"))
    assert both.complete


def test_a_policy_refuses_a_repeated_or_unknown_category():
    with pytest.raises(ValueError):
        VerificationPolicy(required_categories=(VerificationEvidenceCategory.CODE_VERIFICATION,) * 2)
    with pytest.raises(ValueError):
        VerificationPolicy(required_categories=("stronger_than_v4",))
    with pytest.raises(ValueError):
        VerificationPolicy(required_categories="code_verification")


# ---- serialization identity -----------------------------------------------------------------------


def test_a_legacy_policy_serializes_without_required_categories():
    made = plan(VerificationPolicy(minimum_level=VerificationLevel.V2), candidate("c", VerificationRouteKind.EXTERNAL_SOLVER, "b"))
    assert "required_categories" not in plan_to_dict(made)["policy"]
    assert plan_to_dict(plan_from_dict(plan_to_dict(made))) == plan_to_dict(made)


def test_a_typed_policy_round_trips():
    policy = VerificationPolicy(required_categories=(VerificationEvidenceCategory.EXPERIMENTAL_VALIDATION,
                                                     VerificationEvidenceCategory.CODE_VERIFICATION))
    made = plan(policy, candidate("ext", VerificationRouteKind.EXTERNAL_SOLVER, "b"),
                candidate("lab", VerificationRouteKind.EXPERIMENTAL_MEASUREMENT, "c"))
    payload = plan_to_dict(made)
    assert payload["policy"]["required_categories"] == ["code_verification", "experimental_validation"]
    assert plan_from_dict(payload).policy == policy


def test_a_planning_option_names_its_evidence_category():
    evidence = IndependenceEvidence("p", "v", IndependenceLevel.STRONG, (), "declared")
    option = VerificationPlanningOption("cap", "p", "v", VerificationRouteKind.EXPERIMENTAL_MEASUREMENT, evidence, "basis")
    assert option.evidence_category is VerificationEvidenceCategory.EXPERIMENTAL_VALIDATION
