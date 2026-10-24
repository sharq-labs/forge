"""Representation-coverage instrument: what the unchanged Mind arm CAN answer, decided before any run.

Two stages, frozen separately:

1. ``reachable()`` (pre-run, written into PLAN.json): for every (problem, axis), the set of dispositions the Mind arm's
   declared answer paths can produce, and the semantic fidelity of the path.  It is computed only from the capability
   table below and the pack's structure (whether a held-out set exists, whether a probe's box or region is empty),
   using the adapter's own pure problem builder; the Mind is not run and no truth is read.
2. ``classify()`` (post-seal): the historically correct answer T is classified against the frozen reachable set:
   - NOT_REPRESENTABLE: no reachable answer would score CORRECT / CORRECT_REFUSAL against T;
   - REPRESENTABLE_EXACTLY: some would, through a path whose semantics are the question's (EXACT);
   - REPRESENTABLE_APPROXIMATELY: some would, but only through a proxy path (PROXY), or by a fixed refusal of a
     question the arm cannot judge (NONE);
   - UNKNOWN: the reachable set could not be computed.
   Whether the Mind actually answered correctly never enters the classification.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..candidate import mind_arm
from ..candidate.common import AXES, NOT_ASSESSABLE, NOT_SUPPORTED, REFUSED, SUPPORTED, Problem
from .score import outcome

EXACT, PROXY, NONE = "EXACT", "PROXY", "NONE"
CLASSES = ("REPRESENTABLE_EXACTLY", "REPRESENTABLE_APPROXIMATELY", "NOT_REPRESENTABLE", "UNKNOWN")

CAPABILITY = {
    "MODEL_ADEQUACY": {
        "path": "none: the declared 1RC family is not in the hypothesis space (log-linear structures)",
        "reachable": [NOT_ASSESSABLE], "semantics": NONE},
    "MODEL_DISCREPANCY": {
        "path": "none: residuals of the declared family are never computed by the arm",
        "reachable": [NOT_ASSESSABLE], "semantics": NONE},
    "IDENTIFIABILITY": {
        "path": "RELAXATION probe: curvature in ln t of the relaxation impedance stands for an identifiable RC time scale",
        "reachable": sorted({v for v in mind_arm.TRANSLATION["RELAXATION"].values()}),
        "reachable_if_problem_refused": [REFUSED], "semantics": PROXY,
        "limits": "no judgment of R0-versus-OCV confounding, hold-convention sensitivity, bound activity or R0 alone"},
    "WITHIN_CELL_GENERALIZATION": {
        "path": "PREDICTION probe per held-out subset: the Mind's own log-linear law, compared to the declared bar",
        "reachable": [SUPPORTED, NOT_SUPPORTED, NOT_ASSESSABLE, REFUSED],
        "reachable_if_set_absent": [NOT_ASSESSABLE], "semantics_if_set_absent": EXACT,
        "reachable_if_region_empty": [NOT_ASSESSABLE], "semantics": PROXY,
        "limits": "scores loaded samples at t_on >= median(dt)/tolerance only; applicability is extrapolation of the "
                  "settable inputs, not the declared temperature/current/SOC rule; a decisive answer requires the "
                  "Mind to issue a LAW first"},
    "CROSS_CELL_TRANSFER": {
        "path": "PREDICTION probe per held-out subset (same as within-cell; cell identity is not represented)",
        "reachable": [SUPPORTED, NOT_SUPPORTED, NOT_ASSESSABLE, REFUSED],
        "reachable_if_set_absent": [NOT_ASSESSABLE], "semantics_if_set_absent": EXACT,
        "reachable_if_region_empty": [NOT_ASSESSABLE], "semantics": PROXY,
        "limits": "as within-cell; transfer is judged only through prediction error of the Mind's own law"},
}
SET_OF_AXIS = {"WITHIN_CELL_GENERALIZATION": "within_cell_heldout", "CROSS_CELL_TRANSFER": "cross_cell_heldout"}


def reachable(problem: Problem) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    try:
        probes = mind_arm.probe_problems(problem)
    except Exception as exc:                            # noqa: BLE001 - recorded, classified UNKNOWN
        return {a: {"reachable": None, "semantics": None, "why": f"capability probe failed: {exc!r}"} for a in AXES}
    for axis in AXES:
        cap = CAPABILITY[axis]
        if axis in ("MODEL_ADEQUACY", "MODEL_DISCREPANCY"):
            out[axis] = {"reachable": cap["reachable"], "semantics": cap["semantics"], "why": cap["path"]}
        elif axis == "IDENTIFIABILITY":
            if probes.get("RELAXATION") is None:
                out[axis] = {"reachable": cap["reachable_if_problem_refused"], "semantics": cap["semantics"],
                             "why": "the RELAXATION probe's problem is refused from the pack alone (empty box or pool): "
                                    "the arm can only refuse"}
            else:
                out[axis] = {"reachable": cap["reachable"], "semantics": cap["semantics"],
                             "why": cap["path"] + "; " + cap["limits"]}
        else:
            sets = problem.heldout(SET_OF_AXIS[axis])
            if sets is None:
                out[axis] = {"reachable": cap["reachable_if_set_absent"], "semantics": cap["semantics_if_set_absent"],
                             "why": "no held-out set of this kind is supplied; the arm answers NOT_ASSESSABLE, which is "
                                    "the question's own answer for an absent set"}
                continue
            subs = {k: probes.get(f"PREDICTION[{SET_OF_AXIS[axis]}/{k}]") for k in sets}
            if all(v is None for v in subs.values()):
                out[axis] = {"reachable": cap["reachable_if_region_empty"], "semantics": cap["semantics"],
                             "why": "every subset's region or problem is empty/refused from the pack alone"}
            else:
                out[axis] = {"reachable": cap["reachable"], "semantics": cap["semantics"],
                             "why": cap["path"] + "; " + cap["limits"],
                             "subsets_with_problem": sorted(k for k, v in subs.items() if v is not None)}
    return out


def classify(truth: str | None, entry: Mapping[str, Any]) -> str | None:
    if truth is None:
        return None
    if entry.get("reachable") is None:
        return "UNKNOWN"
    if not any(outcome(a, truth) in ("CORRECT", "CORRECT_REFUSAL") for a in entry["reachable"]):
        return "NOT_REPRESENTABLE"
    return "REPRESENTABLE_EXACTLY" if entry["semantics"] == EXACT else "REPRESENTABLE_APPROXIMATELY"


__all__ = ["CAPABILITY", "CLASSES", "classify", "reachable"]
