# E3 — Adequacy evidence vs parameter EVSI

Config hash: `3a812af7cf01cf21b007c814efebbfed8ea24830c1153f7f8b56c57c441ba3e2`
Preregistration hash: `77ac74aab7fe94151dd0abf34b0b96bd4d24d44dafd45e67025b999d256db1f1`

A measurement may have almost zero value for estimating theta and still be mandatory evidence for deciding whether the model containing theta deserves certification. E3 does not fake the former to justify the latter.

## World A — well specified

After calibration: decision **A**, P(above)=1, sd=14.4014 Ω, EVPI=1.046e-50.

| candidate | family | parameter EVSI | cost | net |
|---|---|---|---|---|
| `adequacy_probe_16V` | validate | 1.045e-50 | 0.15 | -0.1500 |
| `adequacy_probe_20V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `adequacy_probe_22V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `adequacy_probe_24V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `adequacy_probe_28V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `parameter_repeat_10V` | characterize | 4.181e-51 | 0.15 | -0.1500 |

- EVSI-only review: **stop_not_assessed** (criterion `none registered`), actions executed: none
- Obligation-aware review (pre): **stop_not_assessed** (criterion `adequacy:constant_r:declared_range`, arbiter `inconclusive`)

| probe executed | Vs [V] | parameter EVSI | admitted | reason |
|---|---|---|---|---|
| `adequacy_probe_16V` | 16 | 1.045e-50 | True | `SATISFY_ADEQUACY_OBLIGATION` |
| `adequacy_probe_22V` | 22 | 1.046e-50 | True | `SATISFY_ADEQUACY_OBLIGATION` |
| `adequacy_probe_28V` | 28 | 1.046e-50 | True | `SATISFY_ADEQUACY_OBLIGATION` |

- Obligation status: **completed** | adequacy: **acceptable_for_declared_scope**
- Obligation-aware review (post): **stop_approved** (arbiter `valid`)
- `POSTERIOR_DECISION = A` | `SCIENTIFIC_CERTIFICATION = ELIGIBLE` | `reason = ADEQUACY_ACCEPTABLE_FOR_DECLARED_SCOPE` | `disposition = CERTIFICATION_ELIGIBLE`

## World B — misspecified

After calibration: decision **A**, P(above)=1, sd=14.4014 Ω, EVPI=1.046e-50.

| candidate | family | parameter EVSI | cost | net |
|---|---|---|---|---|
| `adequacy_probe_16V` | validate | 1.045e-50 | 0.15 | -0.1500 |
| `adequacy_probe_20V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `adequacy_probe_22V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `adequacy_probe_24V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `adequacy_probe_28V` | validate | 1.046e-50 | 0.15 | -0.1500 |
| `parameter_repeat_10V` | characterize | 4.181e-51 | 0.15 | -0.1500 |

- EVSI-only review: **stop_not_assessed** (criterion `none registered`), actions executed: none
- Obligation-aware review (pre): **stop_not_assessed** (criterion `adequacy:constant_r:declared_range`, arbiter `inconclusive`)

| probe executed | Vs [V] | parameter EVSI | admitted | reason |
|---|---|---|---|---|
| `adequacy_probe_16V` | 16 | 1.045e-50 | True | `SATISFY_ADEQUACY_OBLIGATION` |
| `adequacy_probe_22V` | 22 | 1.046e-50 | True | `SATISFY_ADEQUACY_OBLIGATION` |
| `adequacy_probe_28V` | 28 | 1.046e-50 | True | `SATISFY_ADEQUACY_OBLIGATION` |

- Obligation status: **completed** | adequacy: **model_space_inadequate**
- Obligation-aware review (post): **stop_rejected** (arbiter `invalid`)
- `POSTERIOR_DECISION = A` | `SCIENTIFIC_CERTIFICATION = NOT_CERTIFIABLE` | `reason = MODEL_SPACE_INADEQUATE` | `disposition = MODEL_REVISION_REQUIRED`

## Controls

- **1 no obligation:** review `stop_not_assessed`, acquired nothing.
- **2 outstanding:** routed `adequacy_probe_16V`.
- **3 already satisfied:** next_probe = `None`; 3 of 5 catalogue probes executed; never required: ['adequacy_probe_20V', 'adequacy_probe_24V'].
- **4 budget:** shared → `unresolved_budget_infeasible` / `REQUIRED_ADEQUACY_EVIDENCE_BUDGET_INFEASIBLE`; reserved → `completed`.
- **5 execution invalid:** obligation `unresolved_execution_failure`, adequacy scored `False`, disposition `execution_repair_required`.
- **6 model inadequate:** obligation `completed`, certification `MODEL_SPACE_INADEQUATE`.

## Adversarial injections

| # | attempt | caught | catcher |
|---|---|---|---|
| A | give the adequacy probes a positive information value | yes | identical UtilityEngine scores under both policies |
| B | hold STOP_APPROVED while a mandatory obligation is outstanding | yes | StopReview.__post_init__ (frozen M5.1 structural guard) |
| C | mark the obligation satisfied because the action was attempted | yes | ProbeRecord.is_obligation_evidence |
| D | treat a discharged obligation as a passing model | yes | certify_campaign (obligation and adequacy are separate arguments) |
| E | consume the budget on parameter actions and hide the consequence | yes | BudgetLedger.affordable(family=VALIDATE) + explicit reporting |
| F | discharge the obligation with a cheaper, different action | yes | ObligationLedger.record_probe condition binding |
| G | commit a predictive after its observation exists | yes | E2 CommitmentLedger.commit (sealed ledger) |
| H | let posterior confidence, EVPI or EVSI reach the certification gate | yes | certify_campaign signature |

## What the frozen stack did on its own

| capability | campaign-native |
|---|---|
| adequacy acquisition is campaign native | **no** |
| stop refusal is campaign native | **yes** |
| validation budget fence is campaign native | **yes** |

Adequacy probes executed by any CampaignRunner pass: `none`. Every probe in this run was executed by the experiment-local adapter, which is why the verdict is bounded below the obligation policy's own result.

## Strongest supported claim

On the computational Electrical benchmark, E3 verified that a finite preregistered adequacy obligation can remain scientifically binding after parameter-learning EVSI has collapsed, without assigning fake parameter information value to adequacy probes. The existing frozen campaign stack genuinely refused scientific STOP and protected validation budget, but it did not natively acquire the required adequacy evidence; that acquisition required an experiment-local adapter.

## Architecture gaps retained

1. **campaign-scoped obligation vocabulary is missing** — ObligationSet is evaluated per evidence record; placing the adequacy obligation there yields arbiter INCONCLUSIVE, admitted=False and belief_size=0 — it blocks all admission
2. **_propose_stop has no resolution branch routing a non-approved stop review to the evidence that would resolve the obligation** — the runner pauses with NO_ACTION_WORTH_BUYING whatever the review returns; no runner pass executed any adequacy probe
3. **no supported campaign initialization path from previously admitted evidence / assurance state** — without hand-building a CampaignCheckpoint the stop review short-circuits at 'obligations were never assessed' and never reaches the registered criterion
4. **adequacy probes still rely on the experiment-local E2 predictive commitment seam** — a probe cannot honestly satisfy an adequacy obligation if its prediction was not committed before observation, and nothing in src/ can hold that commitment

Next step: **CAMPAIGN OBLIGATION ROUTING INTEGRATION** — connect the four seams above minimally so that a campaign-scoped obligation can be declared, seen by the existing liveness router, resolved by the existing execution path, and discharged only by evidence carrying a pre-observation predictive commitment. Not a generic validation subsystem, and not a claim that a CampaignObligation type alone closes the gap — three of the four gaps are integration, not vocabulary. Not started.

**E3 PARTIALLY VERIFIED**