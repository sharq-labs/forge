# Genesis-lite v0.3: D5 deployment verification (option A1, rootless namespaces), 2026-10-20

**Status:** DEPLOYMENT_VERIFICATION, development tier. This verifies the isolation of proposer cards. It is not a
measurement of any arm, not a certification, and it does not replace the certified isolation-probe rerun (OD-3).

**Owner decision:** D5 / OD-20, option A1, decided 2026-10-20 in session.

**Provenance** (`result.json`):

| | |
|---|---|
| HEAD | `70f851615c8da1272f8c23cafce13ee3a777c06c` (draft branch) |
| Tree | a clean native WSL clone (`tree_clean: true`) |
| Python | 3.12.3 |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| unshare | unshare from util-linux 2.39.3 |
| WSL | True |
| Code sha256 | `deployment_attacks.py` `5903ace4a733…`, `harness.py` `0dd5cab60079…`, `isolation.py` `21d237a0d133…`, `secret_scan.py` `da7eb1d83336…` |
| Wall time | 39.0 s |
| `result.json` sha256 | `80db5957d71755d76f349383f735c8c2ca61d606e38f20efe51edb17e9617df7` |

The `result.json` digest is pinned in `preregistration.DEPLOYMENT_EVIDENCE_SHA256` and checked by
`test_d5_deployment_evidence_is_pinned_verified_and_measured_this_code`.

Command, in WSL Ubuntu, from a fresh clone of the draft branch at that HEAD:

`PYTHONPATH=src:. <venv 3.12>/bin/python -m benchmarks.genesis_lite.v0_3.isolation --out <result.json> --cards 2`

**Method:**
- Ten attack channels each run as a proposer in fresh per-card processes of the v0.3 harness, twice: once without the
  namespaces and once with them.
- The operator's canary secrets are a random root file, a run log holding the root, and a registry line, all in a host
  temp directory. A TCP listener runs on host loopback.
- Verified requires every channel REFUSED with the namespaces, and the same probe REACHED without them (the probes have
  power).

| channel | without namespaces | with namespaces |
|---|---|---|
| cmdline | REACHED | REFUSED |
| cross_card_state | REACHED | REFUSED |
| network | REACHED | REFUSED |
| operator_process | REACHED | REFUSED |
| package_write | REACHED | REFUSED |
| persistence | REACHED | REFUSED |
| root_file | REACHED | REFUSED |
| run_log | REACHED | REFUSED |
| secret_inventory | REACHED | REFUSED |
| wsl_interop | REACHED | REFUSED |

**A defect found and fixed during verification.**
- The first run (HEAD `e15801b0`) was NOT verified: `secret_inventory` was REACHED inside the namespaces.
- Cause: the scanner flagged its own compiled bytecode in the card's private cache. CPython folds the marker pieces
  `b'a' + b'b'` into one constant.
- Fixed test-first in `70f85161` (`test_fda19_the_scan_does_not_flag_its_own_compiled_bytecode`), then re-run.

**Residual risks, disclosed:**
- Outside its namespaces the proposer runs under the same Linux account.
- The benchmark tree and the Python environment are readable inside the namespaces, so they must hold no secret.
- On WSL the namespaces share the host's utility VM.
- The certified escrow stays in the operator's process. The `operator_process` channel shows that a proposer cannot
  reach any other process.
- The certified isolation-probe rerun is OD-3.
