# Genesis-lite v0 — preregistered benchmark over Blindfold, and its Tier-1 pilot (BR-16)

| Field | Value |
|---|---|
| Date | 2026-10-14 |
| Branch | `feat/br16-genesis-lite-benchmark` (worktree `D:/forge-br16`), base `origin/main` `e193e573` |
| Code | `benchmarks/genesis_lite/` (benchmark layer), `tests/genesis_lite/` (adversarial tests) |
| Preregistration | `benchmarks/genesis_lite/preregistration/genesis_lite_v0.json`, sha256 `f99fcfbdc97aabcbea52fa72c12ad196d420e298237c5374184f537c67774ab0`, status `FROZEN_FOR_PILOT` |
| Pilot | `benchmarks/genesis_lite/pilot_results/v0-2026-10-14/`, run at `e493ff3f` on WSL Python 3.12 |
| Security boundary | `SECURITY_BOUNDARY_NOT_PROVEN` (in-process escrow); nothing here counts as novel discovery |
| **Outcome** | **PILOT_COMPLETE · BLOCKED_OWNER_APPROVAL**. This is **not** `GENESIS_A1_PASS`. |

**Why it is not an A1 PASS.** The live plan's A1 exit gate requires four things, and none is met:

* **A frozen preregistration.** This one is frozen for the pilot only. The A1 freeze starts after G0 exits, and G0 has
  not: the certificate does not bind `main` (BR-15).
* **A frozen baseline set.**
* **Baseline distributions over ≥20 seeds.** The pilot ran 3 seeds over 10 worlds per cell.
* **An owner-approved compute budget.**

The external evaluator (OD-8) is also still undecided.

Scope rule: this round adds **benchmark, measurement and evaluation infrastructure only**. No certified file changed;
`certified_dependency`/certificate scope membership was checked, and 0 of the 15 changed files are pinned. No
hypothesis generator, belief state, planner, outcome model or domain capability was added. New test files are
recertification *triggers* under the repository's conservative `tests/**` rule; they are not pinned files.

## 1. Benchmark schema (freeze-ready)

Genesis-lite reuses `engcore.blindfold` unchanged: the escrow, hidden L5 worlds, the law language, admission,
adjudication, the credit table and the reference baselines. It does not create a second benchmark authority. It adds:

| Element | Definition |
|---|---|
| Campaign | One universe of each kind: discoverable, no_solution, insufficient_evidence, indistinguishable, spurious_correlate, confounded. The escrow shuffles the kind order with a hidden seed. |
| Presentation (per campaign, never per kind) | `anonymous` (the escrow's names); `renamed` (keyed names and dimensions); `paraphrased` (renamed, reordered, keyed rewording); `trap` (anti-historical textbook vocabulary on every kind). Every presentation pseudonymises the universe id with a key private to the run. |
| Cell | (arm, kind, presentation). The unit of analysis is the **world**: seeds are averaged per world, never pooled as instances. |
| Arms | §3 below. All arms get the identical presented card and an escrow-enforced budget; one sealed submission per universe. |
| Primitive library | One frozen library (`primitives.py`, digest in the preregistration): the Blindfold law language. The v0 *searched* family is monomials over variable subsets. |
| Reveal | Proposals are stored content-addressed and sealed by the escrow. The answer key is then exported by the operator (`answer_key.py`). The separately implemented evaluator re-scores and must agree with the escrow; the leakage audit and the trap verification follow. Any failure marks the run `INVALID_BENCHMARK` with a reason. |
| Statuses | VALID, INVALID_BENCHMARK, EVALUATOR_DISAGREEMENT, KEY_MISMATCH, REPRESENTATION_LIMITED, NO_STRONG_BASELINE, NOT_AVAILABLE, NOT_INTEGRATED, NOT_APPLICABLE_IN_V0, NO_LITERAL_LEAK_FOUND / LITERAL_LEAK_FOUND |

Not covered in v0, and recorded in the preregistration:

* **G1/G2 mechanism recovery:** needs the port grammar (Genesis Step 4).
* **G3 distinguishable-rival falsification:** the generator has no such kind. Adding one changes certified
  `engcore.blindfold`.
* **G4 over a mechanism library:** only variable selection is measured.

## 2. Preregistration and digest

The preregistration is built from the code (`preregistration.py`) and byte-pinned. `test_f8_the_committed_preregistration_is_exactly_what_the_code_rebuilds`
and the pilot's own start check (`pilot.prereg_matches_code`) both refuse a mismatch, so any change to an arm, the
harness, the evaluator, the credit table or the plan creates a new identity. It freezes:

* the digests of the substrate sources, the primitive library, the harness and arm files, the evaluator files and the
  credit table (`cfb8d68c…`, equal to the escrow's `DEFAULT_CREDIT`);
* the class table, the arm table and its configuration, and the arms not run, with their rule;
* the metrics, the REPRESENTATION_LIMITED and representation-gap rules, and the known structural tells;
* the statistical plan for both tiers: world as unit, cluster bootstrap, a strongest-baseline rule, a paired lift rule
  on shared roots, and a fixed Holm family;
* the reveal protocol, the open owner decisions, and the pilot-root commitment
  `073814653d48e3879030270072f1912e0dc1bf10df161e4fdd18bbe225183686`.

The pilot root is revealed in `summary.json`; the pilot is not held out.

**Amendment required before any formal tier (finding P-1, §7).** v0's per-cell lift rule names the strongest
*competence-role* arm per cell. The pilot shows that a reckless floor arm dominates the discoverable cell. The formal
plan must therefore be re-identified as v0.1, before any formal run, with two changes:

1. the strongest baseline per cell becomes the maximum over all non-adversarial arms;
2. a lift claim in one cell requires no significant loss in the same campaigns' control cells, so a proposer cannot
   trade control failures for discovery credit.

This change is proposed here and **not** applied to the frozen v0 preregistration, because v0 has already produced
pilot output.

## 3. Baseline coverage matrix (Genesis §10.5)

| §10.5 arm family | v0 arm | Status | Note |
|---|---|---|---|
| Grammar enumeration over the frozen grammar | `monomial_enumeration` | RUN, **partial** | Searches the monomial family only. The generator also draws exp / two-term / regime laws, so the full-grammar enumerator is NOT_APPLICABLE_IN_V0. **No strong applicable baseline** for out-of-family worlds (per-world rule). |
| Constrained random valid expressions | `random_structures` | RUN | Same family; equal search effort. |
| PySR (identity-bound) | — | NOT_AVAILABLE | Not installed; never substituted. |
| PySINDy | — | NOT_AVAILABLE | No dynamics or inverse class in v0. |
| Random admissible design | `careful` (existing) | RUN | Random design with replicate/hold-out. |
| Space-filling design | `space_filling` | RUN | Latin hypercube in log space. |
| BO/BoTorch-only | — | NOT_AVAILABLE | Not installed. |
| Fixed discriminating-design heuristic (G3) | — | NOT_APPLICABLE_IN_V0 | No distinguishable-rival kind exists. |
| Greedy primitive selection (G4) | `greedy_forward` | RUN | Over variables only. |
| Indistinguishable answer | `extrapolation_pair` | RUN | Fixed rival-pair heuristic (review H3). |
| Extrapolating law recovery | `extrapolating_fit` | RUN | Enumeration without the no-extrapolation refusal (review H3). |
| `careful`, refusal floors | `careful`, `always_refuse`, `always_insufficient`, `always_law`, `single_setting` | RUN | Floors and sanity arms, never the competence bar in G6 cells. |
| Mechanism enumeration (G1/G2) | — | NOT_APPLICABLE_IN_V0 | Needs the port grammar. |
| LLM ablation / model swap | — | NOT_APPLICABLE_IN_V0 | No Mind exists. |
| Adversarial trap control | `historical_answer` | RUN | Must fail: it does (§7). |

Every run arm is frozen by the digest of `arms.py` plus the substrate `baselines.py`, and by its configuration
(precision 0.02, lack-of-fit 3.5, Occam slack 0.05, CV 3 folds, rival power 4 at 0.5 sigma). Every arm shares one
decision gate, so tuning effort is equal by construction (`test_structure_search_arms_share_one_gate_and_differ_only_in_search`).

## 4. Leakage audit: threat model and attack results

| Channel | Attack (test) | Result |
|---|---|---|
| Task serialization | Spy arm records every presented card in all four presentations (`test_f1_…`) | Only the reviewed keys are present. No law, kind, tolerance, sigma, seed or evaluation data appears. The key is exported only after all six seals. |
| Injected card field | `card_hook` adds a key (`test_f6_a_leaked_card_field…`) | Refused before the proposer sees it: **INVALID_BENCHMARK**. |
| Hidden number in an allowed field | Tolerances smuggled into `task_text` (`test_f6_a_hidden_number…`) | Post-reveal audit **LITERAL_LEAK_FOUND**: INVALID_BENCHMARK. |
| Crash while presenting | `card_hook` raises (`test_f6_a_crash_while_presenting…`) | INVALID_BENCHMARK (the benchmark's fault, not scored against the proposer). |
| Evaluator object references (in-process) | Proposer scans `gc` for `HiddenWorld`, links it by public ranges, returns the true law (`test_l2_in_process…`) | **The attack SUCCEEDS** (law_pass). The boundary stays SECURITY_BOUNDARY_NOT_PROVEN, so no formal run may use the in-process escrow (owner decision). |
| Same attack, escrow in a child process | `test_l2_with_the_escrow_in_a_child_process…` | Nothing found in the proposer's process. Same OS account, so this is still NOT_PROVEN. |
| Logs, errors, tracebacks | Out-of-box, covariate-setting and unset-input requests (`test_l3_…`) | Refusals carry no kind, tolerance, sigma or hidden number. Refusal texts are re-translated to presented names (review L2). |
| Seeds / identifiers | `test_l4_…` | Kind is not derivable from ids, and card order is shuffled per campaign. |
| Cross-run linkage | Stateful proposer collects ids across presentations and seeds (`test_h1_…`) | Ids are pairwise disjoint across runs. Residual: public ranges identify a world when a master seed is reused, so the formal tier never reuses one across seeds or presentations. |
| Shared temp files / caches | `test_l5_…` | A run writes no file; repeated runs give identical outcomes. |
| Answer-key / root access | `test_l7_…` | No answer key is committed; the preregistration holds only the root commitment. |
| Future observations | `test_l8_…` | Other universes cannot be addressed; a sealed universe takes no further observation. |
| Vocabulary revealing the mechanism | Trap vocabulary on every kind (`test_l6_…`); renamed/paraphrased per campaign | One wording per campaign; every kind wears the trap vocabulary. |
| Textbook answer valid in traps | Best-constant textbook law checked per trap world of every law-credit kind (`test_f2_…`, `test_l1_…`) | Every run's trap verification passed (30 distinct trap worlds of law-credit kinds, checked in every trap-presented run; 0 INVALID). `historical_answer` earned −1.00 in every trap cell (60 universes). |
| Structural tell | `region_tell` measured on generated worlds (`test_the_region_tell…`) and in the pilot | KNOWN and recorded: a box region rules out INDISTINGUISHABLE. In the pilot, `box` occurred for every kind except indistinguishable. The "pushed" tell did not occur in 10 worlds. The literal audit never clears a structural tell. |

## 5. Evaluator independence report

| Property | State |
|---|---|
| Code | `benchmarks/genesis_lite/evaluator/` imports only the standard library. This is enforced by an AST test and by a fresh `python -I` probe showing that no `engcore` module is loaded. |
| Rules | Re-implemented from the preregistered rule text. It must agree with the escrow on outcome, credit and **every per-law fraction within tolerance**, read from the escrow's own score responses. Hand-computed golden cases are pinned (`test_m3_golden_cases_hand_computed`). A mismatch is EVALUATOR_DISAGREEMENT (`test_m3_a_fraction…`, `test_f6_an_evaluator_disagreement…`). |
| Pilot | 960/960 runs VALID: the separate evaluator agreed with the escrow on all 5,760 universes. |
| Limits | **Code independence only.** It is the same team; worlds and truths come from FORGE's generator (a common-mode risk); the escrow runs in-process. It is **not** third-party evaluation. |
| Evaluator identity | **OWNER_DECISION_REQUIRED (OD-8):** a named evaluator, or a selection process with a deadline. |
| Held-out protocol | v0 instances are FORGE-generated from operator master seeds committed by sha256 before a run and revealed after. Third-party task authoring needs OD-8. |
| Self-scoring | Scores, thresholds and criteria live in frozen files whose digests are in the preregistration. A changed config invalidates the run before scoring (`test_f8_…`). |

## 6. Cost pilot (MEASURED) and forecast (ESTIMATE)

MEASURED on WSL2 Ubuntu, Python 3.12.3, 20 logical CPUs, one process, in-process escrow, at commit `e493ff3f`
(preregistration `f99fcfbd…`):

* 960 campaign runs: 12 arms × 4 presentations × 10 campaigns, with 3 seeds for stochastic arms.
* 85.07 s elapsed. 0 invalid runs, 0 inadmissible proposals.
* Run log sha256 `0c279655…02383` (kept by the operator).

| Arm | s / campaign (mean ± sd) | observe calls / campaign | peak traced KiB | sd of seed means (credit) |
|---|---|---|---|---|
| careful | 0.068 ± 0.013 | 205.8 | 1039 | — |
| monomial_enumeration | 0.088 ± 0.016 | 205.8 | 1044 | 0.018 |
| random_structures | 0.087 ± 0.016 | 205.8 | 1039 | 0.026 |
| greedy_forward | 0.077 ± 0.014 | 205.8 | 1039 | 0.087 |
| space_filling | 0.070 ± 0.013 | 205.8 | 1042 | 0.092 |
| extrapolating_fit | 0.088 ± 0.016 | 205.8 | 1050 | 0.141 |
| extrapolation_pair | 0.072 ± 0.013 | 205.8 | 1047 | 0.027 |
| single_setting | 0.067 ± 0.013 | 205.8 | 1029 | — |
| always_law | 0.069 ± 0.013 | 205.8 | 1067 | — |
| always_refuse / always_insufficient | 0.015 ± 0.003 | 0 | 287 / 359 | — |
| historical_answer | 0.029 ± 0.025 | 51.5 | 288 | — |

A campaign's fixed overhead is about 0.015 s (create, score, reveal and the separate re-score: the `always_refuse` row). Searching arms spend about 0.006–0.015 s per universe in the proposer, including their observation round trips through the escrow (`proposer_seconds_per_universe_by_kind` in `summary.json`). Memory comes from one
tracemalloc-instrumented campaign per arm, which is excluded from the timing.

**ESTIMATE (not measured).** The formal baseline tier as preregistered is 30 campaigns × 4 presentations, ×20 seeds
for stochastic arms: **15,120 campaign runs ≈ 1,185 s** (95% interval 1,181–1,188 s) on the pilot machine. It
**excludes**:

* the Mind, LLM-ablation and model-swap arms (they do not exist; UNMEASURED);
* any isolated-escrow transport (UNMEASURED; required by the owner decision below);
* PySR, BoTorch and a full-grammar enumerator.

Genesis §10.6's illustration (≈18,000 runs per domain *including* the Mind arms) is therefore the scale that still
needs a measured per-run Mind cost.

## 7. Pilot findings (indicative only: 10 worlds per cell, not a rate claim)

Full-credit rate per world (mean credit), anonymous presentation. All cells are in `summary.json` with
cluster-bootstrap intervals.

| Arm | discoverable | spurious | confounded | indistinguishable | no_solution | insufficient |
|---|---|---|---|---|---|---|
| careful | 0.10 (+0.10) | 0.50 (+0.50) | 0.20 (+0.20) | 0.00 (+0.50) | 0.70 | 1.00 |
| monomial_enumeration | 0.10 (+0.10) | 0.27 (+0.23) | 0.10 (−0.10) | 0.00 (+0.45) | 0.97 | 0.90 |
| extrapolating_fit | 0.27 (+0.23) | 0.30 (+0.17) | 0.07 (−0.17) | 0.00 (−0.37) | 0.90 | 0.83 |
| extrapolation_pair | 0.10 (−0.02) | 0.47 (+0.38) | 0.33 (+0.33) | **0.20** (+0.00) | 0.60 | 0.97 |
| space_filling | 0.10 (+0.10) | 0.43 (+0.43) | 0.47 (+0.47) | 0.00 (+0.47) | 0.67 | 0.97 |
| single_setting (non-discoverer) | 0.00 | 0.00 | **1.00** | 0.00 (+0.45) | 0.00 | 1.00 |
| always_law (floor) | **0.70** (+0.40) | 0.10 (−0.80) | 0.00 (−1.00) | 0.00 (−0.80) | 0.00 | 0.00 |
| historical_answer, trap presentation | −1.00 in every cell | | | | | |

**P-1 (benchmark-design defect for the formal tier).** In the discoverable cell, the reckless floor arm `always_law`
earns full credit in 0.70 of worlds; the best competence arm earns 0.27, because the competence gates refuse often. A
per-cell lift rule restricted to competence arms would credit a proposer that simply proposes more, while it fails
every control. The fix is the v0.1 amendment in §2.

**P-2.** The `no_solution` and `insufficient_evidence` cells are indicatively REPRESENTATION_LIMITED: enumeration
earns full credit there. The `confounded` cell is solved by a non-discoverer (`single_setting`, 1.00). These cells
measure control classification, not reasoning, and cannot carry a discovery lift claim.

**P-3.** Only 0.70 of discoverable, 0.50 of spurious and 0.40 of confounded pilot worlds have a truth inside the
searched family. The rest are NO_STRONG_BASELINE worlds.

**P-4.** The indistinguishable cell's only full-credit arm is the fixed pair heuristic (0.20). That is a weak but
real bar.

**P-5.** Traps work: the textbook answer failed in every trap world. Presentation sensitivity (outcome agreement with
the anonymous presentation on the same worlds) ranges from 0.79 to 1.00 per arm. It mixes presentation effects with
run-private design randomness.

## 8. Owner decisions needed for the formal campaign

| ID | Decision |
|---|---|
| OD-3 / G0 | Recertify the intended HEAD so that G0 can exit. The A1 freeze and the formal runs wait for it (BR-15). |
| OD-8 | Name the external evaluator, or a selection process with a deadline. This is required before the held-out protocol is fixed. |
| OD-15 (new) | Approve the formal compute budget. Baselines are ≈20 min on one machine (ESTIMATE). The Mind/LLM arms are UNMEASURED and need their own pilot once a Mind exists; until then the A1 baseline tier can run alone. |
| OD-16 (new) | Approve the v0.1 identity: the §2 amendment (strongest baseline over all non-adversarial arms; no-loss-in-controls condition). Optionally also integrate PySR/BoTorch and a full-grammar enumerator, and add a distinguishable-rival kind (a certified Blindfold change, which needs recertification). |
| OD-17 (new) | Decide the escrow deployment for formal runs: an isolated escrow (process or host boundary demonstrated by the isolation demo) instead of the in-process transport, whose leak the pilot's attack test demonstrates. |
| OD-7 | Set the A1 window. |

## 9. Tests and replay

```bash
python -m pytest tests/genesis_lite -q
```

The suite has 42 tests, covering Genesis F1–F8, the leakage threat model, evaluator independence, the freeze, and the
review fixes. Results: on Windows 3.14, 42 passed. On WSL 3.12 at `e493ff3f`, FAST had 10416 passed and 1 failed (`test_the_certificate_describes_this_tree`, the stale-certificate failure the base also has); the regression pack had 256 passed.

To replay the pilot, run the following on a supported interpreter from the committed tree. It refuses to run if the
code no longer rebuilds the preregistration, or if the root does not match the commitment:

```bash
python -m benchmarks.genesis_lite.pilot --root-file <file holding the root hex from summary.json> --out <dir>
```

Outcomes are deterministic given the root and the code (escrow noise and arm designs are seeded from them); wall
times are not.

## 10. Review record

The forge-scientific-reviewer was run twice, read-only.

* **Round 1: CHANGES REQUIRED.**
  * H1: cross-run linkage.
  * H2: enumeration did not cover the grammar.
  * H3: straw-man cells.
  * H4: no strongest-arm or decision rule.
  * H5: pseudo-replication.
  * M1–M5 and L1–L5.
* **Round 2: CHANGES REQUIRED.** One HIGH: distinct roots per arm would make the paired lift impossible, and the Holm
  family was not fixed. Five LOWs.

Every item was fixed before the preregistration was frozen for the pilot. The design defect P-1 surfaced from pilot
data, after the freeze, and is proposed as an amendment (OD-16) rather than applied to v0.
