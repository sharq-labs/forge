# Round19 focused independent skeptic S2

Reviewed HEAD `0b605b43416d575b60f87ca57eea7a1d646489d5`, native Ubuntu-24.04 WSL, repository `.venv/bin/python`. Imported owners module from `/home/dev_kaeem/forge-gen2-authority-v1/src/engcore/mind/world/owners.py`. Source/test files unchanged by this review. Final status showed `M docs/work/PROGRESS.md`, an external concurrent edit; S2 wrote only its assigned artifact directory. No broad suites run.

## Disposition

**MAJOR S2-F1: permanent false rewrite on honest monotonic detached replacements, independently reproduced.** This blocks closure independently of disputed B-F1. **B-F1: reproduced; MAJOR under the written current-generation/final-acceptance contract.** The latter is a source-publication currency gap, not erased retained history or simultaneous executor reservation. A narrower source-capture linearization contract would change that classification, but that is not the final-open-check boundary presently claimed in the closure README.

## S2-F1 deterministic regression

`test_s2_r6.py` uses Events and `sys.settrace` line checkpoints only, without replacing methods or changing source/private state. Initial canonical ledger is empty before reader construction. A publishes L1 with charge `initial`, reads it, and pauses immediately before comparison at owners.py:886. B reads the same L1, compares and clears its unread barrier; B then hits the production one-second wait for A and returns transient refusal. C publishes a canonical detached copy L2 extending L1 by charge `forward`, retains its entries and pauses before readback at :863. A resumes with its earlier legitimate one-charge snapshot. The latest barrier is a raw tuple holding L2 entries. A's old L1 charge object differs by identity from the canonically equal L2 charge object. `_against_unread` reaches :844 and returns `_rewrote_unread`; :949-951 persists that conclusion into `_diverged`. C also refuses permanently.

The matched in-place append control preserves charge identities: A gets transient `behind unread`, C reads revision 2, and no permanent divergence exists. Final execution: **1 failed, 1 passed**, failing `[True]` (detached) as the safety assertion requires. The exact original R6 stress node passed on one independent isolated execution; this does not negate the parent's FAST failure or this deterministic schedule.

Affected source: :823-844 (identity incomparability converted to rewrite), :866-879 (canonical resolution covers only snapshot barriers), :892-904 (exact-barrier protection), :939-951 (unresolved handling only protects some cases and stores permanent refusal). Correction to parent hypothesis: a changed exact barrier can explain the general race, but this minimal schedule does not require a populated `resolved` entry being skipped at :893. A's original barrier directly matches its own snapshot and skips normalization at :873. C's newly installed raw tuple has never been canonically compared against A. Treat every unnormalized/new incomparable barrier as transiently unresolved and reconcile canonical content outside the lock on a fresh pin; retain exact-barrier guards and do not clear unseen entries. Identity mismatch is not contradiction evidence. No production fix was made.

## B-F1 independent replay and interpretation

Copied B's reproducer to S2 and independently executed both controls: **2 passed**, characterizing actual executor counts of 2 for late publication and 1 for prepublication. First dispatch completes and spends a replacement that has not been published. R2 captures it locally but pauses before source publication. Owner restores the original. R1 starts afterward, reads original, pauses before comparison. R2 publishes spent replacement and refuses its own dispatch. R1 resumes and executes a second time. Both readers subsequently refuse.

This is NOT ordinary overlapping executor reservation: first dispatch completed before R1 began. Nor does the trace establish that an unpublished ephemeral state must have been knowable earlier: at R1 capture it was outside the source and is explicitly excluded by the callback-local residual. The critical event is its later committed publication, before R1 comparison and the final acceptance boundary. The source now owns admissible canonical history that R1 has not reconciled.

`AccountPublication._history` checks latest token only at :441-446; `_retain_publication` captures that tuple at :1041; :1163-1165 compares old local state and only checks source openness. The written design says to serve only the current generation after comparison; owners.py:537-538 says all source generations are reconciled before authority is served; closure README explicitly calls the final open-source check the read-acceptance linearization boundary. R1 does not satisfy those statements once R2 commits. The earlier ephemeral-state exclusion cannot by itself excuse ignoring a state after it becomes source-owned. Therefore I classify the implementation against that written boundary as MAJOR. If the owner instead selects history capture/readback as the source generation linearization point, B-F1 becomes an explicit delayed-publication residual; that weaker semantic choice must be stated coherently instead of claiming currency at the final open check.

A candidate correction is a source-generation currency check at the actual authority acceptance boundary, refusing/retrying when publication changed since reconciliation. It must respect lock ordering and bounded interruption handling. This is distinct from atomic execution reservation and does not claim to solve all in-place mutation/executor races. No fix or proof of sufficient synchronization was attempted.

## Execution and limits

All commands use `PYTHONPATH=repo/src:repo PYTHONDONTWRITEBYTECODE=1`, cwd the exact repository, shell entry PowerShell here-string piped to `wsl -d Ubuntu-24.04 -- python3 -`.

- `.venv/bin/python -m pytest -q -s -p no:cacheprovider /home/dev_kaeem/br11-review/r19/S2/test_late_publication_probe.py`: 2 passed; `late-publication.log`.
- `.venv/bin/python -m pytest -q -s -p no:cacheprovider /home/dev_kaeem/br11-review/r19/S2/test_s2_r6.py`: 1 failed / 1 passed; `r6-controls.log`.
- `.venv/bin/python -m pytest -q -p no:cacheprovider tests/mind/test_authority_review_r6.py::test_concurrent_verifications_never_refuse_for_good_an_account_that_only_moves_forward`: 1 passed; `r6-original.log`.

Development attempts: initial B checkpoint held the reader lock while C attempted capture and timed out; this was a harness scheduling failure, not product evidence (`probes.log`). A subsequent trace with the fixture's preexisting charge retained multiple incomparable identity histories, giving `_PendingHistories` and correctly transient refusal. Starting from an empty canonical ledger isolates the unprotected raw-tuple case. Final controls explicitly discriminate detached vs same-object appends.

Finite synthetic software concurrency evidence only. No physical validation, certification, exhaustive schedule coverage, or broad-suite verification. R6 stress root cause is consistent with deterministic failure, but the precise FAST interleaving was not recorded, so cannot prove they are the identical interleaving. No repository PROGRESS edits by S2 because assigned review scope was read-only; execution records are here.

## Authorized R6 remediation after frozen review

Root explicitly ended the read-only source freeze for this bounded correction. S2 owns only `_against_unread` and new `tests/mind/test_authority_review_r19.py`; concurrent B work owns publication currency. No B-F1 semantics were edited by S2.

The new repository regression was first executed with original reviewed owners.py: `.venv/bin/python -m pytest -q -p no:cacheprovider tests/mind/test_authority_review_r19.py` -> **1 failed, 1 passed in 5.20s**, detached case failing `assert "rewrote" not in outcomes["A"]`; `fix-red.log`. It asserts both future direct read and future pin recover revision 2.

Changed only the raw identity-incomparable return from `_rewrote_unread` to `"unresolved histories"`, documented why another comparison can install an unnormalized barrier, and corrected the method docstring. Canonical content incompatibility still follows the existing `_observe_all` divergence path.

Executed `.venv/bin/python -m pytest -q -p no:cacheprovider tests/mind/test_authority_review_r19.py tests/mind/test_authority_review_r6.py tests/mind/test_authority_lifetime.py tests/mind/test_authority_lifetime_state_machine.py` -> **73 passed in 7.82s**, `fix-focused.log`. Owner source hash unchanged during this command (hashes in log). Executed `git diff --check -- src/engcore/mind/world/owners.py tests/mind/test_authority_review_r19.py` -> exit 0. No commit. Parent owns concurrent PROGRESS edits and was sent exact commands/results for append. These results establish the bounded correction, not the later combined B/source changes or broad integration.
