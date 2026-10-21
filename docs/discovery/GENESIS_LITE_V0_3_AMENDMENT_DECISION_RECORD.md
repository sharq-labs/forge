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
>
> **Status correction 2026-10-21 (CHANGE_RUNTIME_BOUNDARY):** §10 closes the rootless Podman runtime as
> BLOCKED_BY_D5_DEVICE_BOUNDARY, gives the evidence type of every BLOCKER 1 statement, and corrects §3, §7, §8 and §9
> wording in 10.2. D5 = NOT_PROVEN, N-1 = OPEN, D7 = REQUIRES_RERUN.

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
| **D5-A1b-deployment** | OD-20 (amends D5) | **DECIDED 2026-10-21 (owner, in session): D5-A1b, rootless Podman per-card isolation. A1 is SUPERSEDED for the formal deployment** (the row above stays as the historical decision). Reason: the fifth review showed that the hand-built namespace probe had not proven cross-card state isolation outside /tmp. A1b is a bounded implementation refinement of the approved rootless-namespace route, not a weakening of it: Podman provides the rootless Linux namespace boundary. The contract: a brand-new container for every card; no container reuse; read-only root filesystem; read-only FORGE source and Python environment; network=none; all capabilities dropped; no-new-privileges; rootless user namespace; private writable mounts for the card; complete writable-mount inventory; Card-A/Card-B canary isolation; a deliberately shared-volume positive control; deployment verification before admission (`isolation.py`, `container_evidence.py`, `container_probe.py`, `formal.deployment_problems`). **Device nodes (owner, 2026-10-21): no exemption.** A writable device or pseudo-file mount stays blocking | — | — | D5 stays NOT_PROVEN until D5-A1b evidence passes and is pinned (section 7). |
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

## 7. D5-A1b and the device-node decision (owner, 2026-10-21)

This section records two owner decisions taken after section 6 was written. Section 6's "open owner decision"
bullet is now decided by D5-A1b. Nothing above is rewritten.

- **D5-A1b.** Rootless Podman per-card isolation (the D5-A1b row in section 3) supersedes A1 for the formal
  deployment. The historical A1 decision, its evidence (sha256 `519f3669...`) and its tests stay as history.
- **Device nodes.** Rootless Podman (crun) bind-mounts six host character devices read-write into every container:
  `/dev/null` 1:3, `/dev/zero` 1:5, `/dev/full` 1:7, `/dev/random` 1:8, `/dev/urandom` 1:9 and `/dev/tty` 5:0.
  They cannot be removed, because rootless crun cannot create device nodes. The owner chose **strict**: no exemption,
  so they stay blocking (`DEVICE_NODE_WRITABLE_MOUNT`). With this runtime, D5 and N-1 therefore cannot pass. Passing
  needs a runtime without these mounts, or a later owner decision.
- **Runtime reduction (implementation, not a policy).** With `/dev` mounted as a read-only tmpfs, the devpts and
  mqueue mounts disappear. The writable mounts left are the four declared private tmpfs and the six device nodes.
- **Cgroup root (implementation).** The card's own and the operator's host-side mount views must match field for
  field. The one exception is the `root` of a cgroup filesystem, which the kernel reports relative to the reader's
  cgroup namespace (cgroup_namespaces(7)).
- **D7.** The historical timing-pilot head `f7df8968` is preserved by the local annotated tag
  `evidence/d7-timing-pilot-head-2026-10-20`. The tag does not make the old timing current. The D7 evidence is
  HISTORICAL_ONLY, REQUIRES_RERUN and REQUIRES_REPIN_AFTER_N1, and the readiness gate carries it as a technical row.
- **Status.** D5 = NOT_PROVEN. FDA-18 residual = NOT_PROVEN. N-1 = OPEN. A formal campaign is FORBIDDEN. The gate
  derives the D5 rows from the preregistration-pinned evidence (`readiness.deployment_status`), so D5 cannot be marked
  proven by hand.
- **Evidence (2026-10-21).** The D5-A1b verification ran on the formal machine from a clean clone of `754f6cdb`
  ([evidence](../work/evidence/genesis_lite_v0_3_d5_a1b_deployment_2026_10_21/README.md), sha256 `590bfa4f…`, pinned
  in the preregistration). It is BLOCKED solely by the six writable host device nodes; every other contract check
  held, and 11 of 12 attack channels were REFUSED (`cross_card_state` stays UNTESTABLE without passing container
  evidence). The earlier run at `c09b0ef5` is kept as superseded history. "Cannot pass with this runtime" refers to
  this runtime and launcher: no alternative launcher configuration was tested beyond `/dev` as a read-only tmpfs.
- **Evidence re-pinned (2026-10-21).** The second review pass replaced the read-only rule with an allowlist that
  ignores the operator's backing label. The verification was re-run from a clean clone of `d4ead0b2` (sha256
  `29c72411…`, now the pinned file) with the same verdict: BLOCKED solely by the six host device nodes. The `754f6cdb`
  run is kept as superseded history.
- **Evidence re-pinned again (2026-10-21).** The third review pass's hardening MINORs were fixed: Podman's own
  read-only mounts are tied to device, root and size, and each kept tree is bound exactly once. The verification was
  re-run from a clean clone of `ad55b7c5` (sha256 `a9bc4c64…`, now the pinned file) with the same verdict: BLOCKED
  solely by the six host device nodes, under the unchanged strict rule. The `d4ead0b2` run is kept as superseded
  history.
- **MINOR-A closed and evidence re-pinned (2026-10-21).** Every card now also shows that its `/proc` and `/sys` are
  its own. Through its `/proc` it is PID 1 (NSpid `["1"]`) of a PID namespace that is not the operator's, and both
  mounts are on devices other than the operator's procfs and sysfs. A positive control shows that a host procfs is
  detected. The verification was re-run from a clean clone of `12baeb04` (sha256 `967f089e…`, now the pinned file)
  with the same verdict: BLOCKED solely by the six host device nodes, under the unchanged strict rule. The `ad55b7c5`
  run is kept as superseded history.

## 8. The device policy amendment: STATELESS_DEVICE (owner, 2026-10-21)

This section records an owner decision taken after section 7. The strict device-node rule above stays as the
historical decision; nothing above is rewritten.

- **Decision (owner, in session, 2026-10-21).** A shared writable character device is not automatically a failure when
  executed evidence proves it is a non-state-carrying operating-system endpoint under the D5 threat model. The
  admissible set is only `/dev/null` 1:3, `/dev/zero` 1:5, `/dev/full` 1:7, `/dev/random` 1:8, `/dev/urandom` 1:9 and
  `/dev/tty` 5:0. No other writable device is admitted, and admission is per device, never for the group.
- **Contract.** `forge.genesis_lite.v0_3/stateless_device/1` (`benchmarks/genesis_lite/v0_3/device_contract.py`).
  Every device must show its exact identity in every card (path, character device, major:minor, mode and owner, the
  host node's device and inode, a private nosuid,noexec devtmpfs bind of exactly that node), no state (unchanged node
  metadata), the semantics of its kind, no recoverable selected message in repeated encoder/decoder trials between
  fresh cards, and no alias. The tty is admitted only without any terminal. Positive controls must show power: a
  shared file must carry the selected bit, and a container given a terminal must be told apart. Any missing, malformed,
  unknown or contradictory field blocks.
- **Randomness.** `/dev/random` and `/dev/urandom` are a shared kernel RNG service, not private per-card state. The
  cards are not claimed to receive independent entropy; the claim is only that a card can neither set nor read their
  state through them. Formal scientific randomness never comes from them: a static screen requires every stochastic
  generator in the Genesis-lite and blindfold code to take an explicit seed, and implicit entropy to appear only at
  declared operational sites. It is a static screen, not a proof.
- **Fallback (owner-ordered).** A device that cannot satisfy its contract is masked or made inaccessible where rootless
  Podman allows; if that is impossible, it stays blocking and D5 stays NOT_PROVEN.
- **Also closed in the same patch.** A missing `/proc` or `/sys` row is incomplete evidence. Malformed or unknown
  operator device records block. The host-procfs control needs both of its signals. The O-1 keyed-stream test no
  longer depends on two Monte-Carlo p values differing.
- **Status.** D5 = NOT_PROVEN until evidence from a clean clone of the final commit passes and is pinned.

## 9. ADMIT_ONLY_PROVEN_STATELESS_SUBSET (owner, 2026-10-21)

The owner narrowed the section 8 policy. Section 8 is kept as history.

- **Admitted only as exact STATELESS_DEVICE endpoints, and only if proven:** `/dev/null` 1:3, `/dev/zero` 1:5,
  `/dev/full` 1:7.
- **Required to be inaccessible in the formal card:** `/dev/random` 1:8 and `/dev/urandom` 1:9, because writes update
  shared kernel RNG state and affect later output; and `/dev/tty` 5:0, to remove controlling-terminal and operator
  interaction risk, including future argv drift.
- **Every other writable device stays a blocker.**
- **Status: NOT IMPLEMENTED; D5 = NOT_PROVEN.** The hostile review's BLOCKER 1 (PROGRESS, 2026-10-21) was confirmed on
  the formal launcher for all six device nodes, including the three this policy would admit. Masking the other three
  therefore cannot make the admitted subset meet the policy's own requirement that Card A cannot leave a value a fresh
  Card B can recover. No launcher configuration that closes BLOCKER 1 for null, zero and full has been shown, so
  admitting them would weaken the policy. The owner instruction for this case applies:
  BLOCKED_WITH_PRECISE_EVIDENCE.

## 10. CHANGE_RUNTIME_BOUNDARY: the current runtime is closed as BLOCKED (owner, 2026-10-21)

The owner decided **CHANGE_RUNTIME_BOUNDARY**. Nothing in sections 0 to 9 is rewritten. The dated corrections in
10.2 say which earlier wording no longer stands.

- The scientific device policy (sections 8 and 9) and every acceptance criterion are unchanged.
- The rootless Podman formal-card runtime is closed as **BLOCKED_BY_D5_DEVICE_BOUNDARY**. Its implementation and
  evidence are kept (10.4).
- A replacement runtime is not selected. The owner-facing comparison is
  [GENESIS_LITE_V0_3_D5_RUNTIME_BOUNDARY_HANDOFF.md](GENESIS_LITE_V0_3_D5_RUNTIME_BOUNDARY_HANDOFF.md).

### 10.1 Evidence taxonomy

| | Evidence type | What it is | What it supports |
|---|---|---|---|
| **A. Executed detector result** | MEASURED | Source: the D5 run at `2e2a9d1b`, pinned at `b1fbefbf` and reverted by `3d62b494`, so it exists only in git history (`result.json` sha256 `b3bc0b64…`). The device trials and the decoder compared message bytes and metadata. All 30 recorded decoder reads recovered no selected message: every `found` flag under `container_evidence.cards[*].devices` and `container_evidence.device_trials` is false. The reads were made by fresh decoder cards (B, C and the trial decoders) over null, zero, full, random and urandom. In `positive_controls.device_channel`, the shared-file control recovered it in both bit directions. To read the record: `git show b1fbefbf:docs/work/evidence/genesis_lite_v0_3_d5_a1b_deployment_2026_10_21/result.json`. | No selected message bytes were recovered in any recorded trial. **The detector did not exercise the mechanism identified by BLOCKER 1, so it neither proves nor disproves BLOCKER 1.** It is NOT_MEASURED_BY_CURRENT_DETECTOR. The pinned run `967f089e` at `12baeb04` predates the trials (`2e2a9d1b`) and holds none. |
| **B. Static review finding** | STATIC_REVIEW | The independent hostile read-only review of `99959b09` (2026-10-21) returned 1 BLOCKER, 2 MAJOR, 7 MINOR and 5 NOTE. The reference is PROGRESS, entry "2026-10-21 — Prompt 3". | **BLOCKER 1**, classified BLOCKER. Its stated scope is all six writable device nodes: null 1:3, zero 1:5, full 1:7, random 1:8, urandom 1:9 and tty 5:0. Its mechanism is not reproduced or expanded here. |
| **C. Formal-machine confirmation** | FORMAL_MACHINE_CONFIRMATION | The implementer separately confirmed the review finding on the formal launcher, in session and before the revert. It was an executed, ad-hoc check. No artifact was kept in the repository: no command record, output or digest. It is not reproducible from the tree. | That the reviewed finding was observed by the implementer on the formal launcher for the six nodes; unpinned. **It is not a selected-message detector measurement.** No trial recovered, or tried to recover, a selected message through BLOCKER 1's mechanism. |
| **D. Current scientific status** | BLOCKED | Derived by the gate (10.3). | D5 = **NOT_PROVEN**. N-1 = **OPEN**. CURRENT_ROOTLESS_PODMAN_RUNTIME = **BLOCKED_BY_D5_DEVICE_BOUNDARY**. D7 = **REQUIRES_RERUN**, only after a replacement runtime is selected. No freeze, certification or formal campaign is permitted. |

What this taxonomy rules out:

- **Device identity.** Device identity alone (path, major:minor, a shared host node) does not prove a communication
  channel.
- **Recovery.** Recovery of a selected message through BLOCKER 1's scope was not experimentally demonstrated.
- **Closure.** BLOCKER 1 is unresolved because only B and C support it. It is not resolved by A, which never tested
  it.

### 10.2 Dated corrections (2026-10-21) of earlier wording

Each of these is kept above as written and is corrected here.

- **Section 3, row D5-A1b.** "D5 stays NOT_PROVEN until D5-A1b evidence passes and is pinned." On this runtime,
  passing and pinned evidence is no longer sufficient. BLOCKER 1 is open, so D5 is BLOCKED on this runtime whatever
  that evidence says (10.3).
- **Section 8, Status.** "D5 = NOT_PROVEN until evidence from a clean clone of the final commit passes and is
  pinned." This is corrected in the same way. D5 is not closeable on the current runtime without further evidence:
  MEASURED evidence that closes BLOCKER 1's mechanism over its scope, which the current detector does not
  produce.
- **Section 9.** "BLOCKER 1 ... was confirmed on the formal launcher for all six device nodes" is evidence type C
  (FORMAL_MACHINE_CONFIRMATION), not a detector measurement.
- **Section 9.** "cannot make the admitted subset meet the policy's own requirement that Card A cannot leave a value
  a fresh Card B can recover" means the requirement cannot be **shown** met, so it stays BLOCKED. It does not mean
  that a recovery by Card B was demonstrated. That recovery is NOT_MEASURED.
- **Section 7.** "With this runtime, D5 and N-1 therefore cannot pass" was written under the strict no-exemption rule
  and the `967f089e` evidence. It still holds today, because BLOCKER 1 is open (10.1 B and C) and no MEASURED evidence covers
  its scope (10.1 A). It no longer rests on that rule, which section 8 replaced.
- **PROGRESS (Prompt 3 entry).** It reads "This is a cross-card state channel", "all six devices were ADMITTED
  wrongly" and "The D5 PASS is therefore invalid". The corrected reading is STATIC_REVIEW plus
  FORMAL_MACHINE_CONFIRMATION. The admissions and the PASS do not stand, because their detector did not exercise
  BLOCKER 1, not because a channel was measured. PROGRESS carries the same correction.

### 10.3 The gate stays fail-closed (derived, not a hand-set status)

`readiness.BOUNDARY_FINDINGS` records BLOCKER 1 **by finding and scope, not by runtime name**. It holds:

- the evidence types `STATIC_REVIEW + FORMAL_MACHINE_CONFIRMATION`, with a source for each;
- the detector status `NOT_MEASURED_BY_CURRENT_DETECTOR`;
- the six-node scope;
- an empty list of declared detectors;
- the runtime status `BLOCKED_BY_D5_DEVICE_BOUNDARY` for `rootless_podman_per_card`.

The finding is open for every runtime, the current one, a renamed one and any replacement alike. It closes only
when the pinned D5 evidence holds `boundary_findings["BLOCKER 1"]` with all of these:

- `evidence: MEASURED`;
- a `detector` from the finding's declared list;
- a closing result (`REFUSED_WITH_POWER`, `ABSENT` or `PRIVATE_TO_CARD`) for every node in scope.

No detector is declared, so nothing can close it today. The gate checks the closure's declared type and
coverage; it does not re-derive the node results. Declaring a detector is therefore a reviewed code change that
must also add a required test re-deriving every node's result from the raw records in the pinned evidence, as
`container_validation` is re-derived today. The evidence that uses it must still be measured and pinned. Removing the table entry is not a closure; it is a code change to a
preregistration-pinned file.

- `readiness.runtime_boundary_problems()` derives the result from three inputs: that closure, the selected runtime
  (`isolation.DEPLOYMENT`) and the runtime the evidence names.
- `deployment_status()` returns NOT_PROVEN with **`D5_RUNTIME_BOUNDARY_NOT_PROVEN`** in any of these cases:
  - the finding is open, even when the D5 evidence says `verified: true` and even after the runtime is renamed;
  - the D5 evidence measured another runtime;
  - the D5 evidence names no runtime, or a malformed one (blocked, never raised).
- `timing_pilot_status()` keeps D7 a technical blocker while the pilot ran through another runtime, or while the
  pinned D5 evidence leaves the finding open.
- `check()` therefore reports BLOCKED_TECHNICAL, never READY_TO_FREEZE_PENDING_OWNER or PASS. It also returns
  `d5_runtime_boundary: {reason: D5_RUNTIME_BOUNDARY_NOT_PROVEN, problems: [...]}`. That field reflects the D5
  evidence. A D7 runtime mismatch shows in the D7 evidence row.

Tests:

- `test_d5_the_selected_runtime_with_an_open_boundary_finding_never_verifies`;
- `test_d7_a_pilot_on_a_superseded_or_blocked_runtime_is_a_blocker`.

Both are now required tests of their ledger rows. They cover these cases:

- the rename and replacement paths;
- closing sections that are incomplete: an undeclared detector, a non-MEASURED type, a missing `evidence` key, a
  missing node, a non-closing node value, `nodes` that is not a mapping, and a non-mapping section or entry;
- a D7 pilot that carries its own closing section.

They also show the status is derived: a closure declared MEASURED by a declared detector, covering every node, lets
the same record verify.

### 10.4 Preservation of completed work

| Component | Where | Classification |
|---|---|---|
| STATELESS_DEVICE contract and per-device validator | `device_contract.py` (`stateless_device/1`) | REUSABLE with a replacement runtime. The expected node shape (a private devtmpfs bind of the host node) is RUNTIME-SPECIFIC and is re-derived for the replacement. |
| Saved edge cases: a missing `/proc` or `/sys` row; a malformed or unknown device identity; the host-procfs control needing all signals; the O-1 stream without a p-difference assertion | `test_d5_a_missing_proc_or_sys_row_is_incomplete_evidence_and_never_passes`, `test_d5_malformed_or_unknown_host_device_values_block`, `test_d5_a_device_with_a_wrong_identity_is_blocked`, `test_d5_unknown_device_paths_and_aliases_block`, `test_d5_the_host_procfs_control_cannot_pass_on_one_signal`, `test_o1_lift_decision_passes_the_keyed_stream_to_the_monte_carlo_p` | REUSABLE. These are record-level tests, independent of the runtime. |
| Positive controls: shared volume, host listener, shared-file device-channel control, terminal control, host procfs | `isolation.py`, `container_probe.py` | REUSABLE as requirements. Their launch arguments are RUNTIME-SPECIFIC. Their evidence REQUIRES RERUN. |
| `/proc` and `/sys` namespace proofs | `container_probe.py`, `container_evidence.py` (PID-namespace and procfs/sysfs device checks) | REUSABLE probe and checks. Evidence REQUIRES RERUN. |
| Card-A/Card-B (and C) canary infrastructure; selected-message encoder and decoder | `container_probe.py`, `isolation.py` | REUSABLE. It is not, by itself, a detector for BLOCKER 1's scope (10.1 A). |
| Pre-admission verification | `formal.deployment_problems`, the `timing_pilot/2` pre-check (`f8bf7ed7`) | REUSABLE. |
| Twelve attack channels; secret scan | `deployment_attacks.py`, `secret_scan.py` | REUSABLE. Evidence REQUIRES RERUN. |
| Podman launcher, image pin, Containerfile, mount allowlist | `isolation.py` (`DEPLOYMENT`, `IMAGE_*`, `PODMAN_VERSION`, flags), `container/Containerfile`, the allowlist in `container_evidence.py` | RUNTIME-SPECIFIC. |
| D5-A1b evidence `967f089e` (pinned) and `superseded-*/` | `docs/work/evidence/genesis_lite_v0_3_d5_a1b_deployment_2026_10_21/` | HISTORICAL ONLY |
| D5 STATELESS_DEVICE run `b3bc0b64` (pinned at `b1fbefbf`, reverted) | git history | HISTORICAL ONLY. It is the MEASURED source of 10.1 A. |
| A1 evidence `519f3669` | `docs/work/evidence/genesis_lite_v0_3_d5_deployment_2026_10_20/` | HISTORICAL ONLY |
| D7 pilot `3759ff33` (pinned; A1 runtime) | `docs/work/evidence/genesis_lite_v0_3_d7_timing_pilot_2026_10_20/`, tag `evidence/d7-timing-pilot-head-2026-10-20` | HISTORICAL ONLY. D7 REQUIRES RERUN on the replacement runtime. |
| D7 pilot `6f6b1418` (pinned at `99959b09`, reverted) | git history | HISTORICAL ONLY |
| Open findings of the Prompt 3 review (PROGRESS) | MAJOR 1 (the device walk), MAJOR 2 (the attempt keeps only the pre-admission verdict), and the seven MINORs | REUSABLE-OPEN, carried to any replacement: MAJOR 1, MAJOR 2, host-to-card observation untested, D7 binds only 7 files, the gate takes the bound-file list from the evidence, the admission-nonce allowlist text, None seeds pass the screen, and the RNG counters without power on kernel 6.6 (it carries over while the kernel stays). RUNTIME-SPECIFIC: the weak tty control with a null id. |

### 10.5 Status

| Item | Status |
|---|---|
| D5 | NOT_PROVEN |
| N-1 | OPEN |
| Current rootless Podman runtime | BLOCKED_BY_D5_DEVICE_BOUNDARY |
| D7 | REQUIRES_RERUN, after a replacement runtime is selected |
| Freeze, certification, formal campaign, Budget × Noise | not permitted |
