# The scientific claim layer (`engcore.claims`)

**Status: EXPERIMENTAL.** It is not part of any Core Freeze. It is classified in
`tests/test_core_api_layering.py::NON_CORE_PACKAGES` and in
`docs/CORE_FREEZE_POLICY.md`.

The layer takes a **structured scientific claim** and returns an **auditable
assessment**. The caller does not name a system, case, quantity key or report
index:

```
ScientificClaim
   │  compile_claim        CORE-2  routing over declared capabilities, READY / NEEDS_INPUT / ...
   │  select_capability    CORE-4  applicability decides; executability never does
   │  plan_experiment      CORE-5  deterministic plan + SRIA charter, never executes
   │  assess_routes        CORE-6  route independence computed from pinned identities
   │  execute_plan                 one run; the report must be bound to the plan
   │  assemble_evidence    CORE-8  SRIA Evidence via the existing bridge, channels by source
   │  context_problems     CORE-9  evidence counts only for the context it was made for
   │  assure                       Arbiter + issuer-gated CredibilityReportCritic
   │  compare / verdict    CORE-10 SUPPORTED / CONTRADICTED / INSUFFICIENT_EVIDENCE
   │  explain              CORE-13 typed items, each a pointer into the record
   ▼
ClaimAssessment.to_dict()   read back and re-derived by verify_assessment
```

## Where it sits, and what it does not own

The package sits **above** `scientific`, `sria` and `mcp`. It has to: a claim uses
SRIA's discrepancy and uncertainty-channel vocabulary, and the Scientific Core
must not import SRIA. It defines no physics, no validation vocabulary and no
decision engine. Each part of an assessment reuses the existing authority for it:

| concern | authority reused |
|---|---|
| the comparison | `ConstraintDefinition` (offset-temperature and tolerance rules, I-22/R-48) |
| applicability | each model's own `ValidityDomain.assess`, `ValidityStatus`, `UnknownReason` |
| route independence | `SCIENTIFIC_ROUTE_DECLARATIONS`, `canonical_component_identity`, the consensus rule |
| credibility of a run | `CredibilityEvidenceReport.verdict` |
| evidence | `evidence_from_credibility_report` (the value comes from the report, never the caller) |
| levels | `CredibilityReportCritic` through the `Arbiter`, with issuer gating |
| uncertainty channels | `CHANNEL_OF_SOURCE`, `UncertaintyDeclaration`, and the obligation for each required uncertainty channel |
| discrepancy | `ModelDiscrepancy`, `model_discrepancy_check` |
| decision / context | `CampaignCharter`, `TerminalDecision`, `ConfidenceRequirement` |
| repair hints | `domains.repair.ConditionRepair` (the domain's own exact inversion) |

## The claim (CORE-1)

`ScientificClaim` is frozen and strict. On read, any unknown or missing field is
refused. It carries:

- the QOI, its units and optional instance qualifiers;
- a `THRESHOLD` (`<` `<=` `>` `>=`) or `TOLERANCE_BAND` (`==` plus a tolerance) comparison;
- a target, either a literal quantity or `input_ref` to a stated input;
- the capability identifiers the claim requires;
- inputs, split three ways:
  - `operating_context` (the regime the claim is about);
  - `known_inputs` (the subject);
  - `missing_inputs` (declared unknown, never defaulted);
- caller assumptions;
- the decision;
- the `ValidationLevel` bar;
- an uncertainty demand, in SRIA channels with an explicit coverage factor;
- an explicit `ModelDiscrepancy`, where `UNKNOWN` is allowed.

Scientific identity excludes the id, the prose statement and the output format.
The prose statement is never read.

## Capabilities (CORE-3), and how to add one

A `CapabilityDeclaration` states what one executable capability produces, provides,
accepts, runs, can attain and cannot assess. Routing matches **declared
identifiers only**. The production declarations (`engcore.mcp.capabilities`) are:

- `system.electrothermal`;
- `system.battery`;
- `benchmark.nafems_t3`.

They are built once per process (about 1 s) and derived from each system's
`CaseDescription`, the model definitions and the realizations the system binds.

To add a capability for a new system:

1. Write one function returning a `CapabilityDeclaration`, beside the system. Derive
   every field a record already states: inputs from the case description, models
   from the model registry, provided capabilities from realizations, and
   produced units from `ModelOutputSpec`. Hand-write only what no record states:
   roles, activation, and the conditions the system never assembles.
2. Give it an executor, `(case, *, run_id) -> CapabilityRun`, that calls the
   system's existing run function.
3. Add the declaration to `production_registry()`.
4. Pin every hand-written fact against a real run, following
   `tests/claims/test_claims_production_capabilities.py`:
   - declared outputs equal the report's values;
   - predicted active models equal the report's validity records;
   - attainable levels bound the attained levels;
   - declared-unassessable conditions equal what a run leaves UNKNOWN.

No central switch is edited, and no keyword is matched.

## Compilation and selection (CORE-2, CORE-4, CORE-7)

**Statuses.** The compiler returns one of:

- `READY`;
- `NEEDS_INPUT`;
- `AMBIGUOUS`;
- `UNSUPPORTED_CAPABILITY`;
- `REFUSED`.

It also returns *predicted gaps* that a READY run cannot close: an unattainable
level, an unquantified demanded channel, an unsupported discrepancy, or pending
or at-risk applicability.

**Pre-execution applicability.** Each candidate's active models are assessed with
their own validity domains, over exactly the inputs the claim states. Every
UNKNOWN condition gets a basis:

| basis | meaning | effect |
|---|---|---|
| `MISSING_CONTEXT` | a caller input the condition reads directly is unstated | blocking: NEEDS_INPUT |
| `PENDING_EXECUTION` | reads state the run computes. Inputs known only from the system's regime-unioned `unlocks` measurement are *advisory* | decided by the run |
| `DECLARED_UNASSESSABLE` | the capability declares it never assembles the context | candidate rejected |
| `NOT_ASSESSABLE` | evaluated and inconclusive; no declaration repairs it | shown |

**Rejections.** A candidate is rejected when:

- a model is OUTSIDE its validated domain;
- its applicability can never be established;
- it would silently drop a stated input;
- a stated input is invalid;
- a qualifier would select nothing.

**Ranking.** UNKNOWN never beats IN_DOMAIN. Two applicable candidates are
AMBIGUOUS and are never ranked.

**Repairs.** Every `RepairAction` field is read from a declaration: an input's
description, dimension and unit, the conditions it unlocks, a model's own
`RangeCondition` bounds, or the identifiers that separate two candidates. Each
repair names its `source`.

## Planning and routes (CORE-5, CORE-6)

`ExperimentPlan` fixes what runs:

- the capability digest;
- model instances and versions;
- the exact case and its digest;
- numerics the system will default;
- the route classification;
- a step graph: execute, validity checks, level checks, uncertainty checks, oracle, evidence, assure, compare.

A requirement nothing can meet is kept as an `UNAVAILABLE` step.

**Identity.** The plan builds the SRIA charter, which binds the claim identity,
the plan's core digest, the QOI, the discrepancy and the uncertainty demand.
Evidence from the plan may carry only one context reference:
`charter:<digest>#decision:<id>`.

The same scientific request always gives the same plan. An edited plan is
refused on read.

**Solver routes.** These are classified from their pins as:

- `ALIAS`;
- `SHARED_IMPLEMENTATION`;
- `PARTIALLY_INDEPENDENT`;
- `INDEPENDENT`;
- `UNVERIFIED`.

A test holds this prediction to `CrossSolverConsensus` on every pinned pair. Only
`INDEPENDENT` could earn `CROSS_SOLVER_VALIDATED`, and that is **verification**.

## The verdict (CORE-10)

Support and contradiction clear the **same** admissibility bar:

- the claim is ready;
- the case was executed;
- the report is bound to the plan;
- evidence is in the plan's context;
- the credibility report is `SUPPORTED`;
- the assurance decision is `VALID`;
- a demanded discrepancy is supported.

| admissible? | comparison | verdict |
|---|---|---|
| yes | satisfied over the whole band | **SUPPORTED** |
| yes | violated over the whole band | **CONTRADICTED** |
| yes | the band contains the bound, or a demanded channel is unusable | INSUFFICIENT_EVIDENCE |
| no | anything | INSUFFICIENT_EVIDENCE |

A model outside its validity domain, a `NOT_SUPPORTED` run, a missing level and an
UNKNOWN demanded channel are all *cannot establish*. None of them is *false*.

**The comparison rule.**

- With **no channel demanded**, it is a point check. Known uncertainty is shown
  and not used, so missing uncertainty can never answer more firmly than known
  uncertainty.
- With channels demanded, it is a guard-banded decision:
  - only the demanded channels count;
  - each must be quantified *and* attributed to that channel;
  - a STANDARD record contributes `k·u`, using the claim's coverage factor (no `k` declared means no band);
  - an INTERVAL record contributes its own bounds;
  - half-widths are summed **linearly**, with no independence assumed.

## Uncertainty, context, sources, oracles (CORE-8, 9, 11, 12)

**Transport.** Each record is classified as `UNKNOWN`, `ATTRIBUTED`,
`UNATTRIBUTED` or `MIXTURE`. Only ATTRIBUTED records enter a channel. The bridge's
`unattributable_uncertainty="unknown"` files COMBINED and UNSPECIFIED records
under no channel and states that in the declaration.

**Context.** `context_problems` refuses evidence whose context, subject, run,
capability, value or discrepancy is not the plan's. This closes audit finding N2
on this path; the certified Arbiter still does not compare `context_ref` with its
charter.

**Sources.** There is one adapter per `SourceClass`, and SRIA's
`IMPLEMENTED_SOURCE_CLASSES` decides which are implemented. BENCHMARK, MEASUREMENT
and LITERATURE answer `NOT_IMPLEMENTED`.

**Oracles.** `discover_oracles` reaches trusted oracles only through declared
routes. A trusted oracle is reported only when its content reproduces the
repository pin. Applicability is `EXACT`, `MISMATCH` or `UNKNOWN` against the
claim's stated conditions.

## Explanation and read-back (CORE-13)

`explain(record)` is a pure function of the serialized record. Its item kinds are:

- `FINDING`;
- `MISSING_EVIDENCE`;
- `MODEL_LIMITATION`;
- `NUMERICAL_FAILURE`;
- `VALIDITY_FAILURE`;
- `UNCERTAINTY_GAP`;
- `VALIDATION_GAP`;
- `ASSUMPTION`;
- `CONTRADICTION`;
- `REPAIR_ACTION`.

Every item carries a JSON pointer to the value it restates.

`verify_assessment(record, registry)` re-derives everything from the claim, plan
and credibility report the record carries. It then compares the whole record and
refuses any edit.

## Behaviour on the production registry

| claim | verdict |
|---|---|
| NAFEMS T3 probe temperature ≈ 309.75 ± 0.5 K at the benchmark point | SUPPORTED, BENCHMARK_VALIDATED |
| the same, against a 305 K target | CONTRADICTED |
| electrothermal `final_temperature < 353.15 K`, example case | SUPPORTED (verification only, and said so) |
| the same, with EXPERIMENTALLY_VALIDATED required | INSUFFICIENT_EVIDENCE |
| T3 at another conductivity | INSUFFICIENT_EVIDENCE (outside validity; nothing runs) |
| any battery claim | INSUFFICIENT_EVIDENCE: the battery boundary never assembles its lumped body's applicability |

## Known limitations

- **Uncertainty.** No production domain quantifies uncertainty. A claim that
  demands a channel is INSUFFICIENT_EVIDENCE on every production system today.
  That is an honest answer, and it is tested.
- **Battery.** No battery claim can be SUPPORTED until the boundary accepts a
  body-applicability declaration.
- **Cross-solver.** CROSS_SOLVER_VALIDATED is withheld on the MCP electrothermal
  path: there is no artifact-verified independence evidence.
- **Sources.** Only SIMULATION evidence is implemented.
- **Repair hints in read-back.** A domain's `ConditionRepair` hints are read back
  as recorded data. They only feed repairs, never the verdict.
- **Natural language.** Natural-language parsing is deliberately absent. An outer
  adapter may produce `ScientificClaim` records, and nothing it writes in
  `statement` is read.

## Performance

These medians were measured on the development machine for the finished series:

| claim | compile | plan | execute | whole assessment |
|---|---|---|---|---|
| NAFEMS T3 | 0.8 ms | 1.0 ms | 24 ms | 31 ms |
| electrothermal example | 2.1 ms | 2.1 ms | 9 ms | 18 ms |

Building the production registry takes about 0.1 s, or about 1 s including the
first imports of the system modules. It happens once per process and is cached.
Routing and planning never import or walk the repository per request.

The remaining overhead is evidence assembly, the Arbiter, and building and
explaining the record. It is a few milliseconds: comparable to the lumped
electrothermal solve, which is itself tiny, and small against any
non-trivial simulation.

The integrity invariants and the tests that hold them are listed, executable, in
`tests/claims/test_claims_invariants.py`. The guards those tests protect are
mutation-checked in `tests/claims/test_claims_mutations.py`.
