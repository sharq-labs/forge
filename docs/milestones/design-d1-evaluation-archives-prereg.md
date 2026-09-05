# D1 — Design Evaluation, Population and Selection Archives V0.1 preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Starting stable checkpoint: `15b6002bdb924a3ddae32ba507a4138495a4bc5b` (D0 PASS/FROZEN)

## Purpose

Add the smallest domain-neutral layer that can take many D0 design candidates, bind each evaluated candidate to attributable scientific output, and preserve more than one kind of success without collapsing a design study to one scalar winner.

D1 is the bridge from **candidate identity** to **evidence-bearing evaluation and deterministic archives**. It is not yet a candidate generator, optimizer, system pack, solver, LLM planner, autonomous discovery policy or multi-fidelity escalation engine.

The motivating product behavior is future support for populations where different candidates may be valuable for different reasons. D1 must therefore preserve Pareto/non-dominated alternatives and scoped elites rather than forcing every candidate into one weighted overall score.

## Architectural boundary

D1 may depend on the frozen D0 contracts and existing domain-neutral scientific contracts:

- `DesignSpaceReference`
- `DesignCandidate` / `DesignCandidateReference`
- `TwinReference`
- `FidelityLadder` / `FidelityRung`
- `ScientificResult`
- `ObjectiveDefinition`
- `Quantity`
- deterministic serialization / scientific errors

D1 must not import or branch on:

- any concrete `engcore.domains` package;
- any drone/HVAC/aircraft/reactor/biology/system pack;
- SRIA campaign policy;
- a concrete optimizer/search backend;
- an LLM provider;
- web/API/database frameworks.

No archive may contain hard-coded component names such as battery, motor, wing, compressor or reactor.

## Relationship to Scientific Twin and scientific truth

D1 does not change the frozen Scientific Twin contract.

Every `DesignEvaluation` must bind:

1. one exact `DesignCandidateReference`;
2. the exact `TwinReference` represented by that candidate;
3. one attributable `ScientificResult`;
4. one declared fidelity selection when fidelity is supplied.

A D1 evaluation or archive membership is **not** a claim that a Twin is physically true, experimentally validated, globally adequate or safe.

`ScientificResult.is_usable` must not be silently promoted into design feasibility, truth or validation. Any selection/admission eligibility carried by D1 is an explicit decision-layer declaration supplied by the caller with reasons; D1 does not invent it from convergence alone.

## Scope frozen for D1

### 1. Design population

An immutable population record with:

- stable population id;
- exact `DesignSpaceReference`;
- generation number;
- unique `DesignCandidateReference` members;
- deterministic serialization.

A population is a declared set. D1 does not generate the candidates.

### 2. Fidelity selection reference

A compact immutable binding to an exact fidelity ladder version and rung id.

It must be verifiable against a supplied `FidelityLadder` and must not assign domain-specific meaning to a rung.

### 3. Design evaluation

An immutable record containing:

- stable evaluation id;
- exact candidate reference;
- exact Twin reference;
- exact design-space reference;
- attributable `ScientificResult`;
- optional fidelity selection;
- explicit selection eligibility state (`UNKNOWN`, `ELIGIBLE`, `INELIGIBLE`) and non-empty reasons for non-unknown decisions;
- deterministic metadata.

Construction/validation requirements:

- candidate, Twin and design-space identities must agree when a concrete `DesignCandidate` is supplied;
- result values remain `Quantity` values and retain the complete ScientificResult provenance/validation/UQ record;
- D1 never rewrites scientific result values or uncertainties;
- eligibility is not inferred from `ScientificResult.is_usable`.

### 4. Objective projection

D1 may project declared `ObjectiveDefinition` records onto a `DesignEvaluation` by reading the named metric from its ScientificResult.

Projection must:

- fail closed when an objective metric is missing;
- verify dimensional compatibility with the objective unit;
- convert only through the existing `Quantity` contract;
- preserve objective direction;
- never invent missing objective values.

### 5. Exact Pareto dominance

D1 implements deterministic pairwise Pareto dominance for evaluations under an explicit tuple of `ObjectiveDefinition` records.

Rules:

- only explicitly `ELIGIBLE` evaluations may enter a selection archive;
- A dominates B iff A is no worse on every declared objective and strictly better on at least one;
- objective direction (`MINIMIZE`/`MAXIMIZE`) is respected;
- no weighted sum, hidden normalization or LLM judgment is used;
- ties do not dominate each other;
- incompatible/missing units fail closed.

### 6. Pareto archive

An immutable/deterministically constructed archive containing the non-dominated eligible evaluations for one declared objective set.

The archive must be invariant to input ordering and must retain distinct tied/non-dominated candidates.

### 7. Scoped elite archive

A general archive that preserves partial successes under a caller-declared `scope_ref` and a caller-declared subset of objectives.

Examples such as propulsion, energy storage, thermal, control or structure belong to future system/domain layers; D1 stores only opaque scope identifiers and objective definitions.

A scoped elite archive uses the same exact Pareto rule within its declared scope. It must not assume that combining elites from different scopes produces a superior whole-system design.

## Explicitly deferred

Successor milestones, not D1 acceptance requirements:

- candidate generation;
- Sobol/LHS/DOE generation;
- mixed-variable optimizer encoding/search;
- conditional-variable activation rules;
- component/system compatibility graphs;
- recombination operators;
- novelty archive;
- failure-knowledge taxonomy beyond explicit selection ineligibility;
- learned surrogate ranking;
- multi-fidelity escalation policy;
- Scientific Design Memory across studies;
- SRIA integration;
- any concrete system pack;
- automatic top-N promotion to a next simulation level.

## Acceptance criteria

### A1 — domain neutrality

D1 contains no concrete domain/product/system imports or hard-coded product/component conditionals.

### A2 — attributable evaluation

Every DesignEvaluation carries one complete ScientificResult and exact candidate/Twin/design-space identity.

### A3 — no scientific-status inflation

Selection eligibility is explicit and is never inferred from result convergence/usability, validation level, posterior mass or archive membership.

### A4 — objective projection exactness

Declared objectives resolve to existing result metrics with compatible units; missing/incompatible metrics fail closed.

### A5 — exact deterministic dominance

Pairwise Pareto dominance follows the frozen no-worse/all + strictly-better/one rule, respects direction and is deterministic.

### A6 — Pareto archive order invariance

The same eligible evaluations and objective definitions yield the same archive membership regardless of input order.

### A7 — preserve plural success

Distinct tied/non-dominated evaluations are retained; D1 does not force a single global winner.

### A8 — scoped partial-success boundary

Scoped elite archives use opaque caller-declared scope ids and objective subsets, contain no product semantics, and make no recombination/compatibility claim.

### A9 — population identity

Population generation/member identities are immutable, unique and deterministically serialized; D1 does not generate members.

### A10 — fidelity generality

Fidelity selections validate only ladder/version/rung identity and carry no hard-coded scientific meaning.

### A11 — deterministic round-trip

All persistent D1 records serialize deterministically and round-trip without type/identity loss.

### A12 — regression safety

Targeted D1 tests pass and the full repository regression remains green. Frozen K1/K1.5/K2/Twin/K3/K3.1/K4/D0 semantics remain untouched.

## Failure policy

If practical system work later requires a new ranking, archive, compatibility or recombination concept, it must be introduced through a successor milestone. D1 is not rewritten to contain drone/HVAC/etc. exceptions after observing a product-specific use case.
