# E1 — Electrical quantitative verification

Config hash: `6dbf8febd6989b42fcfd58f4139ffa34330808018a1b427bb5042f43a38e847e`
Preregistration hash (config+truth): `3254c045fbc7dc11fdfbfca03bf4937bae2e769bd0d353cafc19e80fb21b356e`

## Solver verification (gate)

| Vs [V] | R2 [ohm] | solver V_mid [V] | analytic V_mid [V] | abs err [V] | rel err |
|---|---|---|---|---|---|
| 10 | 500 | 3.33333333333 | 3.33333333333 | 0.000e+00 | 0.000e+00 |
| 10 | 1000 | 5 | 5 | 0.000e+00 | 0.000e+00 |
| 10 | 1200 | 5.45454545455 | 5.45454545455 | 0.000e+00 | 0.000e+00 |
| 10 | 2000 | 6.66666666667 | 6.66666666667 | 0.000e+00 | 0.000e+00 |
| 10 | 2500 | 7.14285714286 | 7.14285714286 | 0.000e+00 | 0.000e+00 |
| 0.01 | 1000 | 0.005 | 0.005 | 0.000e+00 | 0.000e+00 |
| 2 | 900 | 0.947368421053 | 0.947368421053 | 0.000e+00 | 0.000e+00 |
| 5 | 1600 | 3.07692307692 | 3.07692307692 | 4.441e-16 | 1.443e-16 |

Worst relative error 1.443e-16 (tolerance 1.0e-09); |error|/sigma = 8.882e-14.

## Prior stage (no observations)

decision B | P(above)=0.643564 | EVPI=0.643564 | mean R2=1500 | sd=583.095

| action | EVSI | cost | net | predictive mean [V] | predictive sd [V] |
|---|---|---|---|---|---|
| measure_vmid_0V01 | -7.10543e-15 | 0.01 | -0.01 | 0.00575825 | 0.0500113 |
| measure_vmid_10V | 0.625494 | 0.15 | 0.475494 | 5.75825 | 1.06321 |
| measure_vmid_10V_premium | 0.643564 | 5 | -4.35644 | 5.75825 | 1.06204 |

## Campaign

state=paused pause=no_action_worth_buying stop_review=stop_not_assessed spent=0.15
- iteration 1: outcome=recommend_action selected=measure_vmid_10V verdict=valid admitted=['e1-run-ev-1']
- iteration 2: outcome=stop_proposal selected=- verdict=- admitted=[]
- prediction preceded observation: True (DECISION_RECOMMENDED seq [3, 16] < EXECUTION_STARTED seq [5])

## Posterior after campaign

decision A | P(above)=1 | EVPI=9.19248e-07 | mean R2=1337.26 | sd=27.3251

## Terminal decision

SRIA: **A** | oracle: **A** | correct: **True**

## Certificate assumptions

| proposition | status | basis |
|---|---|---|
| circuit topology (two-resistor divider, ideal source) | ASSERTED_FOR_BENCHMARK | declared in the preregistered configuration |
| solver/model equations (linear resistive DC via MNA) | ANALYTICALLY_CHECKED | agreement with the closed-form divider relation at 8 preregistered points, worst relative error 1.443e-16 |
| observation mapping (y measures node_voltage:mid) | ASSERTED_FOR_BENCHMARK | declared observation model |
| observation noise (Gaussian, declared sigma) | ASSERTED_FOR_BENCHMARK | benchmark-injected synthetic noise, honestly labelled; the solver itself is deterministic |
| prior (uniform over the frozen R2 grid) | ASSERTED_FOR_BENCHMARK | preregistered before any scored observation |
| terminal utility / loss matrix | ASSERTED_FOR_BENCHMARK | preregistered; asymmetric with indifference at P=0.8 |
| acquisition cost model (declared per-action costs) | ASSERTED_FOR_BENCHMARK | preregistered; no fitted cost model in E1 |
| computational failure probability p_cf = 0 | ASSERTED_FOR_BENCHMARK | declared, not measured. A dense LU on a well-conditioned 3x3 MNA system did not fail in this experiment, but no failure corpus exists for this domain and M2 failure learning remains INSUFFICIENT_DATA. Every candidate score carries the factor (1 - p_cf) = 1 on this assertion |
| cost-to-utility tradeoff lambda = 1.0 (declared benchmark cost units per unit of terminal loss) | ASSERTED_FOR_BENCHMARK | preregistered exchange rate with no external referent. It sets which actions are affordable and therefore drives selection directly: at lambda = 1.0 the premium instrument has EVSI 0.644 against cost 5.0 and loses, while a campaign valuing the decision ~10x higher would buy it. The ordering of actions by information is independent of lambda; the ordering by net value is not |
| support/transport: IN_DOMAIN_FOR_THIS_VERIFICATION | VERIFIED | the decision QoI is the inferred parameter itself; the observed operating conditions are exactly the candidate action set; the solver is verified across the full prior support; no extrapolation beyond verified conditions occurs |
| posterior arithmetic (normalized, batch==sequential, order-invariant) | VERIFIED | tests over the exact grid update |
| EVSI bounds (0 <= EVSI <= EVPPI = EVPI) | VERIFIED | tests; EVPPI(R2) = EVPI because R2 is the complete latent decision-relevant state |
| numerical error negligible vs observation noise | VERIFIED | worst |solver-analytic| / smallest sigma = 8.882e-14 |

**E1 VERIFIED END-TO-END**