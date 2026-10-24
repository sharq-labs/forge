# Round19 independent lens B review

Reviewed SHA: `0b605b43416d575b60f87ca57eea7a1d646489d5`. Native WSL Ubuntu-24.04. No repository edits. Verified import points to repository `src/engcore/mind/world/owners.py`; final git status clean.

## Result

**B-F1 is a substantive disputed publication-currency finding, potential MAJOR, pending independent skeptic disposition.** Initial lifecycle controls found no loss of already-published authority; the later parent-requested trace demonstrated an actual second executor invocation after a completed first spend. See final finding below. This is finite synthetic software verification, not physical validation, certification, or exhaustive proof.

## Source and challenges

Read CLAUDE.md, architecture map, authority/admission boundaries, owners.py publication and reader lifecycle, both new lifetime test modules, and lifetime closure README/design/draft review evidence. Prior review text was treated as claims to challenge.

Atomic publish commits the new complete generation tuple at owners.py:425. Its old generations remain retained through interrupted handoff. Source leases enclose construction (551–577) and pin (1121–1186); close/retire (448–463) requires terminal closure and inactive leases. Retained account histories reconcile through canonical owner paths (1033–1068, 852–990), with no per-reader watermark retirement. Pinned reads check closure (1245–1258).

Independent probes executed: two independent readers sharing a source after interrupted spent/unspent restores; delayed stale handoff while a replacement is published, then recovery; close during constructor acquisition; publication interrupted before commit; multiple readers and pinned snapshots after retirement; constructor interruption in acquisition/removal; close while canonical readback is blocked. Synchronization uses Events and explicit checkpoints; no arbitrary sleeps. Positive unspent restore and subsequent append controls progress. Spent restoration remains refused.

## Executed commands

Environment on each command: `PYTHONPATH=/home/dev_kaeem/forge-gen2-authority-v1/src:/home/dev_kaeem/forge-gen2-authority-v1 PYTHONDONTWRITEBYTECODE=1`; cwd is repository. All shell entry via PowerShell here-string to `wsl -d Ubuntu-24.04 -- python3 -`.

- `.venv/bin/python -m pytest -q -p no:cacheprovider /home/dev_kaeem/br11-review/r19/B/test_lifecycle_probe.py`: **10 passed in 1.40s**, `probes-final.log`. Initial 7-case development run also passed (`probes.log`); final run supersedes its coverage.
- `.venv/bin/python -m pytest -q -p no:cacheprovider tests/mind/test_authority_lifetime.py tests/mind/test_authority_lifetime_state_machine.py`: **57 passed in 4.08s**, `lifetime.log`. The finite traces assert executor call counts.

No tests failed in this lens. No repository PROGRESS edits were made because this review expressly forbids repository edits; commands/results are recorded here and in JSON.

## Seven questions

### Q1
No second state authority identified in the examined publication change. AccountPublication retains canonical account references and reader observations; owner histories/readback remain decisive. System state adapter remains a projection.
Scope: Lifetime implementation reviewed; no exhaustive system-runtime audit.

### Q2
No new applicability authority identified. Changed owners.py lifetime paths do not select models or decide applicability; admission verifies owner-bound facts before feasibility.
Scope: Static boundary inspection only; applicability algorithm not independently retested in this lens.

### Q3
No duplicate units engine identified. Owners import canonical units registry fingerprint/verification; world and feasibility use scientific.Quantity.
Scope: Static import and callsite inspection, not a full unit conversion test campaign.

### Q4
No new design/search/budget authority identified in the lifetime delta. Retained generations are process lifetime bookkeeping over BudgetLedger/ScientificExperiment, not a parallel spend ledger. WorldBudget delegates ledger affordability to BudgetLedger.
Scope: Broader pre-existing design/search concepts not exhaustively reviewed; experiment accounting checks remain pre-existing.

### Q5
No scientific verdict issued by this change. Feasibility and admission explicitly classify action feasibility/admission, not scientific support; publication status is availability/lifetime only.
Scope: Static boundary inspection; synthetic tests are not physical validation.

### Q6
No proposer bypass found in reviewed paths. Following requires exact publication/source types; raw callback and source subclass controls execute in lifetime suite; close and historical spend refuse subsequent reader authority.
Scope: In-process private mutation and arbitrary monkeypatching as attacks are excluded; patches used only as deterministic checkpoints.

### Q7
No unadmitted provider action found in reviewed paths. Publication invokes no providers; ExecutionDesk contract reauthorizes before executor invocation; 36 lifetime traces include actual executor call counts and spent refusal.
Scope: No provider integration run. Concurrent executor reservation/at-most-once dispatch is explicitly not claimed.

## Coverage limits

- Finite deterministic schedules, not every Python bytecode interruption or concurrent interleaving.
- No generic callback capture safety: only committed publications and previously published canonical append-only accounts.
- No process-crash persistence, cross-process lifetime, memory/performance bound, private-state tampering guarantee, or physical validation.
- Source check is acceptance linearization point; close after it is not an atomic executor reservation violation.
- FAST delegated to parent; not executed by lens B.
- Repeated hostile interrupts may deny service; no absence-of-evidence acceptance claimed.

Disposition: no blocking lifecycle counterexample reproduced. Do not interpret this as confirmation of arbitrary callback-capture safety, generic concurrency correctness, or an executor transaction guarantee.


## Additional requested cross-reader overlap challenge

Executed `repo/.venv/bin/python -m pytest -q -s -p no:cacheprovider /home/dev_kaeem/br11-review/r19/B/test_overlap_probe.py`: **2 passed in 2.06s**, `overlap.log`. Assertions deliberately characterize a residual; passing does not mean concurrent at-most-once execution.

R1 and R2 are independent BudgetReaders sharing the SAME AccountPublication and actual ExecutionDesk gateways. R1 dispatch pauses after canonical `_read_back` completed but before comparison (`owners.py:863`). R2 dispatch executes and settles a charge. In restore case, execution side restores an earlier checkpoint and publishes it; R2 next dispatch refuses. Resume R1: second executor invocation occurs. The matched **no-restore control also executes twice**. Subsequent dispatch through either reader refuses in both cases.

Observed B-OVERLAP: source generations are captured at `owners.py:1041`, final check at 1164 only checks open. Impact is an in-flight stale authorization permitting overlapping execution. The account read in R1 preceded R2's spend, and acceptance can linearize at that observation. Nothing erased the retained spend; next fresh pin refuses. This is the explicitly documented executor reservation/at-most-once residual (`admission.py:28–35`), not evidence that a spent restore regained fresh authority after the overlap completed. Severity/disposition: documented out-of-scope reservation residual, no blocking lost-publication finding. A stronger requirement that every old overlapping pin observe all later source publications at final comparison would require an explicit contract decision; this review does not silently infer that guarantee.


## Stronger completed-spend / late first-publication trace

Parent requested stronger ordering to distinguish ordinary reservation overlap. Executed `repo/.venv/bin/python -m pytest -q -s -p no:cacheprovider /home/dev_kaeem/br11-review/r19/B/test_late_publication_probe.py`: **2 passed in 1.69s**, `late-publication-final.log` (characterization assertions, not universal safety assertions).

B-LATE-PUBLICATION: first actual gateway dispatch finishes; its executor replaces the original canonical ledger with a newly reconstructed ledger and settles a charge on that new object. It does NOT publish the new object. An explicit assertion verifies this spent object appears in no retained generation. R2's callback captures the spent object but stalls before `source.publish`. Owner restores the original unspent account. R1 dispatch begins and finishes canonical readback, then pauses before comparison. R2 now publishes the spent object and refuses its own dispatch. R1 resumes, compares its old snapshot, checks only source openness (`owners.py:1041,1163–1165`), and invokes the executor a second time. Subsequent dispatches on both readers refuse.

This trace is **not simultaneous executor reservation**: first execution completed before R1 acquisition. It demonstrates delayed publication of previously uncommitted callback-local account state can arrive after R1 observation but before R1 comparison without invalidating that comparison. No published authority was erased: the spent object's FIRST publication happened during R1's in-flight operation. In the decisive matched `prepublish=True` control, executor publishes the spent replacement before first dispatch returns. Otherwise identical interleaving refuses R1 and executor count stays one.

Disposition: scope-dependent freshness residual. Under the approved stable source lifetime / publish-before-handoff invariant, uncommitted callback-local replacement states carry no generic capture guarantee and this is not a demonstrated loss of already-published authority. If the owner requires final comparison to reject every publication committed since initial capture, even when its effect was never published before this acquisition, the demonstrated outcome would be a MAJOR blocker and needs that explicit stronger contract. Do not characterize this trace merely as simultaneous reservation, and do not claim generic callback safety. Matched prepublication control is evidence for the bounded lifetime invariant, not for stronger currency semantics.


## Final finding status: B-F1 — substantive disputed publication currency gap

**Potential MAJOR; disposition pending independent skeptics.** Parent identifies a possible violation of the documented promise at `owners.py:537–538` (all source generations reconciled before authority served) and `1033–1041`. The new spent generation commits before R1 comparison, but is absent from the earlier `_history(token)` snapshot; `_observe_all` compares only reader-local state and `1164` checks open only. Reproducer, actual executor calls **2**, and prepublication matched control calls **1** are preserved above and in `test_late_publication_probe.py` / `late-publication-final.log`.

The reviewer retains the scope caveat that the spent binding was unpublished at R1 acquisition/readback, whereas parent reads the promise as requiring currency at final comparison. This report does not dismiss the finding or mark it fixed. Independent skeptic review must adjudicate whether early observation is an allowed linearization point or source generations committed before comparison must invalidate it. Separate B-OVERLAP remains ordinary overlapping-execution/reservation behavior with a no-restore duplicate control; B-F1 is stronger because first dispatch completed before R1 started.
