# Engineering Design Synthesis and Assembly Architecture

> **Status:** strategic architecture direction; NOT IMPLEMENTED.
>
> **Purpose:** define how Forge evolves from analysis of an existing engineered
> system into generation of buildable candidate products and assemblies, while
> continuing to use mature open-source computational providers rather than
> recreating CAD kernels, solvers, component databases or optimization engines.
>
> **Current execution boundary:** this document does not start BIG 14 or add
> production contracts. BIG 14/15 remain review, hardening, full verification,
> mutation and recertification work.

## 1. Goal

Forge must eventually support this bounded engineering loop:

```text
engineering intent / requirements
        ↓
formal objectives + constraints + operating envelope
        ↓
system architecture / product template
        ↓
design space + topology choices
        ↓
parametric geometry / CAD
        ↓
assembly synthesis
        ↓
standard-component selection + custom-part generation
        ↓
joints / interfaces / fits / routing / serviceability
        ↓
physics model graph + solver plan
        ↓
multi-fidelity design campaign
        ↓
reliability / lifecycle / manufacturing / cost
        ↓
candidate engineering designs
        ↓
experiment / validation
```

A design is not considered buildable merely because a mesh solves or a geometric
solid can be rendered.

## 2. CapabilityPack vs SystemPack

Forge should keep reusable engineering science separate from products.

A **CapabilityPack** owns reusable physics/engineering capability such as
thermal, CFD, structural, electromagnetics, electrical, battery, combustion,
multibody dynamics, controls, vehicle dynamics, flight dynamics or lifecycle.

A **SystemPack** / **ProductTemplate** composes those capabilities into an
engineered product such as an electric motor, robot arm, HVAC unit, drone,
vehicle, pump or aircraft subsystem.

Product-specific names must not leak into frozen Scientific Core.

## 3. Parametric geometry is not mesh

Forge's existing field/mesh semantics are necessary for analysis but are not a
substitute for product geometry.

The design-synthesis layer must represent:

- parametric dimensions;
- topological alternatives;
- regions, interfaces and mating surfaces;
- reference frames and datum features;
- materials and manufacturing process constraints;
- geometry identity/version;
- CAD-provider provenance;
- conversion to analysis meshes without losing the design identity.

Prefer mature open-source CAD/geometry providers where appropriate. Forge should
own the contracts, not a new CAD kernel.

## 4. Assembly is first-class

A product is an assembly graph, not a bag of isolated solids.

Forge must be able to represent components, interfaces and assembly relations,
including at least:

- bolts, screws, nuts and washers;
- pins and retaining features;
- shafts, keys and splines;
- bearings and bushings;
- gears, belts, chains and couplings;
- springs and dampers;
- seals and gaskets;
- linear guides;
- welds, bonded joints, snap-fits and press-fits;
- motors, gearboxes, actuators, sensors and encoders;
- electrical connectors;
- cable, hose and pipe routing;
- lubrication requirements;
- mechanical stops and safety clearances.

The assembly graph must carry exact component/interface identities and be
replayable as part of the candidate design identity.

## 5. Standard components vs custom parts

Forge must not generate a custom part when a suitable catalog/standard component
is the more appropriate engineering choice.

A standard-component record should be able to carry:

- manufacturer / standard / part number identity where applicable;
- geometry and interface dimensions;
- material;
- ratings and admissible operating envelope;
- radial/axial/torque/speed/temperature limits as applicable;
- tolerance / fit requirements;
- mass;
- cost or cost status;
- availability/source status;
- source/provenance;
- uncertainty where known;
- lifecycle/reliability model or an explicit UNKNOWN.

Candidate selection must never silently invent a rating, tolerance, availability,
cost or lifetime.

Custom parts may be synthesized when needed, but their manufacturability,
tolerances and interfaces must be explicit.

## 6. Joint and interface engineering

Assembly synthesis must model engineering meaning, not only CAD contact.

Examples include:

- fastener preload, clamp load, slip and fatigue;
- threaded engagement and locking method;
- bearing radial/axial load, speed, lubrication and life;
- shaft torsion/bending and critical sections;
- key/spline torque transfer;
- gear ratio, backlash, tooth/contact load and efficiency;
- press-fit/interference and clearance fits;
- weld load path and fatigue where modeled;
- bonded-joint area/environment/applicability;
- alignment and allowable misalignment;
- connector mating and retention;
- cable/hose bend radius and routing constraints.

When the required scientific model is unavailable, the interface remains
unsupported/UNKNOWN rather than being reduced to a geometric coincidence.

## 7. Assembly feasibility

Before expensive solver execution, Forge should reject candidates that are
mechanically or operationally impossible using cheap deterministic checks where
possible:

- interference/collision;
- missing mating interface;
- inaccessible fastener/tool path;
- impossible assembly order;
- insufficient clearance;
- impossible bearing/shaft/fit combination;
- routing violation;
- impossible maintenance/removal path;
- unsupported component rating;
- violated manufacturing tolerance/process rule.

These checks are engineering filters, not physical validation.

## 8. Manufacturability and serviceability

A candidate design should eventually carry:

- manufacturing process assumptions;
- minimum feature sizes;
- tooling/access constraints;
- standard stock/material choices;
- geometric and dimensional tolerances;
- fits;
- assembly sequence;
- inspection features;
- maintainability/serviceability;
- replaceable wear components;
- disassembly constraints;
- manufacturing variation distributions when sourced/admitted.

Manufacturing feasibility and low cost do not constitute scientific evidence for
performance.

## 9. High-throughput design campaigns

Assembly constraints participate in the same multi-fidelity campaign as physics.

Example:

```text
1000 generated candidates
        ↓
assembly / geometry / catalog feasibility filters
        ↓
cheap physics models
        ↓
medium-fidelity analysis
        ↓
high-fidelity coupled analysis
        ↓
independent checks
        ↓
prototype / experiment
```

A candidate rejected by an assembly or catalog constraint should not consume an
expensive CFD/FEM/EM solve.

The campaign must preserve the reason for rejection and must not hide negative
results.

## 10. Example — human-like robotic arm

A robotic-arm request should not stop at links and joint coordinates.

A serious candidate may require:

```text
shoulder
├── actuator / motor
├── gearbox
├── shaft
├── bearing pair
├── housing
├── fasteners
├── encoder
├── cable passage
└── mechanical stops

elbow
├── actuator / transmission
├── shaft or pin
├── bearings / bushings
├── housing
├── fasteners
└── routing

wrist
├── compact actuators
├── gears / belts / couplings
├── bearings
├── sensors
├── wiring
└── service clearances
```

The system-level result must connect assembly decisions to mass, inertia, stiffness,
backlash, thermal load, power, control performance, fatigue, serviceability and
lifecycle where those models exist.

## 11. Provider policy

Forge should prefer mature open-source providers for CAD, optimization, dynamics,
component calculations and numerical solving when scientifically and operationally
appropriate.

Before implementing a new computational engine, record:

1. whether a mature open-source project already solves it;
2. the project's scientific/engineering maturity;
3. automation/API suitability;
4. license/deployment implications;
5. supported capability and applicability envelope;
6. validation/reference routes;
7. whether Forge needs an adapter, a generic contract, or genuinely new computation.

Forge's differentiator is orchestration, scientific identity, applicability,
mechanism reasoning, design synthesis, evidence and discovery—not rewriting mature
engineering software.

## 12. Scientific and engineering guards

1. A standard component is not acceptable merely because its geometry fits.
2. Missing rating/tolerance/life/cost/availability stays UNKNOWN.
3. A CAD-valid assembly is not a mechanically valid assembly.
4. A mechanically feasible assembly is not experimentally validated.
5. Optimization score is not evidence.
6. Low-fidelity acceptance cannot silently replace high-fidelity evidence.
7. A catalog component's source/version/identity must be bound to the candidate.
8. Post-hoc changes to constraints or component choices must remain visible.
9. Failed and rejected candidate designs remain part of discovery memory.
10. Product-specific assembly rules stay outside frozen Scientific Core.

## 13. Definition of success

Forge has a usable design-synthesis/assembly layer when a candidate product can be
traced from:

```text
requirements
 -> system architecture
 -> design variables
 -> geometry/topology
 -> component identities
 -> joints/interfaces/fits
 -> assembly sequence
 -> manufacturing assumptions
 -> model graph
 -> provider executions
 -> UQ / lifecycle / reliability
 -> evidence
```

and when the system can distinguish:

- buildable candidate;
- analysis-only geometry;
- unsupported assembly interface;
- catalog component with insufficient evidence;
- manufacturable but scientifically unvalidated candidate;
- simulated improvement only;
- experimentally validated improvement.
