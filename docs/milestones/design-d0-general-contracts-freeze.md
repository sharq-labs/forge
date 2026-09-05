# D0 — General Design & Discovery Contracts V0.1 freeze

Status: **PASS / FROZEN**

Milestone ID: `D0`

## Frozen identities

- Starting stable checkpoint (K4 PASS/FROZEN): `d3d5d4c23b2cd9d04ee19bf123b2c26403627087`
- D0 implementation/tested source before freeze record: `49117f6c3919888e6244166b89c47793d6162448`
- D0 preregistration: `docs/design-d0-general-contracts-prereg.md`

The D0 preregistration was frozen before implementation and was not rewritten after observing test outcomes.

## Scope actually delivered

D0 remains a domain-neutral representation and lineage layer only.

Delivered contracts:

- `DesignSpaceReference`
- `DesignSpace`
- `DesignCandidateReference`
- `DesignCandidate`
- domain-neutral fidelity declarations / ladder
- deterministic serialization and round-trip support
- exact binding from every `DesignCandidate` to one `TwinReference`

D0 reuses existing Scientific Core types rather than introducing a parallel type system:

- `ScientificVariable`
- `ScientificValue`
- `Quantity`
- `IntegerValue`
- `BooleanValue`
- `CategoricalValue`
- `TwinReference`

No product/system/domain-specific design logic was added to the general layer.

## Scientific Twin boundary

The D0 implementation preserves the frozen architectural distinction:

- `ScientificTwin`: the exact scientific system instance.
- `DesignSpace`: the declared choices that may vary.
- `DesignCandidate`: the exact design choices and the exact Twin that represents them.

A candidate is not a solver result, evidence record, feasibility verdict, validation claim, adequacy claim, or truth claim.

Candidate lineage and Twin lineage remain distinct records.

## Domain-neutrality boundary

`engcore.design` contains no drone, HVAC, aircraft, reactor, biology, kinetics, thermal, electrical, or other concrete product/domain branching.

The layer does not import concrete domain packages, SRIA campaign policy, concrete optimizer backends, LLM providers, web frameworks, databases, or product-specific solvers.

A future system pack must therefore be removable without changing D0.

## Variable representation

D0 structurally supports the four existing declared design kinds:

- continuous
- integer
- categorical
- boolean

This is representability only. D0 does not claim that all four kinds are searchable by the existing optimizer adapter.

Assignment validation fails closed on:

- missing variables;
- undeclared extra variables;
- wrong typed value kinds;
- out-of-bound continuous/integer values;
- invalid categorical values.

No raw Python scientific primitives are accepted as design assignments.

## Fidelity boundary

D0 fidelity declarations are generic ordered records identified by stable rung ids/ranks and capability identifiers.

No fidelity rung is hard-coded to CFD, FEA, fast simulation, deep validation, drone, thermal, or any other concrete scientific/system meaning.

Concrete domains and system packs remain responsible for mapping scientific meaning onto the general fidelity contracts.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 — domain neutrality | PASS |
| A2 — reuse scientific types | PASS |
| A3 — four design kinds represented | PASS |
| A4 — exact assignment validation | PASS |
| A5 — candidate/Twin identity boundary | PASS |
| A6 — deterministic lineage | PASS |
| A7 — fidelity generality | PASS |
| A8 — no scientific-status inflation | PASS |
| A9 — deterministic round-trip | PASS |
| A10 — regression safety | PASS |

## Targeted test gate

D0 targeted contract suite:

- `6 passed`
- `0 failed`
- `0 errors`
- wall time: `1.01 s`

## Full regression gate

Full repository regression executed against D0 tested source `49117f6c3919888e6244166b89c47793d6162448`:

- `1336 passed`
- `4 warnings`
- `0 failed`
- `0 errors`
- wall time: `201.09 s` (`0:03:21`)

The four warnings were the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they were not D0 failures.

## Tooling correction recorded during D0

The repository uses a `src/` layout. The initial targeted run could not import `engcore` because pytest configuration exposed `.` but not `src`.

`pyproject.toml` was corrected to include both `src` and `.` in pytest's Python path. This was a tooling/import-path correction only; it did not change scientific semantics, design semantics, Twin semantics, or any frozen milestone behavior.

## Explicitly not part of D0

The following remain successor work and are not retroactively included in D0:

- mixed-variable optimizer encoding/search;
- conditional-variable activation rules;
- `DesignEvaluation`;
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
- any drone/HVAC/aircraft/system pack.

## Frozen outcome

D0 is **PASS / FROZEN**.

The milestone establishes a reusable domain-neutral bridge from declared design space to exact design candidate identity and exact Scientific Twin identity without conflating design representation with search, simulation, evidence, feasibility, validation, adequacy or truth.

Any future extension must be introduced through a successor milestone rather than rewriting D0 after observing later system-pack needs.
