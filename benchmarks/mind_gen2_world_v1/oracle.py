"""The independent truth oracle for the feasibility benchmark (never imports ``engcore.mind.world``).

A case is a declared mutation of a FEASIBLE-by-construction base proposal.  Its expected outcome is derived here
from the mutation kind and the recorded construction facts, by the rules the GEN2-BR1 brief states:

* a value outside a declared finite level set or range is infeasible under the authority that declared the limit
  (protocol metadata: INFEASIBLE_PROTOCOL, brief section 5; problem specification: INFEASIBLE_DOMAIN, section 7);
* a dimensionally wrong or wrongly typed value is INFEASIBLE_DOMAIN (section 8);
* a fixed protocol condition changed, or a protocol condition the action does not offer, is INFEASIBLE_PROTOCOL
  (sections 3 and 13 B);
* a state set directly is INFEASIBLE_STATE (section 13 C); a measurement, latent, nuisance or derived value set as a
  control, or a latent / derived / unrecorded / unoffered variable observed, is INFEASIBLE_DOMAIN (sections 3, 13 D-E);
* an unavailable or other-version provider is INFEASIBLE_PROVIDER (section 13 H), a cost above what remains is
  INFEASIBLE_BUDGET (13 I), a model execution outside its model's validity domain is INFEASIBLE_APPLICABILITY
  (section 9), a violated state precondition is INFEASIBLE_STATE, a violated protocol constraint INFEASIBLE_PROTOCOL
  (13 J);
* anything absent or undecidable (an undeclared name or action, a control without a value, an observation list never
  given, a budget dimension never declared, a precondition whose uncertainty is unknown) is MISSING_INFORMATION.

A case that combines two mutations expects both codes and the status that comes first in the published precedence
(DOMAIN, PROTOCOL, STATE, APPLICABILITY, PROVIDER, BUDGET, MISSING_INFORMATION).  Disclosure: the oracle, the case
generator and the checker were written by the same author; the oracle shares the checker's reading of the brief, so
agreement shows consistent implementation of that reading, not its correctness.
"""

from __future__ import annotations

from typing import Any, Mapping

PRECEDENCE = ("INFEASIBLE_DOMAIN", "INFEASIBLE_PROTOCOL", "INFEASIBLE_STATE", "INFEASIBLE_APPLICABILITY",
              "INFEASIBLE_PROVIDER", "INFEASIBLE_BUDGET", "MISSING_INFORMATION")

BY_DECLARER = {"protocol_metadata": "INFEASIBLE_PROTOCOL", "problem_specification": "INFEASIBLE_DOMAIN"}

#: mutation -> (status or None when it depends on the declarer, code)
RULES: Mapping[str, tuple[str | None, str]] = {
    "OFF_LEVEL": (None, "LEVEL_NOT_DECLARED"),
    "ABOVE_RANGE": (None, "OUTSIDE_RANGE"),
    "BELOW_RANGE": (None, "OUTSIDE_RANGE"),
    "INTEGER_ABOVE_RANGE": (None, "OUTSIDE_RANGE"),
    "UNDECLARED_CATEGORY": (None, "CATEGORY_NOT_DECLARED"),
    "WRONG_UNIT": ("INFEASIBLE_DOMAIN", "UNIT_INCOMPATIBLE"),
    "WRONG_KIND": ("INFEASIBLE_DOMAIN", "VALUE_KIND_MISMATCH"),
    "MISSING_CONTROL": ("MISSING_INFORMATION", "CONTROL_NOT_SUPPLIED"),
    "SET_STATE": ("INFEASIBLE_STATE", "STATE_NOT_DIRECTLY_SETTABLE"),
    "SET_MEASUREMENT": ("INFEASIBLE_DOMAIN", "ROLE_NOT_CONTROLLABLE"),
    "SET_LATENT": ("INFEASIBLE_DOMAIN", "ROLE_NOT_CONTROLLABLE"),
    "SET_NUISANCE": ("INFEASIBLE_DOMAIN", "ROLE_NOT_CONTROLLABLE"),
    "SET_DERIVED": ("INFEASIBLE_DOMAIN", "ROLE_NOT_CONTROLLABLE"),
    "SET_UNOFFERED_INPUT": ("INFEASIBLE_DOMAIN", "CONTROL_NOT_OFFERED_BY_ACTION"),
    "SET_UNSELECTABLE_PROTOCOL": ("INFEASIBLE_PROTOCOL", "PROTOCOL_CONDITION_NOT_SELECTABLE"),
    "CHANGE_FIXED": ("INFEASIBLE_PROTOCOL", "FIXED_CONDITION_CHANGED"),
    "UNDECLARED_VARIABLE": ("MISSING_INFORMATION", "UNDECLARED_VARIABLE"),
    "UNDECLARED_ACTION": ("MISSING_INFORMATION", "UNDECLARED_ACTION"),
    "OBSERVE_LATENT": ("INFEASIBLE_DOMAIN", "LATENT_NOT_OBSERVABLE"),
    "OBSERVE_DERIVED": ("INFEASIBLE_DOMAIN", "DERIVED_NOT_OBSERVABLE"),
    "OBSERVE_NO_CHANNEL": ("INFEASIBLE_DOMAIN", "NO_OBSERVATION_CHANNEL"),
    "OBSERVE_UNOFFERED": ("INFEASIBLE_DOMAIN", "OBSERVABLE_NOT_OFFERED_BY_ACTION"),
    "OBSERVE_NOTHING": ("MISSING_INFORMATION", "OBSERVE_TARGETS_NOT_SUPPLIED"),
    "PROVIDER_DOWN": ("INFEASIBLE_PROVIDER", "PROVIDER_UNAVAILABLE"),
    "PROVIDER_OTHER_VERSION": ("INFEASIBLE_PROVIDER", "PROVIDER_VERSION_MISMATCH"),
    "BUDGET_EXHAUSTED": ("INFEASIBLE_BUDGET", "OVER_BUDGET"),
    "BUDGET_UNDECLARED": ("MISSING_INFORMATION", "BUDGET_DIMENSION_UNDECLARED"),
    "APPLICABILITY_OUTSIDE": ("INFEASIBLE_APPLICABILITY", "OUTSIDE_VALIDATED_DOMAIN"),
    "PRECONDITION_VIOLATED": ("INFEASIBLE_STATE", "PRECONDITION_VIOLATED"),
    "PRECONDITION_UNCERTAIN": ("MISSING_INFORMATION", "PRECONDITION_UNCERTAINTY_UNKNOWN"),
    "CONSTRAINT_VIOLATED": (None, "CONSTRAINT_VIOLATED"),
}


#: Mutations that keep a proposal valid by construction: another declared member, the same value in another unit
#: spelling, a declared bound itself (inclusive), a fixed condition restated, a subset of the offered observables.
VALID = frozenset({"VALID_LEVEL", "VALID_RESPELL", "VALID_BOUNDARY", "VALID_INTEGER_BOUND", "VALID_FIXED_RESTATE",
                   "VALID_OBSERVE_SUBSET"})


def label(mutations: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Expected outcome of a case made of zero (BASE) or more mutations, each {kind, facts}."""
    mutations = [m for m in mutations if m["kind"] not in VALID]
    if not mutations:
        return {"status": "FEASIBLE", "codes": []}
    statuses, codes = [], []
    for m in mutations:
        status, code = RULES[m["kind"]]
        if status is None:
            status = BY_DECLARER[m["facts"]["declared_by"]]
        statuses.append(status)
        codes.append(code)
    return {"status": min(statuses, key=PRECEDENCE.index), "codes": sorted(set(codes))}


def audit(mutation: Mapping[str, Any]) -> list[str]:
    """Construction audit of one mutation from its recorded facts, in plain arithmetic: does it do what it says?"""
    kind, f = mutation["kind"], mutation["facts"]
    problems = []
    if kind == "VALID_LEVEL":
        if not any(abs(f["value"] - lv) <= 1e-9 * max(1.0, abs(lv)) for lv in f["levels"]):
            problems.append("the level is not declared")
    elif kind in ("VALID_RESPELL", "VALID_FIXED_RESTATE"):
        if abs(f["base_value"] - f["respelled_in_base"]) > 1e-9 * max(1.0, abs(f["base_value"])):
            problems.append("the respelled value is not the same value")
    elif kind in ("VALID_BOUNDARY", "VALID_INTEGER_BOUND"):
        if not f["lower"] <= f["value"] <= f["upper"]:
            problems.append("the boundary value is not inside its inclusive range")
    elif kind == "OFF_LEVEL":
        if any(abs(f["value"] - lv) <= 1e-9 * max(1.0, abs(lv)) for lv in f["levels"]):
            problems.append("the off-level value equals a declared level")
    elif kind in ("ABOVE_RANGE", "INTEGER_ABOVE_RANGE"):
        if not f["value"] > f["upper"]:
            problems.append("the value is not above the upper bound")
    elif kind == "BELOW_RANGE":
        if not f["value"] < f["lower"]:
            problems.append("the value is not below the lower bound")
    elif kind == "UNDECLARED_CATEGORY":
        if f["value"] in f["categories"]:
            problems.append("the category is declared")
    elif kind == "WRONG_UNIT":
        if f["proposed_dimension"] == f["declared_dimension"]:
            problems.append("the proposed unit has the declared dimension")
    elif kind == "CHANGE_FIXED":
        if f["proposed"] == f["fixed"]:
            problems.append("the proposed value equals the fixed one")
    elif kind == "BUDGET_EXHAUSTED":
        if not f["cost"] > f["remaining"]:
            problems.append("the cost does not exceed what remains")
    elif kind == "APPLICABILITY_OUTSIDE":
        if f["model_lower"] <= f["value"] <= f["model_upper"]:
            problems.append("the value is inside the model's validity range")
        if "control_lower" in f and not f["control_lower"] <= f["value"] <= f["control_upper"]:
            problems.append("the value is outside the control's own domain (that would be a domain case)")
    elif kind == "PRECONDITION_VIOLATED":
        if f["operator"] == "<=" and not f["lower_edge"] > f["bound"]:
            problems.append("the state interval does not lie wholly above the ceiling")
        if f["operator"] == ">=" and not f["upper_edge"] < f["bound"]:
            problems.append("the state interval does not lie wholly below the floor")
    elif kind == "CONSTRAINT_VIOLATED":
        op, v, b = f["operator"], f["value"], f["bound"]
        held = {"<=": v <= b, "<": v < b, ">=": v >= b, ">": v > b}[op]
        if held:
            problems.append("the constrained value satisfies the constraint")
        if not f["control_lower"] <= v <= f["control_upper"]:
            problems.append("the constrained value is outside the control's domain")
    return problems


__all__ = ["BY_DECLARER", "PRECEDENCE", "RULES", "audit", "label"]
