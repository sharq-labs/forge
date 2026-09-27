"""BIG 14 study on flagship A: the representative-day approximation error (pre-registered).

The published flagship ages the cell over 56 days while resolving 4 of them (14-day macro steps). This study reruns
the SAME flagship with every other setting unchanged and only ``macro_days`` varied, down to 1 (every day resolved),
and compares each run against that reference with the tolerances pre-registered in
``data/big14_a_representative_day_preregistration.json``.

A difference to a more resolved run of the same model is numerical verification of a time-scale approximation. It is
not validation and says nothing about the error against a real cell.

    python -m forge_flagships.representative_day_study --out <dir> [--cases normal hot] [--macro-days 14 7 4 2 1]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

from . import battery_cooling as bc

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_representative_day_preregistration.json")


def load_preregistration() -> tuple[dict, str]:
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def run_one(case_name: str, macro_days: int, registry=None) -> dict:
    """One full flagship run at ``macro_days``; the observed quantities of interest, or the refusal."""
    from engcore.system_runtime import SystemExecutor

    prereg, _ = load_preregistration()
    fl = bc.build_flagship(bc.CASES[case_name], registry, macro_days=macro_days)
    t0 = time.perf_counter()
    result = SystemExecutor(fl.context).run(fl.request)
    wall = time.perf_counter() - t0
    row = {"case": case_name, "macro_days": macro_days, "status": result.status.value, "wall_s": round(wall, 1),
           "result_digest": result.digest, "request_digest": fl.request.digest, "values": {}}
    wanted = [q["observable"] for q in prereg["quantities_of_interest"]] + ["resolved_days", "represented_days"]
    for name in wanted:
        observed = result.observable(name)
        if observed.availability.value == "available":
            q = observed.value.value
            row["values"][name] = {"magnitude": float(q.magnitude), "units": q.units}
        else:
            row["values"][name] = {"availability": observed.availability.value}
    return row


def judge(rows: list[dict]) -> dict:
    """Pre-registered comparison of every run against the macro_days = 1 reference of its case."""
    prereg, _ = load_preregistration()
    out: dict = {}
    for case in sorted({r["case"] for r in rows}):
        runs = {r["macro_days"]: r for r in rows if r["case"] == case}
        ref = runs.get(1)
        case_out = {"reference_available": ref is not None and ref["status"] == "succeeded", "quantities": {}}
        for spec in prereg["quantities_of_interest"]:
            name, tol = spec["observable"], spec["tolerance"]
            seq = {}
            for m, r in sorted(runs.items(), reverse=True):
                v = r["values"].get(name, {})
                seq[str(m)] = v.get("magnitude")
            entry = {"sequence": seq, "tolerance": tol}
            if case_out["reference_available"] and seq.get("14") is not None and seq.get("1") is not None:
                diff = seq["14"] - seq["1"]
                bound = tol["value"] * abs(seq["1"]) if tol["kind"] == "relative" else tol["value"]
                entry.update(difference_14_minus_1=diff, allowed=bound, met=abs(diff) <= bound)
                diffs = [abs(seq[str(m)] - seq["1"]) for m in (14, 7, 4, 2) if seq.get(str(m)) is not None]
                entry["differences_to_reference_by_macro_days"] = {str(m): seq[str(m)] - seq["1"] for m in (14, 7, 4, 2)
                                                                   if seq.get(str(m)) is not None}
                entry["monotone_toward_reference"] = all(a >= b for a, b in zip(diffs, diffs[1:]))
            else:
                entry.update(met=None, reason="reference or 14-day run missing or refused")
            case_out["quantities"][name] = entry
        case_out["met"] = all(q.get("met") is True for q in case_out["quantities"].values())
        out[case] = case_out
    out["met"] = all(v["met"] for k, v in out.items() if isinstance(v, dict) and "met" in v)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases", nargs="+", default=None)
    ap.add_argument("--macro-days", nargs="+", type=int, default=None)
    a = ap.parse_args(argv)
    prereg, prereg_sha = load_preregistration()
    cases = a.cases or prereg["runs"]["cases"]
    macros = a.macro_days or prereg["runs"]["macro_days"]
    os.makedirs(a.out, exist_ok=True)
    registry = bc.make_registry()
    rows = []
    for case in cases:
        for m in macros:
            row = run_one(case, m, registry)
            rows.append(row)
            with open(os.path.join(a.out, "runs.jsonl"), "ab") as fh:
                fh.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
            print(f"{case} macro_days={m}: {row['status']} in {row['wall_s']} s", flush=True)
    verdict = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": prereg_sha,
               "classification": prereg["classification"], "rows": rows, "judgement": judge(rows)}
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(verdict, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("met" if verdict["judgement"]["met"] else "NOT met", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
