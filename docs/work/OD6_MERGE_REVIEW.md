# OD-6 merge review package — `feat/od6-engineering-program-epic`

Prepared 2026-10-18 for the owner's review. **Nothing was executed** (no pytest, no checker run, no generator run), **no
PR was opened and nothing was merged.** This branch is the canonical OD-6 change of
`docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md`; it takes effect only when it is reviewed and merged.

- Base: `origin/main` `de11dffa` (re-fetched 2026-10-18; unchanged).
- Worktree: `D:/forge-od6`. It contains no Phase 1–3.5 code; the Phase branches are untouched and unmerged.
- Merge preview (`git merge-tree --write-tree origin/main HEAD`): **clean**. Against the Phase 3.5 branch: one
  docs-only textual conflict, `docs/work/PROGRESS.md` (both sides append; keep both entries).

## Decision implemented

Owner, in session, 2026-10-18: the active epic moves from the capability `battery.thevenin_1rc` to the research program
`engrt.numerical_foundations` (contract `docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md`), using the schema /2
research-program mechanism of `docs/work/OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md` (Option C) with this program instead
of Genesis.

**Build-first is explicit:** program gates order DECISIONS, never work. No gate requires `DV0` (the deferred-validation
gate), so every gate's scope — M1, M2, E1, E2, E3 — may be written and implemented before any test runs. M2 and E3
are only DECIDED after M1. Built-but-unverified work stays MISSING; nothing promotes a capability (Gate H).

## Cross-Domain Scientific Architecture Requirements (added 2026-10-18, owner direction)

The program contract now carries ten requirements CDAR-1..CDAR-10 (physics-agnostic shared structure; heat is the
first reference application), multi-domain acceptance criteria for M1, M2, E1, E2 and E3, and three architectural
fixtures (RC circuit, spring-mass, chemical mixing) that must exist before any of those gates is decided. They are
acceptance criteria, not a program or an exception. The evidence is the read-only audit
`docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md` (of the Phase 3.5 tree). Core semantic gaps (A-1, A-2, A-3, A-7, A-9)
are recorded for the Core compatibility review, not implemented. Pinned by
`test_the_program_contract_carries_the_cross_domain_architecture_requirements` (NOT RUN).

## Files

| File | Change |
| --- | --- |
| `docs/project/scientific_capability_completion.json` | schema /2; `active_epic` = the program; `research_programs` (gates DV0, M1, M2, E1, E2, E3, all MISSING); `exception_process` scoped to "outside the active epic's scope"; every capability unchanged |
| `tools/capability_maturity.py` | /1 refused ("migrate"); program validation (exact fields, own statuses, ordered `requires`, every decided gate cites repository-relative existing evidence, no maturity vocabulary, unique ids across both arrays, planned ids unique); a decided program cannot stay the epic; programs table rendered |
| `tests/test_capability_completion.py` | program pin, build-first pin (DV0 required by no gate), battery snapshot (stage and statuses fixed, evidence may only grow), negative tests for every back door, governance-document consistency (policy, PR template, matrix, ACTIVE_PLAN) |
| `docs/SCIENTIFIC_CAPABILITY_MATRIX.md` | **hand-edited** to the renderer's format (traced line by line by the review; confirm with the generator) |
| `docs/project/ENGINEERING_FOUNDATIONS_PROGRAM.md` | new program contract: build-first, scope per gate, Cross-Domain Scientific Architecture Requirements and per-gate criteria, preconditions, prohibitions, battery / EXC-1 / Genesis relationships, exit |
| `docs/work/CROSS_DOMAIN_ARCHITECTURE_AUDIT.md` | new read-only audit: generic / thermal-biased / missing per area, gaps A-1..A-12 mapped to CDARs and owners |
| `docs/project/SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md` | active-epic rule names the program; "Research program epics" section; A2 row |
| `.github/pull_request_template.md` | line 3 and the exception section name the program's scope |
| `docs/work/ACTIVE_PLAN.md`, `docs/work/PROGRESS.md` | epic line at the top, OD-6 row decided, stale battery / EXC-1 statements marked superseded on merge, progress entry |

## Read-only review (subagent, nothing executed) and dispositions

| # | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| M1 | MAJOR | BLOCKED_WITH_EVIDENCE could be recorded with no evidence | Fixed: every decided status needs evidence; test |
| M2 | MAJOR | Exit unreachable after a FAIL (dependants could never be decided); deferred semantics unstated | Fixed: BLOCKED allowed once requirements are decided either way; PASS/FAIL still need required PASS; deferred keeps the program open, stated; tests |
| M3 | MAJOR | The branch referenced unmerged Phase work as if on main | Fixed: DV0 covers "every DV row present when decided"; E1/E3 state the Phase landing as a precondition (not a `requires`); landing order stated |
| M4 | MAJOR | Ledger `exception_process` and PR template contradicted the program model | Fixed: both scoped to "outside the active epic's scope" |
| m | MINOR | ACTIVE_PLAN stale statements; not pinned | Fixed: top epic line (pinned by the test), stale statements marked superseded |
| m | MINOR | "G0" collided with the plan's "G0 Trust lane" | Renamed the program gate to **DV0** |
| m | MINOR | Scope mismatch (E3 areas; EXC-1's `claims/adaptive_resolution.py`) | Fixed |
| m | MINOR | `planned_capabilities` unchecked; DEFERRED needed nothing; absolute/`..` evidence paths escaped the repo | Fixed; tests |
| m | MINOR | Two-programs-one-id untested; a weak assertion | Fixed |
| m | MINOR | "Executed evidence" is only reviewable (any existing path satisfies PASS) | Recorded: the same limit as the capability gates; reviewers check the evidence |

## Verification to run before merging (NOT RUN)

```
python -m pytest tests/test_capability_completion.py benchmarks/battery_1rc_closure/tests/test_battery_1rc_closure.py -q
python -m tools.capability_maturity            # "coherent", or a stale-matrix error
python -m tools.capability_maturity --write    # only if the line above reports the matrix stale; then re-run it
python tools/forge_check.py --changed
```

## Certification impact

- `tests/test_capability_completion.py` is an `assurance_suites` recertification trigger
  (`tools/certification/recertification_scope.py`): this merge needs OD-3 recertification (or joins the pending OD-3
  candidate).
- The checker, ledger, matrix, policy, contract and PR template are outside the certified SCOPE.
- No `src/` file changes; no mutant targets a changed line.

## Merge checklist (owner)

- [ ] The verification commands above pass (or every failure is fixed on this branch).
- [ ] Merge this branch ALONE into `main` (merge commit, no squash/rebase, per OD-4/OD-5 practice); do not merge the
      Phase 1–3.5 branches with it.
- [ ] Record the recertification decision (OD-3).
- [ ] Accept the Cross-Domain Scientific Architecture Requirements as binding acceptance criteria of M1-E3.
- [ ] After merge: the Phase 3.5 proposals P35-A4/A5/E1/E2/E3 are covered by gates M1, M2, E1, E2, E3 — no separate
      exceptions; EXC-1 is superseded.

## Draft PR description

> **governance(OD-6): active epic → research program `engrt.numerical_foundations`**
>
> Owner decision OD-6 (2026-10-18). Re-points the active epic through the canonical mechanism: ledger schema /2
> (`research_programs`), checker, test pin, PR template, policy. Battery 1RC stays tracked at FUNCTIONAL with every gate
> and its evidence; Genesis A2 stays blocked. Program gates DV0, M1, M2, E1, E2, E3 — build-first: gates order
> decisions only, no gate requires DV0. A research result never promotes a capability.
>
> Capability impact: none (no stage changes). Active-epic exception: N/A (this PR changes the epic).
> Verification: see `docs/work/OD6_MERGE_REVIEW.md` (to be run before merge). Needs OD-3 recertification (test edit).
