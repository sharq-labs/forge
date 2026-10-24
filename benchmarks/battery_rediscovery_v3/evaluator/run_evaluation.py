"""Evaluate the sealed v3 outputs (run only after the seal and the replay are committed).  No amendment option exists.

    python -m benchmarks.battery_rediscovery_v3.evaluator.run_evaluation

Order: verify the seal and the committed replay (``truth.verify_seal`` refuses otherwise) -> require the post-seal
mutation report (PASS) -> post-seal leakage audit of the candidate material and both access logs -> compute the truth
table (references A and B; written to TruthBundle/TRUTH.json, the first truth in this tree) -> ``assemble``: score every
arm on the PLAN's primary instances, the conclusion rule with the single-instance robustness check, the bridge set,
degeneracy dimensions, implementation correlation and evidence strength -> results/EVALUATION.json and EVALUATION.md.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from benchmarks.battery_rediscovery_v2.candidate import arms
from benchmarks.battery_rediscovery_v2.candidate.common import AXES, digest, load_pack, write_json
from benchmarks.battery_rediscovery_v2.evaluator.run_evaluation import replay_summary
from benchmarks.battery_rediscovery_v2.evaluator.score import outcome

from .. import leakage, mutation
from ..build_pack import CHEN_PARTNER, PARTNER
from . import conclusion as cr
from . import diagnostics, truth

HERE = pathlib.Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
TRUTH_DIR = HERE / "TruthBundle"
VAULT = HERE / "EvaluatorVault"
V2_SEALED = ROOT / "benchmarks" / "battery_rediscovery_v2" / "results" / "candidate"
LABEL = {"OLD_MIND": "Old Mind", "REPRESENTATION_ONLY": "Representation", "SEMANTIC_ROLES_ONLY": "Roles",
         "REPRESENTATION_PLUS_ROLES": "Combined", "CAREFUL_BASELINE": "Careful"}
ROW_AXES = {"MODEL_ADEQUACY": "MODEL_ADEQUACY", "IDENTIFIABILITY": "IDENTIFIABILITY",
            "WITHIN_CELL": "WITHIN_CELL_GENERALIZATION", "CROSS_CELL": "CROSS_CELL_TRANSFER",
            "MODEL_DISCREPANCY": "MODEL_DISCREPANCY"}
SUPPORT_AXES = ("MODEL_ADEQUACY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER")


def build_instances(rows: list[dict[str, Any]], table: dict[str, Any], outputs: dict[str, dict[str, Any]],
                    arm_names) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        c = table[r["problem"]]["combined"][r["axis"]]
        out.append({"key": r["key"], "truth": table[r["problem"]]["truth"][r["axis"]], "heldout": r["heldout"],
                    "basis_kind": c["basis_kind"], "implementation_correlated": c["implementation_correlated"],
                    "answers": {a: outputs[a][r["problem"]]["answers"][r["axis"]]["disposition"] for a in arm_names}})
    return out


def _condition(design: dict[str, Any], spec: dict[str, Any]) -> str:
    if design["kind"] == "gitt":
        return "GITT pulses, beginning of life" if design["rpt"] == 0 else "GITT pulses, aged (latest RPT)"
    if design["kind"] == "chen":
        return "constant-current rate tests (0.5-7.5 A)"
    return spec["description"].split(".")[0] + ", " + str(spec["sets"]["calibration"][0]["columns"]["level_A"][0]) + " A"


def _md(rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(rows[0]) + " |", "|---|" + "---:|" * (len(rows[0]) - 1)]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def assemble(*, plan, table, specs, outputs, rs, ident, timings, audit_status, mut, v2_truth, v2_outputs, seal):
    """Scores, conclusion, degeneracy, correlation, evidence strength and the report: a pure function of its inputs."""
    leakage_ok = audit_status == "PASS" and mut["status"] == "PASS"
    primary = build_instances(plan["instances"]["primary"], table, outputs, arms.ALL_ARMS)
    bridge = build_instances(plan["instances"]["bridge"], table, outputs, arms.ALL_ARMS)
    disagreement = sum(i["basis_kind"] == "REFERENCE_DISAGREEMENT" for i in primary) / max(len(primary), 1)
    concl = cr.conclude(instances=primary, seal_ok=True, leakage_ok=leakage_ok, replay_exact=rs["exact"],
                        reference_disagreement_fraction=disagreement)
    degeneracy, degenerate_support = {}, []
    for pid in plan["eligibility"]["primary_problems"] + plan["eligibility"]["bridge_problems"]:
        dims = table[pid]["dimensions"]
        bd = table[pid]["reference_b"]["diagnostics"]
        comb = outputs["REPRESENTATION_PLUS_ROLES"][pid]
        pset = (comb.get("assessment") or {}).get("hypothesis", {}).get("parameter_set")
        cdeg = diagnostics.candidate_degeneracy(pset, horizon_s=bd["horizon_s"], median_dt_s=bd["median_dt_s"])
        degeneracy[pid] = {**dims, "CANDIDATE_PARAMETER_DEGENERACY": cdeg}
        for axis in SUPPORT_AXES:
            if comb["answers"][axis]["disposition"] == "SUPPORTED" and (
                    dims["PARAMETER_DEGENERACY"]["value"] == "YES" or cdeg["value"] == "YES"):
                degenerate_support.append({"instance": f"{pid}/{axis}", "reference_flags": dims["PARAMETER_DEGENERACY"]["flags"],
                                           "candidate_flags": cdeg["flags"], "truth": table[pid]["truth"][axis]})
    decided = [i for i in primary if i["truth"] in ("SUPPORTED", "NOT_SUPPORTED")]
    cells, conditions = set(), set()
    for i in decided:
        pid, axis = i["key"].split("/")
        d = ident[pid]["design"]
        cells.add(f"{d['kind']}:{d.get('expt', '')}:{d['cell']}")
        conditions.add(_condition(d, specs[pid]))
        if axis == "CROSS_CELL_TRANSFER" and d["kind"] == "gitt":     # the partner cell carries decided evidence too
            cells.add(f"gitt:{d['expt']}:{PARTNER[d['cell']]}")
        elif axis == "CROSS_CELL_TRANSFER" and d["kind"] == "chen":
            cells.add(f"chen::{CHEN_PARTNER[d['cell']]}")
    corr = [i["key"] for i in decided if i["implementation_correlated"]]
    assess = {}
    for ax in AXES:
        xs = [i for i in primary if i["key"].endswith("/" + ax)]
        assess[ax] = {k: sum(i["truth"] == k for i in xs) for k in ("SUPPORTED", "NOT_SUPPORTED", "NOT_ASSESSABLE")}
        assess[ax]["UNSCORED"] = sum(i["truth"] is None for i in xs)
        assess[ax]["REFERENCE_DISAGREEMENT"] = sum(i["basis_kind"] == "REFERENCE_DISAGREEMENT" for i in xs)
    compute = {a: round(sum(v for k, v in timings.items() if k.startswith(a + "__")), 1) for a in arms.ALL_ARMS}
    bridge_pids = plan["eligibility"]["bridge_problems"]
    bridge_repro = {f"{a}__{pid}": (f"{a}__{pid}" in v2_outputs
                                    and digest(v2_outputs[f"{a}__{pid}"]) == digest(outputs[a][pid]))
                    for a in arms.ALL_ARMS for pid in bridge_pids}
    bridge_truth_vs_v2 = {pid: {ax: {"v3": table[pid]["truth"][ax], "v2": v2_truth[pid][ax]["truth"]} for ax in AXES}
                          for pid in bridge_pids}
    st = concl["statistics"]
    rows = [["Axis", *[LABEL[a] for a in cr.ARMS], "Decided N"]]
    for label, axis in ROW_AXES.items():
        rows.append([label, *[f"{st[a]['by_axis'][axis]['correct']}/{st[a]['by_axis'][axis]['scored']}" for a in cr.ARMS],
                     str(st[cr.COMB]["by_axis"][axis]["decided"])])
    rows.append(["CORRECT_REFUSAL", *[str(st[a]["correct_refusal_n"]) for a in cr.ARMS], "-"])
    rows.append(["FALSE_SUPPORT", *[str(st[a]["false_support_n"]) for a in cr.ARMS], "-"])
    rows.append(["FALSE_REFUSE", *[str(st[a]["false_refuse_n"]) for a in cr.ARMS], "-"])
    rows.append(["REPLAY", *[f"{rs['per_arm'][a]['identical']}/{rs['per_arm'][a]['outputs']}"
                             + (" EXACT" if rs["per_arm"][a]["identical"] == rs["per_arm"][a]["outputs"] else "")
                             for a in cr.ARMS], "-"])
    strength = {"TOTAL_DECIDED_INSTANCES": len(decided),
                "HELD_OUT_DECIDED_INSTANCES": sum(i["heldout"] for i in decided),
                "INDEPENDENT_CELLS": len(cells), "OPERATING_CONDITIONS": sorted(conditions),
                "SINGLE_INSTANCE_ROBUST": "YES" if concl["robustness"]["robust"] else "NO",
                "IMPLEMENTATION_CORRELATED_INSTANCES": len(corr),
                "LEAKAGE": "PASS" if leakage_ok else "LEAKAGE_INVALIDATED",
                "REPLAY": "EXACT" if rs["exact"] else "NOT_EXACT",
                "REFERENCE_DISAGREEMENT_FRACTION": disagreement}
    ev = {"schema": "forge.battery_rediscovery_v3.evaluation/1", "seal": seal, "conclusion": concl, "table": rows,
          "evidence_strength": strength, "assessability": assess, "implementation_correlated": corr,
          "degeneracy": degeneracy, "degenerate_support": degenerate_support, "compute_cost_s": compute,
          "replay": rs, "leakage": {"post_seal_audit": audit_status, "post_seal_mutation": {k: mut[k] for k in (
              "status", "leak_mutations", "leaks_caught", "benign_controls", "benign_triggered")}},
          "bridge": {"reproduces_v2_sealed_outputs": bridge_repro, "all_reproduce": all(bridge_repro.values()),
                     "truth_v3_vs_v2": bridge_truth_vs_v2, "scores": {a: cr.arm_statistics(bridge, a) for a in cr.ARMS},
                     "note": "SECONDARY_BRIDGE_SET: never counted in the primary conclusion"},
          "instances": [dict(i, outcomes={a: outcome(i["answers"][a], i["truth"]) for a in arms.ALL_ARMS})
                        for i in primary],
          "reference_arms": {a: cr.arm_statistics(primary, a) for a in arms.REFERENCE_ARMS}}
    md = ["# battery_rediscovery_v3 evaluation", "", f"**V3_CONCLUSION: {concl['verdict']}** ({concl['why']})", "",
          _md(rows), "", "Cells: correct (CORRECT + CORRECT_REFUSAL) / scored primary instances on that axis.", "",
          _md([["Evidence-strength axis", "Result"]] + [[k, str(v)] for k, v in strength.items()]), ""]
    md += [f"- {k}: holds={v['holds']}" for k, v in concl["criteria"].items()]
    md += [f"- {k}: holds={v['holds']}" for k, v in concl["hypotheses"].items()]
    md += ["", f"Robustness: {concl['robustness']['perturbations_checked']} perturbations, "
               f"{len(concl['robustness']['breaking'])} breaking.", ""]
    return ev, "\n".join(md) + "\n"


def main() -> int:
    cand, rep_dir = RESULTS / "candidate", RESULTS / "replay"
    seal = truth.verify_seal(RESULTS)                              # refuses unless sealed and replayed
    mut = json.loads((HERE / "MUTATION_REPORT_post_seal.json").read_bytes())
    audit = leakage.audit(mutation.protected_values(), phase="post_seal",
                          access_logs=[(RESULTS / "ACCESS_LOG.json", [cand], []),
                                       (RESULTS / "ACCESS_LOG_REPLAY.json", [rep_dir], [cand])])
    write_json(RESULTS / "LEAKAGE_POST_SEAL.json", audit)
    plan = json.loads((HERE / "PLAN.json").read_bytes())
    t = truth.extract(RESULTS)
    TRUTH_DIR.mkdir(exist_ok=True)
    truth_sha = write_json(TRUTH_DIR / "TRUTH.json", t)
    specs = load_pack(HERE / "CandidateBundle")
    outputs = {a: {pid: json.loads((cand / f"{a}__{pid}.json").read_bytes()) for pid in sorted(specs)}
               for a in arms.ALL_ARMS}
    rs = replay_summary(json.loads((rep_dir / "REPLAY.json").read_bytes()))
    ident = json.loads((VAULT / "IDENTITY_MAP.json").read_bytes())
    timings = json.loads((cand / "TIMINGS.json").read_bytes())
    v2_truth = json.loads((ROOT / "benchmarks" / "battery_rediscovery_v2" / "results" / "TRUTH.json").read_bytes())["table"]
    v2_outputs = {f"{a}__{pid}": json.loads((V2_SEALED / f"{a}__{pid}.json").read_bytes())
                  for a in arms.ALL_ARMS for pid in plan["eligibility"]["bridge_problems"]
                  if (V2_SEALED / f"{a}__{pid}.json").exists()}
    ev, md = assemble(plan=plan, table=t["table"], specs=specs, outputs=outputs, rs=rs, ident=ident, timings=timings,
                      audit_status=audit["status"], mut=mut, v2_truth=v2_truth, v2_outputs=v2_outputs, seal=t["seal"])
    ev["truth_sha256"] = truth_sha
    write_json(RESULTS / "EVALUATION.json", ev)
    (RESULTS / "EVALUATION.md").write_bytes(md.encode())
    print(ev["conclusion"]["verdict"], "-", ev["conclusion"]["why"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
