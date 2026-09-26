# Mechanistic Discovery Architecture

> **Status:** strategic architecture direction; NOT IMPLEMENTED.
>
> **Purpose:** define how Forge should evolve from a simulation/assurance runtime into a
> mechanism-aware scientific discovery system without weakening its existing scientific
> authority rules.
>
> **Current execution boundary:** this document does not start BIG 14 or add production
> contracts. BIG 14/15 remain review, hardening, validation and recertification work.

## 1. Core idea

Forge must not stop at:

```text
input -> solver -> output
```

For discovery, the target is:

```text
cause candidate
    -> declared mechanism
    -> state transition
    -> observable consequence
    -> downstream system consequence
    -> evidence / applicability / uncertainty
```

The solver is a computation provider for a model of a mechanism. It is not the
mechanism itself and it is never scientific authority by virtue of returning a number.

A mechanism-aware result should be able to answer, within the limits of the model and
available evidence:

- what changed;
- which declared mechanism(s) carried the change;
- which state variables changed;
- which equations/models/providers produced the result;
- what assumptions and applicability bounds were active;
- what uncertainty and model discrepancy are known or UNKNOWN;
- what competing explanations remain;
- which variables are controllable interventions;
- which next simulation or experiment could discriminate between hypotheses.

## 2. Scientific authority boundary

Forge must keep three concepts separate:

| Concept | Meaning | What it does NOT prove |
|---|---|---|
| **Dependency** | B numerically or logically depends on A in a declared model/run | that A causes B in the real system |
| **Mechanism** | a declared physical/chemical/engineering model explains how A can affect B under stated conditions | that the mechanism is the unique or true real-world cause |
| **Causal claim** | a claim that changing A would change B in the target system/population/context | it is not granted by a dependency edge, solver run, sensitivity result, correlation or LLM assertion |

Rules:

1. A mechanism explanation is always model-conditioned and applicability-conditioned.
2. Sensitivity is not causality.
3. A simulated intervention is not an experimental intervention.
4. Solver agreement is not causal proof.
5. A residual unexplained by known models is **unexplained**, not evidence that a new
   mechanism exists.
6. Competing mechanisms may remain simultaneously admissible.
7. LLM/planner output may propose hypotheses or structured candidate mechanisms but may
   not grant applicability, causal truth, validation, quantified uncertainty or evidence.
8. UNKNOWN must remain UNKNOWN throughout mechanistic reasoning.

## 3. Proposed generic vocabulary

Names are provisional; the concepts are the requirement.

### 3.1 MechanismDefinition

A reusable scientific definition of a mechanism:

- identity and version;
- typed inputs and outputs;
- state variables read and written;
- governing law/model family;
- parameters and units;
- conservation relations;
- assumptions;
- applicability envelope;
- expected failure/invalid regimes;
- uncertainty and model discrepancy status;
- source/evidence references;
- admissible provider/model realizations.

### 3.2 MechanismInstance

Binds a `MechanismDefinition` to a concrete run context:

- component/system;
- geometry/region;
- materials;
- environment;
- time window;
- lifecycle state;
- model realization;
- provider execution;
- input/output identities.

### 3.3 DependencyEdge

Records that one quantity/state/model consumes another. It carries no causal authority.

### 3.4 StateTransition

Reuses existing Forge state/timeline/lifecycle authority. A mechanism may explain or
predict a transition, but must not create a parallel state authority.

### 3.5 Intervention

A typed proposed change to one or more controllable variables:

- geometry;
- material;
- operating condition;
- controller command;
- environment scenario;
- model parameter where scientifically admissible.

Each intervention must distinguish:

- physically controllable variable;
- merely uncertain parameter;
- calibration parameter;
- fixed context;
- hypothetical/simulated-only intervention.

### 3.6 MechanisticExplanation

A derived, non-authoritative explanation graph for a specific result:

```text
observed/result quantity
  <- state transition
  <- mechanism instance
  <- declared inputs
  <- upstream mechanisms / state / environment / material
```

It must carry the exact run/model/evidence identities from which it was derived.

## 4. Cross-domain requirement

The mechanism vocabulary must work across every current and future domain.

| Domain | Example mechanism chain |
|---|---|
| Battery | reaction/transport -> overpotential -> voltage/heat -> temperature -> degradation |
| Thermal | heat generation -> conduction/convection/radiation -> temperature field -> property change |
| Structural | load/thermal strain -> stress/strain -> deformation -> damage/failure mechanism |
| CFD | pressure/viscous forces -> momentum transport -> flow field -> separation/vortices/losses |
| Chemistry | composition + kinetics + transport -> reaction progress -> species + heat release |
| Thermal-fluid | pressure/enthalpy/mass flow -> component exchange -> heat/work transfer |
| Electrical | voltage/current -> dissipation/field response -> power/losses -> thermal coupling |
| Materials | composition + state + history -> constitutive properties -> domain response |
| Environment | exposure history -> degradation driver -> material/state transition |
| Corrosion | environment + material -> corrosion process -> thickness/property loss |
| Moisture | humidity/exposure -> transport/uptake -> material-state change |
| Lifecycle | accumulated stress/exposure -> damage/degradation -> future physics |
| Electric motor (future) | current -> electromagnetic field -> force/torque -> losses -> heat -> material/state feedback |
| Drone/aircraft (future) | propulsion -> forces/moments -> dynamics -> energy demand -> thermal/structural/lifecycle feedback |

## 5. Discovery capabilities that build on the mechanism layer

| Priority | Capability | Purpose | Scientific guard |
|---|---|---|---|
| P0 | **Mechanism Graph** | represent mechanism-conditioned cause/effect pathways across domains | graph edges are not causal proof |
| P0 | **Intervention Engine** | represent what can actually be changed in a design/system | simulated intervention remains simulation |
| P0 | **Counterfactual Runs** | compare same system under one controlled declared change | counterfactual result is model-conditioned |
| P0 | **Root-Cause Reasoning** | trace failures/results backward through admissible mechanisms | returns candidate explanations, not automatic causal verdict |
| P0 | **Scientific Knowledge Graph** | connect mechanisms, laws, materials, systems and evidence | every scientific edge requires provenance/classification |
| P0 | **Equation/Law Graph** | make laws explicit objects with assumptions and applicability | equations do not gain validity outside their envelope |
| P0 | **Conservation Graph** | connect mass/energy/charge/momentum balances across mechanisms | missing terms stay UNKNOWN, never zero |
| P0/P1 | **Model Discrepancy Representation** | separate model inadequacy from input uncertainty | absence is NOT QUANTIFIED, not zero |
| P1 | **Uncertainty Propagation** | propagate admitted input/model uncertainty through graph | UNKNOWN inputs cannot become quantified by assumption |
| P1 | **Sensitivity Analysis** | identify influential parameters and mechanisms | sensitivity is not causality |
| P1 | **Identifiability Analysis** | determine whether observations can identify parameters/mechanisms | non-identifiable parameters must remain unresolved |
| P1 | **Inverse Problems** | infer candidate parameters/states from observations | posterior/inferred value is not direct measurement |
| P1 | **Calibration** | fit models to calibration data with provenance | calibration and validation data remain separated |
| P1 | **Experimental Evidence Registry** | bind datasets, instruments, conditions and uncertainty to validation | experimental label requires actual experimental provenance |
| P1 | **Automated Experiment Design** | choose experiments that discriminate hypotheses or reduce uncertainty | information value does not equal proof |
| P1 | **Active Learning** | choose the next simulation/experiment by expected information gain | acquisition score is a policy, not evidence |
| P1 | **Hypothesis Engine** | generate explicit, falsifiable hypotheses | hypotheses are not evidence |
| P1 | **Hypothesis Falsification** | design checks intended to reject hypotheses | failed falsification is not automatic confirmation |
| P1 | **Competing Mechanisms** | keep multiple explanations alive until evidence distinguishes them | no forced single explanation |
| P1 | **Evidence Updating** | update support when new admissible evidence arrives | evidence removal cannot increase assurance |
| P1 | **Negative Results as First-Class Evidence** | preserve failures, disagreements and null results | negative execution result still needs evidence classification |
| P1 | **Scientific Search Space** | define controllable variables, bounds and forbidden regions | search space cannot silently widen after results |
| P1 | **Constraint Explanation** | explain which mechanism path contributed to a violated constraint | explanation remains model-conditioned |
| P1 | **Trade-off Graph** | expose performance/mass/temperature/cost/lifetime trade-offs | no hidden scalarization/ranking |
| P1 | **Dimensional Analysis** | use dimensions/Buckingham-Pi to constrain models/search | dimensionally valid does not mean physically valid |
| P1 | **Regime Detection** | identify laminar/turbulent, transport/kinetic-limited, etc. | detection requires declared criteria and applicability |
| P1/P2 | **Lifecycle Mechanism Graph** | connect exposure -> damage -> property change -> later physics | degradation model validity remains explicit |
| P1/P2 | **Multi-Fidelity Modeling** | analytic/reduced/FEM/CFD/experimental fidelity ladder | lower fidelity cannot silently stand in for higher fidelity |
| P2 | **Surrogate Models with Trust Envelopes** | accelerate repeated solves within learned applicability bounds | out-of-distribution use is refused/UNKNOWN |
| P2 | **Differentiable Simulation** | expose gradients where scientifically meaningful | gradient is local model information, not causality |
| P2 | **MDO** | multidisciplinary design optimization over coupled systems | optimum is conditional on objectives/constraints/models |
| P2 | **Robust Design** | optimize under admitted uncertainty/distributional variation | UNKNOWN uncertainty must not be replaced by guessed distributions |
| P2 | **Manufacturing Tolerance Engine** | propagate manufacturing variation into system behavior | tolerances need sourced/declared distributions |
| P2 | **Failure Mechanism Graph** | connect fatigue/corrosion/thermal/electrical failure pathways | failure mechanism claim needs applicability/evidence |
| P2 | **Novelty / Residual Detection** | detect observations not explained by admitted models | residual means unexplained, not novel mechanism proven |
| P2/P3 | **Unknown-Mechanism Discovery** | cluster unexplained residuals and propose testable missing-mechanism hypotheses | proposals remain hypotheses until discriminating evidence |
| P2 | **Scaling-Law Discovery** | infer candidate dimensionless/scaling relations | fitted laws require holdout/validation and regime bounds |
| P2 | **Automatic Model Selection** | select among models using applicability/evidence, not LLM preference | selection policy cannot create evidence |
| P2 | **Model Ensemble Reasoning** | preserve model disagreement instead of hiding it | ensemble consensus is not truth |
| P2 | **Discovery Memory** | retain failed hypotheses, negative results and tested interventions | memory records provenance; repetition avoidance is policy |

## 6. Mechanism-aware discovery loop

Target future loop:

```text
Observation / engineering objective
          ↓
Known mechanisms + current state
          ↓
Uncertainty / contradiction / unexplained residual
          ↓
Competing falsifiable hypotheses
          ↓
Candidate interventions
          ↓
Simulation / multi-fidelity analysis
          ↓
Discriminating experiment if required
          ↓
Admissible evidence
          ↓
Hypotheses rejected / retained / unresolved
          ↓
Knowledge and mechanism records updated
          ↓
New design or next experiment
          ↓
Repeat
```

Forge must be able to stop at any point with:

```text
UNEXPLAINED / INSUFFICIENT EVIDENCE / UNKNOWN
```

rather than inventing a mechanism.

## 7. Example: mechanism-aware motor discovery

A future electric-motor domain should not be a black box mapping voltage/current to
torque. A minimally useful mechanistic representation would include:

```text
electrical input
  -> winding current
  -> electromagnetic field
  -> air-gap force
  -> torque
  -> rotor/shaft dynamics

current
  -> copper loss
  -> heat
  -> winding temperature
  -> resistance change
  -> current/torque feedback

magnetic state + speed
  -> iron/eddy losses
  -> heat

temperature + stress + time
  -> insulation / magnet / bearing degradation
  -> future performance
```

The same design principle applies to batteries, reactors, HVAC, vehicles, drones,
aircraft and every other domain.

## 8. Architecture constraints

The mechanism/discovery layer must:

1. reuse existing Forge timeline, state, lifecycle, provenance, evidence, UQ,
   applicability, result and trust authorities;
2. not create a second ScientificResult, Evidence, Validation or Uncertainty vocabulary;
3. keep domain-specific mechanisms outside frozen Scientific Core unless a generic
   contract is proven necessary;
4. bind every explanation to exact request/model/provider/state/evidence identities;
5. serialize/replay deterministically where the underlying run is replayable;
6. preserve failed and contradictory mechanisms/evidence;
7. keep discovery search policy separate from scientific evidence;
8. make post-hoc hypotheses/criteria visibly post-hoc;
9. refuse unsupported extrapolation;
10. keep mechanism definitions provider-neutral where possible.

## 9. Proposed implementation order

This is a future roadmap after the current BIG 14/15 review and hardening campaign.

### Discovery Foundation A — Mechanism semantics

- inventory existing domain laws/state transitions before creating contracts;
- define dependency vs mechanism vs causal-claim semantics;
- prototype `MechanismDefinition`, `MechanismInstance`, `DependencyEdge` and
  `MechanisticExplanation`;
- prove them on existing battery, thermo-mechanical, CFD and chemistry flagships;
- no discovery search yet.

### Discovery Foundation B — Interventions and counterfactuals

- typed controllable/fixed/uncertain variables;
- counterfactual run identity;
- one-change and multi-change intervention records;
- root-cause candidate tracing;
- negative controls.

### Discovery Foundation C — UQ, sensitivity and identifiability

- quantified uncertainty only from admitted distributions/measurements/models;
- model discrepancy representation;
- global/local sensitivity;
- identifiability;
- inverse/calibration workflows with calibration/validation split.

### Discovery Foundation D — Hypotheses and experiments

- explicit hypothesis records;
- competing mechanisms;
- falsification criteria;
- experiment-design objectives;
- active-learning policy;
- experimental evidence registry.

### Discovery Foundation E — Design discovery

- multi-fidelity execution;
- trustworthy surrogates;
- robust/MDO search;
- scaling-law candidates;
- residual/novelty detection;
- discovery memory.

## 10. Definition of success

Forge becomes mechanism-aware only when a result can be traced as:

```text
result
 -> state transition(s)
 -> mechanism instance(s)
 -> model/law
 -> assumptions/applicability
 -> material/environment/time context
 -> provider execution(s)
 -> uncertainty/model discrepancy
 -> evidence
```

and the system can distinguish all of these outcomes:

- mechanism supported for this bounded context;
- mechanism computationally exercised but not validated;
- competing mechanisms unresolved;
- intervention improved the simulated objective only;
- result sensitive to a parameter but causality not established;
- observation unexplained by admitted mechanisms;
- evidence insufficient;
- applicability UNKNOWN;
- uncertainty UNKNOWN.

That distinction is a prerequisite for scientific discovery, not a presentation feature.
