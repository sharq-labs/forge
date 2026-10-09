"""PySINDy runner (runs INSIDE the provider environment).  JSON request on stdin, JSON result on stdout.

The provider owns the algorithm (sparse regression); this runner only reports what it fitted.  It makes no claim about
the fitted equations: FORGE turns them into PROPOSED hypotheses and nothing more.
"""

import json
import sys


def main() -> int:
    req = json.load(sys.stdin)
    import numpy as np
    import pysindy as ps

    t = np.asarray(req["t"], dtype=float)
    x = np.asarray(req["x"], dtype=float)
    names = list(req["feature_names"])
    model = ps.SINDy(optimizer=ps.STLSQ(threshold=float(req.get("threshold", 0.1))),
                     feature_library=ps.PolynomialLibrary(degree=int(req.get("poly_degree", 2))))
    model.fit(x, t=t, feature_names=names)
    out = {"provider": "pysindy", "provider_version": ps.__version__, "terms": list(model.get_feature_names()),
           "targets": [f"d{n}/dt" for n in names], "coefficients": [[float(c) for c in row] for row in model.coefficients()],
           "training_score_r2": float(model.score(x, t=t)),
           "settings": {"threshold": float(req.get("threshold", 0.1)), "poly_degree": int(req.get("poly_degree", 2))}}
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
