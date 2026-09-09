# Scientific bound register

Every applicability bound Forge currently enforces, what kind of claim it is,
and whether it is sourced.

**The inventory is read off the model records, not grepped.** Walking `engcore`
for `ScientificModelDefinition` objects finds **16 models carrying 64
conditions**. A previous round reported "15 bounds"; that figure counted only
the thermal and material subset it had audited, and is superseded.

---

## 1. The classification that reframes the count

Not every threshold is a scientific claim. Sorting the 64 by *what kind of
statement the number is* gives:

| kind | count | needs a source? |
|---|---|---|
| **definitional** — a utilisation or margin bounded at 0 or 1 | **32** | **no** |
| **positivity / physical domain** — `x > 0`, `x >= 0` | **18** | **no** |
| **substantive scientific threshold** | **11** (10 distinct names) | **yes** |

### Why 32 need no source

A "utilisation" is defined as *value ÷ the limit the caller declared*, so
`utilisation <= 1` **is** the statement "at or under the declared limit". The
number 1 is a tautology given the definition; the scientific content lives
entirely in the caller's declared limit, which Forge does not supply and does
not vouch for. `operating_temperature_utilization = T/T_max`,
`continuous_c_rate_utilization = |C|/C_continuous`,
`dissipated_power_utilization`, `melting_temperature_utilization` and 28 others
are all of this shape.

`soc_window_margin >= 0` and `cutoff_consistency_margin >= 0` are the same idea
with the sign reversed: a margin is negative exactly when the trajectory left
the declared window.

This is a real finding and it cuts the sourcing problem by a factor of six.
**It does not make those 32 verified** — it relocates the question from Forge to
the caller, and Forge's report says which limit it used.

### Why 18 need no source

`resistance > 0`, `nominal_capacity > 0`, `k0 > 0`, `alpha > 0`,
`heat_capacity > 0` and the rest state the physical domain of the quantity.
A negative resistance or a negative absolute capacity is not a value the
quantity can take.

Two of these are worth naming because they **refuse a mathematically clean
limit**: `alpha > 0` (conduction) and `internal_resistance > 0` (Rint). In both
cases the limit removes the model's entire content — with no diffusivity
nothing diffuses, with no internal resistance the Rint model says only what the
OCV curve already says — so Forge refuses rather than returning the degenerate
answer. `tests/oracles/` pins both refusals.

---

## 2. The 11 substantive thresholds

| ID | domain | condition | value | inclusivity | source class | reference | hard/soft | status |
|---|---|---|---|---|---|---|---|---|
| **B-BIOT** | thermal | `biot_number` | ≤ 0.1 | inclusive | `PRIMARY_LITERATURE_DERIVED` | Incropera, DeWitt, Bergman & Lavine 6th ed. (2007) §5.1 | **SOFT** | **VERIFIED (as an approximation criterion)** |
| **B-FOURIER** | thermal | `internal_fourier_number` | ≥ 0.2 | inclusive | `PRIMARY_LITERATURE_DERIVED` | Incropera 6th ed. §5.5, one-term series validity | **SOFT** | **VERIFIED (as an approximation criterion)** |
| **B-GEOM** | thermal | `geometry_route_ratio` | [1/3, 3] | inclusive both | `ANALYTICALLY_DERIVED` | derived from the two standard characteristic-length conventions; see §3 | hard, given the two conventions | **VERIFIED** |
| **B-CONV-AGREE** | thermal | `convection_conductance_agreement_ratio` | [0.5, 2.0] | inclusive both | `ANALYTICALLY_DERIVED` (scoped) | orientation ambiguity: Incropera §9.6.3 gives 0.54 vs 0.27 Ra^¼ for the two horizontal-plate orientations — a factor of two | soft | **VERIFIED (as a scope bound)** |
| **B-RAD** | thermal | `radiation_to_convection_ratio` | ≤ 0.1 | inclusive | **`INTERNAL_POLICY`** | none found | soft | **POLICY** — see §4 |
| **B-DEBYE** | material | `reduced_debye_temperature` | ≥ 1/3 | inclusive | `INTERNAL_POLICY` (regime is standard, the fraction is not) | Bloch–Grüneisen linear regime; the literature quotes θ_D/2, θ_D/3 and θ_D/5 | soft | **POLICY** |
| **B-DEBYE-REF** | material | `reference_reduced_debye_temperature` | ≥ 1/5 | inclusive | `EMPIRICALLY_CHARACTERIZED` | Kittel 8th ed. Ch. 5 Tab. 1 — beryllium θ_D = 1440 K refuses a 1/3 floor at a conventional 293.15 K reference | soft | **VERIFIED against one material** |
| **B-POL** | battery | `polarization_unmodelled_fraction` | ≤ 0.05 | inclusive | **`INTERNAL_POLICY`** | none found; a 5 % neglect allowance | soft | **POLICY** |
| **B-ETA** | battery | `coulombic_efficiency` | (0, 1] | upper inclusive | `ANALYTICALLY_DERIVED` | charge conservation: a cell cannot return more charge than it accepted | **hard** | **VERIFIED** |
| **B-TCR-RANGE** | material | `temperature` | [200, 450] K | inclusive both | `INTERNAL_POLICY` | repository scope for the linear TCR form | scope | **POLICY** |
| **B-CSTR-RANGE** | kinetics | `temperature`, `adiabatic_ceiling_temperature` | [250, 1000] K | inclusive both | `INTERNAL_POLICY` | repository scope | scope | **POLICY** |
| **B-ELEC-LEN** | electrical | `lumped_electrical_length` | ≤ 0.1 | inclusive | `STANDARD_DERIVED` (conventional) | the electrically-small criterion, L < λ/10 | soft | **VERIFIED, but see §5** |

**Tally: 5 verified, 5 policy, 1 verified-with-scope, 0 conflicted, 0
unsourced-and-unclassified.**

---

## 3. B-GEOM, derived

Two conventions define a characteristic length and they disagree by a
geometry-dependent factor:

| body | `L_c` (conduction path) | `V/A_s` | ratio |
|---|---|---|---|
| plane wall, half-thickness `L` | `L` | `L` | 1 |
| long cylinder, radius `r_o` | `r_o` | `r_o/2` | 2 |
| sphere, radius `r_o` | `r_o` | `r_o/3` | **3** |

So across the standard shapes the ratio spans exactly 1 to 3, and the sphere
sets the bound. A declared pair disagreeing by more than 3 cannot be reconciled
by any choice of shape convention — which is precisely what the condition
claims. **The bound is derived, not chosen**, and the inclusivity matters: a
body at exactly 3× *is* the sphere, so admitting the endpoint is correct rather
than a rounding accident.

---

## 4. B-RAD, and why U01881 stays unresolved

`radiation_to_convection_ratio = h_r / h`, with
`h_r = εσ(T_s+T_sur)(T_s²+T_sur²)` — the exact linearised radiation
coefficient, independently verified by `ORA-RAD-LINEARIZATION`.

**The quantity is right. The threshold is not sourced.** `h_r/h ≤ 0.1` is a
10 %-neglect allowance: it says the radiative path may be omitted from a
convection-only lumped model while it carries under a tenth of the convective
path. That is a reasonable engineering position and **no primary source was
found that states this criterion at this value**, so it is classified
`INTERNAL_POLICY` rather than given a citation it does not have.

What that costs, concretely:

> `U01881` computes `h_r/h = 0.109` — **9 % past the bound**. Whether that case
> is scientifically outside the lumped model's applicability depends entirely on
> whether the bound is 0.1, or 0.12, or 0.2. **An oracle can confirm the ratio
> and cannot confirm the bound**, so `U01881` remains under review.

The other five cases in that group sit at 2.6× to 20× the bound, where no
plausible reading of a neglect threshold admits them; those are resolved.
`U01881` is the one the unsourced threshold actually decides, and it is the
only one left open.

**The bound was not moved.** Widening it to resolve `U01881` would be tuning a
scientific threshold to change a benchmark outcome.

---

## 5. B-ELEC-LEN never binds

`lumped_electrical_length = L/λ` with `λ = c/f`. `KCL_MODEL` is a steady-state
DC model with `f = 0` in its assumptions, so `λ` is unbounded and the ratio is
**exactly zero for a circuit of any size**. The condition is evaluated and
always passes.

This is deliberate — the assessment reads a quantity and compares it with a
declared bound rather than hard-coding IN_DOMAIN — and it means the bound is
**latent**: correct, conventional, and incapable of affecting any current
verdict. It is listed here so a future AC model does not inherit it silently.

---

## 6. What "SOFT" means, and why two entries carry it

`B-BIOT` and `B-FOURIER` are the two thresholds most likely to be misread as
physical law. Neither is.

* **Bi ≤ 0.1** is an *approximation criterion*: it marks where neglecting the
  internal temperature gradient introduces an error small enough to accept. It
  is not a transition, nothing changes at 0.1, and the literature states it with
  an associated error rather than as a boundary.
* **Fo ≥ 0.2** likewise marks where the transient conduction series is
  adequately represented by its first term.

Both are recorded as `SOFT_SCIENTIFIC_BOUND`. Forge's verdicts treat them as
sharp, which is the right engineering behaviour for a screen and is **not** a
claim that physics changes at the number. The `internal_fourier_number`
adjudication of 2026-09-09 already reflects this: under the floor the criterion
reports `INSUFFICIENT_EVIDENCE` with reason `conservative_screen`, not
`NOT_SUPPORTED` — a gap, not a finding against the design.

---

## 7. Numerical tolerances

Four declared threshold gates exist, each carrying its own `basis` string in
the source.

| gate | values | class | margin observed |
|---|---|---|---|
| `electrical.dc.linear_residual` | atol/rtol 1e-9 | `NUMERICALLY_CHARACTERIZED` — round-off scale on a direct factorisation | residuals exactly **0**; margin infinite |
| `electrical.dc.cross_solver` | rel 1e-9 | `NUMERICALLY_CHARACTERIZED`, preregistered | — |
| `kinetics.cstr.verification_gate` | 1e-9, 1e-9, 1e-6 | `EMPIRICAL` — **self-labelled** "declared after exploratory feasibility analysis, not preregistered" | — |
| `thermal.conduction1d.refinement` | analytic_rel_tol 1e-3, min_contraction 1.5 | `EMPIRICAL` — **self-labelled** "declared after exploratory analysis that had already seen 2.0–2.3" | linear residual 1e-16 vs 1e-10, margin **1e5×** |

Plus `IntegrationSettings` (BDF, rtol = atol = 1e-8) — `SOLVER_CHARACTERIZED` —
and the caller-declared electro-thermal coupling tolerance.

**Sensitivity, measured.** Five representative cases were run at 0.1×, 1× and
10× the coupling tolerance — a 100-fold range:

| case | spread in `final_temperature` | verdict |
|---|---|---|
| S00013 | 3.6e-11 relative | unchanged |
| U01001 | 3.6e-10 relative | unchanged |
| U00002 | 3.3e-10 relative | unchanged |
| S00581 | 2.9e-09 relative | unchanged |
| U00204 | 1.2e-08 relative | unchanged |

**No verdict moved.** A margin metric initially flagged the coupling as running
at 1.01× its bound; that was an artefact of measuring a *convergence criterion*
against itself — an iteration that stops when the change drops below tolerance
necessarily finishes just under it. The converged value is what matters, and on
a contracting map it is insensitive. Recorded because the mis-reading is an easy
one to publish.

**No tolerance was changed.**

---

## 8. Verification coverage

Coverage of verification, not accuracy.

| metric | value |
|---|---|
| conditions enforced | **64** across 16 models |
| needing no source (definitional + positivity) | **50** (78 %) |
| substantive thresholds | **11** |
| substantive thresholds sourced or derived | **6 of 11 (55 %)** |
| substantive thresholds classified `INTERNAL_POLICY` | **5 of 11 (45 %)** |
| conflicted | **0** |
| unsourced-and-unclassified | **0** — every bound now has a class |
| trust-affecting tolerance gates | 4, all with a written basis; 2 self-labelled empirical |
| tolerances demonstrated insensitive | coupling, over a 100× range |

Prior rounds reported "4 of 15 sourced (27 %)". That figure counted a different
population against a different denominator; on the full inventory the
comparable statement is **6 of 11 substantive thresholds sourced or derived,
with the remaining 5 explicitly classified as policy rather than left
unlabelled.**

---

## 9. What is still not established

* **B-RAD and B-POL are neglect allowances with no located source.** Both
  decide verdicts. `U01881` is the case that turns on B-RAD.
* **B-DEBYE's fraction is convention.** The regime is standard; θ_D/3 versus
  θ_D/5 is a choice, and Forge already uses both in different places for
  reasons it documents.
* **The 32 definitional bounds relocate trust to the caller.** Forge verifies
  that a declared limit was respected; nothing verifies the declared limit.
  That is the correct division of responsibility and it should not be read as
  Forge having checked a rating.
* **No bound is verified against experiment.** Every entry above is a
  definition, a derivation, a citation, or a policy.
