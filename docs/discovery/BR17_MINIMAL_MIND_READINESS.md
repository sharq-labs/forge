# BR-17 Minimal Mind — start-gate check (2026-10-14)

**Outcome: BLOCKED_BY_PREREQUISITE.** No Mind code was written. The active epic was not changed.

## Start gate, checked against the live state

`origin/main` = `e193e573`, read on 2026-10-14.

| # | Prerequisite | State | Evidence |
|---|---|---|---|
| 1 | Genesis A1 has passed its recorded gate | **NOT MET** | BR-16 is `PILOT_COMPLETE · BLOCKED_OWNER_APPROVAL` ([GENESIS_LITE_V0.md](GENESIS_LITE_V0.md)). The A1 exit gate in `docs/work/ACTIVE_PLAN.md` (frozen preregistration, frozen baseline set, ≥20-seed baseline distributions, owner-approved budget) is unmet. The A1 freeze itself waits for G0 exit, and G0 has not exited: `core_certificate.py --verify` FAILS on `main` (BR-15). |
| 2 | Frozen benchmarks and baseline identities | **NOT MET** | Genesis-lite v0 (`f99fcfbd…`) is frozen for the pilot only. Pilot finding P-1 requires a re-identified v0.1 lift rule (OD-16) before any comparison. No formal baseline tier has run. |
| 3 | Active-epic restriction resolved | **NOT MET** | `scientific_capability_completion.json` has `active_epic: battery.thevenin_1rc`. The ACTIVE_PLAN section "Active-epic exceptions (open)" reads **None**. Completion Policy: A2 is "Not until one condition holds". |

The Completion Policy grants A1 and B1 a preparation allowance and grants A2 none. So no Mind capability was built:
no hypothesis generator, outcome model, belief state, planner or invalidation engine. This file is governance
documentation only.

## Owner map for the loop, for when the gate opens

Each transition below is assigned to an owner in `docs/architecture/discovery_authority_map.md`. "Gap" marks work
that would be new A2 capability; under Genesis §4 it must justify why no existing owner serves it. Nothing in this
table has been re-verified against code for enforcement; that is BR-17's own first task once the gate opens.

| Transition | Existing owner (authority map) | Gap for A2 |
|---|---|---|
| Hypothesis | `sria.decision.Hypothesis` (status only from sealed verdicts); LLM and external input only as `sria.decision.external.ExternalSuggestion` | Proposer integration only |
| Pre-result prediction | Hypothesis `predictions`; sealed falsifiers and the exposure clock in `claims.falsification` | A calibrated predictive OutcomeModel (Genesis §5.3), with every number citing an execution record (§8.3) |
| Experiment selection | `sria.decision` `ActionFamily` and `UtilityEngine` | Value of information over an explicit belief (§5.5) |
| Provider execution | Genesis-lite escrow `observe`; provider records (a failed run exposes no outputs) | — |
| Evidence admission | `sria.evidence`, the gateway / Arbiter (certified) | — |
| Falsification | `claims.falsification`, `claims.multiplicity`, `claims.novelty` | — |
| Belief update | Gateway belief (certified) | Probabilistic belief over competing hypotheses (§5.4) |
| Dependency invalidation | `credibility.evidence_graph` lineage | A single justification graph with invalidation precision and recall (Genesis Step 3) |
| Replanning or refusal | `sria.campaign` runner and stop review (certified since BR-15) | — |
| Benchmark and evaluation | Genesis-lite v0 (BR-16): frozen arms, a separate evaluator, a leakage audit | The v0.1 amendment (OD-16); an LLM-ablation arm once a Mind exists |

## Minimal owner actions that unblock BR-17

1. **G0:** recertify the intended HEAD, including BR-15's closure (OD-3).
2. **A1:**
   1. approve v0.1 (OD-16);
   2. name the evaluator or a selection process (OD-8);
   3. approve the budget (OD-15);
   4. choose the escrow deployment (OD-17);
   5. then run the formal baseline tier (≥20 seeds) and freeze the baseline-freeze addendum.
3. **A2:** change the active epic through the reviewed ledger change, or approve one narrowly scoped exception with
   all eight required fields (OD-6).
