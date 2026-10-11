# Forge Master Plan — Strategy

> **Status:** strategic contract, consolidated 2026-10-11.
> **Owns:** direction — what Forge is proving NOW, what comes NEXT, what waits until LATER, and what is superseded.
> **Does not own:** the task queue (`docs/work/ACTIVE_PLAN.md`), the Mind/Discovery scientific contract
> (`docs/discovery/FORGE_GENESIS.md`), maturity (`docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`),
> measurement (`docs/project/PERFORMANCE.md`) or repository rules (`CLAUDE.md`).
> **Previous version** (including "Big Rocks First" and the P0–P40 phase table):
> `docs/archive/FORGE_MASTER_PLAN_2026-10-10.md` — historical reference, not executable authority.

Part I (§1–§6) is the live strategy. Part II is architecture reference: it constrains *how* things are built and never
authorizes *what* to build next.

---

## 1. Authority by scope

Authority is assigned **by scope**. No document globally overrides another; each is final only inside its own scope.
**Execution authority does not imply semantic authority outside the document's scope.**

| Scope | Owning document | Owns | Does not own |
|---|---|---|---|
| Repository-wide working rules | `CLAUDE.md` (+ `docs/CORE_FREEZE_POLICY.md` for frozen contracts) | Non-negotiable engineering and scientific working rules | Strategy, the queue |
| Strategic direction | this file, Part I | NOW / NEXT / LATER / SUPERSEDED | Tasks, science semantics, maturity, measurement |
| Active work | `docs/work/ACTIVE_PLAN.md` | Only "what work is active right now?" — the sole execution queue | Any semantics owned below |
| Mind / Discovery / Genesis | `docs/discovery/FORGE_GENESIS.md` | Scientific and benchmark semantics, step gates | Scheduling |
| Capability maturity | `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md` + `scientific_capability_completion.json` | Maturity stages, promotion, active-epic and exception rules | Scheduling beyond its own policy |
| Performance | `docs/project/PERFORMANCE.md` (measured numbers in `docs/performance/core-performance.md`) | Measurement semantics, measured evidence, freezes, compute claims | Scheduling |
| History | `docs/work/PROGRESS.md`, `docs/work/archive/`, `docs/archive/`, `docs/audits/` | The historical record | Anything current |

Rules:

- `ACTIVE_PLAN.md` selects what to work on. It may **not** override Genesis science, Completion maturity rules,
  Performance measurement semantics, or `CLAUDE.md` repository constraints. Work that would need such an override is
  not schedulable until the owning document is changed through its own process.
- This file sets direction. It does not redefine a semantic owned by another document.
- `CLAUDE.md` scientific authority rules bind every document and every change.
- **Conflict rule.** If two live documents appear to disagree, decide by scope: the document that owns the scope in
  question governs it. If ownership itself is unclear, do not silently pick one: record the conflict in
  `ACTIVE_PLAN.md` under OWNER_DECISION_REQUIRED and continue only with work every involved document allows.
- Repository code and executed results remain the authority for what is actually implemented.

## 2. North Star and boundary

Forge is a **solver-neutral scientific reasoning and trust runtime**. It is **not** a universal physics solver. It
orchestrates mature numerical and scientific providers and decides what can scientifically be claimed from their
outputs: SUPPORTED, REVIEW or REFUSED, with the evidence, uncertainty, applicability and replay that justify it.

Core boundary:

```text
AI workers (Claude, Codex, …)  → propose        (typed proposals only; replaceable)
Solvers / providers            → compute
Data                           → observe        (admitted with provenance, licence, uncertainty)
FORGE Mind                     → manages scientific state and decisions
Trust Layer                    → admits evidence and controls every scientific claim
```

AI workers never own scientific verdicts, evidence admission, applicability, uncertainty, hypothesis status,
planner-authoritative priors or hypothesis weights, predicted separation/divergence, falsification thresholds, success
criteria, utility exchange rates, stopping policy, benchmark grading, or novelty/equivalence decisions. Every
planner-authoritative number must trace back to an execution, admitted data, or a qualified surrogate/model record.

**The moat** is evidence-bound scientific authority: executable Trust semantics, correct refusal, sealed falsification,
multiplicity tracking, Blindfold/escrowed evaluation, provenance and replay, and adversarial scientific validation.

**Not the moat:** provider count, feature count, line count, number of named domains, or generated-candidate count.

## 3. What Forge is proving now

> Forge is currently proving a **trustworthy, measurable scientific reasoning loop** — not maximizing feature or
> provider breadth.
>
> 1. Stabilize / recertify the Trust lane within a bounded timebox.
> 2. Establish Genesis-lite measurement and strong baselines on the existing Blindfold substrate.
> 3. Assemble the Minimal Mind and prove benchmark lift over those baselines.
> 4. Execute one narrow, real engineering refusal/correction demo.
> 5. Add broader cognition, multiphysics and compute only when measurements justify them.

Governing principle (from Genesis): **Measure first. Build the minimum generic mechanism that improves the measurement.
Keep only capabilities that survive ablation.**

## 4. Now / Next / Later

Two near-term tracks share **one** Trust architecture and **one** Mind. Neither may create a second scientific
authority, hypothesis store, belief state, evidence graph or planner.

- **Track A — Discovery credibility:** Genesis-lite, Minimal Mind, measurement, anti-leakage, ablation.
- **Track B — Narrow real demo:** infeasible-specification refusal and correction with real engineering providers.

### NOW

| ID | Item | Why now | Detailed gate |
|---|---|---|---|
| N0 | **Trust lane (Gate G0):** land or honestly disposition the open trust/authority work and recertify against the intended HEAD, inside a timebox with a circuit breaker (§5.2). | Everything else rests on authority that matches the code. | `ACTIVE_PLAN.md` G0 |
| N1 | **Genesis-lite measurement (Track A1):** freeze scoring, strong equal-budget baselines, leakage controls and a compute-budget estimate on the existing Blindfold substrate. | A fitness function must exist before cognition is added. | Genesis §18 Step 1 |
| N2 | **Minimal Mind loop (Track A2):** one closed, measurable loop over existing owners — only after N1 baselines are frozen **and** the Completion Policy's active-epic condition is met (epic changed, or one narrowly scoped approved exception). | Prove lift, calibration and correct refusal. | Genesis §18 Step 2 |
| N3 | **Narrow demo preparation (Track B1):** infeasible-spec refusal + correction on real providers. Preparatory engineering may run alongside N2 using already-built capabilities (new foundations follow the Completion Policy); the demo is not claimed until the N2 gate passes. | One real, auditable demonstration. | `ACTIVE_PLAN.md` Track B |

Continuous in NOW: authority-critical defects interrupt any track (wrong numbers, false SUPPORTED/validated,
corrupted identity/provenance/replay/evidence, evaluator capture, hidden-data leakage). Everything else goes to the
deferred-hardening ledger.

### NEXT — starts only when its prerequisite gate passes

- **One justification/dependency graph** (Genesis Step 3), unifying assumption dependencies, hypothesis lineage,
  evidence support/contradiction, plan/run dependencies, Twin context, design impact, fidelity
  invalidation/resurrection and coupling staleness over existing content identities.
- **Port-based mechanism representation** (Genesis Step 4): typed effort/flow ports, storage, dissipation,
  transformation, conservation, constitutive laws, units/applicability; domain packs supply semantics.
- **Stronger multiphysics only where a benchmark demands it**, extending the existing PhysicsGraph / coupling runtime
  (never a second one): coupling stability/strength, stronger coupling methods, coupled-level verification, interface
  error transport into UQ, consistent constitutive state, regime/instability detection, geometry–physics staleness,
  qualified ROMs, DAE initialization, coupled identifiability.
- **Measured compute scaling** on the staged architecture (`PERFORMANCE.md` §Compute staging): 10 → 100 → 1,000
  candidate campaigns before any larger claim.
- **Narrow intelligent engineering synthesis:** catalog/component selection + bounded continuous parameters +
  explicit constraints + typed interfaces + local replacement + impact analysis that preserves unaffected results.
- **Held-out graduation by reasoning structure** (Genesis Step 6) with a named external evaluator.

### LATER — pulled only by a named benchmark, a measured workload or a customer; never by availability

- Broad provider expansion (new providers need a named benchmark or claim that requires them).
- Free-form / generative geometry and general CAD/assembly synthesis.
- Large distributed / HPC / GPU infrastructure.
- Strategy meta-learning (after ≥ 50 comparable recorded campaigns).
- Therapeutic Hypothesis Assurance as a product (after observational/clinical evidence semantics exist).
- Strengthening domains: materials/chemistry, NIST AM-Bench, safe fusion-energy engineering, bounded biomedical
  engineering.
- Product depth beyond the Track B demo: full drone, vehicle, motor, HVAC, battery-pack products; motion systems;
  assembly breadth; the 3D engineering viewer (Scene IR stays presentation-only).
- Public Blindfold leaderboard, external red-team engagements, an L6 prospective result.

### DEFERRED / SUPERSEDED

| Former rule | Status | Replaced by | Where the old text lives |
|---|---|---|---|
| "Big Rocks First" (old §8.1, 2026-10-09): breadth and providers before hardening | **SUPERSEDED** | §3–§4 and the provider strategy freeze | `docs/archive/FORGE_MASTER_PLAN_2026-10-10.md` §8.1 |
| Roadmap P0–P40 as an ordered phase queue (old §9) | **SUPERSEDED** as execution order; kept as a capability-horizon reference | §4 + `ACTIVE_PLAN.md` | archive §9 |
| Old §10 flagship breadth (HVAC, battery pack, drone, vehicle, fusion, biomedical) | **DEFERRED → LATER** | Track B narrow demo | archive §10; `PERFORMANCE.md` rows 50–58 |
| "Finish the three rocks, then pivot" (`PERFORMANCE.md`, 2026-10-09) | **CLOSED** (rocks merged in #124, Roadmap V2 R1–R8 merged in #125; not certified) | §4 | archive appendix |
| BIG 14 / BIG 15 milestone queue in `ACTIVE_PLAN.md` | **SUPERSEDED** as a queue; live open items carried into G0 | `ACTIVE_PLAN.md` G0 | `docs/work/archive/ACTIVE_PLAN_HISTORY_TO_2026-10-10.md` |
| Nuclear-principle rediscovery in Genesis graduation (owner direction, early Oct 2026; never in this plan's text) | **REMOVED** | Genesis §17.3 | — |
| Therapeutics as a Genesis-core graduation requirement; retrospective therapeutic ranking as a Genesis benchmark (old §4.13.3, §10) | **REMOVED** from Genesis core; LATER product | Genesis §17.1 | archive §4.13.3, §10 |
| Graduation by count of named domains ("five-domain") | **SUPERSEDED** | graduation by reasoning structure, Genesis §17 | — |
| Old §11 progress metrics led by counts | **SUPERSEDED** | §5.4 evidence-maturity progress | archive §11 |

## 5. Program governance

### 5.1 Timebox framework

Every active step in `ACTIVE_PLAN.md` records:

- **start condition;**
- **window:** a maximum engineering window or an owner-set deadline. Dates are never invented: until the owner sets
  one, the field reads `OWNER_DECISION_REQUIRED`;
- **exit gate;**
- **circuit-breaker condition;**
- **allowed outcomes:** `PASS` · `FAIL` · `BLOCKED_WITH_EVIDENCE` · `DEFERRED_BY_OWNER`.

A step whose window has expired may not keep blocking the steps after it: the circuit breaker (§5.2) applies. A `FAIL`
or `BLOCKED_WITH_EVIDENCE` outcome is recorded exactly as observed; it is never rewritten into a pass.

### 5.2 Trust-lane circuit breaker

The project has repeatedly spent large effort on assurance/control-plane work. The circuit breaker stops that work
from blocking everything indefinitely **without** loosening any scientific gate. It changes scheduling only.

When a Trust, recertification or assurance blocker exceeds its window, it is placed in exactly one state:

| State | Meaning | Behaviour |
|---|---|---|
| `SCIENTIFIC_CORRECTNESS` | It can produce wrong numbers, a false SUPPORTED/validated result, or corrupted evidence admission, identity, provenance, replay or claim authority. | **Blocking** until scientifically resolved, or explicitly superseded by stronger evidence. It blocks every claim that depends on it. |
| `GOVERNANCE_ONLY` | Automation, CI enforcement, certificate staleness, packaging or assurance-tool performance — **and** a complete evidence record (below) shows no scientific effect. | May be isolated or deferred. Dependent work may proceed; everything produced meanwhile is labelled **uncertified**. The red result stays recorded. |
| `UNCLASSIFIED` | Default state, and the state of anything whose evidence record is missing or incomplete. | **Blocking** (fail-closed), exactly like `SCIENTIFIC_CORRECTNESS`. Escalate as OWNER_DECISION_REQUIRED if it cannot be classified. |

`GOVERNANCE_ONLY` is never inferred because a blocker is inconvenient, slow or expensive. It requires a short evidence
record, kept in `ACTIVE_PLAN.md` or PROGRESS, that answers all six questions:

1. What scientific result could this issue corrupt?
2. Why can it not corrupt that result?
3. Does it affect evidence admission?
4. Does it affect identity, provenance or replay?
5. Does it affect merge or claim authority?
6. What remains red or unknown after deferral?

If any answer is missing, unsupported or "unknown", the blocker is `UNCLASSIFIED` and blocks.

Every time the breaker fires:

1. **Preserve** the red or negative result exactly as observed.
2. **Document** the blocker, its state and its evidence record in `ACTIVE_PLAN.md`.
3. **Never** loosen a gate, tolerance, criterion, skip rule or certificate to clear it.

The circuit breaker never makes anything certified, qualified or validated, and it never permits bypassing scientific
integrity.

### 5.3 Control-plane budget

Assurance, orchestration, CI, mutation testing and governance exist to protect the product; they must not become the
whole roadmap.

- **Planning warning threshold:** roughly **20 %** of engineering effort over the last four checkpoints, measured by
  merged PRs or sessions by area. It is a warning, not a scientific rule.
- **Why 20 % alone is weak:** effort is hard to measure, and front-loaded trust work is legitimate. So it is paired
  with a sharper signal: **two consecutive `ACTIVE_PLAN.md` checkpoints that advance no Track A/B gate and no
  capability maturity stage** also raise the warning.
- On a warning, record it under OWNER_DECISION_REQUIRED; do not stop work.
- Fixes classified `SCIENTIFIC_CORRECTNESS` are exempt and never count against the budget.

### 5.4 Progress metric

Primary question: **how many relevant capabilities advanced in evidence maturity?** — the computed stage in
`docs/project/scientific_capability_completion.json` (`python -m tools.capability_maturity`), plus the Genesis
measurement vector (baseline lift, calibration, correct refusal, invalidation precision/recall).

Secondary, never primary: qualified provider/regime combinations, replayable evidence bundles, externally scored
blind results, Red Team seeded-flaw detection, false-discovery and false-elimination rates.

Not progress: files, lines, providers, features, foundations, or generated-candidate counts.

### 5.5 Negative results stay visible

Planning never manufactures maturity. As of 2026-10-11 the record includes: the four BIG 13 flagships end
`insufficient_evidence`; the Kirkaldy 2024 fade study is NOT MET (activation energy NOT ESTABLISHED, model discrepancy
NOT QUANTIFIED); the LG M50 DFN study is NOT MET; Battery Practical Pass 1 reported WEAKLY_IDENTIFIABLE (local record,
not on the remote); many uncertainty channels are UNKNOWN; the Roadmap V2 discovery stack is built but not certified or
qualified. Details: `docs/work/PROGRESS.md`, `docs/flagships/README.md`.

### 5.6 Change-control rule

Before adding a large feature, ask:

1. Which NOW/NEXT item and which measurement does it serve?
2. Does a mature provider already solve the numerical problem?
3. Does it require a new generic contract, or only a DomainPack/provider?
4. What is the validity envelope, and what evidence proves it?
5. How are time, environment, lifecycle and uncertainty represented?
6. Can it replay, and does it preserve fail-closed behaviour?
7. Does it duplicate an existing owner (see `docs/architecture/discovery_authority_map.md`)?

If those questions cannot be answered, the feature is not ready.

## 6. Session resume protocol

Every new AI/engineering session:

1. reads `CLAUDE.md` and Part I of this file;
2. reads `docs/work/ACTIVE_PLAN.md` — the only executable queue;
3. reads `docs/discovery/FORGE_GENESIS.md` when the task touches the Mind, Discovery, Blindfold or Genesis;
4. reads the newest relevant `docs/work/PROGRESS.md` entries;
5. inspects the actual HEAD, branches and open PRs before assuming any status;
6. works on the **current gate** in `ACTIVE_PLAN.md`; Part II of this file and every archive are not task lists;
7. updates `ACTIVE_PLAN.md` when the bounded plan changes, appends facts to `PROGRESS.md`, and edits this file only
   for a genuine strategic decision.

Recovery prompt for a lost chat:

> Read `CLAUDE.md`, Part I of `docs/project/FORGE_MASTER_PLAN.md`, and `docs/work/ACTIVE_PLAN.md`. Inspect the current
> HEAD and open PRs and continue the current gate in the active plan. Do not change direction unless repository
> evidence requires it.

---

# Part II — Architecture reference (not an execution queue)

These principles constrain **how** anything is built. They never authorize **what** to build next: scheduling comes
only from Part I §4 and `ACTIVE_PLAN.md`. Phrases such as "must eventually" describe the long-term horizon.

Section numbers keep their pre-2026-10-11 values with an `A.` prefix (old "§4.8" = `A.4.8`) so older references still
resolve. Gaps are sections moved to
`docs/archive/FORGE_MASTER_PLAN_2026-10-10.md`: §4.10–§4.12 and §4.14 (product breadth: design synthesis, motion
systems, electromechanical/wiring, 3D viewer — LATER; detail also in `docs/architecture/design_synthesis.md`,
`motion_systems.md`, `visualization_runtime.md`), §4.13.2–§4.13.3 (now owned by Genesis), §4.13.6 (frontier verticals —
LATER), §8.1 (Big Rocks First — SUPERSEDED), §9 (P0–P40 — SUPERSEDED), §10 (flagships — LATER), §11 (metrics — replaced
by Part I §5.4), §12–§14 (replaced by Part I §5.6 and §6).

### A.2.1 Universal architecture rule

Forge should generalize engineering concepts at the lowest layer where their
meaning is truly cross-domain, then add domain meaning above that layer.

Canonical ownership:

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
Discovery over trusted Scientific Twins
```

The rule is:

> **Core owns universal engineering concepts. Domains own physics-specific
> meaning. Providers own solver-specific translation. Flagships own application
> composition.**

Examples:

- geometry, topology, regions, interfaces, frames, materials, fields, time,
  uncertainty, evidence and replay are generic foundations;
- `lifting_surface`, `crash_structure`, `stator_region` and
  `battery_cooling_plate` are domain/product semantics layered on those
  foundations;
- Gmsh, OpenVSP, OpenFOAM, Code_Aster, CalculiX, OpenRadioss and other tools
  translate canonical records to provider-specific syntax and back;
- a drone, car, motor, HVAC system or battery pack composes reusable
  capabilities rather than creating a new Scientific Core branch.

A concept must not be specialized to one flagship merely because that flagship
is the first place it is exercised. Geometry/body work in particular is a
global Spatial/Geometry Foundation, not an automotive or aerospace subsystem.

## A.3. Explicit non-goals

Forge must **not** become an inferior rewrite of mature tools.

Do not build a new CFD, FEM, CAS, battery electrochemistry, chemical kinetics, mesh generator, CAD kernel, multibody-dynamics engine, control toolbox, optimizer or HPC linear-solver stack merely because Forge needs those capabilities.

Do not recreate mature standard-component catalogs, fastener/bearing data, wiring catalogs or engineering standards by hand when a reliable open-source or standards-backed source can be integrated with explicit provenance.

Prefer adapters/providers around mature open-source projects where scientifically appropriate.

Expected provider families include, over time:

- ngspice — electrical circuits;
- SymPy — symbolic mathematics;
- FEniCSx + PETSc — PDE/FEM and scalable numerics;
- Gmsh + meshio — geometry/mesh pipeline;
- preCICE — numerical multiphysics coupling;
- OpenFOAM and/or SU2 — CFD;
- PyBaMM — battery electrochemistry;
- Cantera — chemical thermodynamics/kinetics;
- CoolProp — thermophysical properties;
- TESPy / OpenModelica — system-level thermal/dynamic models;
- CalculiX / Code_Aster / Elmer where independent structural providers are useful.

A provider is not considered "integrated" because it can be imported or executed. A real Forge integration requires canonical input/output, identity, applicability, evidence, replay and failure semantics.

## A.4. First-class scientific pillars

### A.4.1 Mathematics

Forge needs explicit mathematical capabilities for:

- linear algebra;
- symbolic algebra;
- calculus;
- ODE/DAE;
- PDE;
- numerical analysis;
- probability and statistics;
- Bayesian inference;
- uncertainty quantification;
- sensitivity;
- optimization;
- automatic differentiation where useful.

Forge owns the contracts, scientific semantics and evidence. External libraries perform computation.

### A.4.2 Scientific data

Data is a first-class scientific input.

Every admitted dataset must be able to carry:

- source/provider;
- version and immutable identity;
- license/usage restrictions;
- measurement or derivation method;
- units;
- uncertainty;
- operating conditions;
- validity envelope;
- calibration/validation role;
- redistribution policy;
- content digest and provenance.

Initial policy: **open/free data first**. Use NASA, NIST, Zenodo, universities, public benchmark datasets and appropriately licensed public experimental data.

Paid/proprietary data is deferred until funding, a customer, or a specific capability justifies it.

### A.4.3 Materials

A material is not a bag of constants.

The material system must support properties that depend on state and history, including where relevant:

- mechanical;
- thermal;
- electrical;
- chemical;
- fatigue;
- creep;
- corrosion;
- oxidation;
- moisture;
- UV exposure;
- temperature/pressure dependence;
- anisotropy/composites;
- degradation state.

The same material identity should be consumable by multiple domains without duplicating authority.

### A.4.4 Time

Time is a core scientific dimension, not an add-on.

Forge must represent:

- simulation clocks;
- time windows;
- event timelines;
- usage histories;
- exposure histories;
- cycle histories;
- state histories;
- state transitions;
- checkpoints and replay.

Different domains may advance on different time scales.

### A.4.5 Environment

Environment is an input domain with explicit history.

Target environmental quantities include:

- solar irradiance and orientation;
- ambient temperature;
- humidity;
- wind;
- rain/water exposure;
- salt/chloride exposure;
- dust/sand;
- ambient pressure/altitude;
- gravity/body forces;
- seasonal and location-dependent variation.

Environmental inputs must remain traceable to source data or declared scenarios.

### A.4.6 Lifecycle and degradation

Forge must represent how a product changes with time, use and environment.

Target degradation families include:

- corrosion;
- fatigue;
- crack/damage accumulation;
- wear/friction;
- oxidation;
- UV aging;
- thermal aging;
- moisture degradation;
- creep;
- coating degradation;
- fouling/erosion;
- battery calendar aging;
- battery cycle aging.

Degradation changes the future physics. Updated thickness, material properties, resistance, capacity, geometry or other state must feed back into subsequent simulation.

### A.4.7 Spatial / Geometry Foundation, fields and mesh

Spatial/geometry semantics are a **global Core foundation** shared by every
applicable domain. They must not be designed around cars, drones or any other
single flagship.

The canonical foundation should support, incrementally:

- `GeometryEntity`, `Body`, `Part`, `Assembly`, `Region`,
  `Boundary`, `Interface` and topology relations;
- coordinate frames and rigid transforms;
- parametric dimensions/variants without turning Forge into a CAD kernel;
- material and property bindings to bodies/regions;
- boundary-condition and load bindings;
- canonical provider-entity mappings;
- geometry receipts, immutable identity and provenance;
- mesh identity and geometry-to-mesh bindings;
- scalar, vector and tensor fields;
- interpolation/projection and conservative mappings where supported;
- discretization metadata and transfer-error evidence.

Provider-native identifiers such as Gmsh `(dim, tag)` values must never become
the scientific identity of a Forge entity. A stable Forge identity maps to
provider entities through an explicit adapter/receipt.

The same geometry may carry different domain semantics simultaneously. For
example, one surface can be an aerodynamic wall to CFD, a load-bearing boundary
to structures and a thermal interface to heat transfer without duplicating the
underlying geometry authority.

Initial provider direction:

```text
Spatial / Geometry Foundation
      ├── Gmsh / OpenCASCADE     → mesh / CAD translation
      ├── OpenVSP                → aerospace parametric geometry
      ├── OpenFOAM / SU2         → fluid-domain mapping
      ├── Code_Aster / CalculiX  → structural mapping
      └── future providers       → same canonical contracts
```

Core semantics remain provider-neutral.

### A.4.8 Multiphysics

A multiphysics simulation is not several independent runs.

Forge must support:

- arbitrary participants;
- typed ports;
- coupling edges;
- one-way and two-way coupling;
- explicit/sequential coupling;
- iterative/fixed-point coupling;
- relaxation/acceleration;
- convergence criteria;
- field/scalar transfer;
- mapping provenance;
- conservation checks;
- coupling residual history;
- stateful transient execution.

### A.4.9 Scientific trust

The existing scientific authority rules remain load-bearing.

In particular:

- UNKNOWN never becomes VALID;
- missing uncertainty never becomes zero;
- solver agreement never becomes physical truth;
- convergence is not validation;
- verification is not validation;
- LLM/planner assertions are not scientific evidence;
- evidence is bound to the exact run/model/context it supports;
- removing evidence cannot increase assurance;
- unsupported claims must remain REVIEW/REFUSED rather than being forced through.

### A.4.10–4.12 → LATER (moved to the archive)

Design synthesis, motion systems / multibody dynamics and electromechanical actuation / controls / wiring are
long-term horizon. Detail: `docs/architecture/design_synthesis.md`, `docs/architecture/motion_systems.md` and the
archived Master Plan §4.10–§4.12. The NEXT item "narrow intelligent engineering synthesis" (Part I §4) is the only
currently scheduled slice.

## A.4.13 Mechanism-aware and blind scientific discovery

Forge's discovery direction is mechanism-aware rather than black-box search.

Dependency, mechanism and causal claim remain distinct. Sensitivity, solver
agreement, correlation, optimization score or an LLM proposal do not become
causal/scientific evidence.

Discovery may propose competing mechanisms, interventions, counterfactuals,
scaling relationships, candidate designs or unexplained residuals, but stronger
claims require the applicable evidence path and, where necessary,
discriminating experiments.

The strategic target is **Blind Scientific Discovery**, not a library of
domain-specific answer templates. Forge should be able to receive a bounded
problem, an admitted knowledge universe, physical/mathematical primitives,
available data and providers, then generate and falsify hypotheses without
being told the expected historical answer.

Canonical direction:

```text
Problem / scientific objective
        ↓
Admitted Knowledge Universe
        ↓
Hypothesis / Candidate Generation
        ↓
Dimensional + logical + physical constraints
        ↓
High-throughput cheap evaluation
        ↓
Multi-fidelity promotion
        ↓
Independent solvers / evidence
        ↓
Falsification + UQ + model discrepancy
        ↓
Surviving hypotheses / candidates
        ↓
Next-best experiment or explicit UNKNOWN
        ↺
```

First-class discovery contracts should include, reusing existing authority
where possible:

- `Hypothesis` / `HypothesisIR`;
- `Experiment` / `ExperimentIR`;
- `DesignSpace`, `DesignVariable`, `DesignCandidate`;
- constraints, objectives and compatibility rules;
- fidelity rung and provider plan;
- candidate/hypothesis lineage;
- Design Memory for positive, negative and refused results;
- Pareto and elite archives where optimization is applicable;
- novelty / duplicate detection using canonical identity;
- experiment-selection rationale and expected information gain;
- trust/evidence state for every promoted claim.

The LLM is a proposer and interpreter, not scientific authority. Numerical
providers, admitted data, holdouts, experiments and Forge's Trust Layer remain
the authority for what a hypothesis is allowed to claim.

### A.4.13.1 High-throughput multi-fidelity discovery

"Millions of experiments" means millions of **virtual hypothesis/candidate
evaluations** where the fidelity permits it, not millions of high-fidelity CFD,
FEM or explicit-dynamics solves on one machine.

The runtime should aggressively reduce the candidate population before
expensive execution:

```text
millions of hypotheses/candidates
        ↓
symbolic / dimensional / hard-constraint filters
        ↓
vectorized algebraic / lumped models
        ↓
surrogates / reduced-order models
        ↓
medium-fidelity numerical providers
        ↓
small high-value set
        ↓
high-fidelity providers
        ↓
independent verification / experiment
```

Throughput is recorded by fidelity class. A cheap screening result must never
be relabeled as high-fidelity support. A favorable surrogate must not override
a contradictory higher-fidelity or experimental result.

### A.4.13.2–4.13.3 → owned by FORGE Genesis

Blind historical rediscovery, leakage control and the Genesis benchmark are specified only in
`docs/discovery/FORGE_GENESIS.md`. The archived text is superseded where they differ (for example, therapeutic and
fusion tasks are no longer Genesis-core benchmark families).

### A.4.13.4 Scientific Red Team / Design-Killer search

Discovery must also be able to run in the opposite direction: attempt to break
a proposed engineering/scientific claim.

Target flow:

```text
Claim / candidate
    ↓
Scientific Twin
    ↓
admissible parameter/environment/model variation
    ↓
multi-fidelity adversarial search
    ↓
counterexamples / failure regions / model disagreement
    ↓
Trust Envelope
    ↓
dominant evidence gaps
    ↓
next-best experiment
```

This "physics penetration testing" capability is a core strategic
differentiator. It should find the conditions, assumptions or coupled
subsystems that destroy a nominally attractive result before Forge permits a
strong support claim.

### A.4.13.5 Credibility graph and next-best experiment

For system-level decisions, Forge should represent how lower-level evidence and
uncertainty support or weaken higher-level claims. A weak upstream material,
model or subsystem claim must not disappear inside a confident whole-system
summary.

The discovery runtime should therefore support:

- claim/evidence dependency graphs;
- dominant uncertainty/evidence-gap tracing;
- propagation of REVIEW/UNKNOWN states;
- experiment ranking by expected ability to discriminate hypotheses or reduce
  decision-relevant uncertainty;
- immutable evidence updates that create new Scientific Twin revisions.

### A.4.13.6 and 4.14 → LATER (moved to the archive)

Frontier verticals (safe fusion-energy engineering, bounded biomedical / medical-device engineering) and the global 3D
engineering viewer are LATER items (Part I §4). Detail: archived §4.13.6 and §4.14 and
`docs/architecture/visualization_runtime.md`. Scene IR remains presentation-only.

## A.5. Multi-timescale execution

Forge must eventually coordinate phenomena whose natural time scales differ by many orders of magnitude.

Examples:

```text
Electrical / switching       microseconds → seconds
Vibration / controls         milliseconds → seconds
CFD / transient mechanics    milliseconds → minutes
Thermal                      seconds → hours
Battery operation            minutes → days
Fatigue / wear               days → years
Corrosion / UV aging         months → decades
```

Do not brute-force a decade using the fastest time step.

The runtime should support scientifically justified representative windows, aggregation, reduced/accelerated evolution, slow-state updates, re-evaluation and explicit approximation evidence.

## A.6. Domain-extension rule

A new domain must enter through generic extension contracts.

**Failure condition:** adding a new domain requires sprinkling domain-specific names or branches throughout Scientific Core.

Preferred reusable scientific shape:

```text
CapabilityPack / DomainPack
├── Models / Governing Laws
├── Mechanisms
├── Realizations
├── Solver Providers
├── State Schema
├── Ports
├── Coupling Semantics
├── Applicability / Regimes
├── Conservation
├── Uncertainty / Model Discrepancy
├── Design Variables / Constraints
├── Geometry / Motion Requirements
├── Validation Routes
└── Result Adapters
```

Products such as a motor, robotic arm, suspension, HVAC unit, drone, vehicle or
aircraft should normally be composed as a `SystemPack` / `ProductTemplate`
from reusable capabilities rather than becoming new Scientific Core branches.

A SystemPack may additionally bind geometry, assembly topology, standard
components, joints/mechanisms, wiring/routing, controls, manufacturing
assumptions and product-level requirements.

The strongest extensibility test is an external package that can be installed and enabled without modifying Forge Core.

## A.7. Provider-integration definition of done

A provider is production-worthy only when it has:

- deterministic identity/version capture;
- declared supported model/realization/solver capabilities;
- canonical input adaptation;
- canonical ScientificResult adaptation;
- units and dimensions preserved;
- applicability checks;
- explicit unsupported cases;
- convergence/numerical-health evidence where relevant;
- uncertainty handling or an explicit statement that it is unavailable;
- replay/provenance;
- adversarial tests;
- at least one external/reference validation route.

Do not count shallow wrappers toward provider breadth.

## A.8. Data policy

Until funding or a specific commercial need:

1. prefer open/public datasets;
2. preserve original license and source metadata;
3. never silently redistribute data whose license does not permit it;
4. separate REFERENCE, EXPERIMENTAL and SYNTHETIC data;
5. keep calibration and validation/holdout roles explicit;
6. do not call public data "certified" unless an appropriate authority actually certifies it;
7. use paid data only when it unlocks a capability not reasonably achievable with open data.
