# MINIMUM FOUNDATION FOR ELECTRO-THERMAL PROOF — Evidence

**Milestone:** `MIN-FOUNDATION-ET`
**Decision status:** `PROPOSED`
**Evidence level:** `L1 EXERCISED` for one abstraction; **`L0 REASONED` for most of what the milestone concluded** — see §13, which is the most important section of this document.
**Falsifier verdict:** SURVIVES WITH REQUIRED CHANGES. One `BREAKING-RISK` was found and **closed before commit**.
**Date of this record:** 2026-09-02
**Branch:** `min-foundation-electrothermal`

> **Temporal boundary.** `docs/min-foundation-electrothermal-prereg.md` is the
> preregistration: committed at `b81de39`, before any source file was added or
> edited on this branch, and immutable. **This** document was written after
> execution. Deviations, corrections, adversarial findings and the final
> classification live here and nowhere else.
>
> This is **not** a freeze document.

---

# 1. Result against the preregistered hypotheses

**H1 is supported, at the bottom of its own stated range. H0(A) loses on a
measurement, not on an argument — but it loses by exactly one record, and the
eleven deferrals it did not touch remain `L0`.**

Prereg §2 allowed "at most two" new universal semantic records and declared
three or more a falsification. **One** was forced:

```text
QuantityDependency
```

H0(B) — that the new abstraction merely wraps domain-specific information — is
refuted by construction: the record contains no domain vocabulary, no domain
enum member and no domain unit, survives all five preregistered reductions, and
was built for an unrelated domain pair in a test that imports nothing from
either implemented domain.

## 1.1 What the executed pass produced

One resistor `R1` (10 Ω at 293.15 K, α = 0.00393 K⁻¹) on a 5 V ideal source,
thermally a lumped body (C = 2.5 J/K, hA = 0.05 W/K, ambient 300 K), advanced
120 s from 300 K.

| Stage | Quantity | Value |
|---|---|---|
| initial state | `T₀` | 300.000000 K |
| property | `R(T₀)` | 10.269205 Ω |
| electrical solve | `P` | 2.434463 W |
| thermal step | `T₁` | 344.272271 K |
| property, feedback demonstrated | `R(T₁)` | 12.009105 Ω |

ΔR = **+16.9429 %**. The feedback is not a rounding artefact; it is the
dominant effect at this operating point, and it was **not fed back**.

## 1.2 Predicted vs. observed (prereg §6.2, §10)

| # | Prediction | Observed |
|---|---|---|
| 1 | The N0 gate **fails**: ≥ 2 dimensionally admissible sources per target | **confirmed** — 5 / 4 / 5 |
| 2 | ≥ 3 watt-valued metrics in the electrical result | **confirmed** — 4 |
| 3 | `TEST K`: the electrical domain **refuses** a temperature-updated resistance under one problem id | **confirmed** — `CircuitBindingError` |
| 4 | `TEST L`: `check_against` reports `MISSING` for a reusable model against an instance-scoped problem | **confirmed** — `resistance`, `voltage_across` |
| 5 | Eleven of twelve candidates deferred | **confirmed as a decision**; see §13 for what that is worth as *evidence* |
| 6 | At most two new universal records | **confirmed** — one |

No prediction was falsified.

**Two things happened that were not predicted**, and both are findings:

* **The third dependency's target is not merely ambiguous — it is invisible.**
  `R:R1` is a configured `ScientificParameter` carrying a value, so a
  records-only reader has no reason to think anything supplies it. It sits
  among seven genuinely configured parameters and is indistinguishable from
  them. Ambiguity was predicted; undetectability was not.
* **The capability layer is asymmetric by physics.** See §5.

---

# 2. Reviewer verdict (prereg §3)

`architecture-decision-reviewer`, on *"What is the minimum semantic foundation
required by a real two-way electro-thermal consumer?"*, comparing three
skeletons. Verdict: **ACCEPT WITH CHANGES**, selecting **skeleton B** under
contract scope **N0 (zero new universal contracts)** as the gate.

Its seven required changes were all carried into the preregistration and
honoured. Its own stated weakest link — *"the coupling statement … I judge
deferrable"* — is the one that **did not survive execution**, and it named in
advance the condition under which it would fall: *"if the coupling relation
cannot be recovered from the serialized artifacts by any deterministic rule."*
It could not be. That is the milestone's central result, and it arrived as a
measurement the review had asked for rather than as a reversal.

**Skeleton A** (lumped R(T) + thermal mass, both written fresh) was rejected as
too weak: both halves would have been written by one author on one day against
one idea, and it never touches `DCCircuit`, so it could not have discovered
`TEST K`. **Skeleton C** (spatial thermal field) was rejected as premature and,
as available, impossible: the frozen conduction model declares *no source
term*, welds its boundary and initial conditions, carries a **dimensionless**
field explicitly disclaiming any temperature scale, and lives in a byte-pinned
tree with no unfreeze path.

---

# 3. Abstractions implemented

## 3.1 The one universal record

`src/engcore/scientific/composition/dependency.py` — `quantity_dependency/1`.

```text
QuantityDependency
    source_problem_id : str
    source_quantity   : str
    target_problem_id : str
    target_quantity   : str
    unit_exemplar     : str     dimension, checked by dimensionality
    name, description : str     prose; disqualified as evidence
```

with `check_against(target_problem=…, source_problem=…, source_result=…) ->
tuple[BindingIssue, …]`, and two module functions `unresolved_inputs(problems)`
and `externally_imposed(problems, dependencies)`.

It carries **no** value, state, solver, backend, tolerance, mapping,
interpolation, coordinate transform, relaxation factor, convergence criterion,
schedule or execution order. It has no direction flag: source and target *are*
the direction.

## 3.2 Domain and system records — no new contracts

| Record | Contract used | New contract? |
|---|---|---|
| `electrical.material.linear_tcr_resistance` | `ScientificModelDefinition` | no |
| `…linear_tcr_resistance.closed_form` | `ModelRealizationDefinition` | no |
| `thermal.lumped.first_order_capacity` | `ScientificModelDefinition` | no |
| `…first_order_capacity.closed_form` | `ModelRealizationDefinition` | no |
| the instance | `ScientificTwin` | no |
| cross-domain attribution | `ProvenanceRecord.bindings`, arity 5 | no |

`R(T) = R_ref(1 + α(T − T_ref))` is stated as a **model plus a realization**,
not as a parallel property hierarchy. Prereg §5's constraint held without
strain: `ModelInputSpec` already *is* a typed property requirement,
`ModelOutputSpec` already *is* a property identity, and
`ProvenanceRecord.bindings` already records which realization computed the
value.

---

# 4. The N0 gate — built and executed, not analysed

MODEL0-R's finding D4 was that a preregistered reduction gate had been
*analysed* rather than *executed*. This gate was built and run first, with zero
new contracts, and the result is a count.

**Targets a records-only reader can detect** (`CONTROL` variables, plus `STATE`
variables no declared condition determines): **3**.

| Target | Dimension | Dimensionally admissible sources |
|---|---|---|
| `resistance-tcr-R1 :: temperature` | Θ | **5** |
| `thermal-lumped-R1 :: heat_input` | M·L²·T⁻³ | **4** |
| `thermal-lumped-R1 :: ambient_temperature` | Θ | **5** |

The four power-valued metrics in one electrical result are
`resistor_power:R1`, `source_power:V1`, `total_resistor_dissipation` and
`total_source_delivered_power`. Dimension cannot choose between them; only
parsing the name or reading the orchestration source could, and both are
forbidden by the brief.

**Targets the reader cannot detect at all: 1** — `R:R1`, a configured
parameter.

**And the reader cannot tell a supplied control from an environmental one:**
`ambient_temperature` is genuinely imposed by the environment, yet five
candidate suppliers are dimensionally admissible for it. With the dependency
set declared, `externally_imposed` returns exactly that one entry, and absence
of a record is the answer.

**Had any count been 1, H0(A) would have won and no contract would have been
added.** The gate was written to permit that outcome.

---

# 5. The capability layer: one direction, by physics

The milestone exercises `ModelRealizationDefinition.required_capabilities`,
which MODEL0-R left empty and classified as unexercised.

```text
LINEAR_TCR_REALIZATION.required_capabilities  = {thermal:body_temperature}
LUMPED_CLOSED_FORM_REALIZATION.provided_...   = {thermal:body_temperature}
LUMPED_CLOSED_FORM_REALIZATION.required_...   = {}          <- and correctly so
```

R(T) is **undefined** without a temperature, so the requirement is a true
scientific claim. A lumped energy balance is satisfied by **any** heat source —
combustion, friction, a heater — so a matching requirement on the thermal side
would be a false claim welding thermal physics to one domain.

**So the capability layer can express thermal → electrical and structurally
cannot express electrical → thermal.** And even where it *can*, it names no
quantity: it orders the sciences, it does not wire the numbers. That is why
capabilities do not close the gate, and it is an argument from physics rather
than from a missing feature.

A second result, free: `electrical/material.py` declares
`thermal:body_temperature` **by identifier and imports nothing thermal**
(asserted over the module's AST, not its text). An open, registry-free
identifier space lets one domain require another's science without acquiring a
code dependency on it.

---

# 6. Abstractions rejected or deferred

The test for each was prereg §5's: *what exact information becomes impossible,
duplicated, ambiguous or domain-specific without it?*

| # | Candidate | Verdict | Why the answer was weak |
|---|---|---|---|
| 1 | Material Identity | **DEFER** | `R_ref`, `α`, `T_ref` are three typed `ScientificParameter`s. Nothing is duplicated with one conductor |
| 2 | Material State | **DEFER** | The evaluation state is a name-keyed context; `validity_context(extra=…)` already builds one and `ValidityDomain.assess` already consumes it |
| 3 | Material Property Identity | **DEFER** | `ModelOutputSpec.metric` + `unit_exemplar` already identifies it |
| 4 | Property Requirement | **DEFER** | `ModelInputSpec` **is** one: name, source kind, dimension, value kind, role, required-ness |
| 5 | Property Binding | **DEFER** | Stated by the problem's `ModelReference` plus `ProvenanceRecord.bindings` |
| 6 | `ComponentDefinition` | **DEFER** | A typed component concept already exists domain-locally (`Resistor`, `ElectricalNode`). A universal one adds no checkable fact here |
| 7 | component usage / instance | **DEFER, and see §13** | Not forced at arity 1. **The deferral is `L0`:** the pack's constructor forecloses the 2:1 case |
| 8 | state-coordinate binding | **SPLIT** | Specification layer already exists — `ModelInputSpec(source_kind=VARIABLE, role=STATE, unit_exemplar="kelvin")`. Instance layer is the one new record |
| 9 | `CausalPort` | **DEFER** | A port type would record nothing the `ModelOutputSpec`/`ModelInputSpec` pair does not |
| 10 | `PhysicalConnector` | **DEFER, strongly** | No network, no conservation topology. Modelica's own specification records that potential+flow was *insufficient* for convective transport and needed a third variable kind — freezing connector semantics on a resistor and a lump would repeat that at our cost |
| 11 | hierarchical composition | **DEFER** | One level exists. There is no nesting to express |
| 12 | `SystemDefinition` / `SystemInstance` | **DEFER** | Duplicates `ScientificTwin` — see §7 |

**Reduced away during implementation and the adversarial pass** (prereg §10
TEST H requires at least one):

* **`QuantityEndpoint`** — a companion endpoint type was designed and dropped
  before it was written. Four flat fields carry it; two types where one
  suffices is what a reduction attack exists to kill.
* **`DependencyBindingReport`** — `check_against` returns
  `tuple[BindingIssue, …]` and reuses the existing issue type. `MISSING` and
  `WRONG_DIMENSION` already mean here what they mean when a model is checked
  against a problem.
* **`QuantityDependency.key`** — written, then deleted during the adversarial
  pass because nothing read it and no collection type exists that would dedup
  or order these records. An identity accessor with no caller is a guess about
  a future contract.

---

# 7. Duplication proof for `SystemInstance` — and the correction to it

`ScientificTwin` is already "a versioned declaration of one specific scientific
system instance", carrying `models` and `declarations` with roles
`PARAMETER / STATE / OPERATING_CONDITION / CONTROL`, globally-unique names,
`assumptions`, `evidence_refs` and `parent`. The whole electro-thermal instance
is declarable in one twin, and `build_twin` does exactly that. A
`SystemInstance` would restate it.

**Correction to preregistration §4, row 11.** The prereg called the twin *"the
only instance authority"*. That is not what the code does, and the falsifier
was right to say so (finding C-6). What happens is:

> the problems and the solver bindings are built from the **domain
> declarations**; the twin is derived from the same object afterwards and is
> **read by nothing**.

The twin here is a faithful derived copy, not an authority. Nothing links a
twin declaration name (`heat_capacity:R1`) to a problem quantity name
(`heat_capacity`); the correspondence is asserted in a test, which is precisely
the point — it is in no contract. `test_f1b` records this rather than hiding
it, and **§13 gives "twin as instance authority" zero evidence.**

The duplication argument stands regardless: nothing here needed a second
instance record, and creating one would have been the duplication the brief
forbids. What was *not* established is that the twin can carry the role.

---

# 8. Reduction attacks (prereg §6.4), all executed

| # | Reduction | Result |
|---|---|---|
| 1 | `ScientificProblem.metadata` | **Fails.** Untyped escape hatch, explicitly banned. `test_h1` asserts metadata is empty everywhere on the path and that the pack never writes `artifacts` |
| 2 | A field on `ScientificModelDefinition` | **Fails, and it is executed.** The *same* `LUMPED_CAPACITY_MODEL` record accepts a combustion supplier unchanged (`test_h2`). A supplier on the model would make one reusable claim into two, and would make a lumped balance electrical physics |
| 3 | `ScientificTwin` declarations | **Fails.** `TwinDatum` holds a typed **value**; `require_scientific_value` refuses a `QuantityDependency` (`test_h3`). Encoding a relation in a value is the string convention we refuse |
| 4 | `ProvenanceRecord` | **Fails, decisively.** Provenance exists only after a run. `test_h4` builds and checks every dependency with **nothing executed**; `ProvenanceRecord` requires a `run_id`. A representation that cannot exist before the run is not the representation |
| 5 | One merged electro-thermal model | **Fails.** Excluded by the brief's requirement of one electrical and one thermal model, and it is the monolith cross-domain composition exists to avoid. `test_h5` shows neither model's serialized form contains the other's vocabulary |

The falsifier independently re-derived four of these five and did not overturn
any.

---

# 9. The typed representation

```text
ScientificTwin  electrothermal-resistor-body / 0.1.0        (8 declarations)
│
├── PROBLEM  electrical_dc:electrothermal-resistor-body-R1
│     models  electrical.dc.kcl · electrical.dc.resistor_ohm
│             electrical.dc.ideal_voltage_source
│     R:R1 [ohm]  <- PARAMETER   (target of D3 — and invisible without it)
│
├── PROBLEM  resistance-tcr-R1
│     models  electrical.material.linear_tcr_resistance
│     temperature [kelvin]  <- VARIABLE, role=STATE, no initial condition
│     metric  resistance [ohm]
│
└── PROBLEM  thermal-lumped-R1
      models  thermal.lumped.first_order_capacity
      temperature [kelvin]         VARIABLE, role=STATE, initial condition 300 K
      heat_input [watt]            VARIABLE, role=CONTROL   <- target of D1
      ambient_temperature [kelvin] VARIABLE, role=CONTROL   <- no supplier
      metrics  final_temperature · steady_state_temperature · time_constant

D1  electrical … :: resistor_power:R1   [W] ──▶ thermal … :: heat_input
D2  thermal …    :: final_temperature   [K] ──▶ resistance-tcr-R1 :: temperature
D3  resistance…  :: resistance          [Ω] ──▶ electrical … :: R:R1
```

`D1` is electrical → thermal. `D2` + `D3` are thermal → electrical, routed
**through a material property**, which is the scientifically correct statement
of the feedback rather than a shortcut. Following the edges from the electrical
problem returns to it: the loop closes by traversal of records, with no name
parsing (`test_b`).

`ProvenanceRecord` carries **5 `ExecutionBinding`s over 5 models, 2
realizations and 3 solvers** — the repository's first arity > 1 multi-solver
record, which `model0r-differential-evidence.md` §9.1 named as untested. At
5 models and 3 solvers no positional zip of the participant sets is even
possible, which is the D2 defect made unrepresentable rather than merely
avoided.

---

# 10. Falsifier findings and resolutions

`architecture-falsifier`, primary attack *"prove this minimum foundation is
actually electro-thermal-specific architecture disguised as universal
architecture."* Verdict: **SURVIVES WITH REQUIRED CHANGES**. No `BLOCKER`.

The primary attack **failed against the record** and **partially succeeded
against what was shipped beside it.**

| # | Finding | Class | Resolution |
|---|---|---|---|
| **D-1** | An endpoint resolves across three namespaces with unstated precedence, and the shipped thermal domain already collided: `TEMPERATURE` and `TEMPERATURE_METRIC` were both `"temperature"`, so one endpoint denoted both T(t₀)=300 K and T(t_end)=344.27 K — same dimension, so no check could notice | **BREAKING-RISK** | **Fixed before commit.** The endpoint resolution rule is stated in the contract (*one name means one thing, across a problem's declarations and the metrics of results computed from it* — the rule `ScientificResult` already enforces internally, applied one level out), and `TEMPERATURE_METRIC` is now `final_temperature`. `test_b6` asserts no overlap for every problem/result pair. After commit this would have cost a published-metric rename or a `quantity_dependency/2` bump against an exact-match schema check |
| **C-2** | `unresolved_inputs` encoded a transient-IVP assumption in universal core: it tested only for an initial condition and never read `boundary_conditions`, so a steady-state problem pinned by Dirichlet conditions would be reported as needing an external supplier | **IMPLEMENTATION-CONCERN** — *the strongest evidence for the primary attack* | **Fixed.** Boundary conditions are consulted; `test_b7` covers the boundary-value case. Recorded because it contains **no domain word**: the lexical leakage scan structurally could not have caught it |
| **C-6** | The twin is derived and read by nothing; prereg §4 row 11 overstates it | IMPLEMENTATION-CONCERN | **Restated, not dressed up** — §7 and §13. `test_f1b` asserts the twin is not an input to anything |
| **C-7** | Both new solvers wrote provenance mixing problem-derived and binding-derived values with no consistency guard, which the sibling DC domain has | IMPLEMENTATION-CONCERN | **Fixed.** `verify_problem_matches_body` and `verify_problem_matches_conductor` refuse an inconsistent pairing in `prepare`, before anything is attributed |
| **C-8** | `ThermalBody` folded `ambient_temperature` and `duration` into instance identity, so the same body at a second ambient was refused as "a different body" — the same configuration/state conflation the milestone measures in the electrical domain | IMPLEMENTATION-CONCERN | **Fixed.** Identity is `physical_key` = (id, heat capacity, ambient conductance), mirroring `ConductionSlab.fingerprint`'s exclusion of the discretization |
| **C-10** | The lumped residual check claimed `ANALYTICALLY_VERIFIED` — the repository's only use of the taxonomy's highest level, from a one-point self-consistency check, while the milestone that had an *independent* closed form claimed only `DIMENSIONALLY_VALID` | IMPLEMENTATION-CONCERN | **Fixed.** `establishes=None`. The residual is *not* circular (a wrong τ, steady state or exponent sign each leave it non-zero) and it still runs; it simply earns no level |
| **C-9** | Capability policy is internally inconsistent: the thermal module mints a domain solver capability for a closed-form scalar update, the material module declines to on the ground that it would be inflation | IMPLEMENTATION-CONCERN | **Recorded, not forced.** Both are defensible and no contract decides. This is MODEL0-R finding D5 met from a second direction. The comment that called the sibling's choice an anti-pattern was rewritten |
| **C-12** | `key` unused; `check_against` accepted a bare value mapping with no identity check; `QUANTITY_DEPENDENCY_SCHEMA` unexported | IMPLEMENTATION-CONCERN | **Fixed.** `key` deleted; `check_against` now takes a `source_result` so *which run these numbers came from* is checkable (`test_b3b`); schema exported |
| **C-1/C-3** | `data_references` is never consulted, so a bulk-field endpoint is reported `MISSING` | ADDITIVE-FUTURE-EXTENSION | **Deliberately not taken**, with a reason recorded in the contract: consulting it would make a field endpoint check *clean* while nothing in the record can state how a field is transported between supports. An honest `MISSING` beats a clean check implying a transfer semantics no contract provides |
| **C-4/C-5** | Fan-in has no combination rule and no detector; the pack's `component_id == body_id` invariant forecloses the 2:1 experiment | ADDITIVE-FUTURE-EXTENSION / IMPLEMENTATION-CONCERN | **Measured rather than filled.** `test_b8` constructs the fan-in case at record level: two records, both checking clean, target reads as supplied, and no field states sum/override/split. A combination rule invented from one consumer would be a coupling engine decided on no evidence |
| **C-11** | `resistor_body.py` imports `resistance_name` from a non-exported submodule and re-derives `resistor_power:{cid}`, because the DC package publishes no metric-name helper and prereg §9 forbids editing it | IMPLEMENTATION-CONCERN | **Recorded** as fitness question 9 = "almost" (§11). The string-building is in a *system pack*, which is where cross-domain knowledge belongs — it is not a leak into core — but it is a duplicated source of truth for one name |

**Attacks that were run and did not land** are recorded because a falsifier
that finds only hits is not being read carefully: the primary attack itself
against the record; the reductions to `ProvenanceRecord` and `ScientificTwin`;
`formulation=ODE` with `core:algebraic` as a "dodge"; `unit_exemplar` as
decorative; a registry or global-singleton trap; a moved schema; a domain
branch in core.

---

# 11. Architecture fitness (master context §59)

| # | Question | Answer |
|---|---|---|
| 1 | Frozen core contract or schema changed? | **No.** `test_g3` pins six existing schema strings. The new record is additive at `quantity_dependency/1`. `ModelRealizationDefinition`'s field set is unchanged |
| 2 | Serialized records required migration? | **No.** Nothing existing moved, so nothing migrates |
| 3 | Domain-specific branch added to universal core? | **No** *conditional* and no domain *literal* (`test_d`). But see §13: `test_d` is a lexical scan and the C-2 leak contained no domain word — the honest claim is "no domain vocabulary or conditional leakage, tested lexically", not "no domain leakage" |
| 4 | Provider identity leaked upward? | **No.** `test_e` scans the serialized dependency and twin for solver, backend, `scipy`, `numpy`, `mna`, device and thread strings |
| 5 | Untyped metadata used as an escape hatch? | **No.** `test_h1` asserts metadata is empty on every new record and provenance on the path |
| 6 | Existing abstraction duplicated? | **No, and two were deliberately reused:** `BindingIssue`/`BindingIssueKind` instead of a parallel issue type, and `ValidityDomain`/`RangeCondition` for the property's declared range |
| 7 | New semantic abstraction required? | **Yes, one** — and the gate that forced it is a count, not an argument |
| 8 | Frozen invariant violated? | **No.** `test_i` re-asserts the T1/T2/T3 digest map and set-equality over `domains/thermal`; `test_i2` asserts the DC package's file set and that its temperature-independence assumption is unedited |
| 9 | Implementable from the published contract alone? | **Almost.** The models, realizations, twin, dependencies and provenance needed only published contracts. The system pack needed `resistance_name` from a non-exported submodule and had to re-derive one metric-name convention — finding C-11 |
| — | Could another domain use the contract without reading electrical/thermal source? | **Yes.** `test_d3` builds a mechanical → lubricant dependency importing nothing from either implemented domain |

**Core Edit Ratio**, secondary diagnostic only: **11 added lines, 0 removed**
in `engcore/scientific/__init__.py` (exports only) — the sole edit to any
pre-existing file in the repository — plus a 449-line new subpackage, against
1 434 new domain and system lines and 1 058 test lines. The number is
unremarkable and nothing above rests on it.

---

# 12. Tests

All figures below are from the **final tree**, after every falsifier
correction. An earlier FULL run at 1677 passed (42 tests) predates the
adversarial pass and is superseded.

| Suite | Command | Result |
|---|---|---|
| Targeted | `pytest tests/test_min_foundation_electrothermal.py -q` | **47 passed** |
| FAST | `pytest tests/ -m "not expensive" -q` | **1187 passed**, 495 deselected |
| FULL | `pytest tests/ -q` | **1682 passed**, 0 failed (568 s) |

Baseline before this milestone: **1635 FULL / 1140 FAST**.
`1635 + 47 = 1682` and `1140 + 47 = 1187`. **No pre-existing test was edited,
weakened, skipped, reordered or re-toleranced**, and none broke — including
across the new subpackage under `engcore/scientific`, which the existing
dependency-direction and domain-leakage guardrails scan.

*(A local `--basetemp` is required on this machine: 23 tests using `tmp_path`
error with `PermissionError` against the default Windows temp root.
Environment, not code — the same condition MODEL0-R recorded.)*

Coverage against prereg §10: TEST A (`test_a`, `test_a2`), B (`test_b`–`b8`),
C (`test_c`–`c4`), D (`test_d`–`d3`), E (`test_e`–`e3`), F (`test_f`, `f1b`,
`f2`), G (`test_g`–`g4`), H (`test_h1`–`h6`), I (`test_i`, `i2`), J
(`test_j`–`j3`), K (`test_k`, `k2`), L (`test_l`), plus five gate tests
(`test_gate_a`–`gate_e`).

`TEST J` is structural rather than textual — it walks the module's AST for
`While` nodes, counts `solve_circuit` calls, and scans identifiers — because a
substring scan over source would have been satisfied or defeated by prose.

## 12.1 Fail conditions (prereg §8)

All ten checked, none tripped. §8.1 (≤ 2 records) — one. §8.2 (no schema moved)
— `test_g3`. §8.3 (no domain branch) — `test_d`, with the caveat in §11. §8.4
(no solver identity in a foundation object) — `test_e`. §8.5 (no metadata) —
`test_h1`. §8.6 (no second instance authority) — none created; §7 records that
the twin is not exercised as one either. §8.7 (dependence not recoverable only
by string parsing) — `test_c`. §8.8 (frozen tree unchanged) — `test_i`. §8.9
(no pre-existing test edited) — counts above. §8.10 (no coupled solve) —
`test_j`.

---

# 13. Evidence level, per abstraction

**Ceiling honoured: `PROPOSED` / at most `L1 EXERCISED`. `L2` is not claimed
and is excluded by the preregistration.**

This section is deliberately the least flattering part of the document.

| Claim | Level | Why |
|---|---|---|
| `QuantityDependency` carries information with no home in existing contracts | **`L1 EXERCISED`** | Built, executed, survived five reductions and an adversarial pass. One consumer |
| The record contains no domain semantics | **`L1 EXERCISED`** | `test_d2`, `test_d3`; falsifier attacked it directly and failed |
| `ModelInputSpec` suffices as a property requirement / state-coordinate *specification* | **`L1 EXERCISED`** | Actually used to state R(T)'s dependence, and read back from the serialized record |
| `required_capabilities` carries real information | **`L1 EXERCISED`** | First exercise anywhere; MODEL0-R had it empty |
| `ProvenanceRecord.bindings` at arity > 1 over several solvers | **`L1 EXERCISED`** | 5 bindings, 3 solvers, 2 realizations |
| The electrical domain conflates configuration with operating state | **`L1 EXERCISED`** | Measured: `CircuitBindingError` |
| `check_against` is unusable for multi-instance domains | **`L1 EXERCISED`** | Measured: two `MISSING` issues |
| **Deferral of ten of the eleven candidates** | **`L0 REASONED`** | **Never confronted with a case that could have forced them.** `test_f2` asserts class names are absent from `__all__`; absence of a class is not evidence the concept was not needed |
| **Deferral of component instance/usage (#7)** | **`L0 REASONED`** | Confronted, but `ElectroThermalResistor` refuses `component_id != body_id`, so the 2:1 case cannot be constructed in the pack. `test_b8` measures the record-level fan-in gap instead |
| **`ScientificTwin` as instance authority** | **`L0`, zero evidence** | Nothing reads it (§7) |
| Multi-instance arity, fan-in, fan-out | **zero** | Only measured as a gap |
| `unit_exemplar` for dimension-changing or offset-unit transport | **zero** | All three dependencies are same-unit identity transports |
| Pre-execution checking of a **source** | **zero** | Only targets were checked pre-execution |
| Capability granularity (`thermal:body_temperature`) | **`L0 REASONED`** | Argued; no spatial realization exists to satisfy it |
| `formulation` | **`L1` at most, never `L2`** | Read for the first time, but one realization differentiates nothing. MODEL0-R §9.6 is unchanged |
| "No domain leakage" | **`L1`, narrowly** | Tested lexically. Record it as "no domain vocabulary or conditional leakage"; C-2 proves a structural leak can contain no domain word |

**What this milestone has is an executable proof, not an architectural proof.**
It shows the structure runs for one case. Every stress case that differs in
*kind* — arity, causality, dimensionality, flow direction — bends or breaks,
and none was executed.

---

# 14. Known unknowns carried forward

1. **Fan-in / fan-out have no combination rule.** Two sources on one target are
   representable and check clean; nothing states sum, override or split, and
   nothing reports the multiplicity. Measured in `test_b8`, deliberately unfilled.
2. **Endpoint arity-independence is inherited, not supplied.** `(problem_id,
   quantity_name)` disambiguates at arity > 1 *because each instance gets its
   own problem* — except in the electrical domain, which packs N resistors into
   one problem and separates them by embedding the component id in the name.
   The record genuinely never parses that name, but where a domain packs many
   instances into one problem without per-instance naming, the deferred
   component-instance concept returns immediately.
3. **Bidirectional flow breaks the directed form.** Source and target are fixed
   at declaration time; for convective transport the upstream side is a runtime
   property of the sign of the mass flow. Modelica's specification records that
   even its across/through pair was insufficient here and needed `stream`. A
   directed scalar record is strictly weaker. This is the honest limit on the
   fluid+thermal and HVAC direction.
4. **Acausal / potential-flow composition is untouched.** A mechanical+thermal
   pair (torque/speed) would encode a causal decomposition of an acausal
   connection, and the τ·ω power balance has no home.
5. **Field and tensor endpoints.** `data_references` is deliberately not
   consulted (§10, C-3); `Quantity` is scalar and `ScientificVariable.unit` is
   one string.
6. **No collection type owns dependency-set invariants.** Every other collection
   record in core enforces name uniqueness; a set of dependencies enforces
   nothing, and two near-duplicate records are both valid and undetected.
7. **The endpoint uniqueness rule is stated, not enforced.** Enforcing it would
   require this record to hold both sides, which it deliberately does not.
8. **Capability granularity and subsumption** — MODEL0-R D5, now met from a
   second direction (§10, C-9) and still open.
9. **The applicability envelope** (MODEL0-R evidence §4) — this milestone is the
   second structurally different consumer §4 asked for, and it **collects**
   evidence without deciding: α_TCR makes R undecidable before execution, and
   `assess_resistance_validity` requires the state passed explicitly because
   `validity_context` is built from parameters. A validity condition on a state
   coordinate is never automatic. **The shape is not decided here.**
10. **Two role vocabularies with no mapping.** `VariableRole
    {DESIGN, STATE, OBSERVABLE, CONTROL}` and `TwinDatumRole
    {PARAMETER, STATE, OPERATING_CONDITION, CONTROL}` overlap but differ, and
    nothing declares a correspondence. The ambient is `OPERATING_CONDITION` on
    the twin and `CONTROL` on the problem. No mapping was invented.
11. **Nothing heterogeneous, external, concurrent, distributed or at scale.**
    All code here was written by one author on one day.

---

# 15. Final decision and status

```text
Decision status:   PROPOSED
Evidence:          L1 EXERCISED  (one abstraction; most conclusions are L0 — §13)
Milestone:         COMPLETE
```

**Verdict: KEEP one record, DEFER eleven abstractions, and record honestly that
the deferrals are reasoned rather than exercised.**

The null hypothesis was given a real chance and lost by a measurement: three
targets with five, four and five dimensionally admissible sources, a fourth
target invisible to any records-only reader, and a capability layer that cannot
express one of the two directions for a reason rooted in physics. Had the counts
come back as one, no contract would have been added.

**Not frozen.** `PROPOSED` means the design is being built on and may be
revised. In particular the endpoint identity, the fan-in rule and the directed
form are all places later evidence should be expected to push.

---

# 16. Exact next milestone

# `ELECTRO-THERMAL VERTICAL PROOF`

Execute the actual coupled electro-thermal simulation: close the loop that this
milestone only represented, and decide — with a consumer in hand — what
coupling iteration, convergence and state-advance semantics actually require.

**Not started here.** It requires its own preregistration, written before any
source file is added or edited.

The first questions it inherits: whether a directed `QuantityDependency` set is
sufficient input for an iteration; where coupled convergence is recorded, given
that numerical convergence, coupling convergence and scientific validity are
three different things; and whether closing the loop forces the
component-instance concept that arity 1 allowed this milestone to defer.
