"""MCP assembly for the executable NAFEMS T3 validation vertical."""

from __future__ import annotations

from ..domains.thermal_models.nafems_t3 import NAFEMST3Numerics, solve_nafems_t3
from ..scientific.results.validation import ValidationLevel
from .evidence import CredibilityEvidenceReport


def run_nafems_t3_credibility(
    *,
    run_id: str = "nafems-t3",
    numerics: NAFEMST3Numerics | None = None,
) -> CredibilityEvidenceReport:
    """Execute T3 and require its repository-trusted benchmark level."""

    result = solve_nafems_t3(run_id=run_id, numerics=numerics)
    return CredibilityEvidenceReport.from_result(
        result,
        required_levels=(ValidationLevel.BENCHMARK_VALIDATED,),
        notes=(
            "NAFEMS T3 executable vertical: the benchmark level comes from "
            "the repository-pinned external oracle comparison."
        ),
    )


__all__ = ["run_nafems_t3_credibility"]
