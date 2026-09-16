# Main adversarial audit — 2026-09-15

Audited tree: `origin/main` at `1edddd70ce2127b518d7f9fda7210e8589883c6b`.
Question asked: can Forge accept, certify, route, infer from, admit, serialize, replay or present scientific
evidence more strongly than the evidence justifies? Verdict at the audited commit: **yes**; core freeze
rejected with 7 P0, 23 P1, 22 P2 and 12 P3 findings.

This document records every finding, what now enforces its invariant, the regression test that was seen
failing on the audited tree, and what remains open. Mutation ids refer to `tests/mutation_guards.py`
(GUARDS 29–35) unless marked `TRUST-*` (`benchmarks/trust_hardening/audit/mutations.py`).

Status legend: **FIXED** (the adversarial scenario is refused), **PARTIAL** (the scenario is refused; a
stated residual remains), **DEFERRED** (needs a frozen-API shape change; stated as a Core Freeze V3 non-claim).

## P0 — scientific false accept / trust-chain break

| ID | Area | Status | What now holds |
|---|---|---|---|
| SRIA-TRUST-01 | SRIA | FIXED | The Arbiter runs a fixed registry of trusted critics itself and records what each produced; `decide(evidence=…)` counts only assessments it recorded for that record hash (or that record's run), from the record's own domain pack, with a budget about the claimed quantity and the evidence's own uncertainty declaration. An `AdmissionAuthority` declares the critic registry and obligation policies it trusts and serves one Arbiter, so a second Arbiter with fabricated critics can decide but never admit. Claims stating a value are bound to the assessed result's value. |
| SRIA-TRUST-02 | SRIA | FIXED | Charters carry a digest and derived version; obligation sets carry the charter digest; the runner refuses a mismatched set or version; decisions commit the policy digest into their hash and authorization. |
| SRIA-TRUST-03 | SRIA | FIXED | Domain checks resolve only in DOMAIN assessments of the evidence's pack; a check reported twice is unmet as ambiguous; every assessment of a required critic class must pass. |
| SRIA-TRUST-04 | SRIA | FIXED | Authorization requires a decision about the exact `record_hash`; a decision authorizes at most once. |
| CONS-01 | consensus | FIXED | A route pin names its threshold gate and tolerance key; any other declared set or key awards no level, including after `from_dict`. |
| HUQ-01 | Hybrid UQ | FIXED | A multistart below `max(6, 2p+2)` starts or narrower than the default policy is at most DOWNGRADED (`MULTISTART_INCOMPLETE`); the policy used is committed in the diagnostics digest. |
| HUQ-02 / INF-04 | Hybrid UQ / inference | FIXED | A collapsed posterior (ESS < p+1) is refused before any small-grid waiver; the grid predictive wrapper takes its claim from the router's own judgement and never hard-codes SUPPORTED. |

## P1 — major trust or applicability gap

| ID | Status | What now holds / residual |
|---|---|---|
| HUQ-03 | FIXED | Log-parameter widths are measured on the natural scale; the verdict is unit-invariant. |
| HUQ-04 | FIXED | `PosteriorGrid` refuses weights that are not the normalized likelihood; the grid digest covers log-likelihood and mask. |
| HUQ-05 | PARTIAL | Rebuilt tables are spot-checked against `forward` at 8 deterministic nodes; a builder altering only unchecked nodes is not caught. |
| HUQ-06 | FIXED | A supplied grid must match the request's parameter names and dataset. |
| HUQ-07 | FIXED | Predictive probes include pairwise diagonals and Σ∇g. |
| HUQ-08 | FIXED | χ² probes include pairwise diagonals; a converged refit below the estimate's objective refuses (`NOT_A_LOCAL_MINIMUM`). Cost of the validity check is now 4p+1+2p² evaluations. |
| HUQ-09 | PARTIAL | Reasons and identifiability are re-derived from carried numbers on read; digests are documented as integrity-only. The Jacobian is not stored, so it cannot be re-derived. |
| HUQ-10 | FIXED | Fewer evaluated probes than parameters records NaN and refuses. |
| RES-01 | FIXED | Silent provenance in a stored result loads only marked (`stored_attribution_gap`), round-trips as written, and cannot become SUPPORTED; no schema bump (Core Freeze V1 serialization contract preserved). |
| RES-02 | FIXED | An older schema label carrying keys only newer versions write is refused; required keys must be present. |
| RES-04 | PARTIAL | At the MCP evidence boundary an assessment must cover exactly the resolved model's declared conditions; the core `ScientificResult` constructor cannot check names (no registry in the core). |
| VAL-01 | PARTIAL / DEFERRED | CROSS_SOLVER / BENCHMARK / EXPERIMENTAL levels need a verifiable issuer record in `evidence`, re-checked on construction and read. A genuine record copied onto another check, and weaker hand-built levels, remain; a result-binding field on `ValidationCheck` is deferred. |
| IND-02 | PARTIAL | `CrossSolverConsensus.from_results` takes typed results bound to route solver, version, backend, run and value hash; `over()` never awards a level. A fabricated `ScientificResult` is still constructible. Execution bindings as a dataclass field / schema /4 are deferred. |
| IND-03 | FIXED | `py:` identities must hash the source Forge resolves; `ext:` identities need a pinned digest. |
| IND-04 | FIXED | The CSTR steady-state check no longer awards CROSS_SOLVER_VALIDATED. K1's preregistered A6 is recorded unmet in `experiments/kinetics_k1/ADJUDICATION_A6.md`. |
| NUM-01 | FIXED | DC checks are relative to the circuit's own current, voltage and power scales. |
| INF-01 | PARTIAL / DEFERRED | Held-out validation and prediction refuse conditions outside the model's validity domain (study layer). Applicability fields on `CalibrationResult` / `QuantifiedPredictiveResult` are deferred. |
| INF-02 | FIXED | Held-out scoring uses each observation's declared sigma; a differing override is refused. |
| INF-03 | PARTIAL / DEFERRED | The study layer re-derives the posterior's log-likelihood from the calibration half (content binding); the frozen `require_posterior_was_fitted_here` still compares labels. |
| CAP-01 | FIXED | CSTR liquid-phase conditions require a declared boiling/freezing range; the textbook liquid declares one. K2 C3 and K3 H1 genuinely boil and stay refused; K2–K4 records carry supersession notes. |
| CERT-01 | FIXED | `src/engcore/uq/**` is certified (`predictive_representation`). |
| CERT-02 | FIXED | RIDGE-1..8 and HD-1..10 are in the certified population (GUARD 35). |
| CERT-05 | FIXED | The SRIA evidence-to-belief chain is certified (`assurance_admission`) and mutated (GUARD 29); every new invariant has a mutation. |

## P2 — defense in depth

| ID | Status | Note |
|---|---|---|
| SRIA-05 | FIXED | One evidence id names one record; history keeps every write; invalidated/superseded records are not re-admitted. |
| SRIA-06 | FIXED | Obligation state is derived from Arbiter decisions; stop review no longer accepts a caller mapping. |
| SER-01 | FIXED | Resumed state is re-derived from the event log; legacy migration is opt-in; digests documented as integrity-only. |
| RES-05 | FIXED | `convergence` and `validation` are required keys. |
| RES-06 | FIXED | An OK evaluation requires a usable, in-domain result and matching objective values. |
| RES-07 | FIXED | A trusted execution record's parts must describe one execution; non-converged output is never trusted. |
| INF-05 | FIXED | Coverage is CALIBRATED only when the Wilson interval is contained in the band; zero intervals refused. |
| INF-06 | FIXED | Content digests are unit-canonical and ulp-tolerant; shared condition ids across halves refused. |
| INF-07 | PARTIAL | Held-out dataset id equal to the posterior's is refused; content binding deferred with INF-03. |
| INF-08 | PARTIAL / DEFERRED | TCR tables refuse out-of-bounds rows; generic tables need the parameter set (deferred). |
| INF-09 | FIXED | OCV adequacy takes a typed `ValidityAssessment`. |
| HUQ-11 | PARTIAL | Predictive nonlinearity is judged against parameter sd; a separate parameter-interval claim is deferred. |
| HUQ-12 | FIXED | Finite means, closed `grid_summary`, interval consistency, estimate↔inference-point consistency on read. |
| NUM-02 | FIXED | ngspice admission floor is a voltage converted through the declared resistance. |
| IND-05 | FIXED | Consensus reads compare identities with the pin before importing anything. |
| CAP-02 | FIXED | A declared battery pulse is screened (polarization at pulse duration, terminal voltage and cutoff at pulse current). The battery benchmark record was re-scored honestly (389→219 exact match; answer key unchanged), see `benchmarks/hard/BATTERY_PULSE_RESCORE.md`. |
| CAP-03 | PARTIAL | Resistance variation over the transient is bounded when element data is declared; element-less cases are stated as quasi-static. |
| CAP-04 | FIXED | `consumed_by_verdict` is truthful (schema `mcp_asserted_context/2`). |
| CAP-05 | FIXED | The flagship example is the cited part; a declared Debye temperature is recorded as an explicit elemental-metal assertion, and a declared non-elemental class disables the Debye conditions. |
| CERT-03 | FIXED | Every file a certified mutation names is a recertification trigger. |
| CERT-04 | FIXED | The trust runner has a control run and attributes each kill to a named test. |
| CERT-06 | FIXED | `api_snapshot.py` and package `__init__` files are in the control plane. |

## P3

| ID | Status | Note |
|---|---|---|
| INF-10 | FIXED | Identifiability thresholds cannot be loosened. |
| INF-11 | FIXED | Omitted coverage/censoring caps the cost-model verdict at DEGRADED. |
| HUQ-13 | FIXED | Nested record mappings frozen. |
| HUQ-14 | FIXED | `why` is in the digest and must follow from the numbers. |
| IND-06 | FIXED | CSTR cross-method text reports agreement truthfully. |
| NUM-03 | PARTIAL | Declared per-quantity absolute floors; the DC floor of 1e-15 is not scale-free. |
| NUM-04 | PARTIAL | Offset-scale parameter units refused; bare grids carry no units. |
| RES-08 | FIXED | Stored status and attained levels must match the checks (and MCP verdict qualifiers). |
| CERT-07 | FIXED | Functional gates have a declared skip ceiling. |
| CERT-08 | FIXED | An import-time kill must be an engcore refusal. |
| CERT-09 | FIXED | Stale suite/mutant counts corrected; harness helpers covered by triggers. |
| CAP-06 | PARTIAL | Stale tool text corrected; refused-run attribution fixed; lumped C vs ρ·c·V and first-sweep criterion text remain stated limitations. |

## Consequences worth knowing

- **Core Freeze V3.** The V2 serialization contract is superseded (its identity references contradict their own
  numbers). V1 and the frozen API surface are unchanged. See `certification/core_freeze_v3.json`.
- **Cost.** The local-Gaussian validity check now costs 4p+1+2p² forward evaluations and the default 6-start
  multistart downgrades routes with p ≥ 3; at p = 41 diagnostics take ~105 s (was ~4 s).
- **Evidence regenerated / superseded.** Core V2 `TCR`, `FAILURE_CASES`, `PERFORMANCE`, `WHEEL_V2` were regenerated;
  `BATTERY_T41` and `KINETICS_K2` carry `.SUPERSEDED` markers (bytes untouched).
- **Benchmarks.** Hard benchmark (electrothermal) unchanged. Battery record re-scored lower under the pulse rule;
  generator correction deferred to a new benchmark version. No hold-out case's truth was changed.
- **Stored state.** SRIA checkpoints written before these fixes are refused on resume; stored results with
  silent provenance load marked and unattributed.
- **Residual trust-root assumption.** Within one Python process, whoever constructs the admission authority chooses
  what it trusts (an architectural boundary, not security isolation, as the modules state).
