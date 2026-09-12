# Solver Lifecycle & Concurrency Hardening — Sprint 2

Base `52dea3f` (Sprint 1 closed) · code head `e6dad0e` · branch `claude/solver-lifecycle-hardening-sprint-2` · 2026-09-11

## 1. FINAL RESULT

**SOLVER LIFECYCLE & CONCURRENCY HARDENING COMPLETE**

| Acceptance condition | Verdict | Where |
|---|---|---|
| Registry exposes no shared problem-specific mutable execution state | **HOLDS** | §4 · `ee8d76e` |
| `BatteryCellSolver` lifecycle safe | **HOLDS** | §6 · SLM-1a, SLM-6 |
| `ElectricalDCSolver` lifecycle safe | **HOLDS** | §6 · SLM-1b, SLM-2, SLM-5 |
| all other registered solvers classified | **HOLDS** — 8 adapters + registry, 0 UNKNOWN | §5 |
| sequential contamination tests green | **HOLDS** | §6 rows 1–2 |
| interleaved prepare/solve tests green | **HOLDS** | §6 row 3 |
| concurrent mixed solves green | **HOLDS** — 8, 20 and 100 concurrent requests | §6 rows 4–5, 9 |
| failure cleanup tests green | **HOLDS** — 12 failure scenarios | §7 |
| lifecycle fault injections all detected | **HOLDS** — 9/9 killed, CONTROL GREEN | §8 |
| FAST green | **HOLDS** — 4124 passed, 3 skipped | §12 |
| FULL green | **HOLDS** — 4665 passed, 3 skipped, 0 failed | §12 |
| installed wheel green | **HOLDS** — lifecycle smoke OK, 355 passed | §12 |
| previous scientific outputs preserved | **HOLDS** — 14/14 cases equivalent | §10 |
| no material performance regression | **HOLDS** — +6 µs per registry resolve, solves unchanged | §11 |
| existing certified mutation harness | **HOLDS** — CONTROL GREEN, 79/79 killed, exit 0 | §8 |

Two defects were reproduced and closed: the registry handed every request one
shared solver instance (§2.3), and a CSTR prepared solve carried an evaluation
budget that every execution spent (§2.4). No lock was added anywhere.

## 2. ORIGINAL ARCHITECTURE

### 2.1 Registry semantics

`SolverRegistry._solvers: dict[(solver_id, version), ScientificSolver]` stored
the **instance** it was given. `register(solver)` kept that object, and `get`,
`candidates`, `resolve`, `list` and iteration returned the same object to every
caller. No module under `src/` or `experiments/` builds a registry; registries
are built in tests. Production entry points construct a solver per call
(`solver = solver or XSolver()`).

### 2.2 Stateful solvers

Every adapter binds its system — and the operating point, numerics or
realization beside it — into a table on the instance, keyed by problem id.
`prepare` reads that table and copies what it needs into `PreparedSolve.payload`.

| Solver | Registry stored instance? | Mutable execution state | Lifetime | Reentrant at `52dea3f`? |
|---|---|---|---|---|
| `ElectricalDCSolver` | yes | `_circuits` | instance, never cleared | **no** — refusal and poisoning |
| `NgspiceDCSolver` | yes | `_circuits` (silent overwrite) · `_version` (lazy cache) | instance | **no** — refusal |
| `BatteryCellSolver` | yes | `_bound` (cell, load) | instance | **no** — silent wrong result |
| `LumpedThermalSolver` | yes | `_bound` (body, watts) | instance | **no** — silent wrong result, poisoning |
| `ResistancePropertySolver` | yes | `_bound` (conductor, kelvin) | instance | **no** — silent wrong result |
| `CSTRSolver` | yes | `_runs` · evaluation counter inside the prepared payload | instance · prepared solve | **no** — silent wrong numerics; prepared solve not re-executable |
| `SchemeSolver` / `ReducedSchemeSolver` | yes | `_bound` (slab, realization) | instance | **no** — silent wrong realization |
| `Conduction1DSolver` (T1 byte-pinned) | yes | `_slabs` | instance | **no** — silent wrong resolution |

The default problem ids ignore the operating point:
`battery-cell-{cell_id}-{load_id}`, `thermal-lumped-{body_id}`,
`resistance-tcr-{component_id}`, `kinetics-cstr-{run_label}`,
`thermal-conduction1d-{slab_id}`, `electrical_dc:{circuit_id}`. And each
problem check verifies physical identity, not the operating point or numerics
bound beside it.

### 2.3 Reproduced failures — shared solver instance (`e737a6a`, 16 strict xfails)

| Scenario | Solvers | What happened |
|---|---|---|
| A bound, B bound (same default id), A prepared | lumped, resistance, battery, CSTR, scheme, conduction | A solved at B's heat input / temperature / load current / tolerance / realization / resolution, **silently** |
| bind→prepare window held open across 8 threads | battery, lumped, resistance | 4 of 8 requests solved another request's operating point |
| A then B, same circuit id, different circuit | DC | B refused by A's stale binding |
| 48 threaded mixed requests on one instance | DC | 24 of 48 refused |
| A bound, B bound, A prepared | ngspice | A's prepare refused: B had overwritten A's circuit |
| a failed request, then a valid one | lumped, DC | the failed request's binding poisoned the next |
| `registry.resolve` twice | lumped | both requests received one instance |

Not reproduced: A→B→A when each request binds immediately before its own
prepare; a DC prepared solve under a later rebind; repeated identical requests
(deterministic).

### 2.4 Reproduced failure — prepared solve re-execution (`6e69699`, 2 strict xfails)

Found by the SL-9 search and reproduced before it was fixed. `CSTRSolver.prepare`
calls `assemble(run)`, which closes the right-hand side over an
`_EvaluationCounter`, and `solve` charged that counter.

| Execution of one prepared solve | Before the fix |
|---|---|
| first | CONVERGED, 402 evaluations |
| second | CONVERGED, **804** evaluations reported |
| four concurrent | all four differ from a single execution |
| second, budget 407 | **MAX_ITERATIONS after 0.5 ms**, nothing integrated |

The six other adapters executed one prepared solve identically once, twice and
four times concurrently.

## 3. ROOT CAUSE

A solver instance is a **session**: it carries the bindings of the requests made
through it. That is inherent in the adapter API — `bind_*` followed by
`prepare(problem)` — and the byte-pinned E1/E2 harnesses call `bind_circuit` and
then `prepare` repeatedly on one instance.

The registry stored one session per solver and returned it to every caller, so
independent requests shared one binding table. Where the operating point is not
part of the problem check, the last bind silently won. Where it is (the DC
circuit fingerprint), a stale binding refused an independent request.

Separately, the CSTR evaluation budget is **per execution**, but it was built at
preparation and stored in the prepared payload.

## 4. NEW LIFECYCLE ARCHITECTURE

**Chosen: factory / session (Option B).** Option A (stateless adapters) was not
reachable. `Conduction1DSolver` is T1 byte-pinned and keeps `_slabs`, and the
pinned E1/E2 harnesses depend on bind-then-prepare against one instance.

```
SolverRegistry
  └─ SolverDefinition (per solver_id, version)
       ├─ factory        zero-argument callable, called once per request
       └─ probe          built once at registration; answers identity,
                         capabilities and supports(); never returned, never bound
resolve / get / candidates / list / iteration / selection-rule candidates
  └─ factory() → a new session → bind → prepare → PreparedSolve → solve
```

- **Registration takes factories, never sessions.**
  - `register` accepts a class or any zero-argument callable.
  - An already-constructed solver is refused with a migration message: the
    registry cannot tell a pristine instance from one carrying bindings.
  - The core support refusals (`does not use the core support contract`,
    `overrides supports()`) apply to the probe unchanged.
- **Every way out of the registry is a new session.**
  - `resolve`, `get`, `candidates`, `list`, `__iter__`, and the candidates
    handed to a `selection_rule`, each call the factory.
  - `chosen is one of the candidates` is still enforced, by object identity.
- **The factory is checked.** A session is refused if the factory returns:
  - the probe, or
  - an instance it already handed out (tracked by weak reference, keyed by
    `id`, because dataclass solvers are unhashable), or
  - a solver identifying as something other than its definition.
- **Failure has nothing to clean up.**
  - A failed request's session is dropped with the request.
  - There is no reset and no `finally` on any solver or registry state.
- **The contract boundary.** A caller who constructs one solver directly and
  shares it across independent requests is sharing a session. The adapter
  refusals still apply inside a session (§6 `test_a_directly_constructed_solver_is_one_session`).
- **CSTR execution budget.**
  - `solve` creates the execution's own `_EvaluationCounter`.
  - The right-hand side charges the counter of the execution integrating it,
    held in a `ContextVar` that `solve` sets around `solve_ivp`. Called directly,
    it charges the system's own counter, so `assemble(run)` keeps its tested
    semantics.
  - A right-hand side a caller substituted into the payload is charged too, so
    the two domain tests that inject a finite-time singularity are unchanged.
  - The one `finally` resets that context token. It is execution-scoped and
    not shared.

## 5. STATE OWNERSHIP TABLE

| State | Before | After | Reason |
|---|---|---|---|
| the registered solver | one instance per `(id, version)`, returned to every caller | `SolverDefinition`: factory + private probe | the registry holds no request state (SL-7) |
| `BatteryCellSolver._bound` | on the instance the registry shared | on the request's session | PROBLEM_STATE; the bind→prepare API needs it on the object `prepare` is called on |
| `ElectricalDCSolver._circuits` | same | session | PROBLEM_STATE; pinned E1/E2 call shape |
| `NgspiceDCSolver._circuits` | same | session | PROBLEM_STATE |
| `NgspiceDCSolver._version` | lazy, per instance | lazy, per session | SAFE_CACHE — the provider's version |
| `LumpedThermalSolver._bound`, `ResistancePropertySolver._bound`, `CSTRSolver._runs`, `SchemeSolver._bound` | same | session | PROBLEM_STATE |
| `Conduction1DSolver._slabs` | same | session (file unchanged) | PROBLEM_STATE; T1 byte-pinned |
| `settings`, `invocation`, `backend`, `solver_id`, `version` | instance | instance | IMMUTABLE_CONFIGURATION |
| `PreparedSolve.payload`, all adapters | owns everything `solve` reads | unchanged | verified: binding tables are read only in `bind_*`/`prepare` |
| CSTR `_EvaluationCounter` | built at prepare inside the payload; charged by every execution | **moved** to a local of `solve`; the payload's counter is charged only by direct calls | per-execution state does not belong to a preparation |

**Moved fields.** One field changed owner in code: the CSTR evaluation counter
went from preparation to execution. The binding tables changed owner by
lifecycle, from a registry-shared object to a request-owned session, without
a code move. No adapter field needed to move into `PreparedSolve`, which
already owned what `solve` reads.

### SL-9 — targeted `self.* =` search (solver adapters, protocol, registry)

| Location | Write | Class |
|---|---|---|
| `battery/solver.py:256`, `:294` | `self._bound = {}` · `self._bound[key] = …` | PROBLEM_STATE |
| `battery/solver.py:257` | `self.settings` | IMMUTABLE_CONFIGURATION |
| `electrical/dc/solver.py:80`, `:121` | `_circuits` field · `self._circuits[key] = …` | PROBLEM_STATE |
| `electrical/ngspice.py:460–461` | `self.invocation`, `self.settings` | IMMUTABLE_CONFIGURATION |
| `electrical/ngspice.py:464`, `:498` | `_circuits` | PROBLEM_STATE |
| `electrical/ngspice.py:465`, `:472` | `_version` | SAFE_CACHE |
| `electrical/material.py:1561`, `:1599` | `_bound` | PROBLEM_STATE |
| `electrical/material.py:1562` | `self.settings` | IMMUTABLE_CONFIGURATION |
| `thermal_models/lumped.py:1437`, `:1476` | `_bound` | PROBLEM_STATE |
| `thermal_models/lumped.py:1438` | `self.settings` | IMMUTABLE_CONFIGURATION |
| `thermal_models/conduction1d_schemes.py:426`, `:478`, `:777` | `_bound` | PROBLEM_STATE |
| `thermal_models/conduction1d_schemes.py:423–425` | `backend`, `solver_id`, `version` | IMMUTABLE_CONFIGURATION |
| `kinetics/cstr/solver.py:259`, `:311` (pre-fix numbering) | `_runs` | PROBLEM_STATE |
| `kinetics/cstr/solver.py:147`, `:157`, `:158` (pre-fix numbering) | `_EvaluationCounter` fields, charged from the prepared payload | PROBLEM_STATE in `PreparedSolve` → per execution after `e6dad0e` |
| `thermal/conduction1d/solver.py:157`, `:199` | `_slabs` | PROBLEM_STATE (frozen file) |
| `lumped.py:1082`, `material.py:1003`, `ngspice.py:202` | `object.__setattr__` in a frozen value object's `__post_init__` | IMMUTABLE_CONFIGURATION |
| `solvers/protocol.py`, `solvers/capability.py` | `object.__setattr__` normalisation in frozen records | IMMUTABLE_CONFIGURATION |
| `solvers/registry.py` | `_definitions`, `_factory`, `_probe`, `_identity` | IMMUTABLE_CONFIGURATION (registration time) |
| `solvers/registry.py` | `_issued` (weak references by `id`) | SAFE_CACHE — bookkeeping, never request data |

UNKNOWN: none. PROBLEM_STATE on a shared registry object after the fix: none.
The probe is never bound; `test_9` asserts its `_bound` is empty after 64
threaded resolves.

## 6. CONCURRENCY RESULTS

`tests/test_solver_lifecycle_state_isolation.py` — 75 tests. Every result is
compared with an isolated baseline: a registry of its own, and one request.

| # | SL-8 scenario | Tests | Result |
|---|---|---|---|
| 1 | A then B | `test_1` ×8 solvers, `test_8` | green |
| 2 | A then B then A | `test_1_a_then_b_then_a_through_one_registry` ×8 | green |
| 3 | A prepared, B prepared, A solved | `test_2_a_prepared_b_prepared_b_solved_a_solved` ×4, `test_2_a_bound_b_bound_a_prepared_captures_a` ×8 | green |
| 4 | A and B concurrently | `test_3` ×8 — 8 threads, a barrier holding every request between bind and prepare | green |
| 5 | 20–100 mixed concurrent solves | `test_4[20]`, `test_4[100]` — 16 workers over DC, battery, lumped, resistance | green, 0 cross-contaminated |
| 6 | one fails, then a valid one | §7 | green |
| 7 | same definition reused | `test_7` — 20 sessions, 20 operating points | green |
| 8 | different implementations | `test_8` — native DC, ngspice, lumped, battery in one registry | green |
| 9 | registry singleton under concurrency | `test_9` — module-level registry, 64 threaded resolves | green; 64 distinct sessions, probe never bound |
| 10 | `PreparedSolve` copy behaviour | `test_10` ×4 (`copy.copy`, `dataclasses.replace`, executed on another session, frozen); `test_10b` ×7 (once = twice = 4 concurrent); `test_10c` (fresh CSTR budget) | green |

`PreparedSolve` has no serialization of its own (the payload is opaque by
contract); `RawSolverOutput.to_dict()` is what `test_10b` compares.

**Registry contract (SL-7).** These are all green:
- constructed instances are refused (×3);
- every way out is a new session;
- a factory returning one shared instance is refused;
- a factory re-issuing a session is refused;
- a factory producing another identity is refused;
- a selection rule chooses among new sessions and cannot substitute one.

**Red before green.** The same file at `dd6e0a2` (67 tests) was run against the
pre-fix registry. A shim registered each factory's instance, which is exactly
how pre-fix callers used it. Result: **43 failed, 24 passed**.
- 24 failures are leakage: silent wrong results, refusals and poisoning.
- 9 are registry-contract behaviour that did not exist.
- 10 are `test_6`. Under the shim its injected failure never fires, because the
  one instance is the probe's, so those 10 are not evidence of leakage. The
  failure-poisoning red is carried by `test_5`, which failed genuinely.
- The 24 that passed:
  - the operating-point sanity check;
  - A→B→A for the seven non-DC solvers, each binding right before its own prepare;
  - prepared-then-solved for battery, lumped and resistance;
  - prepared solves carried through copies, for the same three;
  - the different-implementations test;
  - repeated determinism for all eight;
  - the directly-constructed-session check.

  None of these reproduced a leak in §2.3 either.

Against the fix: 67 passed at `dd6e0a2`, 75 passed at `e6dad0e`.

## 7. FAILURE ISOLATION RESULTS

| Failure | Tests | Result |
|---|---|---|
| a prepare refused (problem describes another body) · then a valid request | `test_5_a_failed_lumped_request_…` | green |
| a prepare refused (problem describes another circuit) · then valid requests at both circuits | `test_5_a_failed_dc_request_…` | green |
| injected exception at **bind**, **prepare**, **solve**, **backend call** (after the payload is read), **result construction** (`extract_metrics`) — DC and lumped | `test_6` ×10 | green: the next request, at a different operating point under the same problem id, matches its isolated baseline and extracts metrics |

No cleanup code exists to be skipped. The factory makes the first request's
session fail; the registry hands the next request a new one. No registry or
adapter state is reset in a `finally:`. Across `registry.py` and the eight
adapters, the one `finally:` is the CSTR execution's reset of its context token
(§4). It restores a context-local variable and touches nothing shared.
`registry.py` contains no lock.

## 8. MUTATION / FAULT-INJECTION RESULTS

`tests/mutation_guards.py` is byte-pinned, so the lifecycle faults were planted
by the targeted apply-and-revert script. That script restores each mutation and
verifies the restore by digest. The unmutated control ran first.

| Id | Spec | Planted defect | Result |
|---|---|---|---|
| SLM1a | SLM-1 | battery bindings move onto one table every instance shares | **killed** |
| SLM1b | SLM-1 | DC `_circuits` default factory returns one shared dict | **killed** |
| SLM2 | SLM-2 | one assembled DC system object reused by every problem under that id | **killed** |
| SLM2b | SLM-2 | a CSTR execution charges the counter its prepared solve carries | **killed** |
| SLM3a | SLM-3 | the registry returns its one stored instance for every request | **killed** |
| SLM3b | SLM-3 | a factory returning one mutable session every time is accepted | **killed** |
| SLM4 | SLM-4 | a request's session, failed or not, is handed to the next request | **killed** |
| SLM5 | SLM-5 | DC `solve` reads the latest `_circuits` rather than the prepared state | **killed** |
| SLM6 | SLM-6 | battery `solve` reads the latest `_bound` rather than the prepared state | **killed** |

Final run of all nine against the `e6dad0e` content: **CONTROL GREEN (75 passed); 9/9 mutations killed**, every restore verified by digest.

**SLM-4 as specified is inapplicable.** The architecture has no state reset
after failure that could be skipped. SLM4 plants the nearest real regression, a
failed request's session surviving into the next request, and it is killed.

**Two anchors were corrected.** SLM5 and SLM6 first matched 3 and 2 lines,
because the payload line also appears in `validate` and `extract_metrics`.
Both were re-anchored on the `solve` lines and then killed. Neither was
classified invalid; the denominator did not shrink.

**Existing certified harness.** `registry.py` (G4a) and `cstr/solver.py` (G9c)
are in its scope. Both anchor texts are unchanged.
`tests/mutation_guards.py` was run unmodified against `e6dad0e`: **CONTROL GREEN; 79/79 mutations were killed by the guard they name**, exit 0. G4a (the registry stops refusing a solver that decides its own support) and G9c (the CSTR discards its assessment) were both RED.

## 9. API CHANGES

| API | OLD | NEW | MIGRATION |
|---|---|---|---|
| `SolverRegistry(...)` | iterable of solver **instances** (`solvers=`) | iterable of **factories** (`factories=`); an instance raises `TypeError` | `SolverRegistry([ElectricalDCSolver])`, or `SolverRegistry([lambda: NgspiceDCSolver(invocation=…)])` |
| `SolverRegistry.register` | `register(solver) -> None`, stores the instance | `register(factory) -> SolverDefinition`; calls the factory once for the probe | `register(MySolver)` / `register(lambda: MySolver(args))` |
| `resolve`, `get`, `candidates`, `list`, `__iter__` | the stored instance, every call | a new session, every call; call shape unchanged | keep the session a request was given; do not re-resolve expecting earlier bindings |
| `selection_rule` | chose among stored instances | chooses among new sessions; must return one of them | none for rules that pick from the sequence |
| `SolverRegistry.definition(id, version)` | — | new, additive | — |
| `capabilities`, `capability_names`, `unregister`, `__len__` | — | unchanged | — |
| solver constructors | — | unchanged | — |
| `bind_*` / `prepare` / `solve` / `validate` / `extract_metrics` | — | unchanged. CSTR: each `solve` spends its own budget, and a re-execution reports its own evaluations, not the running sum | — |
| `PreparedSolve` | — | unchanged | — |
| `kinetics.cstr.solver.assemble` | — | unchanged shape; direct `rhs` calls charge `system.counter` as before | — |

Only five test modules called the registry and were migrated. No production,
experiment or pinned file did.

## 10. OUTPUT EQUIVALENCE

`sl15_outputs.py` ran 14 single-thread cases through a registry built the way
each tree expects. The before tree was the pre-fix worktree (`e737a6a`, `src/`
identical to `52dea3f`); the after tree was `e6dad0e`. Each case ran
bind → prepare → solve → extract_metrics → validate, and the DC convenience
entry point contributed provenance. Recorded per case:
- solver identity;
- prepared settings, payload and notes;
- raw values, convergence, iterations, warnings and diagnostics;
- metrics with units;
- the full validation report: checks, verdicts, attained levels;
- the DC result bundle, including provenance.

Only wall-clock fields were dropped.

| Cases | Result |
|---|---|
| DC ×2 operating points, DC bundle, battery ×2, lumped ×2, resistance ×2, CSTR prepare, **CSTR full solve**, conduction 1-D, scheme implicit, scheme explicit | **14/14 equivalent** |

## 11. PERFORMANCE BEFORE / AFTER

Sequential, single process, median of 7 repeats, per call; two runs of each
tree. Before is the pre-fix worktree; after is `e6dad0e`.

| Measurement | before r1 | before r2 | after r1 | after r2 |
|---|---:|---:|---:|---:|
| registry resolve (3 solvers) | 11.65 µs | 11.45 µs | 17.59 µs | 18.60 µs |
| registry request: resolve + bind + prepare + solve (lumped) | 42.12 µs | 46.88 µs | 48.71 µs | 48.75 µs |
| DC bind + prepare | 163.00 µs | 168.33 µs | 150.59 µs | 159.60 µs |
| DC bind + prepare + solve | 275.29 µs | 263.92 µs | 256.60 µs | 267.46 µs |
| battery bind + prepare + solve | 67.20 µs | 67.73 µs | 65.84 µs | 66.85 µs |
| CSTR bind + prepare + solve (K15 hold-out, BDF) | 20.96 ms | 21.85 ms | 20.70 ms | 20.60 ms |
| `solve_circuit` end to end (validation + provenance) | 1.29 ms | 1.43 ms | 1.31 ms | 1.38 ms |

Resolve costs about **+6 µs**: one factory call, one identity comparison and one
weak reference. The whole request costs +2 to +7 µs. The CSTR context-variable
lookup per right-hand-side evaluation is below run-to-run noise. Nothing was
optimized.

## 12. FAST / FULL / DOMAIN TESTS

| Run | Tree | Result |
|---|---|---|
| lifecycle + migrated registry suites (`test_scientific_core`, `test_dc_integration`, `test_model0r_realization_foundation`, `test_core_guards`) | `ee8d76e` + tests | green |
| committed reproductions (16 strict xfails) against the new registry alone | `ee8d76e` | 11 passed, 16 xfailed |
| **FAST** | `dd6e0a2` | 4116 passed, 3 skipped |
| **FULL** | `dd6e0a2` | 4657 passed, 3 skipped, 0 failed |
| lifecycle + kinetics domain suite | `e6dad0e` | 301 passed |
| **FAST** | `e6dad0e` | **4124 passed, 3 skipped** |
| **FULL** | `e6dad0e` | **4665 passed, 3 skipped, 0 failed** |
| **installed wheel** | wheels of `dd6e0a2` and `e6dad0e` | **LIFECYCLE SMOKE OK · 355 passed**, each |

| Guard group | Files | Result at `e6dad0e` |
|---|---|---|
| Contract Guard | `test_core_guards.py` (includes the registry's core-support refusals), `test_design_d0_contracts.py`, `test_data_boundary0.py` | 305 passed |
| Capability Boundary | the six domain applicability suites (battery, DC, DC rating, material, CSTR, lumped), `mcp/test_battery_boundary.py` | 293 passed |
| Scientific Truth | `domains/test_evidentiary_level_audit.py`, `kinetics/test_k2_truth_admissibility.py`, `oracles/test_independent_case_truth.py`, `oracles/test_independent_reason_truth.py`, `test_result_validity.py`, `test_blind_challenge_guards.py` | 294 passed, 3 skipped |

The repository does not name suites this way. The grouping is by what each file guards, and every file also passes inside FULL.

**Wheel details.**
- Built from `git archive e6dad0e`, installed with `--target` on `D:`, and run
  under `python -I -S` with no checkout on the path.
- 194 entries, 0 under `src/`; `engcore/py.typed` ships; `import src` and
  `import src.engcore` raise `ModuleNotFoundError`.
- The smoke script, against the installed package:
  - registers classes, and refuses a constructed instance;
  - isolates interleaved battery requests;
  - matches 32 concurrent lumped requests against their isolated baselines;
  - hands out a new session from every exit.
- Then `test_scientific_core.py`, the four trust-boundary files that need no
  checkout, and `inference/test_grid_inference.py`.

**No frozen artifact changed.** No file under `experiments/`,
`src/engcore/domains/thermal/`, `benchmarks/blind/` or `certification/` was
touched, nor `tests/mutation_guards.py` or either pinned test module. The
reproductions pinned against them pass inside FULL. Empirical datasets were not
re-run: single-solve runtime outputs are equivalent (§10).

## 13. FILES CHANGED

| File | Change |
|---|---|
| `src/engcore/scientific/solvers/registry.py` | factory/session registry, `SolverDefinition` |
| `src/engcore/domains/kinetics/cstr/solver.py` | per-execution evaluation budget |
| `tests/test_solver_lifecycle_state_isolation.py` | new — reproductions, then the concurrency, failure-isolation and registry-contract guards |
| `tests/test_scientific_core.py` | registry call sites register factories |
| `tests/domains/electrical/test_dc_integration.py` | same |
| `tests/test_model0r_realization_foundation.py` | same |
| `tests/test_core_guards.py` | same (the two core-support refusals register classes) |
| `benchmarks/hardening_solver_lifecycle/ROUND_REPORT.md` | new — this report |

## 14. COMMITS

| Commit | Message |
|---|---|
| `e737a6a` | test(solver): reproduce lifecycle state leakage |
| `ee8d76e` | refactor(registry): enforce safe solver lifecycle |
| `dd6e0a2` | test(solver): add concurrency and failure-isolation guards |
| `6e69699` | test(solver): observe a CSTR prepared solve spending its budget twice |
| `e6dad0e` | fix(kinetics): each execution of a CSTR prepared solve spends its own budget |
| `this commit` | docs(core): close solver lifecycle hardening sprint |

The suggested commit `refactor(solver): move problem state into prepared solve`
was not made, because there was nothing to move. `PreparedSolve` already owned
everything `solve` reads, as the SL-6 grep verified and SLM5/SLM6 guard. The one
misplaced state found went the other way, out of the prepared solve and into
the execution (`e6dad0e`). No commit was amended.

## 15. PUSH RESULT

Pushed to `origin` (`github.com:sharq-labs/forge`) as the **new branch `claude/solver-lifecycle-hardening-sprint-2`**, upstream tracking set. `git ls-remote` shows the remote head at `e6dad0e`, which includes every code and test commit in §14. This report commit follows on the same branch as a fast-forward. `main` was not touched, and nothing was force-pushed.

## 16. DEFERRED ITEMS

- **A directly constructed solver is still a session.**
  - Sharing one across independent requests shares its bindings. That is
    documented as outside the contract, not made impossible.
  - Making adapters stateless is blocked by the T1-pinned `Conduction1DSolver`
    and the pinned E1/E2 call shape.
- **Default problem ids ignore the operating point.** Inside one session, a
  second bind under the same id silently replaces the first for lumped,
  resistance, battery, CSTR, scheme and conduction. That is a problem-identity
  question for the domains, not a lifecycle one.
- **ngspice identity probe runs at session creation.** The registry's identity
  check calls the solver's lazy version probe then. For a session that is used,
  this moves the probe earlier rather than adding one. Sessions created only by
  `candidates()` / `list()` pay one probe each. No production registry holds
  ngspice.
- **Re-issue detection is best-effort in two cases.**
  - It is a check-then-record, so a pathological factory handing one object to
    two threads at the same instant could pass it.
  - A `__slots__` solver without `__weakref__` is not tracked.
  - The probe check always holds.
- **The SLM mutations live in the targeted script, not in the byte-pinned
  `tests/mutation_guards.py`.** Joining them is a certification-round change, as
  it is for Sprint 1's 36 targeted mutations.
- **`certification/current_core_v1.json` is further stale.**
  `scientific/solvers/registry.py` has now changed as well. Re-certification is
  a separate round.
- **Branch base.** This branch is based on Sprint 1's unmerged head `52dea3f`.
  Local `main` is behind `origin/main`, and the integration analysis from
  Sprint 1 still applies.
