# Open-Source Architecture Study 06 — OpenMDAO + Modelica/OpenModelica

**Purpose:** Learn multidisciplinary system composition, coupled-system solving, component interfaces, acausal modeling and optimization architecture relevant to Crafty SYSTEM0, PhysicsGraph and DISCOVERY0.  
**Projects studied:** OpenMDAO and Modelica/OpenModelica ecosystem  
**Study date:** 2026-09-02  
**Mode:** Read-only architecture study

---

# 1. Why these projects matter

OpenMDAO and Modelica attack system composition from different directions.

OpenMDAO is strong at:

- multidisciplinary decomposition
- explicit/implicit components
- data connections
- hierarchical groups
- coupled nonlinear solving
- derivative propagation
- design variables / objectives / constraints
- optimization

Modelica is strong at:

- reusable physical components
- first-principles equation modeling
- acausal connections
- physical connectors/ports
- events/state
- multi-domain component libraries

Together they are highly relevant to Crafty's long-term goal of composing systems such as HVAC, motors, batteries and aircraft from reusable physics/components.

---

# 2. OpenMDAO lesson: a system is a graph of components

OpenMDAO decomposes a model into Components and Groups. Outputs from one component connect to inputs of another.

The framework then solves the overall coupled model and can optimize across it.

## Crafty lesson

This supports a future `SystemGraph` / `PhysicsGraph` where nodes remain modular.

However Crafty connections must carry more scientific semantics than ordinary data flow.

Future edge semantics should include:

```text
Scientific quantity
unit/dimension
state/time semantics
field/scalar structure
validity
mapping/coupling realization
```

---

# 3. Units-aware connections are valuable

OpenMDAO can automatically convert compatible units when connecting variables.

## Crafty lesson

Crafty's existing unit system should remain active through SYSTEM0 and coupling layers.

A connection should fail if scientific dimensions are incompatible.

Automatic conversion is acceptable only after dimensional compatibility is established and the conversion is explicit in provenance.

---

# 4. Cyclic dependencies require solver policy

OpenMDAO requires nonlinear solvers when components have cyclic dependencies and supports solver configuration at multiple hierarchy levels.

Example concept:

```text
A → B
↑   ↓
└── C
```

cannot be executed as a simple topological one-pass graph.

## Crafty lesson

The future compiler from PhysicsGraph to ExecutionPlan must detect:

```text
acyclic dependencies
cyclic coupled blocks
implicit subsystems
```

and choose/require an appropriate coupled execution realization.

This aligns with preCICE coupling loops and PETSc nonlinear hierarchy.

---

# 5. Hierarchical solvers are useful

OpenMDAO lets solver policies exist at different hierarchy levels.

## Crafty lesson

Complex systems may require nested execution policies:

```text
Vehicle System
├─ Battery thermal/electrical coupled block
│   └─ own convergence
├─ Motor EM/thermal coupled block
│   └─ own convergence
└─ Vehicle-level energy loop
    └─ outer convergence/control
```

The PhysicsGraph should be able to compile into hierarchical execution blocks rather than one global flat loop.

---

# 6. Explicit vs implicit components

OpenMDAO distinguishes components where outputs are directly computable from inputs from components requiring residual equations/convergence.

## Crafty lesson

This maps well to computational realization categories.

Possible future execution semantics:

```text
ExplicitRealization
output = f(input)

ImplicitRealization
R(state, input) = 0
```

This distinction can help the planner construct execution blocks.

It must not replace the broader MODEL0-R formulation enum; it is execution semantics within/under realizations.

---

# 7. Design variables, objectives and constraints belong above the simulation graph

OpenMDAO makes design variables/objectives/constraints first-class for multidisciplinary optimization.

Crafty already has richer Design/Discovery infrastructure.

## Crafty synthesis

Do not merge scientific simulation topology and optimization semantics.

Preferred:

```text
Simulation Model / PhysicsGraph
↓ exposes
Quantities / Metrics / Design Parameters
↓
Design Study
├─ design variables
├─ objectives
├─ constraints
└─ optimizer / discovery policy
```

This lets the same physical system support many different design studies without redefining its physics.

---

# 8. Derivatives across systems are strategic

OpenMDAO emphasizes efficient analytic/total derivatives for large design spaces.

## Crafty lesson

Future numerical/domain contracts should preserve derivative/sensitivity capabilities through composition.

A provider could advertise:

```text
supports:
- local_jacobian
- parameter_sensitivity
- adjoint
- automatic_differentiation
```

The Design Engine could exploit these when available while retaining gradient-free options.

---

# 9. Modelica lesson: physical connections can be acausal

Modelica supports equation-based acausal component connections.

Instead of every component declaring a fixed computational direction, connected equations are flattened and the simulation environment determines how to solve the combined equation system.

## Major Crafty lesson

Do not force every scientific relationship into an input→output causal pipeline at model-definition time.

Some physical relationships are naturally constraints/equations.

Example electrical connector:

```text
voltage compatibility
+
current conservation
```

Rather than deciding in advance which component "produces" voltage and which "consumes" it.

---

# 10. But Crafty should support both causal and acausal composition

OpenMDAO is largely explicit data-flow/component oriented; Modelica highlights acausal physical composition.

Crafty needs both.

Candidate future port/connection semantics:

```text
Causal Port
- explicit provider/consumer direction

Physical Connector
- effort/potential variables
- flow variables
- connection equations

Constraint Interface
- shared equations/compatibility conditions
```

This is especially important for:

- electrical systems
- mechanical connections
- hydraulic systems
- thermal networks

---

# 11. Modelica connector semantics are stronger than variable-name matching

Modelica connectors encode physical interaction semantics, including potential/flow-style relationships in standard physical libraries.

## Crafty lesson

`SYSTEM0` should not merely define:

```text
port: dict[str, float]
```

Instead future ports should be typed by interaction semantics.

Example concept:

```text
ElectricalPin
├─ electric potential
└─ electric current (flow)

ThermalPort
├─ temperature
└─ heat flow

MechanicalTranslationalPort
├─ position/velocity context
└─ force
```

But these domain connector types belong in domain packs built on generic connector contracts, not hard-coded in universal core.

---

# 12. Components should be reusable independent of system context

Modelica's component/library philosophy encourages reusable models that can be connected in different systems.

## Crafty lesson

A compressor, heat exchanger or motor component pack should not know the entire HVAC/vehicle system.

Preferred dependency direction:

```text
Reusable Component
↓ used by
System Pack
↓ configured by
Study
```

not:

```text
Component imports whole system/application
```

---

# 13. Flattening / compilation is an important systems lesson

Modelica environments translate hierarchical component models into a flattened system of equations for simulation.

## Crafty adoption candidate

Crafty should consider a compile phase:

```text
SystemGraph
+ component models
+ connections
+ capabilities
↓
Resolved Scientific Graph
↓
Realization Selection
↓
Equation/Coupling Graph
↓
Executable Plan
```

This is preferable to having each component imperatively call neighboring components.

---

# 14. Events are first-class in physical-system modeling

Modelica has explicit event semantics where continuous integration may stop when conditions change and discrete updates occur.

## Crafty lesson

STATE0/SIM0 eventually need hybrid continuous/discrete simulation semantics.

Important future systems include:

- controls
- switches
- thermostats
- failure events
- contact transitions
- phase transitions
- mode changes

A universal simulation runtime that only supports smooth time integration will be insufficient.

---

# 15. Initialization deserves separate semantics

Equation-based system models often require initialization constraints distinct from normal-time equations.

## Crafty lesson

Future state/runtime contracts should distinguish:

```text
Initial Conditions
Initialization Constraints
Runtime Equations
Event Reinitialization
```

Do not hide all initialization inside a solver-specific setup callback.

---

# 16. System composition vs scientific capability planning

Neither OpenMDAO nor Modelica alone performs Crafty's intended automatic scientific capability planning.

They typically assume the model/component network has already been constructed.

Crafty's differentiating layer can sit above them conceptually:

```text
User Objective
↓
Capability Planner
↓
Select scientific models/components
↓
Construct System/Physics Graph
↓
Compile/solve
```

This is one of the strongest arguments for continuing CAP0.

---

# 17. What Crafty should adopt from OpenMDAO

1. Hierarchical component/group graph.
2. Explicit connections with units.
3. Cyclic-dependency detection requiring solver policy.
4. Nested nonlinear/linear solver hierarchies.
5. Explicit vs implicit execution semantics.
6. Design variables/objectives/constraints above simulation components.
7. Efficient derivative propagation as a future capability.
8. Same simulation model reusable across multiple optimization studies.

---

# 18. What Crafty should adopt from Modelica

1. Equation-based first-principles component modeling.
2. Acausal physical connections.
3. Typed physical connectors.
4. Component reuse and libraries.
5. Hierarchical model flattening/compilation.
6. Explicit state/event semantics.
7. Initialization distinct from normal-time execution.
8. Multi-domain component composition as a native concept.

---

# 19. What Crafty should NOT copy directly

1. Do not build a new Modelica language before universal Crafty contracts are stable.
2. Do not force all components into acausal equation flattening; external solvers and black-box realizations require causal interfaces too.
3. Do not make OpenMDAO-style variable connections the only coupling mechanism.
4. Do not make system component classes carry scientific validity implicitly.
5. Do not merge optimization objectives into scientific model identity.
6. Do not create a huge standard component library before the core composition architecture is proven.

---

# 20. Candidate SYSTEM0 architecture after this study

Future candidate only:

```text
SystemDefinition
├─ Components
├─ Interfaces / Ports
├─ Connections
├─ Environment
└─ System Constraints

ComponentInstance
├─ component/model identity
├─ parameters
├─ state
├─ exposed capabilities
└─ ports

Port
├─ interaction type
├─ quantities
├─ causal/acausal semantics
└─ compatibility rules

Connection
├─ endpoints
├─ scientific compatibility
├─ connection equations OR transfer semantics
└─ coupling realization if needed
```

---

# 21. Candidate graph compilation architecture

```text
Scientific Intent
↓
Capability Planner
↓
System Builder
↓
SystemGraph
↓
Connection/Equation Resolution
↓
PhysicsGraph
↓
Realization Selection
↓
Coupled Blocks / Dependency Analysis
↓
ExecutionPlan
```

This combines lessons from OpenMDAO, Modelica, preCICE and MOOSE.

---

# 22. New candidate invariants

### Candidate AD

Scientific system topology is separate from any particular optimization study.

### Candidate AE

Crafty must support both causal dataflow interfaces and acausal physical/constraint connections.

### Candidate AF

Components expose typed physical interaction ports rather than unstructured dictionaries.

### Candidate AG

Hybrid continuous/discrete events must remain representable in future state/runtime architecture.

### Candidate AH

System composition should compile to an executable graph; components should not imperatively orchestrate their neighbors.

### Candidate AI

Design variables/objectives/constraints belong to Study/Design layers, not scientific model identity.

---

# 23. Overall lesson

OpenMDAO shows how to solve and optimize multidisciplinary graphs efficiently.

Modelica shows how to describe reusable first-principles physical systems without forcing arbitrary computational causality too early.

Crafty should combine these lessons with its unique layers:

```text
Scientific Capability Planning
+
Validity-aware Model / Realization selection
+
Causal & Acausal System Composition
+
Numerical/Coupling runtime
+
UQ + SRIA
+
Design / Scientific Memory
```

No OpenMDAO, Modelica or OpenModelica implementation code has been copied into Crafty.
