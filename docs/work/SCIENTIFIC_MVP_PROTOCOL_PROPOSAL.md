# Scientific MVP evaluation protocol — proposed, not approved

Prepared 2026-10-28 against `dd567d53d2444950f57ffaeb9903c74d7c38f04d`.
This is a reviewable design, not an executable queue or scientific result.
Execution remains in ACTIVE_PLAN.md; Genesis owns scientific semantics.
Owner response in this session: prepare the protocol now; the owner will name
an independent evaluator later. Prepare campaign/assurance cost estimates before
requesting approval. No formal evaluation or full assurance budget is approved.

## Product claim and exclusions

The proposed deliverable is a reproducible research asset: bounded relationship
search, parameter estimation, model comparison/rejection and explicit refusal.
Report these outcomes separately. Existing Thevenin/Rint assessment is not
discovery of those equations. Provider availability is not physics qualification.
No universal-solver, SaaS, clinical, production-ready or general-discovery claim.
The maturity ledger and all mandatory repository gates remain binding.

## Access and separation

| Role | May read | Must not read or change |
|---|---|---|
| Builder | Source, synthetic/development tasks, public protocol, public grammar | Hidden roots/seeds, final tasks/labels, evaluator credentials, final results during development |
| Candidate runtime | Frozen candidate image, public task card, budgeted observations | Repository history, evaluator filesystem/processes, operator credentials, network except approved observation channel |
| Custodian/evaluator | Approved final generator/data, secret roots, frozen candidate output; read-only frozen implementation for execution/replay audit | Modifying candidate implementation after freeze or thresholds/tasks after outcomes |
| Buyer/operator | Public release, permitted datasets, audit/replay bundle | Unreleased evaluator secrets or data without redistribution rights |

A different AI agent alone is not independent evaluation. The custodian must
control separate credentials/storage and document prior exposure, conflicts and
authoring process. Candidate and evaluator share only a specified protocol.
Every evaluated baseline has the same runtime access boundary, observation
accounting and final-data restrictions as the candidate. Final task authors must
not tailor cases using candidate-specific behavior or results; authoring rules
and exposure are recorded before task construction.
Security receipts bind source/image, environment, escrow key, protocol and run.
The real launcher must pass filesystem, symlink/traversal, process/memory,
inherited-descriptor, environment, network, log, replay and budget attacks.
Planted-leak controls must fail the boundary. An unavailable OS boundary stays
NOT_PROVEN. Existing isolation.py is reused, not replaced by a label/audit hook.

## Data lifecycle

Three roles: calibration -> selection -> sealed final evaluation. Selection
data may rank models; it cannot be called independent confirmation. Split by
physical cell/experiment/world and bind derived lineage, not randomly by rows.
Final targets are absent from builder and candidate APIs/files/images.
Counterfactual changes to final labels must not change the sealed candidate.
The custodian assigns fresh final instances only after engine and baseline
freeze. No existing battery TruthBundle or historical pilot is a fresh final set.

## Scoring amendment (FDA-05 approved; remaining items proposed)

Owner explicitly approved on 2026-10-28 in this chat: for a new benchmark
version, remove recovery credit for bracketing-only pairs and require at least
one model to pass the existing accuracy criterion; preserve unresolved
indistinguishability as a separate outcome. This approves item 2 below only,
not a formal run, statistical thresholds, or changes to historical identities.

1. Keep v0/v0.1/v0.2 artifacts immutable. A corrected implementation is a new
   benchmark identity; old results never inherit new semantics.
2. For pair answers, retain finite/in-box agreement/fit and outside-divergence
   checks, but do not grant recovery credit solely for bracketing truth. Require
   at least one law to pass the existing tolerance and PASS_FRACTION criterion
   for recovery, in addition to the existing pair eligibility checks.
   Honest unresolved indistinguishability is reported separately as refusal or
   preserved ambiguity, not counted as mechanism recovery. No new tolerance or
   sharpness threshold is introduced by this approved amendment.
3. Record competent-baseline eligibility per task and scored outcome, including
   spurious-correlate and confounded law credit, rather than discoverable alone.
   Missing/inapplicable competent baselines prohibit lift claims for that cell.
   No task disappears because an arm fails; invalid runs remain in the report.
4. Freeze the comparison set and tune all arms only on development data with
   equal access and effort. Enumeration/random use the same grammar and bounds.
   Always-refuse/always-law are sanity controls, never competence comparators.
5. Report false support, false refusal, answer rate, correct-useful coverage and
   error conditional on answering, with denominators per question type. An
   always-refuse system fails usefulness even with zero false support.

## Statistical design awaiting review

Specify estimands and independent units before coding a replacement decision
rule. Worlds/cells are units; seeds and presentations are repeated measurements.
Do not pass uncentered bootstrap tail fractions to Holm as assumed p-values.
Choose and justify an appropriate paired test under its actual assumptions;
calibrate it on synthetic nulls, clusters, ties, failures and multiplicity.
Use simultaneous comparisons or a comparator selected on development data;
do not silently select the comparator on final outcomes and use a naive test.
Report intervals separately from significance. Thresholds for false support,
false refusal, useful coverage, noninferiority and minimum meaningful lift are
owner/reviewer decisions; none has been fabricated here. Power determines the
required sample count subject to Genesis floors (30 instances/class/domain and
20 seeds where stochasticity matters). The floor is not a power guarantee.

## Real-measurement feasibility

Reuse the battery ingestion and bounded equivalent-circuit path if appropriate.
Before final approval obtain exact source terms/attribution/redistribution rights,
raw archive hashes, sensor calibration or defensible measurement error bounds,
sampling/current-hold conventions, initial conditions and applicability ranges.
An unspecified license is not a permission grant. A known model residual is not
automatically measurement uncertainty or model-form uncertainty. Unknown stays
unknown. Justify pulse-duration-specific acceptance bars before evaluating new
cells. The 10 s versus 288 s inherited-bar issue must not be hidden by tolerance
widening. If the data cannot support a useful decision, report NOT_ASSESSABLE
and acquire better data or stop this demo rather than manufacture validation.

## Cost estimate procedure (no campaign authorized)

After scorer, baseline and isolation readiness, propose a development-only pilot
matrix and hard local timeout. Measure per-arm/per-class wall and CPU time,
memory, provider calls, failures and variance. Include startup and replay cost.
Estimate final cost as sum(N_independent * N_stochastic_seeds * N_presentations
* measured_per_run_cost) across arms/classes, plus isolation/scoring/replay.
Deterministic arms need not be multiplied by meaningless random seeds. Report
an interval and concurrency/memory constraints, not only a point estimate.
Prepare full-assurance costs separately from scientific campaigns. Ask for the
concrete capped budget before either. No paid services are authorized.

## Freeze and stop rules

Proposed engine improvement limit: eight engineering days, development-only,
after prerequisites and the active-epic condition are satisfied. Owner approval
of the timebox is still needed. Freeze source/config/grammar/dependencies and
baseline settings. The independent operator executes the final protocol once.
A valid negative result remains negative. Leakage or protocol drift means
INVALID_BENCHMARK, not a scientific engine failure. No improvement/retry on the
same final set; a new evaluation requires a new approved identity and fresh data.
Independent operation is necessary for technical research-asset delivery, which
may honestly include negative results. That delivery does not close Scientific
MVP/Genesis A2 or B1, waive baseline-lift or predecessor gates, or authorize a
superiority claim. Any alternate milestone requires owner approval. Marketing
claims must match the actual final outcome and demonstrated scope.

## Concrete unresolved decisions

- Baseline eligibility amendment and statistical test/thresholds (FDA-05 pair
  semantics above are approved, not implemented or validated by this document).
- Active-epic exception/change if new Mind capability is needed (not for repairs).
- Independent custodian and final data rights/quality.
- Approved pilot, formal campaign and assurance budgets after measurement.
- Compatibility policy for data roles and model implementation/unit bindings.

Do not implement these decisions by silently updating historical pins, widening
tolerances or inventing evidence. Technical preparation can continue independently.
