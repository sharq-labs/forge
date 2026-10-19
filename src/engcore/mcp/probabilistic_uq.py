"""Declared independent-input probabilistic propagation for engineering runs."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import scipy
from scipy.special import ndtri
from scipy.stats import qmc

from ..scientific.units.quantity import (
    Quantity,
    base_unit,
    is_ratio_scale,
    require_spread_unit,
)

__all__ = [
    "PROBABILISTIC_UQ_SCHEMA",
    "SAMPLER_SEED",
    "build_deterministic_samples",
    "predictive_intervals",
    "sample_design",
]

# /2 (BUY-01, FDA-04, FDA-14): the design, the quantile rule and the spread
# units all changed, so every /1 value means something else. Nothing reads /1
# back; a /1 answer stays what it was and is not reinterpreted.
PROBABILISTIC_UQ_SCHEMA = "engineering_probabilistic_uq/2"

# Part of the /2 result identity. A fixed seed makes the design reproducible;
# it does not make any one finite design independent, which is why the realised
# rank correlation is reported with every answer.
SAMPLER_SEED = 20261019

# ODC-04a (owner-approved 2026-10-19, Option D): the smallest admitted
# eigenvalue of the design's rank-correlation matrix. With standardised inputs,
# no linear combination of them may carry less than sqrt(0.64) = 0.8 of its
# declared spread. A risk-policy bar for linear outputs only; it says nothing
# about the error of a nonlinear output. Evidence:
# docs/work/proposals/ODC_04A_DESIGN_CORRELATION_BOUND.md.
MINIMUM_DESIGN_LAMBDA = 0.64
PAIRING = "iman_conover_identity_vdw/1"


def _declared_quantity(spec: Mapping[str, Any], name: str) -> Quantity:
    value = spec.get(name)
    if not isinstance(value, str):
        raise TypeError(f"distribution field {name!r} must be a unit-bearing string")
    return Quantity.parse(value)


def _unit_design(count: int, columns: int) -> np.ndarray:
    """Midpoint Latin hypercube: each column a seeded permutation of (i+0.5)/n.

    The /1 lattice derived each column from the previous by a modular stride,
    and some pairs came out exact reverses (FDA-04). Here SciPy permutes every
    column independently from one generator. ``scramble=False`` keeps the
    points on stratum midpoints, which is what the Hazen rule below assumes.
    """
    generator = np.random.default_rng(SAMPLER_SEED)
    try:
        engine = qmc.LatinHypercube(d=columns, scramble=False, rng=generator)
    except TypeError:  # SciPy < 1.15 names the argument `seed`
        engine = qmc.LatinHypercube(d=columns, scramble=False, seed=generator)
    return engine.random(n=count)


def _ranks(design: np.ndarray) -> np.ndarray:
    return np.rint(design * design.shape[0] - 0.5).astype(int)


def _pair_for_independence(design: np.ndarray) -> np.ndarray:
    """Iman-Conover restricted pairing to the identity target, one pass.

    Each column keeps exactly its values -- its midpoint strata -- and only
    which values share a row changes: the van der Waerden scores of the ranks
    are decorrelated through the Cholesky factor of their own correlation, and
    every column is re-ranked to follow them (Iman & Conover 1982, Commun.
    Statist. Simul. Comput. 11(3):311-334). Spurious rank correlation of the
    random permutations shrinks; it does not vanish.

    A design it cannot decorrelate -- n <= k, or a score correlation that is
    not positive definite -- is returned unchanged, so the eigenvalue bound
    below still sees, and refuses, its dependence.
    """
    count, columns = design.shape
    if columns < 2 or count <= columns:
        return design
    scores = ndtri((_ranks(design) + 0.5) / count)
    try:
        factor = np.linalg.cholesky(np.corrcoef(scores, rowvar=False))
    except np.linalg.LinAlgError:
        return design
    target = np.linalg.solve(factor, scores.T).T
    paired = np.empty_like(design)
    for column in range(columns):
        paired[np.argsort(target[:, column], kind="stable"), column] = np.sort(
            design[:, column])
    return paired


def _rank_eigenvalues(design: np.ndarray) -> np.ndarray:
    """Ascending eigenvalues of the realised Spearman matrix, floored at 0."""
    correlation = np.corrcoef(_ranks(design), rowvar=False)
    return np.maximum(np.linalg.eigvalsh(correlation), 0.0)


def _assessed_design(count: int, columns: int) -> tuple[np.ndarray, dict[str, Any]]:
    """The design and the record of its identity and realised dependence."""
    design = _pair_for_independence(_unit_design(count, columns))
    record: dict[str, Any] = {
        "sampler": {
            "algorithm": "scipy.stats.qmc.LatinHypercube",
            "scramble": False,
            "strength": 1,
            "optimization": None,
            "pairing": PAIRING,
            "seed": SAMPLER_SEED,
            "scipy_version": scipy.__version__,
            "numpy_version": np.__version__,
        },
        "stratum_width": 1.0 / count,
        "max_abs_pairwise_rank_correlation": None,
        "max_correlation_pair": None,
        "lambda_min": None,
        "lambda_max": None,
        "linear_output_sd_ratio_band": None,
        "minimum_lambda": MINIMUM_DESIGN_LAMBDA,
        "bound_scope": "design_dependence_bound_linear_outputs_only",
        "admitted": True,
    }
    if columns < 2:
        return design, record
    correlation = np.corrcoef(_ranks(design), rowvar=False)
    upper = np.triu_indices(columns, k=1)
    strongest = int(np.argmax(np.abs(correlation[upper])))
    eigenvalues = _rank_eigenvalues(design)
    # With n <= k the rank matrix is singular by construction; say so exactly
    # rather than report the rounding residue of an eigensolver.
    lowest = 0.0 if count <= columns else float(eigenvalues[0])
    highest = float(eigenvalues[-1])
    record.update({
        "max_abs_pairwise_rank_correlation": float(abs(correlation[upper][strongest])),
        "max_correlation_pair": [int(upper[0][strongest]), int(upper[1][strongest])],
        "lambda_min": lowest,
        "lambda_max": highest,
        "linear_output_sd_ratio_band": [float(np.sqrt(lowest)), float(np.sqrt(highest))],
        "admitted": count > columns and lowest >= MINIMUM_DESIGN_LAMBDA,
    })
    return design, record


def sample_design(sample_count: int, input_count: int) -> dict[str, Any]:
    """The sampler's identity and the realised dependence of its design.

    The realised Spearman matrix R is the dependence the propagation actually
    used between the inputs. For an output linear in standardised inputs the
    design's sd lies within ``linear_output_sd_ratio_band`` = [sqrt(lambda_min),
    sqrt(lambda_max)] times the true sd. Nothing here bounds a nonlinear output.
    """
    return _assessed_design(int(sample_count), int(input_count))[1]


def build_deterministic_samples(
    inputs: Sequence[Mapping[str, Any]], *, sample_count: int,
    dependence: str,
) -> list[dict[str, str]]:
    """Seeded midpoint Latin-hypercube samples; never infer a dependence structure."""
    if dependence != "independent":
        raise ValueError(
            "dependence must be explicitly 'independent'; correlated inputs "
            "require a declared correlation model, which this version refuses"
        )
    count = int(sample_count)
    if not 4 <= count <= 256:
        raise ValueError("sample_count must be between 4 and 256")
    if not inputs:
        raise ValueError("at least one uncertain input is required")

    columns = len(inputs)
    design, record = _assessed_design(count, columns)
    # A design whose realised dependence is past the bound would report a
    # combination of inputs as more certain than declared -- at the limit,
    # n <= k, as certain (FDA-04). Refused, whatever was declared.
    if count <= columns:
        raise ValueError(
            f"sample_count={count} does not exceed the {columns} uncertain "
            f"inputs, so some linear combination of them has zero sample "
            f"variance; the design cannot represent independence"
        )
    if not record["admitted"]:
        raise ValueError(
            f"the sample design for {columns} inputs at sample_count={count} "
            f"has rank-correlation lambda_min={record['lambda_min']:.3f}, below "
            f"{MINIMUM_DESIGN_LAMBDA}: some linear combination of the inputs "
            f"would carry less than {MINIMUM_DESIGN_LAMBDA ** 0.5:.1f} of its "
            f"declared spread, so it cannot represent independence; increase "
            f"sample_count"
        )
    paths: set[str] = set()
    samples = [dict() for _ in range(count)]
    for column, spec in enumerate(inputs):
        path = str(spec.get("path", "")).strip()
        distribution = str(spec.get("distribution", "")).strip().lower()
        if not path or path in paths:
            raise ValueError("uncertain input paths must be non-empty and unique")
        paths.add(path)
        quantiles = design[:, column]

        if distribution == "uniform":
            lower = _declared_quantity(spec, "lower")
            upper = _declared_quantity(spec, "upper").to(lower.units)
            lo = lower.magnitude
            hi = upper.magnitude
            if hi <= lo:
                raise ValueError(f"uniform input {path!r} requires upper > lower")
            magnitudes = lo + quantiles * (hi - lo)
            unit = lower.units
        elif distribution == "normal":
            mean = _declared_quantity(spec, "mean")
            sigma = _declared_quantity(spec, "standard_deviation")
            # A standard deviation is a difference. '2 degC' is refused as
            # ambiguous; '2 delta_degC' and '2 kelvin' are read as spreads.
            require_spread_unit(sigma.units, context=f"standard_deviation of {path!r}")
            spread = sigma.magnitude_as_spread_in(mean.units)
            if spread <= 0:
                raise ValueError(
                    f"normal input {path!r} requires positive standard_deviation"
                )
            magnitudes = mean.magnitude + spread * ndtri(quantiles)
            unit = mean.units
        else:
            raise ValueError(
                f"input {path!r} distribution must be 'uniform' or 'normal'"
            )
        for index, magnitude in enumerate(magnitudes):
            samples[index][path] = str(Quantity(float(magnitude), unit))
    return samples


def _spread(magnitude: float, unit: str) -> dict[str, Any]:
    """A difference of values in ``unit``, on a scale whose zero is zero."""
    if is_ratio_scale(unit):
        return Quantity(magnitude, unit).to_dict()
    target = base_unit(unit)
    return Quantity(
        Quantity(magnitude, unit).magnitude_as_spread_in(target), target
    ).to_dict()


def predictive_intervals(
    answers: Sequence[Mapping[str, Any]], *, credible_mass: float,
) -> dict[str, Any]:
    """Empirical central intervals, fail-closed on unsupported sampled mass."""
    mass = float(credible_mass)
    if not 0.0 < mass < 1.0:
        raise ValueError("credible_mass must lie strictly between zero and one")
    if not answers:
        raise ValueError("predictive intervals require sampled answers")

    verdicts = [answer.get("verdict") for answer in answers]
    rejected = [index for index, verdict in enumerate(verdicts) if verdict != "supported"]
    if rejected:
        return {
            "schema": PROBABILISTIC_UQ_SCHEMA,
            "status": "predictive_support_not_admitted",
            "sample_count": len(answers),
            "rejected_sample_indices": rejected,
            "sample_verdicts": verdicts,
            "intervals": [],
            "reason": (
                "At least one equal-mass sample was not SUPPORTED. Refusing "
                "silent conditioning or a predictive interval over partial support."
            ),
        }

    tail = (1.0 - mass) / 2.0
    # Hazen places sample i at (i - 0.5)/n, the midpoint of its stratum. A
    # tail below 0.5/n has no sample inside it: NumPy would clip to the
    # extreme value and the interval would hold less than the stated mass.
    minimum_tail = 0.5 / len(answers)
    if tail < minimum_tail:
        return {
            "schema": PROBABILISTIC_UQ_SCHEMA,
            "status": "sample_resolution_insufficient",
            "sample_count": len(answers),
            "rejected_sample_indices": [],
            "sample_verdicts": verdicts,
            "credible_mass": mass,
            "minimum_tail_mass": minimum_tail,
            "intervals": [],
            "reason": (
                f"A central mass of {mass} needs tails of {tail}; with "
                f"{len(answers)} samples the outermost stratum midpoint is at "
                f"{minimum_tail}. Increase sample_count or lower credible_mass."
            ),
        }

    series: dict[tuple[str, str], list[Quantity]] = {}
    for answer in answers:
        for result in answer["results"]:
            for name, payload in result["values"].items():
                series.setdefault((result["subject"], name), []).append(
                    Quantity(payload["magnitude"], payload["units"])
                )

    intervals = []
    for (subject, name), values in sorted(series.items()):
        if len(values) != len(answers):
            continue
        unit = values[0].units
        magnitudes = np.asarray(
            [value.magnitude_in(unit) for value in values], dtype=float
        )
        intervals.append({
            "subject": subject,
            "quantity": name,
            "mean": Quantity(float(np.mean(magnitudes)), unit).to_dict(),
            "standard_uncertainty": _spread(float(np.std(magnitudes, ddof=1)), unit),
            "lower": Quantity(
                float(np.quantile(magnitudes, tail, method="hazen")), unit
            ).to_dict(),
            "upper": Quantity(
                float(np.quantile(magnitudes, 1.0 - tail, method="hazen")), unit
            ).to_dict(),
            "credible_mass": mass,
            "mass_semantics": "nominal_empirical_quantile_mass_not_coverage",
            "method": "midpoint_latin_hypercube_hazen_empirical_central_interval",
            "sample_count": len(values),
        })
    return {
        "schema": PROBABILISTIC_UQ_SCHEMA,
        "status": "completed",
        "sample_count": len(answers),
        "rejected_sample_indices": [],
        "sample_verdicts": verdicts,
        "intervals": intervals,
        "conditional_on": "declared independent input distributions",
        "does_not_include": [
            "input correlation",
            "model-form uncertainty",
            "observation or measurement noise unless represented as an input",
            "probability outside the declared distribution families",
            "calibrated predictive coverage",
            "sampling error of the quantile estimate",
        ],
    }
