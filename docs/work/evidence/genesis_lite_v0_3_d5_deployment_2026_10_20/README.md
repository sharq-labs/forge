# Genesis-lite v0.3: D5 deployment verification (option A1, rootless namespaces), 2026-10-20

**Status:** DEPLOYMENT_VERIFICATION, development tier. This verifies the isolation of proposer cards. It is not a
measurement of any arm, not a certification, and it does not replace the certified isolation-probe rerun (OD-3).

**Owner decision:** D5 / OD-20, option A1, decided 2026-10-20 in session.

**Provenance** (`result.json`):

| | |
|---|---|
| HEAD | `a4d73dd4f57592e191cb757dd91be21a6427d306` (draft branch) |
| Tree | a clean native WSL clone (`tree_clean: true`) |
| Python | 3.12.3 |
| Kernel | 6.6.87.2-microsoft-standard-WSL2 |
| Tools | setpriv: setpriv from util-linux 2.39.3; unshare: unshare from util-linux 2.39.3 |
| WSL | False |
| Code sha256 | `deployment_attacks.py` `6961025b26a9…`, `harness.py` `331edd8a5a8f…`, `isolation.py` `d7f96b37608d…`, `secret_scan.py` `da7eb1d83336…` |
| Wall time | 400.5 s |
| `result.json` sha256 | `519f3669b48b5bd08f79af172af51e590ce7e1432141e96bfc7446edd8c2f0c7` |

The `result.json` digest is pinned in `preregistration.DEPLOYMENT_EVIDENCE_SHA256` and checked by
`test_d5_deployment_evidence_is_pinned_verified_and_measured_this_code`. That test also refuses the evidence once the
launcher, the attack suite, the harness or the scanner changes.

**Run history:**
- `e15801b0`: NOT verified. `secret_inventory` was REACHED inside the namespaces, because the scanner flagged its own
  bytecode (CPython constant-folds `b'a' + b'b'`). Fixed test-first in `70f85161`.
- `70f85161` (`80db5957…`) and `f9909822` (`782a1b91…`): reported verified. **Withdrawn** by the fourth scientific review
  (I-1, BLOCKER): the proposer kept every capability as root of its user namespace, so it could unmount the masks or
  remount the kept tree read-write, and no probe tried. Several REFUSED verdicts were also vacuous (I-3).
- `20f3d379`: capabilities dropped (`setpriv`), new `unmask` and `remount_rw` channels, persistence detected from the
  host, a scan of everything visible. NOT verified:
  - `remount_rw` had no power (it probed a non-mount point);
  - `secret_inventory` was REACHED, because the committed preregistration held the registry-line marker in compact JSON.
  Both are fixed in `3d960cd0`.
- `3d960cd0` (`8031b422a3d7b590…`): verified on the old Ubuntu distro. Superseded when the owner wiped every distro and
  installed a fresh, hardened Ubuntu-24.04.
- `a4d73dd4`: verified on the hardened Ubuntu-24.04 distro. This is the run pinned here. The hardening is the
  owner's, in `/etc/wsl.conf` (`[interop] enabled=false, appendWindowsPath=false`; `[automount] enabled=false,
  mountFsTab=false`). Confirmed read-only before the run:
  - no `WSLInterop` binfmt handler is registered;
  - PATH has no Windows entries;
  - `/mnt/c`, `/mnt/d` and `/mnt/k` are empty, not mounted;
  - the only Windows-backed mount, `/usr/lib/wsl/drivers` (9p), is read-only;
  - the `/run/WSL/*_interop` sockets still exist, and the deployment masks `/run` for every card.

**Still NOT_PROVEN** (fifth scientific review, N-1): the cross-card channel probes only the card's private `/tmp`. A
REFUSED there does not show that no writable location is shared between cards. The readiness ledger keeps D5, FDA-18
and the isolation boundary at BLOCKED_WITH_EVIDENCE_NOT_PROVEN until a per-card writable-mount inventory proves it.

Command, in WSL Ubuntu, from a fresh clone of the draft branch at that HEAD:

`PYTHONPATH=src:. <venv 3.12>/bin/python -m benchmarks.genesis_lite.v0_3.isolation --out <result.json> --cards 2`

**Method:**
- Twelve attack channels each run as a proposer in fresh per-card processes of the v0.3 harness, under three
  configurations:
  - without namespaces;
  - in the namespaces WITH capabilities (the escapable launcher the review found, used only as a power control);
  - in the D5 deployment, with capabilities dropped.
- The operator's canary secrets are a random root file, a run log holding the root, and a registry line, all in a host
  temp directory. A TCP listener runs on host loopback.
- Inside a namespace, the scan covers everything visible except root-owned system directories.
- Verified requires every channel REFUSED in the D5 deployment, and the same probe REACHED in at least one control
  configuration (the probes have power).

| channel | without namespaces | namespaces with capabilities | D5 deployment |
|---|---|---|---|
| cmdline | REACHED | REFUSED | REFUSED |
| cross_card_state | REACHED | REFUSED | REFUSED |
| network | REACHED | REFUSED | REFUSED |
| operator_process | REACHED | REFUSED | REFUSED |
| package_write | REACHED | REFUSED | REFUSED |
| persistence | REACHED | REFUSED | REFUSED |
| remount_rw | REFUSED | REACHED | REFUSED |
| root_file | REACHED | REFUSED | REFUSED |
| run_log | REACHED | REFUSED | REFUSED |
| secret_inventory | REACHED | REFUSED | REFUSED |
| unmask | REFUSED | REACHED | REFUSED |
| wsl_interop | REACHED | REFUSED | REFUSED |

**Residual risks, disclosed:**
- Outside its namespaces the proposer runs under the same Linux account.
- The benchmark tree and the Python environment are readable inside the namespaces, so they must hold no secret.
- On WSL the namespaces share the host's utility VM.
- The certified escrow stays in the operator's process. The `operator_process` channel shows that a proposer cannot
  reach any other process.
- The certified isolation-probe rerun is OD-3.
