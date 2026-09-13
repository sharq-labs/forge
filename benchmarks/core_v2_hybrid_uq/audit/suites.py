"""Part 19: the Core V2 assurance suites, run on a clean candidate and recorded.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/suites.py

Writes benchmarks/core_v2_hybrid_uq/SUITES.json. FAST and FULL run with ``-n 4``; everything else serially.
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
RUN_TEMP = f"D:/v2_suites/run{int(time.time())}"

SUITES = {
    "hybrid_uq_focused": ["tests/hybrid_uq"],
    "v1_thin_ridge_regressions": ["tests/inference/test_grid_resolution_repair.py", "tests/inference/test_tcr_calibration.py",
                                  "tests/inference/test_tcr_heldout_uq.py", "tests/inference/test_reproducibility_and_evidence.py"],
    "battery_regressions": ["tests/domains/battery"],
    "tcr_regressions": ["tests/inference", "tests/hybrid_uq/test_hybrid_uq_tcr.py"],
    "kinetics_regressions": ["tests/test_k3_predictive_uq.py", "tests/test_k31_predictive_admission.py", "tests/test_k4_model_adequacy.py"],
    "serialization": ["tests/test_core_api_serialization.py", "tests/hybrid_uq/test_hybrid_uq_records.py"],
    "identity": ["tests/test_evidence_pairing_integrity.py", "tests/hybrid_uq/test_hybrid_uq_records.py"],
    "dependency_layering": ["tests/test_core_api_layering.py", "tests/test_core_api_contracts.py", "tests/test_core_v2_compatibility.py"],
    "api_snapshot_v1": ["tests/test_core_api_snapshot.py", "tests/test_core_freeze_policy.py", "tests/test_core_api_deprecation.py"],
    "api_snapshot_v2": ["tests/test_core_v2_api_snapshot.py", "tests/test_core_v2_compatibility.py"],
    "contract_guard": ["tests/test_core_guards.py", "tests/test_design_d0_contracts.py", "tests/test_data_boundary0.py"],
    "freeze_manifest_v1": ["tests/test_core_freeze_manifest.py"],
    "certificate": ["tests/test_core_certificate.py"],
    "FAST": ["tests", "-n", "4", "-m", "not expensive and not campaign"],
    "FULL": ["tests", "-n", "4"],
}


def main():
    env = dict(os.environ, TMPDIR="D:/b3tmp", TEMP="D:/b3tmp", TMP="D:/b3tmp")
    pathlib.Path(RUN_TEMP).mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    clean = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip() == ""
    out = {"schema": "core_v2_suites/1", "commit": head, "clean_tree": clean, "suites": {}}
    for name, selection in SUITES.items():
        argv = [sys.executable, "-X", "utf8", "-m", "pytest", *selection, "-q", "-p", "no:cacheprovider", f"--basetemp={RUN_TEMP}/{name}"]
        started = time.monotonic()
        done = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        summary = lines[-1].strip("= ") if lines else "?"
        count = lambda word: int(m.group(1)) if (m := re.search(rf"(\d+) {word}", summary)) else 0
        failed = [line for line in done.stdout.splitlines() if line.startswith(("FAILED", "ERROR"))]
        out["suites"][name] = {"command": "python -X utf8 -m pytest " + " ".join(selection) + " -q -p no:cacheprovider", "exit_code": done.returncode,
                               "passed": count("passed"), "failed": count("failed"), "errors": count("error"), "skipped": count("skipped"),
                               "seconds": round(time.monotonic() - started, 1), "summary_line": summary, "failing": failed[:20],
                               "green": done.returncode == 0}
        print(f"{name:28s} exit={done.returncode} {summary}", flush=True)
    (ROOT / "benchmarks" / "core_v2_hybrid_uq" / "SUITES.json").write_bytes((json.dumps(out, indent=1) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
