# D2 — Mixed-Variable Candidate Generation V0.1 preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Starting stable checkpoint: `6de57f3e8c3602087a2f81911df82613fb373b97` (D1 PASS/FROZEN)

## Purpose

Add the smallest domain-neutral generation layer that can turn a frozen D0 `DesignSpace` into a deterministic initial population of typed design proposals, materialize each accepted proposal as an exact candidate `ScientificTwin`, and emit D0/D1 `DesignCandidate` / `DesignPopulation` records.

D2 is the first milestone that **creates candidate populations**. It is not an optimizer, adaptive search policy, recombination engine, system pack, solver, LLM planner, or scientific validation engine.

The practical target is to support generation of hundreds or thousands of structurally valid mixed-variable candidates while preserving exact scientific typing and explicit system-owned constraints.

## Architectural boundary

D2 may depend on frozen domain-neutral contracts from D0/D1 and the Scientific Core:

- `DesignSpace` / `DesignSpaceReference`
- `DesignCandidate` / `DesignCandidateReference`
- `DesignPopulation`
- `ScientificVariable` / `VariableKind`
- typed `ScientificValue`
- `Quantity`, `IntegerValue`, `CategoricalValue`, `BooleanValue`
- `ScientificTwin` / `TwinKind`
- deterministic serialization / scientific errors

D2 must not import or branch on:

- concrete `engcore.domains` packages;
- any drone/HVAC/aircraft/reactor/biology/system pack;
- SRIA campaign policy;
- a concrete optimizer backend;
- an LLM provider;
- web/API/database frameworks.

A future multirotor or HVAC system pack must be removable without modifying D2.

## Relationship to the existing optimizer adapter

The existing Scientific Core `CandidateCodec` remains frozen and continuous-only. D2 must **not** silently widen or rewrite that frozen adapter.

D2 introduces a separate generation-time mixed-variable mapping because representable mixed design variables need initial-population generation before a future mixed-variable optimizer exists.

This does not claim that the current optimizer backend can optimize categorical/integer/boolean variables.

## Scope frozen for D2

### 1. Candidate generation plan

A persistent immutable `CandidateGenerationPlan` declares:

- exact population id;
- exact `DesignSpaceReference`;
- requested accepted candidate count;
- generation number, restricted to generation zero in D2 V0.1;
- deterministic sequence start index;
- explicit finite attempt budget;
- explicit generation strategy identifier;
- optional candidate-id prefix.

Only one baseline strategy is required in D2: a deterministic unscrumbled Halton low-discrepancy sequence (`halton_v1`).

No claim is made that Halton is globally optimal for every future design space.

### 2. Searchability rules for the four represented variable kinds

D2 must generate all four D0 variable kinds without converting them to raw Python scientific values.

#### Continuous

- requires finite lower and upper bounds;
- generated value is `Quantity` in the variable's declared unit;
- mapping remains inside the declared bounds.

#### Integer

- requires finite lower and upper bounds;
- lower and upper must be exactly integer-valued after normalization;
- the variable unit must be dimensionless because `IntegerValue` is an exact unitless count/index contract;
- generation covers the inclusive integer domain without rounding an arbitrary physical quantity.

#### Categorical

- uses the declared category vocabulary;
- unit must be dimensionless;
- bounds must not be supplied because ignoring numeric bounds on a categorical value would be unsafe.

#### Boolean

- generates `BooleanValue`;
- unit must be dimensionless;
- bounds must not be supplied.

D2 refuses a design space that is representable by D0 but not safely searchable under these V0.1 generation rules.

### 3. Candidate proposal

Before a system-specific Twin exists, D2 may represent a typed `CandidateProposal` containing:

- deterministic candidate id;
- exact `DesignSpaceReference`;
- source sequence index;
- exact typed assignments;
- strategy id;
- deterministic assignment digest.

A proposal is not yet a `DesignCandidate`, not evidence, not feasible, and not scientifically validated.

### 4. Explicit constraint/admission boundary

D0 `constraint_refs` remain opaque identifiers. D2 must never interpret their scientific meaning.

If a `DesignSpace` declares constraint references, generation must fail closed unless the caller supplies a runtime domain/system-owned proposal gate declaring the **exact same constraint-reference set**.

The gate returns an explicit accept/reject decision. Rejections require non-empty reasons.

D2 may resample after rejected proposals until the accepted target count is reached or the explicit attempt budget is exhausted.

D2 does not treat a proposal-gate acceptance as physical truth, validation, safety, model adequacy, or experimental evidence. It means only that the caller-declared generation/admission rules accepted that proposal.

### 5. Scientific Twin materialization boundary

The general design layer cannot invent system-specific models or Twin declarations.

D2 therefore requires a caller-supplied domain/system `TwinMaterializer` protocol that turns an accepted `CandidateProposal` into a concrete `ScientificTwin`.

D2 must verify that:

- the materializer returns a `ScientificTwin`;
- the Twin kind is `CANDIDATE`;
- Twin references are unique within the generated batch;
- a deterministic D2 generation-binding record is attached to the returned Twin metadata, containing candidate identity, design-space identity, source sequence index, strategy id, and assignment digest.

The binding proves internal generation identity. It does **not** prove that the system pack's scientific model/declaration mapping is physically correct; that remains system/domain validation work.

### 6. Initial `DesignCandidate` / `DesignPopulation` materialization

Every accepted/materialized proposal becomes a D0 `DesignCandidate`:

- same deterministic candidate id;
- exact design-space reference;
- exact materialized Twin reference;
- exact typed assignments;
- generation zero;
- no parents;
- explicit generation operator.

The resulting D1 `DesignPopulation` contains exactly those candidate references and generation zero.

### 7. Duplicate prevention and finite discrete spaces

D2 must not silently emit duplicate typed assignment sets in one generated population.

For a fully discrete design space, D2 should determine the exact finite cardinality and fail before generation when the requested unique population exceeds that cardinality.

For rejected/duplicate proposals during generation, the attempt budget is authoritative. Exhaustion fails closed rather than returning a smaller population while claiming success.

### 8. Determinism

For the same:

- D2 implementation;
- design-space declaration;
- generation plan;
- proposal gate behavior;
- Twin materializer behavior;

the generated proposal sequence, accepted sequence indices, candidate ids and assignment digests must be deterministic.

D2 does not claim cross-version cryptographic reproducibility of arbitrary caller code.

## Explicitly deferred

The following are successor milestones, not D2 V0.1 acceptance requirements:

- conditional-variable activation/deactivation;
- adaptive generation based on D1 evaluations;
- Bayesian/evolutionary/mixed-variable optimization;
- Sobol/LHS strategy portfolio;
- component compatibility graphs;
- recombination / mutation operators;
- novelty search;
- uncertainty-directed generation;
- multi-fidelity promotion policy;
- Scientific Design Memory;
- SRIA integration;
- any concrete system pack;
- generation of derived candidates with parent lineage;
- proof that a system pack materialized the scientifically correct Twin equations/models;
- cryptographic artifact/evidence authenticity.

## Acceptance criteria

### A1 — domain neutrality

D2 contains no concrete product/domain imports or product-specific branches.

### A2 — frozen adapter protection

The existing Scientific Core `CandidateCodec` remains unchanged and continuous-only; D2 does not retrofit mixed-variable behavior into a frozen scientific milestone.

### A3 — four-kind mixed generation

Continuous, integer, categorical and boolean assignments are generated as the existing typed scientific values and pass `DesignSpace.validate_assignments(...)`.

### A4 — searchability fails closed

Unsafe/undefined V0.1 generation spaces fail explicitly: unbounded continuous/integer variables, non-integer integer bounds, dimensional discrete variables, or numeric bounds on categorical/boolean variables.

### A5 — deterministic low-discrepancy baseline

`halton_v1` deterministically maps source sequence indices to valid typed assignments without hidden random state.

### A6 — explicit constraints

Declared `constraint_refs` are never ignored and never interpreted by D2. Exact constraint-reference agreement with a caller-supplied gate is required before constrained generation.

### A7 — no status inflation

Proposal acceptance means only admission by the explicit gate. D2 never calls an accepted proposal feasible, validated, adequate, safe, optimal or true.

### A8 — exact Twin binding

Every emitted `DesignCandidate` references a concrete unique `ScientificTwin(kind=CANDIDATE)` materialized by caller-owned system logic and carrying D2's deterministic generation binding.

### A9 — population exactness

Successful generation returns exactly the requested number of unique candidates, and the D1 population membership exactly matches them. Attempt-budget exhaustion fails closed.

### A10 — duplicate/cardinality safety

Duplicate typed assignments are not emitted. Fully discrete over-requested populations fail before pretending sufficient unique designs exist.

### A11 — deterministic persistent records

Generation plans and proposals serialize deterministically and round-trip without scientific type loss.

### A12 — practical population test

A domain-neutral synthetic test generates at least 1000 mixed typed candidates, all assignment-valid and identity-unique, without changing scientific semantics.

### A13 — regression safety

Targeted D2 tests pass and the full repository regression remains green. Frozen K1/K1.5/K2/Twin/K3/K3.1/K4/D0/D1 semantics remain untouched.

## Failure policy

If the first real system pack reveals a missing topology/conditional/compatibility concept, add it through a successor milestone. Do not insert system-specific exceptions into D2 after observing a concrete product implementation.
