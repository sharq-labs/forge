# HETEROGENEOUS REAL PROVIDER PROOF — Preregistration

**Milestone:** `HETERO-NGSPICE` — the first proof using a genuinely external
scientific provider that Crafty did not write.
**Kind:** provider-substitution milestone. It is not `COUPLE0`, not a provider
framework, not API/MCP.
**Decision status target:** at most `PROPOSED`.
**Evidence target:** at most `L1 EXERCISED` for the provider boundary. `L3` is
excluded outright. A **scoped** `L2` claim is permitted for exactly one existing
contract — see §14.
**Date:** 2026-09-02
**Branch:** `heterogeneous-ngspice-proof`
**Preregistered before implementation.** Everything below was written before any
source file was added or edited on this branch. The working tree was verified
clean at `07a49df`.

> **This file is immutable.** It records what was committed to *before* results
> were observed. Executed results, deviations, corrections, adversarial findings
> and the final classification go in
> `docs/heterogeneous-ngspice-evidence.md` and nowhere else.
>
> This is **not** a freeze document.

**Canonical milestones verified present before this document was written:**

| Milestone | Decision | Evidence | Record |
|---|---|---|---|
| `DATA-BOUNDARY0` | `PROPOSED` | `L1 EXERCISED` | master context §56 |
| `MODEL0-R` differential | `DESIGN-FROZEN` | `L2 DIFFERENTIATED` (scoped) | master context §58 |
| `MIN-FOUNDATION-ET` | `PROPOSED` | `L1 EXERCISED` / `L0` deferrals | master context §64 |
| `ET-VERTICAL` | `PROPOSED` | `L1 EXERCISED`; several claims `L0` | master context §65 |

---

# 1. The single question

> Can **one existing Crafty scientific execution path** be replaced by a **real
> external provider** while preserving scientific semantics, realization
> meaning, coupling behaviour, provenance and validation — **without changing
> universal Crafty Core**?

---

# 2. Measured provider facts

**Recorded before any hypothesis was tested.** Measuring the provider is not
implementing Crafty, so this spike ran before this document was finalised, as
the architecture review required. Every number below is an observation, not a
prediction.

## 2.1 Availability — and the honest history

ngspice was **absent** from this machine. Discovery found: nothing on `PATH`;
no `ngspice.exe` / `ngspice_con.exe`; no `ngspice*.dll` or `libngspice*`; no
`Spice*` directory on `C:` or `D:`; no registry uninstall entry matching
`spice`; no `PySpice` or `ahkab`; `winget search ngspice` → *"No package found
matching input criteria"*; and no ngspice inside the WSL Ubuntu distro either.

**Execution stopped at that point and the user was asked.** With explicit
authorization, ngspice was installed into WSL Ubuntu (noble) via
`apt-get install ngspice`. **No mock, no stub, no second Crafty-written solver
and no wrapper around the native path is used anywhere in this milestone.**

## 2.2 Provider identity

```text
binary   /usr/bin/ngspice        8 300 800 bytes, dated 2024-03-31
banner   ngspice-42 : Circuit level simulation program
         Compiled with KLU Direct Linear Solver
         The U. C. Berkeley CAD Group
package  ngspice 42+ds-3build1   (Ubuntu noble/universe)
host     WSL Ubuntu noble on Windows 11
reach    Windows -> wsl.exe -> /usr/bin/ngspice     (no native Windows build exists here)
```

## 2.3 Invocation modes confirmed working

* `ngspice -b <file>` — batch from a file.
* `ngspice -b` with the netlist on **stdin** — confirmed working. **This is the
  mode selected**, because no file path crosses the Windows/WSL boundary at all.
* A `.control / run / print … / .endc` block emits deterministic
  `name = value` lines. Names return **lower-cased**.
* `@R1[i]` and `@R1[p]` yield element current and power directly — exactly the
  quantities the electro-thermal loop consumes.
* `set numdgt=12` raises the printed precision to **13 significant digits**
  (`5.500000000000e+00`), so the text channel is **not** the accuracy bound.

## 2.4 Exit-code behaviour — the crux

| Case | exit code | how it is detectable |
|---|---|---|
| missing input file | **1** | exit code |
| malformed element (`RQ n0 n1 NOT_A_NUMBER`) | **1** | exit code + `"Error on line 3"` |
| **singular circuit** (floating sub-network) | **0** | *only* `"Warning: singular matrix"` — **on stderr** |
| **requested quantity undefined** | **0** | the quantity is simply **absent** from stdout |

**ngspice's exit code is not a sufficient failure channel, and its two exit-0
cases are semantically opposite.** One is a scientific finding; the other is a
provider failure.

## 2.5 R1 — the singular circuit, measured on both paths

The architecture review flagged this as the deciding unknown. It resolved
**worse than the review anticipated**, and the result is stated here so that it
is a preregistered fact rather than a later discovery.

```text
circuit:  V1 n0->ref 12 V ;  R1 n1->n2 10 Ω   (R1 floats: no path to the datum)

ngspice   exit 0
          v(n0)=1.2e+01  v(n1)=0.0  v(n2)=0.0  i(v1)=0.0  @r1[i]=0.0  @r1[p]=0.0
          i.e. the COMPLETE requested quantity set, as plausible zeros
          "Warning: singular matrix: check node n1"   -> stderr only

native    convergence = FAILED
          validation  = FAIL  ("linear system could not be solved uniquely;
                               the circuit is singular")
          metrics     = 0
```

So the review's proposed rule — *"report CONVERGED only when the complete
requested quantity set was obtained"* — **is insufficient**: the set *is*
complete. See §9 for what is preregistered as a consequence.

## 2.6 R2 — gmin does not perturb a well-posed network

A decade-spread ladder (1 Ω, 1 kΩ, 1 MΩ, 1 GΩ) returned identical values with
default options and with `.options gmin=1e-15`, and both matched the analytic
solution (`i = 9.99e-9 A`, `v(n3) = 9.99 V`). **ngspice's regularisation engages
only when the assembled system is singular.**

## 2.7 R3 — sign conventions agree, measured on one identical circuit

`V1 zz_top→ref 6 V`, `R1 zz_top→aa_mid 100 Ω`, `R2 aa_mid→ref 200 Ω`:

| Quantity | native Crafty | ngspice |
|---|---|---|
| `node_voltage:zz_top` | +6.000000000e+00 V | `v(zz_top)` +6.000000000e+00 |
| `node_voltage:aa_mid` | +4.000000000e+00 V | `v(aa_mid)` +4.000000000e+00 |
| `resistor_current:R1` | +2.000000000e-02 A | `@r1[i]` +2.000000000e-02 |
| `resistor_current:R2` | +2.000000000e-02 A | `@r2[i]` +2.000000000e-02 |
| `resistor_power:R1` | +4.000000000e-02 W | `@r1[p]` +4.000000000e-02 |
| `resistor_power:R2` | +8.000000000e-02 W | `@r2[p]` +8.000000000e-02 |
| `source_current:V1` | **−2.000000000e-02 A** | `i(v1)` **−2.000000000e-02** |

**No negation is required anywhere**, including the voltage-source branch
current. This was measured rather than assumed, because a silent sign flip
would propagate into `source_power` and still let the coupled loop converge — to
the wrong physics.

## 2.8 R4 — datum mapping

ngspice mandates node `0` as the datum. Crafty's `reference_node` is an
arbitrary node id. **The adapter renames Crafty's declared reference node to
`0`** — it does **not** add a shorting source, which would put an element into
the provider input that the Crafty circuit does not contain. Verified on a
circuit whose reference node is not lexically first.

## 2.9 R7 — cost of the boundary

| | per invocation |
|---|---|
| `ngspice -b` inside WSL | **3 ms** |
| `wsl.exe -e ngspice -b` from Windows | **143 ms** |

~140 ms is WSL process-start overhead. A 10-iteration coupled run costs ≈ 1.4 s;
the 50-iteration case ≈ 7 s. Acceptable, and recorded because `ET-VERTICAL`
§15.6 already noted that a fresh solver per call is affordable only for cheap
participants.

---

# 3. Hypotheses

## H1 — primary

> Crafty can execute the **same** scientific electrical problem through (A) its
> existing native path and (B) real external ngspice, preserving the scientific
> problem/model meaning and producing scientifically equivalent results within
> the tolerance preregistered in §10, **without changing universal scientific
> semantics**.

Quantified in advance: **zero files added or edited under
`src/engcore/scientific/`**, and **zero new `ScientificModelDefinition`
records**. Either is a falsification of H1 as stated.

## H0 — null, and it is allowed to win

> Supporting an external provider requires one or more of: provider-specific
> semantics in scientific core; duplication of the scientific model; mutation of
> coupling semantics; provider identity leaking into scientific meaning; untyped
> metadata conventions; inability to preserve provenance; inability to
> distinguish provider failure from scientific failure; or architectural change
> larger than an adapter boundary.

**H0 is refutable on three independent limbs, each of which can come out the
other way:** the core-edit count; whether the ngspice path binds the *same*
`ModelReference`s the native path binds; and whether the failure taxonomy,
version channel and metric mapping can be expressed without a new universal
record.

**A partial H0 win is explicitly anticipated on the realization limb — see §8.2.**

---

# 4. Reviewer verdict, and the option selected

`architecture-decision-reviewer` was run **before this document**, comparing six
options (A CLI+`ScientificSolver`, A′ executor-callable-only, A″ A plus a
declared DC realization, B libngspice FFI, C provider framework first, D defer).

**Verdict: ACCEPT WITH CHANGES, selecting A″** — CLI/batch subprocess adapter
satisfying the full `ScientificSolver` protocol, plus a declared DC realization
record shared by both providers. **A is the preregistered fallback** if §8.2
cannot be satisfied honestly.

## 4.1 Why B is rejected

**Not on preference — on measured unbuildability.** `apt` installed the
`ngspice` binary only; `libngspice-dev` is a separate package; and the library
would live inside WSL, so calling it in-process from a Windows Python requires a
WSL-side Python bridge that does not exist. Choosing B means installing more
packages, building a bridge, then writing the FFI adapter — a different and
larger milestone. Independently, PySpice's own documentation records that shared
mode is *less* safe than the subprocess mode it defaults to, and that ngspice's
global-variable design forces one library copy per worker.

## 4.2 Why C is rejected

Premature abstraction on every test: one provider, no second consumer, and a
registry added later is purely additive because **nothing serialized names a
provider**. `ET-VERTICAL` recorded the sibling refusal as its own fail condition
12. `C` is deferred with a named trigger: **a second external provider whose
process-execution needs actually overlap.**

## 4.3 The eleven required changes, carried in

1. Preregistration committed before any source edit. *(This document.)*
2. Provider spike run first, results recorded as measured facts. *(§2.)*
3. The failure taxonomy of §9 — three outcomes, no classifier, no new core type.
4. The singular-circuit asymmetry is **predicted, not engineered away**. *(§9.3.)*
5. Realization identity decided scientifically, with the grain problem handled
   explicitly. *(§8.)*
6. Adapter placement beside `dc/`, not inside it, not in a provider tree. *(§11.)*
7. `SolverIdentity` only; no provenance extension; version read at run time.
8. WSL boundary legitimate for `L1`, with named refusals. *(§15.)*
9. `H0` reachable on three limbs. *(§3.)*
10. ngspice options that change what was solved recorded in `SolverSettings`.
11. Provider text carried in `RawSolverOutput.warnings`; **never branched on**.

---

# 5. Integration mode

```text
Crafty DCCircuit + ScientificProblem        (unchanged, existing records)
        ↓  adapter: emit provider syntax
SPICE netlist text                          (provider syntax — NOT Crafty IR)
        ↓  wsl.exe -e ngspice -b   (netlist on STDIN, no file path crosses)
ngspice-42 process
        ↓  parse "name = value"
Quantity-valued metrics                     (existing units contract)
        ↓  Crafty's own validate()
ScientificResult                            (existing record, unchanged)
```

The netlist is **provider syntax and never becomes Crafty's scientific IR**. No
equation IR and no circuit IR is created for this milestone.

---

# 6. The common scientific problem

Taken from the repository's actual domain semantics — **not** a parallel
test-only format. The same Crafty `DCCircuit` / `ScientificProblem` feeds both
paths.

**Standalone case (§11 of the brief):** the electrical half of `ET-VERTICAL`'s
CASE E — one ideal source and **two** series resistive elements, which is
non-trivial enough to expose a datum error, a node-ordering error, a sign flip
or a units error:

```text
V1  n0 -> gnd   12 V
R1  n0 -> n1    10 Ω
R2  n1 -> gnd   20 Ω        reference node: gnd
```

**Coupled cases (§12 of the brief):** `ET-VERTICAL` CASE A (one self-heating
resistor) and CASE E (two conductors in series, two thermal bodies), run twice
each — once native, once with the ngspice provider substituted.

---

# 7. Where the substitution happens

`ET-VERTICAL` already split the coupling loop:

```python
run_fixed_point(problems, executors, plan, *, run_id, software_version, assumptions)
run_fixed_point_coupling(system, plan, *, run_id)   # builds executors, delegates
```

`run_fixed_point` is public, domain-free, and takes the dispatch table **as
data**. Substituting the provider therefore means **handing it a table whose
electrical entry calls ngspice** — with **zero edits to the coupling loop**.

**Preregistered prediction:** TEST D is satisfiable by asserting the native and
external runs call *the same function object*, and that
`src/engcore/systems/electrothermal/coupled.py` is **byte-unchanged**.

**Fail condition:** any appearance of `native_coupling()` / `ngspice_coupling()`,
or any edit to the coupling loop, falsifies the milestone's central claim.

---

# 8. Realization identity — decided scientifically, in advance

## 8.1 The finding

Native Crafty assembles a **dense** MNA matrix (`np.zeros((size,size))`) and
solves it with `scipy.linalg.solve(assume_a="gen")` — dense LAPACK LU with
partial pivoting, `BACKEND = "scipy.linalg.solve"`. ngspice-42 assembles MNA and
solves with **KLU / SPARSE 1.3** direct sparse factorisation.

**These are the same computational realization executed by two concrete
solvers.** The decision rests on the frozen contract's own criterion, not on
provider names:

* Both pose the same mathematical form — a linear algebraic system,
  `ModelFormulation.ALGEBRAIC`.
* Both assemble by modified nodal analysis.
* Both require exactly `{electrical:dc_linear, core:linear_system}`, and **the
  capability vocabulary contains no sparse/dense distinction** — `CoreCapabilities`
  offers `LINEAR_SYSTEM` and nothing finer. `required_solver_capabilities` is the
  one field `MODEL0-R`'s differential proof established as differentiating and
  non-reducible, and it is **identical** here.
* `ModelRealizationDefinition`'s own docstring makes dense-vs-sparse an execution
  property by construction: *"a realization that named [a concrete solver] would
  have made changing a linear solver into a change of scientific identity."*

**R2 supports this at the level that matters:** on well-posed networks ngspice's
gmin does not perturb the answer. The regularisation difference exposed by R1
engages **only outside** the realization's precondition, so it is a property of
each concrete solver's behaviour on an inadmissible system, not of the
realization. The realization record will state that precondition explicitly.

## 8.2 The grain problem — the anticipated partial H0 win

Two structural facts, both verified, neither anticipated by the milestone brief:

* **There is no DC realization record to reuse.** `grep` over
  `src/engcore/domains/electrical/dc/` returns **zero** references to
  `realization`. All three DC models currently bind with `realization=None`,
  which `ET-VERTICAL` §11 recorded as *"honest"*. One must therefore be
  **authored** — so "the realization stays the same while the solver changes"
  cannot be demonstrated by reuse and must be demonstrated by prediction.
* **`ModelRealizationDefinition.model` is a single `ModelReference`, but one DC
  analysis invokes three models** (`electrical.dc.kcl`,
  `electrical.dc.resistor_ohm`, `electrical.dc.ideal_voltage_source`). MNA
  realizes them **jointly**, and the record cannot say so.

**Preregistered handling.** Declare **one realization record per DC model**,
each `ALGEBRAIC`, each requiring the same solver capabilities, each stating MNA
in `assumptions`; both providers bind all three. **The triplication is recorded
as a measured limitation of the record's grain**, mirroring
`model0r-differential-evidence.md` known-unknown 1. No composite "DC analysis"
model is invented and **no field is added** — `ModelRealizationDefinition` is
`DESIGN-FROZEN`.

**To keep this from being constructed evidence, the record's exact field values
are fixed here, in advance**, and "the ngspice adapter satisfies them unchanged"
is a checkable prediction rather than an outcome arranged afterwards:

```text
realization_id   electrical.dc.<model>.modified_nodal_analysis
version          0.1.0
model            ModelReference(<the model>, 0.1.0)
formulation      ModelFormulation.ALGEBRAIC
provided_capabilities        frozenset()
required_capabilities        frozenset()
required_solver_capabilities {electrical:dc_linear, core:linear_system}
assumptions      "modified nodal analysis: one equation per non-reference node,
                  plus one branch-current unknown per ideal voltage source"
                 "linear elements only; the assembled system is solved directly,
                  not iterated"
                 "the assembled system is non-singular; behaviour on a singular
                  system is a property of the concrete solver and is not claimed
                  by this realization"
implementation   ImplementationReference("engcore.domains.electrical.dc_realizations", "0.1.0", ...)
```

**If the grain problem cannot be handled honestly, the preregistered fallback is
option A:** leave `realization=None` on both paths and let the milestone be a
solver-substitution proof only. That is a smaller, honest result and is
preferable to a realization record shaped to make the proof work.

## 8.3 The payoff, and its ceiling

If it holds, `ProvenanceRecord.solvers_for_realization(...)` returns **two
solvers for one realization, one of which Crafty did not write** — the exact
shape that method's docstring was built for, never executed, and precisely the
gap `model0r-differential-evidence.md` §8.2 records (*"no code Crafty did not
write is involved anywhere in this milestone"*).

**That is the one scoped `L2` claim this milestone may make**, and only for
`Realization != Solver`. It does **not** upgrade the MODEL0-R boundary as a
whole, and nothing else here may claim `L2`.

---

# 9. Failure taxonomy — three outcomes, no classifier

## 9.1 The rule

| Outcome | Mechanism |
|---|---|
| **Provider execution failure** | **Raise**, from an error class local to the adapter inheriting `Exception` — **not** `ScientificCoreError` — mirroring `engcore.data`'s `BulkDataError`. Covers: launch failure, non-zero exit, unparsable output, **and any requested quantity absent from the output**. **No `ScientificResult` is synthesised.** |
| **Numerical convergence** | Reported from what was obtained, never from ngspice's exit code and **never from any warning text**. |
| **Scientific validity** | Decided **only** by Crafty's own `build_validation_report` (KCL, resistor-metric consistency, voltage-source relation, power balance), run over the provider's metrics exactly as on the native path. |

**A requested quantity absent from provider output is a provider failure**, not a
scientific one: the adapter cannot distinguish "absent because the solve had no
unique solution" from "absent because the adapter emitted a name ngspice does
not define." An ambiguous absence must be reported, never interpreted.

## 9.2 What is forbidden

**Mapping `"Warning: singular matrix"` onto `ConvergenceState.FAILED` is
forbidden.** It would make a serialized scientific field depend on an English
string from one ngspice version — provider text entering scientific semantics,
and the same magic-string failure mode `model0r-differential-evidence.md` §1
identified. Provider stdout/stderr may be carried **verbatim** in
`RawSolverOutput.warnings`, its sanctioned uninterpreted channel. **Control flow
may never branch on it**, and a test asserts this.

`ConvergenceState` gains **no member**. `ET-VERTICAL`'s `test_j2` already pins
its six values and is a pre-existing test.

## 9.3 The predicted asymmetry — stated as a result, not discovered as one

Given §2.5, the following is **predicted in advance**:

> On a structurally singular circuit, the native path reports
> `convergence=FAILED`, `validation=FAIL` and **zero metrics**. The ngspice path
> returns a **complete quantity set of zeros with exit 0**, and — because all
> currents and voltages are zero — **Crafty's own validation checks are
> predicted to PASS** (KCL is trivially satisfied, `v = iR` holds as `0 = 0`,
> and the power balance is `0 = 0`).
>
> **Prediction: the external path reports a CONVERGED, PASSING result for a
> circuit the native path refuses as singular.**

This is a genuine limit of provider substitution. **It will not be engineered
away**, because every available fix is worse: branching on stderr text is
forbidden by §9.2, and a Crafty-side structural connectivity pre-check would be
new domain logic added asymmetrically to make one provider look like the other.
It is recorded as a finding and as a known unknown.

**If the prediction is wrong** — if Crafty's validation *does* catch the
degenerate zeros — that is a better result than expected and must be reported as
such, with the check that caught it named.

---

# 10. Numerical comparison, fixed before observing results

**Scientific equivalence does not mean byte equality.** Content identity is not
scientific equivalence.

| Comparison | Criterion |
|---|---|
| Standalone electrical QoIs | **relative 1e-9**, with an **absolute floor of 1e-12** in each quantity's own unit |
| Coupled converged temperature | **absolute 1e-4 K** |
| Coupled `R*`, `P*`, `I*` | **relative 1e-6** |
| Coupling outcome | **exact equality** (`CouplingOutcome`) |
| Iteration count | **recorded, not required to match** |

**Justification.** Both paths perform a direct double-precision factorisation of
a small, well-conditioned system, so the true difference should sit near machine
epsilon; `set numdgt=12` lifts ngspice's text channel to 13 significant digits so
the transport is not the bound (§2.3). `1e-9` is therefore loose against the
arithmetic yet tight enough that any real translation error — a sign flip, a
factor-of-two, a wrong datum, a units slip — is caught by many orders of
magnitude. The absolute floor prevents a meaningless relative comparison against
quantities near zero. The coupled temperature tolerance is 100× the coupling
criterion (`1e-6 K`), because the fixed point is only located to that criterion
and a tighter demand would test the coupling tolerance rather than the provider.
**Iteration counts are not required to match**: Gauss–Seidel path length is not a
scientific invariant, and requiring it would be unjustified.

---

# 11. Placement

| Item | Location | Why |
|---|---|---|
| MNA realization records | `src/engcore/domains/electrical/dc_realizations.py` (**new**) | Beside `dc/`, following the pattern `material.py` and `thermal_lumped.py` already established. **`test_i2` pins the `dc/` file set**, so a new file inside it would break a pre-existing test |
| ngspice adapter | `src/engcore/domains/electrical/ngspice.py` (**new**) | Beside `dc/`: the DC package must not acquire subprocess/WSL machinery, and leaving `dc/**` byte-unchanged keeps the native path a clean control |
| Tests | `tests/test_heterogeneous_ngspice.py` (**new**) | |

**Not** `engcore/providers/`: a netlist emitter is irreducibly electrical
knowledge, and a provider tree that must import a domain is a misfiled domain
module, not a plane. Deferred with a named trigger (§4.2). Moving it later
changes no serialized record.

**`src/engcore/scientific/**` is not added to or edited.** Predicted; a fail
condition if violated.

---

# 12. Required tests

| ID | Test |
|---|---|
| **A** | **Real external process.** The ngspice executable actually runs. Mocking the subprocess is insufficient for this test; mocks may exist only for unit tests of the parser and error paths. |
| **B** | **Same scientific input.** Both paths consume the same canonical Crafty `DCCircuit` / `ScientificProblem`; the netlist is derived from it, never hand-written. |
| **C** | **Standalone numerical equivalence** within §10. |
| **D** | **Provider substitution.** `coupled.py` is byte-unchanged and the native and external runs invoke the *same function object*. |
| **E** | **Closed-loop equivalence.** Final coupled QoIs agree within §10, for CASE A and CASE E. |
| **F** | **Provenance distinction.** Native identifies the native solver; external identifies ngspice with its **run-time-read** version. Model identity is identical on both. |
| **G** | **Real provider failure**, typed and distinguishable from numerical non-convergence, coupling non-convergence and scientific invalidity. At least one failure is a genuine ngspice non-zero exit, not a simulated one. |
| **H** | **No provider leakage.** No `if provider == "ngspice"` or equivalent anywhere under `src/engcore/scientific/`; no ngspice vocabulary in universal core. |
| **I** | **No provider syntax in scientific records.** No SPICE netlist text is stored in any `ScientificProblem`, `ScientificModelDefinition`, `ModelRealizationDefinition`, `QuantityDependency`, or in `ProvenanceRecord.metadata`. The netlist lives in `PreparedSolve.payload`, which the contract already names as its home. |
| **J** | **Executable relocation.** Changing the configured invocation does not change the serialized `ScientificResult`. Asserted as byte-identity, reusing DATA-BOUNDARY0's relocation discipline. |
| **K** | **Regression.** All prior milestone tests green, unedited. Baselines: FULL **1744**, FAST **1249** passed / 495 deselected. |
| **L** | **Provider text is never branched on.** The adapter's control flow does not read provider stdout/stderr for anything except carrying it into `RawSolverOutput.warnings`. |
| **M** | **Realization shared.** Both providers bind the *same* `RealizationReference`s, and `solvers_for_realization` returns two solvers for one realization. |
| **N** | **Record growth.** The serialized run does not grow because the provider was substituted; netlist and stdout do not enter `ProvenanceRecord.metadata` (`ET-VERTICAL` §15.3 measured 16 kB/iteration already). |

---

# 13. Fail conditions

1. Any file added or edited under `src/engcore/scientific/`.
2. Any existing serialized schema version bumped.
3. A provider name, netlist syntax, executable path or WSL mechanic appearing in
   any scientific record or in universal core.
4. A new `ScientificModelDefinition` minted because the provider differs.
5. A realization record duplicated merely because the provider differs.
6. The coupling loop edited, or a second coupling function created.
7. Provider failure reported as numerical non-convergence, coupling
   non-convergence or scientific invalidity — or the reverse.
8. Control flow branching on provider stdout/stderr text.
9. A new `ConvergenceState` member.
10. Any pre-existing test edited, weakened, skipped or re-toleranced; or any file
    under `src/engcore/domains/electrical/dc/` or `src/engcore/domains/thermal/`
    changed; or `coupled.py` or `resistor_body.py` changed.
11. A generic provider framework required to make the proof pass.
12. The equivalence claim resting on a mock, a stub, or any Crafty-written stand-in.

---

# 14. Evidence ceiling, declared before running

```text
Decision status ceiling:   PROPOSED
Evidence ceiling:          L1 EXERCISED   (the provider boundary)
Scoped exception:          L2 DIFFERENTIATED for `Realization != Solver` only,
                           and only if §8.2 is satisfied honestly
L3:                        excluded outright
```

One provider, one version, one platform, one domain. **A successful ngspice
experiment proves that real external-provider substitution has been
*exercised*. It does not prove a universal provider architecture**, and the
evidence document may not say otherwise.

Per-claim levels are required. Stated in advance as **zero evidence**: session-
stateful providers, asynchrony, concurrency, remote execution, field-valued
provider output, timeouts and hangs, provider version drift, and any second
provider.

---

# 15. What the evidence document must refuse to claim

The provider is real ngspice-42 doing a real MNA/KLU solve; the WSL crossing is
an execution fact. That is enough for `L1` and not for more. The evidence
document must **refuse** to claim:

* portability across ngspice builds, distributions, versions or platforms — this
  is one apt build of ngspice-42 dated 2024-03-31, on one WSL Ubuntu noble, on
  one Windows machine;
* anything about in-process integration, libngspice, callbacks or shared-library
  error semantics;
* anything about session state, concurrency, asynchrony, restart or remote
  execution;
* anything about timeouts or hangs, unless executed;
* agreement between the two paths beyond the circuits actually run, to a
  tolerance declared before running.

---

# 16. Reduction attack

Run after the proof works. For every new type:

| # | Attack |
|---|---|
| R1 | `ElectricalDomainAdapterForNgspice` instead of any universal provider contract — can the adapter stay local without losing anything? |
| R2 | A parser result wrapper — is it derivable from what the adapter already returns? |
| R3 | A provider configuration record — is it more than an argv tuple? |
| R4 | An execution result record — does `RawSolverOutput` already carry it? |
| R5 | A netlist builder *class* — is it a function? |
| R6 | The three realization records — is one enough, or none? |

**Delete anything that merely wraps one use.** At least one new type must be
deleted or survive a serious attempt.

---

# 17. Stop rule

Stop when: real ngspice execution works; standalone equivalence is executed;
coupled provider substitution works; provider failure semantics work; provenance
is correct; and the falsification pass is complete.

Do **not** continue into FEniCSx, PETSc, OpenFOAM, a generic provider
framework, API/MCP or HVAC.

Per master context §60: at most **two** adversarial rounds.
