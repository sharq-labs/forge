# Reviewer D: Blindfold isolation, benchmark statistics, discovery reasoning

Target: `D:/forge-main-337519d1` at HEAD `abed661f`. This was a read-only review. No FORGE code was run. I ran two
stdlib-only scripts that I wrote myself, from the scratch directory, with `-I -S`. They are labelled INDEPENDENT
DERIVATION and are not EXECUTED_REPRODUCED:
- `d_sim_vacuous_bracket.py` (about 4 s);
- `d_sim_sparse_holdout.py` (about 2 s).

Scope:
- Read in full: `benchmarks/genesis_lite/{harness,proposer_host,analysis,arms,answer_key,presentation,primitives,pilot,preregistration}.py`,
  `evaluator/{__init__,score,expr}.py`, every file in `src/engcore/blindfold/`, `src/engcore/mind/*`,
  `src/engcore/scientific/discovery/*` and `tests/genesis_lite/{attack_arms,lift_records,test_genesis_lite_isolation,test_genesis_lite_final_review}.py`.
- Read in part: `test_genesis_lite_leakage.py`, plus the `test_` index of the other two Genesis-lite test files.
- Read the v0.2 pilot `summary.json` (recorded data).

Already known and not re-reported: B-LEAK, O-1 to O-5, D1 to D7, P-1, the absence of a formal driver and fresh root
commitment, the absence of an environment manifest, compute not equalised beyond the query budget, and best-of-N
attempts remaining procedural.

Certification:
- Every `src/engcore/blindfold/*.py` file is pinned in `certification/current_core_v2.json:11599-11607`.
- Every `src/engcore/scientific/discovery/*.py` file is pinned there at `:10858-10866`.
- `benchmarks/**` is outside the certificate scope but prereg-pinned (`preregistration.py:40-43`), so any change to it is
  a new benchmark identity.
- `src/engcore/mind/` is in neither.

---

## D-01. A gain on out-of-family *spurious_correlate* worlds counts as lift. The D4 cap covers only the discoverable kind.

1. **ID / new_or_known:** D-01, `variant_of: D4` (G0/A1 closure). What is new: two of the three kinds that can earn
   law credit are not capped. `spurious_correlate` earns credit only through a passing law (every refusal scores 0).
2. **Category:** benchmark validity (representation circularity, §10.3/§10.5).
3. **Location:**
   - `benchmarks/genesis_lite/analysis.py:131-145`: `out_of_family` reads only the discoverable universe.
   - `analysis.py:192-196`: `_capped` caps only when `k == "discoverable"`.
   - `harness.py:330` computes `truth_in_searched_family` for every universe.
   - The pilot measured an in-family share for spurious of 0.383 (`pilot_results/v0_2-2026-10-14/summary.json`
     `truth_in_searched_family_fraction`).
   - Credit table: `evaluator/score.py:48-49`.
4. **Contract:**
   - Genesis §10.5: "If a class has no strong applicable baseline, it cannot support a lift claim for that class."
   - prereg `representation_gap_rule`: "v0.1 search arms cover only the monomial family … In those worlds the candidate is
     capped".
   - analysis docstring at lines 21-24.
5. **Invariant:** a lift claim must not rest on the representation's reach (§10.3). The G0/A1 closure states D4 as
   "closed".
6. **Root cause:** the cap is keyed on the kind name, not on "any kind whose credit requires a law that no arm can
   represent".
7. **Trigger:** a candidate that can fit exp, two-term or regime laws and avoids `u1` passes out-of-family spurious
   worlds. About 62% of spurious worlds are out of family. No registered arm can pass them.
8. **Expected vs observed:**
   - Expected: those cells are capped at the comparator.
   - Observed: the candidate keeps the +1 per such world. The strongest baseline earns about 0.13 per spurious world
     (pilot), so the candidate gains up to about +0.6 per world set.
   - For scale: the strongest baseline's pooled mean is 3.13, and with 2,400 world sets the standard error of the paired
     difference is a few hundredths.
9. **Reasoning:** take the D4 reproducer (`test_genesis_lite_final_review.py:69-80`) and move the candidate's +1 from
   off-family *discoverable* worlds to off-family *spurious* worlds.
   - Nothing caps it.
   - Every per-kind non-inferiority check is unchanged, because the candidate equals `careful` on every other kind.
   - The pooled difference is positive, so the outcome is that of the positive control (`lift_claimed True`).
10. **Evidence:** SOURCE_PROVEN (the code path above is complete; nothing upstream refuses it).
11. **Affected:** the v0.2 lift rule, i.e. any future Mind or candidate claim.
12. **False-support risk:** high. A representation-only gain would be reported as reasoning lift.
13. **Replay/provenance:** none.
14. **Compatibility:** changing `analysis.py` is a new benchmark identity (v0.3).
15. **Certification:** not in the certificate; prereg-pinned.
16. **Genesis impact:**
    - blocks Minimal Mind Step-2 (gate validity) and Independent Blindfold Graduation;
    - should be fixed before the Genesis-lite Step-1 freeze (OD-19);
    - does not affect Step-0.
17. **Reproduction plan (not executed):** add `test_d4_variant_spurious` to `test_genesis_lite_final_review.py`.
    - Build `lift_records.records` with `truth_in_searched_family=False` on spurious for even campaigns.
    - Give the Mind credit 1.0 there and the `CAREFUL` pattern elsewhere.
    - Assert `lift_claimed is False`.
    - Expected today: True. Cost under 10 s. No isolation needed.
18. **Repair:** derive `off_family[ws]` per kind for every kind in `LAW_CREDIT_KINDS`. The truth flag already exists per
    universe. Cap every such cell. Report the share per kind.
19. **Owner approval:** yes. OD-19, for the v0.3 identity.
20. **Self-challenge:** "Spurious measures avoiding `u1`, not discovery."
    - The credit is still +1 only for a law that passes at the evaluation points.
    - An in-family candidate and an out-of-family candidate are separated purely by grammar reach.
    - The objection does not survive.

## D-02. A vacuous INDISTINGUISHABLE pair scores a full hit, because the bracketing credit has no width bound.

1. **ID / new_or_known:** D-02, NEW.
   - The 2026-10 design decision "a bracketing pair is credited without knowing which branch is true" is recorded
     (`PROGRESS.md:1923-1924`).
   - What is new: the bracket is unbounded, so a pair that says nothing about the extrapolation gets the same +1.0 as one
     that contains the truth.
2. **Category:** scoring error (credit-function edge case); refusal farming.
3. **Location:**
   - `evaluator/score.py:90-117` (`_pair_hit`; condition (d) at `:117`);
   - the identical rule in `src/engcore/blindfold/escrow.py:570-609` (`brackets` at `:604`);
   - credit +1.0, against +0.5 for the honest `insufficient_evidence` (`score.py:46-47`, `roles.py:163`).
4. **Contract:**
   - the `_assess_pair` docstring says the pair "rewards an honest statement of the extrapolation spread";
   - Genesis §12 (proper scoring).
5. **Invariant:** "UNKNOWN never improves an answer" (CLAUDE.md). An uninformative interval must not outscore an honest
   refusal.
6. **Root cause:** condition (d) accepts `min(A,B)(1-tol) <= t <= max(A,B)(1+tol)` at 90% of points, with no bound on
   max/min outside the box.
7. **Trigger:**
   - Take any extended-region world with a good in-box fit L.
   - Build A = L·(1+K·r^m) and B = L·(1+K·r^m)^-1, with r = ∏ x_i/high_i, K ≈ σ̂/3 and m = 40.
   - The pair needs about 20 nodes. It is admissible, it is finite, it agrees within σ in the box, and outside the box it
     brackets any truth.
8. **Expected vs observed:**
   - Expected: a miss, or at most the refusal's 0.5.
   - Observed in the independent derivation, on 2,000 synthetic worlds per row:
     - truth equal to the power law outside the box: HIT 1787/2000;
     - truth departing by exp(0.5 (ln r)^2): HIT 1793/2000;
     - truth departing by exp(2 (ln r)^2): HIT 1807/2000.
   - In the last two rows the in-box law passes as a law 0/2000 times.
   - Every miss came from my noisy in-box fit, never from the bracket.
9. **Reasoning:**
   - In the box r ≤ 1, so |A−B|/B ≤ 2K+K² ≤ σ.
   - Outside the box r^m grows without limit, so [B, A] grows without limit.
   - The 50%-differ condition only requires the pair to be wide.
10. **Evidence:** SOURCE_PROVEN (rule text plus an independent re-implementation of that text). Whether a policy using
    it beats the strongest baseline is STATIC_SUSPICION (see D-03).
11. **Affected:** the INDISTINGUISHABLE cell of every arm. The per-kind reference there is `always_insufficient` at 0.5.
12. **False-support risk:** medium-high.
    - Any proposer that can partly isolate INDISTINGUISHABLE worlds turns 0.5 into 1.0 with no extrapolation knowledge.
    - Spurious and confounded worlds are excluded through the `u1` tells, and the two refusal kinds through the noise
      level.
13. **Replay/provenance:** none.
14. **Compatibility:**
    - a credit-rule change is a new identity;
    - the escrow side is a certified change.
15. **Certification:** `escrow.py` is certificate-pinned; `score.py` is prereg-pinned.
16. **Genesis impact:**
    - should be fixed before the Step-1 scoring freeze;
    - blocks the validity of the Step-2 gate;
    - blocks Graduation.
17. **Reproduction plan (not executed):**
    - Add a Genesis-lite test that runs `harness.run_one` with an arm returning the vacuous pair on extended-region cards,
      using `MASTER` and a few campaign ids.
    - Assert that `indistinguishable_hit` is not awarded when max(A,B)/min(A,B) at the evaluation points exceeds a
      preregistered factor.
    - Cost about 30 s; same-account process isolation is enough.
18. **Repair:**
    - Bound the bracket width, e.g. max/min ≤ 1 + c·tol at the bracketed points, or score the pair by a proper
      interval score.
    - Credit bracketing below containment.
    - Apply the same change in the escrow and in the evaluator.
19. **Owner approval:** yes. This is a scientific-design decision (credit table and rule), plus a certified Blindfold
    change.
20. **Self-challenge:** "The pair must still agree within σ in the box and differ outside, so it is not free."
    - That requires only a good in-box fit and a wide pair.
    - Neither is evidence about the extrapolation.
    - The objection does not survive.

## D-03. The campaign has a fixed one-of-each mix and one persistent proposer process. A stateful candidate can use answer exclusivity; no baseline does.

1. **ID / new_or_known:** D-03, NEW. Grep for exclusivity, "one of each" and stateful exploitation found only the
   cross-run id linkage (H1).
2. **Category:** answer structure inferable from campaign composition and order; unfair comparison.
3. **Location:**
   - `harness.py:43`: `MIX = {k: 1 for k in KINDS}`. The mix is public through prereg `campaign_mix`
     (`preregistration.py:145`).
   - `harness.py:210-215`: one `ProposerHost` per `run_one`, "one fresh interpreter per campaign" (`:57`).
   - `roles.py:352-385`: the cards are handed one by one to the same proposer callable and sealed between cards.
   - `arms.py:183-295` and `baselines.py`: every registered arm is stateless.
4. **Contract:** Genesis §10.5: baselines "under the same budget, primitive library, observation access"; a lift must
   measure reasoning about the world, not benchmark composition (§10.3).
5. **Invariant:** the lift measures scientific inference per world.
6. **Root cause:** the world-set unit (one world of every kind) is visible to the proposer as a constraint, because one
   process sees all six cards.
7. **Trigger:** a candidate keeps state across cards.
   - Example: a clean (low-noise, no `u1` association), box-region card has been seen. With the region tell, at most one
     discoverable card exists, so a later clean extended card is INDISTINGUISHABLE with certainty.
   - Combined with D-02, that is +1.0 instead of +0.5.
   - Under ideal tells this happens when the discoverable world is box-shaped (p = 0.5) and comes earlier (p = 0.5),
     giving about +0.125 per world set from composition alone.
   - Elimination on the two high-noise cards adds more.
8. **Expected vs observed:**
   - Expected: no information from the other cards.
   - Observed: the channel exists. Its magnitude is unmeasured.
9. **Reasoning:** the closed-form estimate above (an analytic upper-bound sketch, not a measurement).
10. **Evidence:** SOURCE_PROVEN for the channel; STATIC_SUSPICION for the magnitude.
11. **Affected:** the primary endpoint for any stateful candidate (the Mind, LLM arms).
12. **False-support risk:** medium.
13. **Replay/provenance:** none.
14. **Compatibility:** a harness change is a new identity.
15. **Certification:** prereg-pinned; `roles.py` is certified.
16. **Genesis impact:** blocks the validity of Minimal Mind Step-2 and Graduation. It does not block the Step-1 baseline
    runs (the baselines are stateless).
17. **Reproduction plan (not executed):**
    - Write a test arm that records its decisions in process state and answers the vacuous pair on the clean extended
      card only after a clean box card.
    - Compare the INDISTINGUISHABLE credit with `space_filling` over 50 campaigns.
    - About 2 min; process isolation is enough.
18. **Repair:**
    - Use one fresh proposer process per card, with no writable persistent storage (needs OD-20); or
    - draw the mix i.i.d. with hidden counts, and redefine the unit accordingly.
    - Add a mix-aware baseline if the composition is kept.
19. **Owner approval:** yes. OD-19 (identity) and OD-20.
20. **Self-challenge:** "Using all available information is good science."
    - A real lab does not know that exactly one of six problems is unsolvable.
    - The information is an artifact of the benchmark.
    - The objection does not survive.

## D-04. Reveal happens per run, but world sets are shared across arms. Kinds are written to the run log before later arms run the same worlds.

1. **ID / new_or_known:** D-04, `variant_of: B-LEAK`.
   - New channel: the run log and operator memory, not the root file.
   - It survives a fix that only protects the root or moves the escrow out of process (P-2).
2. **Category:** leakage through logs; reveal-protocol ordering.
3. **Location:**
   - `pilot.py:53-64`: the outer loop is over arms, so every world set of arm *n* is revealed before arm *n+1* starts.
   - `pilot.py:240-242`: the sink writes `runs.jsonl` immediately.
   - `harness.py:296` (key export) and `:325-331`: each universe's `kind`, `answer`, `outcome` and `credit` are recorded
     in campaign card order.
   - Card order is identical for every arm on a world set (same master and campaign id, `escrow.py:351-361`).
4. **Contract:** prereg `reveal_protocol`: "answer key exported … only after every universe is sealed". Sealing is per
   run, but the same universes are re-presented to later arms.
5. **Invariant:** "Evidence must remain bound to the exact context it was produced for"; the hidden key is not available
   while the world is live.
6. **Root cause:** `run_one` couples sealing, reveal and recording per run.
7. **Trigger:** a proposer under the same account reads `--out/runs.jsonl` (the path is on the operator's command line,
   as in B-LEAK) and takes `universes[k].kind` for card *k*.
8. **Expected vs observed:**
   - Expected: no kind exists outside the escrow until every arm has finished the world set.
   - Observed: kinds are on disk, and in operator memory, during the later arms' runs.
9. **Reasoning:** traced line by line above. Control credit dominates the joint endpoint (closure: an oracle that never
   proposes a law scores about 3.5), so kind knowledge alone exceeds every baseline.
10. **Evidence:** SOURCE_PROVEN for ordering and content. Exploitation needs a same-account file read (not executed).
11. **Affected:** pilot, and any formal driver built on `run_one` with this ordering.
12. **False-support risk:** high in the current deployment; nil under a correct OD-20 deployment.
13. **Replay/provenance:** the run log is an answer oracle until the grid completes.
14. **Compatibility:** driver and harness design (new identity).
15. **Certification:** prereg-pinned.
16. **Genesis impact:** blocks the Step-1 formal tier (part of the B-LEAK lift), Step-2 and Graduation.
17. **Reproduction plan (not executed):**
    - Write a test proposer, run after `always_refuse` in `run_pilot` with `campaigns=1` and `seeds=(0,)`, that reads a
      runs file path passed through `extra_paths` and answers each card's kind.
    - Expect full control credit.
    - About 1 min.
18. **Repair:**
    - Write records to an operator-only sealed store.
    - Export the key and kinds per world set only after every arm has finished it, or run all arms of a world set in
      parallel in isolated domains.
    - State that the OD-20 requirement "cannot read operator files" explicitly includes output directories and logs.
19. **Owner approval:** yes. OD-20 and OD-19.
20. **Self-challenge:** "Same-account runs are already declared non-formal."
    - True for B-LEAK. The formal driver does not exist, though, and nothing in the prereg or the isolation verifier
      (D-05) names this artifact.
    - Survives as a variant.

## D-05. The isolation demo (the planned B-LEAK verifier, P-1) cannot detect the measured leak class.

1. **ID / new_or_known:** D-05, `variant_of: B-LEAK`. New: the verification instrument proposed to lift B-LEAK is blind
   to it.
2. **Category:** isolation verification.
3. **Location:**
   - `src/engcore/blindfold/isolation_probe.py:62-97`: `scan_for_leaks` reads only files with ctime or mtime at or after
     `since`, and matches only the escrow journal canary.
   - `isolation.py:306-341`: `leaked` is computed only from the canary and the digests of `escrow.secret`,
     `escrow.ed25519.pem` and `journal.jsonl`.
   - The Genesis-lite harness never uses `EscrowStorage`. Its secret is a root file and master seeds derived from it
     (`harness.py:230`, `pilot.py:218-232`).
4. **Contract:**
   - the `isolation.py` docstring says the demo shows that "no readable file matched the secret, key or journal";
   - the readiness review §2 conditions 1-4.
5. **Invariant:** "Do not claim an isolation boundary works unless demonstrated." The verifier must cover the secret
   actually in use.
6. **Root cause:** the detector is specific to `EscrowStorage` artifacts.
7. **Trigger:** a deployment with a world-readable root file created before the escrow storage, or a readable
   `runs.jsonl` (D-04). The demo still returns OS_ISOLATION_BOUNDARY_VERIFIED.
8. **Expected vs observed:**
   - Expected: NOT_PROVEN.
   - Observed: none of the 11 checks inspects either artifact.
9. **Reasoning:** the old file is skipped by the `since` filter, and even a new file without the canary is not flagged.
10. **Evidence:** SOURCE_PROVEN.
11. **Affected:** the OD-20 acceptance evidence.
12. **False-support risk:** high if the demo record is used to lift B-LEAK.
13. **Replay/provenance:** the isolation record is bound to the escrow key id, not to the Genesis-lite secret set.
14. **Compatibility:** a certified change.
15. **Certification:** certificate-pinned.
16. **Genesis impact:** blocks lifting B-LEAK (the formal Step-1 tier) and Graduation.
17. **Reproduction plan (not executed, Linux root):** run `run_isolation_demo` with a planted 0644 root file of age
    greater than the escrow storage's. Expect OS_ISOLATION_BOUNDARY_VERIFIED today. About 1 min.
18. **Repair:**
    - Give the demo the deployment's own secret set: the root, derived master seeds, run logs and output directories.
    - Add positive controls for each.
    - Run the Genesis-lite harness itself inside the demo domain, including the cmdline, persistence and code-write
      attack arms (P-3).
19. **Owner approval:** yes. OD-20, plus a certified change.
20. **Self-challenge:** "P-1 would extend the demo anyway."
    - Nothing records that the current checks are insufficient.
    - Survives.

## D-06. "Presentation invariance" compares different worlds while labelled "same worlds"

1. **ID / new_or_known:** D-06, NEW.
2. **Category:** metric error.
3. **Location:**
   - `pilot.py:43-46`: there is one master per *presentation*;
   - `pilot.py:160-165` pairs records on `(seed, "anonymous", campaign_id, kind)`;
   - the note at `pilot.py:180` says "same worlds";
   - the prereg secondary metric says "presentation invariance (deterministic arms, paired worlds)".
4. **Contract:** Genesis §10.1, renamed and paraphrased variants.
5. **Invariant:** a reported metric means what its label says.
6. **Root cause:** v0.1 changed the master derivation; the metric and note kept the v0 semantics. v0 reported
   0.79-1.00; v0.2 reports 0.47-0.68, which is consistent with independent worlds.
7. **Trigger:** every pilot run.
8. **Expected vs observed:** a same-world invariance figure was expected; a cross-world agreement figure is reported.
9. **What the design cannot tell apart:** the v0.2 pilot shows `careful` discovery at 0.267 on anonymous and 0.033 on
   renamed, and `space_filling` at 0.267 against 0.033. The design cannot say whether that is world sampling or
   presentation sensitivity.
10. **Evidence:** SOURCE_PROVEN.
11. **Affected:** the secondary metric only; no decision uses it.
12. **False-support risk:** low.
13. **Replay/provenance:** none.
14. **Compatibility:** new identity.
15. **Certification:** prereg-pinned.
16. **Genesis impact:** none for the gates. It weakens the renamed-variant control (Step-1 quality).
17. **Reproduction plan:** read the summary, as above (done).
18. **Repair:**
    - Relabel the metric; or
    - add a same-world invariance measurement on a separate, non-reused, explicitly linked root.
19. **Owner approval:** OD-19.
20. **Self-challenge:** "It is labelled descriptive."
    - The label "same worlds" is false.
    - Survives as MINOR.

## D-07. Kind-conditional generator priors are tells, and the proposer has the generator source

1. **ID / new_or_known:** D-07, `variant_of: held-out instances from FORGE's own generator`. New: specific tells that are
   absent from prereg `known_structural_tells` (`preregistration.py:162-167`).
2. **Category:** overfitting to the generator; answer structure inferable.
3. **Location:**
   - `universe.py:291-293`: INDISTINGUISHABLE is forced to the power or exp form; discoverable, spurious and confounded
     worlds draw two-term or regime forms 40% of the time.
   - The proposer's `sys.path` holds the repository root and `src` (`harness.py:64`), so `engcore.blindfold.universe` is
     importable.
4. **Contract:**
   - the `universe.py` docstring: INDISTINGUISHABLE is "observationally equivalent in the box to a DISCOVERABLE universe
     with an extended region";
   - Genesis §10.1, third-party authoring.
5. **Invariant:** the control is not separable from its look-alike by generator artifacts.
6. **Root cause:** the expression size limits forced a form restriction. The equivalence holds only pointwise, not in
   distribution.
7. **Trigger:** an in-box two-term or regime signature rules out INDISTINGUISHABLE.
8. **Expected vs observed:** equivalence was expected; a detectable prior gap exists.
9. **Reasoning:** P(form ∈ {two_term, regime} | INDISTINGUISHABLE) = 0, against 0.4 otherwise.
10. **Evidence:** SOURCE_PROVEN for the asymmetry; STATIC_SUSPICION for how detectable it is in the box under the noise.
11. **Affected:** the INDISTINGUISHABLE control.
12. **False-support risk:** low-medium (it compounds D-02 and D-03).
13. **Replay/provenance:** none.
14. **Compatibility:** a certified generator change.
15. **Certification:** pinned.
16. **Genesis impact:** Graduation, and Step-2 validity (minor).
17. **Reproduction plan:** a stdlib re-implementation of `generate_universe` (feasible, not done) that tabulates form by
    kind.
18. **Repair:** list the tell in `known_structural_tells` and measure it per world; or match the form distributions;
    or use third-party worlds.
19. **Owner approval:** OD-19 and OD-8.
20. **Self-challenge:** two-term and regime forms may be indistinguishable in the box at σ ≤ 0.02.
    - Not established. Kept as MINOR.

## D-08. Holdout survival in Scientific Core discovery is granted to pure noise

1. **ID / new_or_known:** D-08, NEW in its quantification. Partly acknowledged: `sria/decision/discovery_adapter.py`
   says "a holdout scored inside the search … is not a sealed falsifier verdict".
2. **Category:** discovery reasoning (false survival, selection on the holdout).
3. **Location:**
   - `src/engcore/scientific/discovery/symbolic_regression.py:19-20`: an absolute `holdout_rmse_limit=0.05` and
     `minimum_holdout_improvement=0.0`.
   - `:84-115`: up to 2,000 candidates are tested on one holdout.
   - `:136-146`: the ranking uses the holdout.
   - `campaign.py:62-76` turns `SURVIVED_HOLDOUT` into `HOLDOUT_SURVIVOR`, citing "the reserved holdout set".
4. **Contract:** the package docstring: "never promotes a fitted pattern".
5. **Invariant:** "UNKNOWN never improves an answer"; validation on a reserved holdout.
6. **Root cause:**
   - the threshold is absolute and scale-dependent;
   - the improvement bar is zero;
   - the holdout is used both for selection and as the reported survival.
7. **Trigger:** a target with holdout spread below 0.05.
8. **Expected vs observed:**
   - Expected: no survivors on a pure-noise target.
   - Observed in the independent derivation (10 random features, 30 calibration and 15 holdout points, 175
     candidates):
     - noise sd 0.01 and 0.03: about 31% of candidates survive, and the top-ranked candidate is a survivor in 100% of
       datasets;
     - noise sd 0.2: 0%.
9. **Reasoning:** with the zero bar, any candidate that is no worse than the calibration mean passes.
10. **Evidence:** SOURCE_PROVEN plus the independent derivation.
11. **Affected:** the `scientific.discovery` API. No production consumer outside the package and adapter (grep).
12. **False-support risk:** low today; medium if wired in.
13. **Replay/provenance:** the candidate fingerprint embeds the false status.
14. **Compatibility:** changing the defaults changes the records.
15. **Certification:** certified (`current_core_v2.json:10858-10866`).
16. **Genesis impact:** none today. It would become one if Step-2 reuses it.
17. **Reproduction plan:** the scratch script `d_sim_sparse_holdout.py` (done, 2 s).
18. **Repair:**
    - Use a relative or noise-scaled limit and a positive improvement bar.
    - Use a separate locked test split.
    - Rename the status `SELECTED_ON_HOLDOUT`.
19. **Owner approval:** OD-3 (a certified change).
20. **Self-challenge:** "There is no consumer, and the adapter neutralises it."
    - `review_discovery_candidate` still issues `HOLDOUT_SURVIVOR`.
    - MINOR.

Sub-item, sorting bug: `symbolic_regression.py:142` uses `(item.holdout_rmse or float("inf"))`, so a holdout RMSE of
exactly 0.0 sorts last among survivors. Evidence SOURCE_PROVEN; MINOR.

## D-09. The formal records are not bound to a root commitment, and the pilot root is published

1. **ID / new_or_known:** D-09, `variant_of: readiness row 11` (no formal driver or fresh root). New: the analysis cannot
   detect formal-grid records produced under a known root.
2. **Location:**
   - `pilot.py:43-46`: the master label carries no tier tag;
   - `summary.json` holds `pilot_root_revealed_hex` (committed);
   - `RunRecord` (`harness.py:159-180`) has no root commitment;
   - `analysis.coverage_problems:218-248` checks only the prereg digest.
3. **Consequence:** worlds that anyone can derive would pass `lift_decision`.
4. **Evidence:** SOURCE_PROVEN.
5. **Severity:** MINOR; it needs an operator error, and OD-8 would catch it.
6. **Repair:** record a root commitment id per record and have `lift_decision` require the preregistered formal
   commitment.
7. **Genesis impact:** Step-1 formal tier.
8. **Owner approval:** OD-19.

## D-10. The Mind accepts any string as an authority result id and admits a capability once a gate is "resolved" without a citation

1. **ID / new_or_known:** D-10, NEW.
2. **Category:** discovery reasoning boundary.
3. **Location:**
   - `src/engcore/mind/transition.py:236-240`: any non-empty `authority_result_id` is accepted.
   - `:844-848`: the STOP reason asserts "by an existing authority result".
   - `:737-743` and `:752-769`: a gate counts as resolved without `upstream_result_ids`.
4. **Evidence:** CONTRACT_AMBIGUITY. The docstring says the caller holds the status.
5. **Consumers:** none (only tests).
6. **Certification:** none.
7. **Severity:** OBSERVATION.
8. **Genesis impact:** Step-2 design. The Minimal Mind must bind an authority id to a resolvable record.

---

## (a) Hypotheses not confirmed

- **H-1 timing side channel (PERFORMANCE_HYPOTHESIS).**
  - Escrow observe latency depends on the hidden law tree:
    - NO_SOLUTION skips `evaluate` (`universe.py:426-427`);
    - regime, exp and rival forms add nodes.
  - In-process timing is fine-grained. Across the pipe, the difference is roughly 10-20 µs against hundreds of µs of
    jitter (ESTIMATE, unmeasured).
  - Not in the OD-20 requirement list.
  - Test: time 60 observes per kind under the OD-20 deployment.
- **H-2 O-1 calibration at formal n.** At 600 and 2,400 world sets the bootstrap fraction ≈ Φ(−t), which should be
  close to a one-sided p. Not simulated (too slow under the CPU cap at those n). It is still O-1.
- **D-02 plus D-03 economics.** The +0.125 per world-set estimate assumes perfect tells. Unmeasured.

## (b) Inspected and found sound

- **Refusal-text echo channel is closed at the client.**
  - Setting names are filtered (`presentation.py:168-173`).
  - The query-id regex forbids spaces, so "rolled back" and "history was replaced" cannot be echoed
    (`escrow.py:88`, `:286`).
  - Echoed values are floats (`universe.py:416-420`).
  - Non-string query ids fail the regex without being echoed.
  - NaN and Infinity settings are refused without an integrity error (the request digest is stable across JSON round
    trips).
- **Card shape is identical across kinds.**
  - Every card has one covariate, unit "1", a budget from {12, 30, 60} and cost 1.0.
  - The marginal spread of `u1` matches between the irrelevant and confounded cases (0.4·U(0.6,1.4)).
  - NO_SOLUTION noise is drawn like INSUFFICIENT_EVIDENCE's.
  - Only the documented region tells differ.
- **Pseudonyms and stimulus are sound.** They are HMAC-keyed. Universe ids derive from the seed and kind, not the law.
  Observation noise uses a fresh HMAC-seeded RNG per request, so no MT state is recoverable.
- **Budgets and sealing are sound.**
  - The budget is enforced per universe in the escrow.
  - A sealed universe refuses further observations.
  - `TranslatingClient` serves one pseudonym.
  - The receipt, sequence and head are stripped before the proposer sees a response (`presentation.py:179-180`).
- **Statistics unit.** World sets are independent: there is one master per (i, presentation, seed), and arm RNGs are
  seeded per run.
- **Conservative selection rules.**
  - Choosing the strongest baseline and the best per-kind arm on the same data is a winner's-curse effect against the
    candidate.
  - Non-inferiority is an intersection-union test, so no multiplicity correction is needed.
  - Holm over five, with only the pooled test required, is conservative.
  - The cap inherits the comparator's errors (`min(c, ref)`): also conservative.
- **Evaluator independence.** It is stdlib-only. Huge-integer constants are refused at escrow admission and never reach
  the evaluator's `float()`.
- **Candidate-triggered invalidation always blocks its own claim.** Screens apply only when every arm fails identically.
- **`-I` in the proposer host.** It drops the environment variables and user site. The proposer still holds all
  benchmark and generator source by design. There is no evaluator secret to steal without the master.
- **Isolation.** I do not claim that any isolation boundary works. None was demonstrated in this review.
