"""The end-to-end study: calibrate, quantify, predict unseen data, decide.

This is the orchestration layer. It imports ``inference``, ``uq`` and
``adequacy``, and nothing imports it -- which is what keeps the arrow pointing
down into ``adequacy`` rather than the other way.

The four statements it keeps apart
-----------------------------------
Each has its own vocabulary, and none of them is allowed to stand in for
another:

    CALIBRATION_CONVERGED / CALIBRATION_FAILED      did the search succeed
    PARAMETERS_IDENTIFIABLE / WEAKLY / NOT          does the data determine them
    HELD_OUT_VALIDATION_PASS / FAIL                 does it predict unseen data
    UNCERTAINTY_CALIBRATED / UNDER / OVERCOVERS     are the intervals honest
      / COVERAGE_INCONCLUSIVE                       (or is there too little evidence to say)

A study can, and in the misspecified case does, report CONVERGED and
IDENTIFIABLE and still FAIL held-out validation. That combination is the point
of the exercise, not an inconsistency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from ..adequacy.predictive import assess_predictive_observation
from ..domains.electrical import material as _material
from ..inference.admissibility import InferenceAdmissibilityError
from ..inference.calibration import (
    CalibrationResult,
    CalibrationStatus,
    IdentifiabilityReport,
    IdentifiabilityStatus,
    assess_identifiability,
)
from ..inference.grid import (
    InferenceProblemError,
    ObservationSet,
    PosteriorGrid,
    gaussian_grid_posterior,
)
from ..inference.split import (
    ObservationSplit,
    _require_posterior_conditioned_on_calibration,
    require_split,
)
from ..scientific.models.definition import ValidityStatus
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity
# I-03 (R-02): `posterior_predictive_uq` is no longer imported here. The study reached the frozen
# call directly, which is exactly why no V2 evidence gate ran on the one path that ships; it now
# goes through `hybrid_uq.grid_predictive_uncertainty`, which computes the same frozen call under
# the router's own judgement (see `_routed`).
from ..uq.predictive import PredictiveObservableSpec
from .tcr import (
    CONDITION_TEMPERATURE,
    KELVIN,
    OHM,
    PER_KELVIN,
    TCR_MODEL_REF,
    build_tcr_parameter_set,
    tcr_forward_table,
    tcr_validity_at,
)

#: Stated, not implied. The predictive interval this study reports combines
#: PARAMETER uncertainty and MEASUREMENT noise and nothing else. No
#: model-discrepancy term is fitted, assumed or absorbed into either, so a
#: model that is systematically wrong shows up as held-out failure rather than
#: as a quietly inflated sigma that makes the failure disappear.
MODEL_DISCREPANCY_NOT_MODELLED = "MODEL_DISCREPANCY_NOT_MODELLED"

PARAMETER_UNCERTAINTY = "PARAMETER_UNCERTAINTY"
MEASUREMENT_UNCERTAINTY = "MEASUREMENT_UNCERTAINTY"

#: The three sources, named individually, in every result this module returns.
UNCERTAINTY_SOURCES = (
    PARAMETER_UNCERTAINTY,
    MEASUREMENT_UNCERTAINTY,
    MODEL_DISCREPANCY_NOT_MODELLED,
)


class HeldOutValidation(str, Enum):
    PASS = "HELD_OUT_VALIDATION_PASS"
    FAIL = "HELD_OUT_VALIDATION_FAIL"
    #: I-03 part B (R-35): the test could not have found the misspecification a reader would care
    #: about, so absence of rejection is not validation.
    #:
    #: Only PASS and FAIL existed, with FAIL below alpha 0.01 and PASS otherwise -- so ONE held-out
    #: point with a standardized residual of 2.11 read "consistent with the model's own predictive
    #: distribution". Measured over the production TCR pipeline: a linear model fitted to curved
    #: truth PASSED in 24 of 40 seeds at n = 1 and 12 of 40 at n = 3, at a mean standardized
    #: residual of about 2.3 on every point. A new member rather than a renamed one, because the
    #: two existing values are what every consumer and every stored record reads.
    INCONCLUSIVE = "HELD_OUT_VALIDATION_INCONCLUSIVE"


class CoverageVerdict(str, Enum):
    CALIBRATED = "UNCERTAINTY_CALIBRATED"
    UNDERCOVERS = "UNCERTAINTY_UNDERCOVERS"
    OVERCOVERS = "UNCERTAINTY_OVERCOVERS"
    #: INF-05: the Wilson interval neither lies inside the acceptance band nor
    #: wholly outside it -- too little evidence to call the intervals honest or
    #: dishonest. Used to be reported as CALIBRATED (1 covered of 2 was).
    INCONCLUSIVE = "UNCERTAINTY_COVERAGE_INCONCLUSIVE"


@dataclass(frozen=True)
class PredictiveDecomposition:
    """One held-out condition's prediction, with its uncertainty taken apart.

    ``parameter_*`` is what posterior uncertainty in the parameters alone
    implies about the latent model mean. ``total_*`` adds the declared
    independent measurement noise. They are separate fields because collapsing
    them into one sigma destroys the only information that says WHICH of the
    two a wide interval came from -- and the remedies differ: more data narrows
    the first and does nothing to the second.
    """

    condition_id: str
    observation_key: str
    central: Quantity
    parameter_sigma: Quantity
    parameter_lower: Quantity
    parameter_upper: Quantity
    observation_sigma: Quantity
    total_sigma: Quantity
    total_lower: Quantity
    total_upper: Quantity
    confidence_level: float
    sources: tuple[str, ...] = UNCERTAINTY_SOURCES
    #: I-03 (R-02): the V2 route claim this statement earned, and why (`RouteClaim`/`RouteReason`
    #: values). Empty on a record built before this batch. Every evidence gate the 2026-09-16 audit
    #: built lives in `engcore.hybrid_uq`, which had no caller in `src` outside its own package --
    #: so this study, the only production orchestration that turns a calibration into predictive
    #: intervals, ran none of them. It routes through the V2 record now, and carries what that
    #: record says about itself.
    route_claim: str = ""
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "observation_key": self.observation_key,
            "central": self.central.to_dict(),
            "parameter_uncertainty": {
                "standard": self.parameter_sigma.to_dict(),
                "lower": self.parameter_lower.to_dict(),
                "upper": self.parameter_upper.to_dict(),
            },
            "measurement_uncertainty": {"sigma": self.observation_sigma.to_dict()},
            "total": {
                "standard": self.total_sigma.to_dict(),
                "lower": self.total_lower.to_dict(),
                "upper": self.total_upper.to_dict(),
            },
            "confidence_level": self.confidence_level,
            "uncertainty_sources": list(self.sources),
            "model_discrepancy": MODEL_DISCREPANCY_NOT_MODELLED,
            # I-03: written only when there is something to say, so a record produced before this
            # batch keeps its bytes.
            **({"route_claim": self.route_claim} if self.route_claim else {}),
            **({"reasons": list(self.reasons)} if self.reasons else {}),
        }


@dataclass(frozen=True)
class HeldOutMetrics:
    """What the model did on evidence it was never fitted to."""

    n: int
    rmse: float
    mae: float
    standardized_residuals: tuple[float, ...]
    mean_log_predictive_density: float
    covered: int
    coverage_fraction: float
    nominal_coverage: float
    chi_square: float
    chi_square_p_value: float
    verdict: HeldOutValidation
    why: str
    heldout_dataset_id: str
    posterior_dataset_id: str
    #: I-03 (R-02): the V2 route claim the predictive statements behind this verdict earned, and
    #: why. See :class:`PredictiveDecomposition`. The verdict WORD is unchanged by it -- there is no
    #: third word yet, and adding one is I-03's part B (R-35) -- so this is recorded beside the
    #: verdict rather than folded into it.
    route_claim: str = ""
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "rmse": self.rmse,
            "mae": self.mae,
            "standardized_residuals": list(self.standardized_residuals),
            "mean_log_predictive_density": self.mean_log_predictive_density,
            "covered": self.covered,
            "coverage_fraction": self.coverage_fraction,
            "nominal_coverage": self.nominal_coverage,
            "chi_square": self.chi_square,
            "chi_square_p_value": self.chi_square_p_value,
            "verdict": self.verdict.value,
            "why": self.why,
            "heldout_dataset_id": self.heldout_dataset_id,
            "posterior_dataset_id": self.posterior_dataset_id,
            "model_discrepancy": MODEL_DISCREPANCY_NOT_MODELLED,
            **({"route_claim": self.route_claim} if self.route_claim else {}),
            **({"reasons": list(self.reasons)} if self.reasons else {}),
        }


#: Declared BEFORE any result was seen. A held-out set whose standardized
#: residuals are this unlikely under the model's own predictive distribution is
#: evidence against the model, not noise.
HELD_OUT_CHI_SQUARE_ALPHA = 0.01

#: I-03 part B (R-35): the level EACH of the two held-out tests runs at, so the family-wise
#: false-rejection rate stays at or below the 0.01 above.
#:
#: Two tests now look at the held-out residuals -- the omnibus chi-square, and a direct test of
#: their mean. Running both at the declared alpha would give a union rate of up to twice it, so each
#: runs at half. Bonferroni rather than anything sharper because the two statistics are not
#: independent and a correction that assumed they were would claim a level it does not have. The
#: declared constant above does not change value; this is derived from it.
HELD_OUT_PER_TEST_ALPHA = HELD_OUT_CHI_SQUARE_ALPHA / 2.0

#: I-03 part B (R-35): below this many held-out points the verdict is INCONCLUSIVE.
#:
#: DERIVED from the alpha above, and no new number. The effect size of interest is a common bias of
#: ONE declared sigma per held-out point: below its own declared measurement noise a model is not
#: wrong in any way this evidence can speak to. The mean-residual test has |E z| = sqrt(n) at that
#: effect, so it finds it at better than even odds exactly when sqrt(n) >= z_{1 - alpha/2}, i.e.
#: n >= z^2. At alpha = 0.01, z_{0.995} = 2.575829 and z^2 = 6.6349, so the smallest integer n is 7.
#:
#: A FAIL is still a FAIL below the floor: a rejection is evidence whatever the sample size, and
#: withholding it would be the opposite error to the one this rule closes.
HELD_OUT_MINIMUM_N = 7

#: I-03 part B (R-38): what a coverage repetition's calibration status actually is.
#:
#: Every repetition recorded ``CALIBRATION_CONVERGED`` although it builds a grid posterior and no
#: optimizer runs and no convergence criterion is evaluated. Not a new ``CalibrationStatus`` member,
#: because that enum's own docstring is "Did the optimizer find a minimum": a value meaning no
#: optimizer ran is the ABSENCE of a calibration status rather than one of its members, and adding
#: it would make it a legal value for a ``CalibrationResult`` -- a record that must never claim it.
COVERAGE_CALIBRATION_STATUS = "CALIBRATION_NOT_RUN_GRID_POSTERIOR"


def held_out_verdict(
    *, standardized_residuals: Sequence[float]
) -> tuple[HeldOutValidation, str]:
    """The held-out verdict, as its own rule over the residuals and nothing else (I-03 part B, R-35).

    THREE ANSWERS, NOT TWO.

    * **FAIL** when either test rejects at :data:`HELD_OUT_PER_TEST_ALPHA`. Two tests, because the
      omnibus chi-square is a sum of SQUARES and is therefore blind to sign -- and a truncated
      expansion leaves a common-sign bias, which is exactly what the audit measured (a mean
      standardized residual of about 2.3 on every point). The second test reads that mean directly:
      under the null the standardized residuals have mean 0 and sd 1/sqrt(n), so
      ``z = sqrt(n) * mean(r)`` is standard normal.
    * **INCONCLUSIVE** below :data:`HELD_OUT_MINIMUM_N`: the tests could not have found a one-sigma
      common bias at better than even odds, so not rejecting is not evidence of anything. This is
      the defect the re-audit found -- absence of rejection reported as validation.
    * **PASS** otherwise, and the sentence says NOT REJECTED rather than "consistent with", because
      that is what a test that did not reject has established.

    A rejection outranks the floor: FAIL is issued at any n. A rejection is evidence whatever the
    sample size, and withholding it would be the opposite error to the one the floor closes.

    Its own function so that the rule is stated once, can be read at its boundary by a test, and is
    not entangled with the loop that computes the residuals.
    """
    from scipy.stats import chi2, norm

    residuals = tuple(float(r) for r in standardized_residuals)
    n = len(residuals)
    if n == 0:
        raise InferenceProblemError(
            "a held-out verdict needs held-out residuals; an empty set is not a pass"
        )
    chi_square = float(sum(r * r for r in residuals))
    chi_square_p = float(chi2.sf(chi_square, df=n))
    mean_residual = float(sum(residuals) / n)
    bias_z = float(math.sqrt(n) * mean_residual)
    bias_p = float(2.0 * norm.sf(abs(bias_z)))

    if chi_square_p < HELD_OUT_PER_TEST_ALPHA or bias_p < HELD_OUT_PER_TEST_ALPHA:
        which = []
        if chi_square_p < HELD_OUT_PER_TEST_ALPHA:
            which.append(
                f"the omnibus chi-square is {chi_square:.4g} on {n} degrees of freedom, "
                f"p = {chi_square_p:.3g}"
            )
        if bias_p < HELD_OUT_PER_TEST_ALPHA:
            which.append(
                f"the mean standardized residual is {mean_residual:.4g}, z = {bias_z:.4g}, "
                f"p = {bias_p:.3g} -- a common-sign bias, which a sum of squares cannot see"
            )
        return HeldOutValidation.FAIL, (
            f"{' and '.join(which)}, below the per-test alpha of {HELD_OUT_PER_TEST_ALPHA} (two "
            f"tests at half the declared {HELD_OUT_CHI_SQUARE_ALPHA}, so the family-wise rate is "
            f"the declared one). The model's own predictive distribution says data like this is "
            f"implausible, which is evidence against the model rather than noise"
        )
    if n < HELD_OUT_MINIMUM_N:
        return HeldOutValidation.INCONCLUSIVE, (
            f"{n} held-out point(s) is below the minimum of {HELD_OUT_MINIMUM_N}, which is where "
            f"the mean-residual test finds a common bias of one declared sigma per point at better "
            f"than even odds at alpha {HELD_OUT_CHI_SQUARE_ALPHA} (n >= z_(1-alpha/2)^2 = 6.6349). "
            f"Neither test rejected -- chi-square {chi_square:.4g} on {n} dof, p = "
            f"{chi_square_p:.3g}; mean residual {mean_residual:.4g}, p = {bias_p:.3g} -- but "
            f"neither had the power to have found it, so this is not validation"
        )
    return HeldOutValidation.PASS, (
        f"NOT REJECTED: chi-square {chi_square:.4g} on {n} degrees of freedom, p = "
        f"{chi_square_p:.3g}, and mean standardized residual {mean_residual:.4g}, z = "
        f"{bias_z:.4g}, p = {bias_p:.3g}; neither is below the per-test alpha of "
        f"{HELD_OUT_PER_TEST_ALPHA}. A test that did not reject has established that this evidence "
        f"is not against the model, which is weaker than saying the model is right"
    )


def _require_declared_sigma(
    split: ObservationSplit, observation_sigma: Quantity | None
) -> None:
    """INF-02: the noise a held-out score uses is each observation's DECLARED sigma.

    ``observation_sigma`` used to replace every held-out observation's own
    sigma, so a caller could widen the predictive distribution until a failing
    model passed (chi2 49.3, p 5e-10 at the declared 0.002 ohm; chi2 1.81 at a
    caller's 0.02 ohm). The parameter is kept for its callers, and it must now
    state the declared sigma: anything else is refused rather than used.

    **None is the right answer for a half that declares more than one sigma (I-03 part B, R-38).**
    The check compares ONE value with EVERY held-out observation's declared sigma, so a half
    declaring [0.002, 0.002, 0.003] ohm could not be predicted or validated with any single value --
    0.002 was refused by the 0.003 reading and 0.003 by the 0.002 ones -- and that lost a justified
    validation for nothing, because the per-observation loop already builds its spec from
    ``observation.sigma``. Omitted, the evidence's own sigmas are used and there is nothing to
    compare; given, this check is exactly what it was, because the argument is the only thing
    standing between a caller and a self-chosen noise level.
    """
    if observation_sigma is None:
        return
    if not isinstance(observation_sigma, Quantity):
        raise InferenceProblemError("observation_sigma must be a Quantity")
    given = observation_sigma.magnitude_in(OHM)
    for observation in split.held_out.observations:
        declared = observation.sigma.magnitude_in(OHM)
        if not math.isclose(given, declared, rel_tol=1.0e-12, abs_tol=0.0):
            raise InferenceProblemError(
                f"observation_sigma {given!r} ohm differs from the declared sigma "
                f"{declared!r} ohm of held-out observation {observation.key!r}. A "
                f"held-out score is computed with the measurement uncertainty the "
                f"evidence declares; a caller's sigma is not evidence, and a wider "
                f"one turns a failing model into a passing one"
            )


def _require_bound_and_applicable(
    posterior: PosteriorGrid,
    split: ObservationSplit,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    counter: dict[str, int] | None,
):
    """INF-03 and INF-01, before any held-out or predictive statement is made. Returns the calibration table.

    Content binding: the posterior must be the likelihood of this split's
    calibration half, recomputed through the production forward model over the
    posterior's own points -- not merely carry its dataset id.

    Applicability: the linear TCR model's own validity assessment, of the
    conductor the posterior's MAP estimate declares, at every condition of the
    split. A calibration sweep may leave candidates unassessed; a statement
    about the calibrated model at a declared condition may not. Anything but
    IN_DOMAIN is refused, so no PASS and no predictive interval is issued where
    the model has not been shown to apply.
    """
    calibration_table = tcr_forward_table(
        split.calibration,
        [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition,
        counter=counter,
    )
    _require_posterior_conditioned_on_calibration(split, posterior, calibration_table)

    expected = (_material.REFERENCE_RESISTANCE, _material.TEMPERATURE_COEFFICIENT)
    if tuple(posterior.parameter_names) != expected:
        raise InferenceProblemError(
            f"a TCR posterior's axes are {expected!r}, got {tuple(posterior.parameter_names)!r}"
        )
    r_ref, alpha = (float(v) for v in posterior.map_point)
    problems: list[str] = []
    seen: set[str] = set()
    for observation in (*split.calibration.observations, *split.held_out.observations):
        condition = observation.condition_id
        if condition in seen:
            continue
        seen.add(condition)
        temperature = temperatures_by_condition[condition]
        assessment = tcr_validity_at(
            reference_resistance=Quantity(r_ref, OHM),
            temperature_coefficient=Quantity(alpha, PER_KELVIN),
            reference_temperature=reference_temperature,
            temperature=temperature,
        )
        if assessment.status is not ValidityStatus.IN_DOMAIN:
            detail = list(assessment.violated) or list(assessment.unknown)
            problems.append(
                f"{condition} at {temperature.magnitude_in(KELVIN):g} K: "
                f"{assessment.status.value} {detail}"
            )
    if problems:
        raise InferenceAdmissibilityError(
            f"{TCR_MODEL_REF.model_id} is not shown to apply at the study's declared "
            f"conditions for the calibrated conductor (MAP R_ref={r_ref:.6g} ohm, "
            f"alpha={alpha:.6g} /K): {problems}. A held-out verdict or a predictive "
            f"interval there would be a statement about a model outside its "
            f"validated domain"
        )
    return calibration_table


def _routed(
    posterior: PosteriorGrid,
    predictive_table,
    spec: PredictiveObservableSpec,
    *,
    calibration: ObservationSet,
    forward,
    predict,
    twin: TwinReference,
    credible_mass: float,
):
    """One predictive quantity, through the V2 record rather than the frozen call (I-03, R-02).

    ``hybrid_uq.grid_predictive_uncertainty`` computes the SAME frozen ``posterior_predictive_uq``
    on the same inputs, and wraps it in the router's own judgement: the grid is held to the evidence
    it describes (CORE-005), the declared noise must explain the calibration residuals (CORE-001),
    the box must contain the posterior (CORE-002), equal node mass must be the declared prior
    (CORE-010), every mode must be resolved, and no admissibility cut may truncate it. A grid the
    router would not route RAISES here, where the study used to answer it with an interval.

    So the numbers this returns are the numbers the study always computed; what is new is the
    refusal where the judgement fails, and the claim and reasons where it does not.
    """
    from ..hybrid_uq import grid_predictive_uncertainty

    return grid_predictive_uncertainty(
        posterior, predictive_table, spec,
        twin=twin, model=TCR_MODEL_REF, source_ref=spec.observation_key,
        confidence_level=credible_mass,
        observations=calibration, forward=forward,
        # R-23 (I-13 part B): the table this study builds is checked against the forward model it was built
        # from, at the nodes the reported numbers stand on. Without it the record would say
        # PREDICTIVE_TABLE_NOT_CHECKED, which is the true statement about a table nobody compared with
        # anything -- and this study HAS the model, so there is nothing to withhold.
        predict=predict,
    )


def _predict_one(observations: ObservationSet, key: str, *, reference_temperature, temperatures_by_condition,
                 counter):
    """A one-output evaluator for R-23's table check: this prediction's value, from the production model."""
    index = list(observations.keys).index(key)
    evaluator = _forward_for(
        observations, reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition, counter=counter,
    )

    def predict(point):
        values = evaluator(point)
        return None if values is None else [values[index]]

    return predict


def _forward_for(
    observations: ObservationSet,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    counter: dict[str, int] | None,
):
    """The production forward evaluator the V2 binding check re-evaluates the grid through."""
    from .tcr import tcr_forward_evaluator

    return tcr_forward_evaluator(
        observations,
        reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition,
        counter=counter,
    )


def predict_held_out(
    posterior: PosteriorGrid,
    split: ObservationSplit,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    # I-03 part B (R-38): optional, so a held-out half whose readings declare
    # different sigmas can be validated at all. Given, INF-02's check is unchanged.
    observation_sigma: Quantity | None = None,
    twin: TwinReference,
    credible_mass: float = 0.95,
    counter: dict[str, int] | None = None,
) -> tuple[PredictiveDecomposition, ...]:
    """B1: one decomposed predictive interval per held-out condition.

    The predictive table is built over the SAME parameter support as the
    posterior -- the UQ layer refuses anything else -- but evaluated at the
    held-out conditions, which the posterior has never seen.

    Refused, before any interval is computed, when the posterior is not the
    calibration half's likelihood (INF-03), when ``observation_sigma`` is not
    the held-out observations' declared sigma (INF-02), or when the model is not
    IN_DOMAIN at the declared conditions (INF-01).
    """
    require_split(split)
    split.require_posterior_was_fitted_here(posterior.dataset_id)
    _require_declared_sigma(split, observation_sigma)
    _require_bound_and_applicable(
        posterior, split, reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition, counter=counter,
    )
    predictive_table = tcr_forward_table(
        split.held_out,
        [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition,
        counter=counter,
    )
    forward = _forward_for(
        split.calibration, reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition, counter=counter,
    )
    out: list[PredictiveDecomposition] = []
    for observation in split.held_out.observations:
        spec = PredictiveObservableSpec(
            observation_key=observation.key,
            unit=OHM,
            observation_sigma=observation.sigma,
            # I-03 part B: the operating point this prediction is AT, so CORE-006 can compare it
            # with the range the calibration covered instead of saying nothing.
            conditions={CONDITION_TEMPERATURE: temperatures_by_condition[observation.condition_id]},
        )
        # I-03 (R-02): through the V2 record. Every gate the audit built was in `hybrid_uq`, which
        # nothing in `src` called, so this study -- the only production path to a predictive
        # interval -- ran none of them.
        routed = _routed(
            posterior, predictive_table, spec,
            calibration=split.calibration, forward=forward,
            predict=_predict_one(
                split.held_out, observation.key, reference_temperature=reference_temperature,
                temperatures_by_condition=temperatures_by_condition, counter=counter),
            twin=twin, credible_mass=credible_mass,
        )
        out.append(
            PredictiveDecomposition(
                condition_id=observation.condition_id,
                observation_key=observation.key,
                central=Quantity(routed.mean, routed.unit),
                parameter_sigma=Quantity(routed.parameter_standard_uncertainty, routed.unit),
                parameter_lower=Quantity(routed.parameter_interval[0], routed.unit),
                parameter_upper=Quantity(routed.parameter_interval[1], routed.unit),
                observation_sigma=spec.observation_sigma,
                total_sigma=Quantity(routed.total_standard_uncertainty, routed.unit),
                total_lower=Quantity(routed.total_interval[0], routed.unit),
                total_upper=Quantity(routed.total_interval[1], routed.unit),
                confidence_level=routed.confidence_level,
                route_claim=routed.route_claim.value,
                reasons=tuple(reason.value for reason in routed.reasons),
            )
        )
    return tuple(out)


def validate_held_out(
    posterior: PosteriorGrid,
    split: ObservationSplit,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    # I-03 part B (R-38): optional, so a held-out half whose readings declare
    # different sigmas can be validated at all. Given, INF-02's check is unchanged.
    observation_sigma: Quantity | None = None,
    twin: TwinReference,
    credible_mass: float = 0.95,
    counter: dict[str, int] | None = None,
) -> HeldOutMetrics:
    """B2: score the held-out set, and only the held-out set.

    The calibration half is never touched here. The split refuses a posterior
    that was not conditioned on the calibration half, which is what stops this
    function from being handed the fitting data under a different label -- and,
    since a label is only a label, the posterior's log-likelihood must also BE
    the calibration half's likelihood (INF-03). The score uses each held-out
    observation's declared sigma (INF-02), and no verdict is issued where the
    model is not IN_DOMAIN at the declared conditions (INF-01).
    """
    require_split(split)
    split.require_posterior_was_fitted_here(posterior.dataset_id)
    _require_declared_sigma(split, observation_sigma)
    calibration_table = _require_bound_and_applicable(
        posterior, split, reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition, counter=counter,
    )

    predictive_table = tcr_forward_table(
        split.held_out,
        [tuple(float(v) for v in row) for row in posterior.points],
        reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition,
        counter=counter,
    )

    # I-03 (R-02): the V2 judgement, once, before any residual is scored. It raises for a grid the
    # router would not route -- a truncated box, a calibration the declared noise does not explain,
    # a non-uniform prior axis, an unresolved mode -- each of which the study used to answer with a
    # verdict. The claim and reasons it leaves are recorded on the metrics below.
    forward = _forward_for(
        split.calibration, reference_temperature=reference_temperature,
        temperatures_by_condition=temperatures_by_condition, counter=counter,
    )
    first = split.held_out.observations[0]
    routed = _routed(
        posterior, predictive_table,
        PredictiveObservableSpec(
            observation_key=first.key, unit=OHM, observation_sigma=first.sigma,
            # I-03 part B: as above. The first held-out condition stands for the set here, and the
            # per-observation records below each carry their own.
            conditions={CONDITION_TEMPERATURE: temperatures_by_condition[first.condition_id]},
        ),
        calibration=split.calibration, forward=forward,
        predict=_predict_one(
            split.held_out, first.key, reference_temperature=reference_temperature,
            temperatures_by_condition=temperatures_by_condition, counter=counter),
        twin=twin, credible_mass=credible_mass,
    )

    residuals: list[float] = []
    log_densities: list[float] = []
    errors: list[float] = []
    covered = 0
    for observation in split.held_out.observations:
        spec = PredictiveObservableSpec(
            observation_key=observation.key,
            unit=OHM,
            observation_sigma=observation.sigma,
        )
        assessment = assess_predictive_observation(
            posterior,
            predictive_table,
            spec,
            observation.value,
            twin=twin,
            model=TCR_MODEL_REF,
            source_ref=f"study:{split.heldout_dataset_id}",
            heldout_dataset_id=split.heldout_dataset_id,
            credible_mass=credible_mass,
            # CORE-007: bound by content, so these assessments can support a model comparison
            split=split,
            calibration_table=calibration_table,
        )
        residuals.append(assessment.standardized_residual)
        log_densities.append(assessment.log_predictive_density)
        errors.append(
            assessment.observed.magnitude_in(OHM)
            - assessment.predictive_mean.magnitude_in(OHM)
        )
        covered += 1 if assessment.covered_by_central_interval else 0

    n = len(residuals)
    error_array = np.asarray(errors, dtype=np.float64)
    chi_square = float(np.sum(np.asarray(residuals) ** 2))

    from scipy.stats import chi2

    p_value = float(chi2.sf(chi_square, df=n))
    # I-03 part B (R-35): the verdict is `held_out_verdict`'s, stated once and read here. The
    # omnibus chi-square and its p-value are still recorded on the metrics -- they are the numbers a
    # reader compares across studies -- but they are no longer the whole of the rule: a sum of
    # squares is blind to the common-sign bias a truncated expansion leaves, and neither test could
    # have found a one-sigma bias below HELD_OUT_MINIMUM_N points.
    verdict, why = held_out_verdict(standardized_residuals=residuals)

    return HeldOutMetrics(
        n=n,
        rmse=float(np.sqrt(np.mean(error_array**2))),
        mae=float(np.mean(np.abs(error_array))),
        standardized_residuals=tuple(residuals),
        mean_log_predictive_density=float(np.mean(log_densities)),
        covered=covered,
        coverage_fraction=covered / n if n else float("nan"),
        nominal_coverage=credible_mass,
        chi_square=chi_square,
        chi_square_p_value=p_value,
        verdict=verdict,
        why=why,
        heldout_dataset_id=split.heldout_dataset_id,
        posterior_dataset_id=posterior.dataset_id,
        # I-03: what the V2 judgement left. The verdict word above is unchanged by it; there is no
        # third word yet and adding one is part B (R-35).
        route_claim=routed.route_claim.value,
        reasons=tuple(reason.value for reason in routed.reasons),
    )


@dataclass(frozen=True)
class CoverageStudy:
    """B3: empirical interval coverage over repeated synthetic experiments."""

    repetitions: int
    intervals_evaluated: int
    nominal: float
    measured: float
    standard_error: float
    wilson_lower: float
    wilson_upper: float
    verdict: CoverageVerdict
    why: str
    seeds: tuple[int, ...]
    algorithm: str
    acceptance_half_width: float
    #: I-03 part B (R-36): the clustering this study measured in its own indicators, and what the
    #: interval was therefore computed at.
    #:
    #: Within one repetition every held-out interval shares ONE posterior, so the coverage
    #: indicators are not independent trials. The audit measured an intraclass correlation of 0.365
    #: and a design effect of 2.09 over 300 repetitions of 4 intervals -- the pooled Wilson interval
    #: overstated precision by about 1.45x, and verdicts near the band edges were wrong in both
    #: directions. Recorded rather than applied invisibly, so a reader can see the correction.
    #: ``intraclass_correlation`` is NaN when there is nothing to measure it from (one repetition,
    #: or one interval each).
    intervals_per_repetition: float = float("nan")
    intraclass_correlation: float = float("nan")
    design_effect: float = 1.0
    effective_sample_size: float = float("nan")
    #: How many repetitions the V2 evidence judgement refused, and what that does to the verdict.
    #: Part A recorded the fraction in `why`; part B makes it decide, against the study's own
    #: acceptance half-width (see `coverage_verdict_with_refusals`).
    refused_repetitions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "repetitions": self.repetitions,
            "intervals_evaluated": self.intervals_evaluated,
            "nominal_coverage": self.nominal,
            "measured_coverage": self.measured,
            "standard_error": self.standard_error,
            "wilson_95_interval": [self.wilson_lower, self.wilson_upper],
            "verdict": self.verdict.value,
            "why": self.why,
            "seeds": list(self.seeds),
            "algorithm": self.algorithm,
            "acceptance_half_width": self.acceptance_half_width,
            # I-03 part B: written unconditionally beside the rest. A coverage study record is
            # produced fresh by a run, and no stored one in this repository has bytes to keep.
            "clustering": {
                "intervals_per_repetition": self.intervals_per_repetition,
                "intraclass_correlation": self.intraclass_correlation,
                "design_effect": self.design_effect,
                "effective_sample_size": self.effective_sample_size,
            },
            "refused_repetitions": self.refused_repetitions,
        }


def coverage_design_effect(
    per_repetition: Sequence[tuple[int, int]]
) -> tuple[float, float, float]:
    """The intraclass correlation, the design effect and the effective sample size (I-03 part B, R-36).

    ``per_repetition`` is ``(covered, intervals)`` for each repetition.

    THE DEFECT. `run_coverage_study` summed covered and total over every interval of every
    repetition and handed them to a Wilson interval as independent Bernoulli trials. Within one
    repetition every interval shares ONE posterior, and at extrapolated conditions parameter
    uncertainty dominates (the audit measured parameter sd / total sd around 0.94), so the coverage
    indicators are strongly clustered. Measured on the production pipeline over 300 repetitions of
    4 intervals: intraclass correlation 0.365, design effect 2.09 -- so the reported interval and
    standard error overstated precision by about sqrt(2.09) = 1.45, and verdicts near the band edges
    were wrong in both directions.

    THE ESTIMATOR is the conventional one-way random-effects ANOVA one, on the 0/1 indicators::

        ICC = (MS_between - MS_within) / (MS_between + (m - 1) MS_within)

    with ``m`` the mean intervals per repetition, and the design effect ``1 + (m - 1) ICC``. The
    design effect is MEASURED per study rather than assumed: it is a property of this design and
    this data, and a fixed inflation factor would be a number chosen once.

    ``max(ICC, 0)``: the ANOVA estimator can come out negative when within-repetition agreement is
    lower than chance. A negative design effect is not a thing, and inflating precision for negative
    clustering would claim more than the data has -- so the correction never makes the interval
    NARROWER than the independent one, which is the fail-closed direction.
    """
    groups = [(int(c), int(m)) for c, m in per_repetition if int(m) > 0]
    total = sum(m for _, m in groups)
    if not groups or total <= 0:
        return (float("nan"), 1.0, 0.0)
    k = len(groups)
    grand = sum(c for c, _ in groups) / total
    mean_m = total / k
    if k < 2 or mean_m <= 1.0:
        # One repetition, or one interval each: there is no within- or no between-group variance to
        # compare, so nothing here can measure clustering. Reported as no correction rather than as
        # a number, which is what `nan` for the ICC says.
        return (float("nan"), 1.0, float(total))
    between = sum(m * (c / m - grand) ** 2 for c, m in groups) / (k - 1)
    within = sum(c * (1.0 - c / m) ** 2 + (m - c) * (0.0 - c / m) ** 2 for c, m in groups)
    within /= (total - k)
    denominator = between + (mean_m - 1.0) * within
    icc = 0.0 if denominator == 0.0 else (between - within) / denominator
    design_effect = 1.0 + (mean_m - 1.0) * max(icc, 0.0)
    return (float(icc), float(design_effect), float(total / design_effect))


def coverage_verdict_with_refusals(
    *,
    covered: int,
    total: int,
    nominal: float,
    acceptance_half_width: float,
    effective_sample_size: float,
    refused: int,
    repetitions: int,
) -> tuple["CoverageVerdict", str]:
    """The coverage verdict, at the effective sample size and knowing what was refused (R-36).

    A refused repetition's intervals are UNOBSERVED, so in the worst case they would all have been
    covered or all missed: the selection alone can move the measured coverage by at most the refused
    fraction ``f``. At or below the study's own ``acceptance_half_width`` that cannot carry the
    measurement across the band, and the verdict is about the model. Above it, the verdict would be
    about the gate, and INCONCLUSIVE is the honest word.

    DERIVED from a threshold the study already declares, and no new number.
    """
    fraction = 0.0 if repetitions <= 0 else refused / repetitions
    if fraction > acceptance_half_width:
        return (
            CoverageVerdict.INCONCLUSIVE,
            f"{refused} of {repetitions} repetition(s) were refused by the V2 evidence judgement, a "
            f"fraction of {fraction:.4f}, which exceeds this study's own acceptance half-width of "
            f"{acceptance_half_width}. Those repetitions' intervals are unobserved, so the "
            f"selection alone could move the measured coverage by up to {fraction:.4f} -- enough to "
            f"carry it across the band. This measurement is about which grids the gate routed, not "
            f"about the model's intervals",
        )
    return classify_coverage(
        covered, total, nominal=nominal, acceptance_half_width=acceptance_half_width,
        effective_sample_size=effective_sample_size,
    )


def wilson_interval(
    successes: float, trials: float, z: float = 1.959963985
) -> tuple[float, float]:
    """Wilson score interval: honest near 0 and 1, where the normal one is not.

    A coverage study that reports 0.96 from 200 intervals without saying how
    precisely it knows that number has not measured coverage; it has measured
    one draw of it.

    ``successes`` and ``trials`` are floats rather than ints since I-03 part B (R-36), so the
    interval can be computed at an EFFECTIVE sample size -- the pooled count divided by the measured
    design effect, which is not an integer. The arithmetic is unchanged and an integer pair gives
    exactly the interval it always gave.
    """
    if trials <= 0:
        return (float("nan"), float("nan"))
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denominator
    margin = (
        z
        * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))
        / denominator
    )
    return (centre - margin, centre + margin)


@dataclass(frozen=True)
class CoverageRepetition:
    """One synthetic experiment's contribution to the coverage tally."""

    seed: int
    intervals: int
    covered: int
    calibration_status: str
    heldout_verdict: str
    #: Solver calls this repetition actually made, counted as they happened
    #: rather than derived from the grid shape -- the two can disagree, and the
    #: measured one is the one the performance section may quote.
    forward_evaluations: int
    #: I-03 part A (batch 17): why the V2 evidence judgement refused this repetition's grid, when it
    #: did. Empty for a repetition that produced intervals.
    #:
    #: A repetition whose grid the router would not route is EVIDENCE ABOUT THE PIPELINE, not a lost
    #: trial: it is recorded with zero intervals and its reason rather than killing the study, which
    #: is what a FAIL_FAST sweep did the moment any repetition was refused. Measured on this
    #: study's own fixture: seed 13 of [11, 12, 13] gives chi-square 13.6471 on 2 degrees of freedom
    #: -- p = 0.0011 -- from a WELL-SPECIFIED model at the true noise, so a goodness-of-fit gate
    #: with a declared false-refusal rate refuses that fraction of repetitions by construction.
    #: What the coverage VERDICT should do about a refused fraction is I-03 part B's (R-36): the
    #: fraction is reported here and in the study's `why`, and the coverage number it accompanies is
    #: conditional on the repetitions that were routable, which the `why` now says.
    route_refused_because: str = ""


def run_coverage_study(
    *,
    truth,
    calibration_temperatures: Sequence[float],
    heldout_temperatures: Sequence[float],
    reference_temperature: Quantity,
    # Required here, unlike on the two functions above: this one SYNTHESIZES the observations, so
    # the sigma is the noise it draws from rather than a claim about evidence that already exists.
    observation_sigma: Quantity,
    twin: TwinReference,
    seeds: Sequence[int],
    grid_points_per_axis: int = 15,
    sigma_span: float = 6.0,
    credible_mass: float = 0.95,
    acceptance_half_width: float = 0.05,
    workers: int = 1,
) -> tuple[CoverageStudy, tuple[CoverageRepetition, ...], int]:
    """B3: repeat the whole pipeline on fresh noise and count what the intervals catch.

    Each repetition is an independent case run through Sprint 7's
    :func:`run_sweep` -- the same execution path the rest of the repository
    uses for high-throughput work, rather than a second loop written here.

    The seed schedule is explicit and passed in. Nothing draws from global
    randomness, so the whole study is a deterministic function of ``seeds``.

    Returns the study, the per-repetition record, and the total number of
    forward evaluations, which the performance section reports.
    """
    from ..execution.sweep import (
        FailurePolicy,
        SharedContext,
        SweepCase,
        SweepDefinition,
        run_sweep,
    )

    from .tcr import ols_reference_estimate, synthesize_tcr_observations

    all_temperatures = list(calibration_temperatures) + list(heldout_temperatures)
    by_condition = {
        f"T{i}": Quantity(float(t), "kelvin") for i, t in enumerate(all_temperatures)
    }
    heldout_ids = tuple(
        f"T{i}" for i in range(len(calibration_temperatures), len(all_temperatures))
    )
    r_bounds, a_bounds = (
        (p.bounds.lower.magnitude_in(p.unit), p.bounds.upper.magnitude_in(p.unit))
        for p in build_tcr_parameter_set().parameters
    )

    def one_repetition(shared: SharedContext, case: SweepCase) -> CoverageRepetition:
        seed = int(case.inputs["seed"])
        counter: dict[str, int] = {}
        source = synthesize_tcr_observations(
            truth,
            all_temperatures,
            sigma=observation_sigma,
            dataset_id=f"cov.source.{seed}",
            seed=seed,
        )
        split = ObservationSplit.partition(
            source=source,
            held_out_condition_ids=heldout_ids,
            twin=twin,
            calibration_dataset_id=f"cov.cal.{seed}",
            heldout_dataset_id=f"cov.held.{seed}",
        )
        oracle = ols_reference_estimate(
            split.calibration, by_condition, reference_temperature
        )
        # INF-08: axes clipped to the declared parameter bounds, which the
        # forward table now refuses to cross.
        r_axis = _bounded_axis(
            oracle["reference_resistance"],
            sigma_span * oracle["se_reference_resistance"],
            grid_points_per_axis,
            lower=r_bounds[0],
            upper=r_bounds[1],
        )
        a_axis = _bounded_axis(
            oracle["temperature_coefficient"],
            sigma_span * oracle["se_temperature_coefficient"],
            grid_points_per_axis,
            lower=a_bounds[0],
            upper=a_bounds[1],
        )
        points = [(float(r), float(a)) for r in r_axis for a in a_axis]
        table = tcr_forward_table(
            split.calibration,
            points,
            reference_temperature=reference_temperature,
            temperatures_by_condition=by_condition,
            counter=counter,
        )
        posterior = gaussian_grid_posterior(table, split.calibration)
        # I-03 part A: the V2 judgement can refuse this repetition's grid, and at the gate's own
        # false-refusal rate it sometimes will on perfectly good data. Recorded, not fatal.
        from ..hybrid_uq import HybridUQError

        try:
            metrics = validate_held_out(
                posterior,
                split,
                reference_temperature=reference_temperature,
                temperatures_by_condition=by_condition,
                observation_sigma=observation_sigma,
                twin=twin,
                credible_mass=credible_mass,
                counter=counter,
            )
        except HybridUQError as refused:
            return CoverageRepetition(
                seed=seed,
                intervals=0,
                covered=0,
                calibration_status=COVERAGE_CALIBRATION_STATUS,
                heldout_verdict="",
                forward_evaluations=(
                    grid_points_per_axis**2 * 2 * len(split.calibration.observations)
                ) if counter.get("n", 0) else 0,
                route_refused_because=str(refused),
            )
        # `counter` counts grid ROWS; each row runs one production solve per
        # condition in the set it was built over. The calibration table is built
        # twice -- once to fit, once inside validate_held_out to bind the
        # posterior to the calibration half by content (INF-03).
        rows = counter.get("n", 0)
        return CoverageRepetition(
            seed=seed,
            intervals=metrics.n,
            covered=metrics.covered,
            calibration_status=COVERAGE_CALIBRATION_STATUS,
            heldout_verdict=metrics.verdict.value,
            forward_evaluations=(
                grid_points_per_axis**2
                * (2 * len(split.calibration.observations) + len(split.held_out.observations))
            ) if rows else 0,
        )

    definition = SweepDefinition(
        sweep_id="tcr-coverage",
        operation=one_repetition,
        cases=tuple(
            SweepCase(case_id=f"rep-{seed}", inputs={"seed": int(seed)})
            for seed in seeds
        ),
        shared=SharedContext(),
        on_failure=FailurePolicy.FAIL_FAST,
        description="repeated synthetic TCR experiments for empirical coverage",
    )
    summary = run_sweep(definition, workers=workers)
    repetitions = tuple(outcome.value for outcome in summary.outcomes if outcome.ok)
    if len(repetitions) != len(tuple(seeds)):
        raise RuntimeError(
            f"coverage study lost {len(tuple(seeds)) - len(repetitions)} "
            f"repetition(s); a coverage number computed over the survivors "
            f"would be conditioned on which ones survived"
        )

    covered = sum(r.covered for r in repetitions)
    total = sum(r.intervals for r in repetitions)
    refused = tuple(r for r in repetitions if r.route_refused_because)
    # I-03 part B (R-36): the clustering these indicators actually have, measured from the
    # repetitions that produced intervals. Within one repetition they share one posterior.
    contributing = [(r.covered, r.intervals) for r in repetitions if r.intervals > 0]
    icc, design_effect, effective = coverage_design_effect(contributing)
    intervals_per_repetition = (total / len(contributing)) if contributing else float("nan")
    verdict, why = coverage_verdict_with_refusals(
        covered=covered,
        total=total,
        nominal=credible_mass,
        acceptance_half_width=acceptance_half_width,
        effective_sample_size=effective,
        refused=len(refused),
        repetitions=len(repetitions),
    )
    # The conditioning is stated whether or not it decided the verdict: a reader of a CALIBRATED
    # number needs to know it was computed on the repetitions a gate routed.
    if refused:
        why += (
            f". {len(refused)} of {len(repetitions)} repetition(s) were refused by the V2 evidence "
            f"judgement and contributed no intervals, so this coverage fraction is conditional on "
            f"the {len(repetitions) - len(refused)} whose grids it routed. A goodness-of-fit gate "
            f"refuses a fraction of well-specified repetitions equal to its own false-refusal rate; "
            f"seed(s) {[r.seed for r in refused]} were refused here"
        )
    measured = covered / total if total else float("nan")
    # The interval and the standard error at the EFFECTIVE size; the point estimate is the pooled
    # fraction. A design effect of 2.09 makes the interval about 1.45x wider, which is the whole of
    # the correction.
    low, high = wilson_interval(measured * effective, effective) if effective > 0 else (
        float("nan"), float("nan"))
    study = CoverageStudy(
        repetitions=len(repetitions),
        intervals_evaluated=total,
        nominal=credible_mass,
        measured=measured,
        standard_error=math.sqrt(
            measured * (1.0 - measured) / effective
        ) if effective > 0 and total else float("nan"),
        wilson_lower=low,
        wilson_upper=high,
        verdict=verdict,
        why=why,
        seeds=tuple(int(s) for s in seeds),
        algorithm="grid posterior + exact Gaussian-mixture predictive interval",
        acceptance_half_width=acceptance_half_width,
        intervals_per_repetition=intervals_per_repetition,
        intraclass_correlation=icc,
        design_effect=design_effect,
        effective_sample_size=effective,
        refused_repetitions=len(refused),
    )
    return study, repetitions, sum(r.forward_evaluations for r in repetitions)


def classify_coverage(
    covered: int,
    total: int,
    *,
    nominal: float,
    acceptance_half_width: float,
    #: I-03 part B (R-36): the sample size the INTERVAL is computed at, when it is not the interval
    #: count. Within one coverage repetition every interval shares one posterior, so the indicators
    #: are clustered and the pooled count overstates the evidence -- the audit measured a design
    #: effect of 2.09 on the production pipeline. None keeps the pooled count, which is what a
    #: caller passing only the two counts asked for; the study passes the effective size.
    effective_sample_size: float | None = None,
) -> tuple[CoverageVerdict, str]:
    """Compare measured against nominal using a threshold fixed in advance.

    ``acceptance_half_width`` is an argument with a declared default rather
    than a number chosen once the result was on screen.

    INF-05: CALIBRATED requires the Wilson interval to lie INSIDE the acceptance
    band. It used to require only overlap, which a study with almost no evidence
    satisfies by having a wide interval: 1 covered of 2 (Wilson [0.09, 0.91])
    and even 0 of 0 (NaN) came back CALIBRATED. An interval that is neither
    inside the band nor wholly outside it is INCONCLUSIVE, and no intervals at
    all is refused.
    """
    covered, total = int(covered), int(total)
    if total <= 0:
        raise ValueError(
            "no intervals were evaluated, so there is no coverage to classify; an "
            "absent measurement is not a calibrated one"
        )
    if not 0 <= covered <= total:
        raise ValueError(f"covered={covered} is not between 0 and total={total}")
    measured = covered / total
    # I-03 part B (R-36): the POINT estimate is the pooled fraction; the INTERVAL is computed at the
    # effective sample size, which is the pooled count divided by the measured design effect. The
    # Wilson form takes counts, so the effective size enters as the same fraction over an effective
    # denominator -- which is what "this fraction, known this precisely" means.
    trials = float(total) if effective_sample_size is None else float(effective_sample_size)
    if trials <= 0.0:
        raise ValueError(
            f"effective_sample_size={effective_sample_size!r} leaves no evidence to classify"
        )
    low, high = wilson_interval(measured * trials, trials)
    band_low = nominal - acceptance_half_width
    band_high = nominal + acceptance_half_width

    if high < band_low:
        return (
            CoverageVerdict.UNDERCOVERS,
            f"measured {measured:.4f} over {total} intervals, Wilson 95% "
            f"[{low:.4f}, {high:.4f}] lies entirely below the acceptance band "
            f"[{band_low:.3f}, {band_high:.3f}] around nominal {nominal}",
        )
    if low > band_high:
        return (
            CoverageVerdict.OVERCOVERS,
            f"measured {measured:.4f} over {total} intervals, Wilson 95% "
            f"[{low:.4f}, {high:.4f}] lies entirely above the acceptance band "
            f"[{band_low:.3f}, {band_high:.3f}] around nominal {nominal}",
        )
    if band_low <= low and high <= band_high:
        return (
            CoverageVerdict.CALIBRATED,
            f"measured {measured:.4f} over {total} intervals, Wilson 95% "
            f"[{low:.4f}, {high:.4f}] lies inside the acceptance band "
            f"[{band_low:.3f}, {band_high:.3f}] around nominal {nominal}",
        )
    return (
        CoverageVerdict.INCONCLUSIVE,
        f"measured {measured:.4f} over {total} intervals, Wilson 95% "
        f"[{low:.4f}, {high:.4f}] straddles the acceptance band "
        f"[{band_low:.3f}, {band_high:.3f}] around nominal {nominal}: too little "
        f"evidence to call the intervals calibrated or miscalibrated"
    )


def _bounded_axis(
    centre: float, half_width: float, points: int, *, lower: float, upper: float
) -> np.ndarray:
    """``points`` evenly spaced values over ``centre +/- half_width``, clipped to ``[lower, upper]`` (INF-08)."""
    low = max(float(centre) - float(half_width), float(lower))
    high = min(float(centre) + float(half_width), float(upper))
    if not low < high:
        raise InferenceProblemError(
            f"the grid axis centred at {centre!r} +/- {half_width!r} has no extent "
            f"inside the declared bounds [{lower!r}, {upper!r}]"
        )
    return np.linspace(low, high, int(points))
