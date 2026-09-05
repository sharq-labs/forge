# K1 — Kinetics/CSTR Solver Admission Gate: results

- experiment version: `1.0.1`
- base commit: `0d0f1990b92a1ec68b86f315ef8c1a9a40d54085`
- preregistration hash: `73d09cc0004663409f27edf86fb2bb571bdb7bb78a39203e35ca9c0069d00cb0`
- environment: python 3.14.2, numpy 2.5.1, scipy 1.18.0, Windows/AMD64

## Regime results

| regime | category | convergence | usable | case | gate levels | nfev | wall s | T_final K | X | ref error |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | easy | `converged` | True | E | numerically_converged, cross_solver_validated | 350 | 0.018 | 312.6562 | 0.04806 | 5.45e-16 |
| R2 | moderately_stiff | `converged` | True | E | numerically_converged, analytically_verified, cross_solver_validated | 1135 | 0.049 | 549.1809 | 0.99988 | 0.00e+00 |
| R3 | strongly_stiff | `converged` | True | E | numerically_converged, analytically_verified, cross_solver_validated | 1563 | 0.062 | 893.9329 | 1.00000 | 1.27e-16 |
| R5 | failure_prone | `max_iterations` | False | A | — | 501 | 0.026 | — | — | — |
| R6a | branch_sensitive | `converged` | True | E | numerically_converged, cross_solver_validated | 409 | 0.019 | 324.4754 | 0.12275 | 7.01e-16 |
| R6b | branch_sensitive | `converged` | True | E | numerically_converged, cross_solver_validated | 2046 | 0.098 | 324.4754 | 0.12275 | 3.85e-15 |
| R7 | branch_sensitive | `converged` | True | E | — | 33993 | 1.253 | 399.4539 | 0.96112 | — |
| R8 | unusable_result | `converged` | False | D | — | 1935 | 0.073 | 1186.8201 | 1.00000 | — |

## Stiffness, measured rather than asserted

| regime | BDF nfev | RK45 nfev | ratio | band | in band | probe outcome |
|---|---|---|---|---|---|---|
| R1 | 350 | 332 | 0.9 | [-, 5.0] | True | `completed_horizon` |
| R2 | 1135 | 181142 | 159.6 | [20.0, -] | True | `completed_horizon` |
| R3 | 1563 | 5000001 | ≥ 3199.0 | [200.0, -] | True | `rhs_budget_exhausted` |

## Validity envelope: declarations that were refused

16 of 16 refused; 16 by the domain's own error type, before any solve.

- ✓ `negative_absolute_temperature` — exp(-E/(R T)) has an essential singularity at T = 0 and no meaning below it
- ✓ `temperature_above_envelope` — outside the model's declared 250-1000 K single-phase constant-property envelope
- ✓ `temperature_below_envelope` — below the declared envelope; the liquid phase is not assured
- ✓ `negative_feed_concentration` — a negative concentration is not a state of the system
- ✓ `zero_volume` — a zero-volume tank has no residence time
- ✓ `negative_flow_rate` — reversed flow is not the modelled configuration
- ✓ `negative_ua` — a negative UA would pump heat up its own gradient
- ✓ `non_positive_k0` — a zero pre-exponential factor is not an Arrhenius rate
- ✓ `negative_activation_energy` — a negative barrier makes the rate fall with temperature, which is not the Arrhenius model
- ✓ `non_positive_density` — a zero density gives an infinite temperature response
- ✓ `negative_initial_concentration` — a negative initial concentration is not a state of the system
- ✓ `initial_temperature_outside_envelope` — starting outside the envelope the model does not cover
- ✓ `bare_number_instead_of_quantity` — a bare number is not a declaration: it carries no unit and cannot be dimension-checked
- ✓ `wrong_dimension_for_temperature` — a pressure is not a temperature
- ✓ `unknown_integration_method` — LSODA switches between stiff and non-stiff internally, so a work count from it cannot be attributed to one method and would corrupt the stiffness measurement
- ✓ `non_positive_rtol` — a zero relative tolerance is not achievable

## Failure semantics: the five cases

- case A: represented
- case B: represented
- case C: represented
- case D: represented
- case E: represented

Case B is exercised directly against the adapter rather than by a regime: `not_converged`, partial trajectory preserved = True, metrics extracted = False.

## Acceptance criteria

- **A1** PASS — A1 R1 completes through the full five-stage contract with CONVERGED, is_usable True, and metrics carrying mol/m**3, kelvin, seconds and dimensionless
- **A2** PASS — A2 R2 and R3 complete and are shown to be materially stiff by measurement: their RK45/BDF evaluation ratios fall inside their preregistered bands, and R1's ratio falls inside its band showing it is NOT stiff
- **A3** PASS — A3 R5 ends as MAX_ITERATIONS with no metrics extracted and its partial trajectory preserved, through a genuine computational limit rather than a mocked failure
- **A4** PASS — A4 every regime's convergence state and its is_usable verdict are independent: R8 is CONVERGED and not usable, and R7 is CONVERGED and usable while its verification gate awards nothing
- **A5** PASS — A5 every declaration in R4 is refused by the domain before any solve, and the Scientific Core contains no CSTR-specific validity rule
- **A6** PASS — A6 the verification gate awards ANALYTICALLY_VERIFIED on at least one regime from the exact reaction-free invariant, and CROSS_SOLVER_VALIDATED on at least one regime from the independent algebraic steady state
- **A7** PASS — A7 the five failure-semantics cases A-E are each represented by a distinct combination of existing Core states, with no two collapsed
- **A8** PASS — A8 no regime is awarded NUMERICALLY_CONVERGED by a single solve; every such award comes from the tolerance ladder
- **A9** PASS — A9 R6a and R6b reach the same attractor despite three algebraic steady states existing, and the independent solver reports all three
- **A10** PASS — A10 every result carries a complete provenance record: model identity and version, solver identity and version, method, tolerances, every input as a Quantity, and the physics fingerprint

## Preregistered predictions

- **R1** met (convergence True, usable True, levels True, stiffness band True)
- **R2** met (convergence True, usable True, levels True, stiffness band True)
- **R3** met (convergence True, usable True, levels True, stiffness band True)
- **R5** met (convergence True, usable True, levels True, stiffness band True)
- **R6a** met (convergence True, usable True, levels True, stiffness band True)
- **R6b** met (convergence True, usable True, levels True, stiffness band True)
- **R7** met (convergence True, usable True, levels True, stiffness band True)
- **R8** met (convergence True, usable True, levels True, stiffness band True)

## What this does not show

- no inference of any kind: no Bayesian posterior, no MCMC, no variational inference, no parameter estimation
- no optimization, no acquisition function, no experiment selection
- no generic chemistry ontology, no generic uncertainty engine, no generic domain framework, no surrogate model
- no multiphysics coupling, no digital twin, no visualization
- no modification to T1, T2, T3, E1, E2, E3, S11 or any other frozen experiment, all of which are pinned by digest and are not re-run here
- no physical validation: nothing in K1 is compared against a measurement of a real reactor, and no claim about one is made
- no LLM-supplied numerical result: every number in the results is produced by the code in this repository from the declarations above