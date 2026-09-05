# MINIMUM FOUNDATION FOR ELECTRO-THERMAL PROOF — Preregistration

**Milestone:** `MIN-FOUNDATION-ET` — what is the *smallest* scientific foundation
genuinely required to represent a two-way electro-thermal consumer?
**Kind:** foundation-scoping milestone. **This is not `FOUNDATION1`**, and it is
not the Electro-Thermal Vertical Proof.
**Decision status target:** at most `PROPOSED`.
**Evidence target:** at most `L1 EXERCISED`. `L2` is **excluded in advance** — see §11.
**Date:** 2026-09-02
**Branch:** `min-foundation-electrothermal`
**Preregistered before implementation.** Everything below was written before any
source file was added or edited on this branch.

> **This file is immutable.** It records what was committed to *before* results
> were observed. Executed results, deviations, corrections, adversarial findings
> and the final classification go in
> `docs/min-foundation-electrothermal-evidence.md` and nowhere else.
>
> This is **not** a freeze document.

---

# 1. The single question

> What is the **minimum semantic foundation** that a real two-way
> electro-thermal consumer *forces* into existence, over and above the
> contracts Crafty already has?

Nothing else is decided. This milestone does not execute a coupled solve, and
does not define `FIELD0`, `TOPO0`, `SYSTEM0`, `EQIR0`, `DISC0`, `COUPLE0`,
`MAT0`, a materials database, connectors, an orchestration engine, an external
provider abstraction, API/MCP, OpenFOAM or HVAC.

The prior FOUNDATION1 archaeology produced **hypotheses, not requirements**.
Twelve of them are named in §5 and each must be *forced* by the consumer or
deferred.

---

# 2. Hypotheses

## H1 — primary

> A **small** set of reusable scientific semantics can represent the selected
> electro-thermal consumer without domain-specific branches in Crafty Core and
> without requiring the full historical FOUNDATION1 design.

"Small" is quantified in advance: **at most two** new universal semantic
records. Three or more is a falsification of H1 as stated, not a success to be
re-described.

## H0 — null, and it is allowed to win

> **H0(A)** — the existing contracts are **already sufficient**: the consumer is
> representable with zero new universal semantics, and every one of the twelve
> candidate abstractions is deferrable.
>
> **H0(B)** — the proposed new abstraction carries no independent reusable
> meaning and merely wraps domain-specific information: it is either
> reconstructible from existing typed records, or it is an electrical/thermal
> fact wearing a universal name.

**H0(A) is the predicted outcome for eleven of the twelve candidates and is
recorded as a result, not as a failure to repair.** A milestone in which every
initial abstraction survives unchallenged is to be treated as suspect
(milestone brief §14, §15 TEST H).

## Stopping condition, declared before results

If the N0 gate of §6 completes — the entire consumer represented, and every
directed dependency recovered from serialized records by a deterministic reader
— then **H0(A) wins outright, zero contracts are added, and the milestone ends
there.**

---

# 3. Selected consumer skeleton

`architecture-decision-reviewer` was run before this document, on the decision
*"What is the minimum semantic foundation required by a real two-way
electro-thermal consumer?"*, comparing three skeletons. Verdict:
**ACCEPT WITH CHANGES**, selecting **skeleton B**.

## 3.1 The selected skeleton — B

**Resistor component + separate thermal component + environment**, with an
explicit boundary between them:

```text
             ┌──────────────────────────────────────────┐
             │                                          │
   temperature│                                         │ resistance
             ↓                                          │
   [ thermal body B1 ]                    [ R(T) property model ]
             ↑                                          │
   heat input│                                          ↓
             │        [ electrical circuit: V1, R1 ]────┘
             └──────── dissipated power ────────────────┘
```

* **Electrical side:** the **existing, unmodified** `engcore.domains.electrical.dc`
  MNA path — `DCCircuit`, `build_dc_problem`, `ElectricalDCSolver`. Written
  before coupling was contemplated. This is what makes the evidence worth
  anything.
* **Property:** `R(T) = R_ref · (1 + α_TCR · (T − T_ref))`, a real constitutive
  claim with a declared temperature validity range.
* **Thermal side:** a **new** lumped first-order capacity model,
  `C dT/dt = Q_in − hA·(T − T_amb)`, in a module *beside* the byte-pinned
  `domains/thermal/` tree — the sanctioned pattern already used by
  `thermal_conduction1d_bulk.py` and `thermal_conduction1d_schemes.py`.
* **Environment:** ambient temperature and ambient conductance. Without them
  there is no steady state, and no place to ask whether an externally imposed
  condition has a correct typed home.

## 3.2 Why not skeleton A (lumped R(T) + thermal mass, both written fresh)

Not a straw man — it is cheaper and it does force the state-coordinate
question. It is rejected because **both halves would be written by one author,
on one day, against one idea**, which is precisely the differentiation failure
mode master context §54.1 names. Concretely: skeleton A never touches
`DCCircuit`, so it can never discover whether Crafty's *existing* electrical
domain can accept a temperature-dependent resistance at all. That single
finding is the highest-value information available here, and A cannot produce
it. A is dominated on information gained per unit cost, not on cost.

## 3.3 Why not skeleton C (spatial thermal field)

Rejected as premature **and, as available, impossible**. The frozen
`Conduction1DSolver` cannot be the thermal side: its model declares
`"no source or sink term"` (so Joule heat has nowhere to enter), its boundary
and initial conditions are welded shut by design, its field is **dimensionless**
and explicitly disclaims any absolute temperature scale or material property,
and `domains/thermal/` is byte-pinned by experiments T1/T2/T3 with no sanctioned
unfreeze path (master context §57.1). A spatial thermal field therefore means
writing a new PDE solver **plus** `FieldDefinition`, support, topology and
transfer semantics — the entire DATA-BOUNDARY0 and MODEL0-R deferral list — to
learn what the lumped case already teaches. It fails the milestone's own
constraint (§9 of the brief) outright.

## 3.4 What is deliberately *not* protected against

The lumped choice means this milestone says **nothing** about fields, meshes,
tensor properties, spatial transfer or anisotropy. That is a declared ceiling
(§11), not an oversight.

---

# 4. The exact representation to be built

Deterministically inspectable, no LLM interpretation required to recover any
meaning.

| # | Artifact | Contract used | New? |
|---|---|---|---|
| 1 | DC circuit: `V1` source, resistor `R1` | `DCCircuit`, existing | no |
| 2 | Electrical problem | `ScientificProblem` via existing `build_dc_problem` | no |
| 3 | Electrical models (KCL, Ohm, ideal source) | existing `ScientificModelDefinition`s, **unedited** | no |
| 4 | `electrical.material.linear_tcr_resistance` | `ScientificModelDefinition` (`CONSTITUTIVE_MODEL`) | new **record**, existing contract |
| 5 | Property problem | `ScientificProblem` | no |
| 6 | Property realization | `ModelRealizationDefinition` (`ALGEBRAIC`) | new record, existing contract |
| 7 | `thermal.lumped.first_order_capacity` | `ScientificModelDefinition` (`FUNDAMENTAL_RELATION`) | new record, existing contract |
| 8 | Thermal problem, with `InitialCondition` on the state | `ScientificProblem` | no |
| 9 | Thermal realization | `ModelRealizationDefinition` (`ODE`) | new record, existing contract |
| 10 | Lumped thermal solver | `ScientificSolver` protocol | new domain code |
| 11 | The instance | `ScientificTwin` — the **only** instance authority | no |
| 12 | Execution attribution across two domains | `ProvenanceRecord.bindings` at **arity > 1** | no |
| 13 | The three directed quantity dependencies | **contested — this is the milestone's question** | see §6 |

**Row 4 is deliberately additive, never corrective.** The frozen
`electrical.dc.resistor_ohm` model and its declared assumption
`"temperature-independent resistance"` are left **byte-unchanged**. The new
model is the falsifiable alternative to that assumption, and the two coexisting
is how the boundary of the claim gets recorded rather than overwritten.

**Row 12 is free evidence.** `model0r-differential-evidence.md` §9.1 recorded
that the `ExecutionBinding` shape is untested for a computation produced by
several solvers acting together. This consumer produces exactly that, at no
extra cost.

## 4.1 The three dependencies that close the loop

```text
D1  electrical  resistor_power:R1   [W]  →  thermal   heat_input
D2  thermal     temperature         [K]  →  property  temperature
D3  property    resistance          [Ω]  →  electrical R:R1
```

`D1` is *electrical → thermal*. `D2` + `D3` together are *thermal → electrical*,
routed through a material property — which is the scientifically correct
statement of the feedback, not a shortcut.

---

# 5. The twelve candidate abstractions

Each must be **forced** by the consumer. The test for every one is:

> What exact information becomes **impossible**, **duplicated**, **ambiguous**
> or **domain-specific** if this abstraction does not exist?

A weak answer means DEFER. Predicted verdicts, recorded before implementation so
that a surprise is visible as a surprise:

| # | Candidate | Predicted verdict |
|---|---|---|
| 1 | Material Identity | DEFER |
| 2 | Material State | DEFER — strongest residual case |
| 3 | Material Property Identity | DEFER |
| 4 | Property Requirement | DEFER — `ModelInputSpec` already is one |
| 5 | Property Binding | DEFER |
| 6 | `ComponentDefinition` | DEFER |
| 7 | component usage / instance | DEFER, with a recorded arity limitation |
| 8 | state-coordinate binding | **SPLIT**: specification layer DEFER (`ModelInputSpec.role`), instance layer → §6 |
| 9 | `CausalPort` | DEFER |
| 10 | `PhysicalConnector` | DEFER — strongly |
| 11 | hierarchical composition | DEFER |
| 12 | `SystemDefinition` / `SystemInstance` | DEFER — duplicates `ScientificTwin` |

**Duplication proof for #12, required by the brief §6 and stated in advance.**
`ScientificTwin` is already "a versioned declaration of one specific scientific
system instance", carrying `models`, and `declarations` with roles
`PARAMETER / STATE / OPERATING_CONDITION / CONTROL`, globally-unique declaration
names, `assumptions`, `evidence_refs`, `parent`, and a typed
`scientific_context()` that excludes metadata by construction. The whole
electro-thermal instance is declarable in one twin. A `SystemInstance` would
restate it, creating the second authority the brief forbids. The only thing a
twin does not carry is *topology* — and the electrical domain already states
that topology is domain-specific and keeps it in `DCCircuit`.

**No `RealizationFidelity`-style enum, no metadata bag, and no `SURROGATE`-style
member is added to any existing enumeration.**

---

# 6. The N0 gate — built and executed FIRST, not analysed

`model0r-differential-evidence.md` §2.1 recorded a process failure worth not
repeating: the preregistered reduction gate was **analysed rather than
executed**, which showed fields were *absent* without showing that a working
reduction *loses* anything. The falsifier caught it (finding D4).

So this gate is **built and run**, and it runs **before** any new universal
contract is written.

## 6.1 The gate

Represent the entire consumer of §4 with **zero new universal contracts** — the
three problems, four model records, three realizations, the twin, two solvers,
and an ordinary Python orchestration function that passes values from one solve
to the next.

Then execute the **recovery test**:

> A deterministic reader is given **only the serialized records** — problems,
> models, realizations, twin, results, provenance. It must return the set of
> directed quantity dependencies `{D1, D2, D3}`. It may not read the
> orchestration source, may not parse the internal structure of a quantity
> name, and may not consult an LLM.

* **Gate passes** → H0(A) wins outright. Zero contracts are added, the recovery
  reader ships as the proof, and the milestone stops (§13).
* **Gate fails** → the failure must be reported as a **measured count of
  candidate wirings**, not as an argument. Specifically: how many distinct
  quantities of the correct dimension the reader must choose between for each
  dependency.

## 6.2 Predicted gate outcome, with the number stated in advance

**Predicted: the gate FAILS on `D1`.**

Reason predicted in advance: the electrical result carries **at least three**
watt-valued metrics — `resistor_power:R1`, `source_power:V1`, and
`total_resistor_dissipation`. Dimensional matching alone therefore cannot
select the heat source, and picking one requires either parsing the name or
reading the orchestration code. Both are forbidden by the brief (§8: no
string conventions; §13: no LLM interpretation).

Predicted for `D2`/`D3`: same class of failure, smaller candidate count.

**If the predicted count is 1 rather than ≥ 2 — i.e. the wiring is genuinely
unambiguous — H0(A) wins and no contract is added.** This is the falsifiable
part of the prediction.

## 6.3 The single contract this milestone is permitted to add, if the gate fails

Exactly one, named in advance so that scope cannot expand after results:

```text
QuantityDependency
    source_problem_id : str
    source_quantity   : str
    target_problem_id : str
    target_quantity   : str
    unit_exemplar     : str        # dimension, checked by dimensionality
    name, description : str        # prose; disqualified as evidence
```

Constraints on it, fixed in advance:

* **Standalone record, in its own module and its own schema.** It is *not* a
  field on `ScientificProblem`, `ScientificModelDefinition`, `ScientificTwin`
  or `ScientificResult`. `require_schema` is an exact string match with no
  migration path, so an inline field would make every existing payload
  unreadable by a pre-milestone reader; a standalone record is purely additive
  and breaks nothing. **No existing schema version is bumped by this milestone.**
* It **references by name into namespaces the existing records already
  enumerate** — exactly as `InitialCondition.variable` references
  `ScientificVariable.name` and `ObjectiveDefinition.metric` references a metric
  name. It **never parses** a name's internal structure. A reference into an
  enumerated namespace is not a string convention.
* It carries **no value, no state, no solver, no backend, no tolerance, no
  mapping, no interpolation, no relaxation, no convergence criterion, no
  schedule and no ordering**. Anything else would make it a coupling runtime,
  which is `COUPLE0` and is out of scope.
* It contains **no domain vocabulary**. Test-enforced (§10 TEST D).
* A companion endpoint type (`QuantityEndpoint`) is **pre-emptively rejected**:
  two types where flat fields suffice is what a reduction attack exists to
  kill.

## 6.4 The reduction attack the new record must survive

Run **after** it is built, per brief §14. It must be shown that the same
consumer cannot be represented by any of:

1. `ScientificProblem.metadata` — banned as an untyped escape hatch.
2. A field on `ScientificModelDefinition` (e.g. `supplied_by` on an input) —
   would put a *system-composition* fact on a *reusable scientific claim*. The
   same lumped thermal model heated by combustion instead of Joule dissipation
   would be a different model, which is false.
3. `ScientificTwin` declarations — `TwinDatum` holds a typed **value**, not a
   relation between two quantities. Encoding a relation in a value is a string
   convention.
4. `ProvenanceRecord` (`inputs`, `parent_run_id`, `bindings`) — **decisive
   test**: provenance exists only *after* execution, and the brief requires the
   dependency to be represented *without* executing. A representation that
   cannot exist before the run cannot be the representation.
5. One merged "electro-thermal" model spanning both domains — excluded by the
   brief's requirement of **one** electrical and **one** thermal model, and it
   is the monolith that cross-domain composition exists to avoid.

**If any of 1–5 succeeds without semantic loss, duplicated truth, a string
convention, a domain branch or misplaced responsibility, the record is deleted
and H0 wins.**

---

# 7. What will be executed, and the hard boundary

**One open-loop pass. Not a coupled solve.**

```text
T₀  →  R(T₀)  →  electrical solve  →  P₀  →  thermal step  →  T₁  →  R(T₁)
```

This is admissible under the milestone brief §13 — *"must represent, **without
executing the complete coupled solve**"* — because one open-loop pass is not a
complete coupled solve. It is included because without it the two-way claim is
never exercised at all, and the milestone would be `L0 REASONED`, not `L1`.

**Explicitly forbidden in this milestone, and each is a fail condition:**

* fixed-point or Newton iteration between the two sides;
* any coupling convergence criterion, tolerance, residual or relaxation factor;
* rollback, checkpointing, event handling or time synchronization;
* a second electrical solve at the updated resistance (that is the next
  milestone's job);
* any new `ConvergenceState` member;
* any claim, anywhere in a result or report, that a *coupled* solution
  converged.

`R(T₁)` is computed and recorded as the demonstration that the feedback path
exists and is evaluable. It is **not** fed back.

---

# 8. Fail conditions

Declared before implementation. Any one of these means the milestone did not
succeed as specified, and the evidence document says so plainly.

1. More than **two** new universal semantic records are required (falsifies H1
   as stated in §2).
2. Any existing serialized schema version is bumped.
3. A domain-specific branch (`if domain == "electrical"`, or any equivalent
   including a domain string, a component-type test or a units-based domain
   sniff) appears anywhere under `engcore/scientific`.
4. A concrete solver, backend, provider or implementation identity appears in
   any component/system/dependency foundation object.
5. Untyped `metadata` is used to carry any part of the electro-thermal
   semantics.
6. A second authority for scientific instance state is created alongside
   `ScientificTwin`.
7. The temperature-dependence of resistance is recoverable only by parsing a
   string, reading solver settings, or reading orchestration source.
8. Any file under `src/engcore/domains/thermal/` changes, or any frozen digest
   moves.
9. Any pre-existing test is edited, weakened, skipped, reordered, or has a
   tolerance loosened.
10. A coupled solve, fixed-point iteration or coupling convergence criterion is
    implemented (§7).

---

# 9. Change policy

* `ModelRealizationDefinition` is `DESIGN-FROZEN` and its field set **will not
  be modified**. In particular the open applicability-envelope finding
  (`model0r-differential-evidence.md` §4) is **not** decided here. This
  milestone is the second, structurally different consumer that §4 asked for, so
  it **collects** evidence about state-dependent applicability — `α_TCR` makes
  `R` undecidable before execution — and records it. **Deciding the envelope's
  shape requires its own milestone.**
* `ScientificTwin`, `ScientificProblem`, `ScientificModelDefinition`,
  `ScientificResult` and `ProvenanceRecord` gain **no new fields**.
* `engcore/domains/electrical/dc/` is **not edited**. If the consumer needs a
  temperature-aware component, it is added *beside* the existing types, never by
  changing `DCCircuit.canonical_dict()` — a canonical-form change would move a
  fingerprint that other work may depend on.
* `engcore/domains/thermal/` is **not touched at all**.

---

# 10. Required executed tests

| ID | Test |
|---|---|
| **A** | **Representation completeness.** The full skeleton is constructed from typed contracts alone, and every record round-trips. |
| **B** | **Two-way dependency.** The representation explicitly contains both `electrical → thermal` and `thermal → electrical`, each recovered from records by a deterministic reader. |
| **C** | **Property/state dependency.** The temperature-dependent property identifies its required temperature state explicitly and typed — `ModelInputSpec(source_kind=VARIABLE, role=STATE, unit_exemplar="kelvin")` — with no untyped metadata anywhere in the path. |
| **D** | **No domain leakage.** Every file under `engcore/scientific` is scanned for domain vocabulary (`electrical`, `thermal`, `resistor`, `joule`, `voltage`, `temperature`-as-a-branch, …) and for domain-conditional branches. |
| **E** | **Solver independence.** No component/system/dependency foundation object carries a concrete solver, backend, provider or implementation identity. Asserted over the serialized form. |
| **F** | **Twin authority.** No second instance-state authority exists: the twin is the only record carrying instance declarations, and the new record carries no value. |
| **G** | **Serialization.** Every new semantic record round-trips deterministically, byte-identically, and rejects an unknown schema. |
| **H** | **Reduction proof.** The five reductions of §6.4 are each *executed or demonstrated*, and at least one candidate abstraction is explicitly deleted or deferred as a result. |
| **I** | **Existing regression.** DATA-BOUNDARY0 and MODEL0-R evidence remain green. FULL suite baseline is **1635 passed**; FAST is **1140 passed**, 495 deselected. Every pre-existing test must still pass, unedited. |
| **J** | **Open-loop boundary.** No coupled convergence is claimed, and the executed pass performs exactly one electrical solve and one thermal step. |

Plus two findings-tests, predicted in advance so their outcome is evidence
either way:

| ID | Test |
|---|---|
| **K** | **Configuration/state conflation.** Assert the measured behaviour of the existing electrical domain when a temperature-updated resistance is bound under one problem identity. **Predicted: it is refused**, because `resistance_ohm` is part of `DCCircuit`'s canonical identity and its fingerprint. |
| **L** | **Model binding by exact name.** Assert what `ScientificModelDefinition.check_against` reports for a reusable model with generic input names against an instance-scoped problem. **Predicted: `MISSING` issues**, i.e. the existing binding check is unusable for multi-instance domains. |

---

# 11. Evidence ceiling, declared before running

```text
Decision status ceiling:   PROPOSED
Evidence ceiling:          L1 EXERCISED
```

**`L2 DIFFERENTIATED` is excluded in advance and may not be awarded by the
evidence document.** One electro-thermal skeleton is one consumer. `L2` requires
two **materially different** consumers that could have disagreed — and a second
domain pair (mechanical+thermal, chemical+thermal, fluid+thermal) is explicitly
out of scope here. `L3 STRESSED` is not claimable at all: no scale, concurrency,
latency, hostile input or failure injection.

**Per-abstraction levels may differ**, and the evidence document must state one
per abstraction rather than one for the milestone. Anything the consumer did not
exercise gains **zero** evidence and must be recorded as such — including, in
advance: multi-instance arity, hierarchical composition, tensor or anisotropic
properties, non-scalar quantities, external providers, and any joint
(multi-variable) validity condition.

---

# 12. Frozen and untouched artifacts

* `src/engcore/domains/thermal/**` — byte-pinned by T1/T2/T3; not read for
  modification, not edited, not added to.
* `src/engcore/domains/electrical/dc/**` — not edited.
* All 72 pre-existing test files — not edited.
* `docs/data-boundary0-*.md`, `docs/model0r-differential-*.md` — not edited.
* This preregistration, after its own commit.

---

# 13. Stop rule

Stop as soon as the selected skeleton is represented correctly and the reduction
and falsification passes are complete.

Do **not** continue into: a coupled simulation runtime, the Electro-Thermal
Vertical Proof, `FIELD0`, `TOPO0`, generic connectors, a materials registry or
database, capability-graph traversal, a planner, API/MCP, OpenFOAM or HVAC.

Per master context §60: at most **two** adversarial rounds. If material
uncertainty survives both, obtain executable evidence through a spike rather
than a third round of argument.

**The next milestone is the ELECTRO-THERMAL VERTICAL PROOF.** It is not begun
here.
