"""Phase 7 -- local sensitivity and a bounded robustness envelope, from real runs only.

Sensitivity
-----------
For each perturbable input the claim states, the capability is re-run at
``x0 * (1 - h)`` and ``x0 * (1 + h)`` (every run bound and judged exactly as a
UQ variant is). From the two runs and the reported one:

* local sensitivity ``dy/dx`` by central difference;
* normalized sensitivity ``(dy/dx) * x0 / y0`` -- only when both units are on
  a ratio scale (an offset unit such as degC has no meaningful ratio) and
  neither nominal is zero;
* a monotonicity observation (the two one-sided differences agree in sign);
* a nonlinearity warning when the second difference is not small against the
  first (the central difference is then a poor local slope).

A numerical sensitivity is a property of the declared model at this operating
point. It is **not** a causal statement about the world, and the record says so.

Robustness
----------
"How far can this input move before the claim stops holding?" -- answered one
input at a time, within a declared search limit, by bracketing and bisection
over real runs. The claim holds at a point when the run is usable and the
claim's comparison is satisfied over ``value -/+`` the nominal band's
half-widths (when the claim demands uncertainty, that band is *assumed* not to
change with the input: an assumption the envelope records, because the band is
not re-quantified at every point). Each side ends in one of:

``FAILS_BEYOND``  the comparison fails past the resolved boundary;
``DOMAIN_ENDS``   the run stops being usable (a model leaves its domain, the
                  system refuses) -- beyond it the answer is UNKNOWN, not "holds";
``SEARCH_LIMIT``  the claim held up to the declared limit -- beyond it UNKNOWN.

Joint variation of several inputs is not explored; the envelope says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.units.quantity import Quantity, is_delta_unit
from .._records import tagged_digest
from ..capabilities import declared_path
from ..errors import ClaimLayerError
from ..uq_studies import run_inputs_for, run_variant

_SENS_TAG = "crafty.claims.sensitivity/1"
_ROBUST_TAG = "crafty.claims.robustness/1"
NONLINEARITY_RATIO = 0.1
_OFFSET_UNITS = {"degree_Celsius", "degree_Fahrenheit", "degC", "degF"}


class SensitivityError(ClaimLayerError):
    """A sensitivity or robustness study was asked for something no declaration supports."""


def _perturbable(assessment: Any, registry: Any) -> tuple[Any, dict[str, Quantity]]:
    if assessment.plan is None or assessment.report is None or assessment.execution is None or not assessment.execution.bound:
        raise SensitivityError("a sensitivity study perturbs a bound run; this assessment has none")
    declaration = registry.get(assessment.plan.capability_id)
    allowed = {p.path for p in declaration.perturbable}
    stated = run_inputs_for(assessment.claim, declaration)
    return declaration, {path: value for path, value in sorted(stated.items()) if declared_path(path) in allowed and isinstance(value, Quantity)}


def _ratio_scale(units: str) -> bool:
    text = str(units)
    return text not in _OFFSET_UNITS and not is_delta_unit(text) and "celsius" not in text.lower() and "fahrenheit" not in text.lower()


@dataclass(frozen=True)
class ParameterSensitivity:
    path: str
    nominal: float
    units: str
    step: float
    minus: Mapping[str, Any]
    plus: Mapping[str, Any]
    derivative: float | None
    normalized: float | None
    monotone: str | None
    warnings: tuple[str, ...]
    problem: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "nominal": self.nominal, "units": self.units, "relative_step": self.step,
            "minus": dict(self.minus), "plus": dict(self.plus), "derivative": self.derivative,
            "normalized": self.normalized, "monotone": self.monotone, "warnings": list(self.warnings), "problem": self.problem,
        }


@dataclass(frozen=True)
class SensitivityReport:
    quantity: str
    units: str
    nominal_value: float
    parameters: tuple[ParameterSensitivity, ...]
    assessment_digest: str | None = None
    plan_digest: str | None = None
    capability_digest: str | None = None

    def ranked(self) -> tuple[ParameterSensitivity, ...]:
        """By |normalized| (or |derivative| where no normalization is meaningful); unknowns last."""
        return tuple(sorted(self.parameters, key=lambda p: (p.derivative is None, -abs(p.normalized if p.normalized is not None else (p.derivative or 0.0)), p.path)))

    def _content_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity, "units": self.units, "nominal_value": self.nominal_value,
            "parameters": [p.to_dict() for p in self.parameters],
            "assessment_digest": self.assessment_digest,
            "plan_digest": self.plan_digest,
            "capability_digest": self.capability_digest,
            "notice": "numerical sensitivity of the declared model at this operating point; not a causal relationship",
        }

    def to_dict(self) -> dict[str, Any]:
        body = self._content_dict()
        return {**body, "report_digest": tagged_digest(_SENS_TAG, body)}

    @property
    def digest(self) -> str:
        return tagged_digest(_SENS_TAG, self._content_dict())


def sensitivity_study(assessment: Any, registry: Any, *, relative_step: float = 0.01, parameters: tuple[str, ...] | None = None) -> SensitivityReport:
    """Central-difference sensitivity of the claim's QOI to every perturbable stated input (or the named ones)."""
    if not 0.0 < relative_step < 0.5:
        raise SensitivityError("relative_step must lie in (0, 0.5)")
    declaration, inputs = _perturbable(assessment, registry)
    if parameters is not None:
        unknown = sorted(set(parameters) - set(inputs))
        if unknown:
            raise SensitivityError(f"{unknown} are not perturbable inputs this claim states")
        inputs = {p: inputs[p] for p in sorted(parameters)}
    plan, qoi = assessment.plan, assessment.plan.content["qoi"]
    y0 = float(assessment.report.values[qoi["name"]].to(qoi["units"]).magnitude)
    base = run_inputs_for(assessment.claim, declaration)
    out = []
    for path, nominal in inputs.items():
        x0 = nominal.magnitude
        runs = {}
        for side, sign in (("minus", -1.0), ("plus", 1.0)):
            x = Quantity(x0 * (1.0 + sign * relative_step), nominal.units)
            v = run_variant(plan, registry, {**base, path: x}, f"{plan.run_id}~sensitivity~{path}~{side}")
            runs[side] = {"input": x.magnitude, "run_id": v.run_id, "value": v.value, "usable": v.usable, "problem": v.problem}
        problem = next((f"{s} run not usable: {r['problem']}" for s, r in runs.items() if not r["usable"]), None)
        derivative = normalized = monotone = None
        warnings: list[str] = []
        if problem is None and x0 != 0.0:
            ym, yp = runs["minus"]["value"], runs["plus"]["value"]
            derivative = (yp - ym) / (2.0 * relative_step * x0)
            if _ratio_scale(nominal.units) and _ratio_scale(qoi["units"]) and y0 != 0.0:
                normalized = derivative * x0 / y0
            else:
                warnings.append("normalized sensitivity is not meaningful for an offset unit or a zero nominal")
            left, right = y0 - ym, yp - y0
            monotone = "increasing" if left > 0 and right > 0 else "decreasing" if left < 0 and right < 0 else "not_monotone" if left * right < 0 else "flat"
            first = abs(yp - ym)
            if first > 0 and abs(yp - 2.0 * y0 + ym) > NONLINEARITY_RATIO * first:
                warnings.append("nonlinear at this step: the second difference is not small against the first")
        elif x0 == 0.0:
            problem = "a zero nominal has no relative perturbation"
        out.append(ParameterSensitivity(path, x0, str(nominal.units), relative_step, runs["minus"], runs["plus"], derivative, normalized, monotone, tuple(warnings), problem))
    return SensitivityReport(
        qoi["name"], qoi["units"], y0, tuple(out),
        assessment_digest=assessment.digest,
        plan_digest=plan.digest,
        capability_digest=plan.capability_digest,
    )


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


class BoundaryKind(str, Enum):
    FAILS_BEYOND = "fails_beyond"
    DOMAIN_ENDS = "domain_ends"
    SEARCH_LIMIT = "search_limit"


@dataclass(frozen=True)
class EnvelopeSide:
    direction: str
    kind: BoundaryKind
    last_holding: float
    first_not_holding: float | None
    evaluations: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction, "kind": self.kind.value, "last_holding": self.last_holding,
            "first_not_holding": self.first_not_holding, "beyond": "unknown" if self.kind is not BoundaryKind.FAILS_BEYOND else "claim fails",
            "evaluations": [dict(e) for e in self.evaluations],
        }


@dataclass(frozen=True)
class RobustnessEnvelope:
    quantity: str
    parameters: Mapping[str, Mapping[str, Any]]
    assumptions: tuple[str, ...]
    established: bool
    reason: str | None = None
    assessment_digest: str | None = None
    plan_digest: str | None = None
    capability_digest: str | None = None

    def _content_dict(self) -> dict[str, Any]:
        return {
            "quantity": self.quantity, "established": self.established, "reason": self.reason,
            "parameters": {k: dict(v) for k, v in sorted(self.parameters.items())}, "assumptions": list(self.assumptions),
            "assessment_digest": self.assessment_digest,
            "plan_digest": self.plan_digest,
            "capability_digest": self.capability_digest,
        }

    def to_dict(self) -> dict[str, Any]:
        body = self._content_dict()
        return {**body, "report_digest": tagged_digest(_ROBUST_TAG, body)}

    @property
    def digest(self) -> str:
        return tagged_digest(_ROBUST_TAG, self._content_dict())


def _holds(assessment: Any, value: float) -> bool:
    comparison = assessment.comparison
    qoi = assessment.plan.content["qoi"]
    lo = hi = 0.0
    if comparison.band_lower is not None:
        lo = comparison.value.magnitude - comparison.band_lower.to(comparison.value.units).magnitude
        hi = comparison.band_upper.to(comparison.value.units).magnitude - comparison.value.magnitude
    constraint = assessment.claim.constraint(assessment.compiled.target)
    return all(constraint.check(Quantity(v, qoi["units"])).satisfied for v in (value - lo, value + hi))


def robustness_envelope(assessment: Any, registry: Any, *, search_limit: float = 0.5, resolution: int = 6,
                        parameters: tuple[str, ...] | None = None) -> RobustnessEnvelope:
    """One input at a time: how far can it move (within ``search_limit`` relative) with the claim still holding."""
    qoi = assessment.plan.content["qoi"]["name"] if assessment.plan is not None else None
    assumptions = (
        "one input varied at a time; joint variation is not explored",
        "the claim's uncertainty band, when demanded, is assumed unchanged away from the nominal point (not re-quantified)",
        f"searched to +/-{search_limit:.0%} of each nominal; beyond a boundary the answer is UNKNOWN",
    )
    if assessment.verdict.value != "supported":
        return RobustnessEnvelope(
            qoi or "", {}, assumptions, False,
            f"the claim is {assessment.verdict.value} at its nominal point; there is no support to bound",
            assessment_digest=assessment.digest,
            plan_digest=None if assessment.plan is None else assessment.plan.digest,
            capability_digest=None if assessment.plan is None else assessment.plan.capability_digest,
        )
    if not 0.0 < search_limit <= 0.95:
        raise SensitivityError("search_limit must lie in (0, 0.95]")
    declaration, inputs = _perturbable(assessment, registry)
    if parameters is not None:
        inputs = {p: inputs[p] for p in sorted(parameters) if p in inputs}
    plan = assessment.plan
    base = run_inputs_for(assessment.claim, declaration)
    counter = [0]

    def probe(path: str, nominal: Quantity, relative: float) -> dict[str, Any]:
        counter[0] += 1
        x = Quantity(nominal.magnitude * (1.0 + relative), nominal.units)
        v = run_variant(plan, registry, {**base, path: x}, f"{plan.run_id}~robust~{path}~{counter[0]}")
        state = "unusable" if not v.usable else ("holds" if _holds(assessment, v.value) else "fails")
        return {"relative": relative, "input": x.magnitude, "run_id": v.run_id, "value": v.value, "state": state, "problem": v.problem}

    out: dict[str, Mapping[str, Any]] = {}
    for path, nominal in inputs.items():
        sides = {}
        for direction, sign in (("decrease", -1.0), ("increase", 1.0)):
            evaluations = []
            last_ok, bad, bad_state = 0.0, None, None
            for k in range(1, 5):
                e = probe(path, nominal, sign * search_limit * k / 4)
                evaluations.append(e)
                if e["state"] != "holds":
                    bad, bad_state = e["relative"], e["state"]
                    break
                last_ok = e["relative"]
            if bad is not None:
                for _ in range(resolution):
                    mid = 0.5 * (last_ok + bad)
                    e = probe(path, nominal, mid)
                    evaluations.append(e)
                    if e["state"] == "holds":
                        last_ok = mid
                    else:
                        bad, bad_state = mid, e["state"]
                kind = BoundaryKind.FAILS_BEYOND if bad_state == "fails" else BoundaryKind.DOMAIN_ENDS
            else:
                kind = BoundaryKind.SEARCH_LIMIT
            to_abs = lambda r: None if r is None else nominal.magnitude * (1.0 + r)
            sides[direction] = EnvelopeSide(direction, kind, to_abs(last_ok), to_abs(bad), tuple(evaluations)).to_dict()
        out[path] = {"nominal": nominal.magnitude, "units": str(nominal.units), **sides}
    return RobustnessEnvelope(
        qoi, out, assumptions, True,
        assessment_digest=assessment.digest,
        plan_digest=plan.digest,
        capability_digest=plan.capability_digest,
    )


def verify_sensitivity_record(payload: Mapping[str, Any]) -> None:
    """Refuse an edited or unsealed serialized sensitivity report."""
    expected = payload.get("report_digest")
    body = {k: v for k, v in payload.items() if k != "report_digest"}
    if not isinstance(expected, str) or tagged_digest(_SENS_TAG, body) != expected:
        raise SensitivityError("the sensitivity report digest does not match its content")


def verify_robustness_record(payload: Mapping[str, Any]) -> None:
    """Refuse an edited or unsealed serialized robustness envelope."""
    expected = payload.get("report_digest")
    body = {k: v for k, v in payload.items() if k != "report_digest"}
    if not isinstance(expected, str) or tagged_digest(_ROBUST_TAG, body) != expected:
        raise SensitivityError("the robustness report digest does not match its content")

__all__ = [
    "BoundaryKind",
    "EnvelopeSide",
    "ParameterSensitivity",
    "RobustnessEnvelope",
    "SensitivityError",
    "SensitivityReport",
    "robustness_envelope",
    "sensitivity_study",
    "verify_robustness_record",
    "verify_sensitivity_record",
]
