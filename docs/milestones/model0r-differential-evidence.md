# MODEL0-R DIFFERENTIAL PROOF — Evidence

**Milestone:** `MODEL0-R DIFFERENTIAL PROOF`
**Decision status:** MODEL0-R remains `DESIGN-FROZEN` (not reopened)
**Evidence level:** `L2 DIFFERENTIATED`, **scoped** — see §8
**Falsifier finding D2:** resolved before commit — see §5.2
**Date of this record:** 2026-09-02
**Branch:** `model0r-realization-foundation`

> **Temporal boundary.** `docs/model0r-differential-prereg.md` is the
> preregistration: written before any source file was added or edited, and
> immutable. **This** document was written after execution. Deviations,
> corrections, adversarial findings and the final classification live here and
> nowhere else. Nothing here is back-written into the preregistration.
>
> This is **not** a freeze document.

---

# 1. Result against the preregistered hypothesis

**H1 is supported. H0 loses — but by less than the first draft of this
milestone claimed, and the margin matters.**

`ModelRealizationDefinition` is **not redundant**. Exactly one field both
(a) differs between the two realizations and (b) survives every reduction that
could be constructed:

```text
required_solver_capabilities
```

It cannot live on the model — two realizations of one model differ in it. It
cannot live on the solver — one solver identity executes both. Reducing it to a
`SolverSettings.options` string requires a scheme-string → capability-set
mapping, which is a magic-string branch in whatever performs the mapping.

That is a real, typed, differentiating, non-reducible fact. **It is also one
field's worth of independent information, not a vindication of the eleven-field
record**, and the fact that actually decided the selection in `TEST D2` — the
stability envelope — is not on the record at all.

## 1.1 Executed results

Physical slab fixed at `L = 0.1 m`, `α = 1.2×10⁻⁵ m²/s`, `t_end = 60 s`.
Closed-form `u(L/2, 60 s) = 0.4913436406431834`.

| Config | `r` | Realization | `u:midpoint` | `max|u|` | Validation |
|---|---|---|---|---|---|
| **S** (32, 160) | 0.4608 | implicit BE | 0.492397 | 0.492397 | pass |
| **S** (32, 160) | 0.4608 | explicit FTCS | 0.490848 | 0.490848 | pass |
| **U** (32, 80) | 0.9216 | implicit BE | 0.493166 | 0.493166 | pass |
| **U** (32, 80) | 0.9216 | explicit FTCS | **−1.06×10¹⁷** | **1.12×10¹⁷** | **fail** |

Relative error against the closed form at config S: implicit `2.14×10⁻³`,
explicit `1.01×10⁻³`, byte-pinned `Conduction1DSolver` `2.14×10⁻³` — identical
to the new implicit realization to 1e-9.

## 1.2 Predicted vs. observed (prereg §6)

| # | Prediction | Observed |
|---|---|---|
| 1 | Both agree with the closed form at config S; `max|u| ≤ 1` | **confirmed** |
| 2 | FTCS at config U violates the maximum principle catastrophically; `max|u| > 10⁶` or non-finite | **confirmed** — `1.12×10¹⁷`, matching the predicted `≈10³⁴` amplification of round-off-level content |
| 3 | Predeclared `r` values are correct | **confirmed** — 0.4608 and 0.9216 exactly |
| 4 | `TEST D1` passes with the contract unchanged | **confirmed** |
| 5 | `TEST D2` needs information with no typed home on the record | **confirmed** |
| 6 | Two runs of one solver produce identical `models` and `solvers` | **confirmed** |

No prediction was falsified.

**One observation that was not predicted** (`test_g5`): at config U the explicit
march stayed *finite*, so the solver honestly reported `CONVERGED` while
validation `FAIL`ed. The project's own invariant — *numerical convergence is not
scientific validity* — appeared unprompted, and it is the reason admissibility
has to be decidable **before** execution rather than inferred from the outcome.

---

# 2. Deviations from the preregistration

Recorded because a deviation is evidence about the process.

## 2.1 The §5 gate was analysed first and *built* second

Prereg §5 required the reduction to be **constructed and executed first, as a
gate**, with the scheme carried in `SolverSettings.options`.

What actually happened: a field-by-field reconstruction was run against the
existing frozen solver before implementation (it showed the realization record's
fields absent from `(model, solver, settings, provenance)`), and that was
treated as satisfying the gate. **It did not.** It showed fields were *absent*,
not that a working realization-free system loses something. The steel-man was
analysed, not executed.

This was caught by `architecture-falsifier` (finding D4) and **corrected**:
`ReducedSchemeSolver` now exists, carries the scheme as a string in
`SolverSettings.options` exactly as the frozen production solver does, runs both
schemes, and reproduces the typed path's numbers to 1e-12 (`test_g2`). H0 is
refuted by measuring what the working reduction costs (`test_g2b`), not by the
reduction failing to run.

The stopping condition was re-evaluated against the built reduction and **not**
met: the reduction does not reconstruct everything.

## 2.2 The first loss accounting overstated the result roughly fourfold

The first `test_g4` asserted eight realization fields were "lost" by the
reduction. Four of those were wrong or disqualified:

| Field | First claim | Corrected |
|---|---|---|
| `assumptions` | lost | **present** — `solve_with_realization` writes realization assumptions into provenance, so the stability bound is verbatim in the reduction. It registered as "lost" only because the whole JSON list, brackets included, is not a substring |
| `realization_id`, `name`, `description` | lost | identity and prose, which **prereg §4 disqualifies in advance** |
| `formulation` | lost | held constant across the pair by design, so it differentiates nothing here whether or not it survives |
| `version` | lost | **ambiguous** — the string is present, but only because model, realization and solver all happen to be `0.1.0` and nothing says whose it is |
| `provided_capabilities` | lost | **genuinely lost and machine-usable** — but identical on both realizations, so it does not differentiate them |
| `required_solver_capabilities` | lost | **genuinely lost, machine-usable, and differentiating.** The one that carries the result |

The corrected accounting is asserted in `test_g4` rather than narrated, and the
test now fails if the bound stops being present in provenance.

## 2.3 One change beyond the realization contract

Prereg §8.4 anticipated this and it happened as anticipated:
`ProvenanceRecord` gained `realizations` and went to `provenance_record/2` with
backward reading of `/1`. `ModelRealizationDefinition` was **not** modified
(`test_x3` asserts its exact field set).

---

# 3. Field-by-field classification (prereg §4)

```text
A MODEL-LEVEL   B REALIZATION-LEVEL   C SOLVER-LEVEL
D RUNTIME/EXECUTION-LEVEL             E CURRENTLY AMBIGUOUS
```

| Field | Class | Exercised? | Evidence from this milestone |
|---|---|---|---|
| `realization_id` | **B** | yes | Identity only. Prereg §4 disqualifies identifiers as evidence |
| `version` | **B** | yes | Identity only; ambiguous under reduction (§2.2) |
| `model` | **A** (back-link) | yes | Points at the model. Reconstructible from `provenance.models`; carries no independent information |
| `formulation` | **B** | **no** | Held constant at `PDE` on purpose. **Zero differential evidence** for this field |
| `name`, `description` | **B** | yes | Prose. Disqualified by §4 |
| `provided_capabilities` | **B** | partly | Lost by the reduction and machine-usable, but identical on both members — does not differentiate them. Consumed by nothing in the execution path |
| `required_capabilities` | **E** | **no** | Empty on both members. Unexercised |
| `required_solver_capabilities` | **B** | **yes** | **The surviving field.** Differs between members, machine-usable, lost by the reduction, no home on model or solver |
| `assumptions` | **B**, untyped | yes | Carries the stability bound — but as prose, and it flows into provenance, so the reduction has it too. A selector cannot evaluate it |
| `implementation` | **B**, opaque | yes | Never branched on, by design. Identical on both members here |

**Nothing classified into C or D that was supposed to be B.** No supposedly
realization-level field turned out to belong on the solver or in runtime
settings. That is the result that counts *for* MODEL0-R.

**Two fields classified B but unexercised** (`formulation`,
`required_capabilities`) and **one that is B but untyped** (`assumptions`). Those
count against the record's *current adequacy*, not against the boundary.

---

# 4. The central finding: the deciding fact is not on the record

The selection in `TEST D2` is driven by an applicability envelope
(`r ≤ 1/2`) that reaches the code through `_APPLICABILITY`, a **module-global
side table keyed by realization identity**. On the realization record the bound
exists only as free text in `assumptions`.

The envelope itself reuses `ValidityDomain` / `RangeCondition` — core types that
already carry exactly these semantics at the *model* layer. Nothing was
invented. The type is simply not reachable from a realization record, so the
domain holds it beside the record instead of on it.

**The obvious correction is the wrong one, and this milestone's stress cases say
so.** Promoting `_APPLICABILITY` into a typed `applicability: ValidityDomain`
field on `ModelRealizationDefinition` would freeze half a contract:

* **Anisotropic / multi-dimensional.** The 2-D and 3-D FTCS bound is
  `r_x + r_y + r_z ≤ 1/2` — a **joint** condition over several context
  variables. `ValidityDomain` ANDs independent per-name conditions and
  `RangeCondition` bounds are scalar `Quantity` values. No condition type
  expresses a function of several names.
* **State-dependent properties.** With `α = α(T)`, `r` is not decidable before
  execution — and pre-execution decidability is the entire property `TEST D2`
  rests on.
* **No typed home for the evaluation context.** `fourier_number` is a function
  of the discretization, which lives in `ScientificProblem.metadata` as strings
  and in a domain object bound out of band. A typed envelope evaluated against
  an untyped context buys less than it looks like.

So the evidenced recommendation is **not** "add the field". It is: the record
needs an applicability concept, and the shape it should take is not yet
determined by evidence. `_APPLICABILITY` stays a documented interim, and the
decision is deferred to a milestone that has a second, structurally different
consumer of an envelope.

---

# 5. Falsifier findings and resolutions

`architecture-falsifier`, primary attack *"prove `ModelRealizationDefinition` is
redundant"*. Verdict: **SURVIVES WITH REQUIRED CHANGES**. No `BLOCKER`.

| # | Finding | Resolution |
|---|---|---|
| **D1** | `core:linear_solve` minted a second name for the core-owned `core:linear_system`; capability identity is exact-string with no registry, so a realization requiring one would silently miss a solver providing the other | **Fixed.** `CORE_LINEAR_SOLVE is CoreCapabilities.LINEAR_SYSTEM`. `test_x7` also refuses any future `core:`-namespaced requirement that is not core-owned |
| **D2** | The three provenance tuples are unaligned; at arity > 1 nothing says which realization computed which model, and a four-model producer already exists (`models_for_circuit`) | **Fixed before commit — see §5.2.** A typed `ExecutionBinding` now carries the ternary relation structurally; the ambiguous `realizations` tuple never shipped |
| **D3** | `derived(models=…)` inherited `realizations`, producing a record naming model B with a realization of model A; one hand-rolled copy site dropped the field entirely | **Fixed.** `derived()` refuses to inherit `realizations` when `models` is overridden without an explicit `realizations=`; `study.py:674` now propagates it. `test_x8` |
| **D4** | The preregistered §5 gate was analysed, not executed | **Fixed.** §2.1 |
| **D5** | `solver_capability_gap` is computed over self-declarations, and the byte-pinned `Conduction1DSolver` performs a linear solve while declaring none — a gap that can never be closed | **Recorded.** `test_x9` asserts both the gap and that the frozen source calls `spla.splu`. First concrete consequence of the §57.1 process risk |
| **C5** | Loss accounting inflated | **Fixed.** §2.2 |
| **C7** | The applicability verdict never reaches the produced record — the sentence *"the model is valid here but this realization is not adequate"* is demonstrated in tests and is not expressible in the result | **Recorded as a gap.** Not fixed: it needs the §4 decision first |
| **C8** | The bound is stated twice — prose on the record, typed in the side table — with nothing keeping them consistent | **Recorded.** A direct consequence of §4 and it disappears when §4 is resolved |
| **C9** | The realization travelled through solver mutable state, and provenance recorded the orchestrator's *argument* rather than what executed | **Fixed.** Provenance reads back `prepared.payload.realization`; `test_x11`. The rebind guard was narrowed after it proved too strict — see §5.1 |
| **C10** | `provided_capabilities` is mandatory and unconsumed; `required_capabilities` empty; near-homograph capability names in one flat space | **Recorded** in §3. Not fixed: removing a mandatory field is a MODEL0-R contract change |

## 5.1 One correction that was itself corrected

The first fix for C9 refused to rebind a *different realization* to one problem
id, by analogy with the frozen `bind_slab`. Three tests failed immediately, and
they were right to: **one problem computed two ways is the entire milestone.**
The frozen precedent keys on the slab *fingerprint* — it protects the physics,
not the choice of computation. The guard was narrowed to match, and the C9
concern is carried entirely by reading the realization back from the prepared
solve.

Recorded because a guard that would have made the proof's own comparison illegal
is a useful data point about where the boundary actually sits.

## 5.2 D2 resolved: the ternary relation is typed and structural

The first form of this milestone added a `realizations` tuple beside `models`
and `solvers`. That was the D2 defect: **three independent participant sets
cannot preserve `model → realization → solver` once any of them holds more than
one member.** It was fixed before commit rather than shipped and versioned
around.

`ProvenanceRecord` now carries:

```text
bindings : tuple[ExecutionBinding, ...]        CANONICAL
    ExecutionBinding(model: ModelReference,
                     realization: RealizationReference | None,
                     solver: SolverIdentity)

models, solvers : participant sets             DERIVED VIEW when bindings exist
realizations    : derived property             NOT a field, NOT serialized
```

Five properties, each asserted by a test:

* **Association is structural, never positional.** It comes from the three
  fields of one record. `test_r3` builds a deliberately *crossed* pairing and
  shows that zipping the participant sets produces the opposite of the truth;
  reversing construction order changes nothing.
* **One source of truth.** `realizations` is a derived property with nowhere to
  write it, and is deliberately **not** serialized. Participant sets that
  contradict a binding are refused rather than reconciled (`test_r7`); extra
  participants no binding covers are allowed, because partial knowledge is
  honest and contradiction is not.
* **The realization record is untouched.** The concrete solver lives on the
  binding. A realization is a way of computing a claim, not one execution of
  it, and the same realization on a second backend stays the same realization —
  `test_r4` merges two runs and reads two solvers back for one realization.
* **`realization=None` is a real answer.** Every producer predating MODEL0-R
  computed a model with no declared realization, and such a binding still
  carries a true model→solver association.
* **Nothing is fabricated from old payloads.** `provenance_record/1` loads with
  no bindings *even at arity one*, where a binding looks determined. The record
  never stated that the solver computed that model; inventing it would put a
  claim into the record its author never made (`test_f4`).

`provenance_record/2` was **redefined rather than superseded**: zero persisted
records exist, so the clean schema is the one that ships, instead of an
ambiguous `/2` plus a corrective `/3`. `/1` is still read and never written.

New types: `ExecutionBinding` (in `results/provenance.py`) and
`RealizationReference` (in `realizations/definition.py`, mirroring the existing
`ModelReference` exactly). `ModelRealizationDefinition` gained a `reference()`
**method** and no field — `test_r8` asserts its field set is unchanged.

---

# 6. Architecture fitness (master context §59)

| # | Question | Answer |
|---|---|---|
| 1 | Frozen core contract or schema changed? | **Yes, one:** `ProvenanceRecord` → `provenance_record/2`, carrying `ExecutionBinding`. Required by `TEST F` and then by D2; the alternative was realization identity in untyped `metadata`, which fitness question 5 counts as a failure. `ModelRealizationDefinition` was **not** changed |
| 2 | Serialized records required migration? | **No.** Nothing pins `provenance_record/1`; no on-disk corpus carries a `ProvenanceRecord`; no frozen experiment digest hashes one. Zero measured records — the same position DATA-BOUNDARY0 §4.5 recorded, and the reason `/2` could be redefined cleanly instead of superseded |
| 3 | Domain-specific branch added to universal core? | **No.** `test_x2` scans every file under `engcore/scientific` for five domain strings |
| 4 | Provider identity leaked into scientific semantics? | **No.** `test_e2` scans the serialized realization for `splu`, `solve_banded`, `scipy`, `numpy`, `thread`, `device`, `gpu`, tolerances |
| 5 | Untyped metadata used as an escape hatch? | **No.** `test_f2` asserts realization identity is absent from `provenance.metadata` and present as a typed field. The one place untyped text does carry scientific content is `assumptions` (§4) |
| 6 | Existing abstraction duplicated outside core? | **One, and it was fixed:** `core:linear_solve` duplicated `core:linear_system` (D1). The applicability envelope *reuses* `ValidityDomain`/`RangeCondition` rather than duplicating them |
| 7 | New semantic abstraction required? | **No.** Two realization records, one solver class, one orchestration function |
| 8 | Frozen invariant violated? | **No.** `test_x1` re-asserts the T1/T2/T3 digest map and set-equality over `*.py` under `domains/thermal` |
| 9 | Implementable from the published contract alone? | **Almost.** The realizations, registry use and capability gap needed only published contracts. The applicability envelope did not — it needed a side table, which is finding §4 |

**Core Edit Ratio**, secondary diagnostic only: 51 changed lines in
`engcore/scientific` (all in `provenance.py`), 4 in `engcore/systems`, against
~700 new domain lines and ~800 test lines. The number is unremarkable and it is
not what any of the above rests on.

---

# 7. Tests

| Suite | Command | Result |
|---|---|---|
| Targeted | `pytest tests/test_model0r_differential.py -q` | **53 passed** |
| FAST | `pytest tests/ -m "not expensive" -q --basetemp=…` | **1140 passed**, 495 deselected |
| FULL | `pytest tests/ -q --basetemp=…` | **1635 passed**, 0 failed |

Baseline before this milestone was 1582 FULL / 1087 FAST. `1582 + 53 = 1635` and
`1087 + 53 = 1140`: **no pre-existing test changed and none broke**, including
across the `provenance_record/2` schema change. No test file other than the new
one was edited.

*(A local `--basetemp` is required on this machine: 23 tests that use `tmp_path`
error with `PermissionError` against the default Windows temp root. Environment,
not code — it is why `.pytest_tmp_*` directories exist in the repo root.)*

---

# 8. Evidence level

**Decided by the founder, 2026-09-02:**

```text
MODEL0-R separation:  DESIGN-FROZEN / L2 DIFFERENTIATED
```

**The `L2` claim is scoped to exactly two things:**

* the `Model != Realization != Solver` separation, and
* `required_solver_capabilities` as realization-level information.

**No unexercised `ModelRealizationDefinition` field is promoted to `L2`.** In
particular `formulation`, `required_capabilities`, `implementation`,
`ModelFormulation.DISCRETE` and `ModelFormulation.DAE` gained **zero** evidence
from this milestone and remain where they were.

## 8.1 Basis for the differentiation

Material differentiation rests on **independently defined numerical behaviour
and an executed stability distinction**, not on there being two classes:

* `r ≤ 1/2` is a theorem of the FTCS scheme, and `test_b4` **measures** the
  amplification factor `|1 − 4r|` from the running implementation at both
  configurations rather than asserting it. No author could have chosen it
  otherwise.
* The distinction was executed, not argued: at `r = 0.9216` the two
  realizations disagree by seventeen orders of magnitude, one validating and
  one failing.
* The frozen domain recorded the governing quantity
  (`ConductionSlab.fourier_number`) before this milestone existed.
* One member is cross-validated against byte-pinned code from an earlier commit
  that this milestone cannot edit.

## 8.2 Evidence-lineage limitation (not a failure of differentiation)

Both realization records and both scheme solvers were written by one author, on
one day, against one interface. **This is recorded as a limitation of evidence
lineage, not as a defect in the differentiation** — the differentiator is a
theorem, so common authorship could not have manufactured it.

It does bound what comes next: no code Crafty did not write is involved
anywhere in this milestone, so nothing here speaks to a heterogeneous external
provider. `L3 STRESSED` is not claimable at all — no scale, concurrency,
latency or failure injection.

---

# 9. Known unknowns carried forward

1. ~~Realization → model pairing in provenance (D2).~~ **Resolved** — §5.2.
   What remains open is narrower: a binding names one model, one realization
   and one solver, so a computation genuinely produced by *several* solvers
   acting together is representable only as several bindings, and whether that
   is the right shape for a coupled solve is untested here.
2. **The applicability envelope's shape** (§4). Needed, but the scalar
   per-name form would be wrong for anisotropic and state-dependent cases.
3. **Where the evaluation context lives.** `fourier_number` is a function of the
   discretization, which has no typed home in any universal record.
4. **Capability granularity** (D5). A gap is over declarations; a bundled
   domain capability and a primitive operation share one flat namespace, and one
   byte-pinned solver's under-declaration can never be corrected.
5. **`provided_capabilities` is mandatory and unconsumed** (C10).
6. **`formulation` has no differential evidence.** Held constant on purpose.
7. **`DISCRETE` and `DAE` still have no consumer.** Unchanged, still provisional.
8. **Nothing heterogeneous, external, concurrent, distributed or at scale.**

---

# 10. Final classification

**Decision status: MODEL0-R remains `DESIGN-FROZEN`.** Not reopened, not
modified. `ModelRealizationDefinition`'s field set is byte-identical to what it
was before this milestone.

**Verdict: KEEP.** The realization boundary survives the strongest reduction
that could be built. It is not redundant.

**With one evidenced but deliberately unapplied modification:** the record needs
an applicability concept, and this milestone establishes that the obvious shape
for it would be wrong. That decision is deferred with its reasons recorded,
not left implicit.
