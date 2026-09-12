# Field / Mesh / PDE Architecture Spike — Sprint 4

**Branch** `claude/field-pde-architecture-spike-4` · **base** `5c979fc` · **head** `4aa9f80`
**Question.** Can the Core represent, execute, validate, serialize and compose a
genuine field-valued PDE problem without hiding scientific structure inside
opaque metadata, arrays, labels or solver-private state?

**Answer: yes, through a new first-class field layer — decision B.** The
existing core contracts did not have to change to get there, and no scalar
domain had to become a 0-D mesh. What the scalar IR could not do is stated in
§2 with the tests that prove it; what was built is in §4–§14; what it still
cannot do is in §20 and §23, and is larger than what it can.

| Claim | Verdict | § |
|---|---|---|
| A representational failure was demonstrated before core types changed | **HOLDS** — 10 tests at `571fc9d` | §2 |
| A 2-D field problem is declared, solved, validated, serialized, composed | **HOLDS** | §5–§14 |
| The measured order of accuracy is second | **HOLDS** — 1.957–2.017, measured not asserted | §11 |
| No bulk array in metadata, diagnostics, provenance or validation | **HOLDS** — 895-byte record for a 131 KB field | §7 |
| Scalar domains are unchanged | **HOLDS** — 864 serialized paths identical | §19, §23 |
| Every targeted field mutation is killed | **HOLDS** — 8/8, control green | §22 |
| The certification snapshot still describes the core | **FAILS** — 47 → 54 modules | §23 |

---

## 1. Scope, and what this is not

A spike with one real vertical slice: steady 2-D conduction on a structured
rectangular plate. Not a FEM framework, not a CFD project, not a trust audit
and not a refactor. The slice was chosen to be the smallest problem that still
has every property a field problem has — a support, a location on it, regions,
typed boundary data, bulk values, a unit, and a composition boundary — so that
an architecture that fits it is being tested against the real shape of the
problem rather than a reduced one.

Six commits, kept by concern:

| Commit | What |
|---|---|
| `571fc9d` | `test(fields): reproduce scalar IR ceiling` |
| `46128cc` | `feat(fields): add first-class field and mesh records` |
| `37a28ff` | `feat(data): hold field values outside the scientific core` |
| `54cc440` | `feat(thermal): add structured 2d conduction spike` |
| `acd28ea` | `test(thermal): validate manufactured solution and convergence` |
| `4aa9f80` | `feat(composition): represent field transfer contracts` |

---

## 2. Phase 1 — the ceiling, proved before anything was changed

`tests/test_field_ir_ceiling.py` (10 tests, committed **before** any core type
was added) demonstrates the failure rather than arguing it. The findings, each
one an executed assertion:

1. **There is no array-valued scientific value.** `Quantity(ndarray)` raises
   `TypeError`; `require_scientific_value(ndarray)` raises
   `InvalidScientificProblem`. The value union is scalars and nothing else.
2. **A variable cannot say where it lives.**
   `ScientificVariable.__dataclass_fields__` is exactly
   `{name, unit, kind, role, lower, upper, categories, description}` — no
   shape, no location, no support. `T(x, y)` has nowhere to be declared.
3. **A region is whatever string the caller passed.**
   `BoundaryCondition(region="northeast-ish")` is accepted, and two problems of
   *different geometry* accept an identical boundary condition without
   complaint. Nothing derives a region from a support, so nothing can refuse
   one that is not on it.
4. **A result holds a mapping of scalars.**
   `ScientificResult(values={"T": ndarray})` is refused: a field cannot be a
   result value.
5. **A data reference has a count, not a shape.** `ScientificDataReference` for
   16 values is one identity whatever the intended 4×4 or 2×8 arrangement.
   Correct for what it was designed for, and insufficient to name a field.
6. **Fields already travel, undeclared.** The frozen 1-D solver puts its field
   in `raw.diagnostics["field"]` — nine bare floats with no unit, no shape and
   no support. `conduction1d_bulk.py` exists purely to lift them back out.
   This is the failure in production form: the structure is real, and it is
   being carried as an opaque payload because there was no record for it.
7. **A crossing cannot carry one.** `QuantityTransfer` refuses an ndarray and
   carries a single scalar `Quantity`.

That is the ceiling, and finding 6 is the one that mattered: the platform was
already moving fields, in the one place it could, with every scientific
property stripped off them.

---

## 3. Phase 2 — the narrowed slice

In: 2-D rectangular Cartesian geometry; a structured rectilinear grid;
constant isotropic conductivity; Dirichlet and Neumann conditions; a steady
solve. Robin is **representable** in the records and **not served** by the
solver — deliberately, to check that the two are distinguishable. Out, and
refused rather than approximated: unstructured and adaptive supports, FEM,
CFD, 3-D, vector and tensor fields, anisotropy, temperature dependence, and
every transient term.

---

## 4. Phase 3 — the minimum first-class field model

Seven modules under `src/engcore/scientific/fields/`, all array-free:

| Record | What it fixes |
|---|---|
| `StructuredMesh` | the support, with a **geometric fingerprint** |
| `MeshRegion` + `boundary_regions(mesh)` | regions *derived from* a support, not named by a caller |
| `FieldDefinition` | which field, which unit, which support, nodes or cells, how many components |
| `FieldBoundaryCondition` | typed condition on a **region**, reusing the core `BoundaryKind` |
| `FieldInitialCondition` | uniform or a stored record, exactly one |
| `FieldRecord` + `FieldSummary` | names a field's values and never holds them |
| `FieldTransferContract` / `FieldDependency` | what must be true before a field crosses |

Two design points carry the weight.

**The support has an identity.** `fingerprint()` is a SHA-256 over canonical
geometry and **excludes `mesh_id`**, so renaming a support does not make it a
different one, and a plate declared in millimetres equals the same plate in
metres. `same_support_as` is then a question about geometry rather than about
a label — which is what makes "is this the same field?" answerable at all.

**Regions are derived.** `boundary_regions(mesh)` returns the four edges with
ids `f"{mesh_id}:{edge}"`, and `MeshRegion.require_support(mesh)` refuses a
region against a support it does not belong to. The `"northeast-ish"` string
from §2 has no analogue here: there is no constructor that takes one.

---

## 5. Phase 4 — the three options, and why B

| | A: extend `ScientificVariable`/`Problem` | **B: `FieldProblem` layer composing with the IR** | C: general `ValueShape` hierarchy |
|---|---|---|---|
| scalar backward compatibility | **fails** — arrays enter the value union every scalar record shares | **passes** — nothing scalar is touched | **fails** — rewrites the union every record uses |
| serialization | array inline in every payload quoting a variable | reference by digest, record stays O(1) | new encoder for every shaped value |
| validation | shape checks leak into scalar validation | contained in the field records | every validator learns shapes |
| solver protocols | every solver sees a possibly-array value | field solvers opt in | every solver sees a shape union |
| composition | `QuantityTransfer` would have to carry arrays | `FieldTransferContract` beside it | one transfer type, many shapes |
| units | per-node `Quantity` pressure | one unit per field | one unit per shaped value |
| provenance | bulk data in provenance inputs | digest only | bulk data in provenance inputs |
| maintainability | one type does two jobs | two types, one job each | maximal blast radius |
| future 3-D / vector | awkward | `components` and `dimensionality` already there | natural |
| future unstructured | blocked | `MeshTopology` is an enum with one member today | natural |

**B was chosen.** A and C are both *more elegant in the abstract* and both put
arrays into the value union that every scalar record in this repository shares
— including the types the certified harness and the three frozen experiments
pin. C is the better long-run answer if this platform ever becomes a general
shaped-value system; it is the wrong answer to reach for from here, because its
blast radius lands exactly on the records that are byte-pinned.

**Rejected, explicitly:**

* **A** — forces arrays into `ScientificValue` and changes every scalar record
  to make one field work.
* **C** — rewrites the value union used by every record; maximal blast radius
  on precisely the pinned types.
* **A fourth, considered and rejected without a column**: keep fields in
  `diagnostics` and add a *convention* for reading them. That is what the
  platform does today (§2, finding 6), and a convention is not a contract —
  nothing can refuse a violation of one.

**The smallest architecture that does not make future PDE support impossible.**
`MeshTopology` is an enum whose only member is `STRUCTURED_RECTILINEAR`;
`dimensionality` is a property, not a constant; `components` already exists and
is already checked. None of these is used today beyond the 2-D scalar case, and
each is the place the next case would attach.

---

## 6. What did **not** change

The Scientific Core still **imports no array library**. `scientific/fields/`
declares fields and holds no numbers; `numpy` appears in the runtime plane
(`engcore/data/field.py`) and in the domain solver, which is where it already
was. No existing core record gained a field, and no existing reader changed.

---

## 7. Phase 5 — the bulk data boundary

The rule was: no 128×128 array in diagnostics, metadata, provenance or
validation detail. Measured, not asserted:

| | bytes |
|---|---|
| `FieldRecord.to_dict()` for a 128×128 field | **895** |
| the same field's values, raw float64 | **131 072** |

The record carries the definition, the support's fingerprint, the shape, a
`ScientificDataReference` (name, unit, count, dtype, digest) and a five-number
summary. The values reach storage through the **existing** `store_values` /
`BulkDataResolver` path, unchanged, with length-then-digest verification on the
way back. `test_the_record_names_the_values_and_never_holds_them` asserts
neither `values` nor `data` appears in the payload, and that the whole thing
stays under 2 KB however large the field is.

`ScientificResult` carries the field as one entry in `data_references` — the
channel DATA-BOUNDARY0 built for exactly this — and never in `artifacts`,
`metadata` or `diagnostics`.

---

## 8. Phase 6 — unit semantics

One unit per field, normalized through the existing `normalize_unit` (`"K"`
becomes `"kelvin"`), and **no per-node `Quantity` objects**: 16 384 `Quantity`
instances to describe one field would be absurd and would put the unit in
16 384 places that could disagree.

Conversion is **affine and two-point**, not a scale factor:

```
zero = Quantity(0, u).magnitude_in(target)
one  = Quantity(1, u).magnitude_in(target)
converted = values * (one - zero) + zero
```

`test_a_unit_conversion_is_affine_and_not_a_scale_factor` pins 300 K → 26.85 °C
and back. A scale factor alone turns 0 °C into 0 K, which is the specific bug
this shape avoids.

Boundary conditions are checked **by dimension, never by unit string**, so a
plate in millimetres with a source in kW/m³ is accepted and a boundary value in
volts is refused.

---

## 9. Phase 7 — the reference solver

`src/engcore/domains/thermal_models/conduction2d.py`. A five-point finite
difference operator for `-div(k grad T) = q`, assembled into a `scipy.sparse`
matrix and solved by one direct sparse factorisation.

It lives in `thermal_models/` because `domains/thermal/` is byte-pinned by
three frozen experiments and its file set is asserted — nothing may be added
there. `thermal_models/` is the sanctioned home for thermal work post-dating
those freezes, and says so in its own docstring.

Two implementation choices are load-bearing:

* **Dirichlet rows are pinned by an identity row rather than eliminated**, so
  the unknown numbering stays equal to the node numbering. A row of the
  solution is a row of the support and no consumer has to invert a map.
* **A Neumann edge is imposed by ghost-node elimination**, which keeps the
  boundary truncation error second order. A one-sided difference would have
  been simpler and would have quietly flattened the convergence rate that §11
  measures — see §11 for what caught the sign error in this term.

---

## 10. Phase 8 — the manufactured oracle

`tests/manufactured_conduction2d.py`. Two closed-form solutions, each put
through the operator to produce the source and boundary data it implies, with
the solver then asked to recover it.

| Case | Solution | Boundaries |
|---|---|---|
| `sine_plate` | `T = 300 + 40 sin(πx/Lx) sin(πy/Ly)` | Dirichlet on all four edges |
| `cosine_column` | `T = 300 + 40 cos(πy/2Ly)` | Dirichlet below, **non-zero constant flux** above, zero flux at the sides |

The second case exists because the first does not discriminate. A first-order
one-sided flux condition reproduces a Dirichlet plate and an *insulated* edge
perfectly well, and loses an order only where the prescribed flux is non-zero.
Both sources are **field-valued**, so the field-source path is exercised rather
than a uniform shortcut.

**A representational limit found here, and reported rather than worked around:**
`FieldBoundaryCondition` carries one `Quantity` per region, so a boundary
condition that *varies along an edge* is not representable. Both manufactured
solutions were chosen to have constant data on each edge to fit inside that
limit. It is the first thing a second pass would need. See §23.

---

## 11. Phase 9 — the convergence study, measured

16, 32, 64 and 128 nodes per side. The order is **computed from the measured
errors** by `log(e_coarse/e_fine) / log(h_coarse/h_fine)` and asserted against
a floor of 1.9. Nothing asserts "second order" as a constant.

**`sine_plate`**

| n | h | L2 | order | L∞ | order |
|---|---|---|---|---|---|
| 16 | 0.066667 | 6.8690e-02 | — | 1.4494e-01 | — |
| 32 | 0.032258 | 1.6591e-02 | **1.957** | 3.4164e-02 | **1.991** |
| 64 | 0.015873 | 4.0802e-03 | **1.978** | 8.2848e-03 | **1.998** |
| 128 | 0.007874 | 1.0119e-03 | **1.989** | 2.0395e-03 | **1.999** |

**`cosine_column`** (the non-zero flux edge)

| n | h | L2 | order | L∞ | order |
|---|---|---|---|---|---|
| 16 | 0.066667 | 5.1544e-02 | — | 9.4004e-02 | — |
| 32 | 0.032258 | 1.1917e-02 | **2.017** | 2.2004e-02 | **2.000** |
| 64 | 0.015873 | 2.8682e-03 | **2.009** | 5.3274e-03 | **2.000** |
| 128 | 0.007874 | 7.0370e-04 | **2.004** | 1.3109e-03 | **2.000** |

**Measured order of accuracy: 2.0**, approached from both sides, on both cases,
in both norms. Absolute error at the finest support is 2.04e-03 K (L∞,
`sine_plate`) on a 40 K amplitude.

**This study earned its place immediately.** The ghost-node constant crosses to
the right-hand side with a sign change, and it was first written without one.
Every zero-flux case in the suite passed anyway — the uniform plate, the linear
profile, the insulated sides — because the term is multiplied by a flux of
zero. Only `cosine_column`, with a non-zero prescribed flux, could see it. The
sign was re-derived against a 1-D case, corrected, and the order went to 2.000.

---

## 12. Phase 10 — `ScientificResult` integration

A field solve produces an ordinary `ScientificResult`: `Quantity` values
(`T:min`, `T:max`, `T:mean`, `T:l2_norm`), a `ProvenanceRecord`, a
`ValidationReport`, a `SolverIdentity`, and the field in `data_references`.
A reader that knows nothing about fields gets scalar evidence it can act on;
a reader that does gets the reference and can resolve it.

**Two claims are deliberately not made.**

* `ConvergenceState` is **`NOT_APPLICABLE`**, not `CONVERGED`. A direct sparse
  factorisation neither converges nor fails to, and the enum's own docstring
  says the two must not be conflated.
* The linear-residual check **establishes no level**. The temptation was to
  award `NUMERICALLY_CONVERGED`, as the DC domain does. This repository has
  already ruled against that, in the frozen conduction validation and again in
  `docs/domains/evidentiary-levels.md`: *the linear residual of a direct sparse
  factorization sits at round-off in every run, coarse or fine, so treating it
  as convergence would certify the 8-cell solve exactly as confidently as the
  512-cell one.* This is the same solver kind on the same equation. It takes
  the same answer.

Consequently the gate's thresholds are **deliberately absent** from
`SCIENTIFIC_THRESHOLD_DECLARATIONS`: a registered set is one authorised to
award a level, and this one awards none. The tolerances still travel as a
`VerificationThresholds` record rather than as float arguments, so a caller who
widens one still gets every comparison and every residual — the shape
`test_core_guards.py::test_no_gate_lets_its_caller_set_the_threshold_it_awards_a_level_against`
requires, and which this module was caught violating on first write.

The evidentiary-level audit gained **one** row, for
`field_linear_system_residual`. The other two checks reuse `field_finite` and
`boundary_conditions_held`, whose existing verdicts apply to them verbatim;
minting new names would have split a settled verdict in two.

---

## 13. Phase 11 — serialization

Every new record has `to_dict` / `from_dict` with a schema string checked on
read, satisfying the repository-wide invariant that every reader writing a
schema also checks one.

Round trips asserted: `StructuredMesh` (and a **tampered fingerprint is
refused**), `MeshRegion`, `FieldDefinition`, `FieldBoundaryCondition`,
`FieldInitialCondition`, `FieldRecord`, `FieldTransferContract`,
`FieldDependency`, and the whole `ScientificResult`. After a result round trip
the reference digest still names the same bytes, and the values are recovered
*through the deserialized record* rather than from the original object.

---

## 14. Phase 12 — composition

`FieldDependency` states that one problem's field supplies another's, the way
`QuantityDependency` does for a scalar, and carries a `TransferKind` —
`SCALAR_TRANSFER` or `FIELD_TRANSFER`.

`admit()` answers the question that comes *before* supports and units: is this
even the kind of thing the consumer asked for? A field's mean carries the
field's dimension, so a summary standing in for the distribution it summarises
passes every scalar check there is. Both directions are refused:

* a `Quantity` offered to a field dependency — *"a summary of a field is not the
  field, and carries the same dimension as one"*;
* a `FieldRecord` offered to a scalar dependency — *"which number of it was
  meant is not stated anywhere, and picking one here would be inventing the
  answer."*

---

## 15. Phase 13 — the mesh compatibility matrix

Enumerated, not sampled. Four verdicts, because "no" has three meanings.

| Producer vs consumer | Verdict |
|---|---|
| identical | COMPATIBLE |
| same geometry, renamed support | COMPATIBLE |
| same geometry, twice the resolution | REQUIRES_PROJECTION |
| nodes against cells | REQUIRES_PROJECTION |
| one support, two units of one dimension | REQUIRES_UNIT_CONVERSION |
| **equal counts, transposed support** (32×16 vs 16×32) | REFUSED |
| same resolution, different rectangle | REFUSED |
| same rectangle, moved origin | REFUSED |
| different dimension | REFUSED |
| scalar against a vector field | REFUSED |

A second test asserts that **seven of the ten rows have equal element counts on
both sides**. Those are the rows that cross silently under any check that
compares shapes or lengths, and the matrix would be worth little without them.
The three that do differ in length are named in `CAUGHT_BY_LENGTH_TOO` rather
than quietly filtered.

---

## 16. Phase 14 — the applicability envelope

`APPLICABILITY` is a declared tuple of seven statements, and the refusals are
written from it, so the envelope a reader sees is the envelope the code
enforces. It also becomes `provenance.assumptions`. Each refusal names the
statement it violates rather than surfacing as a numerical symptom:

| Request | Refusal |
|---|---|
| anisotropic conductivity (a tuple) | *"conductivity is isotropic in this model … an anisotropic conductivity is a different equation, not a different number"* |
| temperature-dependent conductivity (a callable) | *"a temperature-dependent property makes this equation nonlinear"* |
| non-positive or non-finite conductivity | *"must be finite and strictly positive"* |
| a field at the cells | *"this discretisation places unknowns at nodes"* |
| a vector field | *"this model solves one scalar field"* |
| a Robin or periodic edge | *"this model serves dirichlet and neumann only. A robin condition is representable in the core records and is not served here"* |
| an all-flux plate | *"the steady temperature is determined only up to a constant and the system is singular. Fix the level somewhere"* |
| a source on another support | names both fingerprints |
| a boundary value of the wrong dimension | names the dimension needed |

The Robin row is the one worth reading twice: **representable** and **not
served** are different facts, and the platform can now say both.

---

## 17. Phase 15 — adversarial cases

All refused, each by a test:

| # | State | Where it is caught |
|---|---|---|
| 1 | array of the wrong shape | `FieldValue` — *"equal counts are not equal fields"* |
| 2 | flat array of the right length | `FieldValue` |
| 3 | NaN or inf in a field | `FieldValue`, naming the count and the first index |
| 4 | field on a support it was not declared on | `FieldDefinition.require_support` |
| 5 | record read back against another support | `FieldRecord.verify_against` |
| 6 | tampered bytes in the store | `BulkDataIntegrityError` from the existing resolver |
| 7 | tampered mesh fingerprint in a payload | `StructuredMesh.from_dict` |
| 8 | condition on a region of no support | `require_complete_boundary` |
| 9 | two conditions on one edge | *"One edge, one condition"* |
| 10 | an edge with no condition | *"leaves the problem under-determined"* |
| 11 | equal-length fields of different geometry | `check_field_transfer` → REFUSED |
| 12 | a scalar passed off as a field, and the reverse | `FieldDependency.admit` |
| 13 | caller-supplied verification tolerance | `VerificationThresholds`, no level awarded |
| 14 | mutation of a held field through the caller's array | copied on construct, `setflags(write=False)` |

---

## 18. Phase 18 — the architecture decision gate

> ### **B — a new first-class field layer is required, and the core contracts are sound.**

Not A: the existing `ScientificVariable` / `ScientificProblem` types could not
be extended to carry a field without putting arrays into the value union every
scalar record shares (§2, §5). A field needed genuinely new records.

Not C: nothing in the core had to be redesigned to accept them. `Quantity`,
`ScientificDataReference`, `BulkDataStore`, `ScientificResult`,
`ValidationCheck`, `ProvenanceRecord`, `BoundaryKind` and
`VerificationThresholds` were all reused **unmodified**, and the field layer
composes with them rather than replacing them. The one core-adjacent lesson —
that a caller-settable tolerance defeats a verification — was already encoded
as a guard, and it caught this module on first write (§12).

Not D: the slice runs, converges at a measured second order against two
independent closed forms, serializes, round-trips and composes.

The verdict is not softened: **B means real new architecture was required.**
Seven new core modules and one runtime module exist that did not before, and
they exist because the platform could not express the problem without them.

---

## 19. Phase 16 — scalar backward compatibility

**Mandatory, and it holds.** No existing scalar domain was modified, and none
had to become a fake 0-D mesh.

* Full suite: **4837 passed, 3 skipped, 0 failed** (4717 before + 120 new).
* The only edits outside new files are: one explanatory comment block in
  `engcore/domains/__init__.py` (no behaviour), one row in the
  evidentiary-level audit and its test, and the count arithmetic that row
  changes.
* Output equivalence, §23.

Battery, DC, CSTR, lumped thermal and material resistance are untouched at
source level and byte-identical at output level.

---

## 20. Phase 19 — what is **not** claimed

Stated plainly, because the numbers above are easy to over-read.

**Forge does not support arbitrary PDEs.** One equation is implemented.
**Forge is not a FEM platform.** There are no elements, no basis functions, no
quadrature and no assembly over a mesh of cells.
**Forge does not support CFD.** There is no advection, no nonlinearity, no
coupling of momentum and continuity, and no time.

The strongest claim the evidence supports, and the only one made:

> **Forge can represent and solve a first-class structured-grid 2-D conduction
> field through its scientific contracts.**

Each word is load-bearing. *Structured-grid*: one topology, `MeshTopology` has
one member. *2-D*: `dimensionality` returns 2 and nothing tests otherwise.
*Conduction*: one operator. *Through its scientific contracts*: the field is
declared, unit-bearing, region-validated, digest-referenced, serializable and
composable — not an array in a diagnostics slot.

---

## 21. Phase 17 — performance

Not an optimization round; a check that the architecture does not impose a cost
where it should not.

**Control plane — O(1) in field size, all of it:**

| Operation (128×128) | Time |
|---|---|
| mesh construction | 0.006 ms |
| mesh fingerprint | 0.005 ms |
| field container (copy + shape + finite check) | 0.007 ms |
| field summary | 0.140 ms |
| boundary completeness validation | 0.005 ms |
| transfer compatibility check | 0.029 ms |
| field record `to_dict` | 0.001 ms |

**Data plane:**

| Operation (16 384 values) | Time |
|---|---|
| store | 1.170 ms |
| resolve + length-and-digest verify | 0.518 ms |

**Solves:**

| Support | Nodes | Wall | Peak memory |
|---|---|---|---|
| 16×16 | 256 | 14.1 ms | 0.1 MB |
| 32×32 | 1 024 | 41.7 ms | 0.6 MB |
| 64×64 | 4 096 | 171.8 ms | 2.4 MB |
| 128×128 | 16 384 | 761.5 ms | 9.9 MB |

**Where the time actually goes, measured:** at 128×128, assembly is 201.7 ms
and the factorisation-and-solve is 37.4 ms (79 888 non-zeros). The cost is the
Python double loop building a `lil_matrix`, not the linear algebra. A
vectorised diagonal construction would remove most of it and is deliberately
out of scope — reported so the number is not mistaken for the cost of the
architecture.

---

## 22. Phase 20 — assurance

| Run | Result |
|---|---|
| **FULL** (`pytest tests/`) | **4837 passed, 3 skipped, 0 failed**, exit 0 |
| Contract Guard | 305 passed |
| Capability Boundary | 304 passed |
| Scientific Truth | 293 passed, 3 skipped |
| New field + conduction suites | 120 passed |
| **Installed wheel** | **FIELD AND CONDUCTION SMOKE OK · 17 checks**, + 120 passed |

**Wheel details.** Built from `git archive 4aa9f80`: 203 entries, **0 under
`src/`**, `engcore/py.typed` ships, and all seven `scientific/fields/` modules,
`engcore/data/field.py` and `engcore/domains/thermal_models/conduction2d.py`
are present. Run under `python -S -E` so `site.py` never executes and the
venv's editable-install hook is never registered; a `conftest.py` asserts
`engcore.__file__` is under the install target before any test runs. *The first
attempt at this passed while importing the checkout — `-I` ignores `PYTHONPATH`
and does not skip site-packages — so the assertion was added to make that
failure impossible to repeat.*

**Targeted field mutations — CONTROL GREEN, 8/8 killed, 0 survivors.**
`tests/mutation_guards.py` is byte-pinned by `certification/current_core_v1.json`
and cannot gain mutations, so these run through the sprint's own apply/revert
harness (each mutation reverted and the restore verified by digest).

| # | Mutation | Verdict |
|---|---|---|
| FM-1 | a field stops checking which support it was declared on | RED (killed) |
| FM-2 | an array of the wrong shape is accepted onto a support | RED (killed) |
| FM-3 | a field transfer stops checking the dimension it carries | RED (killed) |
| FM-4 | a field dependency accepts a scalar summary of the field | RED (killed) |
| FM-5 | a condition naming a region of no support is skipped | RED (killed) |
| FM-6 | an edge with no boundary condition stops being noticed | RED (killed) |
| FM-7 | a field carrying a non-finite value is admitted | RED (killed) |
| FM-8 | a record is read back against a support it was not solved on | RED (killed) |

---

## 23. Phase 21 — output equivalence, and what is left open

**Output equivalence.** The platform's own canonical example cases — the
coupled electrothermal case (DC circuit + material resistance + lumped thermal)
and the battery case — were run on the branch base `5c979fc` in a clean
worktree and on the branch head, and every serialized report compared path by
path:

```
paths before=864 after=864
CHANGED: 0    REMOVED: 0    ADDED: 0
IDENTICAL
```

**Open, and each one real:**

1. **The certification snapshot no longer describes the core.**
   `certification/current_core_v1.json` pins `src/engcore/scientific` at
   **47 modules** and `tree_sha256 82558f5b…`; the tree now holds **54**. The
   snapshot is not read by any test — only referenced by three prior round
   reports — so it drifted **silently**, which is itself the finding. It has
   deliberately *not* been rewritten here: re-certification is a decision, not
   a digest update, and it is a precondition for this branch landing.
2. **A boundary condition cannot vary along an edge** (§10). One `Quantity` per
   region. Both manufactured solutions were chosen to fit inside that limit.
   This is the first thing a second pass needs.
3. **No transient term.** Steady only; `FieldInitialCondition` exists and
   nothing consumes it.
4. **`REQUIRES_PROJECTION` is a verdict, not an operation.** The platform can
   say a projection is needed and cannot perform one.
5. **Robin is representable and unserved**, by design, and untested beyond the
   refusal.
6. **One topology.** `MeshTopology` has a single member; nothing exercises the
   enum as an enum.
7. **Assembly is the performance cost**, not the solve (§21).
8. **`domains/thermal/conduction1d` still routes its field through
   `diagnostics`.** The mechanism that would fix it now exists; migrating a
   byte-pinned frozen tree is out of scope and would need its own decision.
