"""Run the named assurance suites for the V1 thin-ridge repair and record them in the certificate's format.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/suites.py

Writes benchmarks/core_v1_thin_ridge_repair/SUITES.json. The selections are the ones the current
certificate records (certification/current_core_v2.json -> assurance.test_suites), plus this round's
focused grid-resolution, predictive-UQ, TCR, K-series and battery regressions.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
RUN_TEMP = f"D:/rp_suites/run{int(time.time())}"

SUITES = {
    "grid_resolution_repair": "tests/inference/test_grid_resolution_repair.py",
    "tcr_calibration_and_uq": "tests/inference",
    "predictive_uq_and_adequacy": "tests/test_k3_predictive_uq.py tests/test_k31_predictive_admission.py tests/test_k4_model_adequacy.py tests/test_evidence_pairing_integrity.py",
    "battery_regressions": "tests/domains/battery",
    "capability_boundary": "tests/domains -k applicab or boundary tests/mcp/test_battery_boundary.py",
    "certification_suite": "tests/test_core_certificate.py",
    "contract_guard": "tests/test_core_guards.py tests/test_design_d0_contracts.py tests/test_data_boundary0.py",
    "core_api_stability": "tests/test_core_api_snapshot.py tests/test_core_api_contracts.py tests/test_core_api_layering.py tests/test_core_api_serialization.py tests/test_core_api_deprecation.py tests/test_core_freeze_policy.py tests/test_trust_boundary_package_identity.py",
    "mutation_harness_self_guard": "tests/test_mutation_harness.py",
}


def selection_argv(selection: str) -> list[str]:
    if " -k " in selection:
        head, rest = selection.split(" -k ", 1)
        expr, _, tail = rest.partition(" tests/")
        return [*head.split(), "-k", expr, *(("tests/" + tail).split() if tail else [])]
    return selection.split()


def main():
    current = json.loads((ROOT / "certification" / "current_core_v2.json").read_text(encoding="utf-8"))["assurance"]["test_suites"]
    for name in ("field_profile_suites", "field_suites", "scientific_truth"):
        SUITES[name] = current[name]["selection"]
    env = dict(os.environ, TMPDIR="D:/b3tmp", TEMP="D:/b3tmp", TMP="D:/b3tmp")
    out = {}
    pathlib.Path(RUN_TEMP).mkdir(parents=True, exist_ok=False)
    for name, selection in SUITES.items():
        argv = [sys.executable, "-X", "utf8", "-m", "pytest", *selection_argv(selection), "-q", "-p", "no:cacheprovider",
                f"--basetemp={RUN_TEMP}/{name}"]
        started = time.monotonic()
        done = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        summary = lines[-1].strip("= ") if lines else "?"
        count = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", summary)) else 0
        out[name] = {"command": f"python -X utf8 -m pytest {selection} -q -p no:cacheprovider", "selection": selection,
                     "exit_code": done.returncode, "passed": count("passed"), "failed": count("failed"), "skipped": count("skipped"),
                     "deselected": count("deselected"), "seconds": round(time.monotonic() - started, 1), "summary_line": summary}
        print(f"{name:30s} exit={done.returncode} {summary}", flush=True)
    (ROOT / "benchmarks" / "core_v1_thin_ridge_repair" / "SUITES.json").write_bytes((json.dumps(out, indent=1, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
