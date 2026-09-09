# Core assurance matrix

What each stage of the current Forge Core does, what is *proven* about it, and
what is merely *tested*, *assumed* or *unproven*. Written from the code as it
stands at the commit that adds this file, not from any design document.

**The rule this document is written under.** A green end-to-end verdict does
not certify the stages that produced it. Two wrong stages can compose into a
right answer, and a benchmark scored only on final verdicts cannot see the
difference. So every stage below is judged on evidence that is about *that
stage*, and where the only evidence is "the whole pipeline agreed with a number
we also wrote", it says so.

**No percentages.** Confidence in a scientific claim is not a coverage
fraction, and a number invites exactly the reading it cannot support.

---

## A. The pipeline, as the code actually runs it

The reference path is the electro-thermal boundary, because it is the one both
hard benchmarks drive. `run_electrothermal_case`
(`src/engcore/mcp/problem.py:2051`) is the whole boundary end to end.

| # | Stage | Producer | In → Out | Authoritative location | Introduces scientific meaning? |
|---|---|---|---|---|---|
| 1 | Value | caller payload | `str` → `Quantity` | `scientific/units/quantity.py:591` | no — magnitude + unit only |
| 2 | Problem | `build_electrothermal_system` | payload → `ScientificProblem` | `scientific/ir/problem.py:113` | no — a statement of what is asked |
| 3 | Model declaration | domain modules | — → `ScientificModelDefinition` | `scientific/models/definition.py` | **yes** — conditions and their bounds |
| 4 | Dependency / composition | `coupled_dependencies` | problems → edges | `scientific/composition/dependency.py:136` | **yes** — which quantity feeds which |
| 5 | Prerequisite resolution | `ValidityDomain` ordering | conditions → order | `scientific/models/definition.py:1216` | no — ordering only |
| 6 | Applicability | `ValidityDomain.assess` | context → `ValidityAssessment` | `scientific/models/definition.py:1290` | **yes** — in/out/unknown per condition |
| 7 | Coupling execution | `run_fixed_point_coupling` | plan → iterates | `systems/electrothermal/coupled.py:2096` | **yes** — the operating point |
| 8 | Raw result | solvers | prepared → `RawSolverOutput` | `scientific/solvers/protocol.py:328` | no — numbers and diagnostics |
| 9 | Result | domain assembly | raw → `ScientificResult` | `scientific/results/result.py:196` | **yes** — names the metrics |
| 10 | Uncertainty | domain | result → `Uncertainty` | `scientific/results/uncertainty.py:23` | **yes** — not populated on this path |
| 11 | Validation | domain checks | result → `ValidationCheck` | `scientific/results/validation.py:464` | **yes** — levels |
| 12 | Consensus | caller | routes → `CrossSolverConsensus` | `scientific/consensus.py:552` | **yes** — independence |
| 13 | Provenance | run | inputs → `ProvenanceRecord` | `scientific/results/provenance.py:281` | no — lineage |
| 14 | Report + verdict | `derive_verdict` | records → `CredibilityVerdict` | `src/engcore/mcp/evidence.py:502` | **yes** — the external claim |
| 15 | Serialization | `to_json` | record → wire | `scientific/serialization.py:187` | no — must preserve meaning |

Stages the pipeline does **not** have: `ContextOfUse`, `ScientificClaim`, a
scientific-artifact/data layer. Nothing below assumes them.

---

## B. Assurance matrix

`Contract` = the stage's input/output shape is pinned. `Invariant` = a property
over the input space, not an example. `Neg` = wrong input is refused.
`Bound` = thresholds are exercised at, below and above. `Meta` = a metamorphic
or property test. `Ind. oracle` = something outside Forge could contradict it.
`Golden` = a fully specified trace asserting this stage's intermediate state.

| Stage | Contract | Invariant | Neg | Bound | Meta | Oracle type | Ind. oracle | Golden | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 Value | YES | YES | YES | YES | YES | `MATHEMATICAL_IDENTITY` + `EXTERNAL_STANDARD` (pint/SI) | **YES** | PARTIAL | `CERTIFIED_INTERNAL` |
| 2 Problem | YES | YES | YES | PARTIAL | PARTIAL | `CODE_CONTRACT` | NO | PARTIAL | `STRONG_INTERNAL` |
| 3 Model declaration | YES | YES | YES | N/A | PARTIAL | `CODE_CONTRACT` | NO | NO | `PARTIAL` |
| 4 Dependency | YES | YES | YES | N/A | YES | `CODE_CONTRACT` | NO | PARTIAL | `STRONG_INTERNAL` |
| 5 Prerequisites | YES | YES | YES | N/A | YES | `CODE_CONTRACT` | NO | PARTIAL | `STRONG_INTERNAL` |
| 6 Applicability | YES | YES | YES | PARTIAL | YES | `CODE_CONTRACT`; bounds are `EXTERNAL_STANDARD` where cited, else `NO_ORACLE` | PARTIAL | PARTIAL | `PARTIAL` |
| 7 Coupling | YES | PARTIAL | YES | PARTIAL | NO | `INTERNAL_BENCHMARK` | NO | PARTIAL | `PARTIAL` |
| 8 Raw result | YES | YES | YES | N/A | PARTIAL | `CODE_CONTRACT` | NO | NO | `STRONG_INTERNAL` |
| 9 Result | YES | YES | YES | N/A | YES | `ANALYTIC_REFERENCE` (lumped closed form) | PARTIAL | PARTIAL | `STRONG_INTERNAL` |
| 10 Uncertainty | YES | YES | YES | N/A | PARTIAL | `NO_ORACLE` | NO | NO | `CAPABILITY_ABSENT` |
| 11 Validation | YES | YES | YES | PARTIAL | YES | mixed — see `ORACLE_REGISTER.md` | PARTIAL | PARTIAL | `PARTIAL` |
| 12 Consensus | YES | YES | YES | YES | YES | `CODE_CONTRACT` — independence is **declared** | NO | NO | `PARTIAL` |
| 13 Provenance | YES | YES | YES | N/A | YES | `CODE_CONTRACT` | NO | PARTIAL | `STRONG_INTERNAL` |
| 14 Verdict | YES | YES | YES | YES | YES | `CODE_CONTRACT` | NO | PARTIAL | `CERTIFIED_INTERNAL` |
| 15 Serialization | YES | YES | YES | N/A | YES | `CODE_CONTRACT` | NO | PARTIAL | `STRONG_INTERNAL` |

Status vocabulary: `CERTIFIED_INTERNAL` (contract, invariants, negatives,
boundaries and metamorphic properties all present, and mutation-checked);
`STRONG_INTERNAL` (systematic but not mutation-checked); `PARTIAL` (real gaps
named below); `UNPROVEN`; `CAPABILITY_ABSENT` (the stage exists but does
nothing on any current path).

**Why stage 14 is `CERTIFIED_INTERNAL` and stage 6 is not.** `derive_verdict`
is now pinned by properties over its whole input space, and four deliberate
mutations of its rules each turn that module red
(`tests/test_verdict_monotonicity.py`). Applicability is pinned the same way
for its *mechanism* — order independence, the nine condition shapes, reserved
namespaces — but not for its *bounds*, which is the distinction section C is
about.

---

## C. Software correctness vs scientific correctness

These are different claims and the matrix above deliberately does not merge
them.

| Stage | Software claim (proven) | Scientific claim (status) |
|---|---|---|
| 6 Applicability | the evaluator applies the declared range exactly, in an order fixed by declared prerequisites, and reports UNKNOWN for anything it could not derive | whether each declared range is the scientifically right range is a **separate** question, answered per condition |
| 7 Coupling | the loop transports the declared metric, terminates on a declared criterion, and records what it observed | that a converged fixed point is the physical operating point is **assumed**, and U00204 is where the assumption and the benchmark's label disagree |
| 11 Validation | a check cannot claim a level it did not test for, and cannot report PASS while its own residual exceeds its own tolerance | what `analytically_verified` is worth depends on the reference; see the register |
| 12 Consensus | agreement, completeness and shared-component intersection are computed exactly as documented | that the declared components are the *real* shared arithmetic is **unverifiable from here, by design** |

### Where the declared bounds came from

Audited per condition on the reference path. "Sourced" means the code cites a
specific external authority at the point of declaration.

| Condition | Basis | Sourced? |
|---|---|---|
| `melting_temperature_utilization` | bound is 1 by definition; lumped form has no latent-heat term. Cites Incropera et al. 6th ed. §5.1 | **YES** |
| `peak_body_temperature` monotonicity | first-order single-pole response. Cites Incropera 6th ed. §5.1 Eq. 5.6 | **YES** |
| `reference_reduced_debye_temperature` (θ_D/5) | relaxed from 1/3 against beryllium's published θ_D. Cites Kittel 8th ed. Ch. 5 Table 1 | **YES** |
| `reduced_debye_temperature` (θ_D/3) | Bloch–Grüneisen linear regime | PARTIAL — the regime is standard, the exact 1/3 is repository policy |
| `operating_temperature_utilization` | "a hard material limit rather than a modelling tolerance" | **UNSOURCED** — bound of 1 is definitional, but the *operating point* it is read at is a repository choice; see `FALSE_ACCEPT_ADJUDICATIONS.md` |
| `linearization_excursion_ratio` | first-order Taylor remainder grows with excursion | **UNSOURCED** — the argument is stated, the band is caller-declared |
| `biot_number` limit | standard lumped-capacitance criterion | PARTIAL — conventional, not cited at the declaration |
| `internal_fourier_number` floor | one-term series validity | PARTIAL — adjudicated as a *conservative screen* on 2026-09-09 |
| `radiation_to_convection_ratio` | share of heat leaving by radiation | **UNSOURCED** |
| `convection_*` correlations | natural/forced convection correlations | PARTIAL |

Nothing above was changed in this round. `UNSOURCED` means the repository has
not written down where the number came from — not that the number is wrong.

---

## D. Known gaps, per stage

* **6 Applicability.** Two hard material ceilings in one report are evaluated at
  different operating points: `melting_temperature_utilization` at
  `max(T_0, T_ss)` — documented as bounding the trajectory "including horizons
  the caller has not yet asked for" — and `operating_temperature_utilization` at
  `T(duration)`. The endpoint convention is the one the landed
  `internal_fourier_number` adjudication requires; the difference is real,
  deliberate on one side and undocumented on the other. Written up in
  `FALSE_ACCEPT_ADJUDICATIONS.md`. Also: the ceiling condition is the only
  path-dependent one of the three with **no binding-instant parameter**.
* **7 Coupling.** The fixed-point iteration's convergence is a property of the
  *scheme*, not of the design. U00204 converges under the tool's map and its
  four dev siblings are refused; the difference is which map found the basin.
  There is no independent oracle for "this design has a stable operating point".
* **10 Uncertainty.** Representable, tested, and populated by nothing on the
  electro-thermal or battery paths. Every reported verdict is uncertainty-free.
* **12 Consensus.** Independence is a declaration. See
  `CLAIMS_AND_CAPABILITY.md` for what the record can and cannot represent.
* **Scalar ceiling.** `Quantity` is a scalar magnitude and unit. Fields,
  spectra, distributions and time series have no representation. This is an
  architectural limit, not a defect.

---

## E. Assurance coverage, restated as a caution

Do not read the FAST/SCIENTIFIC test counts as scientific confidence. They
count assertions about software behaviour. The two figures that bear on
scientific confidence are:

* **16 validation checks pass today while establishing no evidentiary level**
  (`docs/domains/evidentiary-levels.md`) — the audit exists to report that
  number rather than to shrink it.
* **One check on the reference path establishes a level at all**
  (`analytic_reference_agreement`), and it is code verification of a closed
  form against a series recurrence — not physical validation. Its own detail
  string says so.
