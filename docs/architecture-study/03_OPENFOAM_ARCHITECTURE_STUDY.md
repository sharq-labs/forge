# Open-Source Architecture Study 03 — OpenFOAM

**Purpose:** Learn how a mature, extensible domain engine is structured so Crafty can build strong domain packs without copying OpenFOAM code.  
**Project studied:** OpenFOAM Foundation / OpenFOAM 14 and relevant source architecture  
**Study date:** 2026-09-02  
**Mode:** Read-only architecture study  

---

# 1. Why OpenFOAM matters to Crafty

OpenFOAM is a mature scientific software system whose strength comes from much more than solving Navier–Stokes equations.

Its architecture combines:

- geometric fields
- mesh/topology
- finite-volume discretization
- equation/matrix construction
- boundary conditions
- physical-model families
- runtime selection
- modular solvers
- multi-region execution
- thermophysical models
- source/constraint systems
- diagnostics and postprocessing

For Crafty, OpenFOAM is valuable as an example of what a **deep domain engine** looks like after decades of scientific/software evolution.

The lesson is not "copy OpenFOAM".

The lesson is:

> A strong domain is a complete scientific ecosystem built on reusable abstractions, not a folder containing equations.

---

# 2. Modern OpenFOAM moved from application solvers to modular solver classes

OpenFOAM 11 introduced class-based modular solvers and generalized executables such as `foamRun` / `foamMultiRun`.

The motivation explicitly included:

- easier maintenance
- easier extension
- flexible multi-region simulations
- reuse of solver modules across different coupled cases

This is extremely relevant to Crafty.

## Crafty lesson

Do not create one executable/mega-class per real-world product or simulation scenario.

Prefer:

```text
Generic Simulation Runtime
        ↓ loads
Domain Solver / Realization Modules
        ↓ composed by
System / Physics Graph
```

This supports our rule that HVAC, Tire, Motor, Radar etc. should not each become isolated simulation architectures.

---

# 3. Field is a central abstraction

OpenFOAM's `GeometricField` connects data values to:

- a mesh
- dimensions
- boundary fields
- field source structures
- time/history behavior

This is one of the most important lessons for `FIELD0`.

A serious field is not simply:

```python
array[float]
```

It has geometric and physical context.

## Crafty adoption candidate

Future Crafty field concepts should separate but connect:

```text
FieldDefinition
├─ scientific quantity
├─ tensor rank / shape
├─ unit / dimension
├─ support (volume / surface / point / other)
├─ coordinate frame
├─ spatial topology/reference
├─ temporal/frequency context
├─ boundary representation
└─ uncertainty/provenance when applicable
```

Numerical storage layout should remain a computational concern rather than the scientific identity of the field.

---

# 4. Strong lesson: dimensions travel with fields

OpenFOAM's field/equation ecosystem carries physical dimension information and v14 further expanded units/dimensions support in case configuration.

Crafty already has strong unit semantics through its Scientific Core.

## Crafty implication

Do not lose unit/dimension information when moving from scientific IR into FIELD0 and equation/discretization layers.

Desired boundary:

```text
Scientific Quantity + Units
↓
Field
↓ controlled adapter
Numerical representation
```

A discretization/operator producing dimensionally incompatible equations should be rejectable before the result becomes scientific evidence.

This can become an advantage of Crafty over numerical frameworks where scientific epistemic checks are less central.

---

# 5. Mesh owns topology and geometry, with derived data managed explicitly

OpenFOAM's `fvMesh` stores finite-volume mesh topology and geometry and manages derived geometric data as the mesh changes.

The documentation warns that derived geometry may be invalidated/recomputed after mesh motion/refinement.

## Crafty lesson

Future MESH infrastructure should distinguish:

```text
Topology
Geometry
Derived Geometry Cache
Mesh Revision / State
```

Do not allow stale geometric quantities to survive a topology/geometry mutation without explicit invalidation.

This matters later for:

- adaptive mesh refinement
- moving meshes
- FSI
- contact
- deforming geometry
- optimization with geometry changes

---

# 6. But Crafty must not make `fvMesh` universal

`fvMesh` is specifically designed around finite-volume discretization.

PETSc's DMPlex study already warned us against tying universal topology to one discretization.

Therefore Crafty should split more aggressively:

```text
Crafty MeshTopology / Geometry
        ↓
Discretization-specific View
        ├─ FVM view
        ├─ FEM view
        └─ future views
```

OpenFOAM's design is excellent for its domain; Crafty needs a broader abstraction because its mission is cross-domain and cross-discretization.

---

# 7. Finite-volume equation construction is compositional

OpenFOAM's finite-volume operators produce `fvMatrix` structures representing discretized equations.

Its codebase separates interpolation/divergence/gradient/etc. schemes from higher-level physics equations.

## Crafty lesson

This strongly supports a future pipeline:

```text
Scientific Equation / Residual
↓
Discretization Operators
↓
Discrete Operator / Equation System
↓
Numerical Solver
```

The domain should express physics; shared discretization infrastructure should transform that physics into a numerical problem.

Do not let every domain manually assemble matrices if a reusable operator layer can do so.

---

# 8. Runtime selection is a core scalability mechanism

OpenFOAM uses runtime selection tables heavily for:

- numerical schemes
- physical models
- boundary conditions
- transport/thermophysical models
- solver modules

The configuration selects an implementation without recompiling the central solver for every model choice.

## Crafty adoption candidate

This supports our registry/capability architecture:

```text
Scientific requirement
↓
Registry candidates
↓
Compatibility / validity filtering
↓
Selected implementation
```

But Crafty should improve on plain runtime type selection by including scientific semantics:

```text
capability
validity
fidelity
uncertainty
validation evidence
cost
solver requirements
```

Selection must be scientific, not merely string-to-class lookup.

---

# 9. Boundary conditions are a mature extension ecosystem

OpenFOAM has a broad library of boundary-condition types across general, inlet, outlet, wall, coupled and geometric constraints.

This demonstrates a key domain maturity lesson:

> Boundary behavior is as important as governing equations.

## Crafty implication

Each mature domain pack should have explicit coverage for:

- supported boundary semantics
- required quantities
- compatibility rules
- physical assumptions
- validation status

The universal core should own generic boundary/interface contracts, while domain packs own physical interpretations.

---

# 10. Physical models are separated from the base solver

OpenFOAM's modern `fvModels` and `fvConstraints` systems allow additional source/model/constraint behavior to be composed with solver modules.

This is important because not every physical effect should require a new solver implementation.

Conceptually:

```text
Base Conservation Equations
        +
Physical Models / Sources
        +
Constraints
        ↓
Executable Domain Problem
```

## Crafty lesson

Future domains should avoid creating a new `ScientificModelDefinition` for every combination of effects.

Prefer compositional models when scientifically valid:

```text
Base Model
+
Source Model
+
Constitutive Model
+
Constraint
```

However composition must carry assumptions and validity and must not create physically invalid combinations.

---

# 11. Thermophysical modeling teaches model-family layering

OpenFOAM supports configurable thermophysical/transport/mixture models, with choices made at runtime.

This reinforces the MAT0 vision:

```text
Material / Mixture Identity
↓
State
↓
Property / Constitutive Model Family
↓
Requested property
```

Do not encode "air", "steel", "gasoline" as bags of constants.

The correct property model depends on regime/state/composition.

Crafty should add stronger:

- provenance
- uncertainty
- evidence
- validity domains
- model identity
- sample/batch context

---

# 12. Multi-region solver architecture is a key cross-domain lesson

Modern OpenFOAM modular solvers can execute different solver modules on different mesh regions for problems such as conjugate heat transfer.

## Crafty lesson

A System/Physics Graph must allow different components/regions to use different realizations and possibly different numerical methods.

Example:

```text
Solid region
→ thermal conduction realization

Fluid region
→ CFD realization

Interface
→ heat/flux coupling
```

Crafty must not assume "one system = one solver".

---

# 13. Solver module vs scientific model

Modern OpenFOAM modularity reinforces an important Crafty distinction but also shows why we should go further.

In Crafty:

```text
Scientific Model
!=
Computational Realization
!=
Solver Module
```

A solver module may embody multiple implementation details and algorithmic loops.

Crafty's scientific identity must remain above those implementation choices so results can be compared across realizations.

---

# 14. Demand-driven / derived-data behavior

OpenFOAM frequently computes expensive or derived data on demand and caches it while managing invalidation.

## Crafty lesson

Future Field/Mesh/Material infrastructure should consider explicit derived-value lifecycle:

```text
Source State Revision
↓
Derived Quantity Cache
↓
Dependency tracking
↓
Invalidate when source changes
```

This is particularly useful for expensive material properties, geometry metrics, coupling maps and Jacobians.

But cache invalidation must be deterministic and provenance-safe.

---

# 15. OpenFOAM domain strength comes from orthogonal extension points

A major reason OpenFOAM can grow is that different concerns have different extension mechanisms:

```text
Fields
Mesh
Boundary Conditions
Discretization Schemes
Physical Models
Constraints
Thermophysical Models
Solver Modules
Function Objects / Postprocessing
```

## Crafty lesson

Do not create one generic plugin type called `DomainPlugin` that can do anything.

Prefer explicit extension contracts.

Candidate future Crafty extension categories:

```text
ScientificCapabilityProvider
ScientificModelProvider
RealizationProvider
MaterialPropertyProvider
BoundaryModelProvider
DiscretizationProvider
SolverProvider
CouplingProvider
Postprocessing / DerivedMetricProvider
```

Not all need separate registries immediately, but their semantics should remain distinct.

---

# 16. What OpenFOAM shows about "OpenFOAM-class" domain maturity

A mature domain engine must provide far more than governing equations.

For a future Crafty Fluid domain, maturity would eventually involve:

- conservation laws
- multiple regimes
- material/thermophysical models
- boundary conditions
- source terms
- numerical schemes
- mesh interactions
- steady/transient execution
- nonlinear coupling
- diagnostics
- conservation checking
- benchmark cases
- verification
- validation
- performance/HPC
- documentation
- stable extension surfaces

This validates the Crafty D0–D6 domain maturity concept.

---

# 17. Technical-debt lessons Crafty should avoid

OpenFOAM's age and breadth reveal trade-offs that Crafty can avoid while young.

## Avoid A — scientific meaning tied too closely to implementation classes

Crafty should retain stronger model/realization separation.

## Avoid B — one discretization worldview in universal core

Finite volume is right for OpenFOAM; Crafty must support multiple numerical representations.

## Avoid C — string-driven configuration as scientific truth

Runtime names are convenient but Crafty canonical records should be typed/versioned.

## Avoid D — configuration combinations without epistemic governance

Crafty must know whether a model combination is valid, not only whether classes can be instantiated.

## Avoid E — legacy compatibility influencing the initial universal design

Crafty can define stricter contracts now while the platform is small.

---

# 18. What Crafty should adopt conceptually from OpenFOAM

1. **Field as a first-class scientific/numerical object.**
2. **Explicit dimensions attached to field/equation infrastructure.**
3. **Mesh topology/geometry lifecycle and cache invalidation discipline.**
4. **Composable discretization operators.**
5. **Runtime-selectable implementations.**
6. **Boundary conditions as extensible first-class models.**
7. **Physical model/source/constraint composition.**
8. **Thermophysical model families rather than constant property dictionaries.**
9. **Modular solver classes.**
10. **Different solver modules per region/component.**
11. **Rich postprocessing/derived quantities as part of a mature domain.**
12. **Deep verification/examples/documentation before claiming maturity.**

---

# 19. What Crafty should explicitly NOT copy

1. OpenFOAM's finite-volume-specific core as Crafty's universal core.
2. GPL implementation code into Crafty source without deliberate legal/licensing decisions.
3. Solver-specific scientific identities.
4. String dictionaries as canonical typed science.
5. CFD concepts as universal physics concepts.
6. A single mesh abstraction tied permanently to FVM.
7. Hundreds of model combinations before a clean capability/validity system exists.

---

# 20. OpenFOAM's role in Crafty remains correct

This study strengthens the existing decision:

```text
Crafty Core
├── Native scientific/numerical capabilities
└── Optional Solver Providers
      └── OpenFOAM CFD
```

OpenFOAM can provide high-fidelity CFD while Crafty owns:

- problem interpretation
- scientific capability planning
- scientific model identity
- realization selection
- cross-domain graph
- validation/UQ/SRIA
- design/optimization
- scientific memory

The OpenFOAM adapter should translate between Crafty's typed realization/field/coupling contracts and an OpenFOAM case/result, rather than exposing OpenFOAM's internal object model throughout Crafty.

---

# 21. Combined architecture lesson after MOOSE + PETSc + OpenFOAM

The three studies now form a useful stack:

```text
MOOSE
→ How to organize extensible physics modules and multiphysics applications

PETSc
→ How to organize reusable numerical solver capabilities

OpenFOAM
→ How to make one domain extremely deep and extensible
```

Crafty's synthesis should be:

```text
Scientific Intent
↓
Capability Graph
↓
Scientific Models
↓
Computational Realizations
↓
Physics Graph
↓
Domain Infrastructure
↓
Shared Numerical Capabilities
↓
Native / Optional Solver Backends
↓
Results
↓
Validity + UQ + SRIA
↓
Design / Scientific Memory
```

---

# 22. Impact on planned milestones

## MODEL0-R

Still strongly supported.

Need model/realization separation before solver/domain expansion.

## CAP0

Must select scientifically compatible implementations, not merely runtime type names.

## MAT0

Should support state-dependent property model families and producer/consumer behavior.

## FIELD0

Becomes even more important. Fields need scientific quantity + units + geometry/boundary context.

## MESH / NUM

Universal topology must remain discretization-neutral; FVM-specific views/adapters can be separate.

## COUPLE0

Must support multi-region/multi-realization systems.

## DOMAIN maturity

OpenFOAM becomes the reference example for what "deep domain" means, not a target feature checklist for the first version.

---

# 23. New candidate invariants from OpenFOAM study

These are study recommendations pending architecture freeze:

### Candidate M

Fields preserve scientific dimensions/units through the model-to-discretization boundary.

### Candidate N

Universal mesh topology/geometry is separate from discretization-specific mesh views.

### Candidate O

A system may use different computational realizations/solvers in different regions/components.

### Candidate P

Physical sources, constitutive behavior and constraints should be composable where scientifically valid rather than creating combinatorial solver classes.

### Candidate Q

Extension points must have distinct semantics; avoid one unrestricted `Plugin` escape hatch.

### Candidate R

Derived geometry/material/operator data must have explicit dependency/invalidation semantics.

---

# 24. Recommended next study

# **preCICE**

Reason:

MOOSE and OpenFOAM demonstrate coupling, but preCICE specializes in coupling independent simulation codes.

The next study should focus on:

- solver adapters
- coupling participants
- data transfer
- mesh mapping
- time windows
- explicit vs implicit coupling
- convergence
- acceleration
- checkpoint/rollback
- heterogeneous solver independence

This directly informs `COUPLE0` and may be one of the most important studies for Crafty's cross-domain advantage.

No OpenFOAM implementation code has been copied into Crafty.
