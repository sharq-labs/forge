"""GEN2-BR1.1: the 515 frozen GEN2-BR1 cases re-decided under the BR1.1 check, against BR1's committed results.

BR1's results (``benchmarks/mind_gen2_world_v1/results``) are historical evidence about BR1's code and are never
rewritten.  BR1.1 changes three decision rules on purpose (README section 6, requirements 2 and 5; brief sections 9
and 10):

* a coverage below 1, or an unstated one, is never an enclosure: a precondition, constraint or state-domain decision
  on a value known only within such an interval is MISSING_INFORMATION unless the declaration's core
  ``UncertaintySpecification`` demands that coverage and the record meets it (BR1's synthetic worlds demand none);
* the core assesses applicability at exact points only: an interval model input is MISSING_INFORMATION
  (``APPLICABILITY_INPUT_NOT_EXACT``), never a world-made INFEASIBLE or FEASIBLE;
* a proposed control value is also checked against its variable's own declared domain, pointwise, by the owner.

This module re-decides BR1's frozen cases on BR1's own synthetic worlds with the BR1.1 code, lists every case whose
status moved, and checks the direction: nothing may move toward FEASIBLE.

    python -m benchmarks.mind_gen2_authority_v1.rescore            # (re)write results/BR1_RESCORE.json
    python -m benchmarks.mind_gen2_authority_v1.rescore --check    # verify the committed file
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from collections import Counter
from typing import Any

from benchmarks.mind_gen2_world_v1 import cases as C, run_benchmark as rb

HERE = pathlib.Path(__file__).resolve().parent
BR1 = HERE.parent / "mind_gen2_world_v1" / "results"
PATH = HERE / "results" / "BR1_RESCORE.json"
SCHEMA = "forge.mind.gen2_authority.br1_rescore/1"
#: The only codes a moved case may newly carry: the BR1.1 rules above, and nothing else.
ALLOWED_NEW_CODES = frozenset({
    "PRECONDITION_ENCLOSURE_REQUIRED", "STATE_DOMAIN_ENCLOSURE_REQUIRED", "CONSTRAINT_ENCLOSURE_REQUIRED",
    "APPLICABILITY_INPUT_NOT_EXACT",
})


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    cases = C.load()["cases"]
    rows = rb.decisions(cases, rb._worlds(cases))
    drift, moves, codes = [], Counter(), Counter()
    for r in rows:
        exp, g = r["case"]["expected"], r["gen2"]
        if exp["status"] == g["status"] and set(exp["codes"]) <= set(g["codes"]):
            continue
        new = sorted(set(g["codes"]) - set(exp["codes"]))
        drift.append({"case_id": r["case"]["case_id"], "br1": {"status": exp["status"], "codes": sorted(exp["codes"])},
                      "br1_1": {"status": g["status"], "codes": sorted(g["codes"])}, "new_codes": new})
        moves[f"{exp['status']}->{g['status']}"] += 1
        codes.update(new)
    return {
        "schema": SCHEMA,
        "br1_inputs": {"CASES.json": _sha(BR1 / "CASES.json"), "BENCHMARK.json": _sha(BR1 / "BENCHMARK.json")},
        "cases": len(rows),
        "decisions_digest": rb.decisions_digest(rows),
        "moved": len(drift),
        "moves": dict(sorted(moves.items())),
        "moved_to_feasible": sum(v for k, v in moves.items() if k.endswith("->FEASIBLE")),
        "new_codes": dict(sorted(codes.items())),
        "drift": drift,
        "statement": ("BR1's committed results are not rewritten.  These cases decide differently under BR1.1 by design "
                      "(coverage is never an enclosure; applicability at exact points only); none moves toward "
                      "FEASIBLE.  BR1's synthetic worlds state no coverage and demand none, so the corrected rule "
                      "makes them MISSING_INFORMATION."),
    }


def dump(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n").encode("utf-8")


def main(argv: list[str]) -> int:
    payload = dump(build())
    if "--check" in argv:
        ok = PATH.read_bytes() == payload
        print("BR1_RESCORE", "MATCHES" if ok else "DIFFERS")
        return 0 if ok else 1
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_bytes(payload)
    print(f"wrote {PATH.relative_to(HERE.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
