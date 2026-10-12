# FORGE Performance Tracker

> **Purpose:** measurement policy and evidence ledger — how performance and workstream status are measured, labelled
> and closed. Measured numbers themselves live in `docs/performance/core-performance.md` (command, SHA, environment).
>
> **Authority (2026-10-11):** this file grants **no execution authority**. What to work on now is decided only by
> `docs/work/ACTIVE_PLAN.md`, under the strategy in `docs/project/FORGE_MASTER_PLAN.md` Part I. It does not override
> scientific authority, frozen contracts, certification rules or the capability ledger. In its own scope — measurement
> semantics, measured evidence, freezes and compute claims — it is final: `ACTIVE_PLAN.md` may schedule measurement
> work but cannot redefine how it is measured, labelled or claimed. Execution authority does not imply semantic
> authority outside the document's scope.
>
> **Rule:** work is not closed because code exists. A row is closed only when its **Close Criteria** are met and the
> supporting evidence is recorded.

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
7. Never present a number without its measurement label (below). An ESTIMATED or TARGET value never becomes a claim.

## Measurement labels

| Label | Meaning | May support a claim? |
|---|---|---|
| `MEASURED` | Executed; command, source SHA, environment and date recorded (in `docs/performance/core-performance.md` or PROGRESS) | yes, within the measured environment and scope |
| `ESTIMATED` | Derived by arithmetic or modelling from measured inputs; method stated | no — planning only |
| `TARGET` | A goal someone set | no |
| `UNMEASURED` | Nothing has been run | no |

Labels for the numbers recorded so far: the Roadmap V2 R8 discovery tiers in `core-performance.md` §9 (tier 0–3 rates,
~292 µs trust overhead per screened candidate, false-elimination 0.0 over 963 audits) are `MEASURED` in one container,
one process, seed 7. "50.7 useful promotions per compute-hour" is `ESTIMATED`: the FORGE machinery time is measured,
the high-fidelity cost is a DECLARED 60 s. The Genesis campaign size (Genesis §10.6) is `ESTIMATED`. The 10 / 100 /
1,000 / 10,000 campaign ladder is `UNMEASURED`.

## Compute staging

Compute capability is added only when a measured workload requires it:

```text
content-addressed tasks → process workers per provider environment → scientifically valid result reuse (proven per
execution class, Genesis §21) → telemetry as provenance → vectorized cheap tiers → existing schedulers (Ray / Dask /
Parsl / Slurm) where needed → GPU / HPC only when a measured, accelerator-suitable workload justifies it
```

No bespoke scheduler is built as a moat. A ladder rung (10, 100, 1,000, 10,000 campaigns) is reported only after it
has been run, with strong-scaling, cache-correctness, false-elimination and per-tier cost results.

## Status reconciliation (2026-10-11)

The 2026-10-09 "finish three rocks, then pivot" policy is **closed**: the three rocks merged in PR #124 and Roadmap V2
R1–R8 merged in PR #125 (`main` @ `4634eba`). The original text is archived in
`docs/archive/FORGE_MASTER_PLAN_2026-10-10.md` (appendix). Ledger rows below keep their 2026-10-09 status cells; this
table records what PROGRESS shows was built since. **No row is ticked DONE by this reconciliation**: close criteria were
not re-audited, and nothing below is certified or qualified.

| Rows | Recorded evidence (PROGRESS 2026-10-09/10) | Status now |
|---|---|---|
| 0–4 | Big Rocks + next three rocks merged (#124); Chrono / FEniCSx / CalculiX executed; OpenVSP / OpenRadioss not installable | BUILT; close criteria NOT RE-AUDITED |
| 5 | No salvage matrix found in the repository | unchanged (PLANNED) |
| 6–8 | Discovery authority map; canonical hypothesis and planner owners chosen; duplicates mapped, not removed | PARTIAL |
| 9–11 | `design.fidelity_graph`: measured links, stratified audit, suspension, resurrection | BUILT (not a ledger stage) |
| 12–20 | `engcore.blindfold` (L5, controls, escrow `SECURITY_BOUNDARY_NOT_PROVEN`, roles); sealed falsifiers, multiplicity, novelty | BUILT (not a ledger stage); L0–L4 and L6 levels NOT RE-AUDITED |
| 21–25 | `tools/discovery_performance.py`, one-container measurement (labels above) | PARTIAL (MEASURED once) |
| 26–29 | PySINDy, BoTorch, Dakota executed in provider envs; PySR, Ax NOT_INSTALLED | EXECUTED, not qualified |
| 30–36 | Red Team, seeded-flaw suite, TrustEnvelope, credibility vectors (seven review rounds) | BUILT (not a ledger stage) |
| 47 | Battery readiness: NOT READY for a confirmatory experiment; Kirkaldy stays NOT MET | unchanged |

Mapping to Master Plan Part I §4 (strategic direction; the active queue is `docs/work/ACTIVE_PLAN.md`):

- **NOW:** G0 Trust lane (rows 64, 66); Track A uses rows 6–20 as substrate; Track B demo (drone coupled chain from row 2).
- **NEXT:** rows 9–11 and 21–25 as Genesis Steps 3–5 need them; rows 37 and 60.
- **LATER:** rows 26 and 43 (only when a named benchmark pulls them), 47, 49, 50–58, 61–63.
- **In force as policy:** row 41 (provider strategy freeze).

## Workstream ledger (status cells as of 2026-10-09 unless edited 2026-10-11)

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
| [ ] | 16 | Escrow Service | PARTIAL | Keep hidden generator state, holdouts, and scoring outside the Discovery agent's readable environment. | True separate boundary or explicitly labeled `SECURITY_BOUNDARY_NOT_PROVEN`; all queries logged and budgeted. Status 2026-10-10 (Big Rocks campaign): persistent escrow service (private 0700 storage, keyed journal, persistent budgets/submissions/query ids), MAC-authenticated v4 protocol, signed responses, client checkpoints for rollback, journaled world digests; isolation demo `OS_ISOLATION_BOUNDARY_VERIFIED` (separate uid + namespaces, launcher-verified, canary scan with positive control). NOT a container/host boundary; rollback detection needs a client checkpoint. |
| [ ] | 17 | Evaluator Isolation | PARTIAL | Separate proposer, admission, evaluator, adjudicator, escrow, and reporter authority. | Proposer cannot modify evaluator/scorer/falsifier/hidden truth/evidence authority; write paths are one-way. Status 2026-10-10: the proposer runs in an OS-isolated domain holding only its observe capability; operator/evaluator still run as root in the escrow's domain. |
| [ ] | 18 | Sealed Falsifiers | PARTIAL | Pre-register what would falsify a promoted hypothesis before scored evidence is exposed. | Falsifier identities are sealed, replayable, and linked to exact hypothesis/campaign context. Status 2026-10-10: sealing is journaled into the signed authority ledger (`DurableCampaign`) and replayed with head checks; seals are checked against a machine-readable pre-registered rule. No real campaign has sealed one yet. |
| [ ] | 19 | Multiplicity Accounting | PARTIAL | Make search-scale selection effects visible. | Generated/admitted/tested/promoted counts, budgets, adaptive queries, and holdout queries are recorded per campaign. Status 2026-10-10: durable (journaled) and re-derived from the journal by `verify_discipline` against the pre-registered budget. |
| [ ] | 20 | Novelty Adjudication | PARTIAL | Separate scientific support from novelty. | Novelty status is checked against a frozen prior-art snapshot using canonical identity/equivalence; LLM opinion is non-authoritative. Status 2026-10-10: the battery snapshot is frozen with expressions, a family canonicalizer and declared numeric equivalence, but it is NOT systematic (citations unverified). |
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
| [ ] | 41 | Provider Strategy Freeze | IN FORCE (policy, 2026-10-11) | Stop adding providers for count after the current three rocks. | Future providers require a named benchmark/claim; breadth is no longer a progress metric. |
| [ ] | 42 | Qualify FEniCSx | IN_PROGRESS | Deepen a useful PDE/FEM qualification scope beyond adapter availability. | Real bounded run, independent check/oracle, validity envelope, numerical evidence, provider identity, and failure semantics recorded. |
| [ ] | 43 | Qualify OpenFOAM | PLANNED | Expand qualification beyond the narrow current case family. | At least one meaningful additional case family with verification/evidence and declared applicability is qualified. |
| [ ] | 44 | Keep OpenVSP Scaffold | DEFERRED | Preserve valid adapter work without deepening it now. | Scaffold remains fail-closed and explicitly `REAL_EXECUTION_NOT_VERIFIED` until an aero benchmark pulls it. |
| [ ] | 45 | Keep Chrono Scaffold | DEFERRED | Preserve valid adapter work without broad multibody expansion now. | Scaffold remains fail-closed; unsupported joints/actuators are explicit; real qualification waits for a benchmark. |
| [ ] | 46 | OpenRadioss Governance Decision | REVIEW | Verify authoritative upstream/governance status before further investment. | Evidence-backed KEEP / FORK-MIGRATE / DEFER / REMOVE decision recorded. |
| [ ] | 47 | Battery Degradation Discovery | DEFERRED (LATER; may return as a Genesis inverse-problem domain) | Use battery fade as the first real scientific-discovery proving ground. | New pre-registration, model competition, independent/fresh confirmatory dataset, falsification, multiplicity, and Red Team output. Status 2026-10-10: readiness `NOT_READY` (`docs/flagships/BATTERY_CONFIRMATORY_READINESS.md`): pre-registration draft, hypothesis set, frozen prior-art snapshot, exposure gate, sealed-falsifier rule, Red Team plan and a synthetic dry run exist; no confirmatory dataset is designated and no confirmatory datum was exposed. |
| [x] | 48 | Battery Negative-Result Discipline | DONE | Preserve Kirkaldy NOT MET and prevent observed holdout reuse as unseen validation. | Negative result stays visible; any new study uses new hypothesis/protocol and fresh confirmatory evidence. |
| [ ] | 49 | NIST AM-Bench Vertical | DEFERRED (LATER) | Use prospective/blind additive-manufacturing prediction as the second discovery proof. | Official benchmark protocol followed; prediction sealed before truth exposure; scoring is externally checkable. |
| [ ] | 50 | Fusion F1 | DEFERRED (LATER) | Add one bounded safe fusion-energy component benchmark after Red Team exists. | Component-level benchmark has admitted data/models, independent routes where possible, UQ, falsification, and scoped claims. |
| [ ] | 51 | Fusion F2+ | DEFERRED | Expand fusion multiphysics/lifecycle/RAMI only after F1 demonstrates value. | Pulled by benchmark/evidence need; no whole-system overclaim. |
| [ ] | 52 | Biomedical Benchmark | DEFERRED | Start with one bounded externally referenceable computational engineering benchmark. | Clear engineering context of use, validation route, and no clinical treatment authority. |
| [ ] | 53 | Drone Product | DEFERRED | Preserve template/current bounded coupling proof, but defer full product expansion. | Reopened only by a named benchmark/customer need after Discovery/Red Team priorities. |
| [ ] | 54 | Vehicle Product | DEFERRED | Preserve scaffold; avoid whole-vehicle expansion now. | Reopened only by a high-value benchmark/customer requirement. |
| [ ] | 55 | Motor Product | DEFERRED | Preserve scaffold; defer deeper motor vertical. | Reopened by benchmark/customer pull. |
| [ ] | 56 | HVAC Product | DEFERRED | Preserve scaffold; defer deeper HVAC vertical. | Reopened by benchmark/customer pull. |
| [ ] | 57 | Assembly Breadth | DEFERRED | Keep current topology foundation but postpone broad catalog/serviceability/motion work. | Reopened by product need; no general CAD/assembly platform built speculatively. |
| [ ] | 58 | 3D Viewer | DEFERRED | Preserve Scene IR only; visualization remains presentation, not authority. | Reopened when evidence-bound product visualization has concrete product value. |
| [ ] | 59 | Discovery Passports | PARTIAL | Create a durable record of what each promoted discovery survived. | Passport binds identities, evidence, attacks, budgets, providers, versions, fidelity history, and verdict limits. Status 2026-10-10: `DiscoveryPassport` + `verify_passport` (re-derives discipline, anchor and verdicts from the ledger); provider/version identity not yet bound. |
| [ ] | 60 | Provider / Independence Graph | PLANNED | Record solver/provider capability and real independence relationships. | Shared dependencies are explicit; independent confirmation only counts when independence policy is satisfied. |
| [ ] | 61 | Public Blindfold Leaderboard | DEFERRED | Build network-effect benchmark value after internal v1 is credible. | Third-party submission protocol, sealed scoring, versioned challenge sets, and public result rules exist. |
| [ ] | 62 | External Red-Team Engagements | DEFERRED | Apply the Red Team product to external engineering claims. | Internal seeded-flaw calibration complete; engagement outputs are reproducible and scoped. |
| [ ] | 63 | L6 Prospective Result | DEFERRED | Produce a real prospective result sealed before future measurements exist. | Prediction/protocol timestamped and sealed before data; later scoring uses independent external truth. |
| [ ] | 64 | Continuous Authority Hardening | IN_PROGRESS | Fix authority-critical defects immediately throughout the roadmap. | No known false-support, wrong-number, hidden-data leakage, evaluator-capture, or provenance/identity blocker remains open at a milestone. Status 2026-10-10: issuer-bound authority ledger (signed, persistent, key lifecycle, compromise windows) and issuer-bound credibility; four hostile reviews in the Big Rocks campaign, findings fixed or recorded in `docs/work/PROGRESS.md`. |
| [ ] | 65 | Deferred Hardening Ledger | IN_PROGRESS | Track low-risk lint/UI/package/refactor debt without blocking Big Rocks. | Every deferred item has reason, owner/trigger, and no hidden scientific-authority impact. |
| [ ] | 66 | Full Assurance / Recertification | NOW (Gate G0, owner-run) | Run the expensive SHA-bound campaign at a deliberate integration freeze. | FAST + SCIENTIFIC + required provider suites + mutations + scope/certificate checks pass on the exact final source SHA. |

## Milestone targets

Milestones are the gates in `docs/work/ACTIVE_PLAN.md` (G0, A1, A2, B1) and Genesis §18. The 2026-10-09 milestone text
("finish the existing three rocks", "Roadmap V2 first proof", "first externally impressive demo", "first scientific
result target", "6–12 month target") is archived verbatim in the Master Plan archive appendix; for strategic direction,
Master Plan Part I §4 governs (authority by scope, Master Plan §1).

## Progress metrics

Primary metric: **how many relevant capabilities advanced in evidence maturity** (computed stage,
`python -m tools.capability_maturity`), plus the Genesis measurement vector. The list below is secondary.

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

### 2026-10-11

- Planning consolidation: this file no longer carries execution authority (ACTIVE_PLAN does); added measurement labels
  and compute staging; replaced the closed execution policy with a status reconciliation; rows 41, 47, 49, 50 and 66
  re-dispositioned to match Master Plan Part I §4; milestone targets point to the ACTIVE_PLAN gates. Old text archived.
  No row was ticked DONE and no measurement was changed.

### 2026-10-09

- Created the unified FORGE performance/execution tracker.
- Preserved the owner's decision to finish the current three Big Rocks before the Roadmap V2 pivot.
- Recorded completed foundation work without treating scaffolds as qualification.
- Made Blindfold, evaluator isolation, FidelityGraph, Scientific Red Team, and credibility gaps the next high-leverage scientific priorities.
