"""Mutation test of the v2 leakage firewall: every planted leak must be caught, no benign longer number may trigger.

    python -m benchmarks.battery_rediscovery_v2.mutation --phase pre_run     # writes MUTATION_REPORT_pre_run.json

v1's mutation forms are reused unchanged (``benchmarks.battery_rediscovery_v1.mutation``: the reported form, a decimal
equivalent, a signed form, scientific notation, value plus unit, an SI-prefixed unit, a prose label, a result label, an
assignment and the full-precision transcription; benign controls embed the value inside longer numbers and identifiers).
The carriers are v2 candidate material (the arms module and a pack file), copied to a scratch directory and mutated
there; the candidate tree is never touched.  Text mutations plant every verdict token and a sample of identity tokens.
Measurement-array mutations replace one recorded value of a pack copy (and, as a control, leave a copy unaltered): the
provenance check must flag every altered copy and no unaltered one.  The unmutated carriers must be clean.

Protected values: v1's synthetic values plus the historical 1RC estimates and errors that v0/v1 revealed (the LG HG2
pulse data of Q2 are the same windows those estimates were made on).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
from typing import Any, Sequence

from benchmarks.battery_rediscovery_v1.mutation import SYNTHETIC, _insert, benign_forms, historical_values, leak_forms

from . import leakage as lk
from .candidate.common import write_json

HERE = pathlib.Path(__file__).resolve().parent
CARRIERS = (HERE / "candidate" / "arms.py", HERE / "candidate" / "pack" / "Q2.json")
TEXT_SAMPLES = ["B0039", "BatteryAgingARC_25-44", "41d4a6977e3f", "EVALUATION.md", "battery_1rc_identifiability",
                "CALIBRATION.json"]
ARRAY_CASES = (("Q1", "calibration", "voltage_V"), ("Q2", "calibration", "t_s"), ("Q1", "calibration", "temperature_C"))


def protected_values() -> list[lk.Protected]:
    return list(SYNTHETIC) + historical_values()


def run(values: Sequence[lk.Protected], phase: str) -> dict[str, Any]:
    cases, failures = [], []
    clean = lk.numeric_findings(CARRIERS, values) + lk.text_findings(CARRIERS)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        for carrier in CARRIERS:
            for v in values:
                for kind, form, want in ([(k, f, True) for k, f in leak_forms(v).items()] +
                                         [(k, f, False) for k, f in benign_forms(v).items()]):
                    path = tmp / carrier.name
                    path.write_bytes(_insert(carrier, form).encode())
                    caught = bool([h for f_ in lk.numeric_findings([path], [v]) for h in f_["hits"]])
                    case = {"carrier": carrier.name, "protected": v.name, "kind": kind, "text": form,
                            "expected": "DETECT" if want else "NO_HIT", "caught": caught, "ok": caught == want}
                    cases.append(case)
                    if not case["ok"]:
                        failures.append(case)
            for token in lk.VERDICT + TEXT_SAMPLES:
                path = tmp / carrier.name
                path.write_bytes(_insert(carrier, f"result label: {token}").encode())
                caught = token in (lk.text_findings([path]) or [{"tokens": []}])[0]["tokens"]
                case = {"carrier": carrier.name, "protected": token, "kind": "text_token", "text": token,
                        "expected": "DETECT", "caught": caught, "ok": caught}
                cases.append(case)
                if not caught:
                    failures.append(case)
        for k, (pid, set_name, key) in enumerate(ARRAY_CASES):
            for v in list(values[:2]) + [None]:
                d = tmp / f"pack_{k}_{'none' if v is None else v.name}"
                shutil.copytree(lk.PACK, d)
                if v is not None:
                    spec = json.loads((d / f"{pid}.json").read_bytes())
                    spec["sets"][set_name][0]["columns"][key][3] = float(lk.round_sig(abs(v.value), 3))
                    (d / f"{pid}.json").write_bytes((json.dumps(spec, sort_keys=True, indent=1) + "\n").encode())
                caught = bool(lk.provenance_findings(d))
                want = v is not None
                case = {"carrier": f"pack:{pid}/{key}", "protected": None if v is None else v.name,
                        "kind": "measurement_array" if want else "measurement_array_unaltered",
                        "text": None if v is None else str(lk.round_sig(abs(v.value), 3)),
                        "expected": "DETECT" if want else "NO_HIT", "caught": caught, "ok": caught == want}
                cases.append(case)
                if not case["ok"]:
                    failures.append(case)
    status = "PASS" if not failures and not clean else "FAIL"
    leaks = [c for c in cases if c["expected"] == "DETECT"]
    benign = [c for c in cases if c["expected"] == "NO_HIT"]
    return {"schema": "forge.battery_rediscovery_v2.leakage_mutation/1", "phase": phase,
            "scanner": f"{lk.SCANNER_ID}@{lk.SCANNER_VERSION}", "numeric_engine": lk.NUMERIC_ENGINE,
            "scanner_sha256": hashlib.sha256((HERE / "leakage.py").read_bytes()).hexdigest(),
            "status": status, "unmutated_carriers_clean": not clean, "carrier_findings": clean,
            "leak_mutations": len(leaks), "leaks_caught": sum(c["caught"] for c in leaks),
            "benign_controls": len(benign), "benign_triggered": sum(c["caught"] for c in benign),
            "failures": failures, "protected_values": [{"name": v.name, "value": str(v.value), "unit": v.unit}
                                                       for v in values], "cases": cases}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["pre_run", "post_seal"])
    ap.add_argument("--out", type=pathlib.Path, default=None)
    a = ap.parse_args(argv)
    rep = run(protected_values(), a.phase)
    out = a.out or (HERE / f"MUTATION_REPORT_{a.phase}.json")
    write_json(out, rep)
    print(rep["status"], f"leaks {rep['leaks_caught']}/{rep['leak_mutations']}",
          f"benign triggered {rep['benign_triggered']}/{rep['benign_controls']}", "carriers clean", rep["unmutated_carriers_clean"])
    for f in rep["failures"][:20]:
        print("  FAIL", f)
    for f in rep["carrier_findings"][:10]:
        print("  CARRIER", json.dumps(f)[:300])
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
