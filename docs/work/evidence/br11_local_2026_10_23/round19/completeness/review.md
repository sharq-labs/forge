# Round19 completeness critic

Immutable reviewed implementation: `0b605b43416d575b60f87ca57eea7a1d646489d5`. **CHANGES REQUIRED / NOT CLOSED.** This audits Round19 coverage and evidence; it does not review the pending patches.

## Deduplicated findings

### R19-1 — MAJOR aggregate; E rates MEDIUM
Aliases: S2-F1, E-F1, R6 forward-progress regression
Location: `src/engcore/mind/world/owners.py:823-844,866-879,939-951`
Fresh detached forward history becomes a raw identity-incomparable barrier after the earlier snapshot skipped canonical normalization; identity mismatch becomes permanent divergence.
S2 deterministic detached/in-place controls: 1 failed, 1 passed; E supplied-source independent analysis agrees mechanism. Original stress isolated pass does not refute deterministic failure.
Impact: Normal monotonic restore/progress can terminally lose availability without canonical contradiction; no false-support increase established.
Disposition: Preserve unresolved barrier and reconcile canonical content outside lock. MAJOR because legitimate restore/liveness is central to approved repair, not because availability refusal grants scientific support.

### R19-2 — MAJOR against written final-acceptance/current-generation contract; interpretation disputed
Aliases: B-F1, B-LATE-PUBLICATION, S2 B-F1
Location: `src/engcore/mind/world/owners.py:1041,1163-1165; analogous construction boundary:570-571`
Source publication of completed spend arrives after another reader captured generations/readback but before it serves authority; final acceptance checks open only, not newly committed generations.
B and S2 executed paired late/prepublished schedules: executor counts 2 vs 1. E agrees final freshness absent but distinguishes acquisition-snapshot interpretation.
Impact: One stale dispatch after already-completed spend under written final freshness boundary. Not erasure of already-retained history, nor ordinary overlapping executor reservation.
Disposition: Check/reconcile generation currency with bounded fail-closed retry at coherent acceptance boundary. Preserve explicit disagreement; do not describe reviewers as unanimous on semantics.

There are two unique substantive families, no demonstrated BLOCKER and no additional independently supported MINOR. E-F1 and S2-F1 are one defect, despite severity wording. B-LATE-PUBLICATION duplicates B-F1. B-OVERLAP is the separately characterized executor-reservation residual. Aggregate severity for false permanent refusal reflects required ordinary forward restore behavior; it does not label fail-closed denial as false scientific support.

## Q1–Q7 aggregate

- **Q1** No second physical state authority found in bounded full-path A/F and supporting C/D reviews. Currentness of run/declaration callbacks remains execution-side statement.
- **Q2** No second applicability engine found: exact canonical model and assess_validity delegation; UNKNOWN/non-exact gating refuses. This is not exhaustive domain validation.
- **Q3** No parallel unit registry found: canonical Quantity/conversion/registry seal used. Tests cover selected spellings/bindings; not exhaustive unit fuzzing.
- **Q4** Qualified YES to unresolved budget authority/currentness defects at this SHA: R19-1 promotes identity incomparability into definitive history contradiction; R19-2 misses committed generation at written acceptance boundary. No new search engine or mutable spend ledger found. Observation/attempt affordability remains an explicitly disclosed owner-rule mirror, a maintenance coupling.
- **Q5** No world scientific-support/validation verdict found. Negative feasibility reporting and admission classification stay separate from scientific evidence; replay self-consistency is not provenance.
- **Q6** No direct external-proposer bypass found under execution-side suggestions_only policy. Caller kind is not authentication and Python process is not an isolation boundary. R19-2 is owner-currentness failure, not proposer forgery.
- **Q7** No raw/unadmitted provider path demonstrated, but R19-2 permits stale admitted execution under final-freshness semantics. Therefore do not report unconditional safe execution. No real provider run; at-most-once/reservation excluded.

## Completeness and repair verification gaps

- Final generation currency must be covered at following() construction as well as pinned() acceptance. Constructor can also wait/compare before only an open check. This is an analogous uncovered boundary, not a third independently reproduced defect.
- Add matched positive cases for benign same-content detached and genuinely forward replacement publications during reconciliation; generation churn must not become permanent contradiction or blanket unrecoverable denial.
- Exercise ScientificExperiment alongside BudgetLedger for new concurrent barriers/generation changes; common retention code exists but normalization paths differ. Existing 36-state lifetime product is serial ledger-focused.
- Interrupt bounded rereconciliation at capture, canonical readback and comparison; unresolved history must remain retained, retry exhaustion fail closed, and close/retire lease safety survive interruption. Do not convert bounded retry into authorization.
- Keep B overlap no-restore/restore controls distinct from delayed-publication counterexample so repair is not advertised as reservation or exactly-once execution.
- After patch: preserve failing-first evidence, run direct deterministic regressions and matched controls, rerun required affected ladder/differential gates at immutable repaired SHA, and obtain fresh independent review. This completeness report does not review or approve mutable fixes.
- Active plan specifies two independent skeptics per proposed MAJOR. Available artifact record has S2 for both and E supplied-source analysis (support for R19-1, semantic caveat for R19-2); do not silently count root implementation judgment or original finder as an additional independent skeptical execution. Explicitly record whether E fulfills second skeptic with static-only limits, or obtain remaining review.

## Evidence weighting

A/C/D/F established no counterexample in their bounded lenses; A/F cover broader admission while C/D emphasize identity and replay. Their positive tests are useful controls but cannot discharge S2 deterministic failure. B supplies a matched late-publication schedule; S2 reran it. E is static supplied-source review and supports the identity failure while preserving the late-publication semantic distinction. The approved persistent source, immutable bindings, retained account histories, unknown refusal, and terminal close/quiescent retirement requirements have coverage; their concurrency interactions were incompletely exercised by the serial 36-trace product. That is why the two findings survive the prior passing counts.

The evidence README and active plan at this SHA still say NOT CLOSED. Approved stable publication does not approve weakened acceptance semantics, retirement by timeout, or resetting the publication source during restore. The root has chosen generation rereconciliation rather than reinterpretation; closure must be judged on that repaired immutable implementation.

## Limits

- No new tests executed by completeness critic. Existing reports/logged results used as attributed evidence, not independently rerun.
- Pinned architecture/task/lifetime documents and relevant state-machine source read via git show at 0b605b43416d575b60f87ca57eea7a1d646489d5 because implementation is concurrently changing.
- A/B/C/D/F JSON and Markdown plus S2 and parent-preserved E summary reviewed. E is attributed summary of supplied-source review; no independent disk/execution and broader admission unavailable.
- Only two unique defect families supported; no third substantive defect invented from coverage gaps. No BLOCKER demonstrated. B-OVERLAP is documented executor-reservation residual, not duplicate finding.
- No broad suite result or pending repair result claimed; prior positive lens results cannot outvote later reproducible counterexamples.
- Scientific validation, certification, process-crash persistence, private-state tampering, bounded memory/performance and exactly-once effects remain outside this review.
