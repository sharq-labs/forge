# Scientific Truth & Numerical Oracle Audit

## 1. Final decision

**SCIENTIFIC MODEL TRUTH VALIDATED**

Every shipped equation was re-derived from the physics, checked dimensionally
term by term, and compared against mathematics written outside the code — an
independently coded integrator, closed forms derived here, an external circuit
simulator, exact conservation laws, 50-digit arithmetic, and convergence orders
the schemes themselves justify. **255 oracle-backed checks across all 16 models,
zero disagreements.** No equation defect, implementation defect, unit defect,
sign defect, conservation defect or numerical-method defect was found.

The round found **five defects in its own oracles** instead. Every one is
recorded in §12, because an audit that reports only the subject's mistakes and
not its own is not reporting its reliability.

### What "validated" does and does not mean here

The previous four rounds established that records match runtimes, that the
guarded behaviour is claimed for the right regimes, and that the code is
covered by tests that fail when it changes. **None of that is evidence about
the mathematics**, and this round assumed none of it. The question asked was
only ever: *would an independent scientist, using independent mathematics,
obtain the same number?*

## 2. Scope

| | |
|---|---|
| Models | **16**, all reviewed, all with oracle-backed rows of their own |
| Domains | 6: `thermal.lumped`, `thermal.conduction1d`, `battery.cell`, `electrical.dc`, `electrical.material`, `kinetics.cstr` |
| Equations derived independently | **16**, in `EQUATION_LEDGER.json` |
| Oracle-backed checks | **255**, in `REFERENCE_CASES.json` |
| Randomized draws inside the declared domain | **730 admitted, 265 rejected** |
| Planted scientific defects | **9**, all detected |

Six independent oracle modules were written for this round. **None imports
`engcore`** — verified mechanically, not asserted.

## 3. Model equation matrix

| Model | Equation as implemented | Class | Method | Oracle | Rows |
|---|---|---|---|---|---|
| `thermal.lumped.first_order_capacity` | `C dT/dt = Q - hA(T-T_amb)`, solved in closed form | ODE | analytic | RK4 integration + first law | 32/32 |
| `thermal.conduction1d.linear_diffusion` | `du/dt = α u_xx` | PDE | backward Euler + central differences | closed form + explicit FTCS | 11/11 |
| `battery.cell.coulomb_counting` | `z = z₀ − It/(ηQ)` | ODE, exact integral | none | charge conservation in coulombs | 13/13 |
| `battery.cell.rint_ocv` | `V = OCV(z) − IR`, `Q = I²R` | algebraic | none | KVL + Joule's law | 23/23 |
| `battery.cell.constant_current_runtime` | `t = (z₀−z_stop)ηQ/I` | algebraic | none | charge between states | 2/2 |
| `battery.cell.peukert_capacity_derating` | `Q_eff = Q(I_ref/I)^(k−1)` | empirical | none | re-derived from `I^k t = const` | 4/4 |
| `electrical.dc.kcl` | `Σ I_out = 0` | linear system | MNA | **ngspice** + incidence-matrix solve | 44/44 |
| `electrical.dc.resistor_ohm` | `V = IR`, `P = I²R` | algebraic | MNA | **ngspice** + Ohm/Joule | 54/54 |
| `electrical.dc.ideal_voltage_source` | `v₊ − v₋ = V_src` | linear system | MNA | **ngspice** | 3/3 |
| `electrical.dc.ideal_current_source` | imposed `I`, any `V` | linear system | MNA | **ngspice** | 3/3 |
| `electrical.dc.regulated_voltage_source` | same relation, banded | linear system | MNA | shown identical to the ideal relation | 1/1 |
| `electrical.dc.self_heated_resistor` | `V = IR` + `T_body + P·R_th` | algebraic | MNA | 1-D conduction, derived here | 1/1 |
| `electrical.material.linear_tcr_resistance` | `R = R_ref(1+α(T−T_ref))` | algebraic | none | **mpmath, 50 digits** | 21/21 |
| `electrical.material.rated_linear_tcr_resistance` | the same expression | algebraic | none | mpmath; sharing verified at 4 temperatures | 4/4 |
| `kinetics.cstr.nonisothermal_first_order` | coupled species + energy, Arrhenius | ODE system, stiff | implicit + analytic Jacobian | RK4 + root finding + exact invariant | 36/36 |
| `kinetics.cstr.nonisothermal_first_order_constant_rate` | the same, `k` constant | ODE system | same kernel at `E=0` | RK4 with constant `k`; the `E=0` reduction verified exactly | 3/3 |

**Five models implement an equation another model already uses.** That is a
claim, so it was verified rather than used as a bookkeeping excuse: each was
run and shown to produce the same numbers as the model whose equation it
shares — including `exp(−0/(RT)) == 1.0` exactly, which is what makes the
constant-rate CSTR reachable through the Arrhenius kernel at all.

## 4. Dimensional analysis

**16/16 DIMENSIONALLY_VALID**, worked term by term in `EQUATION_LEDGER.json`.
A passing numerical test was never accepted as evidence — a wrong power of a
unit can match a reference exactly at the one point the reference was built at.

The checks that would have caught a real unit error:

- `τ = C/hA = (J/K)/(W/K) = s`, and `t/τ` dimensionless so `exp()` has an argument
- `β = (−ΔH)/(ρc_p) = m³K/mol`, so `βkC_A = K/s`; `γ = UA/(Vρc_p) = 1/s`
- `E/(RT)` dimensionless — required of any exponent
- `α(T−T_ref)` dimensionless, so the TCR bracket is a pure number. An `α` carrying Ω/K would make the bracket inhomogeneous: one term a number, the other an ohm-kelvin. **This is the classic TCR unit error and it is not present.**
- `It/(ηQ_nom)` needs the hours conversion; without it the term is 3600× too large. The Core converts through its unit system and this audit's oracle divides by an explicit 3600, so either being wrong is loud. (Plant STP-4 confirms it: a ×1000 slip is caught.)

## 5. Independent oracle strategy

| Model family | Oracle | Type | Why independent |
|---|---|---|---|
| lumped thermal | RK4 integration of the ODE | E (alternate numerical method) | production exponentiates, the oracle marches; no shared algebra |
| conduction1d | closed form **and** explicit FTCS | A + E | one exact, one a different discretization from backward Euler |
| battery | charge conservation, KVL, Joule | C + B | written from the laws; converts hours with an explicit 3600 the Core deliberately does not use |
| electrical DC | **ngspice 42** + incidence-matrix nodal solve | **F** + D | ngspice shares no line of code with this repository; the netlist is emitted by this audit, not by the repo's bridge |
| material TCR | mpmath at 50 digits | G | different arithmetic entirely |
| CSTR | RK4, steady-state root finding, exact invariant | E + B + C | explicit vs implicit; algebra vs integration; an invariant whose derivation cancels the rate law |

The CSTR invariant deserves its own note. Adding `β ×` the species balance to
the energy balance gives `dZ/dt = a(Z_f − Z) − γ(T − T_c)` for `Z = T + βC_A` —
**the reaction term cancels identically**. That makes it an oracle over the
*coupling* that holds for any rate law, which is precisely why plant STP-5 (3%
of the reactant not removed from the species balance) is caught by it.

## 6. Reference-case results

**255 rows, 0 disagreements.**

| Check | Clean |
|---|---|
| reference_case | 138/138 |
| conservation | 36/36 |
| limit | 20/20 |
| external_oracle (ngspice) | 14/14 |
| high_precision (50-digit) | 12/12 |
| cross_oracle | 9/9 |
| sign | 9/9 |
| cancellation | 8/8 |
| monotonicity | 7/7 |
| convergence | 2/2 |

**Every tolerance is justified rather than chosen.** Two are worth stating
because they are the difference between a real check and a comfortable one:

- The diffusion tolerance is the scheme's **own predicted error**,
  `λ²t·dt/2 + λt(π dx/L)²/12`, derived from the discretization. Observed over
  predicted is **1.00** on all three reference cases and **1.0003** across 40
  random slabs. A solver making a *different* error of the same size passes a
  tolerance and fails this.
- The material tolerance is the **condition number** `κ = |R_ref|/|R|` times
  machine epsilon. The deliberately ill-conditioned case has κ = 5×10⁴ and an
  error of 1.6×10⁻¹¹ — exactly `κ·ε`, i.e. as good as double precision allows.

## 7. Conservation results

**36/36 residuals at round-off.** Measured explicitly; never inferred from the
equations looking right.

| Law | Where | Residual |
|---|---|---|
| Energy (first law) | lumped thermal, closed-form integral of the loss term | ≤ 1e-10 relative |
| Charge | coulomb counting, in coulombs | ≤ 1e-12 relative, or below the cancellation floor |
| Charge (KCL) | every node of every DC circuit | worst 5.8e-13 relative over 60 random networks |
| Energy (Tellegen) | DC power balance, plus the Core's source total recomputed from potentials | ≤ 1e-10 relative |
| Energy/species coupling | the CSTR invariant ceiling | never crossed, worst overshoot 0.0 K |

## 8. Limiting behaviour

**20/20 LIMIT_CORRECT**, plus 7/7 monotonicity invariants and 9/9 sign cases.

`t→0`, `t→∞`, `Q→0`, `hA→0` (adiabatic ramp `Q/C`), `hA→∞` (clamped to ambient),
`α→0` (frozen profile), `I→0` (`V→OCV`), `R→0`, `R→∞`, `T→T_ref`, `α→0` (flat
resistor), `k→0` (washout to the feed, temperature to the derived mean
`(aT_f+γT_c)/(a+γ)`), `UA→0` (adiabatic), `E→0` (Arrhenius factor exactly 1).

Three limits are **refused at construction** rather than evaluated, and the
refusal is the right answer: zero duration, zero and negative discharge current,
and an exactly flat OCV chord (which has no invertible relation to charge).

## 9. Numerical convergence

| Refined | Observed order | Expected | Source of the expectation |
|---|---|---|---|
| time step | **1.0005, 0.9984, 0.9955, 0.9903** | 1 | backward Euler is first-order in dt |
| mesh | **2.0057, 2.0014, 2.0003** | 2 | second-order central differences |

The spatial ladder's **raw** orders decay 1.975 → 1.885 → 1.611, which looks
like a failing solver and is not. Refining the mesh while the time step is held
fixed measures the *sum* of a shrinking spatial error and a constant
first-order time error. With that floor subtracted the spatial order is exactly
two. This was audit defect **STA-5**; the report shows both columns so a reader
can see the correction rather than take it.

## 10. Solver independence

**No pair in the repository is fully independent — all five are PARTIAL — and
none is coupled.** Traced from the module import graph parsed out of the AST,
because a claim of independence written in a comment is exactly what this round
exists to disbelieve.

| Pair | Verdict | What is shared |
|---|---|---|
| conduction1d solver ↔ its closed-form reference | PARTIAL | problem statement and exception types only; the reference's whole closure is 3 modules and the solver is not among them |
| conduction1d solver ↔ explicit-scheme realization | PARTIAL | the slab declaration; the discretizations differ |
| DC solver ↔ the repository's ngspice bridge | PARTIAL | the circuit declaration, and **two metric-name strings** — `NODE_VOLTAGE_METRIC` and `SOURCE_CURRENT_METRIC`, both plain values, not callables. It borrows names, not numbers |
| lumped thermal ↔ material TCR | PARTIAL | namespace and repair machinery; no physics |
| CSTR solver ↔ CSTR validity context | PARTIAL | the context, which carries derived quantities |

**What PARTIAL costs, stated plainly:** every pair would agree about a
*mis-declared problem*, because they share the declaration objects. That bounds
what the repository's internal agreement can prove, and it is why this round's
oracles take raw tuples and build their own netlists, their own initial
conditions and their own unit conversions. This audit's six oracles are the only
fully independent routes in evidence, and a test asserts they stay that way.

## 11. False-agreement cases

**Zero.** `FALSE_AGREEMENT_CASES.json` is empty, and that is the round's central
result — it is the one gate that could not be passed by any amount of internal
consistency.

The search was not passive. It ran an external simulator on 66 circuits, 50-digit
arithmetic on 8 conductor states, an exact invariant on every reactor, an
independently coded integrator against every closed form, and 730 randomized
draws inside the declared domains. Every one of those could have disagreed with
an implementation whose records, tests and validity conditions were already
proven consistent by earlier rounds. None did.

## 12. Audit mistakes

Five, all found by the audit's own refinement discipline, all recorded.

**STA-1 — an under-resolved oracle manufactured a 3.3% CSTR disagreement.**
The peak temperature occurs at t ≈ 0.12 s. My first RK4 ran at h = 10⁻³ s and
reported 524.6 K against the Core's 541.7 K. Refining to h = 10⁻⁶ s converged to
**541.713**, matching the Core to 5×10⁻⁸. The oracle was wrong, not the Core.
This is why every numerical oracle in the round now carries its own refinement
evidence.

**STA-2 — a relative-residual criterion on catastrophic cancellation.** The
charge balance at 10⁻⁹ A reported a residual of 8×10⁻⁸ relative. `z₀ − z_end` is
a difference of nearly equal doubles; its absolute error is `ulp(z₀)` however
exact both numbers are. Fixed with a floating-point floor derived from that ulp,
not with a looser tolerance.

**STA-3 — a power-balance oracle that double-counted.** I added current-source
power to `total_source_delivered_power`, which already includes it — verified by
a circuit containing *only* a current source whose total is non-zero. The Core's
balance was exact throughout.

**STA-4 — an import tracer that resolved relative imports wrongly.** Using
`n − level + 1` instead of `n − level` found no first-party imports anywhere,
which made **all five independence pairs look trivially independent**. This is
the most dangerous of the five: it produced a clean result by seeing nothing.

**STA-5 — a convergence ladder contaminated by the variable it held fixed.**
Described in §9.

A sixth near-miss, not a defect: two property generators initially rejected
**zero** draws, meaning their domain constraints were not binding and the
property was being checked on an unconstrained set. Both were widened until the
constraints bit (diffusion now rejects 190 of 230, CSTR 10 of 40), and the
guard suite asserts every generator rejects something.

**The Core produced no defect in this round. The audit produced five.** That
ratio is worth stating rather than smoothing over.

## 13. Fixes

**None. No file under `src/` or `tests/` was changed.** The certified
scientific-core digest is `82558f5b…d97d2507`, byte-identical to the certified
value, and `git status` over `src/` and `tests/` is empty.

Where the round found something wrong, the wrong thing was in
`benchmarks/scientific_truth/` and was fixed there.

## 14. Regression guards

`benchmarks/scientific_truth/tests/test_scientific_truth.py` — **25 tests**.
Every assertion is against something computed outside the code under test.
None would notice a record change; none can be satisfied by making the
implementation agree with itself.

Guards that matter most:

- `test_an_endothermic_reaction_cools_the_reactor` — β changes sign with ΔH. A
  model with it backwards heats on an endotherm and returns entirely plausible
  temperatures while doing so. No record, no validity condition and no
  dimensional check would notice.
- `test_the_predicted_discretization_error_is_what_the_solver_actually_makes` —
  stronger than a tolerance: the solver must make *the scheme's* error, not
  merely a small one.
- `test_the_dc_solver_agrees_with_ngspice` — the external oracle.
- `test_this_audits_oracles_do_not_import_the_code_they_judge` — the audit
  policing itself, and the check that plant STP-9 exists to trip.
- `test_randomized_cases_...` — fails if a generator rejects nothing.

## 15. Auditor falsification

**9 planted scientific defects, 9 detected, control GREEN.** Each is made in a
temporary copy and discarded with it.

| ID | Class | Planted | Detected by |
|---|---|---|---|
| STP-1 | SIGN | `β` loses its minus sign: exotherms cool, endotherms heat | CSTR sign checks |
| STP-2 | SIGN | the approach to steady state is reflected | lumped reference cases |
| STP-3 | COEFFICIENT | Joule's law becomes `IR²` instead of `I²R` | battery reference cases |
| STP-4 | UNIT | the ampere-hour conversion out by ×1000 | charge conservation |
| STP-5 | CONSERVATION | 3% of reactant consumed but not removed | the CSTR invariant |
| STP-6 | NUMERICAL | the Fourier number carries a 2% error — still converges, to the wrong answer | predicted-vs-observed error |
| STP-7 | COEFFICIENT | a TCR error of **one part in ten million** | 50-digit arithmetic |
| STP-8 | TEST_ORACLE | **this audit's own** closed form given the wrong eigenvalue | its second, independent FTCS oracle |
| STP-9 | INDEPENDENCE | **this audit's own** oracle rewritten to import the solver it checks | the independence tracer |

Two plants attack the audit rather than the Core. An audit that cannot catch
its own oracles going wrong has no business reporting that the Core is right —
and this one had already made five such mistakes.

## 16. Previous assurance preserved

Four layers, never combined into one number.

| Layer | Question | Status |
|---|---|---|
| A. executable-code mutation | are the branches covered by tests that fail when they change? | **79/79 RED, CONTROL GREEN** — unchanged, not rerun: no file under `src/` changed |
| B. contract integrity / guard | does every record say what its runtime does? | **36 guard tests pass**; 88/88 dimensions |
| C. capability boundary | is that behaviour claimed for the right regimes? | guards pass |
| D. scientific truth *(this round)* | **are the equations themselves right?** | 255/255 checks, 9/9 plants caught |

- **FAST**: 3836 passed, 3 skipped
- **Hard DEV / Battery DEV**: not rerun, and the reason is stated rather than assumed — **no executable scientific code changed**, so both scorecards are evaluating byte-identical code. `git diff HEAD -- src tests` is empty and the core digest matches.
- **Blind V2**: all **30/30** frozen artifacts re-hash to their manifest values. No Blind V2 frozen/sealed artifact path changed.
- No earlier round's result artifact was modified.

## 17. Exact validation scope

This round validates, for the 16 shipped models, that:

1. the governing equations are the equations the physics requires, re-derived independently;
2. the implementations compute those equations correctly, checked against mathematics written outside them;
3. units and dimensions are consistent, worked term by term;
4. the sign conventions are right, including the ones that would still look plausible if they were wrong;
5. conservation residuals are round-off, measured rather than inferred;
6. limiting behaviour is correct;
7. the numerical methods converge at the order their own schemes justify;
8. the routes offered as independent evidence are independent enough to be evidence.

It does **not** validate: that these are the right models for any particular
purpose; correctness outside each model's declared domain; any regime no case
constructed here reaches; or the empirical accuracy of any correlation against
physical measurement — this repository measures nothing and curates no
reference data, which the Peukert record says of itself.

### Conclusions explicitly rejected

None of these follows, and each names two different assurance layers:

- *the tests pass, therefore the equation is correct* — the tests passed while five audit oracles were wrong
- *two solvers agree, therefore both are correct* — which is why §10 traces what they share, and why no pair here is fully independent
- *the record and the runtime agree, therefore the physics is correct* — settled by an earlier round, and evidence about nothing in this one
- *the benchmark is unchanged, therefore the model is correct* — the benchmarks were unchanged throughout, by construction: nothing changed
- *it is dimensionally valid, therefore it is scientifically valid* — `IR²` and `I²R` differ dimensionally, but `βkC_A` with β's sign flipped does not
- *it converged, therefore the governing equation is correct* — plant STP-6 converges perfectly to the wrong answer

## 18. Remaining limitations

1. **No empirical validation.** Every oracle here is mathematical. Agreement with the equations is not agreement with a cell, a reactor or a slab. The repository says this of itself; this round does not change it.
2. **ngspice covers one domain.** It is the only externally-written executable oracle available, and it speaks only for linear resistive DC. The other five domains rest on mathematics derived in this audit — checked, falsified, but written by the same author as the checks.
3. **Coverage is by constructed case, not exhaustive.** 255 checks and 730 random draws is a sample. Randomized testing covers five families and is bounded by what the generators enforce.
4. **Every repository pair shares its problem statement.** §10 bounds what internal agreement can prove. A defect in the declaration objects themselves would be invisible to all five pairs at once, and is only visible to oracles that build their own inputs — as this round's do.
5. **The stiff CSTR integrator's own tolerances were not independently re-derived.** Its endpoints were checked against RK4 and against algebraic root finding, which is stronger, but the adaptive controller's internal error estimate was taken as given.
6. **The 50-digit check applies to one model.** The other equations are short enough that catastrophic cancellation is implausible, but that is an argument, not a measurement.
