"""Independent verdict, mechanism and causal truth.

The rule this module applies is stated once, here, and applied identically to
every system:

* a quantity a condition is stated over that this challenge could not compute
  from the declaration is **UNKNOWN** -- absence of evidence, never a pass;
* a computed quantity outside its declared bound is **VIOLATED**, except where
  the condition declares itself a *conservative screen*, in which case falling
  short of its floor is UNKNOWN: the screen never observed the model being
  wrong, it ran out of evidence before it could observe anything;
* otherwise **SATISFIED**.

The case outcome is then ``NOT_SUPPORTED`` if anything is violated, else
``INSUFFICIENT_EVIDENCE`` if anything is unknown, else ``SUPPORTED``.

**Where that precedence is load-bearing, the case says so.** A case with both a
violation and an unknown is marked ``precedence_dependent``. Both readings are
refusals, so such a case can never turn a refusal into an acceptance; it is
reported on the safety axis and separately on the exact-verdict axis, and that
split is registered in CHALLENGE_SPEC.json before any case exists.
"""

from __future__ import annotations

import json
import math
import pathlib

SATISFIED = "SATISFIED"
VIOLATED = "VIOLATED"
UNKNOWN = "UNKNOWN"

SUPPORTED = "SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
REJECTED_AT_BOUNDARY = "REJECTED_AT_BOUNDARY"
CHALLENGE_ERROR = "CHALLENGE_ERROR"
CORE_ERROR = "CORE_ERROR"

_REGISTER: dict | None = None


def bound_register() -> dict:
    global _REGISTER
    if _REGISTER is None:
        path = pathlib.Path(__file__).resolve().parent.parent / "BOUND_REGISTER.json"
        _REGISTER = json.loads(path.read_text(encoding="utf-8"))
    return _REGISTER


def conditions_for(model_id: str) -> list[dict]:
    """The declared conditions of one model, from the frozen register."""
    out = []
    for bound in bound_register()["bounds"]:
        for occurrence in bound["occurrences"]:
            if occurrence["model_id"] == model_id:
                out.append(
                    {
                        "name": bound["name"],
                        "class": bound["class"],
                        "conservative_screen": bound["conservative_screen"],
                        **occurrence,
                    }
                )
    out.sort(key=lambda c: c["name"])
    return out


def _magnitude(entry: dict | None) -> float | None:
    return None if entry is None else float(entry["magnitude"])


def classify_condition(condition: dict, value: float | None) -> tuple[str, str | None]:
    """(status, reason) for one condition against one computed value."""
    if value is None:
        return UNKNOWN, "not_supplied"
    if not math.isfinite(value):
        return UNKNOWN, "unreadable_shape"
    minimum = _magnitude(condition.get("minimum"))
    maximum = _magnitude(condition.get("maximum"))
    if minimum is not None:
        below = value < minimum if condition.get("minimum_inclusive") else value <= minimum
        if below:
            if condition.get("conservative_screen"):
                return UNKNOWN, "conservative_screen"
            return VIOLATED, "below_minimum"
    if maximum is not None:
        above = value > maximum if condition.get("maximum_inclusive") else value >= maximum
        if above:
            if condition.get("conservative_screen"):
                return UNKNOWN, "conservative_screen"
            return VIOLATED, "above_maximum"
    return SATISFIED, None


def assess(model_id: str, quantities: dict) -> dict:
    """The independent assessment of one model against computed quantities."""
    satisfied: list[str] = []
    violated: list[str] = []
    unknown: list[str] = []
    reasons: dict[str, str] = {}
    values: dict[str, float | None] = {}
    for condition in conditions_for(model_id):
        name = condition["name"]
        value = quantities.get(name)
        status, reason = classify_condition(condition, value)
        values[name] = value
        if status == SATISFIED:
            satisfied.append(name)
        elif status == VIOLATED:
            violated.append(name)
            reasons[name] = reason or "violated"
        else:
            unknown.append(name)
            reasons[name] = reason or "not_supplied"
    if violated:
        outcome = NOT_SUPPORTED
    elif unknown:
        outcome = INSUFFICIENT_EVIDENCE
    else:
        outcome = SUPPORTED
    return {
        "outcome": outcome,
        "satisfied": sorted(satisfied),
        "violated": sorted(violated),
        "unknown": sorted(unknown),
        "condition_reasons": reasons,
        "condition_values": values,
        "precedence_dependent": bool(violated and unknown),
    }


def reason_truth(assessment: dict) -> dict:
    """The independent mechanism set and how well determined it is."""
    violated = assessment["violated"]
    unknown = assessment["unknown"]
    if assessment["outcome"] == SUPPORTED:
        return {"valid_mechanisms": [], "reason_status": "NOT_APPLICABLE"}
    if violated:
        status = "UNIQUE" if len(violated) == 1 else "MULTIPLE_VALID"
        return {"valid_mechanisms": list(violated), "reason_status": status}
    status = "UNIQUE" if len(unknown) == 1 else "MULTIPLE_VALID"
    return {"valid_mechanisms": list(unknown), "reason_status": status}


def causal_truth(
    model_id: str,
    quantities: dict,
    repair: "callable[[str], dict | None]",
) -> dict:
    """Counterfactual repair: fix one defect, keep the others, re-decide.

    ``repair(name)`` returns the quantity mapping that results from repairing
    only the named defect. A condition is a **causal catcher** when repairing
    it alone changes the outcome; when several defects are each independently
    sufficient to refuse, none of them is, and the case says so rather than
    inventing a primary.
    """
    base = assess(model_id, quantities)
    if base["outcome"] == SUPPORTED:
        return {"class": "NOT_APPLICABLE", "catchers": [], "redundant": []}
    candidates = base["violated"] or base["unknown"]
    catchers: list[str] = []
    redundant: list[str] = []
    unresolved = False
    for name in candidates:
        repaired = repair(name)
        if repaired is None:
            unresolved = True
            continue
        after = assess(model_id, repaired)
        if after["outcome"] != base["outcome"]:
            catchers.append(name)
        else:
            redundant.append(name)
    if unresolved and not catchers:
        return {"class": "UNRESOLVED", "catchers": [], "redundant": redundant}
    if len(candidates) == 1 and catchers:
        return {"class": "UNIQUE_CAUSAL_CATCHER", "catchers": catchers, "redundant": []}
    if catchers and redundant:
        return {
            "class": "ONE_CAUSAL_PLUS_REDUNDANT" if len(catchers) == 1 else "MULTIPLE_CAUSAL_CATCHERS",
            "catchers": catchers,
            "redundant": redundant,
        }
    if len(catchers) > 1:
        return {"class": "MULTIPLE_CAUSAL_CATCHERS", "catchers": catchers, "redundant": []}
    if not catchers and len(candidates) > 1:
        # every defect on its own leaves the verdict where it was: each is
        # sufficient, none is necessary, and there is no primary to name.
        return {"class": "NO_UNIQUE_PRIMARY", "catchers": [], "redundant": redundant}
    return {"class": "UNRESOLVED", "catchers": catchers, "redundant": redundant}
