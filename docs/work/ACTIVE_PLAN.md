# Active Plan

Purpose: keep the multidomain Core upgrade bounded and resumable.

## Current objective

Evolve Forge into a domain-agnostic transient system-engineering runtime for
Battery/BESS, Thermal/Energy and multirotor Domain Packs without weakening the
Scientific Core or creating a parallel authority path.

## Task tree

### Phase 1 — contracts and production authority

- [ ] Add a unit-bearing, immutable, digestible scenario/transient contract and
  trace it through authorized execution.
- [x] Add generic hierarchical component/system topology without duplicating
  `ScientificTwin` instance authority.
- [x] Source production realizations and solvers exclusively from enabled,
  validated Domain Packs; reject identity collisions.
- [ ] Remove remaining domain-owned capability declarations from generic
  production assembly where pack registration supplies the same authority.

### Phase 2 — transient execution and validation

- [ ] Bind scenario segments, time-varying inputs, state ownership, events and
  termination conditions to the existing `MultiphysicsRuntime`.
- [ ] Add a content-referenced validation corpus/campaign engine.
- [ ] Add multidimensional validation coverage and explicit applicability
  states; solver success must not imply validation support.

### Phase 3 — certification and replay

- [ ] Require complete validation, verification and QoI × uncertainty-channel
  coverage during production certification.
- [ ] Add actual authorized computational replay while retaining serialization
  roundtrip as a separate integrity check.
- [ ] Consolidate numerical-quality evidence and declare producer capability
  without fabricating unsupported checks.

### Phase 4 — data and design

- [ ] Add measurement/time-series dataset contracts bound to the data plane.
- [ ] Add the missing generic optimization-run/backend contract around the
  existing design-space, candidate and Pareto machinery.
- [ ] Refine data-plane lifecycle/version metadata only where the preceding
  contracts require it.

## Stop conditions

Stop implementation and surface a blocker if a proposed change would require:

- weakening UNKNOWN/fail-closed semantics;
- changing a frozen serialized contract without an explicit version decision;
- inventing measurements, uncertainty, validation, provenance or evidence;
- duplicating an existing scientific identity or authority system;
- adding domain-specific component, state or quantity names to generic Core;
- treating serialization roundtrip, solver agreement or convergence as
  scientific validation.
