# BR-MIND-REPSEM-01: minimal representation + scientific semantic roles repair

Branch `research/mind-representation-semantics-v1` (worktree `D:/forge-repsem`), based on the battery_rediscovery_v1
evaluation commit `d516e681`. Local only. **Development evidence only**: no battery data was evaluated, no battery v2 was
run, and nothing here is a battery improvement claim.

## 1. Gap map (`gap_map.py` → `results/GAP_MAP.json`)

Inputs, all frozen before this task and unmodified:
- the representability records in v1 `PLAN.json`;
- the sealed Mind outputs `MIND__P1.json` and `MIND__P2.json`;
- the candidate-visible pack;
- three labels per instance from `EVALUATION.json`: `class`, `mind_answer`, `mind_outcome`.

The `truth` and `careful_answer` fields are never read, and a test pins this. Each gap is classified from what the
Mind's sealed record says it did.

| Axis | Current answer | Representability | Primary gap | Evidence |
|---|---|---|---|---|
| P1 MODEL_ADEQUACY | NOT_ASSESSABLE | NOT_REPRESENTABLE | REPRESENTATION_MISSING | Frozen capability: the 1RC family is not in the log-linear hypothesis space |
| P2 MODEL_ADEQUACY | NOT_ASSESSABLE | NOT_REPRESENTABLE | REPRESENTATION_MISSING | Same |
| P1 MODEL_DISCREPANCY | NOT_ASSESSABLE | NOT_REPRESENTABLE | REPRESENTATION_MISSING | Frozen capability: the arm never computes residuals of the declared family |
| P2 MODEL_DISCREPANCY | NOT_ASSESSABLE | NOT_REPRESENTABLE | REPRESENTATION_MISSING | Same |
| P1 IDENTIFIABILITY | REFUSED | NOT_REPRESENTABLE | REPRESENTATION_MISSING | The RELAXATION problem is refused (`t_off_s` box low ≥ high); R0/R1/C1 have no representation, and only a proxy path exists |
| P2 IDENTIFIABILITY | REVIEW | APPROXIMATELY | MULTIPLE_CAUSES | The law is linear in ln t_off with no curvature, translated to REVIEW. Two causes: the parameter question is read from an observable's shape (representation), and the log-linear family has no exponential relaxation (hypothesis generation) |
| P1 CROSS_CELL_TRANSFER | NOT_ASSESSABLE | APPROXIMATELY | SEMANTIC_ROLE_ERROR | Refused as a passive association with `z` (inclusion 1.0). `z` is the coulomb-counted state (pack `conventions`) |
| P2 WITHIN_CELL_GENERALIZATION | NOT_ASSESSABLE | APPROXIMATELY | SEMANTIC_ROLE_ERROR | Refused as a passive association with `I_A` (inclusion 0.99 and 0.97). `I_A` is the protocol's pulse level (pack `description`) |
| P1 WITHIN_CELL_GENERALIZATION | NOT_ASSESSABLE | APPROXIMATELY | not a failure (CORRECT_REFUSAL) | |
| P2 CROSS_CELL_TRANSFER | NOT_ASSESSABLE | EXACTLY | not a failure (CORRECT_REFUSAL) | |

Tally of the 8 failures: REPRESENTATION_MISSING 5, SEMANTIC_ROLE_ERROR 2, MULTIPLE_CAUSES 1, all other gap classes 0.

## 2–5. The repair (`src/engcore/mind/repsem/`)

`engcore.mind.minimal` is unchanged. battery_rediscovery_v1 pins it byte-exact, and `test_battery_v1_frozen_artifacts_are_untouched` checks every v1 frozen file.

- **`roles.py`**: seven roles.
  - CONTROLLED_INPUT, FIXED_PROTOCOL_CONDITION, STATE_VARIABLE (with `driven_by`), MEASUREMENT, DERIVED_QUANTITY
    (with `derived_from`), LATENT_PARAMETER, NUISANCE_VARIABLE.
  - Roles are accepted only from `problem_specification` or `protocol_metadata`. Every data column must be declared,
    and a LATENT_PARAMETER may not appear as a column.
  - There is no code path that infers a role from a name or from the data.
  - `legacy_role_table` reproduces v1's two-class rule, for ablation only.
- **`claims.py`**:
  - the five dispositions;
  - ten scoped claim states, one positive and one negative per v1 question. MODEL_DISCREPANCY's positive state is
    `UNRESOLVED`, never "absent", and it carries `not_quantified_as_zero` plus the resolution;
  - six refusal reasons.
  - Each claim type records its meaning, required evidence, refusal condition and applicability scope.
  - Invariants checked on construction:
    - SUPPORTED and NOT_SUPPORTED carry the matching state and bound evidence;
    - a non-committal disposition carries no state and must name a refusal reason, together with the condition that
      triggered it.
- **`hypothesis.py`**: the `ScientificHypothesis` record. Its fields:
  - model family;
  - parameter set (estimates and standard errors);
  - applicability domain;
  - variable roles;
  - claims;
  - competing alternatives (the declared rival, with its discrimination status);
  - evidence for, evidence against;
  - unresolved discriminators.

  It has no `law` field, and `from_dict` refuses one. Its identity is the canonical `sria.decision.Hypothesis`.
- **`families.py` and `assess.py`**: a declared family names its slots by role, and `bind` fills each slot from the
  problem's role table. Under the legacy table, binding is refused as REPRESENTATION_UNAVAILABLE. Judgments:
  - **Identifiability**:
    - a rank-deficient Jacobian decides NOT_IDENTIFIABLE without any noise declaration;
    - otherwise a declared noise is required, and the local covariance is classified by the frozen V1 rule
      (`engcore.hybrid_uq.identifiability.classify`);
    - a weakly identified result, or an estimate on a bound, gives REVIEW.
  - **Adequacy**: the declared bar, or a chi-square against the declared noise.
  - **Discrepancy**: excess residual variance, and lag-1 residual autocorrelation (when independence is declared).
  - **Within- and cross-unit transfer**: applicability (domain and unit relation) is checked first, and an
    out-of-domain subset is never scored. An in-domain failure of the bar is NOT_SUPPORTED, not NOT_ASSESSABLE.
  - Missing noise, bar or set gives NOT_ASSESSABLE with reason INSUFFICIENT_EVIDENCE. A residual estimate never
    stands in for a missing declared noise.

## 6. Failing-first tests

`tests/mind/test_repsem_failing_first.py` (A–H plus counter-tests) and `tests/mind/test_repsem_replay.py` were
committed in `db439744` before the module existed. Their collection then failed with ImportError. Two expectations were
wrong when written, and were corrected as disclosed in PROGRESS:
- test B assumed the claim state `NOT_IDENTIFIABLE` and the refusal reason `NOT_IDENTIFIABLE` differ as strings. The
  brief names both identically; they differ by field and by disposition.
- test H used MODEL_INADEQUATE's within-cell set as negative evidence, but that label was disproved by the
  construction audit.

## 7. Synthetic fixtures (`fixtures.py`)

Six fixtures × five noise seeds × two protocols:
- **short**: 20 s pulses, 60 s rests.
- **long**: 200 s pulses, 300 s rests. Added after the OLD_MIND probe showed that v1's adapter cannot pose a 20 s
  pulse: its time box starts at median(dt)/0.05 = 20 s.

The declared family is always `rc1/1` (rival `rint/1`). The fixture determines what generates the data.

Every truth label is checked by `construction_audit` on noise-free data, through a path independent of the assessor:
- a dense 4³-start oracle fit;
- held-out errors against the bar with a 2× margin;
- Fisher identifiability at the true parameters.

A label the audit does not support is left unscored, never guessed.

Fixture corrections made before any ablation run, all disclosed:
- MODEL_INADEQUATE was first a slow second RC branch. The audit showed rc1 absorbs it (3.1 mV rmse, below the 5 mV
  bar), so it was replaced by a charge-transfer overpotential.
- That fixture's within-cell truth is SUPPORTED, not NOT_SUPPORTED: an inadequate family still interpolates the 1.5 A
  level to 2.2 mV.
- The cross-unit R0 was raised from 0.022 to 0.026 Ω to clear the 2× audit margin.
- Under the long protocol, three identifiability labels (WEAKLY_IDENTIFIABLE at truth) and one within-cell label are
  unscored.

## 8. Ablation (`arms.py`, `run_ablation.py` → `results/ABLATION.json`)

The four arms:
- **OLD_MIND**: v1's Mind arm, unchanged.
- **SEMANTIC_ROLES_ONLY**: the same Mind, with the prediction probe posed by roles: current settable, charge state not
  a covariate, temperature passive.
- **REPRESENTATION_ONLY**: `assess` under the legacy roles.
- **REPRESENTATION_PLUS_ROLES**: `assess` under the declared roles.

Correct answers out of scored answers (5 seeds × 2 protocols):

| Fixture | Old | Representation only | Roles only | Combined |
|---|---:|---:|---:|---:|
| IDENTIFIABLE | 15/45 | 10/45 | 10/45 | 45/45 |
| NON_IDENTIFIABLE | 10/50 | 10/50 | 10/50 | 50/50 |
| MODEL_INADEQUATE | 10/35 | 10/35 | 10/35 | 35/35 |
| CROSS_DOMAIN_TRANSFER_FAIL | 10/45 | 0/45 | 0/45 | 45/45 |
| MODEL_DISCREPANCY | 11/40 | 10/40 | 10/40 | 40/40 |
| OUT_OF_DOMAIN | 10/45 | 20/45 | 20/45 | 45/45 |
| **Total correct** | **66/260** | **60/260** | **60/260** | **260/260** |
| False support | 10 | 0 | 0 | 0 |
| False refusal | 184 | 200 | 200 | 0 |

How to read these numbers:
- **All 10 OLD_MIND false supports are the OUT_OF_DOMAIN fixture under the long protocol.** v1's adapter checks
  applicability only as extrapolation of the settable inputs, so its own law "met the bar" at 3 A and 40 °C.
- **REPRESENTATION_ONLY's zero is structural.** By design a declared family binds only through roles, so under the
  legacy table every family question is refused as REPRESENTATION_UNAVAILABLE.
- **SEMANTIC_ROLES_ONLY's zero is empirical.** Posed with current as a settable input, the Minimal Mind's first design
  request is 1.15 A. The recorded pool holds only 1 and 2 A, so the world refuses it and no rival is ever fitted. The
  Minimal Mind's problem form has two classes, settable and passive, and neither carries a FIXED_PROTOCOL_CONDITION
  faithfully.
- **The combined arm's perfect score is on fixtures whose generating systems are built around its own declared family,
  with 2× truth margins.** It shows that the representation and the refusal logic are correct and expressive. It is
  not evidence of performance on real data.
- 40 of the 60 cross-cell scores are absent sets, which every arm answers correctly.

## 9. Replay

- 120/120 repsem assessments (60 instances × legacy and declared roles) re-execute byte-identically through `replay`.
- A tampered record, or a record checked against another problem, raises `ReplayMismatch`.
- The fit uses a fixed set of starts; there is no randomness.

## Limits for a battery v2 plan

- **P1's family is not implemented here.** P1 declares an UNKNOWN fitted OCV table (13 knots). A v2 needs a
  `DeclaredFamily` for it; v1's `candidate/model.py` already implements that model.
- **P1 will still refuse some questions by design.** P1 declares voltage uncertainty UNKNOWN. Adequacy without a bar,
  compatibility of discrepancy, and practical identifiability will therefore answer NOT_ASSESSABLE / INSUFFICIENT_EVIDENCE
  (missing uncertainty never becomes zero). Only structural non-identifiability and resolved residual structure can
  decide without it.
- **Roles must come from the v2 pack, not from this README.** The gap map's role readings come from pack prose. A v2
  pack must declare roles as protocol metadata, frozen before the run.
- **The developer is not blind.** The v1 outcome labels, the README's CAREFUL column and v0's answers were known while
  this repair was designed.
