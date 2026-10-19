"""R-06: FDA-06 -- the no-strong-baseline cap of the real Genesis-lite analysis on synthetic run records.

Synthetic records only (world set ('anonymous','synthetic-0',0)); no pilot or formal record is read.
Candidate passes the law on BOTH the discoverable and the spurious_correlate world; the comparator passes neither.
Both worlds are declared out of the searched family (the spurious flag is supplied too, to show it has no channel).
"""
import benchmarks.genesis_lite.analysis as an
from engcore.blindfold.roles import DEFAULT_CREDIT

print("analysis:", an.__file__)
WS = ("anonymous", "synthetic-0", 0)


def record(arm, outcomes, discoverable_in_family, spurious_in_family):
    universes = []
    for kind in an.KINDS:
        outcome = outcomes[kind]
        u = {"kind": kind, "outcome": outcome, "credit": float(DEFAULT_CREDIT[kind].get(outcome, 0.0))}
        if kind == "discoverable":
            u["truth_in_searched_family"] = discoverable_in_family
        if kind == "spurious_correlate":
            u["truth_in_searched_family"] = spurious_in_family
        universes.append(u)
    return {"status": "VALID", "arm": arm, "presentation": WS[0], "campaign_id": WS[1], "seed": WS[2],
            "universes": universes}


controls = {"no_solution": "no_law", "insufficient_evidence": "insufficient_evidence",
            "indistinguishable": "insufficient_evidence", "confounded": "confounded"}
cand_out = {"discoverable": "law_pass", "spurious_correlate": "law_pass", **controls}
base_out = {"discoverable": "no_law", "spurious_correlate": "no_law", **controls}


def evaluate(disc_in_family, spur_in_family, label):
    rows = [record("cand", cand_out, disc_in_family, spur_in_family),
            record("ref", base_out, disc_in_family, spur_in_family)]
    credits = an.world_credits(rows)
    off = an.out_of_family(rows)
    capped = an._capped(credits["cand"][WS], credits["ref"][WS], WS, set(), off)
    diff = sum(capped.values()) - sum(credits["ref"][WS].values())
    print(f"{label}: off_family_flag={off[WS]} raw(disc,spur)=({credits['cand'][WS]['discoverable']},"
          f"{credits['cand'][WS]['spurious_correlate']}) capped(disc,spur)=({capped['discoverable']},"
          f"{capped['spurious_correlate']}) paired_primary_difference={diff}")
    return capped, diff


trig, d_trig = evaluate(False, False, "TRIGGER both out of family")
ctrl, d_ctrl = evaluate(True, False, "CONTROL discoverable in family")

reproduced = trig["discoverable"] == 0.0 and trig["spurious_correlate"] == 1.0 and d_trig == 1.0
control_ok = ctrl["discoverable"] == 1.0  # the cap is lifted only when the discoverable truth is in family
print("VERDICT FDA-06:", "REPRODUCED" if reproduced else "NOT_REPRODUCED/CHECK")
print("CONTROL_OK:", control_ok)
