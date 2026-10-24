# battery_rediscovery_v2 evaluation

**Conclusion: REAL_DATA_IMPROVEMENT_CONFIRMED** (H1, H2 and H3 hold)

| Axis | Old Mind | Representation | Roles | Combined | Careful |
|---|---:|---:|---:|---:|---:|
| MODEL_ADEQUACY | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 |
| IDENTIFIABILITY | 1/2 | 1/2 | 1/2 | 2/2 | 2/2 |
| WITHIN_CELL | 0/1 | 0/1 | 0/1 | 1/1 | 1/1 |
| CROSS_CELL | 1/2 | 1/2 | 1/2 | 2/2 | 2/2 |
| MODEL_DISCREPANCY | 1/2 | 1/2 | 1/2 | 2/2 | 1/2 |
| CORRECT_REFUSAL | 3 | 3 | 3 | 3 | 2 |
| FALSE_SUPPORT | 0 | 0 | 0 | 0 | 0 |
| FALSE_REFUSE | 5 | 5 | 5 | 0 | 1 |
| REPLAY | 2/2 EXACT | 2/2 EXACT | 2/2 EXACT | 2/2 EXACT | 2/2 EXACT |

Cells: correct (CORRECT + CORRECT_REFUSAL) / scored instances on that axis, over Q1 and Q2.

Truth per instance:

- Q1 MODEL_ADEQUACY: None
- Q1 IDENTIFIABILITY: NOT_ASSESSABLE
- Q1 WITHIN_CELL_GENERALIZATION: None
- Q1 CROSS_CELL_TRANSFER: NOT_SUPPORTED
- Q1 MODEL_DISCREPANCY: NOT_ASSESSABLE
- Q2 MODEL_ADEQUACY: SUPPORTED
- Q2 IDENTIFIABILITY: SUPPORTED
- Q2 WITHIN_CELL_GENERALIZATION: SUPPORTED
- Q2 CROSS_CELL_TRANSFER: NOT_ASSESSABLE
- Q2 MODEL_DISCREPANCY: NOT_SUPPORTED

Leakage: post-seal audit PASS, post-seal mutation PASS.
Replay: exact=True; repsem 4/4 EXACT; OLD_MIND traces 4/4 VERIFIED.

