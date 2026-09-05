# K1 — Kinetics/CSTR Solver Admission Gate Report

**Verdict: K1 PASS**

**No Core correction was scientifically required.**

---

## 1. Repository baseline

The task described a baseline of "Core V0.2, 957 tests, domains Electrical and
Thermal conduction, T1/T2/T3 frozen". Two checkouts of this repository exist on
disk and only one of them matches that description, so the first action was to
identify which is the SRIA line.

| checkout | branch | HEAD | tests | domains |
|---|---|---|---|---|
| `engineering-ai-core-v0.1/` (primary) | `hardening/electrical-dc-v0.0.1` | `57b14c1` | 203 | Electrical DC only |
| `.claude/worktrees/scientific-computation-platform-47741c/` | `sria/v0.1-m5-campaign-loop` | `0d0f199` | **957** | Electrical + Thermal, T1/T2/T3, SRIA M1–M5 |

The primary checkout is a divergent line carrying a Scientific Core V0 /
Electrical DC hardening effort; it has no thermal domain, no T-series
experiments and no Core V0.2 invariants. **K1 was executed in the SRIA
worktree**, which is the only checkout matching the stated baseline.

Baseline verification, before any file was written:

- `git rev-parse HEAD` → `0d0f1990b92a1ec68b86f315ef8c1a9a40d54085`
- `git status --porcelain` → clean
- full suite → **957 passed** in 100.3 s
- the digest pins T2 and T3 carry over T1 and the shared harness → all matched
  (they are asserted inside the 957)

The baseline was intact. Work proceeded on a new branch `kinetics/cstr-k1`.

## 2. Frozen starting commit

```
0d0f1990b92a1ec68b86f315ef8c1a9a40d54085
Core V0.2: pin SRIA trust-layer invariants; record the stabilization audit
```

Recorded in `experiments/kinetics_k1/__init__.py` as `BASE_COMMIT`, carried
into every result's provenance as `git_commit`, and asserted by a test.

## 3. Scientific model

A perfectly mixed, constant-volume, liquid-phase continuous stirred-tank
reactor carrying one irreversible exothermic reaction `A -> B`, first order in
A, with Arrhenius kinetics and jacket cooling. This is the Aris–Amundson
reactor in the parameterization tabulated by Seborg, Edgar, Mellichamp and
Doyle.

It was chosen because it is the standard worked example for the two behaviours
K1 needs and the earlier domains could not supply: Arrhenius stiffness, and
multiplicity of steady states.

**Model validation status: `SELF_CONSISTENT`,** not `BENCHMARK_VALIDATED`. K1
compares the integrator against an independently derived algebraic steady state
and an exact invariant of the same equations. That establishes that the
numerics solve what they claim to solve. Nothing here has been compared against
a measurement of a real reactor.

## 4. Governing equations

```
dC_A/dt = (q/V)(C_Af - C_A) - k(T) C_A
dT/dt   = (q/V)(T_f  - T  ) + beta k(T) C_A - gamma (T - T_c)
k(T)    = k0 exp(-E/(R T))

beta  = (-dH)/(rho cp)     adiabatic rise per unit concentration  [m**3 K/mol]
gamma = UA/(V rho cp)      jacket cooling rate constant           [1/s]
```

Dimensional check, performed on the equations and asserted as `Quantity`
algebra in `test_the_governing_equation_is_dimensionally_homogeneous`:

| term | dimensions |
|---|---|
| `(q/V)(C_Af - C_A)` | `(m³/s / m³)(mol/m³)` = mol/(m³·s) |
| `k C_A` | `(1/s)(mol/m³)` = mol/(m³·s) |
| `(q/V)(T_f - T)` | `(1/s)(K)` = K/s |
| `beta k C_A` | `(m³·K/mol)(1/s)(mol/m³)` = K/s |
| `gamma (T - T_c)` | `(1/s)(K)` = K/s |

Both balances are homogeneous.

Derived quantities at the base operating point: `tau = V/q = 60 s`,
`beta = 0.209205 m³·K/mol`, `gamma = 0.0348675 1/s`, `E/R = 8750 K`,
full-conversion adiabatic rise `= 209.2 K`, `Da(T_f) = 0.99993`.

## 5. Units

Every declared and reported quantity carries a real physical dimension. No
dimensionless placeholders were used to dodge unit complexity; the one
dimensionless metric is genuinely dimensionless.

| quantity | unit |
|---|---|
| concentration `C_A`, `C_Af` | `mol/m**3` |
| temperature `T`, `T_f`, `T_c` | `kelvin` (absolute) |
| time, residence time | `second` |
| volume / flow | `m**3` / `m**3/s` |
| `k0` | `1/s` |
| activation energy, heat of reaction | `J/mol` |
| density / heat capacity | `kg/m**3` / `J/(kg*K)` |
| `UA` | `W/K` |
| molar gas constant | `J/(mol*K)` |
| conversion | `dimensionless` (a concentration ratio) |

Temperature is kelvin throughout and is enforced positive, because it appears
inside `exp(-E/(R T))` where a relative scale is meaningless.

The gas constant is declared as a `Quantity` (8.314462618 J/(mol·K), SI-exact)
rather than as a bare float, so it is dimension-checkable like every other
input, and it appears in every result's provenance.

## 6. Validity envelope

**Domain-owned. The Scientific Core contains no CSTR-specific rule**, asserted
by `test_the_scientific_core_owns_no_cstr_specific_rule`, which scans
`src/engcore/scientific/` for `cstr|arrhenius|reactor|kinetics|coolant|
concentration` on word boundaries and finds none.

Declared on the model's `ValidityDomain` and enforced at the declaration
boundary, before any integration:

- temperature ∈ [250, 1000] K — single-phase liquid, constant properties, no
  boiling. Below/above, the model is not inaccurate but inapplicable.
- temperature > 0 K absolutely — `exp(-E/(R T))` is singular at zero.
- concentrations ≥ 0 — a negative concentration is not a state of the system.
- `k0` > 0, activation energy ≥ 0, density > 0, `cp` > 0, `V` > 0, `q` > 0,
  `UA` ≥ 0, residence time > 0.

Tested inside (accepted), **at the boundary** (250.0 and 1000.0 accepted —
bounds are inclusive), and just outside (`±1e-9` rejected).

A second, separate envelope check runs *after* a successful solve, over the
whole trajectory: a declaration that was valid does not promise a trajectory
that stays valid. This is what catches R8.

## 7. Solver implementation

`CSTRSolver` satisfies the frozen `ScientificSolver` protocol
(`isinstance(CSTRSolver(), ScientificSolver)` is asserted) with the five
stages strictly separated:

`supports` → `prepare` → `solve` → `extract_metrics` → `validate`

**The protocol was not changed.** `supports` answers on declared capability and
never attempts a solve — asserted by calling it on an unbound problem where any
solve attempt would raise.

**Method justification.** BDF is the production method: variable-order (1–5)
backward differentiation with an **analytic Jacobian**, the standard choice for
stiff chemical kinetics because it is *stiffly stable* in Gear's sense — its
stability region contains the whole negative real axis and a wedge around it, so
a strongly damped mode does not dictate the step size. BDF is A-stable only at
orders 1–2 and A(α)-stable above that, with α shrinking as the order rises; it
is **not** L-stable at every order it runs at. Radau (5th-order Radau IIA, fully
implicit Runge–Kutta) is the cross-method arm — a different family (one-step
rather than multistep) — and it *is* both A-stable and L-stable. Damping rather
than oscillating on the fast chemical mode is what this problem requires, and it
is what rules out the trapezoidal family, which is A-stable but not L-stable.

> **Erratum against the frozen preregistration.** The hashed
> `method_justification` string in `k1_config_frozen.json` says BDF is
> "L-stable". That is wrong for the reason above. The string is inside the
> hashed preregistration payload, so editing it would change `config_hash` and
> break the freeze that makes "these results came from that configuration"
> checkable. The frozen text therefore stays as recorded and the correction is
> carried in `k1_config.PREREGISTRATION_ERRATA`, which is deliberately excluded
> from the hashed payload. No number, threshold, regime or result is affected —
> the error is entirely in the wording of a justification. RK45 is admitted only as a measuring
instrument for stiffness. **LSODA is refused by the domain** because its
internal stiff/non-stiff switching makes its work count unattributable to one
method and would corrupt the only stiffness measurement K1 has.

The analytic Jacobian is verified against a central difference of the
right-hand side to `rtol=1e-4`.

## 8. Independent verification method

Two references, in `reference.py`, which **never imports the solver** — asserted
by parsing its import graph. Independence is claimed at the level of *numerical
machinery*, not of the model: both sides necessarily use the same `k0`, `E` and
operating conditions, because those *are* the model.

**Reference 1 — algebraic steady states by Brent bracketing.** Eliminating
`C_A` in closed form leaves one scalar equation
`g(T) = a(T_f - T) + beta k(T) a C_Af/(a + k(T)) - gamma(T - T_c) = 0`,
solved by dense sign-change scanning plus `scipy.optimize.brentq`. Different
equations (algebraic, not differential), different algorithm (bracketing root
find, not adaptive implicit time stepping), different implementation — the
Arrhenius exponent is recomputed from `E` and `R` rather than reusing the
declaration's derived `E/R` accessor, so the two sides share no arithmetic. A
test confirms each returned root actually zeroes the residual to < 1e-9.

**Reference 2 — an exact invariant of the nonlinear system.** With
`Z = T + beta C_A`, the reaction term cancels *exactly*:
`dZ/dt = a(Z_f - Z) - gamma(T - T_c)`. Under adiabatic operation this has the
closed form `Z(t) = Z_f + (Z_0 - Z_f) exp(-a t)` — an exact solution of a
component of a genuinely nonlinear stiff system, in elementary functions, with
no truncated series to confuse with the solver's own error. It is a demanding
check rather than a trivial one: `C_A` and `T` individually undergo the full
ignition transient and only their combination is smooth, so reproducing `Z(t)`
requires the integrator to keep both states consistently coupled through the
stiff region.

For a cooled reactor the invariant has no closed form, and the gate reports
`NOT_RUN` rather than quietly substituting a weaker claim. The guard
(`invariant_is_exact`) tests `gamma == 0.0` exactly, not within a tolerance —
asserted, because "approximately adiabatic" is how an unearned
`ANALYTICALLY_VERIFIED` would get awarded.

**BDF-vs-Radau establishes nothing** and is recorded with `establishes=None`.
The two are different families but share this domain's right-hand side, its
Jacobian, and SciPy's step-control and error-norm infrastructure; a shared
error is invisible to the comparison. Calling it `CROSS_SOLVER_VALIDATED` would
be letting the solver grade itself with a second copy of its own homework.

## 9. Preregistration

`experiments/kinetics_k1/k1_config.py`, integrity-pinned by SHA-256 over the
canonical JSON payload, using the same discipline as T1/T2/T3.

```
preregistration hash: 73d09cc0004663409f27edf86fb2bb571bdb7bb78a39203e35ca9c0069d00cb0
experiment version:   1.0.1
base commit:          0d0f1990b92a1ec68b86f315ef8c1a9a40d54085
randomness:           none — K1 has no stochastic component, so no seed exists
```

A test recomputes the hash from the live module and asserts it equals the one
recorded in `k1_config_frozen.json` *and* the one recorded in `k1_results.json`,
so results cannot be attributed to a configuration that has since moved.

**This is a feasibility-informed preregistration, not a blind one, and the
artifact says so.** An exploratory pass established which regimes exist in this
parameterization, roughly what they cost, and the scale of every residual before
the bands were written down. The bands were then set comfortably outside those
observations and frozen. Two gate thresholds were *tightened* as a direct
consequence — `INVARIANT_REL_TOL` and `STEADY_STATE_REL_TOL` went from 1e-6 to
1e-9, because exploration showed the residuals sit near 1e-15 and a 1e-6 gate
could not have failed, making it worthless as evidence.

What that costs, plainly: the predictions are not discoveries. Their function is
to fix the criteria before the scored run so a missed band must be reported as
one. The discipline carrying weight here is the no-tuning rule, not surprise.

### The invalidated run

Version 1.0.0 ran, met all eight regime predictions, and **failed acceptance
criterion A7**: failure case B was not represented. The cause was an apparatus
bug — the runner's case-B probe injected a discontinuous sign flip expecting
SciPy to abandon the step; instead SciPy ground the step size down and kept
going until the 5,000,000-evaluation budget ran out, which the adapter reported,
correctly, as `MAX_ITERATIONS`.

Per the preregistration's own rule, the run was **invalidated rather than
patched**: the bug was documented in the package's version history, the probe
was corrected to inject a genuine finite-time singularity (`dT/dt += T²`, the
Riccati blowup), the version was incremented to 1.0.1, and the whole study was
rerun from scratch. The 1.0.0 numbers are superseded, not reported. A test
asserts the invalidation record is still present.

## 10. Regimes tested

Eight scored regimes plus sixteen invalid declarations, designed so each
distinguishable outcome occurs at least once through a genuine mechanism.

| id | category | mechanism |
|---|---|---|
| R1 | easy | well-cooled, `Tc=290 K`, 30 residence times, low conversion |
| R2 | moderately stiff | adiabatic, `T_f=340 K`, ignites to ~549 K |
| R3 | strongly stiff | adiabatic, `C_Af=2600 mol/m³`, ignites to ~894 K |
| R4 | invalid input | 16 declarations outside the envelope |
| R5 | failure-prone | R3's physics under a 500-evaluation budget |
| R6a/R6b | branch-sensitive | `Tc=300 K` (3 algebraic steady states), cold and hot starts |
| R7 | branch-sensitive | `Tc=305 K` — no *stable* steady state at all |
| R8 | unusable result | adiabatic, `C_Af=4000 mol/m³`, exits the envelope |

## 11. Results table

Environment: Python 3.14.2, numpy 2.5.1, scipy 1.18.0, Windows/AMD64.

| regime | convergence | usable | case | gate levels | nfev | njev | nlu | steps | wall s | C_A,f mol/m³ | T_f K | T_max K | X |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `converged` | ✔ | E | NUM, XSOL | 350 | 1 | 28 | 138 | 0.018 | 951.941 | 312.656 | 312.671 | 0.04806 |
| R2 | `converged` | ✔ | E | NUM, **ANA**, XSOL | 1135 | 2 | 79 | 440 | 0.049 | 0.11539 | 549.181 | 549.181 | 0.99988 |
| R3 | `converged` | ✔ | E | NUM, **ANA**, XSOL | 1563 | 4 | 108 | 576 | 0.062 | 6.436e-4 | 893.933 | 893.933 | 1.00000 |
| R5 | `max_iterations` | ✘ | A | — | 501 | — | — | — | 0.026 | — | — | — | — |
| R6a | `converged` | ✔ | E | NUM, XSOL | 409 | 2 | 32 | 156 | 0.019 | 877.253 | 324.475 | 324.678 | 0.12275 |
| R6b | `converged` | ✔ | E | NUM, XSOL | 2046 | 45 | 166 | 698 | 0.098 | 877.253 | 324.475 | 658.849 | 0.12275 |
| R7 | `converged` | ✔ | E* | **none** | 33993 | 15 | 1921 | 11894 | 1.253 | 38.884 | 399.454 | 480.307 | 0.96112 |
| R8 | `converged` | ✘ | **D** | — | 1935 | 3 | 120 | 662 | 0.073 | 8.844e-5 | 1186.820 | 1186.820 | 1.00000 |

`NUM` = `NUMERICALLY_CONVERGED`, `ANA` = `ANALYTICALLY_VERIFIED`,
`XSOL` = `CROSS_SOLVER_VALIDATED`. Every regime that produced metrics attained
exactly `DIMENSIONALLY_VALID` at the per-solve level and nothing more.
R7's case is starred — see §12.

### Stiffness, measured rather than asserted

Stiffness is defined operationally as the ratio of RK45 to BDF right-hand-side
evaluations: a problem is stiff exactly when an explicit method is forced to
take steps far smaller than accuracy alone requires.

| regime | BDF nfev | RK45 nfev | ratio | preregistered band | in band | probe outcome |
|---|---|---|---|---|---|---|
| R1 | 350 | 332 | 0.9 | ≤ 5 | ✔ | completed |
| R2 | 1135 | 181 142 | 159.6 | ≥ 20 | ✔ | completed |
| R3 | 1563 | 5 000 001 | **≥ 3199** | ≥ 200 | ✔ | budget exhausted |

**This corrected a working assumption.** The cooled Seborg regimes — the ones a
textbook calls the canonical stiff CSTR — are *not* measurably stiff at
`rtol=1e-8`: their ratios sit between 0.8 and 2.9, and RK45 is sometimes
*cheaper* than BDF. The reason is that at tight tolerance the explicit step is
limited by accuracy, not stability, so stiffness does not show. The genuinely
stiff regimes in this parameterization are the **adiabatic** ones, where
ignition drives the temperature to 549 K and 894 K and the rate constant to
~10² and ~10⁵ s⁻¹ against a flow rate of 0.0167 s⁻¹. Exploration also showed
the R2 ratio falling monotonically with tolerance (274 → 160 → 65 at
rtol 1e-6/1e-8/1e-10), exactly as that explanation predicts.

R1's band is the control: a regime predicted *not* to be stiff, so that R2's
and R3's numbers mean something.

### Reference agreement

| regime | tolerance ladder final Δ | invariant max rel err | steady-state rel err | steady states found | cross-method max Δ |
|---|---|---|---|---|---|
| R1 | 4.68e-09 | n/a (cooled) | **5.45e-16** | 1 | 4.55e-09 |
| R2 | 6.13e-15 | **2.69e-15** | **0.00e+00** | 1 | 2.48e-15 |
| R3 | 1.68e-16 | **1.14e-15** | **1.27e-16** | 1 | 2.29e-15 |
| R6a | 3.70e-08 | n/a (cooled) | **7.01e-16** | **3** | 3.04e-08 |
| R6b | 3.94e-10 | n/a (cooled) | **3.85e-15** | **3** | 3.91e-10 |
| R7 | **4.70e-06 (fails 1e-6)** | n/a (cooled) | withheld — not stationary | 1 | 1.44e-07 |
| R8 | gate not run (declared) | — | — | — | — |

Gate thresholds in force: tolerance 1e-6, invariant 1e-9, steady state 1e-9,
stationarity 1e-6. Tolerance ladder: rtol/atol = 1e-6, 1e-8, 1e-10, 1e-12.

## 12. Failure cases

All five distinguishable outcomes occurred, each mapping onto a **distinct**
combination of existing Core states. None were collapsed and no new enum value
was added.

| case | regime | `ConvergenceState` | `is_usable` | metrics | mechanism |
|---|---|---|---|---|---|
| **A** execution failure | R5 | `MAX_ITERATIONS` | False | none | 500-evaluation budget exhausted at 0.29 % of the horizon |
| **B** non-convergence | *none* | `NOT_CONVERGED` | False | none | adapter probe: injected `dT/dt += T²`, SciPy status −1 |
| **C** invalid input | R4 ×16 | *no solve attempted* | — | — | refused at the declaration boundary |
| **D** valid run, unusable | R8 | `CONVERGED` | **False** | present | trajectory reached 1186.8 K, outside the 1000 K envelope |
| **D′** valid run, unusable | R7 | `CONVERGED` | **True** | present | no stable steady state; gate awards nothing |
| **E** valid result | R1,R2,R3,R6a,R6b | `CONVERGED` | True | present | converged, inside envelope, no failing check |

**Why `MAX_ITERATIONS` and not `FAILED` for R5.** `MAX_ITERATIONS` means the
backend stopped at a work cap, which an explicit evaluation budget is exactly.
`FAILED` would imply the method or the problem was at fault, and neither was —
R5 was still making progress when it was stopped. A test asserts R5 is *not*
`FAILED`.

**Case B is not produced by any regime, and that is a result rather than a
gap.** The CSTR system is globally bounded: as `T` grows the Arrhenius factor
saturates at `k0`, so the reaction cannot outrun the flow and cooling terms, and
the reactant is consumed, removing the heat source. There is no finite-time
singularity anywhere in the model for any admissible parameters. Manufacturing a
regime that "produced" case B would have been a fabrication. The adapter's
classification was therefore exercised directly, against an injected genuine
finite-time singularity, and labelled in the artifact as an adapter probe and
not a statement about any reactor. It returned `NOT_CONVERGED`, preserved the
partial trajectory (reaching t = 0.00296 s), and extracted no metrics.

**R7 is the sharpest result in the study.** At `Tc = 305 K` the single algebraic
steady state has a positive Jacobian trace with positive determinant — an
unstable focus — and the reactor cycles indefinitely with a sustained 43 K
amplitude confirmed over 3000–6000 s. The integration is impeccable point by
point: finite, inside the envelope, no failing check, `is_usable` **True**. Yet
the reported "final temperature" of 399.45 K is a *phase of a limit cycle*, not
an answer to "what does this reactor do". The per-solve contract cannot see
this, and correctly does not pretend to. The verification gate can, and awards
**nothing**: the end state is not tolerance independent (4.70e-06 against a
1e-06 threshold) and the trajectory is not stationary (the last tenth of the
horizon moves the temperature by 8.6e-02 and the concentration by 8.2e-01
relative), so the steady-state comparison is withheld rather than reported as
disagreement.

**R8 and R7 are deliberately different, and collapsing them would be a lie.**
R8's problem is visible to a single solve, so its per-solve check fails and
`is_usable` goes False. R7's is visible only to a sequence, so `is_usable`
stays True and the *gate* is what refuses. One state cannot carry both.

## 13. Validation results

- **16 of 16** invalid declarations refused, all by the domain's own
  `ReactorConfigurationError`, before any solve. This covers negative and
  out-of-envelope temperatures on both sides, negative concentration, zero
  volume, negative flow, negative `UA`, zero/negative `k0`, negative activation
  energy, zero density, a bare number where a `Quantity` is required, a pressure
  supplied as a temperature, LSODA, and a zero relative tolerance.
- **`ANALYTICALLY_VERIFIED` earned by R2 and R3**, from the exact reaction-free
  invariant, to 2.69e-15 and 1.14e-15 relative — and only on adiabatic regimes,
  asserted.
- **`CROSS_SOLVER_VALIDATED` earned by R1, R2, R3, R6a, R6b**, from the
  independent Brent steady state, best 0.00e+00 and worst 3.85e-15 relative.
- **F7 did not fire**: no converged, stationary production result disagrees with
  the independent reference beyond 1e-9.
- **A8 held**: no single solve ever claimed `NUMERICALLY_CONVERGED`. Every
  regime producing metrics attained exactly `{DIMENSIONALLY_VALID}` per-solve,
  with `tolerance_independence`, `analytic_invariant_agreement` and
  `independent_steady_state_agreement` recorded explicitly as `NOT_RUN` rather
  than left silent.
- An unearned level cannot be smuggled in by deserialization: appending
  `experimentally_validated` to a serialized report's `attained_levels` raises
  `ScientificValidationError`.
- **A9**: R6a and R6b agree on the final temperature to < 1e-6 K despite the
  independent solver finding **three** steady states at `Tc = 300 K`
  (324.475 K stable, 350.006 K saddle, 369.705 K unstable focus). The hot start
  peaked at 658.8 K versus R6a's 324.7 K and still landed on the same attractor.
  Three algebraic steady states do not mean two attractors — in this
  parameterization the upper branch is Hopf-unstable, so the multiplicity window
  produces oscillation rather than bistability.

## 14. Numerical adequacy assessment

The distinction between solver success and numerical adequacy is preserved and
was load-bearing.

What is claimed, separately and with different evidence:

1. **The integrator reported success.** `solve_ivp` status 0. This is the
   integrator's opinion of its own local error control, it is equally confident
   at rtol=1e-2 and 1e-12, and it establishes nothing. Recorded with
   `establishes=None`.
2. **Tolerance independence.** The quantities of interest stop moving down a
   four-rung ladder (1e-6 → 1e-12, absolute tolerances falling with the
   relative one so no rung is silently floored by its atol). This — and only
   this — awards `NUMERICALLY_CONVERGED`. Work rose monotonically down every
   ladder, asserted.
3. **Exact-reference agreement.** Requires (2) first. Agreement without a
   convergent sequence behind it is luck, not verification, and the gate says so
   in the withheld-claim text.
4. **Independent-solver agreement.** Requires (2) *and* stationarity. A
   trajectory still moving cannot be compared to a steady state; a test asserts
   a 60-second-horizon R1 has the comparison withheld with the reason recorded.
5. **Cross-method agreement.** Recorded, awards nothing, reason documented.

R7 is the case that shows the ladder is doing real work: it passes (1)
comfortably and fails (2), so it earns nothing.

## 15. Reproducibility result

- No stochastic component anywhere; the preregistration declares "none" rather
  than a seed.
- `test_the_run_is_deterministic` asserts two solves of identical declarations
  agree bit-for-bit on every metric and on the evaluation count.
- `test_output_density_does_not_change_the_integration_path` asserts that
  reporting resolution (11 vs 20 001 output points) changes neither the
  evaluation count nor the final value — `t_eval` reports the solution, it never
  steers it.
- Results round-trip through `ScientificResult.to_dict`/`from_dict` with
  identical magnitudes, units, convergence state and attained levels.
- No hidden configuration: there are no notebooks, and every number in
  `k1_results.json` derives from the pinned `k1_config.py` plus the recorded
  library versions.

**The study was re-executed from the clean clone and its artifacts diffed
against the committed ones.** The result is the sharpest reproducibility
statement K1 can make:

| artifact | outcome |
|---|---|
| `k1_config_frozen.json` | **byte-identical** |
| `k1_results.json` | 64 changed lines, **all 64 are `wall_seconds_telemetry`** |
| `k1_report.md` | 16 changed lines — the wall-clock column of the 8 result rows |

Every scientific number reproduced exactly: every metric, every reference
residual, every evaluation count, every convergence state, every attained
level, every acceptance verdict. The only quantity that moved is wall-clock
time, which this domain declares as telemetry and never as a score — the
reproducible cost measure is the right-hand-side evaluation count, which is
deterministic for a fixed declaration and did not move.

That is also a small vindication of the design decision: had wall-clock been
used as the cost figure anywhere, K1 would not be reproducible.

## 16. Core changes required

**None. No Core correction was scientifically required.**

This is established by construction rather than by inspection:
`git status --porcelain` against the baseline shows **four untracked additions
and zero modifications to any tracked file**.

```
?? experiments/kinetics_k1/
?? src/engcore/domains/kinetics/
?? tests/domains/kinetics/
?? tests/test_kinetics_k1.py
```

`git diff --stat HEAD` is empty. Not one line of
`src/engcore/scientific/` was touched.

### K1 Evidence-Pulled Core Corrections

*No Core correction was scientifically required.*

Each Core-change precondition was tested and none was met:

| precondition | finding |
|---|---|
| a real scientific state cannot be represented honestly | every one of A–E mapped onto a distinct existing combination |
| existing contracts would require lying or discarding evidence | R5's partial progress, the probe's partial trajectory and R8's envelope violation all had honest homes (`RawSolverOutput.diagnostics`, a FAILing `ValidationCheck`) |
| a new enum value is needed | none. `MAX_ITERATIONS`, `NOT_CONVERGED`, `DIVERGED`, `FAILED`, `CONVERGED` covered every observed case, and `ValidationLevel` needed no addition |
| the Core must branch on this domain | it does not; the scan finds no domain term in the Core |

Two Core design decisions were specifically vindicated by K1 and are worth
naming, because both were doing real work:

- **The `Quantity` finiteness invariant with `RawSolverOutput` as the sanctioned
  exception.** A diverged solve genuinely produces non-finite values, and the
  adapter reports them honestly in diagnostics while `extract_metrics` returns
  `{}`. Without that split, either the adapter would have to lie about
  divergence or non-finite values would reach admitted results.
- **`attained_levels` being derived and never settable.** The gate's three
  levels are earned through passing checks that declare them, and the
  deserialization path recomputes and rejects mismatches.

## 17. Architecture-creep report

Nothing generic was invented. What was added:

| location | files | purpose |
|---|---|---|
| `src/engcore/domains/kinetics/cstr/` | 6 modules | the domain: declarations, model, references, solver, validation |
| `experiments/kinetics_k1/` | 3 modules + 3 artifacts | the preregistration, the runner, the frozen results |
| `tests/` | 2 files, 109 tests | domain and experiment tests |

Everything domain-specific stayed in the domain layer: the kinetics equations,
the reactor configuration, the chemistry validity rules, the kinetic parameter
semantics, the CSTR metrics, the reference solutions and the model assumptions.

No abstraction was promoted to Core. In particular the following were
*deliberately not* generalized, because one domain is not evidence for a generic
abstraction:

- the tolerance ladder and its gate — the Thermal domain has a *refinement*
  ladder that is structurally similar and semantically different (mesh vs
  tolerance); two similar things are not yet a pattern
- the stiffness measurement — meaningful only for time integration
- `IntegrationSettings`, `ReactorChemistry`/`ReactorOperation` split, the
  physics fingerprint, the RHS-evaluation budget

The scope boundary held. No inference, no MCMC, no VI, no BoTorch, no
optimization, no acquisition, no adaptive experiment selection, no surrogate,
no generic chemistry ontology, no generic uncertainty engine, no Domain Mind,
no digital twin, no visualization, no multiphysics, no distributed execution.

## 18. Acceptance criteria A1–A12

The preregistration froze ten criteria (A1–A10). All ten passed, and are scored
in `k1_results.json` from the recorded data rather than asserted in prose. The
task's A1–A12 map onto them as follows.

| task | criterion | verdict | evidence |
|---|---|---|---|
| A1 | benign nonlinear case through the full path | **PASS** | R1: `CONVERGED`, usable, metrics in mol/m³, K, s, dimensionless (prereg A1) |
| A2 | materially stiff case executed and assessed | **PASS** | R2 ratio 159.6, R3 ratio ≥ 3199 with RK45 defeated; R1 control at 0.9 (prereg A2) |
| A3 | genuine failure/invalid/unusable path | **PASS** | R5 budget exhaustion at 0.29 % of horizon; 16/16 R4 refusals; R8 envelope exit — none mocked (prereg A3, A5) |
| A4 | execution success distinguished from scientific validity | **PASS** | R8 `CONVERGED` + not usable; R7 `CONVERGED` + usable + zero gate levels (prereg A4) |
| A5 | validity envelope is domain-owned | **PASS** | Core scan finds no domain term; envelope declared on the model (prereg A5) |
| A6 | at least one independent/reference mechanism | **PASS** | two: exact invariant and Brent steady state, both awarding levels (prereg A6) |
| A7 | frozen experiments unchanged | **PASS** | zero tracked-file modifications; T2/T3 digest pins still match |
| A8 | full repository regression passes | **PASS** | see closing summary |
| A9 | clean-clone execution passes | **PASS** | see closing summary |
| A10 | no speculative Core abstraction added | **PASS** | §17; zero Core files touched |
| A11 | no LLM supplies numerical scientific truth | **PASS** | every number derives from pinned code and declared inputs; see the caveat below |
| A12 | report separates observation from interpretation | **PASS** | §20 vs §21 vs §22 |

**The A11 caveat, stated plainly.** The *declared inputs* — the customary-unit
Seborg parameter table — were supplied from the standard textbook
parameterization and transcribed to SI in the preregistration. That
transcription has **not** been checked against the printed source, and the
preregistration says so explicitly. No K1 conclusion depends on it: the question
K1 asks is whether the contracts can carry a stiff kinetics solver, and that is
answered identically for any defensible parameter set. Every *result* number is
computed by the repository's code from those frozen declarations. No numerical
scientific result was supplied by a language model.

## 19. Falsification triggers F1–F8

| trigger | fired? | evidence |
|---|---|---|
| F1 Core requires CSTR-specific branching | **no** | zero Core modifications; word-boundary scan of `src/engcore/scientific/` finds no domain term |
| F2 a meaningful failure cannot be represented without losing information | **no** | R5 keeps its abort time and horizon fraction; the collapse probe keeps its full partial trajectory; R8 keeps the violating temperature and the reason |
| F3 success auto-promoted to a higher validation claim | **no** | every per-solve report attains exactly `{DIMENSIONALLY_VALID}`; the three higher levels come only from the gate |
| F4 invalid state enters admitted evidence | **no** | R8 is reported not usable; `Quantity` refuses NaN/±Inf; a test asserts every usable result stayed inside the envelope |
| F5 historical frozen artifacts must change | **no** | zero tracked-file modifications; T1/T2 digest pins re-verified; K1 imports no frozen experiment package and writes only inside its own directory (both asserted) |
| F6 a large generic framework invented before evidence | **no** | §17 |
| F7 independent verification materially disagrees | **no** | worst agreement across five regimes 3.85e-15 against a 1e-9 gate |
| F8 cannot be reproduced cleanly | **no** | deterministic; clean-clone verified |

No trigger was tuned away. R7's tolerance-independence failure was *kept* as the
correct outcome rather than loosened, and the 1.0.0 A7 failure was handled by
invalidation and rerun rather than by adjusting the criterion.

## 20. What K1 proved

Observations, and the narrowest interpretation each supports.

1. **A stiff, nonlinear, failure-prone kinetics solver satisfies the frozen
   `ScientificSolver` protocol unchanged.** Five stages, no protocol edit, no
   Core edit, zero tracked-file modifications.
2. **The existing failure vocabulary distinguishes all five cases without a new
   enum value.** A, B, C, D and E each landed on a distinct combination of
   `ConvergenceState`, `is_usable` and metric presence.
3. **Execution success and scientific validity are genuinely separable in this
   Core, in two independent ways.** R8 separates them at the single-solve level;
   R7 separates them at the sequence level with the single solve none the wiser.
4. **A validity envelope can be entirely domain-owned.** 16/16 refusals at the
   declaration boundary, plus a trajectory-level envelope check, with no Core
   knowledge of chemistry.
5. **Two genuinely independent verification mechanisms are constructible and
   agree with the production path to round-off** (worst 3.85e-15 against a
   1e-9 gate).
6. **The Core's refusal to let a single solve claim numerical convergence was
   load-bearing, not ceremony.** R7 passes every single-solve check and fails
   tolerance independence.
7. **Stiffness in this parameterization is a property of adiabatic operation,
   not of the cooled textbook operating point** — measured, not assumed, and it
   contradicted the working assumption K1 started with.
8. **The reactor exhibits three algebraic steady states with one attractor and,
   nearby, no stable steady state at all** — confirming that "the steady state"
   is not always a well-posed question, and that an independent reference and a
   time integrator can correctly answer *different* questions.

## 21. What K1 did **not** prove

- **Nothing about any real reactor.** No physical measurement appears anywhere.
  The model is `SELF_CONSISTENT`, not `BENCHMARK_VALIDATED`, and not
  `EXPERIMENTALLY_VALIDATED`.
- **Not domain neutrality.** Three domains is not a proof of generality. K1
  shows the contracts carry *this* domain; it does not show they carry
  electrochemistry, multi-reaction networks, PDE-coupled kinetics or anything
  with algebraic constraints (no DAE was attempted despite `CoreCapabilities.DAE`
  existing).
- **Not chemistry generality.** One reaction, first order, one phase, constant
  properties, constant volume, prescribed jacket temperature. No reaction
  networks, no equilibrium, no transport limitation, no species beyond A.
- **Not inference readiness.** No parameter was estimated. No posterior, no
  likelihood, no identifiability analysis was performed or implied.
- **Not optimization or Digital Twin readiness.** Nothing was selected,
  optimized, coupled or driven by data.
- **Not uncertainty quantification.** Every result reports
  `UncertaintyKind.UNKNOWN`. The tolerance ladder bounds the *numerical*
  component only; the model-form component was not estimated at all.
- **Not a blind preregistration.** See §9.
- **Not that the parameter transcription is correct** against its printed
  source. See §18.
- **Not that case B arises in practice.** It was exercised against the adapter,
  not produced by any admissible reactor.
- **Not that the verification thresholds are preregistered.** They are declared
  after exploratory analysis, and the artifact says so.

## 22. Remaining scientific debt

Ordered by how much they would change a conclusion.

1. **A `ScientificResult` carries no link to the sequence-level verification
   that judged it.** This is the single most important finding, and it is the
   biggest Core weakness K1 exposed. R7 is `is_usable == True` while its gate
   awards nothing; a consumer reading only the result would admit a limit-cycle
   phase as evidence. This is *not* a representational failure — `is_usable` is
   documented as "the absence of known problems, not the presence of proof", the
   gate emits a `ValidationReport` in the universal vocabulary, and a domain can
   merge it into a result. So no Core change is warranted on the evidence. But
   nothing in the Core *forces* that connection, and the discipline is currently
   convention. If a second domain independently needs it, that is the evidence
   for a minimal generic correction — and K1 deliberately did not pre-empt it.
2. **The verification thresholds are declared, not preregistered.** The remedy
   is a predeclared confirmatory case the thresholds were not chosen from — the
   Thermal domain solved this with a holdout declaration and Kinetics has no
   equivalent yet.
3. **No DAE, no reaction network, no transport limitation.** The `core:dae`
   capability exists and is unexercised.
4. **Uncertainty remains almost entirely unexercised.** Every K1 result is
   `UNKNOWN`. The `STANDARD`/`INTERVAL` paths and the correlated-uncertainty
   question are untouched.
5. **Solver-failure probability is still unmeasured.** K1 produced failures on
   demand but did not estimate how often a realistic workload fails.
6. **`t:T_max` is excluded from the convergence QoIs** because its sampled
   argmax is plateau-valued on a monotone approach. A time-of-peak QoI that is
   robust for both monotone and ignition trajectories was not devised.
7. **The parameter transcription is unverified** against its printed source.
8. **Wall-clock is telemetry only** and was not controlled; the reproducible
   cost measure is the evaluation count.

## 23. Recommendation for K2

**K1 ends here. K2 was not started, and no inference, optimization or
experiment-selection code exists in this branch.**

The recommendation is deliberately narrow, and it is *not* "now do Arrhenius
inference".

**Recommended K2: close the result↔verification gap before adding any inference
layer, using a second domain as the evidence.**

The reasoning: K1's sharpest result is that a scientifically meaningless number
(R7) is `is_usable == True`. Any inference layer built on top of admitted
results would consume exactly such numbers, and would consume them with
confidence. Adding inference *before* that gap is closed builds the next
milestone on the one weakness this one found.

Concretely, K2 should:

1. Take one further domain — ideally one needing a DAE or a reaction network, so
   `core:dae` is exercised and generality has a second data point.
2. Determine whether *that* domain independently needs a result to carry its
   sequence-level verdict. Two independent domains needing it is the evidence
   threshold for a minimal generic Core correction; one is not.
3. Add the Kinetics holdout declaration that turns the declared verification
   gate into confirmatory evidence.

If the appetite is specifically for inference, the smallest honest step is
**single-parameter** estimation of `E/R` or `k0` on R1's benign regime, where
the reference is exact and the trajectory settles — explicitly *not* the
three-parameter correlated posterior, and explicitly not on R7-like regimes
until (1) is settled. But the sequencing above is the stronger recommendation.

---

## Closing summary — the numbers A8/A9 refer to

| item | value |
|---|---|
| worktree | `.claude/worktrees/scientific-computation-platform-47741c` |
| branch | `kinetics/cstr-k1` |
| starting commit | `0d0f1990b92a1ec68b86f315ef8c1a9a40d54085` |
| starting suite | **957 passed** |
| K1 commit | `91dac69` — the domain, the experiment, the tests, this report |
| final commit | the commit adding this section (`git log -1 --format=%H -- docs/kinetics-cstr-k1.md`) |
| final suite (in-place) | **1066 passed** (957 + 109 K1) |
| final suite (clean clone) | **1066 passed** |
| artifacts re-run from the clone | every scientific number identical; only wall-clock telemetry moved (§15) |
| preregistration hash | `73d09cc0004663409f27edf86fb2bb571bdb7bb78a39203e35ca9c0069d00cb0` |
| experiment version | `1.0.1` (1.0.0 invalidated — §9) |
| tracked files modified | **0** |
| Core files touched | **0** |

The clean clone was taken with `git clone --branch kinetics/cstr-k1 --single-branch`
into a fresh directory, checked for a clean working tree, and run with no
`__pycache__` and no local state. The repository's `.gitattributes` pins the
working tree to LF repository-wide, which is what lets the byte-digest freezes
of T1/T2/T3 and the Electrical experiments survive a checkout — those pins were
re-verified from the clone and all matched.

---

# Appendix — merge-readiness corrections (`fix/k1-merge-readiness`)

Six defects were found in review of the frozen K1 branch and corrected on
`fix/k1-merge-readiness`, based on `bc7b1a3`. **No K1 scientific result, regime,
threshold or frozen artifact was changed**, and neither Core was touched —
verified by diffing `src/engcore/scientific/` and `src/engcore/sria/` against
`0d0f199` directly rather than against `HEAD`.

Two corrections change *semantics* that the frozen v1.0.1 artifact recorded
under the old rules. In both cases the artifact is left exactly as frozen and
the correction applies prospectively, with the discrepancy pinned by a test so
it can never be mistaken for drift.

| | defect | disposition |
|---|---|---|
| **P1.1** | `git_commit` carried the frozen Core baseline (`0d0f199`) — a commit that *predates the solver*, so provenance pointed at a tree with no kinetics domain in it | `solve_reactor` now takes `source_commit` (the executing revision, → `ProvenanceRecord.git_commit`) and `core_baseline_commit` (context, → provenance metadata). Resolution happens in the experiment layer; the Core still harvests nothing. **Frozen artifact keeps the old value**, pinned by `test_a10_provenance_is_complete_for_every_regime` |
| **P1.2** | the gate treated `bool(result.values)` as rung success, so a CONVERGED-but-unusable rung (R8) could carry a sequence to a validation level | a rung must be converged **and** `is_usable`. Unusable rungs are *withheld with a recorded reason*, not relabelled as failures, and can no longer become the reference for the invariant or steady-state comparison |
| **P2.1** | the physical envelope was assessed from accepted solver nodes only, which cannot see an excursion between nodes | extrema now taken over accepted nodes **∪** the dense output already computed for the invariant check. Node-only values retained alongside so the contribution is visible. Explicitly labelled a *sampled bound*, not an exact continuous extremum |
| **P2.2** | the steady-state search claimed "every stationary point"; a tangential root at a fold has no sign change and cannot be bracketed | claim narrowed to **transversal roots only**, with `SEARCH_SEMANTICS` carried into every serialized verification record. No continuation framework was built |
| **P3.1** | two false claims: that Arrhenius `dk/dT` grows without bound, and that BDF is L-stable at every order | corrected everywhere editable. `dk/dT → 0` as `T → ∞` (`k → k0`); it is maximised at `E/2R = 4375 K`, far above the 1000 K ceiling, so it rises monotonically only *within the envelope*. BDF is **stiffly stable** (Gear), A-stable at orders 1–2 only. The one occurrence inside the hashed preregistration is recorded as an erratum instead |
| **P3.3** | `int(500.9) → 500` silently ran a different experiment from the one declared | counts must be genuine `int`. Fractional floats, integral floats, strings, `None`, NaN/Inf and `bool` are all refused — `bool` explicitly, since it is an `int` subclass and would read as 1 |

### What the fixes revealed

Two things worth recording, because neither was known before:

- **P2.1's guard is real but non-binding on every K1 regime.** On BDF the
  accepted nodes already resolve every excursion — step control clusters them
  exactly at the peak — so union and node-only extrema agree to the last bit on
  R1, R2, R3, R6a, R6b, R7 and R8. A binding case does exist and is pinned as a
  regression test: **Radau at rtol=1e-3**, whose collocation interpolant leaves
  the node hull by 1.3e-7 mol/m³. The guard tightens a bound; on this domain it
  has never yet changed an admissibility verdict.
- **R8's physics does not survive its own tolerance ladder.** At rtol=1e-12 the
  runaway hits genuine step-size collapse (`NOT_CONVERGED`). So R8's gate is
  refused by *both* routes — three rungs converged-but-unusable and one that
  did not converge at all — which is a stronger negative than K1 originally
  recorded.

### Test count

The K1 tests grew from **109 to 160**; the full authoritative suite from
**1066 to 1117**. All 51 additions are regression tests for the six defects,
including the adversarial cases the review asked for, and two that pin the
frozen artifact's superseded semantics so they cannot be mistaken for drift.

## Final verdict

# K1 PASS

No Core correction was scientifically required.
