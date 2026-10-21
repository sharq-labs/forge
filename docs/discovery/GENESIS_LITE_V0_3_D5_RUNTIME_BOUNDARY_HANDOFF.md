---
ai_schema_version: 1
doc_id: FORGE-GENESIS-LITE-V0-3-D5-RUNTIME-BOUNDARY-HANDOFF
doc_kind: AUDIT_HANDOFF
doc_status: PROPOSED
authority_scope: NONE
source_ref: feat/genesis-lite-v03-clean-n1
evidence_level: NOT_EVIDENCE
last_reviewed: 2026-10-21
supersedes: none
---

# Genesis-lite v0.3 D5: runtime-boundary handoff (owner-facing)

> **This document selects nothing and implements nothing.** It compares four boundary families so the owner can
> choose a replacement for the rootless Podman runtime. Nothing here is evidence. Every row below is a
> design-level expectation unless it is labelled MEASURED. The D5 contract and the device policy (decision record
> sections 8 and 9) are unchanged, and any replacement must meet them as written.

## 1. Why a replacement is needed

- **Owner decision, 2026-10-21: CHANGE_RUNTIME_BOUNDARY.**
- The current runtime is `rootless_podman_per_card`, with rootless Podman 4.9.3 on the owner's WSL2 Ubuntu-24.04.
  Its status is **BLOCKED_BY_D5_DEVICE_BOUNDARY**.
- The cause is review BLOCKER 1. Its evidence types are STATIC_REVIEW plus FORMAL_MACHINE_CONFIRMATION. It is
  NOT_MEASURED_BY_CURRENT_DETECTOR. Decision record section 10 has the evidence taxonomy.
- Its stated scope is all six writable device nodes. This handoff does not restate the mechanism.
- Status: D5 = NOT_PROVEN, N-1 = OPEN. D7 = REQUIRES_RERUN, and only once a replacement runtime is selected. No
  freeze, certification or formal campaign is permitted.
- The gate encodes this. `readiness.BOUNDARY_FINDINGS` keys the finding by finding and scope, not by runtime. So
  `readiness.deployment_status()` reports `D5_RUNTIME_BOUNDARY_NOT_PROVEN` on this runtime, on a renamed one and on
  any replacement. That holds until the pinned D5 evidence closes all six nodes with MEASURED results from a declared
  detector. None is declared yet.

## 2. What any replacement must show (unchanged acceptance)

A replacement must meet all of the following, unchanged in requirement. Clauses that name Podman mechanics are
re-derived for the replacement: the expected node shape, the launch arguments, the image pin and the mount
allowlist (decision record 10.4).

- the full D5-A1b container contract (decision record section 3);
- STATELESS_DEVICE with ADMIT_ONLY_PROVEN_STATELESS_SUBSET (sections 8 and 9);
- the twelve attack channels, each with power;
- Card-A/Card-B canaries;
- the shared-volume, host-listener and host-procfs positive controls;
- pre-admission verification.

On top of the current detector, it also needs **MEASURED** evidence that closes BLOCKER 1's scope, in the form
`readiness.BOUNDARY_FINDINGS` requires. A replacement whose documentation claims the six devices are private is still
NOT_PROVEN until that evidence exists.

## 3. Cost scale (arithmetic from pinned numbers)

- **Cards per formal run.** The grid holds 2,400 world sets × 20 registered arms × 6 cards per arm and world set,
  so one operator run is **288,000 card launches**. The world-set count is in the preregistration. The card count is
  a recorded structural count from the A1 pilot's `result.json` (HISTORICAL_ONLY). The evaluator's replay doubles
  the launches under the pilot's ASSUMED replay factor of 2.0 (`timing_pilot.REPLAY_FACTOR`).
- **Start cost.** Each extra second of per-card start cost adds **80 h to the operator run** (288,000 s), or 160 h
  with replay (assumed factor). ESTIMATED arithmetic.
- **Budget.** The baseline budget is 72 h for the operator run. The pinned D7 pilot (`3759ff33`, superseded A1
  runtime, HISTORICAL_ONLY) ESTIMATES 57.0 h with replay, so about 28.5 h for the operator run.
- **Headroom.** That leaves about 43.5 h, or roughly **0.54 s of extra start cost per card**, before the budget is
  exhausted. ESTIMATED arithmetic on historical numbers.
- **Second reference point.** PROGRESS records the reverted Podman pilot `6f6b1418` (HISTORICAL_ONLY). It MEASURED
  67.9 s per world set and ESTIMATED 45.2 h for the operator run.
  - That is about 0.21 s more per card than the A1 pilot. The two pilots ran on different distros and different
    code (`f7df8968` against `f8bf7ed7`), so the difference is not the runtime's alone.
  - It leaves only about 0.34 s per card of headroom ((72 − 45.2) h × 3,600 s/h / 288,000).
  - This is the closest reference for family 3.
- **Consequence.** Per-card start cost is the deciding overhead for every family below. No family's per-card start
  cost has been MEASURED on the formal machine.

## 4. Boundary families

| | 1. Disposable VM per card | 2. MicroVM / hardware-virtualized sandbox per card | 3. Privileged container runtime inside a dedicated disposable VM | 4. Existing repository boundary: certified Blindfold OS isolation (`engcore.blindfold.isolation`) |
|---|---|---|---|---|
| **Six devices independently controlled** | Expected: each card's guest kernel has its own device nodes, so no card shares a host node. NOT SHOWN. | Expected: the guest gets only the devices the VMM declares, and its own kernel nodes. NOT SHOWN. | Possible: a privileged runtime can give each container its own nodes instead of the six host binds. All cards still share the VM's one kernel. NOT SHOWN, and not known to close BLOCKER 1. | No: its Discovery side runs on the host kernel with the host's device nodes (separate uid and namespaces). Not assessed against BLOCKER 1. |
| **Writable state private per card** | Expected, if each card boots from a read-only base with a discarded overlay and no host share is writable. NOT SHOWN. | Expected, under the same conditions as family 1, with a smaller device and share surface. NOT SHOWN. | Per container, as today (the private tmpfs). State in the shared VM kernel is shared by all cards of an attempt. The VM bounds the operator, not card from card. | Per uid and namespace. Its verified level is OS_ISOLATION_BOUNDARY_VERIFIED, for Escrow versus Discovery, not card versus card. `CONTAINER_BOUNDARY_VERIFIED` and `HOST_BOUNDARY_VERIFIED` are NOT reached. |
| **Formal-machine evidence reproducible** | Only if the D7 machine can start VMs from the launcher. That needs nested virtualization inside WSL2 (NOT CHECKED), or a different formal machine, which reopens D7. | Needs KVM inside WSL2 (nested virtualization, NOT CHECKED), or a different machine (reopens D7). | Partly. The probes, validator and controls carry over. But "dedicated disposable VM" is not a WSL2 distro: all WSL2 distros share one utility VM and kernel. A real VM brings back family 1's machine question. | NOT CHECKED. It needs a root launcher (`isolation_support` refuses a non-root caller; separate uid via setpriv) and an escrow server per instance. Nothing shows it has run on the D7 machine. |
| **Setup cost** | High: guest image, VM orchestration and per-card lifecycle, plus a new launcher, probe transport and validator allowlist. | High: kernel and rootfs build, VMM integration, a new launcher and a new evidence transport. | Moderate: closest to the current code (Podman, `container_probe.py`, `container_evidence.py`). Adds a VM lifecycle and a privileged-mode allowlist. | Low to moderate: certified code exists. Reusing it for cards needs a certified-scope change (OD-3). |
| **Expected runtime overhead** | Largest: a full boot per card. A boot above about 0.54 s per card exhausts the 72 h budget at 288,000 launches (section 3). NOT MEASURED. | Lower than family 1. Vendor-reported boot times are not measurements on this machine. NOT MEASURED. | Near the current container cost per card, plus one VM per attempt. NOT MEASURED on this route. The reverted Podman pilot (section 3) is the closest historical reference. | NOT MEASURED. A1 is a different launcher (Genesis-lite's rootless `unshare` route). Its pinned pilot's MEASURED 42.8 s per world set (HISTORICAL_ONLY) is not this route's cost. |
| **Portability** | Hypervisor-specific. A Windows host gives Hyper-V; a Linux host gives KVM. | Linux with KVM only. | Wherever the chosen VM runs. The container half is Linux-portable. | Linux with namespaces and root. NOT CHECKED on the D7 machine. |
| **Remaining unproven assumptions** | That nothing shared by the hypervisor (shares, clock, entropy, console) carries card state. That boot cost fits the budget. That the D7 machine can host it. | The same as family 1, plus KVM availability in WSL2 and the VMM's device model. | That per-container nodes from a privileged runtime close BLOCKER 1's scope (not shown). That the one shared VM kernel carries no card-to-card state. That privilege inside the VM does not widen the card's reach. | That the host's six device nodes carry no card state (the same question BLOCKER 1 raises, unexamined for this route). A1, the closest existing route, was superseded because it never proved cross-card state privacy. |

## 5. What the owner would decide next

Each of these is a separate decision. None is taken here.

1. **Pick a family**, or ask for a bounded feasibility spike first. The cheapest first fact to establish is whether
   the D7 machine offers KVM inside WSL2. Without it, families 1 and 2 also reopen D7's machine choice.
2. **Decide whether D7's machine stays.** If not, the machine, the manifest and the timing pilot are all redone.
3. **Decide whether certified scope may change.** Family 4 needs this, through OD-3.

After a selection, the order is:

1. implement the launcher;
2. run the MEASURED BLOCKER 1-scope evidence plus the unchanged D5 contract;
3. pin D5;
4. rerun and pin D7;
5. resume D4.
