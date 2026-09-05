# MODEL0-R DIFFERENTIAL PROOF — Preregistration

**Milestone:** `MODEL0-R DIFFERENTIAL PROOF` — does `ModelRealizationDefinition`
carry independent semantic information?
**Kind:** evidence milestone against an existing `DESIGN-FROZEN` boundary. Not `FOUNDATION1`.
**Decision status under test:** MODEL0-R is `DESIGN-FROZEN`; that is not reopened here.
**Evidence target:** at most `L2 DIFFERENTIATED`, and only if §9's ceiling is met.
**Date:** 2026-09-02
**Branch:** `model0r-realization-foundation`
**Preregistered before implementation.** Everything below was written before any
source file was added or edited.

> **This file is immutable.** It records what was committed to *before* results
> were observed. Executed results, corrections, adversarial findings and the
> final classification go in `docs/model0r-differential-evidence.md`.

---

# 1. The single question

> Does the separation between Scientific Model, Computational Realization and
> Solver carry **independently useful information** when ONE scientific model is
> executed through TWO materially different realizations?

Nothing else is decided. This milestone does not define Materials, Components,
Connectors, `FIELD0`, `SYSTEM0`, `EQIR0`, coupling, API/MCP, HVAC, or a generic
provider framework, and does not begin the electro-thermal vertical proof.

---

# 2. Hypothesis and null hypothesis

**HYPOTHESIS (H1).** For one `ScientificModelDefinition`, two materially
different computational realizations require independent semantic information
that cannot be safely or completely derived from

```text
(model, solver, runtime settings)
```

alone.

**NULL / FALSIFYING HYPOTHESIS (H0).** `ModelRealizationDefinition` contributes
no meaningful independent information; the same behaviour can be represented
cleanly using only model + solver + settings without semantic loss.

**H0 is allowed to win.** §5 is the test designed to let it win, it runs as a
gate *before* the expensive work (§8), and a negative result is reported as a
result, not repaired.

Stated in falsifiable form: there exist two realization records `R1`, `R2` of
one model such that some fact `F` is (a) true of `R1` and false of `R2`,
(b) decidable before execution, (c) consequential for validity, selection or
scientific attribution, and (d) has no correct home on the model, on the
solver, or in runtime settings. H0 wins if no such `F` survives §5.

---

# 3. Selected pair, and why

Selected after `architecture-decision-reviewer` returned **ACCEPT WITH CHANGES**:
adopt candidate (B), reject candidate (A) as the primary pair.

One model — `thermal.conduction1d.linear_diffusion` v`0.1.0` (`DIFFUSION_MODEL`,
in the byte-frozen thermal tree) — realized two ways:

| | `R1` implicit | `R2` explicit |
|---|---|---|
| Scheme | Backward Euler in time, 2nd-order central in space | Forward Euler in time (FTCS), 2nd-order central in space |
| Stability | **unconditional** | **conditional**, `r = α·Δt/Δx² ≤ 1/2` |
| Linear solve per step | required | none |
| `formulation` | `PDE` | `PDE` — deliberately **the same** |

## 3.1 Why not the analytic-vs-numerical pair (candidate A)

Three reasons from the repository, not from preference:

1. `reference.py` is the **verification oracle** the FD solver is already gated
   against at `ANALYTIC_REL_TOL`. Agreement is guaranteed by an existing frozen
   gate, so the pair cannot return an informative negative.
2. Promoting the oracle to a peer realization erodes the independence
   `reference.py` was explicitly designed for ("a verification that shares code
   with the thing it verifies tests only that the shared code is
   self-consistent").
3. The initial condition is welded in two pinned files, so there is **no
   reachable regime in which the model is valid and the analytic realization is
   inadequate**. The pair cannot test the one statement the separation exists to
   enable.

The closed form keeps its existing role and verifies **both** members.

## 3.2 Why this pair is materially different

Not by author, not by label, and not by solver brand:

* The stability envelope is a **theorem about the scheme** (von Neumann analysis
  of FTCS), true of every correct implementation and removable by none.
* `formulation` is held **constant** at `PDE`, so the enum is not doing the
  work.
* The difference is forced onto `required_solver_capabilities` and onto declared
  applicability — the two places the claim under test says realization-level
  information lives.
* The frozen domain **pre-recorded the exact quantity this pair needs**:
  `ConductionSlab.fourier_number` exists and its docstring says it "is recorded
  because it is the number that would constrain an explicit scheme, and a reader
  comparing schemes will want it." This milestone turns that latent statement
  into executed evidence.

## 3.3 Same model, not two models

Both realizations carry `model=ModelReference("thermal.conduction1d.linear_diffusion", "0.1.0")`.
No second `ScientificModelDefinition` is created. The physics, assumptions,
validity domain and units are the frozen model's, unmodified.

---

# 4. What counts as independent information

Identifiers and duplicated labels do **not** count. Every field actually
exercised is classified, before the result is known, into exactly one of:

```text
A. MODEL-LEVEL              the scientific claim
B. REALIZATION-LEVEL        how the claim is computed
C. SOLVER-LEVEL             what a backend can execute
D. RUNTIME/EXECUTION-LEVEL  this particular run
E. CURRENTLY AMBIGUOUS
```

**If a supposedly realization-level field repeatedly classifies elsewhere, that
counts against MODEL0-R** and is reported as such.

The classification is recorded in the evidence document as a table, field by
field, with the reason. A field that is exercised but lands in `E` is a finding.

---

# 5. The reduction attack — run FIRST, as a gate

The strongest realistic representation of this proof **without** a realization
object is constructed and executed before the differential implementation is
built out.

Construction: one solver that executes both schemes, with the scheme carried in
`SolverSettings.options` — which is `Mapping[str, Any]` and untyped today, and
which the frozen `Conduction1DSolver` **already uses this way**
(`options={"time_integration": "backward_euler", ...}`, mirrored into
`ProvenanceRecord.metadata`). The null hypothesis's foothold is real and already
in production; it is not a straw.

The reduction is then examined for loss of:

* scientific meaning
* validity meaning
* approximation identity
* provenance
* planner-relevant information
* the ability to select between the two approaches **before** execution

**Stopping condition, preregistered:** if every field of a realization record can
be reconstructed from `(ModelReference, SolverIdentity, SolverSettings,
ProvenanceRecord.metadata)` with nothing duplicated, ambiguous, misplaced or
lost, **the milestone stops there and records the negative result.** The
differential implementation is not built, and MODEL0-R's realization boundary is
reported as weakened or falsified.

No information is invented after the fact to save the boundary.

---

# 6. Predeclared configurations and predicted results

Physical slab held fixed and taken from existing repository constants:
`L = 0.1 m`, `α = 1.2×10⁻⁵ m²/s`, `t_end = 60 s`. Only the discretization varies,
via the frozen public `ConductionSlab.with_discretization`.

`r = α·Δt/Δx² = 0.072 · n_cells² / n_steps` for this slab.

| Config | `n_cells` | `n_steps` | `r` | `R1` implicit | `R2` explicit |
|---|---|---|---|---|---|
| **S** stable | 32 | 160 | **0.4608** | admissible | admissible |
| **U** unstable | 32 | 80 | **0.9216** | admissible | **inadmissible** |

Predictions, recorded so a surprise is visible as a surprise:

1. **Config S:** both realizations agree with the closed-form reference to within
   a stated tolerance, and both satisfy `max|u| ≤ 1` (the discrete maximum
   principle; the initial condition has amplitude exactly 1 and diffusion cannot
   amplify).
2. **Config U:** `R2` violates the maximum principle catastrophically. The
   amplification factor of the worst mode is `|1 − 4r| ≈ 2.686`, so over 80 steps
   round-off-level content is amplified by ≈ `2.7⁸⁰ ≈ 10³⁴`. Predicted
   `max|u| > 10⁶` or non-finite. `R1` at the same configuration stays bounded and
   near the closed form.
3. The arithmetic in this table is confirmed by execution in the first step. If
   it is wrong, the pair loses its adequacy regime and that is reported, not
   patched.
4. **`TEST D1`** (capability-gap selection) passes with the realization contract
   **unchanged**.
5. **`TEST D2`** (stability-based rejection) is predicted to require information
   that has **no typed home** on the current record — the condition is expressible
   only as free text in `assumptions`. If so, the finding is reported with the
   exact minimal change that would fix it; see §8.
6. Two runs of one dual-scheme solver produce **identical**
   `ProvenanceRecord.models` and `ProvenanceRecord.solvers`, so without a
   realization carrier the provenance cannot distinguish two materially
   different computations.

---

# 7. Required executed tests

| | Test | What must hold |
|---|---|---|
| **A** | Same model identity | both realizations resolve to the exact same `ScientificModelDefinition` key |
| **B** | Materially different realization | at least one real semantic distinction that is not solver identity and not arbitrary metadata |
| **C** | Validity distinction | a case where one realization is inadmissible and the other is not, following from real scheme semantics |
| **D** | Planner-relevant distinction | a deterministic pre-execution selection/rejection from inspectable information. No planner is built |
| **E** | Solver substitution | changing a compatible concrete solver does not change the realization's scientific identity |
| **F** | Provenance | the record identifies scientific model, chosen realization and concrete solver without conflating them |
| **G** | Reduction attack | §5, executed; exactly what is duplicated / ambiguous / misplaced / lost is documented |

`TEST E` uses two *different* concrete solvers for one realization. If that
cannot be done honestly, it is documented and **no fake solver is fabricated**.

---

# 8. Change policy

The realization contract is used **unchanged** unless a listed test literally
cannot pass. Preregistered ordering:

1. Implement with `ModelRealizationDefinition` untouched.
2. Where a test cannot pass, record the **concrete consumer** that requires the
   change and the smallest additive change that would satisfy it.
3. `ModelRealizationDefinition` is **not** modified by this milestone. A typed
   applicability envelope on a `DESIGN-FROZEN` record is its own decision with
   its own review; this milestone produces the evidence for it and stops.
4. `ProvenanceRecord` **is** expected to need a realization carrier, because
   `TEST F` requires it and the record currently has `models` and `solvers` and
   no realization. The smallest additive change is one field mirroring the two
   that exist, with a schema version bump and backward reading of the old
   version — exactly the `DATA-BOUNDARY0 §4` pattern. Putting realization
   identity into `ProvenanceRecord.metadata` instead is refused: that is the
   untyped escape hatch this project's own fitness rule counts as a failure.

Not built, at all: equation IR, discretization IR, `FOUNDATION1`, a generic
provider system, a new registry hierarchy, any speculative expansion of
`ModelRealizationDefinition`.

---

# 9. Evidence ceiling, declared before running

`L2 DIFFERENTIATED` requires two **materially different** consumers whose
difference actually exercises the abstraction. §54.1 of the master context
excludes "a second implementation written by the same author, on the same day,
against the same interface."

Recorded before results:

* The `R1` member is executed in part by `Conduction1DSolver`, which is
  **byte-pinned from an earlier commit and unmodifiable** by this milestone.
  That is a stronger independence position than DATA-BOUNDARY0's two-fresh-stores
  case, and the strongest available in-house.
* The `R2` member is nevertheless new code by the same author against the same
  protocol.
* The difference between them is **not** authored: `r ≤ 1/2` is a theorem, and
  the frozen domain recorded the governing quantity before this milestone existed.

**Declared position:** `L2` is claimable only if the executed difference is a
scheme-level fact that neither member's author could have chosen otherwise. If
the distinction turns out to be cosmetic, or reducible to solver identity, the
evidence stays at **`L1 EXERCISED`**. If the pair is materially different but the
information proves to have a correct home outside the realization record, the
result is reported against MODEL0-R regardless of level.

Not claimable at all: `L3 STRESSED`, and any claim about a heterogeneous external
provider — no code Crafty did not write is involved.

---

# 10. Frozen artifacts

`src/engcore/domains/thermal/` is byte-pinned by `THERMAL_FROZEN_FILE_DIGESTS`
and by set-equality over `*.py`. **Not one byte is changed and no file is added
there.** New code lives beside the tree, as `DATA-BOUNDARY0` did. Both digest
checks are re-asserted inside this milestone's own test file.

`run_verification_gate` is welded to `Conduction1DSolver` and cannot be
parameterised without editing a pinned file. A minimal verification against the
closed form is therefore **restated** outside the tree rather than the frozen
gate being changed.

---

# 11. Bulk data

If either realization produces bulk field data it uses the existing
`DATA-BOUNDARY0` path. Arrays are not put into `ScientificResult.values`,
`metadata` or generic `diagnostics`, and the data boundary is not extended.

---

# 12. Scope limits carried forward

Stated now so they are not silently inherited as settled:

* `ModelFormulation.DISCRETE` gets **no consumer** from this milestone and
  remains provisional. It is not used and not "fixed" opportunistically.
* `ModelFormulation.DAE` is likewise unexercised.
* No heterogeneous external provider, no external solver, no scale, no
  concurrency.
* No planner is built. A deterministic selection test is not a planner.
* Cross-domain and coupled consumers are untested.

---

# 13. Stop rule

The milestone ends when the realization boundary is either (A) supported by
differential evidence, (B) shown to require modification, or (C) falsified.

It does not continue into `FOUNDATION1`, does not build a third realization to
increase confidence, and does not start the electro-thermal proof.
