---
ai_schema_version: 1
doc_id: FORGE-BLINDFOLD-V04-DESIGN-OPTIONS-DRAFT
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: 7d24c9485043ab31e49601c33a9334c1e6a44368
evidence_level: STATIC_REVIEW
last_reviewed: 2026-10-30
supersedes: none
---

# DRAFT A1/A4: Genesis-lite v0.4 design options (FDA-06, FDA-18, FDA-21, FDA-22, roster, circularity)

**PROPOSED, for owner decisions D10, D11, D13 and D14. Static reading only; it authorizes no code.** Scope:
ACTIVE_PLAN "Blindfold Step 1 gap closure, Session A", phases A1 and A4. The roster facts below come from a read-only
inventory at `7d24c948`. The arm credits are from the EXC-4b development pilot summary (DEVELOPMENT_DESCRIPTIVE).
The power side of the decision contract is in
[the power and inference draft](BLINDFOLD_V04_POWER_AND_INFERENCE_DRAFT.md).

## 1. The decision contract has two halves that never met

- **v0.2** (`analysis.py`, hash-pinned) has the full rule structure:
  - the unit is a world set and the endpoint is the six-kind sum;
  - the complete comparison set, with the strongest baseline chosen by rule;
  - the **no-strong-baseline cap** ("lose, never gain");
  - per-kind non-inferiority (margin 0.10) and per-presentation margins;
  - screened world sets.

  Its inference, however, is a cluster bootstrap, and O-1 found it invalid as a p-value.
- **v0.3** (`analysis_v3.py`) has valid finite-sample inference (Hoeffding + Holm), but **none** of the cap,
  non-inferiority, presentation margin or screening rules.
- **Proposal:** the v0.4 decision contract is the v0.2 rule structure with every interval or test replaced by the
  valid bound D9 chooses (recommended: empirical-Bernstein). It lives in new files; `analysis.py` and
  `analysis_v3.py` stay as they are.

## 2. FDA-06: the out-of-family cap covers one kind only (D10)

Fact: v0.2 caps the candidate when `truth_in_searched_family` is false **only for discoverable** worlds.
`spurious_correlate` (the truth is the law without `u1`) and `confounded` (the truth is the interventional law) also
earn +1 for a passing law. The cap does not apply there, so an arm whose search family happens to contain those
laws could gain credit no baseline could reach (R-06 REPRODUCED for the capping function).

| Option | Rule | Effect |
|---|---|---|
| **A (recommended)** | Apply the cap to every universe whose credited answer is a law (discoverable, spurious_correlate, confounded's `law_pass`) when the truth lies outside every run arm's searched family | Closes FDA-06. A Mind lift on out-of-family laws must then come from in-family-for-some-baseline worlds, or from controls |
| B | As A, but report out-of-family law credit as a separate secondary endpoint, never in the primary | Keeps the information visible; same primary as A |
| C | No cap; disclose | Leaves FDA-06 open (not recommended) |

Recommendation: **A + B together.** The primary is capped; out-of-family discovery is reported apart. That is
exactly where a stronger Mind (Stage 2b) would show itself later.

## 3. FDA-18: answer exclusivity inside a campaign (D11)

Fact: a campaign holds exactly one world of each kind. A proposer that sees all six cards of a campaign can infer
"exactly one of these is no_solution" by elimination.

| Option | Rule | Cost |
|---|---|---|
| **A (recommended if A6 shows the cost is acceptable)** | Each universe is proposed by its **own** isolated, stateless Discovery process that sees one card only. The unit stays the six-world set for analysis | Process spawns ×6 (measured in A6) |
| B | Randomize the kind mix per campaign (multinomial), and analyse per universe with the campaign as a cluster | Changes the unit and bound (R no longer fixed per unit) |
| C | Keep the mix, declare it, and add a stateless-per-campaign test | The channel stays open for any stateful arm |

## 4. FDA-22: the assessment region is a kind tell (D13)

Facts:
- Indistinguishable worlds **always** get an extended assessment region; other kinds get one with probability 0.5
  (`universe.py:319`).
- A box region therefore rules indistinguishable out. The gated arms refuse on an extended region, which earns
  +0.5 on **every** indistinguishable world. careful, space_filling, PySINDy, grammar and always_insufficient all
  sit at exactly 0.500 there.
- The universe docstring admits the tell, but the credit design does not neutralize it.

| Option | Rule | Effect |
|---|---|---|
| A (withdrawn) | v0.4 world generator in a **new** module: an extended region for every kind (probability 1) | Removes the tell, but every gated baseline refuses on an extended region, so all of them would refuse every world. Discovery would be measured only through extrapolation (found 2026-10-30 after the first answer; the owner then chose C) |
| B | A new credit table for v0.4 where insufficient_evidence on indistinguishable earns 0 instead of 0.5 | Removes the farming, keeps the tell; a credit-table change (new version, never an edit) |
| **C (chosen)** | Disclose; report every arm by box vs extended region and on indistinguishable apart | The tell stays. The gated arms' +0.5 on indistinguishable is the same for all of them, so it cancels in paired differences |

## 5. Roster for v0.4 (D14, with gaps FDA-21 and G7)

Scope proposal: **v0.4 Step 1 scores law recovery plus the five refusal controls only.**
- Classes Genesis §10.5 lists with no applicable baseline here are declared **out of scope** and cannot support any
  lift claim: experiment selection scored by information gain (not implemented), G3 rival falsification
  (`discriminating_design` is NOT_APPLICABLE), G1/G2 mechanism enumeration, and dynamics (PySINDy runs over an
  algebraic library).
- The LLM-ablation arm is a Step 2 requirement (no LLM proposer exists today).

| Gap | Fact | Proposal |
|---|---|---|
| Constrained random valid expressions (§10.5) | `random_structures` draws random monomial subsets, not random grammar expressions | Add `random_grammar`: random valid structures from the same five-shape grammar, the same budget and the same gate |
| "The same frozen expression grammar" | The grammar arm uses five declared shapes (owner H2) | Declare the five-shape grammar the v0.4 frozen grammar; the Mind is later judged against it |
| PySR counts no parameters and skips the precision bar (FDA-21) | `arms_v3.py:15, 190` | `pysr_units` uses the shared gate with the parameter count of its chosen expression |
| PySR mapping refusal farms refusal credit | A `GrammarRefused` becomes `insufficient_evidence` (`arms_v3.py:240`): +1 on insufficient worlds, +0.5 on indistinguishable | In `pysr_units`, a mapping or library failure is recorded and scored inadmissible (−1), never a refusal |
| PySR fit scale | Raw-scale loss, but a log-scale gate; any non-positive prediction forces refusal | `pysr_units` fits in log space on positive outputs (declared before its dev pilot) |
| Design differences | Random design (enumeration, greedy, careful) vs LHS (PySR, PySINDy, grammar, space_filling) | Keep as part of each arm's identity; disclose in the roster table |
| Mind's parameter counting | UNVERIFIED | Read and record before Step 2 (not Step 1) |
| False-law counts for most arms | Recorded only for grammar, careful and mind_full | v0.4 analysis reports false laws per arm per control kind |

## 6. Representation circularity (G15): mandatory strata

The v0.4 analysis reports every arm on these strata:
1. expressible vs not-expressible by the frozen grammar (from the sealed-root reveal, as `expressibility_v3` does);
2. in-family vs out-of-family for every arm;
3. a class the grammar solves within budget is reported as measuring the representation (Genesis §10.3).

Fact for planning: in EXC-4b, 89 of 120 discoverable laws were expressible by fit, and three of the five shapes
overlap the generator's families.

## 7. Decisions asked

- **D10:** FDA-06 = A + B.
- **D11:** FDA-18 = A (if the A6 cost is acceptable), otherwise B.
- **D13:** FDA-22 = C (decided after A was withdrawn).
- **D14:** the roster and scope in §5.
- **D9:** in the power draft (recommended: empirical-Bernstein with a pre-declared strongest-baseline family).
- **D12:** who reviews the preregistration independently.
