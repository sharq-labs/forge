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
from . import analysis, environment, evaluator, formal, isolation, registry
from . import arms as v03_arms

PREREG_SCHEMA = "forge.genesis_lite.preregistration/1"
BENCHMARK_ID = "genesis_lite.blindfold_l5.v0_3"
HERE = pathlib.Path(__file__).resolve().parent
PREREG_PATH = v02.HERE / "preregistration" / "genesis_lite_v0_3.json"
V0_2_PREREG_SHA256 = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"
V0_3_FILES = ("__init__.py", "analysis.py", "arms.py", "deployment_attacks.py", "environment.py", "evaluator.py",
              "formal.py", "harness.py", "preregistration.py", "readiness.py", "registry.py", "secret_scan.py",
              "selfcheck.py", "isolation.py", "timing_pilot.py", "container_evidence.py", "container_probe.py",
              "container/Containerfile")
#: the certified escrow half of FDA-05 (Batch A, OD-3); pinned by digest when it is in the tree
ESCROW_HALF = "pair_bound.py"
ODR = "OWNER_DECISION_REQUIRED"

#: owner-decided values; each stays ODR until the owner decides it (see the decision record)
STATUS = "DRAFT"
FORMAL_ROOT_COMMITMENT = ODR                 # a FRESH root, generated and committed by the operator at freeze
ENVIRONMENT_MANIFEST_SHA256 = ODR            # measured on the owner-approved formal machine (environment.py)
CANDIDATE = ODR                              # {name, spec, code_sha256} named in the freeze, or "NONE" (baselines only)
#: D7 (owner, 2026-10-20): the formal wall-clock cap. Baselines: 72 h (about 1.25 x the ESTIMATED 58 h of the timing
#: pilot). The candidate's cost is measured by a one-campaign timing at D4 and added before the freeze.
BASELINE_BUDGET_HOURS = 72.0
#: D6 (owner, 2026-10-20): the external evaluator is chosen by a selection process; named by the deadline or D6 reopens
EVALUATOR = ODR
EVALUATOR_DEADLINE = "2026-11-17"
CANDIDATE_BUDGET_HOURS = ODR
TOTAL_BUDGET_HOURS = ODR
DECISION_RECORD = "docs/discovery/GENESIS_LITE_V0_3_AMENDMENT_DECISION_RECORD.md"
#: owner decisions taken so far (each also needs its entry in the owner's approval record at freeze)
OWNER_DECISIONS_TAKEN = {
    "D6-evaluator": "OD-8; decided by the owner in session on 2026-10-20: a selection process with a deadline of "
                    "2026-11-17. Criteria: independent of the operator: no access to the operator's machine, the root, the run log or the registry before the reveal; holds the EvaluatorInbox on their own machine; can run formal.verify_attempt and analysis.lift_decision; agrees to publish the verdict whatever it is. The evaluator's name stays OWNER_DECISION_REQUIRED until "
                    "selected, so the freeze (D4) is refused until then; if nobody is named by the deadline, D6 reopens",
    "D7-budget-and-machine": "OD-18; decided by the owner in session on 2026-10-20: the formal machine is the owner's WSL "
                             "machine, since 2026-10-20 a fresh Ubuntu-24.04 distro hardened by the owner (interop and "
                             "automount disabled), where D5 is verified and the environment manifest is measured at "
                             "freeze. The budget was decided on the first timing pilot (MEASURED 43.5 s per world set for "
                             "the 20 baselines; ESTIMATED 58 h formal with replay; the current pinned pilot is in "
                             "formal.timing_pilot); budget approved: 72 h for the "
                             "baselines plus the candidate's cost measured by a one-campaign timing at D4; an overrun "
                             "stops the attempt as BUDGET_EXCEEDED, INVALID, never partially claimed",
    "D5-deployment": "OD-20; decided by the owner in session on 2026-10-20: option A1, rootless Linux namespaces. Every "
                     "formal proposer card runs under unshare in fresh user, PID, mount, network, IPC and UTS namespaces, "
                     "with operator state masked by private tmpfs mounts and only the benchmark tree and the Python "
                     "environment re-bound read-only (isolation.py); a formal card cannot start without it, and proposers run "
                     "without capabilities (setpriv). Verification evidence is pinned by sha256: twelve attack channels "
                     "REFUSED in the deployment, each REACHED by the same probe in a control configuration. The isolation "
                     "boundary stays NOT_PROVEN until every writable location is shown private to its card (fifth "
                     "scientific review, N-1). Residual, disclosed: same Linux account "
                     "outside the namespaces; readable tree and environment; WSL shares the host's utility VM; the "
                     "certified escrow stays in the operator process (the operator_process channel shows a proposer "
                     "cannot reach it); the certified isolation-probe rerun belongs to OD-3. AMENDED by the owner "
                     "in session on 2026-10-21: D5-A1b, rootless Podman per-card isolation, a bounded implementation "
                     "refinement of the approved rootless-namespace route, not a weakening of it. A1 is SUPERSEDED for "
                     "the formal deployment because the fifth review showed that the hand-built namespace probe had not "
                     "proven cross-card state isolation outside /tmp. Podman provides the rootless Linux namespace "
                     "boundary; the deployment contract is: a brand-new container for every card; no container reuse; "
                     "read-only root filesystem; read-only FORGE source and Python environment; network=none; all "
                     "capabilities dropped; no-new-privileges; rootless user namespace; private writable mounts for the "
                     "card; complete writable-mount inventory; Card-A/Card-B canary isolation; a deliberately shared-"
                     "volume positive control; deployment verification before admission (isolation.py, "
                     "container_evidence.py, container_probe.py; formal.deployment_problems). Device nodes (owner, "
                     "2026-10-21): no exemption; a writable device or pseudo-file mount stays blocking. D5 stays "
                     "NOT_PROVEN until complete evidence passes and is pinned",
    "D3b-1-cap-form": "decided by the owner in session on 2026-10-20 after the ODC-O1b study: option B, a cell-level "
                      "cap. A capped (kind, presentation) cell contributes min(0, its summed paired difference): no "
                      "gain, a net loss counts, in the effect size (recomputed per bootstrap resample) and the per-kind "
                      "non-inferiority. Implementation P2 (owner, same session): the sign-flip p uses the uncapped "
                      "differences only, because the min inside every sign vector let capped wins raise significance "
                      "(p = 0.002 at a mean difference of 0, adversarial test). v0.3 only",
    "D3b-2-kind-noninferiority": "decided by the owner in session on 2026-10-20 after the ODC-O1b study: option B, the "
                                 "per-kind non-inferiority margin is 0.15 (v0.2: 0.10) and every kind is still required; "
                                 "the presentation margin is unchanged. v0.3 only. RECONFIRMED by the owner on 2026-10-20 at 0.15, with the corrected interpretation: a NON-INFERIORITY GUARDRAIL, not an equivalence claim and not a statement of acceptable degradation. The margin bounds the 95 % lower bound of the per-kind mean credit difference; read as a success rate it allows about 7.5 points for success -> failure (+1 -> -1), 15 points for success -> refusal (1 -> 0) and 30 points for indistinguishable_hit -> insufficient_evidence (1 -> 0.5)",
    "D2b-root-grinding": "decided by the owner in session on 2026-10-20: bind the admission nonce into the key derivation "
                         "so pre-commit root grinding is refused. K = HMAC-SHA256(revealed root, label / preregistration "
                         "digest / admission nonce / admission digest); the admission is created by the one-attempt "
                         "registry after the commitment, so no stream is computable at commitment time; lift_decision "
                         "uses the keyed stream only with a self-consistent formal admission of this root and this "
                         "preregistration that every record carries (test_d2b_*). admission must also be the evaluator inbox's first admission of the root. Residual, disclosed: an operator who runs complete attempts privately (off the registry) and publishes only the admission of the best one is NOT stopped by the key; the evaluator receiving each admission before the first world (D6) narrows this, but an inbox cannot order publication against execution. That is the operator-honesty residual of the decision record",
    "D3-baselines-and-tells": "covers ODC-06a, ODC-06b, FDA-21, FDA-22, FDA-18 and pilot P-2; decided by the owner in "
                              "session on 2026-10-20, option A as drafted: ODC-06a Genesis section 10.5 rule 4 governs "
                              "over the v0.2 wording; ODC-06b the cap covers every law-credit kind (discoverable, "
                              "spurious_correlate, confounded, indistinguishable); FDA-21 careful keeps ddof = 0 "
                              "(certified, a documented exception) and the corrected <name>_dof arms join the strongest-"
                              "baseline maximum; FDA-22 the form tell is declared and law_form measured, the generator's "
                              "priors are NOT equalised (no certified change); FDA-18 one proposer process per card; "
                              "pilot P-2 CONTROL_SOLVED with the exact binary-bootstrap lower bound >= 0.5",
    "D2-significance": "covers ODC-O1a and ODC-O1b; decided by the owner in session on 2026-10-20: ODC-O1a route B, the "
                       "one-sided paired sign-flip p with the Monte-Carlo stream derived from the revealed formal root "
                       "(HMAC, own label; Holm, alpha and the family unchanged; bootstrap for the lower bound only); the "
                       "exchangeability null scope is accepted and stated; ODC-O1b a bounded, non-formal power and "
                       "null-calibration study on synthetic records is authorised, to run after D3",
    "D1-scoring": "covers ODC-05a, ODC-05b, ODC-05c and ODC-05d; decided by the owner in session on 2026-10-20: ODC-05a form (i), a ratio cap max/min <= 1 + w outside the box, on the BRACKET route only; ODC-05b w = 3 x tol (tol_multiple 3.0), anchored a priori on the generator's declared separation scale (OUTSIDE_TOLERANCES = 3 in universe.py), never tuned on pilot or formal worlds; ODC-05c v0.3 only, never retroactive to v0.2 records; ODC-05d the pass route keeps +1.0 as in v0.2",
}
#: the ODC-O1b study (non-formal, synthetic); its findings are open as D3b
POWER_STUDY_EVIDENCE = "docs/work/evidence/genesis_lite_v0_3_power_study_2026_10_20/result.json"
POWER_STUDY_EVIDENCE_SHA256 = "9ad27938a5a553ba1f7ee671270c80c607476f2783ef9f80cb7f4ec6cc571939"
#: D5 (owner, 2026-10-20, option A1): the historical A1 deployment verification (superseded 2026-10-21; HISTORICAL_ONLY)
A1_DEPLOYMENT_EVIDENCE = "docs/work/evidence/genesis_lite_v0_3_d5_deployment_2026_10_20/result.json"
A1_DEPLOYMENT_EVIDENCE_SHA256 = "519f3669b48b5bd08f79af172af51e590ce7e1432141e96bfc7446edd8c2f0c7"
#: D5-A1b (owner, 2026-10-21): the deployment verification on the formal machine from a clean clone of 12baeb04;
#: BLOCKED by the six writable host device nodes (owner: no exemption), so D5 stays NOT_PROVEN
DEPLOYMENT_EVIDENCE = "docs/work/evidence/genesis_lite_v0_3_d5_a1b_deployment_2026_10_21/result.json"
DEPLOYMENT_EVIDENCE_SHA256 = "967f089e26247ce8db2ef41b0039fdca0886e7f0ed40e648ad57d3d6e1995c5d"
#: D7 (owner, 2026-10-20): the timing pilot on the formal machine, before the formal budget is approved
TIMING_PILOT_EVIDENCE = "docs/work/evidence/genesis_lite_v0_3_d7_timing_pilot_2026_10_20/result.json"
TIMING_PILOT_EVIDENCE_SHA256 = "3759ff334f690f4d3601b588a4bfb6c9dd71f186975a45d024a8714cb85beb4f"
#: fixed here, so that committing a later preregistration never changes what this identity rebuilds to
RETIRED_PILOT_ROOT_COMMITMENTS = (
    "073814653d48e3879030270072f1912e0dc1bf10df161e4fdd18bbe225183686",   # v0
    "2ebf31ab09d6a5f12a51156585ab46923b6b62d2c46740967d316ea904666b9d",   # v0.2
    "b80ae0be4142b504dfe2c3dee90008e32c32fd721fdd130e7787a25a95c94d0a",   # v0.1
)


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def committed_doc_problems(doc_bytes: bytes) -> list[str]:
    """Why ``doc_bytes`` is not the committed v0.3 preregistration that this code rebuilds ([] when it is)."""
    committed = PREREG_PATH.read_bytes()
    if doc_bytes != committed:
        return ["the preregistration given is not the committed genesis_lite_v0_3.json"]
    problems = []
    if PREREG_PATH.with_suffix(".sha256").read_bytes().strip().decode() != sha256(committed):
        problems.append("the committed v0.3 digest file does not match the committed preregistration")
    if canonical(build()) != committed:
        problems.append("the code does not rebuild the committed v0.3 preregistration")
    return problems


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
                "(discoverable, spurious_correlate, confounded, indistinguishable); which universes are capped is "
                "decided per universe (analysis.is_capped / analysis.out_of_family)",
                "D3b-1 (owner, 2026-10-20): capped universes count per (kind, presentation) cell as min(0, the cell's "
                "net difference) in the effect size and the per-kind non-inferiority; the significance test uses the "
                "uncapped differences only (P2) (analysis.capped_parts / capped_bootstrap_ci)",
                "D3b-2 (owner, 2026-10-20): per-kind non-inferiority margin 0.15, every kind required "
                "(analysis.KIND_NONINFERIORITY_MARGIN)",
                "significance: paired sign-flip randomisation p (exact or Monte-Carlo (b+1)/(M+1)); bootstrap for the "
                "lower bound only; Holm, alpha and the family unchanged (analysis.sign_flip_p)",
                "formal driver: world-set-major order, tier-tagged masters, retired-root refusal, root from stdin, "
                "identity never relabelled, hash-chained append-only log (formal.py)",
                "environment manifest measured in a fresh interpreter and committed by digest (environment.py)",
            ],
        },
        "reused_unchanged_from_v0_2": reused,
        "v0_3_files": {n: _sha(HERE / n) for n in V0_3_FILES},
        "package_markers": {rel: _sha(v02.ROOT / rel) for rel in ("benchmarks/__init__.py",
                                                                  "benchmarks/genesis_lite/__init__.py")},
        "escrow_half": {"module": "src/engcore/blindfold/" + ESCROW_HALF,
                        "sha256": (_sha(v02.ROOT / "src" / "engcore" / "blindfold" / ESCROW_HALF)
                                   if (v02.ROOT / "src" / "engcore" / "blindfold" / ESCROW_HALF).is_file()
                                   else "NOT_IN_TREE"),
                        "certification": "new file in certified scope: UNCERTIFIED until OD-3",
                        "rule": "the escrow applies (d') itself: PairBoundedEscrowService runs the v0.2 escrow _score "
                                "with _assess_pair replaced by the bounded assessment; BoundedEvaluatorConfig seals w in "
                                "the config digest declared at campaign creation; escrow.py and roles.py are unchanged"},
        "harness": {
            "module": "benchmarks/genesis_lite/v0_3/harness.py", "id": "forge.genesis_lite.harness.v0_3",
            "procedure": "v0.2 harness._run re-bound to the v0.3 evaluator, the v0.3 config and the bounded escrow; no "
                         "fallback to v0.2",
            "binding": "harness.bind refuses: a document other than the committed v0.3 bytes (v0.2 or any dict that says "
                       "FROZEN), a code tree that does not rebuild it, a credit table, w or environment manifest other "
                       "than the preregistered one, a formal binding of a non-FROZEN identity, a tree without the escrow "
                       "half",
            "proposer": "one fresh isolated proposer process PER CARD with its own working and temporary directory "
                        "(FDA-18); same-account files elsewhere and helper processes remain OD-20 items "
                        "(cross_card_state and persistence attacks)",
            "formal_lockdown": "a formal run takes no card hook, extra path or caller arm spec; it runs a registered "
                               "v0.3 arm or the candidate this identity names and records each arm's code digest",
            "law_form": "each universe records the generator form of its hidden law (FDA-22)",
            "arms": "benchmarks.genesis_lite.v0_3.arms (FDA-21), by registry name",
        },
        "one_attempt_per_root": {
            "module": "benchmarks/genesis_lite/v0_3/registry.py", "registry_schema": registry.REGISTRY_SCHEMA,
            "rule": "a root commitment is admitted to the operator-side registry before the first world is derived; a "
                    "formal root is consumed by its first admission under any identity; development roots are recorded "
                    "apart and can never become formal; the registry lives outside every run directory and its head is "
                    "published to the external evaluator",
        },
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
                               "the law alone earns 0.0 (a v0.2 property kept unchanged by owner decision ODC-05d)",
            "pair_bound_forms": list(evaluator.BOUND_FORMS),
            "pair_bound_scope": "bracket route only (owner decision ODC-05a); covering every hit would refuse the "
                                "generator's honest pair, whose ratio grows without limit outside the box",
            "pair_bound_rule": "w is justified from the rule's purpose, never tuned on pilot or formal worlds (ODC-05b); "
                               "w <= tol is option (iii), no bracket credit at all",
            "escrow_half": "REQUIRED before any v0.3 run: engcore.blindfold.escrow._assess_pair must apply the same "
                           "bound (certified; Batch A; OD-3). Until then the independent evaluator disagrees on such a "
                           "pair and the run is EVALUATOR_DISAGREEMENT (tested)",
        },
        "analysis": {
            "base": "the v0.2 lift rule (benchmarks/genesis_lite/analysis.py, pinned above) with the changes below",
            "capped_kinds": list(analysis.CAPPED_KINDS),
            "cap_rule": "which universes are capped: a capped kind whose truth is outside the searched family (or whose "
                        "flag is unknown), and every REPRESENTATION_LIMITED / CONTROL_SOLVED cell; a VALID record without "
                        "the flag for one of them is refused. How they count (D3b-1): " + analysis.CAP_RULE,
            "significance": analysis.SIGNIFICANCE,
            "sign_flip": {"statistic": "sum over world sets of the paired difference over UNCAPPED kinds only (one-sided, "
                                       "H1 candidate better); capped cells never enter the significance test (D3b-1, P2). "
                                       "They enter the effect size: sum of the uncapped differences + sum over capped "
                                       "(kind, presentation) cells of min(0, the cell's summed difference), per world set",
                          "lattice": analysis.LATTICE, "exact_work_limit": analysis.EXACT_WORK_LIMIT,
                          "monte_carlo_resamples": analysis.SIGN_FLIP_RESAMPLES,
                          "monte_carlo_p": "(b + 1) / (M + 1); the exact path is exact",
                          "stream": "SHAKE-256(K || resample index, 8 bytes big-endian), bits in numpy.unpackbits "
                                    "order, K = HMAC-SHA256(revealed formal root, '" + analysis.SIGN_FLIP_KEY_LABEL
                                    + "/' + the preregistration digest + '/' + the admission nonce + '/' + the admission "
                                    "digest) (D2 + D2b): secret from the proposer until the reveal, and not computable at "
                                    "commitment time because the admission is created afterwards, so pre-commit root "
                                    "grinding cannot fix the stream; lift_decision refuses a root whose sha256 is not the "
                                    "commitment and an admission that is tampered, of another root, preregistration or "
                                    "tier, or not the attempt every record carries. Residual (disclosed): whoever runs the "
                                    "registry could generate unpublished admissions and keep one; the evaluator's inbox "
                                    "binds the first published admission, and the worlds mix in the same nonce"},
            "null_scope": "exchangeability of the two arms within a world set (sign-symmetric difference), tested on "
                          "the UNCAPPED differences (D3b-1, P2); a composite null 'mean <= 0' with an asymmetric "
                          "difference distribution is not covered. Accepted by the owner and stated as the claim's scope "
                          "(D2, 2026-10-20). Disclosed by the final scientific review (2026-10-20): (I-1) which cells are "
                          "capped depends partly on registered arms' outcomes, the comparator's included, so the size is "
                          "conditional on that partition and can exceed nominal slightly; the candidate cannot steer it; "
                          "an owner option not taken is to derive the cap set from arms other than the comparator or from "
                          "separate seeds. (I-6) a candidate that gains uncapped but loses in capped cells is stopped "
                          "only by the percentile-bootstrap lower bound, whose level is approximate. (I-5) the bootstrap "
                          "uses numpy's Generator.multinomial; the numpy version is bound by the formal environment "
                          "manifest (D7)",
            "power_study": "authorised by the owner (ODC-O1b, D2, 2026-10-20): a bounded, non-formal power and "
                           "null-calibration study on SYNTHETIC records only, run after D3 fixes the caps; its result "
                           "is evidence for the owner, never a formal measurement. RAN 2026-10-20: " + POWER_STUDY_EVIDENCE
                           + " sha256 " + POWER_STUDY_EVIDENCE_SHA256,
            "holm": {"alpha": v02_analysis.ALPHA, "family": list(v02_analysis.PRIMARY_FAMILY), "procedure": "unchanged"},
            "control_solved_rule": "a control cell (non-discoverable kind, per presentation) where any registered "
                                   "non-adversarial arm earns full credit with an exact binary-bootstrap lower bound >= "
                                   + str(analysis.CONTROL_SOLVED_LIMIT) + " is capped (pilot P-2); capped cells count "
                                   "as in cap_rule (D3b-1)",
            "claim_scope": analysis.CLAIM_SCOPE,
            "record_binding": "every analysed record carries tier and tier_bound 'formal', the v0.3 harness id, the "
                              "preregistered root commitment, w and environment digest, and ONE attempt digest (D-09); "
                              "these labels gain authority only through the evaluator's post-reveal verify_attempt",
            "bootstrap": f"lower bound only; {v02_analysis.BOOTSTRAP} resamples of world sets as multinomial counts "
                         "from numpy default_rng(0), the capped statistic recomputed per resample, floor order statistic "
                         "(D3b-1)",
            "kind_noninferiority": {"margin": analysis.KIND_NONINFERIORITY_MARGIN, "required": "every kind (D3b-2)",
                                    "statistic": "the capped statistic of that kind alone, per world set"},
            "unchanged": "unit of analysis, grid, comparison set, strongest baseline, representation-limited rule, "
                         "presentation non-inferiority margin, screening and its cap, identity binding: as in v0.2",
        },
        "formal": {
            "driver": "benchmarks/genesis_lite/v0_3/formal.py",
            "evaluator": {"name": EVALUATOR, "selection_deadline": EVALUATOR_DEADLINE,
                          "criteria": "independent of the operator: no access to the operator's machine, the root, the run log or the registry before the reveal; holds the EvaluatorInbox on their own machine; can run formal.verify_attempt and analysis.lift_decision; agrees to publish the verdict whatever it is",
                          "duties": "receives every admission before the first world and the run-log and registry heads at the end; reviews the candidate's pinned source; after the reveal runs verify_attempt and lift_decision(verification=...)"},
            "budget": {"baseline_hours": BASELINE_BUDGET_HOURS, "candidate_hours": CANDIDATE_BUDGET_HOURS,
                       "total_hours": TOTAL_BUDGET_HOURS,
                       "rule": "formal.run_formal checks the elapsed time before each world set and stops past "
                               "total_hours: BUDGET_EXCEEDED, INVALID, never partially claimed (Genesis section 10.6)",
                       "scope": "the cap times the operator's run only (about half of the ESTIMATED 58 h, which counts "
                                "the evaluator's replay as a second run); the evaluator's replay is budgeted separately; "
                                "overshoot is bounded by the world set in progress (every arm's cards x the per-card "
                                "timeout)"},
            "timing_pilot": {"evidence": TIMING_PILOT_EVIDENCE, "evidence_sha256": TIMING_PILOT_EVIDENCE_SHA256,
                             "labels": "MEASURED on the D7 machine through the D5 namespaces; the formal hours are "
                                       "ESTIMATED from it and exclude the candidate's own cost (D4)"},
            "deployment": {"decided": "D5 option A1 (owner, 2026-10-20); amended to D5-A1b (owner, 2026-10-21)",
                           "kind": isolation.DEPLOYMENT,
                           "superseded": {"A1": "rootless_namespaces: superseded for the formal deployment by D5-A1b "
                                                "(2026-10-21); its evidence is historical",
                                          "A1_evidence": A1_DEPLOYMENT_EVIDENCE,
                                          "A1_evidence_sha256": A1_DEPLOYMENT_EVIDENCE_SHA256},
                           "image": f"{isolation.IMAGE_REPOSITORY}@{isolation.IMAGE_DIGEST}",
                           "image_id": isolation.IMAGE_ID, "podman_version": isolation.PODMAN_VERSION,
                           "private_tmpfs": list(isolation.PRIVATE_TMPFS), "device_nodes": "no exemption (owner, "
                                                                                          "2026-10-21)",
                           "evidence": DEPLOYMENT_EVIDENCE, "evidence_sha256": DEPLOYMENT_EVIDENCE_SHA256,
                           "rule": "every formal card through isolation.formal_launcher(): a brand-new rootless Podman "
                                   "container, refused where unavailable; before admission formal.deployment_problems() "
                                   "collects fresh A/B/C container evidence and refuses unless it PASSES"},
            "grid": {"campaign_ids": list(v02_analysis.FORMAL_CAMPAIGNS), "seeds": list(v02_analysis.FORMAL_SEEDS),
                     "presentations": list(v02_analysis.PRIMARY_FAMILY[1:])},
            "world_sets": len(v02_analysis.FORMAL_GRID),
            "order": "world-set-major: every arm runs a world set before any of its records leaves the driver",
            "master_label": formal.LABEL + "/{prereg_sha256}/{attempt_nonce}/{presentation}/{seed}/{campaign_id}",
            "root_commitment_sha256": FORMAL_ROOT_COMMITMENT,
            "candidate": CANDIDATE,
            "candidate_rule": "the candidate runs INSIDE the admitted attempt, world-set-major, beside every registered "
                              "arm; its code is pinned by sha256 (its module, its parent packages and every first-party "
                              "import, read statically; calls and imports of known dynamic-loading names are refused as "
                              "a static screen); it may not take a registered arm's name. Static pinning proves WHICH "
                              "bytes run, not what they do: the external evaluator reviews the pinned source before the "
                              "attempt (D6)",
            "admission": "admitted to the attempt registry and PUBLISHED to the external evaluator before the first "
                         "world; after the reveal the evaluator recomputes every master and answer-key digest "
                         "(formal.verify_attempt)",
            "retired_root_commitments": list(RETIRED_PILOT_ROOT_COMMITMENTS),
            "retired_rule": "these pilot roots (v0, v0.1, v0.2; each revealed with its pilot) are listed here; at run "
                            "time the driver also refuses any root another committed preregistration names",
            "root_channel": "stdin only, never the command line",
            "environment_manifest_schema": environment.MANIFEST_SCHEMA,
            "environment_probe_modules": list(environment.PROBE_MODULES),
            "environment_manifest_sha256": ENVIRONMENT_MANIFEST_SHA256,
            "harness_binding": "formal.harness_runner: the v0.3 harness bound to this identity in the formal tier; "
                               "refuses without the escrow half (OD-3)",
            "attempt_registry": "required; admission before the first world (one_attempt_per_root above)",
            "start_condition": "G0 exit (OD-3), OD-20 deployment verified by an independent isolation-probe rerun that "
                               "covers the Genesis-lite secret inventory (FDA-19 / ODC-BL1), OD-18 budget, OD-8 "
                               "evaluator, this identity frozen and approved (OD-19)",
        },
        "arms": {name: ({**old["arms"][name], "code": "benchmarks/genesis_lite/arms.py (v0.2, unchanged)"}
                        if name in old["arms"] else
                        {"family": v03_arms.ARMS[name][1], "stochastic": v03_arms.ARMS[name][2],
                         "role": v03_arms.ARMS[name][3], "code": "benchmarks/genesis_lite/v0_3/arms.py (v0.2 arm "
                         "re-bound: " + v03_arms.RESIDUAL_DOF + "; " + v03_arms.REPLICATE_NOISE + ")",
                         "observations": old["arms"]["careful"]["observations"],
                         "budget": old["arms"]["careful"]["budget"]})
                 for name in sorted(v03_arms.ARMS)},
        "arms_rule": "v0.3 keeps every v0.2 arm and ADDS the FDA-21 variants (<name>_dof); the strongest baseline is "
                     "the maximum over all of them; careful (certified engcore baseline) keeps ddof = 0",
        "known_structural_tells": old["known_structural_tells"] + [
            "FDA-22: INDISTINGUISHABLE worlds draw only the power or exp form; every other law-bearing kind draws two-term "
            "or regime forms 40% of the time (universe.py), so an in-box two-term or regime signature rules out "
            "INDISTINGUISHABLE; measured per universe as law_form; equalising the priors needs a certified generator "
            "change (owner option)",
            "FDA-18: each campaign holds exactly one world of every kind (public mix); with one fresh proposer process per "
            "card a proposer keeps nothing between cards except what the OD-20 deployment fails to block",
        ],
        "arms_not_run": old["arms_not_run"],
        "statistics_unchanged_from_v0_2": {k: old["statistics"][k] for k in ("unit_of_analysis",)},
        "open_items": {
            "FDA-19 / ODC-BL1": "closed on the benchmark side by v0_3/secret_scan.py (proposer-side scan of the root, "
                                "masters, run log and registry); the certified isolation_probe rerun that covers this inventory is a "
                                "start condition (OD-3), not optional",
            "readiness P-1 / P-2": "the isolation deployment is D5-A1b (rootless Podman per card; A1 superseded "
                                   "2026-10-21). The escrow stays in the operator process: the operator_process "
                                   "channel shows no card reaches another process. NOT_PROVEN until the per-card "
                                   "writable-mount evidence (N-1) passes and is pinned",
        },
        "owner_decisions_taken": dict(OWNER_DECISIONS_TAKEN),
        "owner_decisions_open": {
            "D4-identity-freeze": "OD-19; candidate DEFERRED by the owner (2026-10-20) until the evaluator is named; freeze sequence (owner, 2026-10-20): (1) the evaluator is named (D6, by 2026-11-17); (2) the candidate is chosen AFTER that (deferred by the owner), its code brought into this tree and pinned by sha256 (or NONE), and a one-campaign candidate timing completes the D7 budget total; (3) OD-3 recertifies that final pre-freeze HEAD; (4) the operator generates a fresh formal root and commits its sha256; (5) the environment manifest is measured on the D7 machine; (6) the owner's approvals record binds every decision to the final preregistration digest; only then is the status set to FROZEN. Nothing is frozen or pushed before (6)",
            "OD-3": "recertify the tree that contains engcore/blindfold/pair_bound.py (and the FDA-19 probe scope); scheduled by "
                    "the owner (2026-10-20) on the FINAL pre-freeze HEAD, after the D4 candidate is pinned and timed; the "
                    "owner's manual operation",
        },
    }
    if doc["status"] == "FROZEN" and formal._mentions_owner_decision(doc):
        raise ValueError("a FROZEN v0.3 cannot contain OWNER_DECISION_REQUIRED")
    if FORMAL_ROOT_COMMITMENT in RETIRED_PILOT_ROOT_COMMITMENTS:
        raise ValueError("the formal root commitment is a retired pilot root")
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
