# Open-Source Architecture Study 05 — FEniCSx + MFEM

**Purpose:** Learn equation/form representation, function-space, field and FEM-discretization architecture relevant to Crafty FIELD0 and future Equation IR.  
**Projects studied:** FEniCSx (UFL/FFCx/DOLFINx) and MFEM  
**Study date:** 2026-09-02  
**Mode:** Read-only architecture study

---

# 1. Why these projects matter

FEniCSx and MFEM solve a different architectural problem from OpenFOAM.

OpenFOAM shows how to build a deep FVM/CFD ecosystem. FEniCSx and MFEM show how mathematical field problems can be expressed through finite-element spaces, forms, operators and assembly in a reusable way.

This is directly relevant to Crafty's future:

- FIELD0
- Equation / Residual IR
- FEM realizations
- Structural Mechanics
- Electromagnetics
- high-order methods
- tensor/vector fields

---

# 2. FEniCSx separates mathematical form language from runtime

A major architectural strength of FEniCSx is separation between:

```text
UFL
mathematical/variational form representation

↓

FFCx
analysis + intermediate representation + code generation

↓

DOLFINx
mesh/function spaces/assembly/runtime
```

This separation is highly relevant to Crafty.

## Crafty lesson

Do not force ScientificModelDefinition to contain executable numerical code.

A stronger future pipeline is:

```text
Scientific Model
↓
Computational Realization
↓
Equation / Residual IR
↓
Discretization IR
↓
Generated / assembled operator
↓
Numerical runtime
```

The exact boundary must remain general enough for non-FEM realizations.

---

# 3. UFL demonstrates the value of a mathematical expression graph

UFL represents forms using an expression language and expression tree/graph rather than handwritten matrix assembly.

It can express:

- scalar/vector/tensor expressions
- trial/test functions
- coefficients
- derivatives
- integrals over volume/boundary/interior interfaces
- mixed fields

## Crafty adoption candidate

Crafty should eventually have a **domain-neutral Equation/Residual IR**, but it must be broader than UFL because Crafty also needs:

- algebraic models
- ODE
- DAE
- PDE
- discrete/event models
- reduced-order models
- surrogates

Therefore UFL should inspire the PDE/variational branch of the realization IR, not define the entire universal model language.

---

# 4. Domain and integration region are part of the mathematical form

UFL separates integrals by cell, exterior boundary and interior facet regions.

This reinforces that physical equations are not only symbolic expressions; they are expressions **over spatial supports**.

## Crafty lesson

Future Equation IR should be capable of stating:

```text
expression
+ support/domain
+ measure/integration semantics
+ boundary/interface scope
```

This fits FIELD0 and SYSTEM0.

---

# 5. Function spaces are explicit objects

DOLFINx represents a function space using:

```text
Mesh
+ Finite Element
+ Degree-of-Freedom Map
```

This is a strong architectural lesson.

## Crafty implication

Do not collapse these concepts:

```text
Field scientific identity
Finite-element function space
Mesh
DoF layout
Numerical vector
```

A field such as temperature is a scientific quantity. Its discretized FE representation is one computational realization of that field.

---

# 6. MFEM confirms that field space type matters scientifically/numerically

MFEM explicitly supports different conforming spaces including:

- H1
- H(curl)
- H(div)
- L2
- trace/interface spaces

This is critical for Crafty's long-term electromagnetics and fluid/continuum work.

## Major Crafty lesson

`FIELD0` cannot only know:

```text
scalar/vector/tensor
```

The numerical realization may also need to know the function-space/conformity semantics.

However these should belong to the **discretized field realization**, not the universal scientific field definition.

Possible future split:

```text
ScientificFieldDefinition
↓
DiscreteFieldSpace
├─ support topology
├─ basis/order
├─ conformity
├─ DoF layout
└─ discretization family
```

---

# 7. EM strongly benefits from correct function spaces

MFEM's H(curl) and H(div) support demonstrates why electromagnetics cannot be treated as "just vector arrays on a mesh".

## Crafty lesson

If EM0 is eventually built, the universal field/numerical design must already support domain-appropriate field-space semantics.

This argues strongly against prematurely implementing FIELD0 as a NumPy array wrapper.

---

# 8. Forms compile to lower-level representations

FFCx has explicit compiler phases including analysis, IR representation and code generation.

## Crafty adoption candidate

Long-term Crafty may benefit from a compilation model:

```text
Scientific/Equation IR
↓ validate
Normalized IR
↓ lower
Discretization IR
↓ optimize
Executable Numerical Plan
```

This may be much safer than directly letting domain code manually construct solver calls.

A compiled plan can also be hashed/versioned for provenance.

---

# 9. Assembly is a separate responsibility

DOLFINx exposes assembly from forms into vectors/matrices.

MFEM similarly acts as a translator from finite-element descriptions to linear algebra operators.

## Crafty lesson

`Assembly` should eventually be an explicit computational stage/capability.

Conceptually:

```text
Discrete Form
↓
AssemblyStrategy
↓
Operator / Matrix / Matrix-Free representation
```

Do not assume assembled sparse matrices are always required; high-performance FEM increasingly uses partial/matrix-free assembly.

---

# 10. Matrix-free / operator-based execution must remain possible

MFEM supports operator evaluation patterns that do not require fully assembled global matrices and supports GPU-oriented execution.

## Crafty lesson

Future NUM0 interfaces should center around a generic `LinearOperator` concept rather than require a concrete SparseMatrix everywhere.

Potential:

```text
LinearOperator
├─ assembled sparse matrix
├─ matrix-free operator
├─ block operator
└─ external backend operator
```

This aligns well with PETSc lessons.

---

# 11. High-order support should be architectural, not a separate domain

MFEM supports arbitrary high-order spaces across several field conformities.

## Crafty lesson

Polynomial/basis order is a computational realization parameter, not a new scientific model.

Changing:

```text
P1 → P3
```

usually changes numerical fidelity/discretization, not the underlying physics identity.

Crafty provenance must record it, while Model identity remains stable when scientifically appropriate.

---

# 12. Cross-mesh interpolation exists even inside FEM ecosystems

DOLFINx includes infrastructure for interpolation across different meshes.

This reinforces preCICE's lesson that transfer/mapping is fundamental.

## Crafty implication

Mapping should be shared infrastructure, not implemented independently by every domain.

---

# 13. CPU/GPU portability belongs below scientific models

MFEM abstracts device execution and memory handling below high-level finite-element applications.

## Crafty lesson

Do not put GPU/CPU selection in ScientificModelDefinition.

It belongs in realization/backend/execution policy.

```text
Scientific Model
↓
Realization
↓
Execution Backend
├─ CPU
├─ GPU
└─ distributed
```

---

# 14. What Crafty should adopt from FEniCSx

1. Mathematical form/IR separated from runtime.
2. Expression graphs rather than handwritten assembly everywhere.
3. Explicit domains/boundaries/interfaces in mathematical forms.
4. Function-space abstraction.
5. Compiler/lowering pipeline concept.
6. Assembly as a separate stage.
7. Automated differentiation/derivative transformations over expressions where possible.

---

# 15. What Crafty should adopt from MFEM

1. Rich finite-element space semantics.
2. H1/H(curl)/H(div)/L2 awareness.
3. High-order as a realization parameter.
4. Operator-first rather than matrix-only architecture.
5. Parallel/GPU execution beneath the scientific layer.
6. FEM as a translator from field/problem definitions to algebraic operators.

---

# 16. What Crafty should NOT copy directly

1. Do not make variational FEM forms the universal scientific language.
2. Do not make Field == FiniteElementFunction.
3. Do not tie scientific geometry to a finite-element mesh.
4. Do not expose backend device memory in scientific records.
5. Do not assume assembled matrices.
6. Do not create a Python-expression DSL as the only representation of equations.
7. Do not let mathematical expressibility substitute for validity/evidence.

---

# 17. Proposed field architecture candidate

Pending future FIELD0 design:

```text
ScientificFieldDefinition
├─ quantity
├─ tensor shape/rank
├─ unit/dimension
├─ coordinate frame
├─ spatial support semantics
├─ temporal/frequency semantics
└─ uncertainty semantics

        ↓ realization

DiscreteFieldRepresentation
├─ mesh/topology reference
├─ function/discrete space
├─ basis / order
├─ DoF layout
├─ storage/backend
└─ transfer/interpolation capabilities
```

This separation synthesizes OpenFOAM, PETSc, FEniCSx and MFEM lessons.

---

# 18. Proposed Equation IR layers candidate

Do not build yet; candidate architecture only:

```text
Universal Realization IR
├─ Algebraic
├─ ODE
├─ DAE
├─ PDE
│   ├─ strong/residual representation
│   └─ variational/form representation
├─ Discrete
└─ Surrogate
```

For PDE realizations:

```text
Equation/Form IR
↓
Discretization Plan
↓
Discrete Operator IR
↓
Numerical Solver Stack
```

---

# 19. Impact on MODEL0-R

MODEL0-R should use a formulation classification broad enough to support future lowering paths such as:

- ALGEBRAIC
- ODE
- DAE
- PDE
- DISCRETE
- SURROGATE

But it should **not** attempt to define Equation IR in this milestone.

A ModelRealizationDefinition should describe identity and requirements, not embed a finite-element form compiler.

---

# 20. New candidate invariants

### Candidate Y

Scientific field identity is separate from its discrete function-space representation.

### Candidate Z

Equation/model IR is separate from discretization IR.

### Candidate AA

A numerical operator may be assembled or matrix-free; NUM0 must not assume sparse matrices everywhere.

### Candidate AB

Function-space conformity is a computational field-space property and must remain representable for domains such as electromagnetics.

### Candidate AC

Execution hardware is an execution/backend property, not scientific model identity.

---

# 21. Combined lesson after FEniCSx/MFEM

The architecture is becoming clearer:

```text
Scientific Meaning
↓
Model
↓
Realization
↓
Equation / Residual IR
↓
Field / Space realization
↓
Discretization
↓
Operator
↓
PETSc-like Numerical Stack
```

with OpenFOAM-like mature domain ecosystems and preCICE-like cross-participant coupling above/beside this numerical substrate.

---

# 22. Next study

Recommended next:

# **OpenMDAO + OpenModelica**

Focus:

- multidisciplinary system composition
- component ports/connections
- dependency graphs
- coupled-system solving
- design variables/objectives/constraints
- optimization derivatives
- acausal equation-based modeling
- state/events/component libraries

These are particularly relevant to SYSTEM0, PhysicsGraph and DISCOVERY0.

No FEniCSx or MFEM implementation code has been copied into Crafty.
