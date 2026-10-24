# BR1.1 review round 12 — INTERRUPTED / INCOMPLETE (no result)

**Not a review result. Nothing here was verified by a skeptic or a critic, and nothing here closes or opens a finding.**

| Item | Value |
|---|---|
| Workflow run | `wf_9cb45dfa-bb5` (task `wyb8v1x2z`), script `workflow_r12.js` (this directory), launched 2026-10-23 14:48 UTC |
| Reviewed SHA | `a96baa64e03be498bf2f6001ec86c6bff4eb3698` (gates record; code `d5ef1e32f2b0976fc46e07aa5db3f3148173495d`, records `ec2c00067062fe0989617ff576707fe57e66b949`) |
| Input | `r11_findings.txt` (the round-11 findings and the fixes asked), the round-11 probes |
| Stopped | 2026-10-23 ~15:13 UTC, by the builder, on the owner's instruction to stop the cloud session (TaskStop) |
| Lenses started | A (scientific authority), B (architecture): the workflow's agent concurrency on this 4-CPU host was 2 |
| Lenses not started | C (adversarial), D (replay/stale), E (forge-scientific-reviewer), F (deep attack on the round-11 rewrites); no skeptic, no critic |
| Lens results returned | **none** (both lenses were still probing when stopped; no findings, prior-closure checks or Q1-Q7 verdicts were returned) |
| Agent transcripts | `~/.claude/projects/-home-user-forge/<session>/subagents/workflows/wf_9cb45dfa-bb5/` in the cloud container (NOT preserved: they are ephemeral session files; their probes and outputs are copied here) |

## What the two lenses had produced (raw, unverified leads)

The probe scripts and their `*_out.txt` outputs are in `A-scientific-authority/` and `B-architecture/`. They were run
by the lens agents from `/home/user/forge` at `a96baa6`. The builder has NOT re-run them, and no skeptic has tried to
refute them. Treat every line below as a lead to reproduce, not a finding:

| Lead (probe) | What the probe output shows at `a96baa6` | If it reproduces, class |
|---|---|---|
| B `b1201_unprintable_exception_escapes` | an exception raised inside the ledger's serialization whose own `__str__` raises makes `_read_once`'s handler itself raise; the error leaves `pinned()`; admissions RAISE; after a restore the executed action is DISPATCHED AGAIN (executor ran 2) | the R11-C-F1 class (handed spend never observed) |
| B `b1202_unprintable_hides_other_accounts` | the same for an experiment: an unbound such account makes admission of a world that never reads it RAISE `LookupError`; a bound one hides the spend, re-dispatch | R11-C-F1 class |
| B `b1205_same_spelling_collision`, A `a1205_two_accounts_one_spelling` | a str-subclass key spelling an id but hashing differently sits beside the plain-str key; `_handed`'s normalization keeps one, silently; the spend is hidden, DISPATCHED AGAIN | F11-2 class |
| B `b1204_deterministic_mutation_error`, `b1208_varying_message_is_moving` | an execution-side value that raises the interpreter's "changed size during iteration" text every time, or a message that varies per attempt, is classified moving (never observed): DISPATCHED AGAIN | the round-11 classification rule (adversarial execution-side value) |
| B `b1206_fresh_thread_single_attempt` | a deep-stack verification whose fresh-thread retry is torn once refuses an honest account FOR GOOD | availability (fail-closed) |
| B `b1207_fresh_thread_join_unbounded`, A `a1207_fresh_thread_join_deadlock` | `_at_baseline_depth`'s `thread.join()` has no timeout: under a re-entrant execution-side lock the verification stays blocked (>5 s), its ticket stays in flight, others are refused after `WAIT_S` | availability / the "no deadlock" claim |
| A `a1202_deep_stack_new_unit` | the unit owner wraps `RecursionError` into `UnitCompatibilityError`, so a recursion failure inside a unit parse is not seen as recursion by `_account` (would be refused for good) | availability (fail-closed) |
| B `b1203_recursion_headroom_scan` | at 11 frames of headroom a `RecursionError` escapes the reader (documented residual: the caller's own stack exhausted) | documented residual |
| A `mut_differ_not_moving.txt`, `mut_why_only.txt`, `mut_id_str_call.txt` | three mutants of the round-11 code pass the whole BR1.1 suite (648 passed, 1 skipped) | missing controls |
| A `a1208_served_per_pin` | within one verification the served experiment record is one object (parsed once at the pin) | wording precision (README §4) |
| B `b1209_p24_instrumented` | large-account contention: 13 / 39 / 37 of 48 FEASIBLE in three runs; one torn read per run in two runs | consistent with README §8 |
| B `b1210_alias_spend_recorded`, `b1211_fresh_thread_read_through` | alias refused and its spend recorded; fresh-thread read-through bounded (one nested pin) | consistent with the round-11 claims |

Also here: `A-scientific-authority/suite_head.txt` (649 passed), `rescore.txt` (MATCHES), `runbench.txt` (MATCHES),
`r11_on_aad2f69.txt` (the builder's 20-fail claim reproduced by lens A), `B-architecture/mutants_out*.txt`.

## Consequence

Round 12 has **no result**. Its leads indicate that the round-11 fix very likely left at least one MAJOR-class path in
`owners.BudgetReader` (b1201/b1202, b1205/a1205). BR1.1 is **not closed**; a complete review round is required
after the leads are triaged and fixed.
