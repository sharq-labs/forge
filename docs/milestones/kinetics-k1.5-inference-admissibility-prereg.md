# K1.5 — Kinetics inference-admissibility boundary preregistration

Status: **FROZEN BEFORE IMPLEMENTATION**

Experiment ID: `K1.5`

## Scientific question

Can the repository enforce the smallest boundary needed before K2 so that shared numerical inference can consume only **domain-interpreted, provenance-bearing, sequence-validated predictions**, while refusing bare arrays, ordinary solver outputs, and a `ScientificResult` that is merely `is_usable == True`?

This milestone is deliberately smaller than K2. It does **not** estimate parameters, define a posterior, choose an inference backend, add UQ, perform experiment design, or create a general Scientific Study Runtime.

## Why this is required before K2

K1 established two different facts that inference must not collapse:

1. one solve can be numerically completed and scientifically usable;
2. a sequence-level verification gate is required before numerical adequacy is established.

Therefore `ScientificResult.is_usable` is necessary but insufficient for a numerical prediction to enter a likelihood. A successful single solve cannot certify its own tolerance independence.

K2 would be scientifically unsound if a likelihood could accept raw solver arrays or a single usable `ScientificResult`, because a posterior can be perfectly normalized and sharply wrong when its forward predictions are not scientifically admissible.

## Frozen architecture boundary

K1.5 may add only the following minimal concepts:

- a shared inference-side type representing an **admissible numerical prediction**;
- a shared guard that refuses anything except that type;
- a Kinetics/CSTR adapter that owns observable interpretation and invokes the existing CSTR verification machinery before constructing that type;
- a small confirmatory Kinetics holdout experiment and tests.

K1.5 must **not**:

- modify the universal `ScientificResult` contract;
- modify the universal `ValidationReport` vocabulary;
- overload `DomainPack` into an executable model contract;
- add autonomous Solver/Inference/UQ agents;
- add a generic posterior engine, MCMC, Laplace approximation, BoTorch inference, a message bus, a microservice, a graph database, or a distributed runtime;
- treat GPU/CPU performance as scientific admissibility;
- change any frozen K1 experiment artifact or its recorded result.

## Shared inference boundary requirements

The new inference-side prediction object must be impossible to regard as admitted unless all of the following are present:

1. **Domain interpretation** — a named domain adapter owns the mapping from solver result metrics to inference observables.
2. **Source scientific result** — observable values come from an existing `ScientificResult`; they are not caller-supplied bare floats/arrays.
3. **Provenance** — the source result carries its mandatory `ProvenanceRecord`.
4. **Per-solve usability** — the source result is scientifically usable according to its domain checks.
5. **Sequence validation** — the supplied sequence-level `ValidationReport` has actually attained `ValidationLevel.NUMERICALLY_CONVERGED`.
6. **Typed observables** — every exposed observable remains a `Quantity` with its domain-owned unit.
7. **Binding** — the admitted prediction carries a non-empty domain binding/fingerprint so a validation report for different physics cannot be silently substituted by an adapter.

The shared guard must reject at least:

- NumPy arrays;
- mappings of floats;
- a bare `ScientificResult`, even when `is_usable` is true;
- an attempted prediction whose sequence report did not attain `NUMERICALLY_CONVERGED`.

This is a boundary on **numerical** predictions. K1.5 makes no claim that every future analytic inference path must use numerical convergence.

## Kinetics/CSTR adapter requirements

The CSTR adapter must:

- accept a fully declared `ReactorRun`, not raw arrays;
- execute the ordinary CSTR scientific result lifecycle;
- refuse a source result that the CSTR domain marks unusable;
- execute the existing full CSTR `run_verification_gate` on the same declared reactor physics;
- require `NUMERICALLY_CONVERGED` from that gate before admission;
- expose only explicitly requested, domain-known CSTR observables;
- preserve their `Quantity` units;
- bind admission to `ReactorRun.physics_fingerprint()`;
- attach the verification report/details to the admitted prediction for audit;
- make no claim of physical/experimental validation. The K1/K1.5 reactor remains a computational study, not evidence about a real reactor.

It is acceptable in K1.5 for the adapter's source solve and the verification sequence to be separate executions of the same declared physics. Eliminating repeated work is an execution optimization for K2; it must not be achieved by weakening this scientific boundary.

## Confirmatory holdout

The positive confirmatory point is **H1**, created from K1's frozen benign cooled regime R1 with exactly one physical change:

- coolant temperature: `290 K -> 295 K`.

All other R1 chemistry, operation, initial conditions, horizon, production method, tolerances and numerical budget remain unchanged.

Rationale: this is an unseen benign cooled operating point close enough to the already defensible low-conversion regime that no new model assumption is introduced, while still being a genuinely different physical declaration. The K1 verification thresholds are not changed after observing H1.

### Frozen predictions for H1

Before running H1, K1.5 predicts:

- the source solve completes and is usable;
- the existing tolerance ladder is numerically independent at the frozen K1 threshold;
- the CSTR adapter admits H1;
- admitted observables retain domain units and source provenance.

If H1 fails the frozen sequence criterion, **do not tune the threshold to make it pass**. The outcome is a K1.5 failure/finding and must be reported as such.

## Negative controls

Two existing frozen K1 regimes are used only as negative controls; their historical K1 artifacts are not edited.

### N1 — R7 oscillatory regime

K1 already established that R7 can be `CONVERGED` and `is_usable == True` at the single-solve level while its verification gate awards no numerical adequacy level.

Frozen prediction: the inference adapter **must reject R7**. This is the critical proof that `is_usable` alone cannot cross the inference boundary.

### N2 — R8 envelope-exit regime

K1 already established that R8 can complete integration but is scientifically unusable because its trajectory leaves the model validity envelope.

Frozen prediction: the inference adapter **must reject R8** before it can become an admissible inference prediction.

## Acceptance criteria

K1.5 passes only if all are true:

- **A1** H1 is admitted through the CSTR adapter without changing any K1 verification threshold.
- **A2** H1's admitted values are `Quantity` objects with the CSTR domain-owned units and the source result carries provenance.
- **A3** H1's admission records `NUMERICALLY_CONVERGED` from the sequence-level verification report.
- **A4** R7 is rejected even if its ordinary source `ScientificResult.is_usable` is true.
- **A5** R8 is rejected because its source result is scientifically unusable.
- **A6** the shared inference guard rejects a NumPy array, a float mapping and a bare `ScientificResult`.
- **A7** attempting to construct/admit a numerical prediction with a validation report that lacks `NUMERICALLY_CONVERGED` is rejected.
- **A8** the adapter binds the admission to the same reactor physics fingerprint used to generate the source result and verification evidence.
- **A9** no universal Core result/validation contract and no frozen K1 artifact is modified.
- **A10** existing tests continue to pass; new K1.5 tests cover both positive and negative controls.

## Falsification criteria

- **F1** If H1 fails the frozen sequence criterion, K1.5 does not retune thresholds; the failure is preserved.
- **F2** If R7 can enter inference because it is merely `is_usable`, the boundary is unsound.
- **F3** If R8 can enter inference after its per-solve domain validation failed, the boundary is unsound.
- **F4** If a bare array/mapping/`ScientificResult` can be consumed as an admitted prediction, the shared boundary is not enforced.
- **F5** If validation evidence from different physics can be rebound to a prediction without detection by the CSTR adapter, the adapter is unsound.
- **F6** If implementing K1.5 requires changing frozen K1 artifacts or widening universal Core contracts, stop and report architecture creep rather than forcing the milestone through.

## Performance policy

K1.5 is scored on scientific boundary correctness, not throughput. CPU/GPU acceleration must not alter admission semantics. Performance work already demonstrated that hardware can accelerate suitable workloads; K1.5 does not use performance as a substitute for scientific verification.

For K2, execution optimization may reuse process pools, vectorize likelihoods, cache content-addressed forward results, and use GPU batches where measured beneficial, but the accelerated path must produce the same admissibility decision and scientific values as the reference path.

## Freeze rule

This document is the preregistration. Once committed, do not rewrite its predictions, thresholds, acceptance criteria, negative controls, or falsification rules in response to K1.5 results. Any necessary correction must be recorded as a separate prospective deviation document.