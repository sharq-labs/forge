"""Opt-in live smoke run of the discovery provider adapters (outside the test tiers: it needs provider environments).

    python -m tools.discovery_provider_smoke --discovery-cmd '["micromamba","run","-n","discovery","python","-I"]' \\
        --dakota-cmd '["micromamba","run","-n","dakota","python","-I"]'

Each provider runs in its own environment; FORGE converts the output into proposals/suggestions only.  Prints one JSON
record per provider with what ran and what FORGE made of it.  Executing is not qualifying.
"""

from __future__ import annotations

import argparse
import json
import math

from engcore.claims.discovery_providers import botorch_suggestion, dakota_output, run_provider, sindy_hypotheses
from engcore.sria.decision import HypothesisStatus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--discovery-cmd", required=True, help="JSON list: the PySINDy/BoTorch environment's interpreter")
    ap.add_argument("--dakota-cmd", required=True, help="JSON list: the Dakota environment's interpreter")
    args = ap.parse_args(argv)
    disc, dak = json.loads(args.discovery_cmd), json.loads(args.dakota_cmd)
    out, ok = [], True
    t = [i * 0.1 for i in range(100)]
    run = run_provider(disc, "sindy_runner.py", {"t": t, "x": [[2.0 * math.exp(-0.5 * ti)] for ti in t], "feature_names": ["u"],
                                                 "threshold": 0.05})
    (h,) = sindy_hypotheses(run, units={"u": "m"}, time_unit="s", prefix="smoke", condition_ref="cond:decay")
    good = abs(h.parameters[0].value + 0.5) < 0.01 and h.status is HypothesisStatus.PROPOSED
    ok &= good
    out.append({"provider": "pysindy", "version": run.provider_version, "run": run.digest, "statement": h.statement,
                "status": h.status.value, "recovered_rate_within_0.01_of_-0.5": good})
    bo = run_provider(disc, "botorch_runner.py", {"X": [[0.1, 0.2], [0.5, 0.5], [0.9, 0.1], [0.3, 0.8]], "Y": [0.2, 0.9, 0.4, 0.6],
                                                  "bounds": [[0, 0], [1, 1]]})
    s = botorch_suggestion(bo, names=("x1", "x2"), target_ref="design:toy")
    inside = all(0.0 <= v <= 1.0 for v in s.point.values())
    ok &= inside
    out.append({"provider": "botorch", "version": bo.provider_version, "run": bo.digest, "suggestion": dict(s.point),
                "acquisition_value_engine_own": s.acquisition_value, "inside_bounds": inside})
    dk = run_provider(dak, "dakota_runner.py", {"samples": 20, "seed": 1})
    d = dakota_output(dk)
    std_ok = bool(dk.output.get("moments")) and dk.output["moments"]["std_dev"] > 0
    ok &= std_ok
    out.append({"provider": "dakota", "version": dk.provider_version, "run": dk.digest, "output": d, "moments_present": std_ok})
    print(json.dumps(out, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
