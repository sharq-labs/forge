"""Bridge the existing trusted NAFEMS T3 vertical into the campaign layer."""

from __future__ import annotations

from dataclasses import dataclass

from engcore.domains.thermal_models.nafems_t3 import (
    QOI,
    NAFEMST3Numerics,
    solve_nafems_t3,
)
from engcore.scientific.results.validation import ValidationLevel, ValidationOutcome


@dataclass(frozen=True)
class NAFEMST3CampaignResult:
    temperature_k: float
    external_benchmark_passed: bool
    benchmark_validated: bool
    attained_levels: tuple[str, ...]


def run_existing_nafems_t3(
    *,
    n_cells: int = 160,
    n_steps: int = 640,
    run_id: str = "reference-validation-nafems-t3",
) -> NAFEMST3CampaignResult:
    result = solve_nafems_t3(
        run_id=run_id,
        numerics=NAFEMST3Numerics(n_cells=n_cells, n_steps=n_steps),
    )
    external = [
        check
        for check in result.validation.checks
        if check.name == "nafems_t3_external_benchmark"
    ]
    if len(external) != 1:
        raise RuntimeError(
            f"expected one NAFEMS T3 external benchmark check, found {len(external)}"
        )
    levels = tuple(sorted(level.value for level in result.validation.attained_levels))
    return NAFEMST3CampaignResult(
        temperature_k=result.values[QOI].magnitude_in("kelvin"),
        external_benchmark_passed=external[0].outcome is ValidationOutcome.PASS,
        benchmark_validated=(
            ValidationLevel.BENCHMARK_VALIDATED in result.validation.attained_levels
        ),
        attained_levels=levels,
    )


__all__ = ["NAFEMST3CampaignResult", "run_existing_nafems_t3"]
