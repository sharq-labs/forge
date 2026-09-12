# Field Boundary & Coefficient Expressiveness — Sprint 5

**Branch** `claude/field-expressiveness-sprint-5` · **base** `ff3d97b` · **head** `5d03d5b`

---

## 1. Final verdict

> ### **FIELD EXPRESSIVENESS COMPLETE — HETEROGENEOUS COEFFICIENT EXECUTION DEFERRED**

A boundary datum, a flux and a volumetric source may now be a declared spatial
law rather than a single number. The laws are records: immutable, unit-aware,
coordinate-aware, serializable, deterministic, schema-versioned and
fingerprinted. No path exists by which a callable becomes an authoritative
spatial law. A coefficient `k(x, y)` is **representable with no architectural
change and is not executed**, for a stated reason.

| Acceptance item | Verdict |
|---|---|
| constant-only limitation reproduced | **HOLDS** — §2 |
| first-class spatial profile exists | **HOLDS** — five forms, §3 |
| no arbitrary callable authority path | **HOLDS** — §14, SP-6 |
| spatially varying Dirichlet works | **HOLDS** — §6, §9 |
| spatially varying Neumann works | **HOLDS** — executed and measured, §6, §10 |
| varying source works | **HOLDS** — §7 |
| coordinate semantics explicit | **HOLDS** — §4 |
| unit semantics enforced | **HOLDS** — §5 |
| tabulated integrity enforced | **HOLDS** — §13 |
| serialization round trip | **HOLDS** — §12 |
| fingerprints detect tampering | **HOLDS** — §12 |
| manufactured case requires varying BC | **HOLDS** — §9 |
| independent oracle agrees | **HOLDS** — §10 |
| convergence remains correct | **HOLDS** — §11 |
| provenance identifies profile declarations | **HOLDS** — §15 |
| field-transfer semantics sound | **HOLDS** — §16 |
| scalar and Sprint-4 APIs compatible | **HOLDS** — §16, §19 |
| all valid SP mutations killed | **HOLDS** — 10/10, §15 |
| FAST / FULL / wheel green | **HOLDS** — §18 |
| no material performance disaster | **HOLDS** — §17 |

**Two defects were found and fixed that were not the sprint's subject** — one
in the boundary model and one in the verification criteria. Both are in §6 and
§19, and the second had been shipping since Sprint 4.

---

## 2. Original limit reproduction

`tests/test_field_profile_limit.py`, committed at `377769b` before anything was
built. The limit is measured rather than asserted.

**The cost of a constant edge, measured on the boundary.** A left edge that
truly runs `T = 300 K + 20 K·y/Ly`, approximated by the kindest single number
available — the edge's mean:

| Nodes per side | Worst error against the true edge |
|---|---|
| 16 | 10.000000000 K |
| 32 | 10.000000000 K |
| 64 | 10.000000000 K |

**Dead flat.** A second-order discretisation error falls by about sixteen over
those two steps. This one does not move at all, because the largest distance
from an edge's mean to its ends has nothing to do with how finely the edge is
sampled. That is how a missing representation is told apart from a coarse mesh.

**And a constant edge could not even be declared consistently.** Since this
sprint, a constant standing in for a varying edge is refused outright: it
disagrees with its neighbours at the corners they share, whatever number is
chosen (§6).

**What a pre-evaluated source cannot say.** Sprint 4's field-valued source
works and carries no law. Asserted: the payload names bytes by digest and
contains none of `sin`, `law`, `expression`, `coordinate`, `profile`; and the
same declared source cannot be carried to a refined support — the transfer
verdict is `REQUIRES_PROJECTION`. So a convergence study had to re-evaluate the
law outside the platform, which is where the law then lived.

**Permanent refusals asserted from that first commit**, not added at the end: a
lambda, an ordinary function, a `functools.partial`, an object with `__call__`,
and a bare sequence of per-node numbers are all refused as boundary values, as
is a `Quantity` holding an array.

---

## 3. Profile architecture

`src/engcore/scientific/fields/profiles.py`, 690 lines, **array-free** — this
is a core package and the core imports no array library.

| Form | Law |
|---|---|
| `ConstantProfile` | one value, everywhere |
| `LinearProfile1D` | `intercept + slope·(c − origin)` along one axis |
| `HarmonicProfile1D` | `offset + amplitude·sin(wavenumber·(c − origin) + phase)` |
| `TabulatedProfile1D` | samples along one axis, read by a declared rule |
| `SeparableProfile2D` | `amplitude · f(x) · g(y)`, factors dimensionless |

Every one is immutable, unit-aware, coordinate-aware, deterministic,
serializable, schema-versioned (`spatial_profile/1`) and fingerprinted.

`HarmonicProfile1D` is the "narrowly defined analytic family" the spec allows,
and it is narrow: one sine with four parameters. There is no parser, no
expression tree and no way to compose one law out of arbitrary others. It
exists because a sinusoidal boundary datum is how a problem with a known
closed-form solution is stated, and a law that could only be tabulated could
not state one exactly (§9).

`SeparableProfile2D` requires its factors to be **dimensionless**, which keeps
the unit arithmetic from becoming a second thing to get wrong, and refuses to
nest, which would make the coordinate each factor reads ambiguous.

`as_profile` is the one place a bare value becomes a law — a `Quantity` is
promoted to a `ConstantProfile` — so every consumer downstream handles exactly
one type and the Sprint 4 spelling keeps working unchanged.

---

## 4. Coordinate semantics

**Physical coordinates, never indices.** `evaluate` is keyword-only in `x` and
`y`, so a caller cannot transpose them, and a one-dimensional law reads the
axis it declared. A law read by position in a sequence would give the midpoint
different values on a 5-sample and a 9-sample traverse of one edge; this one is
never told which sample it is on, and a test asserts exactly that over four
sampling densities.

`edge_axis` states once, in one place, that left and right edges run in `y` and
bottom and top in `x`. `require_axis` refuses a law written against the other
one: *"a profile written against one axis does not become a profile of the
other by being bound to it"*. A constant reads no coordinate and binds
anywhere, which is the only reason this is not a bare equality.

Coordinates carry units: a table sampled in millimetres evaluates correctly
against a support in metres (`span` converts to canonical length).

---

## 5. Unit semantics

The existing `Quantity`/Pint architecture is reused unchanged, and **no
per-node `Quantity` objects are created** — one profile-level unit plus
numerical evaluation, as required.

| Bound | Rule |
|---|---|
| Dirichlet law | dimension of the field it prescribes |
| Neumann law | dimension of a flux, checked by the domain |
| volumetric source | `watt/meter**3` |
| coordinates | a length |
| linear slope | `output/length` |
| wavenumber | `1/length` |
| harmonic offset | the amplitude's dimension |
| separable factors | dimensionless |

A numerically plausible law of the wrong dimension is refused wherever it is
bound — on an edge, as a source, or as a coefficient — with the message *"a
numerically plausible profile of the wrong dimension is still the wrong law"*.

---

## 6. Boundary-condition model

`FieldBoundaryCondition.value` now holds either a `Quantity` or a
`SpatialProfile`. **One slot, not two**: a constant condition's payload gained
no key, so anything written before profiles existed reads back unchanged, and
both spellings serialize to a mapping carrying its own schema — the
discriminator is the payload's own statement about itself rather than a guess
from its shape. `law` answers for both, so nothing downstream branches.

`require_consistent` checks three things about a binding: the law varies along
the coordinate the region runs in, it is defined across that region's physical
extent, and (for a prescribed value) it carries the field's dimension.

### A defect found and closed

`regions.py` has said since Sprint 4 that two boundary values at a corner are
*"a conflict worth refusing instead of a silent winner"*, and only half of that
was true. Two conditions on one region were refused; two edges meeting at a
corner both pinned that node, and the winner was **whichever edge the assembly
wrote last**. An iteration order was deciding a boundary value.

`_require_corners_agree` now evaluates both laws at the shared point and
refuses a disagreement. Flux edges are exempt: a derivative constrains nothing
at the point itself. This was found by the Phase 1 limit test, which could not
declare its own constant approximation once the rule existed — which is itself
the sharper statement of the limit.

---

## 7. Source model

A source may be a uniform `Quantity`, a `SpatialProfile`, or a stored
`FieldValue` on the same support. Three spellings, one array: nothing
downstream of `_source_array` knows which it was.

A source law is checked for dimension and for coverage over the plate's
two-dimensional extent (`require_covers_box`, which checks each axis the law
reads against that axis's span, so a law of `x` is not judged against the
extent in `y`).

The result that matters: **one source declaration serves every resolution.**
The same `SeparableProfile2D` — one fingerprint, asserted identical across all
four — is used at 16, 32, 64 and 128, and the error falls at second order.
That is the Phase 1 complaint answered directly.

---

## 8. Coefficient representability

> ### **REPRESENTABLE_NOT_EXECUTED**

`tests/test_field_coefficient_spike.py`, with the verdict held as a value so
the report cannot drift from what the tests show.

**Representable, with no architectural change at all.** A coefficient that
varies in space is the same record as a boundary datum that does: a
`SpatialProfile` in `watt/kelvin/meter`. It stores, serializes, fingerprints
and evaluates exactly as the others do, in one dimension (`k(x) = 10 + 8x`) and
in two (a separable product). Nothing in the profile layer had to learn what a
coefficient is.

**Not executed, and the refusal names what is missing:** the five-point
operator assembled here takes `k` outside the divergence, which holds only
where `k` is constant. A heterogeneous coefficient needs the conservative form
discretised with face conductivities between nodes — *"a different scheme
rather than a different coefficient"*. Executing one silently under a
declaration that says otherwise is the failure the envelope exists to prevent.

A test asserts the four coefficient refusals are four distinct answers:
anisotropy, nonlinearity, heterogeneity and non-positivity each say their own
thing.

---

## 9. Manufactured case

Three new cases, none declarable under the Sprint 4 API.

| Case | Exact field | What it needs |
|---|---|---|
| `sheared_plate` | `T = A + Bx + Cy + Dxy` | **four** varying edges: two prescribed, two flux |
| `harmonic_plate` | `T = T₀ + A·sin(πy)·sinh(πx)/sinh(π)` | one sinusoidal prescribed edge |
| `declared_source_plate` | `T = T₀ + A·sin(πx)sin(πy)` | a source stated as a law |

`sheared_plate` is harmonic, so it has no source, and every edge value *and*
every normal derivative varies. Because it is bilinear, the five-point operator
and the ghost-node flux condition are both exact on it — so it tests
**exactness**, not order.

`harmonic_plate` is the textbook Laplace problem and is deliberately **not
polynomial**: the discretisation has a genuine truncation error, so the order
is measurable, and the boundary datum is exact in closed form rather than
itself an approximation. This is why `HarmonicProfile1D` exists.

A test asserts each case actually has a varying edge, so the suite cannot
quietly degenerate into testing the Sprint 4 API again, and another asserts the
shear case's flux edge differs from its own mean by more than 100 W/m² — a
constant could not have passed.

---

## 10. Oracle

**Independent of the solver in the way that matters.** Each exact field is a
closed-form expression evaluated at the support's node coordinates. It shares
no code with `assemble`, no matrix, and no boundary handling.

Four quantities are compared, not one:

| Measure | Result (`sheared_plate`, 32×32) |
|---|---|
| field, L∞ / scale | < 1e-9 |
| prescribed edges against their own laws, per node | < 1e-9 relative |
| **flux edges** against their laws | < 1e-8 relative |
| field, L2 / scale | < 1e-9 |

The flux comparison is a real one rather than a restatement of the assembly:
the exact normal derivative does not vary along the normal, so a one-sided
difference of the *solution* is an exact estimator of it, and it is compared
against the declared law evaluated at each node's own coordinate.

---

## 11. Convergence table

Order computed from measured errors, never asserted as a constant.

**`harmonic_plate`** — the new varying-Dirichlet case

| n | h | L2 | order | L∞ | order |
|---|---|---|---|---|---|
| 16 | 0.066667 | 2.3010e-02 | — | 4.9903e-02 | — |
| 32 | 0.032258 | 5.5840e-03 | **1.951** | 1.1842e-02 | **1.981** |
| 64 | 0.015873 | 1.3748e-03 | **1.976** | 2.8730e-03 | **1.997** |
| 128 | 0.007874 | 3.4105e-04 | **1.988** | 7.0734e-04 | **1.999** |

**`declared_source_plate`** — the varying source stated as a law

| n | h | L2 | order | L∞ | order |
|---|---|---|---|---|---|
| 16 | 0.066667 | 6.8690e-02 | — | 1.4494e-01 | — |
| 32 | 0.032258 | 1.6591e-02 | **1.957** | 3.4164e-02 | **1.991** |
| 64 | 0.015873 | 4.0802e-03 | **1.978** | 8.2848e-03 | **1.998** |
| 128 | 0.007874 | 1.0119e-03 | **1.989** | 2.0395e-03 | **1.999** |

Identical to Sprint 4's array-sourced `sine_plate` to every printed digit — the
law reproduces the array it replaces, which is what makes it a replacement.

**`sheared_plate`** — exact, so **order is not reported**

| n | L2 | L∞ |
|---|---|---|
| 16 | 1.9950e-10 | 1.4764e-09 |
| 32 | 8.5114e-10 | 8.3195e-09 |
| 64 | 3.5387e-09 | 5.5903e-08 |
| 128 | 1.6472e-08 | 6.5278e-07 |

These are round-off, growing with the condition number as a direct solve's
round-off does. Fitting an "order" to them would produce a negative number and
mean nothing; the case is asserted against an exactness bound instead.

Sprint 4's `sine_plate` and `cosine_column` are unchanged (1.957→1.989 and
2.017→2.004 in L2).

---

## 12. Serialization / fingerprint

Every profile round-trips through `load_profile`, with the schema checked on
read. The digest covers the law's own facts and **excludes the description**.

Asserted to move the fingerprint: values, coordinates, span, axis, unit,
coordinate unit, interpolation method, and profile type — and all six variants
of a table produce six distinct digests. Asserted **not** to move it: the
description. So two laws sharing a display name and differing in their values
have different identities, and renaming one changes nothing.

A payload with its schema removed is refused; one naming a law this version
does not have is refused; and a tampered value deserializes to a *different
identity* rather than to the original.

---

## 13. Failure matrix

| Refused | Where |
|---|---|
| wrong profile output dimension | `require_output_dimension` |
| coordinate unit that is not a length | `TabulatedProfile1D` |
| law bound to an incompatible edge coordinate | `require_axis` |
| non-finite parameter, coordinate or value | `_finite`, on construction |
| duplicate tabulated coordinates | `TabulatedProfile1D` |
| unsorted tabulated coordinates | `TabulatedProfile1D` |
| table shorter than the edge it is bound to | `require_covers` |
| fewer than two samples, or mismatched lengths | `TabulatedProfile1D` |
| out-of-range evaluation (no extrapolation declared) | `evaluate` |
| an undeclared interpolation method | `Interpolation(...)` |
| wrong source dimension, or source not covering the plate | `require_applicable` |
| wrong flux dimension | `require_applicable` |
| missing schema, or an unknown law kind | `load_profile` |
| an arbitrary callable or a string expression | `as_profile` |
| two prescribed edges disagreeing at a corner | `_require_corners_agree` |
| a law offered as a field-transfer payload | `FieldDependency.admit` |
| a spatially varying coefficient (executed) | `require_applicable` |

---

## 14. No-callable guarantee

Asserted on nine inputs: a lambda, an ordinary function, a `functools.partial`,
an object with `__call__`, `eval`, `compile`, a string expression, a dict
carrying `{"expression": ...}`, and a bare `object()`. All refused.

The deserializer is checked structurally as well: a test greps the profile
module's source for `eval(`, `exec(`, `__import__`, `importlib` and
`getattr(builtins` and asserts none appear. `load_profile` dispatches on a
closed table, so a payload cannot name code and be obeyed, whatever it claims
to be.

---

## 15. Targeted mutations

**CONTROL GREEN · 10/10 killed · 0 survivors.** Run through the sprint's own
apply/revert harness — `tests/mutation_guards.py` is certification-pinned and
cannot gain mutations — with each revert verified by digest.

| # | Mutation | Verdict |
|---|---|---|
| SP-1 | a law stops checking which coordinate it varies along | RED (killed) |
| SP-2 | a law stops checking the dimension of its own output | RED (killed) |
| SP-3 | a tabulated law bound to a span it does not cover is accepted | RED (killed) |
| SP-4 | the interpolation method leaves the record and the digest | RED (killed) |
| SP-5 | the digest stops covering the values, so a changed law reuses it | RED (killed) |
| SP-6 | an arbitrary callable is accepted as a spatial law | RED (killed) |
| SP-7 | an edge law is evaluated by array index instead of position | RED (killed) |
| SP-8 | a varying prescribed edge is imposed as its first value | RED (killed) |
| SP-9 | a source law's dimension stops being checked | RED (killed) |
| SP-10 | a serialized law is rebuilt without checking its schema | RED (killed) |

Sprint 4's field mutations were re-run against this tree: **FM-1..FM-8, control
green, 8/8 killed.**

### Provenance (Phase 15)

A result records **which laws produced it, by identity**: each edge's kind,
64-character fingerprint, unit and varying axis, plus the source law's. No
evaluated edge values reach provenance — a test asserts the whole serialized
result stays under 8 KB, and another that two different laws give two different
provenance fingerprints.

---

## 16. Backward compatibility

* **Scalar domains: 864 serialized output paths, 0 changed, 0 added, 0
  removed**, comparing the coupled electrothermal case (DC + material
  resistance + lumped thermal) and the battery case against the pre-Sprint-4
  base `5c979fc`. No scalar domain gained any spatial-profile concept.
* **Sprint 4 constant BC syntax is untouched.** A constant condition's payload
  has exactly the keys it had, and its `value` is still
  `{"schema": "quantity/1", "magnitude": ..., "units": ...}`.
* **Field transfer semantics unchanged.** The full Sprint 4 compatibility
  matrix is re-asserted with the profile layer present, and a profile is
  refused as a transfer payload from both directions: *a law says what a field
  should be everywhere and is an input; a record names values that were
  computed and is an output.*

One Sprint 4 test assertion changed, and one only: a Dirichlet condition of the
wrong dimension is now refused by the profile layer rather than by
`require_same_dimension`, so the expected message moved. Same fact, stated once
for both spellings.

---

## 17. Performance

No architectural-scale regression. **Assembly with varying boundaries costs
what assembly with constant boundaries costs.**

| Single evaluation | |
|---|---|
| constant | 100 ns |
| linear | 500 ns |
| harmonic | 700 ns |
| separable 2-D | 1.40 µs |
| tabulated (33 samples) | 2.10 µs |

| Over a whole edge (linear) | |
|---|---|
| 16 points | 16.3 µs |
| 32 points | 28.6 µs |
| 64 points | 53.4 µs |
| 128 points | 100.8 µs |
| 128 points, tabulated | 287.7 µs |

| Over a whole plate | |
|---|---|
| separable 2-D, 16×16 | 0.37 ms |
| separable 2-D, 64×64 | 5.71 ms |
| separable 2-D, 128×128 | 23.4 ms |

| 128×128 solve | assemble | total |
|---|---|---|
| constant BC (`sine_plate`) | 176.3 ms | 397.0 ms |
| varying BC (`harmonic_plate`) | **175.1 ms** | 392.7 ms |
| four varying BCs (`sheared_plate`) | **176.6 ms** | 393.5 ms |
| declared separable source | 206.1 ms | 445.5 ms |

The only measurable cost is the declared 2-D source, +30 ms at 128×128, which
is the 23 ms plate evaluation plus noise — and it buys a source that is one
declaration at every resolution instead of an array per support.

Noted, not optimized: `TabulatedProfile1D` scans its samples linearly, so
evaluation is O(samples). At 33 samples that is 2.1 µs. A large table on a fine
mesh would want a bisection; nothing here needs it.

---

## 18. FAST / FULL / wheel / guards

| Run | Result |
|---|---|
| **FAST** (`-m "not expensive"`) | **4447 passed, 3 skipped, 541 deselected** |
| **FULL** (`pytest tests/`) | **4988 passed, 3 skipped, 0 failed** |
| Contract Guard | 305 passed |
| Capability Boundary | 304 passed |
| Scientific Truth | 293 passed, 3 skipped |
| field + profile + conduction suites | 271 passed |
| **installed wheel** | **FIELD, PROFILE AND CONDUCTION SMOKE OK · 26 checks**, + 271 passed |

**Wheel.** Built from `git archive 5d03d5b`: 204 entries, **0 under `src/`**,
all eight `scientific/fields/` modules including `profiles.py`. Run under
`python -S -E` so `site.py` never executes and the venv's editable-install hook
is never registered, with a `conftest.py` asserting `engcore.__file__` is under
the install target before any test runs. The smoke solves a bilinear plate with
four varying edges through the installed package and checks it is exact.

**Certified mutation harness: not run.** It is pinned to a core tree this
sprint changed again (§19), so running it would certify nothing; and its
certificate does not describe HEAD in any case. The targeted SP and FM
harnesses cover the new surface.

---

## 19. Certification status

| | |
|---|---|
| stored certificate modules | **47** |
| current modules under `src/engcore/scientific` | **55** |
| stored `tree_sha256` | `82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507` |
| did this sprint change the tree again | **yes — +1 (`fields/profiles.py`)** |

Sprint 4 took it from 47 to 54; this sprint takes it to 55.

**`certification/current_core_v1.json` does not certify HEAD and must not be
described as current.** It has not been edited here — recertification is a
decision, not a digest update, and the spec says this sprint does not perform
one.

The stored digest **could not be independently verified**: no script or
documented method for computing it exists in the repository, and `certification/`
contains only the JSON. A recomputation over sorted relative paths and file
bytes gives `c061590d…`, which says nothing about the stored value because the
original method is unknown. That is a reproducibility gap in the certificate
itself, and is reported rather than papered over.

### The second defect this sprint found

`fix(thermal): judge the solve by scale-free criteria` (`bab1420`) is not
expressiveness work. Both verification criteria were absolute where the
quantities they judge have a scale the caller chooses:

* `boundary_conditions_held` compared the worst prescribed-node error against
  **1e-9 in the field's own unit** — twelve significant digits of a field whose
  magnitudes are in the hundreds. **Every manufactured case in the repository
  was failing it, at every resolution, including at Sprint 4's head**, which
  was verified directly in a worktree at `ff3d97b` before this claim was
  written. Nothing caught it: the convergence study reads the error arrays and
  never the validation report, and the one test that reads the report uses a
  uniform plate whose boundary rows are all identical. It is now relative, at
  1e-7, and a test asserts a flattened varying edge would still be caught.
* `field_linear_system_residual` divided the residual by `max|b|` alone, which
  grows with the conditioning of A and explodes when b is small. Across five
  cases it spanned 4.7e-14 to 1.4e-09 and failed the harmonic plate at 64 and
  128. It is now the backward error
  `max|A T − b| / (max|A|·max|T| + max|b|)`, which measured **4.3e-16 to
  2.7e-15** on the same five cases: flat, at machine epsilon, resolution
  independent.

A new test asserts every manufactured case passes its own validation report at
every resolution — the assertion whose absence let this ship.

---

## 20. Files changed

15 files, +2851 / −72.

| File | Δ |
|---|---|
| `src/engcore/scientific/fields/profiles.py` | **new**, 690 |
| `src/engcore/scientific/fields/conditions.py` | +144 |
| `src/engcore/scientific/fields/regions.py` | +31 |
| `src/engcore/scientific/fields/__init__.py` | +26 |
| `src/engcore/data/field.py` | +69 |
| `src/engcore/domains/thermal_models/conduction2d.py` | +261 |
| `tests/test_field_profiles.py` | **new**, 417 |
| `tests/test_conduction2d_profiled.py` | **new**, 401 |
| `tests/test_field_profile_limit.py` | **new**, 275 |
| `tests/test_field_profiled_conditions.py` | **new**, 258 |
| `tests/test_field_coefficient_spike.py` | **new**, 142 |
| `tests/manufactured_conduction2d.py` | +159 |
| `tests/test_field_composition.py` | +43 |
| `tests/test_field_records.py` | +5 |
| `tests/test_conduction2d.py` | +2 |

No scalar-domain file was touched. Nothing under `domains/thermal/`,
`experiments/`, `benchmarks/blind/` or `certification/` changed.

---

## 21. Commits

| | |
|---|---|
| `377769b` | `test(fields): reproduce constant-profile expressiveness limit` |
| `c2ff29a` | `feat(fields): add deterministic spatial profiles` |
| `3ccb339` | `feat(fields): support profiled boundary conditions` |
| `0d11bdf` | `feat(thermal): support varying boundary and source profiles` |
| `bab1420` | `fix(thermal): judge the solve by scale-free criteria` |
| `907d7a7` | `test(thermal): validate profiled manufactured solution` |
| `5d03d5b` | `feat(fields): ask a law whether it covers a two-dimensional extent` |

**Correction to `907d7a7`'s message.** It states `harmonic_plate` L2 orders as
"2.02, 2.01, 2.00 (Linf 2.01, 2.00, 2.00)". The measured values are **L2 1.951,
1.976, 1.988 and L∞ 1.981, 1.997, 1.999** — the table in §11 and the assertions
in the tests are correct; the commit message is not. It was not amended,
because amending commits is out of bounds for this sprint. The error is
recorded here instead.

---

## 22. Push result

Pushed to `origin/claude/field-expressiveness-sprint-5`. `main` untouched.

---

## 23. Exact new capability claim

> **Forge can represent and solve a structured-grid 2-D conduction field whose
> prescribed values, boundary fluxes and volumetric source are declared spatial
> laws — deterministic, unit-aware, coordinate-aware, serializable and
> fingerprinted records rather than executable objects — and can represent, but
> not execute, a spatially varying conductivity.**

Every clause is load-bearing. *Declared laws*: five closed forms, no expression
language. *Coordinate-aware*: evaluated from physical positions, never indices.
*Represent but not execute* a varying conductivity: §8.

---

## 24. Explicit non-claims

Sprint 4's non-claims stand unchanged and are repeated because the new capability
makes them easier to overstate:

* **Not arbitrary PDEs.** One equation.
* **Not a FEM platform.** No elements, basis functions or quadrature.
* **Not CFD.** No advection, no nonlinearity, no coupling, no time.

And this sprint's own:

* **Not a symbolic mathematics framework.** Five closed forms with fixed
  parameters. No parser, no expression tree, no composition of arbitrary laws,
  no differentiation, no simplification.
* **Not heterogeneous conduction.** `k(x, y)` is representable and refused at
  execution (§8).
* **Not arbitrary interpolation.** `LINEAR` is the only declared rule; anything
  else is refused, not approximated.
* **No extrapolation.** A tabulated law outside its span refuses.
* **Not a general 2-D law.** The only two-dimensional form is a separable
  product; a genuinely non-separable law has no representation here.
* **Robin is still representable and unserved.**
* **No transient term.** `FieldInitialCondition` still has no consumer.

---

## 25. Next step

In the order the evidence supports:

1. **Recertify, or retire the certificate.** It has now missed two sprints and
   its digest cannot be recomputed by any documented method. Until then nothing
   may call V1 current.
2. **A `TabulatedProfile2D`**, if a non-separable two-dimensional law is ever
   needed. The separable product covers the standard closed forms and nothing
   measured.
3. **Heterogeneous conduction**, which is a discretisation change — the
   conservative form with face conductivities — and should be scoped as one.
   The representation is already there.
4. **A corner rule for flux edges.** Two flux edges meeting at a corner are
   currently exempt from the agreement check because a derivative constrains
   nothing at a point. That is correct, and it means a corner where two flux
   edges disagree about the *normal* is still unexamined.
5. **`domains/thermal/conduction1d` still routes its field through
   `diagnostics`.** Unchanged from Sprint 4, and still needs its own decision
   about a byte-pinned frozen tree.
