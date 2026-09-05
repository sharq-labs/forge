# Open-Source Architecture Study 04 — preCICE

**Purpose:** Learn how to design robust cross-solver / cross-domain coupling for Crafty without copying implementation code.  
**Project studied:** preCICE — Precise Code Interaction Coupling Environment  
**Study date:** 2026-09-02  
**Mode:** Read-only architecture study  

---

# 1. Why preCICE matters to Crafty

preCICE specializes in partitioned multiphysics: it couples independent simulation programs that each solve part of a larger physical system.

It provides infrastructure for:

- participant communication
- coupling data exchange
- interface meshes
- mapping between different meshes
- transient/time-window coupling
- explicit and implicit schemes
- convergence criteria
- relaxation / acceleration
- checkpoint / rollback
- solver adapters

This directly addresses one of Crafty's hardest future requirements:

> How can independently developed Domain Engines / Solver Realizations be combined into one scientifically defensible simulation?

---

# 2. Participant abstraction

preCICE treats each coupled solver as a `participant`.

The participant remains responsible for its own internal physics and solve.

Coupling infrastructure does not need to understand the full implementation of that solver.

Conceptually:

```text
Participant A
physics + internal solver

Participant B
physics + internal solver

        ↓ both expose
Coupling Interface
```

## Crafty lesson

This strongly supports keeping Domain Engines independently executable.

Future Crafty execution graph nodes should expose typed interfaces rather than allowing adjacent domains to depend directly on each other's internal classes.

Potential concept:

```text
ExecutableParticipant
├─ realization identity
├─ input ports
├─ output ports
├─ state/checkpoint capability
├─ time capability
└─ solver lifecycle
```

This is a future SIM0/COUPLE0 concern, not MODEL0-R scope.

---

# 3. Coupling data is explicitly declared

preCICE explicitly defines exchanged scalar/vector data and the mesh on which data exists.

This is much stronger than generic key/value wiring.

## Crafty adoption candidate

A coupling edge should identify:

```text
Scientific Quantity
Field/Scalar nature
Unit
Source participant/port
Target participant/port
Spatial support
Temporal semantics
Mapping policy
```

Crafty should additionally include:

- uncertainty transfer semantics
- provenance
- validity assumptions
- coordinate frame
- conservation semantics

---

# 4. Different solvers may use different interface meshes

preCICE explicitly supports non-matching meshes and provides mapping algorithms between them.

This is critical for Crafty's cross-domain ambition.

Example:

```text
CFD mesh
   ↓ force field
Mapping
   ↓
Structural FEM mesh
```

## Crafty lesson

A Physics Graph edge cannot simply assume:

```text
output_array → input_array
```

It may require a **Transfer Realization**.

Future coupling contract candidate:

```text
CouplingTransfer
├─ source field
├─ target field
├─ source topology
├─ target topology
├─ mapping operator
├─ interpolation order
├─ conservation property
├─ error estimate
└─ provenance
```

---

# 5. Explicit vs implicit coupling is a first-class distinction

preCICE supports:

```text
serial explicit
parallel explicit
serial implicit
parallel implicit
multi-participant coupling
```

Explicit coupling performs one exchange per coupling time window.

Implicit coupling repeatedly executes participants until coupling convergence is reached.

## Crafty lesson

The Physics Graph must remain separate from the Coupling Execution Plan.

Same scientific topology:

```text
Fluid ↔ Structure
```

may be executed using:

```text
Loose coupling
or
Iterated fixed-point coupling
or
Accelerated implicit coupling
```

Thus:

```text
PhysicsGraph != CouplingScheme
```

This candidate invariant from the MOOSE study is now strongly reinforced.

---

# 6. Time windows are not the same as participant time steps

preCICE uses coupling time windows. Participants may use smaller internal timesteps and subcycle inside a coupling window.

## Crafty lesson

`STATE0/SIM0` needs at least two time concepts:

```text
Participant local time step
Coupling synchronization window
```

Potentially later:

```text
observation time
control time
experiment time
```

Do not bake a single global `dt` into universal simulation contracts.

---

# 7. Checkpoint / rollback is essential for implicit coupling

For implicit coupling, a participant may need to restore its state and recompute a time window during coupling iterations.

preCICE therefore exposes explicit checkpoint requirements.

## Major Crafty lesson

`STATE0` cannot mean only "current values".

For serious coupled simulations it must support:

```text
State Snapshot
├─ physical state
├─ history-dependent variables
├─ solver-required state
├─ time index
└─ deterministic restore
```

This is especially important later for:

- viscoelasticity
- plasticity
- fatigue
- material aging
- batteries
- controls
- iterative multiphysics

Checkpointability should eventually be a declared execution capability.

---

# 8. Coupling convergence is separate from participant convergence

preCICE documentation highlights that implicit coupling convergence requires participants themselves to be internally converged sufficiently.

This gives Crafty at least three distinct convergence concepts:

```text
1. Internal numerical convergence of participant
2. Coupling/interface convergence
3. Scientific/model validity
```

These must never be collapsed.

Possible result structure later:

```text
NumericalValidation
CouplingValidation
ScientificValidation
```

Crafty's existing principle that numerical convergence != scientific validity is therefore extended naturally to coupled systems.

---

# 9. Coupling acceleration belongs to coupling infrastructure

preCICE provides techniques such as:

- constant relaxation
- Aitken relaxation
- quasi-Newton acceleration variants

These act on coupling iterations rather than modifying domain equations.

## Crafty lesson

Do not implement relaxation/acceleration individually inside Thermal, Mechanical, Fluid, etc.

They belong in shared `COUPLE0` infrastructure.

Conceptually:

```text
CouplingScheme
├─ scheduling
├─ convergence measure
├─ relaxation
├─ acceleration
├─ iteration budget
└─ failure policy
```

---

# 10. High-level coupling API reduces solver awareness

preCICE deliberately uses a high-level API where communication/control is coordinated through operations such as advancing the coupling rather than asking each solver to manually orchestrate every send/receive sequence.

## Crafty lesson

Domain solvers should not understand the complete global Physics Graph.

Prefer inversion of control:

```text
Domain Participant
implements lifecycle contract

Crafty Simulation Runtime
orchestrates global plan
```

This reduces cross-domain dependencies.

---

# 11. Adapters are explicit boundaries

preCICE maintains adapters for multiple independent solvers including OpenFOAM, FEniCSx, CalculiX and others.

## Crafty lesson

This supports our adapter policy:

```text
Crafty typed contracts
        ↕
Adapter
        ↕
External/Native Solver
```

Adapters should own translation concerns.

The universal core should not inherit OpenFOAM/FEniCS-specific types merely because adapters exist.

---

# 12. Participant identity vs scientific identity

A preCICE participant is essentially an executable solver participant.

Crafty needs an additional scientific layer above this.

```text
Scientific Model
↓
Computational Realization
↓
Executable Participant
↓
Coupling Interface
```

This preserves MODEL0-R's distinction while enabling realistic coupled execution.

---

# 13. Data mapping itself needs verification

Mesh mapping can introduce approximation/error even if both underlying solvers are individually correct.

## Crafty improvement opportunity

Mapping should eventually return/report more than mapped values:

```text
MappedField
+
MappingDiagnostics
├─ method
├─ source/target coverage
├─ conservation error
├─ interpolation error estimate
├─ extrapolation flags
└─ provenance
```

This is a natural fit for Crafty's evidence/UQ architecture and could become a differentiator.

---

# 14. Coupling should propagate uncertainty/error

preCICE focuses primarily on numerical coupling infrastructure.

Crafty should eventually add scientific uncertainty semantics:

```text
Source uncertainty
+
Mapping uncertainty/error
+
Participant model uncertainty
+
Coupling residual/error
↓
System result uncertainty
```

This is a difficult long-term capability and should not be promised prematurely, but the contracts should not make it impossible.

---

# 15. Multi-participant coupling confirms the graph model

preCICE supports coupling beyond exactly two participants.

This reinforces Crafty's decision to model a scientific system as a graph rather than a fixed two-solver interface.

Example HVAC graph:

```text
Refrigerant cycle
       ↕
Heat exchanger thermal model
       ↕
CFD airflow
       ↕
Fan electrical/mechanical model
       ↕
Acoustic model
```

COUPLE0 must eventually work over arbitrary bounded graphs.

---

# 16. Coupling topology vs execution schedule

This is now one of the strongest architecture conclusions from all studies.

Define independently:

```text
PhysicsGraph
= scientific dependencies and transfers

ExecutionPlan
= ordering, parallelism, time windows, iterations and checkpoint policy
```

Example:

```text
A ↔ B
```

can produce multiple execution plans without changing the scientific topology.

This separation should become a likely future frozen invariant.

---

# 17. What Crafty should adopt conceptually from preCICE

1. **Participants as independent executable units.**
2. **Explicit typed coupling data.**
3. **Explicit interface meshes/spatial support.**
4. **Mapping as a first-class operation.**
5. **Explicit vs implicit coupling policies.**
6. **Serial vs parallel execution policies.**
7. **Coupling time windows independent from local timesteps.**
8. **Checkpoint/rollback capability.**
9. **Coupling convergence separate from participant convergence.**
10. **Shared relaxation/acceleration infrastructure.**
11. **Adapters as translation boundaries.**
12. **Multi-participant graph support.**

---

# 18. What Crafty should NOT copy directly

1. XML/string configuration as Crafty's canonical scientific record.
2. A coupling layer that only knows scalar/vector names without scientific quantity semantics.
3. Treating coupling participants as the scientific model identity.
4. Limiting coupling to surface interfaces.
5. Assuming uncertainty begins/ends at individual solvers.
6. Making every solver manually control global communication.
7. Designing COUPLE0 specifically around CFD/FSI examples.

---

# 19. Proposed Crafty coupling architecture after this study

This is a **candidate synthesis**, not implementation scope yet:

```text
PhysicsGraph
│
├─ ParticipantNode
│   ├─ ModelRealization
│   ├─ input ports
│   ├─ output ports
│   └─ state capability
│
└─ CouplingEdge
    ├─ ScientificQuantity
    ├─ source / target
    ├─ MappingDefinition
    ├─ unit/frame transform
    ├─ conservation semantics
    └─ validity

             ↓ compile

CouplingExecutionPlan
├─ explicit / implicit
├─ serial / parallel
├─ synchronization windows
├─ iteration/convergence policy
├─ acceleration
├─ checkpoint/rollback
└─ failure policy
```

This architecture is more explicit scientifically than a raw solver-coupling configuration.

---

# 20. Impact on milestone ordering

The preCICE study suggests `STATE0` cannot be treated as a very late optional feature if COUPLE0 aims to support implicit transient coupling.

Possible dependency:

```text
FIELD0
SYSTEM0
NUM0/SOLVER0
STATE0-minimal
↓
COUPLE0
↓
SIM0
```

However a simpler steady-state COUPLE0 could precede full STATE0.

The exact sequence should be decided when preregistering COUPLE0, not changed inside MODEL0-R.

---

# 21. New candidate invariants from preCICE study

### Candidate S

Physics topology and coupling execution policy are independent objects.

### Candidate T

Coupling mappings are computational realizations with their own diagnostics/provenance.

### Candidate U

Internal solver convergence, coupling convergence and scientific validity are separate statuses.

### Candidate V

Transient implicit coupling requires deterministic state checkpoint/restore capability.

### Candidate W

A participant does not need to know the global graph; orchestration belongs to Simulation Runtime.

### Candidate X

Coupling time windows and participant timesteps are distinct concepts.

---

# 22. Combined architecture after four studies

```text
MOOSE
→ pluggable physics architecture

PETSc
→ composable numerical hierarchy

OpenFOAM
→ deep mature domain-engine design

preCICE
→ independent solver/domain coupling
```

Crafty's differentiated layer remains above all four:

```text
Scientific Intent
↓
Capability Planning
↓
Validity-aware Model Selection
↓
Realization Selection
↓
PhysicsGraph
↓
ExecutionPlan
↓
Domain/Numerical/Coupling infrastructure
↓
UQ + SRIA
↓
Design / Scientific Memory
```

---

# 23. Next study

Recommended next:

# **FEniCSx + MFEM**

Focus:

- equation/form abstraction
- finite-element spaces
- fields/functions
- mesh/discretization separation
- assembly
- high-order/tensor/vector spaces
- electromagnetics-relevant H(curl)/H(div) spaces

These studies will inform `FIELD0`, future Equation IR and FEM-related numerical realizations.

No preCICE implementation code has been copied into Crafty.
