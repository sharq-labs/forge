"""Part 19: wheel/source parity for BOTH frozen surfaces, and an isolated-wheel smoke of the V2 route.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/wheel_v2.py <workdir on D:>

Builds the wheel from ``git archive HEAD`` and installs it into a bare target. The probe then runs under
``python -S -E``, which never registers the checkout's editable hook, and asserts where engcore came from before
doing anything else. It records:

* the V1 and V2 frozen digests and counts, from the wheel, against the source;
* an end-to-end routed calculation run from the wheel: calibrate, local route, identifiability, predictive, and a
  refused case.

Writes benchmarks/core_v2_hybrid_uq/WHEEL_V2.json. The V1 script's output file is not touched.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import sysconfig

from common import ROOT, dump, load

V1 = load("_wheel_parity_v1", ROOT / "benchmarks" / "core_api_stability" / "audit" / "wheel_parity.py")
PY = V1.PY

PROBE = r'''
import json, pathlib, sys
TARGET = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(TARGET))
for extra in sys.argv[3:]:
    if extra not in sys.path:
        sys.path.append(extra)
import engcore
where = pathlib.Path(engcore.__file__).resolve()
if not str(where).startswith(str(TARGET.resolve())):
    print(json.dumps({"error": "engcore came from " + str(where)}))
    raise SystemExit(2)
import numpy as np
from engcore import api_snapshot as A
from engcore.hybrid_uq import MultistartPolicy, RouteDecision, route_uncertainty, linearized_predictive_uq
from engcore.inference import (CalibrationParameterSet, CalibrationSpec, GaussianObservation, NoiseModel, ObservationSet,
                               ParameterBounds, ParameterIdentity, calibrate)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

v2 = A.build(modules=A.V2_CANONICAL_MODULES)
model = ModelReference("wheel-smoke.model", "1")
params = CalibrationParameterSet(tuple(ParameterIdentity(name=n, unit="dimensionless", model=model,
    bounds=ParameterBounds(Quantity(-10.0, "dimensionless"), Quantity(10.0, "dimensionless"))) for n in ("a", "b")))
x = np.linspace(0.0, 1.0, 12)
y = 1.0 + 2.0 * x + 0.05 * np.sin(17.0 * x)

def smoke(model_fn, label):
    obs = ObservationSet(tuple(GaussianObservation(condition_id=f"x{i}", observable_name="y", value=Quantity(float(v), "dimensionless"),
                         sigma=Quantity(0.05, "dimensionless"), source_ref=f"wheel:{i}") for i, v in enumerate(y)), dataset_id=f"wheel.{label}")
    forward = lambda t: [Quantity(float(v), "dimensionless") for v in model_fn(np.asarray(t), x)]
    spec = CalibrationSpec(parameters=params, fixed={}, initial_point={"a": Quantity(0.5, "dimensionless"), "b": Quantity(0.5, "dimensionless")}, noise_model=NoiseModel())
    fit = calibrate(spec, obs, forward, heldout_dataset_id=f"wheel.{label}.heldout")
    # The canonical multistart: since audit HUQ-01 a search below max(6, 2p + 2) starts cannot support a claim, and
    # this smoke asserts a SUPPORTED affine route. It asked for 3 starts when WHEEL_V2.json was first written.
    routed = route_uncertainty(calibration=fit, observations=obs, forward=forward, multistart=MultistartPolicy())
    out = {"decision": routed.decision.value, "claim": routed.claim.value, "digest": routed.digest}
    if routed.decision is RouteDecision.LOCAL_GAUSSIAN:
        (p,) = linearized_predictive_uq(routed.local_posterior, lambda t: [Quantity(float(t[0] + 0.5 * t[1]), "dimensionless")],
                                        [PredictiveObservableSpec("y@0.5", "dimensionless", Quantity(0.05, "dimensionless"))])
        out.update({"identifiability": routed.identifiability.status.value, "parameter_sd": p.parameter_standard_uncertainty,
                    "total_sd": p.total_standard_uncertainty, "sources": list(p.sources)})
    return out

print(json.dumps({
    "engcore_file": str(where),
    "v1_frozen_digest": A.frozen_digest(), "v1_frozen_count": A.frozen_only()["symbol_count"],
    "v2_frozen_digest": A.frozen_digest(v2), "v2_frozen_count": A.frozen_only(v2)["symbol_count"],
    "smoke_affine": smoke(lambda t, x: t[0] + t[1] * x, "affine"),
    "smoke_singular": smoke(lambda t, x: (t[0] + t[1]) * x, "singular"),
}))
'''


def main():
    work = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "D:/v2_wheel")
    work.mkdir(parents=True, exist_ok=True)
    install, shipped = V1.build_and_install(work)
    probe = work / "probe_v2.py"
    probe.write_bytes(PROBE.encode("utf-8"))
    site = [sysconfig.get_paths()["purelib"], str(ROOT / ".venv" / "Lib" / "site-packages")]
    done = subprocess.run([PY, "-S", "-E", "-X", "utf8", str(probe), str(install), "--", *site], capture_output=True, text=True, cwd=str(work))
    if done.returncode != 0:
        print(done.stdout[-3000:], done.stderr[-3000:])
        raise SystemExit(f"wheel probe failed with {done.returncode}")
    wheel = json.loads(done.stdout.strip().splitlines()[-1])
    source = json.loads(subprocess.run(
        [PY, "-X", "utf8", "-c", "import json;from engcore import api_snapshot as A;v2=A.build(modules=A.V2_CANONICAL_MODULES);"
         "print(json.dumps({'v1_frozen_digest':A.frozen_digest(),'v1_frozen_count':A.frozen_only()['symbol_count'],"
         "'v2_frozen_digest':A.frozen_digest(v2),'v2_frozen_count':A.frozen_only(v2)['symbol_count']}))"],
        capture_output=True, text=True, check=True, cwd=str(ROOT)).stdout)
    hybrid_files = sorted(p for p in shipped if p.startswith("engcore/hybrid_uq/"))
    result = {
        "shipped_files": len(shipped), "hybrid_uq_files_in_wheel": hybrid_files, "engcore_imported_from": wheel["engcore_file"],
        "source": source, "wheel": {k: wheel[k] for k in source},
        "v1_frozen_api_parity": "MATCH" if source["v1_frozen_digest"] == wheel["v1_frozen_digest"] else "MISMATCH",
        "v2_frozen_api_parity": "MATCH" if source["v2_frozen_digest"] == wheel["v2_frozen_digest"] else "MISMATCH",
        "isolated_wheel_smoke": {"affine": wheel["smoke_affine"], "singular": wheel["smoke_singular"],
                                 "passed": wheel["smoke_affine"]["decision"] == "LOCAL_GAUSSIAN" and wheel["smoke_affine"]["claim"] == "SUPPORTED"
                                 and wheel["smoke_singular"]["decision"] == "REFUSED"},
    }
    print(json.dumps({k: result[k] for k in ("v1_frozen_api_parity", "v2_frozen_api_parity", "isolated_wheel_smoke", "engcore_imported_from")}, indent=1))
    dump("WHEEL_V2.json", result)


if __name__ == "__main__":
    main()
