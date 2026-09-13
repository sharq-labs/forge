"""Core Gap Review, Phases 2, 3 and 8: the requirement, the existing primitives, and compatibility.

Read-only. Reads the live API snapshot, the freeze verifier's binding checks and
the certificate's scope from the frozen tooling itself; edits nothing.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import pathlib


def run(R):
    root = R.ROOT
    from engcore import api_snapshot
    from tools.certification import core_certificate, core_freeze

    snap = api_snapshot.snapshot() if hasattr(api_snapshot, "snapshot") else None
    frozen_file = json.loads((root / "tests/api/frozen_api_snapshot.json").read_text(encoding="utf-8"))
    full_file = json.loads((root / "tests/api/full_api_snapshot.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / core_freeze.MANIFEST_PATH).read_text(encoding="utf-8"))

    def exports(module):
        import importlib
        return sorted(getattr(importlib.import_module(module), "__all__", ()))

    freeze_src = (root / "tools/certification/core_freeze.py").read_text(encoding="utf-8").splitlines()
    cert_src = (root / "tools/certification/core_certificate.py").read_text(encoding="utf-8").splitlines()

    def line_of(lines, needle):
        return next((i + 1 for i, l in enumerate(lines) if needle in l), None)

    scope = [{"area": a.name, "classification": a.classification, "patterns": list(a.patterns)} for a in core_certificate.SCOPE]
    return {
        "schema": "core_gap_hd_uq_compatibility/1",
        "phase2_generic_requirement": {
            "given": [
                "a converged bounded weighted-least-squares calibration estimate (engcore.inference.calibrate)",
                "the caller-supplied forward evaluator calibrate already takes (vector -> admitted Quantities, or None when inadmissible)",
                "observation values and declared sigmas (ObservationSet)",
                "parameter identities with bounds and transforms (CalibrationParameterSet)",
                "optionally: a predictive evaluator and declared observation sigmas for the predicted quantities",
            ],
            "produce": [
                "covariance, correlations, marginal intervals under a NAMED approximation class",
                "identifiability diagnostics under the frozen thresholds, in the declared parameterization",
                "linearized predictive mean, parameter sd and total sd under a NAMED approximation class",
                "explicit refusals/downgrades: rank, residual dof, numerical conditioning, active or near bounds, non-stationarity, nonlinearity along principal axes, predictive nonlinearity, and a global-uniqueness status",
            ],
            "cost_requirement": "O(p) forward evaluations for the approximation plus O(p) for its diagnostics; never m^p",
            "not_required_by_B3": [
                "full-Hessian Laplace (O(p^2) evaluations): B3's forms are affine, where Gauss-Newton is exact",
                "MCMC or any sampler as the primary route",
                "sparse or adaptive grids",
                "non-Gaussian likelihoods, model discrepancy, hierarchical priors",
                "automatic differentiation",
            ],
            "must_not": [
                "claim equivalence to POSTERIOR_GRID or call the result an exact posterior",
                "reuse QuantifiedPredictiveResult: its posterior_support_size (>= 1) is a grid concept",
                "reuse assess_identifiability: it takes a PosteriorGrid and raises GridResolutionError on grid geometry",
                "silently change grid-based behaviour",
            ],
        },
        "phase3_existing_primitives": {
            "calibrate": {"where": "engcore.inference.calibration.calibrate", "reusable": "estimate, residuals, provenance; takes a vector evaluator",
                          "gap": "scipy least_squares' Jacobian (outcome.jac) is discarded; uncertainty_method is a free-text provenance string (default 'grid_posterior_covariance') with no computation behind any other value"},
            "posterior": {"where": "engcore.inference.grid.PosteriorGrid / gaussian_grid_posterior", "reusable": "no: weights >= 0 over enumerated points, uniform prior over the supplied grid",
                          "gap": "the only covariance, correlation and marginal interval in the Core"},
            "identifiability": {"where": "engcore.inference.calibration.assess_identifiability", "reusable": "its THRESHOLDS and classification rule (width decides, correlation/condition corroborate)",
                                "gap": "input type is PosteriorGrid; diagnostics (ESS, occupied support, spacing/sd) are grid-geometric",
                                "frozen_default_thresholds": {k: v.default for k, v in inspect.signature(__import__("engcore.inference", fromlist=["assess_identifiability"]).assess_identifiability).parameters.items() if v.default is not inspect.Parameter.empty}},
            "parameters_and_transforms": {"where": "engcore.inference.parameters", "reusable": "ParameterIdentity, ParameterBounds (inclusive), ParameterTransform {IDENTITY, LOG}",
                                          "gap": "no Jacobian of the transform; no reparameterization map between parameter sets"},
            "predictive_uq": {"where": "engcore.uq.posterior_predictive_uq -> QuantifiedPredictiveResult", "reusable": "the Uncertainty record (kind, method, source) can name an approximation",
                              "gap": "input is PosteriorGrid + AdmittedForwardTable; result requires posterior_support_size >= 1"},
            "adequacy": {"where": "engcore.adequacy.assess_predictive_observation / PredictiveEvidenceIdentity", "reusable": "evidence identity is independent of the UQ method (fields: observation, value, unit, sigma, datasets, twin)",
                         "gap": "scoring takes PosteriorGrid + AdmittedForwardTable; no field records the approximation class of the predictive it scored"},
            "jacobian": {"where": "none numerical", "note": "engcore.scientific.consensus has a JACOBIAN route-independence label, not a derivative"},
            "hessian_fisher_laplace_sampling_sparse": {"where": "none", "note": "grep over scientific, data, inference, uq, adequacy, execution, studies"},
            "delta_method": {"where": "engcore.studies.tcr.ols_reference_estimate (EXPERIMENTAL)", "note": "closed-form 2-parameter OLS oracle for one study, not a general capability"},
            "execution": {"where": "engcore.execution.run_sweep", "reusable": "parallel forward evaluation for a Jacobian or probe set, from the studies layer only (layering: inference may not import execution)"},
        },
        "phase8_compatibility": {
            "live_api": {"frozen_count": frozen_file.get("frozen_count", len(frozen_file.get("symbols", []))),
                         "total_public": len(full_file.get("symbols", [])),
                         "frozen_digest_pinned_in_manifest": manifest.get("api", {}).get("frozen_digest") if isinstance(manifest.get("api"), dict) else None,
                         "canonical_modules": list(api_snapshot.CANONICAL_MODULES),
                         "how_symbols_are_enumerated": "api_snapshot iterates sorted(module.__all__) of each canonical module",
                         "citation": f"src/engcore/api_snapshot.py (for name in sorted(getattr(module, '__all__', ())))",
                         "current_exports": {m: len(exports(m)) for m in ("engcore.inference", "engcore.uq", "engcore.adequacy")}},
            "binding_checks_in_descendant_mode": {
                "contract.api": {"compares": ["frozen_digest", "frozen_count", "total_count", "experimental", "deprecated", "canonical_modules"],
                                 "citation": f"tools/certification/core_freeze.py:{line_of(freeze_src, 'v.add(\"contract.api\"')}"},
                "bytes.pinned_contract_files": {"files": list(core_freeze.PINNED_CONTRACT_FILES), "binding": True,
                                                "citation": f"tools/certification/core_freeze.py:{line_of(freeze_src, 'v.add(\"bytes.pinned_contract_files\"')}"},
                "experimental.visibly_classified": {"citation": f"tools/certification/core_freeze.py:{line_of(freeze_src, 'v.add(\"experimental.visibly_classified\"')}"},
                "certificate.verifies": {"citation": f"tools/certification/core_freeze.py:{line_of(freeze_src, 'v.add(\"certificate.verifies\"')}"},
            },
            "certificate_scope": scope,
            "certificate_out_of_scope": [{"path": p, "why": w} for p, w in core_certificate.OUT_OF_SCOPE],
            "insertion_paths": [
                {"path": "new PUBLIC symbols in engcore.inference / engcore.uq / engcore.adequacy (FROZEN)",
                 "effect": "frozen_digest, frozen_count, total_count move; tests/api/*_snapshot.json bytes change",
                 "v1_verifier": "FAILS contract.api and bytes.pinned_contract_files (both binding)",
                 "existing_callers": "unaffected (MINOR per docs/CORE_FREEZE_POLICY.md section 4)"},
                {"path": "new EXPERIMENTAL symbols in those modules",
                 "effect": "total_count and the experimental list move; full snapshot bytes change",
                 "v1_verifier": "FAILS contract.api and bytes.pinned_contract_files",
                 "existing_callers": "unaffected"},
                {"path": "new non-exported module under src/engcore/inference/ or adequacy/",
                 "effect": "API unchanged; a new .py file enters the CORE_CERTIFIED scope glob",
                 "v1_verifier": "FAILS certificate.verifies (binding) until a certificate is reissued through a certification round",
                 "existing_callers": "unaffected; but a non-exported name is 'internal ... carries no promise' (policy section 2): not a Core contract"},
                {"path": "new non-exported module under src/engcore/uq/",
                 "effect": "API unchanged; uq/** is OUT of certificate scope",
                 "v1_verifier": "PASSES",
                 "rejected_because": "the certificate excludes uq because it 'computes nothing a verdict rests on'; identifiability gates a scientific claim, so placing it there would pass the verifier by contradicting the certificate's own stated boundary, and it would still carry no API promise"},
                {"path": "domain or benchmark code (the B3 route, this probe)",
                 "effect": "no Core change", "v1_verifier": "PASSES",
                 "limitation": "not Core-certified and duplicated per domain: the gap itself"},
            ],
            "what_would_NOT_change": {
                "existing frozen symbols and signatures": "unchanged (purely additive)",
                "serialization of existing records": "unchanged; new records would need their own schema strings",
                "scientific identity / material digests": "unchanged",
                "evidence identity": "unchanged: PredictiveEvidenceIdentity has no method field, so a local-Gaussian assessment and a grid assessment of the same observation share identity; the new assessment type must carry its approximation class beside it",
                "grid-based behaviour": "unchanged: the grid route is not modified",
                "trust/admission semantics": "unchanged for grid rows; the new route must also refuse inadmissible forward points (None) exactly as calibrate does",
            },
            "semantic_classification": "ADDITIVE / MINOR: no existing call, record, digest or verdict changes",
            "executable_classification": "NOT A DESCENDANT OF CORE FREEZE V1: every path that makes the capability a public or certified Core contract fails a binding check of the V1 verifier",
            "verdict": "CORE_FREEZE_V2_REQUIRED",
            "verdict_reason": ("docs/CORE_FREEZE_POLICY.md section 10 states a later commit that fails a contract check is not a descendant of Core Freeze V1, "
                               "and contract.api binds the exact frozen digest and total count. The extension is compatible for callers, but it "
                               "cannot be delivered as Core under the V1 manifest; it needs a new freeze manifest (and a certificate reissue if placed in "
                               "inference/ or adequacy/). The only verifier-passing Core location (non-exported uq/) is rejected on scientific grounds."),
        },
    }
