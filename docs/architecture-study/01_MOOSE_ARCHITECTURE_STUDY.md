# Open-Source Architecture Study 01 — MOOSE

**Purpose:** Learn architectural patterns relevant to Crafty without copying implementation code.  
**Project studied:** MOOSE — Multiphysics Object Oriented Simulation Environment  
**Study date:** 2026-09-02  
**Mode:** Read-only architecture study  

---

# 1. Why MOOSE matters to Crafty

MOOSE is highly relevant because it demonstrates how a shared simulation framework can support many physics modules without forcing each module to rebuild the entire execution infrastructure.

Its public architecture and documentation show a framework composed of a core plus pluggable systems and physics modules. The modules encapsulate reusable kernels, boundary conditions, materials and related physics objects specifically to reduce duplication between applications.

This makes MOOSE especially useful for studying the Crafty principle:

> Every domain owns its physics, but not the shared numerical infrastructure.

MOOSE is **not** a blueprint to copy. Crafty has a broader target: scientific capability planning, model/realization selection, scientific validity, SRIA, design memory and AI-agent integration.

---

# 2. Core architectural pattern

MOOSE's framework is composed of a core and multiple pluggable systems.

A central pattern is object registration + factory creation:

```text
Domain / Module Object
        ↓ registers
Registry / Factory
        ↓
Configuration / Action
        ↓
Runtime object creation
```

The framework Factory stores registered object types and constructs them from validated parameter contracts at runtime.

## Crafty lesson

Crafty should preserve the same broad architectural advantage without copying MOOSE's C++ object model:

```text
Domain Pack
↓ registers
ScientificCapability
ScientificModel
ModelRealization
Component
Coupling capability
↓
Crafty Registries
↓
Planner / Builder
↓
Executable Scientific Plan
```

The universal core must depend on generic contracts, not concrete domain classes.

---

# 3. Registration must be separate from execution

An important MOOSE design pattern is the separation between:

- defining an object type
- registering that type
- validating its parameters
- constructing instances
- executing the configured simulation

This enables new modules to extend the framework without editing a central list of every possible physics object.

## Crafty adoption candidate

Crafty should use independent registries for conceptually different identities:

```text
ScientificCapabilityRegistry
ModelRegistry
RealizationRegistry
SolverRegistry
ComponentRegistry (future)
CouplerRegistry (future)
```

Do **not** collapse these into one universal service locator.

Reason: the scientific meaning of a model, the computational realization of that model and the solver executing that realization are different layers.

---

# 4. MOOSE Action system: declarative problem construction

MOOSE's Action system separates user-facing configuration from the low-level simulation objects it creates.

Actions execute ordered tasks and can construct kernels, materials, boundary conditions and other objects. Task dependencies are resolved rather than relying purely on handwritten setup order.

Conceptually:

```text
High-level input
↓
Actions
↓
Dependency-ordered tasks
↓
Low-level simulation objects
```

## Crafty lesson

This is strongly relevant to the future Crafty planner.

However, Crafty should not make its planner a generic mutable action warehouse.

A better Crafty direction is:

```text
Scientific Intent
↓
Capability Requirements
↓
Planning Graph
↓
Validated Build Plan
↓ FREEZE
Executable Physics Graph
```

The planning phase may be flexible; the execution graph should become deterministic and auditable before the solve begins.

This fits Crafty's scientific provenance philosophy better than allowing arbitrary runtime planner mutation.

---

# 5. Physics abstraction

MOOSE has a higher-level `Physics` system intended to standardize the process of adding an equation and its discretization to a simulation. Importantly, its documentation states that the underlying kernels/boundary conditions/etc. should already work before creating the higher-level Physics abstraction.

## Strong lesson for Crafty

Do not build `Capability Planner` first and expect it to invent physics that does not exist.

Crafty's layers should mature bottom-up and top-down together:

```text
Validated scientific model
+
working computational realization
+
registered capabilities
        ↓
planner can safely compose it
```

Therefore:

> A capability declaration must never imply that an executable validated realization exists unless the registry can prove it.

---

# 6. Materials system: one of the strongest patterns for MAT0

MOOSE materials operate using a producer/consumer property relationship.

A `Material` produces properties; kernels, boundary conditions and even other materials consume those properties.

Properties can depend directly on solution variables and are computed on demand. This allows, for example, thermal conductivity to change with the current temperature during nonlinear solve iterations.

Conceptually:

```text
State / Field
↓
Material Property Model
↓ produces
Material Property
↓ consumed by
Physics Model
```

## Crafty adoption candidate

MAT0 should strongly consider this pattern, expanded with Crafty's epistemic requirements:

```text
MaterialState
↓
MaterialPropertyModel
↓
MaterialPropertyResult
├─ value / field
├─ unit
├─ uncertainty
├─ validity
├─ provenance
└─ derivatives / sensitivities when available
```

A material property should **not** be treated as a static dictionary entry.

Crafty improvement over the basic pattern:

- explicit uncertainty
- validity domain
- sample/batch identity
- source/evidence
- property-model identity
- state/history dependence
- scientific admission where appropriate

---

# 7. Boundary conditions are first-class

MOOSE treats boundary conditions as explicit extensible objects instead of ad-hoc flags inside each physics solver.

It distinguishes classes such as Dirichlet, Neumann, Robin and many specialized interfaces.

## Crafty lesson

Boundary and interface semantics belong in reusable scientific contracts.

Future Crafty physics should avoid solver-specific structures such as:

```text
thermal_solver.left_temperature = ...
```

and prefer generic typed concepts such as:

```text
BoundaryCondition
├─ target
├─ quantity
├─ mathematical type
├─ spatial scope
├─ temporal scope
├─ units
├─ validity
└─ realization requirements
```

Domain-specific physical interpretation remains in the domain layer.

This aligns with the existing Scientific Core rule that not every boundary condition has the same dimensional semantics.

---

# 8. Automatic differentiation lesson

MOOSE uses automatic differentiation to reduce the need for developers to manually implement Jacobians for nonlinear physics.

The public architecture provides AD variants of kernels, boundary conditions and material properties.

## Crafty lesson

When NUM0/PDE infrastructure matures, derivative information should be considered a first-class computational capability rather than domain-by-domain handwritten infrastructure.

Possible future Crafty capabilities:

```text
realization:residual
realization:jacobian
realization:automatic_differentiation
realization:sensitivity
```

Do not implement this in MODEL0-R, but ensure current contracts do not prevent it later.

---

# 9. MOOSE multiphysics: MultiApps + Transfers + convergence

MOOSE supports partitioned multiphysics using separate applications (`MultiApps`) and explicit `Transfers` for moving fields/scalars between them.

The coupling can be loose or iterated to convergence using fixed-point approaches.

This is a crucial lesson because real multiphysics is more than connecting output names.

Conceptually:

```text
Solver A
↓
Transfer / Mapping
↓
Solver B
↓
Transfer / Mapping
↓
Coupling convergence loop
```

## Crafty adoption candidate

Crafty's future `Coupler` should become a first-class contract that can declare:

```text
source quantity / field
source representation
source frame / mesh
↓
transformation / mapping
↓
target representation
unit conversion
space mapping
 time mapping
relaxation
convergence rule
error estimate
conservation rule
```

Coupling strategy should be separate from the scientific models being coupled.

---

# 10. Important MOOSE coupling limitation / lesson

MOOSE's MultiApp architecture is powerful, but the concept of parent/sub-app hierarchies and execution timing introduces orchestration complexity.

For Crafty, avoid making hierarchy itself the scientific meaning of coupling.

Preferred Crafty abstraction:

```text
Physics Graph
nodes = realizations/components
edges = typed scientific transfers

Execution Plan
= one valid scheduling/coupling strategy for that graph
```

This keeps scientific topology separate from runtime scheduling.

That distinction may make Crafty more general for future heterogeneous solvers.

---

# 11. Executioner pattern

MOOSE separates problem definition from execution policy through an `Executioner` system controlling solver behavior, transient execution and time stepping.

## Crafty lesson

Crafty should similarly keep:

```text
What equations/models represent the system?
```

separate from:

```text
How should this study execute them?
```

Future separation candidate:

```text
PhysicsGraph
!=
SimulationExecutionPlan
```

The execution plan can contain:

- steady / transient
- stepping policy
- nonlinear iteration strategy
- coupling strategy
- convergence rules
- checkpoints
- resource policy

This fits SIM0 better than embedding execution choices in domain models.

---

# 12. Computational backend abstraction

Modern MOOSE documentation shows multiple computational backend paths, including traditional MOOSE/libMesh and MFEM-related paths, while preserving higher-level framework concepts where possible.

## Crafty lesson

This supports the decision:

```text
Scientific Model
!=
Computational Realization
!=
Solver Backend
```

Crafty should be able to represent the same scientific model through different realizations/backends.

This strengthens the need for MODEL0-R.

---

# 13. Software Quality Assurance is a major lesson

MOOSE maintains unusually rigorous public software-quality records and separate verification/validation reports for the framework and many physics modules.

Its quality structure includes concepts such as:

- software requirements
- software design descriptions
- requirements traceability
- verification/validation plans
- V&V reports
- failure analysis
- coding standards
- automated testing
- code review

## Crafty adoption candidate

Crafty already has preregistration/freeze/SRIA culture. We should extend it into per-domain maturity records.

Future domain pack structure could include:

```text
domains/<domain>/
├── theory/
├── requirements/
├── models/
├── realizations/
├── verification/
├── validation/
├── benchmarks/
├── limitations/
└── maturity.md
```

A domain should never be labeled "complete" only because its unit tests pass.

---

# 14. Domain maturity lesson

MOOSE's Solid Mechanics module demonstrates that a mature domain contains much more than one equation:

- continuum models
- multiple dimensional assumptions
- small/finite strain regimes
- constitutive/material models
- interface models
- structural elements
- boundary conditions
- numerical kernels
- validation/verification

## Crafty lesson

A Crafty domain engine must eventually be evaluated across:

```text
scientific coverage
numerical coverage
validity coverage
boundary/interface coverage
material integration
verification
validation
failure behavior
performance
extension stability
```

This supports the previously discussed domain maturity levels D0–D6.

---

# 15. What Crafty should adopt conceptually

Strong adoption candidates from MOOSE:

1. **Core + pluggable scientific modules**
2. **Explicit registration instead of universal-core imports**
3. **Typed parameter/contract validation before construction**
4. **Dependency-ordered construction/planning**
5. **First-class boundary/interface objects**
6. **Material property producer/consumer architecture**
7. **State-dependent material properties**
8. **Separation of problem physics from execution policy**
9. **Explicit field/scalar transfer in multiphysics**
10. **Coupling convergence as separate infrastructure**
11. **Automatic-derivative capability as shared numerical infrastructure**
12. **Per-module Verification & Validation discipline**

---

# 16. What Crafty should NOT copy directly

1. Do not copy MOOSE's class hierarchy mechanically.
2. Do not make every concept a generic runtime object.
3. Do not make parent/sub-app hierarchy the fundamental scientific graph.
4. Do not bind Crafty to FEM as its universal mathematical worldview.
5. Do not mix scientific identity with computational implementation.
6. Do not let configuration convenience substitute for scientific validity.
7. Do not inherit decades of backward-compatibility complexity unless required.
8. Do not expose domain objects directly as the universal planner language.

---

# 17. Where Crafty can improve on the pattern

MOOSE primarily answers:

> How do developers build extensible multiphysics simulations?

Crafty's intended higher-level question is:

> Given a scientific objective, what scientifically defensible executable model should be constructed and how much should its result be trusted?

Crafty's differentiation can therefore sit above the mature simulation-framework pattern:

```text
Scientific Intent
↓
Capability Planning
↓
Model Selection
↓
Validity
↓
Realization Selection
↓
Physics Graph
↓
Execution / Coupling
↓
UQ + SRIA
↓
Design / Research Decision
↓
Scientific Memory
```

---

# 18. Mapping to Crafty milestones

| MOOSE lesson | Crafty milestone |
|---|---|
| Factory / registration | MODEL0-R / CAP0 |
| Physics abstraction | MODEL0-R / CAP0 |
| Materials producer-consumer | MAT0 |
| Boundary conditions | FIELD0 / SYSTEM0 / domain contracts |
| Mesh and variables | FIELD0 / MESH/NUM work |
| AD | NUM0 later |
| Executioner | SIM0 |
| MultiApps | COUPLE0 / SIM0 |
| Transfers | COUPLE0 |
| V&V per module | every domain maturity milestone |
| computational backends | MODEL0-R / SOLVER0 |

---

# 19. Impact on MODEL0-R

This MOOSE study **supports**, rather than invalidates, the current MODEL0-R direction.

Specifically it strengthens the separation:

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

However, MODEL0-R should remain small.

Do **not** add MOOSE-inspired Materials, Actions, Physics Graph, Mesh, Fields or Coupling in MODEL0-R.

The architectural lesson should influence future contracts without expanding current scope.

---

# 20. New candidate invariants from this study

These are **study recommendations, not frozen decisions yet**:

### Candidate A

Registration declares capability; registration does not prove scientific validity.

### Candidate B

The planner constructs a plan, but execution uses a frozen/auditable graph.

### Candidate C

Physics topology and runtime scheduling are different objects.

### Candidate D

Material properties are produced from material state/property models, not read as timeless constants.

### Candidate E

Coupling includes transfer + mapping + synchronization + convergence, not only input/output wiring.

### Candidate F

Every mature domain has independent verification/validation records.

---

# 21. Sources reviewed

Primary public sources reviewed include:

- MOOSE System Design Description
- MOOSE Physics Modules documentation
- MOOSE Action System documentation
- MOOSE Physics system documentation
- MOOSE Materials system documentation
- MOOSE Boundary Conditions documentation
- MOOSE Executioner documentation
- MOOSE MultiApp / Transfer documentation
- MOOSE fixed-point coupling documentation
- MOOSE Automatic Differentiation documentation
- MOOSE Software Quality / Verification & Validation records
- MOOSE public GitHub source, including `Factory.h`

This study extracts architectural concepts only. No MOOSE implementation code is copied into Crafty.

---

# 22. Next architecture study

Recommended next project:

# **PETSc**

Reason:

MOOSE tells us how a mature multiphysics framework organizes physics objects and modules. PETSc should teach us how to design the reusable numerical hierarchy beneath those domains:

```text
Vector / Matrix
↓
Preconditioner
↓
Linear Solver
↓
Nonlinear Solver
↓
Time / ODE / DAE Solver
```

After PETSc, study OpenFOAM's mature domain-engine architecture, followed by preCICE for multiphysics coupling.
