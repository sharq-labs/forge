"""Genesis-lite v0.3 preregistration: DRAFT, built from the code, NOT frozen, NOT FREEZE_READY.

v0.3 is a NEW identity. The v0, v0.1 and v0.2 preregistrations and their pilot results are kept byte for byte, and v0.2
stays the active identity of ``benchmarks.genesis_lite`` (``preregistration.PREREG_PATH``) until the owner approves v0.3
(OD-19). No pilot, formal run or measurement may be produced under this draft. :func:`build` refuses to mark the
document FROZEN while any value is ``OWNER_DECISION_REQUIRED``. Freezing means writing the owner's decisions into the
constants below, regenerating, and committing the new digest.

    python -m benchmarks.genesis_lite.v0_3.preregistration      # rewrites genesis_lite_v0_3.json and its .sha256
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from .. import analysis as v02_analysis
from .. import preregistration as v02
from . import analysis, environment, evaluator, formal

PREREG_SCHEMA = "forge.genesis_lite.preregistration/1"
BENCHMARK_ID = "genesis_lite.blindfold_l5.v0_3"
HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = v02.HERE / "preregistration" / "genesis_lite_v0_3.json"
V0_2_PREREG_SHA256 = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"
V0_3_FILES = ("__init__.py", "analysis.py", "environment.py", "evaluator.py", "formal.py", "preregistration.py")
ODR = "OWNER_DECISION_REQUIRED"

#: owner-decided values; each stays ODR until the owner decides it (see the decision record)
STATUS = "DRAFT"
FORMAL_ROOT_COMMITMENT = ODR                 # a FRESH root, generated and committed by the operator at freeze
ENVIRONMENT_MANIFEST_SHA256 = ODR            # measured on the owner-approved formal machine (environment.py)
DECISION_RECORD = "docs/discovery/GENESIS_LITE_V0_3_AMENDMENT_DECISION_RECORD.md"


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v0_2() -> dict[str, Any]:
    committed = v02.PREREG_PATH.read_bytes()
    if hashlib.sha256(committed).hexdigest() != V0_2_PREREG_SHA256:
        raise ValueError("the v0.2 preregistration is not the one v0.3 amends")
    return json.loads(committed)


def build() -> dict[str, Any]:
    old = _v0_2()
    reused = {"harness": {n: _sha(v02.HERE / n) for n in v02.HARNESS_FILES},
              "evaluator": {n: _sha(v02.HERE / n) for n in v02.EVALUATOR_FILES},
              "substrate": {n: _sha(v02.ROOT / "src" / "engcore" / "blindfold" / n) for n in v02.SUBSTRATE}}
    if (reused["harness"] != old["harness"] or reused["evaluator"] != old["evaluator"]["files"]
            or reused["substrate"] != old["substrate"]):
        raise ValueError("a file pinned by v0.2 changed: v0.2 is frozen and v0.3 reuses it unchanged")
    doc: dict[str, Any] = {
        "schema": PREREG_SCHEMA,
        "benchmark_id": BENCHMARK_ID,
        "status": STATUS,
        "status_note": ("DRAFT (not FREEZE_READY): no pilot, formal run or measurement may be produced under this "
                        "document; v0.2 remains the active identity until the owner approves v0.3 (OD-19). Every "
                        "value marked " + ODR + " blocks the freeze.") if STATUS != "FROZEN" else
                       "FROZEN by the owner (OD-19); see the decision record for the approvals",
        "decision_record": DECISION_RECORD,
        "amends": {
            "identity": old["benchmark_id"], "preregistration_sha256": V0_2_PREREG_SHA256,
            "kept": "v0, v0.1 and v0.2 preregistrations and pilot results byte for byte; v0.2 records are never re-scored "
                    "under v0.3 (ODC-05c)",
            "reasons": [
                "FDA-05 (deep audit 2026-10-19, R-05 EXECUTED_REPRODUCED; re-reproduced failing-first by "
                "tests/genesis_lite/test_genesis_lite_v0_3_amendment.py): a vacuous INDISTINGUISHABLE pair (A/B = 1.3e30 "
                "at the region edge) earned +1.0 for two mutually exclusive truths, above the honest refusal (+0.5)",
                "FDA-06 (R-06 EXECUTED_REPRODUCED): out-of-family spurious_correlate (and, statically, confounded) worlds "
                "were not capped at the comparator, against Genesis section 10.5 rule 4",
                "O-1: the fraction of bootstrap means <= 0 fed Holm as a p-value; under a sign-symmetric null with six "
                "world sets it rejects at alpha/5 = 0.01 in 1/32 of the sign patterns and at 0.05 in 5/64 (executed: "
                "the sign patterns enumerated exactly, the p-function v0.2's bootstrap with 2000 resamples)",
                "P-4: no formal-tier driver or fresh-root rule existed; P-5: no environment manifest bound a run",
            ],
            "changes": [
                "pair rule (d'): the bracket route additionally requires max(|A|,|B|)/min(|A|,|B|) <= 1 + w at every "
                "outside-box evaluation point; the 'one law passes' route is unchanged (evaluator.py)",
                "the no-strong-baseline cap covers every kind with a positive law_pass or indistinguishable_hit "
                "(discoverable, spurious_correlate, confounded, indistinguishable), per universe (analysis.capped / "
                "analysis.out_of_family)",
                "significance: paired sign-flip randomisation p (exact or Monte-Carlo (b+1)/(M+1)); bootstrap for the "
                "lower bound only; Holm, alpha and the family unchanged (analysis.sign_flip_p)",
                "formal driver: world-set-major order, tier-tagged masters, retired-root refusal, root from stdin, "
                "identity never relabelled, hash-chained append-only log (formal.py)",
                "environment manifest measured in a fresh interpreter and committed by digest (environment.py)",
            ],
        },
        "reused_unchanged_from_v0_2": reused,
        "v0_3_files": {n: _sha(HERE / n) for n in V0_3_FILES},
        "evaluator": {
            "schema": evaluator.EVALUATOR_SCHEMA, "credit_digest": evaluator.CREDIT_DIGEST,
            "credit_table": "unchanged (the v0.2 table, same digest)",
            "imports": "standard library and the v0.2 evaluator package only; never engcore (tested)",
            "pair_rule": "v0.2 conditions (a)-(c) unchanged; (d') one law passes, OR the truth is bracketed at "
                         "PASS_FRACTION of the evaluation points AND at every outside-box evaluation point both laws are "
                         "finite, non-zero, of one sign and within a factor 1 + w of each other",
            "pair_bound": (evaluator.PAIR_BOUND.to_dict() if isinstance(evaluator.PAIR_BOUND, evaluator.PairBound)
                           else evaluator.PAIR_BOUND),
            "pair_bound_binding": "evaluate_campaign refuses any bound other than this recorded value",
            "pass_route_note": "a passing law paired with any in-box-agreeing, outside-diverging partner earns +1.0 where "
                               "the law alone earns 0.0 (a v0.2 property kept unchanged; ODC-05d)",
            "pair_bound_forms": list(evaluator.BOUND_FORMS),
            "pair_bound_scope": "bracket route only (proposed); covering every hit would refuse the generator's honest "
                                "pair, whose ratio grows without limit outside the box (ODC-05a)",
            "pair_bound_rule": "w is justified from the rule's purpose, never tuned on pilot or formal worlds (ODC-05b); "
                               "w <= tol is option (iii), no bracket credit at all",
            "escrow_half": "REQUIRED before any v0.3 run: engcore.blindfold.escrow._assess_pair must apply the same "
                           "bound (certified; Batch A; OD-3). Until then the independent evaluator disagrees on such a "
                           "pair and the run is EVALUATOR_DISAGREEMENT (tested)",
        },
        "analysis": {
            "base": "the v0.2 lift rule (benchmarks/genesis_lite/analysis.py, pinned above) with two changes",
            "capped_kinds": list(analysis.CAPPED_KINDS),
            "cap_rule": "per universe: a capped kind whose truth is outside the searched family (or whose flag is "
                        "unknown) is capped at the comparator; a VALID record without the flag for one of them is "
                        "refused",
            "significance": analysis.SIGNIFICANCE,
            "sign_flip": {"statistic": "sum of the paired world-set differences (one-sided, H1 candidate better)",
                          "lattice": analysis.LATTICE, "exact_work_limit": analysis.EXACT_WORK_LIMIT,
                          "monte_carlo_resamples": analysis.SIGN_FLIP_RESAMPLES,
                          "monte_carlo_p": "(b + 1) / (M + 1); size approximately alpha for the one fixed public "
                                           "stream (guaranteed only over random streams); the exact path is exact",
                          "stream": "SHAKE-256(" + analysis.SIGN_FLIP_STREAM.decode() + " || resample index, 8 bytes "
                                    "big-endian), bits in numpy.unpackbits order"},
            "null_scope": "exchangeability of the two arms within a world set (sign-symmetric difference); capping errs "
                          "conservative; a composite null 'mean <= 0' with an asymmetric difference distribution is not "
                          "covered (ODC-O1a)",
            "holm": {"alpha": v02_analysis.ALPHA, "family": list(v02_analysis.PRIMARY_FAMILY), "procedure": "unchanged"},
            "record_binding": "every analysed record carries tier 'formal' and the preregistered formal root commitment "
                              "(D-09), in addition to the v0.2 identity binding",
            "bootstrap": f"lower bound only; {v02_analysis.BOOTSTRAP} resamples, Random(0), floor order statistic (unchanged)",
            "unchanged": "unit of analysis, grid, comparison set, strongest baseline, representation-limited rule, "
                         "non-inferiority margins, screening and its cap, identity binding: as in v0.2",
        },
        "formal": {
            "driver": "benchmarks/genesis_lite/v0_3/formal.py",
            "grid": {"campaign_ids": list(v02_analysis.FORMAL_CAMPAIGNS), "seeds": list(v02_analysis.FORMAL_SEEDS),
                     "presentations": list(v02_analysis.PRIMARY_FAMILY[1:])},
            "world_sets": len(v02_analysis.FORMAL_GRID),
            "order": "world-set-major: every arm runs a world set before any of its records leaves the driver",
            "master_label": formal.LABEL + "/{presentation}/{seed}/{campaign_id}",
            "root_commitment_sha256": FORMAL_ROOT_COMMITMENT,
            "retired_root_commitments": sorted(formal.retired_root_commitments()),
            "root_channel": "stdin only, never the command line",
            "environment_manifest_schema": environment.MANIFEST_SCHEMA,
            "environment_probe_modules": list(environment.PROBE_MODULES),
            "environment_manifest_sha256": ENVIRONMENT_MANIFEST_SHA256,
            "harness_binding": "NOT BOUND in this draft: harness.run_one is v0.2-pinned (v0.2 evaluator and identity); a "
                               "v0.3 harness must bind the post-Batch-A escrow (OD-3) and the P-1 isolation deployment "
                               "(OD-20)",
            "start_condition": "G0 exit (OD-3), OD-20 deployment verified by an independent isolation-probe rerun that "
                               "covers the Genesis-lite secret inventory (FDA-19 / ODC-BL1), OD-18 budget, OD-8 "
                               "evaluator, this identity frozen and approved (OD-19)",
        },
        "arms": old["arms"],
        "arms_not_run": old["arms_not_run"],
        "statistics_unchanged_from_v0_2": {k: old["statistics"][k] for k in ("unit_of_analysis",)},
        "not_in_this_draft": {
            "FDA-18": "campaign answer exclusivity (randomise the mix or declare it); must be decided before freeze",
            "FDA-19 / ODC-BL1": "isolation-probe scope over the Genesis-lite secret inventory; certified, OD-3; specified "
                                "only",
            "FDA-21": "baseline sigma ignores fitted degrees of freedom; v0.3 design item",
            "FDA-22": "per-kind form-prior tell; v0.3 design item",
            "P-1 / P-2 / P-3": "isolation deployment wiring, its harness, and in-repository attack arms per measured attack",
            "escrow half of FDA-05": "certified engcore.blindfold.escrow; Batch A; OD-3",
        },
        "owner_decisions_open": {
            "ODC-05a": "form and scope of the informativeness bound: (i) ratio cap (drafted, bracket route only), (ii) "
                       "graded credit, (iii) no bracket credit",
            "ODC-05b": "the value of w and its form (absolute or a multiple of tol), justified from the rule's purpose",
            "ODC-05c": "v0.3 only, never retroactive to v0.2 records (drafted that way)",
            "ODC-06a": "Genesis section 10.5 rule 4 governs over the v0.2 'discoverable only' wording",
            "ODC-06b": "the capped kinds: discoverable + spurious_correlate (+ confounded and indistinguishable, "
                       "drafted)",
            "ODC-05d": "the pass route: keep v0.2's +1.0 for a passing law with an arbitrary partner, constrain the "
                       "partner, or score a pass-route pair at the law_pass credit",
            "ODC-O1a": "significance route B (drafted) including its null scope; or route A",
            "ODC-O1b": "whether to authorise a bounded, non-formal null-calibration study",
            "OD-19": "approve and freeze this v0.3 identity",
            "OD-20": "the escrow deployment (separate OS account / container) and its independent verification",
            "OD-8": "the external evaluator or its selection process",
            "OD-18": "the formal compute budget and the formal machine (fixes the environment manifest)",
            "OD-3": "recertification after Batch A (escrow half of FDA-05, FDA-19 probe scope)",
        },
    }
    if doc["status"] == "FROZEN" and formal._mentions_owner_decision(doc):
        raise ValueError("a FROZEN v0.3 cannot contain OWNER_DECISION_REQUIRED")
    return doc


def canonical(doc: dict[str, Any]) -> bytes:
    return v02.canonical(doc)


def identity_problems() -> tuple[list[str], str]:
    """(problems, sha256 of the committed v0.3 preregistration) for the v0.3 lift rule."""
    committed = PREREG_PATH.read_bytes()
    problems = []
    if json.loads(committed).get("status") != "FROZEN":
        problems.append("v0.3 is a DRAFT identity (not FROZEN): exploratory, no claim")
    if canonical(build()) != committed:
        problems.append("the code does not rebuild the committed v0.3 preregistration")
    return problems, hashlib.sha256(committed).hexdigest()


def main() -> int:
    data = canonical(build())
    PREREG_PATH.write_bytes(data)
    PREREG_PATH.with_suffix(".sha256").write_bytes((hashlib.sha256(data).hexdigest() + "\n").encode())
    print(hashlib.sha256(data).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
