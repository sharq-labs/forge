"""Explain, without moving any tolerance, why P9's held-out chi-square misses the declared 1e-6 agreement.

    python -X utf8 benchmarks/core_gap_hd_uq/audit/explain_p9.py

Recomputes the probe's predictive for every B3 model centred at the committed
B3 closed-form WLS estimate instead of the frozen calibrate estimate, and
records both, appending an "centre_explanation" block to BATTERY_B3_REFERENCE.json.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
R_spec = importlib.util.spec_from_file_location("_rr_explain", HERE / "run_review.py")
R = importlib.util.module_from_spec(R_spec)
sys.modules["_rr_explain"] = R
R_spec.loader.exec_module(R)
B = R._load("_rb_explain", HERE / "review_battery.py")


def main():
    H, results = B.load_b3(R)
    data = H.Data()
    path = R.ROUND / "BATTERY_B3_REFERENCE.json"
    reference = json.loads(path.read_text(encoding="utf-8"))
    explanation = {"question": "is the chi-square disagreement a route difference or a centre difference?",
                   "method": "same probe covariance and predictive Jacobian, predictive mean evaluated at the committed B3 WLS theta",
                   "models": {}}
    for model_id in H.SCORED_MODELS:
        committed = results["models"][model_id]
        param, problem, yh, sh = B.problem_for(R, H, data, model_id)
        wls_theta = np.asarray(committed["routes"]["DOMAIN_LINEAR_GAUSSIAN"]["posterior"]["mean_v"])
        cal_theta = B.estimates_of(results, model_id)
        probe = R.P.local_gaussian(problem, cal_theta)
        total = np.asarray(probe["predictive"]["total_sd"])
        at_wls = B.held_metrics(yh, problem.g(wls_theta), total, R.P.Z95)
        committed_chi = committed["routes"]["DOMAIN_LINEAR_GAUSSIAN"]["metrics"]["chi_square"]
        explanation["models"][model_id] = {
            "max_abs_centre_difference_v": float(np.max(np.abs(wls_theta - cal_theta))),
            "chi_square_relative_at_calibrate_centre": reference["models"][model_id]["vs_b3_domain_route"]["chi_square_relative"],
            "chi_square_relative_at_wls_centre": abs(at_wls["chi_square"] / committed_chi - 1),
        }
    reference["centre_explanation"] = explanation
    path.write_bytes((json.dumps(R.jsonable(reference), indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    for k, v in explanation["models"].items():
        print(k, "%.2e V" % v["max_abs_centre_difference_v"], "%.2e -> %.2e" % (v["chi_square_relative_at_calibrate_centre"], v["chi_square_relative_at_wls_centre"]))


if __name__ == "__main__":
    main()
