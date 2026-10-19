# BR-MIND-01 — Blindfold Discovery → Minimal Scientific Mind (2026-10-19)

Branch `feat/br-mind-01-minimal-mind` (worktree `D:/forge-mind`), base `origin/main` `8ec97064` (PR #172 merge). Not
pushed, not merged. Runs under owner exception **EXC-MIND-1** (`docs/work/ACTIVE_PLAN.md`), because Genesis A1 has not
passed. Status axes are kept apart throughout: nothing here is GENESIS_A1_PASS, SCIENTIFICALLY_VERIFIED, CERTIFIED or
MERGED.

## A. Current truth (census of origin/main 8ec97064, 2026-10-19)

| Requirement | Historical state | Current main state | Evidence | Blocking? |
|---|---|---|---|---|
| G0 (certificate binds intended HEAD) | BR17 note: `--verify` fails on main | Certificate still binds `05522b59` (`fix/hostile-review-p0-p1`), not `8ec97064` | `certification/current_core_v2.json` `repository.commit` | Yes for A1 (OD-3) |
| Genesis-lite preregistration | v0 (`f99fcfbd`), v0.1 (`94efff08`) | v0.2 (`878e6812…`) on main and pinned; v0/v0.1 preserved; v0.2 supersedes P-1 (joint-credit endpoint, all-kind non-inferiority, no lift without strong baseline) | `benchmarks/genesis_lite/preregistration/*.sha256`; `harness.code_identity()` returns no changed file | v0.2 cannot be the formal identity (OD-20 forces v0.3) |
| Frozen baseline identities | 13 arms pilot-frozen | Unchanged: 13 registered arms, `space_filling` strongest in v0.2 pilot | `benchmarks/genesis_lite/arms.py`, v0.2 pilot summary | Formal tier not run |
| ≥20-seed baseline distributions | none | none (`FORMAL_GRID` defined, never run; no formal driver) | `analysis.FORMAL_GRID`; no gl-formal records | Yes |
| Evaluator independence | code-independent stdlib port | unchanged; external evaluator undecided | `evaluator/score.py`; OD-8 open | Yes (OD-8) |
| Escrow isolation boundary | SECURITY_BOUNDARY_NOT_PROVEN; same-account exploit measured | unchanged (B-LEAK open; `PROVEN_BOUNDARY_LABELS` empty) | `blindfold/roles.py`; OD-20 | Yes |
| Compute budget | OD-18 open | open | ACTIVE_PLAN OD table | Yes |
| Scoring defects | FDA-05 (vacuous pair credit), FDA-06 (uncapped out-of-family credit) reproduced | unrepaired; ODC-05/06 undecided | `PROGRESS.md` R-05/R-06; deep-audit closure matrix | Yes (freeze-blocking) |
| Significance procedure | O-1: bootstrap "p" uncalibrated | unrepaired; ODC-O1 undecided | blocker matrix | Yes |
| Active-epic rule for A2 | A2 forbidden without epic change/exception | epic = `engrt.numerical_foundations` (excludes A2) | Completion Policy table | Resolved for this pilot only by **EXC-MIND-1** |
| Existing Mind package | — | `engcore.mind.transition` (dependency-gated next-action state machine, no quantitative loop) | `src/engcore/mind/transition.py` | No; extended, not duplicated |
| Historical docs | `BR17_MINIMAL_MIND_READINESS.md` (e193e573) | STALE as to main HEAD and v0.2; its blocking conclusion still holds | this table | — |

**A1 conclusion: BLOCKED_WITH_PRECISE_EVIDENCE (owner decisions).** Closing A1 requires OD-3 recertification, a v0.3
amendment carrying ODC-05/06/O1 + P-4/P-5, the OD-20 deployment and an independent B-LEAK lift, OD-8, OD-18, OD-19, then
the ≥20-seed formal baseline tier. None of these is an agent-executable bounded fix. The smallest decision record is the
existing `SCIENTIFIC_FINDINGS_OWNER_DECISIONS.md` (ODC-05a/b, ODC-06a/b, ODC-O1a, ODC-BL1) plus OD-3/8/18/19/20; no new
record was needed. Every independently safe task continued under EXC-MIND-1.

## C. New and extended scientific primitives (all in `src/engcore/mind/minimal/`)

| ID | Primitive | Canonical owner reused | What is new |
|---|---|---|---|
| M-1 | `HypothesisCompetition.view()` (state view) | — | read-only knowns / unknowns / hypotheses / contradictions / budget, digested per step |
| M-2 | `HypothesisCompetition` | `sria.decision.Hypothesis` records; `claims.falsification` registry | every rival kept for the whole run; status only from sealed verdicts, verified against the expected anchor (OBS-06) |
| M-3 | `OutcomePrediction` | `sria.decision.HypothesisPrediction` declared on each record | sealed before the result; digest `prediction_seal_digest` |
| M-4 | `OutcomeModel` | — (no owner computes a hypothesis-conditioned predictive) | hyper-g/n Bayes factors for comparison; reference-prior Student-t predictive; covariate submodel |
| M-5 | `ExperimentCandidate` | `sria.decision.ActionProposal`, `ActionFamily`; `ExternalSuggestion` for outside engines | box-feasibility gate; no unplanned repeats |
| M-6 | `select()` | `sria.decision.ScoreComponent` for every utility term | expected discrimination (Box–Hill) + V-optimal precision gain per unit cost |
| M-7 | `refit()` belief update | `claims.falsification.apply_verdicts` for REFUTED | posterior over unrefuted rivals from admitted evidence and the declared prior |
| M-8 | `stopping.decide` | — | STOP / CONTINUE / REFUSE with explicit cost and remaining uncertainty |
| M-9 | `trace.step_record` | — | content-addressed, chained step records |
| M-10 | `runner.replay` | — | exact reasoning-path replay from recorded observations, including the world's refusal |
| F | `falsifier.propose` | `claims.falsification` (sealing, judging) | proposes the most discriminating admissible test of each strong hypothesis; decides nothing |
| — | multiplicity | `claims.multiplicity.MultiplicityLedger` | every run counts generated/admitted/eliminated/tested/escrow queries/adaptive decisions |

Not built (out of scope by the brief): mechanism/port grammar, active causal discovery, analogy, swarms, tournaments,
justification-graph replacement, internet agents, new solvers, BUY, ROM, DAE, FMI. No LLM proposer exists in this
Mind; the proposal boundary (`ingest_proposal`, `ExternalSuggestion`) is tested so that one can be added without
authority.

<!-- results sections D–J are appended after the pilot -->
