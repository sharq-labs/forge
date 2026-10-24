# Proposed owner decision: account handoff lifetime

Status: PROPOSED, NOT APPROVED. This document is decision support, not a second task queue or scientific evidence.
Round16 reviewed b8a65bb9d02b5a18e0a8b26779773c1552204dc1. Local repair gate source 68db8819d433d1819968e44312c44f1da4996dda.

The open failure is a returned live mapping whose native capture and immediate recovery both fail before an account
reference is retained. Ordinary replacement by an earlier owner checkpoint erases the handed spend. Later retry
accepts the restored state and the existing simulated executor runs twice. Independent runtime evidence: A/B/C/D/E,
S1/S2; completeness critic confirms the scope. S1 paired histories show unchanged and spent-then-restored histories
can leave the same recoverable reader state. This is conditional information-loss evidence, not formal proof.

The local repair preserves canonical histories after capture and handles the demonstrated one-shot registration gap.
It does not solve uncaptured information loss. Arbitrary retry counts, a worker thread, or a later read cannot create
missing history; permanent refusal solely for an honest interruption violates the requested usability guarantee.

Decision requested after local repair and Round17 review: authorize design and implementation of an execution-owner
retained handoff contract using existing canonical account records. Specify a publication commit point into an already
identified reader slot, stable snapshot/history retention across restore until authoritative comparison acknowledges
it, and behavior for interrupted publication/acknowledgement, multiple readers, resource failure, and legacy callbacks.
This adds a lifetime obligation, not a second budget ledger, invented spend, scientific evidence, reservation, or durable
at-most-once execution. No protocol implementation is authorized by this proposal itself.

Alternative requiring explicit owner acceptance: define observation as successful native capture and exclude earlier
interruptions from the preservation promise. This weakens the current all-returned-handings guarantee and cannot be
selected silently. Current mutable-callback behavior remains development-incomplete until the owner decides.

Required evidence for any selected implementation: deterministic checkpoints before/after publication, during capture,
recovery and acknowledgement; repeated interruption; concurrent restore/readers; detached canonical equivalence and
true differences; no forgotten spend; no implicit success from unavailable data; honest unchanged recovery; exact
source review, mutants and existing gate differential. No certification or physical validation is implied.
