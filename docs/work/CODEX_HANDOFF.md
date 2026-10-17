# FORGE — Codex handoff (2026-10-18)

The owner is moving FORGE development from Claude to OpenAI Codex. This page is the resume point. It records what
exists, where it lives, what is **implemented but unverified**, what is blocked, and what must never be weakened.
Nothing on this page is a test, validation or certification result. Where a check ran, the exact command is named.

Read first, in this order: `CLAUDE.md` (the working contract; its rules apply to any agent),
`docs/project/FORGE_MASTER_PLAN.md`, `docs/architecture/README.md`, `docs/CORE_FREEZE_POLICY.md`,
`docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`, `docs/work/ACTIVE_PLAN.md`, `docs/work/PROGRESS.md`,
`docs/work/DEFERRED_VALIDATION.md`.

## 1. Where the work is (state at handoff)

Before this integration `origin/main` was `de11dffa` (PR #156, ERT V1 Big Rocks). Main is **uncertified** for every
certification-pinned file changed since the last certificate (PRs #146, #154, #156 and this integration; OD-3 pending)
and its own certificate tests fail on it.

**Integrated 2026-10-18 by owner confirmation in chat**, through branch `integration/codex-handoff-2026-10-18` and one
pull request merged with a merge commit (the PR number and the resulting `main` SHA are in the PR and in
`docs/work/PROGRESS.md` on any later commit). Everything below landed **UNVERIFIED / UNCERTIFIED**: no test, tier,
mutation run or certification ran for it. The branches, in merge order:

| Order | Branch (all on `origin`) | Tip | Base | Content | Status |
| --- | --- | --- | --- | --- | --- |
| 0 | `fix/engrt-v1-phase1-interop` | `c68f9fc1` | main lineage (`423fb467` is in main) | I-8: CallbackParticipant checkpoint identity (PR #155, reviewed, merged into this branch after #154 landed) | IMPLEMENTED / UNVERIFIED in this integration (its own gates ran in its session, see PROGRESS 2026-10-17) |
| 1 | `fix/phase1-scientific-numerical-correctness` | `6249c2d2` | `de11dffa` | Phase 1, P1-BR1..BR7 | IMPLEMENTED / UNVERIFIED; DV-31..DV-47 NOT RUN |
| 2 | `feat/phase2-unified-solver-architecture` | `2661b640` | Phase 1 | Phase 2, P2-BR8..BR12 | IMPLEMENTED / UNVERIFIED (BR8, BR12 PARTIAL); DV-48..DV-64 NOT RUN |
| 3 | `feat/phase3-advanced-numerical-multiphysics` | `7389f4b4` | Phase 2 | Phase 3, P3-BR13..BR17 | IMPLEMENTED / UNVERIFIED (BR16, BR17 PARTIAL); DV-65..DV-86 NOT RUN |
| 4 | `feat/phase35-engineering-foundation-completion` | `e89c5b5b` | Phase 3 | Phase 3.5, WS1..WS3 (+ records) | IMPLEMENTED / UNVERIFIED (WS2, WS3 PARTIAL; WS4..WS6 BLOCKED); DV-87..DV-98 NOT RUN |
| 5 | `test/cdar-architectural-fixtures` | `ff66daef` | Phase 3.5 | CDAR fixtures + gap pins (test code only) | NOT RUN (DV-99) |
| 6 | `feat/od6-engineering-program-epic` | `670d94a0` | `de11dffa` | OD-6 governance: research-program epic, CDAR-1..10, audit A-1..A-13 | in force only on merge; its own checks NOT RUN (`docs/work/OD6_MERGE_REVIEW.md`) |

Dependency order: 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 (1-5 are a linear stack; 0 and 6 are independent of it). On the
old `main` every EXPLICIT coupling plan was refused (commit `35d8f557`) until Phase 1, which is why 5 is stacked on 4.

Integration merge commits on `integration/codex-handoff-2026-10-18`: I-8 `b35445ad`, Phase 1 `0ae939f7`, Phase 2
`0356dbdf`, Phase 3 `29d37bf3`, Phase 3.5 `2e800f6e`, CDAR `a2a5123f`, OD-6 `0ae96d3e`, this page `c4f3453e`
(record commits follow). Repository policy (`docs/assurance/BRANCH_PROTECTION.md`): changes reach `main` through a pull
request, merge commit only, no required status checks; certification comes from the local assurance path, not GitHub.
Phase 1-3.5, CDAR and OD-6 had read-only reviews in their own sessions but no pull-request review; the owner confirmed
the merge knowing that.

### Conflict resolutions (by hand; NOT RUN)

- `docs/work/PROGRESS.md` (I-8, Phase 1 and OD-6 merges): append-only; both sides kept, in merge order.
- `docs/work/ACTIVE_PLAN.md` (Phase 2 merge): the I-8 and P2-BR10 rows for the same item merged into one row naming
  both. (OD-6 merge): OD-6's epic line kept as line 3, where `tests/test_capability_completion.py` pins it; the Phase
  overrides follow.
- **Checkpoint authority, I-8 vs Phase 2 P2-BR10 -- a scientific-design decision for owner review.** Both bound
  provider checkpoints to their build, independently:
  - `src/engcore/execution/multiphysics/external.py`: I-8's `CheckpointSeal` kept; Phase 2's mock label,
    `ExternalProviderFailure` and `_classified` lifecycle calls kept, now wrapping the sealed snapshot and restore.
  - `src/engcore/coupling/adapters.py::provider_participant`: I-8's seal is the restore authority (same participant
    object, issued record, recomputed digest); Phase 2's observed-build drift refusal kept; Phase 2's build tag kept in
    the checkpoint slot (`completeness:...;build:<sha256>` once a build has executed) and re-checked after the seal.
    Consequence: a checkpoint of ANOTHER participant object is refused even for the same build, which is stricter
    than P2-BR10's cross-object restore with a build pin. Three Phase 2 tests were rewritten to that rule
    (`tests/execution/orchestration/test_phase2_checkpoint_recovery.py::test_a_corrupted_checkpoint_token_is_refused`
    and `::test_a_checkpoint_of_another_build_is_refused_on_restore`;
    `tests/test_phase2_review_regressions.py::test_a_restored_fresh_participant_refuses_to_continue_on_another_build`).
    If cross-object resume (recovery in a new process) is required, it needs a designed, persistent issue record --
    not a relaxation of the seal.
  - `providers/pybamm/forge_pybamm/coupling.py`: I-8 side kept; its seal scope already holds the full provider build
    (id, version, digest, adapter, configuration), which subsumes P2-BR10's build tag.
  - DV-100 records the tests that must run for this resolution.

### Preserved, not integrated (all pushed to `origin`)

| Ref | Tip | Why not integrated |
| --- | --- | --- |
| `feat/battery-real-data-identifiability` | `7e923e75` | Battery Practical Pass 1 (from a WSL clone; parent `803946af` is in main). Battery capability work; outside the scope of the program epic once OD-6 merges; needs owner routing |
| `preserve/wip-scientific-rating-findings-2026-10-13` | `58091c09` | uncommitted rating-review fixes (base `c4e05ee6`), touches certified files, never reviewed for landing |
| `preserve/wip-review-b1-b2-b4-b5-followups-2026-10-18` | `85f9579c` | uncommitted follow-ups (base `44637065`): MCP probabilistic UQ, multiphysics extension deprecation, ngspice |
| `preserve/wip-a1-5-operating-rating-mind-loop-2026-10-18` | `fcad7587` | uncommitted `engcore.mind` handlers/loop (base `75c9c1d5`) |
| `preserve/wip-main-checkout-electrical-support-gate-2026-10-18` | `b71b3c14` | uncommitted work in the shared checkout on stale local main `a3f757eb` (electrical support-version gate; also deletes the forge-scientific-review agent/skill) |
| `preserve/wip-claude-md-test-commands-2026-10-18` | `2e8d9941` | uncommitted CLAUDE.md test-command edits (base `91b44e22`) |
| `preserve/wip-hostile-remediation-progress-2026-10-18` | `e82a9c94` | uncommitted PROGRESS edit (base `4b0ad013`) |
| `preserve/stash-*` (4 refs) | `7c2058be`, `269b20e6`, `c1716012`, `be61c384` | git stashes (two from the Windows repo, two from the WSL repair clone) |
| `preserve/ci-local-only-assurance-local-2026-10-06` | `bebb6620` | local `ci/local-only-assurance` diverged from its remote (4 local / 20 remote commits) |
| `fix/final-assurance-blockers` | `aab8d032` | superseded by `tools.certification.ownership` (2026-10-16 landing pass) |
| `evidence-v11`, `fix-bisect-table`, `claude/battery-thermal-flagship-sprint-3`, `claude/battery-voltage-s3-recovery`, `codex/multidomain-science-hardening` | — | September branches, stale by the 2026-10-16 landing decision |
| open PRs #107, #39, #24 | — | owner decision OD-11 |

Every `preserve/wip-*` snapshot is UNREVIEWED and its tests were NOT RUN; each commit message names its source
worktree and base. They were made from a temporary index, so the source worktrees are unchanged. Excluded on purpose:
regenerated benchmark JSON in `forge-g0-main` (the SCIENTIFIC tier rewrites committed JSON locally) and pytest temp
directories.

## 2. Architecture (current)

`docs/architecture/README.md` is the map. Layer direction:

```text
Scientific Core -> domains/systems -> credibility -> claims/SRIA -> MCP
```

- Frozen Scientific Core (`scientific`, `data`, `inference`, `uq`, `hybrid_uq`, `adequacy`, `execution`, `studies`):
  Core Freeze V1 + V3 (V2 superseded); changes need a compatibility review (`docs/CORE_FREEZE_POLICY.md`).
- Multiphysics: `scientific.multiphysics` (ports, graph, plan, conservation, frames) and `execution.multiphysics`
  (`MultiphysicsRuntime` = the single coupling authority after P2-BR8; transfer, mapping, IQN-ILS/IMVJ, window error
  control, checkpoints, external participants).
- Non-Core layers: `scenarios`, `materials`, `numerical`, `spatial`, `pde`, `coupling`, `multiscale`, `providers`
  (separate provider distributions under `providers/<name>/`), `system_runtime`, `engineering`, `systems`, `design`.
- Claims runtime: `docs/scientific-core/scientific-intelligence-layer.md`. `engcore.claims` must not import
  `engcore.mcp`. MCP is transport, never scientific authority.
- Certification: `tools/certification/` (local assurance, certificate, skip admission, mutation population). The
  trust root is the local assurance receipt bound to an exact source commit (`docs/assurance/LOCAL_ASSURANCE.md`).

## 3. Roadmap

`docs/project/FORGE_MASTER_PLAN.md` is the strategic contract (Now / Next / Later, governance, resume protocol).

The owner's **32-Big-Rock, 8-phase engineering roadmap** was given in session prompts; the parts on record:

| Phase | Title | Big Rocks | State |
| --- | --- | --- | --- |
| 1 | Scientific & numerical correctness | BR1 coupling convergence, BR2 conservative field mapping, BR3 honest numerical error bounds, BR4 exact time windows, BR5 typed scientific verification, BR6 sparse numerical correctness, BR7 system runtime outcomes & conservation | built, UNVERIFIED |
| 2 | Unified solver & multiphysics architecture | BR8 single coupling runtime, BR9 unified field transfer, BR10 cross-solver checkpoint & recovery, BR11 solver selection & comparison, BR12 real external solver coupling | built, UNVERIFIED; BR8/BR12 partial |
| 3 | Advanced numerical & multiphysics engine | BR13 numerical stability, BR14 IQN-ILS / IQN-IMVJ, BR15 adaptive coupling windows, BR16 adaptive mesh & time refinement, BR17 nonlinear PDE & moving mesh (ALE) | built, UNVERIFIED; BR16/BR17 partial |
| 3.5 | Engineering foundation completion | WS1..WS7 (not Big Rocks) | WS1-WS3 built, WS4-WS6 blocked |
| 4 | Scientific verification, UQ & multiscale | not stated in the record | **not started** (owner approval required) |
| 5-8 | — | BR18..BR32 | **not recorded in the repository or the available session record; obtain from the owner. Do not invent them.** |

Do not confuse these with the ERT V1 Big Rocks BR1..BR22 already in main (PR #156) — the phase rocks are numbered
P1-BR*, P2-BR*, P3-BR* in the code and records.

## 4. Phase 3.5 and OD-6

Phase 3.5 (`docs/work/ACTIVE_PLAN.md`, `docs/work/PHASE_3_5_POLICY_PROPOSALS.md`):
- WS1 mandatory same-problem admission: `compare_providers` is a DIAGNOSTIC; only `corroborate` (records carry both
  canonical problems, re-derived by `corroboration_admission_problems`) reaches ladder level 5. Consequence: the
  committed `cavity_re100` and `structure_flagship` bundles no longer verify until regenerated with real providers
  (DV-93); their tests assert the refusal.
- WS2 electrothermal runtime candidate (`runtime_adapter.run_coupled_via_runtime`); NATIVE stays the default;
  `RUNTIME_PATH_PARITY_VERIFIED = False` until DV-88..DV-90.
- WS3 conjugate-interface admission (`execution/multiphysics/conjugate_interface.py`); real FE <-> CFD BLOCKED.
- WS4..WS6 (transient 1D adaptation / conservative transfer / coarsening / triangle refinement; provider-backed
  nonlinear PDE; ALE) BLOCKED by policy; under OD-6 they become program gates M1, E1, E3.

OD-6 (decided by the owner 2026-10-18, **in force only when `feat/od6-engineering-program-epic` merges**):
- Active epic moves from capability `battery.thevenin_1rc` to research program `engrt.numerical_foundations`
  (`docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md`, ledger schema /2). Gates DV0, M1, M2, E1, E2, E3, all MISSING.
  Build-first: gates order DECISIONS, never work; no gate requires DV0. A research result never promotes a capability.
- Cross-Domain Scientific Architecture Requirements CDAR-1..CDAR-10 bind M1..E3: the shared structure stays
  physics-agnostic; heat is the first reference application, not an assumption.
- Audit `docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md`, open gaps (all OPEN):
  - A-1 no semantic port role; `quantity` never compared (Core review)
  - A-2 losses/conversions energy-only; no lossy mass, charge or species crossing; field balances refused (Core review)
  - A-3 conservative remap assumes a density; flux/intensive contract not applied (Core review; M1, M2, E2)
  - A-4 CHT admission hard-codes K and W/m^2 (Core review, then E2)
  - A-5 scalar-only materials, free property ids
  - A-6 no multirate coupling
  - A-7 `ProblemAspect` closed (Core review)
  - A-8 domain-pack verification protocol untyped; no field norms
  - A-9 static frames only; component-wise vector fan-in (Core review; E3)
  - A-10 domain-named MCP tools; packs without participants
  - A-11 no ODE/DAE, chemical, multibody or structural participant
  - A-12 offset-scale refusal message suggests kelvin
  - A-13 force, pressure and N/m edges (scalar too) fall under the energy-density rule and can answer it only with a
    prose `transport_declaration` (Core review, with A-1/A-2)
- Program rule: the three CDAR fixtures must have RUN once before any of M1..E3 is decided.

## 5. Implemented versus verified

Nothing built in Phases 1..3.5, the CDAR fixtures, OD-6 or the ERT V1 Big Rocks has been executed as a test in the
session that built it. Their status is **IMPLEMENTED / UNVERIFIED**; every touched certification-pinned file is
**UNCERTIFIED** until OD-3. Static checks only (`py_compile`, import checks, `git diff --check`, merge previews) were
run, plus a plain arithmetic check of the CDAR closed forms that imported nothing from the repository.

Known by design after Phase 1: the stub-run authority tests (`test_h2_*`, `test_r2_*`, the big13 extractor) fail;
mutant N60d of the certified V4 population is stale after P1-BR5 (DV-41, needs OD-3).

## 6. Deferred validation (recipes in `docs/work/DEFERRED_VALIDATION.md`; all NOT RUN)

| Rows | Scope |
| --- | --- |
| DV-1..DV-30 | ERT V1 Big Rocks (in main) |
| DV-31..DV-47 | Phase 1 |
| DV-48..DV-64 | Phase 2 |
| DV-65..DV-86 | Phase 3 |
| DV-87..DV-98 | Phase 3.5 (DV-93 real-provider bundle regeneration; DV-94..DV-97 blocked/not written; DV-98 structural guards and FAST/SCIENTIFIC diffed against a pristine baseline) |
| DV-99 | CDAR fixtures: `pytest tests/architecture/test_cross_domain_fixtures.py -q` |
| DV-100 | Integration conflict resolution (I-8 vs P2-BR10 checkpoint authority): see `DEFERRED_VALIDATION.md` |
| OD-6 | `docs/work/OD6_MERGE_REVIEW.md`: `pytest tests/test_capability_completion.py benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py -q`; `python -m tools.capability_maturity` (the matrix was hand-edited); `python tools/forge_check.py --changed` |

Certification impact: `tests/test_capability_completion.py` and many Phase 1..3.5 files are recertification triggers
(`tools/certification/recertification_scope.py`); landing any of them needs OD-3 recertification of the resulting
main HEAD (hardened local assurance, ~3.5 h; see `docs/assurance/LOCAL_ASSURANCE.md`). Do not run the full assurance,
mutation campaign, hardened certification or expensive tiers without the owner's authorization.

Environment traps that make results lie: GitHub Actions are blocked by billing (a job that fails in ~2 s is billing);
branch rules/rulesets return HTTP 403 on this private repo's plan, so nothing is enforced server-side; a live
`pytest.xfail` is refused by `tools/certification/skip_admission.py` as an UNEXPECTED_SKIP; an env-gated `skipif`
refuses hardened runs; Windows FAST shows ~150 POSIX-only failures (diff against a pristine baseline); writing text on
Windows injects CRLF and breaks SHA-256 byte pins (write bytes).

## 7. Owner decisions open

- Confirm or revise the I-8 vs P2-BR10 checkpoint-authority resolution (section 1).
- OD-3: recertify the resulting `main` HEAD.
- OD-6: merge `feat/od6-engineering-program-epic`; accept CDAR as binding acceptance criteria of M1..E3.
- OD-P2-1, OD-P2-2, OD-P2-4, OD-P2-5 (OD-P2-3 closed by WS1); OD-P3-1..OD-P3-7; OD-P35-1 (EXC-1 amendments;
  EXC-1 expires 2026-10-31), OD-P35-3 (DV-93 bundles), OD-P35-4 (electrothermal delegation after parity),
  OD-P35-5 (Core consensus / ladder V5 same-problem admission); OD-11 (open PRs #107, #39, #24).
- Core compatibility review of A-1, A-2, A-3, A-4, A-7, A-9, A-13.
- Routing of the preserved, unintegrated work listed in section 1 (battery Pass 1, rating fixes, review follow-ups,
  `engcore.mind` loop, electrical support-version gate).
- Authorize the deferred validation campaign (DV-31..DV-100) and Phase 4.
- Supply the roadmap for Phases 4..8 / BR18..BR32.

## 8. Next priorities for Codex

1. When the owner authorizes validation: run DV-100 (the integration's checkpoint-authority tests) and DV-99 first,
   then the DV-31..DV-98 recipes, cheapest first, recording exact commands and failures in `docs/work/PROGRESS.md`;
   diff FAST/SCIENTIFIC against a pristine baseline. Expect failures: nothing in this stack has executed as a test.
2. Route the preserved, unintegrated work of section 1 (each piece needs rebasing onto the new `main` and a review).
3. Then OD-3 recertification of main HEAD.
4. Program work under OD-6 (after merge): M1 (declared-kind 1D adaptation and state transfer), then M2 / E1 / E2 / E3,
   each built physics-agnostic per CDAR; take the Core gaps through review before deciding M2 / E2.
5. Regenerate the two flagship bundles with real providers (DV-93) when a provider environment is available.

## 9. Invariants (from `CLAUDE.md`; any agent must keep them)

- UNKNOWN never improves an answer. Missing uncertainty or model discrepancy never becomes zero. Missing boundary
  conditions are never silently defaulted.
- Model applicability precedes evidence-bearing execution. Verification does not become validation. Solver agreement
  does not prove physical truth. Caller assertions and planner output are not scientific evidence.
- Contradiction requires admissible evidence. Evidence stays bound to the exact context it was produced for. Removing
  evidence never increases assurance. Risk policy sets the evidence bar; it is never evidence.
- Diagnostic hypotheses are not evidence; sensitivity is not causality; a proposed corrective action guarantees nothing.
- A language model may propose structured inputs; it may not select an applicable model, invent measurements, grant
  validation, quantify unknown uncertainty or issue a scientific verdict.
- Never write "tests passed", "verified", "validated" or "green" unless the command ran in that session; write
  **NOT RUN** otherwise. Do not edit frozen or certified artifacts to silence a test. Do not weaken or bypass the
  test / recertification gates. No force-push, no destructive reset, no branch deletion: the certificate children
  `33a8ef74` (`fix/p0-trust-boundaries`), `5bdb086a` (`fix/p0-v4-assurance-descendants`) and `c57df279`
  (`fix/p0-1-scientific-correctness-hardening`) are reachable only from their branches; tag them (`archive/cert/<sha>`)
  before any cleanup.
