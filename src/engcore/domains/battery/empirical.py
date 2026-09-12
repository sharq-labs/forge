"""Is a declared cell's open-circuit voltage EMPIRICALLY adequate against measured OCV?

The gap this closes
--------------------
Battery Flagship B1 calibrated ``battery.cell.rint_ocv`` on measured LiFePO4 data
and missed a held-out measurement by 372 mV. The model's validity assessment of
that calibrated cell reported ZERO violated conditions. Nothing was wrong with
the assessment: every one of its eleven conditions asks whether the model is
being used inside its declared regime -- ratings, SOC window, temperature,
polarization timescale -- and none of them can see whether the OCV the cell
declares is the OCV the cell has. That question needs measured evidence, which
an applicability condition does not have.

Two questions, two answers, never merged
-----------------------------------------
``MODEL_APPLICABLE``
    the existing :func:`~engcore.domains.battery.cell.assess_rint_validity`
    verdict: is the Rint model being used inside the regime it declares?

``MODEL_EMPIRICALLY_ADEQUATE``
    this module: do independent measurements of the cell's open-circuit voltage
    agree with the OCV the cell declares, within their measurement uncertainty?

Neither implies the other. A cell can be applicable and empirically inadequate
(B1), or empirically adequate at the points measured and outside its ratings
elsewhere. :class:`OcvEmpiricalAssessment` carries both, side by side, so a
reader who takes one cannot quietly have taken the other.

Why this is not a RangeCondition on the model record
------------------------------------------------------
Adding a condition to ``RINT_OCV_MODEL`` would turn every existing IN_DOMAIN
verdict that has no measured OCV into UNKNOWN -- including every pinned
hard-benchmark case -- and would put a statement about measured evidence into a
record that describes the model. Kept separate, it changes no existing verdict.

The rule
--------
The rule preregistered for Battery Flagship B1 and reused, not re-chosen: over
the in-claim evidence, chi-square = sum(((measured - declared) / u)^2) on n
degrees of freedom, inadequate below ``alpha`` = 0.01. ``u`` is the
measurement's own standard uncertainty. The declared cell is a declaration,
not an estimate, so there is no parameter uncertainty to add -- which also
means evidence that was USED to declare the cell must not be supplied: scoring
a curve against its own knots is scoring an answer against itself. The
assessment lists exactly which source references it scored so that can be
checked.

What is never adequate
-----------------------
* no measured evidence at all: ``NO_MEASURED_EVIDENCE``;
* only evidence the model does not claim to describe: ``EVIDENCE_OUTSIDE_CLAIM``.
  Charge-conditioned OCV is out of claim (the model is discharge only and
  excludes hysteresis); a state of charge outside a declared curve's interval
  is out of representation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from ...scientific.errors import InvalidScientificProblem
from ...scientific.units.quantity import Quantity
from . import context as ctx
from .cell import CellSpecification

#: The alpha preregistered for Battery Flagship B1 and reused by B2.
DEFAULT_ALPHA = 0.01


class ConditioningDirection(str, Enum):
    """How the cell reached the state of charge its OCV was measured at."""

    DISCHARGE = "discharge"
    CHARGE = "charge"


class OcvEmpiricalStatus(str, Enum):
    EMPIRICALLY_ADEQUATE = "MODEL_EMPIRICALLY_ADEQUATE"
    EMPIRICALLY_INADEQUATE = "MODEL_EMPIRICALLY_INADEQUATE"
    NO_MEASURED_EVIDENCE = "NO_MEASURED_EVIDENCE"
    EVIDENCE_OUTSIDE_CLAIM = "EVIDENCE_OUTSIDE_CLAIM"


@dataclass(frozen=True)
class MeasuredOcvPoint:
    """One measured, rested open-circuit voltage of one cell, with its uncertainty."""

    state_of_charge: Quantity
    open_circuit_voltage: Quantity
    standard_uncertainty: Quantity
    conditioning: ConditioningDirection
    source_ref: str

    def __post_init__(self) -> None:
        if not str(self.source_ref).strip():
            raise InvalidScientificProblem(
                "a measured OCV point needs a source_ref; a voltage whose origin "
                "cannot be named is not evidence"
            )
        z = self.state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        if not 0.0 <= z <= 1.0:
            raise InvalidScientificProblem(f"state of charge {z!r} is outside [0, 1]")
        self.open_circuit_voltage.require_compatible(
            Quantity(1.0, ctx.VOLTAGE_UNIT), context="measured OCV"
        )
        u = self.standard_uncertainty.magnitude_in(ctx.VOLTAGE_UNIT)
        if not math.isfinite(u) or u <= 0.0:
            raise InvalidScientificProblem(
                "a measured OCV needs a strictly positive, finite standard "
                "uncertainty; a zero uncertainty would make any disagreement "
                "infinitely significant and hand the verdict to rounding"
            )
        object.__setattr__(self, "conditioning", ConditioningDirection(self.conditioning))


@dataclass(frozen=True)
class OcvEmpiricalAssessment:
    status: OcvEmpiricalStatus
    alpha: float
    scored: tuple[dict[str, Any], ...] = ()
    excluded: tuple[dict[str, Any], ...] = ()
    chi_square: float | None = None
    degrees_of_freedom: int = 0
    p_value: float | None = None
    applicability_status: str | None = None
    why: str = ""
    independence_note: str = field(
        default=(
            "evidence used to declare this cell must not be supplied; the scored "
            "source references are listed so that can be checked"
        )
    )

    @property
    def empirically_adequate(self) -> bool:
        return self.status is OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "model_applicable_status": self.applicability_status,
            "alpha": self.alpha,
            "chi_square": self.chi_square,
            "degrees_of_freedom": self.degrees_of_freedom,
            "p_value": self.p_value,
            "scored": list(self.scored),
            "excluded": list(self.excluded),
            "why": self.why,
            "independence_note": self.independence_note,
        }


def assess_ocv_empirical_adequacy(
    cell: CellSpecification,
    evidence: Sequence[MeasuredOcvPoint],
    *,
    alpha: float = DEFAULT_ALPHA,
    applicability_status: str | None = None,
) -> OcvEmpiricalAssessment:
    """Score a declared cell's OCV against independent measured OCV.

    ``applicability_status`` is the caller's existing applicability verdict,
    carried alongside so the two answers travel together. It is recorded and
    never consulted: applicability does not make a cell empirically adequate,
    and empirical adequacy does not make it applicable.
    """
    from scipy.stats import chi2

    if not 0.0 < float(alpha) < 1.0:
        raise InvalidScientificProblem("alpha must lie strictly between 0 and 1")
    if not isinstance(cell, CellSpecification):
        raise InvalidScientificProblem("assess_ocv_empirical_adequacy takes a CellSpecification")

    points = tuple(evidence)
    if not points:
        return OcvEmpiricalAssessment(
            status=OcvEmpiricalStatus.NO_MEASURED_EVIDENCE, alpha=float(alpha),
            applicability_status=applicability_status,
            why="no measured OCV was supplied; absence of evidence is not adequacy",
        )

    scored: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for point in points:
        z = point.state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
        if point.conditioning is not ConditioningDirection.DISCHARGE:
            excluded.append({
                "source_ref": point.source_ref, "state_of_charge": z,
                "reason": "charge-conditioned OCV is outside the claim: the model is "
                          "discharge only and excludes hysteresis",
            })
            continue
        declared = cell.open_circuit_voltage(point.state_of_charge)
        if declared is None:
            excluded.append({
                "source_ref": point.source_ref, "state_of_charge": z,
                "reason": "the cell's declared OCV gives no value at this state of "
                          "charge (outside its curve's interval)",
            })
            continue
        measured = point.open_circuit_voltage.magnitude_in(ctx.VOLTAGE_UNIT)
        predicted = declared.magnitude_in(ctx.VOLTAGE_UNIT)
        u = point.standard_uncertainty.magnitude_in(ctx.VOLTAGE_UNIT)
        scored.append({
            "source_ref": point.source_ref, "state_of_charge": z,
            "measured_v": measured, "declared_v": predicted,
            "residual_v": measured - predicted, "standard_uncertainty_v": u,
            "standardized_residual": (measured - predicted) / u,
        })

    if not scored:
        return OcvEmpiricalAssessment(
            status=OcvEmpiricalStatus.EVIDENCE_OUTSIDE_CLAIM, alpha=float(alpha),
            excluded=tuple(excluded), applicability_status=applicability_status,
            why="every supplied point is outside what the model claims to describe",
        )

    statistic = float(sum(row["standardized_residual"] ** 2 for row in scored))
    dof = len(scored)
    p_value = float(chi2.sf(statistic, dof))
    worst = max(scored, key=lambda row: abs(row["standardized_residual"]))
    inadequate = p_value < float(alpha)
    return OcvEmpiricalAssessment(
        status=(OcvEmpiricalStatus.EMPIRICALLY_INADEQUATE if inadequate
                else OcvEmpiricalStatus.EMPIRICALLY_ADEQUATE),
        alpha=float(alpha), scored=tuple(scored), excluded=tuple(excluded),
        chi_square=statistic, degrees_of_freedom=dof, p_value=p_value,
        applicability_status=applicability_status,
        why=(
            f"chi-square {statistic:.4g} on {dof} degrees of freedom, p = {p_value:.3g} "
            f"against alpha {alpha}; worst point SOC {worst['state_of_charge']} misses by "
            f"{worst['residual_v'] * 1e3:+.1f} mV ({worst['standardized_residual']:+.1f} sigma)"
        ),
    )
