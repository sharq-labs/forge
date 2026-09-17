"""Core re-audit 2026-09-16, batch 43: unassessed candidates are not ranked, and a ranking says what it is.

Problem R-44 (the audit's findings 52 and 84), improvement I-21 part B of two, under
benchmarks/core_v4_false_confidence/BATCH43_THRESHOLD_PROTOCOL.json.

Two selection paths applied two different rules, and the one with no production caller had the stricter one.
`_established` looks only at validity, so a result whose validation is `unverified_report()` -- status
NOT_RUN, nothing attained -- wins on its objective against a verified candidate. And the mechanism production
uses is the design Pareto and elite archives, whose gate is a caller-set ELIGIBLE that never consults
`result.validity`, while every multirotor result records `validity_not_assessed` for both its models.
"""

from __future__ import annotations

import pytest

import tests.test_design_d1_evaluation_archives as D
import tests.test_scientific_core as C
from engcore.design import (
    DesignCandidateReference,
    DesignEvaluation,
    ParetoArchive,
    ScopedEliteArchive,
    SelectionEligibility,
)
from engcore.scientific.errors import InvalidScientificProblem, ScientificCoreError
from engcore.scientific.experiments import (
    EvaluationStatus,
    ExperimentBudget,
    ScientificEvaluation,
    ScientificExperiment,
)
from engcore.scientific.results import requirements as R
from engcore.scientific.results.validation import unverified_report
from engcore.scientific.units import Quantity


def _symbol(name):
    assert hasattr(R, name), (
        f"engcore.scientific.results.requirements has no {name!r}; it is preregistered in "
        f"BATCH43_THRESHOLD_PROTOCOL.json"
    )
    return getattr(R, name)


def _ranked_without_assessment():
    assert hasattr(SelectionEligibility, "RANKED_WITHOUT_ASSESSMENT"), (
        "SelectionEligibility has no RANKED_WITHOUT_ASSESSMENT; it is preregistered in "
        "BATCH43_THRESHOLD_PROTOCOL.json")
    return SelectionEligibility.RANKED_WITHOUT_ASSESSMENT


def _unassessed_field(archive):
    assert hasattr(archive, "unassessed"), (
        f"{type(archive).__name__} has no `unassessed`; it is preregistered in "
        f"BATCH43_THRESHOLD_PROTOCOL.json")
    return archive.unassessed


def _assessed():
    from engcore.scientific.models.definition import RangeCondition, ValidityDomain

    domain = ValidityDomain(conditions=(RangeCondition("drive_level", maximum=Quantity(10.0, "volt")),))
    return {"validity_not_assessed": {},
            "validity": {"synthetic.linear_response": domain.assess({"drive_level": Quantity(5.0, "volt")})}}


def _evaluation(index, load, *, validation=None, assessed=True):
    values = {"load": Quantity(load, "watt"), "response": Quantity(0.1, "ampere")}
    extra = dict(_assessed()) if assessed else {}
    if validation is not None:
        extra["validation"] = validation
    result = C._result(result_id=f"res-b43-{index}", values=values, **extra)
    problem = C.build_algebraic_problem()
    return ScientificEvaluation(
        evaluation_id=f"eval-b43-{index}",
        candidate={"drive_level": Quantity(5.0, "volt"), "scale_factor": Quantity(100.0, "ohm")},
        status=EvaluationStatus.OK,
        result=result,
        objective_values={"minimize_load": Quantity(load, "watt")},
        constraint_checks=(problem.constraints[0].check(Quantity(0.1, "ampere")),),
    )


def _experiment(*evaluations):
    experiment = ScientificExperiment("exp-b43", C.build_algebraic_problem(),
                                      ExperimentBudget(max_observations=9))
    for evaluation in evaluations:
        experiment.record(evaluation)
    return experiment


# ---------------------------------------------------------------------------
# one_established_candidate_rule_in_the_results_layer
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-44: the rule lives on ScientificExperiment, which nothing in src calls, and the results layer has none")
def test_r44_the_established_candidate_rule_lives_in_the_results_layer():
    problems = _symbol("result_establishment_problems")
    established = _evaluation(1, 2.0).result
    assert problems(established) == (), problems(established)
    unverified = _evaluation(2, 2.0, validation=unverified_report()).result
    assert problems(unverified), "a result nobody verified is reported as established"
    assert any("not_run" in reason.lower() or "NOT_RUN" in reason for reason in problems(unverified)), \
        problems(unverified)


@pytest.mark.xfail(strict=True, reason="R-44: the shared rule does not exist yet")
def test_r44_a_result_whose_models_were_not_assessed_is_not_established():
    problems = _symbol("result_establishment_problems")
    unassessed = _evaluation(3, 2.0, assessed=False).result
    assert problems(unassessed), "a result whose models nobody assessed is reported as established"


@pytest.mark.xfail(strict=True, reason="R-44 finding 52 as audited: unverified_report() -- status NOT_RUN, nothing attained -- wins on its objective")
def test_r44_a_candidate_with_no_verification_at_all_is_not_ranked():
    """Finding 52 as audited: unverified_report() -- status NOT_RUN, nothing attained -- won the ranking."""
    verified = _evaluation(4, 5.0)
    unverified = _evaluation(5, 0.5, validation=unverified_report())
    best = _experiment(verified, unverified).best("minimize_load")
    assert best is not None and best.evaluation_id == verified.evaluation_id, (
        "the candidate with the better value and no verification behind it was ranked best")


@pytest.mark.xfail(strict=True, reason="R-44: the shared rule does not exist yet")
def test_r44_an_inapplicable_check_does_not_make_a_candidate_unestablished():
    """The control, and the reason batch 40's distinction exists: NOT_APPLICABLE is not NOT_RUN."""
    from engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationLevel,
        ValidationOutcome,
        ValidationReport,
    )

    report = ValidationReport(checks=(
        ValidationCheck(name="dimensional_consistency", outcome=ValidationOutcome.PASS,
                        establishes=ValidationLevel.DIMENSIONALLY_VALID, evidence=("fixture",)),
        ValidationCheck(name="voltage_source_relation", outcome=ValidationOutcome.NOT_APPLICABLE,
                        detail="nothing of that kind here"),
    ))
    evaluation = _evaluation(6, 2.0, validation=report)
    assert _symbol("result_establishment_problems")(evaluation.result) == ()
    assert _experiment(evaluation).best("minimize_load") is evaluation


# ---------------------------------------------------------------------------
# eligible_means_the_models_were_assessed
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-44 finding 84: there is no label between ELIGIBLE and INELIGIBLE, so an unassessed candidate is marked eligible")
def test_r44_there_is_a_label_for_a_candidate_ranked_without_assessment():
    assert hasattr(SelectionEligibility, "RANKED_WITHOUT_ASSESSMENT"), (
        "SelectionEligibility has no RANKED_WITHOUT_ASSESSMENT; it is preregistered")
    assert list(SelectionEligibility)[:3] == [SelectionEligibility.UNKNOWN,
                                              SelectionEligibility.ELIGIBLE,
                                              SelectionEligibility.INELIGIBLE], (
        "the new member must be appended: the member order is frozen")


@pytest.mark.xfail(strict=True, reason="R-44 finding 84 as audited: the eligibility gate never consults result.validity")
def test_r44_eligible_cannot_be_declared_over_an_unassessed_result():
    with pytest.raises(InvalidScientificProblem, match="RANKED_WITHOUT_ASSESSMENT|assess"):
        D._evaluation("b43u", D.TWIN_A, 1000.0, 1.0, eligibility=SelectionEligibility.ELIGIBLE)


@pytest.mark.xfail(strict=True, reason="R-44: the label does not exist yet")
def test_r44_the_honest_label_is_accepted_for_the_same_record():
    evaluation = D._evaluation("b43r", D.TWIN_A, 1000.0, 1.0,
                               eligibility=_ranked_without_assessment())
    assert evaluation.eligibility is _ranked_without_assessment()
    assert evaluation.eligibility_reasons


@pytest.mark.xfail(strict=True, reason="R-44: the label does not exist yet")
def test_r44_the_new_label_still_needs_a_reason():
    candidate = DesignCandidateReference("cand-b43n")
    with pytest.raises(InvalidScientificProblem, match="reason"):
        DesignEvaluation(
            evaluation_id="eval-b43n", candidate=candidate, twin=D.TWIN_A, design_space=D.SPACE,
            result=D._result("result-b43n", 1000.0, 1.0, candidate=candidate, twin=D.TWIN_A),
            eligibility=_ranked_without_assessment(), eligibility_reasons=())


# ---------------------------------------------------------------------------
# an_archive_says_which_members_were_ranked_unassessed
# ---------------------------------------------------------------------------
def _unassessed_pair():
    return (
        D._evaluation("b43a", D.TWIN_A, 1000.0, 1.0, eligibility=_ranked_without_assessment()),
        D._evaluation("b43b", D.TWIN_B, 900.0, 2.0, eligibility=_ranked_without_assessment()),
    )


@pytest.mark.xfail(strict=True, reason="R-44 finding 84: a persisted archive carries no statement about what it ranked without assessment")
def test_r44_an_archive_records_the_members_it_ranked_without_assessment():
    evaluations = _unassessed_pair()
    archive = ParetoArchive.build(archive_id="arch-b43", design_space=D.SPACE,
                                  objectives=(D.RANGE, D.MASS), evaluations=evaluations)
    assert archive.members, "the ranking still happens: refusing would delete the study, not correct it"
    assert tuple(ref.evaluation_id for ref in _unassessed_field(archive)) == tuple(
        ref.evaluation_id for ref in archive.members), (
        "the archive does not say which of its members were ranked without assessment")
    payload = archive.to_dict()
    assert payload["unassessed"], payload
    assert ParetoArchive.from_dict(payload, evaluations=evaluations) == archive


@pytest.mark.xfail(strict=True, reason="R-44 finding 84: the same for the per-objective elite archive")
def test_r44_an_elite_archive_records_it_too():
    evaluations = _unassessed_pair()
    archive = ScopedEliteArchive.build(archive_id="elite-b43", scope_ref="scope-b43",
                                       design_space=D.SPACE, objectives=(D.RANGE, D.MASS),
                                       evaluations=evaluations)
    assert _unassessed_field(archive), "the elite archive does not say what it ranked"


@pytest.mark.xfail(strict=True, reason="R-44: the field does not exist yet")
def test_r44_an_archive_of_assessed_candidates_keeps_its_bytes():
    """The control: the field is written only when it carries information."""
    evaluations = (D._evaluation("b43c", D.TWIN_C, 1000.0, 1.0),
                   D._evaluation("b43d", D.TWIN_D, 900.0, 2.0))
    archive = ParetoArchive.build(archive_id="arch-b43-ok", design_space=D.SPACE,
                                  objectives=(D.RANGE, D.MASS), evaluations=evaluations)
    assert _unassessed_field(archive) == ()
    assert "unassessed" not in archive.to_dict()


# ---------------------------------------------------------------------------
# the_studies_say_what_they_are_doing
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-44 finding 84 as audited: the multirotor studies mark every evaluation ELIGIBLE although every result records validity_not_assessed for both models")
def test_r44_the_reference_study_declares_what_it_did_not_assess():
    """MVR0's two models are reference identities with no ValidityDomain, and its results say so."""
    from engcore.systems.aerospace.multirotor.reference import run_reference_study

    run = run_reference_study(count=4, attempt_budget=16)
    assert run.evaluations
    for evaluation in run.evaluations:
        assert evaluation.result.validity_not_assessed, "the premise: nothing assessed these models"
        assert evaluation.eligibility is _ranked_without_assessment(), (
            f"the study claims {evaluation.eligibility.value!r} over a result that records "
            f"validity_not_assessed for every model it names")
