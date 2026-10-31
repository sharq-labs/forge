"""Genesis-lite v0.4 preregistration: CANDIDATE builder and the owner's freeze step (Genesis §18 Step 1).

``build()`` assembles the candidate document from the code it binds (file digests, the roster, the configuration
constants, the decision contract) plus the owner decisions D1-D14 of 2026-10-30 and the open items.
``write_candidate()`` writes it OUTSIDE the preregistration directory, so nothing formal can run on a candidate.

``freeze()`` is the OWNER's act: it requires a clean tree, the owner's quoted approval and the absence of open items
marked blocking, and writes ``preregistration/genesis_lite_v0_4.json`` and its digest. An agent never calls it
(ACTIVE_PLAN Session A prohibitions).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
from typing import Any

from . import analysis_v4 as a4
from . import arms_v4
from .arms_v3 import PYSR_SETTINGS
from .harness_v4 import SUBSTRATE_V4_FILES, V4_FILES, development_identity_v4
from .isolated_host import DEFAULT_HIDDEN, ISOLATION_LABEL, PRIVATE_WRITABLE, SHARED_STATE, WHITELIST_ROOT
from .pilot_v4 import DOMAIN, PREREG, PREREG_DIGEST, PRESENTATIONS, ROSTER

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE = ROOT / "docs" / "work" / "proposals" / "genesis_lite_v0_4.CANDIDATE.json"
BENCHMARK_ID = "genesis_lite.blindfold_l5.v0_4"
FORMAL_GRID = {"campaigns": 30, "presentations": list(PRESENTATIONS), "seeds": list(range(20)),
               "world_sets_per_arm": 30 * len(PRESENTATIONS) * 20}

#: items that must be resolved (decided or measured) before an owner freeze; ``blocking`` items refuse the freeze
OPEN_ITEMS = {
    "A1-pysr-units-dev-pilot": {"blocking": True, "what": "EXC-5 exit: pysr_units development pilot (fresh dev root, "
                                "under isolation) and QUALIFIED / NOT_QUALIFIED record"},
    "A6-cost": {"blocking": True, "what": "isolated per-universe cost at the 10-campaign rung, BLAS 1, 4 workers; "
                "ESTIMATE with interval for the formal grid"},
    "OD-18-budget": {"blocking": True, "what": "owner sets the wall-clock cap at launch (D5)"},
    "D12-codex-review": {"blocking": True, "what": "independent (Codex) review of this preregistration, findings closed"},
    "review-12b-margin": {"blocking": True, "what": "owner reading: control-kind non-inferiority margin 0.10 vs P-1 "
                          "'no loss allowed in control cells'"},
    "D15-crash-classification": {"blocking": True, "what": "owner decision: a proposer crash or timeout after its "
                                 "outside verification is infrastructure (A), the arm's failure (B) or mixed (C), plus "
                                 "a per-root attempt ledger"},
    "A1b-proposer-env": {"blocking": True, "what": "the formal proposer environment and exposures fixed here and checked "
                         "by the formal driver (G7 pilot: JULIA_DEPOT_PATH with a read-only depot under /opt, "
                         "PYTHON_JULIACALL_PROJECT/EXE, PYTHON_JULIAPKG_OFFLINE, JULIA_NUM_THREADS)"},
    "M-d-candidate-registration": {"blocking": False, "what": "a registration path for a candidate arm with its own "
                                   "identity binding; Step 1 needs none, a Step 2 lift decision does"},
    "multiplicity-iut": {"blocking": False, "what": "proposal: replace holm_family by iut_all (valid at alpha without "
                         "correction and compares every arm); D9 stands until the owner decides"},
}


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _roster() -> dict[str, Any]:
    out = {}
    for name, (spec, role) in sorted(ROSTER.items()):
        module = spec.split(":", 1)[0] if ":" in spec else "benchmarks.genesis_lite.arms"
        rel = pathlib.Path(*module.split(".")).with_suffix(".py")
        out[name] = {"spec": spec, "role": role, "file": rel.as_posix(), "file_sha256": _sha(ROOT / rel)}
    out["pysr_symbolic"]["configuration"] = PYSR_SETTINGS
    out["pysr_units"]["configuration"] = {**arms_v4.PYSR_UNITS_SETTINGS, "validation_fraction": arms_v4.VALIDATION_FRACTION,
                                          "occam_slack": arms_v4.OCCAM_SLACK, "y_units": "1"}
    out["random_grammar"]["configuration"] = {"random_draws": arms_v4.RANDOM_DRAWS}
    return out


def build() -> dict[str, Any]:
    identity, changed = development_identity_v4()
    if changed:
        raise RuntimeError(f"the v0.2-pinned code differs from its preregistration: {changed[:5]}")
    return {
        "schema": "forge.genesis_lite.preregistration/4", "benchmark_id": BENCHMARK_ID, "status": "CANDIDATE_NOT_FROZEN",
        "step": "Genesis §18 Step 1: frozen roster, baseline distributions over >= 20 seeds; no Mind arm (D1)",
        "development_identity_v4": identity,
        "files": {name: _sha(HERE / name) for name in V4_FILES} | {name: _sha(ROOT / name) for name in SUBSTRATE_V4_FILES},
        "master_seed_domain": DOMAIN, "grid": FORMAL_GRID,
        "campaign_id": "gl-v04-formal-{seed}-{campaign}-{presentation}",
        "campaign_mix": "one hidden world of each of the six kinds per campaign (v0.2 generator, unchanged)",
        "roster": _roster(),
        "out_of_scope": {
            "experiment_selection_by_information_gain": "not implemented; only credit is scored",
            "G3_rival_falsification": "discriminating_design NOT_APPLICABLE",
            "G1_G2_mechanism_enumeration": "no port grammar yet (Genesis Step 4)",
            "dynamics": "PySINDy runs over an algebraic log-monomial library",
            "llm_ablation": "Step 2 requirement; no LLM proposer exists",
            "rule": "a class without a strong applicable baseline supports no lift claim",
        },
        "scoring": {"escrow_rule": "engcore.blindfold.escrow_v3.RULE", "credit_table": "v0.2 DEFAULT_CREDIT, unchanged",
                    "evaluator": "benchmarks/genesis_lite/evaluator/score_v3.py",
                    "evaluator_sha256": _sha(HERE / "evaluator" / "score_v3.py")},
        "statistics": {
            "unit": "one world set = one campaign (six worlds) under one (campaign, presentation, seed) master seed; "
                    "units independent (fresh worlds, one stateless isolated proposer per universe)",
            "endpoint": "six-kind credit sum in [-6, 6]; paired differences in [-12, 12]",
            "inference": "empirical-Bernstein lower bound and its p-value (Maurer & Pontil 2009, Thm 4), alpha "
                         f"{a4.ALPHA}; the bootstrap tail and the sign-flip test are not used",
            "superiority": {"multiplicity": "holm_family (D9)", "family": list(a4.PRIMARY_FAMILY)},
            "noninferiority": {"per_kind_margin": a4.NONINFERIORITY_MARGIN, "per_presentation_margin":
                               a4.PRESENTATION_MARGIN, "against": "every non-adversarial arm (IUT)"},
            "cap": "FDA-06: every law kind capped at the comparator where no baseline family represents the truth",
            "representation_limited": f"Clopper-Pearson lower bound >= {a4.REPRESENTATION_LIMIT} for "
                                      f"{a4.REPRESENTATION_ARM}",
            "power_note": "docs/work/proposals/BLINDFOLD_V04_POWER_AND_INFERENCE_DRAFT.md: at 2400 units the bound "
                          "detects about 0.18 per unit with k = 3 (development estimate)",
            "decision_entry": "benchmarks/genesis_lite/decide_v4.py (roles frozen in code, grid from the commitment)",
            "step_1_reports": "baseline distributions per arm, per kind and per stratum; Step 1 tests no lift",
        },
        "strata_disclosures": {
            "region_tell": "D13 option C: indistinguishable worlds always have an extended region, others half the "
                           "time; reported by region and kind",
            "extended_region_refusal": "development finding: on extended regions the gated arms score 0 on "
                                       "discoverable and spurious_correlate (they never extrapolate)",
            "representation_circularity": "EXC-4b: 89/120 discoverable laws expressible by the five-shape grammar; three "
                                          "shapes overlap the generator's families; reported by representation",
        },
        "isolation": {"label": ISOLATION_LABEL, "whitelist_root": WHITELIST_ROOT, "hidden_defaults": list(DEFAULT_HIDDEN),
                      "private_writable": list(PRIVATE_WRITABLE), "shared_state_covered": list(SHARED_STATE),
                      "per_universe_process": True, "record_rule": "six passing outside verifications per VALID record",
                      "boundary_claim": "at most OS_ISOLATION_BOUNDARY_VERIFIED for this host and configuration, "
                                        "through the per-process records; never container or host level"},
        "custody": {"label": "SELF_ADMINISTERED", "root": "the owner writes 32 random bytes to a 0600 file outside "
                    "the tree before the run; the driver writes its SHA-256 commitment before the first campaign; "
                    "revealed only after every campaign is sealed", "external_evaluator": "none (Steps 1-5); Step 6 "
                    "still needs one"},
        "run_rules": {"tier": "formal requires a clean tree and this document frozen with a matching digest",
                      "deadline": "a run that misses its cap is incomplete: it supports no Step 1 gate decision; a "
                                  "rerun needs a fresh root",
                      "invalid_world_sets": "any INVALID_BENCHMARK world set blocks the Step 2 decision on that grid",
                      "deviations": "any change after freezing is a new version, never an edit"},
        "owner_decisions": {"D1": "Step 1 baselines only", "D2": "EXC-5 pysr_units, NOT_QUALIFIED fallback",
                            "D3": "OS isolation, level stated", "D4": "SELF_ADMINISTERED sealed root",
                            "D5": "cap at launch", "D9": "empirical-Bernstein, Holm over the pre-declared family",
                            "D10": "FDA-06 cap on every law kind + out-of-family secondary endpoint",
                            "D11": "one isolated process per universe", "D12": "Codex reviews before freeze",
                            "D13": "region tell disclosed and stratified (option C)", "D14": "roster and scope"},
        "open_items": OPEN_ITEMS,
    }


def canonical(doc: Any) -> bytes:
    return (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write_candidate(path: pathlib.Path = CANDIDATE) -> str:
    data = canonical(build())
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def freeze(owner_approval: str, resolved: dict[str, str]) -> str:
    """The OWNER's freeze. ``resolved`` maps every blocking open item to where it was decided or measured."""
    if not owner_approval.strip():
        raise ValueError("the owner's quoted approval is required")
    missing = sorted(k for k, v in OPEN_ITEMS.items() if v["blocking"] and not resolved.get(k, "").strip())
    if missing:
        raise ValueError(f"blocking open items are not resolved: {missing}")
    if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT).stdout.strip():
        raise ValueError("the tree is not clean")
    doc = {**build(), "status": "FROZEN", "owner_approval": owner_approval, "resolved_open_items": resolved}
    data = canonical(doc)
    PREREG.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    PREREG_DIGEST.write_text(f"{digest}  {PREREG.name}\n")
    return digest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="write the v0.4 preregistration CANDIDATE (never the frozen file)")
    ap.parse_args(argv)
    print(write_candidate())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
