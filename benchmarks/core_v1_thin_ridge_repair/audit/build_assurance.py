"""Assemble certification/v1_thin_ridge_repair_assurance.json for the certificate reissue.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/build_assurance.py

Starts from the assurance embedded in the current certificate and replaces what this round
re-measured: the certified 79 harness (its log is committed beside this script's outputs), the test
suites (SUITES.json), FAST and FULL, the repair mutation matrix (not part of the certified 79), the
frozen API facts and wheel parity. Families this round did not re-run keep their carried-forward labels.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_v1_thin_ridge_repair"


def main():
    certificate = json.loads((ROOT / "certification" / "current_core_v2.json").read_text(encoding="utf-8"))
    assurance = certificate["assurance"]

    identity = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in assurance["harness_identity"]["files"]}
    if identity != assurance["harness_identity"]["files"]:
        raise SystemExit("the harness files changed; '79/79' would describe different bytes")

    log = (ROUND / "MUTATION_HARNESS_79.log").read_bytes()
    text = log.decode("utf-8")
    red = len(re.findall(r"^G\w+\s+RED\b", text, flags=re.M))
    green = len(re.findall(r"^G\w+\s+GREEN\b", text, flags=re.M))
    control = re.search(r"^CONTROL GREEN.*\n\s+(\d+) passed", text, flags=re.M)
    if not (control and red == 79 and green == 0 and "79/79 mutations were killed" in text):
        raise SystemExit("the committed harness log does not show a green control and 79/79 killed")
    harness = dict(assurance["mutation"]["certified_harness"])
    harness.update({
        "control": "GREEN", "control_suites_passed": int(control.group(1)), "killed": red, "survivors": 0, "survivor_ids": [], "total": 79,
        "log": "benchmarks/core_v1_thin_ridge_repair/MUTATION_HARNESS_79.log", "log_bytes": len(log), "log_sha256": hashlib.sha256(log).hexdigest(),
        "why_it_was_re_run": "The certified POPULATION changed this round: src/engcore/inference/calibration.py (inference_admission area) "
                             "gained the private thin-ridge resolution guard. '79/79 killed' is a statement about exact bytes, so it was re-earned "
                             "on the repair candidate (harness run from a scratch worktree at bccbbf7, whose src and tests are identical to the "
                             "certified commit's) rather than carried forward.",
    })
    assurance["mutation"]["certified_harness"] = harness

    ridge = json.loads((ROUND / "RIDGE_MUTATIONS.json").read_text(encoding="utf-8"))
    killed = sum(r["verdict"] == "KILLED" for r in ridge["results"].values())
    assurance["mutation"]["v1_thin_ridge_repair_matrix"] = {
        "command": "python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/ridge_mutations.py --tree <scratch worktree>",
        "control": "GREEN" if ridge["control"]["exit_code"] == 0 else "RED", "killed": killed, "total": len(ridge["results"]),
        "survivors": [k for k, r in ridge["results"].items() if r["verdict"] != "KILLED"],
        "in_the_formal_certificate": False,
        "why_not": "tests/mutation_guards.py is inside certified scope and pinned; RIDGE-1..8 are recorded separately and never added to the certified 79.",
        "runner": "benchmarks/core_v1_thin_ridge_repair/audit/ridge_mutations.py",
    }

    suites = json.loads((ROUND / "SUITES.json").read_text(encoding="utf-8"))
    suites["certification_suite"]["note"] = ("measured BEFORE this reissue: test_the_certificate_describes_this_tree fails because the "
                                             "inference area changed and the certificate has not yet been rebuilt. Re-run after the reissue "
                                             "is recorded in REPAIR_REPORT.md")
    suites["fast"] = {"command": 'python -X utf8 -m pytest tests -n 4 -m "not expensive and not campaign" -q -p no:cacheprovider',
                      "passed": 5005, "failed": 3, "skipped": 5, "summary_line": "3 failed, 5005 passed, 5 skipped, 42 warnings in 74.59s",
                      "failed_tests": ["tests/test_core_certificate.py::test_the_certificate_describes_this_tree",
                                       "tests/test_core_freeze_manifest.py::test_the_tree_is_core_freeze_v1",
                                       "tests/test_core_freeze_manifest.py::test_a_descendant_that_keeps_the_contract_still_verifies"],
                      "note": "all three fail on certificate.verifies before the reissue"}
    suites["full"] = {"command": "python -X utf8 -m pytest tests -n 4 -q -p no:cacheprovider",
                      "passed": 5551, "failed": 3, "skipped": 5, "summary_line": "3 failed, 5551 passed, 5 skipped, 42 warnings in 152.12s",
                      "failed_tests": suites["fast"]["failed_tests"], "note": suites["fast"]["note"]}
    assurance["test_suites"] = suites

    wheel = json.loads((ROUND / "WHEEL_PARITY.json").read_text(encoding="utf-8"))
    assurance["v1_thin_ridge_repair"] = {
        "round": "Core V1 Certified Repair -- Thin-Ridge Posterior Resolution Guard",
        "baseline": "273bfff7d3d685d9e0bb62519795aeb47c05b027",
        "kind": "correctness repair of frozen grid-resolution behaviour; no public API, signature, serialization or identity change",
        "frozen_api_digest": "c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929",
        "frozen_symbol_count": 194, "experimental_symbol_count": 11,
        "wheel_source_frozen_api_parity": "MATCH" if wheel["frozen_api_parity"] is True else "MISMATCH",
        "threshold": {"value": 9.210340371976184, "protocol": "benchmarks/core_v1_thin_ridge_repair/THRESHOLD_PROTOCOL.json",
                      "selection": "benchmarks/core_v1_thin_ridge_repair/THRESHOLD_SELECTION.json"},
        "regression_matrix": "benchmarks/core_v1_thin_ridge_repair/REGRESSION_MATRIX.json",
        "errata": "benchmarks/core_v1_thin_ridge_repair/ERRATA.md",
    }
    out = ROOT / "certification" / "v1_thin_ridge_repair_assurance.json"
    out.write_bytes((json.dumps(assurance, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print("wrote", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
