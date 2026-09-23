# Forge Master Plan — Scientific Multiphysics + Lifecycle Runtime

> **Status:** Strategic operating contract  
> **Authority:** This document defines the long-term technical direction of Forge.  
> **Use:** Read this file at the start of every new AI/engineering session before choosing work.

## 1. North Star

Forge is being built as a **solver-neutral Scientific Multiphysics + Lifecycle Runtime with a built-in Trust Engine**.

The target is not to recreate every scientific solver. Forge should coordinate mature numerical/scientific providers, bind them through canonical contracts, run coupled simulations across different time scales, track how products change through environment and use, and state exactly what the resulting evidence is allowed to prove.

Canonical direction:

```text
Engineering / Scientific Intent
                ↓
       Canonical Scientific IR
                ↓
        Scientific Planner
                ↓
        Multiphysics Graph
                ↓
   Domain / Solver Providers
                ↓
        Coupling Runtime
                ↓
        Scientific Results
                ↓
 Time + Environment + Lifecycle
                ↓
         Updated System State
                ↓
 Validity / V&V / UQ / Evidence
                ↓
  SUPPORTED / REVIEW / REFUSED
```

## 2. What Forge must become

Forge must be able to model a **complete engineered system**, not only an isolated equation or component.

Examples include:

- HVAC systems;
- battery packs and thermal management;
- drones and multirotors;
- vehicle subsystems and eventually full vehicles;
- thermo-structural and fluid-structure systems;
- chemical/reactor systems;
- systems whose material properties and performance change over time.

The long-term differentiator is the combination of:

1. mathematics and numerical foundations;
2. multiphysics orchestration;
3. materials and field/mesh semantics;
4. time and multi-timescale execution;
5. environment and exposure;
6. degradation and lifecycle state;
7. solver/data neutrality;
8. scientific trust, evidence, uncertainty and refusal.

## 3. Explicit non-goals

Forge must **not** become an inferior rewrite of mature tools.

Do not build a new CFD, FEM, CAS, battery electrochemistry, chemical kinetics, mesh generator or HPC linear-solver stack merely because Forge needs those capabilities.

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

## 4. First-class scientific pillars

### 4.1 Mathematics

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

### 4.2 Scientific data

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

### 4.3 Materials

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

### 4.4 Time

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

### 4.5 Environment

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

### 4.6 Lifecycle and degradation

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

### 4.7 Fields, geometry and mesh

Generic multiphysics requires canonical support for:

- geometry/regions/boundaries;
- meshes and mesh identity;
- scalar fields;
- vector fields;
- tensor fields;
- coordinate frames;
- interpolation/projection;
- conservative mappings;
- discretization metadata.

Core semantics must remain provider-neutral.

### 4.8 Multiphysics

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

### 4.9 Scientific trust

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

## 5. Multi-timescale execution

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

## 6. Domain-extension rule

A new domain must enter through generic extension contracts.

**Failure condition:** adding a new domain requires sprinkling domain-specific names or branches throughout Scientific Core.

Preferred shape:

```text
DomainPack
├── Models
├── Realizations
├── Solver Providers
├── State Schema
├── Ports
├── Coupling Semantics
├── Applicability
├── Conservation
├── Validation Routes
└── Result Adapters
```

The strongest extensibility test is an external package that can be installed and enabled without modifying Forge Core.

## 7. Provider-integration definition of done

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

## 8. Data policy

Until funding or a specific commercial need:

1. prefer open/public datasets;
2. preserve original license and source metadata;
3. never silently redistribute data whose license does not permit it;
4. separate REFERENCE, EXPERIMENTAL and SYNTHETIC data;
5. keep calibration and validation/holdout roles explicit;
6. do not call public data "certified" unless an appropriate authority actually certifies it;
7. use paid data only when it unlocks a capability not reasonably achievable with open data.

## 9. Roadmap

The roadmap is ordered by dependency, not marketing value.

| Phase | Objective | Exit criterion |
|---|---|---|
| **P0** | Core/CI/assurance stabilization | automatic gates; one coherent assurance path; current evidence is SHA-bound |
| **P1** | Mathematical provider foundation | symbolic/numerical contracts are provider-backed without new authority paths |
| **P2** | Scientific Data Layer | open dataset can be normalized with provenance/license/uncertainty/validity |
| **P3** | Material System | one material identity is consumable across multiple domains with state-dependent properties |
| **P4** | Time Engine | canonical clocks, windows, events, histories and state transitions |
| **P5** | Environment Engine | reusable environment timeline with solar/weather/exposure/body-force inputs |
| **P6** | Lifecycle/Degradation Engine | generic damage/degradation state updates future model state |
| **P7** | Field + Mesh Core | provider-neutral scalar/vector/tensor field and mesh contracts |
| **P8** | FEM/PDE provider stack | verified spatial thermal + structural cases through external providers |
| **P9** | Generic Coupling | arbitrary two-provider coupled simulation with evidence and convergence |
| **P10** | CFD provider | validated flow + heat-transfer cases |
| **P11** | Structural mechanics breadth | static/modal/thermo-structural/fatigue foundations |
| **P12** | Battery electrochemistry | PyBaMM-class electrochemical + thermal + degradation workflow |
| **P13** | HVAC / thermodynamic systems | refrigerant/property/system/CFD coupling |
| **P14** | Chemistry | detailed kinetics/thermo/transport provider |
| **P15** | Multi-timescale Runtime | fast/medium/slow physics evolve one lifecycle state without brute force |
| **P16** | Graph-level UQ/V&V | uncertainty, validation and numerical evidence compose across coupling |
| **P17** | Flagship systems | HVAC, battery pack, drone, vehicle subsystem demonstrate full architecture |
| **P18** | HPC/scale | distributed/remote execution with documented scale and replay |
| **P19** | Commercial data/funding expansion | paid data/providers only where technically justified |

Do not skip prerequisite phases merely to increase the number of domains.

## 10. Flagship systems

Flagships are integration proofs, not demos that bypass the generic architecture.

### HVAC

Target physics:

- refrigeration thermodynamics;
- compressor/fan/electrical behavior;
- heat exchangers;
- CFD airflow;
- solid conduction;
- humidity/condensation where supported;
- controls;
- environment;
- fouling/corrosion/wear over lifecycle.

### Battery pack

Target physics:

- electrochemistry;
- electrical network;
- heat generation and cooling;
- environment;
- calendar/cycle degradation;
- uncertainty and validation.

### Drone

Target physics:

- battery;
- electrical/motor;
- propeller/aerodynamics;
- thermal;
- structural;
- vibration;
- controls;
- environment and aging.

### Vehicle subsystem

Start bounded rather than attempting a whole car immediately.

Good initial scope:

- battery enclosure;
- cooling;
- structure/materials;
- environmental exposure;
- corrosion/fatigue;
- lifecycle state.

## 11. Progress metrics

Do not use repository file count or raw line count as progress.

Track:

- production domains;
- real external providers;
- validated models;
- admitted external datasets;
- coupled domain pairs;
- supported field types;
- largest verified DOF;
- largest verified coupled graph;
- validated applicability regimes;
- lifecycle/degradation models;
- independent oracles/evaluators;
- replayable reference cases;
- known unsupported regimes.

## 12. Session resume protocol

Every new AI/engineering session must:

1. read `CLAUDE.md`;
2. read this file;
3. read `docs/work/ACTIVE_PLAN.md`;
4. read the newest relevant entries in `docs/work/PROGRESS.md`;
5. inspect the actual repository HEAD and current branch/PR before assuming status;
6. continue the **first executable unfinished task** in the active plan unless it is blocked;
7. do not silently redesign the project based on a single new idea;
8. update `ACTIVE_PLAN.md` when the bounded execution plan changes;
9. append factual milestones/failures/test results to `PROGRESS.md`;
10. update this Master Plan only for a genuine strategic decision.

If documents disagree, use this precedence for project direction:

```text
Scientific authority/frozen-contract rules
        ↓
FORGE_MASTER_PLAN.md
        ↓
ACTIVE_PLAN.md
        ↓
PROGRESS.md
        ↓
historical audits / old chat text
```

Repository code and current test/workflow results remain the authority for what is actually implemented.

## 13. Recovery prompt for a lost chat

If a chat/session is lost, the user can simply say:

> Read `CLAUDE.md`, `docs/project/FORGE_MASTER_PLAN.md`, `docs/work/ACTIVE_PLAN.md`, and `docs/work/PROGRESS.md`. Inspect the current Forge branch/PR and continue from the first unfinished executable task. Do not change the project direction unless the repository evidence requires it.

The agent should not require the previous chat transcript to resume technical work.

## 14. Change-control rule

Before adding a large feature, ask:

1. Which pillar does this strengthen?
2. Does a mature provider already solve the numerical problem?
3. Does it require a new generic contract, or only a DomainPack/provider?
4. What is the validity envelope?
5. What evidence proves it?
6. How does it interact with time/environment/lifecycle?
7. How is uncertainty represented?
8. Can it replay?
9. Does it preserve fail-closed behavior?
10. Does it make the flagship systems more complete?

If those questions cannot be answered, the feature is not ready for Core.
