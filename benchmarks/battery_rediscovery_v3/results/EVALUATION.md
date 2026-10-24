# battery_rediscovery_v3 evaluation

**V3_CONCLUSION: GEN1_REAL_DATA_ADVANTAGE_CONFIRMED** (C1-C4 hold and no single decided instance breaks them)

| Axis | Old Mind | Representation | Roles | Combined | Careful | Decided N |
|---|---:|---:|---:|---:|---:|---:|
| MODEL_ADEQUACY | 0/24 | 0/24 | 0/24 | 24/24 | 23/24 | 24 |
| IDENTIFIABILITY | 21/31 | 31/31 | 21/31 | 31/31 | 10/31 | 0 |
| WITHIN_CELL | 0/31 | 0/31 | 0/31 | 31/31 | 31/31 | 31 |
| CROSS_CELL | 5/23 | 5/23 | 5/23 | 23/23 | 23/23 | 18 |
| MODEL_DISCREPANCY | 31/31 | 31/31 | 31/31 | 31/31 | 0/31 | 0 |
| CORRECT_REFUSAL | 57 | 67 | 57 | 67 | 15 | - |
| FALSE_SUPPORT | 0 | 0 | 0 | 0 | 0 | - |
| FALSE_REFUSE | 73 | 73 | 73 | 0 | 1 | - |
| REPLAY | 33/33 EXACT | 33/33 EXACT | 33/33 EXACT | 33/33 EXACT | 33/33 EXACT | - |

Cells: correct (CORRECT + CORRECT_REFUSAL) / scored primary instances on that axis.

| Evidence-strength axis | Result |
|---|---:|
| TOTAL_DECIDED_INSTANCES | 73 |
| HELD_OUT_DECIDED_INSTANCES | 49 |
| INDEPENDENT_CELLS | 19 |
| OPERATING_CONDITIONS | ['GITT pulses, aged (latest RPT)', 'GITT pulses, beginning of life', 'One cell in a 4 C chamber, 2.0 A', 'One cell in a 43 C chamber, 4.0 A', 'constant-current rate tests (0.5-7.5 A)'] |
| SINGLE_INSTANCE_ROBUST | YES |
| IMPLEMENTATION_CORRELATED_INSTANCES | 0 |
| LEAKAGE | PASS |
| REPLAY | EXACT |
| REFERENCE_DISAGREEMENT_FRACTION | 0.0 |

- C1_primary_comparison: holds=True
- C2_false_support_not_material: holds=True
- C3_beats_single_layer_arms: holds=True
- C4_heldout_improvement: holds=True
- H1: holds=True
- H2: holds=True
- H3: holds=True
- H4: holds=True

Robustness: 146 perturbations, 0 breaking.

