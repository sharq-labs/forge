# S1.1 — Transport guard calibration

Config hash: `f2a660b2cfbd54ff698dd8cf6d11391881a553da1ec7dae438f58757da6f3af8`
Scored rows: 15000

## Confusion counts by margin

| margin policy | GOOD_ALLOW | GOOD_BLOCK | FALSE_REFUSAL | DANGEROUS_MISS | CONTINUE |
|---|---|---|---|---|---|
| very_strict | 1200 | 750 | 1050 | 0 | 0 |
| strict | 1450 | 700 | 800 | 50 | 0 |
| moderate | 1800 | 450 | 450 | 300 | 0 |
| permissive | 2100 | 150 | 150 | 600 | 0 |
| no_guard | 2250 | 0 | 0 | 750 | 0 |

## Rates with explicit denominators

| margin policy | dangerous miss rate | false refusal rate | naive wrong-stop rate |
|---|---|---|---|
| very_strict | 0/750 = 0.0% [0.0, 0.5] | 1050/2250 = 46.7% [44.6, 48.7] | 750/3000 = 25.0% [23.5, 26.6] |
| strict | 50/750 = 6.7% [5.1, 8.7] | 800/2250 = 35.6% [33.6, 37.6] | 750/3000 = 25.0% [23.5, 26.6] |
| moderate | 300/750 = 40.0% [36.6, 43.5] | 450/2250 = 20.0% [18.4, 21.7] | 750/3000 = 25.0% [23.5, 26.6] |
| permissive | 600/750 = 80.0% [77.0, 82.7] | 150/2250 = 6.7% [5.7, 7.8] | 750/3000 = 25.0% [23.5, 26.6] |
| no_guard | 750/750 = 100.0% [99.5, 100.0] | 0/2250 = 0.0% [0.0, 0.2] | 750/3000 = 25.0% [23.5, 26.6] |

Denominators: dangerous-miss rate is over cases where certification would be scientifically wrong; false-refusal rate is over cases where certification would be correct.

### Replication degeneracy — read before quoting the intervals above

Cells (x* x margin x truth family): 300. Cells whose outcome varies across the 50 seeds: **0**.

The replications are **degenerate**: the observation noise never flips a decision, so all 50 seeds in a cell agree. Point estimates are unaffected, but the row-based intervals above are far too narrow and must not be quoted. The honest denominators are the cell counts below.

| margin policy | dangerous miss rate (cells) | false refusal rate (cells) |
|---|---|---|
| very_strict | 0/15 = 0.0% [0.0, 20.4] | 21/45 = 46.7% [32.9, 60.9] |
| strict | 1/15 = 6.7% [1.2, 29.8] | 16/45 = 35.6% [23.2, 50.2] |
| moderate | 6/15 = 40.0% [19.8, 64.3] | 9/45 = 20.0% [10.9, 33.8] |
| permissive | 12/15 = 80.0% [54.8, 93.0] | 3/45 = 6.7% [2.3, 17.9] |
| no_guard | 15/15 = 100.0% [79.6, 100.0] | 0/45 = 0.0% [0.0, 7.9] |

## Trade-off frontier

| margin policy | margin | false refusal rate | dangerous miss rate |
|---|---|---|---|
| very_strict | 0.0 | 46.7% | 0.0% |
| strict | 0.5 | 35.6% | 6.7% |
| moderate | 1.5 | 20.0% | 40.0% |
| permissive | 3.0 | 6.7% | 80.0% |
| no_guard | None | 0.0% | 100.0% |

## By truth class

| margin policy | class | GOOD_ALLOW | GOOD_BLOCK | FALSE_REFUSAL | DANGEROUS_MISS |
|---|---|---|---|---|---|
| very_strict | BENIGN | 600 | 0 | 900 | 0 |
| very_strict | REGIME_CHANGE | 600 | 750 | 150 | 0 |
| strict | BENIGN | 750 | 0 | 750 | 0 |
| strict | REGIME_CHANGE | 700 | 700 | 50 | 50 |
| moderate | BENIGN | 1050 | 0 | 450 | 0 |
| moderate | REGIME_CHANGE | 750 | 450 | 0 | 300 |
| permissive | BENIGN | 1350 | 0 | 150 | 0 |
| permissive | REGIME_CHANGE | 750 | 150 | 0 | 600 |
| no_guard | BENIGN | 1500 | 0 | 0 | 0 |
| no_guard | REGIME_CHANGE | 750 | 0 | 0 | 750 |
