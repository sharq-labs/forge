# Genesis-lite v0.3 D5-A1b deployment verification (2026-10-21)

**Verdict: BLOCKED (`verified: false`). D5 = NOT_PROVEN, N-1 = OPEN.** This is development-tier, non-formal
evidence. It is not a formal measurement, a validation result or a certification.

## Files

| File | What it records |
|---|---|
| `result.json` | The verification output (sha256 `967f089e26247ce8db2ef41b0039fdca0886e7f0ed40e648ad57d3d6e1995c5d`, pinned in the preregistration as `DEPLOYMENT_EVIDENCE`). |
| `command.json` | The exact argv, cwd, PYTHONPATH, exit code (1) and UTC start/end times. |
| `run_checks.json` | The clean tree before and after (the run script refused a dirty tree before starting), and 0 leftover card containers (`podman ps -a --filter label=org.forge.genesis_lite.card`). |
| `stdout.txt`, `stderr.txt` | The raw streams (stderr is empty). |
| `superseded-c09b0ef5/`, `superseded-754f6cdb/`, `superseded-d4ead0b2/`, `superseded-ad55b7c5/` | Earlier D5-A1b runs at `c09b0ef5` (sha256 `5ccccd42…`), `754f6cdb` (`590bfa4f…`), `d4ead0b2` (`29c72411…`) and `ad55b7c5` (`a9bc4c64…`), with the same verdict. They are kept as history. Each was superseded because a read-only review pass changed the probe or validator. In order: MAJOR-1 (read-only host paths, now an allowlist that ignores the backing label); the third-pass MINORs (device, root and size ties for Podman's own mounts; one bind per kept target); then MINOR-A (`/proc` and `/sys` must be the card's own). Evidence about other code is not evidence about this code. |

## What ran

- **Machine.** The D7 formal machine: the owner's hardened WSL Ubuntu-24.04, kernel 6.6.87.2, rootless Podman 4.9.3
  with crun and cgroup v2. These are recorded in `result.json` provenance and in the expected deployment.
- **Source.** A fresh clone of `feat/genesis-lite-v03-clean-n1` at `12baeb0413228a6755d9d467f1392c0cbf61a843`, made
  from a git bundle with no network. `result.json` provenance records `tree_clean: true` and the sha256 of every file
  that ran.
- **Image.** `localhost/forge-card@sha256:89847920916e4636…`, id `2d2651e4d002…`. Its identity rests on that digest and
  id, which `result.json` checks against what Podman reports. The committed `container/Containerfile` is the build file
  found on the machine, byte for byte (sha256 `9aaf37bd…`). It is not a reproducible build recipe: the base image is
  pulled by tag and `apt-get update` is not pinned.
- **Command.** `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2`, wall time 277.4 s.

## Result

**N-1 container evidence: BLOCKED.** The reasons are exactly `DEVICE_NODE_WRITABLE_MOUNT` and
`UNDECLARED_WRITABLE_MOUNT`, for the same six rows in each of cards A, B and C. Each is a host character device that
rootless crun binds read-write from devtmpfs:

- `/dev/null` 1:3
- `/dev/zero` 1:5
- `/dev/full` 1:7
- `/dev/tty` 5:0
- `/dev/random` 1:8
- `/dev/urandom` 1:9

The owner decided on 2026-10-21 that **no device-node exemption** applies, so these stay blocking.

Within the validator's checks, nothing else blocked:

- **Inventory.** The card's raw and parsed mount tables and the operator's host-side view reconcile. The only
  tolerated field is the cgroup2 root, which is namespace-relative.
- **Writable mounts.** Besides the devices, the only writable mounts are the four declared private tmpfs: `/tmp`,
  `/var/tmp`, `/run` and `/dev/shm`.
- **Read-only mounts.** Every one is on the allowlist, one row per target: the image root; the read-only `/dev` (a
  tmpfs on its own device); the card's own `/proc`, `/sys` and cgroup (root `/`) with Podman's default masks (empty
  `size=0k` tmpfs on their own device, or `/dev/null`) and read-only re-binds of the card's own procfs (same device);
  the source and venv each bound exactly once from exactly their host path; and Podman's userdata files of that
  container.
- **The card's own `/proc` and `/sys`.**
  - Through its `/proc`, each card is PID 1 with NSpid exactly `["1"]` and sees one process. Its PID namespace is
    not the operator's.
  - Its `/proc` (0:86 or 0:87) and `/sys` (0:85 or 0:88) are not on the operator's procfs (0:59) or sysfs (0:22).
  - Positive control: a container given the host procfs at `/hostproc` sees NSpid `["22858", "1"]` and 28
    processes through it, so a host procfs would be told apart.
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
  rule, this runtime and launcher cannot pass. Passing needs a runtime or launcher without them, or a later owner
  decision. No alternative launcher configuration was tested beyond `/dev` as a read-only tmpfs.
- The readiness gate derives the D5 rows from this pinned file (`readiness.deployment_status`). They stay
  `BLOCKED_WITH_EVIDENCE_NOT_PROVEN`.
- The historical A1 evidence (`../genesis_lite_v0_3_d5_deployment_2026_10_20`, sha256 `519f3669…`) is unchanged and
  is HISTORICAL_ONLY.
