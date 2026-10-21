# Genesis-lite v0.3 D5-A1b deployment verification under STATELESS_DEVICE (2026-10-21)

**Verdict: VERIFIED (`verified: true`).** The container evidence PASSES, all 12 attack channels are REFUSED, and every
probe has power. This is development-tier, non-formal evidence. It is not a formal measurement, a validation result or
a certification. D5 rows follow it through `readiness.deployment_status()`.

## Files

| File | What it records |
|---|---|
| `result.json` | The verification output (sha256 `b3bc0b6447b1fe46d3cf613692eeea95f0a8b50678106b680a7a224f8fe5ac84`, pinned in the preregistration as `DEPLOYMENT_EVIDENCE`). |
| `command.json` | The exact argv, cwd, PYTHONPATH, exit code (0) and UTC start and end times. |
| `run_checks.json` | The tree was clean before and after (the run script refused a dirty tree). 0 containers, 0 pods and 0 volumes existed before and after, and 0 card-labelled containers were left. Also the Podman version, the kernel and the image digest and id as Podman reports them. |
| `stdout.txt`, `stderr.txt` | The raw streams (stderr is empty). |
| `superseded-*/` | Earlier D5-A1b runs, kept as history: `c09b0ef5`, `754f6cdb`, `d4ead0b2`, `ad55b7c5` and `12baeb04` (sha256 `967f089e…`). All were BLOCKED by the six host device nodes under the strict rule that this run's owner policy replaced. Evidence about other code is not evidence about this code. |

## What ran

- **Machine.** The D7 formal machine: the owner's hardened WSL Ubuntu-24.04 with kernel
  `6.6.87.2-microsoft-standard-WSL2`, rootless Podman 4.9.3 (crun, cgroup v2).
- **Source.** A fresh clone of `feat/genesis-lite-v03-clean-n1` at `2e2a9d1bee393df925dcc4b6c8c297aa8b2fdd51`, made
  from a git bundle with no network. Provenance records `tree_clean: true` and the sha256 of every file that ran,
  `device_contract.py` included.
- **Image.** `localhost/forge-card@sha256:89847920916e4636…`, id `2d2651e4d002…`. Podman reported both, and they
  match the expected deployment. As before, the Containerfile is the build file found on the machine, not a
  reproducible recipe.
- **Command.** `python -m benchmarks.genesis_lite.v0_3.isolation --out result.json --cards 2`. Wall time 278.5 s.

## Result

**Devices, each under `forge.genesis_lite.v0_3/stateless_device/1`:**

| Device | Major:minor | Verdict |
|---|---|---|
| `/dev/null` | 1:3 | ADMITTED |
| `/dev/zero` | 1:5 | ADMITTED |
| `/dev/full` | 1:7 | ADMITTED |
| `/dev/random` | 1:8 | ADMITTED |
| `/dev/urandom` | 1:9 | ADMITTED |
| `/dev/tty` | 5:0 | ADMITTED |

No device was masked. Each verdict comes from its own evidence, in each of the 11 fresh, distinct containers whose
evidence was assessed: cards A, B and C, and four more encoder/decoder pairs.

- **Identity.** In every card:
  - each device has exactly one mount: a private nosuid,noexec bind of the operator's own devtmpfs (0:5) node
    `/<name>`, under the card's read-only `/dev`;
  - in the card it is a character device with the exact major:minor and mode 0666, owned by the overflow id 65534
    (host root is not mapped);
  - its device and inode are the host node's, and its mount id is that row's.
- **No state.** The node metadata (size, link count, atime, mtime and ctime) is identical in every card and on the host,
  before and after card A wrote.
- **Semantics.**
  - `null` takes writes and reads EOF.
  - `zero` takes writes and reads zeros.
  - `full` refuses writes (ENOSPC) and reads zeros.
  - `random` and `urandom` take unprivileged writes and refuse every state-setting ioctl with EPERM. The readable
    counters (entropy_avail, poolsize and RNDGETENTCNT, all 256) are the same in all 11 cards.
- **No cross-card channel.** There were five selected-message trials with bits 1, 0, 1, 0, 1. In each, a fresh
  decoder read 1 MiB from every device and found no 8-byte window of either message.
- **Positive controls.**
  - Through a deliberately shared file, the same encoder and decoder recovered both bits. The metadata comparison saw
    the file change.
  - A container given a terminal was told apart: `/dev/tty` opened, and it had terminals on stdin, stdout and stderr and
    a `/dev/pts`.
- **TTY.** Every formal card was launched without `--tty`. In every card:
  - opening `/dev/tty` gave ENXIO;
  - tty_nr is 0, tpgid is -1, and the card is its own session leader;
  - stdin, stdout and stderr are pipes, with no other descriptor besides the inventory's own listing;
  - there is no `/dev/pts`, and `/dev/ptmx` is dangling (ENOENT).
- **Aliases.**
  - The card's `/dev` holds exactly the six devices, Podman's six symlinks with their exact targets, and the private
    `/dev/shm`.
  - The only other devtmpfs rows are Podman's read-only masks: `/proc/kcore`, `/proc/keys`, `/proc/latency_stats` and
    `/proc/timer_list`. Each is `/dev/null` itself (same device and inode).
  - A walk of the 21,268 entries a card can traverse outside `/proc`, `/sys` and `/dev` found no device node and no
    symlink to a device. Three directories were unreadable to the card, so it cannot traverse them either.
- **Randomness screen.** 42 Genesis-lite and blindfold files at the expected source revision, 0 problems.

**Everything else in N-1 held as before:**
- The inventories reconcile.
- The only other writable mounts are the four declared private tmpfs.
- The read-only allowlist holds.
- The canaries were planted by A and ABSENT in B and C.
- The shared-volume and network controls work.
- Each card is PID 1 with NSpid `["1"]`, on devices other than the operator's procfs (0:59) and sysfs (0:22). The
  host-procfs control showed NSpid `["31573","1"]` and 33 processes.
- Capabilities are 0, NoNewPrivs is 1, IPC is private, the only interface is `lo`, the containers were removed, and
  restart was refused.

**Twelve attack channels.** All 12 were REFUSED in the D5-A1b containers, including `cross_card_state`, which is
refused only on passing container evidence. Every probe showed power: each channel was REACHED without containers or
in the capability-keeping control containers.

## What this does not claim

- The cards do not receive independent physical entropy. `/dev/random`, `/dev/urandom` and `getrandom(2)` are one
  shared kernel CRNG. The claim is only that a card can neither set nor read its state through them.
- The randomness screen is static: dynamic attribute access is not followed. Python's per-process hash randomisation
  and operational identifiers (query ids, container names) use `getrandom(2)`. None of them is a scientific seed, but
  this is a declared residual, not a proof.
- The containers share the host kernel and, on WSL, the utility VM. The other residuals of D5-A1b are unchanged.
