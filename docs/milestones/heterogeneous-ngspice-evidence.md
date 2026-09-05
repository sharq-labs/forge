# HETEROGENEOUS REAL PROVIDER PROOF — Evidence

**Milestone:** `HETERO-NGSPICE`
**Decision status:** `PROPOSED`
**Evidence:** `L1 EXERCISED` for the provider boundary. **The preregistered scoped `L2` for `Realization != Solver` is NOT claimed** — see §12.
**Falsifier verdict:** **FALSIFIED** on first pass — one `BLOCKER` and six `BREAKING-RISK`. **All seven closed before commit**; the same evidence then supports SURVIVES WITH REQUIRED CHANGES.
**Post-acceptance correction (§8.4):** one further provider-admission risk closed after acceptance. Architecture unchanged.
**Date of this record:** 2026-09-02
**Branch:** `heterogeneous-ngspice-proof`

> **Temporal boundary.** `docs/heterogeneous-ngspice-prereg.md` is the
> preregistration: committed at `549ad81`, before any source file was added or
> edited on this branch, and immutable. **This** document was written after
> execution. Deviations, corrections, adversarial findings and the final
> classification live here and nowhere else.
>
> This is **not** a freeze document.

---

# 1. Result against the preregistered hypotheses

**H1 is supported. H0 loses on all three of its declared limbs. But the
milestone was FALSIFIED on its first adversarial pass, and the finding that
falsified it is the most valuable thing in this record.**

| H0 limb | Outcome |
|---|---|
| Provider semantics forced into core | **Refuted.** Zero files added or edited under `src/engcore/scientific/` |
| The scientific model duplicated | **Refuted.** Both paths bind the identical three `ModelReference`s; no model was minted |
| More than an adapter boundary required | **Refuted.** Two new files, both beside `dc/`; `dc/` and `coupled.py` byte-unchanged |

The provider is **real**: `ngspice-42`, `/usr/bin/ngspice`, 8 300 800 bytes, KLU
direct linear solver, installed from Ubuntu `noble/universe` and reached as
`wsl.exe -e ngspice`. No mock, stub, fake provider or Crafty-written stand-in
appears anywhere on the evidence path.

## 1.1 The provider was absent, and execution stopped

Discovery found nothing: not on `PATH`, no `ngspice.exe`/`ngspice_con.exe`, no
`ngspice*.dll` or `libngspice*`, no `Spice*` directory, no registry entry, no
`PySpice`, `winget search ngspice` → *"No package found"*, and no ngspice inside
WSL either.

**Per the brief's non-negotiable rule, implementation stopped and the user was
asked.** ngspice was installed only with explicit authorization. This is
recorded because the alternative — proceeding with a mock — would have made
every number below worthless.

---

# 2. Provider facts, measured before the preregistration was finalised

The architecture review required a bounded spike first. Measuring the provider
is not implementing Crafty, so it ran before the prereg was sealed and its
results are preregistered **as facts**, not predictions.

| # | Question | Measured |
|---|---|---|
| — | Invocation modes | `ngspice -b <file>` and `ngspice -b` **on stdin**, both working. stdin selected: no path crosses the boundary |
| — | Output format | `.control/run/print/.endc` → deterministic `name = value`, names lower-cased |
| — | Precision | default 6–7 significant digits; **`set numdgt=12` → 13 digits**, so the text channel is not the accuracy bound |
| **R1** | Singular circuit | **exit 0**, *complete* requested set as **zeros**, `"Warning: singular matrix"` on **stderr only** |
| **R2** | gmin perturbation | none on well-posed networks (decade ladder 1 Ω…1 GΩ, exact) |
| **R3** | Sign conventions | **agree exactly**, including the negative source current. No negation anywhere |
| **R4** | Datum | ngspice mandates node `0`; the adapter **renames** Crafty's reference node, adding no element |
| **R7** | Cost | **3 ms** in-guest, **143 ms** per Windows→WSL crossing |

## 2.1 Exit codes are not a failure channel

| Case | exit |
|---|---|
| missing input file | 1 |
| malformed element | 1 |
| **singular circuit** | **0** |
| **undefined requested quantity** | **0** |

The two exit-0 cases are semantically **opposite** — one is a scientific
finding, one a provider failure. Any design keying on the exit code alone is
wrong, and that shaped the whole failure taxonomy (§7).

---

# 3. Reviewer verdict and integration mode

`architecture-decision-reviewer` compared six options and returned **ACCEPT WITH
CHANGES, selecting A″** — CLI/batch subprocess adapter satisfying the full
`ScientificSolver` protocol, plus a declared DC realization record shared by
both providers. All eleven required changes were carried into the prereg.

* **B (libngspice/FFI) rejected on measured unbuildability**, not preference:
  apt installed the binary only, `libngspice-dev` is a separate package, and the
  library would live inside WSL, so in-process calling from a Windows Python
  needs a bridge that does not exist. PySpice's own documentation independently
  records that shared mode is *less* safe than the subprocess mode it defaults
  to.
* **C (provider framework first) rejected** as premature abstraction with one
  member. Deferred with a named trigger: a second external provider whose
  process-execution needs actually overlap.

---

# 4. What was built

| Item | Location | Lines |
|---|---|---|
| Three MNA realization records | `src/engcore/domains/electrical/dc_realizations.py` (**new**) | ~230 |
| The provider adapter | `src/engcore/domains/electrical/ngspice.py` (**new**) | ~950 |
| Tests | `tests/test_heterogeneous_ngspice.py` (**new**) | 40 tests |
| Tier labels | `tests/conftest.py` (**edited**) | +18, assertions unchanged |

Both new modules sit **beside** `dc/`, not inside it, because
`test_min_foundation_electrothermal.py::test_i2` pins the `dc/` file set by name
— the same sibling pattern `material.py` and `thermal_lumped.py` established.

**`src/engcore/scientific/**` was not added to or edited.**
**`dc/**`, `coupled.py` and `resistor_body.py` are byte-unchanged.**

The one edit to a pre-existing file is `tests/conftest.py`, which gained an
`EXPENSIVE_MODULES` entry and a `STATIC_GUARDS` allowlist. That is the tiering
mechanism's documented purpose — *"Nothing in the tiering changes what a test
asserts"* — and it changes no assertion. It is recorded as a declared edit to
test infrastructure, not to a test.

---

# 5. Standalone equivalence — the first proof

Same Crafty `DCCircuit` and `ScientificProblem` into both paths.

```text
V1  n0 -> gnd   12 V        R1  n0 -> n1  10 Ω        R2  n1 -> gnd  20 Ω
```

Generated provider input (assigned names; no Crafty identifier need be
SPICE-legal, and the reference node becomes `0` with no element added):

```spice
crafty hetero-standalone
v0 n0 0 DC 12
r0 n0 n1 10
r1 n1 0 20
.op
.control
set numdgt=12
run
print v(n0) v(n1) i(v0) @r0[i] @r0[p] @r1[i] @r1[p]
.endc
.end
```

**Worst relative difference across all 13 metrics: `2.7756e-16`** — machine
epsilon, and **seven orders of magnitude inside the preregistered `1e-9`
bound**. Both report `ConvergenceState.CONVERGED`.

| Metric | native | ngspice |
|---|---|---|
| `node_voltage:n1` | +8.000000000000000e+00 V | identical |
| `resistor_power:R1` | +1.600000000000000e+00 W | identical |
| `resistor_power:R2` | +3.200000000000000e+00 W | identical |
| `source_current:V1` | −4.000000000000001e-01 A | −4.000000000000000e-01 A |

The single differing digit is the signature of two different factorisations —
dense LAPACK LU against sparse KLU — at machine epsilon.

## 5.1 Crafty's own validity authority, over the provider's numbers

`build_validation_report` takes the **native** `PreparedDCSystem` and a solution
vector, so the validity authority is coupled to the native solver's internal
representation and cannot simply be handed a provider's numbers. But `assemble`
is documented *"pure assembly, no solving"* — Crafty's equations can be built
without Crafty solving anything.

That turns reuse into something stronger than reuse: **`linear_system_residual`
substitutes ngspice's solution into the MNA system Crafty assembled itself.**

```text
linear_system_residual                 pass   1.1102230246251565e-16
kirchhoff_current_law                  pass   0.0
resistor_metric_consistency            pass   0.0
voltage_source_relation                pass   0.0
power_balance                          pass   0.0
realization_precondition_non_singular  pass   0.0     <- added by the falsifier
provider_element_metric_consistency    pass   0.0     <- added by the falsifier
```

---

# 6. Coupled substitution — the second proof

`ET-VERTICAL` split the coupling loop so that `run_fixed_point(problems,
executors, plan, …)` takes the dispatch table **as data**. Substituting the
provider is therefore **one dict entry**, and the substitution happens strictly
*below* coupling semantics.

| | native | ngspice | agreement |
|---|---|---|---|
| **CASE A** | `criterion_met`, 10 iterations, `T* = 338.577017565 K` | `criterion_met`, 10 iterations, `T* = 338.577017565 K` | **6.25e-13 K** (bound 1e-4) |
| **CASE E** stage 1 | `T1* = 328.898146247 K` | identical | **7.7e-12 K** |
| **CASE E** stage 2 | `T2* = 355.089513105 K` | identical | **9.2e-12 K** |
| **CASE E** solver | `electrical.dc.mna@0.1.0` | `engcore.electrical.dc.ngspice@42` | — |
| `resistor_power:R1` | 1.589063941 W | identical to 1e-6 rel | — |

**Iteration counts happened to match exactly (10 and 8).** That is recorded, not
required: Gauss–Seidel path length is not a scientific invariant and the prereg
declined to assert it.

**`coupled.py` is byte-unchanged**, contains no provider token, and its `__all__`
names no provider concept. There is no `native_coupling()` / `ngspice_coupling()`
pair. `test_d2` asserts that exactly one key of the dispatch table differs.

---

# 7. Failure taxonomy — three outcomes, no classifier

| Outcome | Mechanism | Executed |
|---|---|---|
| **Provider execution failure** | raises, inheriting `Exception` and **not** `ScientificCoreError` (the line `engcore.data` draws for `BulkDataError`); **no `ScientificResult` is synthesised** | missing executable → `NgspiceUnavailable`; **genuine ngspice exit 1** on a malformed netlist → `NgspiceExecutionFailure`; missing requested quantity → `NgspiceExecutionFailure` |
| **Numerical convergence** | from what was obtained; never from the exit code, never from warning text | `CONVERGED` on both paths |
| **Scientific validity** | Crafty's own `build_validation_report` only | eight checks, §5.1 |

**Mapping `"Warning: singular matrix"` onto `ConvergenceState.FAILED` was
forbidden and is not done.** Provider stdout/stderr is carried verbatim in
`RawSolverOutput.warnings` and never branched on. `ConvergenceState` gained no
member; no schema version moved.

---

# 8. The falsifier: FALSIFIED, and why that was the right answer

`architecture-falsifier`, primary challenge *"prove that Crafty is not actually
provider-neutral and that the ngspice proof works only because the electrical
vertical was hand-shaped around ngspice."*

**Verdict: FALSIFIED.** One `BLOCKER`, six `BREAKING-RISK`. All seven closed
before commit.

The *structure* survived every attack: core untouched, the coupling loop
genuinely provider-agnostic, the netlist never becoming IR, the invocation never
becoming science, no framework smuggled in. What failed was a specific,
load-bearing claim I had reasoned my way into — and the reasoning error is worth
more than the fix.

## 8.1 The BLOCKER — and the preregistration's incomplete enumeration

Prereg §9.3 **predicted** the singular-circuit asymmetry and declared it
deliberately unrepaired, on the argument that *"every available repair is
worse"*. It enumerated two: reading provider stderr (correctly forbidden) and a
Crafty-side connectivity pre-check (new domain logic, added asymmetrically).

**The enumeration was incomplete, and the falsifier found the missing third.**

The decisive observation I had not made: on the singular circuit, the zero
vector ngspice returns is an **exact solution of Crafty's own assembled
`A x = z`**. Every nodal row balances; the constitutive relation holds as
`0 = 0`; the source row is satisfied. Therefore **no check over `(A, x)` could
ever have detected it** — not KCL, not the residual, not the power balance. Only
a property of `A` **alone** can, and that property is rank.

And `validate` **already calls `assemble()`**. The matrix was in hand the whole
time. Testing its rank is neither provider text nor connectivity analysis nor
new domain logic — it is the realization's **own declared precondition**,
checked on an object the adapter constructs anyway.

So the honest disclosure I had written was understating the finding. The real
state was: *the platform had declared a precondition it had no mechanism to
check on either path, and one path silently fabricated a confident answer
outside it.* That collides with master context §15 and §26.1 directly.

**Closed.** `realization_precondition_non_singular` now reports the rank
deficiency:

```text
native   convergence = FAILED     validation = FAIL    metrics = 0
ngspice  convergence = CONVERGED  validation = FAIL    metrics = complete zeros
```

Note what the fix deliberately does **not** touch: `convergence`. The provider
genuinely did return a complete set, and reporting otherwise would misdescribe
the backend. What becomes `FAIL` is the *scientific* verdict — so the two paths
now **agree on the science and differ only on the numerics**, which is a sharper
separation than the milestone originally aimed for.

## 8.2 The six BREAKING-RISKs, all closed

| # | Finding | Resolution |
|---|---|---|
| **D1** | `resistor_current:` and `resistor_power:` are the **only** metrics taken verbatim from the provider that **no other check reads** — KCL, the constitutive check and the power balance all recompute from node voltages. And `resistor_power:<id>` is precisely the endpoint the electro-thermal composition transports into `heat_input`. A provider with a different element-power convention would heat the body wrongly, converge to a wrong fixed point, and pass all six checks | **Fixed.** `provider_element_metric_consistency` reconciles the provider's reported element current and power against Crafty's `v/R` and `v²/R` at the domain's own tolerances |
| **D2** | All three realizations declared one shared `electrical:dc_operating_point`, which none provides alone. `RealizationRegistry.providing()` is a **real existing consumer** and would have returned three realizations for it — a caller taking the first gets the KCL record, which alone computes nothing. Three false statements plus a true docstring is not honesty | **Fixed.** Three distinct capabilities, each true of the record declaring it: `nodal_charge_balance`, `resistor_constitutive_relation`, `ideal_source_constraint`. What remains lost is recorded, not encoded: no capability names the operating point, because no single record may claim it |
| **D3** | The shared realization asserted *"solved directly, not iterated"* — a claim about **procedure**, the category the frozen record excludes; never measured for ngspice; and contradicted by prereg §2.6's own description of gmin stepping. A PETSc Krylov realization would contradict it outright | **Fixed.** Replaced with a claim about mathematical form: *"the model imposes no outer nonlinear iteration"*. Separately, `RawSolverOutput.iterations` no longer fabricates `1` for a value the provider never reported |
| **D4** | `supports()` asked only capability-subset, so it returned `True` for a circuit with a current source that `build_netlist` then refuses, and `True` for a problem declaring **no** capabilities (the empty set is a subset of anything). The protocol's contract is *"never by attempting a solve"* | **Fixed.** Support additionally requires every named model to have a declared realization, and requires `electrical:dc_linear` explicitly. `test_g6` executes both former false positives |
| **D5** | `re.search(r"ngspice-(\S+)", stdout + stderr)` takes the **first** match anywhere and is greedy over punctuation: `ngspice-42,` → version `"42,"`, written into a serialized `SolverIdentity` that participates in `ExecutionBinding.key` | **Fixed.** Anchored to a line start, reads `--version` **stdout only**, character class stops at punctuation |
| **D6** | The scoped `L2` payoff record is **constructed by the test**: the native `solve_circuit` writes no bindings at all, so prereg §8.2's *"both providers bind all three"* was never met | **Not fixed — the claim was withdrawn.** See §12 |

## 8.3 Attacks that did not land

Recorded because a falsifier report that is all hits is not being read
carefully.

* **Name assignment.** Attacked and held: reference → `"0"`, others → `n{i}`,
  resistors → `r{i}`, sources → `v{i}` are four disjoint lexical spaces;
  collisions are impossible by construction; the map travels inside the prepared
  payload and nothing stores it across calls.
* **Deriving `resistor_voltage` and the totals in the adapter** — the half of the
  primary challenge I expected to be the hazard. A derived quantity cannot
  disagree with the provider; the risk was entirely in the *un-derived* half
  (D1).
* **Placement beside `dc/`** rather than a provider tree.
* **No provider framework**; the reduction attacks R1–R6 were real and
  `NgspiceInvocation` survived on a genuine argument (it refuses an empty argv
  and a non-positive timeout).
* **No global registry, no ordering dependence, no key collisions**; no
  `ConvergenceState` member; no schema bumped.
* **Provider identity in a scientific record** — `solver_id` and `backend` do
  appear in the serialized result, and that is correct: `SolverIdentity` is
  where execution provenance belongs. The prereg forbids provider *syntax and
  location*, which `test_i` scans for.

---

# 8.4 Post-acceptance correction — provider power is now admitted, not merely reported

**Raised after this milestone was accepted at `PROPOSED / L1 EXERCISED`. The
architecture was not reopened; one guard was moved and strengthened.**

## The residual risk

`resistor_power:<id>` is a provider-sourced quantity that the electro-thermal
composition transports directly into `heat_input`. §8.2 D1 added
`provider_element_metric_consistency` to the validation report to catch a
provider whose power convention differed. **That was detection, not admission
control**, and the distinction turned out to be the whole point.

## Measured, before fixing

A provider halving its reported element power — node voltages and element
currents left exactly right and entirely plausible — was run through the coupled
loop:

```text
honest provider     criterion_met   T* = 338.577017565 K
halved power        criterion_met   T* = 320.524069785 K
                    validation of the electrical result: FAIL
                    ==> 18.052948 K of wrong physics, admitted
```

The check fired. `validation_status` was `FAIL`. **And the coupling loop
transported the value anyway and converged confidently around it**, because the
loop reads `result.value(...)` and does not read validation reports — nor should
it have to. *A check whose only effect is a field nothing consults is not a
guard.*

## The correction

The reconciliation moved to `extract_metrics`, the boundary the solver contract
describes as where numeric output *"re-enters the unit-aware scientific world"*,
and a violation now **raises** `NgspiceExecutionFailure` — the existing category
for *the provider ran and did not deliver what was asked*. No `ScientificResult`
is synthesised, so there is nothing downstream to transport.

**Two relations, neither of which compares the power against itself.** ngspice
reports node potentials, element currents and element powers on three
*separate* output channels, and the resistance is Crafty's own declaration:

```text
1.  I  ≈  V_drop / R        Ohm's law. Right-hand side is a provider VOLTAGE
                            and a Crafty DECLARATION — no current, no power.
                            Catches a current sign or scale convention error.

2.  P  ≈  V_drop · I        Definition of power. Right-hand side is a provider
                            VOLTAGE and a provider CURRENT — no power.
                            Catches a power convention error, including
                            absorbed-versus-delivered.

3.  P  ≥  0                 A passive element with R > 0 absorbs power. Checked
                            separately because flipping current AND power
                            together satisfies relation 2 while inverting the
                            physics.
```

**Sign convention, decided explicitly.** `build_netlist` emits
`R<i> <node_a> <node_b> <ohms>` in the Crafty circuit's own terminal order, so
the provider's `@r[i]` is positive when current flows `node_a → node_b` — the
same convention as Crafty's `resistor_current`, measured to agree exactly in
spike R3. `resistor_power` is **absorbed** power.

Tolerance `1e-9` absolute and relative — the DC domain's own figure, loose
against the observed machine-epsilon agreement by orders of magnitude, and tight
against any convention error by orders more.

`provider_element_metric_consistency` remains in the report, now as the
*reporting* half: a reader of a stored result can see **that** the power was
reconciled and against what, without needing to know that a violation would have
prevented the record existing.

## Negative cases, executed

| Corruption | Other quantities | Result |
|---|---|---|
| power × 0.5 | voltages and currents correct | **refused** — `V_drop * I` relation |
| power × −1 (delivered, not absorbed) | voltages and currents correct | **refused** |
| current × −1, power left self-consistent | `P = V·I` still holds | **refused** — only the Ohm's-law relation against Crafty's *declared* R catches this |
| the halved-power provider, **inside the coupled loop** | — | **raises; no `CoupledRun` is produced at all** |

## What is unchanged

Native/ngspice equivalence (`2.776e-16` standalone, `6e-13 K` coupled), the
failure taxonomy, `coupled.py` byte-unchanged, zero provider logic in scientific
core, no new framework, no new record type, no schema movement. The singular-
circuit precondition check (§8.1) and this admission gate stay separate concerns:
the singular case returns zeros, which satisfy all three relations above, and is
caught by rank instead.


---

# 9. Deviations from the preregistration

## D-a — §8.2 fixed field values the frozen contract refuses

The prereg fixed the realization records' fields in advance, including
`provided_capabilities frozenset()`. `ModelRealizationDefinition` **refuses**
an empty set: *"a realization that provides nothing can never satisfy
anything"*. **The preregistered record was unbuildable against the frozen
contract.** The substitute was chosen after the fact, and the falsifier then
rejected the first substitute (D2) in favour of three truthful capabilities.

## D-b — §9.3's "every available repair is worse" was wrong

Documented in full in §8.1. The enumeration missed a repair smaller than both it
considered. **This is the single most useful correction in the milestone**, and
it is a reasoning error in the preregistration, not an implementation slip.

## D-c — §8.2's "both providers bind all three" was unachievable

It conflicts with fail condition 10, which freezes `dc/`. The native
`solve_circuit` predates `MODEL0-R` and writes no bindings; making it write them
would edit a frozen package. The freeze correctly won, and the consequence is
§12.

## D-d — `bind_circuit` is more permissive than the native solver's

The native refuses rebinding a *different* circuit under one problem id; the
adapter overwrites, so one solver instance can be reused across coupling
iterations without paying a 143 ms version probe each sweep.
`prepare()`'s `verify_problem_matches_circuit` fingerprint check remains the
real guard. **Recorded as a genuine weakening**: under concurrent use of a
shared solver the loser would silently solve the winner's circuit where the
native would raise. No concurrent consumer exists and §14 declares zero
evidence there, so the mechanism is recorded rather than defended.

---

# 10. Architecture fitness

| # | Question | Answer |
|---|---|---|
| 1 | Frozen universal-core contract changed? | **No** |
| 2 | Scientific schema changed? | **No.** `provenance_record/2`, `raw_solver_output/2`, `scientific_result/2` unchanged |
| 3 | Migration required? | **No** |
| 4 | Provider branch added to scientific core? | **No.** Zero files added or edited under `engcore/scientific` |
| 5 | Provider name leaked into scientific semantics? | **No** — except as `SolverIdentity.solver_id`/`backend`, which is where execution provenance belongs. Core's own docstrings already named ngspice **three times** before this milestone, as an anticipated adapter target |
| 6 | Provider syntax leaked upward? | **No.** No `.control`, `.endc`, `numdgt`, `wsl.exe` or netlist text in any serialized record; the netlist lives in `PreparedSolve.payload`, which the contract names as its home |
| 7 | Metadata escape hatch used? | **No** |
| 8 | Coupling code changed because the provider changed? | **No.** `coupled.py` byte-unchanged |
| 9 | Scientific model duplicated? | **No.** Identical `ModelReference`s on both paths |
| 10 | Realization duplicated because the provider changed? | **No.** Both execute the same three records |
| 11 | Provenance distinguishes execution? | **Yes.** `electrical.dc.mna@0.1.0` vs `engcore.electrical.dc.ngspice@42`, version read at run time |
| 12 | Could another provider be attempted without reading core internals? | **Partly — and the honest answer is no.** `_solution_vector` depends on `PreparedDCSystem`'s unknown ordering, and the adapter imports `NODE_VOLTAGE_METRIC`/`SOURCE_CURRENT_METRIC` from `.dc.solver`, which `dc/__init__.py` does not export. A second adapter would re-derive both |

**Core Edit Ratio**, secondary diagnostic: **0 lines** in universal core; ~1 060
new domain lines; +18 lines of tier labels in test infrastructure.

---

# 11. Realization classification

**Same computational realization, two concrete solvers.** Decided on the frozen
contract's own criterion, not on provider names:

* both pose a linear algebraic system (`ModelFormulation.ALGEBRAIC`);
* both assemble by modified nodal analysis;
* both require exactly `{electrical:dc_linear, core:linear_system}` — and the
  capability vocabulary contains **no sparse/dense distinction**;
* `ModelRealizationDefinition`'s docstring makes a concrete solver an execution
  property by construction.

**R2 supports this where it matters:** on well-posed networks ngspice's gmin does
not perturb the answer. The regularisation difference exposed by R1 engages only
*outside* the realization's precondition, which the record now declares **and
checks**.

## 11.1 The grain problem, measured

`ModelRealizationDefinition.model` is a **single** `ModelReference`; one DC
analysis invokes **three** models that MNA realizes **jointly** — one assembly,
one factorisation. The record cannot say "these three, together."

Three records are declared, each true on its own terms. What is lost is recorded
rather than encoded: **no capability names the operating point**, because no
single record may claim it. The underlying limitation — that
`ModelRealizationDefinition` refuses a realization providing only *jointly* — is
a property of a `DESIGN-FROZEN` contract and is carried forward as a candidate
reopen trigger, not repaired here.

---

# 12. Evidence level — and the withdrawn L2

```text
Decision status:   PROPOSED
Evidence:          L1 EXERCISED   (the provider boundary)
Scoped L2:         NOT CLAIMED
```

The preregistration permitted a scoped `L2 DIFFERENTIATED` for
`Realization != Solver`. **It is not claimed**, and the reason is D6.

**What is genuinely earned:** two materially different concrete solvers — one of
them code Crafty did not write, using a different factorisation — executed the
same three realization records and agreed to `2.776e-16`, and to `6e-13 K` at a
coupled fixed point. That is real, it is more than `MODEL0-R` had, and it is the
first time any external code has participated in a Crafty realization.

**What is not earned:** any record *produced by the system* stating it. The
native `solve_circuit` writes no bindings, so the two-solvers-one-realization
`ProvenanceRecord` exists only inside `test_m`, constructed by the proof from
what demonstrably ran. `MODEL0-R`'s boundary is **not** upgraded, and
`QuantityDependency` and the `ET-VERTICAL` coupling claims are untouched.

Per-claim, stated as **zero evidence**: session-stateful providers, asynchrony,
concurrency, remote execution, field-valued output, timeouts and hangs, provider
version drift, portability across builds/distributions/platforms, and any second
provider.

---

# 13. Known unknowns carried forward

1. **The precondition is now checked on the external path only.** The native
   path enforces non-singularity as a *side effect* of `scipy.linalg.solve`
   raising, not as a declared check. Making that symmetric would edit `dc/`.
2. **`_solution_vector` couples the adapter to the native MNA unknown ordering**,
   and two non-exported constants are imported from `.dc.solver`. Fitness
   question 9 answers **no**.
3. **A non-finite provider value would surface as a `ScientificCoreError`.**
   `_PRINT_LINE` matches `nan`/`inf`, the missing-quantity guard passes, and
   `Quantity` then raises — a provider failure wearing a scientific error's
   type. Essentially unreachable with resistors and ideal sources only; reachable
   the moment a second element type is admitted.
4. **Concurrent use of a shared solver is unguarded** — §9 D-d.
5. **The external `ProvenanceRecord` records `tolerances={}`** while the native
   records six, and the `DCValidationSettings()` that produced its verdict are
   constructed inline and never persisted.
6. **The external record omits `circuit_canonical`**, so it answers *"was it this
   circuit?"* but not *"what exactly was solved?"* — a distinction the native
   docstring draws explicitly.
7. **`dc_realizations.py`'s module path *is* its `ImplementationReference.
   implementation_id`**, so prereg §11's "moving it later changes no serialized
   record" is false for that module.
8. **`test_n`'s bounds pin one build's stderr banner**, not an invariant.
9. **27 of the 40 tests hard-error without WSL + ngspice** rather than skipping,
   so the regression baseline is machine-specific. That is deliberate — a skip
   would let the evidence evaporate silently — but it must be stated.
10. **ngspice's exit-code behaviour has no upstream contract** I could locate.
    §2.1 is measured on one build.
11. **The `2.776e-16` headline is a property of a divider whose values
    round-trip exactly through 13 significant digits.** The text channel
    structurally caps agreement near `1e-13`.

---

# 14. Tests

| Suite | Command | Result |
|---|---|---|
| Targeted | `pytest tests/test_heterogeneous_ngspice.py -q` | **40 passed** |
| FAST | `pytest tests/ -m "not expensive" -q` | **1262 passed**, 516 deselected |
| FULL | `pytest tests/ -q` | **1784 passed** |

Baseline before this milestone: **1744 FULL / 1249 FAST** (495 deselected).
`1744 + 40 = 1784`. The 13 static tests (source scans, record scans, reduction
attacks) stay in FAST; the 27 that launch the provider are tiered `expensive`
by TESTING.md's own behavioural criterion. **No pre-existing test was edited,
weakened, skipped or re-toleranced.**

Coverage against prereg §12: A (`test_a`, `a2`), B (`test_b`, `b2`),
C (`test_c`, `c2`), D (`test_d`, `d2`), E (`test_e`–`e4`), F (`test_f`),
G (`test_g`–`g6`), H (`test_h`), I (`test_i`), J (`test_j`, `j2`),
L (`test_l`), M (`test_m`–`m3`), N (`test_n`); reductions `test_r1`–`r6`.
K is the FULL suite above. The post-acceptance admission gate adds
`test_p`–`p4` (§8.4).

---

# 15. Final decision and status

```text
Decision status:   PROPOSED
Evidence:          L1 EXERCISED   (provider boundary); scoped L2 NOT claimed
Milestone:         COMPLETE
```

**Verdict: KEEP.** A real external provider substituted for a Crafty execution
path, standalone and inside the coupled loop, with universal core untouched, the
coupling algorithm unmodified, provenance distinguishing the executions, and a
failure taxonomy that keeps provider failure, numerical non-convergence,
coupling non-convergence and scientific invalidity apart.

**The milestone was falsified once, and is better for it.** The preregistration
reasoned that a known defect could not be repaired without a worse cost; the
adversarial pass showed the enumeration was incomplete and the repair was
already sitting in a matrix the adapter assembled anyway. The disclosure that
had been written as an honest limitation was in fact understating a fabrication
hazard.

**Not frozen.** `PROPOSED` means this adapter is being built on and may be
revised. The generalisation trigger is preregistered and unmet: **a second
external provider whose process-execution needs actually overlap.**

---

# 16. Exact next milestone

Not started here. Per master context §61 the roadmap continues to **`API / MCP
v0`**, with `CROSS-ARCHITECTURE HOSTILE PROOF` after it. Nothing in this
milestone begins either, and FEniCSx, PETSc, OpenFOAM, a generic provider
framework and HVAC all remain out of scope.

The questions this milestone hands forward:

1. **Session-stateful providers.** Process-per-solve destroys session state;
   `ET-VERTICAL` §15.6 already named this the sharpest edge and it is **not**
   answered here — it is sidestepped.
2. **A second provider is what would make the shared shape evidence** rather
   than an argument, and would decide whether `_solution_vector`'s coupling to
   native internals is a defect or a domain convention.
3. **Whether `ModelRealizationDefinition` should be able to state a joint
   realization** — a `DESIGN-FROZEN` contract with a consumer it cannot express.
