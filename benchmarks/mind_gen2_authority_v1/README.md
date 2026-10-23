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
- **Tests:** `tests/mind/test_authority_{failing_first,mutations,cross_domain,review_r1,...,review_r15}.py`,
  `tests/test_sria_budget_ledger_identity.py`; BR1's tests adapted where §3's interval rule requires
  (`tests/mind/test_world_{failing_first,contract}.py`, `benchmarks/mind_gen2_world_v1/tests`).
- **Benchmark:** this directory (`fixtures.py`, `mutations.py`, `run_benchmark.py`, `rescore.py`,
  `br1_decisions.py`, `ledger_curve.py`, `results/`).

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
| BUDGET_LEDGER | `sria.campaign.BudgetLedger` (`BudgetReader.following` for replaced account objects; an account behind the history observed is refused while behind; a rewritten one, or one handed in a state its owner cannot write down and read back, for good; §4) | ledger id; settled charges; `canonical_digest` of `to_dict()` in the form `from_dict` reads it back | **added** read-only `digest` / `revision` |
| EXPERIMENT | `scientific.experiments.ScientificExperiment` (read back whole by `from_dict` from `to_json`, the rule replay uses; followed like a ledger, and refused for good when handed in a state `to_json` cannot write, §4) | experiment id; evaluations; sha256 of `to_json` (world-derived) | none |
| DECLARATION | the `ProtocolDeclaration` in force, held detached (`DeclarationReader.following`: revisions only move forward, one content per revision) | declaration id; revision; content digest | none (no canonical protocol owner) |
| UNIT_REGISTRY | `scientific.units` | `registry_fingerprint()` after `verify_registry_unmutated()` | none |

- **Liveness** is derived from the reader's type and mode at every call: registry, ledger, experiment and unit readers
  read mutable owner objects; following readers re-ask the execution side; fixed records, snapshots (including every
  following reader's pinned snapshot: run head, declaration set, budget accounts), memos and look-alikes are not live.
  Only live readers back a desk or `authorize_dispatch`. `Authorities.memoized` pins every reader when a verification
  starts, whatever the verification reads, so a following reader observes its owner at every verification (every
  admission that reaches owner verification; one refused at its rebuild observes nothing); whatever a pin raises waits
  for a read of that owner. Liveness states the MODE; which record is current is the execution side's statement.
- **Admission** never decides on the caller's object (a frozen record edited in place is not the world its identity
  names, and the rebuild refuses it) and mints on the owners' fresh projection (no caller-written text reaches an
  executor).
- **Decided = executed** (as requested; realization uncertainty is not assessed, `CONFIGURATION_BASIS`). Every family
  decides on each control assignment and fixed condition AS IT WILL BE EXECUTED (in its variable's declared unit by the
  unit owner's conversion; a declared discrete level of the action's control domain when it declares levels, else of
  the variable's own domain, as that level; an integer as the exact integer), and a fixed condition is checked against
  its variable's own domain as executed, at bind and at every check. A value of a level-set variable is decided and
  executed only as one declared level of the deciding set: the proposed (or fixed) spelling must be matched to exactly
  one level by the unit owner's identity rule (never one it is farther from; a spelling the rule does not call a
  level is refused even when its conversion is one: an underflowing subnormal, a 13+-digit level at the rule's
  rounding edge, a unit with another base unit), and its value as executed must be byte for byte THAT level as
  executed (a negative zero is not the zero level of the deciding set); the domain family refuses anything else
  (LEVEL_NOT_DECLARED, with the reason), bind applies the same rules to a fixed condition (tested as every check
  executes it, round 9), and admission refuses to mint any value that is no declared level of the deciding set, typed
  values included (an independent guard; rounds 7-9). Admission builds the
  configuration it mints from its sources by a separate path, and refuses to mint unless every exact value any family
  read in the check (recorded in the decision, outside its identity) equals the value minted; the executor's settings
  are their magnitudes. The proposal keeps the proposer's spelling; refusal records carry both. (Rounds 2, 3, 4 and 7
  found a BLOCKER or MAJOR where the two differed.)
- **Dispatch.** The desk is immutable; it re-admits once; its executor is wrapped so that any authorization handed to it
  is re-derived, and authorizations name the providers and every applicability binding of the action, each flagged
  `gating` (true only for a MODEL_EXECUTION action, whose execution the model's validity gates) or annotation-only.
  Authorizations are minted from a fresh rebuild and have `verify()` for deferred execution. A desk built with `suggestions_only=True`
  admits and dispatches only proposals that carry their certified `ExternalSuggestion`; the executor guard applies the
  same policy.
- **Replay vs currentness.** `AdmissionRecord.of` (live owners only) records world, proposal, exactly the owner records
  the re-admission read (and every read an owner refused; a pin refused for an owner that was not read is not
  recorded), and the result. `replay_admission` accepts a recorded owner
  payload only if it re-derives its revision and digest by the owner's own rule (state, model, provider and declaration
  records also under the identity they are filed under; a ledger or experiment account is filed under the reader's id;
  a provider report must be the owner's assessment of its status; a ledger's totals must be what its charges give), and
  only under this process's unit registry (`replay_decision` too, for a world that binds the unit registry; a BR1-style
  world binds none, and its decisions replay under this process's registry as BR1's did). A recorded run history and
  recorded refusals are replayed as recorded. BR1.1 is unmerged: records made at its intermediate development commits
  are not supported. REPRODUCED attests self-consistency under the owners' rules, not that the
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
altitude, velocity or winding-temperature precondition, or a model input) and are MISSING_INFORMATION with exactly those reasons.
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
  action; an experiment's `remaining_observations` or `attempt_cap`). A BR1-style world (no owner statement, never
  admitted) keeps BR1's plan rule; its OVER_BUDGET records the remainder that rule compared and its basis
  (`general_pool`, or `validation_pool+general_pool` for a VALIDATE action; `compute_budget` for solver calls and wall
  time; `remaining_observations` for experiments).
- **Followed budget accounts.** A following budget reader observes every account the execution side hands over, at
  its construction and at every verification, whatever the verification reads (`Authorities.memoized` pins every
  reader when a verification starts): a submitted world never chooses what is observed. What one `accounts()` call
  hands over is read entry by entry, so one malformed entry never hides another account (round 11, F11-2). Each of
  the two mappings is read as a dict from the dict's own storage (round 13): no code of the mapping (its truthiness,
  `__len__`, `keys`, `__iter__`, `items`) and no key's `__hash__` or `__eq__` runs, so a mapping cannot hide, add or
  merge an entry; a handing that is not a pair of dicts (a dict subclass is read as the dict it stores; `None` hands
  no account) cannot be read, and since any account in it may hold a spend, the reader refuses every account from
  then on (round 14; a new timeline is stated with a new reader). An account is named by its str id (a str subclass, such as `numpy.str_` or a
  `StrEnum` member, is read as the plain str it spells, and no code of the id runs); two entries whose keys spell one
  id (keys that differ only as objects, such as a str subclass hashing by identity) refuse that id by that reader for
  good (round 12); an entry under a key that is not a str is no account a world can bind and is not read (handing an
  account under another name is the execution side's statement of another account); an account that is not exactly
  its owner's type (`BudgetLedger`, `ScientificExperiment`) is refused by that reader for good; one object handed under
  two ids is observed under both and refused to that verification. Each account is read back by its owner from the
  text its owner writes it down as, and by no other rule: a ledger by `BudgetLedger.from_dict` from its digest rule's
  JSON (`canonical_digest`: sorted keys, `default=str`, so a value that rule stringifies, such as a `Decimal` or
  `numpy.float32` `predicted`, a date or a set `detail`, is served and digested as its `str()`, and a set's `str()`,
  which depends on the process's hash seed, makes that ledger's record digest process-dependent); an experiment whole
  by `ScientificExperiment.from_dict` from `to_json` (the rule replay uses), once per account and content, so an
  experiment holding what `to_json` cannot write (a non-float numpy scalar such as `numpy.int64`, `numpy.float32` or
  `numpy.bool_`, a `Decimal`, a set, bytes, a date, NaN) is one its owner cannot write down, while `numpy.float64`,
  enums, tuples and nested lists and dicts are read. The record served, its digest and its history are detached data a
  checkpoint restore of the same account reproduces; a served experiment record is parsed from the owner's text at
  every read (so no reader-side recursion limit, and no consumer's edit of a served record, reaches a later
  verification). Execution-side code runs inside the owner's own serialization and read-back (`to_dict`, `from_dict`,
  the JSON encoder, and the `str()` the digest rule's `default=str` and a failure's rendering run), with no lock held.
  A read-back is tried up to three times, and its failure is classified by what happens, not by the exception's type
  (round 11): any attempt that succeeds is observed; three attempts that fail alike (the same failure on the same
  text) are the state itself, which its owner cannot write down and read back, and refuse the account by that reader
  from then on (that state cannot be ordered against what was observed, and it may hold a spend); failures that
  differ, or the interpreter's own "changed during iteration" error, are an account that may have moved while it was
  serialized (an honest top-up read half-way included): not read back to that verification. Any exception the
  account's code raises is such a failure, including one that is not an `Exception` (round 13: a `BaseException`
  subclass such as `asyncio.CancelledError`); rendering a failure runs its own `__str__`, and whatever that raises is
  caught and the failure described by its type (round 12; round 13 for a `BaseException` raised there). Only a
  `KeyboardInterrupt` (or a subclass) is not a failure (round 14: `SystemExit` and `GeneratorExit` raised by account
  content are failures): the account it stopped and every account not read yet are not read back, the verification
  compares what it was handed, and the interrupt is then re-raised (round 13).
  A state handed and NOT read back is still observed as the entries of its history (round 13, replacing round 12's
  length), whatever its length (round 14: a state shorter than the history observed may be a rewind that spent): the
  entry objects its owner's container held then (a ledger's `charges` tuple, an experiment's
  `_evaluations` list, the containers the owners' `revision` and `attempts` count), listed directly with no code of the
  account run; an account whose entries cannot be listed that way is refused by that reader for good. A later state of
  that account is decided on only if its container begins with exactly those entry objects (identity, in order) both
  just before and just after its own read-back (round 14): it moved on in place, and from then on its history decides
  as for any read state; a container holding a prefix of them both times is behind; any other rewrote them (or could
  not be listed) and refuses the account by that reader from then on, as a readable state that rewrote its history
  would. An unread state whose entry objects are a prefix of (or are) those of the state whose history was last
  recorded adds no unseen entry and records nothing (round 14), so a transient failure or an interrupt with no
  new entry, then an honest unchanged checkpoint restore, does not retire the account. So the content of such a state is never observed, but no later state that does not
  extend it is decided on: a restore of the account after such a state, then any charges, is refused for good, and so
  is an object-replacing restore of unchanged content made while such a state is the latest the reader holds (identity
  is all that was observed of those entries; a fail-closed availability cost). When every attempt hits the
  interpreter's recursion limit (its own `RecursionError`, or one an owner wrapped, as the unit owner does), the same
  three attempts run once more on a fresh thread (a shallow stack), classified by the same rule, so a verification's own
  deep call stack never refuses an honest account for good; a verification waits for its fresh-thread read-backs at
  most `WAIT_S` in all (round 13), and a fresh thread still running then (it may wait on a lock the verifying caller
  holds), or one that ended without a result, leaves its account not read back to that verification, and what it does
  later reaches nothing the reader holds (it fills a private cache); while one runs, no other verification of that
  reader starts a second for the same account (round 13). An `accounts()` or read-back that reads through the reader
  it feeds on the same thread, or from the fresh thread, is refused at once; from inside the read-back that refusal
  repeats at every attempt, so the account is refused for good.
  Each verification is in flight from its start, through `accounts()` and the read-back (both with no lock held: no
  execution-side code runs under the reader's lock), to the end of its comparison with the history this reader
  observed, which holds the lock (round 13: one interrupted inside its comparison is still in flight to the
  verifications waiting for it). Every observation that extends the history is recorded, and a verification decides
  on an account only once every other verification in flight when it compared has compared too, whichever started
  first (round 10): it waits for them, holding no lock, at most `BudgetReader.WAIT_S` (1 s), then decides on what is
  observed by then (an account another verification moved past is behind; one refused for good meanwhile is refused;
  one whose state another verification was handed meanwhile and could not read back must begin with that state's
  entries, or it is refused to this verification). If one of them is still in flight after `WAIT_S`, or was handed
  accounts and left without comparing them (interrupted), it decides on no account (OWNER_UNAVAILABLE for that
  verification only; round 11). A compared verification never waits for another compared one, so no two wait for each
  other. So a state handed to a verification that started before another one compared is compared before that one
  decides, and a return to an earlier state never re-authorizes what such a state had moved past. The cost: a
  verification whose `accounts()` or read-back does not complete within `WAIT_S` (a slow execution side, or a large
  experiment whose whole read-back is quadratic) makes every verification that compares meanwhile wait `WAIT_S` and be
  refused, until it completes; an execution side that verifies while holding a lock its `accounts()` or its accounts'
  serialization takes is refused after `WAIT_S` in the same way, with no deadlock; the contention measured is in §8.
  An account only moves forward (in the owner's read-back form: a restore of an unchanged account is the same account,
  a top-up with the history unchanged is a move of the owner). An account BEHIND the longest history observed (it went
  back, or a verification's account mapping is older than one already observed) is OWNER_UNAVAILABLE to a verification
  that reads it, for as long as it is behind; a return to the state observed is that state. An account that REWROTE
  its history (neither extends it nor is a prefix of it), or the entries of a state of it handed and not read back, or
  that was handed over in a state its owner cannot write down and read back, is refused by that reader from then on
  (and is not read back again), as is every account of a reader once it was handed something that is not a pair of
  dicts; adopting a new timeline is the execution side's statement, made with a new reader (rounds 5-14). Concurrent verifications never refuse for good an account that only moved forward in place and that
  its owner reads back. A refusal that lasts (behind, rewritten, refused for good) says the same thing at every read,
  so it is recordable and replays; a refusal to one verification only (not read back, in flight, left uncompared)
  states that verification's cause, including the last failure's own text, which the execution side chooses and which
  can differ between verifications. An account no verification reads (unreadable, behind or rewritten) refuses
  nothing; the constructor of a reader the execution side builds still refuses, for the whole reader, an account set
  that is not a dict or not exactly typed, names an account by anything but a str, names two accounts by ids that
  spell one id (round 12), or registers one object under two ids. A world's binding to an account or a provider the
  declaration in force does not name (named as `project_world` binds them: the declaration's budget references and
  `providers`) is never checked against its owner (no provider is probed for it): AUTHORITY_STALE when the world's
  declaration states a numerically older revision (ASCII decimal numerals, compared as numerals; the declaration owner
  keeps no history, so a superseded revision is not told from one never held), AUTHORITY_MISMATCH otherwise; when the
  declaration cannot be read, none of that world's account or provider bindings is checked (OWNER_UNAVAILABLE if the
  declaration owner is unavailable). The follower itself still reads every handed account at every pin. What a reader
  never observes, and so cannot refuse: a state no verification was handed (a spend and its rollback both between two
  verifications look like no change), the content of a state handed and not read back (only its entry objects, above),
  an account handed under a key that is not a str, the state of a verification whose `accounts()` raises (nothing was
  handed), and that of one that leaves between being handed accounts and comparing them (an interrupt, or the
  caller's own stack exhausted, after its read-back and inside its comparison; inside the read-back either is
  re-raised only after the comparison), which only the verifications then waiting for it refuse; at-most-once execution is the execution owner's.
  Every verification reads every handed account back (the cache keeps the accounts handed over now), so admission
  cost grows with the accounts' histories (§8). The observation rule restates `ScientificExperiment.record`, pinned by
  a differential test.
- **Synthetic** means labelled synthetic by the declaration (`SYNTHETIC_BASIS`).
- **Lineage v2** records ancestors' statements; v1 (BR1) keeps its bytes and ids and verifies by walking the store. A
  projection is a root world; admission refuses a history no owner made.
- **Out of scope, no owner:** which run governs across runs, and whether an observation is current.
- **Discrete levels:** a value IS a level when the unit owner's one comparison rule says they are one value
  (`canonical_magnitude` in the base unit, 12 significant digits: the rule that keeps the declared levels distinct, and
  BR1's original rule); it is then decided and executed AS that level. Nothing else matches (no nearest level, no
  interpolation): 1.15 A against levels 1 A / 2 A is INFEASIBLE_PROTOCOL with the declared alternatives. One level set
  decides: the action's control domain when it declares levels, else the variable's own (never one after the other).
  A value the owner calls one level but that lies nearer another declared level, of that set or of the variable's own
  domain, matches neither (no world-made separation threshold: round 5 replaced the round-4 one; round 6 added the
  variable's own levels); another spelling of the SAME level (the variable's 0.7 A beside the action's 700 mA) is not
  another level (round 7). A level declared by the action in another unit executes as its conversion into the
  variable's unit, which can lie off the level in any other spelling by conversion rounding (one or several ulps: 8
  for the 95 degF example below), including the bound's own; a
  bound placed at that level, in any spelling (the variable's, the action's own unit and magnitude, or another), is
  decided on the level as executed, for constraints and model validity endpoints alike. So it can go either way: the
  protocol's 95 degF level executes as 35.00000000000006 degC, which a 35 degC limit refuses from below at a strict and
  at an inclusive bound (a definite INFEASIBLE_PROTOCOL, exported as a feasibility verdict) and admits from above; an
  action level 348.753280839895 ft executes as 106.29999999999998 m, which passes a strict `x < 348.753280839895 ft`.
  The same holds when the variable declares no level set (the action's level, converted, is decided against a bound
  written in the action's own unit), and an action level the action itself declares as -0.0 is executed as -0.0.
  Decided = executed holds in every case; whether bind should instead refuse an action level whose conversion does not
  round-trip bit-exactly is recorded as an owner decision (`docs/work/ACTIVE_PLAN.md`). Since round 8 the identity
  rule is required of the proposed spelling itself, so an honest other-unit spelling whose conversion is byte-equal to
  a 13+-digit level is refused (224043.6073475 mm for the level 8820.6144625 inch, variable in ft, which `15725ec`
  admitted), and a fixed condition spelled that way is refused at bind; this is the rounding-edge cost below.
  The cost of the owner's rule: a level whose base-unit magnitude has 13 or more significant digits can be refused in
  an honest other-unit spelling at the rule's rounding edge (3224.762319965 A is FEASIBLE, 3.224762319965 kA is
  LEVEL_NOT_DECLARED; offset conversions such as degC to K add digits). It fails closed; spelling such a level in its
  declared unit avoids it. A value that IS a level is decided as the level even where its own spelling would decide
  otherwise at a bound (35.0000000001 degC is 35 degC to the unit owner, and it is checked and executed as 35 degC). Round 2's 64-ulp rule was absolute at a zero
  level and was withdrawn (round 3, R3-A2).
- **Integers** are compared as exact integers; an integer domain's bounds stay within ±2**53 (the owner stores a bound
  as a float).
- **Declarations are checked as executed.** A fixed condition, and every level and range edge of an action's domain,
  is checked against its variable's own domain in the variable's unit, by the owner's bound rule, at bind and (fixed
  conditions) at every check. The cost: a domain stated in another unit than its variable can refuse its own edge by
  conversion noise (a variable in mA with own domain [0, 0.7] A: 0.7 A executes as 700.0 mA, which the owner's rule
  reads back as 0.7000000000000001 A, outside), so such a declaration fails closed; stating a domain in its variable's
  own unit avoids it. A typed (integer, category or boolean) fixed condition is accepted only for a variable declared
  in exactly `dimensionless` or with a declared domain of that kind; for any other unit (also units pint treats as
  dimensionless, such as degree, percent or ppm) a fixed condition is a quantity the unit owner converts.
- **Who may propose:** a proposer's kind is caller-asserted; a deployment hosting an external or language-model
  proposer builds its desk with `suggestions_only=True` (the execution side's policy).

### Round-15 lifecycle and reconciliation clarification

The Round-15 retention claim was too broad: Round 16 reproduced lost handed spend when native capture
and immediate recovery both fail before any account entry is retained. A raw pending live dictionary can then be
replaced by an earlier checkpoint, and later recovery cannot reconstruct the lost observation. This is an OPEN
MAJOR, not an accepted exclusion or a successful recovery. The older stack/interruption exclusions above and the
original Round-15 preservation promise conflict; neither changes the user's required all-handed-spend guarantee.

Successfully retained entry observations survive later dictionary replacement. The Round-16 local repair also
recovers an already-returned callback value across a one-shot pre-registration interruption. Repeated pre-capture
failure remains open. A stable execution-owner handoff lifetime/publication/acknowledgement contract needs an explicit
owner decision; no such protocol has been introduced. This buffer is not a budget ledger or scientific evidence.

The current implementation checks a reader's seal under the comparison lock, including after a wait. Starting a
verification while open grants no right to complete after sealing. The authoritative comparison remains atomic with
sealing. A structural invalid handing seals the reader; an interrupt, stack exhaustion or allocation failure while
parsing an honest handing does not establish owner corruption and does not seal it.

A read-back is served only when its before/after entry objects are identical and the serialized history has the same
length. A moving read is refused for that verification. The retained unread observation includes the state listed
before the read, so an in-place rollback cannot erase a spend. The entry-listing step is inside interruption handling:
already read accounts compare before the interrupt propagates.

On a later verification, retained unread entry objects may be reconciled through the **existing canonical entry
history rule**, outside the lock. The resulting history applies only to the identical still-pending barrier. It can
establish that an unchanged detached checkpoint is the observed state, or that a restored account is behind a spend.
Failure to read those entries is an explicit refusal, never equality or currentness. No new persistent scientific
authority or execution ledger is introduced. This supersedes the older unconditional description of object-replacing
restore as permanent retirement. Owner content that remains unreadable can still prevent recovery.

A KeyboardInterrupt raised repeatedly by current account content aborts each entire pin, even when the account is
unbound (CRIT15-2). This is an explicit availability residual: no implicit success, no permanent seal solely from
interruption. There is no sound exception-class distinction between operator interruption and content raising that
same exception, so the code does not invent one. This qualifies the older statement that an unbound account refuses
nothing. Execution-side code and private mutation remain inside the documented in-process trust boundary.

## 5. Controls

Executed at the round-14 fix commit (`7b4a0de8`, local WSL2, CPython 3.12.3; command and environment in
`docs/work/PROGRESS.md` items 28-30): `tests/mind`, `benchmarks/mind_gen2_authority_v1/tests`,
`benchmarks/mind_gen2_world_v1/tests` and `tests/test_sria_budget_ledger_identity.py`, **694 passed** (including the
expensive BR1-decision re-derivation; 649 at the round-11 records commit `ec2c000` in the cloud, CPython 3.13.16, 649
again locally at `d40aff44` before the round-12 fix, 667 at the round-12 fix `33258438`, 685 at the round-13 fix
`13051154`).

| Suite | Tests | What it pins |
|---|---|---|
| `test_authority_failing_first.py` | 29 | the brief's A–O, written failing first: no interval decides; lineage laundering; stale state/model/provider/budget/declaration; missing owner; unit spelling; protocol levels (no 1.15 A, nearest or interpolation); raw proposals never execute |
| `test_authority_mutations.py` | 120 | every projected field and binding field edited, every admitted-action and authorization field edited, replay forgeries |
| `test_authority_cross_domain.py` | 32 | battery, two HVAC worlds, drone, motor: the same guarantees in each |
| `test_authority_review_r1.py` … `_r14.py` | 43 / 35 / 21 / 17 / 17 / 14 / 26 / 16 / 9 / 30 / 37 / 18 / 18 / 9 | one control per confirmed review finding (round 6: per finding behind a PARTIAL verdict; round 12: per confirmed lead of the interrupted round); see below |
| `test_sria_budget_ledger_identity.py` | 5 | the owner addition: read-only, wire shape unchanged, round-trip identity |
| benchmark tests | 7 | committed matrix and re-score reproduce; the re-score guard; BR1's decisions re-derived from BR1's code (expensive) |
| BR1 tests adapted (`test_world_contract.py`, `test_world_failing_first.py`, BR1 benchmark) and unchanged (`test_world_boundary.py`) | 67 / 31 / 8 / 5 | BR1's contract under §3; BR1's committed results byte-identical; the package boundary |

On the trees before their fixes (each file copied into a checkout of that SHA): the round-3 controls fail 20/21 on
`1a87f7c`, the round-4 controls 16/17 on `d0a0408`, the round-5 controls (the file as committed at `2422014`, 11
tests) 9/11 on `c52dcfd`, the round-6 controls 9/14 on `ceac320` deterministically (plus the thread stress test
non-deterministically), the round-7 controls 19/22 on `27b9f71` (the file as committed at `b572bfc`; the round-1
liveness loop, extended with a pinned budget snapshot in round 7, fails there too), the round-8 controls 10/15 on
`15725ec` (the file as committed at `2f7281f`), and the round-9 controls 9/10 on `ceaf8cd` (the 10-test file as
committed at `e573096`; round 10 removed one parameter). On `c52dcfd` the two round-5 tests that pass are a
control for a round-4 reader fix (`test_a_refused_declaration_read_advances_nothing`) and E5-F3's control
(`test_a_fixed_condition_at_its_variables_own_level_is_refused_where_the_level_is`: that path already held); one of the
nine that fail there, the K5-F2 ledger control, fails at the round-4 follower's construction read rather than at the
mapping it guards (reverting the mapping on a later tree makes it fail). On `ceac320` four of the round-6 tests that
pass guard paths that already held: the two experiment-follower controls (both fail on a mutant of the 13-test file at
`0453a95` that drops the experiment history check), and the gating-False and remainder-basis controls; the fifth, a
thread stress test, reproduces the round-6 race only sometimes (1 of 3 of the builder's runs on `ceac320`, 2 of 3 of a
round-7 reviewer's), so it is a supplementary control; the deterministic control of an older mapping compared after a
newer one is round 9's `test_an_older_mapping_compared_after_a_newer_one_is_refused_only_for_its_verification`. On `27b9f71` the three
round-7 tests that pass guard paths that already held: the replay of a refusal of an account behind, the provider half
of K6-F2 (it fails on a mutant that stops naming providers) and the `remaining_observations` basis. On `15725ec` the
five round-8 tests that pass guard paths round 7 had already fixed but left without a control: `accounts()` called
with no lock held, three of the four declaration modes then tested (the modes "no declaration" and "a declaration not
in force" each fail on a mutant that reads that mode's bindings; no mutant was run for "owner unavailable"), and the
budget-free world's verification through the desk. On `ceaf8cd` the one round-9 test that passes is the detachment
control for an in-place change (round 8's served copies were already detached for that case; B9-m1's case, an
equal-content replacement, is closed by the JSON detachment: round 10's
`test_an_equal_content_replacement_serves_the_account_handed_over` fails on a mutant without it). The 30 round-10
controls on `c69e579`: 20 fail, and one more hangs there (the self-containing value, stopped after 20 s); the nine that
pass are the no-metadata case, the Arabic-Indic numeral `int()` accepted, five controls of guards round 9 already had
(the unlocked read-back, the same-thread flag, B9-m1's JSON detachment, the ticket discarded after a failed
`accounts()`, bind's level rule), each of which fails on a mutant that removes its guard, and two supplementary stress
tests (the cache race, whose deterministic control is `test_a_snapshot_reads_back_into_its_own_cache_until_it_compares`,
and concurrent admissions, whose deterministic control is `test_a_compared_verification_decides_on_what_the_ones_in_flight_record`).
Thirteen mutants of the round-10 code (no wait, start-order waiting, no re-check after the wait, no refusal for good,
a shared cache, a locked read-back, the flag reset early, no id check, an undetached ledger, no notify on leaving, no
JSON detachment, no discard in the `finally`, bind on its own conversion) each fail at least one round-10 control.
The 37 round-11 controls on `aad2f69`: 20 fail; the 17 that pass are the depth-3 case and controls of guards round 10
already had (a ledger whose serialization raises `TypeError`, a ledger its owner cannot read back, content too deep
for the owner's encoder, an account that keeps moving, the re-check after the wait, a served record not shared, the
numeral comparison of revisions in nine cases and a multi-digit STALE), each of which fails on a mutant that removes its
guard. Thirteen mutants of the round-11 code (one attempt, alike failures taken as moving, no fresh-thread retry,
never moving, a strict snapshot, no abandonment, no alias refusal, a shared served record, the flag reset after the
leave, no re-check of accounts refused for good while waiting, a lexical revision comparison, accounts refused for good
read again, no torn check) each fail at least one round-10 or round-11 control. The 18 round-12 controls on `d40aff44`
(the file copied into a tree whose `owners.py` is `d40aff44`'s): 14 fail; the 4 that pass are the controls for
mutants of the round-11 code that survived the interrupted round's lenses (a str subclass id rendered by its own
`__str__`, differing failures or failures differing only in their written text taken as alike, the fresh thread
without the read-through flag, an aliased spend not recorded), each of which fails on its mutant. Eighteen mutants of
the round-12 code (the failure rendered by its own code twice, no check for two entries spelling one id in the
snapshot and in the constructor, the length of an unread state not recorded / not compared / not re-checked after the
wait / taken as 0 when unreadable, an unbounded fresh-thread join, a fresh-thread timeout refused for good, a single
fresh-thread attempt, only a direct `RecursionError` seen, and the five survivors above): 17 fail at least one
control; `shared_cache` (the fresh thread writing the snapshot's cache instead of a private copy) passes every test: it
matters only if an abandoned fresh thread writes while the comparison copies that cache, which no deterministic test
schedules (recorded, not claimed as controlled; round 13's `test_an_abandoned_fresh_thread_writes_into_nothing_the_verification_holds`
now controls it deterministically). The 18 round-13 controls, with the restated round-11 abandonment control, on a
tree whose `owners.py` is `3b407ddb`'s: 14 fail; the 5 that pass are the honest-account control (a state not read back,
then an in-place move and an unchanged checkpoint restore, read), the private-cache control (the cache was already
private), the restore-without-a-new-charge case of F13-02 (the round-12 length rule refused it), the shorter-unread
control (R13-CRIT-2: round 12's floor kept the maximum) and the restated round-11 control (its path held), each of
which fails on its mutant. Thirty-two mutants of the round-12/13 code (the entry identity ignored, unread entries not
recorded / not checked on a read / not re-checked after the wait / never cleared / tolerated when unlistable / a
shorter unread state replacing a longer one; a `BaseException` not classified, not classified while rendering, an
interrupt not caught or swallowed; a mapping trusted through `dict(mapping)` in the snapshot or the constructor; the
fresh thread's result read before its liveness, a second fresh thread per account, a deadline per account, a shared
cache; the ticket discarded at the start of the comparison; the round-11 `no_abandon` and `handed_never_set`; and
round 12's eleven re-checked on the rewritten code): each fails at least one control (31 in the first pass;
`box_before_alive` passed there because its control asserted only "not for good", and was caught once the control
required the record be served: `docs/work/evidence/br11_local_2026_10_23/round13/mutation/`). The 9 round-14
controls (8 tests, one over two exception types) on a tree whose `owners.py` is `1c9fdd84`'s: 7 fail; the 2 that pass
guard paths round 13 already had (an unread state with a new entry refuses an object-replacing restore; one that
moved on in place is cleared and an unchanged restore is read), each failing on its mutant. Thirty-eight mutants of
the round-12/13/14 code (round 13's thirty-two adapted to the rewritten code, and six new: the length condition back,
the known-content shortcut by length or off, the after-read listing ignored, the seal off, `SystemExit` /
`GeneratorExit` taken as interrupts): each fails at least one control (37 in the first pass; `unread_not_cleared`
passed there because the round-13 control of it no longer reaches the clearing once a state with no new entry records
nothing, and was caught once the round-14 control with a new entry was added:
`docs/work/evidence/br11_local_2026_10_23/round14/mutation/`). The one-fresh-thread-per-account lock (F14-F4) has no
deterministic control: only a race between two verifications distinguishes it.
Round 9 split the declaration modes into an older revision
(STALE) and a same-revision declaration with other content (MISMATCH) (15 → 16 in r8). Round 6 ran the round-5 fixed-kind test over three units
(11 → 17); round 8 ran the round-7 offset-unit level test over four bound operators with each decision pinned (22 → 26)
and restated the round-6 thread stress test for the round-7 rule (refusals of an account behind are allowed, a refusal
for good is not).

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
subjects. The changes of rounds 3 to 10 left every case's status and codes unchanged; only the decisions digest moved
(rounds 3, 4 and 6; `BR1_RESCORE.json` is unchanged since `a058cf2`, and `rescore --check` MATCHES at `d89dd3b`).

## 8. Performance (`results/PERFORMANCE.json`, `results/BR1_PERFORMANCE_THIS_HOST.json`, `results/LEDGER_SIZE_CURVE.json`)

One idle host: 4 CPUs, Linux, Python 3.13.16. The host's speed changes between container restarts and within a
session, so numbers are compared only within a file (every file names its host and code revision). BR1's reported
numbers were measured on another machine. For the delta, BR1's own harness ran on BR1's 515 cases alternately on BR1's
code (`1202ea6c`), on the round-7 review commit (`27b9f71`) and on BR1.1's code (`d5ef1e3`), five rounds each
(`BR1_PERFORMANCE_THIS_HOST.json`: every run, medians, min-max ranges and the command). The owned-world metrics are
`PERFORMANCE.json` regenerated at `d5ef1e3` (`python -m benchmarks.mind_gen2_authority_v1.run_benchmark`, 25 repeats;
it also carries one single run of BR1's harness, `br1_cases_on_br1_1_code`, and its own reference solver run).

| Metric (ms): median (min-max of 5 runs) | BR1 reported | BR1 code, this host | BR1.1 at `27b9f71` | BR1.1 code, this host | BR1.1 slower than BR1 in paired rounds |
|---|---|---|---|---|---|
| WORLD_BUILD (BR1 cases) | 0.856 | 1.207 (1.171-1.628) | 1.571 (1.025-2.385) | 1.454 (1.223-2.213) | 4 of 5 |
| ACTIONSPACE_BUILD | 0.256 | 0.392 (0.358-0.427) | 0.441 (0.239-0.540) | 0.373 (0.306-0.401) | 2 of 5 |
| FEASIBILITY p50 | 0.140 | 0.189 (0.154-0.234) | 0.196 (0.177-0.220) | 0.224 (0.185-0.234) | 4 of 5 |
| FEASIBILITY p95 | 0.263 | 0.365 (0.268-0.458) | 0.337 (0.288-0.415) | 0.408 (0.365-0.609) | 3 of 5 |
| reference: one in-repo solver execution | — | 151.0 | 138.3 | 144.7 | — |

| Owned worlds (ms), `PERFORMANCE.json` | p50 / p95 |
|---|---|
| check | 0.322 / 0.567 |
| projection from owners (median by world) | 10.8 |
| owner verification | 12.8 / 20.5 |
| admission (verify + rebuild + check + mint) | 16.8 / 23.8 |
| dispatch authorization (re-admission) | 17.7 / 25.3 |

In this file the check on BR1's cases is slower than BR1's in 4 of 5 paired rounds at p50 (median of the paired
ratios +15 %, ratio of the medians +19 %) and in 3 of 5 at p95 (paired median +1 %, ratio of the medians +12 %);
ACTIONSPACE_BUILD shows no consistent difference (2 of 5) and WORLD_BUILD is slower in 4 of 5 (paired median +22 %,
with overlapping ranges). Earlier files on other host states gave a p50 paired median of +7 % (`e573096`) and +27 %
(`d89dd3b`); round 10's interleaved A/B (`e573096` against `d89dd3b`, 8 runs each: p50 medians 0.229 and 0.230 ms)
showed that round 10 did not change the check's cost, and round 11 changed only the budget reader, which the check on
BR1's cases does not run. So the check's extra cost against BR1 is about +7 % to +27 % at p50 depending on the host
state, from the rules of rounds 3-9 (deciding on the value as executed, the level identity and nearer-level rules, the
exact-level guard); no finer attribution by revision is claimed. Within `PERFORMANCE.json`, admission costs ~52× the
check and ~8× less than that file's own reference solver execution (136.7 ms). Under `cProfile` (20 admissions,
battery, at `26d7724`), the verified projection took ~71 % of admission and the unit owner's
`verify_registry_unmutated` alone ~24 %. Cost grows with the bindings, the declarations in force and the budget
accounts' histories (`python -m benchmarks.mind_gen2_authority_v1.ledger_curve`, `LEDGER_SIZE_CURVE.json` at
`d5ef1e3`, 41 repeats, each point with its fastest and slowest run):
- a bound ledger's settled charges (the world carries every charge of a bound ledger): admission p50 20.0 / 16.2 /
  37.4 / 183 ms and check p50 0.28 / 0.45 / 1.15 / 7.2 ms at 0 / 10 / 100 / 1000 charges, about 0.16 ms of admission
  per charge between 100 and 1000;
- one unbound ledger handed to the following reader (read back at every verification through its owner's JSON
  text): admission p50 19.4 / 19.5 / 22.1 / 42.2 ms at 0 / 10 / 100 / 1000 charges;
- one unbound experiment that records a new evaluation before every admission (its owner's whole read-back, which is
  quadratic in the evaluations, runs at every admission; an unchanged experiment is read back once per content):
  admission p50 22.3 / 23.6 / 42.8 / 122 ms at 0 / 100 / 300 / 1000 evaluations.

Concurrency (the bounded wait; the reviewers' probes re-run at `d5ef1e3`): 8 threads × 30 admissions through one desk
while an unbound ledger is spent in place: 240 of 240 FEASIBLE (round 9's ticket rule, at `c69e579`: 201 of 240, 39
refused "in flight"); 4 threads × 40 admissions with a changing set of 30 experiment accounts: 160 of 160 FEASIBLE (at
`c69e579`: 131 FEASIBLE, 16 refused, 13 raised a `RuntimeError` from the shared cache; round 10's first candidate,
refusing while any other verification is in flight, admitted 3 of 160). A large account (B11-4): one unbound experiment of 2500 evaluations that the execution side
extends every 0.1 s (each new content is read back whole, quadratic, about 0.45 s alone), 8 threads × 6 admissions (an
overloaded desk: admission latency p50 about 5.5 s): in 9 interleaved runs each, `d5ef1e3` admitted 3 to 48 of 48
(median 38) and round 10's `aad2f69` 30 to 48 (median 44), the rest refused "in flight" after `WAIT_S`. Round 11's
per-verification work is not larger (its served record is parsed from text, 3.7 ms, where round 10 deep-copied it,
13.7 ms; in an instrumented run no read-back failed or was retried), so the spread is the bounded wait's sensitivity to
scheduling under overload, fail-closed, and is not attributed further; at 1000 evaluations, 48 of 48 (p50 1.2 s). The cost of the
wait: while one verification's `accounts()` or read-back does not complete, every admission that compares meanwhile
takes `WAIT_S` (1 s) and is refused (5 of 5 in the reviewers' p12 probe).

Round-12 fix (`33258438`) against the tree before it (`d40aff44`), interleaved, 5 rounds each, one other host (WSL2,
20 CPUs, CPython 3.12.3; `docs/work/evidence/br11_local_2026_10_23/performance/`): 200 admissions through a following
budget reader on the battery fixture, admission p50 12.30 ms (12.28-12.69) before and 12.36 ms (12.28-12.52) after,
the budget pin p50 0.17 ms in both: NO SPEED DIFFERENCE ESTABLISHED (overlapping ranges). The large-account desk (8 ×
6 admissions): at 1000 evaluations 48 of 48 in all 10 runs; at 2500, overloaded, 14 to 48 of 48 before (median 48) and
31 to 48 after (median 47), every refusal "in flight" (fail-closed): no availability difference is established (the
instrumented read-back counted 0 to 4 torn read-backs per run in both trees, all of the UNBOUND experiment, which
refuses nothing, so these runs say nothing about the not-read-back rule refusing a bound account; round 13, R13-B-F6).
The round-12 paths run only after a read-back has failed.

Round-13 fix (`13051154`) against the round-12 code (`33258438`), the same harness and host, interleaved, 5 rounds each
(`docs/work/evidence/br11_local_2026_10_23/round13/performance/`): admission p50 11.96 ms (11.18-12.65) before and
12.15 ms (11.51-12.78) after, the budget pin p50 0.17 ms in both: NO SPEED DIFFERENCE ESTABLISHED. The desk at 1000
evaluations: 48 of 48 in all 10 runs; at 2500 (overloaded): 41 to 48 of 48 before (median 46) and 46 to 48 after
(median 48), every refusal "in flight" (fail-closed): no availability difference established (overlapping ranges). The
entry listing runs for every handed account twice at every verification, just before and just after its read-back
(round 14, E14-F3 / R14-B-F2: an earlier wording here said only after a failure; these figures measured that code).

Round-14 fix (`7b4a0de8`) against the round-13 code (`13051154`), the same harness and host, interleaved
(`docs/work/evidence/br11_local_2026_10_23/round14/performance/`): admission p50 11.84 ms (11.79-12.26) before and
12.09 ms (11.68-12.80) after, the budget pin p50 0.17 ms in both: NO SPEED DIFFERENCE ESTABLISHED. The desk at 1000
evaluations: 48 of 48 in all 10 runs. At 2500 (overloaded), 10 interleaved rounds each (the first 5 with the admission
runs, 5 more of the desk alone because the first 5 gave two low after-runs): before 48, 47, 48, 48, 44 and 48, 46, 48,
42, 48 (42 to 48); after 48, 48, 45, 23, 29 and 48, 46, 48, 43, 48 (23 to 48); every refusal "in flight"
(fail-closed): the ranges overlap, so no availability difference is established; the extra five runs were chosen after seeing the first results (a data-dependent extension, not a fixed stopping rule) (the two
low runs did not recur).

Nothing is cached across admissions except, per account handed over now, the last content its owner read back (a
function of the content, not a currency claim).

### Round-15 affected-path measurement

Fixed five paired runs, alternating pre/post order, on the same CPython 3.12.3 WSL host with no other campaign tests
running. Pre: exact reviewed `95f3869e`; post source checksum and every sample are in
`round15/performance.json` (under the local evidence directory). Units below are microseconds, ranges of run medians.

| Path | Before | After | Interpretation |
|---|---:|---:|---|
| verification_pin | 119.70–124.69 | 127.21–141.01 | NONOVERLAPPING RANGES IN THIS BOUNDED MEASUREMENT |
| comparison_pre_read_snapshot | 1.97–2.21 | 2.37–2.51 | NONOVERLAPPING RANGES IN THIS BOUNDED MEASUREMENT |
| seal | 9.24–10.00 | 5.85–6.49 | NONOVERLAPPING RANGES IN THIS BOUNDED MEASUREMENT |
| dispatch_authorization | 12897.94–13575.33 | 12962.92–13327.97 | NO SPEED DIFFERENCE ESTABLISHED |
| wait_2ms_bound | 2284.78–2337.49 | 2253.35–2315.94 | NO SPEED DIFFERENCE ESTABLISHED |
| contention_pin | 168.06–179.29 | 175.23–204.09 | NO SPEED DIFFERENCE ESTABLISHED |

The isolated comparison uses an already read synthetic snapshot and includes ticket bookkeeping. The wait probe
uses an explicitly blocked verification and a 2 ms bound. Contention uses four threads and eight barrier-synchronized
reads each: all 32/32 were served in each of ten runs. Availability is recorded separately; safe refusal would not
be false admission. Verification and comparison medians increased in these nonoverlapping ranges; structural sealing decreased.
These bounded microbenchmarks do not establish a general speed claim. No physical simulation, scientific validation, certification or formal measurement campaign ran.

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
| 6 | `ceac320` | A, B, C, D, E | 0 / 0 / 27 | none to verify; Q1, Q5, Q6 NO from every lens; Q2, Q3, Q4, Q7 PARTIAL from at least one lens, on MINOR findings only (the brief does not close on PARTIAL) | K6-F1 (the experiment half of the follower had no control), K6-F2 (a submitted world chose which accounts the follower read) MINOR | `0453a95`, `a058cf2` |
| 7 | `27b9f71` | A, B, C, D, E, F (a deep attack on the two round-6 rewrites) | 1 / 4 / 30 | **R7-C-F1 BLOCKER** (both skeptics) = **A7-F1 MAJOR** (both skeptics) = E7-F2: round 6's nearer-level rule counted another spelling of the SAME level as another level, so a spelling of a refuted level was admitted and dispatched an ulp off the level; **B7-M1 = R7-D1 = F7-F1** (a pinned budget snapshot was derived live: a desk built on it re-dispatched an executed action): reproduced by every repro skeptic, graded MINOR by every scope skeptic (the execution side must build its desk from `pinned()`); treated as MAJOR and fixed | **K7-F1 BLOCKER** (the same class in offset temperature units and on a fixed protocol condition), K7-F2..K7-F4 MINOR | `9a61a01`, `14caa58`, `b572bfc` |
| 8 | `15725ec` | A, B, C, D, E, F (a deep attack on the round-7 rewrites) | 0 / 0 / 36 | none to verify; Q1-Q7 NO from lenses A-E; lens F and the critic held Q4 PARTIAL on two MINORs: the fixed-condition half of the exact-level guard had no control (F8-2 = K8-F1 = A8-F2), and the round-7 unlocked read-back let a rollback land between a verification's read-back and its comparison (F8-1 = B8-m1 = E8-F1) | K8-F1..K8-F3 MINOR | `03f3aab`, `2f7281f` |
| 9 | `ceaf8cd` | A, B, C, D, E, F (a deep attack on the round-8 rewrites) | 0 / 0 / 38 | none to verify; Q1-Q7 NO from every lens and the critic | K9-F1..K9-F3 MINOR | `17a1c31`, `e573096` |
| 10 | `c69e579` | A, B, C, D, E, F (a deep attack on the round-9 rewrites) | 0 / 2 / 36 | **R10-C-F1** (repro skeptic MAJOR, scope skeptic MINOR): round 9's exact-type plain-data rule refused ordinary owner content (an evaluation's frozen nested metadata, numpy and enum values), so a spend recorded with it was never observed and a restore re-dispatched the executed action, sequentially; **R10-C-F2** (both skeptics MINOR): the ticket rule protected a handed spend only when its verification had STARTED first; both treated as MAJOR and fixed. Q4: YES from C, PARTIAL from B and F, NO from A, D, E | K10-F1 (rules both MINOR: the guarantee was stated for handed states but held for observed ones), K10-F2 MINOR | `d89dd3b` |
| 11 | `aad2f69` | A, B, C, D, E, F (a deep attack on the round-10 rewrites) | 0 / 3 / 22 | **R11-C-F1** (both skeptics MAJOR) = **F11-1** (repro MAJOR, scope MINOR): round 10 moved the experiment read-back's `deepcopy` outside the try that classifies read-back failures, so owner-valid content nested ~500 levels deep raised out of every verification, a handed spend was never observed and a restore re-dispatched the executed action (and an unbound such account made every admission raise); **F11-2** (repro MAJOR, scope MINOR): a handed mapping the constructor refused (an id that is a `numpy.str_` since round 10's exact-str rule, or one object under two ids) hid a spend on another, well-formed account; all treated as MAJOR and fixed. Q4: YES from C, F and the critic, PARTIAL from A, B, D (read-back failures classified by exception type: a torn top-up refused for good, a deterministic `RuntimeError` hiding a spend), NO from E | K11-F1 (the whole read-back after the write must be classified), K11-F2 (served experiment records not controlled as detached) MINOR | `d5ef1e3` |
| 12 | `a96baa6` | A, B started; C-F, skeptics and critic never ran | none returned | **INTERRUPTED / INCOMPLETE: no verdict** (the cloud session was stopped on the owner's instruction); the two lenses' probes are preserved as unverified leads and were triaged locally (below) | — | `33258438` |
| 13 | `3b407ddb` (fresh round; local, WSL2, CPython 3.12.3) | A, B, C, D, E (static), F (a deep attack on the round-12 rewrites) | 0 / 5 / 24 (lenses) + 1 MAJOR / 1 MINOR (critic) | **F13-02** = **R13-C-F1** (both skeptics MAJOR, each): a state handed and not read back kept only its length, so a restore plus one more charge was accepted and a fresh admission dispatched the executed action again (also filed MINOR as R13-A-F2, R13-B-F2, E13-F3, D13-4); **R13-B-F1** (both skeptics MAJOR): `dict(mapping)` ran the key objects' `__hash__`/`__eq__`, merging or wiping handed accounts (a spend unobserved, dispatched again); **R13-C-F2** (scope MAJOR, repro MINOR: "the accepted interrupted residual") = **R13-A-F1** (both skeptics MINOR, same reason): account content raising a `BaseException` left every verification with no trace and a restore re-dispatched (also F13-03, R13-B-F3, E13-F4); treated as MAJOR and fixed, since the trigger is a property of the handed state, not an interruption | critic **R13-CRIT-1** MAJOR (not skeptic-verified; treated as MAJOR): the handed container's own code (truthiness, `keys`/`__iter__`) decided what was handed; R13-CRIT-2 MINOR (no control for keeping the longer unread state). Q1-Q3, Q5-Q7 NO from every lens and the critic; Q4 YES from A, B, C, F and the critic, PARTIAL from D, E: the gate did not hold | `13051154` |
| 14 | `1c9fdd84` (fresh round; local) | A, B, C, D, E (static), F (a deep attack on the round-13 rewrites) | 0 / 5 / 19 (lenses) + 1 MAJOR / 2 MINOR (critic) | **R14-A-F1 = R14-C-F1 = D14-F1 = F14-F1 = E14-F1** (one finding from five lenses, both skeptics MAJOR for each): a handed state not read back and SHORTER than the history observed was never recorded, so a return to the observed checkpoint (or a longer state compared first) was accepted and a fresh admission dispatched the executed action again | critic **CRIT14-1** MAJOR (not skeptic-verified; treated as MAJOR): a regression of round 13's dict-only rule, an honest non-dict mapping handed at a verification left its state unobserved and the same authorization was dispatched again after a restore; CRIT14-2 MINOR (controls pinned refusals, not outcomes); CRIT14-3 MINOR (lens B answered Q4 NO and marked F13-02 closed against five confirmed MAJORs: recorded here as a missed finding, not a dissent). Q1-Q3, Q5-Q7 NO from every lens and the critic; Q4 YES from A, C, D, E, F and the critic. Harness defect R14-C-H1: the probe command the round's brief gave imported `~/forge-r13-review` (`3b407ddb`), not `1c9fdd84`; lenses A and C noticed and ran against `~/forge-r14-review`; the MAJOR stands on lens E's static reading of the correct tree and its skeptics; the brief is fixed for later rounds | `7b4a0de8` |

**Round-12 lead triage (local, not a review result).** Every preserved probe
(`docs/work/evidence/br11_cloud_2026_10_23/round12_interrupted/`) was re-run unchanged at `d40aff44` on WSL2 Ubuntu
24.04, CPython 3.12.3 (outputs under the local log directory named in PROGRESS item 28); a cloud output alone was not
taken as a finding. Confirmed, with a failing-first control in `test_authority_review_r12.py` and a mutant each
control catches (§5):
- R12-1 (b1201, b1202): an exception whose own `__str__` raises, or an exact `RuntimeError` whose argument cannot
  render, made `_read_once`'s classifying handler raise; the error left `pinned()`, admissions raised, a world that
  never reads the account raised, and after a restore the executed action was dispatched again (executor ran 2).
  Authority impact: unobserved spend, duplicate dispatch, fail-open of the forward-only rule. Fixed by catching what a
  failure's rendering raises (an `Exception` in round 12, any non-interrupt `BaseException` since round 13), also at
  the five other owner-boundary handlers of `owners.py`.
- R12-2 (b1205, a1205, a1205b): two keys spelling one id (a str subclass hashing by identity) collapsed silently to
  one account: a stale entry hid the spend (dispatched again) and the strict constructor accepted the set and dropped
  an account. Impact: owner-identity confusion, unobserved spend, duplicate dispatch. Fixed: the id is refused for good;
  the constructor refuses.
- R12-3 (b1204, b1208): a spent state whose serialization raises the interpreter's own mutation text every time, or a
  fresh message per attempt, was classified moving (refused per verification, never observed) and a restore
  re-dispatched. Impact: unobserved spend, duplicate dispatch. Root cause: a state not read back left no trace. Fixed
  in round 12 by observing its history's length (shorter later states behind); round 13 found that insufficient (a
  restore plus one more charge re-admitted, F13-02) and replaced it by the state's entry objects.
- R12-4 (b1207, a1207): `_at_baseline_depth` joined its fresh thread with no timeout: a verification holding a lock its
  account's serialization takes blocked for good, kept its ticket in flight, and every other verification was refused
  (a1207: the other verification blocked too). Impact: deadlock / unbounded wait, denial of service against valid
  authority (availability, fail-closed). Fixed: the wait is bounded by `WAIT_S`; the fresh thread fills a private
  cache.
- R12-5 (b1206, a1202): the fresh-thread retry was one attempt, so a single torn read there refused an honest account
  for good; and a recursion failure the unit owner wraps (`UnitCompatibilityError` from `RecursionError`) was not seen
  as recursion, refusing an honest account for good at 12 of 58 caller depths. Impact: denial of service against
  valid authority (availability, fail-closed). Fixed: the fresh thread runs the same classified attempts; recursion is
  read through the exception chain.
- R12-6: of the five mutants of the round-11 code that passed the whole suite in the interrupted round (lens A:
  `id_str_call`, `differ_not_moving`, `why_only`; lens B: `fresh_thread_no_flag`, `alias_not_recorded2`), each now
  fails a round-12 control.
Not a new defect: b1203 (a `RecursionError` escapes at 10 frames of caller headroom here, 11 in the cloud on
3.13: a platform difference; the documented residual "the caller's own stack exhausted inside the reader"), a1208
(within one verification the served experiment record is one object parsed at the pin; wording, §4), b1209 (large-
account contention, §8), b1210 and b1211 (alias spend recorded; fresh-thread read-through bounded: consistent with
the round-11 claims). Round 12 itself stays without a result; a fresh review round reviews the fixed tree.

**Round 13 dispositions** (review outputs: `docs/work/evidence/br11_local_2026_10_23/review_results/review_r13_result.json`;
fixed in `13051154`, controls `test_authority_review_r13.py`, mutants §5). Fixed, MAJOR: F13-02 / R13-C-F1 / R13-A-F2 /
R13-B-F2 / E13-F3 / D13-4 (a state not read back is observed as its entry objects; a later state must begin with them,
a prefix is behind, anything else is refused for good, §4); R13-C-F2 / R13-A-F1 / F13-03 / R13-B-F3 / E13-F4 (any
non-interrupt `BaseException` from account content, or from rendering a failure, is a classified failure; an interrupt
is re-raised only after the verification compared, every unread account observed as not read back); R13-B-F1 /
R13-CRIT-1 / R13-C-F3 (a handed mapping is read as a dict from the dict's own storage, a non-dict refused to that
verification; the entry listing reads the owner's container from the instance dict's own storage, total). Fixed,
MINOR: E13-F1 / F13-01 / D13-1 (the fresh thread's liveness is checked before its result is read); E13-F5 / R13-C-F4 /
R13-A-F4 / R13-B-F4 (one fresh read-back thread per account at a time); D13-5 (one fresh-thread deadline per
verification); R13-B-F5 / D13-2 (the not-read-back and fresh-thread refusals state their real cause and attempt count;
§4 restricts "says the same thing at every read" to lasting refusals); E13-F7 (a verification stays in flight until its
comparison ends); E13-F2 (a control for the private fresh-thread cache, which also kills round 12's surviving
`shared_cache` mutant); R13-CRIT-2 (a control that a shorter state not read back never replaces a longer one);
R13-A-F3 / E13-F4 (wording: rendering runs `__str__`; the entry listing reads the owners' containers directly);
E13-F6 / D13-3 (the round-12 controls evidence file is the 17-test run made before the eighteenth control was added;
the 18 / 14 figure is the mutation harness's `[base]` line, which the local evidence README now says; the test list
at the top names r11-r13); R13-B-F6 (the vacuous §8 sentence restated). The round-11 control
`test_a_verification_waited_for_that_leaves_uncompared_makes_the_waiter_decide_on_nothing` was restated, not weakened:
an exception inside the read-back is now classified and an interrupt there is re-raised only after comparing, so W is
interrupted at the snapshot step, where it still leaves uncompared; it still fails on the round-11 mutants `no_abandon`
and `handed_never_set` (§5).

**Round 14 dispositions** (review outputs: `docs/work/evidence/br11_local_2026_10_23/review_results/review_r14_result.json`;
fixed in `7b4a0de8`, controls `test_authority_review_r14.py`, mutants §5). Fixed, MAJOR: R14-A-F1 = R14-C-F1 = D14-F1 =
F14-F1 = E14-F1 (every state not read back is recorded as its entry objects whatever its length); CRIT14-1 (a handing
that is not a pair of dicts makes the reader refuse every account from then on; the constructor already refused one).
Round-14 attempt, MINOR: F14-F2 was fixed, but R14-C-F2 remained open at the Round-15 SHA (the check covered only a recorded unread state). The change checked unread entries just before AND just after its
read-back); R14-C-F3 / E14-F2 (only a `KeyboardInterrupt` is an interrupt; `SystemExit` / `GeneratorExit` from content
are failures); E14-F4 (an unlistable read state against a recorded unread state states that reason); D14-F3 (a refusal
behind an unread state has its own text); F14-F4 / R14-B-F1 (the one-fresh-thread-per-account check and registration
under one lock: a race, with no deterministic control); F14-F5 (§4 restated: a stack exhausted or an interrupt inside
the read-back is re-raised after the comparison; only one after the read-back leaves uncompared); F14-F6 (`following()`
and the constructor are annotated with dicts); E14-F3 / R14-B-F2 (§8: the entry listing runs twice per handed account
at every verification); R14-B-F3 (the instrumented desk probe is committed beside the A/B harness in both performance
directories); CRIT14-2 (outcome controls for the shorter unread state, sequential and concurrent, and for the non-dict
handing, with mutants `r14_length_condition` and `seal_off`); R14-C-H1 (the round brief's probe path). Narrowed, not
removed (availability, fail-closed): R14-C-F4 / F14-F3 / R14-A-F2 / D14-F2 (an object-replacing restore after a state
not read back): an unread state whose entry objects are a prefix of those of the state last read back now records
nothing, so a transient failure or an interrupt with no new entry, then an honest unchanged checkpoint resume, is read;
after an unread state that holds a new entry, such a restore is still refused for good (§4). Recorded, no change:
R14-B-F4 (lens B's judgements on the behaviours new in `13051154`: each fails closed). The round-13 control
`test_a_handed_mapping_that_is_not_a_dict_refuses_the_verification` now matches the sealing refusal's text (it still
asserts the refusal), and the round-11 restated control's helper absorbs that refusal in its interrupted thread.

Rounds 2, 3, 4 and 7 asked the same question: is the value a decision was made on the value an executor receives (and,
from round 7, is it exactly a declared level when the variable is a level set)? `d113d30` answered it for controls (every family decides on the configuration as it will be executed);
`26d7724` extended it to fixed conditions and restored an independent mint check. Their regression tests fail 20/21
(`test_authority_review_r3.py` on `1a87f7c`) and 16/17 (`test_authority_review_r4.py` on `d0a0408`).

The mint check's history, stated exactly: K-F1 was closed structurally by `1514560` (a proposal's value is read only
for a control, and controls and fixed conditions are disjoint by construction). `1a87f7c` added an independent check
(configuration from the sources, compared with the families' resolution). `d113d30` built the configuration through
that same resolution, which made the check circular (K4-F1). `26d7724` builds it from the sources again and compares it
with every exact value any family read in the check; tests that re-introduce the `bc6980c` read into the shared
resolution, or a raw read into one family only, are refused at mint. Round 7 added a second independent guard: a
value of a level-set variable is minted only if it is exactly one declared level of the deciding set as executed (the
domain family refuses it too). A family that bypassed the shared reading path
altogether would not be seen by this check; the per-value regression tests are the control for that. The exact-level
guard's two halves have their own controls: for controls,
`test_authority_review_r7.py::test_every_spelling_of_one_level_is_decided_alike_and_executed_as_one_value`; for fixed
conditions, `test_authority_review_r8.py::test_a_fixed_condition_the_identity_rule_does_not_match_is_never_executed_as_a_level`
and `test_authority_review_r9.py::test_a_fixed_condition_every_check_would_refuse_is_refused_at_bind` (round 11,
A11-F4).

**MINOR dispositions.** Every MINOR of rounds 1–6 was fixed or is recorded as a documented residual; the builder did
not drop any silently. Round 5's: fixed — A5-F2 / R5-C-M1 / E5-F2 (the compared remainder and its basis), A5-F3 /
E5-F1 (refusals that last), A5-F4 (fixed-condition kind), A5-F5 (no separation threshold), A5-F6 / B5-M2 / E5-F5
(gating flag), A5-F7 / B5-M3 / E5-F4 (fixed-condition refusal labels), B5-M1 / R5-C-M2 (an account no world reads
refuses nothing), R5-D2 (unbound accounts cost nothing in round 5; the quadratic experiment read-back it also named
was made linear in round 6, R6-D3, and is quadratic again since round 7, which reads an experiment back whole by its
owner's rule once per account and content: a documented cost, §8), B5-M4 / K5-F1 / K5-F2 (tests that reproduce the defect they guard), R5-D4 / B5-M5 /
E5-F6 (performance provenance, §8; the re-score guard raises explicitly since round 6), E5-F3 (a control for a path
that already held, §5); K5-F3 (gates last run before the round's code) recurred as B6-M7 and is closed by the gates at
`a058cf2`, `b572bfc`, `1c9303e` and `f5d8dc0` (PROGRESS items 16, 18, 20 and 22); documented — A5-F1 (declarations checked as executed fail closed at a converted edge, §4),
R5-D3 (`replay_decision`'s unit guard needs a world that binds the unit registry, §2), the case-level re-score guard
(§7). Round 6's: fixed — A6-F1 (one level set; a value nearer a level of the variable's own domain matches neither),
A6-F2 (the typed fixed-condition rule, §4), A6-F3 / B6-M2 / E6-F2 / E6-F3 (controls for gating False and the recorded
remainder basis), A6-F4 (a BR1-style OVER_BUDGET states the remainder the plan compared, and its basis), B6-M1 /
R6-C-M2 / R6-D2 (concurrent verifications: snapshots are observed in order under one lock and serve what they
observed; superseded by round 7's unlocked rule and rounds 9-10's comparison rule, §4), B6-M3 / R6-D4 (one refusal message from the first refusal on: recordable), B6-M4 / R6-C-M1 / R6-D1 / E6-F4
(every handed account observed at construction and at every verification, §4), R6-D3 (experiments read back one
evaluation at a time; superseded by round 7's whole read-back, a documented cost, §8), K6-F1 (experiment follower controls), K6-F2 (a world bound to an account or provider the
declaration in force does not name is AUTHORITY_MISMATCH without that record being read; a submitted world never
chooses what is observed), A6-F6 / B6-M6 / R6-C-M3 / R6-D5 / E6-F1 / E6-F5 / E6-F6 (report precision: header lists,
gating wording, the bind message, performance files name their code revision, the noise band, the curve regenerated
with 41 repeats, the re-score guard raises, §5 attributions, §10), B6-M7 (gates re-run at `a058cf2`); documented —
A6-F5 (the identity rule's rounding edge refuses some honest other-unit spellings, §4), B6-M5 (the constructor refuses
a malformed account set for the whole reader, §4). Round 7's: fixed — the BLOCKER and MAJORs above with K7-F1, K7-F2
(cross-unit and offset-unit level controls; the vacuous r6 assertion removed) and K7-F3 (the round-1 liveness loop
includes a pinned budget snapshot); A7-F2 / B7-m1 / R7-C-F3 / R7-D5 / F7-F3 / E7-F3 (providers named as the projection
binds them, `declaration.providers`, with a control that fails on a mutant); B7-m2 / R7-C-F2 / R7-D4 / F7-F2 / E7-F1
(every reader pinned when a verification starts); B7-m3 / R7-D3 / F7-F5 (no lock held across the execution side's
`accounts()` or the read-backs: round 8 put the read-back back under the lock for B8-m1, which reopened this class,
and round 9 closed both with the ticket rule, which round 10 replaced by the bounded wait, §4); B7-m4 / R7-D2 / F7-F4 (an unbound account its owner cannot serialize refuses
nothing); B7-m5 / F7-F7 / E7-F5 (records are detached copies of one serialization; the `remaining_observations` basis
asserted); R7-C-F4 / F7-F6 (a world whose declaration cannot be read reads no account or provider); R7-D6 / F7-F8
(experiments read back whole by the owner's rule, as replay does); A7-F3 / R7-C-F5 / E7-F4 / B7-m6 / R7-D7 (report
precision: the BR1-style budget record, the `compute_budget` basis, the stress test's role, the mutant's file, §8
regenerated and committed at `b572bfc`); K7-F4 (the round-8 brief lists `as_executed`, `matched_level` and the domain
family as changed). To make the follower's refusals safe without a lock around the execution side's callback, round 7
also changed what a refusal of an account BEHIND means: it lasts while the account is behind (an older concurrent
snapshot is behind too), and only a rewritten history is refused for good (§4). Round 8's: fixed — F8-1 / B8-m1 /
E8-F1 (the read-back and the comparison are one locked step again; `accounts()` stays unlocked; superseded by round
9's unlocked read-back and round 10's comparison rule); F8-2 / K8-F1 /
A8-F2 (a fixed-condition control with three independent guards: bind, the family, mint) and K8-F2 (bind applies the
check's level rule to a fixed condition); A8-F1 / B8-m2 / D8-F1 (the round-6 stress test restated for the round-7
rule; the deterministic control of a concurrent older snapshot exists); A8-F5 (the refusal states its real reason);
A8-F6 (a negative zero or an underflowed conversion is not the zero level); A8-F7 / E8-F8 (wording); B8-m3 / R8-C-F3
/ D8-F3 / F8-3 / E8-F6 (the read-back cache keeps one entry per account; the experiment-growth cost is a committed
curve, §8); B8-m4 / D8-F2 (an experiment is served in its owner's read-back form; a torn serialization is refused);
B8-m5 / F8-4 (an eager pin's refusal of any kind waits for a read of that owner and is not recorded otherwise);
B8-m6 (every declaration mode has a control); D8-F5 / E8-F5 (an older-revision world's unnamed bindings are STALE);
E8-F2 (a typed value is never a declared level for the mint guard); E8-F3 (a budget-free world's verification
through the desk is controlled; §2 says which verifications pin); E8-F4 (the r6 experiment control restated);
R8-C-F4 / D8-F4 (an `accounts()` that reads through its reader is refused at once); R8-C-F2 (the K7 test over four
operators with each decision pinned); A8-F4 / E8-F7 (performance re-measured over five alternating runs with ranges;
no label claims more than the ranges show, §8); B8-m7 / D8-F6 / K8-F3 (records and wording); documented —
A8-F3 / R8-C-F1 (a bound at a level declared in another unit is decided on the level as executed, both directions,
§4; whether bind should refuse such a level is an owner decision in the active plan). Round 9's (all MINOR; the
completion gate's review criteria held at `ceaf8cd`, and the brief says not to loop on cosmetic MINORs, so only the
non-cosmetic ones and the records were changed, then reviewed once more in round 10): fixed — B9-m2 / R9-C-F1 /
R9-D-F2 / F9-1 / E9-F1 (no execution-side code under the follower's lock) together with R9-C-F4 / F9-4 / K9-F1 (a
spend an earlier verification was handed is never overtaken by a rollback), both by the ticket rule (§4; it covered only verifications that started earlier, R10-C-F2, and round 10 replaced it);
B9-m1 / R9-C-F2 / F9-2 / R9-D-F1 (experiments detached through a JSON round trip, so nothing is aliased and a JSON
restore changes no digest; round 9 also required exact-type plain JSON data, which hid ordinary spends, R10-C-F1, and
round 10 replaced that rule by the owner's own); B9-m3 (the cache keeps the accounts handed over now); A9-F5 (an eager pin's error
lasts the verification); F9-5 (the exact-level guard compares with the matched level); A9-F1 / F9-3 (bind tests a
fixed condition as every check executes it); A9-F6 / R9-D-F3 / E9-F3 / K9-F2 (STALE only for an older revision, with
a real older-revision control asserting the unnamed binding's own status); R9-D-F4 (a deterministic control of an
older mapping); R9-C-F3 / E9-F4 (refusal messages); A9-F2 / A9-F3 / A9-F4 / A9-F7 / B9-m4 / B9-m5 / R9-C-F5 /
R9-D-F5 / R9-D-F6 / E9-F2 / E9-F5 / E9-F6 / F9-6 (report and record precision: the round-8 narrowing for honest
spellings, the owner question restated, §8 paired comparisons, superseded dispositions, mutant and probe records);
documented — K9-F3 (concurrent verifications refused each other transiently; round 10's bounded wait decides them,
with the contention measured in §8). A9-F7, A9-F2's PROGRESS entry, B9-m5's STALE docstring and E9-F6(d)'s rename were
listed as fixed in round 9 but done only in round 10 (A10-F5). Round 10's: fixed — R10-C-F1 / R10-D-F1 / K10-F2 (each
account read back by its owner from the text its owner writes it down as: no other rule decides readability; a
handed state its owner cannot write down refuses the account for good, which also closes the pre-existing class of
unwritable spends the scope skeptic reproduced on `ceaf8cd`); R10-C-F2 / F10-1 / A10-F1 / E10-F1 / K10-F1 (a
verification decides only once every verification in flight when it compared has compared, whichever started first;
its first candidate, refusing while any other is in flight, refused 157 of 160 admissions in B's p10c load and was
dropped); B10-1 / E10-F4 (each snapshot reads back into a private cache, adopted at its comparison); B10-2 / R10-D-F2
/ E10-F2 (a self-containing value is refused at once by the owner's JSON encoder, not walked forever); B10-4 /
R10-C-m1 / F10-4 (account ids exactly `str`); B10-5 / R10-C-m3 / F10-2 / E10-F3 / R10-D-F3 (a stated revision is
compared as an ASCII decimal numeral, never `int()`-parsed); B10-6 (the ticket is taken inside the `try` that
discards it); F10-5 / E10-F5 (ledger records detached); A10-F6 (bind and the check execute a fixed condition by one
helper, `domains.executed_level`, with a differential control); B10-7 / R10-D-F4 / F10-3 (controls for the unlocked
read-back, the same-thread flag, a failed `accounts()` and B9-m1's equal-content replacement, each failing on its
mutant); A10-F2 / A10-F3 / A10-F4 / A10-F5 / B10-8 / R10-D-F5 / R10-D-F6 / E10-F6 / E10-F7 (report and record
precision: §4 restated for round 10, conversion rounding instead of "an ulp", §8 paired figures and the solver from
the same file, superseded dispositions marked, stale comments and the r7 assertion corrected); documented — B10-3 /
R10-C-m2 / F10-6 (a verification whose `accounts()` does not return makes every verification that compares
meanwhile wait `WAIT_S` and be refused, §4). K10-F1's first ask (state the guarantee for states read back and compared,
and name every unobserved path) was done only in round 11 (E11-F1). Round 11's: fixed — R11-C-F1 / F11-1 / K11-F1
(every read-back step after the account's own serialization runs under one classification; served experiment records
are parsed from the owner's cached text by the C JSON parser, no reader-side `deepcopy`); F11-2 / E11-F1 / R11-C-F4 /
F11-4 (a verification's snapshot is read entry by entry; the guarantee is stated for states handed to and read back
by verifications started before the deciding one compared, with every unobserved path listed, §4); A11-F1 / A11-F2 /
B11-1 / R11-D-F1 / R11-D-F2 / R11-C-F3 (a read-back is tried up to three times and classified by behaviour, with a
recursion failure retried on a fresh thread, so a torn honest move is never refused for good and a failure that
repeats alike, of any exception type, refuses the account for good); a verification waited for that was handed
accounts and left without comparing makes its waiters decide on nothing (F11-1's wait order); B11-3 (the `finally`
resets the flag first and never leaves a ticket in flight); B11-2 / R11-C-F2 / R11-D-F3 / R11-D-F4 / E11-F2 / F11-3 /
K11-F2 (controls: the re-check after the wait, the ledger and recursion classifications, multi-digit revisions, served
records not shared, each failing on its mutant); B11-4 (the cost of the wait names a slow read-back too, with a
large-account contention figure in §8); A11-F3 / R11-D-F6 (the value types each owner rule reads, refuses or
stringifies, §4); A11-F4 (the exact-level guard's controls named above; §5 names the round-9 file revision); R11-D-F5
(PROGRESS item 23's count made precise: 76 with the r10 file's 27 tests then, 79 at `d89dd3b`); E11-F3 (the r8 STALE comment, the r10 contention docstring and revision
label, the read-through refused for good, §4). The documented residuals of earlier rounds are those listed in §4 and §11 (no at-most-once execution or
reservation; the declaration and synthetic labels are the declarer's; liveness is the reader's mode; the provider cache
unless `refresh=True`; the in-process trust boundary; world-derived model and experiment digests; the provider rule
restating `system_runtime` preflight; replay attests self-consistency, not provenance).

### Round 15 dispositions (completed review; repaired locally)

Reviewed source: `95f3869ed020b04c36c098f0c33050aa009212b6`. Six lenses, eight skeptical verifications,
one critic: all 15 returned. Aggregate Q1-Q3/Q5-Q7 NO; **Q4 YES**. The four MAJOR reports describe one seal
lifecycle defect. D/E's PARTIAL answers do not override the confirmed MAJOR; E supplied static findings, not executed
probes. R14-C-F2 was still open at that SHA, while F14-F2's narrower unread-barrier case was closed.

The complete 25-row machine-readable disposition and coverage matrix, original journal results, rerun probes,
failing-first logs and mutation results are in
`docs/work/evidence/br11_local_2026_10_23/round15/`. This is review coverage evidence only, never scientific authority.
Repairs cover sealing during in-flight verification, read-back/entry reconciliation, interruption while parsing or
listing, and recovery of honest detached accounts. CRIT15-2 is the explicit availability residual above.
B15-F4: the preserved R14 base rerun (`reused_base_r14/`) supports 913 passed / 2 failed guards; the missing R12
guard rerun is not reconstructed or retrospectively claimed as present.

Deterministic controls: 33 new R15 tests plus 54 generated traces (87 pass), plus two R13 dictionary-subclass
controls in the mutation harness (89 pass). On reviewed production source that harness has 36 failures / 53 passes.
Sixteen correctness mutants are killed; the single redundant inner-listing-guard removal remains protected by
handing recovery, and removing both safeguards is killed. Mutants include entry-only sealing, omitted comparison
and post-wait checks, interrupt poisoning, discarded before/history checks, and comparison outside the lock.
The generated grammar covers start, wait, compare, seal, spend, top-up, restore, rollback, interruption and redispatch.
It is bounded executable coverage, not exhaustive concurrency analysis or formal proof.

Completed source: L1 115 passed, L2 781 passed, regression 279 passed. Clean-snapshot guards 1496 pass / 2 fail,
affected expensive subset 335 pass / 13 fail / 14 errors, FAST 12792 pass / 67 fail / 190 skipped. All failure IDs
match the unchanged base: **NO NEW FAILURES VS BASE**. Rescore and benchmark MATCHES; Gen1 INTACT.
Exact source SHA and commands: `round15/recovery_candidate.json`, `executions.jsonl`, `gate_differential.json`.
BR1.1 remains NOT CLOSED until the fresh review and all closure evidence are complete.

### Round-16 review and separable local repairs (2026-10-24)

Fresh review at `b8a65bb9d02b5a18e0a8b26779773c1552204dc1`: six lenses, two independent skeptics per MAJOR
alias, and completeness critic complete. Q4 YES; other Qs NO within bounded scope. Four distinct families (2 MAJOR,
2 substantive MINOR), fourteen aliases. Evidence: `docs/work/evidence/br11_local_2026_10_23/round16/`.

Local repairs reuse owner normalization for retained history, preserve identity-incomparable detached observations
until canonical reconciliation, and recover the returned local mapping across the demonstrated registration gap.
Canonical reconciliation runs outside the lock and applies only to the identical pending barrier. Missing or unreadable
history never becomes equality. Distinct unresolved histories can consume memory until reconciliation succeeds;
identity-prefix observations coalesce, and none is discarded to force recovery.

Failing-first: 6 failed / 4 passed on reviewed source; final R16 controls: 16 passed. Six semantic mutants killed.
L2 final: 797 passed; regression: 279 passed. Guards and affected expensive tests have no new failure IDs versus
recorded base. Rescore/benchmark MATCHES; Gen1 INTACT. Five paired affected-path measurements have overlapping
ranges on all six paths: NO SPEED DIFFERENCE ESTABLISHED. These are synthetic software measurements only.
Clean-source FAST: 12808 passed / 67 base failures / 190 skipped; exact failure-ID comparator reports NO NEW FAILURES VS BASE. Fresh Round17 is next for this repair batch. The separate pre-capture challenge still FAILS; no xfail
hides it in the normal suite. BR1.1 NOT CLOSED.

### Round-17 review and owner JSON parity repair (2026-10-24)

Fresh review at `98d72b2ef854012780f4222706884b911c4a2f03`: six lenses, two independent skeptics for all
six MAJOR aliases, completeness critic complete. One known pre-capture MAJOR remains OPEN; D2/F2 identified one
new MINOR where retained entries omitted owner JSON normalization, falsely retiring numeric-key detached histories.
The local repair now follows each owner's complete entry write/read order: ledger owner normalization then its JSON
roundtrip; experiment Scientific Core JSON then owner readback and writability check. No shared permissive serializer
replaces the distinct owner rules. The stale caller-stack docstring exclusion is corrected to an unresolved defect.

Failing-first4 failed/12 passed; 16 new controls; L0 32 passed, L1 201 passed including generated traces, L2 813 passed,
regression279 passed. Seven semantic mutants killed. Guards1528 passed/2 base failures; expensive335 passed/13 base
failures/14 base errors; exact IDs add no new failure. Rescore/benchmark MATCHES; Gen1 INTACT. Five paired measurements overlap on verification/comparison/dispatch/wait/contention (NO SPEED DIFFERENCE ESTABLISHED); seal ranges are lower and nonoverlapping in this bounded run only (6.049–6.331us before, 5.617–5.957us after), no general speed claim. Clean source41a763a6 FAST12824 passed/67 base failures/190 skipped; exact failureIDs in guards/expensive/FAST: NO NEW FAILURES VS BASE. Fresh Round18 next for this repair. Invalid serializer controls do not demonstrate a separate
false-admission path: they preserve the unresolved obligation rather than treating invalid owner output as reconciled.
BR1.1 remains NOT CLOSED. No execution-owner handoff contract has been selected or implemented.

### Round-18 final bounded review: precisely blocked (2026-10-24)

Reviewed `cc7ef06b0d08398173d9448ff47d8abb7e375d44` (source/tests identical to gate source41a763a6).
Six lenses, two independent skeptics per MAJOR alias, completeness critic COMPLETE. Q4 YES; other Qs NO within
bounded scope. One known MAJOR family/six aliases; zero BLOCKER findings; zero open substantive MINOR; no new
separable defect. JSON parity repair held in fresh controls. **BR1.1 NOT CLOSED.**

The concrete owner decision is stable publication of account-ID bindings and recoverable handed history across
checkpoint replacement while reader processing is pending. Matched fresh-dictionary publication controls prevent
this exact loss; a full acknowledgement protocol is optional and not established necessary. Shallow mappings preserve
bindings, not deep payload immutability. Reader-local retry/copy cannot reconstruct already-erased input under the
current mutable callback contract. No new owner contract or weaker observation boundary is selected. See
`docs/work/evidence/br11_local_2026_10_23/round18/OWNER_DECISION.md` and `CRITIC/review.md`.

Maturity: IMPLEMENTED YES (development code, incomplete authority contract), TESTED YES, MEASURED YES;
SCIENTIFICALLY_VERIFIED NO, CERTIFIED NO, FORMAL NO. No ready-for-Kernel claim. No remote change.

## 10. Q1–Q7

Latest completed R18: Q1 NO, Q2 NO, Q3 NO, Q4 YES, Q5 NO, Q6 NO, Q7 NO (bounded review). Closure gate FAILS.

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

**BR1.1 CLOSED within its development contract (2026-10-24).** The owner approved stable publication lifetime; implementation0b605b4 and Round19 correctionsb4bbee0f preserve canonical histories across restore/interruptions and reconcile late generations before final observation. Fresh Round20 sixperspective review, scientific-review skill and completeness critic: Q1–Q7 allNO;0BLOCKER/0MAJOR/0substantiveMINOR.

Evidence and exact results: `docs/work/evidence/br11_local_2026_10_23/round20/README.md`. Targeted885pass; regression279pass; guards1600pass/2basefail; affectedexpensive335pass/13basefail/14baseerrors; cleanFAST12896pass/67basefailureIDs/190skip. Existing unknownprovenance diagnostic increases456to1202 from data-bearing inventory changes; do not call all reasons identical or gates clean. Gen1 INTACT; benchmark/rescore MATCHES.

Explicit AccountPublication callback migration is required for live replacement-following. Published generations retained through source lifetime, terminalclose plus quiescence required for retirement. Final check is an observation boundary, not executor reservation. Persistence, unbounded retention cost and hostile interruption remain limits. No physical validation, certification or formal proof. No push/PR/merge/OD3. Scientific Contract Kernel v0 is next authorized Big Rock and is not started here.
