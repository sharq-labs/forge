# D0 — General Design & Discovery Contracts V0.1 preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Starting stable checkpoint: `d3d5d4c23b2cd9d04ee19bf123b2c26403627087` (K4 PASS/FROZEN)

## Purpose

Introduce the smallest domain-neutral design layer needed to represent many candidate scientific systems without turning any product class (drone, HVAC, aircraft, reactor, biology, etc.) into platform architecture.

D0 is representation and lineage only. It does **not** implement a search algorithm, optimizer, domain pack, system pack, physics model, solver, LLM planner, or discovery policy.

## Architectural boundary

The design layer may depend on existing domain-neutral Scientific Core contracts such as:

- `ScientificVariable`
- typed `ScientificValue`
- `Quantity`
- `TwinReference`
- deterministic serialization and scientific errors

The design layer must not import or branch on:

- any concrete domain under `engcore.domains`
- any future system pack such as drone/HVAC/aircraft
- SRIA campaign semantics
- a concrete optimizer backend
- an LLM provider
- web/API/database frameworks

A drone or HVAC implementation must be deletable without changing D0.

## Scientific Twin relationship

A design candidate is not a replacement for a Scientific Twin.

- `ScientificTwin` answers: **what exact scientific system instance is this?**
- `DesignSpace` answers: **what declared choices may vary?**
- `DesignCandidate` answers: **which exact choices identify this candidate, and which Twin represents it?**

Every scored design candidate in D0 must bind an exact `TwinReference`. Candidate lineage and Twin lineage are related but distinct records and must not be conflated.

## Scope frozen for D0

### 1. Design-space reference

A stable `(space_id, version)` reference with deterministic serialization.

### 2. Design space

An immutable, versioned declaration built from existing `ScientificVariable` records.

Requirements:

- every variable must have role `DESIGN`;
- variable names must be unique;
- continuous, integer, categorical and boolean kinds must be representable;
- candidate assignment validation is exact: no missing variables and no undeclared extra variables;
- values must use the existing typed `ScientificValue` union;
- continuous values must be `Quantity` and satisfy dimensional/bound checks;
- integer values must be `IntegerValue` and satisfy declared numeric bounds when present;
- categorical values must be `CategoricalValue` and belong to the declared categories;
- boolean values must be `BooleanValue`;
- no raw Python scientific primitives are accepted as candidate values;
- optional constraint references may be carried as identifiers, but D0 does not invent or execute domain constraints.

### 3. Design candidate

An immutable candidate record containing:

- stable candidate id;
- exact `DesignSpaceReference`;
- exact `TwinReference`;
- typed assignments;
- generation number;
- zero or more parent candidate references;
- an explicit generation/operator label;
- deterministic metadata serialization.

D0 candidate construction must not imply that the candidate is feasible, optimal, validated, adequate or true.

### 4. Fidelity declarations

A domain-neutral fidelity ladder may declare ordered rungs by stable id/rank and required capability identifiers.

D0 must not hard-code meanings such as CFD, FEA, fast, deep validation, drone, thermal or any specific solver. Concrete system/domain layers map their own scientific meaning onto the generic rung declarations.

## Explicitly deferred

The following are successor milestones, not D0 acceptance requirements:

- mixed-variable optimizer encoding/search;
- conditional-variable activation rules;
- candidate population generation;
- Sobol/LHS/Bayesian/evolutionary search;
- Pareto archives;
- component elite archives;
- novelty/failure archives;
- compatibility graphs;
- recombination operators;
- multi-fidelity escalation policy;
- Scientific Design Memory;
- SRIA integration;
- any drone/HVAC/aircraft system pack.

## Acceptance criteria

### A1 — domain neutrality

`engcore.design` contains no concrete domain/system/product imports or product-specific conditionals.

### A2 — reuse scientific types

No duplicate unit system or parallel primitive-value model is introduced. Design assignments reuse `ScientificVariable`, `ScientificValue`, `Quantity` and `TwinReference`.

### A3 — four design kinds represented

Continuous, integer, categorical and boolean variables can all be represented and validated structurally without claiming that every optimizer can search them.

### A4 — exact assignment validation

Missing variables, undeclared extras, wrong typed value kinds, out-of-bound continuous/integer values, and invalid categories fail closed.

### A5 — candidate/Twin identity boundary

Every `DesignCandidate` binds one exact `TwinReference`; a candidate record itself is not treated as a Twin, solver result, evidence or validation claim.

### A6 — lineage deterministic

Candidate parent references, generation and operator are explicit, immutable and deterministic under serialization round-trip.

### A7 — fidelity generality

Fidelity declarations are ordered and deterministic but contain no domain/product-specific semantics.

### A8 — no scientific-status inflation

D0 exposes no field or helper that silently marks a candidate feasible, adequate, validated, experimentally validated, optimal or true.

### A9 — deterministic round-trip

All new persistent contracts serialize deterministically and round-trip without type loss.

### A10 — regression safety

Targeted D0 tests pass and the full repository regression remains green. Frozen K1/K1.5/K2/Twin/K3/K3.1/K4 semantics are untouched.

## Failure policy

If a concrete future use case cannot be expressed cleanly, D0 is extended only through a successor contract/milestone. We do not insert product-specific exceptions into the general layer after observing a drone/HVAC/etc. implementation.
