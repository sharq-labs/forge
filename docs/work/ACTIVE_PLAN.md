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

## Verified state (2026-10-12; re-check before relying on it)

- `main` = `2d0fa6c3`. Since `4634eba` it also carries #128 (planning consolidation), #129 (test-suite runtime),
  #126 (authority ledger, real escrow, battery blind readiness `NOT_READY`), #123 (Trust Repair Pass 1: R3-01, R3-02)
  and #117 (NASA PCoE raw ingestion). Together with #124 (Big Rocks foundations) and #125 (Roadmap V2 R1–R8) these are
  built, **not certified and not qualified**.
- The hardened certificate (`certification/current_core_v2.json`, the owner's 2026-10-09 recertification carried by
  #123) binds `39d43456` (the #123 tree), **not** `main`. FAST on each landing tree (PROGRESS 2026-10-12, CPython 3.12,
  shallow clone) had 14 failures, identical to unmodified `main` `de36168e` in the same environment (certificate,
  freeze v1/v3/v4 manifests, batch56 r65, two mutation-workspace tests); UNCLASSIFIED. FAST on `2d0fa6c3` itself:
  **NOT RUN** (its tree differs from the last FAST tree `bfccb351` by one PROGRESS entry).
- GitHub rulesets: the REST API returns 403 (private repository on a free plan). No merge gate is enforced remotely.
- Open PRs: #107 self-hosted CI runner, #39 (draft) and #24 (base `claude/core-v2-hybrid-uq`): all BLOCKED in the
  2026-10-12 landing pass (OD-11, OD-15).
- Capability ledger (computed): `thermal.nafems_t3` EVIDENCE_BACKED; `battery.thevenin_1rc` FOUNDATION and still the
  test-pinned completion epic; nothing is PRODUCTION_READY.
- Negative results stand: four BIG 13 flagships `insufficient_evidence`; Kirkaldy fade NOT MET; LG M50 DFN NOT MET.
  Local-only, not on the remote: Battery Practical Pass 1 `7e923e75` (WEAKLY_IDENTIFIABLE). Trust Repair Pass 1
  `803946af` is on `main` through #123.

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
3. DONE 2026-10-12: PR #123 landed by merge commit after the `CLAUDE.md` gates and `forge-scientific-review` (PASS).
   The review's open LOWs: a REGISTRY_CHANGED bundle result carries the stored verdict without re-deriving it
   (`claims/replay/bundle.py`); `mcp/foundations.py` catches bare `Exception`.

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
| OD-3 | Recertification: which HEAD, and when (owner-run). | Certificate binds `39d43456`, not `main` `2d0fa6c3`; #126, #123, #117 and #129 all touch certified scope and landed unrecertified. |
| OD-4 | RESOLVED 2026-10-12 (owner direction: merge the open PRs that pass every gate). PR #123 lands by a merge commit (no rebase); it closes R3-01/R3-02 only. | Its certificate binds `39d43456` (the PR tree), not the merged `main`; recertification stays OD-3. |
| OD-5 | RESOLVED 2026-10-12 (owner direction: merge the open PRs that pass every gate). PR #126 lands as one PR; it creates no new scientific capability stage and changes no maturity. | +8,043 lines; new `engcore.authority`; real escrow is relevant to Genesis leakage controls. Not recertified (OD-3). |
| OD-6 | Completion epic: keep `battery.thevenin_1rc` (PR #117) or re-point it; or approve one narrowly scoped A2 exception. | Pinned by the ledger, `tests/test_capability_completion.py` and the PR template (CONTRACT_PIN: a change needs its own reviewed PR). Blocks A2. No blanket Track A/B exemption exists (Completion Policy, anti-loophole rule). |
| OD-7 | Timebox windows for G0, A1, A2, B1. | None set; no dates invented here. |
| OD-8 | External evaluator for Genesis hidden tasks: name a person or group, or fix a selection process and deadline. | Required before the A1 freeze names its held-out protocol, and before Genesis Step 6. |
| OD-9 | RESOLVED. PR #128 supersedes PR #127 and contains Genesis plus the reviewed planning consolidation. PR #127 was closed without merge; its branch remains preserved. | PR #127 existed as the standalone Genesis document. |
| OD-10 | Publish or record the local-only commit `7e923e75`. (`803946af` is on `main` via #123.) | Not verifiable from the remote. |
| OD-11 | Branch and PR hygiene: close, rebuild or land #107, #39, #24. | About 119 remote branches. #107 (237 behind): certificate conflict between two owner certificates, and it rewrites the CI control-plane workflows and adds self-hosted runners with secrets. #39 / #24 (1,500+ behind) edit frozen Core; see OD-15. |
| OD-12 | Confirm the control-plane budget signal (Master Plan §5.3). | Proposed: ~20 % warning plus a two-checkpoint no-progress signal. |
| OD-13 | Confirm the B1 demo system. | Drone recommended: the only executable product chain today. |
| OD-14 | LANDED as #129 (`de36168e`); recertification still OD-3. Was: branch `perf/test-suite-runtime`: land it (needs the OD-3 recertification: it touches `certified:harness`, `inference_admission`, `certification_control`), and decide whether to add V4 mutation entries for the admission-record memo (changes the certified population count of 680). | Owner-requested. FAST 992 s -> 476 s, SCIENTIFIC 1448 s -> 1024 s, same failure sets (PROGRESS 2026-10-12). Review F1–F4 fixed; the memo's three mutants are killed by `tests/inference/test_admission_record_memo.py` today, outside the certified population. |
| OD-15 | `ScientificResult.is_usable`: keep "converged and no failed check" (validity excluded), or require every declared model IN_DOMAIN as #39 / #24 propose. | `docs/assurance/CORE_SEMANTIC_INVARIANTS.md` records the exclusion as deliberate and a test pins the 6×4 truth table; on `main`, OUTSIDE_VALIDATED_DOMAIN and UNKNOWN validity are `is_usable`. A scientific-design decision on frozen Core, not a merge fix. #24's UQ refusals already exist on `main` (different messages). |

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
- 2026-10-12 — PR #126 (authority ledger, real escrow, battery blind readiness `NOT_READY`) merged with `main` on owner
  direction (OD-5). Its follow-ups (designate the battery confirmatory dataset, provision a production authority ledger,
  seal real battery falsifiers, systematic prior-art search, deploy the data authority behind the escrow) are owner-gated
  and sit under LATER with row 47. Kirkaldy stays NOT MET; no confirmatory datum was exposed. Not recertified (OD-3).
- 2026-10-12 — PR #123 Trust Repair Pass 1 (R3-01 offline revalidation, R3-02 MCP `assess_claim` delegating to the
  canonical claim runtime) merged with `main` on owner direction (OD-4). `803946af` is therefore on the remote (OD-10,
  partly). R3-03 to R3-16 stay open. Not recertified on the merged tree (OD-3).
- 2026-10-12 — PR #117 (deterministic NASA PCoE raw ingestion for the active epic `battery.thevenin_1rc`) merged with
  `main` on owner direction. Ingestion only: `real_data` stays `MISSING`, no SOC / pulse-rest / sensor uncertainty /
  R0-R1-C1 is inferred, and the capability stays FOUNDATION. Its ACTIVE_PLAN edit (an old-queue section with
  re-encoded characters) was not carried; its prereg is `docs/milestones/battery-1rc-production-closure-prereg.md`.
- 2026-10-12 — landing pass closed: #126, #123, #117 merged (`2d0fa6c3`); #107, #39, #24 blocked (OD-11, OD-15).
  Verified state updated. Next agent-executable G0 action is unchanged: FAST on the OD-3 HEAD in a full-history
  checkout, then classify the 14 failures.
