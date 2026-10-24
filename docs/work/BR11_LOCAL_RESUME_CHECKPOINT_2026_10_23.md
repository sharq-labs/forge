---
ai_schema_version: 1
doc_id: FORGE-BR11-LOCAL-RESUME-CHECKPOINT-20261023
doc_kind: SNAPSHOT
doc_status: SNAPSHOT
authority_scope: NONE
source_ref: a96baa64e03be498bf2f6001ec86c6bff4eb3698
evidence_level: MIXED
last_reviewed: 2026-10-23
supersedes: none
---

# GEN2-BR1.1 — local resume checkpoint (2026-10-23)

**State: IN_PROGRESS. Not closed, not certified, not merged.** Resume index only: the executable queue is
[ACTIVE_PLAN](ACTIVE_PLAN.md) (its top entry), the report is
[benchmarks/mind_gen2_authority_v1/README.md](../../benchmarks/mind_gen2_authority_v1/README.md), the history is
[PROGRESS](PROGRESS.md) (last entry, "GEN2-BR1.1", items 1-27). Preserved cloud evidence:
[evidence/br11_cloud_2026_10_23/](evidence/br11_cloud_2026_10_23/README.md).

## Repository state

| Item | Value |
|---|---|
| Branch | `research/mind-gen2-authority-binding-v1` (pushed to `origin` at the handoff; no PR) |
| Base | `1202ea6c3d96f5c31d0b142a32438da75e020cae` (BR1's report commit = tip of `origin/research/mind-gen2-scientific-world-v1`) |
| State this file describes | `a96baa64e03be498bf2f6001ec86c6bff4eb3698` (gates record); code `d5ef1e32f2b0976fc46e07aa5db3f3148173495d`; records `ec2c00067062fe0989617ff576707fe57e66b949` |
| HEAD after the handoff | the handoff commit(s) on top of `a96baa6` (docs and evidence only: no source or test change); `git log --oneline -3` |
| Relation to main | merge-base with `origin/main` (`5ac5267`) is `12862b0`; main is 2 commits past it; this branch is 92 past it |
| Worktree | clean at the handoff |
| Other local branches/worktrees (`tmp/br11-*`, `/home/user/forge-*`) | cloud scratch only, not pushed, not needed |

## Objective and closure criteria

Repair GEN2-BR1's AUTHORITY_DUPLICATION_BLOCKER: the Mind's `ScientificWorld` is a verified projection of FORGE's
owners, and admission and dispatch are non-bypassable (brief: [BRIEF.md](evidence/br11_cloud_2026_10_23/brief/BRIEF.md)).
Closure (brief §24/§25/§32/§34) requires all of: Q1-Q7 all NO from an independent review round (PARTIAL is not enough);
0 BLOCKER and 0 MAJOR after skeptics; the three BR1 MAJORs closed; no raw proposal executes; no stale or missing
binding admits; no duplicate state/applicability/unit/search-space authority; Gen1 intact; replay exact; cross-domain
holds; the changed-file differential has no new deterministic failure. Only then README §10/§12 are filled and one
conclusion chosen (READY_FOR_HYPOTHESIS_PORTFOLIO only with the full gate). Loop until 0/0 or a precise owner blocker;
do not loop on cosmetic MINORs.

## Review rounds (six lenses A-F from round 7; two skeptics per BLOCKER/MAJOR; a completeness critic)

| Round | SHA | B / M / m | Outcome |
|---|---|---|---|
| 1-7 | `5ee16c5`..`27b9f71` | see README §9 | each found a BLOCKER or MAJOR, fixed |
| 8 | `15725ec` | 0 / 0 / 36 | Q4 PARTIAL (lens F, critic) |
| 9 | `ceaf8cd` | 0 / 0 / 38 | Q1-Q7 NO from every lens and the critic; MINORs changed in `17a1c31`/`e573096` |
| 10 | `c69e579` | 0 / 2 / 36 | round 9's changes left two MAJORs in the budget follower; fixed `d89dd3b` |
| 11 | `aad2f69` | 0 / 3 / 22 | round 10's changes left MAJORs (below); fixed `d5ef1e3` |
| 12 | `a96baa6` | none | **INTERRUPTED / INCOMPLETE**: no result (below) |

Round 11's MAJORs and dispositions (code `d5ef1e3`, controls `tests/mind/test_authority_review_r11.py`):
- **R11-C-F1 = F11-1**: round 10's `deepcopy` of the served experiment ran outside the classifying try; owner-valid
  content nested ~500 deep raised out of every verification, so a handed spend was never observed and a restore
  re-dispatched the executed action. Fixed: every read-back step under one classification; served records parsed from
  the owner's cached JSON text.
- **F11-2**: a handed mapping the strict constructor refused (a `numpy.str_` id, an alias) hid a spend on another
  account. Fixed: the snapshot is read entry by entry (str subclass = its plain str; non-str key skipped; mistyped
  account refused for good; alias observed, refused to that verification).

## Latest Q1-Q7 (round 11 at `aad2f69`; round 12 returned none)

Q1, Q2, Q3, Q5, Q6, Q7: NO from every lens and the critic. **Q4: YES** (lenses C, F, critic), PARTIAL (A, B, D), NO (E).
Not re-assessed after `d5ef1e3`. Before (BR1 round 2): Q1 YES, Q2 YES, Q3 YES/PARTIAL, Q4 YES, Q5 YES, Q6 YES, Q7 PARTIAL.

## Latest execution evidence (cloud, Linux, CPython 3.13.16; commands in PROGRESS items 1, 5, 10, 25, 26)

| Check | Result |
|---|---|
| BR1.1 suite (item 1: `tests/mind`, both benchmark test dirs, ledger identity) at `ec2c000` | 649 passed |
| Round-11 controls | 37; on `aad2f69` 20 fail, 17 pass (controls of earlier guards); 13 mutants each caught |
| FAST (`-m "not expensive"`) at `ec2c000` | 94 failed, 5 errors, 12632 passed; failing ids = the base's 99: NEW 0, FIXED 0. FAST is red on the base: **NOT green** |
| Regression pack | 279 passed |
| Guard suites | 1364 passed, 2 failed = the base's two pre-existing failures, identical messages |
| Affected expensive minus campaign | 13 failed, 14 errors, 335 passed = the base's 27 failing ids |
| Gen1 (`gen1_reference --check`) | INTACT |
| `rescore --check` / `run_benchmark --check` | MATCHES / MATCHES |
| Performance (README §8, `d5ef1e3`) | admission p50 16.8 ms; check +7 % to +27 % vs BR1 at p50 by host state |
| Caveat (B11-4) | an overloaded desk (8 threads, a 2500-evaluation account changing every 0.1 s) admits 3-48 of 48 per run (median 38; `aad2f69` median 44), the rest refused "in flight" after `WAIT_S`, fail-closed; 48/48 at 1000 |

## Open items

- **Round 12** (`ROUND12_STATUS.md` in the evidence directory): stopped on the owner's instruction after lenses A and B
  had started and before any lens returned; no skeptic, no critic. Their probes reproduced leads at `a96baa6` that,
  if confirmed, are MAJOR-class in `owners.BudgetReader`: an exception whose `__str__` raises escapes the read-back
  classification (b1201/b1202: re-dispatch after a restore); a str-subclass key spelling an id beside the plain key
  is silently collapsed (b1205/a1205: re-dispatch); a deterministic "changed during iteration" text or a varying
  message hides a spend (b1204/b1208); plus availability leads (unbounded fresh-thread `join`, a torn fresh-thread
  retry refused for good, a recursion error wrapped by the unit owner) and three surviving mutants.
- **Documented residuals** (README §4/§11): at-most-once execution and reservation are the execution owner's; states
  never observed (README §4 list); a stuck `accounts()` or read-back refuses others after `WAIT_S`; ledger values
  `default=str` stringifies; the level rounding edge; the cross-unit level owner question (ACTIVE_PLAN); missing owner
  capabilities (hard enclosure / coverage policy: 9 of 21 base proposals MISSING_INFORMATION; protocol owner;
  reservation; provider status loader).
- **Certification**: UNCERTIFIED. `budget.py` (CORE_CERTIFIED) and the certified harness tests need hardened
  recertification before any merge: NOT RUN (OD-3 boundary). SCIENTIFIC tier: NOT RUN.
- **Push / PR / merge**: branch pushed at the handoff; no PR; not merged; main untouched.

## Resume locally

```bash
git fetch origin research/mind-gen2-authority-binding-v1
git switch research/mind-gen2-authority-binding-v1      # or: git switch -c ... --track origin/...
python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"   # as the repository's TESTING.md says
PYTHONPATH=src:. python -m pytest tests/mind benchmarks/mind_gen2_authority_v1/tests \
    benchmarks/mind_gen2_world_v1/tests tests/test_sria_budget_ledger_identity.py -q -p no:cacheprovider -n 4
# expect 649 passed; then: python -m benchmarks.mind_gen2_authority_v1.rescore --check ; ... run_benchmark --check ;
# python -m benchmarks.battery_rediscovery_v3.gen1_reference --check
```

**Next bounded task (ACTIVE_PLAN):** R12-T1 — reproduce each round-12 lead listed above at HEAD from its preserved probe;
for each confirmed bypass fix `owners.BudgetReader` with a failing-first control (and a mutant that the control
catches), classify the rest as fixed or documented; then run one complete fresh review round (all six lenses, skeptics,
critic). No other scope.
