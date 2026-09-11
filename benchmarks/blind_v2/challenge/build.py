"""Assemble the frozen Blind v2 corpus: primary cases, shadows, truth.

The shape of a run:

1. propose a candidate declaration with a stated *intent*;
2. render it into declared units, then read it back through this challenge's
   own unit algebra -- so a case that cannot survive its own round trip never
   reaches the corpus;
3. ask the oracles what it is;
4. let the truth engine decide the outcome from what the oracles produced;
5. file it under the family it turned out to be, not the one it was aimed at.

Step 5 is the point. A generator that filed cases under the family it intended
would be asserting truth rather than measuring it, and its "compound" family
would contain whatever it happened to believe was compound.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict

from . import generator as gen
from . import truth, units
from .systems import SYSTEMS, SystemSpec

TARGET_PER_SYSTEM = 120
QUOTAS = {
    "nominal_interior": 30,
    "isolated_violation": 28,
    "missing_evidence": 22,
    "boundary_refusal": 14,
    "unit_representation": 14,
    "compound_mechanism": 12,
}
assert sum(QUOTAS.values()) == TARGET_PER_SYSTEM

WRONG_DIMENSION_UNIT = {
    "ohm": "volt",
    "kiloohm": "volt",
    "milliohm": "volt",
    "volt": "ampere",
    "millivolt": "ampere",
    "ampere": "volt",
    "milliampere": "volt",
    "kelvin": "watt",
    "second": "meter",
    "minute": "meter",
    "hour": "meter",
    "watt": "kelvin",
    "milliwatt": "kelvin",
    "kilowatt": "kelvin",
    "meter": "second",
    "millimeter": "second",
    "centimeter": "second",
    "ampere_hour": "volt",
    "milliampere_hour": "volt",
    "coulomb": "volt",
    "dimensionless": "meter",
    "joule / kelvin": "watt",
    "watt / kelvin": "joule",
    "meter ** 2 / second": "meter",
    "1 / second": "meter",
    "1 / hour": "meter",
    "joule / mole": "watt",
    "kilojoule / mole": "watt",
    "mole / meter ** 3": "kelvin",
    "kilogram / meter ** 3": "kelvin",
    "joule / kelvin / kilogram": "watt",
    "meter ** 3": "second",
    "meter ** 2": "second",
    "watt / kelvin / meter": "watt",
    "1 / kelvin": "meter",
    "meter / second": "kelvin",
    "percent": "meter",
    "liter": "second",
}

#: A spelling no unit registry in this repository defines. Named here rather
#: than invented per case so the report can say exactly what was tried: the
#: task's own unit list offers "kilohm", and the shipped registry defines
#: "kiloohm" instead. Declaring the one that does not exist is a legitimate
#: refusal probe and not an invented unit.
UNDEFINED_UNIT = "kilohm"


def _round_trip(declaration: dict) -> dict:
    """Declared units back to SI, by this challenge's own algebra."""
    return {name: units.to_si(e["value"], e["unit"]) for name, e in declaration.items()}


def _case_skeleton(spec: SystemSpec, index: int, family: str, intent: dict) -> dict:
    return {
        "case_id": gen.case_id(spec.system_id, index),
        "system": spec.system_id,
        "model_id": spec.model_id,
        "family": family,
        "intent": intent,
    }


def _oracle_summary(result: dict, spec: SystemSpec, assessment: dict) -> dict:
    """What the two routes produced, and whether they count as independent."""
    routes = result.get("routes", {})
    worst = None
    for route in routes.values():
        for key in ("gap", "worst_gap"):
            value = route.get(key)
            if value is not None and (worst is None or value > worst):
                worst = value
    deciding = set(assessment["violated"] or assessment["unknown"]) or set(
        assessment["satisfied"]
    )
    dual = bool(routes) and bool(deciding & set(spec.dual_conditions))
    level = None
    if dual:
        levels = {r.get("independence_level") for r in routes.values()}
        # The route may name its own strength (the DC operating point does,
        # because ngspice either ran or it did not). Otherwise the system's
        # registered level stands, and it is the weaker claim of the two.
        level = "A" if "A" in levels else spec.independence_level
    return {
        "routes": {k: {kk: vv for kk, vv in v.items()} for k, v in routes.items()},
        "worst_route_gap": worst,
        "dual_oracle": dual,
        "independence_level": level,
        "tolerance_basis": (
            "relative agreement between two independently implemented routes; "
            "the tolerance is the disagreement itself, recorded and never widened"
        ),
    }


def _truth_class(spec: SystemSpec, assessment: dict) -> str:
    """Which kind of claim this case's truth rests on."""
    deciding = assessment["violated"] or assessment["unknown"]
    if not deciding:
        deciding = assessment["satisfied"]
    classes = set()
    register = {b["name"]: b["class"] for b in truth.bound_register()["bounds"]}
    for name in deciding:
        classes.add(register.get(name, "UNRESOLVED"))
    if not classes:
        return "UNRESOLVED"
    if classes <= {"ANALYTICALLY_DERIVED", "SOURCE_BACKED"}:
        return "INDEPENDENT_SCIENTIFIC"
    if classes <= {"INTERNAL_POLICY", "CONTRACT_DECLARED"}:
        return "POLICY_DEPENDENT"
    return "MIXED_SCIENCE_AND_POLICY"


def _causal(spec: SystemSpec, si: dict, assessment: dict) -> dict:
    """Counterfactual repair, one defect at a time, on the declaration itself.

    Repairing a *condition* means moving the declared field its lever names
    back to the nominal interior and recomputing everything downstream. Other
    defects are left exactly where they were, which is what makes the result a
    statement about causation rather than about ordering.
    """
    nominal_reference = si.get("__nominal__", {})

    def repair(name: str):
        lever = spec.levers.get(name)
        if lever is None:
            return None
        field_name, _ = lever
        if field_name not in nominal_reference:
            return None
        repaired = {k: v for k, v in si.items() if k != "__nominal__"}
        repaired[field_name] = nominal_reference[field_name]
        if field_name == "temperature":
            repaired["furthest_temperature"] = repaired[field_name]
            repaired["coldest_temperature"] = min(
                repaired.get("reference_temperature", repaired[field_name]),
                repaired[field_name],
            )
        try:
            return spec.oracle(repaired)["quantities"]
        except Exception:
            return None

    quantities = spec.oracle({k: v for k, v in si.items() if k != "__nominal__"})[
        "quantities"
    ]
    return truth.causal_truth(spec.model_id, quantities, repair)


def _boundary_record(spec: SystemSpec, assessment: dict, condition: str | None) -> dict:
    if condition is None:
        return {"kind": None, "ulps": None, "condition": None}
    value = assessment["condition_values"].get(condition)
    target = gen.bound_target(condition, spec.model_id, 1.0)
    bound = target[0] if target else None
    record = gen.classify_boundary(value, bound)
    record["condition"] = condition
    return record


# =========================================================================
# candidate proposers
# =========================================================================
def _finish(
    spec: SystemSpec,
    si: dict,
    nominal: dict,
    intent: dict,
    rng: random.Random,
    *,
    diversify: bool,
) -> dict | None:
    """Render, round-trip, assess. ``None`` when the case cannot stand up."""
    declaration = gen.render_all(si, spec, rng, diversify=diversify)
    recovered = _round_trip(declaration)
    for name, value in recovered.items():
        target = si.get(name)
        if target is None:
            continue
        if not math.isfinite(value):
            return None
        scale = max(abs(target), 1e-30)
        if abs(value - target) / scale > 1e-9:
            return None
    full = dict(si)
    full.update(recovered)
    extras = spec.extras(rng) if spec.extras else {}
    result = spec.oracle(full)
    assessment = truth.assess(spec.model_id, result["quantities"])
    payload = {
        "declaration": declaration,
        "extras": extras,
        "metrics": spec.metrics(full, extras) if spec.metrics else {},
        "si": {k: v for k, v in full.items() if k != "__nominal__"},
        "assessment": assessment,
        "oracle": _oracle_summary(result, spec, assessment),
        "intent": intent,
        "nominal": nominal,
    }
    return payload


def propose_nominal(spec, rng, log):
    nominal = spec.nominal(rng)
    return _finish(spec, dict(nominal), nominal, {"kind": "nominal_interior"}, rng, diversify=False)


def propose_margin(spec, rng, log, *, inside: bool):
    nominal = spec.nominal(rng)
    conditions = [c for c in spec.levers if gen.bound_target(c, spec.model_id, 1.0)]
    if not conditions:
        return None
    condition = rng.choice(sorted(conditions))
    pool = [m for m, f in gen.MARGINS if (m not in gen.OUTSIDE_MARGINS) == inside]
    margin_name = rng.choice(pool)
    fraction = dict(gen.MARGINS)[margin_name]
    target = gen.bound_target(condition, spec.model_id, fraction)
    if target is None:
        return None
    value, kind = target
    if kind == "minimum_zero":
        field_name = spec.levers[condition][0]
        si = dict(nominal)
        if inside:
            si[field_name] = abs(si.get(field_name, 1.0)) * fraction
        else:
            si[field_name] = rng.choice([0.0, -abs(si.get(field_name, 1.0)) * fraction])
        intent = {
            "kind": "forced_non_positive" if not inside else "scaled_positive",
            "condition": condition,
            "margin": margin_name,
        }
        return _finish(spec, si, nominal, intent, rng, diversify=False)
    tuned = gen.tune(spec, nominal, condition, value, log=log, intent=condition)
    if tuned is None:
        return None
    boundary = None
    if margin_name == "exact_boundary":
        tuned, boundary = gen.snap_to_bound(spec, tuned, condition, value)
    intent = {
        "kind": "margin",
        "condition": condition,
        "margin": margin_name,
        "target_quantity": value,
        "boundary": boundary,
    }
    return _finish(spec, tuned, nominal, intent, rng, diversify=False)


def propose_missing(spec, rng, log):
    nominal = spec.nominal(rng)
    groups = sorted(spec.evidence)
    if not groups:
        return None
    count = rng.choice([1, 1, 2])
    chosen = rng.sample(groups, min(count, len(groups)))
    dropped: list[str] = []
    si = dict(nominal)
    for condition in chosen:
        for key in spec.evidence[condition]:
            if key in si:
                si.pop(key)
                dropped.append(key)
    if not dropped:
        return None
    intent = {"kind": "missing_evidence", "dropped": sorted(set(dropped)), "conditions": chosen}
    return _finish(spec, si, nominal, intent, rng, diversify=False)


def propose_units(spec, rng, log):
    nominal = spec.nominal(rng)
    diversifiable = [
        name
        for name, options in spec.units.items()
        if len(options) > 1 and name in nominal and name not in spec.span_fields
    ]
    if not diversifiable:
        return None
    body = rng.random()
    if body < 0.5:
        si = dict(nominal)
        intent_kind = "unit_diverse_nominal"
    else:
        conditions = [c for c in spec.levers if gen.bound_target(c, spec.model_id, 1.0)]
        if not conditions:
            return None
        condition = rng.choice(sorted(conditions))
        target = gen.bound_target(condition, spec.model_id, rng.choice([1.6, 5.0]))
        if target is None or target[1] == "minimum_zero":
            return None
        si = gen.tune(spec, nominal, condition, target[0], log=log, intent=condition)
        if si is None:
            return None
        intent_kind = "unit_diverse_violation"
    intent = {"kind": intent_kind, "diversifiable": sorted(diversifiable)}
    return _finish(spec, si, nominal, intent, rng, diversify=True)


def propose_refusal(spec, rng, log):
    """A declaration the public contract has no legal reading for."""
    nominal = spec.nominal(rng)
    modes = ["undefined_unit", "wrong_dimension", "non_finite"]
    if spec.span_fields:
        modes.append("affine_span")
    mode = rng.choice(modes)
    declaration = gen.render_all(dict(nominal), spec, rng, diversify=False)
    if not declaration:
        return None
    if mode == "affine_span":
        field_name = rng.choice(sorted(spec.span_fields & set(declaration)))
        span_kelvin = declaration[field_name]["value"]
        declaration = dict(declaration)
        declaration[field_name] = {"value": span_kelvin, "unit": "degC"}
        stage = "unit_compatibility"
        note = (
            "a span declared on an affine scale: 80 degC as a difference is 80 K "
            "and as a state is 353.15 K, and nothing in the declaration says which"
        )
        truth_class = "MIXED_SCIENCE_AND_POLICY"
        acceptable = ["REJECTED_AT_BOUNDARY"]
    elif mode == "undefined_unit":
        candidates = [n for n, e in declaration.items() if units.dimension(e["unit"]) == units.dimension("ohm")]
        field_name = rng.choice(sorted(candidates)) if candidates else rng.choice(sorted(declaration))
        declaration = dict(declaration)
        declaration[field_name] = {"value": declaration[field_name]["value"], "unit": UNDEFINED_UNIT}
        stage = "unit_compatibility"
        note = f"{UNDEFINED_UNIT!r} is not a unit any registry in this repository defines"
        truth_class = "CONTRACT_ONLY"
        acceptable = ["REJECTED_AT_BOUNDARY"]
    elif mode == "wrong_dimension":
        candidates = [n for n, e in declaration.items() if e["unit"] in WRONG_DIMENSION_UNIT]
        if not candidates:
            return None
        field_name = rng.choice(sorted(candidates))
        declaration = dict(declaration)
        declaration[field_name] = {
            "value": declaration[field_name]["value"],
            "unit": WRONG_DIMENSION_UNIT[declaration[field_name]["unit"]],
        }
        stage = "unit_compatibility"
        note = "the declared unit has the wrong dimension for the field it fills"
        truth_class = "CONTRACT_ONLY"
        acceptable = ["REJECTED_AT_BOUNDARY"]
    else:
        field_name = rng.choice(sorted(declaration))
        declaration = dict(declaration)
        declaration[field_name] = {
            "value": rng.choice([float("inf"), float("nan"), -float("inf")]),
            "unit": declaration[field_name]["unit"],
        }
        stage = "schema_type"
        note = "a non-finite magnitude is not a measurement"
        truth_class = "CONTRACT_ONLY"
        acceptable = ["REJECTED_AT_BOUNDARY"]
    return {
        "declaration": declaration,
        "si": None,
        "assessment": None,
        "oracle": {
            "routes": {},
            "worst_route_gap": None,
            "dual_oracle": False,
            "independence_level": None,
            "tolerance_basis": "not applicable: the declaration has no legal reading",
        },
        "extras": {},
        "metrics": {},
        "intent": {
            "kind": "boundary_refusal",
            "mode": mode,
            "field": field_name,
            "predicted_stage": stage,
            "note": note,
            "truth_class": truth_class,
            "acceptable_outcomes": acceptable,
        },
        "nominal": nominal,
    }


# =========================================================================
# assembly
# =========================================================================
def _family_of(candidate: dict) -> str:
    intent = candidate["intent"]
    if intent["kind"] == "boundary_refusal":
        return "boundary_refusal"
    assessment = candidate["assessment"]
    if assessment is None:
        return "boundary_refusal"
    if intent["kind"] in ("unit_diverse_nominal", "unit_diverse_violation"):
        return "unit_representation"
    if intent["kind"] == "missing_evidence":
        return "missing_evidence" if assessment["unknown"] else "nominal_interior"
    defects = len(assessment["violated"]) + len(assessment["unknown"])
    if defects == 0:
        return "nominal_interior"
    if defects == 1:
        return "isolated_violation"
    return "compound_mechanism"


def _record(spec: SystemSpec, candidate: dict, index: int) -> dict:
    intent = candidate["intent"]
    family = _family_of(candidate)
    case = {
        "case_id": gen.case_id(spec.system_id, index),
        "system": spec.system_id,
        "model_id": spec.model_id,
        "family": family,
        "declaration": candidate["declaration"],
        "extras": candidate.get("extras") or {},
        "intent": intent,
    }
    if candidate["assessment"] is None:
        truth_record = {
            "case_id": case["case_id"],
            "outcome": "REJECTED_AT_BOUNDARY",
            "acceptable_outcomes": intent["acceptable_outcomes"],
            "refusal_stage": intent["predicted_stage"],
            "truth_class": intent["truth_class"],
            "valid_mechanisms": [],
            "unknown_mechanisms": [],
            "reason_status": "CONTRACT_REFUSAL",
            "causal": {"class": "NOT_APPLICABLE", "catchers": [], "redundant": []},
            "precedence_dependent": False,
            "channel_ambiguous": False,
            "boundary": {"kind": None, "ulps": None, "condition": None},
            "oracle": candidate["oracle"],
            "expected_metrics": {},
            "note": intent["note"],
        }
        return case, truth_record

    assessment = candidate["assessment"]
    si = dict(candidate["si"])
    si["__nominal__"] = candidate["nominal"]
    reasons = truth.reason_truth(assessment)
    causal = _causal(spec, si, assessment)
    deciding = (assessment["violated"] or assessment["unknown"] or [None])[0]
    boundary = _boundary_record(spec, assessment, deciding)
    channel_ambiguous = intent.get("kind") == "forced_non_positive"
    acceptable = [assessment["outcome"]]
    if channel_ambiguous:
        acceptable = sorted({assessment["outcome"], "REJECTED_AT_BOUNDARY"})
    truth_record = {
        "case_id": case["case_id"],
        "outcome": assessment["outcome"],
        "acceptable_outcomes": acceptable,
        "refusal_stage": None if assessment["outcome"] == "SUPPORTED" else "scientific_applicability",
        "truth_class": _truth_class(spec, assessment),
        "valid_mechanisms": reasons["valid_mechanisms"],
        "unknown_mechanisms": assessment["unknown"],
        "reason_status": reasons["reason_status"],
        "causal": causal,
        "precedence_dependent": assessment["precedence_dependent"],
        "channel_ambiguous": channel_ambiguous,
        "boundary": boundary,
        "condition_values": {
            k: v for k, v in assessment["condition_values"].items() if v is not None
        },
        "satisfied": assessment["satisfied"],
        "violated": assessment["violated"],
        "unknown": assessment["unknown"],
        "oracle": candidate["oracle"],
        "expected_metrics": candidate.get("metrics") or {},
    }
    return case, truth_record


PROPOSERS = (
    ("nominal_interior", lambda s, r, l: propose_nominal(s, r, l)),
    ("inside_margin", lambda s, r, l: propose_margin(s, r, l, inside=True)),
    ("outside_margin", lambda s, r, l: propose_margin(s, r, l, inside=False)),
    ("missing_evidence", lambda s, r, l: propose_missing(s, r, l)),
    ("unit_representation", lambda s, r, l: propose_units(s, r, l)),
    ("boundary_refusal", lambda s, r, l: propose_refusal(s, r, l)),
)


def build_system(spec: SystemSpec, log: gen.GenerationLog) -> tuple[list, list]:
    """Fill the family quotas, then fill what is left with whatever is valid.

    Not every system can supply every family. ``thermal.conduction1d`` declares
    one condition, so it has no compound mechanism to find and never will; a
    loop that insisted would spin forever and a quota that pretended would be
    filled with mislabelled cases. Phase one aims at the quotas; phase two
    takes valid cases in whatever family they fall into, and the shortfall is
    reported rather than papered over.
    """
    rng = random.Random(f"{gen.SEED}:{spec.system_id}")
    filled: dict[str, list] = {family: [] for family in QUOTAS}
    seen: set[str] = set()
    surplus = 0

    def total() -> int:
        return sum(len(v) for v in filled.values())

    def attempt(respect_quota: bool) -> None:
        nonlocal surplus
        name, proposer = PROPOSERS[rng.randrange(len(PROPOSERS))]
        try:
            candidate = proposer(spec, rng, log)
        except Exception as exc:
            log.reject(name, spec.system_id, "proposer_exception", f"{type(exc).__name__}: {exc}")
            return
        if candidate is None:
            log.reject(name, spec.system_id, "not_constructible", name)
            return
        fingerprint = hashlib.sha256(
            json.dumps(candidate["declaration"], sort_keys=True).encode()
        ).hexdigest()
        if fingerprint in seen:
            log.reject(name, spec.system_id, "duplicate_declaration", fingerprint[:12])
            return
        family = _family_of(candidate)
        if respect_quota and len(filled[family]) >= QUOTAS[family]:
            surplus += 1
            return
        seen.add(fingerprint)
        filled[family].append(candidate)

    for _ in range(PHASE_ONE_ATTEMPTS):
        if total() >= TARGET_PER_SYSTEM:
            break
        attempt(respect_quota=True)
    for _ in range(PHASE_TWO_ATTEMPTS):
        if total() >= TARGET_PER_SYSTEM:
            break
        attempt(respect_quota=False)

    cases, truths = [], []
    index = 1
    for family in FAMILY_ORDER:
        for candidate in filled[family]:
            case, truth_record = _record(spec, candidate, index)
            cases.append(case)
            truths.append(truth_record)
            index += 1
    log.reject("surplus", spec.system_id, "surplus_not_selected", str(surplus))
    if total() < TARGET_PER_SYSTEM:
        log.reject(
            "quota", spec.system_id, "target_not_reached",
            f"{total()}/{TARGET_PER_SYSTEM}",
        )
    return cases, truths


PHASE_ONE_ATTEMPTS = 3000
PHASE_TWO_ATTEMPTS = 3000


FAMILY_ORDER = (
    "nominal_interior",
    "isolated_violation",
    "missing_evidence",
    "boundary_refusal",
    "unit_representation",
    "compound_mechanism",
)
