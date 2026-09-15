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
from ..uq.predictive import PredictiveObservableSpec, posterior_predictive_uq
from .tcr import (
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
        }


#: Declared BEFORE any result was seen. A held-out set whose standardized
#: residuals are this unlikely under the model's own predictive distribution is
#: evidence against the model, not noise.
HELD_OUT_CHI_SQUARE_ALPHA = 0.01


def _require_declared_sigma(split: ObservationSplit, observation_sigma: Quantity) -> None:
    """INF-02: the noise a held-out score uses is each observation's DECLARED sigma.

    ``observation_sigma`` used to replace every held-out observation's own
    sigma, so a caller could widen the predictive distribution until a failing
    model passed (chi2 49.3, p 5e-10 at the declared 0.002 ohm; chi2 1.81 at a
    caller's 0.02 ohm). The parameter is kept for its callers, and it must now
    state the declared sigma: anything else is refused rather than used.
    """
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
) -> None:
    """INF-03 and INF-01, before any held-out or predictive statement is made.

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


def predict_held_out(
    posterior: PosteriorGrid,
    split: ObservationSplit,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    observation_sigma: Quantity,
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
    out: list[PredictiveDecomposition] = []
    for observation in split.held_out.observations:
        spec = PredictiveObservableSpec(
            observation_key=observation.key,
            unit=OHM,
            observation_sigma=observation.sigma,
        )
        quantified = posterior_predictive_uq(
            posterior,
            predictive_table,
            spec,
            twin=twin,
            model=TCR_MODEL_REF,
            source_ref=f"study:{split.heldout_dataset_id}",
            credible_mass=credible_mass,
        )
        out.append(
            PredictiveDecomposition(
                condition_id=observation.condition_id,
                observation_key=observation.key,
                central=quantified.mean,
                parameter_sigma=quantified.epistemic_standard_uncertainty,
                parameter_lower=quantified.epistemic_interval.lower,
                parameter_upper=quantified.epistemic_interval.upper,
                observation_sigma=spec.observation_sigma,
                total_sigma=quantified.total_standard_uncertainty,
                total_lower=quantified.total_interval.lower,
                total_upper=quantified.total_interval.upper,
                confidence_level=quantified.confidence_level,
            )
        )
    return tuple(out)


def validate_held_out(
    posterior: PosteriorGrid,
    split: ObservationSplit,
    *,
    reference_temperature: Quantity,
    temperatures_by_condition: Mapping[str, Quantity],
    observation_sigma: Quantity,
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
    if p_value < HELD_OUT_CHI_SQUARE_ALPHA:
        verdict = HeldOutValidation.FAIL
        why = (
            f"the {n} standardized held-out residuals give chi-square "
            f"{chi_square:.4g} on {n} degrees of freedom, p = {p_value:.3g}, "
            f"below the pre-declared alpha of {HELD_OUT_CHI_SQUARE_ALPHA}. The "
            f"model's own predictive distribution says data like this is "
            f"implausible, which is evidence against the model rather than "
            f"noise"
        )
    else:
        verdict = HeldOutValidation.PASS
        why = (
            f"chi-square {chi_square:.4g} on {n} degrees of freedom, "
            f"p = {p_value:.3g}, consistent with the model's own predictive "
            f"distribution at alpha {HELD_OUT_CHI_SQUARE_ALPHA}"
        )

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
        }


def wilson_interval(successes: int, trials: int, z: float = 1.959963985) -> tuple[float, float]:
    """Wilson score interval: honest near 0 and 1, where the normal one is not.

    A coverage study that reports 0.96 from 200 intervals without saying how
    precisely it knows that number has not measured coverage; it has measured
    one draw of it.
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


def run_coverage_study(
    *,
    truth,
    calibration_temperatures: Sequence[float],
    heldout_temperatures: Sequence[float],
    reference_temperature: Quantity,
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
        # `counter` counts grid ROWS; each row runs one production solve per
        # condition in the set it was built over. The calibration table is built
        # twice -- once to fit, once inside validate_held_out to bind the
        # posterior to the calibration half by content (INF-03).
        rows = counter.get("n", 0)
        return CoverageRepetition(
            seed=seed,
            intervals=metrics.n,
            covered=metrics.covered,
            calibration_status=CalibrationStatus.CONVERGED.value,
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
    verdict, why = classify_coverage(
        covered,
        total,
        nominal=credible_mass,
        acceptance_half_width=acceptance_half_width,
    )
    low, high = wilson_interval(covered, total)
    study = CoverageStudy(
        repetitions=len(repetitions),
        intervals_evaluated=total,
        nominal=credible_mass,
        measured=covered / total if total else float("nan"),
        standard_error=math.sqrt(
            (covered / total) * (1.0 - covered / total) / total
        ) if total else float("nan"),
        wilson_lower=low,
        wilson_upper=high,
        verdict=verdict,
        why=why,
        seeds=tuple(int(s) for s in seeds),
        algorithm="grid posterior + exact Gaussian-mixture predictive interval",
        acceptance_half_width=acceptance_half_width,
    )
    return study, repetitions, sum(r.forward_evaluations for r in repetitions)


def classify_coverage(
    covered: int,
    total: int,
    *,
    nominal: float,
    acceptance_half_width: float,
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
    low, high = wilson_interval(covered, total)
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
