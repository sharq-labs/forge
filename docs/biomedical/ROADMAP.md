# FORGE BioBridge — Phased Research Roadmap

**Class:** Candidate FUTURE/LATER roadmap. Not an active work queue.  
**Date:** 2026-10-14. **Execution:** NOT AUTHORIZED. **Tests:** NOT RUN.

The only executable task queue is [ACTIVE_PLAN](../work/ACTIVE_PLAN.md). The Master Plan controls priority, the Completion Policy controls maturity and exceptions, and Genesis controls Discovery benchmark semantics. Every phase below is **conditional** and does not override those contracts.

## Outcome we are trying to prove

A *single frozen FORGE scientific reasoning and trust architecture* can, within a specifically bounded nonclinical biomedical problem:
1. represent the scientific question, physical/biological inputs and applicability limits;
2. propose at least two competing explanations where relevant;
3. preregister predictions and choose an informative admissible experiment or simulation;
4. execute qualified computations and compare them with independent observations;
5. distinguish verification from validation, report explicit uncertainty and model discrepancy;
6. detect contradiction/insufficient evidence and refuse correctly;
7. replay the full evidence trail on a second environment;
8. beat the strongest applicable matched-budget baseline if any **Mind/Discovery lift** is claimed.

A fit to synthetic data alone is *not* experimental validation and does not demonstrate clinical efficacy.

## Gate dependencies — non-bypassable

| Program prerequisite | What must be true |
|---|---|
| G0 Trust | Current code authority/certificate/gate state credibly resolved under Active Plan. |
| A1 Genesis-lite | Frozen preregistration, blinded baseline family, evaluator and compute budget. |
| A2 Minimal Mind | A1 success, policy-approved active-epic decision, calibrated/outcome-backed loop and baseline improvement. |
| B1 narrow real demo | Demonstrates refusal/correction and replay with real engineering providers; not replaced by BioBridge. |
| Biomedical activation | New owner decision placing a *specific* slice in Active Plan, with Completion Policy review/approval and expert reviewer. |

**Decision:** Documentation and candidate evaluation may be proposed now; developing a new domain capability is deferred. The date to activate is **not assigned**.

## Candidate research tracks (selection before development)

| Candidate | Testable research claim | Needed external evidence | Initial recommendation |
|---|---|---|---|
| BME-01 Benchtop thermal model | Temperature and energy-balance prediction for a controlled non-patient-facing lab setup inside a specified operating envelope | Independent thermometer/sensor trace, calibrated uncertainty, known heater/input boundary conditions | **Preferred first physical pilot** |
| BIO-01 Bounded reaction network | Distinguish a one-step and two-step kinetic mechanism under a frozen intervention schedule | Independent timed concentration observations; controlled parameter priors and measurement model | **Parallel research candidate, not simultaneous implementation** |

Select **one** based on data rights, available independent observations, solver applicability, expert reviewer, validation budget and ability to run a meaningful adversarial control. Do not announce both as supported capabilities.

## Proposed phases (relative gates, not deadlines)

| Phase | What gets produced | Pass gate / no-go condition | Permission |
|---|---|---|---|
| P0 — Pre-research | One-page problem statement; benchmark candidate; data-rights inventory; expert-review plan | Scope bounded and nonclinical; unknowns explicitly tracked | **Document-only now** |
| P1 — Benchmark contract | Freeze observable/QoI, inputs, units, reference data split, error metrics, failure modes, baseline and budget *before* seeing holdout | Independent expert review and owner approval; leakage controls valid | **After program gates** |
| P2 — Bounded execution | Domain model/adapter if approved; real provider path; applicability; refusal; provenance and replay | Verification, adversarial tests, no unsupported claims; no Core authority duplication | **Approved scoped epic/exception only** |
| P3 — External validation | Run held-out measurements; sensor uncertainty; model discrepancy; cross-environment reproducibility | Precommitted thresholds met, or explicit FAIL/UNKNOWN retained | **Research only** |
| P4 — Mind / Discovery transfer | Competing hypotheses, preregistered predictions, next-best experiment, falsification, full event log | Strong equal-budget baseline comparison, LLM ablation, scored calibration and independently checked refusal | **Only if A2/Genesis gates permit** |
| P5 — Research beta | Controlled distribution to selected nonclinical researchers | Installation/replay on other machine; external feedback; rights and licence audit | **Separate owner decision** |
| P6 — Product assessment | Assess demand, scientific liability, repeatability, commercialization and any medical-device regulatory perimeter | Go/no-go review; not automatic product or clinical launch | **Separate owner decision** |

## Preferred first pilot — BME-01

**Research question:** In a controlled, non-patient-facing benchtop enclosure, can an explicitly bounded thermal model predict selected sensor temperatures and uncertainty under a declared heating/cooling schedule?

- Inputs: geometry abstraction, material thermal properties, boundary conditions, heater power, timestamps, sensors with positions/calibration.
- Output/QoI: selected temperature-time series, max deviation from reference, energy balance and applicability envelope.
- Baseline: simple lumped thermal model or other admissible analytic reference; same data and budget.
- Verification: convergence / numerical equivalence / energy balance on well-defined cases.
- External validation: withheld observed sensor traces; data collection independent of calibration and ideally of the FORGE implementers.
- Refusal case: missing calibration, unspecified boundary condition or out-of-envelope temperature; no successful claim from incomplete evidence.
- Recorded outcome: supported only under existing Trust semantics and applicable evidence; otherwise REVIEW/REFUSED, never upgraded because the project is biomedical.

No patient contact, no physiological effect claim, no therapeutic endpoint, and no device-market authorization are within the pilot.

## Discovery transfer candidate — BIO-01

**Research question:** Can the existing Mind/Discovery route discriminate between two explicitly specified kinetic mechanisms using declared observations, within a bounded synthetic or nonclinical laboratory setting?

- No generation of unrestricted biological interventions or clinical hypotheses.
- Domain-provided mechanism grammar and allowed observables; no medical interpretations.
- Compare fixed-rule design, random admissible experiment design and strongest supported baselines.
- Separate parameter-fit evidence from held-out mechanistic discrimination; do not treat a good fitted curve as proof of causal mechanism.
- Report identifiability, parameter/model uncertainty, uncertainty in observation operators, disagreement and refusal.

## Exit artifacts for any approved pilot

- Problem and intended use statement; reproducible datasets or legally distributable sanitized examples.
- Frozen protocol, baseline and holdout split, with independent evaluator identified.
- Domain model applicability and non-applicability tests, plus provider/environment manifest.
- Provenance- and replay-bound run/report, with separate verification/experimental-validation sections.
- UQ and model discrepancy ledger with UNKNOWN preserved where unknown.
- Red-team suite designed to force false support if guards are removed.
- External-review disposition and explicit limitations.
- Owner decision on whether evidence warrants activating/advancing any scientific capability; **no automatic maturity promotion**.

## Explicit deferrals / anti-scope creep

- No patient-level records, imaging diagnosis, symptom triage, treatment recommendation, clinical trial guidance or drug-efficacy claim.
- No independent Biomedical Mind, biomedical evidence authority, new Trust verdict vocabulary or competing scientific state.
- No new provider, physiology model or dataset download just because it is available.
- No product pricing, clinical use or safety certification claims inferred from a research benchmark.
- No modifying G0/A1/A2/B1 milestone order without the proper source-of-truth change process.
