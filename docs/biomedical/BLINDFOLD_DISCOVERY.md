# FORGE BioBridge — Biomedical Blindfold & Discovery

**Status:** FUTURE/LATER — preregistration design only, NOT AN ACTIVE EPIC.  
**Date:** 2026-10-14  
**Scientific authority:** [FORGE Genesis](../discovery/FORGE_GENESIS.md) (§§5, 8, 10–12, 17, 18, 22); this document **does not modify** Genesis scoring, create a second Blindfold, or authorize new biomedical implementation.  
**Verification:** Static documentation design. **NOT RUN**. No biomedical benchmark success, medical finding, performance lift, certified discovery, or clinical result has been established.

## 1. Goal and precise scientific question

**Goal:** Eventually test whether the *same frozen, domain-general FORGE Mind* can recover or discriminate **bounded nonclinical biological / bio-kinetic mechanisms** from partially observed data, design informative observations, and refuse when mechanisms are non-identifiable — **without target-specific Mind code or privileged access to answers**.

The evaluated claim is **transfer of scientific reasoning**, not the discovery of a new medicine, diagnosis, treatment, causal clinical mechanism, or a novel biological law. Biomedical terminology is not evidence of biomedical maturity.

### Relationship to other FORGE concepts

| Component | Existing canonical owner | Biomedical role | Non-negotiable boundary |
|---|---|---|---|
| FORGE Mind | Existing `sria.decision` / Genesis orchestration over scientific state | Select among admitted, bounded actions; update hypotheses after evidence | No second `BioMind` or self-awarded authority |
| Discovery | Existing `scientific.discovery`, canonical `sria.decision.Hypothesis`, qualified proposal adapters | Suggest equations or mechanism structures with typed, testable predictions | Proposed ≠ supported, fit ≠ mechanism |
| Blindfold | Existing `engcore.blindfold` | Hidden, independently scoreable synthetic/transformed worlds, refusal traps | **One** benchmark/evaluator authority, not biomedical clone |
| Solvers / models | Existing numerical and provider architecture; future approved Domain Pack | Execute **in-silico** bounded models and observables | A solver result is not a real biological measurement |
| Trust / evidence / UQ | Existing applicability, evidence, SRIA/claims, replay and certificates | Distinguish verification, model limitations and independent empirical evidence | Neither Mind nor domain pack can grant validation or clinical support |
| External evaluator | Independent expert using separate evaluation service | Keeps hidden targets, scores and adjudicates | Current in-process/escrow paths are not presumed leakage-proof |

**Genesis §17.1** expressly defers therapeutics, recommends *bounded mechanistically checkable bio-kinetics*, and requires separate clinical/therapeutic evidence semantics for future clinical claims.

## 2. Candidate Blindfold research tasks

These are **proposals**, not pre-existing verified biomedical benchmarks. Reuse Genesis task families rather than minting new maturity levels.

| ID | Genesis family | Hidden task | What the Mind must prove | Required refusal / negative control |
|---|---|---|---|---|
| BB-01 | G1 Mechanism recovery | A bounded abstract nonclinical reaction network observed through time-series outputs | Recover an **observationally equivalent** candidate mechanism within an explicitly fixed grammar | Multiple equivalent mechanisms → `INDISTINGUISHABLE`, not fabricated certainty |
| BB-02 | G3 Competing mechanisms | Two or more rival toy kinetic mechanisms with overlapping fit to training data | Choose the **most discriminating permitted in-silico observation** before seeing its result | No observation separates rivals → `INSUFFICIENT_EVIDENCE` |
| BB-03 | G4 Anonymous primitives | Artificially named reaction/transport primitives with known generic admissibility rules | Select a minimal admissible subset without relying on biological labels | Invalid primitive combination → reject; guessing familiar names scores poorly |
| BB-04 | G5 Synthetic / trap worlds | Reparameterized, anonymized or transformed nonclinical model world in which a textbook shortcut fails | Reason from observations and stated primitives rather than memorized scientific facts | Historical-textbook answer contradicting hidden world → FAIL |
| BB-05 | G6 No-solution / insufficiency | Missing observables, confounded parameters or a non-identifiable model family | Declare unresolved / refuse without bogus posterior precision | Unsupported `SUPPORTED` or invented uncertainty → FAIL |
| BB-06 | G2 Coupled recovery (**only later**) | Tiny bounded heat-transfer + abstract kinetics model, with predeclared interface semantics | Verify jointly coupled inference and preserve balance/units | Numerically converged but inconsistent conservation → FAIL |

**First recommended slice:** BB-01 + BB-02 + BB-05, on a small **abstract, synthetic nonclinical model**. BB-04 is a required robustness check once an admissible task family exists; BB-06 is delayed until coupled-verification support is demonstrated. None requires designing real-world biological experiments or patient data.

## 3. Controlled evaluation loop

```text
Third-party benchmark author
  └─ freezes hidden synthetic world + admissible primitive grammar
         ↓ [separate evaluator/escrow, sealed answer]
Mind code, allowed tools and baseline policies FROZEN by digest
         ↓
Mind receives only public task card + authorised observations
         ↓
Typed hypothesis proposals (mechanism/parameters/uncertainty)
         ↓
Qualified forward-model / permitted observation request
         ↓
Prediction committed BEFORE observation result
         ↓
Sealed observation returned; falsification & evidence admission
         ↓
Belief update + dependency invalidation + next action / refusal
         ↓
Independent external scorer and immutable replay bundle
```

- **No blindfold by declaration:** Synthetic answer keys, scoring code, hidden parameters and evaluator permissions must be kept outside the proposer/Mind trust boundary.
- Current `engcore.blindfold` documents `SECURITY_BOUNDARY_NOT_PROVEN` for development transports; no run may count as proven novel discovery on an unproven boundary.
- A mere synthetic task **is not empirical validation**. Independent nonclinical laboratory data, if later available and lawfully admitted, are assessed via a separate empirical-validation protocol, never as hidden synthetic truth.
- Keep the event sequence immutable: proposal, pre-observation prediction, action, result, evidence admission, falsifier verdict, belief revision, refusal/stop and costs. A replay must not invoke an AI proposer again.

## 4. Anti-leakage and anti-shortcut conditions

Before formal evaluation, preregister and freeze:

1. **One common admissible primitive grammar** across tasks, not tailored to the hidden mechanism; fixed complexity and budget limits.
2. **Mind code and prompt/model versions by digest**, evaluator/source code external to the tested authority and hidden target kept sealed.
3. **Task authorship and scoring independently reviewed**, ideally by a domain researcher who did not build the Mind.
4. **Isolation / no arbitrary search into hidden material**; enforce permitted data and API boundaries. Any non-proven technical isolation must be honestly labeled.
5. **Anti-historical transforms**, anonymous labels, altered admissible constants/relationships, confounded/indistinguishable and insufficient-information traps.
6. **Precommitted scoring**, positive/negative controls, allowed observation schedule, uncertainties and cost model; do not edit criteria after learning outcomes.
7. **Multiplicity and selection records** for all proposed candidates, including failed or dropped ones; no winner-only reporting.
8. **Separate evaluation dataset and independent expert review**; document contamination risk from published benchmark material and LLM training.

A high score due to explicit answer encoding, information leakage or a weak baseline is marked **INVALID_BENCHMARK**, not Discovery success.

## 5. Baselines and statistical evidence

Use the exact Genesis §10 statistical and baseline policy, not a more permissive biomedical standard.

| Task class | Strong applicable equal-budget comparators |
|---|---|
| Dynamics / mechanism inference | PySINDy on same frozen primitive library where qualified; structured enumeration and valid random search |
| Competing explanations | Rival enumeration plus fixed discriminating observation policy with **executed** forward predictions; random admissible actions |
| Experiment selection | Random admissible design, space-filling design, BO/BoTorch where applicable and qualified |
| Anonymous primitives | Greedy forward selection over same primitive library; random subsets |
| Insufficient evidence | Constant refusal/insufficient-evidence controls **plus** an actually competent task-specific comparator |
| AI-worker contribution | Full Mind versus same Mind with non-LLM proposer (required ablation), plus model-swap arm |

- At least **30 generated instances per formal benchmark class per domain** for a rate claim.
- At least **20 seeds** when stochastic search is material, with confidence intervals and **equal compute/provider-call budgets**.
- Strongest applicable baseline, not `always_refuse` or `careful` alone, is the primary bar.
- Pilot the **10-campaign compute rung** first, record measured runtime/cost/failure variance, then estimate and obtain owner budget approval. Scope can shrink; statistical claims cannot ignore the required floor.
- Report task-specific held-out success, false support/refusal, correct `INDISTINGUISHABLE` classification, predictive calibration (proper scoring rule), falsification quality, information gained per provider call, replay success, and ablation effects.
- Claims of `novel biological discovery` or general domain competence are **not** earned merely through passing this suite.

## 6. Specific scientific traps

| Trap | Risk | Required handling |
|---|---|---|
| Two mechanisms fit same training curve | Identifiability failure | Keep rivals or `INDISTINGUISHABLE`; don't invent a mechanism |
| Hidden transformations change known relationships | Memorization / historical leakage | Score on hidden world, not textbook correctness |
| Parameters are strongly correlated | Unjustified precise posterior | Record dependencies, or UNKNOWN |
| Poorly aligned sample timing / observation operator | False model mismatch | Declare observation mapping, uncertainties and refusal if invalid |
| Numerical solver diverges | Wrongly interpreted as biological falsification | Classify computational failure separately |
| Synthetic network passes every test | Overstated empirical or clinical evidence | Synthetic benchmark claim only |
| Candidate submitted after observation/result | Outcome leakage | Refuse/penalize invalid timing; use pre-result digests |
| Early eliminated rival later becomes plausible | Stale dependency / incorrect pruning | Reinstate or mark unresolved under existing evidence and dependency rules |

## 7. Research-to-real-world evidence boundary

**Track S — synthetic Blindfold:** assesses controlled reasoning competence, robustness to transformations and correct refusal. No human samples, patient records, medical device or clinical claims.

**Track E — independent empirical validation (separately approved):** evaluates a **bounded nonclinical** model against legitimately obtained held-out laboratory/benchtop observations; must disclose observation method, measurement uncertainty, parameter fitting and model discrepancy. This track tests domain-model validity and does not prove autonomous discovery by itself.

**Track C — clinical/therapeutic use: NOT AUTHORIZED:** diagnoses, prognosis, treatment choice, drug effectiveness or patient decisions need distinct intended-use, clinical-evidence, safety, privacy, ethics and regulatory contracts. This is not an automatic next task when S/E pass.

References: [BioBridge Evidence & Safety](EVIDENCE_AND_SAFETY.md), [Genesis](../discovery/FORGE_GENESIS.md) §17.1, [Completion Policy](../project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md).

## 8. Suggested roadmap placement (not authority to execute)

| Proposed research stage | Preconditions | Proposed output | Status |
|---|---|---|---|
| DB0 — paper design | None; no new implementation | Task matrix and candidate scoring policy | **DOCUMENTED ONLY** |
| DB1 — preregistration proposal | G0/A1 gates and independent reviewer identified | Frozen candidate grammar, hidden-task creation method, baselines, compute plan | **DEFERRED** |
| DB2 — approved synthetic trial | Relevant Genesis/Mind gates and owner/Completion Policy approval | Auditable limited synthetic run with correct refusal and ablation | **DEFERRED** |
| DB3 — held-out reasoning transfer | Mind frozen; independent evaluator with proven boundary | Generalization test with no generic Mind patch; negative results preserved | **DEFERRED** |
| DB4 — optional empirical route | Separate explicit nonclinical approval and data rights | Physical/biological measurement comparison, independent validation | **DEFERRED** |
| DB5 — research beta | Independent evidence, package/replay verification, owner decision | External researcher pilot and limitations report | **DEFERRED** |

**No automatic biomedical start:** the current [Active Plan](../work/ACTIVE_PLAN.md) schedules G0 → A1 → A2 → B1, and the [Completion Policy](../project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md) pins `battery.thevenin_1rc` as active completion epic. The Master Plan lists bounded biomedical and therapeutics as LATER.

## 9. Go / no-go and acceptance record

A candidate formal BioBridge Blindfold run is **GO** only with:

- authorized narrow nonclinical scope and current program gate clearance;
- no duplicate scientific authorities, and explicit owner/active-epic permission for any new capability;
- qualified domain reviewer and independent held-out evaluator;
- proven or honestly labeled evaluator isolation, frozen task/method digests, strong baselines;
- predeclared outcome/observation semantics, admissible compute budget and no non-public medical data;
- replayable results, all attempts and failures retained, and uncertainty/false support reported.

**NO-GO** if hidden targets leak, score depends on biologically meaningful names rather than permitted observations, models are non-identifiable without uncertainty/refusal, the benchmark lacks credible baseline comparison, or any result is described as clinical validity / therapeutics.

**Evidence status:** Proposed tests and requirements only. **NOT RUN; NOT VALIDATED; NOT PRODUCTION_READY.**
