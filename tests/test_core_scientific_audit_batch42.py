"""Core re-audit 2026-09-16, batch 42: selection ranks only candidates whose declared constraints were checked.

Problems R-41 (the audit's findings 48 and 100) and R-42 (finding 49), improvement I-21 part A of two, under
benchmarks/core_v4_false_confidence/BATCH42_THRESHOLD_PROTOCOL.json.

CORE-015 is recorded as FIXED with "declared constraints checked and satisfied", and the code checks
`all(check.satisfied)` over whatever checks an evaluation happens to carry: `all()` over an empty or unrelated
set is True. And the guard that stops a candidate being ranked on a number its own result contradicts looks
the result up by the OBJECTIVE's name, while an objective names its quantity through `metric`.

Recorded as strict xfails in commit 919f3981, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import copy

import pytest

import tests.test_scientific_core as C
from engcore.scientific.errors import InvalidScientificProblem, ScientificCoreError
from engcore.scientific.experiments import (
    EvaluationStatus,
    ExperimentBudget,
    ScientificEvaluation,
    ScientificExperiment,
)
from engcore.scientific.ir.constraints import (
    ConstraintCheck,
    ConstraintDefinition,
    ConstraintOperator,
)
from engcore.scientific.units import Quantity

WATT = "watt"
AMPERE = "ampere"


def _problem():
    return C.build_algebraic_problem()


def _declared():
    return _problem().constraints[0]


def _honest_check(value=0.1):
    return _declared().check(Quantity(value, AMPERE))


def _evaluation(index, load, *, checks=None, result_load=None, assessed=True):
    """An OK evaluation whose result is assessed IN_DOMAIN, so only this batch's rules can exclude it."""
    from engcore.scientific.models.definition import RangeCondition, ValidityDomain

    domain = ValidityDomain(conditions=(RangeCondition("drive_level", maximum=Quantity(10.0, "volt")),))
    established = {}
    if assessed:
        established = {
            "validity_not_assessed": {},
            "validity": {"synthetic.linear_response": domain.assess({"drive_level": Quantity(5.0, "volt")})},
        }
    values = {"load": Quantity(load if result_load is None else result_load, WATT),
              "response": Quantity(0.1, AMPERE)}
    result = C._result(result_id=f"res-b42-{index}", values=values, **established)
    return ScientificEvaluation(
        evaluation_id=f"eval-b42-{index}",
        candidate={"drive_level": Quantity(5.0, "volt"), "scale_factor": Quantity(100.0, "ohm")},
        status=EvaluationStatus.OK,
        result=result,
        objective_values={"minimize_load": Quantity(load, WATT)},
        constraint_checks=(_honest_check(),) if checks is None else checks,
    )


def _experiment(*evaluations, constraints=None):
    experiment = ScientificExperiment("exp-b42", _problem(), ExperimentBudget(max_observations=9),
                                      constraints=constraints)
    for evaluation in evaluations:
        experiment.record(evaluation)
    return experiment


def _two_constraint_problem():
    """The audited study: two declared constraints, one of which a candidate never checks."""
    import dataclasses

    problem = _problem()
    extra = ConstraintDefinition(name="load_ceiling", metric="load",
                                 operator=ConstraintOperator.LESS_EQUAL, bound=Quantity(100.0, WATT))
    return dataclasses.replace(problem, constraints=(*problem.constraints, extra)), extra


# ---------------------------------------------------------------------------
# a_check_agrees_with_its_own_margin
# ---------------------------------------------------------------------------
def test_r41_an_honest_check_is_unchanged():
    check = _honest_check()
    assert check.satisfied is True and check.margin.magnitude > 0.0
    assert ConstraintCheck.from_dict(check.to_dict()) == check


def test_r41_a_satisfied_verdict_beside_a_negative_margin_is_refused():
    """The audited forgery: satisfied=True with margin -2.5 A survived a round trip and won."""
    with pytest.raises((ScientificCoreError, InvalidScientificProblem), match="margin"):
        ConstraintCheck(constraint="response_ceiling", satisfied=True,
                        margin=Quantity(-2.5, AMPERE), value=Quantity(3.0, AMPERE))


def test_r41_a_violated_verdict_beside_a_positive_margin_is_refused():
    with pytest.raises((ScientificCoreError, InvalidScientificProblem), match="margin"):
        ConstraintCheck(constraint="response_ceiling", satisfied=False,
                        margin=Quantity(0.4, AMPERE), value=Quantity(0.1, AMPERE))


def test_r41_a_truthy_verdict_is_not_a_verdict():
    with pytest.raises((ScientificCoreError, InvalidScientificProblem)):
        ConstraintCheck(constraint="response_ceiling", satisfied=1,
                        margin=Quantity(0.4, AMPERE), value=Quantity(0.1, AMPERE))


def test_r41_a_zero_margin_is_accepted_either_way():
    """The control: at exactly the limit a non-strict operator is satisfied and a strict one is not."""
    for verdict in (True, False):
        ConstraintCheck(constraint="response_ceiling", satisfied=verdict,
                        margin=Quantity(0.0, AMPERE), value=Quantity(0.5, AMPERE))


def test_r41_the_forged_check_cannot_be_read_back_either():
    payload = _honest_check().to_dict()
    payload["margin"] = Quantity(-2.5, AMPERE).to_dict()
    with pytest.raises((ScientificCoreError, InvalidScientificProblem), match="margin"):
        ConstraintCheck.from_dict(payload)


# ---------------------------------------------------------------------------
# a_feasible_candidate_checked_every_declared_constraint
# ---------------------------------------------------------------------------
def test_r41_a_candidate_that_checked_one_of_two_declared_constraints_is_not_best():
    problem, extra = _two_constraint_problem()
    # One study narrows to the constraint the candidate checked; the other declares both.
    experiment = ScientificExperiment("exp-b42-two", problem, ExperimentBudget(max_observations=9),
                                      constraints=(problem.constraints[0],))
    both = ScientificExperiment("exp-b42-both", problem, ExperimentBudget(max_observations=9),
                                constraints=(problem.constraints[0], extra))
    candidate = _evaluation(1, 2.0)
    experiment.record(candidate)
    both.record(_evaluation(1, 2.0))
    assert experiment.best("minimize_load") is candidate, "the one-constraint study is unaffected"
    assert both.best("minimize_load") is None, (
        "a candidate that checked 'response_ceiling' and never evaluated the declared 'load_ceiling' "
        "is ranked as feasible")


def test_r41_a_check_naming_an_undeclared_constraint_does_not_make_a_candidate_feasible():
    forged = ConstraintCheck(constraint="some_other_ceiling", satisfied=True,
                             margin=Quantity(1.0, AMPERE), value=Quantity(0.1, AMPERE))
    experiment = _experiment(_evaluation(2, 2.0, checks=(forged,)))
    assert experiment.best("minimize_load") is None, (
        "a check on a name the study does not declare counted as feasibility")


def test_r41_a_duplicate_check_of_one_constraint_does_not_cover_the_others():
    experiment = _experiment(_evaluation(3, 2.0, checks=(_honest_check(), _honest_check(0.2))))
    assert experiment.best("minimize_load") is None


def test_r41_the_check_is_re_derived_from_the_result_where_the_metric_is_there():
    """A check whose verdict the result contradicts: response 3 A against a declared 0.5 A ceiling."""
    stale = ConstraintCheck(constraint="response_ceiling", satisfied=True,
                            margin=Quantity(0.4, AMPERE), value=Quantity(0.1, AMPERE))
    evaluation = _evaluation(4, 2.0, checks=(stale,))
    evaluation = ScientificEvaluation(
        evaluation_id=evaluation.evaluation_id, candidate=dict(evaluation.candidate),
        status=EvaluationStatus.OK,
        result=C._result(result_id="res-b42-4",
                         values={"load": Quantity(2.0, WATT), "response": Quantity(3.0, AMPERE)},
                         validity_not_assessed={},
                         validity=evaluation.result.validity),
        objective_values=dict(evaluation.objective_values), constraint_checks=(stale,))
    assert _experiment(evaluation).best("minimize_load") is None, (
        "the stored verdict stood while the result the study holds says the constraint is violated")


def test_r41_a_satisfied_candidate_is_still_best():
    """The control: the rules exclude candidates, they do not exclude every candidate."""
    experiment = _experiment(_evaluation(5, 5.0), _evaluation(6, 2.0), _evaluation(7, 9.0))
    best = experiment.best("minimize_load")
    assert best is not None and best.evaluation_id == "eval-b42-6"


# ---------------------------------------------------------------------------
# a_missing_declaration_is_not_a_narrowing_to_nothing
# ---------------------------------------------------------------------------
def test_r41_a_payload_with_no_constraints_key_is_refused():
    payload = copy.deepcopy(_experiment(_evaluation(8, 2.0)).to_dict())
    assert "constraints" in payload
    del payload["constraints"]
    with pytest.raises(ScientificCoreError, match="constraints"):
        ScientificExperiment.from_dict(payload)


def test_r41_a_payload_with_no_objectives_key_is_refused():
    payload = copy.deepcopy(_experiment(_evaluation(9, 2.0)).to_dict())
    del payload["objectives"]
    with pytest.raises(ScientificCoreError, match="objectives"):
        ScientificExperiment.from_dict(payload)


def test_r41_an_explicitly_empty_declaration_still_means_what_it_says():
    """The control: an empty list is a deliberate narrowing and keeps working."""
    payload = copy.deepcopy(_experiment(_evaluation(10, 2.0)).to_dict())
    payload["constraints"] = []
    read = ScientificExperiment.from_dict(payload)
    assert read.constraints == ()


def test_r41_a_round_trip_is_unchanged():
    experiment = _experiment(_evaluation(11, 2.0))
    read = ScientificExperiment.from_dict(experiment.to_dict())
    assert read.to_dict() == experiment.to_dict()


# ---------------------------------------------------------------------------
# a_candidate_is_ranked_on_the_metric_its_objective_names
# ---------------------------------------------------------------------------
def test_r42_ranking_on_a_value_the_result_contradicts_is_refused():
    """The audited case: objective 0.001 W ranked best while the result carries load = 50 W."""
    experiment = _experiment(_evaluation(12, 0.001, result_load=50.0))
    with pytest.raises(ScientificCoreError, match="load"):
        experiment.best("minimize_load")


def test_r42_agreement_within_roundoff_is_still_agreement():
    experiment = _experiment(_evaluation(13, 2.0, result_load=2.0 * (1.0 + 1.0e-12)))
    assert experiment.best("minimize_load").evaluation_id == "eval-b42-13"


def test_r42_a_result_that_does_not_carry_the_metric_is_ranked_on_its_objective():
    """The control: the rule reaches as far as the record does and no further."""
    evaluation = _evaluation(14, 2.0)
    without = ScientificEvaluation(
        evaluation_id="eval-b42-14", candidate=dict(evaluation.candidate), status=EvaluationStatus.OK,
        result=C._result(result_id="res-b42-14", values={"response": Quantity(0.1, AMPERE)},
                         uncertainty={}, validity_not_assessed={}, validity=evaluation.result.validity),
        objective_values={"minimize_load": Quantity(2.0, WATT)},
        constraint_checks=(_honest_check(),))
    assert _experiment(without).best("minimize_load") is without


def test_r41_an_extra_check_on_an_undeclared_constraint_is_refused_on_its_own():
    """ADDED while running batch 42's guard mutations, not preregistered.

    B42f removes the undeclared-name rule and the preregistered reproduction still excluded its candidate,
    because that candidate's forged check REPLACED the declared one and the coverage rule caught it. The case
    only this rule sees is a candidate that checked everything declared and carries one more check besides:
    a verdict on a name nothing in the study is judging candidates against, riding along inside the record.
    """
    extra = ConstraintCheck(constraint="some_other_ceiling", satisfied=True,
                            margin=Quantity(1.0, AMPERE), value=Quantity(0.1, AMPERE))
    experiment = _experiment(_evaluation(15, 2.0, checks=(_honest_check(), extra)))
    assert experiment.best("minimize_load") is None
