from __future__ import annotations

from engcore.claims.analysis.model_discrepancy import (
    DiscrepancyEstimateStatus,DiscrepancyProtocol,ModelFormDiscrepancyEstimate,ResidualPoint,
)
from engcore.claims.measurement_dataset import DatasetSplit
from engcore.claims.model_form_uq import evaluate_discrepancy_for_model_form
from engcore.uq.model_form import ModelFormScope,ModelFormStatus,PromotionDecision

def scope():
    return ModelFormScope("model","a"*64,"b"*64,"c"*64,"temperature","kelvin")

def point(oid,group,split,residual,known):
    return ResidualPoint(oid,group,split,residual,known,max(0.0,abs(residual)-known),
                         abs(residual)+known,"kelvin",f"digest-{oid}",None)

def test_discrepancy_candidate_is_not_automatically_promoted_without_holdout_groups():
    discrepancy=ModelFormDiscrepancyEstimate(
        "temperature","kelvin",DiscrepancyProtocol("p",2,2),
        DiscrepancyEstimateStatus.CALIBRATED_UNVALIDATED,
        (point("c1","c1",DatasetSplit.CALIBRATION,3,1),
         point("c2","c2",DatasetSplit.CALIBRATION,4,1)),
        3,5,(),"no holdout")
    attempt=evaluate_discrepancy_for_model_form(discrepancy,scope=scope())
    assert attempt.estimate.status is ModelFormStatus.CALIBRATED_UNVALIDATED
    assert attempt.estimate.scope==scope()
    assert attempt.promotion.decision is PromotionDecision.REFUSED


def test_a_failed_discrepancy_validation_is_not_rescued_by_the_looser_coverage_test():
    # calibration |r|=4, known=1 -> candidate 3; validation |r|=6.5, known=0.5 -> excess 6.0.
    # The protocol fails it (6.0 > 4+1); the study's 2x coverage test alone would pass it (6.0 <= 6).
    discrepancy=ModelFormDiscrepancyEstimate(
        "temperature","kelvin",DiscrepancyProtocol("p",2,2),
        DiscrepancyEstimateStatus.FAILED_VALIDATION,
        (point("c1","c1",DatasetSplit.CALIBRATION,4,1),point("c2","c2",DatasetSplit.CALIBRATION,4,1),
         point("v1","v1",DatasetSplit.VALIDATION,6.5,0.5),point("v2","v2",DatasetSplit.VALIDATION,6.5,0.5)),
        3,5,("v1","v2"),"validation exceeds the calibration bound")
    attempt=evaluate_discrepancy_for_model_form(discrepancy,scope=scope())
    assert attempt.estimate.status is ModelFormStatus.FAILED_HOLDOUT and attempt.estimate.half_width is None
    assert attempt.promotion.decision is PromotionDecision.REFUSED
    assert "failed_validation" in attempt.estimate.reason


def test_a_point_of_unknown_uncertainty_is_never_dropped_to_let_the_rest_pass():
    discrepancy=ModelFormDiscrepancyEstimate(
        "temperature","kelvin",DiscrepancyProtocol("p",2,2),
        DiscrepancyEstimateStatus.INSUFFICIENT_UNCERTAINTY,
        (point("c1","c1",DatasetSplit.CALIBRATION,3,1),point("c2","c2",DatasetSplit.CALIBRATION,4,1),
         point("v1","v1",DatasetSplit.VALIDATION,2,1),
         ResidualPoint("v2","v2",DatasetSplit.VALIDATION,50.0,None,None,None,"kelvin","digest-v2",None)),
        None,None,(),"v2 has unknown uncertainty")
    attempt=evaluate_discrepancy_for_model_form(discrepancy,scope=scope())
    assert attempt.estimate.status is ModelFormStatus.INSUFFICIENT_DATA
    assert attempt.promotion.decision is PromotionDecision.REFUSED


def test_a_validated_candidate_with_an_unknown_point_uncertainty_fails_closed():
    import pytest

    discrepancy=ModelFormDiscrepancyEstimate(
        "temperature","kelvin",DiscrepancyProtocol("p",2,2),
        DiscrepancyEstimateStatus.VALIDATED_CANDIDATE,
        (point("c1","c1",DatasetSplit.CALIBRATION,3,1),point("c2","c2",DatasetSplit.CALIBRATION,4,1),
         ResidualPoint("v1","v1",DatasetSplit.VALIDATION,2.0,None,None,None,"kelvin","digest-v1",None)),
        3,5,(),"hand-built: the protocol never emits this")
    with pytest.raises(ValueError, match="cannot be dropped"):
        evaluate_discrepancy_for_model_form(discrepancy,scope=scope())
