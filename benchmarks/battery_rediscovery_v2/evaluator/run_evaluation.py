"""Evaluate the sealed v2 outputs (run only after the seal and the replay are committed).  No amendment option exists.

    python -m benchmarks.battery_rediscovery_v2.evaluator.run_evaluation

Order: verify the seal (``truth.extract`` refuses otherwise) -> require the post-seal mutation report (PASS) and the
sandboxed replay -> post-seal leakage audit of the candidate material and both access logs -> compute the truth table
(reference protocol) -> score every arm -> the preregistered hypotheses and the single conclusion -> EVALUATION.json/.md.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from .. import leakage, mutation
from ..candidate import arms
from ..candidate.common import AXES, load_pack, write_json
from . import conclusion as cr
from . import score, truth

HERE = pathlib.Path(__file__).resolve().parents[1]
RESULTS = HERE / "results"
LABEL = {"OLD_MIND": "Old Mind", "REPRESENTATION_ONLY": "Representation", "SEMANTIC_ROLES_ONLY": "Roles",
         "REPRESENTATION_PLUS_ROLES": "Combined", "CAREFUL_BASELINE": "Careful"}
ROW_AXES = {"MODEL_ADEQUACY": "MODEL_ADEQUACY", "IDENTIFIABILITY": "IDENTIFIABILITY", "WITHIN_CELL": "WITHIN_CELL_GENERALIZATION",
            "CROSS_CELL": "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY": "MODEL_DISCREPANCY"}


def replay_summary(rep: dict[str, Any]) -> dict[str, Any]:
    outputs = {k: v for k, v in rep["arms"].items() if "TRACES" not in k}
    traces = {f"{p}:{k}": v for p, d in rep["old_mind_traces"].items() for k, v in d.items()}
    per_arm: dict[str, dict[str, int]] = {}
    for name, v in outputs.items():
        arm = name.split("__")[0]
        per_arm.setdefault(arm, {"identical": 0, "outputs": 0})
        per_arm[arm]["outputs"] += 1
        per_arm[arm]["identical"] += int(v["identical"])
    repsem = rep["repsem_assessments"]
    trace_files = {k: v for k, v in rep["arms"].items() if "TRACES" in k}
    exact = (all(v["identical"] for v in rep["arms"].values())
             and all(v.get("status") == "EXACT" for v in repsem.values())
             and traces and all(v.get("status") == "VERIFIED" and v.get("problem_digest_matches") for v in traces.values()))
    return {"exact": bool(exact), "per_arm": per_arm, "repsem_exact": sum(v.get("status") == "EXACT" for v in repsem.values()),
            "repsem_total": len(repsem), "old_mind_traces_verified": sum(v.get("status") == "VERIFIED" for v in traces.values()),
            "old_mind_traces": len(traces), "trace_files_identical": sum(v["identical"] for v in trace_files.values()),
            "trace_files": len(trace_files),
            "non_identical": sorted(k for k, v in rep["arms"].items() if not v["identical"])}


def _cell(s: dict[str, Any], axis: str) -> str:
    t = s["by_axis"][axis]
    return f"{t['correct']}/{t['scored']}"


def table(scores: dict[str, Any], rs: dict[str, Any]) -> list[list[str]]:
    rows = [["Axis", *[LABEL[a] for a in arms.ARMS]]]
    for label, axis in ROW_AXES.items():
        rows.append([label, *[_cell(scores[a], axis) for a in arms.ARMS]])
    for key in ("CORRECT_REFUSAL", "FALSE_SUPPORT", "FALSE_REFUSE"):
        rows.append([key, *[str(scores[a]["all"]["counts"][key]) for a in arms.ARMS]])
    rows.append(["REPLAY", *[f"{rs['per_arm'][a]['identical']}/{rs['per_arm'][a]['outputs']}"
                             + (" EXACT" if rs["per_arm"][a]["identical"] == rs["per_arm"][a]["outputs"] else "")
                             for a in arms.ARMS]])
    return rows


def _md_table(rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(rows[0]) + " |", "|---|" + "---:|" * (len(rows[0]) - 1)]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def main() -> int:
    cand, rep_dir = RESULTS / "candidate", RESULTS / "replay"
    t = truth.extract(RESULTS)                                     # refuses unless the seal is verified
    mut = json.loads((HERE / "MUTATION_REPORT_post_seal.json").read_bytes())
    rs = replay_summary(json.loads((rep_dir / "REPLAY.json").read_bytes()))
    audit = leakage.audit(mutation.protected_values(), phase="post_seal",
                          access_logs=[(RESULTS / "ACCESS_LOG.json", [cand], []),
                                       (RESULTS / "ACCESS_LOG_REPLAY.json", [rep_dir], [cand])])
    write_json(RESULTS / "LEAKAGE_POST_SEAL.json", audit)
    write_json(RESULTS / "TRUTH.json", t)
    specs = load_pack()
    outputs = {a: {pid: json.loads((cand / f"{a}__{pid}.json").read_bytes()) for pid in sorted(specs)}
               for a in arms.ALL_ARMS}
    scores = {a: score.score_arm(outputs[a], t["table"], specs) for a in arms.ALL_ARMS}
    claims = {pid: outputs["REPRESENTATION_PLUS_ROLES"][pid]["assessment"]["claims"] for pid in specs}
    leakage_ok = audit["status"] == "PASS" and mut["status"] == "PASS"
    concl = cr.conclude(seal_ok=True, leakage_ok=leakage_ok, replay_exact=rs["exact"], scores=scores,
                        combined_claims=claims)
    rows = table(scores, rs)
    ev = {"schema": "forge.battery_rediscovery_v2.evaluation/1", "seal": t["seal"], "conclusion": concl,
          "table": rows, "scores": scores, "replay": rs,
          "leakage": {"post_seal_audit": audit["status"], "post_seal_mutation": {k: mut[k] for k in (
              "status", "leak_mutations", "leaks_caught", "benign_controls", "benign_triggered")}},
          "truth_summary": {pid: {a: t["table"][pid][a]["truth"] for a in AXES} for pid in specs}}
    write_json(RESULTS / "EVALUATION.json", ev)
    md = ["# battery_rediscovery_v2 evaluation", "", f"**Conclusion: {concl['verdict']}** ({concl['why']})", "",
          _md_table(rows), "", "Cells: correct (CORRECT + CORRECT_REFUSAL) / scored instances on that axis, over Q1 and Q2.",
          "", "Truth per instance:", ""]
    for pid in sorted(specs):
        for a in AXES:
            md.append(f"- {pid} {a}: {t['table'][pid][a]['truth']}")
    md += ["", f"Leakage: post-seal audit {audit['status']}, post-seal mutation {mut['status']}.",
           f"Replay: exact={rs['exact']}; repsem {rs['repsem_exact']}/{rs['repsem_total']} EXACT; OLD_MIND traces "
           f"{rs['old_mind_traces_verified']}/{rs['old_mind_traces']} VERIFIED.", ""]
    (RESULTS / "EVALUATION.md").write_bytes(("\n".join(md) + "\n").encode())
    print(concl["verdict"], "-", concl["why"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
