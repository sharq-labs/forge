# GEN2-BR1 — ScientificWorld + Feasible ActionSpace v1

**Development conclusion: AUTHORITY_DUPLICATION_BLOCKER.**

The world model and the action-space check work on synthetic contract fixtures. But the read-only authority review
still answers YES on six of the seven brief questions after two fix rounds, which the brief (§22) makes a blocker.
The stopping rule was committed in `575faaa3` before round 2 was written: if a MAJOR or BLOCKER finding remained after
round 2, BR1 would stop with this conclusion and no third fix round. That condition was met.

This is development evidence on synthetic contract fixtures only. It makes no scientific claim, uses no real data,
and is not certified or formal. Generation 1 stays sealed and byte-identical (`gen1_reference --check`: INTACT).

- **Branch:** `research/mind-gen2-scientific-world-v1`, worktree `D:/forge-gen2-world`, local only (not pushed, not
  merged).
- **Base:** `da9325529f7016bf4fda41c9ff63d4546a2d8d3a`, the Gen1 sealed head.
- **Code:** `src/engcore/mind/world/`, imported by its own path, never re-exported from `engcore.mind` or the Gen1
  packages.
- **Tests:** `tests/mind/test_world_{failing_first,contract,boundary}.py`.
- **Benchmark:** this directory.

## 1. Ownership census (before any code)

A ten-agent read-only census covered nine concept clusters and ended with a critic pass. Its rule: reuse an owner where
one exists, adapt it with a thin view where it nearly fits, and build new only where nothing owns the concept.

| Concept | Existing owner | Decision | Reason |
|---|---|---|---|
| Variable role (7 roles), role provenance, driven_by / derived_from | `mind.repsem.roles` `RoleDeclaration`, `RoleTable`, `RoleSource` | Reuse | Gen1 roles, declared and never inferred; the world embeds the declaration and builds its `RoleTable` |
| Variable identity | `RoleDeclaration.name` | Reuse | No second id scheme; names are verbatim |
| Units, dimension, conversion | `scientific.units` (`Quantity`, `normalize_unit`, `magnitude_in`, `canonical_magnitude`, `base_unit`) | Reuse | Compatibility is the owner's conversion (`base.converts`); 12-digit base-unit keys only match a proposal to a declared level or a restated fixed value |
| Physical meaning | `scientific.semantics.QuantitySemantics` | Reuse (optional) | `None` = undeclared, never inferred |
| Continuous / integer / categorical / boolean domains | `ScientificVariable(role=CONTROL)` + `ScientificValue` | Adapt | Continuous and integer membership call the owner's `require_within_bounds`; categorical and boolean are checked by kind. An integer, categorical or boolean domain is stated in its variable's own unit |
| Discrete unit-bearing levels | none (`VariableKind` is frozen, has no DISCRETE) | Missing → `DiscreteLevels` | The exact Gen1 failure class |
| Conditional constraints / activation | none (grammar refuses continuous consequences; `RangeCondition.requires` is applicability authority) | Missing → `Guard` + `DeclaredConstraint` over a reused `ConstraintDefinition` | Scope is declared, never inferred; outcomes use `design.grammar.ConstraintStatus` |
| Fixed conditions | `ScientificParameter` | Reuse | A parameter is held, a variable varied |
| Preconditions | `ConstraintDefinition` | Reuse | Checked at the edges of the current value's uncertainty |
| Current value + uncertainty | `Uncertainty` (UNKNOWN default) | Reuse | Value slot is new: `NamedQuantity` is Quantity-only and ASCII-id-only |
| Value origin, record binding | none spanning measurement / estimate / computation / declaration | Missing → `ValueOrigin` + typed `RecordRef`, `binders.py` | Copies from `SystemState` and `CalibratedMeasurementObservation` (exact owner types); `verify_bindings` re-reads them. **Round-2 finding: nothing on the admission path calls it (§6)** |
| State / twin / revision | `SystemState`, `TwinRevision`, `ScientificTwin` | Reference only | The world never computes or commits state |
| Revision lineage | `TwinRevision`, `CharterAmendment` | Adapt (pattern) | `Lineage` + `derive()` + `verify_lineage()` + `restatement_problem()` |
| Model applicability | `ScientificModelDefinition.assess_validity` / `ValidityDomain` / `ValidityStatus` | Reuse | Verbatim for exact inputs; gates model execution only |
| Provider availability / health / requirement | `ProviderStatus`, `ProviderHealthReport`, `ProviderBinding`, preflight codes | Reuse | Embedded verbatim; the owner's `executable` rule rebuilt from the payload |
| Action family | `sria.decision.ActionFamily` | Reuse | No fourth planning vocabulary |
| OBSERVE vs INTERVENE; model execution vs system query | none (`ExecutorType` is who executes) | Missing → `ActionMode`, `ExecutionKind` | Declared on each action |
| Proposer identity, external intake | `ProposalProvenance`, `ExternalSuggestion` + `AUTHORITY_KEYS` | Reuse | A language-model proposal carries its certified suggestion; the check re-derives it |
| Experiment count / compute / cost budget | `ExperimentBudget`, `ResourceBudget` + `ResourceUsage`, `BudgetPlan` | Reuse (composed) | Decided by the owners' rules on raw amounts. **Round-2 finding: the budget statement is unverifiable (`BudgetLedger` has no digest)** |
| Feasibility status with structured reasons | none (`FeasibilityVerdict` is a bool; preflight is system-runtime specific) | Missing → `FeasibilityDecision` | Exported to SRIA as `FeasibilityVerdict`, definite infeasibilities only |
| Replay vocabulary | `sria.decision.replay.ReplayResult` / `ReplayOutcome` | Reuse | No third outcome set |
| Canonical digest | `mind.repsem.canonical_bytes` (strict) | Reuse | Identity is the raw owner payload |

## 2. The contract (as of `3cbe0a8c`)

**ScientificWorld** (`world.py`). A frozen, content-addressed view. It carries every field the brief lists:

- WORLD_ID and REVISION (`Lineage`);
- ENTITIES, VARIABLES, RELATIONSHIPS (derived from the role table), CONSTRAINTS;
- AVAILABLE_ACTIONS, OBSERVABLES (declared `ObservationChannel` records), LATENT_QUANTITIES;
- APPLICABILITY (`ApplicabilityBinding` over model records);
- UNCERTAINTY (UNKNOWN by default), BUDGET, PROVENANCE (declarer, basis, typed references).

Each variable binds an identity, a unit validated through the registry, a role, a domain (`None` = no declared
range), a current value with its origin and owner record, and an uncertainty. Observability, controllability and the
applicability bindings that read the variable are derived views, never declared.

Identity:

- `content_digest` covers material fields only. Labels and descriptions are not identity.
- Material fields enter identity as the raw owner payloads. Two worlds that any check or execution could tell apart
  have two identities. A respelled level (1000 mA for 1 A) is a new revision.
- `revision_id` = digest(content, revision, parent, changed fields).
- `derive()` refuses a change that changes nothing. It refuses a bound value or budget statement that changes while
  citing the same owner record (`restatement_problem`), and it re-verifies the parent's own content first.
- `verify_lineage` applies the same rule along a chain.

**Role semantics with behaviour** (enforced when an action binds to a world, and again at the check):

| Role | Behaviour |
|---|---|
| CONTROLLED_INPUT | set only through a declared control of the action, inside its domain; else `CONTROL_NOT_OFFERED_BY_ACTION` |
| FIXED_PROTOCOL_CONDITION | selectable only among finite levels declared by protocol metadata; otherwise a fixed condition (`FIXED_CONDITION_CHANGED`, `PROTOCOL_CONDITION_NOT_SELECTABLE`) |
| STATE_VARIABLE | set only by a separate explicit state-intervention action; else `STATE_NOT_DIRECTLY_SETTABLE`; its value is never DECLARED |
| MEASUREMENT | observable through a channel; never a control |
| DERIVED_QUANTITY | COMPUTED only; never a control, channel or OBSERVE target |
| LATENT_PARAMETER | never a control, channel, observable or OBSERVE target; never OBSERVED |
| NUISANCE_VARIABLE | observable; never a control |

**FeasibleActionSpace and its check** (`feasibility.py`). `check(proposal)` returns a `FeasibilityDecision`
classified `action_feasibility_not_scientific_support`.

| Status | Meaning |
|---|---|
| FEASIBLE | all nine families ran, none left a reason |
| INFEASIBLE_DOMAIN | outside a domain the problem specification declares; wrong dimension or kind; a variable the action does not offer |
| INFEASIBLE_PROTOCOL | outside a limit the protocol metadata declares |
| INFEASIBLE_STATE | a state set directly, a violated precondition, or a current value outside its domain |
| INFEASIBLE_APPLICABILITY | a model execution outside its model's validity domain: the core status verbatim for exact inputs (`OUTSIDE_VALIDATED_DOMAIN`); the world's interval rule has its own code (`INTERVAL_OUTSIDE_VALIDATED_DOMAIN`) |
| INFEASIBLE_PROVIDER | the provider's own codes |
| INFEASIBLE_BUDGET | more than the budget statement says remains |
| MISSING_INFORMATION | anything absent or undecidable: never a default, never FEASIBLE |

Nine check families run on every proposal: action, role, domain, observe, protocol, state, applicability, provider,
budget. Reasons are collected and never short-circuited. Precedence: DOMAIN > PROTOCOL > STATE > APPLICABILITY >
PROVIDER > BUDGET > MISSING_INFORMATION. Reason codes and annotation keys are closed sets. Values are never clamped or
projected. `alternatives()` lists declared members that would be FEASIBLE, labelled "admissible options under the
declared world, not recommendations".

**Mind integration** (`port.py`). `MindWorldPort` lets the Mind read the world and the action space, and propose. It
holds a detached copy and no executor or provider. A FEASIBLE decision yields a `ClearedAction`: an admitted-action
record with a closed configuration and a context of every other value the decision read, each with its owner record or
declared basis. Nothing in the package dispatches.

The research `ExecutionGate` was removed in round 2 (§6). Delivering an admitted action into the existing execution
system is not built. No Ax, BoTorch, PySINDy, PySR, hypothesis portfolio, search tree, attempt memory or model critic
was installed or built.

## 3. History

| Commit | What |
|---|---|
| `9d71df1c` | failing-first tests A–M, seven role invariants, import boundary, four cross-domain fixtures. At this commit both test modules fail at collection (`ModuleNotFoundError: engcore.mind.world`) |
| `6007e7aa` | implementation; 36/36 pass |
| `a2d5d94e` | 44 contract tests from the design review |
| `4998dc2e` | 515 cases frozen before any arm ran |
| `93368e06`, `193abd84` | arms, Gen1 reproduction, runner; first results |
| `5b27dbad` | round-0 authority fix batch (gate re-derives, owner bounds, owner-typed bindings, interval applicability per side, intake revision binding) |
| `575faaa3` | round-1 re-verification failure, gate-removal rationale and **the stopping rule**, committed before round 2 |
| `cc3a3d60`, `08602f75` | round-2 fixes; gate removed; one case-generator bug fixed after a failed run |
| `67cfcf37`, `3cbe0a8c` | round-2 results |

## 4. Cross-domain fixtures and the Gen1 failure class

There are five synthetic worlds over four systems: a battery pulse cell, an HVAC climate chamber, an HVAC field
task, a quadrotor and an electric motor. In the two HVAC tasks the same `T_out` is a fixed protocol condition in one
and a passive nuisance in the other. Every role, domain kind and status appears in at least two worlds. These are
contract fixtures, not scientific claims.

**§15, the Gen1 failure class** (`results/GEN1_REPRODUCTION.json`). The protocol offers I ∈ {1.0 A, 2.0 A} and
t_on ∈ [20, 200] s.

| | GEN1_STYLE_PROPOSAL `I_A = 1.15 A` | Gen1's own initial design (seed 0): 10 requests between 1.097 A and 1.949 A |
|---|---|---|
| GEN1_ROLE_ONLY (real Gen1 code, box [1, 2] A) | FEASIBLE | 10/10 FEASIBLE |
| GEN2_WORLD_ACTIONSPACE | INFEASIBLE_PROTOCOL, `LEVEL_NOT_DECLARED`, with the declared levels | 10/10 INFEASIBLE_PROTOCOL |
| Declared alternatives for I_A | 1.0 A, 2.0 A | 1.0 A, 2.0 A for every request |

This is a grounding improvement, not a scientific-performance improvement. It reproduces the CLASS of the v1 failure,
a protocol level that is not offered. It does not reproduce v1's recorded-pool mechanics.

## 5. Measurement, ablation, performance

**Cases.** 515 cases were frozen at `4998dc2e` before either arm ran. Each case is a declared mutation of a
FEASIBLE-by-construction base proposal. `oracle.py`, the expected-outcome oracle, imports nothing from
`engcore.mind.world`. One author wrote the oracle, the generator and the checker, so agreement shows consistency with
one reading of the brief, not correctness.

The file was regenerated twice, and every change is disclosed:

- **Round 0 (`5b27dbad`).** A restated reading cites a new synthetic record. All 515 records stayed byte-identical.
- **Round 2 (`cc3a3d60`, `08602f75`).** The oracle was amended for the world's interval code. 513 records are
  identical. Two changed their code, with the same status:
  - `drone/value:wind/simulate_flight`, `OUTSIDE_VALIDATED_DOMAIN` → `INTERVAL_OUTSIDE_VALIDATED_DOMAIN`;
  - `hvac_field/value:T_out/simulate_building`, the same change.

**Runs** (Run Observatory v1, ledger `D:/forge-run-ledger`, unmodified; observatory checkouts `578ff981`, `1ce0d573`,
`ba9887a6` as found):

| Run | What | Code | Result |
|---|---|---|---|
| `20261022T114747Z-b0031e2f00a94ea5` / `20261022T114757Z-da10950bd4e64e9a` | Gen1 reproduction / benchmark, before any fix | `93368e06` | RUN_PASS |
| `20261022T122439Z-b9f04e8811e94995` / `20261022T122525Z-99f5fc35579046f8` | after round 0, clean tree | `5b27dbad` / `8bdda7c1` | RUN_PASS |
| `20261022T122455Z-cb5111ea69a640b4` | benchmark with an uncommitted output in the tree | `5b27dbad` | superseded |
| `20261022T132120Z-b3cc1f0dd5664d80` | Gen1 reproduction after round 2, clean tree | `cc3a3d60` | RUN_PASS |
| `20261022T132132Z-aae3ce78b0be4d68` | benchmark after round 2 | `67cfcf37` | **RUN_FAIL** (case-generator bug, fixed in `08602f75`) |
| `20261022T132208Z-86d9280a10f14b0c` | benchmark after round 2, clean tree | `08602f75` | RUN_PASS (the results reported here) |

Every score is identical across all passing runs.

| Metric | GEN2_WORLD_ACTIONSPACE | GEN1_ROLE_ONLY (on the 139 cases Gen1 can pose) |
|---|---|---|
| Valid actions found FEASIBLE | 78/78 | 15/22 |
| Invalid actions found NOT_FEASIBLE | 437/437 | 65/117 |
| False FEASIBLE | 0 | 52 |
| False NOT_FEASIBLE | 0 | 7 |
| Typed status / reason codes correct | 515/515 / 515/515 | N/A (a bool and one string) |
| Not posable in Gen1 | — | 376 |
| Unit errors | 30/30 refused with `UNIT_INCOMPATIBLE` | 7 of the 9 it could pose found FEASIBLE |
| Cross-domain | 5/5 worlds at 1.0; 38/38 mutation kinds correct in every world (34 with one status; 4 differ by declarer, by design) | — |
| Replay | 515/515 REPRODUCED | — |
| Serialization | 52/52 world variants byte-identical; decision digest identical under PYTHONHASHSEED 0 and 4242 | — |

**These scores do not detect the authority defects in §6.** Every fixture binds its values to trusted synthetic
records, and no case attacks the trust in a copy.

**Performance** (`results/PERFORMANCE.json`, run `…86d9280a10f14b0c`; Windows 11, Python 3.14.2, 24 logical CPUs,
loaded machine; medians over 25 builds; 2575 check samples):

| WORLD_BUILD_MS | ACTIONSPACE_BUILD_MS | FEASIBILITY_P50_MS | FEASIBILITY_P95_MS | SERIALIZED_WORLD_BYTES |
|---|---|---|---|---|
| 0.856 | 0.256 | 0.140 | 0.263 | 17 559 – 22 647 |

The in-repo reference is one Gen1 repsem judgment, a SciPy least-squares model fit, which takes 88.2 ms in the same
run. A check is roughly 600 times cheaper than that fit. No unexpectedly large overhead was found. A world's payload
is dominated by the embedded owner records.

## 6. Authority review (brief §22)

Three read-only reviews ran.

- **Round 0.** Two independent lenses, at `193abd84`.
- **Round 1.** Eight skeptics, one per question, plus a critic, at `282b4d58`, after the round-0 fixes.
- **Round 2.** The same structure at `3cbe0a8c`, after the round-1 fixes.

Every round re-ran the earlier probes against the current code and wrote new ones. Probe scripts and outputs were
kept in the session scratchpad and are not committed. The verdicts are YES (duplication or bypass), PARTIAL (only
MINOR issues) and NO.

| Question | Round 0 (lens 1 / lens 2) | Round 1 | Round 2 |
|---|---|---|---|
| Q1 second state authority | YES / YES | YES | **YES** |
| Q2 second applicability authority | PARTIAL / YES | YES | **YES** |
| Q3 duplicate units | PARTIAL / PARTIAL | YES | **YES** |
| Q4 duplicate design / search-space concepts | YES / PARTIAL | YES | **YES** |
| Q5 world issues scientific verdicts | NO / NO | YES | **YES** |
| Q6 external proposer bypasses admission | PARTIAL / PARTIAL | PARTIAL | **YES** |
| Q7 provider executes an unadmitted action | YES / YES | YES | PARTIAL |
| Layering, Gen1 pins, frozen artifacts | — / NO | NO | NO |
| Findings | several BLOCKERs | 1 BLOCKER, 16 MAJOR, 20 MINOR | 0 BLOCKER, 15 MAJOR, 24 MINOR |

**Round-2 MAJOR findings**:

- **State (Q1).**
  - Admission is decided on the world's unverified state copy. Nothing on the path Mind → proposal → check → clear
    calls `verify_bindings`; the removed gate was its only caller.
  - The restatement rule only checks that a reference is new, so a state can be advanced to any value by citing a
    fresh, synthetic or older reference.
  - Which state is current is decided by a world rule over the records the caller happens to supply.
- **Applicability (Q2).**
  - Admission is decided on the world's unverified copy of the model record (`verify_models` is never called on the
    admission path).
  - An interval stated at 10 % coverage is used as a hard enclosure.
- **Units (Q3).** Hop-wise conversion through kelvin admits a temperature difference for a point variable.
- **Design (Q4).**
  - The world's `contained()` rule stands in for the owner's pointwise check, so a value the variable's own domain
    refuses can be cleared.
  - The budget statement is an unverifiable restatement: any record kind may be its authority, and the owner
    `BudgetLedger` has no digest.
- **Verdicts (Q5).** Interval rules ignore a declared `confidence_level`.
- **Intake (Q6).** A `str`-subclass variable name survives `canonical()`. A configuration the check never read, a
  directly set state included, reaches FEASIBLE and a `ClearedAction`.
- **Execution (Q7).**
  - `clear()` can record a configuration other than the one it decided.
  - A `ClearedAction` can be built or loaded for an unchecked configuration, and nothing can verify it.
- **Critic.**
  - Lineage laundering: unbind, then re-bind the same owner reference with another value.
  - A DECLARED set point's stated uncertainty is treated as zero at the applicability gate.
  - Provider snapshots are not verified against the provider authority at admission.

**Independently reproduced** by the main session (`scratchpad/spotcheck_r2.py`, not a reviewer script):

- A 10 %-coverage interval [0.105, 0.115] against a 0.1 floor gives **FEASIBLE**. The same value with a STANDARD
  uncertainty gives MISSING_INFORMATION.
- SOC is unbound, then re-bound to **the same owner reference** with 0.05. Both revisions are accepted,
  `verify_lineage` verifies all three, and the decision flips FEASIBLE → INFEASIBLE_STATE.
- SOC bound to a SYSTEM_STATE digest that no record holds still yields FEASIBLE and a `ClearedAction`.

**Structural cause.** BR1 asked the world to be a read-only reasoning view and also the place where admission is
decided. A view over owner records can only admit soundly if admission verifies those records with their owners. That
needs four things:

- the state owner's current state, with run and system identity;
- the model registry;
- the live provider authority;
- a budget ledger with a verifiable digest.

Two of those owners expose no verifiable record today: `BudgetLedger` has no digest, and no head-state view exists.
Every attempt to close the gap inside `engcore.mind.world` added another world-made rule: dispatch ledgers, currency
rules, coverage, containment, lineage. Each rule became a second authority in turn. Round 0's "a gate inside the Mind
package" and round 2's "no gate, a record only" both failed for this reason.

**Requirements for the owner-reviewed next step.** These are not done here; this is the list the round-1 review asked
to see in the tree:

1. Admission (`clear`) takes the owners' records and verifies them, or refuses: the bound values against the state
   owner's head state (same system and run), the model records against `ModelRegistry`, the provider snapshots against
   the live provider authority (typed `ProviderStatus`), and the budget against a ledger record with a digest. This
   needs a `BudgetLedger` digest and a head-state view, both owner changes.
2. A coverage policy for interval uncertainty, owned by the core. A coverage below 1 never serves as an enclosure.
3. The restatement rule is checked over the whole lineage. An owner reference never carries two values, even with an
   unbound revision between them.
4. Unit identity keeps the owner's difference flag, and compatibility is one rule (the owner's `canonical_value` /
   `is_delta_unit`).
5. The world's containment check uses the owner's pointwise rule, or refuses.
6. Names and values are rebuilt as exact builtin types in `canonical()`.
7. A `ClearedAction` verifier (re-derive and compare) that any consumer must call. The record carries the execution
   kind, the provider binding, the model and the synthetic status.
8. Execution wiring is the execution owner's job:
   - an owner-declared mapping from action to execution kind to executor;
   - a persistent, atomic reservation keyed by the owner's budget statement;
   - no dispatch of synthetic worlds;
   - state staleness after a dispatch.

## 7. Final table (brief §24)

| Axis | Before Gen2 | After BR1 | Status |
|---|---|---|---|
| WORLD_MODEL | role labels only | `ScientificWorld`: 7 roles with behaviour, typed domains, owner-bound values, channels, applicability, provider snapshots, budget, lineage | IMPLEMENTED on synthetic fixtures; owner verification not on the admission path |
| ROLE_BEHAVIOR | partial | all 7 roles enforced at bind and check, in 5 worlds | PASS (development) |
| ACTION_SPACE | none/minimal | `FeasibleActionSpace`: 8 typed statuses, 9 families, closed reason codes, declared alternatives | IMPLEMENTED |
| DISCRETE_FEASIBILITY | Gen1 box admitted 1.15 A | 1.15 A INFEASIBLE_PROTOCOL, never clamped; alternatives 1.0 A, 2.0 A | PASS |
| CONTINUOUS_FEASIBILITY | Gen1 box hulls | owner `require_within_bounds`, exact | PARTIAL: world containment rule (round-2 MAJOR) |
| FIXED_PROTOCOL | none | fixed conditions; protocol-only selection | PASS |
| STATE_VS_CONTROL | Gen1 interventional roles | a state is set only by an explicit state intervention | PARTIAL: admission on unverified state copies (MAJOR) |
| UNIT_ENFORCEMENT | unvalidated strings | owner conversion; 30/30 unit errors refused | PARTIAL: kelvin bridge admits a difference for a point (MAJOR) |
| APPLICABILITY | none | core status verbatim for exact inputs; world interval rule with its own code | PARTIAL: coverage ignored, model record unverified at admission (MAJOR) |
| PROVIDER_FEASIBILITY | none | owner status and health embedded verbatim | PARTIAL: snapshot unverified at admission (MAJOR) |
| BUDGET_FEASIBILITY | Gen1 query budget only | every dimension limited or unbounded; owners' rules on raw amounts | PARTIAL: budget statement unverifiable (MAJOR) |
| CROSS_DOMAIN | battery only | 5 worlds, 4 systems; 38/38 kinds correct in every world | PASS (synthetic) |
| REPLAY | none | 515/515 REPRODUCED; byte-identical round trips; hash-seed independent | PASS |
| AUTHORITY_DUPLICATION | 0 required | round 2: YES on Q1–Q6, 15 MAJOR | **FAIL: BLOCKER** |

On the 515 frozen synthetic cases:

- VALID_ACTIONS_ADMITTED **78/78**;
- INVALID_ACTIONS_REJECTED **437/437**;
- FALSE_ADMISSIONS **0**;
- FALSE_REJECTIONS **0**.

These counters keep the brief's names. "Admitted" means found FEASIBLE by the action-feasibility check, never
evidence admission. Performance:

- WORLD_BUILD_MS 0.856;
- ACTIONSPACE_BUILD_MS 0.256;
- FEASIBILITY_P50_MS 0.140;
- FEASIBILITY_P95_MS 0.263;
- SERIALIZED_WORLD_BYTES 17 559 – 22 647.

## 8. Decisions recorded, not defaulted

- **INFEASIBLE_APPLICABILITY** is an eighth status. Folding model applicability into DOMAIN or PROVIDER would hide
  which authority refused.
- **A provider limit such as "unavailable above a temperature"** is expressed as the validity domain of the model the
  provider route executes.
- **Explicit state interventions are kept** (brief §6), as separate actions only. Which ActionFamily labels state
  preparation is an open owner decision.
- **Time-series controls are refused in BR1.** A scalar would silently mean a constant profile.
- **Monotonicity is about information about the system.** That information is values, uncertainties, provider
  statements and budget statements, and removing it never improves an answer. Withdrawing a declared domain,
  constraint or precondition changes the question instead. The round-2 review still rates the domain case MINOR.
- **The research gate was removed** (rationale in `575faaa3`). The round-2 review agreed for its dispatch, ledger and
  reservation functions. It did not agree for binding verification and the synthetic refusal, which were dropped
  rather than moved into admission (§6, requirement 1).
- **Governance.** EXC-MIND-1 does not cover a new Mind subpackage. Any merge needs an exception amendment or an epic
  decision, and OD-3, because new `tests/**` files are a recertification trigger.

## 9. Development conclusion

**AUTHORITY_DUPLICATION_BLOCKER.**

The world model, the role semantics, the typed feasibility statuses, the never-clamp rule, the declared alternatives
and replay all work, and the check is about 0.14 ms. But the round-2 authority review answers YES on six of seven
questions with MAJOR findings. The three main ones were reproduced independently:

- admission on unverified owner copies;
- coverage intervals used as enclosures;
- an owner reference re-bound to a new value through an unbound revision.

By the stopping rule committed beforehand, BR1 stops here without a third fix round. Resolving the blocker needs owner
decisions (§6, requirements 1–8): a verifiable budget ledger, a head-state view, a core coverage policy, and where
admission verification lives. BR1 claims nothing SCIENTIFICALLY_VERIFIED, CERTIFIED or FORMAL, and does not claim
GEN2_OUTPERFORMS_GEN1_SCIENTIFICALLY.
