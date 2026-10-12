# Active Plan

**The only executable queue.** Scope (Master Plan §1): this file owns only "what work is active right now?". It may not
override Genesis science, Completion maturity rules, Performance measurement semantics or `CLAUDE.md` repository
constraints; execution authority does not imply semantic authority outside its scope. Strategy: `docs/project/FORGE_MASTER_PLAN.md` Part I. Track A science:
`docs/discovery/FORGE_GENESIS.md`. Maturity: `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`. History up to
2026-10-10 (BIG 14 queue, Big Rocks program, Local Assurance passes 2–13): `docs/work/archive/ACTIVE_PLAN_HISTORY_TO_2026-10-10.md`
— not a queue. Last consolidated: 2026-10-11.

## Objective

Prove a trustworthy, measurable scientific reasoning loop. Order: **G0** Trust lane → **A1** Genesis-lite measurement →
**A2** Minimal Mind → **B1** narrow real demo. One Trust architecture, one Mind; no second authority.

## Verified state (2026-10-11; re-check before relying on it)

- `main` = `4634eba` (PR #122). It contains PR #124 (Big Rocks foundations) and PR #125 (Roadmap V2 R1–R8: Blindfold,
  escrow, falsifiers, multiplicity, novelty, Red Team, credibility vectors, FidelityGraph, discovery providers).
  These are built, **not certified and not qualified**.
- The hardened certificate (`certification/current_core_v2.json`, recertified 2026-10-09 in `d383eed0`) binds commit
  `3e396bc4` on `local/r1r4-assurance`, **not** `main`. The last recorded FAST run (on `1e7cbebc`, PROGRESS 2026-10-10)
  had 14 failures, all in the known base-drift set (certificate, freeze v1/v3/v4 manifests, batch56 r65, two
  mutation-workspace tests). FAST on `4634eba`: **NOT RUN**.
- GitHub rulesets: the REST API returns 403 (private repository on a free plan). No merge gate is enforced remotely.
- Open PRs: #123 Trust Repair Pass 1 (conflicts; base `44637065`); #126 authority ledger + real escrow + battery blind
  readiness (mergeable; starts a new foundation); #127 Genesis document; #117 battery 1RC NASA ingestion (conflicts);
  stale #107, #39, #24.
- Capability ledger (computed): `thermal.nafems_t3` EVIDENCE_BACKED; `battery.thevenin_1rc` FOUNDATION and still the
  test-pinned completion epic; nothing is PRODUCTION_READY.
- Negative results stand: four BIG 13 flagships `insufficient_evidence`; Kirkaldy fade NOT MET; LG M50 DFN NOT MET.
  Local-only, not on the remote: Trust Repair Pass 1 `803946af`; Battery Practical Pass 1 `7e923e75` (WEAKLY_IDENTIFIABLE).

## Current gate: G0 — Trust lane

| Field | Value |
|---|---|
| Start condition | Now. |
| Window | OWNER_DECISION_REQUIRED (OD-7). |
| Exit gate | The certificate binds the intended `main` HEAD, **or** every unresolved failure is classified with evidence and no `SCIENTIFIC_CORRECTNESS` or `UNCLASSIFIED` item remains open. |
| Circuit breaker | Window expired → Master Plan §5.2: classify (unclassified = blocking), preserve the red result, document here, then fix / isolate / ask. Never loosen a gate. |
| Outcomes | PASS · FAIL · BLOCKED_WITH_EVIDENCE · DEFERRED_BY_OWNER |

Next actions (agent-executable now):

1. Run the FAST tier on the intended certification HEAD selected by OD-3, normally the post-merge `main` HEAD, in a
   supported environment (3.11 or 3.12); record exact failures in PROGRESS. Compare failures against the previously
   recorded 14-test drift set only where still applicable; the historical drift set is not current truth.
2. Classify every failure as `SCIENTIFIC_CORRECTNESS`, `GOVERNANCE_ONLY` or `UNCLASSIFIED` (Master Plan §5.2).
   `GOVERNANCE_ONLY` needs the complete six-question evidence record; anything less stays `UNCLASSIFIED` and blocking.
3. Rebase PR #123 onto current `main` locally, run the `CLAUDE.md` gates and `forge-scientific-review`, and report.
   Do not push, merge or recertify without the owner.

Owner-run: hardened recertification (it writes the certificate); merges (OD-3, OD-4).

## Track A — Discovery credibility

**A1 Genesis-lite measurement** (Genesis §18 Step 1, on the existing `engcore.blindfold`)

| Field | Value |
|---|---|
| Start condition | Preparation now, limited to benchmark, governance, measurement, stabilization or evaluation infrastructure as the Completion Policy allows for A1 (documents, specifications, a pilot cost measurement; no certified file touched; no new scientific capability). The preregistration freeze and the formal ≥20-seed baseline runs start when G0 exits (PASS, or `GOVERNANCE_ONLY` blockers isolated with complete evidence records). |
| Window | OWNER_DECISION_REQUIRED (OD-7). |
| Exit gate | Genesis Step 1 gate: frozen preregistration digest, frozen baseline set (Genesis §10.5), baseline distributions over ≥20 seeds, owner-approved compute estimate (Genesis §10.6). |
| Circuit breaker | Window expired → record what was measured as smoke-scope only and ask the owner. No maturity claim. |
| Outcomes | PASS · FAIL · BLOCKED_WITH_EVIDENCE · DEFERRED_BY_OWNER |

Next actions: draft the Genesis-lite preregistration (task classes, scoring, baselines, leakage-control status
including the escrow's `SECURITY_BOUNDARY_NOT_PROVEN` label); measure per-run cost at the 10-run rung; write the compute
estimate.

**A2 Minimal Mind** (Genesis Step 2). Start: A1 PASS **and** the Completion Policy condition — the active epic formally
changed (OD-6) or a complete, owner-approved, unexpired narrowly scoped exception. Neither exists today. Window: OWNER_DECISION_REQUIRED. Exit: lift over the strongest
applicable frozen baseline with confidence intervals, calibrated predictions scored by a proper scoring rule, LLM-ablation
arm reported. Reuse owners from `docs/architecture/discovery_authority_map.md`; new Mind code must justify why an
existing owner cannot serve.

## Track B — Narrow real demo

**B1 Infeasible-specification refusal and correction** (candidate: drone; OD-13)

| Field | Value |
|---|---|
| Start condition | Preparatory engineering when A2 starts. The demo itself runs only after the A2 gate PASSES. |
| Window | OWNER_DECISION_REQUIRED (OD-7). |
| Exit gate | The user's infeasible requirement is refused and the binding physical constraint is named; a corrected admissible specification is executed through real providers; uncertainty and applicability are reported; the evidence bundle replays; a scientific review is clean. |
| Circuit breaker | Window expired → the existing Trust-only refusal behavior may be recorded or demonstrated separately, explicitly labelled as NOT a B1 completion and NOT evidence of Minimal Mind / Genesis capability, with no maturity change and no bypass of the A2 PASS gate; otherwise BLOCKED_WITH_EVIDENCE. |
| Outcomes | PASS · FAIL · BLOCKED_WITH_EVIDENCE · DEFERRED_BY_OWNER |

Substrate: `engcore.systems.products.drone_coupled` (steady algebraic hover chain; every coefficient a declared input;
uncertainty UNKNOWN) through MCP `run_product_screening(..., screening="coupled_hover")`. Missing: admitted component
data with provenance, one external validation route, quantified uncertainty. Preparation uses already-built
capabilities only; a new capability foundation for the demo (model, provider adapter, synthesis engine) follows the same
Completion Policy rule as A2. Rules: a correction is a PROPOSED
hypothesis until the Trust Layer admits it; the demo changes no maturity stage; it never substitutes for A1/A2 results.

## Not now

Everything in Master Plan §4 NEXT, LATER and DEFERRED. In particular: no new providers without a named benchmark, no
product depth beyond B1, no viewer/assembly/motion work, no GPU/HPC orchestration, no fusion, biomedical or
therapeutic work.

## OWNER_DECISION_REQUIRED

| ID | Decision | Facts |
|---|---|---|
| OD-1 | Merge-gate enforcement: make the repository public, upgrade the plan, or formally accept local SHA-bound assurance as the only merge control. | Rulesets API 403; red gates cannot block merges. |
| OD-2 | Supported Python policy. | `requires-python >=3.11`; CI 3.11/3.12; local runs on 3.13 and 3.14. |
| OD-3 | Recertification: which HEAD, and when (owner-run). | Certificate binds `3e396bc4`, not `main`. |
| OD-4 | PR #123: land plan. | Conflicts against `main`; closes R3-01/R3-02 only. |
| OD-5 | PR #126: land, hold or split. | +8,043 lines; new `engcore.authority`; real escrow is relevant to Genesis leakage controls. |
| OD-6 | Completion epic: keep `battery.thevenin_1rc` (PR #117) or re-point it; or approve one narrowly scoped A2 exception. | Pinned by the ledger, `tests/test_capability_completion.py` and the PR template (CONTRACT_PIN: a change needs its own reviewed PR). Blocks A2. No blanket Track A/B exemption exists (Completion Policy, anti-loophole rule). |
| OD-7 | Timebox windows for G0, A1, A2, B1. | None set; no dates invented here. |
| OD-8 | External evaluator for Genesis hidden tasks: name a person or group, or fix a selection process and deadline. | Required before the A1 freeze names its held-out protocol, and before Genesis Step 6. |
| OD-9 | RESOLVED. PR #128 supersedes PR #127 and contains Genesis plus the reviewed planning consolidation. PR #127 was closed without merge; its branch remains preserved. | PR #127 existed as the standalone Genesis document. |
| OD-10 | Publish or record the local-only commits `803946af` and `7e923e75`. | Not verifiable from the remote. |
| OD-11 | Branch and PR hygiene. | About 119 remote branches; stale PRs #24, #39, #107. |
| OD-12 | Confirm the control-plane budget signal (Master Plan §5.3). | Proposed: ~20 % warning plus a two-checkpoint no-progress signal. |
| OD-13 | Confirm the B1 demo system. | Drone recommended: the only executable product chain today. |
| OD-14 | Branch `perf/test-suite-runtime`: land it (needs the OD-3 recertification: it touches `certified:harness`, `inference_admission`, `certification_control`), and decide whether to add V4 mutation entries for the admission-record memo (changes the certified population count of 680). | Owner-requested. FAST 992 s -> 476 s, SCIENTIFIC 1448 s -> 1024 s, same failure sets (PROGRESS 2026-10-12). Review F1–F4 fixed; the memo's three mutants are killed by `tests/inference/test_admission_record_memo.py` today, outside the certified population. |

## Active-epic exceptions (open)

None. An exception is valid only with every field the Completion Policy requires (scope, allowed work, reason, start,
exit, expiry, owner approval, prohibitions).

## Stop conditions

Stop and surface a blocker if a change would: weaken UNKNOWN or fail-closed semantics; change a frozen serialized
contract without a version decision; invent measurements, uncertainty, validation, provenance or evidence; duplicate an
existing scientific identity or authority; add domain-specific branches to the generic Core; treat convergence, replay or
solver agreement as validation; change a tolerance or criterion after seeing a result; or bypass an assurance gate.

## Checkpoint log

- 2026-10-11 — planning consolidation (docs only): Big Rocks First and P0–P40 superseded; this file reduced to the live
  queue; history archived. No code, test, result, threshold or certificate changed.
- 2026-10-12 — owner-requested, outside the queue: test-suite runtime branch `perf/test-suite-runtime` (OD-14). Tier
  relabelling and duplicate-work removal; no assertion, tolerance or result changed. Not merged, not recertified.
- 2026-10-12 — PR #117 (deterministic NASA PCoE raw ingestion for the active epic `battery.thevenin_1rc`) merged with
  `main` on owner direction. Ingestion only: `real_data` stays `MISSING`, no SOC / pulse-rest / sensor uncertainty /
  R0-R1-C1 is inferred, and the capability stays FOUNDATION. Its ACTIVE_PLAN edit (an old-queue section with
  re-encoded characters) was not carried; its prereg is `docs/milestones/battery-1rc-production-closure-prereg.md`.
