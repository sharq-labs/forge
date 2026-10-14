"""Genesis-lite v0 preregistration: built from the code, frozen by digest, committed BEFORE any pilot run.

Any change to what it covers (the Blindfold substrate, the primitive library, an arm, the harness, the evaluator, the
credit table, the class table, the statistical plan) changes the digest; ``tests/genesis_lite`` refuses a committed
preregistration that the code no longer rebuilds, so a benchmark change is a NEW identity, never a silent edit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

from engcore.blindfold.roles import DEFAULT_CREDIT

from . import arms as arm_module
from .evaluator import CREDIT, CREDIT_DIGEST, credit_digest
from .harness import CONFIG, KINDS, MIX
from .presentation import PRESENTATIONS, TRAP_TEMPLATES
from .primitives import library_digest

PREREG_SCHEMA = "forge.genesis_lite.preregistration/1"
BENCHMARK_ID = "genesis_lite.blindfold_l5.v0"
ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = HERE / "preregistration" / "genesis_lite_v0.json"

SUBSTRATE = ("universe.py", "escrow.py", "expression.py", "roles.py", "baselines.py")
HARNESS_FILES = ("harness.py", "presentation.py", "answer_key.py", "primitives.py", "arms.py", "pilot.py")
EVALUATOR_FILES = ("evaluator/__init__.py", "evaluator/expr.py", "evaluator/score.py")

#: (kind, presentation) -> Genesis class. Every cell is scored; the table is part of the identity.
CLASS_TABLE = {
    "discoverable": "G0/G5 law recovery (synthetic universe)",
    "no_solution": "G6 no-solution",
    "insufficient_evidence": "G6 insufficient evidence",
    "indistinguishable": "G3 (partial) observationally indistinguishable rival mechanism",
    "spurious_correlate": "spurious-correlation control",
    "confounded": "confounding control",
}
PRESENTATION_ROLE = {
    "anonymous": "the escrow's invented names (synthetic universe, G5)",
    "renamed": "keyed renaming of every name (G5 transformed)",
    "paraphrased": "renamed + reordered + reworded task text (G5 paraphrased)",
    "trap": "anti-historical trap vocabulary (Genesis §10.2) on every kind; worlds where a law can earn credit are verified to defeat the textbook law",
}


def _file_digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(pilot_root_commitment: str) -> dict[str, Any]:
    if len(pilot_root_commitment) != 64:
        raise ValueError("the pilot root commitment is a sha256 hex digest")
    if credit_digest(DEFAULT_CREDIT) != CREDIT_DIGEST:
        raise ValueError("the independent evaluator's credit table differs from the escrow's DEFAULT_CREDIT")
    blindfold = ROOT / "src" / "engcore" / "blindfold"
    doc = {
        "schema": PREREG_SCHEMA,
        "benchmark_id": BENCHMARK_ID,
        "status": "FROZEN_FOR_PILOT",
        "domain": "blindfold L5 synthetic scalar laws (one domain)",
        "substrate": {name: _file_digest(blindfold / name) for name in SUBSTRATE},
        "primitive_library_digest": library_digest(),
        "harness": {name: _file_digest(HERE / name) for name in HARNESS_FILES},
        "evaluator": {"files": {name: _file_digest(HERE / name) for name in EVALUATOR_FILES},
                      "credit_digest": CREDIT_DIGEST, "escrow_config_digest": CONFIG.digest,
                      "imports": "standard library only; never engcore (tested)",
                      "independence": "CODE independence only: a separate implementation by the same team. Outcome, credit and "
                                      "every per-law fraction within tolerance must equal the escrow's; the generator and "
                                      "truth function are shared (common-mode risk). Not third-party evaluation.",
                      "leakage_audit": "LITERAL only (NO_LITERAL_LEAK_FOUND / LITERAL_LEAK_FOUND); structural tells are "
                                       "measured separately and are never cleared by this audit"},
        "campaign_mix": dict(MIX),
        "classes": {"kinds": {k: CLASS_TABLE[k] for k in KINDS}, "presentations": dict(PRESENTATION_ROLE),
                    "trap_templates": [list(t[:3]) for t in TRAP_TEMPLATES],
                    "not_covered": {
                        "G1/G2 mechanism recovery": "needs the canonical port mechanism representation (Genesis Step 4)",
                        "G3 distinguishable rival falsification": "the Blindfold generator has no distinguishable-rival kind; adding one changes certified engcore.blindfold (owner decision)",
                        "G4 anonymous primitive selection over a mechanism library": "only variable selection is measured (greedy_forward); no mechanism-primitive library exists",
                    }},
        "arms": {name: {"family": fam, "stochastic": sto, "role": role, "code": "harness.arms.py + substrate.baselines.py",
                        "config": {"precision": arm_module.PRECISION, "lack_of_fit_ratio": arm_module.LACK_OF_FIT_RATIO,
                                   "occam_slack": arm_module.OCCAM_SLACK},
                        "observations": "presented card + observe client only",
                        "budget": "the universe's query_budget, enforced by the escrow; one sealed submission"}
                 for name, (_fn, fam, sto, role) in sorted(arm_module.ARMS.items())},
        "arms_not_run": {name: {"family": fam, "rule": "status is measured per environment (NOT_AVAILABLE / NOT_INTEGRATED / "
                                "NOT_APPLICABLE_IN_V0); never substituted; a class without a strong arm supports no lift claim"}
                         for name, (fam, _m) in sorted(arm_module.UNAVAILABLE_ARMS.items())},
        "known_structural_tells": [
            "a box-shaped assessment region rules out INDISTINGUISHABLE (Blindfold universe.py docstring)",
            "an extended region pushed beyond near 0.5 / far 1.3 box spans can only be INDISTINGUISHABLE (_rival pushes "
            "the region out by 1.4x); measured per world as region_tell",
            "the region's extension follows the first dimensionless group, hinting which inputs carry structure",
            "public ranges identify a world across runs that share a master seed: the formal tier never reuses one"],
        "metrics": {
            "primary": "full-credit rate per (arm, kind, presentation) cell: credit == 1.0 (law_pass on discoverable/spurious; the "
                       "correct refusal on no_solution / insufficient_evidence / confounded; an indistinguishable HIT)",
            "secondary": ["mean credit (DEFAULT_CREDIT table)", "credit over the best constant answer", "inadmissible count",
                          "observe calls", "wall seconds", "presentation invariance (deterministic arms, paired worlds)"],
            "not_measured_in_v0": ["proper prediction score / calibration (needs predictive distributions: the Mind)",
                                   "information gain per provider call (needs a belief model)",
                                   "invalidation precision/recall (needs the justification graph)"],
        },
        "representation_limited_rule": "a (kind, presentation) cell is REPRESENTATION_LIMITED when monomial_enumeration's "
                                       "full-credit rate has a cluster-bootstrap 95% lower bound >= 0.5 at the formal tier: that "
                                       "cell measures the representation, and no lift there is credited as reasoning. Pilot "
                                       "values are indicative only.",
        "representation_gap_rule": "v0 search arms cover only the monomial family; the generator also draws exponential, "
                                   "two-term and regime laws. For law-recovery cells (discoverable, spurious_correlate, "
                                   "confounded) there is NO STRONG APPLICABLE BASELINE for worlds whose truth is outside the "
                                   "family (Genesis §10.5 rule 4). The rule is PER WORLD: out-of-family worlds are reported "
                                   "as NO_STRONG_BASELINE and excluded from every lift computation; a law-recovery cell enters "
                                   "the lift family only with >= 10 in-family worlds.",
        "statistics": {
            "unit_of_analysis": "the WORLD (one hidden universe). Per world: the fraction of seeds with full credit, and "
                                "the mean credit over seeds; a cell's rate is the mean over its worlds; intervals are "
                                "percentile bootstrap over worlds (2000 resamples, Random(0)). Seeds are never pooled as "
                                "independent instances.",
            "tier1_pilot": {"campaigns_per_presentation": 10, "worlds_per_cell": 10, "stochastic_seeds": [0, 1, 2],
                            "world_reuse": "paired: campaign i uses one master seed for every arm, presentation and seed; ids "
                                           "and names are pseudonymised per run",
                            "purpose": "cost and variance measurement ONLY; never a rate claim"},
            "tier2_formal": {"campaigns_per_presentation": 30, "worlds_per_cell": 30, "stochastic_seeds": 20,
                             "world_reuse": "one master root per (campaign, seed, presentation), committed by sha256 before "
                                            "the campaign and revealed after, SHARED by every arm (so baseline and Mind face the "
                                            "same worlds and lift is paired); never reused across seeds or presentations; ids and "
                                            "names pseudonymised per arm",
                             "proposer_state": "every arm, the Mind included, runs each campaign in a fresh process from an "
                                               "empty state and is stateless across universes (precondition, checked by the "
                                               "operator); a stateful arm could link worlds only within its own run",
                             "strongest_baseline_rule": "per (kind, presentation) cell, the competence-role arm with the "
                                                        "highest formal-tier mean credit (ties: lower measured cost) is the "
                                                        "named strongest applicable baseline; it is computed from the "
                                                        "baseline runs and frozen in a baseline-freeze addendum (digest) "
                                                        "BEFORE any Mind run",
                             "lift_decision_rule": "Mind lift in a cell = mean over worlds of (Mind credit - strongest "
                                                   "baseline credit) on the SAME worlds (shared roots), each world's credit "
                                                   "averaged over its seeds; a cell is claimed only when the 95% cluster "
                                                   "bootstrap lower bound of that mean is > 0 after Holm correction at alpha "
                                                   "0.05 over the FIXED family of every eligible cell (all (kind, "
                                                   "presentation) cells not REPRESENTATION_LIMITED and with >= 10 in-family "
                                                   "worlds where the representation-gap rule applies), the family frozen in "
                                                   "the baseline-freeze addendum before any Mind run",
                             "rules": ["every arm reported for every cell", "no post-result tuning of criteria",
                                       "no compute-budget increase mid-campaign", "a defective task is INVALID_BENCHMARK with a "
                                       "new identity and a rerun from preregistration",
                                       "invalid runs are reported and never aggregated"],
                             "start_condition": "G0 exit, owner-approved compute budget, owner decision on the evaluator "
                                                "and on the escrow deployment"},
        },
        "reveal_protocol": ["master seed derived from a pilot root committed here by sha256 before any run",
                            "proposals stored content-addressed and sealed by one escrow score each",
                            "answer key exported by the operator only after every universe is sealed",
                            "independent evaluator re-scores every sealed proposal; any disagreement invalidates the run",
                            "presented cards audited against the key; trap instances verified (textbook law must fail)",
                            "the pilot root is revealed with the pilot results (the pilot is not held out)"],
        "pilot_root_commitment_sha256": pilot_root_commitment,
        "security_boundary": "SECURITY_BOUNDARY_NOT_PROVEN (in-process escrow transport); no result counts as novel discovery",
        "owner_decisions_open": {
            "external_evaluator": "OWNER_DECISION_REQUIRED: name an evaluator or a selection process with a deadline (Genesis §26)",
            "held_out_authoring": "OWNER_DECISION_REQUIRED: v0 instances come from FORGE's own generator",
            "compute_budget": "OWNER_DECISION_REQUIRED: formal tier from the pilot ESTIMATE",
            "escrow_deployment": "OWNER_DECISION_REQUIRED: formal runs need an isolated escrow (process boundary demonstrated)",
        },
    }
    return doc


def digest(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def canonical(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True).encode() + b"\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="write the Genesis-lite v0 preregistration")
    parser.add_argument("--commitment", required=True, help="sha256 hex of the pilot root secret (kept outside the repo)")
    args = parser.parse_args(argv)
    doc = build(args.commitment)
    PREREG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREREG_PATH.write_bytes(canonical(doc))
    PREREG_PATH.with_suffix(".sha256").write_bytes((digest(doc) + "\n").encode())
    print(digest(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
