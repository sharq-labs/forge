# Genesis-lite v0.3: D7 timing pilot, 2026-10-20

**Status:** NON_FORMAL_TIMING_PILOT, development tier.
- It ran on a fresh synthetic root (never the formal one) with its own campaign ids (`gl-pilot-<i>`), so no formal world
  was derived.
- It is a cost measurement only. It is not a measurement of any arm's quality.

**Owner decision:** D7 (2026-10-20).
- The formal machine is this WSL Ubuntu.
- The pilot measures cost before the budget is approved (Genesis §10.6).
- Budget approved: 72 h for the baselines, plus the candidate's measured cost.

**Provenance:**

| | |
|---|---|
| HEAD | `f7df896836b62e7bc96f2eaee28883d655cb4e3a` (escrow branch: `bind` requires the escrow half of FDA-05) |
| Tree | a clean native WSL clone |
| Python | 3.12.3 |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| Code sha256 | `arms.py` `11a6fe0ca65f…`, `harness.py` `331edd8a5a8f…`, `isolation.py` `d7f96b37608d…`, `timing_pilot.py` `97ca7aa9ecb3…` |
| Pilot wall time | 455.3 s |
| `result.json` sha256 | `3759ff334f690f4d3601b588a4bfb6c9dd71f186975a45d024a8714cb85beb4f` |

The `result.json` digest is pinned in `preregistration.TIMING_PILOT_EVIDENCE_SHA256`. The test
`test_d7_timing_pilot_evidence_is_pinned_and_timed_this_code` checks the code byte for byte, because the escrow branch is
rebased and its commit identities move.

**Superseded runs:**
- The first pilot (HEAD `10f892cd`, `a543bc217fdcba29…`, 43.5 s per world set). It timed the launcher before the
  fourth scientific review made every card drop its capabilities (`setpriv`). The D7 budget was decided on this run.
- The re-run under the capability drop (HEAD `d5852482`, `4361bb626c5df8f4…`, 43.7 s), on the earlier distro.

This run is on the owner's fresh, hardened Ubuntu-24.04 distro, with interop and automount disabled.

Command, in WSL Ubuntu, from a fresh clone of the escrow branch at that HEAD:

`PYTHONPATH=src:. <venv 3.12>/bin/python -m benchmarks.genesis_lite.v0_3.timing_pilot --out <result.json> --campaigns 10`

## MEASURED

The pilot ran 10 world sets (presentation `paraphrased`, seed 0) against all 20
registered arms, with [6] cards per world set. Every card ran in its own D5 namespace without
capabilities. Every run was VALID.

- **Seconds per world set, all arms: 42.8** (95 % interval ±0.58 over the
  10 world sets).

| arm | mean s / world set | max |
|---|---|---|
| always_insufficient | 2.05 | 2.12 |
| always_law | 2.13 | 2.26 |
| always_refuse | 2.04 | 2.22 |
| careful | 2.15 | 2.21 |
| extrapolating_fit | 2.16 | 2.26 |
| extrapolating_fit_dof | 2.15 | 2.24 |
| extrapolation_pair | 2.16 | 2.35 |
| extrapolation_pair_dof | 2.17 | 2.26 |
| fit_all_gated | 2.15 | 2.34 |
| fit_all_gated_dof | 2.14 | 2.30 |
| greedy_forward | 2.18 | 2.31 |
| greedy_forward_dof | 2.17 | 2.24 |
| historical_answer | 2.02 | 2.12 |
| monomial_enumeration | 2.13 | 2.30 |
| monomial_enumeration_dof | 2.16 | 2.31 |
| random_structures | 2.15 | 2.25 |
| random_structures_dof | 2.20 | 2.41 |
| single_setting | 2.17 | 2.46 |
| space_filling | 2.14 | 2.26 |
| space_filling_dof | 2.16 | 2.28 |

## ESTIMATED

The formal attempt is 2400 world sets × 2, counting the evaluator's replay of
every record as one more run (ASSUMED).

**Total: 57.0 h, 95 % interval 56.2–57.8 h.** Of
that, the operator's run alone is about 28.5 h. The budget cap in
`formal.run_formal` times the operator's run only.

Excluded: the candidate's own cost (D4); evaluator review time; restarts.

Not measured:
- parallel execution;
- the other presentations and seeds, assumed to cost the same;
- the candidate.
