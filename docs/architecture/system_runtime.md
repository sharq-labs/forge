# System runtime (BIG 12)

**Status:** design of `src/engcore/system_runtime/` (non-Core, registered). This page is written
before the code so the reuse decisions are checkable against it. The runtime is an
*orchestration* layer over authorities that already exist. It adds no solver family, no coupling
loop, no clock, no trust verdict.

```text
SystemRunRequest (content-bound, canonical)
  -> compile_plan -> SystemExecutionPlan (deterministic DAG, content digest)
  -> preflight -> READY | DEFERRED_CHECKS | REFUSED   (never "validated")
  -> SystemExecutor: topological run over NodeAuthorities
        -> delegates to MultiphysicsRuntime (BIG 9) / MultiTimescaleRuntime (BIG 10) / providers (BIG 11)
  -> SystemRunResult (node receipts, availability per observable, state history, trace)
  -> assess_constraints / assess_conservation / trust_handoff (existing CredibilityEvidenceReport)
  -> SystemCheckpoint / resume / replay
```

## Reuse map (nothing below is re-implemented)

| Need | Existing authority reused | What BIG 12 adds |
| --- | --- | --- |
| system topology, constraint bindings | `systems.SystemDefinition` (`digest`, `constraint_bindings`, `constraints`) | request binds its digest; constraint bindings get a *consumer* (`assess_constraints`); `unsupported_execution_bindings` is unchanged |
| scenario identity | `scenarios.ScenarioSpecification.digest` | referenced by digest, verified against the supplied object |
| clock | `scenarios.Timeline` (BIG 2) | referenced by digest; state time is a `Quantity` on that basis. No new time runtime |
| environment | `scenarios.EnvironmentTimeline` (BIG 3) | digest reference, or an explicit stated absence; required channels checked in preflight |
| materials | `materials.MaterialState` / `ResolvedProperty` (BIG 5) | digest references bound into the request and into node identity |
| lifecycle / slow state | `scenarios.lifecycle` + `multiscale` (BIG 4 / 10) | called through an authority; not re-run here |
| coupling | `execution.multiphysics.MultiphysicsRuntime` (BIG 9) + `coupling` adapters | `MultiphysicsAuthority` wraps a runtime and *delegates*; no iteration loop is written here |
| long horizon | `multiscale.MultiTimescaleRuntime`, `MacroCheckpoint` (BIG 10) | `MultiscaleAuthority` wraps it; resume uses its own checkpoint |
| providers | `providers.ProviderRegistry.require`, `ProviderStatus`, `ProviderExecutionIdentity/Record` (BIG 11) | explicit `ProviderBinding`s (id + version [+ digest]); preflight refuses unavailable / mismatched, never falls back |
| resource records | `execution.orchestration.resources.ResourceBudget` / `ResourceUsage` | recorded per node; operational, never evidence |
| constraints | `scientific.ir.constraints.ConstraintDefinition.check` / `ConstraintCheck` | status `UNAVAILABLE` when the result is missing (never a pass) |
| conservation | `scientific.conservation.ConservationBalance` | closed only from terms the providers computed; else INCOMPLETE |
| state values | `execution.multiphysics.InitialStateValue` (value + `Uncertainty`) | `SystemState` groups them at a synchronization boundary with a digest chain |
| trust | `credibility.CredibilityEvidenceReport` / `CredibilityVerdict` | `trust_handoff` builds the report; the verdict is *derived by the existing function*. No new verdict enum |
| serialization | `scientific.serialization` schema helpers | each record: schema tag, strict keys, digest |

## Vocabularies (kept separate on purpose)

* **Execution status** (per node): `PENDING`, `RUNNING`, `SUCCEEDED`, `REFUSED`, `FAILED`, `BLOCKED`.
  It says what happened to a computation, never whether the science supports it.
* **Result availability** (per requested observable): `AVAILABLE`, `BLOCKED`, `REFUSED`, `FAILED`,
  `UNKNOWN`, each with the dependency path that decided it.
* **Preflight**: `READY`, `DEFERRED_CHECKS`, `REFUSED`. Not scientific support.
* **Scientific assessment**: only the existing `CredibilityVerdict`, produced by `derive_verdict`.

## Identity

`SystemRunRequest.digest` covers every scientifically relevant item (system / scenario / timeline /
environment / material digests, initial state, observables, provider bindings incl. version and
optional digest, model selections, nodes and their authority identities, constraint observations,
mode). It excludes the caller's request label, the workspace hint and the resource budget
(recorded in a separate operational digest). The plan digest covers the compiled node graph. A node's
*execution identity* additionally covers the digests of its actual input values, the authority's
identity digest and the state digest, which is what exact reuse and stale-output protection key on.
