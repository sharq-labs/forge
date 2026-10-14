# G0 / A1 unblocking sprint (2026-10-14)

Local integration branch `integration/g0-a1-unblock`, worktree `D:/forge-g0a1`. It is `origin/main` `e193e573` plus
BR-15 (`fix/br15-authority-closure`) plus BR-16 (`feat/br16-genesis-lite-benchmark`), merged locally.

**Nothing is pushed, opened as a PR or merged to `main`.** Hardened recertification and FULL local assurance were
**not** run. No owner decision is assumed. BR-17 and BR-18 stay closed (their prerequisites have not changed).

Owner-decision numbering: the Genesis decisions that BR-16 drafted as OD-15..17 are renumbered **OD-18** (budget),
**OD-19** (v0.1 identity) and **OD-20** (escrow deployment), because open PR #130 already uses OD-15..17.

## 1. Actual state

| Item | Implemented | Committed | On `main` | Tested (this sprint unless stated) | Proven |
|---|---|---|---|---|---|
| `main` `e193e573` | — | yes | yes | `--verify` **FAILS**: PR #142 edited `tests/mutation_guards.py` and `tests/test_formal_xdist.py` after certificate child `b1eea81b`. CI FAST and SCIENTIFIC fail only on that; Branch Policy fails with 403. | not certified |
| BR-15 authority closure (derived dependency closure, +71 pinned files) | yes | `fix/br15-authority-closure` | no | part of the integration gates (§6) | pending recertification |
| F-9 restored stop-review state | yes | `01f9bee6`, `d118583d`, `9df87275` | no | reproducers fail before each step; `test_audit_sria_stop_review_restore.py` 8 passed; SRIA suites 220 passed | pending recertification |
| F-7 CI V4 shards vs `actions/checkout` | yes | `c96dd2f5` | no | local simulation plus test (Linux real bash, Windows static) | **not run on GitHub** |
| Genesis-lite v0 (BR-16) | yes | yes | no | v0 pilot (960 runs) | cost only |
| Proposer isolation, v0.1 contract, review fixes | yes | `81adb4c9` … `0f69a453` | no | Genesis-lite tests (§6); v0.1 pilot (1,560 runs) | not a proven boundary |
| Integration candidate | merged locally | final HEAD in §6 | no | §6 | — |

## 2. G0

| Check | Result |
|---|---|
| Certification-sensitive changes | yes, in five places: `assurance_admission` (`sria/campaign/runner.py`, and under the new scope `events.py` and `persistence.py`); `certification_control` (the workflow, `core_certificate.py`, `tests/test_formal_xdist.py`); `harness` (`tests/mutation_guards.py`); the scope itself (`system_runtime_dependencies` added; `assurance_admission` and `verdict_authority` patterns changed) |
| Pinning checks on the integration tree | `certified_dependency_problems == []`, `authority_closure_problems == []`, `harness_pinning_problems == []`, `registry_problems == []` (the production registry pin is unchanged) |
| `--verify` | fails only for the expected drift above (certified commit `05522b59`) |
| Lineage | `b1eea81b` is an ancestor of `main`; the next certificate child must be a certificate-only commit on the exact final HEAD in §6 |
| Code-level authority gaps with reproducers | F-9 FIXED, including the review hardening; F-7 FIXED, unverified on GitHub. No other reproduced gap is open. |

**Recertification candidate:** `integration/g0-a1-unblock` at the final HEAD in §6. Only the owner runs `local_assurance`
on it (OD-3); it was not launched.

## 3. Blindfold benchmark defect P-1 (v0 → v0.1)

The cause was measured from the v0 pilot run log (10 discoverable worlds, anonymous presentation):

| Candidate cause | Finding |
|---|---|
| Representation leakage | **Ruled out.** `always_law` failed all 3 out-of-family worlds; the literal audit was clean; the separate evaluator agreed on 5,760/5,760 universes. |
| Scoring defect | **Ruled out.** Same evidence, plus golden scoring cases. |
| Excessively simple task structure | **Yes.** `always_law` passed exactly the 7 pure-power-law worlds. |
| Baseline competence | **Yes.** The gated arms refused 9 of 10. Their fixed 0.02 precision bar and minimum-count rule are far stricter than the scoring tolerance. |
| Invalid discovery metric | **Yes, the decisive one.** v0's per-cell lift rule credits a proposer that fails every control. |

**v0.1 contract** (`benchmarks/genesis_lite/analysis.py`, identity `genesis_lite.blindfold_l5.v0_1`, preregistration
`94efff08…`, v0 preserved byte-for-byte):

* **Unit.** A world set is one campaign under one (presentation, seed) root. It is never reused, and every arm runs it
  once.
* **Primary endpoint.** The joint world-set credit over all six kinds.
* **Strongest baseline.** Chosen over every non-adversarial arm, with roles taken from the frozen registry.
* **Lift** requires all of:
  * complete VALID, isolated runs for every compared arm on the **preregistered grid**, with content-paired universes;
  * a paired cluster-bootstrap lower bound above 0, after Holm correction over a fixed family;
  * per-presentation non-inferiority;
  * per-control-kind non-inferiority against the best arm on that kind.
* **Arms.** One stronger arm was added (`fit_all_gated`); none was removed or weakened.

The criteria make lift **harder**; the tests prove both directions. Reckless, trading, invalidating, incomplete,
presentation-selective and caller-weakened comparisons are refused, and a genuine improvement is accepted.

| Pilot (indicative only) | v0 per cell | v0.1 joint endpoint, v0.1 pilot |
|---|---|---|
| `always_law` | wins the discoverable cell (0.70) | **last** (−4.64) |
| strongest baseline | — | `space_filling` (+3.18), then `careful` (+3.12) |
| best arm per control kind | — | refusal floors on insufficient-evidence, indistinguishable and no-solution; `single_setting` on confounded; `careful` on spurious |

**Recorded limitations.**

* Most credit comes from control classification: the non-discoverer `single_setting` scores +2.44.
* Only 0.44 of the pilot's discoverable worlds are inside the searched family.
* Where a refusal floor is the best arm for a control kind, the per-kind non-inferiority bar effectively requires a
  future Mind to refuse as reliably as that floor.

## 4. Escrow leakage (OD-20)

| Path | In-process | `isolation="proposer_process"` |
|---|---|---|
| Heap scan for `HiddenWorld` objects | **steals the law**; the run is still VALID | finds nothing |
| Stack walk to `master_seed`, re-deriving every world | **steals the law**; the run is still VALID | finds nothing |
| Secrets in the environment or working directory | none | none: scrubbed environment and an empty temporary working directory (tested with a planted secret) |
| Reading the operator's memory | — | `PermissionError` on Linux, YAMA `ptrace_scope=1` (tested); **not established on Windows** |
| Crafted setting name (`rolled back`) that invalidates a losing run | **run turned INVALID** | refused at the client in **both** modes (reproducer fails before the fix); `lift_decision` also refuses incomplete coverage |
| Files readable by the same OS account | possible | **still possible** |

Measured overhead of the isolated proposer: about 0.15 s per world set. The escrow keeps stating
**SECURITY_BOUNDARY_NOT_PROVEN**.

Residual in certified `engcore.blindfold`: the client classifies refusals by their text, and the escrow echoes caller
input into refusal texts. Genesis-lite blocks this channel at its client; the structural fix (refusal codes) needs a
certified change.

**OD-20 deployment requirements before any formal or held-out run** (also a preregistered formal start condition):

1. The operator, the escrow and every secret run under a different OS account or container from the proposer.
2. The proposer has a read-only filesystem with no access to operator paths, no network and no ptrace.
3. Secrets are never on a filesystem the proposer can mount.
4. The isolation demo (`engcore.blindfold.isolation`) is re-run on that deployment and bound to the escrow key id.

## 5. A1 preparation

| Item | State |
|---|---|
| Baseline matrix | 13 run arms, including `fit_all_gated` and `extrapolation_pair`. NOT_AVAILABLE: PySR, BoTorch, PySINDy. NOT_APPLICABLE_IN_V0: full-grammar enumeration, discriminating design, port-grammar mechanisms, LLM ablation. |
| Scoring | Frozen `DEFAULT_CREDIT` (`cfb8d68c…`); separate evaluator; v0.1 endpoints in `analysis.py` |
| Preregistration | v0.1 `94efff08…`, `FREEZE_READY`. The formal freeze follows the OD-3, OD-8, OD-18, OD-19 and OD-20 decisions. |
| Formal requirements | 4 presentations × 30 campaigns × 20 seeds = 600 world sets per presentation, which means **600 worlds per kind × presentation cell** (floor is 30); every arm on every world set; `proposer_process` plus the OD-20 deployment; the world set as the unit |
| Pilot cost, MEASURED | v0 (in-process): 960 runs in 85 s. v0.1 (isolated): **1,560 runs in 374.6 s**, 0 invalid, 0 inadmissible, 0.12–0.25 s per world set (WSL 3.12, 20 CPUs) |
| Formal budget, ESTIMATE | **31,200 baseline world-set runs ≈ 6,451 s (≈ 1.8 h)** on one machine, 95% interval 6,440–6,462 s from pilot variance. Excludes the Mind, LLM-ablation and model-swap arms (UNMEASURED) and the OD-20 deployment overhead (UNMEASURED). |
| External evaluator (OD-8) requirements | A person or group outside the FORGE team, without write access. They receive the frozen preregistration and the evaluator package, and sealed proposals plus answer keys only after sealing. They run `benchmarks/genesis_lite/evaluator` (or their own implementation of the rule text) and publish agreement per universe. A deadline is recorded in ACTIVE_PLAN. |

## 6. Gates run

| Gate | HEAD / environment | Result |
|---|---|---|
| FAST `-m "not expensive" -n 4` | integration `5ead8312`, WSL 3.12 | 10493 passed, 156 skipped, 1 failed (`test_the_certificate_describes_this_tree`, expected until recertification) |
| FAST | integration `5ead8312`, WSL 3.11 | 10493 passed, 156 skipped, 1 failed (same) |
| Focused adversarial set (`tests/genesis_lite`, F-9, F-7, closure) | `5ead8312`, WSL 3.12 | 108 passed |
| Regression `tools/forge_check.py --regression` | `5ead8312`, WSL 3.12 | 256 passed, exit 0 |
| Genesis-lite tests | BR-16 `90a970cf`, WSL 3.12 | 67 passed |
| v0.1 pilot | BR-16 `ed65ef3c`, WSL 3.12 | 1,560 runs, 0 invalid |
| Final-HEAD re-run | see PROGRESS | — |
| Hardened recertification, FULL local assurance | — | **NOT RUN** (owner) |

## 7. OD-6: the active epic stays `battery.thevenin_1rc`

The battery 1RC ledger entry is at FOUNDATION with 11 gates MISSING: execution, provenance/replay, real data,
calibration, independent validation, measurement UQ, benchmark metrics, parameter UQ, model discrepancy, claims
integration and domain-pack integration. Recorded outcomes: Sprint 3 Gate A not passed; Kirkaldy fade NOT MET; Battery
Practical Pass 1 WEAKLY_IDENTIFIABLE (local only).

| | Option A: narrowly scoped Minimal Mind exception | Option B: formal active-epic change |
|---|---|---|
| Mechanism | A PR section "Active-epic exception" plus an ACTIVE_PLAN entry with all eight fields; the ledger is unchanged | A separate reviewed PR changes `active_epic` in `scientific_capability_completion.json`, the pin `tests/test_capability_completion.py::test_active_epic_is_battery_1rc_and_still_incomplete` and the PR-template line, and adds a ledger entry for the new epic |
| Scope (draft) | Genesis Step 2 only: the four missing loop pieces (outcome model for the Blindfold L5 task family, belief over `sria.decision.Hypothesis`, VoI through the `sria.decision` UtilityEngine, invalidation over `credibility.evidence_graph`) in one new non-certified package, measured only by Genesis-lite v0.1 | what the new epic's ledger entry names |
| Start / exit / expiry | Start: A1 PASS. Exit: the Step 2 gate (PASS, or FAILED_TO_SHOW_LIFT recorded). Expiry: the owner sets it (OD-7). | until the next epic change |
| Prohibited (A) | no new Trust, evidence, hypothesis or benchmark authority; no domain capability; no LLM authority over priors, thresholds or verdicts; no certified-area change without recertification; no battery ledger edit | — |
| Effect on battery | stays active; defects, stabilisation and active-epic prerequisite work continue | no longer active; its 11 MISSING gates are deferred, and new battery capability work needs its own exception |
| Anti-loophole | a second concurrent exception, or a renewal, triggers an owner review of the epic | — |

Both options are presented; neither is chosen. Option A is the smaller, reversible change. Option B is the honest
choice if Genesis becomes the program's priority.

## 8. Closure table

| Blocker | Root Cause | Fix Implemented | Evidence | Owner Action | Remaining Risk | Status |
|---|---|---|---|---|---|---|
| `main` not certified | PR #142 changed certified harness files after recertification | none possible without recertification | `--verify` fails on `e193e573`; CI shows the same single failure | OD-3: recertify the integration final HEAD | none beyond that | OWNER_DECISION_REQUIRED |
| Certified modules import uncertified authority code (BR-15) | the closure was seeded only at 6 roots | derived dependency closure; +71 pinned files | 23 tests failed before / passed after; pinning checks `[]` | OD-3 | duck-typed runtime objects are invisible to a static closure | FIXED (pending recertification) |
| F-9 restored stop-review state | restore did not check the stop review against the log | `stop_review_disagreements` in restore and in the store; StopReview invariants; VALID verdict | 3 fail-before steps; 8 passed; 220 SRIA tests passed | OD-3 | a log forged consistently end to end with invented ids (unkeyed chain) | FIXED |
| F-7 CI V4 shards fail on runner checkout | `actions/checkout` writes `config.worktree`; admission refuses it | workflow step removing exactly the three sparse defaults | local simulation (refused → admitted; hostile still refused); 3 tests | push plus a CI run (owner) | not yet observed on GitHub | PARTIALLY_FIXED |
| P-1 benchmark defect | per-cell metric, over-conservative gates, simple worlds | v0.1 joint-credit contract; completeness-gated lift; `fit_all_gated` | reproduced on v0 data; 15 analysis tests; v0.1 pilot | OD-19: approve v0.1 | benchmark credit is dominated by controls; out-of-family worlds have NO_STRONG_BASELINE | FIXED (pending approval) |
| Escrow leak (in-process) | the proposer shared the operator's process | `proposer_process` isolation; crafted-name guard; completeness rule | attacks succeed in-process and fail isolated; reproducers fail before | OD-20: separate-account deployment | same-account file reads; Windows memory reads; blindfold refusal-text classification | PARTIALLY_FIXED |
| A1 formal tier not run | needs the G0 exit and the owner decisions | freeze-ready v0.1; MEASURED pilot; ESTIMATE | §5 | OD-8, OD-18, OD-19, OD-20, then run | Mind/LLM cost UNMEASURED | OWNER_DECISION_REQUIRED |
| Active epic blocks A2 | policy | options A/B prepared | §7 | OD-6 | — | OWNER_DECISION_REQUIRED |
| Host governance | private free plan (rulesets 403); squash/rebase merges enabled | none (settings) | Branch Policy 403 | OD-1: plan or visibility; disable squash/rebase | merges are not gated | OWNER_DECISION_REQUIRED |
