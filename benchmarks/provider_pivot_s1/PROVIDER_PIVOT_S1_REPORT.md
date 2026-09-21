# Forge provider pivot — Sprint 1

Branch `claude/provider-architecture-pybamm-pybop`, base
`claude/battery-voltage-s3-recovery @ 0b032c97` (local only; that branch has not
been pushed to `origin`, and its tip was verified before this branch was cut).

```bash
python benchmarks/provider_pivot_s1/harness/sensitivity.py
python benchmarks/provider_pivot_s1/harness/fit.py
python benchmarks/provider_pivot_s1/harness/compare.py
```

Those three need `forge[battery-pybamm]`, `forge[battery-fit]` and
`forge[sensitivity]`. PyBOP 26.3 declares `requires-python = ">=3.10,<3.14"`, so
they were run on a dedicated **CPython 3.13.15** environment. The rest of the
repository suite still runs on 3.14, where those extras are uninstallable and
every provider reports `PROVIDER_UNAVAILABLE`.

---

## 1. Verdict

**FORGE PROVIDER PIVOT SPRINT 1: PASS**

PyBaMM operates as an external scientific provider. Forge selects the model,
owns the parameters, screens applicability before the provider is called,
normalises the output into its own vocabulary, records what ran, re-executes it
to check replay, and decides — through the same credibility path a native solve
travels — that none of it is supported yet.

The last clause is the interesting one. A wrapper would have returned the
number.

---

## 2. Area by area

| Area | Before | After | Provider | Forge value added | Evidence | Status |
|---|---|---|---|---|---|---|
| External solver execution | one adapter, ngspice, subprocess only | a generic contract plus an in-process adapter | PyBaMM 26.8.0.0 | request/identity/outcome/replay generalised; execution deliberately not | `src/engcore/providers/contract.py`, `COMPARISON.json` | **done** |
| Battery physics | native 1-RC Thevenin only | ECM / SPM / SPMe / DFN allowlisted through PyBaMM; two of the four executed this round | PyBaMM | model allowlist with declared inclusions, exclusions, cost and applicability | `MODEL_CATALOGUE` | **allowlist done; SPM and DFN never run — see §5** |
| Model fidelity | implicit | explicit axis, and explicitly not an order | — | `fidelity_class` is a label; a guard fails if it is ever compared | `test_fidelity_is_a_label_and_not_an_order` | **done** |
| Parameter authority | per-round JSON records | one frozen record, digested, with lineage | — | a named PyBaMM set cannot be mutated in place; overrides mint a new authority citing its parent | `FIT.json` → `blocks.*.authority` | **done** |
| Parameter inference | Forge's own fitters | PyBOP | PyBOP 26.3 | calibration-only enforced by a type, before PyBOP is imported | `FIT.json`, `test_pybop_cannot_fit_anything_but_calibration_data` | **done** |
| Sensitivity | none | Morris / Sobol / FAST | SALib 1.6.0 | sensitivity is evidence that can never become validation | `SENSITIVITY.json` | **done** |
| Canonical QoIs | domain constants | same constants, provider-independent | — | no PyBaMM spelling crosses into Core; a QoI the model cannot produce is refused, not defaulted | `CANONICAL_QOIS`, `test_canonical_qois_are_provider_independent` | **done** |
| Applicability | per-domain | screened before the provider runs | — | `Chen2020` + SPMe refuses 52 of 52 NASA trajectories without PyBaMM being called | `COMPARISON.json` → `routes.pybamm_spme\|*` | **done** |
| Provenance | run/model/solver | plus provider version, Python version, platform, CasADi/NumPy/SciPy versions, adapter version, authority digest, configuration digest | — | versions, never locations — the ngspice rule kept | `ProvenanceRecord.environment` | **done** |
| Replay | stored-artifact comparison | re-execution | — | 3 of 3 sampled runs re-executed, identity matched, bit-identical at tolerance 0 | `COMPARISON.json` → `replay` | **done** |
| Failure vocabulary | exceptions | six outcomes in two halves plus `OK` | — | "PyBaMM is not installed" is not "the science does not hold" | `ExecutionOutcome` | **done** |
| Risk / coverage | none | coverage, false trust, over-refusal, risk-vs-coverage curve | — | the record type cannot name an engine, so two providers cannot be scored on different scales | `COMPARISON.json` → `risk_*` | **done** |
| Native battery models | production | unchanged and still the baseline | — | nothing deleted, nothing deprecated | `git diff --stat src/engcore/domains/` is empty | **done** |
| Independent Gate A | not passed (S3 recovery) | still not passed, and not attempted | — | no holdout opened, none manufactured | §5 | **open** |

---

## 3. The comparison

52 development trajectories from the NASA PCoE Li-ion aging archive — 33
calibration, 19 validation — loaded through the Sprint 3 recovery's own corpus
loader, which refuses to return a holdout trajectory. 11 755 samples inside the
applicability window; 3 082 outside it and scored by nobody.

**One window, applied to every route identically.** Every discharge in this
archive runs to a charge state near zero; the open-circuit-voltage authority
was measured down to 0.10 (warm) and 0.05 (cold) and below its floor the curve
is *held*. A prediction there is not one the OCV authority supports, for either
model, so the window is the screen both are held to.

| route | split | n | offered | refused | MAE | RMSE | P95 | bias | runtime |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| native | calibration | 33 | 33 | 0 % | 22.93 mV | 49.98 mV | 91.52 mV | +1.56 mV | 0.51 s |
| native | validation | 19 | 19 | 0 % | 24.70 mV | 44.63 mV | 94.80 mV | −6.82 mV | 0.37 s |
| pybamm_thevenin_1rc | calibration | 33 | 24 | 27 % | 27.75 mV | 41.48 mV | 78.32 mV | −2.84 mV | 0.45 s |
| pybamm_thevenin_1rc | validation | 19 | 19 | 0 % | 30.89 mV | 41.13 mV | 83.62 mV | −9.04 mV | 0.36 s |
| pybamm_spme | calibration | 33 | 0 | **100 %** | — | — | — | — | 0.00 s |
| pybamm_spme | validation | 19 | 0 | **100 %** | — | — | — | — | 0.00 s |

These are **not** the recovery's Gate A numbers and are not comparable to them:
that round scored its own case selection at its own stride, and this one scores
every sample inside the OCV window.

### THE TABLE ABOVE IS NOT A MODEL COMPARISON

Each route is scored over the trajectories **that route offered**, which is the
right population for a refusal rate and the wrong one for comparing two models.
The native route offers all 33 calibration trajectories; the equivalent-circuit
route offers 24, and the nine it declines are the aged cells where the native
model is 77 to 183 mV out. Reading the first table as a comparison charges the
native model for cases its competitor never attempted — which is exactly what
the first draft of this report did, concluding that "the provider route has the
lower calibration RMSE". It does not.

Over the trajectories **both** routes offered:

| route | split | traj | samples | MAE | RMSE | P95 | bias |
|---|---|---:|---:|---:|---:|---:|---:|
| native | calibration | 24 | 6 199 | **16.07 mV** | **30.43 mV** | **45.11 mV** | +1.31 mV |
| pybamm_thevenin_1rc | calibration | 24 | 6 223 | 27.75 mV | 41.48 mV | 78.32 mV | −2.84 mV |
| native | validation | 19 | 4 773 | **24.70 mV** | 44.63 mV | 94.80 mV | −6.82 mV |
| pybamm_thevenin_1rc | validation | 19 | 4 792 | 30.89 mV | **41.13 mV** | **83.62 mV** | −9.04 mV |

**On calibration the native model is better on every statistic** — 12 mV of MAE
and 11 mV of RMSE. It should be: it carries an Arrhenius temperature dependence
on both resistances and a measured charge-state shape on the ohmic term, none of
which the equivalent circuit has, and its parameters were fitted on those very
trajectories.

**On validation the result is mixed and genuinely so.** The native model is
better typically (MAE 24.70 against 30.89 mV); the equivalent circuit has fewer
large excursions (RMSE 41.13 against 44.63, P95 83.62 against 94.80). A model
with a temperature-dependent resistance tracks the middle of the distribution
better and its tail worse, which is what a temperature term does when the
temperature it is keyed to is itself predicted.

Neither of those is a reason to prefer either model, and this round does not:
that is a decision for an independent Gate A, which §5 says requires new
evidence.

### SPMe

**SPMe refuses everything, and PyBaMM is never called for it.** `Chen2020`
describes a 5 A.h NMC811/graphite-SiOx LG M50; the archive holds ~1.6 A.h
18650 lithium-cobalt-oxide cells. Chemistry and capacity both fail the screen.
PyBaMM would have solved every one of those 52 in about a quarter of a second
each and returned a beautifully converged voltage curve for a cell that is not
this cell. That is the single clearest thing in this report.

### Sensitivity, and what it was allowed to decide

Morris elementary effects over the five parameters an equivalent-circuit
voltage prediction can depend on, on the longest warm calibration discharge
(`B0005.d0032`, 321 samples inside the window), 72 design points, SALib 1.6.0.

| parameter | mu* (mean absolute elementary effect) |
|---|---:|
| `R0 [Ohm]` | 0.861 |
| `R1 [Ohm]` | 0.350 |
| `initial_state_of_charge` | 0.054 |
| `C1 [F]` | 0.051 |
| `capacity_scale` | 0.019 |

An order of magnitude between the second and the third. That is what decided
the fit: `R0` and `R1` are fitted, `C1` is **held** at the recovery's own
polarization capacitance rather than handed to an optimiser that would move it
against a response that barely carries it.

It decided nothing else. `SensitivityEvidence.is_validation_evidence` is
`False` and the record says why in its own payload.

---

## 4. Risk and coverage

Per-trajectory decisions against the preregistered 50 mV RMSE limit, computed by
`engcore.credibility.risk_coverage.summarise` over records that carry no field
naming which engine produced them.

| route | coverage | false trust | correct refusals | over-refusals | over-refusal rate |
|---|---:|---:|---:|---:|---:|
| native | 100 % | 38.5 % (20/52) | 0 | 0 | *unmeasured* |
| pybamm_thevenin_1rc | 82.7 % | 25.6 % (11/43) | 2 | 2 | 50 % |
| pybamm_spme | 0 % | *unmeasured* | 0 | 0 | *unmeasured* |

**The screen buys 13 points of false trust for 17 points of coverage.** That is
the product's whole proposition, measured on real data for the first time.

**The over-refusal rate is measured, not assumed.** A refusal hides what the
model would have said, so each of the 9 refused trajectories was re-run under a
*counterfactual* authority declaring that cell's own measured capacity — a
measuring instrument with its own digest, never offered as a supported
prediction. Four of the nine could be observed (the other five fail a second
screen condition too). Of those four, **two refusals were correct** (72.0 and
62.9 mV, outside the gate) and **two were over-refusals** (40.9 and 42.5 mV,
inside it).

So the 25 % capacity band is a useful screen and a crude one. It is not
tightened here: choosing a tolerance to improve a number measured on the same
data is how a screen stops being a screen.

**A corroboration, and it is not the same claim.** The native model — which has
no capacity screen — is outside the 50 mV gate on **all nine** of those aged
cells, at 76.8 to 182.6 mV. That is the same failure the recovery round
diagnosed when it opened B0041: a model with no impedance-growth term, asked
about a cell that has grown impedance. The screen catches those cases
prospectively rather than by opening a holdout. It does not follow that all nine
refusals were correct *for the equivalent-circuit model*, and the paragraph above
says what was actually measured.

### The trust path

| route | coverage through the full credibility verdict |
|---|---|
| native | not computed — this march produces no `ScientificResult` |
| pybamm_thevenin_1rc | **0 %** |
| pybamm_spme | **0 %** |

Zero, and correctly so. A PyBaMM run attains no `ValidationLevel`: its adapter's
checks compare an output against the shape it was asked for, with no independent
reference, so they establish nothing. Without an attained level the credibility
report is `INSUFFICIENT_EVIDENCE`, which is the honest reading of "this ran and
nobody has shown it agrees with the world".

The native row is blank because the recovery's march predates the result
contract in this corpus and its own freeze record says so ("no replay of an
authorized plan and no certification record"). A `ScientificResult` was **not**
fabricated to fill that cell. The claim that both engines enter the same
assembly is proved instead where a native solve does produce one:
`tests/providers/test_provider_trust_path.py::test_native_and_pybamm_results_enter_the_same_trust_assembly`.

---

## 5. What this round does not establish

* **No independent Gate A, for any of the three routes.** Every cell in this
  archive has had its residuals read — B0041 by the recovery round, B0007,
  B0036 and B0044 by Sprint 3. No pristine holdout remains and this round did
  not manufacture one. An independent Gate A requires **new evidence**: another
  archive, another campaign, or cells nobody here has scored.
* **No validation level for any provider result.** Coverage through the trust
  path is zero and will stay zero until somebody produces validation evidence
  bound to a provider run.
* **No parameter uncertainty from the fit.** PyBOP's Bayesian samplers were not
  run. `FitEvidence.parameter_uncertainty` is `None` — not zero, and not the
  per-trajectory spread, which is a dispersion of point estimates with no
  probability model behind it.
* **No SPM or DFN result at all.** Neither has a parameter authority for these
  cells, and there is no electrode-level characterisation of them to build one
  from. They are in the allowlist and were never run.
* **Sensitivity was screened on one trajectory.** The longest warm calibration
  discharge, named in `SENSITIVITY.json`. A ranking on one scenario is a
  screening result and is labelled as one.

---

## 6. Declared approximations, and what each cost

**One**, and it is measured rather than argued.

The native cell's charge state is closed at `z = 1`, which is where all 52
trajectories start; PyBaMM's equivalent-circuit model carries its SoC bounds as
termination *events*, so at exactly 1.0 the event is non-positive at the initial
condition and the solve ends before its first step. The measured full-charge
state is therefore mapped to the largest state the ECM can represent, by
subtracting `ECM_STATE_MARGIN = 1e-3`.

It is applied in the benchmark and never inside the adapter: a provider that
quietly moved a caller's scientific input to make its own model run is the thing
this sprint is against. Re-running the whole equivalent-circuit route at a tenth
of the margin moves

| metric | at 1e-3 | at 1e-4 | change |
|---|---:|---:|---:|
| MAE | 29.115 mV | 29.017 mV | −98.5 µV |
| RMSE | 41.327 mV | 41.318 mV | −9.6 µV |
| P95 | 82.402 mV | 82.325 mV | −76.7 µV |
| bias | −5.542 mV | −4.877 mV | +664.9 µV |

against a 50 mV gate.

---

## 7. What went wrong, and what it cost

Recorded so a later session does not repeat it.

1. **Screening an ambient temperature against a cell-temperature band.** The
   OCV authority states its bands on *median measured cell temperature* and
   says "Ambient is not the condition." The first screen compared the ambient.
   Found by the counterfactual probe, which could not lift a refusal it should
   have been able to lift. Fixed by giving `ParameterAuthority` a
   `temperature_basis` and `CellUnderTest` both quantities; a cell that cannot
   supply the authority's basis is refused, never given the other as a
   substitute. Regression test:
   `test_a_band_stated_against_cell_temperature_is_not_screened_on_ambient`.
2. **Fitting outside the interval the parameter authority was measured over.**
   The first PyBOP run fitted whole trajectories, tail included. Nine of
   thirty-three fits failed outright (the provider's solve terminated at its own
   SoC floor before the measured trajectory ended, and PyBOP's cost cannot take
   a length mismatch) and six survivors drove `R0` onto its lower bound,
   compensating for a held OCV tail with a resistance the cell does not have.
   Both are one defect. Fixed by the applicability window.
3. **One parameter set per temperature band.** Reproduced the recovery's own
   finding from the other direction: `R0`'s interquartile spread was 81 % across
   the warm band, because that band pools 1 A, 2 A and 4 A discharges and the
   measured resistance is rate-dependent. Per operating block the spreads are
   0.3 % to 34.8 %.
4. **A screening design spending a sixth of its points on a model boundary.**
   Morris at `initial_state_of_charge ∈ [0.90, 1.00]` put 12 of 72 points at
   exactly 1.0, every one of them refused, and SALib correctly reported
   `MISSING_EVIDENCE` rather than substituting a value. The range now stops at
   0.999.
5. **Text searches for a forbidden word.** Two guards were first written as
   substring searches and both fired on prose that was *explaining* the rule —
   `risk_coverage.py`'s docstring saying why its record cannot name a provider,
   and `pybop_provider.py`'s saying why a fit is not a `ScientificResult`. Both
   are now AST walks, which is the distinction `tests/core_vocabulary.py`
   already drew for the Scientific Core.
6. **Comparing two models over two different populations.** The per-route
   table scores each route over the trajectories it offered, and read as a
   model comparison it said the provider route had the lower calibration RMSE.
   It does not: the native route was additionally carrying the nine aged cells
   the provider declined. Over the 24 both offered the native model is better
   by 12 mV of MAE and 11 mV of RMSE. `COMPARISON.json` now carries a
   `like_for_like` block and §3 leads with the warning.
7. **Reaching a first-party module through an opaque `sys.path` insert.** The
   harness inserted a pre-joined path variable, and `test_core_guards.py`'s
   dependency sweep — which resolves such a module by reading the *string
   segments* of the mutation — saw `corpus` and `predict` as two third-party
   packages it could not resolve. Fixed by spelling the segments out and
   re-exporting `march` through `common`. The same sweep caught
   `battery_cases`, which a test reached the same way; that fixture is now
   written out locally.

### Four repository guards this work moved, each deliberately

`tests/test_heterogeneous_ngspice.py::test_r1_...` asserted
`not (REPO_ROOT / "src/engcore/providers").exists()`. Its named trigger has
fired, so the file-absence stand-in is replaced by what it stood for: the six
forbidden framework names — registry, definition, capability graph, backend
hierarchy — now checked against **both** packages, plus a new assertion that
the generic contract names no provider and a new control test that the ngspice
adapter did not move under it.

`test_the_bare_install_..._must_be_green` pinned the exact set of modules under
`src/` that reach an optional dependency at `{mcp/server.py}`. It is now that
module plus the two provider adapters, with `salib_provider.py` named in the
comment: the guard derives `salib` from `pyproject.toml` while the package
imports as `SALib`, so it is blind to that module by a spelling rather than by
an exemption.

`test_the_policy_names_every_non_core_package` and `NON_CORE_PACKAGES`: the
first was **already red on the base branch** (`domainpacks` classified and never
named in the policy); both are repaired in the same edit that adds `providers`.

`test_every_static_guard_exists` caught the R1 rename — `conftest.py`'s
`STATIC_GUARDS` still named the old function, and a renamed guard would have
dropped out of the FAST tier silently. Updated with the new name and its new
control test.

---

## 8. Architecture budget

| | |
|---|---|
| new production code lines (excluding blanks, comments, docstrings) | **2 246** |
| — `engcore/providers/` | 2 094 |
| — `engcore/credibility/risk_coverage.py` | 152 |
| new schemas | **4** (`provider_identity`, `provider_request`, `provider_execution_receipt`, `provider_replay_report`) |
| new public abstractions | 31 classes, 1 new non-Core package |
| new test files / code lines | 5 / 1 118 |
| new benchmark harness files / code lines | 4 / 1 242 |
| repository guards updated | 4, each recorded in §7 |
| frozen Core digest | **unmoved** — nothing is exported from a canonical module |
| native models deleted | **0** |

### Forge contracts reused rather than reinvented

`ScientificResult`, `ProvenanceRecord`, `ExecutionBinding`, `ModelReference`,
`SolverIdentity`, `ConvergenceState`, `ValidationReport`, `ValidationCheck`,
`ValidationOutcome`, `Uncertainty`, `Quantity`, `ScientificDataReference`,
`BulkDataStore` / `store_values` / `BulkDataResolver`,
`CredibilityEvidenceReport.from_result`, `CredibilityVerdict`,
`ModelValidityRecord`, `ValidityAssessment`, `schema_string` / `require_schema`,
`freeze`, and the battery domain's own canonical metric names.

No new trust subsystem, no new UQ subsystem, no new replay subsystem, no new
certification subsystem, no new generic physics framework, no plugin discovery,
no capability graph, no provider registry.

---

## 9. The two questions

### DID FORGE BECOME A WRAPPER? **NO.**

P15 names seven things the answer has to be built from. Item by item:

| required | present | where |
|---|---|---|
| same solver output | **yes** — PyBaMM's numbers, unaltered; the adapter renames and does not recompute | `COMPARISON.json` → `per_trajectory[*].routes.pybamm_thevenin_1rc` |
| Forge applicability | **yes** — 52/52 SPMe refusals and 9/52 ECM refusals, all before PyBaMM is called | `ParameterAuthority.screen`, `PyBaMMModelSpec.state_of_charge_interval` |
| Forge validation evidence | **no, and declared** — the comparison is development and validation evidence; none of it is bound to a provider run as an attained `ValidationLevel`, and the trust path reports 0 % coverage because of it | §5 |
| Forge UQ requirements | **yes** — every provider value carries an explicit `Uncertainty.unknown` with a reason; PyBaMM quantifies none and the adapter invents none | `_to_scientific_result` |
| Forge refusal behaviour | **yes** — six outcomes in two halves, provider failure distinguished from scientific refusal | `ExecutionOutcome` |
| Forge replay | **yes** — re-execution, 3 of 3 sampled runs bit-identical at tolerance 0 with identity matched | `COMPARISON.json` → `replay` |
| Forge trust verdict | **yes** — `INSUFFICIENT_EVIDENCE`, through the unchanged credibility path | §4 |

Six of seven. The seventh is the sprint's declared gap and not an oversight:
binding validation evidence to a provider run means issuing an attained level,
and this corpus has no pristine holdout left to issue one from. Manufacturing
one would have been the failure this round exists to avoid.

And six pieces of evidence, each of which a wrapper would fail:

1. **It refuses runs the provider would have completed.** SPMe + `Chen2020` is
   declined on 52 of 52 trajectories and PyBaMM is never called. The refusal
   names chemistry and capacity, and the physics is correct: those parameters
   describe a different cell.
2. **It refuses the provider's own boundary as applicability.** At `SoC = 1.0`
   exactly, PyBaMM's ECM ends before its first step. That reaches a caller as
   `MODEL_NOT_APPLICABLE` with the interval named, not as a stack trace.
3. **A successful execution does not become support.** Every equivalent-circuit
   run that delivered reached `INSUFFICIENT_EVIDENCE` in the credibility path,
   because its checks establish no validation level.
4. **It will not let the provider's fitter see validation data.** Four dataset
   roles are refused before PyBOP is imported, including "unspecified".
5. **It re-executes.** Replay is a second solve compared at tolerance 0, and a
   run that reproduced the same numbers under a different provider version is
   reported as *not* reproduced, with the moved field named.
6. **It measures its own guardrail.** 25.6 % false trust at 82.7 % coverage
   against 38.5 % at 100 %, with the over-refusal rate obtained by running the
   counterfactual rather than by assuming the refusals were right — and the
   answer came back 2 right, 2 wrong.

### DID THE SAME TRUST ENGINE WORK FOR BOTH NATIVE AND EXTERNAL SOLVERS? **YES.**

`CredibilityEvidenceReport.from_result` was written before any provider existed
and is unchanged. It takes a native battery solve and a PyBaMM solve, and

* with no applicability evidence, returns `INSUFFICIENT_EVIDENCE` for both;
* given the applicability record its model's declared conditions support,
  returns `SUPPORTED` for the native result;
* given the honest `UNKNOWN` assessment, does not return `SUPPORTED` for the
  provider result;
* refuses an empty `IN_DOMAIN` assessment **identically** for both, so the
  shortcut is closed on the provider side and the native side by one rule.

And the negative half: `tests/providers/test_provider_trust_path.py::test_the_trust_path_contains_no_branch_on_provider_identity`
walks every module of `credibility`, `claims` and `sria` and asserts that none
of them names a provider in code — identifiers, attributes and non-docstring
literals, the same reach `tests/core_vocabulary.py` uses for domain leakage.

---

## 10. Status summary

```text
PyBaMM models integrated    4 allowlisted: thevenin_1rc, spm, spme, dfn
                            2 executed this round (thevenin_1rc; spme, refused
                            before execution on every case, which is a result)
PyBaMM exact version        26.8.0.0
PyBOP exact version         26.3
SALib exact version         1.6.0
Parameter authority         WORKING. Named sets immutable; overrides mint a
                            derived authority with its own digest and the
                            parent's recorded. 6 fitted block authorities.
Sensitivity                 WORKING. Morris, 72 design points, R0 0.861 >
                            R1 0.350 >> the rest. Decided what to fit and
                            nothing else; is_validation_evidence is False.
Canonical QoIs              terminal_voltage, current, time, state_of_charge,
                            cell_temperature, open_circuit_voltage. Forge
                            names, not PyBaMM's. A QoI a model cannot produce
                            is refused, never defaulted.
Replay                      WORKING, by re-execution. 3/3 sampled: executed,
                            identity matched, bit-identical at tolerance 0.
Trust path                  WORKING and returning 0 % coverage, correctly.
                            Same CredibilityEvidenceReport.from_result for
                            native and provider; no branch on provider in
                            credibility, claims or sria.
False-trust metrics         WORKING and provider-independent by type.
                            native 38.5 % at 100 % coverage;
                            PyBaMM ECM 25.6 % at 82.7 %, over-refusal 50 %
                            measured on 4 observable counterfactuals.
New production code         2 246 lines (2 094 providers + 152 risk_coverage)
New abstractions            31 public classes, 4 schemas, 1 non-Core package
Known gaps                  no independent Gate A; no validation level bound
                            to any provider run; no parameter uncertainty;
                            SPM and DFN never executed; sensitivity screened
                            on one scenario. All in section 5.
```

---

## 11. Provider versions and licences

| provider | version | licence | integration | distribution |
|---|---|---|---|---|
| PyBaMM | 26.8.0.0 | BSD-3-Clause | optional runtime import | not vendored, not redistributed |
| PyBOP | 26.3 | BSD-3-Clause | optional runtime import | not vendored, not redistributed |
| SALib | 1.6.0 | MIT | optional runtime import | not vendored, not redistributed |

Environment: CPython 3.13.15, CasADi 3.7.2, NumPy 2.3.5, SciPy 1.18.1,
win32-AMD64. Every one of those is recorded in the provenance of every run.
