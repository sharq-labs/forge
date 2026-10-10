# FORGE Performance Tracker

> **Purpose:** Single execution tracker for the current FORGE roadmap.  
> **Location:** Same strategic area as `FORGE_MASTER_PLAN.md`.  
> **Rule:** Work is not closed because code exists. A row is closed only when its **Close Criteria** are met and the supporting evidence is recorded.  
> **Authority:** This tracker does not override scientific authority, frozen contracts, certification rules, or `FORGE_MASTER_PLAN.md`.

## Status legend

- `[ ] PLANNED` — not started.
- `[ ] IN_PROGRESS` — active work.
- `[ ] PARTIAL` — useful implementation exists, but exit criteria are not met.
- `[ ] BLOCKED` — blocked by an explicit external or technical dependency.
- `[ ] DEFERRED` — intentionally postponed.
- `[x] DONE` — close criteria satisfied and evidence recorded.

## Closing rules

1. Never mark a provider `DONE` because it imports, probes, or has an adapter. Qualification must match the declared scope.
2. Never mark Discovery `DONE` because a search returned a candidate. Falsification, leakage controls, multiplicity, uncertainty, and authority boundaries remain separate requirements.
3. Never mark a scientific claim `DONE` because two solvers agree. Verification, validation, applicability, uncertainty, and model-form evidence remain distinct.
4. Any false-support, wrong-number, provenance/identity corruption, evaluator-capture, or hidden-data leakage bug interrupts normal sequencing.
5. Lightweight targeted tests run continuously. Full Local Assurance / hardened recertification runs at deliberate integration freezes, not after every row.
6. Update this tracker at every major checkpoint. Put detailed transcripts, SHAs, failures, and measurements in `docs/work/PROGRESS.md`.

## Current execution policy

The current cloud implementation is allowed to finish the previously selected **NEXT THREE BIG ROCKS** before the Roadmap V2 pivot:

1. bounded real-provider runs and qualification records;
2. one bounded executable product coupling;
3. Twin / Discovery history integration with the existing SRIA/evidence authority.

After those three are checkpointed and preserved, the program pivots to the higher-leverage sequence:

```text
Discovery Authority Consolidation
        ↓
FidelityGraph
        ↓
Blindfold + Escrow
        ↓
Evaluator Isolation
        ↓
Multiplicity + Sealed Falsifiers
        ↓
Scientific Red Team
        ↓
Credibility Vectors
        ↓
Battery / AM-Bench Discovery Proofs
```

## Master execution table

| Done | # | Workstream / Big Rock | Current Status | Objective | Close Criteria |
|---|---:|---|---|---|---|
| [ ] | 0 | Preserve Current Big Rocks | IN_PROGRESS | Preserve all current Big Rocks history on a remote feature branch before further pivot work. | Remote branch exists; remote HEAD equals intended local checkpoint; no main push/merge required. |
| [ ] | 1 | Real Provider Runs | IN_PROGRESS | Complete bounded real executions for the current provider proofs instead of adding breadth. | Each targeted provider has a recorded `QUALIFIED / UNAVAILABLE / FAILED / DEFERRED` disposition with exact version/adapter identity. |
| [ ] | 2 | Executable Coupling | IN_PROGRESS | Prove one bounded system chain, initially propulsion → electrical → thermal. | End-to-end coupled path executes with declared inputs, provenance, failure semantics, and no full-product overclaim. |
| [ ] | 3 | Twin + Discovery + SRIA Integration | IN_PROGRESS | Wire Twin evidence and Discovery history into existing SRIA/evidence authority. | No duplicate EvidenceGraph/Planner/Twin authority; lineage and evidence references resolve through canonical paths. |
| [ ] | 4 | Checkpoint & Sync | PLANNED | Commit, push, and reconcile the completed three rocks with current main. | Clean checkpoint; remote branch preserved; conservative main sync; targeted regressions pass. |
| [ ] | 5 | Roadmap V2 Salvage Audit | PLANNED | Classify every Big Rocks deliverable as KEEP / EXTEND / SCAFFOLD / DEFER / DUPLICATE. | Salvage matrix reviewed; no useful foundation discarded without an architectural reason. |
| [ ] | 6 | Discovery Authority Consolidation | PLANNED | Consolidate ScientificTwin, D0–D3, SRIA, next-experiment, discovery, and Hypothesis authorities. | One canonical ownership map; duplicate authorities removed, aliased, or explicitly deprecated. |
| [ ] | 7 | Hypothesis Contract Upgrade | PLANNED | Extend the canonical hypothesis record for mechanism/equation/model/intervention/regime/design/null claims. | Typed statement, scope, predictions, falsifiers, provenance, novelty, complexity, and status are identity-bound. |
| [ ] | 8 | ExperimentPlanner Consolidation | PLANNED | Unify Explore / Characterize / Optimize / ReduceUncertainty / Discriminate / Validate behind one planner contract. | One canonical planner authority; external numerics may plug in without gaining scientific authority. |
| [ ] | 9 | FidelityGraph | PLANNED | Replace simple rank-only fidelity reasoning with measured links between realizations. | `FidelityLink(L→H)` records validity domain, discrepancy, uncertainty, decision/rank behavior, version, and audit history. |
| [ ] | 10 | False-Elimination Audits | PLANNED | Measure how often cheap models wrongly reject candidates. | Stratified higher-fidelity audit sampling implemented and `FALSE_ELIMINATION_RATE` reported for active links. |
| [ ] | 11 | Candidate Resurrection | PLANNED | Re-open candidates eliminated by invalidated or materially changed fidelity links. | Elimination stores link/version; suspension/update can deterministically requeue affected candidates. |
| [ ] | 12 | FORGE Blindfold | PLANNED | Establish the main sealed discovery benchmark. | Benchmark protocol exists with leakage controls, refusal scoring, compute budgets, and reproducible scoring. |
| [ ] | 13 | Blindfold L0–L6 Hierarchy | PLANNED | Separate retrieval, reasoning, transformed search, historical rediscovery, OOD, synthetic, and prospective discovery. | Each level has explicit construction, scoring, and claim limits; L0–L3 are not marketed as genuine novelty. |
| [ ] | 14 | Blindfold L5 Synthetic Universes | PLANNED | Test unseen in-silico discovery using post-training generated universes. | Hidden generator creates sufficiently diverse universes; instances are scored without exposing truth to proposer runtime. |
| [ ] | 15 | Negative / Control Universes | PLANNED | Reward correct scientific refusal and expose false-discovery behavior. | Controls include NO_SOLUTION, INSUFFICIENT_EVIDENCE, INDISTINGUISHABLE, SPURIOUS_CORRELATE, and CONFOUNDED cases. |
| [ ] | 16 | Escrow Service | PLANNED | Keep hidden generator state, holdouts, and scoring outside the Discovery agent's readable environment. | True separate boundary or explicitly labeled `SECURITY_BOUNDARY_NOT_PROVEN`; all queries logged and budgeted. |
| [ ] | 17 | Evaluator Isolation | PLANNED | Separate proposer, admission, evaluator, adjudicator, escrow, and reporter authority. | Proposer cannot modify evaluator/scorer/falsifier/hidden truth/evidence authority; write paths are one-way. |
| [ ] | 18 | Sealed Falsifiers | PLANNED | Pre-register what would falsify a promoted hypothesis before scored evidence is exposed. | Falsifier identities are sealed, replayable, and linked to exact hypothesis/campaign context. |
| [ ] | 19 | Multiplicity Accounting | PLANNED | Make search-scale selection effects visible. | Generated/admitted/tested/promoted counts, budgets, adaptive queries, and holdout queries are recorded per campaign. |
| [ ] | 20 | Novelty Adjudication | PLANNED | Separate scientific support from novelty. | Novelty status is checked against a frozen prior-art snapshot using canonical identity/equivalence; LLM opinion is non-authoritative. |
| [ ] | 21 | High-Throughput Tier 0 | PLANNED | Scale dimensional/logical/canonical filtering. | Measured elimination throughput published with correctness audits; no unmeasured marketing throughput claim. |
| [ ] | 22 | High-Throughput Tier 1 | PLANNED | Scale vectorized algebraic/lumped evaluation. | Batched screening works with replayable campaign records and measured trust overhead. |
| [ ] | 23 | High-Throughput Tier 2 | PLANNED | Add surrogate / reduced-order evaluation under declared validity. | Surrogate validity and uncertainty checked for every promoted use; surrogate output never raises evidence level. |
| [ ] | 24 | High-Throughput Tier 3 | PLANNED | Run batched small ODE/PDE numerical evaluations. | Throughput, failure/refusal behavior, and promotion records are measured per worker/environment. |
| [ ] | 25 | Discovery Compute Metrics | PLANNED | Publish real throughput and efficiency instead of raw candidate counts. | Candidates/sec, eliminations/sec, Tier-1 evals/sec, Tier-3 solves/sec/worker, trust overhead, useful promotions/compute-hour, false-elimination rate recorded. |
| [ ] | 26 | PySR Provider | PLANNED | Use mature symbolic regression instead of expanding Forge's own brute-force search. | Provider contract, identity, deterministic/replay semantics, targeted benchmarks, and explicit authority boundary implemented. |
| [ ] | 27 | PySINDy Provider | PLANNED | Add mature sparse dynamics identification. | Provider contract + benchmark + provenance + applicability/refusal semantics complete. |
| [ ] | 28 | BoTorch / Ax Provider | PLANNED | Supply Bayesian/multi-fidelity/cost-aware search numerics under SRIA. | Numeric provider integrated without replacing ExperimentPlanner authority; seeds/version/model identity bound. |
| [ ] | 29 | Dakota Provider | PLANNED | Reuse mature MF UQ / reliability / calibration methods. | Named benchmark needs it; provider records methods, versions, assumptions, and result authority correctly. |
| [ ] | 30 | Scientific Red Team V0 | PLANNED | Adversarially search for admissible counterexamples to important claims. | `Claim → AttackSpace → AttackPlan → CounterexampleCandidate → Replay → IndependentCheck → TrustEnvelope` executes. |
| [ ] | 31 | Attack Model Form | PLANNED | Attack assumptions/model family, not parameters only. | Model-form alternatives are declared/admitted and counterexamples require appropriate independent reproduction. |
| [ ] | 32 | Attack Boundaries / Environment / Numerics | PLANNED | Search BC, environment, operating-regime, numerical, and provider alternatives. | Attack dimensions have sources/plausibility limits; out-of-plausibility findings are not physical counterexamples. |
| [ ] | 33 | Seeded-Flaw Red Team Benchmark | PLANNED | Calibrate Red Team using known injected defects. | Detection rate, evaluations-to-counterexample, false alarms, and independent confirmation rate reported. |
| [ ] | 34 | Trust Envelope | PLANNED | Report where a claim failed, survived, or remains unknown. | Output uses `FALSIFIED / SURVIVED(region,budget,method) / UNKNOWN`; absence of failure never becomes SAFE. |
| [ ] | 35 | Credibility Graph V2 | PLANNED | Extend the existing evidence/credibility graph with decision-relevant factor vectors. | Factor levels, required levels, gaps, defeaters, and propagation policies exist; no unjustified scalar percentage. |
| [ ] | 36 | Decision-Specific Credibility | PLANNED | Tie credibility requirements to a stated context of use / decision. | Required factor vector is explicit for the decision; UNKNOWN never satisfies a requirement. |
| [ ] | 37 | Dominant Evidence Gap | PLANNED | Identify the evidence gap whose closure most improves the decision state. | Blocking gap is computable and can feed ExperimentPlanner without fabricating confidence. |
| [x] | 38 | Minimum Robust Geometry Foundation | DONE (FOUNDATION) | Preserve the provider-neutral geometry/region/boundary/interface identity foundation already built. | Stable Forge identity; provider-native tags isolated in receipts/maps; targeted tests and hostile fixes completed. |
| [ ] | 39 | Geometry Regeneration Check | PARTIAL | Detect persistent-naming/selector changes on regeneration instead of silently remapping. | Region selectors re-resolve; receipt mismatch causes UNKNOWN/refusal; no silent remap. |
| [ ] | 40 | Twin Revision DAG | PARTIAL | Extend the existing frozen ScientificTwin through immutable non-Core revisions and typed change events. | Revision DAG, event semantics, evidence snapshot references, and authority separation are complete and integrated. |
| [ ] | 41 | Provider Strategy Freeze | PLANNED | Stop adding providers for count after the current three rocks. | Future providers require a named benchmark/claim; breadth is no longer a progress metric. |
| [ ] | 42 | Qualify FEniCSx | IN_PROGRESS | Deepen a useful PDE/FEM qualification scope beyond adapter availability. | Real bounded run, independent check/oracle, validity envelope, numerical evidence, provider identity, and failure semantics recorded. |
| [ ] | 43 | Qualify OpenFOAM | PLANNED | Expand qualification beyond the narrow current case family. | At least one meaningful additional case family with verification/evidence and declared applicability is qualified. |
| [ ] | 44 | Keep OpenVSP Scaffold | DEFERRED | Preserve valid adapter work without deepening it now. | Scaffold remains fail-closed and explicitly `REAL_EXECUTION_NOT_VERIFIED` until an aero benchmark pulls it. |
| [ ] | 45 | Keep Chrono Scaffold | DEFERRED | Preserve valid adapter work without broad multibody expansion now. | Scaffold remains fail-closed; unsupported joints/actuators are explicit; real qualification waits for a benchmark. |
| [ ] | 46 | OpenRadioss Governance Decision | REVIEW | Verify authoritative upstream/governance status before further investment. | Evidence-backed KEEP / FORK-MIGRATE / DEFER / REMOVE decision recorded. |
| [ ] | 47 | Battery Degradation Discovery | PLANNED | Use battery fade as the first real scientific-discovery proving ground. | New pre-registration, model competition, independent/fresh confirmatory dataset, falsification, multiplicity, and Red Team output. |
| [x] | 48 | Battery Negative-Result Discipline | DONE | Preserve Kirkaldy NOT MET and prevent observed holdout reuse as unseen validation. | Negative result stays visible; any new study uses new hypothesis/protocol and fresh confirmatory evidence. |
| [ ] | 49 | NIST AM-Bench Vertical | PLANNED | Use prospective/blind additive-manufacturing prediction as the second discovery proof. | Official benchmark protocol followed; prediction sealed before truth exposure; scoring is externally checkable. |
| [ ] | 50 | Fusion F1 | PLANNED | Add one bounded safe fusion-energy component benchmark after Red Team exists. | Component-level benchmark has admitted data/models, independent routes where possible, UQ, falsification, and scoped claims. |
| [ ] | 51 | Fusion F2+ | DEFERRED | Expand fusion multiphysics/lifecycle/RAMI only after F1 demonstrates value. | Pulled by benchmark/evidence need; no whole-system overclaim. |
| [ ] | 52 | Biomedical Benchmark | DEFERRED | Start with one bounded externally referenceable computational engineering benchmark. | Clear engineering context of use, validation route, and no clinical treatment authority. |
| [ ] | 53 | Drone Product | DEFERRED | Preserve template/current bounded coupling proof, but defer full product expansion. | Reopened only by a named benchmark/customer need after Discovery/Red Team priorities. |
| [ ] | 54 | Vehicle Product | DEFERRED | Preserve scaffold; avoid whole-vehicle expansion now. | Reopened only by a high-value benchmark/customer requirement. |
| [ ] | 55 | Motor Product | DEFERRED | Preserve scaffold; defer deeper motor vertical. | Reopened by benchmark/customer pull. |
| [ ] | 56 | HVAC Product | DEFERRED | Preserve scaffold; defer deeper HVAC vertical. | Reopened by benchmark/customer pull. |
| [ ] | 57 | Assembly Breadth | DEFERRED | Keep current topology foundation but postpone broad catalog/serviceability/motion work. | Reopened by product need; no general CAD/assembly platform built speculatively. |
| [ ] | 58 | 3D Viewer | DEFERRED | Preserve Scene IR only; visualization remains presentation, not authority. | Reopened when evidence-bound product visualization has concrete product value. |
| [ ] | 59 | Discovery Passports | PLANNED | Create a durable record of what each promoted discovery survived. | Passport binds identities, evidence, attacks, budgets, providers, versions, fidelity history, and verdict limits. |
| [ ] | 60 | Provider / Independence Graph | PLANNED | Record solver/provider capability and real independence relationships. | Shared dependencies are explicit; independent confirmation only counts when independence policy is satisfied. |
| [ ] | 61 | Public Blindfold Leaderboard | DEFERRED | Build network-effect benchmark value after internal v1 is credible. | Third-party submission protocol, sealed scoring, versioned challenge sets, and public result rules exist. |
| [ ] | 62 | External Red-Team Engagements | DEFERRED | Apply the Red Team product to external engineering claims. | Internal seeded-flaw calibration complete; engagement outputs are reproducible and scoped. |
| [ ] | 63 | L6 Prospective Result | DEFERRED | Produce a real prospective result sealed before future measurements exist. | Prediction/protocol timestamped and sealed before data; later scoring uses independent external truth. |
| [ ] | 64 | Continuous Authority Hardening | IN_PROGRESS | Fix authority-critical defects immediately throughout the roadmap. | No known false-support, wrong-number, hidden-data leakage, evaluator-capture, or provenance/identity blocker remains open at a milestone. |
| [ ] | 65 | Deferred Hardening Ledger | IN_PROGRESS | Track low-risk lint/UI/package/refactor debt without blocking Big Rocks. | Every deferred item has reason, owner/trigger, and no hidden scientific-authority impact. |
| [ ] | 66 | Full Assurance / Recertification | DEFERRED UNTIL FREEZE | Run the expensive SHA-bound campaign at a deliberate integration freeze. | FAST + SCIENTIFIC + required provider suites + mutations + scope/certificate checks pass on the exact final source SHA. |

## Milestone targets

### Current checkpoint — finish the existing three rocks

- [ ] Bounded real-provider proof(s) recorded.
- [ ] One bounded executable coupled chain recorded.
- [ ] Twin / Discovery history integrated with canonical SRIA/evidence authority.
- [ ] Current work committed and pushed safely.
- [ ] No new breadth added merely for provider count.

### Roadmap V2 first proof

- [ ] Canonical Discovery ownership consolidated.
- [ ] FidelityGraph active with measured links.
- [ ] Blindfold L5 minimum benchmark works.
- [ ] Escrow boundary is real or explicitly marked unproven.
- [ ] Evaluator isolation prevents proposer write access.
- [ ] Multiplicity and sealed falsifiers are recorded.
- [ ] Scientific Red Team attacks the discovery output.
- [ ] Credibility output uses factor vectors/gaps, not a scalar score.

### First externally impressive demo

A live Blindfold run where an unseen universe is selected after the system is fixed:

```text
Blindfold universe
        ↓
Forge proposes/searches
        ↓
Forge discovers or correctly refuses
        ↓
Escrow scores hidden truth
        ↓
Scientific Red Team attacks the survivor
        ↓
Trust Envelope
        ↓
Replayable Discovery Passport
```

The demonstration succeeds only if it proves all three behaviors:

- not dependent on memorizing a known answer;
- willing to return `INSUFFICIENT_EVIDENCE` / `INDISTINGUISHABLE`;
- able to attack and qualify its own discovery.

### First scientific result target

A pre-registered blind competition for lithium-ion capacity-fade model structure using an exploratory dataset and a truly independent confirmatory dataset.

The result may be positive or negative. A rigorous negative result still counts as scientific progress if the protocol, multiplicity, falsification, and uncertainty are preserved.

### 6–12 month target

- [ ] Blindfold v1 credible enough for outside submissions.
- [ ] Battery discovery proof completed.
- [ ] AM-Bench prospective/blind vertical active.
- [ ] Red Team seeded-flaw suite published internally or externally.
- [ ] At least one cross-family reproduced counterexample.
- [ ] Discovery Passport corpus accumulating.
- [ ] Fusion F1 starts only after Red Team and credibility machinery are usable.
- [ ] One L6 prospective result is targeted before broad product expansion.

## Progress metrics

Do **not** use raw file count, LOC, provider count, or generated-candidate count as primary success metrics.

Track:

- false accepts on Blindfold controls;
- false-discovery rate at a fixed abstention policy;
- false-elimination rate per active fidelity link;
- Blindfold L5 recovery relative to baselines at matched compute;
- correct refusal rate;
- candidates/sec by fidelity class;
- trust/provenance overhead;
- useful promotions per compute-hour;
- Red Team seeded-flaw detection rate;
- evaluations-to-first-counterexample;
- independent cross-family confirmations;
- number of qualified provider/regime combinations;
- number of replayable Discovery Passports;
- number of externally scored blind/prospective results.

## Update template

When closing or changing a row, append a short entry here **and** record the detailed evidence in `docs/work/PROGRESS.md`:

```text
DATE:
ROW:
STATUS:
SOURCE_SHA:
EVIDENCE:
TESTS:
SCIENTIFIC_REVIEW:
CERTIFICATION_IMPACT:
NOTES:
```

## Change log

### 2026-10-09

- Created the unified FORGE performance/execution tracker.
- Preserved the owner's decision to finish the current three Big Rocks before the Roadmap V2 pivot.
- Recorded completed foundation work without treating scaffolds as qualification.
- Made Blindfold, evaluator isolation, FidelityGraph, Scientific Red Team, and credibility gaps the next high-leverage scientific priorities.
