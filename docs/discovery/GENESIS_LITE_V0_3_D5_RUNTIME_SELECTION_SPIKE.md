---
ai_schema_version: 1
doc_id: FORGE-GENESIS-LITE-V0-3-D5-RUNTIME-SELECTION-SPIKE
doc_kind: AUDIT_HANDOFF
doc_status: PROPOSED
authority_scope: NONE
source_ref: feat/genesis-lite-v03-clean-n1
evidence_level: NOT_EVIDENCE
last_reviewed: 2026-10-21
supersedes: none
---

# Genesis-lite v0.3 D5: replacement runtime selection spike (BR-D5-RUNTIME-01)

> **This document implements nothing and pins nothing.** It reports a bounded spike on the formal machine, run from
> `839af190`. It used synthetic no-op cards only: no Genesis roots, worlds or formal state. Its probe evidence lives
> outside the repository in `D:\forge-d5-runtime-spike\` (manifest `SHA256SUMS`, sha256 `e92f0efa…`). The spike
> results are MEASURED in the spike only. They are not D5 evidence: they are unpinned, the detector is not declared in
> `readiness.BOUNDARY_FINDINGS`, and the D5 contract was not rerun. D5 = NOT_PROVEN, N-1 = OPEN, D7 =
> REQUIRES_RERUN. The comparison follows the [handoff](GENESIS_LITE_V0_3_D5_RUNTIME_BOUNDARY_HANDOFF.md) section 4.

## 1. Result

**SELECT_RUNTIME_FOR_D5_IMPLEMENTATION: family 3a, a rootful OCI runtime (crun 1.14.1) with one fresh container per
card. The launcher builds each card's private device tmpfs. It runs inside the formal machine's WSL2 VM.**

Task status: **RUNTIME_SELECTED_FOR_IMPLEMENTATION.** The 72-hour budget does not need to change.

## 2. The detector used here (BLOCKER 1's mechanism)

PROGRESS describes BLOCKER 1 this way: a card can change the shared host nodes' persistent metadata without opening
them, and a later card can see the change. The confirming test changed the host nodes' timestamps.

- **Encoder card.** For bit 1 it calls `utimensat(UTIME_NOW)` on all six paths. For bit 0 it does nothing.
- **Decoder card.** A fresh card that reports `stat` for the six paths.
- **Rule.** The operator guesses 1 when the decoder sees `max(mtime, ctime)` inside the encoder's window
  `[t_a, t_b − 10 ms)`. Giving the decoder the exact window favours the attacker.
- **Guard band.** The 10 ms guard band was set after the first 8-trial run. In that run, timestamps from tmpfs's coarse
  clock fell up to 5 ms before `t_b`, which gave bit-independent false 1s. The 24-trial runs below used the fixed rule.
- **Trials.** 24 trials, 12 at each bit, in a fixed order.

| Configuration | null | zero | full | random | urandom | tty |
|---|---|---|---|---|---|---|
| Closed runtime: rootless Podman 4.9.3, `FINAL_FLAGS` (positive control on the real mechanism) | RECOVERED 24/24 | RECOVERED 24/24 | RECOVERED 24/24 | RECOVERED 24/24 | RECOVERED 24/24 | RECOVERED 24/24 |
| 3a misconfigured: one device tmpfs shared rw by every card (in-runtime power control) | RECOVERED 24/24 | RECOVERED 24/24 | RECOVERED 24/24 | ABSENT | ABSENT | ABSENT |
| 3a candidate: fresh tmpfs per card, bound ro | not recovered (touch EROFS) | not recovered | not recovered | ABSENT (ENOENT) | ABSENT | ABSENT |
| 3a candidate, bound rw (privacy without relying on ro) | not recovered (touch OK) | not recovered | not recovered | ABSENT | ABSENT | ABSENT |

- **Candidate rows.** The decoder's guess was 0 in all 24 trials, at both bit values. Its node stamps fell within
  −5.1 to +2.0 ms of its own launch, whatever the encoder did: the node is created fresh for each card.
- **The closed runtime.** This is the first selected-message recovery through BLOCKER 1's mechanism. It is spike
  evidence, unpinned, and it does not change the decision record's evidence taxonomy (section 10.1).
- **Scope limit.** The detector covers the timestamp mechanism as PROGRESS describes it. The review's own mechanism
  text is not in the tree. If that text names a further metadata channel, the detector must cover it (stop condition
  S7).

## 3. Isolation census of a candidate card (3 cards ro, 1 card rw, MEASURED in the spike)

- **`/dev` view.** It holds exactly `full`, `null`, `zero` and `shm`. The three nodes are 1:7, 1:3 and 1:5, mode
  0666, on the card's own tmpfs, not on the host devtmpfs (host `st_dev` 5).
- **The three blocked nodes.** random, urandom and tty are ENOENT, both to open and to `utimensat`.
- **Device semantics.** null writes 64 bytes and reads 0. zero reads zeros. full returns ENOSPC.
- **Aliases.** No mount point in the card is a character device or devtmpfs. The control is the first smoke run
  (kept as `superseded_smoke_full_ro_hostmask.json`). With crun's own `maskedPaths`, `/proc/kcore`, `/proc/keys`,
  `/proc/latency_stats` and `/proc/timer_list` were read-only binds of the **host** `/dev/null` (devtmpfs 5:4). That
  is a reachable alias of a BLOCKER-1 node. The closed Podman runtime shows the same four aliases. The candidate
  masks files with an empty file from the card's own tmpfs instead.
- **Process.** uid and gid are 1000 inside a fresh user namespace (host 101000). The capability sets are empty,
  `NoNewPrivs` is 1 and `Seccomp` is 2 (Podman's default profile, reduced to OCI form). The card is PID 1
  (`NSpid ["1"]`), sees only PID 1, and has its own pid, mnt, net, ipc, uts, cgroup and user namespaces, all distinct
  from the host's.
- **Terminal.** No fd 0–2 is a tty, `/dev/tty` is absent and the card is its own session leader.
- **State.** The rootfs and `/dev` are read-only (EROFS). `/tmp` is a private tmpfs. A mark left by one card was
  never visible to the next. `mknod` returns EPERM.
- **Cleanup.** After every batch (1,601 timed cards (warm-ups included) plus every probe card): 0 leftover mounts, card directories, crun
  containers, card cgroups or processes at host uid ≥ 100000. Per-card cleanup failures: 0 of 1,601.

## 4. Comparison

Overhead is the per-card launch-to-cleanup wall time of a no-op card, minus the median bare host exec of the same
payload. The cards were launched one after another; concurrency was not measured. Each row ran 50 warm-up launches
first.

| Runtime family | Availability | Device isolation | State isolation | Median start | P95 start | Budget fit | Setup cost | Open assumptions | Decision |
|---|---|---|---|---:|---:|---|---|---|---|
| Closed: rootless Podman per card (reference) | AVAILABLE_NOW | **FAILS**: all six host nodes recovered 24/24 | Per container, except the six host nodes and four mask aliases | 0.133 s (n=200) | 0.155 s | Fits on time (+12.4 h at p95) | none | none needed | Remains BLOCKED_BY_D5_DEVICE_BOUNDARY |
| 1. Disposable VM per card | Hyper-V: AVAILABLE_WITH_BOUNDED_SETUP (needs elevation; `Get-VM` denied). QEMU/KVM full VM: not installed | Expected per guest kernel. NOT SHOWN | Expected. NOT SHOWN | NOT MEASURED (no guest) | NOT MEASURED | Unknown: a full boot per card | High | Boot cost; a WSL launcher cannot drive Hyper-V (interop disabled); hypervisor shares | **REJECT for this formal machine** (Hyper-V path needs undeclared host interaction). QEMU path not probed, and dominated by 3a |
| 2. MicroVM per card | AVAILABLE_WITH_BOUNDED_SETUP: `/dev/kvm` present, nested=Y, kvm_intel loaded; Firecracker, cloud-hypervisor, QEMU and Kata absent (downloads) | Expected. NOT SHOWN | Expected. NOT SHOWN | Floor only: 0.028 s for a bare KVM VM create+run(hlt)+destroy (n=1000), not a boot | Floor 0.040 s (worst 0.049 s) | Floor fits; guest boot NOT MEASURED | High | Guest boot cost under nested KVM; VMM device model; kvm group or root | **Not selected.** Fallback if the owner rejects a root launcher or requires separate kernels |
| 3a. Rootful OCI runtime (crun) per card, in the formal WSL2 VM | AVAILABLE_NOW | **Each node controlled independently**: null/zero/full private per card (not recovered, ro or rw); random/urandom/tty ABSENT; no host-node alias; detector power shown in-runtime | Fresh namespaces, tmpfs and container per card; 0 residue in 1,601 timed cards | 0.011 s `/bin/true` (n=1000); 0.0065 s `python3 -I -c pass` (n=500); cold 0.013 s | 0.012 s / 0.0078 s (worst 0.024 s / 0.011 s) | **Fits**: +1.0 h at p95 against 43.5 h of headroom (0.54 s/card), or 26.8 h against the Podman-pilot reference (0.34 s/card) | Moderate | Shared WSL2 kernel (the D5 attack channels must be rerun); root launcher; concurrency; rootfs tree identity; detector scope (S7) | **SELECT** |
| 3b. As 3a, inside a dedicated disposable VM | AVAILABLE_WITH_BOUNDED_SETUP (needs family 1 or 2 machinery) | Same as 3a | Same as 3a per card; adds attempt-level and operator isolation | 3a + one VM per attempt, NOT MEASURED | NOT MEASURED | Expected to fit | High | As 3a, plus the VM machinery | Not needed by any hard condition. It composes with 3a later if the owner wants operator isolation |
| 4. Blindfold OS isolation (`engcore.blindfold.isolation`) | AVAILABLE_NOW in code; root launcher; not run here | **Fails by construction**: `unshare` with no `/dev` mount (source lines 144–148) leaves the host devtmpfs nodes, the nodes shown above to carry the channel | Per uid and namespace, not card versus card | NOT MEASURED | NOT MEASURED | n/a | Low, plus OD-3 | n/a | **REJECT** (shares the unresolved D5 state) |

## 5. Why 3a closes the finding rather than hiding it

- **What carried the channel.** BLOCKER 1's channel is persistent metadata on an inode shared by all cards: the host
  devtmpfs nodes. Under 3a no card can reach any host device inode. Each admitted node is a new inode on a tmpfs
  created for that card and destroyed with it. The alias walk finds no host node reachable, masks included. The
  three nodes section 9 requires to be inaccessible are absent, not masked.
- **Privacy does not rest on read-only.** The same result holds with the nodes writable (the rw row), so it does not
  rest on EROFS alone.
- **The detector has power.** The identical detector recovers 24/24 on the closed runtime and on a misconfigured 3a
  launcher. The candidate rows are a powered negative, not an untested one.
- **No policy is weakened.** This is exactly section 9's policy: null, zero and full admitted as STATELESS_DEVICE
  endpoints only if proven; random, urandom and tty inaccessible; nothing else writable.

## 6. Minimum implementation scope (not done here)

1. **Launcher.** Add the launcher in `benchmarks/genesis_lite/v0_3/isolation.py` under a new `DEPLOYMENT` name; the
   old one stays as history. It covers:
   - the OCI spec builder;
   - one tmpfs per card, made private, holding mknod'd null, zero and full plus an empty mask file;
   - `/dev` bound ro, nosuid, noexec;
   - **no crun `maskedPaths` for files**;
   - `rootfsPropagation: rprivate`;
   - user-namespace mapping, empty capability sets and no_new_privs;
   - the pinned seccomp profile;
   - a device cgroup allowing only 1:3, 1:5 and 1:7;
   - read-only rootfs;
   - per-card cleanup with residue checks.
2. **`container_evidence.py`.** A re-derived mount allowlist and spec-field checks in place of `REQUIRED_FLAGS`.
3. **`device_contract.py`.** The node shape is re-derived:
   - a card-private tmpfs node, never on the host devtmpfs;
   - ctime inside the card's own launch window;
   - random, urandom and tty must be ABSENT.

   **Identity must not use `st_dev`/`st_ino` equality across cards.** Sequential cards measurably reuse the same
   anonymous device number and inode numbers.
4. **`container_probe.py`.** Add the character-device mount walk (partly addresses MAJOR 1) and the timestamp
   encoder and decoder.
5. **`readiness.py`.** Declare the detector in `BOUNDARY_FINDINGS`, with the required re-derivation test from raw
   records (decision record 10.3). This is a reviewed change to a preregistration-pinned file.
6. **`formal.deployment_problems` pre-admission identity.**
   - crun version and binary digest;
   - kernel release;
   - image digest, plus a digest of the exported rootfs tree (the spike's export tar sha256 `7d1ab3c8…` is one
     instance, not a pin);
   - seccomp profile digest;
   - the declared root launch (`wsl.exe -u root`, or an equivalent stated operator action).
7. **Reused unchanged.** The Containerfile and image.

**Tests and positive controls required:**

- Detector power: the shared-tmpfs launcher recovers the bit, and the closed runtime recovers on all six nodes
  (historical control).
- The candidate is PRIVATE_TO_CARD for null, zero and full and ABSENT for random, urandom and tty, re-derived from raw
  records.
- The alias walk detects a crun file mask built from the host `/dev/null`.
- The propagation control detects a leaked host mount when make-private is omitted.
- Zero residue after N cards.
- Rerun the twelve attack channels, the Card-A/B/C canaries, the shared-volume, host-listener, host-procfs and
  terminal controls, and pre-admission verification on the new runtime.
- The readiness tests for the closure.

## 7. Stop conditions

- **S1.** Any host devtmpfs node or alias is reachable in a card's view.
- **S2.** A power control fails to recover (no power).
- **S3.** Any candidate node is recovered, or any blocked node is present.
- **S4.** Any residue after any card.
- **S5.** crun, kernel, rootfs or seccomp identity drifts from the pins.
- **S6.** The root launch needs anything beyond the declared operator action.
- **S7.** BLOCKER 1's original review text names a mechanism the detector does not cover.
- **S8.** Any of the twelve attack channels is not REFUSED on the new runtime.
- **S9.** With the formal worker count, the D7 rerun's p95 per-card overhead exceeds 0.34 s.

## 8. Not run

Not run: D5, D7, the D5 contract, the attack channels, the repository test suite, freeze, certification, formal runs
and Budget × Noise. Nothing was pushed or installed.

Spike side effects on the formal machine:

- The reference trials touched the six host `/dev` nodes' timestamps, as the earlier confirmation did. This is
  harmless and resets on restart.
- Every spike directory, mount and cgroup was removed and checked absent afterwards.
- One command mis-quoted through `wsl.exe` and created `/rootfs`, `/scripts` and `/kvm_floor` at the WSL root. They
  were identified by timestamp and removed.
