# Active Plan

Purpose: define the one bounded, resumable execution slice that Forge should
pursue now. Strategic direction remains in
`docs/project/FORGE_MASTER_PLAN.md`; completed work, failed approaches and test
transcripts remain in `docs/work/PROGRESS.md`.

## Current objective

### User-requested audit — 2026-10-13

The user requested a current-tree audit of every implemented scientific model.
This is a read-only scientific review and diagnostic execution slice alongside
BIG 14, not authorization to repair models or change acceptance criteria.

- [x] Pin source HEAD `a3f757eb5fdbc804ef11e3c4088a757c31981870` and inventory
      native models, realizations, provider cases and flagship compositions.
- [ ] Complete independent per-model scientific reviews and reconcile findings.
- [ ] Execute regression, local full tiers sequentially, available provider
      tests, and minimal counterexamples; record unavailable environments.
- [ ] Publish a per-model coverage ledger, findings and exact execution results
      in `docs/work/MODEL_AUDIT_2026-10-13.md` and preserve diagnostic evidence.

Existing uncommitted planning/review edits are preserved. Production code,
frozen artifacts, acceptance thresholds and certification are not changed.

The architecture-first BUILD phase through **BIG 13** is complete and merged.
Forge now enters **BIG 14 — Scientific Closure & Recertification**.

BIG 14 is a stabilization, diagnosis and evidence campaign. It is not another
breadth-expansion phase. New providers, domains and flagships remain out of
scope until the existing architecture has passed its declared gates and the
current flagship evidence gaps have an honest disposition.

Starting evidence state:

- four flagships execute through the generic BIG 12 `SystemExecutor`;
- all four end `insufficient_evidence`; none is validated;
- six pre-registered criteria were not met as written;
- full FAST, SCIENTIFIC, mutation and hardened recertification campaigns have
  not run on the merged BIG 13 tree;
- the final BIG 12 and BIG 13 fix batches have not received their missing
  independent re-reviews.

Negative results must remain visible. BIG 14 must not improve an outcome by
loosening a tolerance, replacing a pre-registered criterion with a post-hoc
one, treating solver agreement as validation, or turning an unknown
uncertainty/model discrepancy into zero.

## Current repository state

- Branch: `main`
- Planning baseline: `a3f757eb` (merge of PR #109, BIG 13)
- Working state: BIG 13 is merged; this plan update is not yet committed.
- First execution action: create a bounded BIG 14 branch from the current
  `origin/main`, then replace the planning baseline above with the branch and
  exact base SHA.

## Roadmap view

### Now — BIG 14

Close known authority/review gaps, establish a reproducible full-tree
baseline, select a bounded flagship evidence target, diagnose its residuals,
quantify only supportable uncertainty channels, and run the full assurance
campaign.

### Next — BIG 15

Complete graph-level UQ/V&V and evidence composition using the findings and
contracts proven in BIG 14. Do not start while BIG 14 exit criteria remain
unmet.

### Later

Additional flagship breadth, HPC/scale and commercial-data expansion remain
directional under the Master Plan. They do not displace scientific closure.

## Mapping to the Master Plan

`BIG` numbers are execution milestones; `P` numbers are strategic Master Plan
phases. They are related but not numerically identical.

| Execution milestone | Master Plan relationship | Status |
|---|---|---|
| BIG 2–9 | P1–P8 foundations | Built; full merged-tree campaign pending |
| BIG 10 | P14 multi-timescale runtime | Built; full campaign pending |
| BIG 11 | Provider work spanning P7–P13 | Built; residual reviews recorded |
| BIG 12 | Cross-phase end-to-end runtime | Built; final fix batch needs re-review |
| BIG 13 | P16 integration demonstrations | Built; all results remain insufficient evidence |
| BIG 14 | P0 closure plus bounded P15/P16 evidence work | Current |
| BIG 15 | P15 graph-level UQ/V&V completion | Next |

## BIG 14 execution order

The sections below are sequential unless a task explicitly says it may run in
parallel. The first unchecked item in this section is the next executable task.
Historical status later in this file is not an execution queue.

### 14.0 — Establish the branch and baseline

Owner: repository maintainer / implementation agent.

- [ ] Create a bounded BIG 14 branch from current `origin/main`; record branch,
      base SHA and worktree here and in PROGRESS.
- [ ] Inventory supported Python and provider environments, including exact
      versions, optional dependencies, external executables and WSL/conda
      requirements. Unsupported environments must be explicitly refused.
- [ ] Run and record, before changing scientific behavior:
      `python tools/forge_check.py --changed`,
      `python tools/forge_check.py --regression`, and `git diff --check`.
- [ ] Classify every baseline failure as product defect, stale test/certificate,
      unsupported environment, missing dependency or external-policy blocker;
      record the evidence for the classification.

#### Baseline stop gate

Do not begin flagship evidence work (14.2 or 14.3) while a baseline failure can
alter scientific authority, evidence admission, applicability, uncertainty,
replay identity or assurance. Infrastructure and authority repairs in 14.1 may
proceed specifically to close those failures.

### 14.1 — Close authority, runtime and review debt

Owner: implementation agent. Reviewer: independent read-only scientific
reviewer for every claim/evidence/UQ/assurance change.

- [ ] Re-review the final BIG 12 fix batch; resolve or explicitly disposition
      model-selection binding, output-node applicability, multiscale resume
      dependency and commit-taint findings.
- [ ] Run the missing BIG 13 round-5 review; resolve or explicitly disposition
      every finding. Bundle self-consistency must not be called authenticity.
- [ ] Fix the source-first Units findings U-01/U-02/U-03 and verify that the
      unit-registry fingerprint is bound at the execution/replay envelope.
- [ ] Harden provider identity failure semantics: a failed, non-zero or timed
      out version probe must not create or cache an execution identity.
- [ ] Align advertised Python/optional-dependency support with the environments
      actually tested; either support an environment or refuse it explicitly.
- [ ] Re-run the affected regression packs after each bounded fix and append
      the exact commands/results to PROGRESS.

### 14.2 — Triage and select the evidence target

Owner: repository maintainer. Selection must be recorded before new evidence
or acceptance logic is added.

- [ ] Perform a bounded triage of all four flagships using existing records:
      admissible independent data, applicability status, unresolved numerical
      residuals, execution cost and expected evidence value.
- [ ] Select one primary flagship and at most one backup for deep closure work.
      Record the selection rationale, exact target outputs and evidence bar.
- [ ] Pre-register the diagnostic questions and acceptance criteria without
      changing the six BIG 13 outcomes.
- [ ] Move the non-selected flagships to explicit deferred status; retain their
      `insufficient_evidence` verdicts and recorded gaps.

The triage must cover these known questions, but deep implementation is limited
to the selected flagship(s):

- A: missing independent cell-side conservation check, non-monotone window
  study, Chen2020 applicability and representative-day approximation error;
- B: peak-stress convergence, the CalculiX difference and absence of an
  independent thermo-structural numerical benchmark;
- C: near-lid mapping/discretization effects, SU2 flux miss and authoritative
  verification of the Ghia transcription;
- D: GRI-Mech applicability and absence of ignition-delay/flame experimental
  comparison.

### 14.3 — Diagnose, quantify and admit evidence

Owner: implementation agent. External dependencies: authoritative data,
provider environments and applicable licenses.

- [ ] Diagnose the selected residuals without changing the scientific question
      or replacing a failed criterion with a post-hoc success criterion.
- [ ] Define an uncertainty budget for each selected output, separating
      numerical, parameter/input, measurement/reference and model-discrepancy
      channels. Missing channels remain UNKNOWN, never zero.
- [ ] Admit experimental/reference data only through existing provenance,
      license, applicability and calibration/holdout contracts. Numerical
      benchmarks and analytic identities must retain their actual class.
- [ ] Re-run the selected flagship through the generic runtime and regenerate
      its bundle/report from the measured records.
- [ ] Run an independent scientific review of the complete evidence path and
      resolve or disposition every HIGH/MEDIUM finding.

### 14.4 — Full verification and recertification

Owner: repository maintainer. External dependency: GitHub Actions and the
repository ruleset for `main`.

- [ ] Run the supported-environment FAST tier:
      `python -m pytest -m "not expensive" -q -n 4`.
- [ ] Run the supported-environment SCIENTIFIC tier:
      `python -m pytest -m "not campaign" -q -n 4`, with required providers;
      report unavailable providers separately from test failures.
- [ ] Run the declared provider and flagship suites in their exact environments.
- [ ] Run normal and hardened mutation populations; investigate surviving
      mutations rather than weakening scientifically valid guards.
- [ ] Run hardened-core recertification for every certified/trust-sensitive
      change and verify that certificate and assurance evidence bind the exact
      measured source commit.
- [ ] Obtain green automatic CI on the final source head and verify externally
      that `main` requires both `tests-gate` and `recertification-gate`.
- [ ] Reconcile ACTIVE_PLAN, PROGRESS, architecture docs and generated reports
      with the final repository and CI state.

## BIG 14 exit decisions

BIG 14 has two separate outcomes. Do not conflate them.

### Scientific-closure exit — required to finish BIG 14

- [ ] FAST, SCIENTIFIC, required provider suites, mutation gates and hardened
      recertification pass on the exact final source head in declared supported
      environments.
- [ ] BIG 12 and BIG 13 final fix batches have independent review dispositions
      with no unresolved HIGH finding.
- [ ] Every investigated residual is diagnosed with admissible evidence or
      remains an explicit blocking UNKNOWN; none is hidden by changed
      tolerances or post-hoc replacement criteria.
- [ ] Bundle integrity/authenticity wording matches the implemented guarantee;
      an unkeyed manifest is never called authenticated.
- [ ] The selected evidence campaign ends in either a scoped support decision
      or a scientifically justified refusal whose missing evidence and next
      admissible step are explicit.

A justified refusal satisfies scientific closure because it retires ambiguity
honestly. It does not satisfy product evidence readiness.

### Product-evidence target — required before claiming readiness

- [ ] At least one bounded flagship output has quantified uncertainty,
      quantified or explicitly bounded model discrepancy, applicable independent
      evidence and a scoped support decision.

If this target is not met, BIG 14 may close scientifically, but Forge remains
not ready to claim validated flagship capability and BIG 15 must preserve that
limitation.

## Historical status and debt handoff

This is a reference ledger, not an execution queue. Detailed implementation,
reviews, failed approaches and exact test commands live in PROGRESS.

| Area | Current status | BIG 14 ownership |
|---|---|---|
| P0 CI/assurance | Automation exists; final merged-tree assurance and branch rules remain unproven | 14.0, 14.4 |
| P0.1 scientific hardening | Implementation exists; full integrated verification remains pending | 14.1, 14.4 |
| BIG 2 Time | Built; runtime checkpoint emission and multi-basis mapping remain deferred | No new feature work unless selected evidence requires it |
| BIG 3 Environment | Built with fail-closed gaps/interpolation semantics | Diagnose only through selected flagship |
| BIG 4 Lifecycle | Built with explicit degradation/state chaining | Diagnose only through selected flagship |
| BIG 5 Data/materials | Built on existing knowledge/provenance records | Use for admissible evidence; do not create parallel records |
| BIG 6 Numerical | Built; PETSc/SUNDIALS breadth is incomplete | No SUNDIALS/DAE expansion in BIG 14 |
| BIG 7 Spatial | Built; mappings are not generically conservative | Diagnose if selected evidence crosses meshes |
| BIG 8 PDE/FEM | Built with real FEniCSx/PETSc proofs | Provider tests belong to 14.4 |
| BIG 9 Coupling | Built; residual non-blocking gaps recorded | Fix only authority/evidence blockers |
| BIG 10 Multi-timescale | Built; approximation uncertainty is mostly UNKNOWN | Quantify only for selected evidence path |
| BIG 11 Providers | Multiple real providers executed; residual reviews recorded | Identity/support fixes in 14.1; suites in 14.4 |
| BIG 12 System runtime | Built; final fix batch not re-reviewed | 14.1 |
| BIG 13 Flagships | Four built; all insufficient evidence; six criteria unmet | 14.2–14.4 |

## Explicitly deferred from BIG 14

- optional flagship E and all other new flagship breadth;
- new solver-provider families or scientific domains;
- SUNDIALS/DAE and general multi-basis/multi-rate feature expansion unless a
  selected evidence path proves it is an unavoidable prerequisite;
- HPC/distributed execution and commercial-data expansion;
- general BIG 15 graph-level UQ/V&V beyond the minimum contracts required for
  the selected BIG 14 evidence path.

## Stop conditions

Stop implementation and surface a scientific/architectural blocker if a
proposed change would require:

- weakening UNKNOWN or fail-closed semantics;
- changing a frozen serialized contract without an explicit version decision;
- inventing measurements, uncertainty, validation, provenance or evidence;
- duplicating an existing scientific identity, timeline, state or authority;
- adding domain-specific names or branches to generic Scientific Core;
- treating convergence, replay, serialization or solver agreement as
  validation;
- changing a tolerance or criterion after seeing the result to make it pass;
- bypassing automatic assurance gates to make a change appear complete.

## Session resume

At a new session:

1. read `CLAUDE.md` and `docs/project/FORGE_MASTER_PLAN.md`;
2. read this file and the newest relevant PROGRESS entries;
3. inspect actual HEAD, branch, worktree and PR/CI state;
4. continue the first unchecked item under **BIG 14 execution order**;
5. update this file only when the bounded plan changes;
6. append every meaningful milestone, failed approach and executed command to
   PROGRESS.

Historical tables and Master Plan phases are context, not alternate execution
queues.
