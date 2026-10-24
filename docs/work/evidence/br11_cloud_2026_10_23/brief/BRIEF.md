# FORGE — GEN2-BR1.1
## Authority-Bound ScientificWorld + Non-Bypassable Action Admission
## Repair campaign for AUTHORITY_DUPLICATION_BLOCKER

We are continuing from the completed GEN2-BR1 review.

Expected starting branch:

research/mind-gen2-scientific-world-v1

Expected exact HEAD:

1202ea6c3d96f5c31d0b142a32438da75e020cae

Expected state:

clean working tree

Current conclusion:

AUTHORITY_DUPLICATION_BLOCKER

Generation 1 is sealed and must remain unchanged.

This task is a repair campaign, not a new cognition feature.

Do NOT start:

- HypothesisPortfolio
- SearchTree
- AttemptMemory
- Ax
- BoTorch
- PySINDy
- PySR
- ModelCritic
- causal reasoning
- Battery v4

==================================================
0. VERIFY THE STARTING POINT
==================================================

Before editing:

1. Verify current branch.
2. Verify exact HEAD.
3. Verify `git status --porcelain` is empty.
4. Verify the committed BR1 README and PROGRESS report exist.
5. Verify GEN1 reference remains intact.

If any identity differs, STOP and report it.

Create a new repair branch from the exact blocked HEAD:

research/mind-gen2-authority-binding-v1

Do not modify main.

==================================================
1. TREAT THE BR1 REVIEW AS BINDING EVIDENCE
==================================================

Read in full:

- the GEN2-BR1 README;
- especially README §6 and its eight repair requirements;
- the final PROGRESS entry;
- the authority map;
- live repository authority documents;
- canonical state/twin owners;
- applicability owners;
- units owners;
- provider capability owners;
- budget/execution owners;
- design/search-space owners;
- protocol/action owners.

Create a repair matrix before implementation:

| Requirement | Current owner | Current defect | Required invariant | Planned change | Test |
|---|---|---|---|---|---|

The eight requirements recorded in README §6 are binding inputs.

Do not paraphrase them away or silently replace them.

==================================================
2. ROOT CAUSE TO REMOVE
==================================================

The root cause from BR1 is:

ScientificWorld currently decides admission using copies of authoritative
records.

Those copies are not proven current or identical to their canonical owners.

This permits:

- stale values;
- invented values;
- rebound values;
- missing-owner references;
- copied applicability;
- copied provider state;
- copied budget state;
- copied unit/domain semantics;

to influence action admission.

This must end.

ScientificWorld must become:

A VERSIONED, READ-ONLY, VERIFIABLE PROJECTION

over authoritative FORGE owners.

It must never become another owner.

==================================================
3. CORE ARCHITECTURE
==================================================

The target architecture is:

CANONICAL OWNERS
    |
    | exact record identity / revision / digest
    v
AUTHORITY BINDING
    |
    | verified read-only projection
    v
SCIENTIFIC WORLD VIEW
    |
    v
FEASIBLE ACTION SPACE
    |
    v
ACTION PROPOSAL
    |
    v
ACTION ADMISSION
    |
    | admitted capability
    v
EXISTING EXECUTION SYSTEM

No layer below the canonical owner may manufacture authoritative state.

==================================================
4. AUTHORITY BINDING RECORD
==================================================

Introduce the minimum generic binding needed to prove where every projected
fact came from.

Do not invent a parallel evidence store.

A binding should identify, where applicable:

- owner kind;
- owner identity;
- authoritative record identity;
- record revision/version;
- exact digest or equivalent content identity;
- source namespace;
- projected fields;
- binding time only as metadata, never identity;
- verification state.

A ScientificWorld value must never become authoritative merely because the
world stores it.

The authoritative identity remains the owner's identity.

==================================================
5. OWNER ADAPTERS, NOT OWNER COPIES
==================================================

Build narrow read-only adapters/projections for existing owners.

The adapter may:

READ
NORMALIZE FOR PRESENTATION
PROJECT ALLOWED FIELDS
VERIFY IDENTITY

The adapter may NOT:

invent state
change scientific meaning
change applicability
change units
change budget semantics
change provider availability
issue scientific verdicts

If an existing owner lacks a necessary read-only identity/digest/current-state
API, prefer adding the smallest read-only capability to THAT OWNER rather than
reimplementing its semantics inside ScientificWorld.

Any modification to an owner must preserve its existing authority and semantics.

==================================================
6. CURRENT-STATE VERIFICATION
==================================================

Admission must verify that every authority-bound fact used by the decision is
still current.

At minimum verify material dependencies such as:

state
protocol
provider availability
applicability
budget
model/configuration
units/domain declarations

If a dependency changed after the world snapshot was built:

do NOT silently continue.

Return an existing appropriate feasibility failure such as:

INFEASIBLE_STATE

or:

MISSING_INFORMATION

with a structured reason identifying the stale binding.

Only add a new typed status if existing semantics cannot truthfully express the
condition and a failing-first test proves the need.

==================================================
7. FIX THE LINEAGE-LAUNDERING DEFECT
==================================================

BR1 reproduced this defect:

SOC was unbound and rebound to a different value while the world lineage still
verified and the admission decision changed.

Write the failing-first regression BEFORE implementation.

Required invariant:

A projected authoritative value cannot change under the same authoritative
record identity.

Changing the authoritative value requires:

- a new authoritative owner record/revision;
- a new verified binding;
- a new world revision.

A world revision alone must not be allowed to legitimize an invented owner
value.

Test:

owner record A says SOC=x
world binds A
attempt to rebind A as SOC=y

Required:

FAIL CLOSED

No valid lineage.
No admitted action.

==================================================
8. FIX THE MISSING-OWNER DEFECT
==================================================

BR1 reproduced:

a SOC value referenced a state record that did not exist, yet admission still
succeeded.

Write the failing-first test first.

Required invariant:

A binding to a non-existent, unreadable, or unverifiable authoritative record
can never support admission.

Required outcome:

MISSING_INFORMATION
or an existing equivalent typed failure.

No admitted-action record may be emitted.

==================================================
9. FIX INTERVAL / UNCERTAINTY SEMANTICS
==================================================

BR1 reproduced:

an interval with only 10% coverage was treated as a hard enclosure and allowed
an action to be considered feasible.

This is scientifically invalid.

Do not interpret arbitrary uncertainty intervals as deterministic domain
bounds.

Explicitly distinguish the semantics already present in FORGE, or introduce the
minimum typed distinction needed, between concepts such as:

hard bound / enclosure
standard uncertainty
confidence/credible interval
coverage interval
distribution summary
unknown uncertainty

Only a semantically valid hard bound/enclosure may prove containment when hard
containment is required.

Example:

value estimate = x
10% coverage interval lies inside domain

must NOT imply:

value is definitely inside domain.

If the decision requires a hard bound and only probabilistic uncertainty is
available:

fail closed with:

MISSING_INFORMATION

or the existing scientifically correct equivalent.

Do not convert probabilistic uncertainty into a deterministic guarantee.

==================================================
10. APPLICABILITY MUST STAY OWNER-BOUND
==================================================

ScientificWorld must not independently decide scientific applicability.

It may expose:

the authoritative applicability record/status
the exact inputs it applies to
its identity
its domain/provenance

Admission may ask whether an action is permitted by that authoritative record.

It must not create a competing applicability calculation.

If applicability depends on inputs not represented exactly in the binding:

fail closed.

==================================================
11. UNITS MUST STAY CANONICAL
==================================================

Do not duplicate the unit system.

ScientificWorld must use the existing FORGE units owner/backend.

A projected quantity binds:

value
canonical quantity/unit identity
source

A conversion used during feasibility must be performed by the canonical unit
system.

No admission decision may rely on unverified copied unit strings.

Keep the existing dimensional mismatch behavior.

Add tests showing that changing only a display string cannot alter scientific
meaning.

==================================================
12. PROTOCOL / SEARCH SPACE AUTHORITY
==================================================

FeasibleActionSpace must not become an independent design/search-space owner.

It is a projection of canonical protocol/design/action declarations.

For every allowed value/domain record, bind:

authoritative source
identity/revision
exact declared domain

Example:

current ∈ {1 A, 2 A}

must remain a projection of the canonical declaration.

The action layer may validate membership.

It may not independently invent:

1.15 A
nearest-value rules
interpolation permissions
new continuous domains

unless the authoritative protocol explicitly permits them.

==================================================
13. PROVIDER AVAILABILITY
==================================================

Do not trust a copied provider-status boolean.

Bind provider feasibility to the current canonical provider capability/health
record.

Before producing an admitted action:

verify the required provider still exists and is applicable/available according
to its canonical owner.

If the provider state changed:

fail closed.

No cached world copy may keep an unavailable provider executable.

==================================================
14. BUDGET AUTHORITY
==================================================

BR1 found that the budget ledger lacks enough identity/current-state support to
verify copies safely.

Do NOT solve this by creating a second budget authority in ScientificWorld.

Inspect the canonical budget/execution owner.

If it already has sufficient immutable/current identity:
bind to it.

If it lacks only a read API or digest:
add the minimum read-only identity/current-state facility to the canonical
owner.

If the repository genuinely has no authoritative current budget state capable
of supporting safe admission:

do NOT invent one.

Instead make budget-sensitive admission fail closed and return a precise
BLOCKED_WITH_EVIDENCE record describing the missing canonical capability.

A missing owner is preferable to duplicate authority.

==================================================
15. NON-BYPASSABLE ADMISSION
==================================================

This is critical.

An ActionProposal must NEVER be executable merely because it exists.

Introduce or reuse the minimum admitted-action representation/capability.

Conceptually:

ActionProposal
    |
    v
Admission
    |
    v
AdmittedAction
    |
    v
Execution Adapter

The execution path exposed by the Gen2 Mind interface must require the admitted
representation.

A raw ActionProposal must be rejected.

An AdmittedAction must bind at least:

proposal identity
world revision
action-space identity
authority bindings used
admission result identity

If any material owner binding is stale at dispatch time:

execution must refuse.

==================================================
16. DO NOT BUILD A SECOND EXECUTION AUTHORITY
==================================================

The Mind package must not reimplement:

provider dispatch
budget mutation
state mutation
execution ownership

The admitted-action capability is authorization metadata for the existing
execution owner.

Execution remains owned by existing FORGE execution infrastructure.

If integration requires duplicating execution semantics, stop and redesign the
boundary.

==================================================
17. EXTERNAL PROPOSER BYPASS
==================================================

Future proposers include:

Mind
Ax
BoTorch
PySINDy
PySR
external AI workers

All must enter the same boundary:

External Proposal
    ->
ActionProposal
    ->
Admission

No proposer may directly construct AdmittedAction.

No proposer may set authority-binding fields.

No proposer may mark itself FEASIBLE.

Write negative tests proving this.

==================================================
18. WORLD SNAPSHOT IMMUTABILITY
==================================================

ScientificWorld snapshots remain content-addressed and immutable.

But world identity must include the identities of the authority bindings, not
just copied values.

If:

state changes
protocol changes
provider state changes
budget changes
applicability changes

then the resulting verified world identity must differ.

A copied value edit without an authoritative owner change must invalidate
verification, not create a legitimate new world.

==================================================
19. TRUSTED PROJECTION VS VERIFIED CURRENTNESS
==================================================

Keep these two concepts separate.

A world can be:

validly serialized
correctly content-addressed
replayable

and still be STALE relative to current owners.

Replay proves:

what the world contained.

Current-owner verification proves:

whether it may support a new action now.

Do not confuse replay integrity with current authority.

==================================================
20. BR1 FUNCTIONALITY MUST SURVIVE
==================================================

Preserve the good BR1 behavior:

7 role semantics
discrete feasibility
continuous feasibility where authoritative
fixed protocol protection
state/control distinction
measurement/control distinction
latent semantics
unit enforcement
provider checks
budget checks where authoritative
cross-domain fixtures
deterministic replay

Do not discard the existing BR1 implementation merely because its authority
binding was flawed.

Refactor it behind verified projections.

==================================================
21. FAILING-FIRST BLOCKER TESTS
==================================================

Before implementation, add failing-first tests for every known blocker.

At minimum:

A. 10%-coverage interval cannot prove hard-domain containment.

B. same owner record cannot be rebound to a different state value.

C. non-existent owner record cannot support admission.

D. stale state binding refuses.

E. stale applicability binding refuses.

F. stale provider binding refuses.

G. stale protocol/domain binding refuses.

H. stale budget binding refuses or reports the precise missing canonical
   capability.

I. copied unit display text cannot change unit authority.

J. raw ActionProposal cannot execute.

K. external proposer cannot mint AdmittedAction.

L. AdmittedAction becomes unusable when material authority changes before
   dispatch.

M. replay of historical world remains exact even when current owners have moved
   on.

N. exact current verified world still admits all valid BR1 controls.

O. invalid 1.15 A proposal remains refused with alternatives 1.0 A and 2.0 A.

==================================================
22. ADVERSARIAL AUTHORITY MUTATIONS
==================================================

Create a mutation suite specifically for authority laundering.

Mutate one property at a time:

owner ID
record ID
record digest
revision
projected state value
unit
domain
provider status
budget
applicability identity
protocol level
world parent
admission binding

Every scientifically material mutation must either:

change the authoritative identity legitimately

or

fail verification/admission.

No laundering through reserialization, rebinding or revision creation.

==================================================
23. CROSS-DOMAIN AUTHORITY TESTS
==================================================

Run authority-bound worlds for at least:

BATTERY
HVAC
DRONE
ELECTRIC_MOTOR

Prefer preserving the fifth BR1 world too if it already exists.

For every domain prove:

- state comes from an owner;
- action domain comes from an owner;
- units come from canonical unit handling;
- provider capability is verified;
- action admission cannot bypass bindings.

Do not write domain-specific authority logic.

==================================================
24. Q1–Q7 REVIEW MUST BE RE-RUN
==================================================

Re-run the exact seven authority-review questions from BR1.

Target:

Q1 second state authority            = NO
Q2 second applicability authority    = NO
Q3 duplicate units                   = NO
Q4 duplicate design/search concepts  = NO
Q5 world issues scientific verdicts  = NO
Q6 external proposer bypass          = NO
Q7 provider executes unadmitted action = NO

PARTIAL is not enough for closure.

For each answer provide:

code path
test
evidence
why the answer is NO

==================================================
25. REVIEW PROCESS
==================================================

Do not stop after an arbitrary number of rounds.

Use independent read-only review lenses such as:

A. scientific authority / ownership
B. software architecture / layering
C. adversarial mutation / bypass
D. replay / provenance / stale-state semantics

After each round:

classify findings:
BLOCKER
MAJOR
MINOR

Fix BLOCKER and MAJOR findings that are within scope.

Re-run the relevant failing-first controls.

Continue until either:

0 BLOCKER
0 MAJOR

or:

a precise external/canonical-owner blocker remains that cannot be solved
without an owner decision.

Do not loop on cosmetic MINOR issues.

==================================================
26. PERFORMANCE
==================================================

Re-measure:

WORLD_BUILD_MS
ACTIONSPACE_BUILD_MS
FEASIBILITY_P50_MS
FEASIBILITY_P95_MS
AUTHORITY_VERIFY_P50_MS
AUTHORITY_VERIFY_P95_MS
ADMISSION_P50_MS
ADMISSION_P95_MS
SERIALIZED_WORLD_BYTES

Compare against BR1 measurements:

WORLD_BUILD_MS ≈ 0.856
ACTIONSPACE_BUILD_MS ≈ 0.256
FEASIBILITY_P50_MS ≈ 0.140
FEASIBILITY_P95_MS ≈ 0.263

Do not sacrifice correctness to preserve these numbers.

Report the actual overhead introduced by authority verification.

==================================================
27. RUN OBSERVATORY
==================================================

If Run Observatory is already available in the cloud checkout/environment,
record the important benchmark/test runs.

Current remote observatory branch identity for reference:

feat/run-observatory-v1

ba9887a63f21934a788f99746cf941202d2740ee

Do not merge/cherry-pick observatory code merely to satisfy this section.

Do not block the repair if it is unavailable.

Report Run IDs if used.

==================================================
28. REPLAY
==================================================

Require exact deterministic replay of:

ScientificWorld
authority bindings
FeasibleActionSpace
ActionProposal
AdmissionResult
AdmittedAction identity

Replay must also demonstrate the distinction:

historical replay = exact

while

new execution using stale authority = refused.

==================================================
29. GEN1 PROTECTION
==================================================

Verify:

GEN1 reference INTACT

Battery v1/v2/v3 frozen files unchanged.

No Gen1 Mind behavioral code modified.

No historical benchmark result rewritten.

Any violation is a BLOCKER.

==================================================
30. TESTING
==================================================

Run at minimum:

- BR1.1 targeted authority tests;
- authority mutation tests;
- existing BR1 world tests;
- repsem tests;
- relevant Mind tests;
- replay tests;
- layering/authority guards;
- Gen1 integrity checks;
- cross-domain fixtures.

Run the repository-required changed-file gate.

If FAST is required:
run exact clean-base differential.

Never report a globally red tier as green.

Report separately:

BASE failures
BRANCH failures
NEW deterministic failures
NEW errors
FIXED failures

Run broader regression/SCIENTIFIC only if repository policy or changed scope
requires it.

Do not run certification just for optics.

==================================================
31. COMMITS
==================================================

Prefer clear local commits such as:

1. test(gen2): authority-binding failing-first controls
2. feat(gen2): bind ScientificWorld to canonical owners
3. feat(gen2): non-bypassable admitted-action boundary
4. test(gen2): adversarial authority mutations and cross-domain controls
5. docs(gen2): BR1.1 closure and review evidence

Exact number may differ if repository practice requires.

Do not push.

Do not merge.

==================================================
32. COMPLETION GATE
==================================================

BR1.1 may close only if:

- Q1–Q7 are all NO;
- 0 BLOCKER;
- 0 MAJOR;
- the three reproduced BR1 MAJOR failures are closed;
- no raw proposal can execute;
- no stale/missing binding can admit;
- no duplicate state/applicability/unit/search-space authority exists;
- Gen1 is intact;
- replay is exact;
- cross-domain functionality survives;
- changed-file differential has no new deterministic failures/errors.

==================================================
33. FINAL TABLE
==================================================

Return:

| Axis | BR1 Blocked State | BR1.1 Result | Status |
|---|---|---|---|
| STATE_AUTHORITY | duplicate/copy trusted | | |
| APPLICABILITY_AUTHORITY | duplicate/copy trusted | | |
| UNIT_AUTHORITY | partial duplicate | | |
| SEARCH_SPACE_AUTHORITY | duplicate/partial | | |
| BUDGET_AUTHORITY | unverifiable copy | | |
| PROVIDER_AUTHORITY | copied status | | |
| WORLD_PROJECTION | unverified | | |
| CURRENTNESS | absent | | |
| ACTION_ADMISSION | bypassable/partial | | |
| EXECUTION_BOUNDARY | partial | | |
| LINEAGE_LAUNDERING | reproduced | | |
| MISSING_OWNER | reproduced | | |
| INTERVAL_SEMANTICS | incorrect hard-bound interpretation | | |
| CROSS_DOMAIN | PASS synthetic | | |
| REPLAY | PASS | | |
| GEN1_INTEGRITY | intact | | |

Then return:

| Review question | Before | After | Evidence |
|---|---|---|---|
| Q1 second state authority | YES | | |
| Q2 second applicability authority | YES | | |
| Q3 duplicate units | YES/PARTIAL | | |
| Q4 duplicate search-space concepts | YES | | |
| Q5 world issues scientific verdicts | YES | | |
| Q6 external proposer bypass | YES | | |
| Q7 unadmitted provider execution | PARTIAL | | |

Then performance:

| Metric | BR1 | BR1.1 | Delta |
|---|---:|---:|---:|
| WORLD_BUILD_MS | 0.856 | | |
| ACTIONSPACE_BUILD_MS | 0.256 | | |
| FEASIBILITY_P50_MS | 0.140 | | |
| FEASIBILITY_P95_MS | 0.263 | | |
| AUTHORITY_VERIFY_P50_MS | N/A | | |
| AUTHORITY_VERIFY_P95_MS | N/A | | |
| ADMISSION_P50_MS | N/A | | |
| ADMISSION_P95_MS | N/A | | |

==================================================
34. DEVELOPMENT CONCLUSION
==================================================

Return exactly one:

READY_FOR_HYPOTHESIS_PORTFOLIO

AUTHORITY_BINDING_PARTIAL

CANONICAL_OWNER_CAPABILITY_MISSING

AUTHORITY_DUPLICATION_BLOCKER

BLOCKED_WITH_PRECISE_EVIDENCE

READY_FOR_HYPOTHESIS_PORTFOLIO requires the full completion gate.

Do not use it because synthetic accuracy is high.

==================================================
35. IF A CANONICAL OWNER CAPABILITY IS MISSING
==================================================

If repair discovers that an authoritative owner genuinely lacks a capability
required for safe projection, for example:

- immutable identity;
- revision;
- digest;
- current-state read;
- current budget read;

do not work around it inside ScientificWorld.

Instead:

1. prove the capability is absent;
2. identify the canonical owner;
3. determine the minimum read-only addition;
4. implement it only if doing so preserves existing semantics and is within the
   authority documents;
5. otherwise return CANONICAL_OWNER_CAPABILITY_MISSING with exact evidence.

No shadow authority is allowed.

==================================================
36. STOP
==================================================

After BR1.1 is closed or precisely blocked:

STOP.

Do not start:

Hypothesis Portfolio
Search Tree
Attempt Memory
Ax
BoTorch
PySINDy
PySR
Model Critic
Battery v4

Do not push.
Do not merge.
Do not certify.

Report:

branch
worktree/cloud checkout path
base SHA
final HEAD SHA
clean/dirty state
commit list
tests
gate differential
Q1–Q7 result
remaining MINOR findings
Run Observatory IDs if any.