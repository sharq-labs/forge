# Round 20 independent A/F review

Reviewed immutable SHA b4bbee0f6df40b7dd0de9b0739beef392dab6be5 in native Ubuntu-24.04 checkout /home/dev_kaeem/forge-gen2-authority-v1. owners.py SHA256 efad8b564d00331877308151648554970222652a3249220c7fe934d4118eb7a3 verified before and after. Source read-only; scratch artifacts only in this directory. Root AGENTS.md absent in native checkout; supplied AGENTS working contract and actual CLAUDE.md read. Required project, architecture, Scientific Core, freeze, claims, active-plan and relevant progress/Genesis contracts consulted. No dependency installation or source edits.

## A — Canonical authority and all-owner binding

No actionable finding within this bounded review.

Actual source inspection: projection.py:33-90 reads declaration, units, state, model, provider and budget through their existing owners. authority.py:226-258 enforces one reader per owner kind and eagerly pins every reader independently of the world bindings selected by a proposer. authority.py:276-320 checks owner identity, canonical record digest/revision and projected payload. This lifetime change retains account objects and entry histories, rather than creating another authoritative accounting value.

owners.py:409-426 freezes the mapping association in publication generations. owners.py:441-456 requires a current source token and defines the final comparison boundary; owners.py:1045-1087 retains all source generations and performs bounded rereconciliation on newer publication while preserving the original handoff. owners.py:1191-1199 refuses and seals a callback switching its original source. New source creation remains an explicit execution-owner new timeline, not a continuity-preserving migration.

Independent probes executed: (1) switch an existing reader to another source after spend, then switch back: refuses both; (2) reconstruct a new reader over the same publication after spend/restore: refuses; (3) delete the current account then restore its old checkpoint: missing stays missing, restore refuses; (4) eager memo pin without a world selecting the account records its history and refuses its restored record. Existing lifetime tests exercise legitimate unspent restores and subsequent progress, so these results are not merely blanket refusal.

## F — External proposer, injected owner/provider and dispatch bypass

No actionable finding within this bounded review.

admission.py:304-336 canonicalizes the proposal and rebuilds/verifies the world, deciding on the owners' fresh projection. admission.py:402-454 requires exact admitted/authorization types and live execution-side authorities and re-derives admission before execution. admission.py:463-534 retains the owner set and suggestion policy in the guarded execution boundary. port.py:90-110 requires the gateway/executable admitted-action interface. Provider status is projected from its registry (projection.py:76-81); the generic world imports no provider execution adapter (executed boundary guard).

Four new bypass probes executed with executor-call assertion zero: raw proposal dispatch, human-labelled proposal admitted elsewhere sent to a suggestions-only execution desk, missing budget-owner registry at dispatch, and a fake reader declaring live=True. All refused. R3 tests include positive dispatch controls, canonical-unit configuration controls, applicability and external-suggestion paths; cross-domain controls and world dependency guards also executed.

## Explicit Q1-Q7

Q1 second state authority: NO. Q2 second applicability authority: NO. Q3 duplicated units authority: NO. Q4 duplicated design/search/budget authority: NO. Q5 world issuing scientific verdicts: NO. Q6 external proposer bypass: NO. Q7 provider executing an unadmitted action: NO. These answers concern the inspected interface, exact SHA and bounded tests; they are not process-isolation claims or proof of every possible schedule.

## Execution and limitations

Exact argv, output, exit code and identity are in execution.json; focused.log has pytest output. Existing .venv/bin/python executed 8 fresh scratch probes plus tests/mind/test_authority_review_r3.py, test_authority_cross_domain.py, test_authority_lifetime.py and test_world_boundary.py: 87 passed in 11.39s, exit 0. No failures or harness repairs. The source hash and HEAD remained unchanged.

This is software contract verification using synthetic fixtures, not scientific validation, certification, a full-suite result, or a proof of concurrency completeness. Arbitrary in-process private mutation/closure introspection remains in the execution trust domain; external isolation is not supplied by this Python interface. Owner replacement with a new publication timeline, persistence/restart continuity, and executor reservation/exactly-once semantics are explicit boundaries. Retention until terminal close can grow memory; no bounded-retention claim was tested. Independent concurrency, identity and completeness lenses must assess their own scopes.

Findings: 0 BLOCKER, 0 MAJOR, 0 MINOR. Verdict for A/F scope: PASS.
