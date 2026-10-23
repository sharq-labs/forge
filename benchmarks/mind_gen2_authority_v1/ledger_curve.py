"""How admission and the check scale with a bound ledger's settled charges (``results/LEDGER_SIZE_CURVE.json``).

The world projects a bound ledger's whole history, so its cost grows with the charges settled.  Measured on the battery
fixture's ``simulate_pulse`` against its solver-call ledger with ``n`` extra settled charges (41 repeats: median, and
the fastest and slowest run, so the spread is visible).  Timings are host-dependent; the file names the code revision.

    python -m benchmarks.mind_gen2_authority_v1.ledger_curve           # writes the file
"""

from __future__ import annotations

import json
import pathlib
import platform
import statistics
import sys
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_authority_v1.run_benchmark import code_revision
from engcore.mind.world import FeasibleActionSpace, admit
from engcore.sria.decision import ActionFamily

PATH = pathlib.Path(__file__).resolve().parent / "results" / "LEDGER_SIZE_CURVE.json"
CHARGES = (0, 10, 100, 1000)


def curve(repeats: int = 41) -> dict:
    out = {}
    for n in CHARGES:
        o = ax.owned("battery")
        ledger = o.ledgers[next(k for k in o.ledgers if k.endswith(".solver"))]
        ledger.total_budget = ledger.total_budget + n * 0.001 + 10
        for i in range(n):
            ledger.settle(charge_id=f"c{i}", action_id="x", iteration=i, family=ActionFamily.EXPLORE, realized=0.001)
        authorities = o.authorities()
        space = FeasibleActionSpace.build(o.world)
        proposal = o.propose("simulate_pulse", *ax.base("battery")["simulate_pulse"])
        admission, check = [], []
        for _ in range(repeats):
            t0 = time.perf_counter()
            result = admit(space, proposal, authorities)
            admission.append((time.perf_counter() - t0) * 1e3)
        for _ in range(repeats):
            t0 = time.perf_counter()
            space.check(proposal)
            check.append((time.perf_counter() - t0) * 1e3)
        out[str(n)] = {"admission_p50_ms": round(statistics.median(admission), 2),
                       "admission_min_max_ms": [round(min(admission), 2), round(max(admission), 2)],
                       "check_p50_ms": round(statistics.median(check), 3),
                       "check_min_max_ms": [round(min(check), 3), round(max(check), 3)], "status": result.status.value}
    return {"schema": "forge.mind.gen2_authority.ledger_size_curve/3",
            "command": "python -m benchmarks.mind_gen2_authority_v1.ledger_curve",
            "code_revision": code_revision(),
            "host": {"platform": platform.platform(), "python": platform.python_version()},
            "repeats": repeats, "settled_charges": out}


def main(argv: list[str]) -> int:
    PATH.write_text(json.dumps(curve(), sort_keys=True, indent=1) + "\n")
    print(PATH.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
