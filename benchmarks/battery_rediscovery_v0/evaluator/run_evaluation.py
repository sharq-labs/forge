"""Evaluate the sealed candidate outputs against historical truth (run only after the seal is committed).

    python -m benchmarks.battery_rediscovery_v0.evaluator.run_evaluation --results <results dir>

Order: verify the seal -> post-seal leakage audit (historical values now admitted to the scan) -> read historical
truth -> score every arm on every axis -> rediscovery comparison -> preregistered conclusion.  Writes EVALUATION.json
and EVALUATION.md next to the seal.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from .. import leakage
from ..candidate.common import AXES, write_json
from . import score, truth

ARMS = ("MIND", "FIXED_FIT", "CAREFUL_BASELINE", "ALWAYS_FIT", "ALWAYS_REFUSE")
PIDS = ("P1", "P2")


def _load_outputs(cand: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {arm: {pid: json.loads((cand / f"{arm}__{pid}.json").read_bytes()) for pid in PIDS} for arm in ARMS}


def _secondary(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm, recs in outputs.items():
        s: dict[str, Any] = {"observations_used": {p: recs[p]["observations_used"] for p in PIDS}}
        for p in PIDS:
            r = recs[p]
            if "fit" in r:
                per = r["fit"]["per_parameter"]
                s.setdefault("parameter_stability", {})[p] = {
                    k: {"forward_hold_shift": round(v["forward_hold_shift"], 4),
                        "multistart_spread_ln": round(v["multistart_spread_ln"], 6),
                        "sd_ln": v["sd_ln"] if v["sd_ln"] == v["sd_ln"] else None} for k, v in per.items()}
                s.setdefault("estimates", {})[p] = r["fit"]["parameters"]
                s.setdefault("calibration_rmse_mV", {})[p] = round(r["fit"]["calibration"]["rmse_mV"], 3)
            if "heldout" in r:
                s.setdefault("heldout", {})[p] = {k: {"rmse_mV": round(v["stats"]["rmse_mV"], 3),
                                                      "p95_abs_mV": round(v["stats"]["p95_abs_mV"], 3),
                                                      "lag1": round(v["stats"]["lag1"], 3), "meets_bar": v["meets_bar"],
                                                      "out_of_domain": len(v["out_of_domain"]),
                                                      "trajectories": v["trajectories"], "coverage_95": v["coverage_95"]}
                                                  for k, v in r["heldout"].items()}
            if arm == "MIND":
                seed = str(r["primary_seed"])
                det = r["detail"]
                s.setdefault("dispositions_stable_across_seeds", {})[p] = r["dispositions_stable_across_seeds"]
                s.setdefault("probes", {})[p] = {}
                runs = {"RELAXATION": det["probes"]["RELAXATION"]["per_seed"][seed]}
                runs.update({f"PREDICTION[{k}]": v["per_seed"][seed] for k, v in det["prediction"].items()})
                for name, run in runs.items():
                    c = run.get("conclusion", {})
                    s["probes"][p][name] = {"kind": c.get("kind"), "translation": run["translation"],
                                            "served": run.get("queries_served"), "refused": len(run.get("queries_refused", [])),
                                            "sealed_predictions": run.get("sealed_pre_result_predictions"),
                                            "eliminated": len(run.get("eliminated", [])),
                                            "heldout": run.get("heldout", {}).get("stats"),
                                            "coverage_95": run.get("heldout", {}).get("coverage_95"),
                                            "problem_refused": run.get("problem_refused"),
                                            "reason": (c.get("reason") or "")[:240]}
        out[arm] = s
    return out


def _replay_summary(replay: dict[str, Any]) -> dict[str, Any]:
    arms = replay["arms"]
    traces = [v for p in replay["mind_traces"].values() for v in p.values()]
    return {"outputs_identical": sum(v["identical"] for v in arms.values()), "outputs": len(arms),
            "mind_traces_verified": sum(1 for v in traces if v.get("status") == "VERIFIED" and v.get("problem_digest_matches")),
            "mind_traces": len(traces),
            "non_identical": sorted(k for k, v in arms.items() if not v["identical"]),
            "trace_status": {f"{p}:{k}": v.get("status") for p, d in replay["mind_traces"].items() for k, v in d.items()}}


def _cell(recs: dict[str, Any], axis: str) -> str:
    return "; ".join(f"{p} {recs[p]['answers'][axis]['disposition']}" for p in PIDS)


def _markdown(ev: dict[str, Any]) -> str:
    T = ev["truth"]["table"]
    out = ev["outputs_answers"]
    best = ev["conclusion"]["checks"]["best_baseline"]
    sm, sb = ev["scores"]["MIND"], ev["scores"][best]
    lines = ["# BR-BATT-REDISC-01 evaluation", "",
             f"Conclusion: **{ev['conclusion']['conclusion']}** (development pilot; not formal, not certified).", "",
             "| Axis | Mind | Best baseline (" + best + ") | Historical truth | Result |", "|---|---|---|---|---|"]
    for axis in AXES:
        res = "; ".join(f"{p} {sm['per_instance'][f'{p}/{axis}']['outcome']}" for p in PIDS)
        tru = "; ".join(f"{p} {T[p][axis]['truth']}{' (derived)' if T[p][axis]['derived'] else ''}" for p in PIDS)
        lines.append(f"| {axis} | {_cell(out['MIND'], axis)} | {_cell(out[best], axis)} | {tru} | {res} |")
    c = ev["conclusion"]["checks"]
    lines += [f"| CORRECT_REFUSAL | {sm['counts']['CORRECT_REFUSAL']} | {sb['counts']['CORRECT_REFUSAL']} | "
              f"{sum(1 for p in PIDS for a in AXES if T[p][a]['truth'] == 'NOT_ASSESSABLE')} opportunities | |",
              f"| FALSE_SUPPORT | {sm['counts']['FALSE_SUPPORT']} | {sb['counts']['FALSE_SUPPORT']} | 0 | |",
              f"| FALSE_REFUSE | {sm['counts']['FALSE_REFUSE']} | {sb['counts']['FALSE_REFUSE']} | 0 | |",
              f"| EFFICIENCY (observations) | {ev['secondary']['MIND']['observations_used']} | "
              f"{ev['secondary'][best]['observations_used']} | | |",
              f"| REPLAY | {ev['replay']['mind_traces_verified']}/{ev['replay']['mind_traces']} traces; "
              f"{ev['replay']['outputs_identical']}/{ev['replay']['outputs']} outputs identical | | | |", "",
              "| Arm | CORRECT | CORRECT_REFUSAL | FALSE_SUPPORT | FALSE_REJECT | UNSUPPORTED_DECISION | FALSE_REFUSE | scored |",
              "|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        k = ev["scores"][arm]["counts"]
        lines.append(f"| {arm} | {k['CORRECT']} | {k['CORRECT_REFUSAL']} | {k['FALSE_SUPPORT']} | {k['FALSE_REJECT']} | "
                     f"{k['UNSUPPORTED_DECISION']} | {k['FALSE_REFUSE']} | {ev['scores'][arm]['scored']} |")
    lines += ["", "Rediscovery classes (Mind):", ""]
    for k, v in ev["rediscovery"]["axes"].items():
        lines.append(f"- {k}: {v['class']} (Mind {v['mind']}, history {v['history']})")
    lines += ["", f"Representation/interface-caused non-committal Mind answers: {c['mind_representation_noncommittal']} of "
              f"{c['mind_scored']} scored.", ""]
    return "\n".join(lines) + "\n"


def evaluate(results: pathlib.Path, *, amendment: str = "") -> dict[str, Any]:
    """``amendment`` (e.g. "AMENDMENT_01") writes every output under a suffixed name, leaving the preregistered
    evaluation files untouched; the amendment is described in ``results/<amendment>.json``."""
    sfx = f"_{amendment}" if amendment else ""
    t = truth.extract(results)                       # refuses unless the seal is verified
    cand = results / "candidate"
    post = leakage.audit(results / "ACCESS_LOG.json", cand, post_seal=True)
    write_json(results / f"LEAKAGE_POST_SEAL{sfx}.json", post)
    pre = json.loads((results / "LEAKAGE_PRE_SEAL.json").read_bytes())
    outputs = _load_outputs(cand)
    scores = {arm: score.score_arm(outputs[arm], t) for arm in ARMS}
    replay = json.loads((results / "replay" / "REPLAY.json").read_bytes())
    rs = _replay_summary(replay)
    primary_traces_ok = all(v == "VERIFIED" for v in rs["trace_status"].values())
    mind_ok = all(outputs["MIND"][p]["schema"] for p in PIDS)
    concl = score.conclusion(leakage_ok=pre["status"] == "PASS" and post["status"] == "PASS", mind_end_to_end=mind_ok,
                             mind_replay_ok=primary_traces_ok and not rs["non_identical"], scores=scores,
                             mind=outputs["MIND"], truth=t)
    ev = {"schema": "forge.battery_rediscovery.evaluation/1", "truth": t, "leakage": {"pre_seal": pre["status"],
          "post_seal": post["status"]}, "scores": scores, "conclusion": concl,
          "rediscovery": score.rediscovery(outputs["MIND"], t), "attention": score.attention(outputs["MIND"], t),
          "secondary": _secondary(outputs), "replay": rs,
          "outputs_answers": {arm: {p: {"answers": outputs[arm][p]["answers"]} for p in PIDS} for arm in ARMS},
          "maturity": {"IMPLEMENTED": "YES", "TESTED": "synthetic-world tests (see PROGRESS)", "MEASURED": "YES (one bounded "
                       "pilot run)", "SCIENTIFICALLY_VERIFIED": "NO", "CERTIFIED": "NO", "FORMAL": "NO"}}
    if amendment:
        ev["amendment"] = json.loads((results / f"{amendment}.json").read_bytes())
    write_json(results / f"EVALUATION{sfx}.json", ev)
    md = _markdown(ev)
    if amendment:
        md = md.replace("# BR-BATT-REDISC-01 evaluation", f"# BR-BATT-REDISC-01 evaluation ({amendment}, post-seal)\n\n"
                        f"{ev['amendment']['summary']}", 1)
    (results / f"EVALUATION{sfx}.md").write_bytes(md.encode())
    return ev


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, type=pathlib.Path)
    ap.add_argument("--amendment", default="", help="write a disclosed post-seal amendment's outputs under this suffix")
    a = ap.parse_args(argv)
    ev = evaluate(a.results, amendment=a.amendment)
    print(ev["conclusion"]["conclusion"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
