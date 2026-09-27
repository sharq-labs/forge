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
8. scientific trust, evidence, uncertainty and refusal;
9. mechanism-aware reasoning grounded in declared laws, mechanisms, applicability and evidence;
10. engineering design synthesis from requirements through geometry, assemblies and manufacturing constraints;
11. motion-system reasoning: kinematics, multibody dynamics, compliant elements, contact, actuation and controls;
12. high-throughput multi-fidelity design discovery without confusing optimization with validation.

## 3. Explicit non-goals

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

## 4.10 Engineering design synthesis and assembly

Forge's long-term target is not only to analyse a supplied geometry. It must
eventually turn engineering requirements into buildable candidate products.

Target flow:

```text
requirements
  -> system architecture / product template
  -> design space / topology
  -> parametric geometry / CAD
  -> assembly synthesis
  -> standard components + custom parts
  -> joints / interfaces / fits / routing
  -> motion / electrical / thermal / structural model graph
  -> solver planning
  -> multi-fidelity design campaign
  -> reliability / lifecycle / manufacturing / cost
  -> experiment / evidence
```

A mesh is not a product design, and a set of solids is not an assembly.

Assembly engineering must be first-class, including bolts, screws, nuts,
washers, pins, shafts, keys/splines, bearings, bushings, gears, belts, chains,
couplings, springs, dampers, seals, guides, welds, bonded joints, press-fits,
motors, gearboxes, actuators, sensors, encoders, connectors, cable/hose/pipe
routing, lubrication, mechanical stops, tolerances, assembly sequence, tool
access and serviceability.

Prefer standard/catalog components when appropriate. Missing ratings,
tolerances, life, cost, availability or operating limits remain UNKNOWN.

Detailed direction: `docs/architecture/design_synthesis.md`.

## 4.11 Motion systems, mechanisms and multibody dynamics

Forge must represent how an assembled machine actually moves, not only whether
its individual parts survive static loads.

Required future capabilities include:

- forward and inverse kinematics;
- generalized coordinates, degrees of freedom and joint limits;
- forward and inverse dynamics;
- mass/inertia and gravity;
- rigid and flexible links where supported;
- revolute, prismatic, spherical, universal and compound joints;
- four-bar and other linkages, cams, slider-cranks and rack/pinion mechanisms;
- gears, belts, chains, cable/tendon transmissions and lead/ball screws;
- springs, dampers, bushings, flexures and other compliant elements;
- friction, stiction, backlash, hysteresis and joint compliance;
- contact, impact and grasp/slip behaviour where supported;
- vibration and suspension behaviour;
- actuator sizing from torque/force/speed/duty requirements;
- motion targets, trajectories and control-performance constraints.

A robot arm, suspension, gripper or machine mechanism must therefore be
simulated as a dynamic system rather than a collection of ideal hinges.

Detailed direction: `docs/architecture/motion_systems.md`.

## 4.12 Electromechanical actuation, controls and power/wiring

Mechanical motion must be coupled to how it is powered and controlled.

Forge should eventually support model composition across:

- electric motors, solenoids and linear actuators;
- hydraulic and pneumatic actuators where applicable;
- gearboxes, transmissions and tendon/cable drives;
- motor electrical behaviour, current, voltage, back-EMF, losses and heating;
- drives / power electronics where modeled;
- sensors and encoders;
- feedback controllers;
- power supply / battery constraints;
- electrical conductors, wire gauge/type, insulation and temperature limits;
- current capacity, voltage drop and resistive heating;
- connectors, fuses/protection and harness identities;
- bend radius, routing, strain relief and serviceability;
- EMI/EMC constraints only where supported by an admitted model/provider.

A motor is not an ideal torque source, and a cable is not only a CAD curve.
Unsupported electrical or control behaviour stays explicit rather than being
silently idealized.

## 4.13 Mechanism-aware discovery

Forge's discovery direction is mechanism-aware rather than black-box search.

Dependency, mechanism and causal claim remain distinct. Sensitivity, solver
agreement, correlation, optimization score or an LLM proposal do not become
causal/scientific evidence.

Discovery may propose competing mechanisms, interventions, counterfactuals,
scaling relationships or unexplained residuals, but stronger claims require
the applicable evidence path and, where necessary, discriminating experiments.

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

The roadmap is ordered by dependency and the project's current strategic priority.
**Time, environment and lifecycle are early Core concerns, not late product features.**
Mathematics/data/material capabilities are strengthened alongside these phases whenever
the active slice requires them.

| Phase | Objective | Exit criterion |
|---|---|---|
| **P0** | Core/CI/assurance stabilization | automatic gates; one coherent assurance path; current evidence is SHA-bound |
| **P1** | Time Engine | canonical clocks, windows, events, usage/exposure/cycle histories and state transitions |
| **P2** | Environment Engine | reusable environment timeline with solar/weather/exposure/body-force inputs |
| **P3** | Lifecycle/Degradation Engine | generic degradation state changes future model/material/system state |
| **P4** | Scientific Data + Materials | open datasets are normalized with provenance/license/uncertainty and materials are state-dependent across domains |
| **P5** | Mathematical provider foundation | symbolic/numerical/statistical capabilities are provider-backed without creating new authority paths |
| **P6** | Field + Mesh Core | provider-neutral scalar/vector/tensor field, region, boundary and mesh contracts |
| **P7** | FEM/PDE provider stack | verified spatial thermal + structural cases through external providers |
| **P8** | Generic Multiphysics Coupling | arbitrary two-provider coupled simulation with evidence, mapping and convergence |
| **P9** | CFD provider | validated flow + heat-transfer cases |
| **P10** | Structural mechanics breadth | static/modal/thermo-structural/fatigue foundations |
| **P11** | Battery electrochemistry | PyBaMM-class electrochemical + thermal + degradation workflow |
| **P12** | HVAC / thermodynamic systems | refrigerant/property/system/CFD coupling |
| **P13** | Chemistry | detailed kinetics/thermo/transport provider |
| **P14** | Multi-timescale Runtime | fast/medium/slow physics evolve one lifecycle state without brute force |
| **P15** | Graph-level UQ/V&V | uncertainty, validation and numerical evidence compose across coupling |
| **P16** | Flagship systems | HVAC, battery pack, drone and vehicle subsystem demonstrate the architecture |
| **P17** | HPC/scale | distributed/remote execution with documented scale and replay |
| **P18** | Commercial data/funding expansion | paid data/providers only where technically justified |
| **P19** | Architecture boundary cleanup | Core, CapabilityPack/DomainPack, Provider and SystemPack/ProductTemplate responsibilities are explicit and product-specific logic does not leak into frozen Core |
| **P20** | OSS provider capability matrix | every integrated provider has capability/applicability/maturity coverage; availability is not confused with full solver capability |
| **P21** | Mechanism semantics | laws/mechanisms/state transitions are provider-neutral and dependency is not promoted to causal proof |
| **P22** | Advanced UQ + model discrepancy | uncertainty, sensitivity and identifiability compose across systems using only admitted information |
| **P23** | Engineering requirements + design space | objectives, constraints, operating envelope, controllable variables and topology choices are identity-bound |
| **P24** | Parametric geometry / CAD / topology | candidate geometry/topology is reproducible and feeds analysis without losing design identity |
| **P25** | Assembly + standard-component synthesis | buildable assembly graph, catalog component selection and custom parts with exact identities/provenance |
| **P26** | Motion systems + multibody dynamics | kinematics/dynamics, mechanisms, trajectories, DOFs, mass/inertia and dynamic loads are modeled for assembled systems |
| **P27** | Compliance + suspension + joint/contact physics | springs, dampers, bushings, flexures, friction, backlash, contact, vibration and suspension behaviour are explicit |
| **P28** | Electromechanical actuation + controls + wiring | actuators, transmissions, sensors, control loops, electrical behaviour and harness/routing constraints compose with mechanics |
| **P29** | Capability-based solver planning | realization, fidelity, primary provider and independent verification routes are selected from declared capability/applicability |
| **P30** | Intervention + counterfactual runtime | controlled changes and replayable counterfactuals support root-cause and design reasoning without granting causal authority |
| **P31** | High-throughput multi-fidelity design discovery | large campaigns use feasibility filters, parallelism, caching, early stopping, fidelity escalation, trusted surrogates and Pareto/MDO search |
| **P32** | Reliability + lifecycle + manufacturability + cost | degradation, fatigue/wear, manufacturing variation/tolerances, serviceability and cost status constrain candidates |
| **P33** | Hypotheses + experimental learning | competing falsifiable hypotheses, experiment design, active learning and negative results are first-class |
| **P34** | Closed-loop experimental validation | calibration and independent/holdout validation remain separate; physical measurements update evidence/model discrepancy |
| **P35** | Validated design discovery | requirements -> design -> assembly -> dynamics/multiphysics -> UQ/reliability -> experiment, with improvement claims limited to admitted evidence |

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
- known unsupported regimes;
- supported mechanism/joint types;
- supported compliant/contact models;
- catalog/component families with provenance-bound ratings;
- maximum verified multibody DOF and motion-system complexity;
- validated actuator/control/wiring model combinations;
- design-campaign throughput by fidelity class;
- buildable candidate designs with closed-loop experimental evidence.

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
