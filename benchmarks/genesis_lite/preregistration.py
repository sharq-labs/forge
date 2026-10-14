"""Genesis-lite v0.1 preregistration: built from the code, frozen by digest, committed BEFORE any v0.1 run.

v0.1 is a NEW identity. The v0 preregistration (``genesis_lite_v0.json``, sha256 recorded beside it) and its pilot
results are kept byte-for-byte as historical evidence; they are never rebuilt or edited.

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

from . import analysis
from . import arms as arm_module
from .evaluator import CREDIT, CREDIT_DIGEST, credit_digest
from .harness import CONFIG, KINDS, MIX
from .presentation import PRESENTATIONS, TRAP_TEMPLATES
from .primitives import library_digest

PREREG_SCHEMA = "forge.genesis_lite.preregistration/1"
BENCHMARK_ID = "genesis_lite.blindfold_l5.v0_2"
ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = HERE / "preregistration" / "genesis_lite_v0_2.json"
V0_1_PREREG_PATH = HERE / "preregistration" / "genesis_lite_v0_1.json"
V0_1_PREREG_SHA256 = "94efff081f7a603653d0da79083428f1da2802e49c60587fcd0e86ce5643fedd"
V0_1_PILOT_SUMMARY = HERE / "pilot_results" / "v0_1-2026-10-14" / "summary.json"
V0_PREREG_PATH = HERE / "preregistration" / "genesis_lite_v0.json"
V0_PREREG_SHA256 = "f99fcfbdc97aabcbea52fa72c12ad196d420e298237c5374184f537c67774ab0"
V0_PILOT_SUMMARY = HERE / "pilot_results" / "v0-2026-10-14" / "summary.json"

SUBSTRATE = ("universe.py", "escrow.py", "expression.py", "roles.py", "baselines.py")
HARNESS_FILES = ("harness.py", "presentation.py", "answer_key.py", "primitives.py", "arms.py", "pilot.py", "analysis.py",
                 "proposer_host.py")
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
        "status": "FREEZE_READY",
        "amends": {
            "identity": "genesis_lite.blindfold_l5.v0_1", "preregistration_sha256": V0_1_PREREG_SHA256,
            "kept": "v0.1 preregistration and its Tier-1 pilot results unchanged (historical evidence); v0.1 is NOT used "
                    "for any formal evaluation",
            "v0_1_pilot_summary_sha256": _file_digest(V0_1_PILOT_SUMMARY),
            "reasons": [
                "G0/A1 final review (2026-10-14), each reproduced by tests/genesis_lite/test_genesis_lite_final_review.py "
                "before the fix: D1 an invalid or omitted registered baseline silently weakened the comparison; D2 the "
                "grid and the record set were chosen by the caller; D3 discovery could be traded for control credit; "
                "D4 gains on discoverable worlds outside every arm's searched family counted as lift; D5 records without "
                "universe ids, and per-kind references, were never content-paired; D6 the preregistered "
                "REPRESENTATION_LIMITED rule was not implemented; D7 the stimulus (renaming, trap template, wording) "
                "differed by arm name; credits were not bound to the frozen table or to the independent evaluator's "
                "agreement; a candidate could take a registered baseline's name",
                "measured: a proposer in a same-account process read the operator's command line, found the root file, "
                "read it and re-derived every hidden world while its run stayed VALID; it also reached the network, "
                "left a child process running after the campaign and wrote into the benchmark package",
            ],
            "changes": ["every registered non-adversarial arm must be complete, VALID, isolated and content-paired; a "
                        "missing or invalid one blocks the claim (analysis.lift_decision)",
                        "the formal grid is preregistered (analysis.FORMAL_GRID); another grid or off-grid records claim "
                        "nothing; the code must rebuild this preregistration",
                        "non-inferiority on every kind, discovery included",
                        "no lift where no strong baseline exists: the candidate is capped at its comparator in "
                        "out-of-family discoverable worlds and in REPRESENTATION_LIMITED cells",
                        "credits must be values of DEFAULT_CREDIT that the independent evaluator agreed with",
                        "one stimulus per world set shared by every arm; only the pseudonym is per run (harness.stimulus_key)",
                        "the bootstrap lower bound uses the floor order statistic"],
            "earlier": {"identity": "genesis_lite.blindfold_l5.v0", "preregistration_sha256": V0_PREREG_SHA256},
        },
        "v0_1_amendment_of_v0": {
            "identity": "genesis_lite.blindfold_l5.v0", "preregistration_sha256": V0_PREREG_SHA256,
            "kept": "v0 preregistration and pilot results unchanged (historical evidence)",
            "reasons": [
                "P-1: per-cell lift let a floor arm that always proposes win the discoverable cell (0.70 vs 0.27) while "
                "scoring -1 on every control; root cause = per-cell metric + over-conservative gated baselines + 70% of "
                "discoverable worlds inside the simple monomial family (not leakage, not a scoring defect: 5,760/5,760 "
                "universes independently re-scored in agreement)",
                "OD-20: in-process proposers stole hidden laws by heap scan and stack walk (tested); v0.1 requires the "
                "isolated proposer process",
            ],
            "v0_pilot_summary_sha256": _file_digest(V0_PILOT_SUMMARY),
            "changes": ["joint campaign credit as the primary endpoint (analysis.py)",
                        "strongest baseline over every non-adversarial arm (floors included)",
                        "control non-inferiority (margin 0.10) and a fixed Holm family",
                        "added arm fit_all_gated (raises the bar; no arm removed or weakened)",
                        "proposer_process isolation required",
                        "one master root per world set (campaign, presentation, seed), shared by every arm, never reused",
                        "setting names outside the card are refused before they reach the escrow"],
        },
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
            "primary": "JOINT world-set credit: per world set (one campaign = one world of every kind, under one "
                       "(presentation, seed) root) the sum over the six kinds of the frozen DEFAULT_CREDIT; an arm's score "
                       "is the mean over the preregistered grid of world sets (benchmarks/genesis_lite/analysis.py, digest "
                       "above)",
            "secondary": ["full-credit rate per (arm, kind, presentation) cell -- DESCRIPTIVE ONLY, never a claim",
                          "discovery credit and control (refusal) credit reported apart; discovery credit split into "
                          "in-family and out-of-family (NO_STRONG_BASELINE) worlds; correct-refusal rate on controls",
                          "mean credit (DEFAULT_CREDIT table)", "credit over the best constant answer", "inadmissible count",
                          "observe calls", "wall seconds", "presentation invariance (deterministic arms, paired worlds)"],
            "not_measured_in_v0": ["proper prediction score / calibration (needs predictive distributions: the Mind)",
                                   "information gain per provider call (needs a belief model)",
                                   "invalidation precision/recall (needs the justification graph)"],
        },
        "representation_limited_rule": "a (kind, presentation) cell is REPRESENTATION_LIMITED when monomial_enumeration's "
                                       "full-credit rate has a cluster-bootstrap 95% lower bound >= 0.5 at the formal tier: that "
                                       "cell measures the representation, and no lift there is credited as reasoning "
                                       "(analysis.representation_limited; the candidate is capped at its comparator there). "
                                       "Pilot values are indicative only.",
        "representation_gap_rule": "v0.1 search arms cover only the monomial family; the generator also draws exponential, "
                                   "two-term and regime laws. The PRIMARY (joint) endpoint includes every world. Discovery "
                                   "credit is additionally reported split into in-family and out-of-family worlds, and the "
                                   "out-of-family share is labelled NO_STRONG_BASELINE (Genesis §10.5 rule 4). In those worlds the "
                                   "candidate is capped at its comparator: no lift comes from them. v0.2 makes no "
                                   "discovery-only lift claim.",
        "statistics": {
            "unit_of_analysis": "the WORLD SET: one campaign (one hidden world of every kind) under one (presentation, seed) "
                                "master root. Every arm runs every world set once. Intervals: percentile bootstrap over world "
                                "sets (2000 resamples, Random(0)). Per-cell rates are descriptive only.",
            "tier1_pilot": {"campaigns_per_presentation": 10, "seeds": [0, 1, 2], "isolation": "proposer_process",
                            "purpose": "cost and variance measurement ONLY; never a rate or lift claim"},
            "tier2_formal": {"campaigns_per_presentation": 30, "seeds": 20,
                             "grid": {"campaign_ids": list(analysis.FORMAL_CAMPAIGNS), "seeds": list(analysis.FORMAL_SEEDS),
                                      "presentations": list(analysis.PRIMARY_FAMILY[1:])},
                             "world_sets_per_presentation": 600, "worlds_per_kind_and_presentation": 600,
                             "world_reuse": "one master root per world set, committed by sha256 before the campaign and "
                                            "revealed after, SHARED by every arm (paired lift) and NEVER reused across seeds, "
                                            "campaigns or presentations, so no proposer, stateful or not, sees a world "
                                            "twice; ids and names pseudonymised per run",
                             "isolation": "proposer_process required and checked by analysis.coverage_problems; in addition "
                                          "the OD-20 deployment (operator, escrow and secrets under another OS account or "
                                          "container; the proposer cannot see operator processes or their command lines, has a "
                                          "read-only filesystem without the operator's files, no network, no ptrace, and "
                                          "every process it starts ends with the campaign) must be "
                                          "in place and verified by the isolation demo before any formal run: a "
                                          "same-account run is INVALID for the formal tier",
                             "strongest_baseline_rule": "the registered non-adversarial arm (competence, floor or sanity "
                                                        "role) with the highest formal-tier PRIMARY score; every such arm "
                                                        "must be complete; frozen in a baseline-freeze addendum (digest) "
                                                        "BEFORE any Mind run",
                             "lift_decision_rule": "analysis.lift_decision (digest above), all of: the preregistered grid; "
                                                   "COMPLETE coverage (a VALID, isolated, content-paired run of the candidate "
                                                   "and of EVERY registered non-adversarial arm on every world set of the "
                                                   "grid, credits from DEFAULT_CREDIT agreed by the independent evaluator; "
                                                   "an invalid world set blocks the claim, it is never dropped); no lift "
                                                   "from out-of-family discoverable worlds or REPRESENTATION_LIMITED cells "
                                                   "(capped at the comparator); pooled paired primary "
                                                   "difference with cluster-bootstrap 95% lower bound > 0 and significant "
                                                   "after Holm (alpha 0.05) over the FIXED family "
                                                   + ", ".join(analysis.PRIMARY_FAMILY) + "; every presentation's paired "
                                                   "primary lower bound > -" + str(analysis.PRESENTATION_MARGIN) + "; every "
                                                   "kind's (discovery included) paired difference to the BEST arm on that kind has a lower "
                                                   "bound > -" + str(analysis.NONINFERIORITY_MARGIN),
                             "rules": ["every arm reported for every cell", "no post-result tuning of criteria",
                                       "no compute-budget increase mid-campaign", "a defective task is INVALID_BENCHMARK with a "
                                       "new identity and a rerun from preregistration",
                                       "invalid runs are reported, never aggregated, and block a lift claim",
                                       "arms may be ADDED by a new identity, never removed or weakened"],
                             "start_condition": "G0 exit (OD-3), owner-approved compute budget (OD-18), evaluator decision "
                                                "(OD-8), OD-20 deployment in place and verified, this identity approved (OD-19)"},
        },
        "reveal_protocol": ["master seed derived from a pilot root committed here by sha256 before any run",
                            "proposals stored content-addressed and sealed by one escrow score each",
                            "answer key exported by the operator only after every universe is sealed",
                            "independent evaluator re-scores every sealed proposal; any disagreement invalidates the run",
                            "presented cards audited against the key; trap instances verified (textbook law must fail)",
                            "the pilot root is revealed with the pilot results (the pilot is not held out)"],
        "pilot_root_commitment_sha256": pilot_root_commitment,
        "security_boundary": "SECURITY_BOUNDARY_NOT_PROVEN: the proposer runs in a separate process under the SAME OS "
                             "account (heap scan, stack walk and environment attacks refused, tested; on Linux YAMA ptrace "
                             "scope >= 1 refuses parent-memory reads). MEASURED 2026-10-14: such a proposer read the "
                             "operator's command line, then the root file it named, and re-derived every hidden world; it "
                             "also reached the network, outlived the campaign through a child process and wrote into the "
                             "benchmark package. Same-account runs are therefore never formal evidence. No result counts as "
                             "novel discovery.",
        "owner_decisions_open": {
            "OD-8 external_evaluator": "name an evaluator or a selection process with a deadline (Genesis §26)",
            "held_out_authoring": "v0.2 instances come from FORGE's own generator",
            "OD-18 compute_budget": "formal tier from the v0.2 pilot ESTIMATE",
            "OD-19 identity": "approve this v0.2 identity before any formal run (v0.1 is superseded, never formal)",
            "OD-20 escrow_deployment": "a separate OS account / container / host for the operator, escrow and secrets",
            "escrow_refusal_codes": "residual in certified engcore.blindfold: the client classifies refusals by text "
                                    "('rolled back'), and the escrow echoes caller input in refusal texts; Genesis-lite "
                                    "blocks the channel at the client, the structural fix (refusal codes) needs a "
                                    "certified change",
        },
    }
    return doc


def digest(doc: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def canonical(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, sort_keys=True, indent=1, ensure_ascii=True).encode() + b"\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="write the Genesis-lite v0.2 preregistration")
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
