# DATA-BOUNDARY0 — Preregistration

**Milestone:** `DATA-BOUNDARY0` — scientific data identity vs. storage location
**Kind:** evidence spike, not a foundation milestone
**Decision status:** `PROPOSED`
**Target evidence level:** `L1 EXERCISED` (see §9 — L2/L3 are explicitly out of reach here)
**Date:** 2026-09-02
**Branch:** `model0r-realization-foundation`
**Preregistered before implementation.** Everything below was written before any
source file was added or edited.

> **This file is immutable.** It records what was committed to *before*
> results were observed, and nothing learned afterwards is written into it.
> Executed results, corrections, adversarial findings, the schema decision,
> known unknowns and process risks are in `docs/data-boundary0-evidence.md`.
> (This pointer is administrative and is not part of the preregistration.)

> This is **not** `FOUNDATION1`. It implements no Materials, Components, Fields,
> Coupling, GPU, MPI, UQ-on-fields, and no generic artifact framework.

---

# 1. The single question

> Can Crafty move a real scientific bulk field without placing O(mesh-size) data
> inside the scientific control plane, and without making scientific identity
> depend on storage location?

Nothing else is being decided. In particular this milestone does **not** decide
what a `Field` is, what a mesh is, how fields are transferred between
participants, or how bulk data is stored in production.

---

# 2. Hypothesis

**HYPOTHESIS.** Bulk scientific data can be separated from `ScientificResult`'s
small semantic record using a storage-independent scientific data
identity/reference.

Stated as the falsifiable form actually tested:

> There exists a typed, immutable, serializable record `R` such that
> (a) `R` is small and O(1) in the size of the data it identifies,
> (b) `R` determines *which* data is meant, independently of where the bytes are,
> (c) relocating the bytes leaves `R` and the serialized `ScientificResult`
>     containing it **byte-identical**,
> (d) substituting or corrupting the bytes is **detected** at resolution,
> (e) removing the bytes produces a **typed failure**, not empty or invented data,
> and (f) `R` can be added to the existing contracts **additively**, without
> rewriting existing scalar consumers or existing solvers.

---

# 3. Primary proof

The real `Conduction1D` field leaves the solver as bulk data, is stored
separately, and is referenced from the scientific result **without being
serialized inline**.

Note on naming, which matters here: `u` in this domain is a **normalized
dimensionless field**, explicitly *not* a temperature. `problem.py` says so in
three places and `test_conduction1d.py::test_12b_field_is_dimensionless_and_never_kelvin`
enforces it. No document produced by this milestone calls it a temperature.

## 3.1 A constraint discovered before implementation

`src/engcore/domains/thermal/` is **frozen byte-for-byte** by three experiments:

```
experiments/thermal_t1/t1_config.py  THERMAL_FROZEN_FILE_DIGESTS  (7 files, whole tree)
experiments/thermal_t2/t2_config.py  T1_FROZEN_FILE_DIGESTS
experiments/thermal_t3/t3_config.py  T2_FROZEN_FILE_DIGESTS
```

and by two tests that run in the FAST tier:

```
tests/test_thermal_t1_fidelity_inference.py::test_frozen_thermal_solver_digests_match
tests/test_thermal_t1_fidelity_inference.py::test_every_thermal_source_file_is_pinned
```

The second asserts **set equality** between the pinned map and every `*.py`
under `src/engcore/domains/thermal`. Editing a file there breaks the first;
adding a file there breaks the second. `git log` shows the tree has never
changed since `2733612` froze it.

**Decision, preregistered:** the frozen tree is not touched. Not one byte, and
no re-pinning. T1/T2/T3's claim — "these numbers are a property of *that*
solver" — is evidence that this spike has no authority to spend.

This turns out to *strengthen* the proof rather than weaken it. Requirement 7
asks for additive evolution instead of signature changes to existing solvers. A
solver that literally cannot be edited is the strongest available test of that
requirement: if the bulk-data boundary can be introduced around an unmodified,
byte-pinned production solver, additivity is demonstrated rather than asserted.

The new path therefore lives in a **new module outside the frozen tree**
(`src/engcore/domains/thermal_conduction1d_bulk.py`) and drives the frozen
`Conduction1DSolver` through its public `ScientificSolver` protocol only.

## 3.2 What "removed from the diagnostics escape hatch" means here

The frozen solver writes the field to `RawSolverOutput.diagnostics["field"]`,
and the frozen `validate()` reads it there. Both are in-process, same-solve, and
neither ever crosses into a `ScientificResult`.

On the new path the lifecycle order is:

```
prepare → solve → validate            (in-process consumer reads diagnostics)
        → capture_bulk                (field REMOVED from diagnostics,
                                       stored, typed reference returned)
        → extract_metrics → ScientificResult(data_references=…)
```

After `capture_bulk` the key `"field"` no longer exists in the raw output that
continues toward the scientific record. Nothing downstream of the capture point
can reach the array except through the reference and a resolver.

---

# 4. Adversarial proof

After creating the `ScientificResult`:

1. **move / re-home** the underlying artifact from storage backend A to
   storage backend B (in-memory → filesystem, and filesystem → a *different*
   filesystem root),
2. **resolve** it from the other storage location,
3. **verify** the `ScientificResult`'s scientific identity and its serialized
   scientific meaning are **byte-identical** before and after.

The comparison is `json.dumps(result.to_dict(), sort_keys=True)` compared as
exact strings, and the reference compared with `==` and `hash()`.

---

# 5. Fail conditions

The spike FAILS if any of the following holds.

| # | Fail condition | How it is checked |
|---|---|---|
| F1 | `ScientificResult` contains the full field inline | serialized size vs. field resolution; explicit scan of `values` / `metadata` / `provenance` / `artifacts` |
| F2 | Scientific identity includes a filesystem/storage location | scan every field and every serialized key of the reference for path/URI/host/device; construct the same reference from two different temp directories and require equality |
| F3 | Existing scalar result consumers must be rewritten | old-style scalar-only results must serialize, deserialize and behave unchanged; a stored payload with **no** `data_references` key must load |
| F4 | Provider/backend identity leaks into scientific data identity | store name/root must not appear anywhere in `reference.to_dict()`; two stores of different kinds must yield equal references |
| F5 | An untyped metadata field is required to make the proof work | the field must not travel through `metadata`, `diagnostics`, or `artifacts` on the new path |
| F6 | Storage relocation changes the scientific record | byte-comparison of the serialized result before/after relocation |
| F7 | The implementation requires premature coupling/mesh/UQ abstractions | source scan of the new modules for `mesh`, `topology`, `coupling`, `transfer`, `interpolat`, `field_definition`, `probe`, `tensor_rank`, `frame` |

---

# 6. Non-goals

Not built, not designed, not sketched:

generic field model · topology · discretization contracts · interpolation ·
transfer operators · Probe framework · field uncertainty · MPI · GPU · S3 ·
production object storage · retention system · generic distributed filesystem ·
external solver integration.

Also not built, per the architecture review: any *support descriptor* on the
reference. Rank, coordinate frame, conformity and field support belong to
`FIELD0`/`TOPO0`, whose vocabulary does not exist yet. A reference that guessed
that vocabulary today would be the untyped-semantics trap in a new costume.

---

# 7. The contract under test

Three planes, and the dependency direction is the load-bearing part:

```
Scientific Control Plane        engcore.scientific        knows NOTHING about storage
        ↓ references
Scientific Data Identity        ScientificDataReference   content identity, no location
        ↓ resolved by
Runtime / Storage Data Plane    engcore.data              knows locations, no domains
```

* `engcore.scientific` must **never** import `engcore.data`. Enforced by a test.
* `engcore.data` must **never** import a named domain pack. Enforced by a test.
* Only a domain/orchestration module may depend on both.

`ScientificDataReference` carries exactly: logical `name`, `unit`, element
`count`, `dtype`, `digest`, `digest_algorithm`. It carries no path, URI, host,
device, provider, store identity, process identity or timestamp.

`count` is a count of values. It is deliberately **not** a shape, mesh,
topology or field support, and the record says so.

---

# 8. Predicted results

Recorded before running, so a surprise is visible as a surprise.

1. Serialized `ScientificResult` size will be constant to within a few bytes
   across a 128× change in field resolution (the only variation being decimal
   digits of `n_cells`/`n_steps` inside numeric diagnostics).
2. Encoded field size will grow linearly with resolution.
3. The serialized result will be **byte-identical** across relocation.
4. Corruption of one byte will be detected; truncation will be detected.
5. Deletion will raise a typed unavailability error while `result.values`
   remains fully usable.
6. No existing test will need to change.

If (6) fails, that is a finding and it is reported, not repaired by editing the
test.

---

# 9. Evidence status rules for this milestone

Two axes, per the project's decision model.

**Decision status:** `PROPOSED`. Nothing here is `DESIGN-FROZEN`. No freeze
document is written by this milestone.

**Evidence:** the maximum claimable is `L1 EXERCISED` — the invariant was
executed against a real solver's real bulk output.

Explicitly **not** claimable:

* `L2 DIFFERENTIATED` — writing two storage backends ourselves differentiates
  nothing. Both were authored by the same person on the same day against the
  same interface. Real differentiation requires a heterogeneous provider that
  Crafty did not write.
* `L3 STRESSED` — no scale, no concurrency, no remote latency, no failure
  injection beyond single-artifact corruption/deletion.

Adversarial *reasoning* from the falsifier is recorded separately and is not
promoted to executed evidence.

---

# 10. Stop rule

This spike ends when the invariant is proven. It does not continue into
Transfer, Probe, `FieldDefinition`, Mesh, Coupling, Materials, UQ, HPC or an
external provider. If any of those turns out to be genuinely required to make
the spike work, the milestone **stops and reports why** instead of implementing
it.
