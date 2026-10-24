"""Mutation test of the v1 leakage screen: every planted leak must be caught, no benign longer number may trigger.

    python -m benchmarks.battery_rediscovery_v1.mutation --phase pre_run     # writes MUTATION_REPORT_pre_run.json

Carriers are real candidate-visible material (a candidate code file and a pack file), copied to a scratch directory and
mutated there; the candidate tree is never touched.  For every protected value the planted forms are: the reported
integer/decimal form, a decimal equivalent, a signed form, scientific notation, value plus unit, an SI-prefixed unit
form where the unit has one, a prose label, a result label and the full-precision transcription.  Text mutations plant
every verdict token and a sample of identity tokens.  Benign controls embed the value inside longer numbers and
identifiers ("760.006", "1760", "76001", "a760b") and must produce no hit.  Measurement-array mutations replace one
recorded value of a pack copy by a protected value (and, as a control, leave a copy unaltered): the provenance check
must flag every altered copy and no unaltered one.  The unmutated carriers must be clean, so a
detection is attributable to the planted text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
from decimal import Decimal
from typing import Any, Sequence

from . import leakage as lk
from .candidate.common import write_json

HERE = pathlib.Path(__file__).resolve().parent
CARRIERS = (HERE / "candidate" / "common.py", HERE / "candidate" / "pack" / "P1.json")

# value from the brief (user-supplied) plus synthetic values exercising every unit path; no history is read for these
SYNTHETIC = (lk.protected("brief_example_C1", "760", "F"), lk.protected("synthetic_R", "0.0321", "ohm"),
             lk.protected("synthetic_tau", "4567", "s"), lk.protected("synthetic_rmse", "12.34", "mV"))
PREFIXED = {"ohm": ("m", "mohm"), "V": ("m", "mV"), "F": ("m", "mF"), "s": ("k", "ks")}


def historical_values() -> list[lk.Protected]:
    """The historical 1RC estimates and errors as v0 already revealed them (results/EVALUATION.json of v0, committed
    e1be5910..986cc43c).  Reading this record is reading history; v1's evaluator is not blind and says so."""
    rec = json.loads((HERE.parent / "battery_rediscovery_v0" / "results" / "EVALUATION.json").read_bytes())["truth"]
    out = []
    for pid, p in sorted(rec["historical_parameters"].items()):
        for k, unit in (("R0", "ohm"), ("R1", "ohm"), ("C1", "F")):
            out.append(lk.protected(f"{pid}.{k}", repr(p["1rc"][k]), unit))
        out.append(lk.protected(f"{pid}.tau", repr(p["tau_s"]), "s"))
        out.append(lk.protected(f"{pid}.calibration_rmse", repr(p["rmse_mV"]), "mV"))
    for pid, roles in sorted(rec["historical_heldout_rmse_mV"].items()):
        for role, v in sorted(roles.items()):
            out.append(lk.protected(f"{pid}.{role}_rmse", repr(v), "mV"))
    return out


def _fmt(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    return s


def leak_forms(v: lk.Protected) -> dict[str, str]:
    r3 = lk.round_sig(abs(v.value), 3)
    s3 = _fmt(r3)
    dec = s3 + (".0" if "." not in s3 else "0")
    forms = {"integer_or_reported": s3, "decimal_equivalent": dec, "signed": "+" + s3,
             "scientific": f"{float(r3):.2e}", "value_plus_unit": f"{s3} {v.unit}", "unit_no_space": f"{s3}{v.unit}",
             "prose_label": f"the historical estimate of {v.name} was {s3} {v.unit}",
             "result_label": f'"{v.name}": {s3}', "assignment": f"{v.name.split('.')[-1]}={s3}",
             "full_precision": format(v.value, "f")}
    if v.base in PREFIXED and v.unit == v.base:
        p, unit = PREFIXED[v.base]
        forms["si_prefixed"] = f"{_fmt(lk.round_sig(abs(v.value) / lk.PREFIX[p], 3))} {unit}"
    return forms


def benign_forms(v: lk.Protected) -> dict[str, str]:
    s3 = _fmt(lk.round_sig(abs(v.value), 3))
    longer = s3 + ("006" if "." in s3 else ".006")
    return {"longer_decimal": longer, "leading_digit": "1" + s3, "trailing_digits": s3 + "01",
            "inside_identifier": "a" + s3.replace(".", "") + "b", "underscore_identifier": "x_" + s3 + "_y",
            "longer_trailing_zero_free": s3 + ("7" if "." in s3 else ".7")}


def _insert(carrier: pathlib.Path, text: str) -> str:
    raw = carrier.read_bytes().decode()
    if carrier.suffix == ".json":
        # inside the problem description string: a JSON-valid place the candidate reads
        key = '"description": "'
        i = raw.index(key) + len(key)
        return raw[:i] + text.replace('"', "'") + " " + raw[i:]
    return raw + "\n# " + text + "\n"


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
                    hits = [h for f_ in lk.numeric_findings([path], [v]) for h in f_["hits"]]
                    caught = bool(hits)
                    ok = caught == want
                    case = {"carrier": carrier.name, "protected": v.name, "kind": kind, "text": form,
                            "expected": "DETECT" if want else "NO_HIT", "caught": caught, "ok": ok}
                    cases.append(case)
                    if not ok:
                        failures.append(case)
            for token in lk.VERDICT + ["B0006", "battery_1rc_closure", "70ffb357511d", "CALIBRATION.json"]:
                path = tmp / carrier.name
                path.write_bytes(_insert(carrier, f"result label: {token}").encode())
                caught = token in (lk.text_findings([path]) or [{"tokens": []}])[0]["tokens"]
                case = {"carrier": carrier.name, "protected": token, "kind": "text_token", "text": token,
                        "expected": "DETECT", "caught": caught, "ok": caught}
                cases.append(case)
                if not caught:
                    failures.append(case)
        # measurement arrays: provenance, not numeric scanning
        pack = HERE / "candidate" / "pack"
        for k, (pid, set_name, key) in enumerate((("P1", "calibration", "voltage_V"), ("P2", "calibration", "t_s"),
                                                   ("P1", "calibration", "temperature_C"))):
            for v in values[:2] + [None]:
                d = tmp / f"pack_{k}_{'none' if v is None else v.name}"
                shutil.copytree(pack, d)
                if v is not None:
                    prob = json.loads((d / f"{pid}.json").read_bytes())
                    prob["sets"][set_name]["trajectories"][0][key][3] = float(lk.round_sig(abs(v.value), 3))
                    (d / f"{pid}.json").write_bytes((json.dumps(prob, sort_keys=True, indent=1) + "\n").encode())
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
    return {"schema": "forge.battery_rediscovery.leakage_mutation/1", "phase": phase,
            "scanner": f"{lk.SCANNER_ID}@{lk.SCANNER_VERSION}",
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
    values = list(SYNTHETIC) + historical_values()
    rep = run(values, a.phase)
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
