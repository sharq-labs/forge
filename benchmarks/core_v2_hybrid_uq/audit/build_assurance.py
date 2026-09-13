"""Assemble certification/core_v2_assurance.json (embedded by the certificate reissue) and
certification/core_freeze_v2_assurance.json (read by the V2 freeze verifier).

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/build_assurance.py certificate
    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/build_assurance.py freeze --candidate <commit>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "core_v2_hybrid_uq"


def load(name):
    return json.loads((ROUND / name).read_text(encoding="utf-8"))


def harness_record():
    log = (ROUND / "MUTATION_HARNESS_79.log").read_bytes()
    text = log.decode("utf-8")
    red = len(re.findall(r"^G\w+\s+RED\b", text, flags=re.M))
    green = len(re.findall(r"^G\w+\s+GREEN\b", text, flags=re.M))
    control = re.search(r"^CONTROL GREEN.*\n\s+(\d+) passed", text, flags=re.M)
    if not (control and red == 79 and green == 0 and "79/79 mutations were killed" in text):
        raise SystemExit("the committed harness log does not show a green control and 79/79 killed")
    return {"control": "GREEN", "control_suites_passed": int(control.group(1)), "killed": 79, "total": 79, "survivors": 0,
            "log": "benchmarks/core_v2_hybrid_uq/MUTATION_HARNESS_79.log", "log_sha256": hashlib.sha256(log).hexdigest(), "log_bytes": len(log),
            "candidate_run_at": "3ca1c82 (src and the pinned harness files byte-identical to the V2 candidate)"}


def certificate_assurance():
    cert = json.loads((ROOT / "certification" / "current_core_v2.json").read_text(encoding="utf-8"))
    assurance = cert["assurance"]
    identity = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in assurance["harness_identity"]["files"]}
    if identity != assurance["harness_identity"]["files"]:
        raise SystemExit("harness files changed: '79/79' would describe different bytes")
    harness = dict(assurance["mutation"]["certified_harness"])
    harness.update(harness_record())
    harness["why_it_was_re_run"] = ("The certified POPULATION changed: Core V2 adds src/engcore/hybrid_uq/** as the certified area "
                                    "routed_uncertainty, and src/engcore/api_snapshot.py gained the V2 surface. '79/79 killed' is re-earned "
                                    "on the V2 candidate rather than carried forward.")
    assurance["mutation"]["certified_harness"] = harness
    hd = load("HD_MUTATIONS.json")
    assurance["mutation"]["core_v2_hd_matrix"] = {
        "runner": "benchmarks/core_v2_hybrid_uq/audit/hd_mutations.py", "control": "GREEN" if hd["control"]["exit_code"] == 0 else "RED",
        "killed": sum(r["verdict"] == "KILLED" for r in hd["results"].values()), "total": len(hd["results"]),
        "in_the_formal_certificate": False, "why_not": "the certified 79 are pinned; V2 mutations are recorded beside them, never added"}
    suites = load("SUITES.json")
    assurance["test_suites"] = {name: {k: v for k, v in s.items() if k != "failing"} for name, s in suites["suites"].items()}
    assurance["test_suites_commit"] = suites["commit"]
    wheel = load("WHEEL_V2.json")
    from engcore import api_snapshot as A

    v2 = A.build(modules=A.V2_CANONICAL_MODULES)
    assurance["core_v2"] = {
        "round": "Core V2 -- Scalable Hybrid Uncertainty Quantification (additive)", "v2_baseline": "7519aee559750f51bfc58aea12ab29ec199743f4",
        "v1_frozen_api_digest": A.frozen_digest(), "v1_frozen_symbol_count": A.frozen_only()["symbol_count"],
        "v2_frozen_api_digest": A.frozen_digest(v2), "v2_frozen_symbol_count": A.frozen_only(v2)["symbol_count"],
        "added_module": list(A.V2_ADDED_MODULES), "wheel_v1_parity": wheel["v1_frozen_api_parity"], "wheel_v2_parity": wheel["v2_frozen_api_parity"],
        "isolated_wheel_smoke": wheel["isolated_wheel_smoke"]["passed"], "api_design": "docs/CORE_V2_API_DESIGN.md",
    }
    out = ROOT / "certification" / "core_v2_assurance.json"
    out.write_bytes((json.dumps(assurance, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print("wrote", out.relative_to(ROOT))


def freeze_assurance(candidate):
    manifest = (ROOT / "certification" / "core_freeze_v2.json").read_bytes()
    suites = load("SUITES.json")["suites"]
    freeze_v2 = load("FREEZE_V2_SUITE.json")
    required = {
        "FAST": suites["FAST"], "FULL": suites["FULL"], "hybrid_uq_focused": suites["hybrid_uq_focused"],
        "v1_thin_ridge_regressions": suites["v1_thin_ridge_regressions"], "api_snapshot_v1": suites["api_snapshot_v1"],
        "api_snapshot_v2": suites["api_snapshot_v2"], "serialization": suites["serialization"], "dependency_layering": suites["dependency_layering"],
        "freeze_manifest_v1": suites["freeze_manifest_v1"], "freeze_manifest_v2": freeze_v2, "certificate": suites["certificate"],
        "battery_regressions": suites["battery_regressions"], "tcr_regressions": suites["tcr_regressions"],
        "kinetics_regressions": suites["kinetics_regressions"], "identity": suites["identity"], "contract_guard": suites["contract_guard"],
    }
    hd = load("HD_MUTATIONS.json")
    wheel = load("WHEEL_V2.json")
    record = {
        "schema": "engcore.core_freeze_assurance/2", "tag": "v2.0-core-freeze", "candidate_commit": candidate,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "suites": {name: {"green": bool(s["green"]), "summary_line": s["summary_line"], "exit_code": s["exit_code"]} for name, s in required.items()},
        "mutations": {"certified_79": harness_record(),
                      "hd_matrix": {"control": "GREEN" if hd["control"]["exit_code"] == 0 else "RED", "total": len(hd["results"]),
                                    "killed": sum(r["verdict"] == "KILLED" for r in hd["results"].values()),
                                    "results": {k: r["verdict"] for k, r in hd["results"].items()}}},
        "wheel": {"v1_frozen_api_parity": wheel["v1_frozen_api_parity"], "v2_frozen_api_parity": wheel["v2_frozen_api_parity"],
                  "isolated_wheel_smoke": wheel["isolated_wheel_smoke"]["passed"]},
        "evidence": {name: hashlib.sha256((ROUND / name).read_bytes()).hexdigest() for name in
                     ("BATTERY_T41.json", "TCR.json", "KINETICS_K2.json", "FAILURE_CASES.json", "PERFORMANCE.json", "HD_MUTATIONS.json",
                      "WHEEL_V2.json", "SUITES.json", "MUTATION_HARNESS_79.log")},
    }
    out = ROOT / "certification" / "core_freeze_v2_assurance.json"
    out.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print("wrote", out.relative_to(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["certificate", "freeze"])
    ap.add_argument("--candidate")
    args = ap.parse_args()
    if args.which == "certificate":
        certificate_assurance()
    else:
        freeze_assurance(subprocess.check_output(["git", "rev-parse", args.candidate], cwd=ROOT, text=True).strip())


if __name__ == "__main__":
    main()
