# Why the Mind ablations are not worse than the full Mind (EXC-2 pilot, read-only analysis)

DEVELOPMENT_DESCRIPTIVE. This analysis reads the pilot's own `runs.jsonl` (sha256 `96681496…`, run at `992deeba`) and the
Mind source (MIND_VERSION 1.0.0). Nothing was re-run, no Mind code was changed, and no statistics were computed: n = 720
paired universes per arm (120 campaigns x 6 universes). These are observations and hypotheses, not findings with
scientific authority. Owner request 2026-10-29: "Close EXC-2, analyze".

## 1. The ablations rarely change the answer

The comparison is per universe on the same world, ablation against full. "Credit delta" is the ablation's credit minus
the full Mind's, summed.

| Ablation | same answer and outcome | different | credit delta |
|---|---|---|---|
| mind_no_falsifier | 710 / 720 | 10 | +6.0 |
| mind_no_belief_update | 674 / 720 | 46 | +3.0 |
| mind_no_adaptive_selection | 630 / 720 | 90 | +1.5 |
| careful (baseline, for scale) | 609 / 720 | 111 | -31.5 |

The differences go both ways and mostly cancel. For example, on no_solution worlds, no_adaptive_selection changes
`no_law` to `insufficient_evidence` in 28 universes and the reverse in 18. These look like flips at decision
boundaries, not a systematic effect.

## 2. The Mind's lead over careful comes from what all four variants share

On worlds whose true law lies inside the Mind's hypothesis family (`truth_in_searched_family`, discoverable plus
spurious_correlate, 95 universes):

| Arm | law_pass | insufficient_evidence |
|---|---|---|
| mind_full | 46 | 49 |
| mind_no_falsifier | 46 | 49 |
| mind_no_belief_update | 44 | 50 |
| mind_no_adaptive_selection | 43 | 52 |
| careful | 31 | 64 |
| space_filling | 30 | 64 |

The fixed-design Mind still recovers 43 laws, against 30 for the space_filling baseline. The confounded answers (105/120
for mind_full) come from the same shared source: `conclude`'s passive-covariate inclusion rule.

The lead therefore comes from the parts that **no ablation removes**: the hypothesis competition, the log-linear and
quadratic fitting, and the conclusion rules in `runner.conclude`. The ablations remove only parts that act while data
is collected.

## 3. Why the parts that act during collection change little here

The labels say "cannot", but these are explanations read from the code and the runs, not established causes.

1. **Everyone gets the same data volume.** Every observing arm spent its whole budget in every universe: the per-universe
   query counts for mind_full, mind_no_adaptive_selection and careful are identical (min 12, mean 34.64, max 60). The
   early stop (`stopping.decide`) needs all of the following, which never held at once:
   - leading weight >= 0.995;
   - region sd <= 0.01;
   - no candidate with utility >= 1e-3;
   - the adaptive phase.

   So adaptive selection could only change *where* the queries went, never *how many* were made.
2. **A space-filling design is already enough in these boxes.** With 12-60 queries over 3-4 settable inputs (`universe.generate_universe`), a Latin
   hypercube pins down an in-family law about as well as targeted queries do (43 vs 46 recovered).
3. **Most failures are outside what selection can fix.**
   - The truth is outside the family in 69 of mind_full's 92 `insufficient_evidence` answers on discoverable worlds. The
     reasons recorded were: every tested rival refuted (29), no rival fitted (20), the leader not fitting the noise
     (14), and so on. No experiment choice adds a missing structure.
   - The region of use leaves the box in 196 mind_full universes, including 63 of the 120 indistinguishable worlds. No
     in-box query reaches that region. The Mind's preserve-a-pair criterion never fired, so it named no correct
     indistinguishable pair.
4. **The falsifier is redundant with the misfit check here.** Without it, the "every tested rival refuted / no rival
   fitted" path disappears (127 universes for mind_full, 0 for mind_no_falsifier), yet only 10 answers change. The
   rivals it refutes are ones the conclusion would already discard for misfit.
5. **`no_belief_update` is a second selection ablation.** By construction (`run_mind`), prior weights steer only
   candidate generation, falsifier proposals and selection. The conclusion still uses the posterior. It was never going
   to differ more than a selection change can.

## 4. What this does and does not say

- It does **not** show that experiment selection is useless. It shows that on these worlds, with this budget and with
  no reward for stopping early, the pilot cannot detect a contribution from selection.
- The owner's goal ("very smart experiment selection") would need conditions where *where* or *how many* queries are
  made changes the answer. Candidate conditions follow. **Each is a proposal only and would need its own owner
  decision; none is authorized by EXC-2, which is closed:**
  - (a) a scarcer budget relative to identifiability;
  - (b) more settable inputs, or narrow features a space-filling design misses;
  - (c) scoring that credits queries saved (the early stop would then matter);
  - (d) a richer hypothesis family, which addresses the 69 out-of-family failures and is not a selection question.
- Changing the Mind, its thresholds or the answer mapping on the basis of these results would breach the EXC-2
  prohibition on tuning on pilot results. Any such change needs a new decision, made before new data is seen.
