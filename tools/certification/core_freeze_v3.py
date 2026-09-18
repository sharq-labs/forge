"""Core Freeze V3: the hardened routed-uncertainty contract after the main adversarial audit.

    python -m tools.certification.core_freeze_v3 --build --candidate <commit>
    python -m tools.certification.core_freeze_v3 --verify

WHY A THIRD FREEZE
------------------
The main adversarial audit (2026-09-15) found Core V2 records that were accepted while contradicting
their own numbers: a serialized ``HybridUQResult`` could report IDENTIFIABLE beside a covariance
correlated at -0.85, a ``RouteDiagnostics`` could claim SUPPORTED with a nonlinearity index of 7.5,
and a one-start multistart earned SUPPORTED on a bimodal posterior (HUQ-01, HUQ-09, HUQ-12, HUQ-14).
The fixes re-derive every claim from the carried numbers on read. The literal fixture records that
Core Freeze V2 pins as its identity references are exactly such records -- a DOWNGRADED route with
missing thresholds and a uniqueness its starts do not imply -- so they are now refused, and the V2
serialization inventory can never again be reproduced by a correct tree. A review that finds a
change incompatible makes it a new freeze, not a compatible one (CORE_FREEZE_POLICY section 10).

WHAT V3 IS, EXACTLY
-------------------
* **Core Freeze V1 still verifies**, unchanged: the V1 manifest, assurance and tag are untouched, the
  194 frozen V1 symbols and their digest do not move, and V1's serialization contract holds.
* **V2 history is not rewritten.** ``certification/core_freeze_v2.json`` stays byte-identical and is
  recorded here by digest; its verifier binds only on its own freeze commit. V3 supersedes its
  contract for descendants.
* **The frozen API surface does not move.** The V2 frozen digest, counts and pinned V2 snapshot
  bytes are required to be exactly the ones Core Freeze V2 recorded: the audit fixes changed
  behaviour and records, not shapes. Deferred shape changes (applicability fields on inference
  results, content-bound posterior checks, an issuer field on validation checks, execution bindings
  on consensus records) are listed as non-claims, not smuggled in.
* **A new serialization inventory**: identity references of literal records that are consistent
  with their own numbers, and that the hardened readers therefore accept.
* **Certificate coverage** of every area the audit found a false accept in: routed uncertainty, the
  predictive representation it calls, execution trust, and the SRIA admission chain.
* **Assurance** records the formal mutation population (GUARDS 1-35) and the trust-hardening
  population, each with a green control and every mutant attributed to the guard it names.

On the freeze commit every check binds; on a later commit the contract checks still bind, and a
commit that fails one is not a descendant of Core Freeze V3.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any, Sequence

from tools.certification import core_freeze_v2 as v2

MANIFEST_SCHEMA = "engcore.core_freeze/3"
ASSURANCE_SCHEMA = "engcore.core_freeze_assurance/3"
MANIFEST_PATH = "certification/core_freeze_v3.json"
ASSURANCE_PATH = "certification/core_freeze_v3_assurance.json"
REPORT_PATH = "certification/CORE_FREEZE_V3.md"
V2_MANIFEST_PATH = v2.MANIFEST_PATH
V1_MANIFEST_PATH = v2.V1_MANIFEST_PATH
TAG = "v3.0-core-freeze"
FIXTURE_DATASET = "core-freeze-v3.fixture"

#: Certificate areas V3 requires. Each is an area in which the main audit found a false accept or an
#: assurance blind spot; a certificate that stops covering one of them is not a V3 certificate.
REQUIRED_CERTIFICATE_AREAS = (
    "assurance_admission",
    "core",
    "evidence_identity",
    "execution_trust",
    "inference_admission",
    "predictive_representation",
    "routed_uncertainty",
)

SUPERSEDES_V2_BECAUSE = (
    "HUQ-09/HUQ-12: serialized Hybrid UQ records re-derive identifiability, refusals and downgrades from their "
    "carried numbers on read; the V2 fixture RouteDiagnostics omits canonical thresholds and declares a "
    "uniqueness and downgrade set its own starts do not imply, so it is refused",
    "HUQ-01: the multistart policy actually used is committed in the diagnostics digest and a search below the "
    "minimum is at most DOWNGRADED; every V2 identity reference built over diagnostics moves",
    "HUQ-14: RoutedIdentifiability's digest covers its `why` text, which must follow from its numbers",
    "HUQ-04: the grid digest covers the log-likelihood and admissible mask the resolution checks read",
)

CAPABILITY_CLAIM = (
    "Core V3 keeps Core V2's routed uncertainty surface and makes each route's claim a function of evidence the "
    "record carries. route_uncertainty returns, deterministically and with every route it considered recorded: "
    "POSTERIOR_GRID when a supplied tensor grid of at most 5 parameters, bound to the request's parameter names "
    "and dataset and whose weights are the normalized likelihood, passes the repaired V1 resolution checks "
    "(a collapsed posterior is refused before any small-grid waiver); LOCAL_GAUSSIAN_APPROXIMATION "
    "(N(z_hat, (Jw^T Jw)^-1) in declared inference coordinates) when its validity diagnostics support it, which "
    "costs 4p+1+2p^2 forward evaluations for the axis and pairwise-diagonal probes plus a deterministic "
    "multistart of at least max(6, 2p+2) starts -- below that search the route is at most DOWNGRADED, and a "
    "converged refit below the estimate's objective refuses; POSTERIOR_GRID rebuilt from the local covariance "
    "when a rebuild policy is supplied, p <= 5, the rebuilt table agrees with the forward model at deterministic "
    "spot-check nodes and the rebuilt grid is accepted by the V1 checks; the local Gaussian DOWNGRADED with its "
    "reasons; or REFUSED with no numbers. Identifiability widths of log parameters are unit-invariant. Predictive "
    "uncertainty keeps parameter and measurement uncertainty separate, probes pairwise diagonals and the "
    "direction Sigma*grad g, judges nonlinearity against the parameter uncertainty, and names model discrepancy "
    "as not modelled. Every record is re-derived from its carried numbers on read. No approximation class is an "
    "exact posterior."
)

NON_CLAIMS = (
    "not an exact posterior, in any route",
    "not a proof of global mode uniqueness: the multistart bounds it, it does not prove it",
    "no model-discrepancy estimate, no estimated noise, no non-Gaussian likelihoods, no informative priors",
    "no MCMC, Laplace-with-full-Hessian, sparse-grid or importance-sampling posterior",
    "no grid route above 5 parameters; no resolution check for non-tensor or linearly mapped point sets (refused)",
    "rebuilt-table verification is a deterministic spot check at a fixed set of nodes, not an exhaustive comparison",
    "serialized digests are integrity checks against accidental edits, not authority: a forger can recompute them; "
    "authority comes from re-deriving each claim from the carried numbers",
    "DEFERRED (compatibility review, no shape change in V3): CalibrationResult, PosteriorGrid and "
    "QuantifiedPredictiveResult carry no applicability field; applicability is enforced only by the study-layer "
    "held-out and prediction gates",
    "DEFERRED: require_posterior_was_fitted_here and assess_predictive_observation bind a posterior to its data by "
    "label; content binding is enforced only in the study layer",
    "DEFERRED: ValidationCheck carries no field tying a level to the result it qualifies; strongest levels need an "
    "issuer record in evidence, weaker levels can still be hand-built",
    "DEFERRED: CrossSolverConsensus execution bindings are a private attribute under schema /3, not a dataclass field",
    "local-route validity thresholds are declared engineering thresholds, not universal guarantees",
)

REQUIRED_SUITES = ("FAST", "hybrid_uq_focused", "audit_regressions", "api_snapshot_v1", "api_snapshot_v2",
                   "freeze_manifest_v1", "freeze_manifest_v3", "certificate")


# =====================================================================
# literal V3 fixture records (identity references; consistent with their own numbers)
# =====================================================================

def fixture_records() -> dict[str, Any]:
    from scipy.stats import norm

    from engcore.hybrid_uq import (
        ApproximationClass, HybridUQResult, LocalGaussianPosterior, LocalSensitivity, MultistartPolicy, ParameterInterval,
        RouteClaim, RouteDecision, RouteDiagnostics, RouteReason, RoutedPredictiveUncertainty,
        MODEL_DISCREPANCY_NOT_MODELLED, UNCERTAINTY_SOURCES, assess_routed_identifiability,
    )

    sensitivity = LocalSensitivity(
        parameter_set_digest="a" * 64, parameter_names=("intercept", "slope"), inference_transforms=("identity", "log"),
        estimate=(1.5, 2.0), observation_keys=("x0:y", "x1:y", "x2:y"), observation_units=("volt", "volt", "volt"),
        observed=(1.5, 3.5, 5.5), sigma=(0.5, 0.5, 0.5), predicted=(1.5, 3.5, 5.5),
        jacobian=((1.0, 0.0), (1.0, 2.0), (1.0, 4.0)), steps=(0.25, 0.125), one_sided=(False, True),
        dataset_id=FIXTURE_DATASET, evaluation_count=5)
    policy = MultistartPolicy(starts=4)
    same = {"status": "CALIBRATION_CONVERGED", "estimate": (1.5, 1.0), "chi_square": 0.0, "mahalanobis_sq": 0.0,
            "classification": "SAME_OPTIMUM", "retractions": 0}
    starts = ((0.5, 1.0), (1.0, 0.5), (2.0, 1.5), (0.25, 0.75), (1.25, 1.25), (1.75, 0.25))
    thresholds = {"nonlinearity_downgrade": 0.1, "nonlinearity_refuse": 0.5, "bound_downgrade_sd": 3.0, "stationarity_sd": 0.05,
                  "at_bound_relative": 1.0e-6, "numerical_condition_limit": 67108864.0, "probe_sd": 2.0,
                  "multistart_starts": 6.0, "multistart_interior_fraction": 0.8, "multistart_max_evaluations": 2000.0,
                  "multistart_mode_separation_quantile": 0.999, "multistart_comparable_fit_quantile": 0.99,
                  "multistart_maximum_retractions": 12.0, "multistart_minimum_starts": 6.0}
    diagnostics = RouteDiagnostics(
        parameters=2, observations=3, jacobian_rank=2, jacobian_condition=4.0, raw_jacobian_condition=8.0,
        newton_step_in_sd=(0.0, 0.0), at_bound=(), near_bound=("slope",), minimum_bound_distance_sd=2.0,
        nonlinearity_index=0.0, nonlinearity_probes_skipped=0, minimum_chi_square_rise=4.0,
        multistart=tuple(dict(same, start=s) for s in starts),
        uniqueness="MULTISTART_NO_SECOND_MODE", thresholds=thresholds,
        evaluation_count=17, claim=RouteClaim.DOWNGRADED, refusals=(), downgrades=(RouteReason.BOUND_WITHIN_3_SD,))
    posterior = LocalGaussianPosterior(
        approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION, parameter_names=("intercept", "slope"),
        parameter_units=("volt", "volt"), inference_transforms=("identity", "log"), parameterization="declared",
        parameterization_digest="b" * 64, estimate=(1.5, 1.0), inference_point=(1.5, 0.0), covariance=((0.25, 0.0), (0.0, 0.0625)),
        lower_bounds=(-10.0, -0.5), upper_bounds=(10.0, 2.0), diagnostics=diagnostics, sensitivity_digest="c" * 64,
        dataset_id=FIXTURE_DATASET)
    interval = ParameterInterval(name="intercept", unit="volt", inference_transform="identity", estimate=1.5,
                                 inference_standard_uncertainty=0.5, lower=0.5, upper=2.5, confidence_level=0.95,
                                 approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION)
    identifiability = assess_routed_identifiability(posterior)
    q = float(norm.ppf(0.975))
    predictive = RoutedPredictiveUncertainty(
        observation_key="x3:y", unit="volt", approximation_class=ApproximationClass.LINEARIZED_PREDICTIVE_UQ, mean=7.5,
        parameter_standard_uncertainty=0.75, measurement_standard_uncertainty=1.0, total_standard_uncertainty=1.25,
        parameter_interval=(7.5 - q * 0.75, 7.5 + q * 0.75), total_interval=(7.5 - q * 1.25, 7.5 + q * 1.25), confidence_level=0.95,
        sources=UNCERTAINTY_SOURCES, model_discrepancy=MODEL_DISCREPANCY_NOT_MODELLED, posterior_digest="d" * 64,
        route_claim=RouteClaim.DOWNGRADED, reasons=(RouteReason.BOUND_WITHIN_3_SD,), predictive_nonlinearity=0.0)
    result = HybridUQResult(
        decision=RouteDecision.LOCAL_GAUSSIAN, approximation_class=ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION,
        claim=RouteClaim.DOWNGRADED, parameter_names=("intercept", "slope"), coordinates="inference", mean=(1.5, 0.0),
        covariance=((0.25, 0.0), (0.0, 0.0625)), local_posterior=posterior, grid_summary=None,
        considered=({"route": "GRID_AS_SUPPLIED", "outcome": "SKIPPED", "reason": "GRID_NOT_SUPPLIED"},
                    {"route": "LOCAL_GAUSSIAN_DOWNGRADED", "outcome": "USED", "reason": "BOUND_WITHIN_3_SD"}),
        identifiability=identifiability)
    return {"LocalSensitivity": sensitivity, "MultistartPolicy": policy, "RouteDiagnostics": diagnostics, "ParameterInterval": interval,
            "LocalGaussianPosterior": posterior, "RoutedIdentifiability": identifiability, "RoutedPredictiveUncertainty": predictive,
            "HybridUQResult": result}


def serialization_facts() -> dict[str, Any]:
    """V2's algorithm over V3's fixtures: byte-identical round trips, unknown schemas refused, identities."""
    from engcore.hybrid_uq import HybridUQError

    inventory = {}
    for name, record in sorted(fixture_records().items()):
        payload = record.to_dict()
        first = v2.canonical(payload)
        again = type(record).from_dict(json.loads(first.decode("utf-8")))
        round_trip = v2.canonical(again.to_dict()) == first
        refused = []
        stem, _, version = payload["schema"].rpartition("/")
        for bad in (f"{stem}/{int(version) + 1}", None):
            try:
                type(record).from_dict(dict(payload, schema=bad))
                refused.append(False)
            except HybridUQError:
                refused.append(True)
        inventory[name] = {"schema": payload["schema"], "round_trip_byte_identical": round_trip, "unknown_schema_refused": all(refused),
                           "canonical_sha256": v2.sha256_bytes(first), "identity_digest": getattr(record, "digest", None)}
    return inventory


def v2_fixtures_refused() -> dict[str, str]:
    """Which V2 identity-reference records the hardened readers now refuse, and why (the supersession, measured)."""
    refused = {}
    try:
        v2.fixture_records()
    except Exception as exc:  # noqa: BLE001 - the claim is that construction refuses, whatever the class
        refused["fixture_records"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    return refused


def certificate_facts(root: pathlib.Path) -> dict[str, Any]:
    from tools.certification import core_certificate as cc

    certificate = cc.load_certificate(root / "certification/current_core_v2.json")
    result = cc.verify_certificate(root, certificate, require_clean=False, require_commit=False)
    areas = certificate.get("manifest", {}).get("areas", {})
    return {"verifies": bool(result.ok), "certified_areas": sorted(areas),
            "missing_required_areas": sorted(set(REQUIRED_CERTIFICATE_AREAS) - set(areas)),
            "live_scope_areas": sorted(a.name for a in cc.SCOPE)}


# =====================================================================
# build and verify
# =====================================================================

def build_manifest(root: pathlib.Path, candidate: str) -> dict[str, Any]:
    v2_manifest = json.loads((root / V2_MANIFEST_PATH).read_bytes())
    return {
        "schema": MANIFEST_SCHEMA,
        "freeze": {"name": "Core Freeze V3", "tag": TAG, "candidate_commit": candidate,
                   "additive_over": "Core Freeze V1 (v1.0-core-freeze), unchanged",
                   "supersedes": "Core Freeze V2 (v2.0-core-freeze) contract, for descendants; V2 history untouched"},
        "v1_manifest_sha256": v2.sha256_bytes((root / V1_MANIFEST_PATH).read_bytes()),
        "v2_manifest_sha256": v2.sha256_bytes((root / V2_MANIFEST_PATH).read_bytes()),
        "supersedes_v2_because": list(SUPERSEDES_V2_BECAUSE),
        "v2_fixtures_refused": v2_fixtures_refused(),
        "api": v2.api_facts(),
        "api_identical_to_v2_manifest": v2.api_facts() == v2_manifest.get("api"),
        "pinned_v2_snapshot_files": v2.pinned_facts(root),
        "serialization_inventory": serialization_facts(),
        "vocabulary": v2.vocabulary_facts(),
        "v1_repair": v2.repair_facts(root),
        "certificate": {"required_areas": list(REQUIRED_CERTIFICATE_AREAS),
                        "issued_by": "the recertify workflow's certificate-only child"},
        "capability_claim": CAPABILITY_CLAIM,
        "non_claims": list(NON_CLAIMS),
        "references": {"audit": "docs/audits/MAIN_AUDIT_2026-09-15.md", "policy": "docs/CORE_FREEZE_POLICY.md",
                       "verifier": "tools/certification/core_freeze_v3.py", "manifest_tests": "tests/test_core_freeze_v3_manifest.py",
                       "v1_verifier": "tools/certification/core_freeze.py", "superseded_v2_verifier": "tools/certification/core_freeze_v2.py"},
    }


def verify(root: pathlib.Path, *, require_clean: bool = True, require_assurance: bool = True) -> v2.Verification:
    from tools.certification import core_freeze as v1
    from tools.certification import mutation_population as formal

    manifest_file = root / MANIFEST_PATH
    if not manifest_file.exists():
        v = v2.Verification(mode="NO_MANIFEST")
        v.add("manifest.present", False, MANIFEST_PATH)
        return v
    manifest = json.loads(manifest_file.read_bytes())
    head = v2.git(root, "rev-parse", "HEAD")
    candidate = manifest.get("freeze", {}).get("candidate_commit", "")
    exact = head == candidate
    descends = bool(candidate) and subprocess.run(["git", "merge-base", "--is-ancestor", candidate, head], cwd=root).returncode == 0
    v = v2.Verification(mode="EXACT_FREEZE" if exact else ("DESCENDANT" if descends else "UNRELATED"))
    v.add("manifest.schema", manifest.get("schema") == MANIFEST_SCHEMA, manifest.get("schema"))
    clean = v2.git(root, "status", "--porcelain") == ""
    v.add("tree.clean", clean or not require_clean, "" if clean else "uncommitted changes")
    v.add("tree.relation", v.mode in ("EXACT_FREEZE", "DESCENDANT"), f"candidate {candidate[:12]}, HEAD {head[:12]}")

    v1_result = v1.verify(root, require_clean=require_clean)
    v.add("v1.freeze_verifies", v1_result.ok, f"Core Freeze V1 verifier mode {v1_result.mode}")
    v.add("v1.manifest_unchanged", v2.sha256_bytes((root / V1_MANIFEST_PATH).read_bytes()) == manifest.get("v1_manifest_sha256"))
    v.add("v2.history_unchanged", v2.sha256_bytes((root / V2_MANIFEST_PATH).read_bytes()) == manifest.get("v2_manifest_sha256"),
          "the V2 manifest is a record of its own freeze and is never rewritten")

    live_api = v2.api_facts()
    v.add("v1.symbols_preserved", live_api["v1"]["frozen_digest"] == v2.V1_FROZEN_DIGEST and live_api["v1"]["frozen_count"] == v2.V1_FROZEN_COUNT
          and live_api["v1_entries_byte_identical_in_v2"], f"{live_api['v1']['frozen_count']} V1 frozen symbols")
    v2_manifest = json.loads((root / V2_MANIFEST_PATH).read_bytes())
    v.add("api.unchanged_from_v2", live_api == v2_manifest.get("api") and live_api == manifest.get("api"),
          "V3 moves no frozen shape: the live surface equals what Core Freeze V2 recorded")
    pinned_ok = v2.pinned_facts(root) == manifest.get("pinned_v2_snapshot_files") == v2_manifest.get("pinned_v2_snapshot_files")
    v.add("api.pinned_snapshot_bytes", pinned_ok, "pinned V2 snapshot files unchanged since Core Freeze V2")

    # SUPERSEDED BY V4, and REPORTED rather than raised (I-29, R-70's shape one level up). The
    # 2026-09-16 scientific core re-audit made a `route_diagnostics/1` record that names no
    # thresholds and carries a nan chi-square minimum refuse on read -- and V3's own identity
    # references are exactly such records, so `serialization_facts()` now RAISES from inside this
    # verifier. It used to take the whole process down with a traceback, which says nothing about
    # which contract holds: a verifier's job is to report that this tree is not a V3 tree and why.
    try:
        live_ser = serialization_facts()
    except BaseException as refusal:  # noqa: BLE001 - the refusal IS the supersession, and is named
        name = f"{type(refusal).__module__}.{type(refusal).__qualname__}"
        v.add("v3.serialization_and_identity", False,
              f"superseded by Core Freeze V4: this tree refuses V3's own identity references "
              f"({name}: {str(refusal)[:200]})")
        v.add("v3.v2_fixtures_still_refused", bool(v2_fixtures_refused()),
              "the hardened readers must keep refusing the self-contradicting V2 identity references")
    else:
        ser_ok = live_ser == manifest.get("serialization_inventory") and all(
            e["round_trip_byte_identical"] and e["unknown_schema_refused"] for e in live_ser.values())
        v.add("v3.serialization_and_identity", ser_ok, f"{len(live_ser)} records")
        v.add("v3.v2_fixtures_still_refused", bool(v2_fixtures_refused()),
              "the hardened readers must keep refusing the self-contradicting V2 identity references")
    v.add("v3.vocabulary", v2.vocabulary_facts() == manifest.get("vocabulary"))
    v.add("v3.no_exact_posterior", not any(c["exact_posterior"] for c in v2.vocabulary_facts()["approximation_classes"].values()))
    repair = v2.repair_facts(root)
    v.add("v1.thin_ridge_repair_in_force", repair["is_two_ln_100"] and repair["errata_present"], f"threshold {repair['aliasing_number_minimum']}")

    cert = certificate_facts(root)
    v.add("certificate.verifies", cert["verifies"])
    missing_scope = sorted(set(REQUIRED_CERTIFICATE_AREAS) - set(cert["live_scope_areas"]))
    v.add("certificate.scope_covers_required_areas", not missing_scope, f"missing from SCOPE {missing_scope}")
    v.add("certificate.covers_required_areas", not cert["missing_required_areas"], f"missing {cert['missing_required_areas']}")

    assurance_file = root / ASSURANCE_PATH
    if assurance_file.exists():
        assurance = json.loads(assurance_file.read_bytes())
        v.add("assurance.schema", assurance.get("schema") == ASSURANCE_SCHEMA)
        v.add("assurance.manifest_sha256", assurance.get("manifest_sha256") == v2.sha256_bytes(manifest_file.read_bytes()))
        v.add("assurance.candidate_matches", assurance.get("candidate_commit") == candidate)
        suites = assurance.get("suites", {})
        missing = [s for s in REQUIRED_SUITES if s not in suites]
        red = [s for s, r in suites.items() if s in REQUIRED_SUITES and not r.get("green")]
        v.add("assurance.required_suites_green", not missing and not red, f"missing {missing} red {red}")
        mut = assurance.get("mutations", {})
        population = formal.canonical_population(root)
        fm = mut.get("formal", {})
        v.add("assurance.formal_population",
              fm.get("control") == "GREEN" and fm.get("population_sha256") == population.sha256
              and fm.get("killed") == population.count == formal.EXPECTED_FORMAL_POPULATION,
              f"{fm.get('killed')}/{population.count}")
        tr = mut.get("trust", {})
        v.add("assurance.trust_population", tr.get("control") == "GREEN" and tr.get("killed") == tr.get("population", -1) > 0,
              f"{tr.get('killed')}/{tr.get('population')}")
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
    root = v2.repo_root(pathlib.Path(__file__).resolve().parent)
    if str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    if args.build:
        if not args.candidate:
            raise SystemExit("--build needs --candidate <commit>")
        if v2.git(root, "status", "--porcelain") and not args.allow_dirty:
            raise SystemExit("refusing to build a freeze manifest from a dirty tree")
        manifest = build_manifest(root, v2.git(root, "rev-parse", args.candidate))
        (root / MANIFEST_PATH).write_bytes(json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        print(f"wrote {MANIFEST_PATH}\n  frozen digest (unchanged from V2) {manifest['api']['v2']['frozen_digest']}")
        return 0
    result = verify(root, require_clean=not args.allow_dirty)
    print(result.render())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
