---
ai_schema_version: 1
doc_id: FORGE-GENESIS-LITE-V0-3-AMENDMENT-DECISIONS
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: multiple
evidence_level: EXECUTED_BOUNDED
last_reviewed: 2026-10-20
supersedes: none
---

> **Status correction 2026-10-21:** the status statements below predate the fifth review and are superseded by
> §6. They are the READY_TO_FREEZE_PENDING_OWNER verdict, the FDA-18 residual "closed by D5", readiness P-1/P-2
> "FIXED by D5", "D5 ... verified" and the source refs in §0. The D1-D7 decision text is unchanged.

# Genesis-lite v0.3: freeze readiness and the owner's decisions

> **Nothing here is approved, frozen or certified.** v0.3 is a DRAFT identity on two local branches, and v0.2 stays
> the active identity. On the escrow-branch tip, the freeze-readiness gate reports **READY_TO_FREEZE_PENDING_OWNER**:
> no technical blocker it can see remains, only the owner's decisions and OD-3. That verdict means every named test
> passed on a clean HEAD. It does not mean no defect is left (§2 lists the residual limits).
>
> An approval of one decision implies no other. Freezing is not approval to run anything: formal baselines, a Mind
> tier, recertification, push and merge each need their own approval.

## 0. Where the work is (source refs)

| Branch | Contains | Certified files |
|---|---|---|
| `feat/genesis-lite-v03-amendment-draft` | the v0.3 package (`benchmarks/genesis_lite/v0_3/`), tests, the DRAFT preregistration, docs | none touched |
| `feat/genesis-lite-v03-escrow-fda05`, stacked on the draft | adds `src/engcore/blindfold/pair_bound.py`, its tests and the regenerated preregistration | one NEW file (`certified:verdict_authority`); `escrow.py`, `roles.py` and `__init__.py` are byte-identical to `origin/main` |

- Base: `origin/main` `8ec97064`. Nothing is pushed.
- The exact tips and every command are in `docs/work/PROGRESS.md`, entry "2026-10-20 — BR-MIND-02B".
- The gate: `python -m benchmarks.genesis_lite.v0_3.readiness`. It runs the v0.3 test files itself, binds the result
  to the clean HEAD, and exits 0 only on PASS.

Because the escrow half is a NEW module, v0.2's pinned substrate does not move. v0.2 still rebuilds and still runs as
its own identity; a test checks this.

## 1. Blocker closure

"P-1/P-2/P-3" names two different lists in this repository: the pilot findings (`docs/discovery/GENESIS_LITE_V0.md`
§7) and the readiness-review isolation items (quoted in the closure plan and in X3). Both lists are covered below.

| Blocker | Original finding | Status | Evidence (exact tests named in `readiness.REQUIRED_TESTS`) |
|---|---|---|---|
| FDA-05 evaluator half | R-05 | FIXED_AND_TESTED | The bracket route is bounded by w; w is bound to the preregistration |
| FDA-05 escrow half | R-05 | FIXED_AND_TESTED; **UNCERTIFIED (OD-3)** | `pair_bound.py` runs `EscrowService._score`'s own code with only `_assess_pair` bounded; the config digest seals w. Failing-first on an unbounded stub: 10/16 failed, including an end-to-end `EVALUATOR_DISAGREEMENT`. The evaluator and the escrow agree on 40/40 synthetic cases |
| FDA-06 | R-06 | FIXED_AND_TESTED | Caps discoverable, spurious, confounded and indistinguishable |
| O-1 | static | FIXED_AND_TESTED | Sign-flip p; the bootstrap is used only for the bound |
| **FDA-18** | D-03 | FIXED_AND_TESTED (process memory, temp files, bytecode cache); residual closed by D5 | One process, temp directory and pycache per card. v0.2 carries state across cards (pinned). The same-account residual is closed by the D5 namespaces (cross_card_state and persistence REFUSED, with power shown) |
| **FDA-21** | E-07 | FIXED_AND_TESTED | `<name>_dof` arms are added beside the unchanged v0.2 arms. Residual variance: v0.2 2/6 σ², v0.3 1.0 σ². `careful` (certified) keeps ddof = 0, a documented exception |
| **FDA-22** | D-07 | FIXED_AND_TESTED (declare and measure) | The tell is reproduced and declared, and `law_form` is recorded and re-derived. Equalising the priors is a D3 option (certified `universe.py`) |
| FDA-19 | D-05 | FIXED_AND_TESTED (benchmark side) | `secret_scan.py` (streamed; wrapped and UTF-16 hex). It does not detect encoded copies or raw secrets inside large binary files (stated limits) |
| **pilot P-1** (always_law) | §7 | NOT_A_REAL_BLOCKER | Solved by the v0.1 joint endpoint; proven on v0.3 |
| **pilot P-2** (control cells) | §7 | FIXED_AND_TESTED | CONTROL_SOLVED cap: a control cell that a registered arm already solves cannot carry a gain. The lift is labelled JOINT_BENCHMARK_LIFT, never a discovery lift |
| **pilot P-3** (out-of-family share) | §7 | FIXED_AND_TESTED | FDA-06 cap |
| **readiness P-1/P-2** (isolation deployment, out-of-process escrow) | readiness §2 | FIXED by D5 (A1) | The deployment is the D5 namespaces. The escrow stays in the operator's process: the `operator_process` channel shows no card can reach any other process. Wiring the certified `escrow_server.py` out of process is not required, and the certified isolation-probe rerun is OD-3 |
| **readiness P-3** (attack arms) | §2 | FIXED_AND_TESTED | Twelve channels, run through the harness's per-card processes. A channel that cannot be tested reports UNTESTABLE, never a vacuous REFUSED. Verification needs every channel REFUSED in the D5 deployment and REACHED without it or with capabilities (probe power) |
| **v0.3 harness** | — | FIXED_AND_TESTED | `bind()` refuses: the v0.2 prereg, a dict that only says FROZEN, a changed w, a changed credit table, a changed environment, a modified evaluator, a formal binding of a DRAFT, a missing escrow half. Formal lockdown: no hooks, extra paths or caller arm specs. Records carry their sealed proposals |
| **escrow FDA-05 agreement** | — | FIXED_AND_TESTED | The escrow and the evaluator apply the same bracket identity and w, bound the same hits, give the same credit and refuse the same inputs. Any disagreement makes the run INVALID |
| **one attempt per root** | review | FIXED_AND_TESTED | The registry (nonce, time, chained, self-digest) admits the attempt before the first world. The admission is published to the evaluator's `EvaluatorInbox`, which refuses a second admission. Masters mix in the nonce |
| post-reveal verification | review | FIXED_AND_TESTED | `verify_attempt` reads the whole published log and requires exactly the expected runs. It re-derives keys, shown cards, kind, law form and the searched-family flag, re-scores every sealed proposal, replays every registered arm, and re-derives screens. `lift_decision` requires a clean verification |
| P-4 driver / P-5 manifest | readiness | FIXED_AND_TESTED | The candidate runs inside the attempt. Its code is pinned statically: the module, parent packages, first-party imports and dynamic-loading calls; candidate code never runs on the operator's side. The manifest records every installed distribution. The driver refuses a dirty checkout |

## 2. Hostile reviews (five static rounds, read-only reviewer agents; none executed code)

| Round | BLOCKER | MAJOR | Disposition |
|---|---|---|---|
| 1 (first draft) | 0 | 6 | 4 fixed; the pass route → D1; the evidence record written |
| 2 | 1 (the candidate could not run inside the attempt) | 7 | all fixed or routed (§1) |
| 3 | 1 (a fix imported candidate code as the operator) | 2 | fixed (static pinning; whole-log verification and replay) |
| 4 | 0 | 2 | fixed (sealed proposals re-scored, key fields re-derived, replay wired; CPython resolution) |
| 5 | 0 | 1 (screened world sets unverifiable) | fixed: the screen is re-derived. MINORs fixed: package markers pinned, per-card pycache, call-site dynamic screen, `import *`, bound validation, verification required by `lift_decision` |

**Residual limits, routed to governance rather than code:**

- **Operator honesty.** The operator holds the root, the escrow and the inbox file. It could fabricate a candidate's
  proposals together with a consistent log before publishing. Only the OD-20 separation and an external evaluator
  that receives the admission before the first world (D5, D6) close this.
- **Behaviour versus bytes.** Static pinning proves which bytes run, not what they do. Code reached through attribute
  tricks or through pinned helpers is covered by the evaluator's review of the candidate's source (D6).
- **Untested defects.** The gate is only as strong as its named tests. A defect no test exercises can pass it, which
  is why every BLOCKER and MAJOR above has a named test.
- **Replay environment.** Replay assumes the evaluator's machine matches the formal environment (D7).

## 3. The owner's decisions (the smallest coherent set)

Earlier IDs fold into these:

| Decision | Absorbs |
|---|---|
| D1 | ODC-05a/b/c/d |
| D2 | ODC-O1a/b |
| D3 | ODC-06a/b, FDA-21, FDA-22, FDA-18, pilot P-2 |
| D4 | OD-19 |
| D5 | OD-20 |
| D6 | OD-8 |
| D7 | OD-18 |

As far as the live documents show, none of them was decided elsewhere. No threshold below is chosen on the owner's
behalf.

| ID | Exact choice | Option A | Option B | Recommended | Scientific consequence |
|---|---|---|---|---|---|
| **D1-scoring** | The bracket bound, w, and the pass route | **DECIDED 2026-10-20 (owner, in session):** (i) ratio cap on the bracket route only; **w = 3 × tol** (`tol_multiple` 3.0), anchored a priori on the generator's declared separation scale (`OUTSIDE_TOLERANCES = 3`), never tuned on pilot or formal worlds; v0.3 only; pass route kept at +1.0 | — | — | Honest spreads up to 3·tol (0.09–0.24) earn bracket credit; a pair just under the bound can still be gamed (threshold gaming). The honest (law, rival) pair is unaffected. A passing law with an arbitrary partner keeps +1.0 in INDISTINGUISHABLE worlds and −0.5 in discoverable ones. |
| **D2-significance** | The O-1 route | **DECIDED 2026-10-20 (owner, in session):** ODC-O1a route B, the one-sided paired sign-flip p. The Monte-Carlo stream is keyed by the revealed formal root (K = HMAC-SHA256(root, `forge.genesis_lite.v0_3/sign_flip_stream/<prereg sha>`)). It is unknown to the proposer while the attempt runs and fixed once the root is committed, so no stream can be chosen after the commitment (pre-commitment root grinding is open as D2b); `lift_decision` refuses a root whose sha256 is not the commitment. Holm, alpha and the family are unchanged; the bootstrap is used for the lower bound only. The exchangeability null scope is accepted and stated in the preregistration. ODC-O1b: a bounded, non-formal power and null-calibration study on synthetic records only is authorised, to run after D3 | — | — | The composite null 'mean ≤ 0' with an asymmetric difference distribution is outside the claim's scope. The study ran on 2026-10-20 (evidence pinned by sha256). The scientific review of 2026-10-20 found that whoever generates the root can grind roots before committing; that is open as D2b. |
| **D2b-root-grinding** | Raised by the scientific review 2026-10-20 (I-1) | **DECIDED 2026-10-20 (owner, relayed verbatim from the parent session): bind the admission nonce into the HMAC derivation so pre-commit root grinding is refused.** K = HMAC-SHA256(root, label / prereg digest / admission nonce / admission digest). `lift_decision` keys p only with a self-consistent formal admission of this root and preregistration that every record carries. Failing-first: on the prior code the claim's stream equalled the pre-commit computable HMAC(root, label/prereg) (True); `test_d2b_a_root_ground_before_commitment_cannot_fix_the_claims_stream` failed, then passed | — | — | Residual, disclosed: an operator who runs complete attempts privately (off the registry) and publishes only the admission of the best one is NOT stopped by the key; the evaluator receiving each admission before the first world (D6) narrows this, but an inbox cannot order publication against execution. That is the operator-honesty residual of the decision record. |
| **D3-baselines-and-tells** | Comparison set and tells | **DECIDED 2026-10-20 (owner, in session): option A as drafted.** ODC-06a: Genesis §10.5 rule 4 governs. ODC-06b: the cap covers all four law-credit kinds (discoverable, spurious_correlate, confounded, indistinguishable). FDA-21: `careful` keeps ddof = 0 (certified, documented exception) and the `_dof` arms join the strongest-baseline maximum. FDA-22: the form tell is declared and `law_form` measured; the priors are not equalised. FDA-18: one proposer process per card. Pilot P-2: CONTROL_SOLVED at an exact binary-bootstrap lower bound ≥ 0.5 | — | — | No certified change. The tell stays exploitable by any proposer, and the claim says so. |
| **D3b-1-cap-form** | Raised by the ODC-O1b study | **DECIDED 2026-10-20 (owner, in session): option B, cell-level cap.** A capped (kind, presentation) cell contributes min(0, its summed paired difference) to the effect size (recomputed in every bootstrap resample) and to the per-kind non-inferiority. **Implementation P2 (owner, same session):** the sign-flip p uses the uncapped differences only. The first implementation, with the min inside every sign vector, let capped wins raise significance (p = 0.002 at a mean difference of 0; caught by the adversarial test). v0.3 only | — | — | No gain through a capped class in the effect size, and capped data never enter p (tested). Disclosed by the final review (I-1): which cells are capped depends partly on the comparator's own outcomes, so the size of p is conditional on that partition and can exceed nominal slightly. An owner option not taken: derive the cap set from arms other than the comparator, or from separate seeds. A net loss still counts. A residual noise bias of −σ_cell/√(2π) per noisy capped cell remains: -0.092 per world set at equal skill with 20 capped control cells (study re-run on the decided rule). The builder's earlier "about −0.006" omitted the sum over cells. |
| **D3b-2-kind-noninferiority** | Raised by the ODC-O1b study | **DECIDED 2026-10-20 (owner, in session): option B.** The per-kind margin is 0.15 and every kind is still required; the presentation margin is unchanged. v0.3 only | — | — | The margin applies to the lower bound of the mean credit difference (about 0.094 credit at the study's SE). The rate it tolerates depends on the outcome lost (final review I-3): success → failure (+1 → −1) about 7.5 points, success → refusal (1 → 0) about 15 points, indistinguishable_hit → insufficient_evidence (1 → 0.5) about 30 points. **RECONFIRMED by the owner on 2026-10-20 at 0.15** (relayed verbatim): a non-inferiority guardrail, not an equivalence claim and not an acceptable-degradation claim. The 7.5 / 15 / 30-point success-rate readings are recorded in the preregistration. |
| **D4-identity-freeze** | OD-19 | **OPEN; the candidate was DEFERRED by the owner on 2026-10-20 until the evaluator is named.** Freeze sequence: (1) evaluator named (D6); (2) candidate chosen, its code brought in and pinned by sha256 (or NONE), and a one-campaign timing completes the budget; (3) OD-3 recertifies that final HEAD; (4) fresh root generated and its sha256 committed; (5) manifest measured on the D7 machine; (6) the approvals record binds everything to the final digest; then FROZEN | — | — | Freezing fixes every bound value; a later change is a v0.4. |
| **D5-deployment** | OD-20 | **DECIDED 2026-10-20 (owner, in session): option A1, rootless Linux namespaces (`isolation.py`).** Every formal card is launched through `formal_launcher()` (refused where unavailable). Proposers run without capabilities (setpriv). Verification evidence ([evidence](../work/evidence/genesis_lite_v0_3_d5_deployment_2026_10_20/README.md), sha256 `519f3669b48b5bd0…`, on the owner's hardened Ubuntu-24.04): twelve channels REFUSED in the deployment, each REACHED by the same probe in a control configuration. **The isolation boundary is NOT_PROVEN** until every writable location is shown private to its card (fifth review, N-1) | — | — | Residual: the same Linux account outside the namespaces; WSL shares the host VM; the certified isolation-probe rerun is OD-3. |
| **D6-evaluator** | OD-8 | **DECIDED 2026-10-20 (owner, in session): a selection process with a deadline of 2026-11-17.** Criteria: independent of the operator: no access to the operator's machine, the root, the run log or the registry before the reveal; holds the EvaluatorInbox on their own machine; can run formal.verify_attempt and analysis.lift_decision; agrees to publish the verdict whatever it is. Duties: receives every admission before the first world and the run-log and registry heads at the end; reviews the candidate's pinned source; after the reveal runs verify_attempt and lift_decision(verification=...) | — | — | The name stays OWNER_DECISION_REQUIRED in the preregistration, so the freeze is refused until someone is named. If nobody is named by the deadline, D6 reopens. |
| **D7-budget-and-machine** | OD-18 | **DECIDED 2026-10-20 (owner, in session).** Machine: the owner's WSL machine, since 2026-10-20 a fresh Ubuntu-24.04 distro hardened by the owner (interop and automount disabled). The manifest is measured there at freeze. A timing pilot ran first, on the earlier distro ([evidence](../work/evidence/genesis_lite_v0_3_d7_timing_pilot_2026_10_20/README.md)): MEASURED 43.5 s per world set for the 20 baselines; ESTIMATED 58 h (57–59) formal with replay. The budget was decided on that run; the re-run under the capability drop measured 43.7 s. **Budget: 72 h for the baselines plus the candidate's cost from a one-campaign timing at D4.** `formal.run_formal` stops past the total as BUDGET_EXCEEDED (INVALID, never partially claimed) | — | — | The total stays OWNER_DECISION_REQUIRED until D4 measures the candidate, so a freeze is refused until then. |
| **OD-3** | Recertification | **SCHEDULED 2026-10-20 (owner, in session): on the final pre-freeze HEAD**, after the D4 candidate is pinned and timed; one recertification of exactly the tree that freezes (the owner's manual operation) | — | — | Until then the escrow half and every v0.3 run are UNCERTIFIED. |

The approval record is the owner's file,
`benchmarks/genesis_lite/preregistration/genesis_lite_v0_3.owner_approvals.json`. Each decision needs:
- `status: APPROVED`;
- the `choice`;
- `prereg_sha256` (the preregistration it approves).

D1 also names `pair_bound`, and OD-3 names `certified_head`. The gate never writes this file.

## 4. The owner's next action

1. Name the evaluator by 2026-11-17 (D6 selection), then decide the D4 candidate (deferred until then) and schedule OD-3 on the final pre-freeze HEAD (owner, 2026-10-20). D6 is decided (selection process). D5 is decided (A1) and verified; D7 is decided (budget: 72 h for the baselines plus the candidate's measured cost). D2b is decided and D3b-2 reconfirmed (2026-10-20). D3b-1 and D3b-2 are decided (2026-10-20); the power study is re-run on the decided rule. D3 is decided (2026-10-20): option A as drafted. The power and null-calibration study (ODC-O1b) ran on 2026-10-20; its evidence is in `docs/work/evidence/genesis_lite_v0_3_power_study_2026_10_20/`. D2 is decided (2026-10-20): a root-keyed sign-flip stream, the null scope accepted, and the power study authorised after D3. D1 is decided (2026-10-20): `PAIR_BOUND` is set in the evaluator, and the preregistration lists it under `owner_decisions_taken`. The approval record is written once all decisions are taken, so that every entry names the FINAL preregistration digest (each decision changes it).
2. Set `PAIR_BOUND`, `CANDIDATE`, `FORMAL_ROOT_COMMITMENT` (a fresh root) and `ENVIRONMENT_MANIFEST_SHA256` (measured
   on the D7 machine), and set `STATUS = "FROZEN"`. Regenerate, commit, and rerun the gate.
3. Run OD-3 on that HEAD.

The gate then reports PASS or names exactly what is still missing.

## 5. Not done, not authorised

- No freeze, push, PR, merge, recertification, formal baseline, Mind tier or formal measurement.
- No change to v0/v0.1/v0.2 or to any existing certified file.
- No re-scoring of v0.2 records.

## 6. Status correction (2026-10-21, clean rebuild on restored main)

This section supersedes the status statements in the header blockquote, in section 0 and in section 1 (the FDA-18 and readiness P-1/P-2 rows), and the claim in section 4 that D5 is verified. Everything else above is unchanged; in particular, no D1-D7 decision text was edited.

- **Where the work is.** The premature PR #174 merge (070f47db) was reverted by PR #182, so main 12862b0b has a tree identical to pre-#174 main 9f1c24f1. This record now lives on `feat/genesis-lite-v03-clean-n1`, which was rebuilt from that main by byte copies from 1cb5e187. The branches named in section 0 are preservation history.
- **The gate.** `python -m benchmarks.genesis_lite.v0_3.readiness` reports **BLOCKED_TECHNICAL**, not READY_TO_FREEZE_PENDING_OWNER. Its technical blockers are exactly the three rows that `readiness.LEDGER` marks BLOCKED_WITH_EVIDENCE_NOT_PROVEN:
  - FDA-18 residual (same-account files, helper processes);
  - the isolation boundary (D5);
  - readiness P-1/P-2.
  The evaluator and the escrow agree on 48 of 48 synthetic cases, which supersedes the 40/40 in the section 1 FDA-05 escrow-half row.
- **Truthful status.** D5 = NOT_PROVEN. FDA-18 residual = NOT_PROVEN. N-1 = OPEN. A formal campaign is FORBIDDEN.
- **Evidence.** The D5 deployment (519f3669) and D7 timing pilot (3759ff33) records are historical. Their recorded heads (a4d73dd4 and f7df8968) are not this branch's HEAD, and f7df8968 is on no remote branch. Both records require a rerun and a re-pin after N-1. The power study (9ad27938, head 20f3d379) is historical evidence for D2/D3b.
- **An open owner decision, not recorded above.** The N-1 failing-first tests carried onto this branch require a fresh Podman container per card:
  - `test_genesis_lite_v0_3_container_isolation.py`;
  - `test_genesis_lite_v0_3_container_contract.py`;
  - `container_isolation_probe.py`.
  They require pinned `podman` arguments, a `localhost/forge-card@sha256:...` image digest, and a proposed `validate_container_evidence` contract with schema `checkpoint2.container_evidence.contract/2`. The recorded D5 decision (option A1, rootless namespaces, `isolation.DEPLOYMENT = "rootless_namespaces"`) does not say this. Implementing those tests as written changes the D5 deployment. Before the N-1 repair, the owner must either record that change as an amendment to D5, or keep A1 and have the tests recast. Nothing in these tests is a decision.
