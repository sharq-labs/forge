"""Deterministic generation of the Blind v2 primary corpus.

The generator states an *intent* -- this family, this condition, this margin,
these unit spellings -- and then hands the declaration to the oracles. The
oracles decide the truth. When what came out does not match what was intended
the sample is **rejected and logged**, never relabelled: a generator allowed to
write the answer key is a generator that cannot be surprised by its own cases.

Nothing here knows what the system under test would say. Nothing here imports
it.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field

from . import truth, units
from .systems import SYSTEMS, SystemSpec

SEED = 20260910

FAMILIES = (
    "nominal_interior",
    "isolated_violation",
    "missing_evidence",
    "boundary_refusal",
    "unit_representation",
    "compound_mechanism",
)

MARGINS = (
    ("far_inside", 0.20),
    ("moderately_inside", 0.60),
    ("near_inside", 0.98),
    ("exact_boundary", 1.00),
    ("near_outside", 1.02),
    ("moderately_outside", 1.60),
    ("far_outside", 5.00),
)
OUTSIDE_MARGINS = ("near_outside", "moderately_outside", "far_outside")


@dataclass
class Rejection:
    case_intent: str
    system: str
    reason: str
    detail: str


@dataclass
class GenerationLog:
    rejections: list[Rejection] = field(default_factory=list)

    def reject(self, intent: str, system: str, reason: str, detail: str = "") -> None:
        self.rejections.append(Rejection(intent, system, reason, detail))


# ---- unit rendering ------------------------------------------------------
def render(field_name: str, si_value: float, unit: str) -> dict:
    """SI magnitude -> a declaration in ``unit``.

    The inverse of this challenge's own :func:`units.to_si`, and the only place
    a declared number is produced. An affine unit inverts through its offset;
    every other unit through its factor alone.
    """
    spec = units.parse(unit)
    value = (si_value - spec.offset) / spec.factor
    return {"value": value, "unit": unit}


def to_si(declaration: dict) -> dict:
    """A rendered declaration back to SI, by this challenge's own algebra."""
    out: dict[str, float] = {}
    for name, entry in declaration.items():
        out[name] = units.to_si(entry["value"], entry["unit"])
    return out


def render_all(
    si: dict, spec: SystemSpec, rng: random.Random, *, diversify: bool
) -> dict:
    """Render every declared field, optionally in a non-canonical spelling.

    A *span* field is never rendered in an affine unit: a difference stated on
    an offset scale is ambiguous, and the challenge probes that deliberately in
    its own family rather than letting it leak into every other case.
    """
    out: dict[str, dict] = {}
    for name, value in si.items():
        options = spec.units.get(name)
        if options is None:
            continue
        if name in spec.span_fields:
            options = tuple(u for u in options if units.is_ratio_scale(u))
        if diversify and len(options) > 1:
            unit = rng.choice(options)
        else:
            unit = options[0]
        out[name] = render(name, value, unit)
    return out


# ---- levers --------------------------------------------------------------
def _quantity(spec: SystemSpec, si: dict, condition: str) -> float | None:
    forward = spec.cheap or spec.oracle
    return forward(si)["quantities"].get(condition)


def tune(
    spec: SystemSpec,
    si: dict,
    condition: str,
    target: float,
    *,
    log: GenerationLog,
    intent: str,
) -> dict | None:
    """Move one declared field until ``condition`` reads ``target``.

    Bisection on the declaration, using this challenge's own oracle as the
    forward map. Solving for the declaration that produces a stated margin --
    rather than choosing a declaration and reporting whatever margin fell out
    -- is what makes the boundary stratification a design rather than a hope.
    """
    lever = spec.levers.get(condition)
    if lever is None:
        log.reject(intent, spec.system_id, "no_lever", condition)
        return None
    name, direction = lever
    base = si.get(name)
    if base is None or base == 0.0:
        log.reject(intent, spec.system_id, "lever_not_declared", name)
        return None

    def probe(scale: float) -> float | None:
        trial = dict(si)
        trial[name] = base * scale
        if name == "temperature":
            trial["furthest_temperature"] = trial[name]
            trial["coldest_temperature"] = min(
                trial.get("reference_temperature", trial[name]), trial[name]
            )
        if name == "cell_temperature":
            trial["resistance_reference_temperature"] = si.get(
                "resistance_reference_temperature"
            )
        return _quantity(spec, trial, condition)

    lo, hi = 1e-6, 1e6
    current = probe(1.0)
    if current is None:
        log.reject(intent, spec.system_id, "condition_not_computable", condition)
        return None

    def residual(scale: float) -> float:
        value = probe(scale)
        return math.inf if value is None else value - target

    # bracket
    a, b = lo, hi
    fa, fb = residual(a), residual(b)
    if not (math.isfinite(fa) and math.isfinite(fb)) or fa * fb > 0.0:
        log.reject(intent, spec.system_id, "no_bracket", f"{condition}->{target}")
        return None
    # Bisect in log space until the bracket is two adjacent floats. Stopping
    # at a relative tolerance instead would leave the lever hundreds of ULPs
    # off, and a quantity amplified by the forward map thousands -- which is
    # the difference between an exact-boundary case and one that only looks
    # like one.
    best_scale, best_residual = 1.0, abs(residual(1.0))
    for _ in range(400):
        mid = math.sqrt(a * b)
        if mid <= a or mid >= b:
            break
        fm = residual(mid)
        if not math.isfinite(fm):
            log.reject(intent, spec.system_id, "non_finite_probe", condition)
            return None
        if abs(fm) < best_residual:
            best_scale, best_residual = mid, abs(fm)
        if fm == 0.0:
            best_scale = mid
            break
        if fa * fm < 0.0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    scale = best_scale
    tuned = dict(si)
    tuned[name] = base * scale
    if name == "temperature":
        tuned["furthest_temperature"] = tuned[name]
        tuned["coldest_temperature"] = min(
            tuned.get("reference_temperature", tuned[name]), tuned[name]
        )
    return tuned


def bound_target(condition: str, model_id: str, margin: float) -> tuple[float, str] | None:
    """The quantity value that sits ``margin`` fractions into/past a bound."""
    for bound in truth.bound_register()["bounds"]:
        if bound["name"] != condition:
            continue
        for occurrence in bound["occurrences"]:
            if occurrence["model_id"] != model_id:
                continue
            maximum = occurrence.get("maximum")
            minimum = occurrence.get("minimum")
            if maximum is not None:
                return float(maximum["magnitude"]) * margin, "maximum"
            if minimum is not None:
                floor = float(minimum["magnitude"])
                if floor == 0.0:
                    # a strictly-positive floor: inside is above it, outside
                    # is at or below it. Scale about a unit reference instead
                    # of about zero, which has no fractions.
                    return (1.0 - margin) if margin <= 1.0 else -(margin - 1.0), "minimum_zero"
                return floor / margin if margin else floor, "minimum"
    return None


def case_id(system_id: str, index: int) -> str:
    tag = system_id.replace(".", "_").upper()
    return f"V2-{tag}-{index:05d}"


def digest_case(case: dict) -> str:
    payload = json.dumps(case, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---- boundary representability ------------------------------------------
def _ulp(x: float) -> float:
    return math.ulp(abs(x)) if x != 0.0 else math.ulp(0.0)


def classify_boundary(value: float | None, bound: float | None) -> dict:
    """How close a computed quantity actually sits to its declared bound.

    A margin the generator *asked* for is not a margin it *achieved*: the
    declaration is a float, the forward map is floating point, and a bound like
    0.1 is not a binary fraction. This records which of the three the case
    really is, so that "exact boundary" never appears in a report as a claim
    the arithmetic could not support.
    """
    if value is None or bound is None:
        return {"kind": None, "ulps": None}
    if value == bound:
        return {"kind": "MATHEMATICAL_BOUNDARY", "ulps": 0.0}
    ulps = abs(value - bound) / _ulp(bound)
    if ulps <= 1.0:
        return {"kind": "WITHIN_1_ULP_BOUNDARY", "ulps": ulps}
    return {"kind": "REPRESENTABLE_BOUNDARY", "ulps": ulps}


def snap_to_bound(
    spec: SystemSpec, si: dict, condition: str, bound: float
) -> tuple[dict, dict]:
    """Nudge the lever by single ULPs, trying for exact equality with a bound.

    Returns the best declaration found and its boundary classification. Where
    exact equality is unreachable -- which is the ordinary case, since a bound
    like 0.1 has no exact binary representation and the forward map rounds --
    the case says WITHIN_1_ULP_BOUNDARY and means it.
    """
    lever = spec.levers.get(condition)
    if lever is None:
        return si, {"kind": None, "ulps": None}
    name, _ = lever
    best = dict(si)
    best_class = classify_boundary(_quantity(spec, best, condition), bound)
    if best_class["kind"] == "MATHEMATICAL_BOUNDARY":
        return best, best_class
    current = si[name]
    for step in range(-24, 25):
        trial = dict(si)
        trial[name] = math.nextafter(current, math.inf if step > 0 else -math.inf)
        for _ in range(abs(step) - 1):
            trial[name] = math.nextafter(
                trial[name], math.inf if step > 0 else -math.inf
            )
        if name == "temperature":
            trial["furthest_temperature"] = trial[name]
            trial["coldest_temperature"] = min(
                trial.get("reference_temperature", trial[name]), trial[name]
            )
        value = _quantity(spec, trial, condition)
        candidate = classify_boundary(value, bound)
        if candidate["ulps"] is None:
            continue
        if candidate["ulps"] < (best_class["ulps"] if best_class["ulps"] is not None else math.inf):
            best, best_class = trial, candidate
        if candidate["kind"] == "MATHEMATICAL_BOUNDARY":
            break
    return best, best_class
