# GEN2-BR1.1 — Authority-Bound ScientificWorld + Non-Bypassable Action Admission

**Development conclusion: see §12** (filled in when the review loop closes).

GEN2-BR1 (`benchmarks/mind_gen2_world_v1/README.md`) ended AUTHORITY_DUPLICATION_BLOCKER: admission was decided on
world copies of owner records that nothing verified with their owners. BR1.1 is the repair campaign. It makes
`ScientificWorld` a versioned, read-only, verifiable projection of FORGE's canonical owners, and it makes action
admission and dispatch non-bypassable. This is development evidence on synthetic contract fixtures only: no real data,
no scientific claim, nothing certified or formal. Generation 1 stays sealed and byte-identical (`gen1_reference
--check`: INTACT).

- **Branch:** `research/mind-gen2-authority-binding-v1`, from `1202ea6c3d96f5c31d0b142a32438da75e020cae` (BR1's
  report commit). Local only: not pushed, not merged, not certified.
- **Code:** `src/engcore/mind/world/` (new: `authority.py`, `owners.py`, `declaration.py`, `projection.py`,
  `admission.py`; changed: `__init__.py`, `world.py`, `feasibility.py`, `variables.py`, `base.py`, `actions.py`,
  `domains.py`, `port.py`; removed: `binders.py`). One owner file outside the package: `src/engcore/sria/campaign/budget.py`
  (read-only `BudgetLedger.digest` / `revision`).
- **Tests:** `tests/mind/test_authority_{failing_first,mutations,cross_domain,review_r1,review_r2,review_r3,review_r4}.py`,
  `tests/test_sria_budget_ledger_identity.py`; BR1's tests adapted where §3's interval rule requires
  (`tests/mind/test_world_{failing_first,contract}.py`, `benchmarks/mind_gen2_world_v1/tests`).
- **Benchmark:** this directory (`fixtures.py`, `mutations.py`, `run_benchmark.py`, `rescore.py`,
  `br1_decisions.py`, `results/`).

## 1. The eight BR1 requirements (repair matrix)

| # | Requirement (BR1 §6) | Canonical owner | BR1 defect | Invariant now | Change | Tests |
|---|---|---|---|---|---|---|
| 1 | Admission verifies the owners' records or refuses | `system_runtime` run record (state); `scientific.ModelRegistry`; `providers.ProviderRegistry` + `health`; `sria.campaign.BudgetLedger` / `ScientificExperiment`; the declaration in force; `scientific.units` | admission decided on unverified copies; `BudgetLedger` had no digest; no head-state view | every projected fact carries an `AuthorityBinding`; `admit` rebuilds the world from its payload, verifies every binding against its live owner and that the world is exactly the owners' fresh projection, then decides and mints on that projection; any failure is MISSING_INFORMATION with an AUTHORITY reason | `authority.py`, `owners.py`, `projection.py`, `admission.py`; `BudgetLedger.digest` / `.revision` (owner addition); head state read from `SystemRunResult.final_state` / `SystemCheckpoint.state` (no owner change) | failing-first C–H, M; mutations (101 cases); cross-domain; review r1/r2 |
| 2 | A coverage below 1 is never an enclosure | core `Uncertainty` | a 10 %-coverage interval proved containment (FEASIBLE) | no current value of a world decides a containment, whatever its uncertainty's kind, coverage or source (§3); the core states no enclosure form and no decision-coverage policy, so the decision fails closed | `feasibility._world_basis`, `_check_state`; codes `*_ENCLOSURE_REQUIRED` | failing-first A (3); review r1 |
| 3 | The restatement rule holds over the whole lineage | owner record identity | unbind, then re-bind the same reference with another value | an owner statement carries one value from root to leaf; `verify_lineage` walks the store; lineage v2 records ancestors' statements | `Lineage.bound`, `restatement_problem`, `verify_lineage`, lineage schema v2 | failing-first B (2); mutations; review r1 |
| 4 | Units keep the difference flag; one compatibility rule | `scientific.units` | kelvin bridged a difference into a point | `converts()` = owner conversion AND equal difference flags; the world binds the sealed registry fingerprint; every budget amount is converted by the unit owner | `base.converts`, `UNIT_REGISTRY` binding, budget unit rules | failing-first I (4); review r2 |
| 5 | Containment uses the owner's pointwise rule | variable domain (`require_within_bounds`) | the world's `contained()` stood in | the variable's own domain is checked pointwise at every check | `feasibility._check_domains` | failing-first R5 |
| 6 | Names and values are exact builtin types | `feasibility.canonical` | a `str` subclass survived | every proposal is rebuilt from its payload with exact types; intake normalizes look-alike keys and requires canonical value payloads | `canonical`, `actions._key_form` | failing-first R6, K; review r1 |
| 7 | A verifier every consumer must call | (BR1 `ClearedAction`, removed) | a `ClearedAction` could be built or loaded for an unchecked configuration | `AdmittedAction` is minted only by admission; `authorize_dispatch` re-admits it against the live owners and requires the identical digest; `DispatchAuthorization.verify()` and `verify_authorization` re-derive what an executor holds | `admission.py` | failing-first J, K, L; mutations (10 fields); review r1/r2 |
| 8 | Execution wiring belongs to the execution owner | the execution side | a Mind-side dispatch ledger (BR1 round 0) | the execution side holds the live readers and the executor (`ExecutionDesk`, immutable); the Mind holds an `AdmissionGateway` only; synthetic worlds are refused unless the executor accepts them; the desk records no effects and reserves no budget (stated, §4) | `ExecutionDesk`, `AdmissionGateway`, `_GuardedExecutor` | failing-first L; review r1 |

## 2. Design

(See the module docstrings for the exact contracts; this is the map.)

```text
ProtocolDeclaration (held in force by the execution side) ─┐
system_runtime run record (head state; the execution side   │
  states which record is the head)                         │  project_world(declaration, authorities)
scientific.ModelRegistry ──────────────────────────────────┼──────────────────────────────────────► ScientificWorld
providers.ProviderRegistry + assess_health ────────────────┤      (a root world; every projected fact bound)
sria.campaign.BudgetLedger / ScientificExperiment ─────────┤
scientific.units sealed registry ──────────────────────────┘
                                       Mind ── MindWorldPort ── ProposedAction ── AdmissionGateway.admit
admit: rebuild the world from its payload ─ verify every binding now ─ world == the owners' fresh projection
       ─ decide on that projection (the feasibility check) ─ FEASIBLE only: AdmittedAction (minted by admission only)
                                       Mind ── AdmissionGateway.dispatch(AdmittedAction)
ExecutionDesk (immutable; live readers; the execution owner's executor behind a guard)
       ─ authorize_dispatch: re-admit NOW, identical admitted digest ─ DispatchAuthorization (fresh, self-verifying)
```

- **Bindings.** `AuthorityBinding` = owner kind, owner instance, record id, revision, the owner's record digest,
  projected fields, a digest of exactly what was projected; `bound_at` is metadata. World identity covers every
  binding's identity.
- **Owners** (`owners.py`):

| Owner kind | Owner | Record / revision / digest | Owner change |
|---|---|---|---|
| SYSTEM_STATE | `system_runtime` `SystemRunResult` / `SystemCheckpoint` (`RunStateReader.following` re-asks the execution side for the head; a head never goes back) | (state owner, variable) of the head state; sequence; `SystemState.digest`; superseded states give STALE, unknown digests MISSING | none |
| MODEL_RECORD | `scientific.ModelRegistry` (exact `ScientificModelDefinition`) | (model, version); sha256 of `engcore.scientific.to_json` (world-derived: the model defines no digest) | none |
| PROVIDER_STATUS | `providers.ProviderRegistry.status` (the owner's cache, or `refresh=True`) + `providers.health.assess_health` | provider id; version; the health report's status-digest rule | none |
| BUDGET_LEDGER | `sria.campaign.BudgetLedger` (`BudgetReader.following` for replaced account objects; an account never goes back a revision) | ledger id; settled charges; `canonical_digest` of `to_dict()` in the form `from_dict` reads it back | **added** read-only `digest` / `revision` |
| EXPERIMENT | `scientific.experiments.ScientificExperiment` | experiment id; evaluations; sha256 of `to_json` (world-derived) | none |
| DECLARATION | the `ProtocolDeclaration` in force, held detached (`DeclarationReader.following`: revisions only move forward, one content per revision) | declaration id; revision; content digest | none (no canonical protocol owner) |
| UNIT_REGISTRY | `scientific.units` | `registry_fingerprint()` after `verify_registry_unmutated()` | none |

- **Liveness** is derived from the reader's type and mode at every call: registry, ledger, experiment and unit readers
  read mutable owner objects; following readers re-ask the execution side; fixed records, snapshots, memos and
  look-alikes are not live. Only live readers back a desk or `authorize_dispatch`. Liveness states the MODE; which
  record is current is the execution side's statement.
- **Admission** never decides on the caller's object (a frozen record edited in place is not the world its identity
  names, and the rebuild refuses it) and mints on the owners' fresh projection (no caller-written text reaches an
  executor).
- **Decided = executed** (as requested; realization uncertainty is not assessed, `CONFIGURATION_BASIS`). Every family
  decides on each control assignment and fixed condition AS IT WILL BE EXECUTED (in its variable's declared unit by the
  unit owner's conversion; a declared discrete level of the action's or the variable's own domain as that level; an
  integer as the exact integer), and a fixed condition is checked against its variable's own domain as executed, at
  bind and at every check. Admission builds the configuration it mints from its sources by a separate path, and refuses
  to mint unless every exact value any family read in the check (recorded in the decision, outside its identity) equals
  the value minted; the executor's settings are their magnitudes. The proposal keeps the proposer's spelling; refusal
  records carry both. (Rounds 2, 3 and 4 found a BLOCKER or MAJOR where the two differed.)
- **Dispatch.** The desk is immutable; it re-admits once; its executor is wrapped so that any authorization handed to it
  is re-derived, and authorizations name the providers and the models whose applicability gated them. Authorizations
  are minted from a fresh rebuild and have `verify()` for deferred execution. A desk built with `suggestions_only=True`
  admits and dispatches only proposals that carry their certified `ExternalSuggestion`; the executor guard applies the
  same policy.
- **Replay vs currentness.** `AdmissionRecord.of` (live owners only) records world, proposal, exactly the owner records
  the re-admission read (and every read an owner refused), and the result. `replay_admission` accepts a recorded owner
  payload only if it re-derives its revision and digest by the owner's own rule (state, model, provider and declaration
  records also under the identity they are filed under; a ledger or experiment account is filed under the reader's id;
  a provider report must be the owner's assessment of its status; a ledger's totals must be what its charges give), and
  only under this process's unit registry (`replay_decision` too, for a world that binds the unit registry; a BR1-style
  world binds none, and its decisions replay under this process's registry as BR1's did). A recorded run history and recorded refusals are
  replayed as recorded. BR1.1 is unmerged: records made at its intermediate development commits are not supported. REPRODUCED attests self-consistency under the owners' rules, not that the
  owners held those records; it never authorizes a dispatch.
- **Threat model.** Every record crossing the boundary is re-derived. A Python process is one trust domain: code that
  introspects private members, closures or tracebacks of execution-side objects is inside the execution side's trust
  boundary; isolating a proposer needs a process boundary.

## 3. Interval semantics (brief §9) and what it costs

No core uncertainty record is a hard enclosure (`UNKNOWN` states nothing, `STANDARD` a spread, `INTERVAL` a coverage
strictly below 1 or none), and no FORGE owner states a decision-coverage policy. So **a current value of a world never
decides a containment**: a precondition, a constraint, a variable's own declared domain or a model's validity domain
read from a current value is MISSING_INFORMATION whatever the uncertainty's kind, coverage or source. A DECLARED set point
is a current value like any other (UNKNOWN never makes it exact); an exact protocol level is the action's fixed
condition. Exact values are the proposal's assignments (for the action's controls only) and fixed conditions, as they
will be executed (§2), and they are exact as REQUESTED: realization uncertainty is not assessed (`CONFIGURATION_BASIS`).

Round 1 showed the first BR1.1 design, a declared-coverage band, to be a world-made policy at a caller-chosen level (a
1 %-coverage interval decided FEASIBLE; NUMERICAL-source intervals counted); it was removed. The cost is real: on the
owned fixtures 12 of 21 BR1 base proposals are admitted; the other 9 read a current value (a SOC, room-temperature,
velocity or winding-temperature precondition, or a model input) and are MISSING_INFORMATION with exactly those reasons.
Deciding state preconditions needs an owner capability FORGE lacks (§11).

## 4. Decisions recorded, not defaulted

- **Protocol declarations are caller-declared**: content-addressed, revisioned, held in force by the execution side.
  Verified declaration checks and every admitted action and authorization say so (`DECLARATION_HELD`,
  `DECLARATION_PROVENANCE`).
- **Budget.** One owner account (object) states one dimension. Solver-call ledgers account exactly in `dimensionless`
  (a count is never rescaled) and wall-time ledgers in a time unit; a cost ledger's source states the declared cost
  unit, and every amount is converted into the ledger's unit by the unit owner (an equal budget in another unit decides
  the same). Every ledger and cost unit is ratio-scale (`is_ratio_scale`: on an offset scale a conversion moves an
  amount's zero). The decision is the declared estimate against the owner's current account, not an owner cost
  prediction, and nothing is reserved (`BUDGET_BASIS`); dimensions the declaration leaves unbounded are listed on every
  admitted action and authorization; a refusal records the amount and the remainder the owner compared it with, in the
  ledger's unit, and which remainder that was (`general_pool`, or `validation_pool+general_pool` for a VALIDATE
  action; an experiment's `remaining_observations` or `attempt_cap`). A followed account a world binds only moves
  forward from the history the reader accepted for it (in the owner's read-back form: a restore of an unchanged account
  is the same account, a top-up with the history unchanged is a move of the owner); one that went back or rewrote its
  history is OWNER_UNAVAILABLE to that reader from then on (round 5), and adopting a new timeline is the execution
  side's statement, made with a new reader. A reader cannot refuse a state it never observed (a spend and a rollback
  both between two verifications look like no change); at-most-once execution is the execution owner's. Admission
  cost grows linearly with a bound ledger's settled charges (§8). The observation rule
  restates `ScientificExperiment.record`, pinned by a differential test.
- **Synthetic** means labelled synthetic by the declaration (`SYNTHETIC_BASIS`).
- **Lineage v2** records ancestors' statements; v1 (BR1) keeps its bytes and ids and verifies by walking the store. A
  projection is a root world; admission refuses a history no owner made.
- **Out of scope, no owner:** which run governs across runs, and whether an observation is current.
- **Discrete levels:** a value IS a level when the unit owner's one comparison rule says they are one value
  (`canonical_magnitude` in the base unit, 12 significant digits: the rule that keeps the declared levels distinct, and
  BR1's original rule); it is then decided and executed AS that level. Nothing else matches (no nearest level, no
  interpolation): 1.15 A against levels 1 A / 2 A is INFEASIBLE_PROTOCOL with the declared alternatives. A value the
  owner calls one level but that lies nearer another declared level matches neither (no world-made separation
  threshold: round 5 replaced the round-4 one). A value that IS
  a level is decided as the level even where its own spelling would decide otherwise at a bound (35.0000000001 degC is
  35 degC to the unit owner, and it is checked and executed as 35 degC). Round 2's 64-ulp rule was absolute at a zero
  level and was withdrawn (round 3, R3-A2).
- **Integers** are compared as exact integers; an integer domain's bounds stay within ±2**53 (the owner stores a bound
  as a float).
- **Declarations are checked as executed.** A fixed condition, and every level and range edge of an action's domain,
  is checked against its variable's own domain in the variable's unit, by the owner's bound rule, at bind and (fixed
  conditions) at every check. The cost: a domain stated in another unit than its variable can refuse its own edge by
  conversion noise (a variable in mA with own domain [0, 0.7] A: 0.7 A executes as 700.0 mA, which the owner's rule
  reads back as 0.7000000000000001 A, outside), so such a declaration fails closed; stating a domain in its variable's
  own unit avoids it. A fixed condition for a dimensioned variable is a quantity the unit owner converts (an integer,
  category or boolean is refused).
- **Who may propose:** a proposer's kind is caller-asserted; a deployment hosting an external or language-model
  proposer builds its desk with `suggestions_only=True` (the execution side's policy).

## 5. Controls

Executed at `2422014` (command and environment in `docs/work/PROGRESS.md`): `tests/mind`,
`benchmarks/mind_gen2_authority_v1/tests`, `benchmarks/mind_gen2_world_v1/tests` and
`tests/test_sria_budget_ledger_identity.py`, **511 passed** (including the expensive BR1-decision re-derivation).

| Suite | Tests | What it pins |
|---|---|---|
| `test_authority_failing_first.py` | 29 | the brief's A–O, written failing first: no interval decides; lineage laundering; stale state/model/provider/budget/declaration; missing owner; unit spelling; protocol levels (no 1.15 A, nearest or interpolation); raw proposals never execute |
| `test_authority_mutations.py` | 120 | every projected field and binding field edited, every admitted-action and authorization field edited, replay forgeries |
| `test_authority_cross_domain.py` | 32 | battery, two HVAC worlds, drone, motor: the same guarantees in each |
| `test_authority_review_r1.py` … `_r5.py` | 43 / 35 / 21 / 17 / 11 | one control per confirmed review finding; the round-3, round-4 and round-5 controls fail 20/21, 16/17 and 9/11 on the trees before their fixes (the round-5 file's 2 others are controls for round-4 fixes) |
| `test_sria_budget_ledger_identity.py` | 5 | the owner addition: read-only, wire shape unchanged, round-trip identity |
| benchmark tests | 7 | committed matrix and re-score reproduce; the re-score guard; BR1's decisions re-derived from BR1's code (expensive) |
| BR1 tests adapted (`test_world_contract.py`, `test_world_failing_first.py`, BR1 benchmark) and unchanged (`test_world_boundary.py`) | 67 / 31 / 8 / 5 | BR1's contract under §3; BR1's committed results byte-identical; the package boundary |

## 6. Owned fixtures and the authority matrix (`results/AUTHORITY.json`)

Six owned worlds (battery, hvac_chamber, hvac_field, drone, motor, Gen1's two-level pool), each projected from a
declaration through real owner objects (a `SystemCheckpoint` chain, a `ModelRegistry`, a `ProviderRegistry`,
`BudgetLedger`s, a `ScientificExperiment`, the sealed unit registry). `python -m benchmarks.mind_gen2_authority_v1.run_benchmark --check`
reproduces the file byte for byte.

| Measure | Result |
|---|---|
| BR1 base proposals admitted on owned worlds | 12 / 21 (the other 9 are MISSING_INFORMATION because they read a current value: §3) |
| owner changes after projection (state advanced or head advanced in place, model replaced, provider down or re-probed down, budget charged, declaration revised) | 0 / 37 admitted (all AUTHORITY_STALE) |
| world mutations (19 kinds × 6 worlds, 13 not applicable) | 0 / 101 admitted: 34 AUTHORITY_MISMATCH, 32 refused at rebuild, 16 AUTHORITY_MISSING, 11 AUTHORITY_STALE, 5 AUTHORITY_UNVERIFIABLE, 3 refused by the unit owner |
| replay of every base admission | 21 / 21 REPRODUCED |
| Gen1's failure class (1.15 A on levels 1 A / 2 A) | INFEASIBLE_PROTOCOL `LEVEL_NOT_DECLARED`; declared alternatives 1.0 A, 2.0 A |

## 7. BR1 re-score (`results/BR1_RESCORE.json`)

BR1's committed results are not rewritten. BR1's own decisions on its 515 frozen cases were exported by running BR1's
code at `1202ea6c` (`br1_decisions.py`; the export reproduces BR1's committed `decisions_digest`, and an expensive test
re-derives it). Against them, BR1.1 changes **259 cases: 53 in status, 206 in codes only; none toward FEASIBLE**.

| Moves | New codes (cases) | Lost codes (cases) |
|---|---|---|
| FEASIBLE → MISSING_INFORMATION 44, INFEASIBLE_STATE → MISSING_INFORMATION 7, INFEASIBLE_APPLICABILITY → MISSING_INFORMATION 2 | PRECONDITION_ENCLOSURE_REQUIRED 207, STATE_DOMAIN_ENCLOSURE_REQUIRED 60, APPLICABILITY_INPUT_NOT_EXACT 50, STATE_DOMAIN_UNDECIDABLE 1 | PRECONDITION_VIOLATED 7, CONSTRAINT_VIOLATED 4, INTERVAL_OUTSIDE_VALIDATED_DOMAIN 2, STATE_DOMAIN_UNDECIDED 2, OUTSIDE_VALIDATED_DOMAIN 1 |

`rescore.py` refuses any move toward FEASIBLE, any status move other than to MISSING_INFORMATION, any new code outside
the BR1.1 rules, and any lost code without its stated cause among the case's own BR1.1 codes (`CONDITIONAL_LOST_CODES`:
the matching undecidable code, the value having been a current value of the world; or a role refusal, the value having
been one the proposer may not set). The check is per case, not per subject: BR1's exported decisions carry codes, not
subjects. The round-3, round-4 and round-5 changes left every case's status and codes unchanged; only the decisions
digest moved (rounds 3 and 4).

## 8. Performance (`results/PERFORMANCE.json`, `results/BR1_PERFORMANCE_THIS_HOST.json`, `results/LEDGER_SIZE_CURVE.json`)

One idle host: 4 CPUs, Linux, Python 3.13.16. BR1's reported numbers were measured on another machine. For the delta,
BR1's own harness ran on BR1's 515 cases alternately on BR1's code (`1202ea6c`) and on BR1.1's code at `26d7724`, three
times each; the medians are below (`BR1_PERFORMANCE_THIS_HOST.json`, with every run and the command). Single runs on
this host differ by up to ~30 %, so deltas inside that are noise; `PERFORMANCE.json` also carries one single run of the
same harness (`br1_cases_on_br1_1_code`), which agrees within that band. The owned-world metrics are `PERFORMANCE.json`
regenerated at `2422014` (`python -m benchmarks.mind_gen2_authority_v1.run_benchmark`, 25 repeats).

| Metric (ms) | BR1 reported | BR1 code, this host | BR1.1 code, this host | Delta (this host) |
|---|---|---|---|---|
| WORLD_BUILD (BR1 cases) | 0.856 | 1.480 | 1.651 | +12 % (noise band) |
| ACTIONSPACE_BUILD | 0.256 | 0.457 | 0.386 | −16 % |
| FEASIBILITY p50 | 0.140 | 0.244 | 0.233 | −4 % (noise) |
| FEASIBILITY p95 | 0.263 | 0.479 | 0.415 | −13 % |
| check on owned worlds p50 / p95 | — | — | 0.353 / 0.551 | new |
| projection from owners (median by world) | — | — | 11.5 | new |
| owner verification p50 / p95 | — | — | 13.8 / 18.1 | new |
| admission (verify + rebuild + check + mint) p50 / p95 | — | — | 17.8 / 23.9 | new |
| dispatch authorization (re-admission) p50 / p95 | — | — | 19.2 / 24.3 | new |
| reference: one in-repo solver execution (median) | — | 163.4 | 161.9 | — |

The check is as fast as BR1's within this host's noise. Admission costs ~50× the check and stays ~8× cheaper than one
solver execution on these fixtures. Under `cProfile` (20 admissions, battery, at `26d7724`), the verified projection
takes ~71 % of admission and the unit owner's `verify_registry_unmutated` alone ~24 %. Cost grows linearly with the
bindings, the declarations in force and, measured, a bound ledger's settled charges: admission p50 20 / 34 / 38 / 197 ms
and check p50 0.40 / 0.54 / 1.2 / 8.4 ms at 0 / 10 / 100 / 1000 charges (`python -m
benchmarks.mind_gen2_authority_v1.ledger_curve`, `LEDGER_SIZE_CURVE.json`): the world carries every charge of a bound
ledger, so past ~1000 charges an admission costs about one solver execution. Nothing is cached across admissions (a
cache would be a currency claim).

## 9. Review rounds

Every round: independent read-only lenses at a fixed SHA, each told to reproduce with probes (scratch only) and to
re-check the previous round's BLOCKER/MAJOR first; every BLOCKER/MAJOR re-tested by skeptics told to refute it; then a
completeness critic. The builder did not overrule a finding: each was fixed or is recorded below with why it stays.

| Round | SHA reviewed | Lenses | Filed (B / M / m) | After skeptics | Critic | Fixed in |
|---|---|---|---|---|---|---|
| 1 | `5ee16c5` | A scientific authority, B architecture, C adversarial bypass, D replay/stale | 2 / 8 / 31 | BLOCKER C-F1 = D-F1 (a world edited in place after it was built was verified on its cached digest, admitted and dispatched); MAJOR A-F1, A-F3 (a declared coverage band decided containment on a probabilistic interval at a caller-chosen level), A-F2 (an UNKNOWN set point was exact), A-F4 = B2 (one ledger stated several budget dimensions); B1, C-F2, D-F2 downgraded to MINOR | CR-1, CR-2 filed MAJOR (role table cached outside identity; authorizations not self-verifying), fixed; CR-3..CR-7 MINOR | `36e4ac5`, `be781d5`, `5adf3e7`, `bc6980c`, `31cfa03` |
| 2 | `bc6980c` | A, B, C, D, E forge-scientific-reviewer (static) | 0 / 3 / 41 | R2-A1 (cost amount unitless), R2-B-01 = C2-F1 (one ledger under two reader ids) confirmed but MINOR: 0 BLOCKER / 0 MAJOR from the lenses | **K-F1 BLOCKER** (a fixed condition restated at 12-digit equality was decided on the restated value and dispatched at the fixed value: a strict validity endpoint and a `T_out < 35 degC` constraint were admitted and dispatched at the refuted value), K-F2..K-F6 MINOR | `1514560`, `991a4d3`, `a0378d4`, `0a0890d`, `867a6a1`, `1a87f7c` |
| 3 | `1a87f7c` | A, B, C, D, E | 6 / 0 / 23 | every BLOCKER confirmed by two skeptics (reproduce, scope): **R3-A1 = R3-B-01 = R3-C-01 = R3-D1 = E3-F1** (a level control was decided on the proposer's spelling and executed as the matched level: a strict validity endpoint or constraint at a level was admitted for one spelling and executed at the refuted level), **R3-A2** (the 64-ulp level rule was absolute at a zero level: a declared 1e-14 F level was executed as 0 F) | **K3-F1 BLOCKER** (an integer decided through a float, executed exact: int64 seeds past the bound admitted), K3-F2, K3-F3 MINOR | `d113d30` |
| 4 | `d0a0408` | A, B, C, D, E | 0 / 2 / 29 | **R4-A1 = R4-C-F1** (a fixed condition's own domain checked on its declared spelling, the converted value executed: 101.52641641114641 psi inside 700 kPa as spelled, 7.000000000000001 bar outside as executed): reproduced by both repro skeptics; both scope skeptics graded it MINOR (declared by the execution side, unreachable by a proposer); treated as MAJOR and fixed | **K4-F1 MAJOR** (the `d113d30` mint guard re-derived with the function that built the configuration, so a regression of the K-F1 kind was not caught), K4-F2..K4-F4 MINOR | `26d7724` |
| 5 | `c52dcfd` | A, B, C, D, E | 0 / 3 / 23 | **B5-F1 = R5-C-F1 = R5-D1** (the round-4 budget follower took a history it had just refused as its baseline: a rolled-back account was refused once, then re-authorized): reproduced by every repro skeptic; B5-F1 confirmed MAJOR by both its skeptics | K5-F1..K5-F3 MINOR (follower tests never showed a refusal twice; two round-4 reader fixes had no control; gates last run before 26d7724) | `2422014` |
| 6 | (this report's SHA) | A, B, C, D, E | see PROGRESS | | | |

Rounds 2, 3 and 4 asked the same question three times: is the value a decision was made on the value an executor
receives? `d113d30` answered it for controls (every family decides on the configuration as it will be executed);
`26d7724` extended it to fixed conditions and restored an independent mint check. Their regression tests fail 20/21
(`test_authority_review_r3.py` on `1a87f7c`) and 16/17 (`test_authority_review_r4.py` on `d0a0408`).

The mint check's history, stated exactly: K-F1 was closed structurally by `1514560` (a proposal's value is read only
for a control, and controls and fixed conditions are disjoint by construction). `1a87f7c` added an independent check
(configuration from the sources, compared with the families' resolution). `d113d30` built the configuration through
that same resolution, which made the check circular (K4-F1). `26d7724` builds it from the sources again and compares it
with every exact value any family read in the check; tests that re-introduce the `bc6980c` read into the shared
resolution, or a raw read into one family only, are refused at mint. A family that bypassed the shared reading path
altogether would not be seen by this check; the per-value regression tests are the control for that.

**MINOR dispositions.** Every MINOR of rounds 1–5 was fixed or is recorded as a documented residual; the builder did
not drop any silently. Round 5's, in particular: fixed — A5-F2 / R5-C-M1 / E5-F2 (the compared remainder and its
basis), A5-F3 / E5-F1 (refusals that last), A5-F4 (fixed-condition kind), A5-F5 (no separation threshold), A5-F6 /
B5-M2 / E5-F5 (gating flag), A5-F7 / B5-M3 / E5-F4 (fixed-condition refusal labels), B5-M1 / R5-C-M2 / R5-D2 (only
bound accounts are read), B5-M4 / K5-F1 / K5-F2 (tests that reproduce the defect they guard), R5-D4 / B5-M5 / E5-F6
(performance provenance, §8); documented — A5-F1 (declarations checked as executed fail closed at a converted edge,
§4), R5-D3 (`replay_decision`'s unit guard needs a world that binds the unit registry, §2), the case-level re-score
guard (§7). The documented residuals of earlier rounds are those listed in §4 and §11 (no at-most-once execution or
reservation; the declaration and synthetic labels are the declarer's; liveness is the reader's mode; the provider cache
unless `refresh=True`; the in-process trust boundary; world-derived model and experiment digests; the provider rule
restating `system_runtime` preflight; replay attests self-consistency, not provenance).

## 10. Q1–Q7

Filled when the review loop closes (round 4 verdicts; see `docs/work/PROGRESS.md`). Before = GEN2-BR1's round-2
authority review.

## 11. Owner capabilities missing (failed closed, nothing worked around)

| Capability | Who would own it | What BR1.1 does without it | Minimum addition |
|---|---|---|---|
| A hard enclosure form, or a core decision-coverage policy | `scientific` uncertainty core (CORE-016 vocabulary) | no current value decides a containment: preconditions, state domains, constraints and applicability on current values are MISSING_INFORMATION (`*_ENCLOSURE_REQUIRED`, `*_UNCERTAINTY_UNKNOWN`, `APPLICABILITY_INPUT_NOT_EXACT`); 9 of 21 base proposals are therefore not admitted | an `Uncertainty` kind that states a guaranteed bound (with its basis), or an owner-stated coverage policy per decision class, read-only to the world |
| A canonical protocol owner | an execution/protocol owner (none in FORGE) | the declaration is caller-declared, held in force by the execution side, content-addressed and revision-bound; every binding, admitted action and authorization says so (`DECLARATION_PROVENANCE`) | an owner registry of protocol declarations with revisions and digests |
| Budget reservation | `sria.campaign` (`BudgetLedger`) / the execution owner | admission decides each action alone against the account (`BUDGET_BASIS`): distinct admitted actions can over-commit one ledger before any settles; nothing is reserved | a reservation API on the ledger, called by the execution owner at dispatch |
| At-most-once execution | the execution owner (`EffectLedger.once`) | the desk records no effects; a still-admissible action re-dispatches; once the executor moves a bound owner it no longer re-admits | execution-owner wiring (out of BR1.1) |
| A provider status loader | `providers` | owner constructors only; the recorded status must round-trip exactly through `to_dict`, and the health report is re-derived from the status by `assess_health` | a `ProviderStatus.from_dict` on the owner |
| Cross-run state currency; observation currency | `system_runtime` / the execution side | out of scope: the execution side states which run governs; nothing is inferred | owner statements of governing run and observation currency |

The one owner change BR1.1 makes is additive and read-only: `BudgetLedger.digest` and `.revision`
(`src/engcore/sria/campaign/budget.py`, no field, schema or wire change). The file is CORE_CERTIFIED
(`assurance_admission`); hardened recertification is required before merge and was NOT RUN (owner decision). The
changed-file gate also marks the certified harness tests BR1.1 adds or changes (`tests/mind/test_authority_*.py`,
`tests/mind/test_world_contract.py`, `tests/mind/test_world_failing_first.py`, `tests/test_sria_budget_ledger_identity.py`)
as needing recertification.

## 12. Final table and conclusion

Filled when the review loop closes.
