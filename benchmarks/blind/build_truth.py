"""Establish the truth of the blind corpus. Runs NO Forge, states no result.

This module is the other half of the firewall. :mod:`generate` writes payloads
and knows nothing about answers; this one reads payloads and decides what is
true about them, using only the independent oracle layer. Neither imports
``engcore``, and ``tests/test_blind_challenge_guards.py`` fails if either
starts to.

What a truth record contains, and why each field is there
---------------------------------------------------------

``independent_verdict``
    What the conditions imply under the documented precedence: a violation is a
    finding and outranks a gap, a gap outranks a clean pass.

``truth_class``
    Which KIND of statement decided the case. A case decided by
    ``radiation_to_convection_ratio <= 0.1`` is decided by a neglect allowance
    with no located source, and reporting agreement on it as a scientific
    result would be a category error. See :mod:`bound_registry`.

``valid_reason_set``
    **Every** sufficient reason, not one primary one. Where two conditions are
    both violated, either is a correct thing for a report to say, and a truth
    that named one would score a correct answer wrong.

``causal_catcher_set`` / ``primary_catcher_status``
    Counterfactual repair, applied to the condition set: a condition is causal
    when repairing IT ALONE changes the verdict. Where several conditions are
    each violated, repairing any one leaves the verdict where it was, so none
    of them is uniquely causal — and that is reported as
    ``NO_UNIQUE_PRIMARY`` rather than resolved by picking one.

``boundary_stratum`` / ``truth_confidence_class``
    How far the deciding condition sits from its bound, and whether the truth
    at that distance is defensible. A case within
    ``families.RESOLUTION_FLOOR`` of its bound is ``ARITHMETIC_SENSITIVE`` and
    is **excluded from the primary denominator**: at that distance the answer
    is decided by which implementation rounds which way.

``second_oracle`` / ``unresolved_dependencies``
    Where a second, independently implemented oracle exists, its disagreement
    with the first. A disagreement is only material if it could move the
    deciding condition across its bound — that comparison is what promotes a
    case to UNRESOLVED, rather than a fixed tolerance that would be either too
    strict for one domain or too loose for another.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from . import admissibility as adm
from . import bound_registry as reg
from .families import RESOLUTION_FLOOR
from .oracles import battery as battery_oracle
from .oracles import conduction as conduction_oracle
from .oracles import electrothermal as et_oracle
from .oracles import kinetics as kinetics_oracle
from .oracles import spice as spice_oracle

__all__ = ["TRUTH_BUILDER_VERSION", "build_truth", "payload_digest"]

TRUTH_BUILDER_VERSION = "blind-truth/1.0.0"

#: Which oracle module answers which system, and which second oracle it has.
_ORACLES = {
    "electrothermal": (et_oracle.ORACLE_ID, et_oracle.SECOND_ORACLE_ID),
    "battery": (battery_oracle.ORACLE_ID, battery_oracle.SECOND_ORACLE_ID),
    "kinetics_cstr": (kinetics_oracle.ORACLE_ID, kinetics_oracle.SECOND_ORACLE_ID),
    "conduction_1d": (conduction_oracle.ORACLE_ID, conduction_oracle.SECOND_ORACLE_ID),
}


def _portable(value: Any) -> Any:
    """Make a truth record writable as strict JSON, without losing what it says.

    ``Infinity`` and ``NaN`` are not JSON. They are also real answers here: a
    condition at a positivity floor has an unbounded excess, and a malformed
    payload really does carry a non-finite magnitude. Writing them with
    ``allow_nan=True`` would produce a file that only Python can read, and
    writing them as ``null`` would make "no value" and "unbounded" the same
    string in a frozen artifact.

    So they are written as the strings ``"+inf"``, ``"-inf"`` and ``"nan"``,
    which every reader can parse and none can mistake for a number.
    """
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "+inf" if value > 0.0 else "-inf"
        return value
    if isinstance(value, dict):
        return {key: _portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    return value


def payload_digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# stratification
# ---------------------------------------------------------------------------

def _bounds_for(system: str) -> dict:
    if system == "electrothermal":
        return et_oracle.BOUNDS
    if system == "battery":
        return battery_oracle.BOUNDS
    if system == "kinetics_cstr":
        return kinetics_oracle.BOUNDS
    return conduction_oracle.BOUNDS


def _excess(condition, bounds: dict) -> float | None:
    """How far the value sits toward refusal, as a ratio: 1.0 IS the bound.

    Normalised so that one number orders every condition the same way whatever
    shape its bound has: ``value / maximum`` for an upper bound,
    ``minimum / value`` for a lower one, the larger of the two for a two-sided
    bound. Below one is inside; above one is outside; exactly one is on it.

    ``relative_position`` on the oracle's own record is deliberately not reused
    here: it takes the max of the two ratios, which is the wrong combination
    for a two-sided bound because the lower ratio is unbounded above.
    """
    if condition.value is None or not math.isfinite(condition.value):
        return None
    minimum, maximum, _min_incl, _max_incl = bounds[condition.name]
    ratios = []
    if maximum is not None:
        ratios.append(abs(condition.value) / maximum if maximum != 0.0
                      else math.inf)
    if minimum is not None:
        if minimum == 0.0:
            # A positivity floor. There is no scale to normalise against, so
            # the only honest statement is which side of zero the value is on.
            ratios.append(0.0 if condition.value > 0.0 else math.inf)
        elif condition.value == 0.0:
            ratios.append(math.inf)
        else:
            ratios.append(minimum / condition.value)
    return max(ratios) if ratios else None


def _stratum(condition, bounds: dict, system: str) -> tuple[str, str]:
    """``(boundary_stratum, truth_confidence_class)`` for one condition."""
    if condition.status == "unknown":
        return "NOT_APPLICABLE", "DECIDED"
    excess = _excess(condition, bounds)
    if excess is None or not math.isfinite(excess):
        return ("FAR_OUTSIDE" if condition.status == "violated"
                else "FAR_INSIDE"), "DECIDED"
    distance = abs(excess - 1.0)
    if distance < RESOLUTION_FLOOR:
        return "AT_BOUNDARY", "ARITHMETIC_SENSITIVE"
    soft = reg.is_soft(condition.name,
                       system="kinetics" if system == "kinetics_cstr" else "")
    if excess < 1.0:
        stratum = "FAR_INSIDE" if excess <= 0.8 else "NEAR_INSIDE"
    else:
        stratum = "FAR_OUTSIDE" if excess > 1.2 else "NEAR_OUTSIDE"
    if soft and stratum in ("NEAR_INSIDE", "NEAR_OUTSIDE"):
        # A soft bound is an approximation criterion, not a transition. There
        # is nothing at the number for a case to be near, so a case beside one
        # is tagged for what it is rather than given a boundary it does not
        # have.
        stratum = "SOFT_BOUND_NEAR"
    return stratum, "DECIDED"


# ---------------------------------------------------------------------------
# reason, cause, class
# ---------------------------------------------------------------------------

def _system_key(system: str) -> str:
    return "kinetics_cstr" if system == "kinetics_cstr" else ""


def _classify_case(conditions, checks, system: str) -> dict:
    """Reasons, causes and the truth class, from the condition set alone.

    The verdict is a pure function of the condition statuses, which is what
    makes counterfactual repair exact here rather than approximate: repairing
    one condition means flipping its status to satisfied and re-deriving, and
    no physics has to be re-run to know the answer.
    """
    violated = [c for c in conditions if c.status == "violated"]
    unknown = [c for c in conditions if c.status == "unknown"]
    failed = list(checks)

    def verdict_of(repaired: str | None) -> str:
        remaining_violated = [c for c in violated if _key(c) != repaired]
        remaining_failed = [f for f in failed if f != repaired]
        remaining_unknown = [c for c in unknown if _key(c) != repaired]
        if remaining_violated or remaining_failed:
            return "NOT_SUPPORTED"
        if remaining_unknown:
            return "INSUFFICIENT_EVIDENCE"
        return "SUPPORTED"

    verdict = verdict_of(None)

    if verdict == "NOT_SUPPORTED":
        deciding = [_key(c) for c in violated] + list(failed)
        reason_names = [c.name for c in violated] + list(failed)
    elif verdict == "INSUFFICIENT_EVIDENCE":
        deciding = [_key(c) for c in unknown]
        reason_names = [c.name for c in unknown]
    else:
        deciding, reason_names = [], []

    causal = sorted(name for name in deciding if verdict_of(name) != verdict)

    if verdict == "SUPPORTED":
        status = "NOT_APPLICABLE"
    elif len(causal) == 1 and len(deciding) == 1 and not unknown:
        status = "UNIQUE_CAUSAL_CATCHER"
    elif len(causal) == 1 and len(deciding) == 1:
        # One thing decides the verdict, and repairing it would expose gaps
        # that were there all along. The gaps are redundant for THIS verdict
        # and would not be for the next one.
        status = "ONE_CAUSAL_PLUS_REDUNDANT"
    elif len(deciding) > 1:
        models = {name.split("::")[0] for name in deciding if "::" in name}
        status = ("MULTIPLE_CAUSAL_CATCHERS" if len(models) <= 1
                  else "NO_UNIQUE_PRIMARY")
    else:
        status = "UNRESOLVED"

    key = _system_key(system)
    classes = sorted({reg.class_of(name, system=key) for name in reason_names})
    policy = sorted({name for name in reason_names
                     if reg.is_policy(name, system=key)})
    if not reason_names:
        # A SUPPORTED case turns on whichever bound it came closest to
        # refusing: that is the statement its truth actually rests on.
        truth_class = "SUPPORTED_PENDING"
    elif verdict == "INSUFFICIENT_EVIDENCE":
        # An absent declaration cannot be assessed. That follows from the
        # record's semantics, not from the world.
        truth_class = "CONTRACT_ONLY"
    elif not policy:
        truth_class = "INDEPENDENT_SCIENTIFIC"
    elif len(policy) == len(set(reason_names)):
        truth_class = "POLICY_DEPENDENT"
    else:
        truth_class = "MIXED_SCIENCE_AND_POLICY"

    return {
        "verdict": verdict,
        "valid_reason_set": sorted(set(deciding)),
        "reason_names": sorted(set(reason_names)),
        "reason_classes": classes,
        "causal_catcher_set": causal,
        "primary_catcher_status": status,
        "policy_dependencies": policy,
        "truth_class": truth_class,
    }


def _key(condition) -> str:
    return f"{condition.model_id}::{condition.name}"


# ---------------------------------------------------------------------------
# per-system truth
# ---------------------------------------------------------------------------

def _electrothermal_truth(payload: dict) -> tuple[Any, list[str], dict]:
    truth = et_oracle.evaluate(payload)
    second: dict = {}
    if truth.converged and truth.stage_states:
        second["rk4"] = et_oracle.second_oracle(payload, truth)
        resistances = [state["resistance_ohm"] for state in truth.stage_states]
        source_v = et_oracle.to_si(payload["source_voltage"], "V")
        second["ngspice"] = spice_oracle.series_current(resistances, source_v)
    return truth, list(truth.failed_checks), second


def _battery_truth(payload: dict) -> tuple[Any, list[str], dict]:
    truth = battery_oracle.evaluate(payload)
    return truth, [], {"rk4_and_charge_balance":
                       battery_oracle.second_oracle(payload, truth)}


def _kinetics_truth(payload: dict) -> tuple[Any, list[str], dict]:
    truth = kinetics_oracle.evaluate(payload)
    second: dict = {}
    if truth.verdict != "REJECTED_AT_BOUNDARY":
        second["rk4"] = kinetics_oracle.integrate_ceiling(payload)
    return truth, [], second


def _conduction_truth(payload: dict) -> tuple[Any, list[str], dict]:
    truth = conduction_oracle.evaluate(payload)
    second: dict = {}
    if payload.get("realization", "").endswith("explicit_forward_euler"):
        try:
            second["ftcs_march"] = conduction_oracle.march_amplification(payload)
        except conduction_oracle.OracleUnresolved as exc:
            second["ftcs_march"] = {"status": "unresolved", "why": str(exc)}
    return truth, [], second


#: The construction contract, per system. `kinetics_cstr` keeps its own,
#: which lives with the oracle because the CSTR's refusal ordering is part of
#: what that oracle already models.
_REFUSALS = {
    "electrothermal": adm.electrothermal_refusal,
    "battery": adm.battery_refusal,
    "conduction_1d": adm.conduction_refusal,
    "kinetics_cstr": kinetics_oracle.construction_refusal,
}

_BUILDERS = {
    "electrothermal": _electrothermal_truth,
    "battery": _battery_truth,
    "kinetics_cstr": _kinetics_truth,
    "conduction_1d": _conduction_truth,
}


def _second_oracle_verdict(system: str, second: dict, deciding_distance: float | None
                           ) -> tuple[str, list[str], float | None]:
    """Does the second oracle leave the truth standing?

    ``MATERIAL_DISAGREEMENT`` only when the gap between the two independent
    implementations is large enough to move the deciding condition across its
    bound. A fixed tolerance would be arbitrary; this one is the question the
    disagreement actually bears on.
    """
    notes: list[str] = []
    worst: float | None = None
    for name, report in second.items():
        status = report.get("status")
        if status in ("unavailable", "not_applicable", "not_integrable"):
            notes.append(f"{name}:{status}")
            continue
        if status in ("failed", "unresolved", "diverged"):
            notes.append(f"{name}:{status}")
            continue
        gap = report.get("worst_relative_gap")
        if gap is None:
            gap = report.get("relative_gap")
        if name == "ngspice" and gap is not None:
            # ngspice's printed output carries about six significant figures,
            # so a gap at the quantisation is the format's limit and not a
            # disagreement between the two solvers.
            quantisation = report.get("print_quantisation")
            analytic = abs(report.get("analytic_a") or 0.0)
            if quantisation and analytic:
                floor = quantisation / analytic
                gap = max(0.0, gap - floor)
        if name == "ftcs_march":
            gap = report.get("oracle_gap")
            if report.get("falsifies_bound"):
                return ("BOUND_FALSIFIED",
                        [f"{name}: growth measured at r <= 1/2"], gap)
        if name == "rk4" and system == "kinetics_cstr":
            if report.get("ceiling_respected") is False:
                return ("BOUND_FALSIFIED",
                        [f"{name}: the trajectory exceeded the analytic "
                         f"ceiling"], None)
            continue
        if gap is None:
            continue
        worst = gap if worst is None else max(worst, gap)
    if worst is None:
        return "SINGLE_ORACLE" if not second else "AGREED", notes, worst
    # `max(..., RESOLUTION_FLOOR)`: below the floor the case is already
    # ARITHMETIC_SENSITIVE and out of the primary denominator, and calling it
    # UNRESOLVED as well would count one limitation twice. A disagreement is
    # material when it could move a condition the challenge still claims to
    # have decided.
    if deciding_distance is not None and worst >= max(deciding_distance,
                                                      RESOLUTION_FLOOR):
        return "MATERIAL_DISAGREEMENT", notes, worst
    return "AGREED", notes, worst


def build_truth(case: dict) -> dict:
    """One frozen truth record. No Forge, no verdict from anything but the oracles."""
    system = case["system"]
    payload = case["payload"]
    bounds = _bounds_for(system)
    record: dict[str, Any] = {
        "case_id": case["id"],
        "system": system,
        "family": case["family"],
        "family_kind": case["family_kind"],
        "target": case["target"],
        "intended_position": case["intended_position"],
        "intended_stratum": case["intended_stratum"],
        "payload_digest": payload_digest(payload),
        "oracle_ids": list(_ORACLES[system]),
        "numerical_tolerance_basis": (
            "exact comparison against the declared bound; no tolerance is "
            "applied at classification. A case within RESOLUTION_FLOOR "
            f"({RESOLUTION_FLOOR}) relative of its bound is ARITHMETIC_"
            "SENSITIVE and leaves the primary denominator. The floor is 5e5x "
            "the worst measured disagreement between this oracle and the "
            "runtime over the 1400 open development cases."
        ),
    }

    if case["family_kind"] == "malformed":
        # The truth of a malformed payload is that the boundary must refuse to
        # build anything from it. That is a claim about the record's semantics
        # and nothing else, which is what CONTRACT_ONLY means.
        record.update({
            "independent_verdict": "REJECTED_AT_BOUNDARY",
            "truth_class": "CONTRACT_ONLY",
            "truth_confidence_class": "DECIDED",
            "boundary_stratum": "MALFORMED",
            "evaluated_conditions": [],
            "satisfied_conditions": [],
            "violated_conditions": [],
            "unknown_conditions": [],
            "valid_reason_set": ["payload_rejected_at_boundary"],
            "reason_names": ["payload_rejected_at_boundary"],
            "reason_classes": ["CONTRACT"],
            "causal_catcher_set": ["payload_rejected_at_boundary"],
            "primary_catcher_status": "UNIQUE_CAUSAL_CATCHER",
            "policy_dependencies": [],
            "bound_ids": [],
            "second_oracle": {},
            "second_oracle_status": "SINGLE_ORACLE",
            "unresolved_dependencies": [],
        })
        return _portable(record)

    # THE BOUNDARY REFUSES BEFORE IT ASSESSES, and a truth that did not know
    # that would be confidently wrong about every case whose DECLARATION is
    # inadmissible rather than whose design is. Checked first, for every
    # system, against the contract transcribed in `admissibility`.
    refusal = _REFUSALS[system](payload)
    if refusal is not None:
        record.update({
            "independent_verdict": "REJECTED_AT_BOUNDARY",
            "truth_class": "CONTRACT_ONLY",
            "truth_confidence_class": "DECIDED",
            "boundary_stratum": "CONSTRUCTION_REFUSED",
            "evaluated_conditions": [], "satisfied_conditions": [],
            "violated_conditions": [], "unknown_conditions": [],
            "valid_reason_set": [refusal], "reason_names": [refusal],
            "reason_classes": ["CONTRACT"], "causal_catcher_set": [refusal],
            "primary_catcher_status": "UNIQUE_CAUSAL_CATCHER",
            "policy_dependencies": [], "bound_ids": [], "second_oracle": {},
            "second_oracle_status": "NOT_REACHED",
            "unresolved_dependencies": [],
            "construction_refusal": refusal,
        })
        return _portable(record)

    try:
        truth, failed_checks, second = _BUILDERS[system](payload)
    except et_oracle.OracleUnresolved as exc:
        record.update({
            "independent_verdict": "UNRESOLVED",
            "truth_class": "UNRESOLVED",
            "truth_confidence_class": "UNRESOLVED",
            "boundary_stratum": "UNRESOLVED",
            "evaluated_conditions": [], "satisfied_conditions": [],
            "violated_conditions": [], "unknown_conditions": [],
            "valid_reason_set": [], "reason_names": [], "reason_classes": [],
            "causal_catcher_set": [], "primary_catcher_status": "UNRESOLVED",
            "policy_dependencies": [], "bound_ids": [], "second_oracle": {},
            "second_oracle_status": "NOT_REACHED",
            "unresolved_dependencies": [f"{exc.reason}: {exc.detail}"],
        })
        return _portable(record)

    if getattr(truth, "verdict", None) == "REJECTED_AT_BOUNDARY":
        record.update({
            "independent_verdict": "REJECTED_AT_BOUNDARY",
            "truth_class": "CONTRACT_ONLY",
            "truth_confidence_class": "DECIDED",
            "boundary_stratum": "CONSTRUCTION_REFUSED",
            "evaluated_conditions": [], "satisfied_conditions": [],
            "violated_conditions": [], "unknown_conditions": [],
            "valid_reason_set": [truth.state["construction_refusal"]],
            "reason_names": [truth.state["construction_refusal"]],
            "reason_classes": ["CONTRACT"],
            "causal_catcher_set": [truth.state["construction_refusal"]],
            "primary_catcher_status": "UNIQUE_CAUSAL_CATCHER",
            "policy_dependencies": [], "bound_ids": [],
            "second_oracle": second, "second_oracle_status": "NOT_REACHED",
            "unresolved_dependencies": [], "state": truth.state,
        })
        return _portable(record)

    classified = _classify_case(truth.conditions, failed_checks, system)

    # Which condition the case's truth actually rests on: the deciding one, or
    # for a clean case the one it came closest to refusing.
    deciding_names = {name.split("::")[-1] for name in classified["valid_reason_set"]}
    candidates = [c for c in truth.conditions if c.name in deciding_names]
    if not candidates:
        scored = [(e, c) for c in truth.conditions
                  if (e := _excess(c, bounds)) is not None and math.isfinite(e)]
        candidates = [max(scored, key=lambda pair: (pair[0], pair[1].name))[1]] if scored else []
    anchor = candidates[0] if candidates else None
    if len(candidates) > 1:
        ranked = [(e if (e := _excess(c, bounds)) is not None else -1.0, c.name, c)
                  for c in candidates]
        anchor = max(ranked, key=lambda triple: (triple[0], triple[1]))[2]

    if anchor is not None:
        stratum, confidence = _stratum(anchor, bounds, system)
    else:
        stratum, confidence = "NOT_APPLICABLE", "DECIDED"

    if classified["truth_class"] == "SUPPORTED_PENDING":
        key = _system_key(system)
        classified["truth_class"] = (
            "POLICY_DEPENDENT" if anchor is not None
            and reg.is_policy(anchor.name, system=key)
            else "INDEPENDENT_SCIENTIFIC")

    excess = _excess(anchor, bounds) if anchor is not None else None
    distance = abs(excess - 1.0) if excess is not None and math.isfinite(excess) else None
    oracle_status, notes, worst = _second_oracle_verdict(system, second, distance)

    unresolved: list[str] = []
    truth_class = classified["truth_class"]
    if oracle_status == "MATERIAL_DISAGREEMENT":
        unresolved.append(
            f"the two independent oracles disagree by {worst:.3e} relative, "
            f"which is at least the deciding condition's distance from its "
            f"bound ({distance:.3e}); the truth of this case is not decidable "
            f"to the precision it needs")
        truth_class = "UNRESOLVED"
    elif oracle_status == "BOUND_FALSIFIED":
        unresolved.extend(notes)
        truth_class = "UNRESOLVED"

    bound_ids = sorted({
        bound.bound_id for name in classified["reason_names"]
        if (bound := reg.bound_for(name, system=_system_key(system))) is not None
    })

    record.update({
        "independent_verdict": (classified["verdict"] if truth_class != "UNRESOLVED"
                                else "UNRESOLVED"),
        "truth_class": truth_class,
        "truth_confidence_class": ("UNRESOLVED" if truth_class == "UNRESOLVED"
                                   else confidence),
        "boundary_stratum": ("UNRESOLVED" if truth_class == "UNRESOLVED"
                             else stratum),
        "deciding_condition": anchor.name if anchor is not None else None,
        "deciding_excess": excess,
        "evaluated_conditions": [
            {"name": c.name, "model": c.model_id, "status": c.status,
             "value": c.value, "unknown_reason": c.unknown_reason}
            for c in truth.conditions],
        "satisfied_conditions": sorted(truth.satisfied),
        "violated_conditions": sorted(truth.violated),
        "unknown_conditions": sorted(truth.unknown),
        "failed_checks": sorted(failed_checks),
        "valid_reason_set": classified["valid_reason_set"],
        "reason_names": classified["reason_names"],
        "reason_classes": classified["reason_classes"],
        "causal_catcher_set": classified["causal_catcher_set"],
        "primary_catcher_status": ("UNRESOLVED" if truth_class == "UNRESOLVED"
                                   else classified["primary_catcher_status"]),
        "policy_dependencies": classified["policy_dependencies"],
        "bound_ids": bound_ids,
        "second_oracle": second,
        "second_oracle_status": oracle_status,
        "second_oracle_worst_gap": worst,
        "second_oracle_notes": notes,
        "unresolved_dependencies": unresolved,
        "state": getattr(truth, "state", None) or {
            "stage_states": list(getattr(truth, "stage_states", ())),
            "current_a": getattr(truth, "current_a", None),
            "converged": getattr(truth, "converged", None),
        },
    })
    return _portable(record)
