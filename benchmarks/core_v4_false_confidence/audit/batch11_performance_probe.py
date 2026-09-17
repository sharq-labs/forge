"""Does I-04 move any claim in the committed PERFORMANCE.json? Re-derives the verdicts only, no timings.

`benchmarks/core_v2_hybrid_uq/PERFORMANCE.json` is the one cheap committed record whose V2 claims turn on the
CORE-001 rule this batch changed. Its pooled half can be re-derived from the bytes it carries (chi-square
minimum, degrees of freedom, variance ratio); its LEVERAGE half cannot, because the record carries no
residuals and no Jacobian. So this probe re-runs the route for the same five parameterizations and prints the
claim and reasons -- and nothing else. It never writes PERFORMANCE.json: rewriting it here would replace that
record's measured wall times with this container's, which is environment drift and not evidence.

    python -X utf8 benchmarks/core_v4_false_confidence/audit/batch11_performance_probe.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "benchmarks" / "core_v2_hybrid_uq" / "audit"))

from common import b3_harness  # noqa: E402

from engcore.hybrid_uq import MultistartPolicy, route_uncertainty  # noqa: E402
from engcore.inference import CalibrationSpec, NoiseModel, calibrate  # noqa: E402


def main() -> int:
    H = b3_harness()
    bc = H.bc
    data = H.Data()
    cal = data.split.calibration
    n_cal = len(cal.observations)
    committed = json.loads((ROOT / "benchmarks" / "core_v2_hybrid_uq" / "PERFORMANCE.json").read_text(encoding="utf-8"))
    moved = 0
    for p in (2, 5, 10, 20, 41):
        param = bc.TabulatedKnotParameterization(tuple(np.linspace(0.0, 1.0, p)), source=f"v2-scaling-p{p}")
        spec = CalibrationSpec(
            parameters=bc.build_curve_parameter_set(param, lower=H.Q(H.BOUNDS[0], H.VOLT), upper=H.Q(H.BOUNDS[1], H.VOLT)),
            fixed={H.ctx.NOMINAL_CAPACITY: H.FIXED.nominal_capacity, H.ctx.INTERNAL_RESISTANCE: H.FIXED.internal_resistance,
                   H.ctx.COULOMBIC_EFFICIENCY: H.FIXED.coulombic_efficiency, H.ctx.CELL_TEMPERATURE: H.CELL_TEMPERATURE,
                   H.ctx.DISCHARGE_CURRENT: H.CONDITIONING_CURRENT},
            initial_point={n: H.Q(float(v), H.VOLT) for n, v in zip(param.names, H.initial_point(p))},
            noise_model=NoiseModel())
        forward = bc.curve_forward_evaluator(cal, fixed=H.FIXED, conditions=data.conditions, parameterization=param)
        fit = calibrate(spec, cal, forward, heldout_dataset_id=data.split.heldout_dataset_id,
                        max_evaluations=H.MAX_EVALUATIONS, seed=H.SEED)
        routed = route_uncertainty(calibration=fit, observations=cal, forward=forward, multistart=MultistartPolicy())
        d = routed.local_posterior.diagnostics
        was = committed["v2_measured"][str(p)]
        reasons = sorted(r.value for r in routed.local_posterior.reasons)
        same = routed.claim.value == was["claim"] and reasons == sorted(was["reasons_with_default_multistart"])
        moved += 0 if same else 1
        ratio = float(d.chi_square_minimum) / (n_cal - p)
        lev = float(d.leverage_weighted_chi_square)
        c1 = d.leverage_null_cumulants[0] if d.leverage_null_cumulants else float("nan")
        print(f"p={p:2}  committed {was['claim']:10} {sorted(was['reasons_with_default_multistart'])}\n"
              f"      now       {routed.claim.value:10} {reasons}   {'SAME' if same else 'MOVED'}\n"
              f"      pooled chi2 {d.chi_square_minimum:.6g} on {n_cal - p} dof, ratio {ratio:.4g}; "
              f"leverage {lev:.6g} against a null mean of {c1:.6g}, ratio {lev / c1:.4g}", flush=True)
    print(f"\n{moved} of 5 claims moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
