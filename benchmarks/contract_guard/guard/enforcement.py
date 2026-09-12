"""Does the runtime enforce the bound the record publishes?

Every condition publishes a structured bound: a minimum, a maximum, and
whether each edge is inside. This module hands the model's own
``assess_validity`` a synthetic value and asks how it classifies it. Five
probes per bounded edge:

    far inside, just inside, exactly on the edge, just outside, far outside

and the classification must be the one the record's inclusivity flag predicts.
That is the whole check, and it needs no domain nominal, so it reaches every
condition in every model rather than the ones someone wrote a fixture for.

A condition declared ``conservative_screen`` refuses below its floor as UNKNOWN
rather than VIOLATED -- a gap in the evidence, not a finding against the design
-- and the probe expects exactly that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SATISFIED = "SATISFIED"
VIOLATED = "VIOLATED"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Probe:
    edge: str        # "minimum" | "maximum"
    position: str    # far_inside | just_inside | on_edge | just_outside | far_outside
    value: float
    expected: str
    observed: str

    @property
    def agrees(self) -> bool:
        return self.expected == self.observed


def _classify(model, ref, payload_value: float) -> str:
    """Ask the model how it classifies one synthetic value for one condition."""
    from engcore.scientific.units.quantity import Quantity

    units = ref.units or "dimensionless"
    if ref.kind == "CrossLimitCondition":
        # The condition forms numerator/denominator from the declared
        # namespace, so the probe supplies a pair whose ratio is the value.
        payload = ref.condition.to_dict()
        numerator = payload["numerator"]
        denominator = payload["denominator"]
        declared = {
            numerator: Quantity(payload_value, "kelvin"),
            denominator: Quantity(1.0, "kelvin"),
        }
        assessment = model.assess_validity(declared=declared, assembled={})
    else:
        quantity = {ref.name: Quantity(payload_value, units)}
        if ref.is_derived:
            assessment = model.assess_validity(declared={}, assembled=quantity)
        else:
            assessment = model.assess_validity(declared=quantity, assembled={})
    if ref.name in assessment.violated:
        return VIOLATED
    if ref.name in assessment.satisfied:
        return SATISFIED
    return UNKNOWN


def _step(value: float) -> float:
    """A step that is small against the bound but not lost in its own ULP."""
    return max(abs(value) * 1e-9, 1e-12)


def probes_for(ref) -> list[tuple[str, str, float, str]]:
    """(edge, position, value, expected) for every edge the record declares."""
    out: list[tuple[str, str, float, str]] = []
    outside = UNKNOWN if ref.conservative_screen else VIOLATED

    if ref.minimum is not None:
        low, delta = ref.minimum, _step(ref.minimum or 1.0)
        on_edge = SATISFIED if ref.minimum_inclusive else outside
        span = max(abs(low), 1.0)
        out += [
            ("minimum", "far_inside", low + span, SATISFIED),
            ("minimum", "just_inside", low + delta, SATISFIED),
            ("minimum", "on_edge", low, on_edge),
            ("minimum", "just_outside", low - delta, outside),
            ("minimum", "far_outside", low - span, outside),
        ]
    if ref.maximum is not None:
        high, delta = ref.maximum, _step(ref.maximum or 1.0)
        on_edge = SATISFIED if ref.maximum_inclusive else outside
        span = max(abs(high), 1.0)
        out += [
            ("maximum", "far_inside", high - span, SATISFIED),
            ("maximum", "just_inside", high - delta, SATISFIED),
            ("maximum", "on_edge", high, on_edge),
            ("maximum", "just_outside", high + delta, outside),
            ("maximum", "far_outside", high + span, outside),
        ]
    return out


def check(ref) -> list[Probe]:
    """Run every probe for one condition. Returns them all, agreeing or not."""
    from . import records

    model = records.model_by_id(ref.model_id)
    results: list[Probe] = []
    for edge, position, value, expected in probes_for(ref):
        # A probe that would cross the OTHER edge tests nothing about this one,
        # and "crossing" has to respect that edge's own inclusivity: for a
        # coulombic efficiency in (0, 1], the far-inside maximum probe lands on
        # 0.0, which is the EXCLUDED minimum. Skipping only values strictly
        # past the edge let that through and reported the Core for enforcing
        # its own bound.
        if edge == "minimum" and ref.maximum is not None:
            if value > ref.maximum or (
                value == ref.maximum and not ref.maximum_inclusive
            ):
                continue
        if edge == "maximum" and ref.minimum is not None:
            if value < ref.minimum or (
                value == ref.minimum and not ref.minimum_inclusive
            ):
                continue
        if not math.isfinite(value):
            continue
        try:
            observed = _classify(model, ref, value)
        except Exception as exc:  # a refusal is an answer, and is recorded
            observed = f"REFUSED:{type(exc).__name__}"
        results.append(Probe(edge, position, value, expected, observed))
    return results


def disagreements(ref) -> list[Probe]:
    return [p for p in check(ref) if not p.agrees]


def survey(refs=None) -> dict:
    """Probe every condition on the shipped surface and report the aggregate."""
    from . import records

    conditions = list(records.conditions() if refs is None else refs)
    probes = 0
    disagreeing: list[dict] = []
    for ref in conditions:
        for probe in check(ref):
            probes += 1
            if probe.agrees:
                continue
            disagreeing.append(
                {
                    "condition": ref.ref,
                    "edge": probe.edge,
                    "position": probe.position,
                    "value": probe.value,
                    "expected": probe.expected,
                    "observed": probe.observed,
                }
            )
    return {
        "conditions": len(conditions),
        "probes": probes,
        "disagreements": disagreeing,
    }
