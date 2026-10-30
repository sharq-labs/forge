---
ai_schema_version: 1
doc_id: FORGE-BLINDFOLD-STEP1-GAP-CLOSURE-SESSION-A
doc_kind: EVIDENCE_REPORT
doc_status: ACTIVE
authority_scope: NONE
source_ref: 0af67b4bd9f7846bca59c66719a793f4a7a3a044
evidence_level: EXECUTED
last_reviewed: 2026-10-31
supersedes: none
---

# Step record: Blindfold Step 1 gap closure, Session A (2026-10-30)

One record per step ([template](templates/STEP_RECORD_TEMPLATE.md)). `ACTIVE_PLAN.md` stays the queue and
`PROGRESS.md` holds the executed commands. **This record is updated as Session A proceeds; `source_ref` is the commit
its latest update describes.**

## 1. Decision

- **Step / ACTIVE_PLAN section:** "Blindfold Step 1 gap closure, Session A (owner, 2026-10-30)".
- **Owner approvals (chat, 2026-10-30):** "Accept defaults" (D1–D8); "يلا ابدا"; the checkpoint answers D9 (empirical-Bernstein), D10 (FDA-06 A+B), D11 (process per universe), D12 (Codex), D13 (option C, after option A was withdrawn), D14 (roster and scope).
- **Options considered:**
  - inference: Hoeffding / Hoeffding with more units / empirical-Bernstein / sign-flip. Sign-flip is rejected: its type-I error is 0.105 under a skewed null.
  - isolation: proposer_process (same account) / per-campaign OS isolation / per-universe OS isolation (chosen, D11).
  - region tell: extended region for all kinds (withdrawn: every gated arm would refuse everything) / p = 0.8 / disclose and stratify (chosen).

## 2. Gap register: state at this record

| Gap | State | Evidence |
|---|---|---|
| G1 power | **DECIDED + IMPLEMENTED.** Empirical-Bernstein (`analysis_v4`). Detects about 0.18/unit at n = 2400 (development estimate) | power draft; `test_analysis_v4.py` |
| G2 FDA-06 | **CLOSED (code).** Every law kind is capped; out-of-family credit is reported apart | the FDA-06 test is parametrized over all three kinds; mutation KILLED |
| G3 FDA-18 | **CLOSED (code).** One isolated proposer per universe; no state passes between processes | persistence test; the F1 integration mutant was KILLED (marks found in /dev/shm, /run/lock, /var/crash without the fix). 2026-10-31: the kernel user keyring was a channel (reproduced); a fresh user namespace per process closes it, and its mutant is KILLED (`0af67b4b`) |
| G4 FDA-19 | **CLOSED (tests).** v0.4 attacks cover the root dir, operator outputs, pilot_results, other /opt checkouts, drvfs, network, /proc and persistence | `test_v04_isolation.py`, 14 → 16 integration tests |
| G5 B-LEAK | **IMPLEMENTED + EXECUTED on this host.** OS isolation per universe, verified from outside per process | root runs at `8fbcb710`; no claim beyond this host/config |
| G6 FDA-21/22 | **DECIDED / DISCLOSED.** pysr_units uses the precision bar with its constant count; the region tell is disclosed and stratified | design draft §4–5; strata in `analysis_v4` |
| G7 PySR | **OPEN.** pysr_units is implemented but has not run. The Julia depot (675 MB under /home, hidden in isolation) must be exposed read-only under /opt | waits for the OD-3 run to finish |
| G8 driver | **CLOSED.** `pilot_v4` is in-tree; the root comes from a 0600 file outside the tree; the commitment is written before the run | `test_v04_pilot.py` root run |
| G9 manifest | **CLOSED.** `environment.json` and its digest | same |
| G10 cost | **OPEN.** Isolated measurement not run yet | waits for OD-3 |
| G11 certificate | **OPEN (Session B).** The other session's OD-3 is running on `921f8d26`; the v0.4 files need the next batch | — |
| G12 independent review | **DECIDED (Codex, owner runs it).** Not done | — |
| G13 dress rehearsal | **OPEN (Session B)** | — |
| G14 operator identity | **CLOSED.** The operator is root; proposers are uid 65534 in another pid namespace; the visible-process attack finds no readable process | integration test |
| G15 circularity | **DISCLOSED + STRATIFIED** | `strata()`; the candidate preregistration |
| G16 clean SHA | **CLOSED (code).** The formal tier refuses a dirty tree | `pilot_v4.run` |
| FDA-05 | Already closed in v0.3 (escrow_v3, owner 2026-10-29) | ACTIVE_PLAN |
| O-1 | **CLOSED (design).** The bootstrap tail is never a p-value; empirical-Bernstein instead | power draft §4 |

## 3. Review

- `forge-scientific-review` (forked, read-only, static), 2026-10-30: **CHANGES REQUIRED** (2 HIGH, 5 MEDIUM, 5 LOW). All fixed in `8fbcb710`. 9/9 fix-reverting mutations are KILLED, and the F1 integration mutant is KILLED.
- **Recorded, not fixed:**
  - 12b, the control-kind margin 0.10 vs P-1 "no loss allowed": an owner reading;
  - the IUT-vs-Holm proposal: D9 stands until the owner decides.
- Re-review of those fixes (forked, read-only, static), 2026-10-31, at `1979907f`: **CHANGES REQUIRED**:
  - 2 HIGH: `decide_v4` trusted a supplied reveal; no identity or freeze check at decision time;
  - 3 MEDIUM: incomplete runs not blocked; unknown outcome scored 0; kernel keyring shared across proposers;
  - 4 LOW.
  All fixed in `0fd4376a` and `0af67b4b` (PROGRESS 2026-10-31). 15/15 fix-reverting mutations are KILLED. M3 was
  reproduced on this host before the fix, and its integration mutant is KILLED.
- **Not yet done:** a fresh review of the 2026-10-31 fixes; Codex review of the candidate (D12).

## 4. Evidence and readiness

| Axis | State | Command / SHA / location |
|---|---|---|
| Implementation | v0.4 path complete except a PySR run under isolation | `857f88cb`..`cb24af3e` |
| Execution (tests) | Windows: v0.4 files pass (66 + 8 + 4, skips are platform skips). WSL root `/opt` clone: 84 passed, 3 skipped at `8fbcb710` | PROGRESS 2026-10-30 Session A |
| Scientific validation | NOT APPLICABLE / NOT RUN: no formal campaign; development smoke only | — |
| Certification (OD-3) | NOT RUN for v0.4 files; the other session's OD-3 on `921f8d26` is in progress | — |
| Preregistration | CANDIDATE built in the clean clone at `8b6f43d0` (SHA-256 `2d87e581…6bbfa2`); NOT FROZEN; 5 blocking open items | `docs/work/proposals/genesis_lite_v0_4.CANDIDATE.json` |
| Owner permission | Local commits only; nothing pushed to `main`; no merge | — |
