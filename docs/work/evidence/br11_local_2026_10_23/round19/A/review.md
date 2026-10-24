# Round19 independent review — lens A

Reviewed immutable implementation: `0b605b43416d575b60f87ca57eea7a1d646489d5`.

No actionable finding established. This is a bounded software-authority review, not scientific validation or approval of the broader tree.

## Questions

### Q1
No second state authority found in reviewed paths.
RunStateReader accepts exact SystemRunResult/SystemCheckpoint, obtains canonical head and digest, checks following heads for rollback/rewrite, and projection verification compares owner facts and exact declaration projection. A following callback is the execution-side currentness statement, not independent proof of currentness.
Evidence: `src/engcore/mind/world/owners.py:243`, `src/engcore/mind/world/owners.py:255`, `src/engcore/mind/world/projection.py:108`

### Q2
No second model-applicability authority found.
Exact canonical model records are registry-read; ApplicabilityBinding delegates to ScientificModelDefinition.assess_validity. UNKNOWN and non-exact current inputs refuse model execution; non-model queries retain annotation-only applicability.
Evidence: `src/engcore/mind/world/owners.py:316`, `src/engcore/mind/world/world.py:122`, `src/engcore/mind/world/feasibility.py:853`

### Q3
No duplicate unit authority found.
Quantity, base-unit conversion and canonical magnitude come from scientific.units. UnitRegistryReader verifies the seal and binds the fingerprint. Budget amount conversion delegates to that owner. Local value encodings and domain checks do not constitute another unit registry.
Evidence: `src/engcore/mind/world/base.py:23`, `src/engcore/mind/world/owners.py:1347`, `src/engcore/mind/world/world.py:315`

### Q4
No competing design/search or spend authority established; one explicitly documented rule mirror remains.
FeasibleActionSpace checks and enumerates declared alternatives rather than ranking/searching/selecting. BudgetLedger.affordable owns ledger decisions; AccountPublication retains canonical account objects/history, not a second balance. Observation affordability mirrors ScientificExperiment.record because the owner has no affordability query; this is disclosed and is a maintenance coupling, not an independently writable accounting authority. Positive/negative public-lifetime probes below found no restore amplification.
Evidence: `src/engcore/mind/world/feasibility.py:460`, `src/engcore/mind/world/world.py:247`, `src/engcore/mind/world/world.py:339`, `src/engcore/mind/world/owners.py:392`, `src/engcore/mind/world/owners.py:1033`

### Q5
No scientific-support verdict issued by reviewed world/admission paths.
Classification explicitly says feasibility/admission is not scientific support. Current uncertain state containment refuses with MISSING_INFORMATION. Requested configuration exactness is separately disclosed from realization uncertainty; no conversion into evidence, validation or physical truth was identified.
Evidence: `src/engcore/mind/world/feasibility.py:77`, `src/engcore/mind/world/feasibility.py:770`, `src/engcore/mind/world/admission.py:72`

### Q6
No external-proposer bypass established under the execution-side suggestions_only policy.
Typed suggestion intake rejects authority and unknown keys, binds revision/family, and admission reconstructs proposal/world. Desk and guarded executor apply suggestions_only independently of port. ProposerKind is caller-asserted; deployments must enable the policy for external proposers. This is not Python-process isolation.
Evidence: `src/engcore/mind/world/actions.py:586`, `src/engcore/mind/world/admission.py:519`, `src/engcore/mind/world/admission.py:537`

### Q7
No public desk path to provider/executor with an unadmitted action established.
Dispatch requires exact AdmittedAction, live shipped owner readers, fresh re-admission and matching digest. Guarded executor re-derives supplied authorization. Provider invocation/effects remain executor-owned; this review does not claim atomic reservation or at-most-once dispatch.
Evidence: `src/engcore/mind/world/admission.py:402`, `src/engcore/mind/world/admission.py:443`, `src/engcore/mind/world/admission.py:457`

## Executed evidence

Environment: native WSL Ubuntu-24.04, CPython 3.12.3; import resolved to `/home/dev_kaeem/forge-gen2-authority-v1/src/engcore/mind/world/owners.py`. All Python runs set PYTHONPATH to repo/src:repo and PYTHONDONTWRITEBYTECODE=1. Pytest disabled cacheprovider and used external basetemp. Exact pytest argv and output are in the logs.

- 57 passed in 3.90s; /home/dev_kaeem/br11-review/r19/A/lifetime-tests.log
- 10 passed in 2.16s; /home/dev_kaeem/br11-review/r19/A/boundary-tests.log
- 8 adversarial rollback attempts refused; 5 legitimate detached restores/topups readable; /home/dev_kaeem/br11-review/r19/A/probe_public_lifetime.log

Independent probe challenges retained earlier-generation growth after successor publication, removal/readdition, and reader destruction/reconstruction on the same source. Each restores a pre-spend checkpoint without reader observation of the spend; all eight combinations refuse. Five unchanged detached restores with legitimate total-budget changes remain readable. These exercise normal source lifetime, not private-state corruption.

## Findings

None established; no severity/line/reproducer item is claimed without a counterexample.

## Limits

- Read-only bounded review of SHA 0b605b43416d575b60f87ca57eea7a1d646489d5; no source, branch, worktree, or repository-doc changes. Native Ubuntu-24.04 CPython 3.12.3 and owners.__file__ confirmed.
- Reviewed CLAUDE.md, architecture README, world owners/authority/projection/admission/feasibility/actions/port/base and relevant world budget/applicability code; checked canonical BudgetLedger behavior. Current lifetime evidence README read as claims/context, not authority or substitute for reruns.
- 67 focused pytest cases executed, not the broad FAST/regression suite. Independent public API probe covers eight serial lifetime variants and five positive restores/topups; not exhaustive concurrency or interruption-state exploration.
- Existing lifecycle tests deliberately inject KeyboardInterrupt/patch internals as fault controls. Independent probe uses only public publication, settlement, restore, close and retirement operations; no private-state tampering.
- Persistent source across ordinary restore is required by the approved contract. Deliberately replacing source states a new timeline; arbitrary private-member mutation, process-crash persistence, executor reservation/concurrency and at-most-once effects remain out of scope.
- Following run/declaration callbacks are trusted execution-side currentness statements; provider status freshness follows refresh policy. A live reader mode does not establish environmental truth.
- Source retains every distinct publication generation and may retain historical accounts indefinitely; no bounded-memory/performance claim. No physical validation, certification, universal correctness, or formal verification claimed.

Git HEAD rechecked unchanged. git status --short at completion:
```
(clean)
```
