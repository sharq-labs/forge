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

## B. Files

New: `src/engcore/mind/minimal/{__init__,problem,structures,outcome_model,competition,experiments,falsifier,stopping,trace,runner}.py`;
`benchmarks/genesis_lite_mind/{__init__,arm,pilot}.py`, `MIND_PILOT_PLAN.json`, `pilot_results/v1-2026-10-19/`;
`tests/mind/test_minimal_mind.py`; `tests/genesis_lite_mind/test_mind_arm.py`; this report.
Edited: `docs/work/ACTIVE_PLAN.md` (EXC-MIND-1), `docs/work/PROGRESS.md`. No certified file, no v0.2-pinned file,
no existing `engcore.mind.transition` behaviour changed.

## D. Development history and failed approaches (development worlds only, never the pilot root)

Each was found on development worlds, fixed for a stated reason, and is recorded so it is not repeated:

1. Beta-binomial prior over inputs AND the passive covariate: gave an irrelevant covariate ~50% inclusion whenever the
   true dependence used every input → false `confounded`. Now beta-binomial over settable inputs, 0.5 per covariate.
2. A passive copy of an input was set aside only at inclusion ≥ 0.9 → its structure counted as "no dependence".
   Copies (R² ≥ 0.9 on settable inputs) are now always set aside.
3. Fixed-g Zellner prior (g = max(n, p²)): information paradox — a structure leaving 3,600× more residual variance kept
   8% weight. Plain hyper-g: no Occam penalty at these n (0/100 no-dependence worlds concluded). Final: hyper-g/n.
4. g-prior posterior means shrink exponents by g/(1+g) (~8% at n = 12): estimation uses the reference prior.
5. Misfitting rivals predicted with their own inflated residual variance and were never refutable: falsifier
   predictions now use the replicate measurement-noise bound (the claim is "form + measurement noise").
6. Optimal-design candidates hammered box corners (up to 18 of 30 queries repeats): only the declared replicate
   candidate may revisit an observed setting.
7. Survivorship of the untested: refuting tested leaders left untested rivals carrying the conclusion → only rivals
   that survived a decisive sealed test carry it once anything is refuted.
8. Association read from a misfitting survivor: the lack-of-fit check now precedes the association check.
9. A wildly misfitting rival overflowed `exp()` while sealing → an inadmissible proposal. Non-finite predictions are
   now unsealable, and non-finite utility terms contribute nothing.

Last development sweep (100 worlds per kind per variant, 2,400 runs, 0 crashes): FULL 3.60, NO_ADAPTIVE 3.71,
NO_FALSIFIER 3.64, NO_BELIEF_UPDATE 3.63. Development stopped there; more tuning against the ablations would have
been fitting to the generator.

## E. Executed tests (this session, Windows CPython 3.14.2, `.venv` of the shared checkout, `PYTHONPATH` = worktree)

| Command | Result |
|---|---|
| `pytest tests/mind -q` | 46 passed (27 new Minimal Mind + 19 existing transition) |
| `pytest tests/genesis_lite_mind -q` | 8 passed (v0.2 identity untouched; isolated proposer VALID; renamed/paraphrased/trap identical answers; strict client; no hidden-answer path; trace pairing + replay) |
| `pytest tests/mind tests/genesis_lite_mind tests/genesis_lite tests/test_core_api_layering.py tests/test_core_semantic_invariants.py -n 4` | 273 passed, 1 failed: `test_every_reader_that_writes_a_schema_also_checks_one` — **pre-existing**: same test fails on pristine `8ec97064` with an identical 43-class set, none from this branch |
| `pytest` on the six `forge_check` architecture guards `-n 4` | 94 passed |
| `tools/forge_check.py --changed --base origin/main --workers 4` | see PROGRESS (run after the pilot) |

Acceptance tests 1–12 of the brief map to: rivals survive / no deletion (1, 3); discrimination over a replicate and a
replicate is never a falsifier test (2); registry refutation of a strong hypothesis, refutation in the loop, forged or
foreign statuses never verify (4); renaming, reordering and trap vocabulary leave the reasoning unchanged, in the Mind
and through the harness (5, 7); strict observe-only client and no hidden-answer path (6); no-dependence and
insufficient-evidence worlds never get a law, extrapolation is not claimed, an unsettable association is not promoted,
a non-positive observable refuses (8, 9); sealed-before-result predictions, exact replay, tampered traces diverge or
break the chain (10); each ablation removes exactly one capability (11, measured in the pilot); AI proposals carrying
status/belief/uncertainty/thresholds/outcomes are refused, admitted ones start PROPOSED at the declared prior, an
external suggestion's own number is ignored (12).

## F. Stage 2 pilot (MEASURED; indicative; no formal, maturity or lift claim)

Plan `MIND_PILOT_PLAN.json` (sha256 `b5b775bd…`) committed in `e2b8037c` BEFORE the root existed; root kept in
`D:/forge-mind-operator/`, revealed in `summary.json`. Grid: 10 campaigns × 4 presentations × 3 seeds = 120 world
sets; 17 arms (13 registered v0.2 + 4 Mind variants), each in an isolated proposer process: **2,040 runs, 0 invalid,
536.6 s** (4 workers). `runs.jsonl` sha256 `f108005e…`, `summary.json` `eb4acda6…`.

Primary endpoint (mean campaign credit, 6 kinds, max 6): FULL **3.504**; NO_FALSIFIER 3.529; NO_ADAPTIVE 3.450;
NO_BELIEF_UPDATE 3.417; strongest registered baseline `careful` **3.113**; `space_filling` 3.033; `extrapolation_pair`
2.658; `single_setting` 2.488; `monomial_enumeration` 2.404; `always_law` −4.775.

| Comparison (paired by world set, n = 120) | Mean | 95% bootstrap | sign-flip p |
|---|---|---|---|
| FULL − careful, raw | +0.392 | [0.250, 0.529] | 5e-5 |
| FULL − careful, v0.2 lift rule (NO_STRONG_BASELINE / REPRESENTATION_LIMITED cells capped) | +0.125 | lower 0.000 | Holm: not significant |
| FULL − careful, in-family discoverable worlds only (n = 43) | +0.302 | [0.163, 0.442] | 4.5e-4 |
| FULL − extrapolating_fit, in-family discoverable (n = 43) | −0.023 | [−0.256, 0.209] | 1.0 |

`analysis.lift_decision` (exploratory grid): `lift_claimed = False`. Per-kind non-inferiority fails against floor
arms (confounded vs `single_setting` −0.18; no_solution vs `always_refuse` −0.23) and on discoverable vs
`extrapolating_fit` (lower bound −0.175). Presentation non-inferiority holds in all four presentations. Most of the
raw gain sits in the capped cells (insufficient-evidence and no-solution are REPRESENTATION_LIMITED; 77 of 120
discoverable worlds are out of family). **BASELINE_LIFT: NOT ESTABLISHED.**

What the Mind did measurably (descriptive): **0 negative-credit outcomes and 0 false laws in 720 worlds** (as
`space_filling`; `careful` 2, `extrapolating_fit` 85, `fit_all_gated` 202). In-family law recovery matched the
extrapolating arms (0.51) without their false laws. All 90 trap worlds that admit a law: 0 textbook answers
(`historical_answer` 90/90 `law_fail`). Indistinguishable answers: 0 (so no FDA-05 vacuous-pair credit was earned).

## G. Ablations (FULL minus variant, paired, n = 120)

| Capability removed | Pooled Δ | 95% bootstrap | p | Verdict |
|---|---|---|---|---|
| Adaptive experiment selection | +0.054 | [−0.088, 0.183] | 0.46 | **UNJUSTIFIED_ON_THIS_PILOT** (helps no_solution +0.18; hurts confounded −0.05, discoverable −0.07) |
| Sequential belief update (prior-weight fixed policy) | +0.088 | [−0.008, 0.188] | 0.10 | **UNJUSTIFIED_ON_THIS_PILOT** (borderline) |
| Falsifier role | −0.025 | [−0.079, 0.025] | 0.45 | **UNJUSTIFIED_ON_THIS_PILOT** (192 of 720 worlds had a registry refutation; no credit effect) |
| LLM proposer | — | — | — | NOT_APPLICABLE: no LLM proposer exists; the boundary is tested instead |

The in-family gain is identical with adaptive selection removed: it comes from the inference and conclusion rules
(all evidence used, no hold-out split, model-averaged precision and the no-extrapolation rule), not from the loop's
experiment choice. Development showed why: the discriminating design probes box extremes where out-of-family laws
misfit, so the Mind refuses worlds where a wrong-but-adequate power law would have scored `law_pass`.

## H. Pre-result prediction scores (FULL; every query with a sealed mixture prediction)

| Kind | Queries | Mean log density of ln y | 90% interval coverage |
|---|---|---|---|
| confounded | 3,774 | −1.735 | 0.830 |
| discoverable | 3,247 | +0.076 | 0.892 |
| indistinguishable | 3,103 | +0.370 | 0.870 |
| insufficient_evidence | 3,576 | −1.635 | 0.898 |
| no_solution | 3,648 | −1.237 | 0.896 |
| spurious_correlate | 3,033 | +0.134 | 0.881 |

Intervals are close to nominal except under confounding (0.83: the latent cause is not in any rival). Prediction
quality is scored apart from credit: full-credit worlds have the *worse* mean log score (−1.21 vs −0.67), because
correct refusals happen in the noisiest worlds. A correct final answer does not certify the intermediate predictions.

## I. Leakage, isolation, replay

All 2,040 runs: `proposer_process` isolation, literal leakage audit clean, independent evaluator agrees, 0 invalid.
Escrow label unchanged: **SECURITY_BOUNDARY_NOT_PROVEN** (same-account process separation; B-LEAK open, OD-20).
Replay: **720 / 720 FULL traces VERIFIED** from recorded observations; 0 traces missing. A Mind run makes no LLM
call and holds no score, operator or truth handle.

Adaptive-search statistical safety (brief §11, option B): the world set is the unit and every arm, the Mind included,
was frozen before any pilot world existed, so across-world comparisons do not depend on the Mind's within-world
adaptivity. The Mind's within-world posteriors and falsifier verdicts (k = 4, about 19 sealed tests per world) carry
no frequentist family-wise guarantee and are not used as evidence of lift. The bootstrap "p" of `lift_decision`
remains O-1-uncalibrated; the sign-flip p values above are exploratory with no multiplicity correction.

## J. Status

| Axis | Status | Evidence |
|---|---|---|
| A1_GATE | **BLOCKED_WITH_PRECISE_EVIDENCE** (owner decisions) | §A; OD-3/8/18/19/20, ODC-05/06/O1 open; certificate binds `05522b59` |
| MINIMAL_MIND_IMPLEMENTED | IMPLEMENTED (pilot scope, EXC-MIND-1) | `engcore.mind.minimal`, commit `e2b8037c` |
| ADVERSARIAL_TESTED | TESTED (Stage 1, Windows 3.14) | §E |
| BLINDFOLD_MEASURED | **MEASURED (pilot)** — MINIMAL_MIND_MEASURED in the pilot sense | §F, 2,040 runs, 0 invalid |
| BASELINE_LIFT | **NOT ESTABLISHED** (raw +0.39; capped +0.125, lower bound 0.0; per-kind non-inferiority fails) | §F |
| ABLATION_LIFT | **NONE**: adaptive selection, sequential belief update and the falsifier are each UNJUSTIFIED_ON_THIS_PILOT | §G |
| LEAKAGE_CONTROL | literal audit clean on 2,040 runs; isolated processes; boundary NOT PROVEN | §I |
| REPLAY | VERIFIED 720/720 | §I |
| SCIENTIFICALLY_VERIFIED | NO | pilot only, not a formal grid, no independent review |
| CERTIFIED | NO | no certified file touched; no recertification |
| MERGED | NO | local branch only |

## Stage 3

Formal tier ESTIMATE from pilot wall times: ~40,100 s sequential-equivalent for all 17 arms on the 2,400-world-set
formal grid (~8,600 s for the FULL Mind). It is **not warranted now**: A1 must pass first, and on this pilot no
cognitive component of the Mind showed lift over its own ablation.

## The single next Big Rock

**Close Genesis A1 through the v0.3 amendment** (ODC-05/06/O-1 scoring repairs, P-4 formal driver, P-5 environment
manifest, the OD-20 isolated deployment with an independent B-LEAK lift, OD-3 recertification), then run the frozen
formal baseline tier. Until scoring and isolation are frozen, nothing further measured here can become a claim, and
building more Mind capability would be capability without a valid test.

