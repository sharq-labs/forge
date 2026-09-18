# SDR-08 — Reference Posterior Reproducibility Closure

## Finding

The Core V4 false-confidence reference posterior artifact failed the expensive
re-derivation gate even though every reference case still converged and the
rebuilt scientific moments were unchanged to floating-point round-off.

Historical failing gate:

- pinned artifact digest:
  `8c21374c99ae0527aeb5511f3c9b96e7fa108f84450e6360d87579cc78105d7d`
- rebuilt artifact digest:
  `7176ef65b6a194d13b0aae40e3ee4eb79f6dc3a1bea019b9422b111ea9aac1ac`

The old gate required byte-identical serialized float64 output from a fresh
NumPy/SciPy execution.

## What did not change

The Git blob IDs prove that, between the Batch-6 reference commit and the
PR-48 head, both of these files remained byte-identical:

- `REFERENCE_POSTERIORS.json`
- `audit/reference_posteriors.py`

The seven reference-case builders retain the same scientific equations and
case declarations. Changes around the synthetic fixture were admission-record
strings and later trust contracts, not the reference physics.

The committed reference file is therefore not being silently rewritten.

## What the failing CI actually rebuilt

The Python 3.12 scientific gate rebuilt all seven references and reported every
one as CONVERGED.

Examples of pinned versus rebuilt values:

| Case | Quantity | Pinned | Rebuilt | Difference |
|---|---|---:|---:|---:|
| off_axis_flat_tail | sd[0] | 5.674841993486391 | 5.674841993486394 | ~3e-15 |
| off_axis_flat_tail | sd[1] | 11.349683986972789 | 11.349683986972781 | ~8e-15 |
| off_axis_flat_tail | mean[1] | 6.574601973952099e-16 | 6.609296443471635e-16 | ~3.5e-18 |
| worse_local_optimum_holds_the_mass | sd | 7.0758001732946445 | 7.075800173294645 | ~5e-16 |
| retracted_starts_never_leave_the_basin | halved-step movement | 0 | ~1.776e-16 | ~1.776e-16 |

The remaining printed means and standard deviations were identical at Python
float representation.

These are round-off differences, not scientifically different posteriors.

## Provider environment

The failing CI installed from lower-bounded dependencies and resolved, among
other packages:

- Python 3.12.14
- NumPy 2.5.3
- SciPy 1.18.1

The project deliberately lower-bounds its scientific stack rather than pinning
one resolved machine environment. Requiring exact raw float64 bytes from every
valid provider stack therefore made provider-level reduction/interpolation
round-off look like a scientific reproducibility failure.

## Corrected contract

Two different questions are now tested separately.

### 1. Is the committed evidence artifact exactly the artifact that was reviewed?

**Still exact.**

The cheap integrity test recomputes SHA-256 over the committed JSON payload and
requires exact equality with the stored digest.

No tolerance applies.

### 2. Does a fresh provider execution re-derive the same scientific posterior?

**Numerical comparison.**

Structural declarations remain exact:

- schema;
- protocol;
- case set;
- problem id;
- parameter names;
- node counts;
- bounds;
- quantile step count;
- convergence boolean.

Floating results are compared in units of each marginal standard deviation.

The cross-provider limit is:

```
4096 * float64_epsilon
≈ 9.09e-13 marginal SD
```

It applies to:

- mean;
- marginal standard deviation;
- halved-step movement;
- every pinned quantile-function sample.

This is more than ten orders of magnitude tighter than the existing reference
admission condition:

```
REFERENCE_CONVERGENCE_SD = 0.01 SD
```

so the new rule admits floating-provider round-off while still refusing a
scientifically meaningful posterior movement.

## What was not changed

- `REFERENCE_POSTERIORS.json` was **not regenerated**.
- Its digest was **not replaced**.
- The 0.01 SD dense-reference convergence criterion was not changed.
- The 2000-step quantile grid was not changed.
- The 0.90 false-confidence mass floor was not changed.
- No failing reference was reclassified as converged.
- No scientific case, model equation or observation was changed to make CI
  pass.

## New guards

The conformance suite now explicitly verifies that:

1. a sub-tolerance float64 perturbation is accepted as provider round-off;
2. a perturbation above the declared re-derivation tolerance is rejected;
3. a quantile-function shift above that tolerance is rejected;
4. the committed artifact's own byte digest remains exact.

## Closure criterion

SDR-08 is closed only when the Python 3.12 scientific gate re-derives the
current pinned reference successfully under this two-part contract and the
normal FAST/trust/mutation gates remain green.
