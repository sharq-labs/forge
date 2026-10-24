# battery_rediscovery_v1 evaluation (BR-BATT-REDISC-02)

Conclusion: **REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY** (development; not formal, not certified; no amendment).

v0 history: PREREGISTERED_RESULT = LEAKAGE_INVALIDATED; POST_SEAL_AMENDMENT_RESULT = REPRESENTATION_BOTTLENECK; CONFIRMED_RESULT = NONE.

| Axis | Mind | Careful baseline | Representability | Result (Mind) |
|---|---|---|---|---|
| MODEL_ADEQUACY | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | P1 NOT_SUPPORTED; P2 NOT_SUPPORTED | P1 NOT_REPR; P2 NOT_REPR | P1 FALSE_REFUSE; P2 FALSE_REFUSE |
| IDENTIFIABILITY | P1 REFUSED; P2 REVIEW | P1 SUPPORTED; P2 SUPPORTED | P1 NOT_REPR; P2 APPROX | P1 FALSE_REFUSE; P2 FALSE_REFUSE |
| WITHIN_CELL_GENERALIZATION | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | P1 NOT_ASSESSABLE; P2 NOT_SUPPORTED | P1 APPROX; P2 APPROX | P1 CORRECT_REFUSAL; P2 FALSE_REFUSE |
| CROSS_CELL_TRANSFER | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | P1 NOT_SUPPORTED; P2 NOT_ASSESSABLE | P1 APPROX; P2 EXACT | P1 FALSE_REFUSE; P2 CORRECT_REFUSAL |
| MODEL_DISCREPANCY | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | P1 NOT_SUPPORTED; P2 NOT_SUPPORTED | P1 NOT_REPR; P2 NOT_REPR | P1 FALSE_REFUSE; P2 FALSE_REFUSE |
| CORRECT_REFUSAL | 2 | 2 | APPROX: 1, EXACT: 1 | |
| FALSE_SUPPORT | 0 | 1 | - | |
| FALSE_REFUSE | 8 | 0 | APPROX: 3, NOT_REPR: 5 | |

| Coverage | Count | Mind correct | Mind incorrect/refused |
|---|---:|---:|---:|
| REPRESENTABLE_EXACTLY | 1 | 1 | 0 |
| REPRESENTABLE_APPROXIMATELY | 4 | 1 | 3 |
| NOT_REPRESENTABLE | 5 | 0 | 5 |
| UNKNOWN | 0 | 0 | 0 |

- failures: 8; in NOT_REPRESENTABLE: 5; share_N = 0.62
- accuracy on R (EXACT+APPROX): Mind 0.40, CAREFUL 1.00; on N: Mind 0.00, CAREFUL 0.80; on EXACT only: Mind 1.00, CAREFUL 1.00
- totals (CORRECT + CORRECT_REFUSAL): MIND_V0_REPRESENTATION 2, FIXED_FIT 4, CAREFUL_BASELINE 9, ALWAYS_FIT 1, ALWAYS_REFUSE 2
- checks: {"leakage_ok": true, "end_to_end": true, "replay_ok": true, "careful_total": 9, "trivial_best": 2, "n_R": 5, "n_N": 5, "n_U": 0, "share_N": 0.625, "acc_R_mind": 0.4, "acc_N_mind": 0.0, "acc_R_careful": 1.0, "majority_of_failures_in_N": true, "materially_better_on_R": true, "not_poor_where_representable": false}
- leakage: mutation pre-run PASS, post-seal PASS; pre-seal audit PASS, post-seal audit PASS
- replay: 12/12 outputs identical, 5/5 traces VERIFIED
- v0 replication: 12/12 sealed outputs byte-identical to v0's

