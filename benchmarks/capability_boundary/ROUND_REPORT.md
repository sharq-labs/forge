# Scientific Capability Boundary Audit

## 1. Final decision

**SCIENTIFIC CAPABILITY AUDIT EXPOSED OVERCLAIMS — HARDENING REQUIRED**

Three shipped models reported themselves **applicable** in regimes their own
equations cannot represent. All three are repaired, each with a regression test
written before the fix and shown failing, and each with an executable boundary
guard proven capable of failing. No capability-boundary finding remains open.

The decision is the one the round reserves for exposed overclaims rather than
the certified one, because overclaims were exposed. That they were then fixed
does not retroactively make the starting state certified.

### What this round did not ask

The previous three rounds established that every published record says what its
guarded runtime does, on 88 of 88 material contract dimensions, with 15 of 15
semantic contract mutations caught. **All three defects below sat inside that
agreement.** Record and runtime agreed perfectly about each of them; the tests
passed; the runtime returned a clean number. Contract consistency was the
precondition for finding these, not a defence against them.

## 2. Scope

- **16 shipped models**, 6 systems: `thermal.lumped`, `thermal.conduction1d`,
  `battery.cell`, `electrical.dc`, `electrical.material`, `kinetics.cstr`
- **16 published capability claims** read against the equations behind them
- **86 real physical cases** expanded from those claims and judged one at a time
- **7 adversarial boundary cases** run against the runtime with independent oracles
- **7 planted capability overclaims**, covering all five classes the round names

Every model is in `MODEL_CAPABILITY_SURFACE.json` with status `REVIEWED`. There
is no unexplained omission.

## 3. Capability matrix

`represents` legend: **YES** the equations carry it · **BOUNDED** a declared
condition refuses or UNKNOWNs it · **DISCLOSED** nothing refuses it and the
record says so · **NO** nothing refuses it and the record does not say so.

| Model | Published claim (abbreviated) | Actual represented regime | Match | Finding |
|---|---|---|---|---|
| `thermal.lumped.first_order_capacity` | lumped energy balance `C dT/dt = Q - hA(T-T_amb)` | 0-D, linear, constant C and hA, one convective path | EXACT | — |
| `thermal.conduction1d.linear_diffusion` | 1-D diffusion on a finite slab | 1-D, linear, constant α, fixed sinusoidal IC, Dirichlet 0 | EXACT | — |
| `battery.cell.rint_ocv` | Rint cell with affine OCV | quasi-static, one constant R, affine chord or declared curve | EXACT | — |
| `battery.cell.coulomb_counting` | charge balance | exact integral for constant I, no feedback | EXACT | — |
| `battery.cell.peukert_capacity_derating` | Peukert rate derating | fitted power law, lead-acid provenance, contested for Li-ion | EXACT | — |
| `battery.cell.constant_current_runtime` | time to a declared cutoff | monotone discharge to the higher of two cutoffs | **VALIDITY_LIMIT_MISSING** | **CB-3** |
| `electrical.dc.kcl` | nodal charge balance | exact conservation, lumped, DC | EXACT | — |
| `electrical.dc.resistor_ohm` | `V = I R` | linear, time-invariant, temperature-independent R | EXACT | — |
| `electrical.dc.self_heated_resistor` | `V = I R` with a hot-spot check | one R over the run, single element-to-body drop | EXACT | — |
| `electrical.dc.ideal_voltage_source` | fixed terminal voltage | zero internal impedance, unlimited current | EXACT | — |
| `electrical.dc.ideal_current_source` | fixed current | infinite output impedance, unlimited compliance | EXACT | — |
| `electrical.dc.regulated_voltage_source` | ideal source inside a regulation band | static Thevenin equivalent | EXACT | — |
| `electrical.material.linear_tcr_resistance` | `R(T) = R_ref(1 + α(T-T_ref))` | first-order Taylor about T_ref, one α over 200–450 K | **VALIDITY_LIMIT_MISSING** | **CB-1** |
| `electrical.material.rated_linear_tcr_resistance` | the same, inside material limits | the same, bounded by band, T_max and Debye floor | EXACT | — |
| `kinetics.cstr.nonisothermal_first_order` | non-isothermal CSTR, Arrhenius | 0-D, nonlinear, single liquid phase, constant properties | EXACT | — |
| `kinetics.cstr.nonisothermal_first_order_constant_rate` | the same balances, k constant | 0-D, linear, **claims the same envelope** | **VALIDITY_LIMIT_MISSING** | **CB-2** |

**Real-case counts, as found:** 19 YES · 37 BOUNDED · 27 DISCLOSED · **3 NO**.
All three NO cases were repaired in this round; `unresolved_no_cases` is empty.

## 4. Findings

All three share one shape, and it is worth naming before the detail: **a bound
the repository already computes, or already declares for a sibling record, was
missing from one model's validity domain — and the model reported IN_DOMAIN in
a regime its own equation could not represent.**

---

### CB-1 — `electrical.material.linear_tcr_resistance` reports IN_DOMAIN at a negative resistance

| | |
|---|---|
| **Severity** | MEDIUM |
| **Class** | MISSING_VALIDITY_BOUNDARY |
| **False-confidence class** | **D — normal-looking supported result** on the applicability surface |

**Published capability.** "Resistance of a conductor as a linear function of its
temperature: `R(T) = R_ref (1 + alpha (T - T_ref))`", with a declared validity
range of 200–450 K.

**What the equations encode.** A first-order Taylor expansion of ρ(T) about
T_ref. The record's own coefficient description explicitly admits a negative α
and names the case: *"a semiconductor or an alloy read off a local tangent — and
the band is how far that tangent is claimed to carry."* **This record declares no
band.** Its two conditions were a fixed 200–450 K window and a positive reference
resistance.

**Real case that breaks the claim.** `R_ref = 1000 Ω` at `T_ref = 300 K`,
`α = -0.01 /K`, evaluated at 420 K. Every value sits inside the model's own
declared range and the declaration is exactly the one the record invites.

**Independent evidence.** Two sources, neither the model under test.
*Sign/domain:* every straight line with a non-zero slope crosses zero, and past
the crossing the expression describes a negative conductor, computed here in
arithmetic that does not call the model. *Sibling record:* the rated model
declares this exact bound and states its own reason —

> *"1 + alpha (T - T_ref) > 0. Every straight line with a non-zero slope crosses
> zero; past the crossing the form does not describe a poor conductor but a
> negative one. The bound is the physics of the quantity, not a tolerance."*

**Runtime behaviour as found.** `IN_DOMAIN`, both conditions SATISFIED, at 380 K
(R = 200 Ω), 400 K (**R = 0 Ω**) and 420 K (**R = −200 Ω**).

**False-confidence risk.** Partly mitigated and precisely so. The solver's own
`resistance_strictly_positive` check does report FAIL on the computed number, so
this was never a silent wrong answer. What was wrong is the **applicability**
verdict — the one a caller reads *before* deciding to run. The module's own
comment draws exactly that line: *"the solver's admissibility check catches that
after computing a number. This condition catches it before, which is the
difference between 'was this result checked' and 'was this model applicable'."*

**Source of truth.** The sibling record's declaration, the derivation function
`linear_resistance_ratio()` already present in the module, and the sign of the
quantity itself.

**Why this one and not the other three limits.** The rated sibling adds four
conditions. Three of them — the linearization band, the maximum operating
temperature, the Debye floor — each ask the material for a limit this record
deliberately does not take, and their absence is what makes this the weaker
claim. `linear_resistance_ratio` asks for **nothing**: it is built from the three
inputs this record already requires, and R_ref cancels out of it. That asymmetry
is the whole argument.

**Fix.** A `linear_resistance_ratio > 0` condition on the unrated record,
reserved as a derived quantity and assembled from the stripped context exactly as
the rated assembler does. UNKNOWN unless a temperature is supplied.

**Regression guard.** `test_the_linear_tcr_model_refuses_a_line_that_has_crossed_zero`

---

### CB-2 — `kinetics.cstr...constant_rate` claims an envelope it never checks

| | |
|---|---|
| **Severity** | HIGH |
| **Class** | MISSING_VALIDITY_BOUNDARY |
| **False-confidence class** | **D — normal-looking supported result** |

**Published capability.** "The same well-mixed species and energy balances as the
primary CSTR model, but with a single temperature-independent rate constant." Its
validity domain's own description: *"Same single-phase CSTR envelope as the
primary model."* Its temperature condition declares 250–1000 K; its assumptions
declare a single liquid phase with no boiling.

**What the equations encode.** The same two balances. The primary model bounds
them with `adiabatic_ceiling_temperature ≤ 1000 K` — the hottest state a
declaration can reach, decided before any solve. The constant-rate record does
not state that condition, and does not even *reserve* the quantity, so it can
never read it.

**Real case that breaks the claim.** An ordinary strongly exothermic liquid feed:
ΔH = −500 kJ/mol, C_A0 = C_Af = 1000 mol/m³, ρ = 1000 kg/m³, c_p = 239 J/kg/K,
T_0 = T_f = 350 K, T_c = 300 K. Every one of its four conditions is satisfied.

**Independent evidence — an exact invariant, derived by hand.** For
Z = T + β C_A, adding β times the species balance to the energy balance gives

```
dZ/dt = (Z_f - Z)/τ - γ (T - T_c)
```

**The reaction term cancels identically.** No `k` survives, so the bound holds for
*any* rate law — Arrhenius or constant — and does not depend on either
implementation. With C_A ≥ 0 and C_A ≤ max(C_A0, C_Af):

```
T ≤ Z ≤ max(T_0, T_f, T_c) + β max(C_A0, C_Af) = 2442 K
```

Computed by hand: 2442 K. Computed by the runtime assembler: 2442.05 K. Holding k
constant does not weaken this bound by one step.

**Runtime behaviour as found.** The primary model refuses the declaration on
`adiabatic_ceiling_temperature`. The constant-rate model returns **IN_DOMAIN**,
all four conditions SATISFIED, on the identical declaration — for a reactor whose
contents can reach more than twice its own stated 1000 K ceiling, in a model that
assumes a single liquid phase with no vapour space.

**False-confidence risk.** High and unmitigated. Nothing downstream catches it,
and the record actively tells the reader the envelope is the same as its
sibling's.

**Source of truth.** The invariant derivation, which the primary model's own
record states in full and which this audit re-derived independently.

**Fix.** An `adiabatic_ceiling_temperature ≤ 1000 K` condition on the
constant-rate record, reserved as a derived quantity. The assembler already
computed the value and already placed it in the context this model is assessed
against.

**Regression guard.**
`test_both_cstr_models_refuse_a_declaration_whose_ceiling_leaves_the_envelope`

---

### CB-3 — `battery.cell.constant_current_runtime` reports IN_DOMAIN at a negative runtime

| | |
|---|---|
| **Severity** | MEDIUM |
| **Class** | MISSING_VALIDITY_BOUNDARY |
| **False-confidence class** | **D — normal-looking supported result** |

**Published capability.** "Time to the first of a declared state-of-charge cutoff
and a declared terminal-voltage cutoff, under a constant discharge current:
`t = (z_0 - z_stop) η Q_nom / I`, with z_stop the higher of the two cutoffs."

**What the equations encode.** A discharge at constant current walks z
monotonically **down** — "discharge only" is the record's own first assumption —
so a cutoff declared *above* z_0 is never reached.

**Real case that breaks the claim.** A 2.5 Ah cell at 30% state of charge,
discharged at 1 A, with a declared SOC cutoff of 0.8 and a 3.0 V cutoff. Both
cutoffs sit inside the declared 0.05–0.95 usable window; the current is inside
the declared continuous rating.

**Independent evidence.** The model's own monotonicity assumption, plus the sign
of the quantity: an elapsed time to an event that does not occur is not a number
the model may report. Computed by hand from the published formula: −4500 s.
Computed by the solver: −4500 s.

**Runtime behaviour as found.** `IN_DOMAIN`, all three conditions SATISFIED, and
the solver emits `runtime_to_cutoff = -4500 s` (−1.25 hours).

**Why the existing condition does not cover it.** `cutoff_consistency_margin`
compares the two cutoffs **with each other** and answers which of them stops the
run first. Neither is compared with where the run *starts*. Those are different
questions and only the first was being asked.

**Source of truth — the repository's own stated intent.** The solver comment at
the site of the computation:

> *"Negative when the run already starts below the cutoff, which is a real answer
> to a badly posed question and is reported rather than clipped: **the runtime
> model's own conditions are where that is judged**."*

They did not judge it. The implementation delegated the check to a condition that
did not exist.

**Fix.** A `cutoff_reachability_margin ≥ 0` condition, with the derivation
`z_0 − z_stop` added beside the consistency margin it complements. UNKNOWN unless
the starting state of charge and at least one cutoff are declared.

**Regression guard.**
`test_the_runtime_model_refuses_a_cutoff_above_where_the_discharge_starts`

## 5. Non-findings — examined and proven safe

Reported because an audit that shows only its hits is not showing its
denominator.

**CB-N1 · `thermal.conduction1d.linear_diffusion`, a 25×-wrong coarse solve.**
At 4 cells and 2 steps the midpoint comes back 25 times the true value, checked
against the in-repo closed form `u = sin(πx/L)exp(-απ²t/L²)` — an oracle a test
asserts never imports the solver. Every per-solve check passes. **Not a finding:**
the result contract refuses to dress it up. `attained_levels` is exactly
`{DIMENSIONALLY_VALID}`, `discretization_convergence` and
`analytic_reference_agreement` are both `NOT_RUN` with their reasons, and every
metric's uncertainty is `UNKNOWN` with the reason stated. Backward Euler is also
unconditionally stable, and the *explicit* FTCS realization carries its own von
Neumann `fourier_number` condition. Response class **C**, correctly.

**CB-N2 · `battery.cell.coulomb_counting` past empty.** A discharge giving
z_end = −1.1 returns UNKNOWN with no window declared, and VIOLATED with one. It
never reaches IN_DOMAIN. Response class **B**.

**CB-N3 · `battery.cell.rint_ocv` past the chord.** z_end = −0.1 is refused on
`soc_window_margin`. Response class **A**.

**CB-N4 · `thermal.lumped.first_order_capacity` bare.** A complete, buildable body
with nothing said about its regime leaves 10 of 12 conditions UNKNOWN. The model
is fail-closed: it cannot reach IN_DOMAIN without the caller stating the regime.
Response class **B**. This is the contrast that defines the three findings — all
three defective models could reach IN_DOMAIN from a declaration that was already
complete.

**Examined and judged adequately disclosed rather than bounded:**

- **CSTR boiling.** The 250–1000 K envelope is solvent-independent while the real
  boundary (a boiling point) is solvent-specific, and no boiling point is
  declarable. Both `assumptions` and `exclusions` name boiling and a vapour
  space, and the temperature condition's own text says the constant-property and
  no-phase-change assumptions fail outside the band. Bounding it would require a
  new input — expanding the physics, which the round warns against. Disclosed,
  not hidden; recorded as a limitation in §9.
- **`self_heated_resistor` constant resistance.** An element that heats changes
  resistance, invalidating the circuit solve its dissipation came from. Excluded
  explicitly: *"any change of resistance over the run; one resistance describes
  the element throughout."* Bounding it needs a TCR declaration this record does
  not take — a different model, not a missing condition.
- **`rint_ocv` charging.** Excluded in both `assumptions` and `exclusions`, and
  the record says outright that *no condition here would catch a charge*. A
  disclosed uncaught gap is not the same defect as an undisclosed one.
- **`conduction1d` empty `exclusions`.** The only shipped record with no
  exclusions tuple. Its seven assumptions name every approximation this audit
  identified, so nothing is hidden; the empty field is a record-completeness
  observation for a contract round, not a capability boundary.

## 6. Audit mistakes

Kept visible.

**CBA-1 — a planted defect aimed at a guard that did not cover it.** Plant CBP-7
removes the lumped model's phase-change limit. It was first pointed at
`test_the_lumped_model_cannot_reach_in_domain_without_stating_its_regime`, and
**survived** — correctly, because loosening a bound does not change a condition
that is UNKNOWN for want of a declaration. Investigation showed the plant was
valid and the *guard set* was short: nothing asserted the lumped phase-change
boundary at all. `test_the_lumped_model_refuses_a_body_its_own_run_would_melt`
was added for it, and the plant is now caught. Recorded rather than tidied away,
because the honest reading is that the falsification found a hole in this round's
own guards.

**CBA-2 — an anchor that stopped being unique.** Plants CBP-1 and CBP-2 first
reported `DID_NOT_APPLY`: the three-line anchor they targeted began matching
*both* material records once the unrated one gained the same condition. Re-anchored
on a comment only the unrated record carries. A harness bug, not a finding.

**CBA-3 — a benchmark-preservation check that compared the wrong files, twice.**
The worst mistake of the round, and it reported PASS while being wrong.
`score_hard.py` defaults `--results` to `results_hard.json` **whatever `--cases`
says**, so the battery command documented in `certification/current_core_v1.json`
overwrites the *hard* scorecard and never writes a battery one. Two consequences,
both of which this audit walked into:

1. The "Battery DEV bit-identical" check compared the committed
   `results_battery.json` against a copy of itself that no run had touched. It
   was trivially true and evidence of nothing.
2. The committed `results_battery.json` is an **all-400** scorecard, while the
   documented command scores the **280-case dev split**. The two were never
   comparable, so even a correctly-written comparison against the committed file
   would have failed for the wrong reason.

Caught because a later pass of the same check reported `identical=False` for
Hard DEV with `total_cases: 280` — a hard scorecard cannot have 280 cases, and
that inconsistency is what exposed it. Both benchmarks were then re-scored
properly: same command, pristine `git archive HEAD` checkout versus working
tree, compared summary and every row. Both are bit-identical, and
`build_assurance.py` now documents the trap at the comparison function so the
next round does not repeat it.

The lesson is the round's own: a check that passes is not a check that ran.

**Not an audit mistake, but a judgement worth flagging:** the aluminium framing.
An early draft of CB-1 used a positive-α metal with a badly-placed reference
temperature to cross zero. On checking, a *correctly* referenced metal cannot
cross zero inside 200–450 K — that case is a caller declaration error, not a
model boundary. The finding was re-grounded on the negative-α case the record
itself invites, which needs no mis-declaration at all.

## 7. Existing assurance status

Three layers, deliberately never merged into one number. See
`EXISTING_ASSURANCE.json`.

| Layer | Question it answers | Result |
|---|---|---|
| Certified executable-code mutation | are the executable branches covered by tests that fail when they change? | **79/79 RED, CONTROL GREEN** — re-run this round |
| Contract guard | does every record say what its guarded runtime does? | **15/15 semantic contract mutants caught, CONTROL GREEN** — re-run this round |
| Capability boundary *(new)* | is that agreed behaviour scientifically valid in this regime? | 3 defects found and repaired; **7/7 planted overclaims caught, CONTROL GREEN** |

**Executable scientific code changed**, in four domain modules, so nothing was
assumed preserved:

- `src/engcore/domains/battery/context.py`, `battery/models.py`,
  `electrical/material.py`, `kinetics/cstr/alternatives.py`

What changed in them is three validity conditions and one derivation. **No
equation, no coefficient and no numerical method was altered**, which is why:

- **FAST**: 3836 passed, 3 skipped
- **Hard DEV**: 1400 cases, scorecard **bit-identical**, rows included
- **Battery DEV** (dev split): 280 cases, scorecard **bit-identical**, rows included
- **Certified scientific-core digest**: `82558f5b…d97d2507`, unchanged (the four
  changed modules are under `domains/`, outside `src/engcore/scientific/**`)

**How those two comparisons were made**, because the obvious way is wrong and
this audit got it wrong first (see CBA-3). Each benchmark was scored **twice by
this round with the same command**: once on a pristine `git archive HEAD`
checkout and once on the working tree. The scorecards committed in the
repository are not used as baselines.

1680 benchmark cases, zero verdict changes, every row equal. That is the
evidence behind the judgement in §9 that narrowing the unrated TCR record did
not re-judge anything that cited it.

**Earlier rounds' result artifacts are not rewritten.**
`benchmarks/contract_guard/CONTRACT_GUARD_MATRIX.json` still records the 64
conditions and 353 probes that existed when that round ran; recomputed today it
reads 67 and 368, with the same 88/88 guarded dimensions. The artifact is left as
that round's result rather than edited to match this one, and the delta is
recorded here instead.

**One change was made to Contract Guard machinery** (not to a result artifact):
`benchmarks/contract_guard/guard/prerequisites.py` now merges claim-map
supplements registered by later rounds. That guard fired — correctly — the moment
this round added a condition the Contract Integrity claim map did not cover, which
is exactly what it was built for. The mapping is supplied in this round's own
directory rather than by editing the earlier round's file, and it is exercised by
a guard here rather than left as an unexecuted entry.

## 8. Exact certification scope

This round certifies that **every shipped capability claim was read against the
equations that implement it**, that the regimes found inside the wording and
outside the equations are now refused or explicitly disclosed, and that each
boundary carries a guard proven to fail when the boundary is removed.

It does **not** certify:

- full scientific correctness of any model
- numerical accuracy of any result
- the validity of the underlying physics
- fitness for any particular use
- that no capability boundary remains undiscovered

Five statements that do **not** follow from anything in this report, and are
rejected explicitly:

- record and runtime agree, **therefore** scientifically correct — all three
  defects here sat inside perfect agreement
- the tests pass, **therefore** the claim is scientifically valid — the tests
  passed on all three
- the model returns a number, **therefore** the model applies — the three
  findings are precisely models returning clean numbers where they do not apply
- the scientific digest is unchanged, **therefore** the capability claim is valid
  — the digest was unchanged throughout, including while all three defects were
  live
- the out-of-regime input is physically valid, **therefore** the model must
  support it — a physically valid declaration the equations cannot carry is a
  declaration the model must **refuse**, which is what all three fixes do

The Blind V2, Contract Integrity and Contract Guard certifications stand exactly
as published, with their own scopes and their own limits, and none of them is
extended by this one.

## 9. Remaining limitations

1. **Solvent-independent CSTR envelope.** 250–1000 K is a fixed band for every
   fluid, while the physical boundary is a boiling point. Disclosed in
   assumptions and exclusions; not enforceable without a new declared input.
2. **Self-heating feedback on resistance is disclosed, not bounded**, in both
   `self_heated_resistor` and the unrated TCR record. Each excludes it in words;
   neither can measure it without a declaration it does not take.
3. **The unrated TCR record still has no material band.** CB-1 fixed the
   positivity bound because it needs nothing declared. How far one α carries is a
   property of the material, and that remains the rated sibling's claim.
4. **Adversarial cases are constructed, not exhaustive.** Seven boundary cases
   across sixteen models is a sample chosen by reading equations. A regime nobody
   thought to construct is a regime nobody checked, and the three findings were
   each found by one specific construction.
5. **`version` was not bumped on the three narrowed records.** Judgement call,
   with reasoning: each change refuses only declarations where the model's own
   output had stopped being the quantity it claims to compute, all three
   conditions are UNKNOWN unless their inputs are supplied, and 1680 benchmark
   cases changed no verdict. An external consumer holding a 0.1.0 result whose
   multiplier was non-positive, whose ceiling exceeded the envelope, or whose
   runtime was negative would now get a refusal instead. That is the intended
   effect, and it is disclosed here rather than hidden behind an unchanged
   version string.
6. **Two systems carry the boundary evidence for their families.** `thermal.lumped`
   and the primary CSTR are the models with rich condition sets; several others
   have one or two conditions and rest more heavily on disclosure.
