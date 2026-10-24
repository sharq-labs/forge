"""Mutation test of the v3 leakage firewall: every planted leak must be caught, no benign control may trigger.

    python -m benchmarks.battery_rediscovery_v3.mutation --phase pre_run     # writes MUTATION_REPORT_pre_run.json

Four families of cases:

1. NUMERIC: v1's mutation forms (reported form, decimal equivalent, signed, scientific, value plus unit, SI-prefixed unit,
   prose label, result label, assignment, full-precision transcription) of every protected value, planted in copies of
   candidate material (a GEN1 code file and two bundle files) in a scratch directory; benign controls embed the value
   inside longer numbers and identifiers.  The candidate tree is never touched.
2. TEXT: every verdict token and a sample of identity tokens, planted the same way.
3. MEASUREMENT ARRAYS: one recorded value of a bundle copy replaced; the provenance check must flag every altered copy
   and no unaltered copy.
4. RUNTIME: synthetic access logs that read the EvaluatorVault, the TruthBundle, the v2 pack, a v2 results file, a path
   outside every root, an output during a run, or load an evaluator module, must each be flagged; a benign log (bundle,
   GEN1 code, engcore, outputs written) must not.  One REAL subprocess control installs the sandbox hook, opens a vault
   file and must be flagged from its own access log.
The unmutated carriers must be clean.

Protected values: v1's synthetic values, the historical 1RC estimates and errors v0 revealed, v2's truth statistics and
optimum (the bridge problems are v2's), and the battery numbers the evaluator's project memory holds for the archives
this benchmark draws on (Sprint 3 voltage results, the LG HG2 identifiability results).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from benchmarks.battery_rediscovery_v1.mutation import SYNTHETIC, _insert, benign_forms, historical_values, leak_forms
from benchmarks.battery_rediscovery_v2.candidate.common import write_json

from . import leakage as lk

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CARRIERS = (lk.GEN1_CANDIDATE / "arms.py", lk.PACK / "P01.json", lk.PACK / "P25.json")
TEXT_SAMPLES = ["B0029", "B0051", "Expt 4", "Kirkaldy", "LGM50_cell02", "10637534", "EvaluatorVault", "TruthBundle",
                "battery_1rc_crosscell"]
ARRAY_CASES = (("P01", "calibration", "voltage_V"), ("P25", "calibration", "t_s"), ("P28", "calibration", "temperature_C"))
MEMORY_VALUES = (("sprint3.gateA_rmse", "62.40", "mV"), ("sprint3.gateA_p95", "108.13", "mV"),
                 ("sprint3.B0044_rmse", "99.74", "mV"), ("sprint3.recovery_before", "116.4", "mV"),
                 ("sprint3.recovery_after", "38.4", "mV"), ("sprint3.B0041_bias", "128", "mV"),
                 ("lghg2.R0", "20.7", "mohm"), ("lghg2.R1", "15.6", "mohm"), ("lghg2.tau", "24.8", "s"),
                 ("lghg2.pulse_rmse", "12.6", "mV"), ("lghg2.cc_rmse", "28.7", "mV"))
#: a memory value is protected only if its recorded form has >= 3 significant digits: a two-digit number such as the
#: LG HG2 constant-current bias (-25 mV) coincides with protocol facts (a 25 C ambient) and would protect nothing


def _v2_truth_values() -> list[lk.Protected]:
    """v2's truth statistics and optimum.  An optimum value equal to one of its declared bounds (v2 Q1's R1 = 1 ohm) is
    the bound, not an estimate, carries no information beyond the pack's declaration, and would match every "1": it is
    not protected."""
    t = json.loads((ROOT / "benchmarks" / "battery_rediscovery_v2" / "results" / "TRUTH.json").read_bytes())["table"]
    out = []
    for pid, table in sorted(t.items()):
        bounds = json.loads((lk.GEN1_CANDIDATE / "pack" / f"{pid}.json").read_bytes())["declared_family"]["parameter_bounds"]
        out.append(lk.protected(f"v2.{pid}.adequacy_rmse", repr(table["MODEL_ADEQUACY"]["rmse"]), "V"))
        for name, v in sorted(table["diagnostics"]["parameters"].items()):
            if name in ("R0", "R1", "C1") and v not in bounds[name]:
                out.append(lk.protected(f"v2.{pid}.{name}", repr(v), {"R0": "ohm", "R1": "ohm", "C1": "F"}[name]))
        for key, per in sorted(table["diagnostics"]["subsets"].items()):
            for sub, d in sorted(per.items()):
                out.append(lk.protected(f"v2.{pid}.{key}.{sub}.rmse", repr(d["rmse"]), "V"))
    return out


def protected_values() -> list[lk.Protected]:
    return (list(SYNTHETIC) + historical_values() + _v2_truth_values()
            + [lk.protected(n, v, u) for n, v, u in MEMORY_VALUES])


def _case(cases, failures, **c):
    c["ok"] = c["caught"] == (c["expected"] == "DETECT")
    cases.append(c)
    if not c["ok"]:
        failures.append(c)


def runtime_cases(tmp: pathlib.Path) -> list[dict[str, Any]]:
    out_dir = lk.HERE / "results" / "candidate"
    ok_paths = [[str(lk.PACK / "P01.json"), "rb"], [str(lk.GEN1_CANDIDATE / "arms.py"), "r"],
                [str(ROOT / "src" / "engcore" / "mind" / "repsem" / "assess.py"), "r"],
                [str(out_dir / "OLD_MIND__P01.json"), "wb"]]
    base_modules = ["benchmarks.battery_rediscovery_v2.candidate.run", "engcore.mind.repsem"]
    bad = {"vault_read": [str(lk.VAULT / "IDENTITY_MAP.json"), "rb"],
           "truth_bundle_read": [str(lk.TRUTH / "TRUTH.json"), "rb"],
           "v2_pack_read": [str(lk.GEN1_CANDIDATE / "pack" / "Q1.json"), "rb"],
           "v2_results_read": [str(ROOT / "benchmarks" / "battery_rediscovery_v2" / "results" / "TRUTH.json"), "rb"],
           "outside_roots": ["D:/forge-data/kirkaldy2024/record.json", "rb"],
           "output_read_during_run": [str(out_dir / "REPRESENTATION_PLUS_ROLES__P01.json"), "rb"]}
    rows = []
    for name, extra in [("benign", None), *bad.items()]:
        log = {"opened": ok_paths + ([extra] if extra else []), "modules": base_modules, "exit": 0}
        rows.append({"name": name, "flagged": lk.runtime_failed(lk.runtime_findings(log, [out_dir])),
                     "expected": "NO_HIT" if extra is None else "DETECT"})
    log = {"opened": ok_paths, "modules": base_modules + ["benchmarks.battery_rediscovery_v3.evaluator.truth"], "exit": 0}
    rows.append({"name": "evaluator_module_loaded", "flagged": lk.runtime_failed(lk.runtime_findings(log, [out_dir])),
                 "expected": "DETECT"})
    # one real process: the sandbox hook sees a vault read
    real_log = tmp / "real_access_log.json"
    code = ("import sys; from benchmarks.battery_rediscovery_v3 import sandbox_run as s; s.install(); "
            f"open(r'{lk.VAULT / 'IDENTITY_MAP.json'}', 'rb').read(64); s.write_log(r'{real_log}', 0)")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)
    r = lk.runtime_findings(json.loads(real_log.read_bytes()), [out_dir])
    rows.append({"name": "real_process_vault_read", "flagged": bool(r["forbidden_paths"]), "expected": "DETECT"})
    return rows


def run(values: Sequence[lk.Protected], phase: str) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
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
                    _case(cases, failures, carrier=carrier.name, protected=v.name, kind=kind, text=form,
                          expected="DETECT" if want else "NO_HIT", caught=caught)
            for token in lk.VERDICT + TEXT_SAMPLES:
                path = tmp / carrier.name
                path.write_bytes(_insert(carrier, f"result label: {token}").encode())
                caught = token in (lk.text_findings([path]) or [{"tokens": []}])[0]["tokens"]
                _case(cases, failures, carrier=carrier.name, protected=token, kind="text_token", text=token,
                      expected="DETECT", caught=caught)
        for k, (pid, set_name, key) in enumerate(ARRAY_CASES):
            for v in list(values[:2]) + [None]:
                d = tmp / f"pack_{k}_{'none' if v is None else v.name}"
                shutil.copytree(lk.PACK, d)
                if v is not None:
                    spec = json.loads((d / f"{pid}.json").read_bytes())
                    col = spec["sets"][set_name][0]["columns"][key]
                    col[3] = float(lk.round_sig(abs(v.value), 3)) if key != "t_s" else col[3] + 1e-6
                    (d / f"{pid}.json").write_bytes((json.dumps(spec, sort_keys=True, indent=1) + "\n").encode())
                caught = bool(lk.provenance_findings(d))
                _case(cases, failures, carrier=f"pack:{pid}/{key}", protected=None if v is None else v.name,
                      kind="measurement_array" if v is not None else "measurement_array_unaltered",
                      text=None, expected="DETECT" if v is not None else "NO_HIT", caught=caught)
        for row in runtime_cases(tmp):
            _case(cases, failures, carrier="runtime", protected=row["name"], kind="runtime_access", text=None,
                  expected=row["expected"], caught=row["flagged"])
    status = "PASS" if not failures and not clean else "FAIL"
    leaks = [c for c in cases if c["expected"] == "DETECT"]
    benign = [c for c in cases if c["expected"] == "NO_HIT"]
    return {"schema": "forge.battery_rediscovery_v3.leakage_mutation/1", "phase": phase,
            "scanner": f"{lk.SCANNER_ID}@{lk.SCANNER_VERSION}", "numeric_engine": lk.NUMERIC_ENGINE,
            "scanner_sha256": hashlib.sha256((HERE / "leakage.py").read_bytes()).hexdigest(),
            "status": status, "unmutated_carriers_clean": not clean, "carrier_findings": clean,
            "leak_mutations": len(leaks), "leaks_caught": sum(c["caught"] for c in leaks),
            "benign_controls": len(benign), "benign_triggered": sum(c["caught"] for c in benign),
            "runtime_cases": [c for c in cases if c["kind"] == "runtime_access"],
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
          f"benign triggered {rep['benign_triggered']}/{rep['benign_controls']}", "carriers clean",
          rep["unmutated_carriers_clean"])
    for f in rep["failures"][:20]:
        print("  FAIL", json.dumps(f)[:300])
    for f in rep["carrier_findings"][:10]:
        print("  CARRIER", json.dumps(f)[:300])
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
