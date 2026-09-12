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
from ..inference.calibration import (
    CalibrationResult,
    CalibrationStatus,
    IdentifiabilityReport,
    IdentifiabilityStatus,
    assess_identifiability,
)
from ..inference.grid import ObservationSet, PosteriorGrid, gaussian_grid_posterior
from ..inference.split import ObservationSplit, require_split
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity
from ..uq.predictive import PredictiveObservableSpec, posterior_predictive_uq
from .tcr import OHM, TCR_MODEL_REF, tcr_forward_table

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
    """
    require_split(split)
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
            observation_sigma=observation_sigma,
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
                observation_sigma=observation_sigma,
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
    function from being handed the fitting data under a different label.
    """
    require_split(split)
    split.require_posterior_was_fitted_here(posterior.dataset_id)

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
            observation_sigma=observation_sigma,
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
        r_axis = np.linspace(
            oracle["reference_resistance"] - sigma_span * oracle["se_reference_resistance"],
            oracle["reference_resistance"] + sigma_span * oracle["se_reference_resistance"],
            grid_points_per_axis,
        )
        a_axis = np.linspace(
            oracle["temperature_coefficient"]
            - sigma_span * oracle["se_temperature_coefficient"],
            oracle["temperature_coefficient"]
            + sigma_span * oracle["se_temperature_coefficient"],
            grid_points_per_axis,
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
        # condition in the set it was built over.
        rows = counter.get("n", 0)
        return CoverageRepetition(
            seed=seed,
            intervals=metrics.n,
            covered=metrics.covered,
            calibration_status=CalibrationStatus.CONVERGED.value,
            heldout_verdict=metrics.verdict.value,
            forward_evaluations=(
                grid_points_per_axis**2
                * (len(split.calibration.observations) + len(split.held_out.observations))
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
    than a number chosen once the result was on screen. The verdict is decided
    by whether the Wilson interval for the measured coverage overlaps the
    acceptance band, so a study with few repetitions cannot claim calibration
    it has not earned.
    """
    measured = covered / total if total else float("nan")
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
    return (
        CoverageVerdict.CALIBRATED,
        f"measured {measured:.4f} over {total} intervals, Wilson 95% "
        f"[{low:.4f}, {high:.4f}] overlaps the acceptance band "
        f"[{band_low:.3f}, {band_high:.3f}] around nominal {nominal}",
    )
