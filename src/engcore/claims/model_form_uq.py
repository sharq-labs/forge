"""Adapter from claims held-out discrepancy evidence into Core model-form UQ.

The adapter preserves the existing fail-closed boundary: a discrepancy
candidate is not authoritative MODEL_FORM uncertainty on arrival. It must pass
the independent Core promotion policy first.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..uq.model_form import (
    ModelFormEstimate,
    ModelFormPolicy,
    ModelFormStudy,
    ModelResidualObservation,
    PromotionReport,
    assess_promotion,
    evaluate_model_form_study,
)
from .analysis.model_discrepancy import ModelFormDiscrepancyEstimate
from .measurement_dataset import DatasetSplit


@dataclass(frozen=True)
class ModelFormPromotionAttempt:
    estimate: ModelFormEstimate
    promotion: PromotionReport


def evaluate_discrepancy_for_model_form(
    discrepancy:ModelFormDiscrepancyEstimate,
    *,
    policy:ModelFormPolicy=ModelFormPolicy(),
)->ModelFormPromotionAttempt:
    observations=[]
    for point in discrepancy.points:
        if point.known_half_width is None:
            continue
        observations.append(
            ModelResidualObservation(
                observation_id=point.observation_id,
                independence_group=point.independence_group,
                quantity=discrepancy.quantity,
                units=point.units,
                residual=point.residual,
                known_uncertainty_half_width=float(point.known_half_width),
                held_out=point.split is DatasetSplit.VALIDATION,
            )
        )
    estimate=evaluate_model_form_study(ModelFormStudy(tuple(observations),policy))
    return ModelFormPromotionAttempt(estimate,assess_promotion(estimate,policy))
