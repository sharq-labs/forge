# Scientific Core V0 — Foundation

> **We do not reinvent decades of validated scientific work, and we do not
> reduce our platform to a thin wrapper around existing packages.**

That sentence is the design constraint this package exists to satisfy. Both
halves bind. We will not rewrite RK45, LAPACK or a finite-element assembler;
we will also not hand a user a number produced by someone else's library with
no unit, no model identity, no validity statement and no provenance.

## Status

**V0 foundation — contracts only.** No physical domain is implemented: no
Ohm's law, no Newtonian mechanics, no thermal or chemical model, no CFD, no
FEA, no mesh, no multiphysics coupling. The next phase (Domain Validation)
adds Electrical DC and Motion/ODE **through these same contracts**.

**MODEL0-R (additive)** adds scientific capability identity and the
computational realization contract described below. It adds representation
only: no numerical engine, no mesh, no materials, no domain resolver, no
model or solver selection, and no automatic planning of any kind exists.

## Purpose

Give every future scientific domain one vocabulary for: what is being asked,
what model answers it, when that model is valid, which solver ran, what came
back, how well it was checked, how uncertain it is, and where it came from.

## Architecture

```
Scientific Core          contracts, IR, validity, results, provenance
        |
Domain Models            electrical, thermal, mechanics, chemistry (later)
        |
Solver Adapters          adapters satisfying ScientificSolver (later)
        |
Scientific Libraries     SciPy, SUNDIALS, FEniCSx, Cantera, ngspice, ...
```

### Capability / model / realization separation (MODEL0-R)

```
ScientificCapability          what science is required or provided
        |
ScientificModelDefinition     the versioned scientific claim
        |
ModelRealizationDefinition    how that claim is computed
        |
SolverCapability              what computational operation is needed
        |
ScientificSolver              the backend that executes it
```

**A scientific model is not its numerical implementation.** One model may have
several realizations — a closed-form simplification, a reduced-order form, a
native discretization, an external package — that represent the same science
at different formulation, cost, solver requirements, validation evidence and
applicability. Before MODEL0-R the two were one record, so
"the model is valid here but this particular realization is not adequate" was
inexpressible.

`ScientificCapability` and `SolverCapability` are likewise separate types and
must never be conflated. `ScientificCapability` answers *which physical or
scientific operation is needed*; `SolverCapability` answers *which
computational operation a backend can execute*. The relationship between them
is many-to-many: one science may be reachable through several solver
capabilities, and one solver capability serves many sciences.

Neither capability type has a registry. Identifiers are open and namespaced,
so a domain package declares its own without editing the core, exactly as it
already does for solver capabilities. **No capability is defined in the core**
— it understands the grammar of an identifier and nothing about any science.

A realization declares the solver capabilities it needs as
`SolverCapabilityId` values — a typed, validated, canonical identity — never a
concrete solver name and never an unvalidated string. **A solver capability's
identity is its canonical name; `description` is documentation about a
capability and is excluded from equality and hashing.** Anything else would
let one capability appear twice in a set, and let a realization requiring
`core:pde` miss a solver providing it because the two sides worded their prose
differently. `SolverCapability` (name + prose) remains what a solver
*publishes*; `SolverCapabilityId` (name alone) is what a record *references*,
so a reference round-trips through serialization unchanged. The stored
`solver_capability/1` schema is unaffected.

`RealizationRegistry` mirrors `ModelRegistry`'s discipline: instance-based,
deterministic, duplicate-detecting, no global singleton. It looks up and
filters; it does **not** rank, score or select. Preferring one realization
over another depends on the question being asked, and a registry that
answered it silently would make results depend on registration order.

```
Scientific Core          ScientificProblem / Quantity / ScientificResult
        |
Experiment Engine        ScientificExperiment, ScientificEvaluation
        |
Optimizer Adapter        CandidateCodec + ObjectiveEncoder  <- the ONE
        |                                                      translation
Optimization Backends    existing stacked_v0301 / adaptive_stacked_v034
```

The optimizer boundary is deliberately one-directional. The core defines
`NumericSearchBackend` as a protocol and **never imports a concrete
optimizer**; a test enforces this. Search sees normalized `[0,1]^d` vectors
and unitless scores. The scientific layer sees units, always.

## Dependency direction

```
units / results / provenance      (foundational services)
        ^
Scientific IR
        ^
Models
        ^
Solver contracts
        ^
Experiments
        ^
Platform / application layer
```

Nothing in `engcore.scientific` may import a web framework, an API layer, a
database, a visualization frontend, an LLM gateway, the optimizer research
stack, or a benchmark suite. Three guardrail tests enforce this by scanning
the package's own import statements.

## What the Scientific Core owns

Scientific IR (`ir/`) · units contract (`units/`) · model representation and
validity (`models/`) · scientific capability identity (`capabilities.py`) ·
computational realization contracts (`realizations/`) · solver orchestration
contracts (`solvers/`) · validation semantics, uncertainty, provenance and the
result record (`results/`) · experiment representation and the optimizer
boundary (`experiments/`) · the error taxonomy and deterministic
serialization.

Stated as long-term policy: **Crafty owns scientific representation,
scientific model identity, computational realization contracts, capability
semantics, validity, uncertainty, provenance, assurance, and — in a future
milestone — a native numerical runtime.** None of that is delegated.

**Crafty must not require a proprietary external CAE product.** External
scientific solvers are optional providers reached through
`ScientificSolver` adapters, never a dependency of the core. General-purpose
numerical libraries (NumPy, SciPy) remain implementation dependencies.
`ImplementationReference` records which code computed a realization for
provenance; the core never interprets or branches on that identity, which is
what keeps an optional provider from becoming a hidden requirement.

## What external packages own

Numerical algorithms and their correctness: integration, linear algebra, root
finding, meshing, discretization, chemical equilibrium, circuit simulation.
Also the unit algebra itself — Pint is the units backend behind our
`Quantity` contract, chosen so the backend stays replaceable and never leaks
into a scientific record.

## AI independence

`engcore.scientific` imports no LLM provider and never will. If every AI
provider disappeared tomorrow, the Scientific Core would remain fully usable.
AI may later propose problems, models or candidates; it never computes,
validates or accepts a result. Deterministic scientific systems do that.

## Validation philosophy

1. **Numerical convergence is not scientific validity.** They are separate
   fields on a result and separate levels in a report.
2. **Checks coexist; the level is derived.** `ValidationReport` holds checks;
   an attained `ValidationLevel` must be *backed by a passing check that
   declares it*. `require_level` raises otherwise, and a hand-edited record
   claiming an unearned level is rejected on load.
3. **`NOT_RUN` is not `PASS`.** A check that never ran contributes no
   evidence. No result may claim validation that was not performed.
4. **A model states when it is valid.** `ValidityDomain` yields `IN_DOMAIN`,
   `OUTSIDE_VALIDATED_DOMAIN` or `UNKNOWN` — and an *empty* domain is
   `UNKNOWN`, because absence of declared limits is not evidence of unlimited
   validity.
5. **Uncertainty is never invented.** `UncertaintyKind.UNKNOWN` is the honest
   default; a quantified uncertainty must name the method that produced it.

## Fidelity: why the core declares none

`ModelRealizationDefinition` carries **no fidelity field**, and no enum,
flag or metadata bag replaces it. This is a decision, not an omission.

A draft of this milestone required `fidelity: RealizationFidelity` with the
members `ANALYTICAL`, `REDUCED_ORDER`, `ENGINEERING`, `NUMERICAL` and
`HIGH_FIDELITY`. Those members are **not one semantic axis**. They are at
least four, conflated:

| Member | Axis it actually belongs to |
|---|---|
| `ANALYTICAL` vs `NUMERICAL` | solution character — closed form vs discretized and iterated |
| `REDUCED_ORDER` | a reduction operation applied to a full-order model |
| `ENGINEERING` | provenance — handbook correlation, design-code method |
| `HIGH_FIDELITY` | *relative* resolution, meaningless without a stated reference |

Because the field held exactly one member, the ordinary combinations could
not be written down. **`numerical + reduced_order`** and **`numerical +
high_fidelity`** are not edge cases — nearly every reduced-order and every
high-fidelity realization in practice is numerical — and each one forced the
author to discard one true fact to record the other. A required field that
silently deletes information about its most common subjects is worse than no
field.

Widening it to a *set* of members was rejected for the same reason: a set
drawn from four unnamed axes is still not a classification, and this milestone
has no evidence with which to name those axes. `HIGH_FIDELITY` in particular
is not an absolute property of anything — DNS is high fidelity beside LES,
LES beside RANS, RANS beside a lumped correlation — so as a universal category
it asserts nothing checkable.

The axes that *are* evidenced already have homes, and MODEL0-R uses them:

* **`ModelFormulation`** — the computational form (`ALGEBRAIC`, `ODE`, `DAE`,
  `PDE`, `DISCRETE`). One axis, disjoint members, decidable from the record
  itself. A `SURROGATE` member was removed for the same reason as the fidelity
  enum: it names a *strategy*, not a form, and a surrogate is itself posed in
  one of these forms — a response surface is algebraic, a learned
  latent-dynamics model is an ODE. Offering it as a sixth member made a caller
  discard the mathematical form to record the strategy. Surrogate character is
  deferred until there is evidence for a coherent realization-strategy axis.
* **`assumptions`** — where "POD-Galerkin reduction to 12 modes" is stated as
  the falsifiable claim it is, rather than compressed into the label
  `REDUCED_ORDER`.
* **`FidelityRung`/`FidelityLadder` (`engcore.design`)** — an *ordered* ladder
  of execution classes with an explicit rank **per study**. Relative fidelity
  is only answerable against a stated quantity and regime, and this is the
  layer that supplies one. It sits above the core and imports it, so the core
  could not reuse it without inverting the dependency direction anyway.
* **`ModelType` / `ModelValidationStatus`** — epistemic character and
  established evidence, at the model layer where they belong. Note that
  `EMPIRICAL_CORRELATION` and `APPROXIMATION` already covered what
  `ENGINEERING` was reaching for.
* **`engcore.sria.calibration.fidelity`** — a third, distinct thing again:
  measured *relationships* between rungs.

**Calibration was never a fidelity class either.** An earlier draft listed
`CALIBRATED` beside those members. *Fitted to data* is a claim about evidence,
orthogonal to computational form: a reduced-order realization may be
calibrated and so may a high-fidelity one. It was also a second, weaker answer
to a question the package already answers — `TwinKind.CALIBRATED` fails closed
without at least one calibration evidence reference, whereas a fidelity member
would have let any record call itself calibrated with no evidence at all.

Calibration status is therefore **deferred, not renamed**: no calibration
field, flag or subsystem is added here. Whether a *realization* needs a
distinct fidelity or calibration record is a question for a later milestone
that arrives with the study context making it answerable.

Consequently `RealizationRegistry.list()` offers **no fidelity filter**. A
filter over a fact no record declares could only ever lie.

## Provenance philosophy

Every `ScientificResult` requires a `ProvenanceRecord`: a number that cannot
be attributed is not a scientific result. The record carries run id, software
version, git commit, model and solver identities with versions, unit-carrying
inputs, assumptions, tolerances, environment, timestamp and parent run.

The core **collects nothing on its own**. Every environment fact is supplied
by the caller — auto-harvesting machine identity would be both a privacy
problem and a determinism problem. Serialization is deterministic: identical
inputs produce byte-identical JSON.

## Units policy

Scientific input and output preserve units, always. Numerical kernels may
receive plain arrays — through an adapter, via `Quantity.magnitude_in(unit)`
or `CandidateCodec`, which are the only sanctioned exits from the unit-aware
world. A bare number is never silently interpreted: `Quantity.parse("42")`
raises rather than assume dimensionless.

Dimensional agreement is checked by **dimensionality, never by unit string**.
A model declaring `kelvin` accepts a problem in `degC`; `m` and `cm` are
interchangeable; `K` and `V` are not.

## Finiteness policy

`Quantity` refuses NaN and ±Inf. That single invariant keeps non-finite
values out of parameters, bounds, tolerances, results, uncertainties,
provenance and optimizer candidates without a check in each.

The one sanctioned home for non-finite numbers is `RawSolverOutput`: a
diverged backend must be able to report NaN honestly, and forcing an adapter
to hide it would make it lie. The boundary is therefore **raw backend output
may be non-finite; interpreted science may not.** `ObjectiveDefinition.weight`
and `SolverSettings.tolerances` carry their own finiteness checks since they
are plain floats rather than quantities.

## Constraint semantics

For measured `x`, bound `b`, tolerance `τ >= 0`:
`<=` → `x <= b + τ` · `<` → `x < b − τ` · `>=` → `x >= b − τ` ·
`>` → `x > b + τ` · `==` → `|x − b| <= τ`.

Tolerance **relaxes** a non-strict bound and **tightens** a strict one; at
`τ = 0` every operator has its exact mathematical meaning, so `x < b`
correctly fails at `x == b`. Exact equality is permitted — a study may demand
it — though non-zero tolerance is normally right for floating-point results.

## Condition validation: what the core owns

The universal core validates only dimension relationships that are true *by
definition*:

| Condition | Core enforces variable's dimension? |
|---|---|
| `InitialCondition` | **Yes** — it *is* the variable's value at t₀ |
| Dirichlet | **Yes** — it *is* a prescribed field value |
| Neumann | **No** — a derivative/flux, commonly `[variable]/[length]` |
| Robin | **No** — mixed coefficients of several dimensions |
| Periodic / Other | **No** — domain-defined |

Forcing a Neumann flux to match its field would reject correct physics. That
validation belongs to the domain or solver adapter, not here.

## Optimizer boundary policy

`CandidateCodec.encode` rejects a candidate outside its declared physical
bounds; `decode` rejects any component outside `[0, 1]`. Extrapolating past a
declared bound would silently invent a candidate the problem never
authorized. A backend that legitimately proposes just outside a box
constraint calls `clip()` — the explicit, recorded correction path.
`ScientificVariable.require_within_bounds` is named for what it does: it
rejects, it does not clamp.

## Typed scientific values

A parameter is not always dimensional. `ScientificValue` is a small **closed**
union — `Quantity`, `IntegerValue`, `BooleanValue`, `CategoricalValue` — each
schema-tagged and round-trip typed. Adding a kind is a deliberate contract
change, not something a caller can do by passing an arbitrary object.

**Representability is not optimizability.** A categorical parameter can be
declared today; `CandidateCodec` still refuses to encode non-continuous
*design variables*, because every naive encoding silently changes the search
geometry. Model validity context is derived from typed parameters through
`problem.validity_context(extra=...)` — `metadata` is never a side channel.

## Extension path for a new domain

1. Define `ScientificModelDefinition`s with required variables, assumptions,
   a `ValidityDomain` and provided metrics; register them in a
   `ModelRegistry` instance (no global singleton exists).
2. Declare domain capabilities as `SolverCapability("domain:name")` — the
   identifier is extensible, so no core change is needed.
3. Implement a solver adapter satisfying `ScientificSolver`
   (`supports/prepare/solve/validate/extract_metrics`) over a mature library.
4. Express studies as `ScientificProblem` + `ScientificExperiment`. Reuse
   `OptimizerAdapter` to drive any search backend.
5. *Optional, additive:* declare `ModelRealizationDefinition`s naming the
   `ScientificCapability`s each realization provides and requires, its
   `ModelFormulation`, and the solver capabilities it needs. Register them in
   a `RealizationRegistry` instance. A realization claims no universal
   fidelity category; state its approximation in `assumptions`, and any
   ranking in a study-scoped `FidelityLadder`.

Nothing in steps 1–5 requires editing the Scientific Core.

**Step 5 is not required today.** Every existing domain declares no
realization and continues to work unchanged; `RealizationRegistry.for_model`
returns an empty tuple for such a model rather than raising, because "the
science is known and nothing implements it" is a legitimate state that must
stay distinguishable from "no such model". A future automatic planner may
refuse to plan for a model with no declared realization; current manual
workflows are unaffected.

## Scientific failure semantics

Nothing in the core infers missing information, and the contracts are shaped
so a future planner can report *which* of these five states it hit rather
than one undifferentiated "not found":

| State | How it stays distinguishable |
|---|---|
| capability unknown | not in `RealizationRegistry.provided_capabilities()` |
| capability unsupported | provided, but no realization survives the filters |
| scientific model unavailable | `ModelNotFoundError` from `ModelRegistry` |
| computational realization unavailable | `RealizationNotFoundError`, or an empty `for_model(...)` |
| compatible solver unavailable | `SolverNotFoundError`, or a non-empty `solver_capability_gap(...)` |

The planner itself is not implemented. These are the contracts that keep it
implementable without a breaking change.

## Bulk scientific data: identity, not location (DATA-BOUNDARY0)

A `ScientificResult` is a small interpreted record. A solved field is not. One
CFD state is O(mesh), and a record carrying it inline stops being readable,
diffable and cheaply hashable, and drags the whole array through every
provenance and evidence payload that quotes it.

The record therefore **names** its bulk data instead of containing it:

```
Scientific control plane      ScientificResult          no storage knowledge
        | references
Scientific data identity      ScientificDataReference   content, not location
        | resolved by
Runtime / storage plane       engcore.data              locations live here
```

`ScientificDataReference` carries a logical `name`, a `unit`, a value `count`,
a `dtype`, and a **content digest**. It carries no path, URI, host, device,
provider or store identity. Where bytes sit is an execution fact, and an
execution fact must not change what a result *means*: if a path were part of
the identity, moving a file would silently mint a different scientific record
and a provenance chain would rot the first time storage was reorganized.
Relocating an artifact therefore leaves both the reference and the serialized
result **byte-identical**, and there is nothing to migrate.

### What the digest proves, and what it does not

The digest is a statement about bytes, and only about bytes. It gives
**content identity**, **integrity**, **relocation stability** and **content
addressing**.

It does **not** prove scientific equivalence:

* Two computations that are scientifically equivalent to within tolerance will
  in general produce **different** digests. Different hardware, compiler, BLAS,
  thread count, reduction order or library version routinely change the last
  bits of a floating-point result while changing nothing a scientist would call
  the answer. A digest mismatch is evidence that the bytes differ; it is not
  evidence that the science differs.
* A digest match says the byte images agree. It says nothing about whether
  either computation was correct, converged or physically meaningful — those
  belong to validation and uncertainty, which are separate fields on the
  result.

Tolerance-level comparison of two datasets is a real and different operation.
Nothing here implements it or substitutes for it.

**Identity is over the canonical byte image**, not IEEE value equality: `-0.0`
and `0.0` are distinct preimages, as are distinct NaN payload bit patterns.
Normalizing before hashing would mean the digest no longer attests to the bytes
a solver actually produced, which is the one thing it exists to do. A producer
that exposes a buffer that is not 1-D contiguous float64 is refused rather than
converted, so a float32 or device array cannot be silently upcast into a digest
that describes data nobody computed.

### What the reference does not decide

`count` is a count of values. It is **not** a shape, mesh, topology or field
support, and no descriptor field exists. `count` may be zero: this milestone
found no evidence that an empty scientific dataset is invalid, and no storage
invariant requires otherwise. The consequence is documented rather than banned
— every empty payload of a dtype shares one digest, so one empty blob satisfies
every empty reference; a consumer for which emptiness is a domain error
enforces that itself.

**DATA-BOUNDARY0 intentionally does not define `FIELD0`/`TOPO0` descriptors.**
Shape, support, coordinate frame and topology semantics remain deferred and
undecided. Nothing here closes the reference against future work, and no rule
is recorded about the form a future descriptor must take. One factual
constraint a later milestone will have to plan around: `require_schema` is an
exact string match with no migration path, so changing a schema version string
makes existing stored records unloadable by the current reader. That constrains
how an evolution is rolled out; it does not forbid one. Widening the closed
`dtype` or `digest_algorithm` sets is a value change and touches no schema.

### The legacy `artifacts` field

`ScientificResult.artifacts` is **unchanged**. It is legacy, generic and
untyped, it predates this milestone, and every value that loaded before still
loads — including on the deserialization path. Absence of an in-repo producer
is not evidence that no external caller exists.

New scientific-data code must not use it as the bulk-data channel: it carries
no unit, no count and no content identity, so nothing can check what was put in
it. Bulk data belongs in `data_references`. A fitness test
(`test_f4b_new_scientific_data_code_does_not_use_the_artifacts_channel`)
asserts that the modules introduced by DATA-BOUNDARY0 never write `artifacts`;
it constrains new code only and breaks no stored value.

Reference **names** are likewise not policed by shape. `phase/alpha`,
`velocity/x` and `species:H2O` are scientific names that happen to contain
punctuation, and rejecting them on the suspicion that they resemble a path
would let a storage concern dictate scientific vocabulary. Storage
independence is achieved by the record having no storage field at all, not by
guessing at strings.

Nothing in `engcore.scientific` imports `engcore.data`, and nothing in
`engcore.data` imports a named domain pack. Both directions are enforced by
tests. Only a domain/orchestration module may depend on both.

### Failure semantics for bulk data

| State | Answer |
|---|---|
| present and intact | the values |
| absent from every consulted store | `BulkDataUnavailable` |
| present but corrupt, truncated or substituted | `BulkDataIntegrityError` |

There is no fourth outcome. Empty, zero-filled and nearest-match are never
*fabricated*, and a bulk failure never invalidates the scalar values of the
result that referenced it — those were computed, validated and attributed, and
remain usable. (An empty result that was genuinely stored and verifies against
its reference is a legitimate answer, not a fabricated one.)

### Schema version

`data_references` is **scientific content**, not decoration: it is the result's
statement of which bulk data the claim is about, and for `RawSolverOutput` it
is the only statement that a solve produced bulk data at all once the array has
left `diagnostics`. A reader that accepted such a payload and then ignored the
field would return a result that silently understates what was computed.

So the version moves. The writer emits `scientific_result/2` and
`raw_solver_output/2`; the reader accepts `/1` and `/2`:

| Direction | Behaviour |
|---|---|
| `/1` payload → this reader | succeeds, `data_references == ()` |
| `/2` payload → this reader | succeeds, references round-trip |
| `/2` payload → a pre-milestone reader | **fails loudly** on schema mismatch |
| unknown `/3` → this reader | fails loudly; the accept-set is exact strings |

The mechanism is one helper (`require_schema_any`) and one branch per
`from_dict`. A `/1` payload loads with no references **by version, not by key
presence** — `/1` predates the contract and cannot have written one.
Re-serializing a `/1` payload writes `/2`; that one-way upgrade is intended.
This is not a migration framework and none is implied: a third version means
one more string.

The cost — a pre-milestone reader can no longer read any new payload, including
scalar-only ones — was accepted deliberately. Loud failure is recoverable;
silent understatement of a scientific claim is not.

**Status:** `PROPOSED`, evidence `L1 EXERCISED`. Two storage backends written
by one author against one interface differentiate nothing; heterogeneous
provider evidence comes later.

* Preregistration (written before execution): `docs/data-boundary0-prereg.md`
* Evidence (written after execution): `docs/data-boundary0-evidence.md`

## One quantity supplied by another (MIN-FOUNDATION-ET)

A `ScientificProblem` states what is to be computed. It does not state where its
externally imposed inputs come from, and for one problem that is right: a
control is imposed, and by what is not the problem's business.

Composing two problems makes it wrong. Then there is a fact with no home —
*the quantity named X of problem P supplies the quantity named Y of problem Q*
— and without a record for it that fact survives only in an orchestration
function's control flow.

```
Scientific claim          ScientificModelDefinition   reusable, supplier-free
        |
Computation               ModelRealizationDefinition  how the claim is computed
        |
System composition        QuantityDependency          what supplies what
```

`engcore.scientific.composition.QuantityDependency` is a standalone
`quantity_dependency/1` record naming two endpoints and a dimension. It carries
no value, state, solver, backend, tolerance, mapping, interpolation,
relaxation, convergence criterion, schedule or execution order — those belong to
a coupling *runtime*, and this is a *declaration*. It has no direction flag:
source and target are the direction.

**It is standalone rather than a field on an existing record, for two reasons.**
`require_schema` is an exact string match with no migration path, so an inline
field would make every stored payload unreadable by a pre-milestone reader.
More importantly it would be *wrong* on `ScientificModelDefinition`: a model is
a reusable claim, and recording on it that its input comes from some other model
would make the same claim, fed from a different source in a different system, a
different model. The supplier is a property of the assembly, never of the
science. `ProvenanceRecord` fails for a sharper reason — provenance exists only
*after* a run, and a composition must be inspectable before anything executes.

### Endpoint identity, and the invariant it rests on

An endpoint name resolves into `result.values ∪ problem.variables ∪
problem.parameters`. `ScientificProblem` guarantees uniqueness across variables
and parameters; result metrics are a third namespace with no such guarantee, so
the rule a composing domain must hold is **one name means one thing, across a
problem's declarations and the metrics of results computed from it** — the rule
`ScientificResult` already enforces inside its own record, one level out.

It is stated rather than enforced, because enforcing it would require the record
to hold both sides, which it deliberately does not. Violating it is silently
harmful when the two meanings share a dimension: a `STATE` variable at the start
of an interval and an output metric of the same name at the end are both the
same unit, both check clean, and nothing says which was transported.

Endpoint names are **references into namespaces existing records enumerate**,
exactly as `InitialCondition.variable` names a variable. Nothing parses a name's
internal structure. `ScientificResult.data_references` is deliberately *not*
consulted: it would make a field endpoint check clean while nothing in the record
can state how a field is transported between supports, and an honest `MISSING`
beats a clean check implying a transfer semantics no contract provides.

### What absence means

An externally imposed input with **no** dependency record is imposed by the
environment. `unresolved_inputs` reports every `CONTROL` variable and every
`STATE` variable no declared condition determines — initial *or* boundary;
`externally_imposed` reports those a dependency does not supply. Both readers
are **deliberately incomplete**, and the incompleteness is the finding: a
quantity a domain models as a configured `ScientificParameter` carries a value,
so it reads as settled even when a composition supplies it. Nothing in the
contracts distinguishes *configured* from *computed elsewhere*.

### What was not built

No `ComponentDefinition`, component instance, `SystemDefinition`,
`SystemInstance`, causal port, physical connector, hierarchy, material entity,
material state or property hierarchy. Each was tested against *what exact
information becomes impossible, duplicated, ambiguous or domain-specific
without it?* and each gave a weak answer for the consumer at hand.
`ScientificTwin` remains the versioned record for one system instance; a second
would be a duplicate, not a layer. No fan-in combination rule exists — two
sources on one target are representable and nothing states how they combine,
which is recorded as a measured gap rather than filled from one consumer.

**Status:** `PROPOSED`, evidence `L1 EXERCISED` for the record itself and
**`L0 REASONED` for most of the deferrals** — they were argued, not confronted
with a case that could have forced them. One consumer, one arity, one direction
of causality, scalar quantities only.

* Preregistration (written before execution): `docs/min-foundation-electrothermal-prereg.md`
* Evidence (written after execution): `docs/min-foundation-electrothermal-evidence.md`

## Deliberately deferred

Symbolic/expression constraints; mixed-variable encoding (integer,
categorical, boolean are *representable* but not encodable in V0); PDE
machinery beyond generic condition types; a UQ engine; persistence and
databases; distributed scheduling; an AI planner; RAG; visualization.

Deferred by DATA-BOUNDARY0 specifically: a generic field model; topology;
discretization contracts; interpolation; transfer operators; a Probe framework;
field uncertainty; MPI; GPU; object storage; a retention, ownership or
garbage-collection system for stored artifacts; a distributed filesystem; and
any external provider. Content-addressed blobs are shared by construction, so a
store deletion or a move with `remove_source=True` affects every reference to
that content — a documented consequence of the dedup, not a lifetime system.

Deferred by MODEL0-R specifically: capability-graph traversal; domain, model
and solver resolvers; a knowledge graph; materials and substances; geometry,
mesh and field structures; FEM/FVM/FDM and PDE execution; multiphysics
coupling; state, history and degradation; any external-solver adapter; and a
per-realization calibration record. A realization record carries none of these
and gains no metadata mapping in which to hide them — a concept that cannot be
stated cleanly is deferred explicitly, not smuggled in untyped.

Deferred by MIN-FOUNDATION-ET specifically: a coupling runtime of any kind —
iteration, convergence criteria, relaxation, rollback, scheduling, time
synchronization, transfer or interpolation; component, port, connector, system
and hierarchy records; materials, material state and a property hierarchy; a
fan-in combination rule; field and tensor endpoints; and enforcement (rather
than statement) of endpoint name uniqueness. `QuantityDependency` carries none
of these and has no metadata mapping in which to hide them.

**Work packages are pulled by a proof, not pushed by a layer map**
(master context §54.2). `CAP0`, `MAT0`, `FIELD0`, `SYSTEM0`, `TOPO0` and the
rest remain the catalogue this draws from; which of them arrives next, and how
much of it, is decided by what the next proof actually requires. The next
milestone is the **ELECTRO-THERMAL VERTICAL PROOF**, which executes the coupled
simulation this foundation only represents. It is not implemented, and requires
its own preregistration written before any source file is added or edited.
