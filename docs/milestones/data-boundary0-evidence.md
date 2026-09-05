# DATA-BOUNDARY0 — Evidence

**Milestone:** `DATA-BOUNDARY0` — scientific data identity vs. storage location
**Decision status:** `PROPOSED`
**Evidence level:** `L1 EXERCISED`
**Date of this record:** 2026-09-02
**Branch:** `model0r-realization-foundation`

> **Temporal boundary — read this first.**
>
> `docs/data-boundary0-prereg.md` is the **preregistration**: everything it
> contains was written *before* any source file was added or edited, and it is
> immutable. It records what was committed to before results were observed.
>
> **This** document is the **evidence record**: everything in it was written
> *after* execution. Executed results, corrections, adversarial findings, the
> schema decision, known unknowns and process risks live here and nowhere else.
> Nothing here may be back-written into the preregistration.
>
> This is **not** a freeze document. Nothing in DATA-BOUNDARY0 is
> `DESIGN-FROZEN`. No contract described here is closed to revision.

---

# 1. Result against the preregistered hypothesis

The preregistered hypothesis (prereg §2) required a record `R` satisfying six
properties. All six were executed against the real solved field of the frozen
`Conduction1DSolver`, at four spatial resolutions.

| | Preregistered requirement | Outcome | Executed by |
|---|---|---|---|
| a | `R` is small and O(1) in the size of the data | **holds** | `b3` |
| b | `R` determines *which* data is meant, independently of location | **holds** | `f1`, `f2` |
| c | Relocation leaves `R` and the serialized result byte-identical | **holds** | `c1`, `c2`, `f3` |
| d | Substitution or corruption is detected at resolution | **holds** | `d1`–`d4` |
| e | Removal produces a typed failure, not empty or invented data | **holds** | `e1`–`e3` |
| f | `R` is added additively, without rewriting scalar consumers or solvers | **holds, with one qualification** | `a1`–`a6` |

**The qualification on (f).** Additivity holds at the level of *code*: no
existing solver, scalar consumer or test was modified, and the frozen thermal
tree was not touched. It does **not** hold at the level of the *serialized
schema*: `scientific_result` and `raw_solver_output` are now written at version
`/2`. That change was made deliberately and after review; §4 records why.

## 1.1 Predicted vs. observed (prereg §8)

| # | Prediction | Observed |
|---|---|---|
| 1 | Record size constant across a 128× resolution change | **confirmed** — variation is only decimal digits of `n_cells`/`n_steps` |
| 2 | Encoded field size grows linearly with resolution | **confirmed** — >50× growth over the same span |
| 3 | Serialized result byte-identical across relocation | **confirmed** — exact string comparison, two relocations, two roots |
| 4 | One-byte corruption and truncation both detected | **confirmed**, and distinguished from each other in the message |
| 5 | Deletion raises a typed unavailability error while `result.values` stays usable | **confirmed** |
| 6 | No existing test needs to change | **confirmed** — the only test file edited is the new `tests/test_data_boundary0.py` |

No prediction was falsified. No surprise was recorded.

## 1.2 Fail conditions (prereg §5)

F1–F7 were all checked and **none triggered**. F2 and F4 are checked by
scanning every field and serialized key of the reference, and by constructing
the same reference through two structurally different backends rooted at
different directories.

---

# 2. Architecture-falsifier findings and what was done about them

The adversarial pass produced findings that were **reasoning**, not executed
evidence. Each accepted finding was converted into a test, so it is now both.
These live in the `FALSIFIER CORRECTIONS` block of `tests/test_data_boundary0.py`.

| Finding | Substance | Resolution | Test |
|---|---|---|---|
| D-2 | A producer exposing a non-float64 or non-contiguous buffer could be silently upcast, giving a digest for data nobody computed | Such a buffer is **refused**, not converted | `x1` |
| C-10 | `relocate(remove_source=True)` is the only operation that can leave zero copies; it must not trust the destination write | Destination is re-verified through a resolver before the source is dropped | `x3` |
| C-16 | A milestone about typed failure must not surface a bare `KeyError`/`TypeError` from three frames down | Capture failures are wrapped in `BulkDataError` | `x4` |
| C-2 | Content addressing means dedup **and** an ownership hazard: a move affects every reference to that content | Documented as a consequence, asserted as a fact; retention remains a preregistered non-goal | `x5` |
| D-3 | Capture ordering: both `validate` **and** `extract_metrics` are same-solve in-process consumers | Capture happens after both; asserted structurally against the source | `x6` |
| C-15 | Every zero-count reference shares one digest | **Reconsidered — see §3.4.** Originally a universal ban; now documented and allowed | `x2` |
| D-4 | `ScientificResult.artifacts` is an untyped string channel beside a scientific record | **Reconsidered — see §3.3.** Originally narrowed; now restored with a fitness rule | `f4`, `f4b` |

---

# 3. Correction pass (post-execution)

The first implementation passed the hypothesis at L1 and was then corrected
before commit. Each correction below removes an overreach, not a mechanism.

## 3.1 Content identity is not scientific equivalence

The first draft's prose implied in several places that a byte digest attests to
scientific sameness — most concretely the claim that "two identical
computations run on two machines would disagree" if identity included a path,
which reads as a promise that they otherwise agree. They do not, in general.

Corrected throughout. The digest proves **content identity, integrity,
relocation stability and content addressing**, over bytes and nothing else.
Two computations that are scientifically equivalent to within tolerance
normally produce different digests: hardware, compiler, BLAS, thread count,
reduction order and library version routinely move the last bits without
moving the science. A digest match likewise says nothing about whether either
computation was correct or converged — those are validation and uncertainty
questions, and they stay separate fields on the result.

Tolerance-level comparison of two datasets is a real and different operation.
Nothing in this milestone implements it or substitutes for it.

**The byte-exact mechanism is unchanged.** Only the claims about what it proved
were wrong.

## 3.2 No path-shape heuristic on scientific names

The first draft rejected a reference `name` containing `/`, `\` or `://`. That
is a storage concern policing scientific vocabulary. `phase/alpha`,
`velocity/x` and `species:H2O` are ordinary scientific names, and there is no
storage field on the reference for such a name to be confused with — the
heuristic protected nothing and cost real vocabulary. Removed
(`reject_location_like` and its marker table are gone).

Storage independence is achieved **structurally**: the record has no location
field. `f2` still asserts that no store name, root or path fragment appears
anywhere in the reference or the serialized result; `f4c` asserts that
punctuated scientific names are accepted.

## 3.3 `artifacts` restored

The first draft narrowed the pre-existing `ScientificResult.artifacts` field to
reject path-shaped labels, on the grounds that it had no in-repo producer.
**Absence of an in-repo producer is not evidence that no external caller
exists**, and the rejection also applied on the deserialization path, which
would have made a previously valid stored record unloadable. Restored to its
previous accepted behaviour.

Replaced with documentation plus a fitness rule: `artifacts` is legacy and
generic, and new scientific-data code must not use it as the bulk-data channel.
`f4b` asserts statically that no module introduced by this milestone writes it.
This constrains new code only and breaks no stored value.

## 3.4 The universal `count > 0` rule removed

The first draft refused `count == 0` everywhere, reasoning that all empty
payloads share one digest. The observation is true; the universal prohibition
does not follow. This milestone has **no evidence** that an empty scientific
dataset is invalid, and no storage invariant here requires a non-empty payload
— an empty blob round-trips through both backends and verifies (`x2`).

`count >= 0` is now the rule; `count < 0` is still refused. The shared-digest
consequence is documented on the field and asserted as an executed fact.

The Conduction1D consumer was inspected for a non-emptiness requirement and
**does not have one**: the frozen solver with `n_cells >= 1` cannot produce an
empty field. No guard was added there either — it would have been speculative
validation of exactly the kind §3.6 removes.

Related prose fix: the "never returns empty or zero-filled data" rule in
`engcore.data` now says what it always meant — nothing is ever *fabricated*.
Data that was genuinely stored empty and verifies is a real answer.

## 3.5 The reference is not frozen

The first draft recorded a permanent rule: the reference is "identity-only and
closed", and every future descriptor "attaches as a separate sibling record
keyed by reference name, never as a new field here". A micro-spike does not get
to legislate that.

Removed. What is recorded instead:

* DATA-BOUNDARY0 **intentionally does not define `FIELD0`/`TOPO0` descriptors**.
* Future shape, support, frame and topology semantics remain **deferred**.
* One factual constraint, stated as a property of the code rather than a law:
  `require_schema` was an exact string match, so a version change made stored
  records unloadable by the reader that pinned the old string. That constrains
  *how* an evolution is rolled out. §4 is the first exercise of exactly that
  constraint, and it shows the cost is a small reader-side accept-set — not a
  migration framework.

## 3.6 Minimization

Removed as unused, speculative or duplicative:

| Removed | Why |
|---|---|
| `reject_location_like` + `_LOCATION_MARKERS` | §3.2 |
| `ScientificDataReference.matches()` | duplicated the resolver's length+digest check; the resolver is the single place integrity is decided |
| `data_reference_names()` | no caller anywhere |
| `resolve_all()` | no caller anywhere |
| `store.encode()` re-export | no caller; `encode_float64` is importable |
| `BulkDataResolver.stores` / `.store_names` | no external caller; the one internal use is now inline |
| `@runtime_checkable` on `BulkDataStore` | no `isinstance` check exists |
| `for_values(dtype=…)` parameter | one legal value; the encoder is float64-only and the constructor already rejects anything else |
| `for_values`' own dtype guard | third redundant check of the same closed set |
| `content_digest` / `encode_float64` / `decode_float64` re-exports from `engcore.scientific.results` | public surface with no consumer |

`InMemoryBulkStore.__len__` was removed and **restored**: it is asserted
against by `x5`, so it was not dead.

Kept deliberately, because each is exercised and load-bearing: the relocation
test, integrity detection (length **and** digest), the typed missing-artifact
failure, scalar backward compatibility, the O(1)-in-data-size record, the
storage-independent reference, both dependency-direction tests, the
duplicate-name and scalar/bulk name-collision rules, `InMemoryBulkStore.corrupt`
and `__len__`, and `capture_bulk(required=…)`.

### Production lines of code

| | Total lines | Non-blank | Code (excl. comments/docstrings) |
|---|---|---|---|
| Before minimization | 1262 | 1071 | 603 |
| After minimization | 1229 | 1048 | **545** |

Code lines −58 (−9.6%). Total fell only 33 because the corrective
documentation from §3.1 and §3.5 grew while the code shrank
(`data_reference.py`: 186 → 154 code lines). The §4 schema work then added
back a small, deliberate amount.

---

# 4. Schema decision: `scientific_result/2` and `raw_solver_output/2`

## 4.1 The question

Does adding optional `data_references` to `scientific_result/1` create a
semantic forward-compatibility problem, because an older reader silently drops
the new reference?

## 4.2 The governing rule

**An old reader silently dropping `data_references` is not acceptable if those
references are part of the scientific content of the result.**

They are. A reference is the result's statement of *which bulk data this claim
is about*. A reader that returns the record while dropping it produces a
scientific result that silently understates what was computed — a result that
looks complete and is not. For `RawSolverOutput` the same holds and is if
anything sharper: once `capture_bulk` has moved an array out of `diagnostics`,
`data_references` is the **only** statement that the solve produced bulk data
at all, so a reader that dropped it would report the solve as having produced
nothing.

That is a different class of loss from dropping a decorative field, and it
governs the decision.

## 4.3 The policy implemented

The smallest thing that produces the required property:

* the writer emits `scientific_result/2` and `raw_solver_output/2`, always;
* the reader accepts `/1` **and** `/2`, via a two-element tuple of exact
  strings (`SUPPORTED_RESULT_SCHEMAS`, `SUPPORTED_RAW_OUTPUT_SCHEMAS`);
* a `/1` payload loads with `data_references = ()`, **by version, not by key
  presence** — `/1` predates the contract and cannot have written one;
* a `/2` payload loads its references normally.

One helper, `require_schema_any(payload, accepted)` in
`engcore.scientific.serialization`, plus one ternary branch in each `from_dict`.
Deliberately a tuple of exact strings, **not** a version range or comparison: a
range would admit versions that do not exist yet, which is the failure
`require_schema` existed to prevent. `require_schema` itself is unchanged and
still used by every other record.

**No generic migration framework was built, and none is implied.** There is no
upgrade path registry, no per-version transformer, no schema descriptor. Adding
a third version later means adding one string and, if it needs one, one more
branch.

## 4.4 Behaviour, stated as the desired property

| Direction | Behaviour | Test |
|---|---|---|
| OLD payload (`/1`) → NEW reader | **succeeds**, `data_references == ()` | `a3`, `a3b`, `a4` |
| NEW payload (`/2`) → NEW reader | **succeeds**, references round-trip | `a2c`, `a4`, `g2` |
| NEW payload (`/2`) → OLD reader | **fails loudly** on schema mismatch | `a2b` |
| NEW payload → OLD reader, silently losing scientific data | **impossible** | `a2b` |
| Unknown version (`/3`) → NEW reader | **fails loudly** — the accept-set is exact | `a2b` |

Re-serializing a `/1` payload through this reader writes `/2`. That is the
intended one-way upgrade and is asserted (`a3`, `a4`).

## 4.5 What this costs, recorded honestly

A reader older than this milestone can no longer read *any* new payload,
including scalar-only ones that carry no references. That cost is real and was
accepted, because the alternative — an old reader succeeding while dropping
scientific content — is the failure mode the rule in §4.2 forbids. Loud failure
is recoverable; silent understatement of a scientific claim is not.

The migration cost of the bump itself is **zero measured records**: there is no
persistence layer (prereg §6 non-goal), no on-disk result corpus, and no
external consumer pinned to a version. It is cheaper to do now than at any
later point.

*(Record of a superseded position: an earlier draft of this analysis
recommended KEEP `/1`, weighing "silent loss of an optional field for readers
that do not exist" against "hard failure on every payload". That weighing
treated `data_references` as optional decoration. It is scientific content, and
under the §4.2 rule the earlier recommendation does not survive. Recorded
because a reversed decision is evidence about the decision process, not
something to tidy away.)*

---

# 5. Tests

| Suite | Command | Result |
|---|---|---|
| Targeted DATA-BOUNDARY0 | `pytest tests/test_data_boundary0.py -q` | **52 passed** |
| FAST | `pytest tests/ -m "not expensive" -q` | **1087 passed**, 495 deselected, 9.0 s |
| FULL | `pytest tests/ -q -rsxX` | **1582 passed**, 0 failed |

No pre-existing test file was modified. The frozen thermal tree and the three
frozen experiment configs are byte-unchanged; `a5`, `a6` and the two
`test_thermal_t1_fidelity_inference` pin tests all pass.

---

# 6. Known unknowns

Recorded so that the limits of this evidence are explicit and are not inherited
as settled facts.

1. **Heterogeneous storage.** Both backends were written by one author on one
   day against one interface. Nothing here differentiates the contract against
   a provider Crafty did not write (object storage, a distributed filesystem,
   device memory, a database blob store). This is why the evidence level is L1
   and not L2.
2. **Scale, concurrency and latency.** No test exceeds a few thousand values,
   nothing is concurrent, nothing is remote. Failure injection stops at
   single-artifact corruption, truncation and deletion.
3. **Non-float64 data.** `dtype` is a closed set with one member. Integer,
   complex, mixed-precision and structured data are unexercised, and the digest
   domain-separation tag is designed for, but not tested against, a second
   dtype.
4. **Multi-dimensional and non-contiguous data.** `count` is a count. Anything
   with a shape is out of scope and its representation is undecided.
5. **Lifetime and ownership.** Content addressing shares blobs; there is no
   retention, ownership, reference-counting or garbage collection. A move with
   `remove_source=True` affects every reference to that content (`x5`). This is
   documented behaviour, not a solved problem.
6. **Whether an empty scientific dataset is ever meaningful.** §3.4 removed the
   universal ban for lack of evidence either way. That is an absence of
   evidence, not evidence of validity.
7. **Whether `FIELD0`/`TOPO0` descriptors belong on the reference or beside
   it.** Deliberately undecided; see §3.5.
8. **Whether a third schema version needs more than an accept-set.** §4's
   mechanism is sufficient for an additive change. A change that alters the
   *meaning* of an existing field has not been faced and is not designed for.

---

# 7. Process risk (recorded, not addressed here)

**Frozen experimental evidence must not imply that production code is immutable
forever.**

`src/engcore/domains/thermal/` is pinned byte-for-byte by three frozen
experiments (T1/T2/T3) because those experiments measured a property of that
exact solver. Pinning is the correct way to protect an experimental claim. It
is *not* a correct way to own production code indefinitely: a defect in a
frozen file today has no sanctioned repair path, and the pin does not
distinguish "this evidence is about this code" from "this code may never
change".

DATA-BOUNDARY0 worked *around* the freeze — the bulk path is a bridge module
beside the frozen tree — which was the right call for a spike and is not a
general answer. Designing the unfreeze / evidence-versioning procedure is
**out of scope for this milestone and was not attempted.** It is logged here to
be addressed by whichever milestone next needs to change that tree.

---

# 8. Final classification and recommendation

**Decision status: `PROPOSED`.** Nothing is `DESIGN-FROZEN`. This is not a
freeze document and no freeze document was written.

**Evidence level: `L1 EXERCISED`.** The invariant was executed against a real
solver's real bulk output, at four resolutions, including relocation,
corruption, truncation, substitution and deletion.

Explicitly **not** claimed:

* `L2 DIFFERENTIATED` — two backends by one author against one interface
  differentiate nothing. See known unknown 1.
* `L3 STRESSED` — no scale, no concurrency, no remote latency, no broad failure
  injection. See known unknown 2.

**Recommendation.** Adopt the boundary as a `PROPOSED` contract and build on it:
the dependency direction (`engcore.scientific` never imports `engcore.data`;
`engcore.data` never imports a named domain) is the load-bearing part and is
test-enforced in both directions. Do **not** promote it past L1 on this
evidence, and do not treat the reference's current field set as closed.

The next thing that would actually raise the evidence level is a **storage
backend Crafty did not write**, resolving a reference produced by a solver
Crafty did not write. Not another in-house backend, and not another domain
bridge over the same two stores.
