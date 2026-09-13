"""Core Freeze V2: build the V2 freeze manifest, record its assurance, verify both.

    python -m tools.certification.core_freeze_v2 --build --candidate <commit>
    python -m tools.certification.core_freeze_v2 --record-assurance --candidate <commit>
    python -m tools.certification.core_freeze_v2 --verify

Core V2 is ADDITIVE to Core Freeze V1: one new canonical module (``engcore.hybrid_uq``) and nothing changed in
the seven V1 modules. This verifier therefore checks two things.

1. **Core Freeze V1 still verifies**, by calling the V1 verifier itself (``tools/certification/core_freeze.py``).
   V1 history is not rewritten; the V1 manifest, assurance and tag are untouched.
2. **The V2 contract holds**:
   * the V2 API surface -- frozen digest, counts, modules, the added symbols, and the pinned V2 snapshot bytes;
   * every V1 frozen entry byte-identical inside the V2 surface;
   * the V2 serialization inventory: schema strings, byte-identical round trips, and unknown-schema refusal;
   * identity reference digests of literal V2 fixture records (no floating-point numerics, so machine-independent);
   * the route-class vocabulary (approximation classes, claims, decisions, reasons and their severities);
   * the V1 thin-ridge repair still in force;
   * the certificate verifying.

As in V1, on the freeze commit every check binds; on a later commit the contract checks still bind, and a commit
that fails one is not a descendant of Core Freeze V2.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import math
import pathlib
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

MANIFEST_SCHEMA = "engcore.core_freeze/2"
ASSURANCE_SCHEMA = "engcore.core_freeze_assurance/2"
MANIFEST_PATH = "certification/core_freeze_v2.json"
ASSURANCE_PATH = "certification/core_freeze_v2_assurance.json"
REPORT_PATH = "certification/CORE_FREEZE_V2.md"
V1_MANIFEST_PATH = "certification/core_freeze_v1.json"
TAG = "v2.0-core-freeze"
PINNED_V2_FILES = ("tests/api/v2_frozen_api_snapshot.json", "tests/api/v2_full_api_snapshot.json")
V1_FROZEN_DIGEST = "c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929"
V1_FROZEN_COUNT = 194

CAPABILITY_CLAIM = (
    "Core V2 adds routed uncertainty quantification beside Core V1's grid route, for calibrations posed through "
    "engcore.inference.calibrate with declared Gaussian observation noise and a flat prior inside declared bounds. "
    "route_uncertainty returns, deterministically and with every route it considered recorded: POSTERIOR_GRID when "
    "a supplied tensor grid of at most 5 parameters passes the repaired V1 resolution checks; "
    "LOCAL_GAUSSIAN_APPROXIMATION (N(z_hat, (Jw^T Jw)^-1) in declared inference coordinates, O(p) forward "
    "evaluations plus a mandatory deterministic multistart) when its validity diagnostics support it; "
    "POSTERIOR_GRID rebuilt from the local covariance when a rebuild policy is supplied, p <= 5, and the rebuilt grid "
    "is contained, converged at declared bounds, and accepted by the V1 checks; the local Gaussian DOWNGRADED with its "
    "reasons; or REFUSED with no numbers. Identifiability uses the frozen V1 thresholds and rule in a recorded "
    "parameterization. Predictive uncertainty keeps parameter and measurement uncertainty separate and names model "
    "discrepancy as not modelled. No approximation class is an exact posterior."
)
NON_CLAIMS = (
    "not an exact posterior, in any route",
    "not a proof of global mode uniqueness: multistart bounds it, it does not prove it",
    "no model-discrepancy estimate, no estimated noise, no non-Gaussian likelihoods, no informative priors",
    "no MCMC, Laplace-with-full-Hessian, sparse-grid or importance-sampling posterior",
    "no grid route above 5 parameters; no resolution check for non-tensor or linearly mapped point sets (refused)",
    "no adequacy scoring over the linearized predictive in the frozen API (engcore.adequacy is unchanged)",
    "no change to any V1 symbol, signature, default, enum, record schema, serialization or identity digest",
    "local-route validity thresholds are declared engineering thresholds validated on Battery B3, TCR, K2 and synthetic "
    "failure cases, not universal guarantees",
)
REQUIRED_SUITES = ("FAST", "FULL", "hybrid_uq_focused", "v1_thin_ridge_regressions", "api_snapshot_v1", "api_snapshot_v2",
                   "serialization", "dependency_layering", "freeze_manifest_v1", "freeze_manifest_v2", "certificate")


def repo_root(start: pathlib.Path) -> pathlib.Path:
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    raise SystemExit(f"no repository root above {start}")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def git(root: pathlib.Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check).stdout.strip()


# =====================================================================
# literal V2 fixture records (identity references; no numerics)
# =====================================================================

def fixture_records() -> dict[str, Any]:
    from engcore.hybrid_uq import (
        ApproximationClass, HybridUQResult, LocalGaussianPosterior, LocalSensitivity, MultistartPolicy, ParameterInterval,
        RouteClaim, RouteDecision, RouteDiagnostics, RouteReason, RoutedIdentifiability, RoutedPredictiveUncertainty,
        MODEL_DISCREPANCY_NOT_MODELLED, UNCERTAINTY_SOURCES,
    )
    from engcore.inference import IdentifiabilityReport, IdentifiabilityStatus

    sensitivity = LocalSensitivity(
        parameter_set_digest="a" * 64, parameter_names=("intercept", "slope"), inference_transforms=("identity", "log"),
        estimate=(1.5, 2.0), observation_keys=("x0:y", "x1:y", "x2:y"), observation_units=("volt", "volt", "volt"),
        observed=(1.5, 3.5, 5.5), sigma=(0.5, 0.5, 0.5), predicted=(1.5, 3.5, 5.5),
        jacobian=((1.0, 0.0), (1.0, 2.0), (1.0, 4.0)), steps=(0.25, 0.125), one_sided=(False, True),
        dataset_id="core-freeze-v2.fixture", evaluation_count=5)
    policy = MultistartPolicy(starts=4)
    diagnostics = RouteDiagnostics(
        parameters=2, observations=3, jacobian_rank=2, jacobian_condition=4.0, raw_jacobian_condition=8.0,
        newton_step_in_sd=(0.0, 0.0), at_bound=(), near_bound=("slope",), minimum_bound_distance_sd=2.5,
        nonlinearity_index=0.0, nonlinearity_probes_skipped=0, minimum_chi_square_rise=4.0,
        multistart=({"start": (0.5, 1.0), "status": "CALIBRATION_CONVERGED", "estimate": (1.5, 2.0), "chi_square": 0.0,
                     "mahalanobis_sq": 0.0, "classification": "SAME_OPTIMUM", "retractions": 0},),
        uniqueness="MULTISTART_NO_SECOND_MODE", thresholds={"nonlinearity_refuse": 0.5, "probe_sd": 2.0},
        evaluation_count=17, claim=RouteClaim.DOWNGRADED, refusals=(), downgrades=(RouteReason.BOUND_WITHIN_3_SD,))
    posterior = LocalGaussianPosterior(
        approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, parameter_names=("intercept", "slope"),
        parameter_units=("volt", "volt"), inference_transforms=("identity", "log"), parameterization="declared",
        parameterization_digest="b" * 64, estimate=(1.5, 2.0), inference_point=(1.5, 0.5), covariance=((0.25, 0.0), (0.0, 0.0625)),
        lower_bounds=(-10.0, -2.0), upper_bounds=(10.0, 2.0), diagnostics=diagnostics, sensitivity_digest="c" * 64,
        dataset_id="core-freeze-v2.fixture")
    interval = ParameterInterval(name="intercept", unit="volt", inference_transform="identity", estimate=1.5,
                                 inference_standard_uncertainty=0.5, lower=0.5, upper=2.5, confidence_level=0.95,
                                 approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION)
    report = IdentifiabilityReport(status=IdentifiabilityStatus.WEAKLY_IDENTIFIABLE, condition_number=4.0, max_abs_correlation=0.5,
                                   relative_widths=(0.5, 0.25), parameter_names=("intercept", "slope"), correlation_threshold=0.95,
                                   condition_threshold=1.0e6, width_threshold=1.0, why="fixture")
    identifiability = RoutedIdentifiability(approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION,
                                            parameterization_digest="b" * 64, route_claim=RouteClaim.DOWNGRADED, report=report)
    predictive = RoutedPredictiveUncertainty(
        observation_key="x3:y", unit="volt", approximation_class=ApproximationClass.LINEARIZED_PREDICTIVE_UQ, mean=7.5,
        parameter_standard_uncertainty=0.75, measurement_standard_uncertainty=1.0, total_standard_uncertainty=1.25,
        parameter_interval=(6.0, 9.0), total_interval=(5.0, 10.0), confidence_level=0.95, sources=UNCERTAINTY_SOURCES,
        model_discrepancy=MODEL_DISCREPANCY_NOT_MODELLED, posterior_digest="d" * 64, route_claim=RouteClaim.DOWNGRADED,
        reasons=(RouteReason.BOUND_WITHIN_3_SD,), predictive_nonlinearity=0.0)
    result = HybridUQResult(
        decision=RouteDecision.LOCAL_GAUSSIAN, approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION,
        claim=RouteClaim.DOWNGRADED, parameter_names=("intercept", "slope"), coordinates="inference", mean=(1.5, 0.5),
        covariance=((0.25, 0.0), (0.0, 0.0625)), local_posterior=posterior, grid_summary=None,
        considered=({"route": "GRID_AS_SUPPLIED", "outcome": "SKIPPED", "reason": "GRID_NOT_SUPPLIED"},
                    {"route": "LOCAL_GAUSSIAN_DOWNGRADED", "outcome": "USED", "reason": "BOUND_WITHIN_3_SD"}),
        identifiability=identifiability)
    return {"LocalSensitivity": sensitivity, "MultistartPolicy": policy, "RouteDiagnostics": diagnostics, "ParameterInterval": interval,
            "LocalGaussianPosterior": posterior, "RoutedIdentifiability": identifiability, "RoutedPredictiveUncertainty": predictive,
            "HybridUQResult": result}


def serialization_facts() -> dict[str, Any]:
    from engcore.hybrid_uq import HybridUQError

    inventory = {}
    for name, record in sorted(fixture_records().items()):
        payload = record.to_dict()
        first = canonical(payload)
        again = type(record).from_dict(json.loads(first.decode("utf-8")))
        round_trip = canonical(again.to_dict()) == first
        refused = []
        stem, _, version = payload["schema"].rpartition("/")
        for bad in (f"{stem}/{int(version) + 1}", None):
            try:
                type(record).from_dict(dict(payload, schema=bad))
                refused.append(False)
            except HybridUQError:
                refused.append(True)
        inventory[name] = {"schema": payload["schema"], "round_trip_byte_identical": round_trip, "unknown_schema_refused": all(refused),
                           "canonical_sha256": sha256_bytes(first), "identity_digest": getattr(record, "digest", None)}
    return inventory


def api_facts() -> dict[str, Any]:
    from engcore import api_snapshot as A

    v1 = A.build()
    v2 = A.build(modules=A.V2_CANONICAL_MODULES)
    v1_frozen = {(e["module"], e["name"]): e for e in A.frozen_only(v1)["symbols"]}
    v2_frozen = {(e["module"], e["name"]): e for e in A.frozen_only(v2)["symbols"]}
    preserved = all(key in v2_frozen and canonical(v2_frozen[key]) == canonical(entry) for key, entry in v1_frozen.items())
    added = sorted(f"{m}.{n}" for (m, n) in v2_frozen if (m, n) not in v1_frozen)
    return {
        "v1": {"frozen_digest": A.frozen_digest(v1), "frozen_count": A.frozen_only(v1)["symbol_count"], "total_count": v1["symbol_count"],
               "modules": list(A.CANONICAL_MODULES)},
        "v2": {"frozen_digest": A.frozen_digest(v2), "frozen_count": A.frozen_only(v2)["symbol_count"], "total_count": v2["symbol_count"],
               "experimental_count": v2["experimental_count"], "modules": list(A.V2_CANONICAL_MODULES), "added_modules": list(A.V2_ADDED_MODULES),
               "added_frozen_symbols": added},
        "v1_entries_byte_identical_in_v2": preserved,
    }


def vocabulary_facts() -> dict[str, Any]:
    from engcore.hybrid_uq import ApproximationClass, RouteClaim, RouteDecision, RouteReason, UNCERTAINTY_SOURCES, GRID_ROUTE_MAXIMUM_PARAMETERS

    return {
        "approximation_classes": {m.value: {"exact_posterior": m.exact_posterior, "describes": m.describes} for m in ApproximationClass},
        "route_claims": [m.value for m in RouteClaim], "route_decisions": [m.value for m in RouteDecision],
        "route_reasons": {m.value: m.severity.value for m in RouteReason}, "uncertainty_sources": list(UNCERTAINTY_SOURCES),
        "grid_route_maximum_parameters": GRID_ROUTE_MAXIMUM_PARAMETERS,
    }


def repair_facts(root: pathlib.Path) -> dict[str, Any]:
    from engcore.inference import calibration as cal

    return {"aliasing_number_minimum": cal._ALIASING_NUMBER_MINIMUM,
            "is_two_ln_100": cal._ALIASING_NUMBER_MINIMUM is not None and math.isclose(cal._ALIASING_NUMBER_MINIMUM, 2.0 * math.log(100.0), rel_tol=0, abs_tol=1e-15),
            "errata": "benchmarks/core_v1_thin_ridge_repair/ERRATA.md",
            "errata_present": (root / "benchmarks" / "core_v1_thin_ridge_repair" / "ERRATA.md").exists()}


def pinned_facts(root: pathlib.Path) -> dict[str, str]:
    return {rel: sha256_bytes((root / rel).read_bytes()) for rel in PINNED_V2_FILES}


def certificate_facts(root: pathlib.Path) -> dict[str, Any]:
    from tools.certification import core_certificate as cc

    certificate = cc.load_certificate(root / cc_path(cc))
    result = cc.verify_certificate(root, certificate, require_clean=False, require_commit=False)
    areas = certificate.get("manifest", {}).get("areas", {})
    return {"verifies": bool(result.ok), "aggregate_digest": certificate.get("manifest", {}).get("aggregate_digest"),
            "certified_areas": sorted(areas), "hybrid_uq_certified": any("src/engcore/hybrid_uq/**/*.py" in a.get("patterns", ()) for a in areas.values()),
            "certified_commit": certificate.get("repository", {}).get("commit")}


def cc_path(cc) -> str:
    return "certification/current_core_v2.json"


# =====================================================================
# build and verify
# =====================================================================

def build_manifest(root: pathlib.Path, candidate: str) -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA, "freeze": {"name": "Core Freeze V2", "tag": TAG, "candidate_commit": candidate,
                                             "baseline_v1_repaired": "7519aee559750f51bfc58aea12ab29ec199743f4",
                                             "additive_over": "Core Freeze V1 (v1.0-core-freeze), with the certified thin-ridge repair"},
        "v1_manifest_sha256": sha256_bytes((root / V1_MANIFEST_PATH).read_bytes()),
        "api": api_facts(), "pinned_v2_snapshot_files": pinned_facts(root), "serialization_inventory": serialization_facts(),
        "vocabulary": vocabulary_facts(), "v1_repair": repair_facts(root), "certificate": certificate_facts(root),
        "capability_claim": CAPABILITY_CLAIM, "non_claims": list(NON_CLAIMS),
        "references": {"api_design": "docs/CORE_V2_API_DESIGN.md", "policy": "docs/CORE_FREEZE_POLICY.md",
                       "round": "benchmarks/core_v2_hybrid_uq", "verifier": "tools/certification/core_freeze_v2.py",
                       "manifest_tests": "tests/test_core_freeze_v2_manifest.py", "v1_verifier": "tools/certification/core_freeze.py"},
    }


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    binding: bool = True


@dataclass
class Verification:
    mode: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name, ok, detail="", binding=True):
        self.checks.append(Check(name, bool(ok), str(detail), binding))

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.binding)

    def render(self) -> str:
        lines = [f"mode: {self.mode}"]
        for c in self.checks:
            tag = ("PASS" if c.ok else "FAIL") if c.binding else "info"
            lines.append(f"  {tag:4}  {c.name}" + (f" -- {c.detail}" if c.detail else ""))
        lines.append("OK" if self.ok else "FAILED")
        return "\n".join(lines)


def verify(root: pathlib.Path, *, require_clean: bool = True, require_assurance: bool = True) -> Verification:
    from tools.certification import core_freeze as v1

    manifest_file = root / MANIFEST_PATH
    if not manifest_file.exists():
        v = Verification(mode="NO_MANIFEST")
        v.add("manifest.present", False, MANIFEST_PATH)
        return v
    manifest = json.loads(manifest_file.read_bytes())
    head = git(root, "rev-parse", "HEAD")
    candidate = manifest.get("freeze", {}).get("candidate_commit", "")
    exact = head == candidate
    descends = bool(candidate) and subprocess.run(["git", "merge-base", "--is-ancestor", candidate, head], cwd=root).returncode == 0
    v = Verification(mode="EXACT_FREEZE" if exact else ("DESCENDANT" if descends else "UNRELATED"))
    v.add("manifest.schema", manifest.get("schema") == MANIFEST_SCHEMA, manifest.get("schema"))
    clean = git(root, "status", "--porcelain") == ""
    v.add("tree.clean", clean or not require_clean, "" if clean else "uncommitted changes")
    v.add("tree.relation", v.mode in ("EXACT_FREEZE", "DESCENDANT"), f"candidate {candidate[:12]}, HEAD {head[:12]}")

    v1_result = v1.verify(root, require_clean=require_clean)
    v.add("v1.freeze_verifies", v1_result.ok, f"Core Freeze V1 verifier mode {v1_result.mode}")
    v.add("v1.manifest_unchanged", sha256_bytes((root / V1_MANIFEST_PATH).read_bytes()) == manifest.get("v1_manifest_sha256"))

    live_api = api_facts()
    v.add("v1.symbols_preserved", live_api["v1"]["frozen_digest"] == V1_FROZEN_DIGEST and live_api["v1"]["frozen_count"] == V1_FROZEN_COUNT
          and live_api["v1_entries_byte_identical_in_v2"], f"{live_api['v1']['frozen_count']} V1 frozen symbols, digest {live_api['v1']['frozen_digest'][:12]}")
    v.add("v2.api", live_api == manifest.get("api"), "" if live_api == manifest.get("api") else "live V2 API facts differ from the manifest")
    pinned_ok = pinned_facts(root) == manifest.get("pinned_v2_snapshot_files")
    from engcore import api_snapshot as A
    pinned_frozen = json.loads((root / PINNED_V2_FILES[0]).read_bytes())
    pinned_digest_ok = sha256_bytes(A.canonical_bytes(pinned_frozen)) == live_api["v2"]["frozen_digest"]
    v.add("v2.pinned_snapshot_bytes", pinned_ok and pinned_digest_ok, "pinned V2 snapshot files and their frozen digest")
    live_ser = serialization_facts()
    ser_ok = live_ser == manifest.get("serialization_inventory") and all(
        e["round_trip_byte_identical"] and e["unknown_schema_refused"] for e in live_ser.values())
    v.add("v2.serialization_and_identity", ser_ok, f"{len(live_ser)} records")
    v.add("v2.vocabulary", vocabulary_facts() == manifest.get("vocabulary"))
    v.add("v2.no_exact_posterior", not any(c["exact_posterior"] for c in vocabulary_facts()["approximation_classes"].values()))
    repair = repair_facts(root)
    v.add("v1.thin_ridge_repair_in_force", repair["is_two_ln_100"] and repair["errata_present"], f"threshold {repair['aliasing_number_minimum']}")
    cert = certificate_facts(root)
    v.add("certificate.verifies", cert["verifies"])
    v.add("certificate.covers_hybrid_uq", cert["hybrid_uq_certified"])
    v.add("certificate.identity", cert["aggregate_digest"] == manifest.get("certificate", {}).get("aggregate_digest"),
          f"manifest {str(manifest.get('certificate', {}).get('aggregate_digest'))[:12]} / live {str(cert['aggregate_digest'])[:12]}",
          binding=exact)

    assurance_file = root / ASSURANCE_PATH
    if assurance_file.exists():
        assurance = json.loads(assurance_file.read_bytes())
        v.add("assurance.schema", assurance.get("schema") == ASSURANCE_SCHEMA)
        v.add("assurance.manifest_sha256", assurance.get("manifest_sha256") == sha256_bytes(manifest_file.read_bytes()))
        v.add("assurance.candidate_matches", assurance.get("candidate_commit") == candidate)
        suites = assurance.get("suites", {})
        missing = [s for s in REQUIRED_SUITES if s not in suites]
        red = [s for s, r in suites.items() if s in REQUIRED_SUITES and not r.get("green")]
        v.add("assurance.required_suites_green", not missing and not red, f"missing {missing} red {red}")
        mut = assurance.get("mutations", {})
        v.add("assurance.certified_79", mut.get("certified_79", {}).get("killed") == 79 and mut.get("certified_79", {}).get("control") == "GREEN")
        hd = mut.get("hd_matrix", {})
        v.add("assurance.hd_matrix", hd.get("total", 0) >= 10 and hd.get("killed") == hd.get("total") and hd.get("control") == "GREEN",
              f"{hd.get('killed')}/{hd.get('total')}")
        v.add("assurance.wheel_parity", assurance.get("wheel", {}).get("v2_frozen_api_parity") == "MATCH"
              and assurance.get("wheel", {}).get("v1_frozen_api_parity") == "MATCH")
    else:
        v.add("assurance.present", False, "no assurance record yet: a CANDIDATE, not a completed freeze", binding=require_assurance)
    return v


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--candidate")
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    root = repo_root(pathlib.Path(__file__).resolve().parent)
    if str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    if args.build:
        if not args.candidate:
            raise SystemExit("--build needs --candidate <commit>")
        if git(root, "status", "--porcelain") and not args.allow_dirty:
            raise SystemExit("refusing to build a freeze manifest from a dirty tree")
        manifest = build_manifest(root, git(root, "rev-parse", args.candidate))
        (root / MANIFEST_PATH).write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(f"wrote {MANIFEST_PATH}\n  V2 frozen digest {manifest['api']['v2']['frozen_digest']}\n  V2 frozen symbols {manifest['api']['v2']['frozen_count']}")
        return 0
    result = verify(root, require_clean=not args.allow_dirty)
    print(result.render())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
