"""Evaluate the sealed v1 outputs (run only after the seal is committed).  No amendment option exists.

    python -m benchmarks.battery_rediscovery_v1.evaluator.run_evaluation

Order: verify the seal (``truth.extract`` refuses otherwise) -> re-derive the protected values from the historical
records and check them against the pre-run set -> post-seal mutation suite -> post-seal audit of the candidate tree and
both access logs -> score every arm -> classify every scored instance for representability from the FROZEN reachable
sets -> the preregistered primary analysis and conclusion -> v0 replication check.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter
from typing import Any

from .. import leakage, mutation
from ..candidate.common import AXES, write_json
from . import conclusion as cr
from . import representability as rp
from . import score, truth

HERE = pathlib.Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
V0 = HERE.parent / "battery_rediscovery_v0"
ARMS = ("MIND", "FIXED_FIT", "CAREFUL_BASELINE", "ALWAYS_FIT", "ALWAYS_REFUSE")
LABEL = {"MIND": "MIND_V0_REPRESENTATION"}
PIDS = ("P1", "P2")
CAL = {"P1": "benchmarks/battery_1rc_closure/results/CALIBRATION.json",
       "P2": "benchmarks/battery_1rc_identifiability/results/CALIBRATION.json"}


def _protected_post_seal(t: dict[str, Any]) -> tuple[list[leakage.Protected], dict[str, Any]]:
    pre = mutation.historical_values()
    v0 = json.loads((V0 / "results" / "EVALUATION.json").read_bytes())["truth"]
    consistent = (v0["historical_parameters"] == t["historical_parameters"]
                  and v0["historical_heldout_rmse_mV"] == t["historical_heldout_rmse_mV"])
    extra = []
    for pid, rel in CAL.items():
        rec = json.loads((ROOT / rel).read_bytes())
        extra.append(leakage.protected(f"{pid}.rint_calibration_rmse", repr(rec["models"]["rint"]["rmse_mV"]), "mV"))
    return list(mutation.SYNTHETIC) + pre + extra, {"pre_run_values_match_history_records": consistent,
                                                    "added_post_seal": [v.name for v in extra]}


def _replay_summary(replay: dict[str, Any]) -> dict[str, Any]:
    arms = replay["arms"]
    traces = {f"{p}:{k}": v for p, d in replay["mind_traces"].items() for k, v in d.items()}
    return {"outputs_identical": sum(v["identical"] for v in arms.values()), "outputs": len(arms),
            "non_identical": sorted(k for k, v in arms.items() if not v["identical"]),
            "mind_traces": len(traces),
            "mind_traces_verified": sum(1 for v in traces.values() if v.get("status") == "VERIFIED"
                                        and v.get("problem_digest_matches")),
            "trace_status": {k: v.get("status") for k, v in traces.items()}}


def _v0_replication() -> dict[str, Any]:
    out = {}
    for p in sorted((RESULTS / "candidate").glob("*.json")):
        if p.name == "TIMINGS.json":
            continue
        q = V0 / "results" / "candidate" / p.name
        out[p.name] = q.exists() and q.read_bytes() == p.read_bytes()
    return {"files": out, "all_identical": all(out.values()), "identical": sum(out.values()), "compared": len(out)}


def _md(ev: dict[str, Any]) -> str:
    inst, a, c = ev["instances"], ev["analysis"], ev["conclusion"]
    sm, sc = ev["scores"]["MIND"]["counts"], ev["scores"]["CAREFUL_BASELINE"]["counts"]
    short = {"REPRESENTABLE_EXACTLY": "EXACT", "REPRESENTABLE_APPROXIMATELY": "APPROX", "NOT_REPRESENTABLE": "NOT_REPR",
             "UNKNOWN": "UNKNOWN", None: "unscored"}
    L = ["# battery_rediscovery_v1 evaluation (BR-BATT-REDISC-02)", "",
         f"Conclusion: **{c['conclusion']}** (development; not formal, not certified; no amendment).", "",
         "v0 history: PREREGISTERED_RESULT = LEAKAGE_INVALIDATED; POST_SEAL_AMENDMENT_RESULT = REPRESENTATION_BOTTLENECK; "
         "CONFIRMED_RESULT = NONE.", "",
         "| Axis | Mind | Careful baseline | Representability | Result (Mind) |", "|---|---|---|---|---|"]
    for axis in AXES:
        cells = [inst[f"{p}/{axis}"] for p in PIDS]
        L.append(f"| {axis} | " + "; ".join(f"{p} {x['mind_answer']}" for p, x in zip(PIDS, cells)) + " | "
                 + "; ".join(f"{p} {x['careful_answer']}" for p, x in zip(PIDS, cells)) + " | "
                 + "; ".join(f"{p} {short[x['class']]}" for p, x in zip(PIDS, cells)) + " | "
                 + "; ".join(f"{p} {x['mind_outcome']}" for p, x in zip(PIDS, cells)) + " |")

    def by_class(outcome_name: str) -> str:
        counts = Counter(short[x["class"]] for x in inst.values() if x["mind_outcome"] == outcome_name)
        return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "-"
    for row in ("CORRECT_REFUSAL", "FALSE_SUPPORT", "FALSE_REFUSE"):
        L.append(f"| {row} | {sm[row]} | {sc[row]} | {by_class(row)} | |")
    L += ["", "| Coverage | Count | Mind correct | Mind incorrect/refused |", "|---|---:|---:|---:|"]
    for cls in rp.CLASSES:
        ks = [k for k, x in inst.items() if x["class"] == cls]
        good = sum(inst[k]["mind_outcome"] in cr.GOOD for k in ks)
        L.append(f"| {cls} | {len(ks)} | {good} | {len(ks) - good} |")

    def pct(x: Any) -> str:
        return "n/a" if x is None else f"{x:.2f}"
    L += ["", f"- failures: {len(a['failures'])}; in NOT_REPRESENTABLE: {len(a['failures_in_N'])}; share_N = "
              f"{pct(a['share_N'])}",
          f"- accuracy on R (EXACT+APPROX): Mind {pct(a['acc_R_mind'])}, CAREFUL {pct(a['acc_R_careful'])}; on N: Mind "
          f"{pct(a['acc_N_mind'])}, CAREFUL {pct(a['acc_N_careful'])}; on EXACT only: Mind {pct(a['acc_EXACT_mind'])}, "
          f"CAREFUL {pct(a['acc_EXACT_careful'])}",
          f"- totals (CORRECT + CORRECT_REFUSAL): " + ", ".join(f"{LABEL.get(k, k)} {v['correct_total']}"
                                                                for k, v in ev["scores"].items()),
          f"- checks: {json.dumps(c['checks'])}",
          f"- leakage: mutation pre-run {ev['leakage']['mutation_pre_run']}, post-seal {ev['leakage']['mutation_post_seal']}"
          f"; pre-seal audit {ev['leakage']['pre_seal']}, post-seal audit {ev['leakage']['post_seal']}",
          f"- replay: {ev['replay']['outputs_identical']}/{ev['replay']['outputs']} outputs identical, "
          f"{ev['replay']['mind_traces_verified']}/{ev['replay']['mind_traces']} traces VERIFIED",
          f"- v0 replication: {ev['v0_replication']['identical']}/{ev['v0_replication']['compared']} sealed outputs "
          f"byte-identical to v0's", ""]
    return "\n".join(L) + "\n"


def evaluate() -> dict[str, Any]:
    t = truth.extract(RESULTS)                                   # refuses unless the committed seal verifies
    plan = json.loads((HERE / "PLAN.json").read_bytes())
    values, value_check = _protected_post_seal(t)
    mut = mutation.run(values, "post_seal")
    write_json(HERE / "MUTATION_REPORT_post_seal.json", mut)
    cand, rep_dir = RESULTS / "candidate", RESULTS / "replay"
    post = leakage.audit(values, access_logs=[RESULTS / "ACCESS_LOG.json", RESULTS / "ACCESS_LOG_REPLAY.json"],
                         out_dirs=[cand, rep_dir], phase="post_seal")
    write_json(RESULTS / "LEAKAGE_POST_SEAL.json", post)
    pre = json.loads((RESULTS / "LEAKAGE_PRE_SEAL.json").read_bytes())
    outputs = {arm: {p: json.loads((cand / f"{arm}__{p}.json").read_bytes()) for p in PIDS} for arm in ARMS}
    scores = {arm: score.score_arm(outputs[arm], t) for arm in ARMS}
    rs = _replay_summary(json.loads((rep_dir / "REPLAY.json").read_bytes()))
    reach = plan["representability"]["reachable"]
    instances = {}
    for p in PIDS:
        for axis in AXES:
            key = f"{p}/{axis}"
            T = t["table"][p][axis]["truth"]
            if T is None:
                continue
            instances[key] = {"truth": T, "class": rp.classify(T, reach[p][axis]), "reachable": reach[p][axis]["reachable"],
                              "semantics": reach[p][axis]["semantics"], "why": reach[p][axis]["why"],
                              "mind_answer": outputs["MIND"][p]["answers"][axis]["disposition"],
                              "careful_answer": outputs["CAREFUL_BASELINE"][p]["answers"][axis]["disposition"],
                              "mind_outcome": scores["MIND"]["per_instance"][key]["outcome"],
                              "careful_outcome": scores["CAREFUL_BASELINE"]["per_instance"][key]["outcome"]}
    a = cr.analyse(instances)
    leakage_ok = all(x["status"] == "PASS" for x in (plan["leakage"]["mutation_pre_run"], mut, pre, post)) and \
        value_check["pre_run_values_match_history_records"]
    end_to_end = all(outputs["MIND"][p].get("schema") for p in PIDS)
    replay_ok = not rs["non_identical"] and rs["mind_traces_verified"] == rs["mind_traces"] and rs["mind_traces"] > 0
    concl = cr.conclude(leakage_ok=leakage_ok, end_to_end=end_to_end, replay_ok=replay_ok,
                        careful_total=scores["CAREFUL_BASELINE"]["correct_total"],
                        trivial_best=max(scores["ALWAYS_FIT"]["correct_total"], scores["ALWAYS_REFUSE"]["correct_total"]),
                        a=a)
    ev = {"schema": "forge.battery_rediscovery.evaluation/2", "experiment": "battery_rediscovery_v1",
          "v0_history": {"PREREGISTERED_RESULT": "LEAKAGE_INVALIDATED",
                         "POST_SEAL_AMENDMENT_RESULT": "REPRESENTATION_BOTTLENECK", "CONFIRMED_RESULT": "NONE"},
          "truth": t, "arm_labels": LABEL, "scores": scores, "instances": instances, "analysis": a, "conclusion": concl,
          "leakage": {"mutation_pre_run": plan["leakage"]["mutation_pre_run"]["status"], "mutation_post_seal": mut["status"],
                      "post_seal_leaks_caught": f"{mut['leaks_caught']}/{mut['leak_mutations']}",
                      "post_seal_benign_triggered": f"{mut['benign_triggered']}/{mut['benign_controls']}",
                      "pre_seal": pre["status"], "post_seal": post["status"], "protected_values": value_check},
          "replay": rs, "v0_replication": _v0_replication(),
          "maturity": {"IMPLEMENTED": "YES", "TESTED": "YES (synthetic-world, scanner and mutation tests)",
                       "MEASURED": "YES (one sealed run)", "SCIENTIFICALLY_VERIFIED": "NO", "CERTIFIED": "NO",
                       "FORMAL": "NO"}}
    write_json(RESULTS / "EVALUATION.json", ev)
    (RESULTS / "EVALUATION.md").write_bytes(_md(ev).encode())
    return ev


def main() -> int:
    ev = evaluate()
    print(ev["conclusion"]["conclusion"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
