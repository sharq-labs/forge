"""GEN2-BR1.1: the 515 frozen GEN2-BR1 cases re-decided under the BR1.1 check, against what BR1 actually decided.

BR1's results (``benchmarks/mind_gen2_world_v1/results``) are historical evidence about BR1's code and are never
rewritten.  BR1's own per-case decisions are ``results/BR1_DECISIONS.json``, exported by running BR1's code at its
commit and accepted only because they reproduce BR1's committed ``decisions_digest`` (``br1_decisions.py``).  BR1.1
changes three decision rules on purpose (README section 3):

* no current value of a world decides a containment: no core uncertainty record is an enclosure and no owner states a
  decision-coverage policy, so a precondition, constraint or state-domain decision on a current value is
  MISSING_INFORMATION (a declared set point included: it is exact only as an action's fixed condition);
* the core assesses applicability at exact points only: a non-exact model input is MISSING_INFORMATION
  (``APPLICABILITY_INPUT_NOT_EXACT``), never a world-made INFEASIBLE or FEASIBLE;
* a proposed control value is also checked against its variable's own declared domain, pointwise, by the owner.

This module re-decides BR1's frozen cases on BR1's own synthetic worlds with the BR1.1 code and lists EVERY case whose
status or reason codes differ from BR1's actual decision.  It refuses to write a re-score in which a case moves toward
FEASIBLE, moves to any status other than MISSING_INFORMATION, gains a code outside ``ALLOWED_NEW_CODES`` or loses one
outside ``ALLOWED_LOST_CODES`` (the codes the rules above remove).

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
BR1_DECISIONS = HERE / "results" / "BR1_DECISIONS.json"
PATH = HERE / "results" / "BR1_RESCORE.json"
SCHEMA = "forge.mind.gen2_authority.br1_rescore/2"
#: The only codes a case may newly carry: the BR1.1 rules above, and nothing else.
ALLOWED_NEW_CODES = frozenset({
    "PRECONDITION_ENCLOSURE_REQUIRED", "PRECONDITION_UNCERTAINTY_UNKNOWN", "STATE_DOMAIN_ENCLOSURE_REQUIRED",
    "STATE_DOMAIN_UNDECIDABLE", "CONSTRAINT_ENCLOSURE_REQUIRED", "CONSTRAINT_UNDECIDABLE",
    "APPLICABILITY_INPUT_NOT_EXACT",
})
#: The only codes a case may lose: definite decisions BR1 took on a current value (an interval's edges deciding a
#: precondition, the state domain or a model's validity domain), and decisions BR1 took on a value the proposer may
#: not set (a constraint or an applicability input read from a non-control assignment; round 2, R2-A4).
ALLOWED_LOST_CODES = frozenset({
    "PRECONDITION_VIOLATED", "PRECONDITION_UNDECIDED", "STATE_OUTSIDE_DECLARED_DOMAIN", "STATE_DOMAIN_UNDECIDED",
    "INTERVAL_OUTSIDE_VALIDATED_DOMAIN", "CONSTRAINT_VIOLATED", "OUTSIDE_VALIDATED_DOMAIN",
})
#: A definite constraint or validity verdict may be lost only for one of the two BR1.1 causes, stated by the case's
#: own BR1.1 codes: the value it rested on was one the proposer may not set (a role refusal), or a current value of
#: the world (the matching undecidable code).
CONDITIONAL_LOST_CODES = {
    "CONSTRAINT_VIOLATED": frozenset({"CONSTRAINT_ENCLOSURE_REQUIRED", "CONSTRAINT_UNDECIDABLE"}),
    "OUTSIDE_VALIDATED_DOMAIN": frozenset({"APPLICABILITY_INPUT_NOT_EXACT"}),
}
ROLE_REFUSALS = frozenset({"FIXED_CONDITION_CHANGED", "STATE_NOT_DIRECTLY_SETTABLE", "PROTOCOL_CONDITION_NOT_SELECTABLE",
                           "CONTROL_NOT_OFFERED_BY_ACTION", "ROLE_NOT_CONTROLLABLE"})


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    exported = json.loads(BR1_DECISIONS.read_bytes())
    committed = json.loads((BR1 / "BENCHMARK.json").read_bytes())
    if exported["decisions_digest"] != committed["decisions_digest"]:
        raise ValueError("BR1_DECISIONS.json is not BR1's committed decisions")
    br1 = exported["decisions"]
    cases = C.load()["cases"]
    rows = rb.decisions(cases, rb._worlds(cases))
    changed, moves, new_codes, lost_codes = [], Counter(), Counter(), Counter()
    for r in rows:
        cid, g = r["case"]["case_id"], r["gen2"]
        b = br1[cid]
        now = {"status": g["status"], "codes": sorted(g["codes"])}
        if b == now:
            continue
        new, lost = sorted(set(now["codes"]) - set(b["codes"])), sorted(set(b["codes"]) - set(now["codes"]))
        changed.append({"case_id": cid, "br1": b, "br1_1": now, "new_codes": new, "lost_codes": lost,
                        "oracle_expected": {"status": r["case"]["expected"]["status"],
                                            "codes": sorted(r["case"]["expected"]["codes"])}})
        moves[f"{b['status']}->{now['status']}"] += 1
        new_codes.update(new)
        lost_codes.update(lost)
    to_feasible = sum(v for k, v in moves.items() if k.endswith("->FEASIBLE") and not k.startswith("FEASIBLE->"))
    unexpected = sorted(set(new_codes) - ALLOWED_NEW_CODES)
    unexpected_lost = sorted(set(lost_codes) - ALLOWED_LOST_CODES) + sorted(
        f"{c['case_id']}:{code}" for c in changed for code in c["lost_codes"] if code in CONDITIONAL_LOST_CODES
        and not set(c["br1_1"]["codes"]) & (ROLE_REFUSALS | CONDITIONAL_LOST_CODES[code]))
    other_moves = sorted(k for k in moves if k.split("->")[0] != k.split("->")[1] and
                         not k.endswith("->MISSING_INFORMATION"))
    if to_feasible or unexpected or unexpected_lost or other_moves:
        raise ValueError(f"re-score refused: {to_feasible} case(s) toward FEASIBLE, unexpected new codes {unexpected}, "
                         f"unexpected lost codes {unexpected_lost}, status moves other than to MISSING_INFORMATION "
                         f"{other_moves}")
    return {
        "schema": SCHEMA,
        "br1_inputs": {"CASES.json": _sha(BR1 / "CASES.json"), "BENCHMARK.json": _sha(BR1 / "BENCHMARK.json"),
                       "BR1_DECISIONS.json": _sha(BR1_DECISIONS)},
        "cases": len(rows),
        "decisions_digest": rb.decisions_digest(rows),
        "changed": len(changed),
        "status_changed": sum(1 for c in changed if c["br1"]["status"] != c["br1_1"]["status"]),
        "codes_only_changed": sum(1 for c in changed if c["br1"]["status"] == c["br1_1"]["status"]),
        "moves": dict(sorted(moves.items())),
        "moved_to_feasible": to_feasible,
        "new_codes": dict(sorted(new_codes.items())),
        "lost_codes": dict(sorted(lost_codes.items())),
        "allowed_new_codes": sorted(ALLOWED_NEW_CODES),
        "allowed_lost_codes": sorted(ALLOWED_LOST_CODES),
        "conditional_lost_codes": {k: sorted(v | ROLE_REFUSALS) for k, v in sorted(CONDITIONAL_LOST_CODES.items())},
        "changes": changed,
        "statement": ("BR1's committed results are not rewritten.  Every case whose status or codes differ from BR1's "
                      "actual decision is listed: they decide differently under BR1.1 by design (no current value "
                      "decides a containment; applicability at exact points only); none moves toward FEASIBLE and no "
                      "case gains a code outside the allowed set."),
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
