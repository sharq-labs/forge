# Forge Module-by-Module Code Review Ledger

This file is the persistent ledger for the source-code-first review of Forge.

## Review rules

- Review one module at a time.
- Source code is the primary evidence.
- Tests are inspected as executable contracts, but a test is **NOT RUN** unless it was actually executed in the current review.
- Project plan/progress Markdown files are not used as evidence for module quality.
- Do not award scientific validity because code is large, tests exist, or a solver converges.
- Separate:
  - implementation correctness,
  - scientific semantics,
  - architecture,
  - reproducibility/provenance,
  - engineering usefulness,
  - test coverage,
  - production readiness.
- Findings remain open until the code change is reviewed and verified.
- Every module ends in one of:
  - `REVIEWED — CLEAN`
  - `REVIEWED — FIXES PENDING`
  - `REVIEWED — BLOCKED`

## Repository baseline

Review started from:

- repository: `sharq-labs/forge`
- branch: `feat/big-10-multitimescale`
- source HEAD inspected for Review 01: `d5f4b393ba9fedc35df62556600380caf1388ddc`

---

# Review 01 — `engcore.scientific.units`

**Status:** `REVIEWED — FIXES PENDING`

## Scope inspected

Production code:

- `src/engcore/scientific/units/__init__.py`
- `src/engcore/scientific/units/quantity.py`
- `src/engcore/scientific/units/validation.py`

Relevant test code inspected:

- `tests/test_offset_unit_arithmetic.py`
- `tests/test_offset_unit_declaration.py`
- `tests/test_unit_conversion_equivalence.py`
- `tests/test_unit_memoization.py`
- `tests/test_unit_registry_initialization.py`
- relevant unit-registry/cache guards in `tests/test_core_runtime_caches.py`
- relevant unit-registry mutation guards in `tests/test_core_guards.py`
- `tests/scientific/verification/test_quantity_comparison_v2.py`

Dependency declaration inspected:

- `pyproject.toml` — Pint is currently declared as `pint>=0.23`.

Tests were inspected but **NOT RUN** in this review.

## What the module currently owns

The module is a contract around Pint rather than a replacement for dimensional algebra.

It currently provides:

- immutable finite `Quantity` records,
- canonical unit spelling,
- dimensional compatibility,
- absolute conversion,
- spread/difference conversion,
- correct affine-temperature arithmetic,
- explicit rejection of non-finite interpreted quantities,
- deterministic serialization,
- a sealed process-wide Pint registry,
- registry mutation detection,
- registry fingerprinting,
- bounded unit/conversion caches,
- thread-safe one-time registry initialization,
- physical-magnitude canonicalization for identities,
- common dimensional validation helpers.

## Strong points confirmed from code

### S-01 — Affine units are treated seriously

The code correctly distinguishes absolute temperature coordinates from differences.

Examples implemented in the contract:

- `30 degC - 20 degC` becomes a temperature difference rather than `10 degC` as an absolute point.
- absolute + absolute offset temperatures are refused where the backend says the operation is meaningless.
- `magnitude_as_spread_in()` exists specifically for tolerances/bands/sigma-like differences.
- `require_spread_unit()` prevents an affine absolute unit from silently becoming a tolerance.

This is a strong scientific-safety property.

### S-02 — Backend mutation is actively constrained

`_SealedUnitRegistry` refuses mutating Pint APIs and attribute writes after construction.

Direct mutation of Pint internals cannot be fully prevented in Python, so the module also provides `verify_registry_unmutated()` as a detector.

The code explicitly distinguishes prevention from detection.

### S-03 — Registry initialization is thread-safe

Registry construction is guarded by `_REGISTRY_LOCK`, rechecked under the lock, sealed before publication, and the registry/snapshot/digest are published together.

This avoids multiple first-use registries under concurrent initialization.

### S-04 — Unit caches have a defensible safety model

The caches are bounded and based on lexical/unit-registry facts rather than scientific-model state.

`clear_unit_caches()` explicitly clears the module's memoized functions and the test suite contains an enumeration guard intended to catch a new memo omitted from the clear path.

### S-05 — Quantity parsing rejects arithmetic disguised as a declaration

The parser has explicit logic preventing input such as arithmetic expressions from silently becoming a scientific quantity while still supporting legitimate unit expressions and offset-unit declarations.

### S-06 — Identity canonicalization exists

`canonical_magnitude()` addresses physically identical declarations written in different units and normalizes negative zero for identity/digest use.

That is important for mesh/material/parameter identities above this layer.

---

# Findings

## U-01 — HIGH — `Quantity.from_dict()` bypasses the constructor's magnitude-type guard

The constructor deliberately refuses `bool` and `str` magnitudes:

```python
Quantity(True, "volt")      # intended refusal
Quantity("5", "volt")       # intended refusal
```

But deserialization currently does:

```python
return cls(float(payload["magnitude"]), str(payload["units"]))
```

That pre-coercion means a serialized payload can turn:

```json
{"magnitude": true, "units": "volt"}
```

into `1.0 volt` before `Quantity.__post_init__` gets a chance to reject the boolean.

Likewise a numeric string can be converted before the constructor sees that it was a string.

### Why this matters

This is a record-boundary integrity issue. The class states that a flag is not a measurement, but its own wire constructor can erase the type information before enforcing the rule.

### Recommended fix

Do not pre-coerce the magnitude in `from_dict()`.

Pass the raw value into the constructor and require the serialized unit field to be an actual string rather than calling `str(...)` first.

Add adversarial round-trip tests for:

- boolean magnitude,
- numeric-string magnitude,
- non-string unit.

---

## U-02 — HIGH — `coerce_quantity()` also bypasses the same type guard

Current fallback:

```python
return Quantity(float(value), unit)
```

Therefore:

```python
coerce_quantity(True, "volt")
```

can become `1.0 volt`, even though `Quantity(True, "volt")` is explicitly forbidden.

The same pre-coercion pattern can accept values solely because Python exposes `__float__`.

### Why this matters

`coerce_quantity()` is described as a sanctioned numeric-input boundary. Its accepted runtime types should match that contract exactly.

### Recommended fix

Validate the input type before conversion.

At minimum:

- refuse `bool`,
- refuse arbitrary strings on the numeric branch,
- define explicitly which numeric scalar families are accepted.

Prefer one shared magnitude-validation helper so constructor/deserializer/coercion cannot drift apart.

---

## U-03 — MEDIUM — scalar multiplication/division accept values the Quantity contract otherwise rejects

`Quantity.__mul__` and `Quantity.__truediv__` use:

```python
float(other)
```

for non-`Quantity` operands.

That means values such as booleans and numeric strings can be accepted as scale factors even though the class explicitly states that bool/string are not scientific magnitudes.

Examples implied by the current implementation:

```python
Quantity(1, "meter") * True
Quantity(1, "meter") * "2"
```

### Recommended fix

Introduce an explicit scalar guard for arithmetic.

Accepted scale factors should be intentionally numeric; accidental truth values or numeric text should be refused.

Add tests for multiplication and division by:

- `True` / `False`,
- numeric strings,
- invalid objects,
- zero where division semantics need a stable Forge error contract.

---

## U-04 — MEDIUM — heavy reliance on Pint private internals while dependency policy is lower-bound-only

The module uses private/backend implementation details in several places, including structures such as:

- `_units`,
- `_prefixes`,
- `_dimensions`,
- `_contexts`,
- `Unit(...)._units`,
- direct parsing/inspection helpers around Pint's internal containers.

At the package level Pint is declared as:

```text
pint>=0.23
```

with no upper bound.

### Why this matters

The scientific semantics are carefully guarded, but a future Pint release may change private representation while still satisfying the dependency declaration.

This is primarily a compatibility/operational risk, not evidence that current numerical answers are wrong.

### Recommended fix

Do not immediately rewrite the layer.

Instead:

1. define a tested Pint compatibility range or compatibility policy,
2. run the units contract against at least:
   - the minimum supported Pint,
   - the primary development Pint,
   - latest Pint in a compatibility job,
3. isolate private-Pint access behind the smallest possible internal adapter,
4. refuse at startup with a precise compatibility error if a required backend invariant disappears.

---

## U-05 — MEDIUM / CROSS-MODULE FOLLOW-UP — exact unit-registry identity needs to be proven in replay/execution provenance

The module has a thoughtful `registry_fingerprint()` representing the sealed definition baseline.

However `Quantity.to_dict()` itself serializes only:

- magnitude,
- normalized unit string.

That is reasonable for keeping each quantity compact, but because Pint is not pinned to one exact version, replay across environments needs some higher-level record to bind the unit-definition baseline.

### Review action

Do **not** change `Quantity` schema yet.

When reviewing:

- `scientific.results`,
- execution manifests,
- replay/provenance,

verify whether `registry_fingerprint()` is bound once at the execution/replay envelope.

If it is already bound there, close this finding.

If not, add it there rather than duplicating the fingerprint into every quantity.

---

## U-06 — LOW — registry fingerprint explicitly cannot fingerprint context transformation bodies

The code documents that Pint context transformation callables do not expose source in a form currently included in the registry snapshot; the snapshot records context keys and declared metadata, not transformation bodies.

This is a known limitation rather than a hidden defect.

### Current risk

Low while Forge forbids runtime registry/context mutation and does not rely on mutable ad-hoc contexts for scientific meaning.

### Follow-up

If Forge later permits custom unit contexts, the context transformation itself must become content-addressed scientific input or remain prohibited.

---

## U-07 — LOW / API DECISION — critical scale semantics are not all exported at `engcore.scientific.units` package root

The package root exports the general quantity/dimension API, but important internal semantics such as:

- `require_spread_unit`,
- `is_ratio_scale`,
- `is_delta_unit`,
- `canonical_magnitude`

live on `units.quantity`.

This is not currently a correctness defect.

Before BIG 11 external provider adapters proliferate, decide which of these are supported provider-facing contracts versus deliberately internal helpers, so providers do not grow dependencies on unstable private paths by accident.

---

# Test-review observations

The unit-focused tests are unusually strong in the following areas:

- offset/affine temperature arithmetic,
- offset-unit declaration parsing,
- conversion equivalence,
- cache correctness,
- cache clearing,
- unit-registry one-time initialization under threads,
- unit-registry mutation refusal/detection,
- typed tolerance use in verification.

In the unit-focused files inspected, no targeted test was found for the three pre-coercion paths identified above:

- `Quantity.from_dict(bool/string magnitude)`,
- `coerce_quantity(bool)`,
- scalar `Quantity * bool/string` and `Quantity / bool/string`.

This statement is scoped to the reviewed tests; the whole suite was not executed in this review.

---

# Scores — Review 01

| Dimension | Score | Notes |
|---|---:|---|
| Architecture | ⭐⭐⭐⭐⭐ | Clean backend-wrapper boundary; Pint owns algebra |
| Scientific semantics | ⭐⭐⭐⭐⭐ | Strong affine/spread/dimensional handling |
| Record integrity | ⭐⭐⭐⭐☆ | Strong overall, but deserialization pre-coercion needs repair |
| Reproducibility | ⭐⭐⭐⭐☆ | Registry fingerprint exists; higher-level binding must be verified later |
| Test design | ⭐⭐⭐⭐⭐ | Deep adversarial coverage around historical unit defects |
| Extensibility | ⭐⭐⭐⭐☆ | Good contract, but private Pint internals raise compatibility cost |
| Production readiness | ⭐⭐⭐⭐☆ | Strong foundation with several bounded hardening items |

**Overall:** ⭐⭐⭐⭐☆ (strong module; no redesign recommended)

---

# Action list before marking Units clean

## Fix now

- [ ] U-01: preserve raw magnitude/unit types through `Quantity.from_dict()` and refuse invalid wire types.
- [ ] U-02: make `coerce_quantity()` obey the same magnitude-type contract.
- [ ] U-03: guard scalar multiplication/division against bool/string accidental coercion.
- [ ] Add focused adversarial tests for U-01/U-02/U-03.

## Verify later in dependent-module reviews

- [ ] U-05: verify unit-registry fingerprint is bound to execution/replay provenance.
- [ ] Decide provider-facing API status of spread/ratio/canonical-identity helpers.
- [ ] Establish/test Pint-version compatibility policy around private backend access.

## No action required now

- [x] Keep Pint as the dimensional algebra backend.
- [x] Keep affine absolute values and spreads semantically separate.
- [x] Keep the registry sealed.
- [x] Keep bounded lexical caches.
- [x] Keep registry mutation detection as defense in depth.

---

# Verification status for Review 01

Code inspection: **DONE**

Focused tests: **NOT RUN**

Full FAST suite: **NOT RUN**

Full SCIENTIFIC suite: **NOT RUN**

Mutation campaigns: **NOT RUN**

Recertification: **NOT RUN**

The module remains:

`REVIEWED — FIXES PENDING`

until U-01/U-02/U-03 are fixed and focused tests are executed.
