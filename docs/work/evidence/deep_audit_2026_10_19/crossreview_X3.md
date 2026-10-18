# Cross-review X3 — attacks on reviewer D (Genesis-lite / Blindfold), 2026-10-19

Target `D:/forge-main-337519d1` @ `abed661f`, read-only. No FORGE code run, nothing imported from engcore.
One stdlib-only script of my own: `scratchpad/audit/x3_vacuous_pair.py` (`python -I -S`, 11 s, 1,500 worlds per kind).
It re-implements the INDISTINGUISHABLE generator (universe.py:266-394, simplified but with the same distributions) and
the pair rule (escrow.py:570-609 = score.py:90-117). It is an INDEPENDENT DERIVATION, not EXECUTED_REPRODUCED.
I did not rerun reviewer D's scripts.

| ID | D's severity | X3 verdict | X3 severity | Blocks |
|---|---|---|---|---|
| D-02 | MAJOR | CONFIRMED (false-support risk lowered) | MAJOR (scoring-freeze defect); false-lift risk low-medium | Step-1 scoring freeze; validity of Step-2 gate; Graduation |
| D-01 | MAJOR | CONFIRMED, NEW variant of D4; code matches prereg wording (CONTRACT_AMBIGUITY against Genesis §10.5 rule 4) | MAJOR | fix before the Step-1 freeze (OD-19); Step-2 gate; Graduation |
| D-03 | MAJOR | CONFIRMED_REDUCED_SEVERITY | MINOR (MAJOR only together with D-02 unfixed) | Step-2 / Graduation design; not Step-1 baselines |
| D-04 | MAJOR | DUPLICATE_OF_KNOWN (B-LEAK / OD-20 "cannot read operator files") | OBSERVATION | covered by the B-LEAK lift |
| D-05 | MAJOR | CONFIRMED_REDUCED_SEVERITY (variant of B-LEAK) | MINOR | B-LEAK lift (P-1 spec) |
| D-06 | MINOR | CONFIRMED | MINOR (descriptive metric only) | none (Step-1 quality) |
| D-09 | MINOR | DUPLICATE_OF_KNOWN (readiness row 11 / P-4, prereg `world_reuse`) | OBSERVATION | Step-1 formal tier (already blocked) |

---

## D-02 — vacuous INDISTINGUISHABLE pair earns full credit

**Expressible in the grammar? Yes.**
- `expression.py:42-80`: limits are 96 nodes and depth 12. Constants need only be finite; the only size refusal is for
  *ints* above 1e300 (`:52`). `pow` takes any constant exponent, negative ones included (`:64-68`). So B = L·(1+K s)^-1
  is legal.
- The evaluator (`evaluator/expr.py:24-60`) has the same rules and no "oversized constant" refusal for floats.
- Construction: s = Σ over extended inputs of (x/high)^M, or (low/x)^M for a downward extension. Each term is ≤ 1 in
  the box. About 40 nodes per law, depth 7.

**Does the proposer know the geometry? Yes.**
- `public_card` (`universe.py:129-138`) publishes the box (`inputs[].range`) and the `assessment_region`.
- The proposer knows which side each input is extended on. Terms for both sides (Σ (x/high)^M + (low/x)^M) also stay
  ≤ 2n in the box.
- M can be chosen from the card alone, so the pair is finite at the region's far corner. I used
  M = min(60, 250/ln(worst ratio)).
- At the near edge, `ratio ≥ exp(0.3·ln 10^0.7) = 1.62` (`universe.py:205, 320`), so K·s ≥ 1e-4·1.62^60 ≈ 4e8.

**Do the guards defeat it? No.**
- mutual ≤ 2nK ≈ 8e-4 < σ_min = 0.005 (`universe.py:315`), so σ need not be known.
- At every point outside the box, |A−B|/B is about 1e8, so PAIR_DIFFER_FRACTION is met at 100%.
- Bracketing holds at every evaluation point, since the region lies fully outside the box along the extended inputs
  (`_extended_region`, `universe.py:226-237`).
- The only binding guard is that each law must fit the in-box truth (`score.py:101`).

**Derivation results (`x3_vacuous_pair.py`):**

| World kind | Pair hit rate | In-box fit fails | Credit |
|---|---|---|---|
| INDISTINGUISHABLE | 0.771 | 0.229 | E[credit] +0.543 ungated, against +0.500 for the refusal |
| DISCOVERABLE, extended | 1.000 | — | −0.5 for the pair, against 0 for the refusal and +0.84 for the fitted law |

- On INDISTINGUISHABLE worlds, every miss was an in-box fit failure (exp form).
- With a self-check gate (refuse when the in-box fit is poor), the upper bound is 0.771 + 0.229·0.5 = +0.886.
- The `extrapolation_pair`-like heuristic (m = 4, d = 0.5σ̂) hits 0.329 in my simulation and 0.10-0.23 in the
  pilot.
- This confirms D's core claim independently: a pair carrying no extrapolation knowledge outscores the honest refusal.
- Bracket crediting is preregistered and justified:
  - the docstring at `escrow.py:582-583` and `score.py:14-18`;
  - the decision recorded at `PROGRESS.md:1923-1924`.
- The missing width bound is acknowledged nowhere (grep for width, vacuous and bracket in the closure, readiness,
  discovery and PROGRESS docs).
- The rule therefore contradicts its own stated purpose ("honest statement of the extrapolation spread") and the
  invariant "UNKNOWN never improves an answer". This is not a mere CONTRACT_AMBIGUITY.

**Strongest counter-argument (it partly survives):**
- The CREDIT table (`score.py:39-52`) charges −0.5 for a pair hit on discoverable and spurious worlds, and −1 on the
  other kinds.
- By construction, DISCOVERABLE-extended worlds cannot be told apart from INDISTINGUISHABLE ones in the box
  (`universe.py:25-34`).
- Per-kind non-inferiority (`analysis.py:304-310`, margin 0.10) applies against `fit_all_gated` on discoverable (pilot
  0.25) and against `always_insufficient` on INDISTINGUISHABLE (0.5).
- Answering the pair on every clean extended card drops the discoverable cell by about 0.125 and fails
  non-inferiority.
- So D-02 inflates credit only when an artifact separator exists:
  - a pushed region (pilot: 0%, `summary.json` `region_tell`);
  - the D-07 form prior;
  - D-03 composition, where certainty about INDISTINGUISHABLE comes with probability 0.25 per world set, giving about
    +0.1 per world set;
  - or B-LEAK.
- So D's "medium-high" false-support rating is overstated, and I lower it to low-medium.
- The scoring defect stands regardless: the INDISTINGUISHABLE control can no longer separate "quantified the spread"
  from "said nothing".
- It also flows into the correct-refusal metric (`roles.py:284` counts `indistinguishable_hit` as a correct control).

## D-01 — out-of-family cap only on discoverable

- `analysis.py:131-145` reads `truth_in_searched_family` only from the discoverable universe.
- `analysis.py:195` caps only when `k == "discoverable"`.
- `harness.py:331` records the flag for every universe.
- Spurious earns +1 only through `law_pass` (`score.py:48-49`), and 62% of spurious worlds are out of family (pilot
  0.383 in-family).
- Confounded is not exploitable this way, because the `confounded` refusal already earns 1.0.
- A candidate equal to `space_filling` but with a fuller grammar gains on spurious worlds purely from representation.
  `space_filling` already avoids `u1` by using settable inputs only (`arms.py:224-229`), and its spurious cell is
  0.133.
- **Counter-argument:**
  - the prereg scopes the cap explicitly: `amends/changes/3`, "capped … in out-of-family discoverable worlds";
  - `representation_gap_rule` talks about "discovery credit", which `pilot.py:150-153` computes for discoverable only.
- So the code faithfully implements the prereg. The defect is that the prereg conflicts with Genesis §10.5 rule 4 ("If a
  class has no strong applicable baseline, it cannot support a lift claim for that class") and with the project's own D4
  standard (`test_genesis_lite_final_review.py:72-83`).
- The closure measured the spurious in-family share (`G0_A1_FINAL_CLOSURE.md:76`) and still marked D4 "closed" (`:55`)
  without noting the gap. **It is NEW, not a duplicate.**
- Evidence: SOURCE_PROVEN for the code path; CONTRACT_AMBIGUITY between the prereg and Genesis.

## D-03 — campaign composition channel

- **Channel: SOURCE_PROVEN.**
  - One `ProposerHost` per `run_one` (`harness.py:210-215`).
  - The host loop keeps module state across cards (`proposer_host.py`, `while True` loop).
  - Cards are handed out one by one (`roles.py:352-385`).
  - MIX is fixed at one of each kind and is public (prereg `campaign_mix`).
  - The prereg `world_reuse` addresses statefulness only across worlds ("sees a world twice").
  - `GENESIS_LITE_V0.md:114` covers only cross-run linkage.
- **Magnitude (my analysis):**
  - The stateless region-tell policy already captures the "box-D seen" case for D/I, because refusal is optimal on a
    clean extended card. Composition adds about nothing there unless D-02 is open.
  - With D-02 open, certainty about INDISTINGUISHABLE in about 25% of world sets is worth about 0.25 × 0.39 ≈ +0.1 per
    world set, at no cost elsewhere.
  - Joint NS/IE and spurious/confounded elimination is real but bounded by the stateless arms' residual errors (pilot:
    IE 0.87-1.0, NS 0.75-0.96). It is unmeasured.
- Verdict: CONFIRMED_REDUCED_SEVERITY, MINOR. It is MAJOR only in combination with D-02.

## D-04 — runs.jsonl written before later arms

- The ordering is as D says:
  - `pilot.py:53-64` loops over arms outermost;
  - the sink flushes per run (`:240-242`);
  - kinds and outcomes are recorded per universe (`harness.py:325-331`).
- **Counter-argument (it survives):**
  - The proposer is started with `-I`, an empty temp cwd and a scrubbed env (`harness.py:61-66`). It learns `--out` only
    by reading the parent's command line, which is exactly the B-LEAK primitive. With the root file available the same
    way, it gets strictly more (every hidden law).
  - OD-20 already requires that the proposer "cannot read operator files" (`G0_A1_FINAL_CLOSURE.md:120`; readiness §2
    condition 1).
  - P-2 is "only together with P-1".
  - No formal driver exists (readiness row 11).
- Verdict: DUPLICATE_OF_KNOWN, with an OBSERVATION: the P-4 driver should write records to operator-only storage.

## D-05 — the isolation demo's leak detector is EscrowStorage-specific

- True and SOURCE_PROVEN:
  - `isolation_probe.py:62-97` reads only files changed since `since`, and only looks for the journal canary;
  - `isolation.py:325-341` digests only `escrow.secret`, `escrow.ed25519.pem` and `journal.jsonl`.
  - An older, world-readable root file or run log would not be flagged.
- **Counter-argument (strongest):**
  - The demo's semantics are scoped to its own deployment. The record is "bound to the escrow's key id"
    (`isolation.py:30`), and the demo builds its own `IsolatedEscrow`.
  - Its pid-namespace check (`escrow_process_invisible`, `isolation.py:343-344`) would block step 1 of the measured
    attack (the `/proc/<ppid>/cmdline` read).
  - Readiness §2 conditions 3-4 already require in-repo cmdline, root-file, network, persistence and code-write attack
    arms (P-3), plus an independent rerun of the escrow probe in the deployment. So the demo alone cannot lift B-LEAK
    under the documented protocol.
- Residual: if P-1 reuses the detector, it must be given the Genesis-lite secret set. That is a specification gap. MINOR.

## D-06 — "presentation invariance" pairs different worlds

- `master_for` includes the presentation (`pilot.py:43-46`), and the escrow derives worlds from master and campaign
  (`escrow.py:351-361`).
- The pairing key `(seed, "anonymous", cid, kind)` (`pilot.py:160-165`) therefore compares independent worlds, yet
  `summary.json` says "same worlds" and the prereg secondary/7 says "paired worlds".
- It is descriptive only, and no decision uses it. Confirmed, MINOR.

## D-09 — records not bound to a root commitment

- `RunRecord` (`harness.py:159-180`) has no root-commitment field.
- `lift_decision` checks only the grid and the prereg digest.
- But the prereg `world_reuse` already requires a fresh commitment before each campaign, and readiness P-4 ("fresh root
  commitment before, and reveal after") is the known absent item.
- Exploitation needs an operator error (reusing the revealed pilot root under `gl-formal-*` ids).
- DUPLICATE_OF_KNOWN, with an OBSERVATION: P-4 should carry the commitment id in every record and check it in
  `lift_decision`.

## Coverage notes

- **Inspected and found sound:**
  - The DEFAULT_CREDIT tables in `roles.py:156-169` and `score.py:39-52` are identical.
  - The escrow and the evaluator implement the same pair rule, except that the escrow pre-checks `finite`.
  - `_extrapolates`/`region_tell` match the generator's pushed-region rule.
- **Not checked:**
  - an exact replay of `generate_universe`: my generator is a distributional re-implementation, not a byte-exact one;
  - the formal-tier per-kind envelope (pilot numbers only).
