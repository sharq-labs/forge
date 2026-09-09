"""Which mechanism actually justifies a case's verdict, and which merely also failed.

WHY A SEPARATE MODULE FROM THE VERDICT EVALUATOR
------------------------------------------------
Knowing that a case is ``NOT_SUPPORTED`` is not knowing why. A case can carry
three violated conditions of which one is the defect the case was built around
and two are incidental; a scorer that credits any of them cannot tell detection
from coincidence. This module asks the harder question by **counterfactual
repair**: for each condition that failed, undo the one physical or declared
quantity that condition reads, recompute everything from scratch, and see what
happens.

    the violation disappears and the verdict changes    -> CAUSAL_ISOLATED
    the violation disappears, verdict survives on another -> CAUSAL_BUT_REDUNDANT
    the violation survives its own repair                -> NON_CAUSAL
    no legitimate minimal repair exists                  -> NOT_WELL_DEFINED

That distinction cannot be read off a single evaluation, which is why the whole
module exists.

INDEPENDENCE
------------
Imports ``independent_truth`` -- this suite's own evaluator -- and the standard
library. **Nothing from engcore, and nothing that reads stored benchmark
metadata.** It never sees ``should_be_caught_by``, ``acceptable_catchers``,
``expected_reason``, ``expected_verdict``, or any Forge output. The generator's
declared "lead" mechanism is benchmark *intent* and is compared against this
result elsewhere, never used to produce it.

TWO KINDS OF REPAIR, AND WHY BOTH ARE LEGITIMATE
------------------------------------------------
``DECLARATION`` repairs relax a limit the caller declared -- a higher rated
power, a wider linearisation band, a higher melting point. They do not perturb
the operating point at all, so they are as close to a minimal intervention as a
counterfactual gets.

``PHYSICAL`` repairs change a property of the body -- a more conductive
material, a less emissive surface. These do move the operating point, and the
recomputation accounts for that: everything downstream is evaluated afresh.
That is the honest way to ask the question, and it is why a physical repair can
legitimately remove a *different* condition's violation too.

WHAT IT REFUSES TO DO
---------------------
Invent a primary. Where two conditions are each independently sufficient and
each survives the other's repair, the answer is ``MULTIPLE_CAUSAL`` and the
case has no scientifically meaningful primary catcher. Forcing one would make a
"primary catcher accuracy" number that measures an arbitrary ordering.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass

from independent_truth import BOUNDS, POLICY, SOURCED, evaluate, si

# =====================================================================
# Reason classes
# =====================================================================

SCIENTIFIC_VIOLATION = "SCIENTIFIC_VIOLATION"
POLICY_VIOLATION = "POLICY_VIOLATION"
MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
CONTRADICTORY_INPUT = "CONTRADICTORY_INPUT"
INVALID_MODEL_REGIME = "INVALID_MODEL_REGIME"
NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
CONTRACT_VIOLATION = "CONTRACT_VIOLATION"

#: Conditions that compare two DECLARATIONS with each other rather than a
#: declaration with a computed state. A failure here is the payload
#: contradicting itself, which is a different kind of finding from a body
#: leaving a model's regime.
SELF_CONTRADICTION = {
    "declared_limits_are_mutually_consistent",
    "reference_temperature_utilization",
}

#: Conditions that say the body is outside the regime the model is declared
#: over, rather than outside a caller's rating.
REGIME = {
    "biot_number", "internal_fourier_number", "temperature",
    "radiation_to_convection_ratio", "convection_flow_range_utilization",
    "convection_property_range_utilization",
    "convection_conductance_agreement_ratio", "reduced_debye_temperature",
    "reference_reduced_debye_temperature", "ceiling_reduced_debye_temperature",
    "geometry_route_ratio",
    # Both say the composition has left the region it describes, rather than
    # that the body has passed a rating the caller declared.
    "linear_resistance_ratio", "thermal_runaway_no_steady_state",
}


def reason_class(condition, is_unknown=False):
    """What KIND of finding this condition failing represents."""
    if is_unknown:
        return MISSING_REQUIRED_EVIDENCE
    if condition in SELF_CONTRADICTION:
        return CONTRADICTORY_INPUT
    bound_class = BOUNDS.get(condition, (None, None, None))[2]
    if bound_class == POLICY:
        return POLICY_VIOLATION
    if condition in REGIME:
        return INVALID_MODEL_REGIME if bound_class != SOURCED else SCIENTIFIC_VIOLATION
    return CONTRACT_VIOLATION


# =====================================================================
# Counterfactual repairs
# =====================================================================

DECLARATION = "DECLARATION"
PHYSICAL = "PHYSICAL"


@dataclass(frozen=True)
class Repair:
    """How to undo one mechanism without touching anything else."""

    kind: str
    #: Where in the payload the quantity lives, as a path from the payload root.
    path: tuple
    #: Multiply the declared value by this to land the condition comfortably
    #: inside its bound. `None` means "compute it from the observed ratio".
    factor: float | None = None
    #: Set the quantity equal to another computed value instead of scaling.
    match_value: str | None = None
    note: str = ""


APP = ("stages", 0, "body", "applicability")
LIMITS = ("stages", 0, "conductor", "limits")
RATINGS = ("stages", 0, "conductor", "ratings")

#: condition -> the single quantity whose repair undoes it.
#:
#: Each entry answers "what would have to be different about this design for
#: THIS condition to stop failing, changing nothing else that is not entailed?"
REPAIRS = {
    # --- declaration repairs: relax a limit, leave the physics alone -----
    "melting_temperature_utilization": Repair(
        DECLARATION, APP + ("melting_temperature",),
        note="a material that melts higher"),
    "operating_temperature_utilization": Repair(
        DECLARATION, LIMITS + ("maximum_operating_temperature",),
        note="a conductor rated hotter"),
    "linearization_excursion_ratio": Repair(
        DECLARATION, LIMITS + ("linearization_band",),
        note="a coefficient characterised over a wider band"),
    "conductance_excursion_ratio": Repair(
        DECLARATION, APP + ("conductance_excursion_bound",),
        note="a wider constant-hA budget"),
    "capacity_excursion_ratio": Repair(
        DECLARATION, APP + ("capacity_excursion_bound",),
        note="a wider constant-C budget"),
    "dissipated_power_utilization": Repair(
        DECLARATION, RATINGS + ("rated_power",),
        note="a resistor rated for more dissipation"),
    "working_voltage_utilization": Repair(
        DECLARATION, RATINGS + ("maximum_working_voltage",),
        note="a resistor rated for more voltage"),
    "source_current_utilization": Repair(
        DECLARATION, ("source_ratings", "maximum_current"),
        note="a source rated for more current"),
    "reduced_debye_temperature": Repair(
        DECLARATION, LIMITS + ("debye_temperature",), factor=0.25,
        note="a material with a lower Debye temperature"),
    "reference_reduced_debye_temperature": Repair(
        DECLARATION, LIMITS + ("debye_temperature",), factor=0.25,
        note="a material with a lower Debye temperature"),
    "ceiling_reduced_debye_temperature": Repair(
        DECLARATION, LIMITS + ("debye_temperature",), factor=0.25,
        note="a material with a lower Debye temperature"),

    # --- physical repairs: change the body, and recompute everything -----
    "biot_number": Repair(
        PHYSICAL, APP + ("body_conductivity",),
        note="a body that conducts heat internally well enough to be lumped"),
    "radiation_to_convection_ratio": Repair(
        PHYSICAL, APP + ("surface_emissivity",),
        note="a less emissive surface, so radiation stops carrying the heat"),
    "internal_fourier_number": Repair(
        PHYSICAL, ("stages", 0, "body", "duration"),
        note="a horizon long enough for the interior to respond"),
    "geometry_route_ratio": Repair(
        PHYSICAL, APP + ("characteristic_length",), match_value="implied_length",
        note="a declared length that agrees with the one V/A_s implies"),
}

#: Conditions with no legitimate minimal repair. Saying so is better than
#: inventing one: `temperature` is bounded by the range the linear TCR form is
#: declared over, and moving the body into that range means changing the source
#: or the cooling, which changes every other condition too -- so a
#: counterfactual there is not minimal and its result would not isolate
#: anything.
NOT_REPAIRABLE = {
    "temperature",
    "convection_flow_range_utilization",
    "convection_property_range_utilization",
    "convection_conductance_agreement_ratio",
    "declared_limits_are_mutually_consistent",
    "linear_resistance_ratio",
    "thermal_runaway_no_steady_state",
}


def _get(payload, path):
    node = payload
    for key in path[:-1]:
        node = node[key]
    return node.get(path[-1]) if isinstance(node, dict) else None


def _set(payload, path, text):
    node = payload
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = text


def _scaled(text, factor):
    value, unit = str(text).split(None, 1)
    return f"{float(value) * factor} {unit}"


def apply_repair(payload, condition, observed):
    """Return a payload with `condition`'s mechanism undone, or None.

    The repair target is chosen so the condition lands comfortably inside its
    bound -- half of a ceiling, twice a floor -- rather than exactly on it,
    because a counterfactual that lands on the boundary tests the boundary
    rather than the mechanism.
    """
    repair = REPAIRS.get(condition)
    if repair is None:
        return None
    mutated = copy.deepcopy(payload)

    if repair.match_value == "implied_length":
        app = mutated["stages"][0]["body"]["applicability"]
        volume = si(app.get("body_volume"))
        area = si(app.get("surface_area"))
        if not volume or not area:
            return None
        app["characteristic_length"] = f"{volume / area} meter"
        return mutated

    current = _get(mutated, repair.path)
    if current is None:
        return None

    if repair.factor is not None:
        factor = repair.factor
    else:
        low, high, _ = BOUNDS.get(condition, (None, None, None))
        if high is not None and observed is not None and observed > high:
            # Ratio is value/limit: raising the limit by this much lands it at
            # half the bound.
            factor = (observed / high) * 2.0
        elif low is not None and observed is not None and 0 < observed < low:
            factor = (observed / low) * 0.5
        else:
            factor = 2.0
        if condition == "biot_number":
            factor = max(factor, 2.0)          # raise conductivity
        if condition == "radiation_to_convection_ratio":
            factor = 1.0 / max(factor, 2.0)    # LOWER emissivity
        if condition == "internal_fourier_number":
            factor = max(factor, 2.0)          # lengthen the horizon

    _set(mutated, repair.path, _scaled(current, factor))
    return mutated


# =====================================================================
# Causal analysis
# =====================================================================

CAUSAL_ISOLATED = "CAUSAL_ISOLATED"
CAUSAL_BUT_REDUNDANT = "CAUSAL_BUT_REDUNDANT"
NON_CAUSAL = "NON_CAUSAL"
NOT_WELL_DEFINED = "COUNTERFACTUAL_NOT_WELL_DEFINED"

UNIQUE_CAUSAL = "UNIQUE_CAUSAL_CATCHER"
MULTIPLE_CAUSAL = "MULTIPLE_CAUSAL_CATCHERS"
CAUSAL_PLUS_REDUNDANT = "ONE_CAUSAL_PLUS_REDUNDANT"
NO_UNIQUE_PRIMARY = "NO_UNIQUE_PRIMARY"
PRIMARY_UNRESOLVED = "UNRESOLVED"
NOT_APPLICABLE = "NOT_APPLICABLE"


def analyse(case_id, payload):
    """Independent reason set and causal catcher set for one payload."""
    base = evaluate(case_id, payload)
    verdict = base.independent_verdict
    gaps = sorted(base.unknown)

    deciding = list(base.violated) if base.violated else list(base.unknown)
    reasons = []
    for name in deciding:
        reasons.append({
            "condition": name,
            "value": base.values.get(name),
            "reason_class": reason_class(name, is_unknown=not base.violated),
            "bound_class": BOUNDS.get(name, (None, None, "DEFINITIONAL"))[2],
        })

    causal = {}
    if base.violated:
        for name in base.violated:
            if name in NOT_REPAIRABLE:
                causal[name] = NOT_WELL_DEFINED
                continue
            repaired = apply_repair(payload, name, base.values.get(name))
            if repaired is None:
                causal[name] = NOT_WELL_DEFINED
                continue
            after = evaluate(case_id, repaired)
            if name in after.violated:
                # Its own repair did not clear it: this condition is not the
                # thing the repair targets, or the mechanism is entangled.
                causal[name] = NON_CAUSAL
            elif after.independent_verdict != verdict:
                causal[name] = CAUSAL_ISOLATED
            else:
                causal[name] = CAUSAL_BUT_REDUNDANT

    isolated = sorted(n for n, s in causal.items() if s == CAUSAL_ISOLATED)
    redundant = sorted(n for n, s in causal.items() if s == CAUSAL_BUT_REDUNDANT)
    undefined = sorted(n for n, s in causal.items() if s == NOT_WELL_DEFINED)

    if not base.violated:
        primary = NOT_APPLICABLE
    elif len(isolated) == 1 and not redundant and not undefined:
        primary = UNIQUE_CAUSAL
    elif len(isolated) == 1:
        primary = CAUSAL_PLUS_REDUNDANT
    elif len(isolated) > 1:
        primary = MULTIPLE_CAUSAL
    elif redundant and not isolated:
        # Every violation clears under its own repair yet the verdict survives
        # each time: they are jointly sufficient and individually not, so no
        # one of them is the primary.
        primary = NO_UNIQUE_PRIMARY
    else:
        primary = PRIMARY_UNRESOLVED

    policy_reasons = [
        r["condition"] for r in reasons if r["reason_class"] == POLICY_VIOLATION
    ]
    scientific_reasons = [
        r["condition"] for r in reasons
        if r["reason_class"] in (SCIENTIFIC_VIOLATION, INVALID_MODEL_REGIME)
        and r["bound_class"] == SOURCED
    ]

    if not reasons:
        reason_truth_class = "NO_REASON_REQUIRED"
    elif scientific_reasons and policy_reasons:
        reason_truth_class = "MIXED"
    elif scientific_reasons:
        reason_truth_class = "INDEPENDENT_SCIENTIFIC"
    elif policy_reasons:
        reason_truth_class = "POLICY_DEPENDENT"
    else:
        reason_truth_class = "CONTRACT_ONLY"

    return {
        "case_id": case_id,
        "independent_verdict": verdict,
        "truth_class": base.truth_class,
        "valid_reasons": [r["condition"] for r in reasons],
        "gap_conditions": gaps,
        "reason_detail": reasons,
        "reason_classes": sorted({r["reason_class"] for r in reasons}),
        "reason_truth_class": reason_truth_class,
        "reason_oracle_ids": list(base.oracle_ids),
        "reason_bound_ids": sorted(
            r["condition"] for r in reasons if r["condition"] in BOUNDS
        ),
        "causal_status": {n: causal[n] for n in sorted(causal)},
        "causal_catchers": isolated,
        "redundant_catchers": redundant,
        "undefined_catchers": undefined,
        "primary_status": primary,
        "reason_ambiguity": (
            "none" if primary in (UNIQUE_CAUSAL, NOT_APPLICABLE)
            else "several independently sufficient mechanisms"
            if primary in (MULTIPLE_CAUSAL, NO_UNIQUE_PRIMARY)
            else "a mechanism whose counterfactual is not minimal"
        ),
        "policy_dependencies": sorted(policy_reasons),
        "resolution_status": (
            "RESOLVED" if primary != PRIMARY_UNRESOLVED else "UNRESOLVED"
        ),
    }
