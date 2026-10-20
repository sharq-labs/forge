# Genesis-lite v0.3 D5-A1b deployment verification (2026-10-21)

**Verdict: BLOCKED (`verified: false`). D5 = NOT_PROVEN, N-1 = OPEN.** This is development-tier, non-formal
evidence. It is not a formal measurement, a validation result or a certification.

## What ran

- **Machine.** The D7 formal machine: the owner's hardened WSL Ubuntu-24.04 (interop and automount disabled),
  kernel 6.6.87.2, rootless Podman 4.9.3 with crun and cgroup v2.
- **Image.** `localhost/forge-card@sha256:89847920916e4636…`, id `2d2651e4d002…`. It was built from
  `benchmarks/genesis_lite/v0_3/container/Containerfile` (sha256 `9aaf37bd…`, byte-identical to the build file).
- **Source.** A fresh clean clone of `feat/genesis-lite-v03-clean-n1` at `c09b0ef5a0431eb9187b22faf8386166525926a6`
  in `/home/dev_kaeem/forge-n1-c09b0ef5`, transferred by git bundle with no network. The tree was clean before and
  after the run.
- **Command.** `command.json` records the exact argv, cwd, PYTHONPATH, exit code 1 and UTC times:
  `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2`, wall time 267.7 s.
  `stdout.txt` and `stderr.txt` (empty) are the raw streams.
- **Cleanup.** No card container was left afterwards (`podman ps -a --filter label=org.forge.genesis_lite.card`).

## Result (`result.json`, sha256 `5ccccd4202b2407cc8ea2e413afb86af5fb28a3939f051d5537be41c6d3561e3`)

**N-1 container evidence: BLOCKED.** The reasons are exactly `DEVICE_NODE_WRITABLE_MOUNT` and
`UNDECLARED_WRITABLE_MOUNT`, for the same six rows in each of cards A, B and C. Each is a host character device
that rootless crun binds read-write from devtmpfs:

- `/dev/null` 1:3
- `/dev/zero` 1:5
- `/dev/full` 1:7
- `/dev/tty` 5:0
- `/dev/random` 1:8
- `/dev/urandom` 1:9

The owner decided on 2026-10-21 that **no device-node exemption** applies, so these stay blocking.

Every other part of the contract held:

- **Inventory.** The raw, parsed and host-side runtime mount inventories reconcile. The only tolerated field is the
  cgroup2 root, which is namespace-relative.
- **Writable mounts.** The only other writable mounts are the four declared private tmpfs: `/tmp`, `/var/tmp`, `/run`
  and `/dev/shm`. The root, `/dev`, `/proc`, `/sys`, the source tree and the venv are read-only.
- **Canaries.** Card A wrote and read back a fresh 256-bit token on each private mount, attributed to that mount by fd
  `mnt_id`. Fresh cards B and C found every token READ_ABSENT at the identical path.
- **Positive controls.**
  - The deliberately shared volume: token written by container A was READ_OK in container B.
  - The host listener: REACHED from the host and REFUSED from every card.
- **Card containers.**
  - Containers: three distinct ids, each removed after its card; restart refused (exit 125).
  - Privileges: the pinned image, every capability set 0, NoNewPrivs 1, private IPC, only `lo`.
  - Read-only: source and venv writes failed with EROFS.

**Twelve attack channels.** Each ran on two cards per configuration.

- In the D5-A1b containers, 11 channels were REFUSED.
- `cross_card_state` is UNTESTABLE: since N-1 it is refused only on container evidence that passes.
- Every probe showed power: REACHED without containers or in the capability-keeping control containers. unmask and
  remount_rw were reached only in the control containers.

## Status this evidence supports

- D5-A1b is implemented and runs. It is BLOCKED solely by the six writable host device nodes. Under the strict owner
  rule, this rootless runtime cannot pass. Passing needs a runtime without them, or a later owner decision.
- The readiness gate derives the D5 rows from this pinned file (`readiness.deployment_status`). They stay
  `BLOCKED_WITH_EVIDENCE_NOT_PROVEN`.
- The historical A1 evidence (`../genesis_lite_v0_3_d5_deployment_2026_10_20`, sha256 `519f3669…`) is unchanged and
  is HISTORICAL_ONLY.
