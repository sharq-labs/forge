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
| **FDA-18** | D-03 | FIXED_AND_TESTED (process memory, temp files, bytecode cache) + OWNER (residual) | One process, temp directory and pycache per card. v0.2 carries state across cards (pinned). The residual is measured: same-account files beside the temp directory → D5 |
| **FDA-21** | E-07 | FIXED_AND_TESTED | `<name>_dof` arms are added beside the unchanged v0.2 arms. Residual variance: v0.2 2/6 σ², v0.3 1.0 σ². `careful` (certified) keeps ddof = 0, a documented exception |
| **FDA-22** | D-07 | FIXED_AND_TESTED (declare and measure) | The tell is reproduced and declared, and `law_form` is recorded and re-derived. Equalising the priors is a D3 option (certified `universe.py`) |
| FDA-19 | D-05 | FIXED_AND_TESTED (benchmark side) | `secret_scan.py` (streamed; wrapped and UTF-16 hex). It does not detect encoded copies or raw secrets inside large binary files (stated limits) |
| **pilot P-1** (always_law) | §7 | NOT_A_REAL_BLOCKER | Solved by the v0.1 joint endpoint; proven on v0.3 |
| **pilot P-2** (control cells) | §7 | FIXED_AND_TESTED | CONTROL_SOLVED cap: a control cell that a registered arm already solves cannot carry a gain. The lift is labelled JOINT_BENCHMARK_LIFT, never a discovery lift |
| **pilot P-3** (out-of-family share) | §7 | FIXED_AND_TESTED | FDA-06 cap |
| **readiness P-1/P-2** (isolation deployment, out-of-process escrow) | readiness §2 | OWNER_DECISION_REQUIRED (D5 / OD-20) | Needs a chosen deployment. The certified `escrow_server.py` exists; wiring it follows the D5 choice |
| **readiness P-3** (attack arms) | §2 | FIXED_AND_TESTED | Seven channels, run through the harness's per-card processes. A channel that cannot be tested reports UNTESTABLE, never a vacuous REFUSED. On this same-account host the suite is NOT verified |
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
| **D1-scoring** | The bracket bound, w, and the pass route | (i) ratio cap on the bracket route only. The owner sets w a priori (absolute, or a multiple of tol). v0.3 only. Pass route kept. | (iii) no bracket credit (w at most tol); pass-route pairs scored at the kind's `law_pass` value | A on the form (the audit's recommendation). **No recommendation on w**: it is the owner's. The pass route needs a deliberate choice. | A credits an honest spread up to w, and a pair just under w can be gamed. B is strictest: INDISTINGUISHABLE then rewards only "contains the truth" or refusal. |
| **D2-significance** | The O-1 route | Sign-flip p, as drafted. Null = exchangeability within a world set. Caps err conservative. With the fixed public stream the size is about alpha. | Defer O-1 until the scoring is frozen (BVB handoff §3). Run a bounded null-calibration and power study first. | A, plus a bounded power study on synthetic records before the formal tier (separate approval) | No power analysis is preregistered, and the caps may leave little claimable region. |
| **D3-baselines-and-tells** | Comparison set and tells | As drafted: §10.5 governs the cap; four capped kinds; `_dof` arms added; FDA-22 declared and measured; one process per card; CONTROL_SOLVED | As A, plus equalising the generator's form priors and correcting `careful`'s ddof (both certified, OD-3) | A | A measures the tell; B removes it at the cost of certified changes. |
| **D4-identity-freeze** | OD-19 | Freeze once D1–D3, D5 and D7 are settled. Name the candidate, or NONE for baselines only. The operator generates a fresh root and commits its sha256. | Keep the draft | A, after D5 is verified | Freezing fixes every bound value; a later change is a v0.4. |
| **D5-deployment** | OD-20 | A container or separate OS account with no operator processes or files, no network, no persistence and a read-only package. Verified by `verify_deployment(deployment_runner(...), scan_findings=secret_scan.scan(...))`: every channel REFUSED, none UNTESTABLE, the scan clean. | A separate host | A, or B where a container cannot hide `/proc` | Until D5 is verified, same-account runs are never formal evidence. |
| **D6-evaluator** | OD-8 | A named external evaluator. It receives each admission (inbox) before the first world and the heads at the end; it reviews the candidate's pinned source; after the reveal it runs `verify_attempt` and `lift_decision(verification=...)`. | A selection process with a deadline | A | Without it, one-attempt enforcement and record integrity rest on the operator. |
| **D7-budget-and-machine** | OD-18 | Approve the formal compute and the formal machine (Linux 3.11/3.12, OD-2). The manifest is measured there. | Postpone | A | Per-card processes add a start cost per card (UNMEASURED at formal scale). `_dof` adds 7 arms. Evaluator replay roughly doubles the baseline cost. |
| **OD-3** | Recertification | Recertify a HEAD with `pair_bound.py` and the new tests (and Batch A per ODC-SQ1) | Hold | A | Until then the escrow half and every v0.3 run are UNCERTIFIED. |

The approval record is the owner's file,
`benchmarks/genesis_lite/preregistration/genesis_lite_v0_3.owner_approvals.json`. Each decision needs:
- `status: APPROVED`;
- the `choice`;
- `prereg_sha256` (the preregistration it approves).

D1 also names `pair_bound`, and OD-3 names `certified_head`. The gate never writes this file.

## 4. The owner's next action

1. Write the approval record for D1–D7. Option A in each row is the drafted state.
2. Set `PAIR_BOUND`, `CANDIDATE`, `FORMAL_ROOT_COMMITMENT` (a fresh root) and `ENVIRONMENT_MANIFEST_SHA256` (measured
   on the D7 machine), and set `STATUS = "FROZEN"`. Regenerate, commit, and rerun the gate.
3. Run OD-3 on that HEAD.

The gate then reports PASS or names exactly what is still missing.

## 5. Not done, not authorised

- No freeze, push, PR, merge, recertification, formal baseline, Mind tier or formal measurement.
- No change to v0/v0.1/v0.2 or to any existing certified file.
- No re-scoring of v0.2 records.
