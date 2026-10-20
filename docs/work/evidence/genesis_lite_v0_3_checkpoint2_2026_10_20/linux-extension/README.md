# Checkpoint 2 extension — failing-first isolation specifications

Date: 2026-10-20 (Africa/Cairo). Parent review pending.
Production HEAD: `1cb5e187ef46ba2735fa292112a5e2bfd2334007`.
Final result: **40 failed, 9 passed, no skips/errors, exit 1, 2.22 s**.
This is a red test baseline, not deployment acceptance.

## Execution and provenance

Dedicated Linux Git checkout:
`/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo`.
It was created with `git clone --shared --no-checkout /home/dev_kaeem/forge`,
then fetched a local incremental bundle and checked out the exact PR SHA detached.
The bundle was created on Windows with:
`git bundle create D:/gl03tmp/cp2-transfer.bundle HEAD ^d6773060fea04f97f3027d9e33a0df7a5413d64e`.
Binary transfer used Python subprocess stdin to WSL, with automount unchanged.
The initial dedicated checkout was clean; only the three test files were then copied.
The clone borrows objects from the existing Linux repository; retain that repository
while using this checkout. No tracked file there was modified; its HEAD remains
`f7df896836b62e7bc96f2eaee28883d655cb4e3a`.

Exact command and environment are machine-readable in `command.json`:

```bash
cd /home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/repo
export PYTHONPATH="$PWD/src:$PWD"
export TMPDIR=/tmp
export FORGE_CHECKPOINT_SOURCE_SHA=1cb5e187ef46ba2735fa292112a5e2bfd2334007
export FORGE_CHECKPOINT_EVIDENCE=/home/dev_kaeem/forge-cp2-1cb5e187-ozVlV6/evidence
/home/dev_kaeem/venvs/forge312/bin/python -m pytest \
  tests/genesis_lite/test_genesis_lite_v0_3_container_isolation.py \
  tests/genesis_lite/test_genesis_lite_v0_3_container_runtime.py \
  -q -p no:cacheprovider --basetemp=/tmp/forge-cp2-ozVlV6-final -rA --tb=short
```

Runtime: existing CPython 3.12.3 venv, rootless Podman 4.9.3 on the existing
Ubuntu-24.04 distro. No install, image build or security change.
Image digest read from both image inspection and each actual container inspection:
`sha256:89847920916e46363fe52f7cecc3a2b937d34d6b355dd3e8cc14527fe65a8261`.
Image ID: `2d2651e4d002c518bb669cb044209897ff02e33318a4b92ac185cf23be33f532`.
The test also checks rootless status and actual Git HEAD; caller environment
values alone are not accepted as source/image identity.

`runtime.json` preserves exact create/start argv, inspections, container IDs,
stdout/stderr, restart refusals, raw and parsed mountinfo, canary observations,
kernel status, network results, and source/test/launcher/probe/Containerfile
digests. Five successful development test containers were removed automatically;
all five subsequent attempts to start those IDs were refused. A deliberately
wrong, absent image digest was refused with `--pull=never`. No remaining
containers were listed at close.

## Coverage and interpretation

| Requirement | Executed coverage | Limit |
|---|---|---|
| Explicit container flags, no shell | Original command-contract assertions remain red | Current production still uses namespaces/shell |
| Full mountinfo inventory | 36 real entries retained, unique IDs and declared runtime mounts reconciled | Test-only parser; production validator absent |
| Host/Windows/shared/undeclared writable rejection | Named mutation specifications against a complete admissible synthetic baseline; real shared-volume leak also supplied to current verifier | Windows backing and shared propagation are injected evidence, not observed real mounts |
| Unprobeable writable locations | Real `/dev`, `/proc`, `/dev/pts`, `/dev/mqueue` and six device endpoints recorded as UNPROBEABLE; verifier refusal assertion fails | No pseudo-filesystem exemption; this rig is not an admissible deployment |
| HOME/work/tmp/cache | Three fresh containers have private paths and no earlier environment canaries | Applies to test rig, not production launcher |
| Image binding/mismatch | Inspection IDs/digests match pinned image; absent wrong image refused by Podman; production identity assertion fails | A different valid image substitution is specified in validator mutation tests |
| Container reuse/restart | Five distinct full IDs; removed IDs cannot restart; repeated fresh B has no A canary | Production remains unimplemented; no resumed-container claim |
| Kernel restrictions | All five capability sets zero, NNP=1, only loopback, host/external connections fail; host listener reachable in positive control | Narrow measured targets, not proof against every network technique |
| Source/venv read-only | Actual open-for-write refusal plus inspection/mount flags | No writes made to source or venv |
| A/B all-mount canaries | Every writable mount recorded; writes attempted only on directory-backed safe filesystem types; all other entries fail closed as unprobeable | Cannot claim successful canaries on unprobeable mounts |
| Shared-volume positive control | A writes cryptographic token to actual host bind at `/shared`; fresh B reads it | This is now a real Podman bind-volume control |
| Pre-admission refusal | Existing test executes real checker with successful tool discovery and injected runtime denial; synthetic registry wrongly consumed | Empty world plan, synthetic root only; no real formal admission |

The tests use a **test-only Podman rig**, not a production replacement.
Its `create`/`start` sequence permits inspection before automatic removal;
it is not the required future production `podman run` implementation.

The proposed validation API is explicitly documented by
`admissible_contract_evidence` and `validator_contract` in the runtime test file:
`isolation.validate_container_evidence(report, expected=...)` must accept one
complete admissible synthetic baseline and reject independent mutations with
named reason codes. **21 assertions currently fail with
MISSING_VALIDATION_CONTRACT** (one positive baseline plus twenty negative
specifications), rather than import/attribute errors. An always-reject validator
cannot pass the positive baseline. These 21 are absent-contract failures, not
twenty-one separately reproduced security exploits.

The other **19 failures** are assertions against current behavior: sixteen
original regressions, two real unsafe-evidence acceptance cases and absent
production image binding. The **9 passes** comprise four original controls and
five runtime fixture/control tests. No production security closure is claimed.

## Failed fixture approaches retained

- `pytest-initial.txt`, `runtime-initial.json`: 17 failures, 5 passes, 19 setup
  errors. `--rm` deleted the CID file before the test read it.
- `pytest-cid-error.txt`: same counts; `/run/.containerenv` was empty, so it
  could not recover the ID. Replaced with pre-start inspection of created IDs.
- One orchestration command had a Python string-escaping SyntaxError and did
  not run pytest.
- `pytest-pre-review.txt`: 33 failures, 8 passes, no setup errors. Its mutation
  tests started from already-unsafe real evidence; parent review correctly
  required a separate admissible baseline and specific rejection reasons.
- `pytest.txt`: final consolidated run after those fixture/test corrections.

`tests-consolidated.patch` includes all three added test files.
`production-preservation.json` binds unchanged production bytes.
`git diff --exit-code HEAD -- benchmarks src` passed on both checkouts;
no production or preregistration edits, commits, push, merge, freeze, formal
campaign, OS security changes or dependency installs occurred.

Stop: **BLOCKED_WITH_PRECISE_EVIDENCE; checkpoint 2 ready for review**.
Checkpoint 3 implementation requires the next review instruction.
