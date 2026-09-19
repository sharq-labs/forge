"""Adapter from claims held-out discrepancy evidence into scoped Core model-form UQ."""

from __future__ import annotations
from dataclasses import dataclass
from ..uq.model_form import (ModelFormEstimate,ModelFormPolicy,ModelFormScope,ModelFormStudy,
    ModelResidualObservation,PromotionReport,assess_promotion,evaluate_model_form_study)
from .analysis.model_discrepancy import ModelFormDiscrepancyEstimate
from .measurement_dataset import DatasetSplit

@dataclass(frozen=True)
class ModelFormPromotionAttempt:
    estimate:ModelFormEstimate
    promotion:PromotionReport

def evaluate_discrepancy_for_model_form(discrepancy:ModelFormDiscrepancyEstimate,*,
        scope:ModelFormScope,policy:ModelFormPolicy=ModelFormPolicy())->ModelFormPromotionAttempt:
    if scope.quantity!=discrepancy.quantity:
        raise ValueError("discrepancy quantity does not match model-form scope")
    observations=[]
    for point in discrepancy.points:
        if point.known_half_width is None: continue
        observations.append(ModelResidualObservation(
            point.observation_id,point.independence_group,discrepancy.quantity,point.units,
            point.residual,float(point.known_half_width),point.split is DatasetSplit.VALIDATION))
    estimate=evaluate_model_form_study(ModelFormStudy(tuple(observations),policy,scope))
    return ModelFormPromotionAttempt(estimate,assess_promotion(estimate,policy))
