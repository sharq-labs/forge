"""Stdlib-only: record the owner-authorized R-03..R-06 outcomes in the findings register (scratch package only)."""
import json, sys

path = sys.argv[1]
reg = json.load(open(path, encoding="utf-8"))
results = {
    "FDA-03": ("R-03", "Real MaterialPropertySet.resolve: 350 K gave INTERPOLATED 25.0 (ids a<b) and 20.0 (ids swapped) from the same "
               "two conflicting 300 K data; 300 K exactly gave UNKNOWN 'sources are not arbitrated'; coverage at 350 K "
               "conflicted=False. Control without coincident data: 20.0 independent of claim id."),
    "FDA-04": ("R-04", "Real build_deterministic_samples + predictive_intervals: n=4,k=3 Y=x1+x2 and n=32,k=17 Y=x15+x16 both "
               "status=completed, lower=upper=1.0, width 0, sd 0. Control n=32,k=2 Y=x0+x1 width 1.681, sd 0.471."),
    "FDA-14": ("R-04", "Same run: stated 0.95, realised input mass 0.7125 (n=4) and 0.9203125 (n=32), equal to 0.95-0.95/n."),
    "FDA-05": ("R-05", "Real evaluator score_universe and escrow _assess_pair on a synthetic world: one vacuous pair (A/B = 1.33e30 "
               "at the region edge) scored indistinguishable_hit, credit 1.0, escrow hit=True, for BOTH mutually exclusive "
               "truths T_up and T_down. Controls: honest refusal 0.5; informative pair hit; in-box-disagreeing pair miss; "
               "vacuous pair on a discoverable world -0.5."),
    "FDA-06": ("R-06", "Real analysis.world_credits/out_of_family/_capped on synthetic VALID records: with both truths out of family, "
               "discoverable credit capped 1.0->0.0 but spurious_correlate stays 1.0 (a supplied truth_in_searched_family=False "
               "on the spurious world is ignored); paired primary difference +1.0. Scope: the capping function lift_decision "
               "calls, not the full lift_decision pipeline."),
}
for f in reg["findings"]:
    if f["f1_id"] in results:
        rid, summary = results[f["f1_id"]]
        f["f10_evidence"] = "EXECUTED_REPRODUCED (" + rid + "; static class before: " + f["f10_evidence"] + ")"
        f["execution"] = {"reproduction": rid, "authorized": "owner, 2026-10-19 (R-03..R-06 only)",
                          "record": f"../repro/{rid}.json", "stdout": f"../repro/{rid}.out", "result": summary,
                          "negative_controls": "passed", "source_unchanged": True}
reg["counts"]["EXECUTED_REPRODUCED"] = sum(1 for f in reg["findings"] if "execution" in f)
reg["executions"] = {"authorized": ["R-03", "R-04", "R-05", "R-06"], "not_run": "all other R-xx (no authorization)",
                     "environment": "phyx .venv CPython 3.14.2, NumPy 2.5.2, SciPy 1.18.1, Pint 0.25.3; sitecustomize platform._wmi=None; "
                                    "-B, PYTHONDONTWRITEBYTECODE=1, BLAS threads 1, cwd scratch",
                     "source": "abed661f, tracked hash index bf233a73... identical before and after every run; no .pyc written in repo"}
json.dump(reg, open(path, "w", encoding="utf-8"), indent=2)
print("updated", reg["counts"])
