from __future__ import annotations

from engcore.claims.analysis.model_discrepancy import (
    DiscrepancyEstimateStatus, DiscrepancyProtocol,
    ModelFormDiscrepancyEstimate, ResidualPoint,
)
from engcore.claims.measurement_dataset import DatasetSplit
from engcore.claims.model_form_uq import evaluate_discrepancy_for_model_form
from engcore.uq.model_form import ModelFormStatus, PromotionDecision


def point(oid, group, split, residual, known):
    return ResidualPoint(
        oid, group, split, residual, known,
        max(0.0, abs(residual)-known), abs(residual)+known,
        "kelvin", f"digest-{oid}", None,
    )


def test_discrepancy_candidate_is_not_automatically_promoted_without_holdout_groups():
    discrepancy = ModelFormDiscrepancyEstimate(
        "temperature",
        "kelvin",
        DiscrepancyProtocol("p", 2, 2),
        DiscrepancyEstimateStatus.CALIBRATED_UNVALIDATED,
        (
            point("c1","c1",DatasetSplit.CALIBRATION,3.0,1.0),
            point("c2","c2",DatasetSplit.CALIBRATION,4.0,1.0),
        ),
        3.0,
        5.0,
        (),
        "no holdout",
    )
    attempt = evaluate_discrepancy_for_model_form(discrepancy)
    assert attempt.estimate.status is ModelFormStatus.CALIBRATED_UNVALIDATED
    assert attempt.promotion.decision is PromotionDecision.REFUSED
