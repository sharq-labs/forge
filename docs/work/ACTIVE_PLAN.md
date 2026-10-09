# Active Plan

Purpose: define the one bounded, resumable execution slice that Forge should
pursue now. Strategic direction remains in
`docs/project/FORGE_MASTER_PLAN.md`; completed work, failed approaches and test
transcripts remain in `docs/work/PROGRESS.md`.

## Current objective

The architecture-first BUILD phase through **BIG 13** is complete and merged.
Forge now enters **BIG 14 — Scientific Closure & Recertification**.

BIG 14 remains the stabilization, diagnosis and evidence campaign for the
certification/trust lane. The 2026-10-09 owner strategy additionally authorizes
a **separate parallel Big Rocks expansion lane** for geometry, provider breadth,
Scientific Twins and Discovery. That expansion lane must not mutate the frozen
Trust-Repair source/certificate, and its new capabilities remain unqualified
until the later integration/hardening campaign.

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

## Owner priority update — 2026-10-09

This owner update narrows the immediate execution sequence while preserving the
BIG 14 scientific-closure rules. It does **not** authorize weakening or skipping
the running trust/certification work.

### Live repository/science state

- `main` = `446370651bc1630daf55b9dc0e7db9189946f0fa` (merge of PR #121).
- PR #120 (bundle containment R1 + finite replay tolerance R4) is merged and its
  certificate lineage was verified.
- PR #121 is merged with the Kirkaldy fade study preserved as **NOT MET**;
  activation energy remains NOT ESTABLISHED and model discrepancy NOT
  QUANTIFIED.
- Trust Repair Pass 1 exists locally at
  `803946af905f51c76f2ea9f4c691d410c9c2ca7b`; its landing/recertification
  work is the current trust-critical operation.
- Battery Practical Pass 1 exists locally at
  `7e923e75f38644d567748d2a2ec223a80762d6dc`; decision
  **WEAKLY_IDENTIFIABLE**, so calibration is not authorized.
- Automatic GitHub CI/status enforcement is not currently a reliable merge
  control; local SHA-bound assurance remains authoritative until repository
  policy/billing is resolved.

### Execution order from here — Big Rocks First

This owner decision supersedes the earlier small-fix-first ordering for the
**parallel expansion lane**. It does not weaken or interrupt the frozen
Trust-Repair/recertification lane.

1. **Finish the in-flight Trust Repair Pass 1 landing/recertification on its
   frozen source.** Do not modify its source SHA, certificate or assurance
   artifacts while it is running.
2. Run a separate **Big Rocks expansion lane**. The intended cloud working
   branch is `feat/big-rocks-foundations`; verify the actual remote ref before
   assuming it exists.
3. Build the **general Spatial / Geometry Foundation** and generalized Gmsh /
   OpenCASCADE mapping first, together with generic assembly/product topology.
4. Expand solver/provider breadth early rather than waiting for product polish:
   Gmsh/OpenVSP, OpenFOAM/SU2, FEniCSx/PETSc,
   CalculiX/Code_Aster/Elmer, OpenRadioss, Project Chrono, preCICE,
   PyBaMM/PyBOP, ngspice, Cantera, CoolProp, TESPy,
   OpenModelica/FMI-FMU and other justified providers. Missing cloud
   executables are recorded as `REAL_EXECUTION_DEFERRED`, not fabricated.
5. Build the **Scientific Twin** foundation over canonical system/geometry/model/
   evidence/state identities.
6. Build the **Blind Scientific Discovery Runtime**:
   hypothesis/experiment IR, multi-fidelity search, Design Memory,
   falsification, recursive discovery and next-best-experiment selection.
7. Build the **FORGE Genesis** benchmark: blinded historical rediscovery,
   transformed physics, synthetic universes and no-solution/insufficient-
   evidence challenges.
8. Build the **Scientific Red Team / Design-Killer + Credibility Graph**
   capability over Scientific Twins.
9. Exercise the common architecture with vertical slices: Drone, Vehicle/Car,
   Motor, HVAC, Battery Pack, safe Fusion-energy engineering and bounded
   Biomedical/medical-device engineering.
10. **Then freeze feature breadth and run one integration/hardening campaign**:
    close authority-relevant B1/B2/B4/B5/UQ issues, run supported-environment
    tests, qualify real providers, perform hostile scientific review, classify
    certification scope and recertify the final source where required.

During the expansion lane, use targeted/contract tests and coherent checkpoint
commits. Do **not** serialize every Big Rock behind Full Local Assurance.

A small defect interrupts expansion immediately only if it can produce wrong
scientific numbers, false support/validation, corrupted identity/provenance/
replay/evidence, or directly blocks the current Big Rock. Other cleanup enters
`DEFERRED_HARDENING`.

### Universal architecture rule### Universal architecture rule

New work should follow:

```text
Core Foundations
    ↓
Domain Semantics
    ↓
Domain Models / System Composition
    ↓
Provider Adapters
    ↓
Flagships / Products
    ↓
Discovery
```

Core owns universal engineering concepts; domains own physics-specific meaning;
providers own solver-specific translation; flagships own composition. Do not
create `CarGeometry`, `DroneGeometry` or similar Core authority when a
generic spatial/geometry contract is sufficient.

## Current repository state (historical BIG 14 snapshot; retained for traceability)

- Branch: `feat/big-14-flagship-a` (14.2/14.3 flagship A work), worktree
  `D:/forge-b14`, based on `a0928965` (PR #111's head, merged as `72b829f3`). No PR
  opened yet. 14.1 work was on `feat/big-14-scientific-closure` (merged).
- Base of BIG 14: `origin/main` @ `a3f757eb5fdbc804ef11e3c4088a757c31981870`
  (merge of PR #109, BIG 13)
- Pristine baseline worktree (never edited): `D:/forge-b14-base`, detached at
  the same SHA; baseline test runs happen there so edits cannot contaminate
  tree-walking tests.
- PRs: #110 (14.0 + 14.1 baseline repairs) MERGED 2026-09-27 at `86fa1896`
  by the sharq-labs account with `recertification-gate` red (void formal
  mutation control rounds). #111 carries the follow-up. Verify GitHub
  before any current PR claim.
- Never switch branches in the shared checkout; it is used by other sessions.

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

The Master Plan names the P16 flagship systems as HVAC, battery pack, drone and
vehicle subsystem (§10). BIG 13 flagships A-D are integration proofs of the
generic runtime; only A overlaps a P16 system (battery), and none of them
completes P16. BIG 14 does not redefine P16.

| Execution milestone | Master Plan relationship | Status |
|---|---|---|
| BIG 2–9 | P1–P8 foundations | Built; full merged-tree campaign pending |
| BIG 10 | P14 multi-timescale runtime | Built; full campaign pending |
| BIG 11 | Provider work spanning P7–P13 | Built; residual reviews recorded |
| BIG 12 | Cross-phase end-to-end runtime | Built; final fix batch needs re-review |
| BIG 13 | Integration proofs toward P16 (not the P16 systems) | Built; all results remain insufficient evidence |
| BIG 14 | P0 closure plus bounded P15/P16 evidence work | Current |
| BIG 15 | P15 graph-level UQ/V&V completion | Next |

## BIG 14 execution order

The sections below are sequential unless a task explicitly says it may run in
parallel. The first unchecked item in this section is the next executable task.
Historical status later in this file is not an execution queue.

### 14.0 — Establish the branch and baseline

Owner: repository maintainer / implementation agent.

- [x] Create a bounded BIG 14 branch from current `origin/main` in its own
      worktree; record branch, base SHA and worktree here and in PROGRESS
      (including the PROGRESS "Current branch / PR" header).
- [x] Decide the untracked `AGENTS.md`, `.agents/` and `.codex/` in the shared
      checkout: ignored by owner decision (`.gitignore`, plus the shared
      repository's `info/exclude` until this branch merges).
- [x] Inventory supported Python and provider environments, including exact
      versions, optional dependencies, external executables and WSL/conda
      requirements (PROGRESS, BIG 14 14.0). Explicit refusal of unsupported
      environments is carried by the 14.1 support-alignment item.
- [x] Measure the base SHA in the pristine worktree before changing scientific
      behavior, and record exact commands and results:
      `python tools/forge_check.py --regression`, `git diff --check`, and the
      FAST tier `python -m pytest -m "not expensive" -q -n 4` as a measurement
      (not a gate). `forge_check.py --changed` on an unchanged branch selects
      only the architecture pack and is not a baseline. Save the sorted failing
      node ids; later runs are compared against that list so old drift and new
      regressions cannot hide each other.
- [x] Classify every baseline failure as product defect, stale test/certificate,
      unsupported environment, missing dependency or external-policy blocker;
      record the evidence for the classification. Previously recorded drift
      (Python 3.14 API-surface artifacts, stale `current_core_v2.json`) must be
      re-confirmed on this SHA, not assumed.

#### Baseline stop gate

Do not begin flagship evidence work (14.2 or 14.3) while a baseline failure can
alter scientific authority, evidence admission, applicability, uncertainty,
replay identity or assurance. Infrastructure and authority repairs in 14.1 may
proceed specifically to close those failures.

### 14.1 — Close authority, runtime and review debt

Owner: implementation agent. Reviewer: independent read-only scientific
reviewer for every claim/evidence/UQ/assurance change.

Baseline repairs first (classes from PROGRESS, BIG 14 14.0):

- [x] Class 1: make the provider-free flagship suite run in the core CI
      environment, and make provider suites skip (not error) outside their
      provider environments. The BIG 13 pre-registration pins must execute.
- [x] Class 2: every one of the 12 schema-less `from_dict` readers either
      checks its schema or is proven nested-only (exemption with a test).
- [x] Class 3: classify the nine BIG 5-13 non-Core packages in
      `docs/CORE_FREEZE_POLICY.md`.
- [x] Class 4: add `corrosion` and `hygrothermal` to the derived domain list
      after checking they are real domain packages.
- [x] Class 5: restore the bare-install boundary (optional extras imported
      lazily and named in the guard; tests skip when an extra is absent).
- [x] Independent scientific review of the class 1-5 repairs: round 1 and
      round 2 CHANGES REQUIRED (all fixed), round 3 PASS; LOW residuals L2-L5
      recorded in PROGRESS (BIG 14 14.1).
- [ ] Class 6: run hardened recertification on 3.12 after the repairs
      (GitHub workflow; needs the owner's go-ahead to push the branch / open
      the PR, whose automatic classification runs it).
- [ ] Owner action: configure the `main` ruleset to require `tests-gate` and
      `recertification-gate` (Branch Policy currently reports NOT ENFORCED).
      CONFIGURED BUT NOT ENFORCED. On 2026-09-28 the ruleset "Protect main"
      (id 23351506) was set to require both (source GitHub Actions 15368;
      strict up-to-date on; merge only; no bypass; approvals 0), and
      `branch_policy` reported OK. The repository was later made PRIVATE on a
      free plan. GitHub then disables rulesets: every rules API call returns
      403 "Upgrade to GitHub Pro or make this repository public", and
      `branch_policy` fails. A red gate cannot block a merge today.
      OWNER DECISION: make the repository public, or upgrade to GitHub Pro.
- [x] Fix `tools/wsl_env.sh` so it is not pinned to `/mnt/d/forge-b13`.

Then review and authority debt:

- [x] Re-review the final BIG 12 fix batch; resolve or explicitly disposition
      model-selection binding, output-node applicability, multiscale resume
      dependency and commit-taint findings. Done 2026-09-28 on
      `feat/big-14-reviews` (PROGRESS, "14.1 review debt"): (a) HIGH closed
      by refusing validity records and keeping labels out of
      `provenance.models`; R1, N1, N2, (c) and (d)-1 fixed. Deferred with
      reasons: the executed-model binding.
- [x] BIG 12 R2 / (d)-2 (MEDIUM): state reads are not DAG edges. Done
      2026-09-28 (owner decision), `246098fc`: `reads_owners` (omitted when
      empty, so no stored digest moves), a StateView per node, and the planner
      orders readers against writers and every two committing nodes. No
      flagship request needed a change.
- [x] BIG 12 (b) (MEDIUM): output-node applicability is undisclosed. Done
      without a version bump: `undeclared_applicability(result)` is derived
      from the plan the result carries and named in the `trust_handoff`
      notes. Making declare-or-waive mandatory for output nodes stays a
      request-contract change for a later regeneration.
- [x] Run the missing BIG 13 round-5 review; resolve or explicitly disposition
      every finding. Done 2026-09-28: F1 partial (the recorded providers are
      bound; completeness and pre-registration are a documented limit), F2-F8
      fixed, F4 pins the committed bundles' full digests. Bundle self-consistency must not be called authenticity.
      Include: `engineering/reference.py` `ReferenceCondition` / `EnvelopeBound`
      readers pre-coerce with `float(payload[...])` (the U-01 pattern; found
      by the 14.1 units review).
- [x] Run the missing second BIG 11 re-review (the focused re-review's fixes
      were never re-reviewed); resolve or disposition its findings. Done
      2026-09-28: A1 HIGH (held UNKNOWN ambient) and A2 MEDIUM (non-affine
      selections) fixed; LOW A3-A6 recorded.
- [x] Resolve or explicitly defer BIG 13 review M7: study/limit records ship
      inline but their provider bindings are not compared with the main
      request. DEFERRED to BIG 15 graph-level V&V (the study requests are not
      shipped; stated in `engineering.md`).
- [x] Fix the Units findings U-01/U-02/U-03
      (`docs/code_audit/MODULE_BY_MODULE_REVIEW.md`) with focused adversarial
      tests (also numpy bool/arrays, bytes, memoryview, numbers as units).
- [x] U-05 - OWNER DECISION (2026-09-28: bind it, `b07a58f1`;
      `claim_replay_environment/2`; /1 still verifies and never replays
      exactly): verified that the unit-definition content
      (`registry_fingerprint()`) is bound nowhere; only the Pint version is
      (claims replay environment, provider identities). Binding it moves
      every stored bundle's environment fingerprint: needs a version decision.
- [x] U-04 - OWNER DECISION (2026-09-28: `pint>=0.25.3,<0.27`, the
      measured range) on a Pint compatibility range: the units
      contract passes on Pint 0.25.3 and 0.26.1; the declared minimum 0.23 is
      untested and there is no upper bound.
- [x] U-06 recorded as accepted LOW residual (runtime context mutation is
      prohibited; the ledger states the limit).
- [x] Harden provider identity failure semantics. Known defect:
      `executable_probe` in `src/engcore/providers/catalog.py` ignores the
      version probe's exit code, so a non-zero exit whose output parses as a
      version yields `AVAILABLE` and is cached. Also establish whether a cached
      `AVAILABLE` status can outlive a changed executable/environment before an
      execution identity is formed. A failed, non-zero or timed-out probe must
      not create or cache an execution identity.
      Done: exit code enforced (OpenFOAM's own probe too); CalculiX declares
      its measured 201; refresh drops the cached Python environment digest.
- [x] Review F2 (MEDIUM): a conda package set changed after a cached probe
      is now re-checked at launch beside the executable re-hash
      (`ProcessInvocation.conda_environment`, `conda_environment_of`); every
      adapter invocation declares it (static test). Residual: the digest
      covers conda package RECORDS, not files edited in place, nor system
      tools reached through PATH (/bin/sh, a host C toolchain).
- [x] Re-review N1 (MEDIUM): library providers (Cantera, PyBaMM, CoolProp,
      TESPy) now check at execution that the library they import is the one
      discovery bound (`require_library_unchanged`, 1-3 ms per call), in
      every function that forms an identity (PyBaMM coupling `advance`
      included), and the module IN MEMORY must match (location, `__version__`,
      the discovery it was first imported under); discovery refuses a module
      that is not a file of the distribution it binds (shadowing / editable).
      Declared dependencies are covered too: per-distribution pins, their
      `__version__` in memory, and every module derived from a distribution's
      own files must load from those files - the parsed RECORD's module
      files, else the conda package record's files (conda-installed casadi),
      else nothing is established and it is refused; editable installs and
      checkout egg-infos establish nothing. Adapters re-check after importing.
- [x] Re-review the F-1 / F-2 fix (`catalog._footprint`: parsed RECORD,
      editable refusal, empty-module refusal). NOT re-reviewed: the review
      loop on this sub-area was closed after seven rounds; carry it into the
      next review batch. Re-reviewed 2026-09-28: PASS (LOW B1-B4 recorded).
      Recorded LOW: `Mechanism.from_cantera_data` and
      `forge_pybamm.parameter_set` import their library without the check
      (their outputs are content-hashed); `<pkg>.libs` dirs derive as module
      names; conda egg-info packages are refused (visible, not silent). OPERATING RULE: a provider-environment change takes effect in a
      new process; a same-version rebuild of an already-loaded module cannot
      be seen from inside the process. Residuals: the shared python-environment
      digest is re-read only on refresh; undeclared dependencies are unbound;
      `found_but_refused` reads reason prefixes; FEniCSx (distribution
      `fenics-dolfinx`, LIBRARY mode) is not covered by this check - open.
- [x] Project review 2026-10-05 (`docs/work/PROJECT_REVIEW_2026-10-05.md`),
      re-read against `origin/main` @ `16c87f40` on 2026-10-09:
      R1 (HIGH, bundle export path containment) FIXED on
      `fix/big-14-review-r1-r4`; R4 (MEDIUM, non-finite replay tolerance)
      FIXED on the same branch; R2 (failed version probe) and R3 (RECORD vs
      installed bytes) were already covered by the provider-identity items
      above (`returncode` refusal, `catalog._footprint`); R5 (provider and
      flagship collection in CI) is carried by the Pass 13 per-skip admission
      rules, and the provider suites still run in their own environments
      under 14.4.
- [ ] Align advertised Python/optional-dependency support with the environments
      actually tested; either support an environment or refuse it explicitly.
      OWNER DECISION: `pyproject.toml` says `requires-python = ">=3.11"`;
      CI runs 3.11/3.12 only; the local venv is 3.14 and the provider env is
      3.13 (PyBOP caps below 3.14).
- [ ] Re-run the affected regression packs after each bounded fix and append
      the exact commands/results to PROGRESS.

### 14.2 — Triage and select the evidence target

Owner: repository maintainer. Selection must be recorded before new evidence
or acceptance logic is added.

- [ ] Perform a bounded triage of all four flagships using existing records:
      admissible independent data, applicability status, unresolved numerical
      residuals, execution cost and expected evidence value.
      NOT recorded as a written triage: the owner chose flagship A directly.
- [x] Select one primary flagship and at most one backup for deep closure work.
      Owner decision (2026-09-27): **flagship A** (battery + cooling +
      lifecycle), no backup. The owner's rationale is not recorded. Facts in
      its favour: it is the only BIG 13 flagship that overlaps a P16 system,
      and measured LG M50 data exist (Chen 2020, Zenodo 4032561). The evidence bar and target outputs are fixed per
      study in each pre-registration (`flagships/forge_flagships/data/big14_a_*`).
- [ ] Pre-register the diagnostic questions, acceptance criteria and the 14.3
      timebox without changing the six BIG 13 outcomes. The pre-registration
      is committed and pushed before any new evidence-bearing execution of the
      selected flagship, and its commit SHA is recorded in PROGRESS. (BIG 13
      could not show from git that its constants preceded the first run; BIG
      14 must be able to.)
      PARTIAL: every flagship A study so far has its own pre-registration
      committed and pushed before its first run (SHAs in PROGRESS), but no
      umbrella pre-registration and no 14.3 timebox were registered before
      the first run. TIMEBOX: owner decision 2026-10-09, two weeks,
      2026-10-09 to 2026-10-23, pre-registered in
      `big14_a_campaign_timebox_preregistration.json` for every 14.3 study
      registered from that date (the earlier studies keep their outcomes).
- [x] Move the non-selected flagships to explicit deferred status; retain their
      `insufficient_evidence` verdicts and recorded gaps. Done 2026-10-09:
      B, C and D DEFERRED in `docs/flagships/README.md` ("BIG 14 status"),
      with their open questions carried unchanged.

Flagship A status (details and SHAs in PROGRESS, "flagship A" entry):

- [x] Cell-side conservation check (BIG 13 M5): met; heat of mixing (83-128 %
      of counted heat) and reversible heat are absent from the model.
- [x] Window study (BIG 13 criterion 1 diagnosis): H1 supported; criterion 1
      stays NOT MET as registered.
- [x] Representative-day approximation error (pre-registered `31c10f2d`):
      MET in both cases; the published 4-of-56-day run underestimates fade
      by 1.2-1.3 % (first order in the macro step).
- [x] Chen2020 against measured LG M50 cells: NOT MET (SPM 149-153 mV at C/2);
      electrode-balance correction: NOT MET (SPM 33-38 mV); heat-of-mixing Hc
      supported.
- [x] OWNER DECISION carried out (2026-09-28): the cell model moved from SPM
      to DFN with the heat of mixing. Study `big14-a-lgm50-dfn`:
      NOT MET (V1 and C1 met at 13.6-16.9 mV; T1 missed on 2 of 3 cells).
      The balance factors are interior (0.980 / 0.854) and carried into the flagship.
- [x] Independence of the Chen 2020 data: NOT independent. The C/2-1.5C curves are
      Chen2020's tuning data (paper read; `chen2020_independence.json`).
- [x] DFN energy check (`big14-a-cell-energy-check-dfn`, review L5): NOT MET,
      1.10 % at 313 K against 1 %.
- [x] Flagship A regenerated on DFN; four battery bundles and the report re-pinned.
  - Degradation voltage shift: -36.2 mV (normal).
  - Fresh-day module heat: 69.0 Wh (was 28.8 Wh on SPM).
  - Window refinement: differences now monotone, but the peak-heat tolerance is
    missed. Level 4 still NOT reached.
- [x] LG M50T ageing data (Kirkaldy 2024, Zenodo 10637534, CC-BY-4.0) for the
      fade model. Download approved by the owner 2026-10-09: Expt 5 (standard
      cycle ageing, 10.4 GB, calibration) and Expt 4 (drive-cycle ageing,
      11.4 GB, holdout) into `D:/forge-data/kirkaldy2024/raw` (not committed).
      Study `big14-a-kirkaldy-fade` pre-registered before any capacity value
      was read (`dd53eec7`). RUN 2026-10-09: **NOT MET** (holdout RMSE 0.037
      against 0.015; 25 degC bias 0.027 against 0.010; 10 and 40 degC bias
      met; activation energy at its lower bound in every refit, so NOT
      ESTABLISHED: the calibration fade is not monotone in temperature, per
      the PROGRESS fade levels and the record's
      `calibration_residuals_per_temperature` (10 degC -0.048, 25 degC
      +0.013, 40 degC +0.004), and a monotonic Arrhenius factor cannot
      represent it). Model discrepancy NOT
      QUANTIFIED. Flagship A's declared fade parameters overpredict this
      cell's fade, 38 of 64 predictions outside the model's state range
      (reported, not judged; LG M50T is not flagship A's LG M50).
      CLOSED 2026-10-09 as a justified negative result: the throughput-Arrhenius
      campaign is NOT MET. No threshold or split changed; five recorded
      deviations (`deviations_from_preregistration`) and the activation-energy
      spread not carried as uncertainty (bound-pinned) are stated in
      `docs/flagships/README.md`; none can turn NOT MET into MET.
- [ ] (NOT STARTED; not part of this campaign) A temperature-dependent or
      non-monotone fade law is a NEW study: its own model hypothesis, a new
      pre-registration, explicit complexity control, calibration/selection
      data, and a fresh confirmatory holdout not used to choose the law. The
      Kirkaldy Expt 4 holdout has been observed; it may serve exploratory or
      model-development work but must not be relabelled as unseen
      confirmatory evidence for the new law.
- [ ] Out-of-sample cell data (LG M50 curves NOT used by Chen2020): the only
      untouched curves in hand are C/10. An independent dataset is needed for
      any validation claim about the cell model.

The triage must cover these known questions, but deep implementation is limited
to the selected flagship(s):

- A: missing independent cell-side conservation check, non-monotone window
  study (whose monotone requirement was itself added after the first review),
  Chen2020 applicability and representative-day approximation error;
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
- [ ] Respect the pre-registered timebox. If admissible independent data or a
      required provider environment is not available within it, close the
      selected campaign as a justified refusal (missing evidence and next
      admissible step named) instead of extending scope.

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

- [ ] At least one bounded flagship output has quantified uncertainty, model
      discrepancy quantified or bounded by admissible evidence (a caller- or
      flagship-declared bound is not evidence), applicable independent
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
| BIG 11 Providers | Multiple real providers executed; second re-review not run | Re-review and identity/support fixes in 14.1; suites in 14.4 |
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


## 2026-10-07 bounded override - Local Assurance optimization

Current task: external temporary mutation scratch, bounded independent
--mutation-workers (default 2), fail-closed concurrency and non-certifying
failure diagnostics. Focused control-plane tests and independent review only;
commit locally after checks. Resume remains design-only. Do not run full
assurance, generate a certificate, push, open a PR or merge in this task.

Optimization implementation complete: targeted Python 3.12 pack 215 passed,
Python 3.11 local-control pack 31 passed; independent read-only review PASS.
Next action: further control-plane review. Full assurance remains deferred
until explicit user authorization; no certificate or external publication.


## 2026-10-07 bounded override - Optimization pass 2 (static only)

Base: 8d5eed3f47a0490d481b7ff5c9927f2f944096db in WSL
/home/dev_kaeem/forge-local-assurance-72bf7c4c.
Implement per-shard persistent isolated seed/worker storage for V4 then Formal,
complete byte/mode manifests, incremental repair and fail-closed ownership.
Add non-authoritative performance telemetry outside official evidence.
Default mutation-workers stays 2. Resume and prior evidence reuse stay disabled.

Absolute restriction: implementation and static review only. TESTS_RUN: 0.
Do not execute project code, tests, assurance, benchmarks, measurements or any
certification path in this slice. Do not push, open a PR or merge. Keep edits
available for review; no local commit is required for this slice.
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.

Implementation complete with independent source-only review disposition;
execution remains unverified. Next bounded action is further static optimization
review of restore/hash I/O and failure telemetry completeness. Do not execute
project code or tests without a later explicit change to the restriction.
CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## 2026-10-07 bounded override — Optimization pass 3 (static only)

Supersedes earlier execution/local-commit permissions for this slice. Optimize
persistent workspace indexing, sparse restoration, descendant ownership and
non-authoritative lifecycle diagnostics. Keep full worker SHA-256 verification,
independent .git copies, unchanged populations/default workers and no resume.
No tests, project execution, assurance, benchmarks, certificates, commit, push,
PR or merge. TESTS_RUN: 0; ASSURANCE_RUN: NO;
FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.

Implementation and independent hostile static review are the completion gates.
Future tests remain specifications until explicitly authorized. Static cost and
remaining memory/ownership risks: LOCAL_ASSURANCE_OPTIMIZATION_PASS_3.md.

Pass 3 implementation complete; independent hostile static reviewer PASS after
Git case-normalization correction. Execution remains unverified. Next bounded
work: pass 4 static memory/Git-sealing/ownership review; testing and measurements
require explicit authorization. CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## 2026-10-07 bounded override — Optimization pass 4 (static only)

Replace full pristine byte cache with streamed seed-backed restoration and full
seed identity checks; seal inherited Git/config/import/pytest/temp redirects;
enforce detectable dedicated-process assumptions and explicit handle lifecycle.
Retain independent Git storage, full worker SHA, populations/verdicts/control
ordering/default workers and no resume. No tests/imports/project execution,
assurance, benchmarks, certificates, commit, push, PR or merge. TESTS_RUN: 0;
ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
Implementation and independent hostile accumulated Pass 2–4 static review are
completion gates. Contract: LOCAL_ASSURANCE_OPTIMIZATION_PASS_4.md.

Pass 4 complete with final independent hostile static review PASS after Git
section-grammar correction. No execution verification. Next bounded action:
Pass 5 static Git/config/environment, cleanup and specification review. Explicit
authorization is required to change the execution restriction. No publication.
CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## 2026-10-07 bounded override — Optimization pass 5 (static only)

Audit full Git inputs/closure, owned cleanup, reaper transitions, scan/read model,
restoration I/O, telemetry and bounded concurrency. No tests/imports/project
execution, assurance, benchmarks, certificates, commit, push, PR or merge.
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
Implemented fresh owned artifacts/tokens, atomic diagnostics, Git lazy-fetch/
format refusal, ceiling/host attributes sealing, candidate SHA skip, parent
abnormal retention and non-destructive old-run quarantine. Default workers 2;
all populations/expectations/attribution/control order unchanged; no resume.
Fresh reviewer found arbitrary target absolute-path access is outside this
control plane: OS sandbox vs controlled target/toolchain contract clarification
pending. Do not issue unqualified PASS for an unenforced OS isolation claim.
Contract and cost tables: LOCAL_ASSURANCE_OPTIMIZATION_PASS_5.md.

Pass 5 source corrections complete; fresh independent review BLOCKER for literal
arbitrary-target OS isolation. Controlled-input findings corrected, cost P2 fixed.
Await user contract disposition; no OS sandbox/provider restrictions invented.
Do not claim PASS/ready while that demonstrated access capability remains in scope.
CONTROL_PLANE_NOT_READY. All execution/publication restrictions remain active.

User contract decision received: "Controlled targets and toolchain; seal inherited
inputs and runner-owned paths." This explicitly resolves the prior scope blocker;
no OS isolation guarantee claimed. Final reviewer confirmation requested under
that accepted contract. Execution/publication prohibitions remain unchanged.

Final fresh independent reviewer PASS under the explicitly accepted controlled-
target/toolchain contract; previous scope blocker and cost P2 resolved. No OS
sandbox claim, no source execution or tests. Final git diff --check exit 0;
git diff --stat/status inspected, changes remain uncommitted, HEAD unchanged.
TESTS_RUN: 0; ASSURANCE_RUN: NO; FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.
No scientific/domain change, certificate, commit, push, PR or merge.
Recommended Pass 6: statically audit specification/contract compatibility and
owned filesystem operations; first runtime validation requires explicit change
of execution authorization. CONTROL_PLANE_READY_FOR_NEXT_OPTIMIZATION_PASS.


## Local Assurance Pass 6 — static stabilization

Complete accumulated tracked/untracked audit recorded in
LOCAL_ASSURANCE_OPTIMIZATION_PASS_6.md. Implementation repairs and unexecuted
specifications cover collisions, safe canonical evidence closure, atomic JSON,
source identity, exit-code authority and failure retention. Independent static
review is the freeze condition. Tests and all runtime probes remain prohibited.
Next executable performance work requires separate authorization for runtime
validation; do not alter workspace trust semantics for startup optimization.
TESTS_RUN: 0. ASSURANCE_RUN: NO. FULL_LOCAL_ASSURANCE: NOT_RUN_BY_DESIGN.

Final independent static review returned PASS. Workspace architecture is ready
to freeze under the controlled-target/toolchain contract; runtime compatibility
remains unestablished. Pass 6 complete; await authorized runtime validation.


## Pass 7 — fresh-process startup optimization

Implemented deterministic mutation plugin policy, immutable startup inputs,
interpreter identity checks and no shared bytecode. Preserved the frozen workspace
and attribution contracts. Static target model: 284 Formal + four controls and
678 eligible V4 + eight controls = up to 974 fresh pytest launches. Specifications
written but NOT RUN. Next Pass 8 requires explicit runtime-validation authorization;
no persistent interpreter, fork optimization or workspace redesign is scheduled.

Pass 7 complete: independent final static review PASS; FRESH_PROCESS_OPTIMIZED.
Pass 8 recommendation is bounded runtime validation/measurement only after explicit
authorization. Existing execution ban remains in force.


## Pass 8 — bounded runtime validation

Done 2026-10-07: runtime control plane behaved as specified; blocked only by the
certification_control registration of mutation_startup.py / test_mutation_workspace.py.

## Pass 9 — certification scope fix and V4 verification cost

Done 2026-10-07: registration fixed; snapshot() implementation made ~2.5-3x faster with
an identical manifest. No verification pass removed; removing attempt-start S/W is an
owner decision because specs pin "refuse before execution".
Next (needs authorization): decide whether to commit Passes 2–9, then a 1/2/4-worker
bounded measurement or Full Local Assurance. Optional owner decision: whether the
attempt-start seed check (A1) may move to the restore-time check.

## Pass 12 — safe Formal pytest-xdist

Done 2026-10-07: opt-in Formal xdist with structured crash refusal, per-set named-alone control,
serial confirmation and serial import refusals; -22 % Formal wall on a representative bounded run.
Next (needs authorization): Full Local Assurance with --mutation-workers 4 --formal-pytest-workers 2,
or keep the default 1; the xdist-vs-serial verdict divergence is an owner design decision.

## Pass 13 — semantic skip admission + final recertification

Done 2026-10-08 (source change): scalar skip ceilings replaced by per-skip admission
(tools/certification/skip_admission.py, assurance /7); refusal UX hardened; review round fixed.
Next: one source commit, then a fresh Full Local Assurance from zero
(`run --workers 4 --mutation-workers 4 --formal-pytest-workers 2`); on SOURCE_PASS only, the
certificate-only child and `local_assurance verify`. No push, PR or merge without the owner.
Open (not this pass): provider qualification runs for the 11 optional providers are a separate
activity; the admitted provider skips do not claim them.
