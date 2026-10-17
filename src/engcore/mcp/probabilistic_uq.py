"""Declared independent-input probabilistic propagation for engineering runs."""

from __future__ import annotations

import operator
from typing import Any, Mapping, Sequence

import numpy as np
import scipy
from scipy.special import ndtri
from scipy.stats import qmc

from ..scientific.units.quantity import Quantity

__all__ = [
    "LATIN_HYPERCUBE_SAMPLER",
    "PROBABILISTIC_UQ_SCHEMA",
    "build_deterministic_samples",
    "latin_hypercube_provenance",
    "predictive_intervals",
]

# /2: seeded Latin hypercube with a `sampling` provenance block. /1 records came
# from a fixed-stride design that coupled the inputs (review finding B1).
PROBABILISTIC_UQ_SCHEMA = "engineering_probabilistic_uq/2"
LATIN_HYPERCUBE_SAMPLER = "scipy.stats.qmc.LatinHypercube"


def _sampling_seed(seed: Any) -> int:
    if isinstance(seed, bool):
        raise TypeError("seed must be an explicit non-negative integer")
    try:
        value = operator.index(seed)
    except TypeError:
        raise TypeError("seed must be an explicit non-negative integer") from None
    if value < 0:
        raise ValueError("seed must be an explicit non-negative integer")
    return value


def _unit_hypercube(count: int, dimension: int, seed: int) -> np.ndarray:
    """Centred Latin hypercube: independent random stratum permutations per column."""
    generator = np.random.default_rng(seed)
    try:
        engine = qmc.LatinHypercube(d=dimension, scramble=False, rng=generator)
    except TypeError:  # SciPy < 1.15 names the generator argument ``seed``.
        engine = qmc.LatinHypercube(d=dimension, scramble=False, seed=generator)
    return engine.random(count)


def latin_hypercube_provenance(
    *, seed: int, sample_count: int, dimension: int,
) -> dict[str, Any]:
    """The record that, with the declared inputs, reproduces the sample design."""
    return {
        "sampler": LATIN_HYPERCUBE_SAMPLER,
        "scramble": False,
        "seed": _sampling_seed(seed),
        "generator": "numpy.random.default_rng",
        "scipy_version": scipy.__version__,
        "numpy_version": np.__version__,
        "sample_count": int(sample_count),
        "dimension": int(dimension),
    }


def _declared_quantity(spec: Mapping[str, Any], name: str) -> Quantity:
    value = spec.get(name)
    if not isinstance(value, str):
        raise TypeError(f"distribution field {name!r} must be a unit-bearing string")
    return Quantity.parse(value)


def build_deterministic_samples(
    inputs: Sequence[Mapping[str, Any]], *, sample_count: int,
    dependence: str, seed: int,
) -> list[dict[str, str]]:
    """Seeded Latin-hypercube samples; never infer a dependence structure.

    Each column is an independent random permutation of the stratum
    midpoints, so every marginal has one point per equal-mass stratum and no
    input is coupled to another by construction. The seed is a required
    argument here; a boundary that defaults it (the MCP tool uses 0) must
    report the seed it used through ``latin_hypercube_provenance``.
    """
    seed = _sampling_seed(seed)
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

    paths: set[str] = set()
    samples = [dict() for _ in range(count)]
    # A fixed modular stride per column was used here before; it coupled the
    # columns (rho ~ 0.42 between the first two at every n), which biased the
    # propagated variance of any output that combines two inputs.
    unit_samples = _unit_hypercube(count, len(inputs), seed)
    for column, spec in enumerate(inputs):
        path = str(spec.get("path", "")).strip()
        distribution = str(spec.get("distribution", "")).strip().lower()
        if not path or path in paths:
            raise ValueError("uncertain input paths must be non-empty and unique")
        paths.add(path)
        quantiles = unit_samples[:, column]

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
            sigma = _declared_quantity(spec, "standard_deviation").to(mean.units)
            if sigma.magnitude <= 0:
                raise ValueError(
                    f"normal input {path!r} requires positive standard_deviation"
                )
            magnitudes = mean.magnitude + sigma.magnitude * ndtri(quantiles)
            unit = mean.units
        else:
            raise ValueError(
                f"input {path!r} distribution must be 'uniform' or 'normal'"
            )
        for index, magnitude in enumerate(magnitudes):
            samples[index][path] = str(Quantity(float(magnitude), unit))
    return samples


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
                "silent conditioning or a predictive interval over partial support. "
                "The refusal is a fact about this one seeded sample design, not "
                "about the declared distributions as a whole."
            ),
        }

    series: dict[tuple[str, str], list[Quantity]] = {}
    for answer in answers:
        for result in answer["results"]:
            for name, payload in result["values"].items():
                series.setdefault((result["subject"], name), []).append(
                    Quantity(payload["magnitude"], payload["units"])
                )

    tail = (1.0 - mass) / 2.0
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
            "standard_uncertainty": Quantity(
                float(np.std(magnitudes, ddof=1)), unit
            ).to_dict(),
            "lower": Quantity(float(np.quantile(magnitudes, tail)), unit).to_dict(),
            "upper": Quantity(
                float(np.quantile(magnitudes, 1.0 - tail)), unit
            ).to_dict(),
            "credible_mass": mass,
            "method": "seeded_latin_hypercube_midpoint_empirical_central_interval",
            "sample_count": len(values),
        })
    return {
        "schema": PROBABILISTIC_UQ_SCHEMA,
        "status": "completed",
        "sample_count": len(answers),
        "rejected_sample_indices": [],
        "sample_verdicts": verdicts,
        "intervals": intervals,
        "conditional_on": (
            "declared independent input distributions, evaluated on one seeded "
            "Latin-hypercube sample design (see sampling)"
        ),
        "does_not_include": [
            "input correlation",
            "model-form uncertainty",
            "observation or measurement noise unless represented as an input",
            "probability outside the declared distribution families",
            "finite-sample estimation error of the interval endpoints",
            "variation across sample designs (other seeds)",
        ],
    }
