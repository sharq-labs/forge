"""Declared independent-input probabilistic propagation for engineering runs."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.special import ndtri

from ..scientific.units.quantity import Quantity

__all__ = [
    "PROBABILISTIC_UQ_SCHEMA",
    "build_deterministic_samples",
    "predictive_intervals",
]

PROBABILISTIC_UQ_SCHEMA = "engineering_probabilistic_uq/1"


def _declared_quantity(spec: Mapping[str, Any], name: str) -> Quantity:
    value = spec.get(name)
    if not isinstance(value, str):
        raise TypeError(f"distribution field {name!r} must be a unit-bearing string")
    return Quantity.parse(value)


def build_deterministic_samples(
    inputs: Sequence[Mapping[str, Any]], *, sample_count: int,
    dependence: str,
) -> list[dict[str, str]]:
    """Deterministic stratified samples; never infer a dependence structure."""
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
    base_quantiles = (np.arange(count, dtype=float) + 0.5) / count
    for column, spec in enumerate(inputs):
        path = str(spec.get("path", "")).strip()
        distribution = str(spec.get("distribution", "")).strip().lower()
        if not path or path in paths:
            raise ValueError("uncertain input paths must be non-empty and unique")
        paths.add(path)
        # A deterministic permutation gives every marginal one point in every
        # stratum without pretending the points are random observations.
        stride = 2 * column + 1
        while math.gcd(stride, count) != 1:
            stride += 2
        quantiles = base_quantiles[(np.arange(count) * stride + column) % count]

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
                "silent conditioning or a predictive interval over partial support."
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
            "method": "deterministic_latin_hypercube_empirical_central_interval",
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
        ],
    }
