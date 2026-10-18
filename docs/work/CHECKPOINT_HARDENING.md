# Checkpoint integrity repair — R1–R5

Base: `0284ae161ad957d51674ee481e47cfd43d10c5f0`. Branch: `codex/checkpoint-integrity-hardening`.
Owner-authorized bounded repair, 2026-10-18. Build-First: IMPLEMENTED / UNVERIFIED;
no scientific validation, qualification or certification is conferred.

## Compatibility review: proposed admission contract

The owner requires strict same-participant issuance and fail-closed integrity/identity.
No cross-process restoration is added. CheckpointSeal's registry, identity and issued-record
checks remain authoritative. Existing serialized checkpoint records keep their fields and
schemas; legacy records remain readable but are not necessarily admissible for continuation.

R1: every token requires the session's versioned `snapshot_integrity_codec` and
`snapshot_integrity_bytes(snapshot)` hook. The hook must read the complete continuation
payload each time, resolve and verify any content-addressed references, and return immutable
canonical bytes, never a cached digest. Forge hashes those bytes. The codec is provider code,
not a caller assertion of scientific evidence; its completeness needs provider-specific tests
and review. A malicious or incomplete provider implementation is not made trustworthy by hashing.
No pickle, repr-based fingerprint, automatic object serializer or digest-only escape is allowed.
Missing integrity support refuses checkpoint issuance/restore; there is no weakened mode.
An explicitly qualified inline-bytes codec may return the bytes token itself. Python's
bytes type alone is not a completeness declaration: it may contain a path or blob reference.
After issuance/record admission, failed integrity reads (including interruption) raise
`CheckpointIntegrityError`, preserving the original exception as cause and retiring the
affected wrapper. A classified provider failure retains its identity/phase in that cause.

R2: restore failure may follow mutation. A runtime with a failed restoration is permanently
unusable; built-in callback/external participants are invalidated too. Callback adapters may
separate read-only admission from restore application: safe foreign/record rejection leaves
the wrapper usable, but detected issued-payload corruption does not (it may alias live state).
Process-local object-identity retirement prevents reuse of custom participants in a fresh
runtime even without retirement hooks. Weak-value entries are used where possible; objects
that cannot be weak-referenced are retained strongly for process lifetime after failure.
No reset method clears this state. Finalization remains available. Direct use of raw provider
sessions or arbitrary custom callbacks outside Forge wrappers is outside this guarantee.

R3: this PyBaMM adapter supports physical origin zero only; arbitrary origins require a
separate provider design. Initialization, checkpointing and requests must agree with the
held solution clock. Solver times are checked against physical request endpoints, allowing
only floating-point representation roundoff (including PyBaMM's endpoint nextafter).
The existing y-only scientific state digest and build/configuration scope are preserved;
the seal separately fingerprints continuation time. No historical evidence is regenerated.
The held solution's committed fingerprint is checked before execution, including mutation
through an aliased checkpoint without an intervening restore. Failed solver endpoint checks
retire the wrapper. Absolute origins other than zero are explicitly unsupported.

R4: execution requires both checkpoint and executing backend/plan to name build and canonical
problem. Missing bindings refuse caller resume. Adoption may bind a just-produced checkpoint
from known backend/plan context, but may not invent missing context. Cold starts remain legal;
unusable checkpoints are discarded with the existing diagnostics. Legacy migration requires
an authoritative producer record of the original build/problem or a deliberate cold start;
copying current identities onto an old checkpoint is not migration. Cross-solver conversion
also requires an exact problem match; no conversion implementation is introduced here.
Both orchestration runners compare backend build identity before/after execution; observable
drift refuses the result and its checkpoint. A transient switch that restores the same identity
is not detectable by this comparison; provider build-attestation remains a separate obligation.

The existing native `provider_participant` declaration-only mode is retained and labelled
`build_basis=participant_spec_declaration`; no provider identity is invented for native records.
Once an expected or observed provider build is required, missing identity still refuses.
Declaration-only rollback must not be described as verified executable-build recovery.

These are deliberate behavioral admission restrictions in Core-package internals. Independent
compatibility/scientific review completed with PASS (static review only; see
CHECKPOINT_HARDENING_REVIEW.md). No frozen API snapshot, schema,
certificate or assurance threshold is to be edited to accommodate them. Frozen-surface,
serialization, identity and dependency checks are deferred, so compatibility is not verified.
Existing test fixtures that require working continuation must explicitly state build/problem;
their scientific routing expectations remain intact.

## Deferred execution

See DV-101 onward in DEFERRED_VALIDATION.md. No pytest, forge_check, mutation, full tiers,
provider solve or OD-3 execution is authorized in this task. Only static parsing/diff checks.

## Persistent recovery boundary

Durable recovery needs a separate protected issuance registry or authenticated manifest,
immutable payloads, provider codecs, full build/problem/time/mesh/configuration binding,
atomic coupled-set publication and isolated restore verification. A fresh process must not
reconstruct this in-memory seal's registry from caller-supplied data.

## Independent review and failed approaches

Read-only reviewer: `/root/checkpoint_review`, applying `.claude/skills/forge-scientific-review/SKILL.md`.
Initial and second reviews: CHANGES REQUIRED (review results only, no execution).
Corrections from those reviews:
- Removed automatic bytes-token integrity inference; bytes can encode mutable external references.
- Separated callback admission/application and retired direct application failures.
- Added pre/post backend-build checks before successful reporting or checkpoint adoption.
- Added process-local retirement for custom participants without hooks; bare object ids are insufficient.
- Retired issued-payload integrity read failures, preserving the original provider error as cause.
- Protected PyBaMM live state against alias mutation, including mutation without restore.
- Added adversarial tests for every above case and wrong provider-returned endpoints.

Do not repeat the rejected approaches: hashing a bytes handle is not content verification;
safe record rejection and corrupt issued/live state are different; an old runtime flag alone
cannot retire a custom session reused elsewhere. Do not fabricate provider identities for
native numerical records. Final review: PASS, no outstanding HIGH/MEDIUM finding in the
inspected patch. See CHECKPOINT_HARDENING_REVIEW.md. This is not test execution or certification.
