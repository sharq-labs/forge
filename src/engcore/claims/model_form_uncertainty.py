"""Authoritative conversion from qualified model-form estimates to Core uncertainty."""

from __future__ import annotations

from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from ..scientific.units.quantity import Quantity, require_spread_unit
from ..uq.model_form import ModelFormEstimate, ModelFormPolicy
from ..uq.model_form.authority import AuthorityDecision, authorize_model_form
from ..uq.model_form.qualification import ProducerQualification


class ModelFormAuthorityError(ValueError):
    pass


def promote_model_form_interval(
    estimate:ModelFormEstimate,
    qualification:ProducerQualification,
    nominal:Quantity,
    *,
    policy:ModelFormPolicy=ModelFormPolicy(),
)->Uncertainty:
    authority=authorize_model_form(estimate,qualification,policy)
    if authority.decision is not AuthorityDecision.AUTHORIZED:
        raise ModelFormAuthorityError("; ".join(authority.reasons))
    if estimate.half_width is None:
        raise ModelFormAuthorityError("authorized estimate unexpectedly has no interval half-width")
    spread_unit=require_spread_unit(estimate.units,context="model-form interval half-width")
    center=nominal.to(estimate.units)
    half=Quantity(estimate.half_width,spread_unit).magnitude_as_spread_in(estimate.units)
    lower=Quantity(center.magnitude-half,estimate.units)
    upper=Quantity(center.magnitude+half,estimate.units)
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=lower,
        upper=upper,
        source=f"{qualification.producer_id}:{qualification.method_id}",
        method="qualified held-out model-form discrepancy interval",
        notes=(
            f"empirical holdout coverage={estimate.empirical_holdout_coverage}; "
            f"producer validation={qualification.validation_digest}; "
            f"independent review={qualification.independent_review_digest}"
        ),
        source_kind=UncertaintySource.MODEL_FORM,
    )
