# Scientific Intelligence Layer (Core G–N)

Continues the claim layer of PRs #51–#56. Scientific-intelligence orchestration lives in
`engcore.claims`; credibility/V&V report semantics and the SRIA bridge live in
`engcore.credibility`. Both are non-Core. Two SRIA changes are marked **certified area**.

## Pipeline

```
ScientificClaim (+ DecisionContext, + InputUncertainty)
  → apply_policy (risk → evidence bar; adds only)        claims/policy.py
  → compile_claim → select capability                    claims/compiler.py
  → plan_experiment (UQ study specs bound in the plan)   claims/planning.py, uq_studies.py
  → execute_plan                                         claims/execution.py
  → uncertainty studies: refinement (NUMERICAL),         claims/uq_studies.py
      propagation (EPISTEMIC_PARAMETER)                  numerical_uq.py, parameter_uq.py
  → SRIA evidence (+ study channel records)              credibility/sria_bridge.py
  → Arbiter: context of use enforced by the authority    sria/assurance/arbiter.py (certified area)
  → external evidence: benchmark / measurement /         claims/external_evidence.py
      literature, judged standing, never a level
  → verdict (policy_satisfied withholds admissibility)   claims/verdict.py
  → evidence gaps → next best experiment                 claims/gaps.py, next_experiment.py
  → sensitivity / robustness / challenge                 claims/analysis/sensitivity.py, challenge.py
  → scientific diagnostics: blockers → assumptions →      claims/analysis/diagnostics.py
      model-data discrepancy → repair hypotheses/actions
  → impact graph / replay bundle                         claims/analysis/impact.py, claims/replay/bundle.py
```

The natural-language boundary is `claims/nl_adapter.py`, an outer contract.
A language model proposes a claim. It holds no authority over verdicts,
evidence, levels, uncertainty, models or input values.

## What each phase can claim, and what it cannot

| Phase | Established by real runs | Never |
|---|---|---|
| 1 Context | Charter-bound evidence is VALID only under its own charter's policy, and `REQUIRED_CONTEXT` pins the decision | A wrong context is INVALID; it is INCONCLUSIVE |
| 2 UQ | GCI interval from a declared ladder (T3); Wilks 95/95 over propagated runs (electrothermal) | Zero or narrower when a rule fails; UNKNOWN instead |
| 3 Policy | Monotone risk → requirements, digest-bound, part of claim identity | Risk as evidence; consequence inferred from prose |
| 4 External | Pinned, applicable, quantified records are ADMISSIBLE | A validation level; a changed verdict |
| 5/6 Gaps | Every insufficiency explained, with pointers; actions derived from declarations | Invented prose; promised support |
| 7/8 | Sensitivity, a one-at-a-time envelope, challenges backed by run ids | Causal claims; weakening from weak evidence |
| 9/10 | Impact over existing identities; digest + re-derivation + replay | Edits to historical records |
| Diagnostic | Recorded blockers, explicit assumptions, model-data mismatch and testable repair hypotheses | A physical-causality claim, automatic model-form UQ, or a promised fix |

## Invariants

`tests/claims/test_intelligence_invariants.py` ties each of the 14
invariants to at least two tests. Every new guard is also a mutant in
`tests/claims/test_claims_mutations.py`, and some property there must kill it.

## Certification impact

The following are in the `assurance_admission` area of `current_core_v2.json`:
- `sria/assurance/arbiter.py`, `sria/assurance/obligations.py` and
  `sria/assurance/__init__.py` (Phase 1);
- `sria/evidence.py` (Phase 4 flag).

Every change there is additive:
- a new enum member, appended;
- a new keyword argument with a default;
- a new module-level helper;
- a decision over correctly bound evidence under an unbound policy records
  nothing new.

The certificate was already stale before this work, so recertification runs
through the manual Recertify Hardened Core workflow on Python 3.12. It is not
done locally.

## Open

- Measurement and literature have no production pins yet (the pin list is
  empty on purpose), so no production claim reaches ADMISSIBLE measurement
  evidence.
- MODEL_FORM uncertainty and supported discrepancy still have no quantitative producer. The diagnostic layer can now identify an admissible model-data mismatch, but explicitly does not convert that mismatch into MODEL_FORM uncertainty.
- NUMERICAL is quantified only where a capability declares a ladder (T3), and
  EPISTEMIC_PARAMETER only for electrothermal.
- The robustness envelope is one-at-a-time, and it treats the demanded band
  as unchanged away from the nominal point.
