"""Scientific core audit 2026-09-16, batch 3a: verification is not validation, and unknowns are not passes.

Findings CORE-008, CORE-013 and CORE-015 (docs/audits/CORE_SCIENTIFIC_AUDIT_2026-09-16.md), under
benchmarks/core_v4_false_confidence/BATCH3_THRESHOLD_PROTOCOL.json. Recorded as strict xfails before the fix.
"""

from __future__ import annotations

import pytest

from engcore.scientific.experiments import EvaluationStatus, ExperimentBudget, ScientificEvaluation, ScientificExperiment
from engcore.scientific.models.definition import RangeCondition, ValidityDomain
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.validation import ValidationCheck, ValidationLevel, ValidationOutcome, ValidationReport
from engcore.scientific.units.quantity import Quantity

from test_scientific_core import build_algebraic_problem

AUDITED = pytest.mark.xfail(strict=True, reason="reproduced before batch 3a; fixed in batch 3a")

CONVERGED = ValidationCheck("mesh_convergence", ValidationOutcome.PASS, establishes=ValidationLevel.NUMERICALLY_CONVERGED,
                            residual=1e-4, tolerance=1e-3)
NEVER_RAN = ValidationCheck("experimental_comparison", ValidationOutcome.NOT_RUN, detail="no data")


# ---------------------------------------------------------------------------
# CORE-013: one PASS outvoted a check that never ran
# ---------------------------------------------------------------------------
@AUDITED
def test_core013_a_report_with_a_check_that_never_ran_is_not_a_pass():
    report = ValidationReport(checks=(CONVERGED, NEVER_RAN))
    assert report.status is ValidationOutcome.NOT_RUN
    assert report.to_dict()["status"] == "not_run"
    assert ValidationReport.from_dict(report.to_dict()).status is ValidationOutcome.NOT_RUN


def test_core013_a_failure_still_dominates_and_a_clean_report_still_passes():
    failed = ValidationCheck("balance", ValidationOutcome.FAIL, residual=1.0, tolerance=1e-3)
    assert ValidationReport(checks=(CONVERGED, NEVER_RAN, failed)).status is ValidationOutcome.FAIL
    assert ValidationReport(checks=(CONVERGED,)).status is ValidationOutcome.PASS


# ---------------------------------------------------------------------------
# CORE-008: verification alone read as support
# ---------------------------------------------------------------------------
@AUDITED
def test_core008_a_report_says_when_its_evidence_is_verification_only():
    assert ValidationReport(checks=(CONVERGED,)).evidence_basis == "VERIFICATION_ONLY"
    assert ValidationReport(checks=()).evidence_basis == "NONE"
    assert ValidationReport(checks=(CONVERGED,)).to_dict()["evidence_basis"] == "VERIFICATION_ONLY"


# ---------------------------------------------------------------------------
# CORE-015: an unassessed candidate ranked best
# ---------------------------------------------------------------------------
_DOMAIN = ValidityDomain(conditions=(RangeCondition("T", minimum=Quantity(250, "kelvin"), maximum=Quantity(400, "kelvin")),))


def _evaluation(index, load, validity):
    problem = build_algebraic_problem()
    constraint = problem.constraints[0]
    model = ("synthetic.linear_response", "1.0.0")
    extra = ({"validity": {model[0]: validity}} if validity is not None
             else {"validity_not_assessed": {model[0]: "a candidate nothing asked about"}})
    result = ScientificResult(result_id=f"res-{index}", values={"load": Quantity(load, "watt")},
                              provenance=ProvenanceRecord(run_id=f"run-{index}", models=(model,)), models=(model,),
                              validation=ValidationReport(checks=(CONVERGED,)), **extra)
    return ScientificEvaluation(evaluation_id=f"eval-{index}", candidate={}, status=EvaluationStatus.OK, result=result,
                                objective_values={"minimize_load": Quantity(load, "watt")},
                                constraint_checks=(constraint.check(Quantity(0.1, "ampere")),))


@AUDITED
def test_core015_an_unassessed_or_unknown_candidate_is_never_best():
    experiment = ScientificExperiment("exp-core015", build_algebraic_problem(), ExperimentBudget(max_observations=5))
    experiment.record(_evaluation(1, 5.0, _DOMAIN.assess({"T": Quantity(300, "kelvin")})))  # IN_DOMAIN
    experiment.record(_evaluation(2, 1.0, _DOMAIN.assess({})))  # UNKNOWN, and the lowest load
    experiment.record(_evaluation(3, 0.5, None))  # not assessed, lower still
    best = experiment.best("minimize_load")
    assert best is not None and best.evaluation_id == "eval-1"


@AUDITED
def test_core015_no_established_candidate_means_no_best():
    experiment = ScientificExperiment("exp-core015b", build_algebraic_problem(), ExperimentBudget(max_observations=5))
    experiment.record(_evaluation(1, 1.0, _DOMAIN.assess({})))
    assert experiment.best("minimize_load") is None
