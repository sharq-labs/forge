# E2 — Model adequacy / predictive surprise

Config hash: `d6add0d816563ea65f70473cf5cdc926dd7fa17ebff6769790879f8de057ab13`
Preregistration hash (config+truth): `6b93e70dac164f286170b3218943062602d47013bbdb83092a102e46a496b216`

**v1.1.0** — supersedes config `dbe7c538e6f8af198be14bd6863d91249b748969c69b27c308c7df38b0275bce`. The v1.0.0 aggregate combined per-condition tail probabilities with Fisher's method and referred the result to χ² on 2N degrees of freedom, which assumes independence the conditions do not have. That reference is withdrawn as invalid; see *Why the aggregate had to change* below. Per-condition statistics, thresholds, K_min, the challenge set, the seed, the grid and the hidden law are unchanged.

## Solver verification (gate)

| Vs [V] | R2 [Ω] | solver V_mid [V] | analytic V_mid [V] | rel err |
|---|---|---|---|---|
| 4 | 500 | 1.33333333333 | 1.33333333333 | 0.000e+00 |
| 4 | 1378 | 2.31791421362 | 2.31791421362 | 0.000e+00 |
| 10 | 1000 | 5 | 5 | 0.000e+00 |
| 10 | 1378 | 5.79478553406 | 5.79478553406 | 0.000e+00 |
| 16 | 1500 | 9.6 | 9.6 | 1.850e-16 |
| 20 | 1378 | 11.5895710681 | 11.5895710681 | 0.000e+00 |
| 24 | 2000 | 16 | 16 | 0.000e+00 |
| 28 | 1450 | 16.5714285714 | 16.5714285714 | 0.000e+00 |
| 28 | 2500 | 20 | 20 | 0.000e+00 |

Worst relative error 1.850e-16 (tolerance 1.0e-09); |error|/σ = 3.553e-14.

- **Proves:** IMPLEMENTATION VERIFICATION: the MNA path reproduces the closed-form linear resistive DC relation to machine precision
- **Does not prove:** MODEL ADEQUACY: agreement with the equations of the assumed family says nothing about whether that family describes the hidden world. E2 exists precisely to show these can diverge, and in the scored run they do

## Posterior, stage by stage (scored misspecified run)

- prior — decision B | P(above)=0.648379 | mean=1500 Ω | sd=578.792 Ω | H=5.99396 nats | EVPI=6.484e-01
- after calibration — decision A | P(above)=1 | mean=1399.99 Ω | sd=14.4014 Ω | H=2.47672 nats | EVPI=1.046e-50
- after challenge — decision A | P(above)=1 | mean=1476.6 Ω | sd=6.09477 Ω | H=1.61691 nats | EVPI=0.000e+00

Every line above reads `p(R2 | data, M_const)`. The posterior gets **sharper** across the challenge phase while the family's predictions are failing — that divergence is the finding, not an anomaly.

## Precommitted challenge predictions and their surprise

| condition | Vs [V] | predictive mean ± sd [V] | observed [V] | z | two-sided tail | NLPD | level |
|---|---|---|---|---|---|---|---|
| `challenge_vmid_04V` | 4 | 2.33326 ± 0.05099 | 2.24069 | -1.816 | 6.943e-02 | -0.409 | consistent |
| `challenge_vmid_10V` | 10 | 5.83316 ± 0.05590 | 5.80272 | -0.544 | 5.861e-01 | -1.817 | consistent |
| `challenge_vmid_16V` | 16 | 9.33305 ± 0.06403 | 9.50360 | +2.663 | 7.735e-03 | 1.718 | moderate |
| `challenge_vmid_20V` | 20 | 11.66632 ± 0.07071 | 11.93492 | +3.799 | 1.456e-04 | 5.484 | moderate |
| `challenge_vmid_24V` | 24 | 13.99958 ± 0.07810 | 14.41622 | +5.334 | 9.583e-08 | 12.597 | extreme |
| `challenge_vmid_28V` | 28 | 16.33284 ± 0.08603 | 16.87720 | +6.328 | 2.485e-10 | 18.487 | extreme |

Joint log score S = 20.296 against a simulated null of -8.533 ± 1.722 (99th pct -3.167) over 20000 posterior-predictive draws → **p_joint = 5.000e-05** (Monte Carlo floor); n_extreme = 2, n_moderate = 2.

*Deprecated v1.0.0 diagnostic:* Fisher X² = 110.350 on 12 df → χ²-independent p = 5.1024e-18, versus 4.9998e-05 against the correctly simulated null. The χ²(2N) reference assumes independence these conditions do not have and is not used to decide anything.

**MODEL_SPACE_INADEQUATE**

2 of 6 preregistered conditions fell in the far tail of their own pre-observation predictive (threshold 0.0001), AND the complete challenge vector scored 20.296 against a simulated null of -8.533 +/- 1.722, giving p_joint = 5.000e-05 (Monte Carlo floor: 0 of 20000 null draws were as extreme, so the true value is below 5.0e-05). The joint score already allows the family to move theta anywhere its own calibration posterior permits, so this is not something a shared-parameter shift can explain away.

## Why the aggregate had to change (v1.0.0 → v1.1.0)

The six challenge conditions are conditionally independent given θ and share ONE calibration posterior. Marginalizing it leaves them positively dependent — exact correlations 0.088 to 0.625, largest between exactly the high-drive conditions that carry the most weight in any aggregate.

| Vs [V] | 4 | 10 | 16 | 20 | 24 | 28 |
|---|---|---|---|---|---|---|
| **4** | 1.0000 | 0.0877 | 0.1225 | 0.1387 | 0.1507 | 0.1596 |
| **10** | 0.0877 | 1.0000 | 0.2794 | 0.3162 | 0.3436 | 0.3639 |
| **16** | 0.1225 | 0.2794 | 1.0000 | 0.4417 | 0.4799 | 0.5084 |
| **20** | 0.1387 | 0.3162 | 0.4417 | 1.0000 | 0.5432 | 0.5754 |
| **24** | 0.1507 | 0.3436 | 0.4799 | 0.5432 | 1.0000 | 0.6251 |
| **28** | 0.1596 | 0.3639 | 0.5084 | 0.5754 | 0.6251 | 1.0000 |

Measured against the true null, Fisher's statistic has 1.75× the variance the χ²(2N) reference assumes, and rejects at nominal 5% 8.2% of the time. Reference verdict: **ANTI-CONSERVATIVE** — v1.0.0's aggregate p-values were too small.

Threshold robustness: all three control verdicts are unchanged for any α_joint from 1e-4 to 1e-2 (`True`).

## Controls

| control | truth | verdict | n_extreme | joint log score | p_joint |
|---|---|---|---|---|---|
| A — well specified | `A_well_specified` | **model_adequacy_acceptable** | 0 | -10.536 | 9.213e-01 |
| B — one isolated outlier | `B_single_outlier` | **model_adequacy_not_established** | 1 | 25.129 | 5.000e-05 |
| C — systematic misspecification | `C_systematic_misspecification` | **model_space_inadequate** | 2 | 20.296 | 5.000e-05 |

**D — computational failure:** critic `fail`, arbiter `invalid`, admitted `False`, posterior unchanged `True`. Failure path → `execution_repair_required`; adequacy path → `model_revision_required`. Distinct: `True`.

**E — confidence is not adequacy:** P(decision) = 1.000000, posterior sd = 6.095 ohm, EVPI = 0.000e+00, best EVSI = 0.000e+00. Every one of these is computed INSIDE the family under suspicion, so none of them is evidence that the family is right, and none is an argument the gate can hear

## Terminal decision vs scientific certification

- `POSTERIOR_DECISION = A`
- `SCIENTIFIC_CERTIFICATION = NOT_CERTIFIABLE`
- `reason = MODEL_SPACE_INADEQUATE`
- `disposition = MODEL_REVISION_REQUIRED`

the decision preferred by p(R2 | data, M_const) — a statement conditional on the family, not about the world

## Adversarial injections

| # | attempt | caught | catcher |
|---|---|---|---|
| A | register a predictive for a condition after its observation exists | yes | CommitmentLedger.commit (ledger sealed) |
| B | invalidate an observation because the model predicted it poorly | yes | E2Harness.assess (computational checks only) + the admission chain |
| C | override MODEL_SPACE_INADEQUATE with a very sharp posterior | yes | certify() signature — posterior strength is not a parameter |
| D | override MODEL_SPACE_INADEQUATE with EVSI at the floor | yes | certify() signature — EVSI is not a parameter |
| E | let the hidden law influence the predictive or the adequacy verdict | yes | module boundary (transitive AST import test) + this recomputation |
| F | edit a committed predictive after its observation was executed | yes | PredictiveCommitment.verify_integrity via score_commitments |

## Certificate assumptions

| proposition | status | basis |
|---|---|---|
| circuit topology (two-resistor divider, ideal source) | ASSERTED_FOR_BENCHMARK | declared in the preregistered configuration; E1-derived |
| ASSUMED MODEL FAMILY: R2 is a single condition-independent constant | ASSERTED_FOR_BENCHMARK | declared before the run as the family inference is conditional on. This is a PROPOSITION ABOUT THE WORLD and E2 tested it: it is MODEL_SPACE_INADEQUATE |
| SOLVER IMPLEMENTATION OF THAT FAMILY (linear resistive DC via MNA) computes what the family specifies | ANALYTICALLY_CHECKED | agreement with the closed-form divider relation at 9 preregistered points spanning the full challenge range, worst relative error 1.850e-16. NOT THE SAME PROPOSITION as the row above: this one is about code agreeing with equations, that one is about equations agreeing with the world, and in this run the first holds while the second fails |
| Electrical solver equations (Ohm/KCL, MNA assembly) | ANALYTICALLY_CHECKED | verified against an independently derived KVL/KCL closed form the solver did not produce |
| observation mapping (y measures node_voltage:mid) | ASSERTED_FOR_BENCHMARK | declared observation model |
| noise model (Gaussian, declared sigma, additive) | ASSERTED_FOR_BENCHMARK | benchmark-injected synthetic noise, honestly labelled; the solver itself is deterministic. Draws depend on (action_id, repeat) only, so controls share them exactly |
| prior (uniform over the frozen R2 grid) | ASSERTED_FOR_BENCHMARK | preregistered before any scored observation |
| terminal utility / loss matrix | ASSERTED_FOR_BENCHMARK | preregistered; asymmetric with indifference at P=0.8 |
| cost model (declared per-action costs) | ASSERTED_FOR_BENCHMARK | preregistered; no fitted cost model in E2 |
| computational failure probability p_cf = 0 | ASSERTED_FOR_BENCHMARK | declared, not measured, for a dense LU on a well-conditioned 3x3 MNA system. Control D shows what a genuine computational failure does instead of assuming it cannot happen |
| cost-to-utility tradeoff lambda = 1.0 | ASSERTED_FOR_BENCHMARK | preregistered exchange rate with no external referent. E2 does not let it steer: the action schedule is frozen, so lambda affects reported net value and nothing that was executed |
| support/transport: IN_DOMAIN_FOR_THIS_VERIFICATION | VERIFIED | the solver is verified across the full prior support at every voltage that is measured or predicted, so no numerical extrapolation occurs. Note this is transport of the SOLVER, and is independent of — and in this run contradicted by — the adequacy of the model family at those same conditions |
| predictive adequacy rule (preregistered, v1.1.0) | VERIFIED | two-sided marginal predictive tail per condition (each EXACTLY Uniform(0,1) under the null), plus a JOINT log score over all 6 conditions calibrated by 20000 posterior-predictive draws. Strongest verdict requires n_extreme >= 2 AND p_joint < 0.0001. Controls A and B exercise both non-firing branches |
| aggregate reference distribution accounts for dependence between challenge conditions | VERIFIED | the conditions share one calibration posterior and are positively dependent (exact off-diagonal correlations 0.088 to 0.625). v1.0.0 combined the tails with Fisher and referred them to chi-square(2N), which assumes independence and is anti-conservative here; v1.1.0 replaces it with the joint score under a simulated null. Superseded config hash dbe7c538e6f8af198be14bd6863d91249b748969c69b27c308c7df38b0275bce |
| internal null (Vs = 10 V) discriminates against a condition-independent harness offset | ASSERTED_FOR_BENCHMARK | the synthetic grader law was CONSTRUCTED to vanish at the calibration condition, so a clean result there is expected under this benchmark's failure mode and separates it from a constant offset. It does NOT exclude other fault mechanisms: a condition-dependent or drive-scaling instrument fault would also leave this condition clean. One alternative is discriminated against, not all of them |
| prediction preceded observation | VERIFIED | content-hashed predictive artifacts sealed in a hash-chained ledger, sequence-ordered before every challenge execution, and cross-recorded in the campaign event log; a post-hoc commitment raises rather than being accepted |
| posterior arithmetic (normalized, order-invariant) | VERIFIED | tests over the exact grid update, inherited from E1 |
| grader truth availability | GRADER_ONLY | the misspecified law lives in e2_truth and is unreachable from e2_config, e2_model and e2_adequacy, checked transitively by AST and by a runtime recomputation under an altered law |
| numerical error negligible vs observation noise | VERIFIED | worst |solver-analytic| / smallest sigma = 3.553e-14 |

**E2 MODEL-INADEQUACY DETECTED CORRECTLY**