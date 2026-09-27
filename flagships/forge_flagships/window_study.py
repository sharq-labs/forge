"""BIG 14 study on flagship A: why the coupling-window differences grow (pre-registered diagnosis of BIG 13 criterion 1).

Runs the fresh-cell coupled day at the pre-registered window sizes, records the three compared quantities, the dense
PyBaMM heat series of each run, coupling iterations and wall time, and evaluates the pre-registered predictions in
``data/big14_a_window_study_preregistration.json``. It does not re-judge BIG 13 criterion 1.

    python -m forge_flagships.window_study --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

from . import battery_cooling as bc

HERE = os.path.dirname(os.path.abspath(__file__))
PREREGISTRATION = os.path.join(HERE, "data", "big14_a_window_study_preregistration.json")


def load_preregistration() -> tuple[dict, str]:
    with open(PREREGISTRATION, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def run_window(case_name: str, window_s: int, registry=None) -> dict:
    from engcore.system_runtime import SystemExecutor

    prereg, _ = load_preregistration()
    fl = bc.build_flagship(bc.CASES[case_name], registry, window_s=window_s, only_day=True)
    t0 = time.perf_counter()
    result = SystemExecutor(fl.context).run(fl.request)
    wall = time.perf_counter() - t0
    row = {"window_s": window_s, "status": result.status.value, "wall_s": round(wall, 1), "result_digest": result.digest, "values": {}}
    for name in prereg["quantities"]:
        observed = result.observable(name)
        row["values"][name] = float(observed.value.value.magnitude) if observed.availability.value == "available" else None
    table = fl.store.tables.get("day-fresh")
    if table is not None:
        discharge = [r for r in table.rows if r["current_A"] > 0]
        dense = [h for r in discharge for h in r["series"]["heat_W"]]
        row["max_dense_heat_in_discharge_W"] = max(dense) if dense else None
        row["windows"] = len(table.rows)
    return row


def judge(rows: list[dict]) -> dict:
    prereg, _ = load_preregistration()
    ok = [r for r in rows if r["status"] == "succeeded"]
    out: dict = {"all_succeeded": len(ok) == len(rows), "quantities": {}}
    ws = [r["window_s"] for r in ok]
    for name in prereg["quantities"]:
        v = [r["values"][name] for r in ok]
        diffs = [abs(b - a) for a, b in zip(v, v[1:])]
        entry = {"values": dict(zip(map(str, ws), v)), "successive_differences": dict(zip([f"{a}->{b}" for a, b in zip(ws, ws[1:])], diffs))}
        if len(diffs) >= 3:
            last, prev = diffs[-1], diffs[-2]
            entry["P1_last_below_max_earlier"] = last < max(diffs[:-1])
            entry["P1_ratio_last_two"] = (prev / last) if last > 0 else None
            entry["P1_met"] = entry["P1_last_below_max_earlier"] and entry["P1_ratio_last_two"] is not None and entry["P1_ratio_last_two"] >= 1.5
        out["quantities"][name] = entry
    finest = ok[-1] if ok else None
    if finest is not None and finest.get("max_dense_heat_in_discharge_W") is not None:
        target = finest["max_dense_heat_in_discharge_W"]
        gaps = [target - r["values"]["peak_heat_fresh"] for r in ok]
        out["P2"] = {"target_max_dense_heat_W": target, "gaps": dict(zip(map(str, ws), gaps)),
                     "met": all(g >= 0 for g in gaps) and all(a > b for a, b in zip(gaps, gaps[1:]))}
    p1 = all(q.get("P1_met") for q in out["quantities"].values())
    out["H1_supported"] = bool(out["all_succeeded"] and p1 and out.get("P2", {}).get("met"))
    out["H0_indicated"] = not out["H1_supported"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    prereg, prereg_sha = load_preregistration()
    os.makedirs(a.out, exist_ok=True)
    registry = bc.make_registry()
    rows = []
    for w in prereg["runs"]["windows_s"]:
        row = run_window(prereg["runs"]["case"], w, registry)
        rows.append(row)
        with open(os.path.join(a.out, "runs.jsonl"), "ab") as fh:
            fh.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
        print(f"window {w} s: {row['status']} in {row['wall_s']} s", flush=True)
    verdict = {"preregistration": os.path.basename(PREREGISTRATION), "preregistration_sha256": prereg_sha,
               "classification": prereg["classification"], "rows": rows, "judgement": judge(rows)}
    with open(os.path.join(a.out, "study.json"), "wb") as fh:
        fh.write((json.dumps(verdict, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print("H1 supported" if verdict["judgement"]["H1_supported"] else "H0 indicated (H1 not supported)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
