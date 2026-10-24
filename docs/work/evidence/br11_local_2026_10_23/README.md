# GEN2-BR1.1 local-session evidence, 2026-10-23

**UNCERTIFIED. Developer triage, test and measurement evidence for an IN-PROGRESS repair: not a review result, a
validation, a certification or a closure result.** Context: `docs/work/PROGRESS.md` GEN2-BR1.1 item 28 and README §5,
§8, §9 of `benchmarks/mind_gen2_authority_v1/`.

## Provenance

| Item | Value |
|---|---|
| Environment | WSL2 Ubuntu 24.04 (kernel 6.6.87.2-microsoft-standard-WSL2), 20 CPUs, CPython 3.12.3 |
| Checkout | native clone `~/forge-gen2-authority-v1` from a full-history bundle of `origin/research/mind-gen2-authority-binding-v1` at `d40aff44`; `.venv` with `pip install -e ".[dev,mcp,oracles]"` |
| Base | worktree `~/forge-gen2-base-1202` at `1202ea6c` (BR1's report commit), run with the same interpreter |
| Copied from | `~/br11-logs/` (the session's log directory); file contents are byte-identical copies |

## Layout

| Path | Content |
|---|---|
| `baseline/` | the BR1.1 suite and the three checks at `d40aff44` before any change (`summary.txt`, `env.txt`) |
| `r12_probes_d40aff44/` | every preserved round-12 probe re-run unchanged at `d40aff44` (one output per probe; `_summary.txt`) |
| `controls/` | the round-12 controls on the tree before the fix, as first run with 17 controls (`r12_controls_prefix_d40aff44.txt`: 13 failed, 4 passed), before the eighteenth (`test_a_state_not_read_back_while_a_rollback_waits_refuses_the_rollback`) was added; the 18-control figure (14 failed, 4 passed) is `mutation/summary.txt` `[base]`, which ran the committed 18-test file on a tree whose `owners.py` is `d40aff44`'s (round 13, E13-F6 / D13-3) |
| `mutation/` | `mutate_r12_local.py`, `run_mutants_local.sh`, `summary.txt` (base + 18 mutants) |
| `checks_33258438/` | the BR1.1 suite and the three checks at the fix commit |
| `gates/` | `gates.sh`; per tree (`base_1202ea6c`, `branch_33258438`): `summary.txt`, `fast_failing_ids.txt`, `guards_failing.txt`, `expensive_failing_ids.txt`, `env.txt` |
| `performance/` | `ab_r12.py`, `b1209_p24_instrumented.py` (the preserved probe with a signature-agnostic counter), `ab_r12.jsonl` |
| `EVIDENCE_MANIFEST.sha256` | SHA-256 of every other file here |

The base's guard-suite run in `gates/base_1202ea6c/summary.txt` collected no tests (it named the BR1.1-only
`tests/test_sria_budget_ledger_identity.py`); it was re-run without that file (`guards_failing.txt` is that re-run's).

## Verify

From this directory: `sha256sum -c EVIDENCE_MANIFEST.sha256`.

## Round 13 (added with the round-13 fix)

| Path | Content |
|---|---|
| `review_results/review_r13_result.json` | the fresh review round 13 at `3b407ddb`: six lens outputs (findings, prior-closure checks, Q1-Q7), every skeptic verdict and the critic, as the workflow returned them |
| `round13/mutation/` | `mutate_r13_local.py`, `run_mutants_r13.sh`; `summary_first_pass.txt` (base = the round-13 controls and the restated round-11 control on a tree whose `owners.py` is `3b407ddb`'s, plus 32 mutants: 31 caught, `box_before_alive` passed); `summary_rerun_tightened_control.txt` (base and `box_before_alive` again after that control was tightened to require the record be served: caught) |
| `round13/checks/`, `round13/gates/`, `round13/performance/` | the BR1.1 suite and checks, the gates against `1202ea6c` and the A/B at the round-13 fix |

## Round 14 (added with the round-14 fix)

| Path | Content |
|---|---|
| `review_results/review_r14_result.json` | the fresh review round 14 at `1c9fdd84` (six lenses, every skeptic verdict, the critic), rebuilt from the workflow journal's full per-agent results. Its brief's probe command imported `~/forge-r13-review` (`3b407ddb`), not `1c9fdd84` (R14-C-H1): each lens says which tree it ran against |
| `round14/mutation/` | `mutate_r14_local.py`, `run_mutants_r14.sh`; `summary_first_pass.txt` (base = the round-14 controls on a tree whose `owners.py` is `1c9fdd84`'s, plus 38 mutants: 37 caught, `unread_not_cleared` passed); `summary_rerun_new_control.txt` (base and `unread_not_cleared` after the round-14 clearing control was added: caught) |
| `round14/checks/`, `round14/gates/`, `round14/performance/` | the BR1.1 suite and checks, the gates against `1202ea6c` and the A/B (`13051154` against `7b4a0de8`) at the round-14 fix; `performance/` and `round13/performance/` also hold the instrumented desk probe the A/B harness runs (R14-B-F3) |
