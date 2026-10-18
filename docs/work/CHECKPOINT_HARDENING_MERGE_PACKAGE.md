# PR package: harden checkpoint integrity and fail-closed recovery

Status: IMPLEMENTED / UNVERIFIED / UNCERTIFIED. No physical validation claim.
Base: `0284ae161ad957d51674ee481e47cfd43d10c5f0`.
Branch: `codex/checkpoint-integrity-hardening`.

## Proposed PR title

fix: harden checkpoint payload integrity, recovery retirement and time admission

## Proposed PR body

Opaque external snapshots could restore changed payloads under a stored state digest.
Failed sequential restoration could also leave mixed participant state reusable, and
legacy orchestration references could continue without build/problem bindings.

Require a versioned provider codec that reads complete continuation bytes and verifies
referenced content; Forge computes and rechecks its fingerprint. Keep CheckpointSeal's
strict same-participant issuance, record and state identity. Refuse and retire corrupt or
unreadable issued payloads, preserving original failure causes. Separate safe admission
from callback restore application, retire failed applications, and track failed custom
participant objects across runtimes. Bind PyBaMM continuation to physical time and its
committed live-state fingerprint. Require build/problem identity for orchestration resume
and conversion, and refuse observable within-call build drift before accepting results.

Compatibility: serialized record schemas and existing state/build digests are preserved.
Legacy readability does not authorize continuation. Missing identity needs producer-backed
migration or an explicit cold start. Native declaration-only callbacks remain labelled;
they never establish observed provider-build identity. External providers must implement
the integrity codec, including when a token is bytes. PyBaMM physical origins other than
zero are explicitly refused. No cross-process recovery is enabled.

Validation: NOT RUN by owner Build-First policy. Adversarial tests are written; only
compile-only source inspection and `git diff --check` are permitted. Execution recipes are
DV-101..DV-106, following DV-100 and DV-99. Static review is not test execution.
Changed certified/SCOPE files require separately authorized final-source OD-3 work;
certificates, snapshots, evidence and acceptance thresholds are not regenerated here.

## Merge requirements

- Independent scientific/compatibility review: PASS (static only), recorded in CHECKPOINT_HARDENING_REVIEW.md.
- Separately authorized deferred tests and relevant consumer/API gates, with exact results.
- Normal repository classification/gates and separately authorized OD-3 as applicable.
- Resolve the supplied automatic-CI policy versus historical local-only handoff policy with
  the owner; this patch changes no workflow or branch protection.
- No automatic merge. No PR is opened or branch pushed by this package, avoiding an
  accidental test/assurance campaign before execution authorization.

## Remaining limits

- Codec completeness and accurate provider/build declarations require provider-specific
  qualification. A hash cannot authenticate an incomplete or malicious encoder.
- Retirement is process-local, not a durable issuance or recovery system. Nonweakrefable
  retired custom participants are strongly retained until process exit.
- Raw sessions/custom callbacks invoked outside Forge wrappers cannot be policed here.
- PyBaMM completeness remains declared; its numerical behavior and roundoff-only endpoint
  policy need real-provider execution. Zero-origin operation is the bounded supported scope.
- No capability, maturity stage, validation level or certification is promoted.

## Next bounded tasks

First: a read-only Core semantic compatibility proposal for A-1/A-2/A-13 together:
quantity meaning and port roles, transported versus stored quantity, generalized losses/
conversion, mechanical effort-flow meaning, fail-closed legacy admission and schema/digest
impact. Use nonthermal adversarial examples; reuse existing scientific records. Do not
replace the energy guard with an unreviewed prose bypass or a new evidence vocabulary.

Then: an A-3 declared-field-kind compatibility slice (density, integrated amount, intensive),
with dimension-generic overlap rules and vector semantics. Specify analytical unequal-cell
counterexamples and separate transfer conservation diagnostics from error bounds. M1 may
use a locally declared kind; shared FieldMapper changes and M2 acceptance need Core review.
These are recommendations, not authorization to expand this repair.

## Exact changed-file inventory

- `docs/work/ACTIVE_PLAN.md`
- `docs/work/CHECKPOINT_HARDENING.md`
- `docs/work/CHECKPOINT_HARDENING_MERGE_PACKAGE.md`
- `docs/work/CHECKPOINT_HARDENING_REVIEW.md`
- `docs/work/DEFERRED_VALIDATION.md`
- `docs/work/PROGRESS.md`
- `providers/pybamm/forge_pybamm/coupling.py`
- `providers/pybamm/tests/test_pybamm_checkpoint_identity.py`
- `src/engcore/coupling/adapters.py`
- `src/engcore/execution/multiphysics/external.py`
- `src/engcore/execution/multiphysics/participant.py`
- `src/engcore/execution/multiphysics/runtime.py`
- `src/engcore/execution/orchestration/advanced_runner.py`
- `src/engcore/execution/orchestration/checkpoint.py`
- `src/engcore/execution/orchestration/runner.py`
- `tests/execution/orchestration/test_checkpoint_required_identity.py`
- `tests/execution/orchestration/test_checkpoint_routing.py`
- `tests/execution/orchestration/test_phase2_checkpoint_recovery.py`
- `tests/test_checkpoint_integrity_hardening.py`
- `tests/test_external_participant_checkpoints.py`
- `tests/test_system_runtime_external_providers.py`
