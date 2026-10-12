"""BoTorch runner (runs INSIDE the provider environment): fit a GP to the observations and suggest one point by
maximising log expected improvement.  The acquisition value is BoTorch's number, not FORGE's utility."""

import json
import sys


def main() -> int:
    req = json.load(sys.stdin)
    import botorch
    import torch
    from botorch.acquisition import LogExpectedImprovement
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import SingleTaskGP
    from botorch.optim import optimize_acqf
    from gpytorch.mlls import ExactMarginalLogLikelihood

    torch.manual_seed(int(req.get("seed", 0)))
    X = torch.tensor(req["X"], dtype=torch.double)
    Y = torch.tensor(req["Y"], dtype=torch.double).reshape(-1, 1)
    bounds = torch.tensor(req["bounds"], dtype=torch.double)
    gp = SingleTaskGP((X - bounds[0]) / (bounds[1] - bounds[0]), Y)
    fit_gpytorch_mll(ExactMarginalLogLikelihood(gp.likelihood, gp))
    acq = LogExpectedImprovement(gp, best_f=Y.max())
    unit = torch.stack([torch.zeros(X.shape[1], dtype=torch.double), torch.ones(X.shape[1], dtype=torch.double)])
    cand, value = optimize_acqf(acq, bounds=unit, q=1, num_restarts=4, raw_samples=64)
    point = (bounds[0] + cand[0] * (bounds[1] - bounds[0])).tolist()
    json.dump({"provider": "botorch", "provider_version": botorch.__version__, "point": point,
               "acquisition": "log_expected_improvement", "acquisition_value": float(value)}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
