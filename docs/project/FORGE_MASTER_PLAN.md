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
12. a global 3D engineering visualization runtime that can show assemblies, dimensions, cutaways, motion and evidence-bound scientific overlays;
13. high-throughput multi-fidelity design discovery without confusing optimization with validation.

### 2.1 Universal architecture rule

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

### 4.7 Spatial / Geometry Foundation, fields and mesh

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

## 4.13 Mechanism-aware and blind scientific discovery

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

### 4.13.1 High-throughput multi-fidelity discovery

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

### 4.13.2 Blind historical rediscovery and leakage control

Historical rediscovery is a benchmark, not proof of novel science. To make it
meaningful, Forge should support a frozen knowledge cutoff: only information
available before a chosen historical date is admitted during discovery, while
later evidence is hidden for scoring.

Because foundation models may already know famous discoveries, benchmark mode
must reduce memorization leakage through combinations of:

- anonymized entity identifiers;
- hidden domain labels where practical;
- transformed variables/coordinates;
- withheld future evidence;
- exact data/provenance cutoffs;
- synthetic universes generated after model training and unknown to the model.

A strong benchmark asks whether the system can recover a predictive mechanism
or useful candidate from relationships and evidence, not whether it can recall
a famous name.

### 4.13.3 FORGE Genesis benchmark

Create a general benchmark family spanning:

- blinded known-law rediscovery;
- transformed known physics;
- synthetic hidden-law universes;
- competing hypotheses requiring discriminating experiments;
- materials/design discovery;
- safe biomedical retrospective-discovery tasks;
- safe energy/fusion engineering tasks;
- adversarial/noisy/insufficient-evidence cases where refusal is correct.

Each challenge binds:

```text
knowledge cutoff
allowed primitives
allowed tools/providers
compute budget
hidden target/future evidence
scoring protocol
```

Score at minimum:

- holdout prediction;
- law/mechanism recovery where defined;
- candidate rank and search efficiency;
- false-discovery rate;
- uncertainty calibration;
- experiment efficiency;
- compute used by fidelity class;
- correct refusal when no stable conclusion is supportable.

Forge earns credit for saying **INSUFFICIENT EVIDENCE** when that is the
scientifically correct result.

### 4.13.4 Scientific Red Team / Design-Killer search

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

### 4.13.5 Credibility graph and next-best experiment

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

### 4.13.6 Frontier-science verticals

Discovery remains generic, but selected verticals should exercise it.

**Fusion energy engineering** is a strategic frontier vertical because it
forces coupled plasma/field, electromagnetic, thermal, structural, materials,
cooling, controls, lifecycle and reliability reasoning. Initial work should
focus on non-weapon energy-system/component problems, design-killer search,
materials/lifetime uncertainty and whole-system credibility rather than
claiming a new plasma solver.

**Biomedical / medical-device engineering** is another strategic vertical.
Initial work should focus on bounded in-silico engineering questions such as
biomechanics, implants, hemodynamics, bioheat and retrospective therapeutic
hypothesis ranking from frozen historical evidence. Simulation or discovery
does not become a patient-specific diagnosis or treatment claim without the
required clinical evidence and validation path.

## 4.14 Global 3D engineering visualization runtime## 4.14 Global 3D engineering visualization runtime

Forge should have one global interactive engineering viewer for complete
products and their internal subsystems. The viewer is a presentation/runtime
layer over authoritative Forge product, geometry, simulation and evidence
records; it is not a new scientific authority.

Target capabilities include:

- whole-product and hierarchical subsystem 3D views;
- assembly tree with exact part/component identities;
- authoritative dimensions, tolerances, fits, labels and engineering metadata;
- transparent / X-ray modes;
- section and cutaway views;
- exploded assembly views;
- hide/show/isolate and progressive level-of-detail loading;
- motion playback for mechanisms, multibody trajectories and flight/vehicle states;
- time-synchronized telemetry and simulation values;
- thermal, electrical, structural, flow, vibration and lifecycle overlays;
- force, torque, velocity, heat-flow, current or other vectors where supported;
- interactive inspection of limits, margins, warnings and failure-risk indicators;
- large-system scene streaming so a vehicle, drone or machine does not require every detailed fastener/mesh to be loaded at once.

A motor should eventually be viewable in normal, transparent, cutaway,
exploded, motion, electrical, thermal and risk/limits modes. A winding
hotspot may be highlighted only when the thermal/electrical model,
component/material limit and applicability/evidence path support that
interpretation. The viewer must never infer burnout, failure or safe state
from colour or geometry alone.

Preferred architecture:

```text
Forge Product / Assembly / Simulation Records
                    ↓
          Canonical Forge Scene IR
                    ↓
          VisualizationProvider
                    ↓
        Three.js (initial web provider)
                    ↓
      Interactive Engineering Viewer
```

Three.js is an initial rendering provider, not a Core dependency. Future
Babylon.js, ParaView/VTK, WebGPU, Unity or other visualization providers may
consume the same scene contract when justified.

Detailed direction: `docs/architecture/visualization_runtime.md`.
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

## 8.1 Owner strategy update — 2026-10-09: Big Rocks First

The owner has explicitly changed the execution strategy from small-fix-first to
**Big Rocks First**.

Forge should build the largest reusable capability foundations and provider
breadth first, using targeted tests while building, then perform a deliberate
integration/hardening/qualification campaign over the resulting architecture.

This does **not** weaken scientific authority. A small issue interrupts a Big
Rock only when it:

1. can make scientific numbers materially wrong;
2. can create a false `SUPPORTED`/validated result;
3. corrupts identity, provenance, replay or evidence;
4. blocks the Big Rock itself.

Other cleanup, product polish, lint, packaging and non-authority debt goes to a
`DEFERRED_HARDENING` ledger.

The in-flight Trust Repair/certification work remains isolated and must finish
against its frozen source. Parallel expansion work must not mutate that source,
certificate or assurance artifacts.

### Big Rock A — General Spatial / Geometry Foundation

Build provider-neutral geometry/body/part/assembly/region/boundary/interface,
frames/transforms, parameterized variants, material/boundary bindings,
geometry-to-mesh bindings and provider-entity receipts.

First provider: generalized Gmsh/OpenCASCADE rather than one-off geometry paths.

### Big Rock B — Assembly / product topology

Build the reusable hierarchy and interfaces required by complete engineered
systems:

```text
System → Subsystem → Assembly → Component → Part / Body
```

Composition owns placement, interfaces, replaceable components and state
ownership without leaking drone/car/motor semantics into Core.

### Big Rock C — Provider breadth before polish

Add the broad solver/provider boundaries early. Integration means canonical
contracts, probe/identity, input translation, output parsing, provenance,
failure/refusal semantics and targeted tests. Real execution should be used
where the environment provides it; unavailable executables do not block
independent adapter work and must remain explicitly unqualified.

Priority provider families:

- geometry/mesh: Gmsh/OpenCASCADE, meshio, OpenVSP;
- CFD: OpenFOAM, SU2;
- PDE/FEM/structural: FEniCSx/PETSc, CalculiX, Code_Aster, Elmer;
- explicit dynamics/crash: OpenRadioss;
- multibody: Project Chrono;
- coupling: preCICE;
- battery: PyBaMM/PyBOP;
- electrical: ngspice;
- chemistry/thermo: Cantera, CoolProp;
- system thermal/dynamics: TESPy, OpenModelica/FMI-FMU, EnergyPlus where useful;
- additional domain providers only when they fit the same canonical boundary.

Provider maturity remains explicit:

`AVAILABLE → INTEGRATED → QUALIFIED → COUPLING_CERTIFIED → VALIDATED FLAGSHIP`

Availability or adapter existence alone never implies qualification.

### Big Rock D — Scientific Twin

Create a versioned executable representation of a concrete candidate system
that binds/references geometry, composition, materials, models, state,
environment/scenario, evidence, uncertainty and lineage without manufacturing
new scientific authority.

### Big Rock E — Blind Discovery Runtime

Build the generic hypothesis/candidate search runtime described in §4.13:

- Hypothesis/Experiment IR;
- high-throughput multi-fidelity evaluation;
- falsification;
- Design Memory;
- next-best-experiment selection;
- recursive component/system discovery;
- blind historical rediscovery;
- synthetic-universe benchmarks.

Do not create disease-, fusion-, drone- or vehicle-answer templates and call
them discovery.

### Big Rock F — Scientific Red Team / Credibility Graph

Build autonomous counterexample/design-killer search, trust envelopes and
system-level credibility/evidence-gap graphs over Scientific Twins.

### Big Rock G — Cross-domain vertical slices

Exercise the generic architecture with real compositions rather than new Core
branches:

- Drone;
- Vehicle/Car;
- Electric Motor;
- HVAC;
- Battery Pack;
- Fusion energy engineering;
- Biomedical / medical-device engineering.

### Hardening after the large structure exists

Do not run Full Local Assurance after every Big Rock. During expansion, run
bounded targeted/contract tests and checkpoint coherent work.

After the achievable Big Rocks reach an architecture freeze:

```text
integration inventory
    → deferred correctness/hardening
    → supported-environment tests
    → provider qualification
    → scientific hostile review
    → scope classification
    → one final recertification boundary where required
```

Known B1/B2/B4/B5/UQ issues remain important. Fix immediately when they can
invalidate discovery/trust results; otherwise integrate them into the final
hardening campaign rather than serializing the whole program behind every
small defect.

### Cloud / local execution split

Cloud development may build contracts, adapters, geometry, twins, discovery,
safe vertical compositions and targeted tests, checkpointing to feature
branches. Heavy provider qualification and final assurance remain bound to
declared supported local/provider environments.

## 9. Roadmap## 9. Roadmap

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
| **P25** | Global 3D Engineering Viewer + Scene Runtime | whole products and subsystems render from a canonical scene contract with exact dimensions, hierarchy, transparency/cutaways, exploded views, progressive loading and evidence-bound simulation overlays |
| **P26** | Assembly + standard-component synthesis | buildable assembly graph, catalog component selection and custom parts with exact identities/provenance |
| **P27** | Motion systems + multibody dynamics | kinematics/dynamics, mechanisms, trajectories, DOFs, mass/inertia and dynamic loads are modeled for assembled systems and can drive viewer playback |
| **P28** | Compliance + suspension + joint/contact physics | springs, dampers, bushings, flexures, friction, backlash, contact, vibration and suspension behaviour are explicit |
| **P29** | Electromechanical actuation + controls + wiring | actuators, transmissions, sensors, control loops, electrical behaviour and harness/routing constraints compose with mechanics |
| **P30** | Capability-based solver planning | realization, fidelity, primary provider and independent verification routes are selected from declared capability/applicability |
| **P31** | Intervention + counterfactual runtime | controlled changes and replayable counterfactuals support root-cause and design reasoning without granting causal authority |
| **P32** | High-throughput multi-fidelity design discovery | large campaigns use feasibility filters, parallelism, caching, early stopping, fidelity escalation, trusted surrogates and Pareto/MDO search |
| **P33** | Reliability + lifecycle + manufacturability + cost | degradation, fatigue/wear, manufacturing variation/tolerances, serviceability and cost status constrain candidates |
| **P34** | Hypotheses + experimental learning | competing falsifiable hypotheses, experiment design, active learning and negative results are first-class |
| **P35** | Closed-loop experimental validation | calibration and independent/holdout validation remain separate; physical measurements update evidence/model discrepancy |
| **P36** | Validated design discovery | requirements -> design -> 3D/assembly -> dynamics/multiphysics -> UQ/reliability -> experiment, with improvement claims limited to admitted evidence |
| **P37** | Blind Scientific Discovery Runtime | generic hypotheses/experiments, frozen knowledge universes, multi-fidelity falsification and Design Memory work without answer templates |
| **P38** | FORGE Genesis benchmark | blinded historical rediscovery, transformed physics, synthetic universes and insufficient-evidence cases measure genuine discovery rather than memorization |
| **P39** | Scientific Red Team + Credibility Graph | candidate/claim attacks find counterexamples, design killers, trust envelopes and dominant evidence gaps across coupled systems |
| **P40** | Frontier discovery verticals | Fusion-energy and biomedical/medical-device slices exercise the generic runtime with bounded claims, independent evidence and no domain-specific scientific-authority shortcuts |

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

### Fusion energy engineering

Target use is a safe frontier engineering vertical over the generic platform,
not a weapon-design benchmark and not a replacement plasma solver.

Initial targets:

- coupled thermal/structural/electromagnetic/materials system reasoning;
- geometry/material/lifecycle candidate search;
- cooling and power-conversion interfaces;
- reliability/availability/maintainability/inspectability reasoning;
- design-killer search and trust-envelope construction;
- whole-system credibility/evidence-gap graphs;
- next-best experiment selection where evidence is expensive.

### Biomedical / medical-device engineering

Initial targets are bounded engineering/scientific questions:

- biomechanics and implants;
- hemodynamics/airflow;
- bioheat and tissue thermal models;
- musculoskeletal/mechanical-system models;
- retrospective, blinded therapeutic-hypothesis ranking from historically
  frozen evidence as a Discovery benchmark.

Forge must keep simulation/hypothesis support separate from clinical diagnosis,
prescription or patient-specific treatment authority.

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
