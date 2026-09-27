# Motion Systems, Multibody Dynamics and Electromechanical Architecture

> **Status:** strategic architecture direction; NOT IMPLEMENTED.
>
> **Scope:** future capabilities for machines whose engineering meaning depends
> on motion, joints, mechanisms, compliance, contact, actuation, sensing,
> control and power/wiring.
>
> **Execution boundary:** this does not start new feature work during BIG 14/15.

## 1. Why this is first-class

A robot arm, vehicle suspension, gripper, machine linkage or drone mechanism is
not adequately represented by static CAD plus stress analysis.

Forge must eventually model the closed engineering loop:

```text
motion requirement / task
        ↓
mechanism topology + DOFs
        ↓
kinematics / trajectory
        ↓
mass + inertia + gravity
        ↓
actuators + transmissions
        ↓
springs / dampers / bushings / flexures
        ↓
friction / backlash / contact
        ↓
sensors + controls
        ↓
electrical / hydraulic / pneumatic supply
        ↓
dynamic response + loads + losses + heat
        ↓
structural / thermal / lifecycle consequences
```

## 2. Kinematics and mechanism topology

Required future contracts include:

- rigid-body links and reference frames;
- generalized coordinates;
- degrees of freedom and constraints;
- revolute, prismatic, spherical, universal and compound joints;
- joint limits and mechanical stops;
- closed-loop mechanisms;
- four-bar linkages;
- slider-crank mechanisms;
- cams and followers;
- rack and pinion;
- gears;
- belts and chains;
- cable/tendon/pulley systems;
- lead/ball screws;
- parallel mechanisms where supported;
- forward and inverse kinematics;
- workspace and singularity checks;
- collision/interference checks;
- prescribed motion and target trajectories.

Kinematic feasibility is not dynamic feasibility and is not validation.

## 3. Multibody dynamics

The dynamic layer must support, through provider-neutral contracts:

- mass and center of mass;
- inertia tensors;
- gravity/body forces;
- external loads;
- position, velocity and acceleration state;
- forward dynamics;
- inverse dynamics;
- joint reactions;
- actuator torque/force requirements;
- transient loads;
- energy/power accounting;
- rigid-body dynamics;
- flexible-body participation only when an admitted model/provider supports it.

A useful canonical relation is the model family represented by:

```text
M(q) q_ddot + C(q, q_dot) q_dot + G(q)
+ F_friction + F_compliance + F_contact
= tau_actuation + tau_external
```

Forge owns the semantic contract and provenance; a mature external provider
should perform the numerical solve where appropriate.

## 4. Compliance, suspension and vibration

Compliant elements are first-class components, not geometry decorations.

Target component/model families include:

- linear and nonlinear springs;
- torsional springs;
- dampers;
- bump stops;
- bushings;
- rubber/elastomer mounts;
- flexures;
- tire/wheel compliance where relevant;
- anti-roll/linked spring mechanisms;
- suspension linkages;
- vibration isolators.

Models may include stiffness, damping, preload, hysteresis, temperature or
frequency dependence only when the selected model/provider and evidence support
those behaviours.

## 5. Friction, backlash and contact

Ideal joints are insufficient for many machines.

Forge should be able to declare, where supported:

- static/dynamic friction;
- stiction;
- rolling/contact friction;
- backlash/deadband;
- bearing/joint compliance;
- impact/contact;
- contact stiffness/damping;
- grasp contact and slip/no-slip evaluation;
- wear/friction feedback into lifecycle state.

Unknown coefficients or unsupported contact regimes remain UNKNOWN/unsupported.

## 6. Actuation and transmission

Motion synthesis should choose or evaluate actuators and transmissions against
the dynamic requirements.

Target families include:

- electric motors;
- linear electric actuators;
- solenoids;
- hydraulic cylinders/motors;
- pneumatic cylinders/motors;
- cable/tendon actuation;
- gearboxes;
- harmonic/planetary/spur/worm reductions where represented;
- belt/chain reductions;
- ball/lead screws;
- clutches/brakes where represented.

An actuator must be evaluated against torque/force, speed, acceleration, duty
cycle, power, thermal limits, efficiency and lifecycle information that is
actually available.

## 7. Electrical power and wiring

Electrical design is more than a circuit diagram and more than a CAD cable
curve.

Future wiring/harness contracts should support, where source data exists:

- conductor material;
- wire/cable type;
- cross-section or gauge;
- strand/construction metadata;
- insulation type and temperature rating;
- voltage/current rating;
- continuous/transient current capacity;
- resistance and voltage drop;
- I2R heating;
- connector identities and ratings;
- fuse/protection device identities;
- harness topology;
- length;
- bend radius;
- routing and clearance;
- strain relief;
- moving-cable/flex requirements;
- mass;
- environmental suitability;
- source/provenance;
- uncertainty/UNKNOWN fields.

A wire that geometrically fits but violates current, thermal, bend-radius or
environmental limits is not an admissible design.

## 8. Sensors and control loops

Motion systems generally close the loop through sensing and control.

Target contracts include:

- encoders and position sensors;
- velocity/acceleration sensing;
- force/torque sensing;
- motor current sensing;
- controller sample/update rate;
- reference trajectories;
- feedback/feedforward control;
- saturation and actuator limits;
- tracking error;
- stability/performance evidence appropriate to the model;
- delays and filtering where modeled.

Control simulation does not prove real hardware stability outside the model's
applicability/evidence envelope.

## 9. Coupled electromechanical behaviour

A motor should not be reduced to an ideal torque source when the selected
fidelity requires electrical/thermal feedback.

Target coupling may include:

```text
voltage
 -> current
 -> electromagnetic torque
 -> speed
 -> back-EMF
 -> current change

current
 -> electrical loss
 -> heat
 -> resistance / material-state change
 -> future electrical behaviour
```

Likewise, mechanical load affects actuator current and temperature; temperature
and degradation may affect available torque, efficiency, insulation or bearing
life.

## 10. Human-like robotic arm example

A future request such as:

```text
Design a human-like arm with a specified reach, payload,
motion speed, accuracy, mass and lifetime.
```

should decompose into:

```text
task / motion envelope
 -> shoulder/elbow/wrist DOFs
 -> mechanism topology
 -> link geometry + mass/inertia
 -> actuator candidates
 -> gearbox/transmission candidates
 -> shafts/bearings/fasteners
 -> springs/dampers/compliance if useful
 -> sensors
 -> wiring/harness
 -> controller
 -> inverse kinematics
 -> inverse dynamics
 -> transient multibody simulation
 -> structural/thermal/lifecycle checks
 -> contact/grasp checks if needed
 -> multi-fidelity design campaign
```

The design search may explore different mechanisms and actuator arrangements,
not only different dimensions of one frozen topology.

## 11. Vehicle suspension example

A suspension candidate may require a system model containing:

```text
road input
 -> tire/wheel
 -> knuckle
 -> control arms / links
 -> bushings
 -> spring
 -> damper
 -> anti-roll coupling
 -> chassis/body
```

Relevant outputs can include wheel travel, body motion, forces, accelerations,
dynamic tire load, joint/bushing loads, damper/spring work and structural loads,
subject to the fidelity and evidence actually available.

## 12. High-throughput design discovery

Motion-system synthesis must integrate with Forge's future multi-fidelity
campaign engine.

Cheap stages may reject:

- unreachable workspace;
- singular mechanisms;
- impossible joint ranges;
- actuator torque/speed insufficiency;
- component rating violations;
- collisions/interference;
- impossible wiring bend/routing;
- infeasible bearing/shaft loads;
- unstable or clearly infeasible control assumptions where a justified cheap
  model exists.

Only surviving candidates should progress to expensive multibody, FEM, CFD,
electromagnetic or coupled simulations.

## 13. Scientific guards

1. Kinematic feasibility is not dynamic feasibility.
2. Dynamic simulation is not experimental validation.
3. An ideal joint cannot silently substitute for friction/compliance/backlash.
4. An ideal torque source cannot silently substitute for an actuator model at a
   fidelity that claims electrical/thermal behaviour.
5. Missing spring/damper/bushing/contact parameters remain UNKNOWN.
6. Unsupported contact/friction regimes remain unsupported.
7. A control simulation cannot establish real-hardware stability outside its
   applicability/evidence envelope.
8. A wire/harness cannot be admitted only because it fits geometrically.
9. Solver agreement is not truth.
10. Optimization scores are not evidence.

## 13.1 Visualization and transparent/cutaway playback

Motion-system results should be consumable by the global 3D engineering
viewer. A mechanism, suspension, motor, drone or robot may therefore be shown
with transparent housings, section/cutaway geometry, motion playback and
time-synchronized engineering overlays.

For electromechanical systems this may include current, losses, temperature,
RPM, torque, bearing state, conductor/connector limits and other margins.
The viewer may highlight an exceeded applicable limit, but it must never infer
burnout/failure from appearance alone.

See `docs/architecture/visualization_runtime.md`.

## 14. Definition of success

This layer is usable when Forge can trace a motion-system candidate from:

```text
task / trajectory
 -> mechanism topology
 -> DOFs / constraints
 -> components / joints
 -> mass / inertia
 -> compliance / contact assumptions
 -> actuator + transmission
 -> wiring + power
 -> sensors + control
 -> provider executions
 -> dynamic response
 -> structural / thermal / lifecycle consequences
 -> uncertainty / evidence
```

and can distinguish an idealized analysis, a feasible candidate, an unsupported
candidate, a simulated improvement and an experimentally validated improvement.
