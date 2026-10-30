---
ai_schema_version: 1
doc_id: FORGE-EXC4-MIND-HYPOTHESIS-LANGUAGE-DRAFT
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: b622af5e6f86324ccc15bc26dc124c3556b7f2de
evidence_level: REPORTED
last_reviewed: 2026-10-30
supersedes: none
---

# DRAFT EXC-4: a richer hypothesis language (Stage 2a: grammar enumeration as a frozen baseline first)

**This is a DRAFT for the owner's decision. It is NOT approved, NOT recorded in `ACTIVE_PLAN.md`, and authorizes no
work.** If the owner approves it, the eight fields below are copied into `ACTIVE_PLAN.md` under "Active-epic
exceptions" *before any code is written*, in the same format as EXC-2 and EXC-3.

## Why this, and why now (evidence, all DEVELOPMENT_DESCRIPTIVE)

Everything here was read at `b622af5e`. Nothing was re-run.

**What EXC-2 found** (`benchmarks/genesis_lite/pilot_results/v0_3-dev-mind-2026-10-29/ANALYSIS.md`):
- The Mind's ablations rarely change the answer.
- Its lead over `careful` (paired mean 3.55 vs 3.29) comes from the hypothesis competition and the conclusion rules, not
  from experiment selection.
- In 69 of `mind_full`'s 92 `insufficient_evidence` answers on discoverable worlds, the truth lies outside the
  log-linear/quadratic family. No experiment choice can add a structure that is missing.
- The analysis names option (d), a richer hypothesis family, as the lever that is "not a selection question".

**What EXC-3 found** (`.../v0_3-dev-scarce-2026-10-29/README.md`):
- At budget fractions 1.0, 0.5 and 0.25, no adaptive design was ahead of a space-filling design.
- Selection is not where the headroom is on these worlds.

**PySR baseline:** `pysr_symbolic` has generic expressive power, yet scored 0.0 discoverable credit and −0.11 on
confounded (EXC-2 summary). Expressive power without the Mind's gating and refusal rules is not enough. The grammar
therefore has to enter *through* a judging layer, not replace it.

**Why a baseline comes before any Mind change:** Genesis forbids crediting the Mind for representation
(`FORGE_GENESIS.md` "representation circularity"; preregistration `representation_limited_rule`). It also lists
`full_grammar_enumeration` as a required arm that does not exist yet (`arms.py` `UNAVAILABLE_ARMS`). Building that
enumerator, freezing it and measuring it is both the prerequisite and the cheapest test of the hypothesis that the
language is the bottleneck. Stage 2b (the Mind entertaining grammar rivals) is a separate, later decision.

## Proposed exception (eight fields, defaults marked *default*)

1. **Exact scope:**
   - A new package `src/engcore/mind/grammar/` with:
     - `dimensions.py`: Buckingham-pi groups computed from the presented card's public units only;
     - `grammar.py`: a typed structure grammar over the escrow expression language;
     - `fit.py`: constant fitting;
     - `evidence.py`: structure scoring.
   - A new development arm `grammar_enumeration` in a new `benchmarks/genesis_lite/arms_grammar_v3.py`, registered in
     `pilot_v3.py`, with its files bound into `harness_v3.development_identity`.
   - Tests for all of the above, and this section in `ACTIVE_PLAN.md`.
   - **Not touched:** `src/engcore/mind/minimal/**` (Gen1 stays byte-identical, MIND_VERSION 1.0.0), the v0.2-pinned
     files, `escrow.py`, `escrow_v3.py`, `engcore.blindfold.universe`, and the credit table.

2. **Allowed capability work:**
   - **Dimensional analysis.** Compute the integer null space of the input-dimension matrix from the card's
     `base_dimensions` and unit strings. This gives one scale monomial matching the output's dimension plus a basis of
     dimensionless groups. Inputs with dimension "1" are groups by themselves. If units are inconsistent or not
     parseable, the arm refuses and never guesses.
   - **Grammar.** Structures are `scale × F(groups)`, where F is built from operators of `engcore.blindfold.expression`
     (`mul`, `pow` with a fitted constant exponent, `add`, `exp`, `piecewise` on one group below a fitted threshold).
     *Default* limits: at most 2 additive terms, at most 1 `exp`, at most 1 `piecewise`, depth ≤ 4, ≤ 12 nodes, and at
     most 5,000 enumerated structures per universe. The grammar is defined by operators and limits, never by templates
     copied from `universe.py`.
   - **Constant fitting.** The scipy `least_squares` (trf) deterministic multi-start pattern already used in
     `engcore.mind.repsem.assess._fit`. No new optimizer and no new dependency.
   - **Scoring and selection.**
     - Score: ln-scale Gaussian likelihood with the replicate-noise estimate, plus a BIC/Laplace complexity penalty
       under a declared structure prior.
     - Count every enumerated structure in `engcore.claims.multiplicity.MultiplicityLedger`.
     - Select by cross-validation inside the training split. Judge on the untouched hold-out through the same decision
       gate the existing arms share (`arms._gate` logic, generalised to nonlinear predictions):
       - refusal when precision or lack of fit fails;
       - the confounding check;
       - no extrapolation outside the query box.
   - **Pilot.** One development pilot on **fresh worlds** (a new root seed, generated only *after* the grammar and arm
     code are frozen by digest). It uses the v0.3 harness at budget fraction 1.0, all registered v0.3 arms plus
     `grammar_enumeration`, *default* 4 workers and a 45-minute cap.
   - **Pre-declared contrasts** (paired, descriptive only):
     - (i) `grammar_enumeration` − `monomial_enumeration`, reported apart on in-family and out-of-family discoverable
       worlds;
     - (ii) `grammar_enumeration` − `pysr_symbolic`;
     - (iii) false-law rate of `grammar_enumeration` on `no_solution`, `confounded` and `insufficient_evidence` worlds
       vs `careful`. A richer language must not buy discovery with false support.

3. **Reason:** the EXC-2 and EXC-3 evidence above. This is the smallest step that tests "the hypothesis language is
   the bottleneck" directly. It also produces the frozen `full_grammar_enumeration`-class baseline that any later Mind
   lift claim would have to beat (Genesis §10.5).

4. **Start condition:** owner approval, then this entry recorded in `ACTIVE_PLAN.md` before any code. Because the
   grammar is new scientific capability under the active epic `engrt.numerical_foundations`, this is a narrowly
   scoped exception under the Completion Policy (`SCIENTIFIC_CAPABILITY_COMPLETION_POLICY.md:87`). It is not A2.

5. **Exit condition:**
   - red-first tests for each module;
   - a `forge-scientific-review` of `dimensions.py`, `evidence.py` and the gate, aimed at hidden defaults, false
     support and leakage;
   - a recorded pilot report with the three contrasts, plus the coverage split "truth form expressible in the grammar:
     yes / no" per world.

   No inferential statistics. Those would need a statistical review and their own decision.

6. **Expiry / timebox:** *default* 2026-11-27, even if unfinished.

7. **Owner approval:** OPEN. The owner must also confirm or change the *default* limits in field 2, the timebox, and
   the worker/cap values.

8. **What remains prohibited:**
   - changing Gen1 Mind code, its thresholds or its answer mapping;
   - plugging grammar rivals into the Mind's competition (that is Stage 2b, its own decision);
   - a Search Tree, Attempt Memory, Model Critic or causal reasoning;
   - AI/LLM proposals;
   - tuning the grammar, its limits, the prior or the gate on EXC-2, EXC-3 or this pilot's results (any change after
     the pilot is a new identity and a new decision);
   - reusing the EXC-2 or EXC-3 roots;
   - changing the credit table or pinned files;
   - any preregistration, formal campaign, A2 closure, lift, novelty or superiority claim;
   - widening this scope.

## Known risks the reviewer should attack

- **Representation circularity / generator fitting.** The generator's out-of-family forms are known: a saturating
  `exp`, a two-term power sum and a regime switch (`universe.py`, around line 291). Operator-level limits that happen to
  contain exactly those forms would let the result measure the generator, not reasoning. Mitigations:
  - the grammar is fixed by operators and size, with no template;
  - expressibility is reported per world;
  - any claim beyond DEVELOPMENT_DESCRIPTIVE needs independently authored worlds (OD-8) and the
    `REPRESENTATION_LIMITED` rule.
- **Multiplicity.** Up to 5,000 structures per universe inflate the chance that a flexible structure fits noise. The
  hold-out gate, the complexity penalty and the ledger family size are the guards. Contrast (iii) measures whether
  they hold.
- **Dimensional analysis as a hidden default.** Unparseable or inconsistent units must refuse, never fall back to
  "dimensionless". A presentation's renamed base dimensions must give the same groups up to renaming (invariance test).
- **Cost.** PySR's formal cost estimate in EXC-2 was about 10,900 s. A 5,000-structure enumerator with multi-start
  fitting must be measured. The 45-minute cap and the structure cap bound it, and a cap hit is reported, never hidden.

## What comes after (each its own decision, not part of this draft)

- **Stage 2b:** the Mind version that entertains grammar rivals. This needs nonlinear predictive distributions for its
  experiment design and falsifier, and must beat `grammar_enumeration` itself, not just `careful`.
- **Stage 4:** an LLM proposer that emits structures in this grammar via `ExternalSuggestion`, with the mandatory
  LLM-ablation and model-swap arms (`FORGE_GENESIS.md` §8.5).
