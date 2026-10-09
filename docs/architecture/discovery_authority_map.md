# Discovery Authority Map (Roadmap V2, R1)

Source-level inventory on branch `feat/roadmap-v2-discovery` (base `66560420`, PR #124 head). Every row names one
canonical owner. Duplicates are adapted into it, aliased, or kept for compatibility. None of them becomes a second
authority.

**Placement rule.** `src/engcore/scientific/**`, `credibility/evidence_graph/**`, the SRIA admission chain and
`sria/campaign/runner.py` are CORE_CERTIFIED (`tools/certification/core_certificate.py`). Changing them turns
`tests/test_core_certificate.py` red until hardened recertification. V2 therefore extends non-certified owners
(`sria/decision`, `design`, `claims`) and consumes certified records read-only.

## Ownership map

| Concept | Canonical owner | Duplicates found | Action |
|---|---|---|---|
| Hypothesis | `sria.decision.hypotheses.Hypothesis`. **Extended** with kind, typed statement, structure digest, predictions, parameters plus provenance, complexity, proposal provenance, knowledge snapshot, parents, novelty, falsifier refs, verdict-backed status and revision | `scientific.discovery.GeneratedHypothesis` (certified; no status; previously unused) and `claims.analysis.diagnostics.RepairHypothesis` (a pipeline-repair hypothesis about why a claim failed) | **ADAPT** `GeneratedHypothesis` through `discovery_adapter`. The kind is now kept; the status is always PROPOSED, because a legacy holdout is not a sealed verdict. **KEEP SEPARATE** `RepairHypothesis`: it is a diagnostic about the claim pipeline, not a scientific hypothesis. It is never converted, and diagnostic hypotheses are not evidence |
| Hypothesis status | `sria.decision.HypothesisStatus`: PROPOSED, ADMITTED_FOR_TEST, SURVIVING, REFUTED, INDISTINGUISHABLE, OUT_OF_SCOPE, UNKNOWN. There is no TRUE | `DiscoveryCandidateStatus` (certified candidate states), `DiscoveryDecision` (certified review), `FalsificationRecord.survived` | **KEEP** the legacy enums for certified compatibility. They do not map onto V2 statuses: a V2 status is set only from sealed-falsifier verdict records (R5) |
| Experiment planning | `sria.decision`. `ActionFamily` = EXPLORE / CHARACTERIZE / DISCRIMINATE / OPTIMIZE / REDUCE_UNCERTAINTY / VALIDATE; generators; one `UtilityEngine`; `DecisionRecommendation` | `claims.next_experiment` (deterministic claim-gap advisor), `scientific.discovery.closed_loop` stage machine, frozen `scientific.experiments.NumericSearchBackend` (ask/tell hook, no implementation) | **ADAPT** `claims.next_experiment.PLANNING_FAMILY`, which maps every gap action to an `ActionFamily` (or to `None`: not an experiment). **ADD** `sria.decision.external`: external engines and language models produce `ExternalSuggestion` → `ActionProposal` (provenance only, content-addressed, no authority keys). **DEPRECATE for new work** the `closed_loop` stage machine (certified; kept) |
| Falsification | V2 sealed falsifiers (R5), on the canonical hypothesis | `scientific.discovery.FalsificationRecord` (bool survived), `claims.analysis.challenge.ChallengeReport` (SURVIVED / WEAKENED / INCONCLUSIVE / NOT_ATTEMPTED), Arbiter INVALID | **ADAPT** in R5. The challenge and Arbiter outcomes stay authoritative for their own domains |
| Discovery history | `design.history.DesignHistory` (hash chain), anchored by `claims.design_memory` | `design.memory` (D3 retention memory) | **KEEP BOTH**. They hold different things: every attempt versus a retained subset |
| Fidelity rungs | `design.fidelity.FidelityLadder` / `FidelityRung` | `sria.calibration.fidelity.FidelityRung` (rung plus model_ref; cost relationships only; refuses accuracy statements) | **KEEP**. SRIA calibration fidelity stays cost-only by its own rule |
| Fidelity observations / standing | `design.multifidelity` | — | **KEEP** |
| Fidelity relationship (measured) | **NEW** `design.fidelity_graph` (`FidelityNode`, `FidelityLink`, `measure_link`, `screen`, `EliminationLedger`, audit, resurrection) | `sria.calibration.fidelity.ModelFidelityRelationship` (cost ratio only, DOMAIN_OWNED accuracy refused) | **EXTEND** design. The accuracy relationship lives above SRIA calibration, which keeps refusing it |
| Candidate | `design.DesignCandidate` (design space plus Twin); `design.search.candidate_key` (content key) | `scientific.discovery.DiscoveredEquationCandidate` (certified law candidate) | **KEEP**. A law candidate enters V2 as an EQUATION hypothesis with `structure_digest` |
| Design space | `design.space.DesignSpace` (+ `grammar`, `hierarchy`) | — | **KEEP** |
| Evidence | `sria.evidence.Evidence` plus gateway belief; `credibility.evidence_graph` | — | **KEEP** (certified) |
| Credibility | `credibility.evidence.CredibilityEvidenceReport` plus `claims.governance.policy` | No factor vector, required vector, dominant gap or defeater exists | **EXTEND** in R7 as a consumer in a non-certified package |
| Scientific Twin | `scientific.twins.ScientificTwin` plus `systems.twin_revision.TwinRevision` | — | **KEEP** |
| Equation identity | `scientific.equations.transformations.canonicalize` / `structurally_equivalent` (certified, unused by discovery) | the fingerprints hash raw records | **ADAPT** in R5 novelty |
| Novelty | `sria.decision.NoveltyStatus`: NOT_CHECKED, KNOWN_EQUIVALENT, POSSIBLY_NOVEL, NOVELTY_UNRESOLVED. There is no NOVEL | — | protocol in R5 |
| Holdout / hidden truth | `scientific.corpus` holdout release/opening (enforced, in-process) | `scientific.discovery.DiscoveryDataset`: the holdout sits in the same object as the search | **REPLACE for discovery** with the escrow boundary (R4). Recorded gap: `ReferenceDataset.cases` exposes locked cases as a public field |

## Duplicate types found

1. Three hypothesis types: SRIA `Hypothesis`, `GeneratedHypothesis` and `RepairHypothesis`.
2. Four status vocabularies around candidates and hypotheses: `DiscoveryCandidateStatus`, `DiscoveryDecision`,
   `FalsificationRecord.survived` and `ChallengeResult`.
3. Two planning vocabularies: `ActionFamily` and claims `ExperimentAction`. A third, `planning.records.GapKind`, holds
   gaps rather than actions.
4. Two `FidelityRung` classes: `design.fidelity` and `sria.calibration.fidelity`.
5. Three gap vocabularies: `claims.gaps.GapClass`, `claims.compiler.GapKind` and `planning.records.GapKind`. These are
   left as found and noted for R7.

## FidelityGraph design (R2)

`FidelityLink(L -> H)` binds the following:

- the low and high node identities (rung plus model / realization / adapter);
- the observable and its unit;
- a `ValidityDomain`: declared, but it must lie inside the measured point hull (a missing variable counts as outside);
- a `LinkMeasurement` computed by `measure_link` from paired evaluations, never declared: the evaluation-set digest,
  Spearman rank correlation, decision agreement at the threshold, the discrepancy `H - L` (mean, std, and an envelope
  never narrower than observed), near-threshold confusion and the point hull;
- the version, status (MEASURED / ADMITTED / SUSPENDED / RETIRED) and audit history.

**Admission.** A link is admitted under a `LinkAdmissionPolicy` record with an absolute floor of 10 pairs. The policy
also sets minimum rank correlation, minimum decision agreement and optional near-threshold confusion. The admission
event binds the exact measurement digest, domain digest and version. Setting the status, carrying an old admission
over, or swapping the measurement or domain makes the link refuse to construct. Re-measurement needs a new evaluation
set.

**Elimination rules.**

- **Hard rejections need no link.** REJECT_HARD is allowed only for a `HardRejectionBasis`: a versioned logical or
  physical constraint judged on the candidate's inputs only, or an exact duplicate with a shared content digest.
- **Elimination needs a standing link.** `screen` eliminates only through an ADMITTED link whose domain contains the
  point and whose discrepancy is QUANTIFIED. It eliminates only when even the optimistic envelope end fails the
  threshold. Everything else is promoted.
- **The value must be the link's.** The screened value must come from the link's low realization and observable.
- **A screening decision is scheduling, not evidence.** It is classified `scheduling_decision_not_evidence` and never
  becomes a multifidelity SUPPORTS or CONTRADICTS observation.

**Ledger.** The `EliminationLedger` is hash-chained, and its entry payloads are immutable canonical JSON. An
elimination is recorded only if it reproduces under the link it names. A candidate cannot be recorded twice while it
stands, and a read-back requires an explicit expected head.

**Audit.**

1. **Draw.** `draw_audit` draws and records a margin-stratified sample of at least one per stratum. Its seed comes
   from the ledger head and the link standing, never from the caller, and only one draw per standing may be pending.
2. **Record.** `record_audit` must score exactly the drawn keys. Each candidate is judged against the threshold it was
   eliminated under.
3. **Resurrect false eliminations.** A false elimination is resurrected at once.
4. **Rate and suspension.** FALSE_ELIMINATION_RATE is cumulative per standing, and is None below `min_audits` (never
   zero). Above the `FalseEliminationPolicy` bound, the link is suspended.

**Resurrection.** `resurrection_queue` requeues, once and with trace, every elimination whose link standing no longer
stands (suspended, retired, re-measured or gone). It also requeues every constraint rejection whose constraint version
changed.

## Migration and compatibility

- **Byte compatibility.** `Hypothesis` keeps its M4G bytes: the new fields are trailing, defaulted, and emitted only
  when set. Test runs are recorded in `docs/work/PROGRESS.md`.
- **Certified code.** No CORE_CERTIFIED file is modified by R1 or R2.
- **Legacy discovery records** (`DiscoveredEquationCandidate`, `GeneratedHypothesis`, `FalsificationRecord`) stay as
  they are. They enter V2 only through adapters, and always as PROPOSED.
- **Planner fidelity rungs.** `design.multifidelity.PromotionPolicy` is unchanged. FidelityGraph screening runs before
  it as the elimination gate.
