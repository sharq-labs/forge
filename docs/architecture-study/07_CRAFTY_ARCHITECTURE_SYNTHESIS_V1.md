# Crafty Architecture Synthesis V1

**Status:** Architecture-study synthesis; recommended baseline before implementation  
**Date:** 2026-09-02  
**Inputs:** MOOSE, PETSc, OpenFOAM, preCICE, FEniCSx, MFEM, OpenMDAO, Modelica/OpenModelica studies  
**Purpose:** Convert open-source lessons into a Crafty-native architecture without copying implementation code.

---

# 1. Executive conclusion

The research **does not invalidate the current Crafty direction**. It strengthens it and makes several boundaries more precise.

The most important conclusion is:

> **Crafty should not become one giant solver, nor a thin wrapper around external solvers. It should become a scientific composition/runtime platform with clean layers from scientific meaning down to numerical execution.**

The immediate `MODEL0-R` milestone remains the correct next implementation step.

Do **not** jump directly into FEM, CFD, materials databases, radar, tire, HVAC, or broad domain expansion.

---

# 2. The architecture that emerged from all studies

```text
User / AI Agent
      ↓
Scientific Intent
      ↓
Quantity of Interest / Objectives
      ↓
Scientific Capability Planner
      ↓
System Builder
      ↓
Scientific System Graph
      ↓
Model Selection + Validity Filtering
      ↓
Computational Realization Selection
      ↓
Physics Graph
      ↓
Execution-Plan Compiler
      ↓
┌──────────────────────────────────────────────┐
│ Execution Substrate                          │
│                                              │
│ Fields / Topology / Geometry                 │
│ Equation / Residual IR                       │
│ Discretization IR                            │
│ Numerical Capability Stack                   │
│ State / Events                               │
│ Coupling / Mapping / Synchronization         │
│ Native or Optional Solver Providers          │
└──────────────────────────────────────────────┘
      ↓
Scientific Results
      ↓
Numerical Diagnostics
+ Coupling Diagnostics
+ Validity
+ UQ
+ Provenance
      ↓
SRIA / Evidence Admission
      ↓
Design / Optimization / Research Decision
      ↓
Scientific Memory
```

This should be treated as the current target architecture, subject to milestone-by-milestone falsification.

---

# 3. The central separation

The strongest repeated conclusion across the studies is that Crafty must preserve multiple distinct identities:

```text
Scientific Capability
!=
Scientific Model
!=
Computational Realization
!=
Equation/Residual Representation
!=
Discretization
!=
Solver Capability
!=
Concrete Solver
!=
Execution Policy
```

These layers may reference one another, but they must not collapse into one object.

## Example

```text
Capability:
thermal:heat_conduction

Scientific Model:
Fourier heat conduction

Realization:
transient 3D numerical conduction

Equation IR:
energy-balance PDE residual

Discretization:
finite element, P2

Solver requirements:
nonlinear solve + sparse linear solve

Concrete solver configuration:
chosen native solver stack

Execution policy:
transient stepping / tolerances / resources
```

Changing the linear solver should not silently create a new scientific model.

---

# 4. What MOOSE contributed

Primary lesson:

> **Core + explicit extensible physics modules.**

Adopt conceptually:

- registration separate from object construction/execution
- typed contracts before construction
- domain modules depend on core, never reverse
- first-class materials and boundary/interface objects
- problem physics separate from execution strategy
- strong per-module Verification & Validation discipline

Crafty improvement:

MOOSE generally assumes developers have already decided what physics to instantiate. Crafty aims to add scientific capability planning and validity-aware model/realization selection above this level.

---

# 5. What PETSc contributed

Primary lesson:

> **Numerical solvers should form a reusable hierarchy of capabilities.**

Conceptual hierarchy:

```text
Vector / LinearOperator
↓
Preconditioner
↓
Linear Solver
↓
Nonlinear Solver
↓
Time / ODE / DAE Solver
```

Adopt conceptually:

- higher numerical capabilities reuse lower capabilities
- operator separate from solver algorithm
- preconditioning first-class
- residual/Jacobian interfaces
- convergence reason/diagnostics explicit
- topology/discretization/data-layout separation
- parallelism below domain physics

Crafty rule:

> A `ModelRealizationDefinition` should request solver **capabilities**, not a concrete solver brand/class.

---

# 6. What OpenFOAM contributed

Primary lesson:

> **A mature domain is a complete ecosystem, not a set of equations.**

A strong domain needs:

- fields
- topology/geometry
- boundary conditions
- physical model families
- source/constraint models
- material/thermophysical behavior
- discretization schemes
- solver modules
- steady/transient regimes
- validation/benchmarks
- diagnostics/postprocessing
- performance and extension APIs

Important architectural lessons:

- Fields are first-class and carry physical dimensions/context.
- Modern solver modules are more reusable than one executable per scenario.
- Runtime-selectable model families scale better than hard-coded combinations.
- Different regions may use different solver modules.
- Derived mesh/model data needs explicit invalidation semantics.

Crafty improvement:

Do not make finite-volume concepts universal. OpenFOAM can later be an optional high-fidelity CFD provider behind Crafty contracts.

---

# 7. What preCICE contributed

Primary lesson:

> **Multiphysics coupling is its own computational/scientific discipline.**

A coupling edge may require:

- field/scalar semantics
- unit/frame conversion
- mesh mapping
- interpolation
- conservation rules
- time synchronization
- explicit/implicit policy
- relaxation/acceleration
- convergence
- checkpoint/rollback
- diagnostics/error

Critical separation:

```text
PhysicsGraph
!=
CouplingExecutionPlan
```

The same physical dependency graph can be executed using different coupling algorithms.

Additional important distinction:

```text
Participant numerical convergence
!=
Coupling convergence
!=
Scientific validity
```

---

# 8. What FEniCSx + MFEM contributed

Primary lesson:

> **Scientific fields/equations must be distinct from their numerical representation.**

Important separations:

```text
ScientificFieldDefinition
!=
DiscreteFieldRepresentation

Equation / Residual IR
!=
Discretization IR

LinearOperator
!=
SparseMatrix only
```

Future numerical infrastructure must allow:

- scalar/vector/tensor fields
- H1 / H(curl) / H(div) / L2-like discrete-space semantics where required
- assembled and matrix-free operators
- different basis/order choices
- CPU/GPU/backend choices below the scientific identity

This is essential for future electromagnetics and serious continuum physics.

---

# 9. What OpenMDAO + Modelica contributed

Primary lesson:

> **Crafty needs both causal workflow composition and acausal physical composition.**

OpenMDAO lesson:

- component/dataflow graph
- coupled cycles
- nested solver blocks
- design variables/objectives/constraints above simulation topology
- derivative propagation

Modelica lesson:

- physical connectors are more than named inputs/outputs
- acausal equations avoid arbitrary early direction choices
- reusable components
- initialization/events/state are first-class
- hierarchical system models can be compiled/flattened into executable equations

Crafty implication:

SYSTEM0 must eventually support:

```text
Causal ports
+
Physical/acausal connectors
+
Constraint interfaces
```

without hard-coding electrical/mechanical/thermal connector types in universal core.

---

# 10. Proposed Crafty layer boundaries

## Layer A — Scientific Meaning

Owns:

- quantities / units
- ScientificProblem
- ScientificCapability
- ScientificModelDefinition
- validity
- assumptions
- uncertainty semantics
- provenance identity

No concrete numerical backend knowledge.

## Layer B — Computational Realization

Owns:

- ModelRealizationDefinition
- formulation class
- fidelity
- required scientific capabilities
- required solver capabilities
- realization-specific assumptions
- implementation identity

Still not the concrete runtime solve itself.

## Layer C — System Composition

Owns:

- components
- ports/interfaces
- environment
- causal/acausal connections
- system constraints

Produces a bounded system/physics graph.

## Layer D — Representation / Discretization

Owns:

- fields
- topology/geometry
- equation/residual IR
- discrete field spaces
- discretization plan
- operator construction

## Layer E — Numerical Runtime

Owns:

- linear/nonlinear/time solvers
- preconditioners
- convergence
- numerical diagnostics
- backend/hardware policy

## Layer F — Coupling Runtime

Owns:

- participants
- transfers/mappings
- synchronization
- coupling convergence
- relaxation/acceleration
- checkpoint/rollback

## Layer G — Simulation Runtime

Owns:

- compile/freeze execution plan
- scheduling
- nested coupled blocks
- state/events
- run lifecycle
- deterministic run identity

## Layer H — Scientific Governance

Owns:

- model adequacy
- UQ
- SRIA assurance/evidence
- certification/admission semantics

## Layer I — Discovery / Decision

Owns:

- design variables/objectives/constraints
- optimization
- research decisions
- scientific memory

---

# 11. Registries should be explicit, not a universal plugin bucket

Avoid:

```text
PluginRegistry<anything>
```

Prefer semantically distinct registries where needed:

```text
ScientificCapabilityRegistry
ModelRegistry                 (already exists)
RealizationRegistry
SolverRegistry                (already exists)
MaterialPropertyProviderRegistry   future
ComponentProviderRegistry          future
DiscretizationProviderRegistry     future
CouplingProviderRegistry           future
```

Do not create all these now. The architectural point is to keep their semantics separate.

---

# 12. Recommended dependency direction

```text
Scientific primitives / units / provenance
              ↑
Scientific IR + Models + Capabilities
              ↑
Computational Realizations
              ↑
System / Field / Equation representations
              ↑
Numerical + Coupling contracts
              ↑
Simulation Runtime
              ↑
Product API / MCP / UI / LLM adapters
```

Domain Packs depend inward on stable contracts.

Universal core must never import named domain packs.

LLM adapters remain outside scientific truth/execution boundaries.

---

# 13. Refined milestone sequence

The studies suggest refining the earlier roadmap to:

```text
MODEL0-R
Scientific Capability + Model/Realization separation

↓

CAP0
Capability registry/dependencies and resolvable capability semantics
(no autonomous planner yet if premature)

↓

MAT0
Material/Substance/State/Property model foundation

↓

FIELD0
Scientific fields, units, frames, support semantics

↓

SYSTEM0
Components, typed ports/interfaces, causal/acausal connections

↓

TOPO0
Universal topology/geometry foundation
(discretization-neutral)

↓

EQIR0
Equation/Residual IR foundation
(algebraic/ODE/DAE/PDE branch boundaries)

↓

DISC0
Discretization IR + discrete field-space contracts

↓

NUM0
Native numerical capability hierarchy

↓

STATE0
State/history/events/checkpoint foundation

↓

COUPLE0
Mappings, synchronization, explicit/implicit coupling

↓

SIM0
Compile/freeze System/Physics Graph → ExecutionPlan

↓

UQ0
Cross-realization / coupled-system uncertainty propagation

↓

DISCOVERY0
Design/optimization/research decision over simulation runtime

↓

OPENFOAM0
Optional high-fidelity CFD provider

↓

Productization
API + MCP + UI

↓

Vertical systems
HVAC / Motor / Tire / Battery / Radar later
```

Names/order are not yet frozen. Each milestone must still be preregistered and justified against the current codebase before implementation.

---

# 14. Why MODEL0-R should still be first

Every later layer depends on answering:

> What scientific model is this, and which computational implementation is being used to realize it?

Without model/realization separation:

- solver identity leaks into physics identity
- fidelity becomes ambiguous
- validation evidence cannot be attributed cleanly
- alternative native/OpenFOAM realizations become difficult to compare
- capability planning becomes string routing instead of scientific reasoning

Therefore `MODEL0-R` remains the correct first change.

---

# 15. MODEL0-R should remain deliberately small

Do **not** add these findings directly into MODEL0-R implementation:

- Field classes
- Mesh/topology
- Equation IR
- SystemGraph
- physical connectors
- coupling scheme
- checkpoint/state
- numerical solver hierarchy
- material property providers

Only ensure MODEL0-R contracts do not prevent those future architectures.

Immediate goal remains:

```text
ScientificCapability
↓
ScientificModelDefinition
↓
ModelRealizationDefinition
↓
SolverCapability
↓
ScientificSolver
```

---

# 16. Recommended additions/clarifications to MODEL0-R specification

Based on the studies, the existing prompt should add these constraints:

### A. Realization requests capabilities, not solver names

`ModelRealizationDefinition` should declare required `SolverCapability` values, never a concrete solver class/name as its core requirement.

### B. Realization formulation must remain broad

Support classification capable of future:

```text
ALGEBRAIC
ODE
DAE
PDE
DISCRETE
SURROGATE
```

without assuming every realization returns scalar outputs or assembled matrices.

### C. Do not put mesh/field/discretization into realization yet

Future representations will reference realizations through separate contracts.

### D. ScientificCapability registration is not proof of availability

The existence of a capability identifier does not prove there is a valid executable realization for the current context.

### E. Realization provenance/versioning is important

Two different implementations of the same scientific model must remain distinguishable and attributable.

### F. No unrestricted `metadata` escape hatch

Future concepts should become explicit contracts rather than anonymous dictionaries.

---

# 17. Candidate future frozen invariants

The studies generated many candidate rules. The strongest ones worth likely freezing after review are:

1. **Scientific Model != Computational Realization != Solver.**
2. **ScientificCapability != SolverCapability.**
3. **PhysicsGraph != ExecutionPlan.**
4. **Scientific Field != Discrete Field Representation.**
5. **Equation IR != Discretization IR.**
6. **Topology/Geometry != discretization-specific mesh view.**
7. **Internal numerical convergence != coupling convergence != scientific validity.**
8. **Realizations request capabilities, not concrete solver brands.**
9. **Domain modules never orchestrate the global simulation graph themselves.**
10. **System topology != optimization study.**
11. **Crafty supports causal and acausal physical composition.**
12. **Material properties are state/model-dependent scientific claims, not timeless constants.**
13. **Coupling transfers/mappings have diagnostics/provenance and potentially uncertainty.**
14. **State checkpoint/restore is a capability required for some implicit transient coupling.**
15. **A universal numerical layer must allow assembled and matrix-free/operator execution.**
16. **Hardware/backend choices are execution properties, not scientific model identity.**

These should be reviewed/frozen via an ADR process rather than silently encoded.

---

# 18. Domain-engine standard after research

A Crafty domain should eventually contain more than models.

Candidate standard:

```text
Domain Pack
├── Capability declarations
├── Scientific theory / assumptions
├── Scientific models
├── Computational realizations
├── Constitutive/material requirements
├── Field/port/interface definitions
├── Boundary/interface models
├── Verification cases
├── Validation cases
├── Benchmarks
├── Known failure / validity regimes
├── Documentation/examples
└── Maturity record
```

This is the route toward OpenFOAM-class depth without building independent infrastructures for every domain.

---

# 19. Recommended first strong native domain

Do not choose the most impressive domain first.

A strong first proving domain remains **Thermal / Heat Conduction** because it exercises:

- fields
- material properties
- boundary conditions
- steady/transient execution
- PDE representation
- discretization
- convergence
- validation

while remaining scientifically manageable.

Then combine with an existing electrical capability to prove cross-domain electro-thermal execution before attempting more difficult systems.

OpenFOAM can later provide high-fidelity fluid capability without defining Crafty's universal architecture.

---

# 20. Vertical-slice strategy after the substrate exists

Recommended progression:

## Slice 1 — Electro-Thermal

Proves:

```text
Electrical ↔ Thermal ↔ Material properties
```

## Slice 2 — HVAC

Proves:

```text
Thermal + Fluid + Electrical + Controls + Optimization
```

and gives a commercially understandable demo.

## Slice 3 — Motor / Energy System

Proves:

```text
Electrical + EM + Mechanical + Thermal + Materials
```

## Slice 4 — Tire later

Proves:

```text
Material history + Contact + Thermal + Wear + Fatigue + Degradation
```

## Slice 5 — Radar later

Proves radically different field/wave/signal/probabilistic domains.

The point is not five bespoke demos. The point is proving the **same core** can construct all of them.

---

# 21. What NOT to build now

The open-source research makes scope discipline even more important.

Do not begin:

- generic FEM implementation
- generic CFD implementation
- radar engine
- tire-life engine
- huge material database
- large component library
- automatic LLM domain planner
- generalized distributed runtime
- GPU framework
- all domain packs simultaneously

Each is valuable later but premature before universal contracts are stable.

---

# 22. IP / acquisition implication

Reading open-source architectures strengthens Crafty's IP position **only if Crafty independently implements its own contracts and code**.

Policy:

```text
Read architecture
↓
Understand design trade-offs
↓
Document concepts
↓
Design Crafty-native contracts
↓
Implement independently
↓
Verify with Crafty tests
```

Do not copy GPL/copyrighted implementation code into Crafty casually.

Maintain clear dependency/license records from the beginning because future strategic buyers will conduct IP/dependency diligence.

The architecture studies themselves should be retained as evidence of deliberate independent design reasoning.

---

# 23. Commercial implication

The research also sharpens Crafty's differentiation.

None of the studied projects alone targets the complete Crafty loop:

```text
Natural-language / user engineering objective
↓
Scientific capability planning
↓
Validity-aware model selection
↓
Realization selection
↓
Cross-domain scientific composition
↓
Simulation / coupling
↓
UQ + evidence governance
↓
Design / research decision
↓
Scientific memory
```

The studied systems demonstrate that each lower-level problem is real and difficult.

Crafty's commercial thesis is to integrate these ideas under a scientific-governance and planning layer rather than compete with each project on its deepest specialty from day one.

---

# 24. Final recommendation

Proceed with Crafty.

Do not redesign it from scratch.

Do not start broad domain expansion.

**Next implementation action:** preregister and execute `MODEL0-R`, updated with the constraints in Section 16.

After MODEL0-R passes full regression, reassess `CAP0` against the actual code and the study findings before implementation.

The open-source study has reduced architecture risk and increased confidence in the general direction; it has not created a reason to abandon the current vision.

---

# 25. Source studies

This synthesis is based on the project-specific studies stored beside this file:

1. `01_MOOSE_ARCHITECTURE_STUDY.md`
2. `02_PETSC_ARCHITECTURE_STUDY.md`
3. `03_OPENFOAM_ARCHITECTURE_STUDY.md`
4. `04_PRECICE_COUPLING_STUDY.md`
5. `05_FENICSX_MFEM_EQUATION_FIELD_STUDY.md`
6. `06_OPENMDAO_MODELICA_SYSTEM_COMPOSITION_STUDY.md`

No implementation code from the studied projects has been copied into Crafty as part of this research cycle.
