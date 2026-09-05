# Open-Source Architecture Study 02 — PETSc

**Purpose:** Learn reusable numerical-kernel architecture for Crafty without copying PETSc implementation code.  
**Project studied:** PETSc — Portable, Extensible Toolkit for Scientific Computation  
**Study date:** 2026-09-02  
**Mode:** Read-only architecture study  

---

# 1. Why PETSc matters to Crafty

MOOSE teaches how many physics modules can share one multiphysics framework.
PETSc teaches the deeper numerical lesson: how solver layers can be composed instead of independently reimplemented.

A central PETSc hierarchy is conceptually:

```text
Vec / Mat
   ↓
PC
   ↓
KSP   linear systems
   ↓
SNES  nonlinear systems
   ↓
TS    ODE / DAE / time integration
```

`SNES` internally uses `KSP` for linear subproblems, and implicit `TS` methods internally use `SNES` for nonlinear solves.

This directly supports Crafty's goal of a shared `NUM0` rather than separate numerical stacks for Thermal, Mechanics, EM, etc.

---

# 2. Main architectural lesson: numerical capability composition

PETSc does not treat each numerical problem as a standalone monolithic solver.

Instead higher layers reuse lower layers:

```text
Time integration
↓ requires
Nonlinear solving
↓ requires
Linear solving
↓ requires
Preconditioning / algebra
```

## Crafty adoption candidate

Future Crafty numerical contracts should form capability dependencies rather than one giant `NumericalSolver` interface.

Conceptual future structure:

```text
LinearOperator / Vector
↓
Preconditioner
↓
LinearSolveCapability
↓
NonlinearSolveCapability
↓
TimeIntegrationCapability
↓
PDE Realization / Coupled Simulation
```

A high-level solver may internally depend on other solver capabilities without domains knowing implementation details.

---

# 3. Solver composition should be explicit

PETSc allows a nonlinear solver to expose/configure its internal linear solver, and preconditioners can themselves contain nested solvers.

This is powerful because solver composition is represented structurally rather than hard-coded globally.

## Crafty lesson

Future computational realizations should declare requirements such as:

```text
requires:
- numerical:nonlinear_residual_solve
- numerical:sparse_linear_solve
- numerical:preconditioning
```

The planner/runtime can then build an execution stack satisfying those requirements.

Do not encode assumptions like:

```python
if formulation == PDE:
    use SomeSpecificSolver()
```

---

# 4. Separate operator from solver

PETSc's `KSP` solves a linear system expressed through operators/matrices rather than embedding physical meaning inside the solver.

## Crafty lesson

Domain physics should generate a mathematical/computational representation and numerical systems should consume that representation.

Long-term conceptual boundary:

```text
Scientific Model
↓
Computational Realization
↓
Equation / Residual IR
↓
Discretization
↓
Linear / Nonlinear Operator
↓
Numerical Solver Stack
```

This is another reason to avoid domain-specific numerical solvers where generic numerical infrastructure can be shared.

---

# 5. Residual/Jacobian as important realization contracts

PETSc's nonlinear/time interfaces revolve around callbacks representing residual functions and Jacobians or their equivalents.

This means the numerical solver does not need to understand the physical origin of the equations.

## Crafty adoption candidate

A future Equation/Realization IR should be capable of exposing concepts such as:

```text
Residual(state, parameters, time)
Jacobian(...)
Mass operator / time derivative structure
Constraints
Boundary contributions
```

The exact API should be designed during NUM/PDE milestones, not MODEL0-R.

Important requirement now:

> MODEL0-R must not force computational realizations to be callable scalar functions only.

Realizations must eventually support algebraic, ODE, DAE, PDE, discrete and surrogate forms.

---

# 6. Preconditioners deserve first-class architecture

PETSc demonstrates that preconditioning is not an implementation detail. For large numerical systems it can determine whether a solve is practical.

PETSc represents `PC` separately and supports nested/composite preconditioners.

## Crafty lesson

Do not design NUM0 as:

```text
solve(A, b)
```

only.

Future solver contracts should allow:

```text
LinearSolver
├─ algorithm
├─ operator
├─ preconditioner
├─ convergence policy
├─ tolerances
├─ resource policy
└─ diagnostics
```

However preconditioner implementation should be deferred until the appropriate NUM0 stage.

---

# 7. Runtime configurability without changing scientific identity

PETSc permits many implementation choices to be changed at runtime through typed solver selection/options.

The same mathematical problem can therefore be executed with different algorithms without changing the physical model.

## Crafty lesson

This strongly supports:

```text
ScientificModelDefinition
!=
ModelRealizationDefinition
!=
SolverConfiguration
```

A change from one linear/nonlinear algorithm to another should not create a new scientific model identity unless it changes the scientific formulation itself.

Crafty provenance must still record the exact solver stack and settings used.

---

# 8. `DM`: bridge between models/discretization and algebraic solvers

PETSc's `DM` abstraction is especially important.

PETSc explicitly describes `DM` as the bridge between model/discretization structures (including meshes) and algebraic solvers/time integrators.

Different `DM` forms support different structured/unstructured/network/particle representations.

## Crafty lesson

Crafty will likely need a similar **bridge layer**, but not necessarily one object named `DM`.

The future architecture should distinguish:

```text
Scientific/Physical Representation
↓
Discretized Representation
↓
Algebraic Representation
```

Potential Crafty concepts:

```text
FieldSpace
Mesh/Topology
DiscretizationPlan
DofLayout
OperatorAssembly
```

These should mediate between Physics Models and generic NUM0 solvers.

Do not let the mesh directly become the scientific model.

---

# 9. DMPlex lesson: topology should not be tied to one discretization

PETSc's DMPlex documentation explicitly states that it was designed to solve the problem of simulation codes tying discretization, data layout and solver too closely together.

DMPlex represents mesh topology independently and can support finite-element and finite-volume style adjacency choices.

## Major Crafty lesson

`FIELD0/MESH` must avoid an FEM-only or FVM-only worldview.

Crafty should eventually permit:

```text
same geometry/topology
↓
FEM realization
or
FVM realization
or
other discretization
```

without rebuilding the scientific system representation.

This is a critical architectural invariant for a universal simulation core.

---

# 10. Mesh entities as topology rather than ad-hoc arrays

DMPlex models cells, faces, edges and vertices as entities in a topological graph rather than separate unrelated storage structures.

## Crafty lesson

When MESH/FIELD infrastructure is designed, topology should be a first-class abstraction and should not be assumed to be a rectangular grid.

This becomes important for:

- structural mechanics
- irregular geometry
- CFD
- electromagnetics
- interfaces
- adaptive refinement
- cross-mesh coupling

Crafty does not need to copy DMPlex; it needs the abstraction lesson.

---

# 11. Data layout is separate from topology

PETSc uses layout/discretization metadata to map physical/discrete fields onto vectors and matrices.

## Crafty lesson

Separate:

```text
MeshTopology
FieldDefinition
Discretization
DegreeOfFreedomLayout
NumericalVector
```

These are different concepts.

Combining them prematurely would make future alternative numerical realizations difficult.

---

# 12. Nested configuration is powerful but dangerous

PETSc can configure nested solver objects through scoped option prefixes.

This enables very deep solver composition.

## Crafty lesson

Crafty will need structured nested solver configuration, but should not rely on stringly-typed global options as the canonical scientific record.

Preferred Crafty pattern:

```text
Typed SolverConfiguration tree
↓
validated
↓
serialized deterministically
↓
provenance record
```

CLI/config aliases may exist at product boundaries, but internal scientific records should remain typed.

---

# 13. Convergence reason is part of result semantics

PETSc solver objects expose convergence/divergence outcomes and diagnostics rather than merely returning a vector.

## Crafty lesson

This already aligns with Crafty's philosophy.

A numerical result should include at least conceptually:

```text
status
converged?
termination reason
iterations
residual norms
error estimates when available
solver stack
settings
```

Then Crafty must keep this separate from scientific validation:

```text
NUMERICALLY_CONVERGED
!=
SCIENTIFICALLY_VALID
```

---

# 14. Parallelism belongs below domain physics where possible

PETSc's algebra/solver abstractions are designed for distributed parallel computation.

## Crafty lesson

Future domain code should not manually own MPI/parallel scheduling unless a genuinely domain-specific algorithm requires it.

Preferred direction:

```text
Domain Physics
↓
Generic computational realization
↓
NUM0 backend
↓
parallel execution
```

This makes future CPU/GPU/distributed execution replaceable.

---

# 15. Shell/custom implementations teach an extension lesson

PETSc allows user-defined implementations inside standard solver contracts (e.g. shell preconditioners).

## Crafty lesson

Crafty's numerical/runtime contracts should eventually allow plugins/native algorithms to satisfy a capability without modifying the core.

This mirrors our high-level rule:

> Core requests capability, registered implementation provides capability.

---

# 16. What Crafty should adopt conceptually from PETSc

1. **Layered numerical capabilities** instead of monolithic numerical solver classes.
2. **Higher numerical layers reuse lower layers.**
3. **Operator/problem representation separate from solver algorithm.**
4. **Preconditioners first-class.**
5. **Residual/Jacobian interfaces as generic nonlinear boundaries.**
6. **Runtime solver selection without changing scientific model identity.**
7. **Typed nested solver configuration in Crafty provenance.**
8. **A bridge layer between discretized physical models and algebraic solvers.**
9. **Mesh topology separate from discretization/data layout.**
10. **Parallel execution below reusable solver interfaces.**
11. **Explicit numerical termination/convergence diagnostics.**

---

# 17. What Crafty should NOT copy directly

1. Do not expose PETSc-style global string options as Crafty's canonical internal contract.
2. Do not make all scientific concepts numerical contexts.
3. Do not let PETSc's abstractions define Crafty's scientific model ontology.
4. Do not force all domains into matrix-based formulations; matrix-free and alternative realizations must remain possible.
5. Do not implement the entire PETSc solver catalog.
6. Do not attempt HPC complexity before basic correctness and scientific contracts are stable.
7. Do not combine topology, field definition and DoF layout into one universal object.

---

# 18. How Crafty can improve beyond PETSc for its own mission

PETSc answers primarily:

> How can mathematical/numerical problems be solved efficiently and compositionally?

Crafty must add scientific meaning above that:

```text
Why is this equation/model appropriate?
What physical capability does it represent?
What is its validity domain?
Which realization should be used?
How uncertain is the result?
What evidence supports it?
What should be simulated next?
```

Therefore PETSc-like numerical architecture should sit **below** Crafty's scientific governance, never replace it.

---

# 19. Proposed future NUM0 shape after MOOSE + PETSc studies

This is a **study candidate**, not a frozen design:

```text
NUM0
├── Numerical Data
│   ├── Vector
│   ├── LinearOperator
│   ├── SparseMatrix representation(s)
│   └── layouts
│
├── Linear
│   ├── LinearProblem
│   ├── LinearSolver
│   ├── Preconditioner
│   └── ConvergencePolicy
│
├── Nonlinear
│   ├── ResidualOperator
│   ├── JacobianProvider
│   ├── NonlinearSolver
│   └── globalization policy
│
├── Time
│   ├── ODEProblem
│   ├── DAEProblem
│   ├── TimeIntegrator
│   └── Event handling
│
└── Diagnostics
    ├── convergence reason
    ├── residual history
    ├── iteration counts
    └── numerical error metadata
```

Mesh/Field/Discretization should interface with this layer but remain separate enough to support multiple formulations.

---

# 20. Impact on MODEL0-R

PETSc strongly reinforces MODEL0-R.

`ModelRealizationDefinition` should be able to declare solver requirements compositionally, rather than containing a solver name.

Good future form conceptually:

```text
Realization:
  formulation: PDE
  requires_solver_capabilities:
    - numerical:nonlinear_solve
    - numerical:sparse_linear_solve
```

Bad form:

```text
solver = "NewtonGMRES"
```

The solver registry/runtime should determine which implementation satisfies those capabilities subject to policy and evidence.

MODEL0-R should still **not implement NUM0**.

---

# 21. New candidate invariants from PETSc study

These are recommendations pending later architecture freeze:

### Candidate G

Higher-level numerical solvers are compositions of lower-level capabilities.

### Candidate H

Scientific model identity must not change solely because a numerical algorithm changes.

### Candidate I

Mesh topology, discretization and numerical data layout are separate concepts.

### Candidate J

Numerical convergence reports must expose termination reason and diagnostics as first-class records.

### Candidate K

Realizations request numerical capabilities, not concrete solver brand/class names.

### Candidate L

The universal numerical layer must not assume FEM, FVM or matrix assembly as the only realization strategy.

---

# 22. Combined lesson: MOOSE + PETSc

MOOSE suggests:

```text
Shared framework
↓
Pluggable physics
```

PETSc suggests:

```text
Shared numerical hierarchy
↓
Composable solvers
```

Combined Crafty direction:

```text
Scientific Intent / Capability Planning
               ↓
        Scientific Models
               ↓
   Computational Realizations
               ↓
      Physics Execution Graph
               ↓
 Shared Numerical Capability Stack
               ↓
      Solver Implementations
```

This is a stronger architecture than building independent solver stacks per domain.

---

# 23. Next architecture study

Recommended next project:

# **OpenFOAM**

Now that MOOSE has provided the general multiphysics/module lesson and PETSc has provided the numerical hierarchy lesson, OpenFOAM should be studied specifically as a **deep, mature domain engine**.

Questions for the OpenFOAM study:

1. How are fields represented?
2. How are meshes/topology handled?
3. How are finite-volume operators expressed?
4. How are boundary conditions extensible?
5. How are physical models selected at runtime?
6. How does solver modularity work in modern OpenFOAM?
7. How are thermophysical/material models layered?
8. What architecture enabled decades of CFD extension?
9. What technical debt should Crafty avoid?
10. Which concepts belong in Crafty shared core vs a future Fluid Domain Pack?

No PETSc implementation code has been copied into Crafty.
