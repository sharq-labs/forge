"""The v1 gap map: why each failed battery_rediscovery_v1 axis failed, from candidate-side records only.

Inputs (all frozen before this task, none modified):
- ``PLAN.json["representability"]``: the reachable answer set and path semantics of every (problem, axis), frozen
  before the v1 run;
- ``results/candidate/MIND__P*.json``: the sealed Mind outputs (conclusion kind, translation key, the problem the probe
  was posed as: its settable inputs and passive covariates);
- the candidate-visible pack (description, conventions, declared model);
- from ``results/EVALUATION.json`` only three labels per instance: ``class`` (the representability class),
  ``mind_answer`` and ``mind_outcome``.  The ``truth`` and ``careful_answer`` fields are never read
  (:data:`EVALUATION_FIELDS_READ` is the whitelist; a test pins it).

The classification rule (:func:`primary_gap`) uses the Mind's own record of what it did, never what the right answer
was: whether a failure happened at all is the outcome label, but WHY is read from the trace.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Mapping

V1 = pathlib.Path(__file__).resolve().parents[1] / "battery_rediscovery_v1"
OUT = pathlib.Path(__file__).resolve().parent / "results" / "GAP_MAP.json"
SCHEMA = "forge.mind.repsem.gap_map/1"
EVALUATION_FIELDS_READ = ("class", "mind_answer", "mind_outcome")
FAILED = ("FALSE_REFUSE", "FALSE_SUPPORT", "WRONG")

GAPS = ("REPRESENTATION_MISSING", "SEMANTIC_ROLE_ERROR", "HYPOTHESIS_GENERATION_FAILURE", "EVIDENCE_UPDATE_FAILURE",
        "STOPPING_REFUSAL_FAILURE", "MULTIPLE_CAUSES", "UNKNOWN")

#: The scientific role each probe variable has under the PROTOCOL, with the candidate-visible pack field that says so.
#: (The v1 adapter gave these variables the Mind's two classes only: settable input or passive covariate.)
PROTOCOL_ROLES = {
    "P1": {"I_A": ("FIXED_PROTOCOL_CONDITION", "description: 'one protocol: constant-current discharge'"),
           "z": ("STATE_VARIABLE", "conventions.initial_soc + capacity_basis: coulomb-counted from the applied current"),
           "T_K": ("NUISANCE_VARIABLE", "measurement_uncertainty.temperature_C: measured, never set")},
    "P2": {"I_A": ("FIXED_PROTOCOL_CONDITION", "description: 'discharge pulses at two current levels' (held-out: two "
                   "other levels)"),
           "z": ("STATE_VARIABLE", "conventions.initial_soc: 'z0 per trajectory, from the coulomb count'"),
           "T_K": ("NUISANCE_VARIABLE", "description: 'at 25 C ambient'; measured, never set")},
}


def _load(path: pathlib.Path) -> Any:
    return json.loads(path.read_bytes())


def _evaluation_labels() -> dict[str, dict[str, str]]:
    instances = _load(V1 / "results" / "EVALUATION.json")["instances"]
    return {k: {f: v[f] for f in EVALUATION_FIELDS_READ} for k, v in sorted(instances.items())}


def _probe_for(axis: str) -> str | None:
    return {"IDENTIFIABILITY": "RELAXATION", "WITHIN_CELL_GENERALIZATION": "within_cell_heldout",
            "CROSS_CELL_TRANSFER": "cross_cell_heldout"}.get(axis)


def _probe_records(mind: Mapping[str, Any], axis: str) -> list[tuple[str, Mapping[str, Any]]]:
    probe = _probe_for(axis)
    if probe is None:
        return []
    detail = mind["detail"]
    if probe == "RELAXATION":
        return [("RELAXATION", detail["probes"]["RELAXATION"]["per_seed"]["0"])]
    return [(k, v["per_seed"]["0"]) for k, v in sorted(detail["prediction"].items()) if v["set"] == probe]


def primary_gap(pid: str, axis: str, label: Mapping[str, str], capability: Mapping[str, Any],
                mind: Mapping[str, Any]) -> tuple[str, list[str]]:
    """``(gap, evidence lines)`` for one failed instance, read from the sealed candidate records only."""
    records = _probe_records(mind, axis)
    if label["class"] == "NOT_REPRESENTABLE" and capability["semantics"] == "NONE":
        return "REPRESENTATION_MISSING", [f"frozen capability: {capability['why']}",
                                          f"sealed answer reason: {mind['answers'][axis]['reason']}"]
    refused = [r for _, r in records if "problem_refused" in r]
    if label["class"] == "NOT_REPRESENTABLE" and refused:
        return "REPRESENTATION_MISSING", [
            f"frozen reachable set {capability['reachable']}: {capability['why']}",
            f"sealed RELAXATION probe: problem_refused ({refused[0]['problem_refused']})",
            "the claim is about latent R0/R1/C1, which have no representation in the Mind; its only path is an observable-"
            "shape proxy, and the proxy's problem cannot be built from this pack"]
    keys = [(name, r.get("translation", {}).get("key"), r) for name, r in records]
    passive = [(name, r) for name, key, r in keys if key == "unidentifiable_passive_association"]
    if passive:
        lines = []
        for name, r in passive:
            diag = r["conclusion"]["diagnostics"]
            cov = [k.split(":", 1)[1] for k in diag if k.startswith("inclusion:")]
            for c in cov:
                role, basis = PROTOCOL_ROLES[pid][c]
                lines.append(f"{name}: refused as a passive association with {c} (inclusion {diag['inclusion:' + c]}); "
                             f"posed as covariates {r['problem']['covariates']} beside settable "
                             f"{[x['name'] for x in r['problem']['inputs']]}; protocol role of {c} = {role} ({basis})")
        roles = {PROTOCOL_ROLES[pid][c][0] for name, r in passive
                 for c in [k.split(':', 1)[1] for k in r["conclusion"]["diagnostics"] if k.startswith("inclusion:")]}
        if roles and "NUISANCE_VARIABLE" not in roles:
            return "SEMANTIC_ROLE_ERROR", lines
        return "UNKNOWN", lines
    linear = [(name, r) for name, key, r in keys if key == "law_linear_only"]
    if linear:
        name, r = linear[0]
        law = r["conclusion"]["laws"][0]
        return "MULTIPLE_CAUSES", [
            f"{name}: LAW {law['hypothesis_id']} linear in ln t_off ({law['linear']}), no curvature term -> translated REVIEW",
            "REPRESENTATION_MISSING: identifiability of latent R0/R1/C1 is judged through the shape of an observable, not "
            "through the parameters' information",
            "HYPOTHESIS_GENERATION_FAILURE: the log-linear structure family has no exponential relaxation term, so an RC "
            "time scale can only appear as curvature in ln t; the arm cannot test it as a parameter"]
    return "UNKNOWN", [f"{n}: translation {k}" for n, k, _ in keys]


def build() -> dict[str, Any]:
    plan = _load(V1 / "PLAN.json")["representability"]
    labels = _evaluation_labels()
    minds = {pid: _load(V1 / "results" / "candidate" / f"MIND__{pid}.json") for pid in ("P1", "P2")}
    rows = []
    for key, label in labels.items():
        pid, axis = key.split("/")
        cap = plan["reachable"][pid][axis]
        failed = label["mind_outcome"] in FAILED
        gap, evidence = primary_gap(pid, axis, label, cap, minds[pid]) if failed else (None, [])
        rows.append({"instance": key, "current_answer": label["mind_answer"], "outcome": label["mind_outcome"],
                     "representability": label["class"], "reachable": cap["reachable"], "semantics": cap["semantics"],
                     "failed": failed, "primary_gap": gap, "evidence": evidence})
    failed = [r for r in rows if r["failed"]]
    tally = {g: sum(r["primary_gap"] == g for r in failed) for g in GAPS}
    return {"schema": SCHEMA, "inputs": {"plan_representability": "battery_rediscovery_v1/PLAN.json#representability",
                                         "sealed_mind": ["results/candidate/MIND__P1.json", "results/candidate/MIND__P2.json"],
                                         "evaluation_fields_read": list(EVALUATION_FIELDS_READ)},
            "rows": rows, "failed": len(failed), "tally": tally,
            "not_representable_failures": sorted(r["instance"] for r in failed if r["representability"] == "NOT_REPRESENTABLE")}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(build(), sort_keys=True, indent=1) + "\n").encode())


if __name__ == "__main__":
    main()
