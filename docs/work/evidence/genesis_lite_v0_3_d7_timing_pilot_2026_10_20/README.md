# Genesis-lite v0.3: D7 timing pilot, 2026-10-20

**Status:** NON_FORMAL_TIMING_PILOT, development tier.
- It ran on a fresh synthetic root (never the formal one) with its own campaign ids (`gl-pilot-<i>`), so no formal world
  was derived.
- It is a cost measurement only. It is not a measurement of any arm's quality.

**Owner decision:** D7 (2026-10-20). The formal machine is this WSL Ubuntu, and this pilot measures cost before the
budget is approved (Genesis §10.6).

**Provenance:**

| | |
|---|---|
| HEAD | `10f892cde98f51099365d13badbfde717ed52248` (escrow branch: `bind` requires the escrow half of FDA-05) |
| Tree | a clean native WSL clone |
| Python | 3.12.3 |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| Code sha256 | `arms.py` `11a6fe0ca65f…`, `harness.py` `331edd8a5a8f…`, `isolation.py` `21d237a0d133…`, `timing_pilot.py` `97ca7aa9ecb3…` |
| Pilot wall time | 455.2 s |
| `result.json` sha256 | `a543bc217fdcba296d4fe64616ec0f667462beab5543d483f89f5ba9e5e285e8` |

The `result.json` digest is pinned in `preregistration.TIMING_PILOT_EVIDENCE_SHA256`. The test
`test_d7_timing_pilot_evidence_is_pinned_and_timed_this_code` checks the code byte for byte, because the escrow branch is
rebased and its commit identities move.

Command, in WSL Ubuntu, from a fresh clone of the escrow branch at that HEAD:

`PYTHONPATH=src:. <venv 3.12>/bin/python -m benchmarks.genesis_lite.v0_3.timing_pilot --out <result.json> --campaigns 10`

## MEASURED

The pilot ran 10 world sets (presentation `paraphrased`, seed 0) against all 20
registered arms, with [6] cards per world set. Every card ran in its own D5 namespace. Every run was
VALID.

- **Seconds per world set, all arms: 43.5** (95 % interval ±0.74 over the
  10 world sets).

| arm | mean s / world set | max |
|---|---|---|
| always_insufficient | 2.06 | 2.27 |
| always_law | 2.18 | 2.34 |
| always_refuse | 2.03 | 2.13 |
| careful | 2.19 | 2.35 |
| extrapolating_fit | 2.21 | 2.41 |
| extrapolating_fit_dof | 2.23 | 2.43 |
| extrapolation_pair | 2.20 | 2.41 |
| extrapolation_pair_dof | 2.18 | 2.34 |
| fit_all_gated | 2.19 | 2.34 |
| fit_all_gated_dof | 2.20 | 2.33 |
| greedy_forward | 2.22 | 2.42 |
| greedy_forward_dof | 2.21 | 2.35 |
| historical_answer | 2.05 | 2.15 |
| monomial_enumeration | 2.19 | 2.41 |
| monomial_enumeration_dof | 2.23 | 2.43 |
| random_structures | 2.22 | 2.44 |
| random_structures_dof | 2.18 | 2.40 |
| single_setting | 2.17 | 2.35 |
| space_filling | 2.16 | 2.30 |
| space_filling_dof | 2.17 | 2.41 |

## ESTIMATED

The formal attempt is 2400 world sets × 2, counting the evaluator's replay of
every record as one more run (ASSUMED).

**Total: 58.0 h, 95 % interval 57.0–59.0 h**,
run sequentially on one machine.

Excluded: the candidate's own cost (D4); evaluator review time; restarts.

Not measured:
- parallel execution;
- the other presentations and seeds, assumed to cost the same as `paraphrased`/seed 0;
- the candidate (a Mind with model calls can be far slower).
