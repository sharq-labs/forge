# Genesis-lite v0.3: D7 timing pilot through the D5-A1b containers, 2026-10-21

**Status:** NON_FORMAL_TIMING_PILOT, development tier.
- The pilot ran on a fresh synthetic root (never the formal one) with its own campaign ids (`gl-pilot-<i>`), so no
  formal world was derived.
- It is a cost measurement only. It says nothing about any arm's quality.

It supersedes the 2026-10-20 pilot
([`../genesis_lite_v0_3_d7_timing_pilot_2026_10_20/`](../genesis_lite_v0_3_d7_timing_pilot_2026_10_20/README.md),
sha256 `3759ff33…`). That pilot timed the A1 namespace launcher; it is kept as HISTORICAL_ONLY and stays pinned as
`HISTORICAL_TIMING_PILOT_EVIDENCE`.

**Owner decision:** D7 (2026-10-20) is unchanged.
- The formal machine is this WSL Ubuntu.
- The budget is 72 h for the baselines, plus the candidate's measured cost.

Only the timing evidence is refreshed here.

## Provenance

| | |
|---|---|
| HEAD | `f8bf7ed71163c44941bba9fe11cd428f157a30b5`: a fresh clone from a git bundle, clean before and after |
| Machine | WSL Ubuntu-24.04, kernel `6.6.87.2-microsoft-standard-WSL2`, rootless Podman 4.9.3 |
| Launcher | `isolation.formal_launcher()`: a brand-new D5-A1b container per card, recorded in `deployment` |
| Pre-admission | `isolation.verify_containers()` ran first and PASSED in 7.6 s. All six devices were ADMITTED under `stateless_device/1`. The pilot refuses to time anything otherwise. |
| D5 evidence | It ran under the pinned D5 evidence, sha256 `b3bc0b64…` (`deployment_evidence_sha256`). |
| Code sha256 | `timing_pilot.py`, `harness.py`, `isolation.py`, `arms.py`, `container_evidence.py`, `container_probe.py` and `device_contract.py`, in `result.json` provenance |
| Wall time | 681.5 s. 0 containers, pods or volumes were left (`command.json`). |
| `result.json` sha256 | `6f6b1418dfd78cebe8795c4f6587204e5da823088dd7afe85107076d5e576092`, pinned as `TIMING_PILOT_EVIDENCE_SHA256` |

The command was `PYTHONPATH=src:. <venv 3.12>/bin/python -m benchmarks.genesis_lite.v0_3.timing_pilot --out <result.json> --campaigns 10`.

## MEASURED

- The pilot ran 10 world sets (presentation `paraphrased`, seed 0) against all 20 registered arms, with 6 cards per
  world set. Every card ran in its own container, and every run was VALID.
- **Seconds per world set, all arms: 67.9** (95 % interval ±0.46 over the 10 world sets). On 2026-10-20 the A1
  namespaces gave 42.8 s.
- Every arm took between 3.26 s and 3.44 s on average per world set; the largest single value was 3.77 s. The per-arm
  table is in `result.json`.

## ESTIMATED (sequential)

- 2,400 world sets × 2 runs, counting the evaluator's replay as one more run (ASSUMED): **90.5 h**, 95 % interval
  89.9–91.1 h.
- **The operator's run alone: 45.2 h**, plus the one pre-admission check (7.6 s). The budget cap in
  `formal.run_formal` times only this run. It is below the approved 72 h baseline cap.
- Excluded: the candidate's own cost (D4), evaluator review time and restarts.
- Not measured: parallel execution; the other presentations and seeds, assumed to cost the same; the candidate.
