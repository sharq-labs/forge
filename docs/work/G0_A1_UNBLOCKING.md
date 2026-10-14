# G0 / A1 unblocking sprint (2026-10-14)

Local integration branch `integration/g0-a1-unblock`, worktree `D:/forge-g0a1`. It is `origin/main` `e193e573` plus
BR-15 (`fix/br15-authority-closure`) plus BR-16 (`feat/br16-genesis-lite-benchmark`), merged locally.

**Nothing is pushed, opened as a PR or merged to `main`.** Hardened recertification and FULL local assurance were
**not** run. No owner decision is assumed. BR-17 and BR-18 stay closed (their prerequisites have not changed).

## 1. Actual state

| Item | Implemented | Committed | Merged to `main` | Tested | Scientifically proven |
|---|---|---|---|---|---|
| `main` `e193e573` certificate | — | yes | yes | `--verify` **FAILS**: PR #142 changed `tests/mutation_guards.py` and `tests/test_formal_xdist.py` after the certificate child `b1eea81b` | not certified |
| BR-15 authority closure (derived closure, +71 pinned files, F-4/F-5) | yes | `fix/br15-authority-closure` | **no** | FAST 3.11/3.12 at `a22869d4`: 10415 passed, 1 expected failure | no; certification pending |
| F-9 restore check (this sprint) | yes | `01f9bee6` | no | reproducer 2 failed before the fix, 3 passed after; SRIA suites 179 passed | no |
| F-7 CI V4 checkout cleanup (this sprint) | yes | `c96dd2f5` | no | local simulation; test passes on Linux (real bash) and on Windows | **not verified on GitHub** (needs a push) |
| BR-16 Genesis-lite v0 + pilot | yes | `feat/br16-genesis-lite-benchmark` | no | 42 tests; FAST 3.12 10416 passed, 1 expected failure | v0 pilot measured cost only |
| Proposer isolation + Genesis-lite v0.1 (this sprint) | yes | `81adb4c9` | no | `tests/genesis_lite` 58 passed (Windows); Linux: see §6 | not a proven security boundary |
| Integration candidate | merged locally | `6f891509` | no | §6 | — |

CI on `main` `e193e573`: FAST 3.11/3.12 and SCIENTIFIC each fail exactly `test_the_certificate_describes_this_tree`;
Branch Policy fails with HTTP 403. On PRs #140 and #142, all eight V4 shards failed on the runner checkout (fixed in
F-7, unverified on GitHub); the formal shards passed.

## 2. G0

| Check | Result |
|---|---|
| Certification-sensitive changes in BR-15 / this sprint | yes, in four areas: `assurance_admission` (`sria/campaign/runner.py`); `certification_control` (the workflow, `core_certificate.py`); `harness` (`tests/mutation_guards.py`); and the scope (`system_runtime_dependencies` added; `assurance_admission` and `verdict_authority` patterns changed) |
| Pinning checks on the integration HEAD | `certified_dependency_problems == []`, `authority_closure_problems == []`, `harness_pinning_problems == []`, `registry_problems == []` (production registry pin unchanged) |
| `--verify` on the integration HEAD | fails only for the expected drift listed above (certified commit `05522b59`) |
| Lineage | the certificate child `b1eea81b` is an ancestor of `main`; the next child must be a certificate-only commit on the exact source below |
| Remaining code-level authority gaps with reproducers | F-9 FIXED; F-7 FIXED (CI-unverified). No other reproduced gap is open. |

**Recertification candidate:** `integration/g0-a1-unblock` at the HEAD recorded in §6. That HEAD includes this document
and PROGRESS; recertify the final docs commit, because every later change to a certified file invalidates the
certificate again. The owner runs `local_assurance` on it (OD-3). It was not launched.

## 3. Blindfold benchmark defect P-1 (v0 → v0.1)

The cause was measured from the v0 pilot's own run log (10 discoverable worlds, anonymous presentation).

| Candidate cause | Finding |
|---|---|
| Representation leakage | **Ruled out.** `always_law` fails all 3 out-of-family worlds; the literal audit was clean; the separate evaluator agreed on 5,760 of 5,760 universes. |
| Scoring defect | **Ruled out.** Same evidence; the golden scoring cases pass. |
| Excessively simple task structure | **Yes.** 7 of 10 discoverable worlds are pure power laws inside the monomial family, and `always_law` passes exactly those 7. |
| Baseline competence | **Yes.** The gated arms refuse 9 of 10, including in-family box-region worlds. The fixed precision bar (0.02 log) and the minimum-count rule are far stricter than the scoring tolerance; at budget 12 the count rule refuses before any fit. |
| Invalid discovery metric | **Yes, the decisive one.** v0's per-cell lift rule compares the discoverable cell alone, so a proposer scoring −1 on every control can still "win" there. |

**v0.1 contract** (`benchmarks/genesis_lite/analysis.py`, a new identity `genesis_lite.blindfold_l5.v0_1`,
preregistration `1eabcfa0…`):

* Primary endpoint: the **joint campaign credit**, i.e. the sum over all six kinds per campaign, averaged over seeds.
* Strongest baseline: chosen over **every non-adversarial arm**, floors included.
* Lift: a paired cluster-bootstrap lower bound above 0 after Holm correction over a **fixed** family, **and**
  non-inferiority on every control kind (margin 0.10).
* One stronger arm added (`fit_all_gated`). Arms are never removed or weakened.

The criteria are not tuned for a Mind: they make lift *harder*, and the tests prove both directions.
`test_p1_a_reckless_proposer_gets_no_lift…` and `…bought_with_one_control_is_refused…` refuse the reckless and trading
patterns, and `test_positive_control_a_better_and_no_worse…` accepts a genuine improvement. On the v0 pilot data under
v0.1, `always_law` ranks last (−4.35 campaign credit) and the strongest baseline is `space_filling` (+3.11).

**Recorded limitation.** The non-discoverer `single_setting` scores +2.45. Most credit in this benchmark comes from
control classification, not discovery, so discovery and control credit are reported apart.

v0 is preserved: its preregistration `f99fcfbd…` and pilot results are byte-identical (a test checks this), and v0.1
`amends` it with the reasons.

## 4. Escrow leakage (OD-20)

| Path | Reproduced (in-process) | After the fix (`isolation="proposer_process"`) |
|---|---|---|
| Heap scan for `HiddenWorld` objects | **steals the law** (`law_pass`), run still VALID | finds nothing (`no_law`) |
| Stack walk to the operator's `master_seed`, re-deriving every world | **steals the law**, run still VALID | finds nothing |
| Secrets in the environment or working directory | none found | none: environment scrubbed, empty temporary working directory (tested with a planted `FORGE_MASTER_SEED_FOR_TEST`) |
| Reading the operator's memory (`/proc/<ppid>/mem`) | — | refused on Linux, YAMA `ptrace_scope=1` (tested); **not established on Windows** |
| Files readable by the same OS account (e.g. the pilot root) | possible | **still possible**: same-account separation does not prevent it |

The fix is one fresh `python -I` proposer interpreter per campaign (`benchmarks/genesis_lite/proposer_host.py`). It
receives only presented cards and observation answers, and the operator refuses a host that imported another
`engcore`. The positive control (identical honest outcomes in both modes) passes. The escrow keeps stating
**SECURITY_BOUNDARY_NOT_PROVEN**.

**OD-20 deployment requirements before any formal or held-out run:**

1. The operator, the escrow and every secret (master roots, answer keys) run under a different OS account or
   container from the proposer.
2. The proposer gets a read-only filesystem with no access to operator paths, no network, and no ptrace
   (Linux YAMA ≥ 1 or a seccomp profile).
3. Secrets are never on a filesystem the proposer can mount.
4. The existing isolation demo (`engcore.blindfold.isolation`) is re-run on that deployment and its record is bound
   to the escrow key id.
5. Only then may a run claim more than NOT_PROVEN.

## 5. A1 preparation

| Item | State |
|---|---|
| Baseline matrix | 12 run arms, including `fit_all_gated`. NOT_AVAILABLE: PySR, BoTorch, PySINDy. NOT_APPLICABLE_IN_V0: full-grammar enumeration, discriminating design, port-grammar mechanisms, LLM ablation. Full matrix in `docs/discovery/GENESIS_LITE_V0.md` §3. |
| Scoring | Frozen `DEFAULT_CREDIT` (`cfb8d68c…`); a separate evaluator; v0.1 endpoints in `analysis.py` |
| Preregistration | v0.1 `1eabcfa0…`, `FREEZE_READY`. The formal freeze follows the OD-3, OD-8, OD-18, OD-19 and OD-20 decisions. |
| Formal requirements | 30 campaigns per presentation (30 worlds per kind × presentation cell) × 4 presentations; 20 seeds for stochastic arms; one root per (campaign, presentation) shared by every arm and seed; `proposer_process` isolation; campaign as the analysis unit |
| Pilot cost | v0 (in-process, MEASURED): 960 runs in 85 s. v0.1 (isolated): see §6. |
| External evaluator requirements (OD-8) | A person or group outside the FORGE development team, with no write access to the repository. They receive the frozen preregistration, the evaluator package and sealed proposals plus answer keys only after sealing. They run `benchmarks/genesis_lite/evaluator` (or their own implementation of the same rule text) and publish agreement or disagreement per universe. A deadline is set in ACTIVE_PLAN. |
| Compute budget request (OD-18) | §6 ESTIMATE for the baseline tier on one machine. The Mind and LLM arms are UNMEASURED and need their own pilot once a Mind exists. |

## 6. Gates run on the integration HEAD

Filled in from actual runs; see PROGRESS.

## 7. OD-6: the active epic stays `battery.thevenin_1rc`

The battery 1RC ledger entry is at stage FOUNDATION with 11 gates MISSING: execution, provenance/replay, real data,
calibration, independent validation, measurement UQ, benchmark metrics, parameter UQ, model discrepancy, claims
integration and domain-pack integration. Recorded outcomes: Sprint 3 Gate A not passed; Kirkaldy fade NOT MET; Battery
Practical Pass 1 WEAKLY_IDENTIFIABLE (local only).

| | Option A: reviewed, narrowly scoped Minimal Mind exception | Option B: formal active-epic change |
|---|---|---|
| Mechanism | A PR section "Active-epic exception" plus an ACTIVE_PLAN entry with all eight fields; the ledger is unchanged | A separate reviewed PR changes `active_epic` in `scientific_capability_completion.json`, the pin in `tests/test_capability_completion.py::test_active_epic_is_battery_1rc_and_still_incomplete` and the PR-template line, and adds a ledger entry for the new epic |
| Scope (draft) | Genesis Step 2 only: the four missing loop pieces (outcome model for the Blindfold L5 task family, belief over `sria.decision.Hypothesis` records, VoI selection through the `sria.decision` UtilityEngine, invalidation over `credibility.evidence_graph`) in one new non-certified package, measured only by Genesis-lite v0.1 | everything the new epic's ledger entry names |
| Start / exit / expiry | Start: A1 PASS. Exit: the Step 2 gate (PASS, or FAILED_TO_SHOW_LIFT recorded). Expiry: the owner sets it under OD-7. | permanent until the next epic change |
| Prohibited (A) | no new Trust, evidence, hypothesis or benchmark authority; no domain capability; no LLM authority over priors, thresholds or verdicts; no certified-area change without recertification; no battery ledger edit | — |
| Effect on battery | stays the active epic; defects, stabilisation and active-epic prerequisite work continue; horizontal expansion stays paused | battery is no longer active; its 11 MISSING gates are deferred, and new battery capability work then needs its own exception under the new epic |
| Anti-loophole | a second concurrent exception, or a renewal, triggers an owner review of the epic | — |
| Owner fields to fill | approver and date; expiry | the PR, its approval and the new epic's ledger entry |

Both options are presented; neither is chosen. **Option A is the smaller, reversible change.** Option B is the honest
choice if Genesis becomes the program's priority, because it stops Mind work from living on an exception.
