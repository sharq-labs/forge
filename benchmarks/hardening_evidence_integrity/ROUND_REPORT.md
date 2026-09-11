# Evidence Integrity & Route Independence Hardening — Sprint 3

Base `3a4f063` (Sprint 2 closed) · code head `65a64bb` · branch `claude/evidence-integrity-hardening-sprint-3` · 2026-09-12

## 1. FINAL RESULT

**EVIDENCE INTEGRITY & ROUTE INDEPENDENCE HARDENING COMPLETE**

| Acceptance condition | Verdict | Where |
|---|---|---|
| different evidence cannot be compared as if identical | **HOLDS** | §5 · `c0acdf6` |
| canonical evidence identity is enforced | **HOLDS** | §5 |
| observation labels alone cannot authenticate evidence | **HOLDS** | §2, §5 |
| different route names cannot manufacture independence | **HOLDS** | §6 · `3fe9711` |
| same implementation under aliases is recognised as shared | **HOLDS** | §6 canonical identity |
| shared backend/method/model construction is represented honestly | **HOLDS** | §7 |
| strongest validation level requires the documented independence strength | **HOLDS** | §7 promotion rule |
| serialized identity tampering fails closed | **HOLDS** | §8 |
| all valid EI/RI mutations killed | **HOLDS** — 21/21 valid killed, 1 invalid | §9 |
| valid pre-existing comparisons remain equivalent | **HOLDS** — 15/15 cases | §10 |
| FAST green | **HOLDS** — 4175 passed, 3 skipped | §12 |
| FULL green | **HOLDS** — 4717 passed, 3 skipped, 0 failed | §12 |
| wheel green | **HOLDS** — EVIDENCE AND INDEPENDENCE SMOKE OK · 383 passed | §12 |
| no material performance regression | **HOLDS** — microseconds against a 275 µs DC solve | §11 |
| existing certified mutation harness | **HOLDS** — CONTROL GREEN, 79/79 killed, exit 0 | §9 |

Two P1 gaps are closed. A model comparison now proves both models were scored
against the same canonical evidence, and route independence is derived from
canonical implementation identity that the domain layer pins and the core
verifies, rather than from names a caller supplies.

## 2. REPRODUCED EVIDENCE BYPASSES

`compare_log_predictive_scores` checked that the paired assessments named the
same observation keys in the same order, that both sides were the same length,
and that each carried its model reference. Nothing about the evidence.

Reproduced at `3a4f063` (probe, then committed as strict xfails in `e8043c7`):

| Pair, identical in key / count / model structure | Before |
|---|---|
| same key, observed **30 K** against **12 K** | compared — **delta +31.79, model a preferred** |
| same values, different posterior dataset id | compared, delta 0.0 |
| same values, different held-out partition | compared, delta 0.0 |
| same values, different twin | compared, delta 0.0 |
| same values, likelihood sigma **9 K** against **2 K** | compared — **delta +1.03, model a preferred** |
| one observation listed twice on both sides | compared, counted twice |
| a duck-typed object carrying `log_predictive_density = 100.0` | compared |

Two of those manufacture a model preference out of an evidence difference. And
two identity facts were not recorded at all: the **likelihood sigma**, which
sets the log density, and the **held-out partition**, which in K4 existed only
as text inside `source_ref`. The assessment had no `from_dict`, so nothing
revalidated a serialized one.

## 3. REPRODUCED FALSE-INDEPENDENCE CASES

Values agree exactly in every case, so any level awarded rests entirely on the
independence verdict. Observed at `3a4f063`, before any fix; committed as strict
xfails in `e610c4e`, where they were red against `c0acdf6`:

| Case | Before |
|---|---|
| one solver identity, two route names, two component labels | INDEPENDENT · **CROSS_SOLVER_VALIDATED** |
| one function spelled `numpy.linalg:solve` and `numpy.linalg.solve` | INDEPENDENT · **CROSS_SOLVER_VALIDATED** |
| one numerical backend behind two wrapper identities | INDEPENDENT · **CROSS_SOLVER_VALIDATED** |
| different implementations, same problem declaration (the DC pair) | INDEPENDENT — no distinction from full independence |
| different numerics, shared model construction left undeclared | INDEPENDENT · **CROSS_SOLVER_VALIDATED** |
| **production `dc_consensus`**: one native result and one solver identity handed to both routes | INDEPENDENT · **CROSS_SOLVER_VALIDATED**, PASS check that `earns_its_level` |
| **production `dc_consensus`**: a native result presented under the external simulator's identity | accepted |
| a serialized record claiming the level for routes named apart | read back with its level |

## 4. ROOT CAUSES

**Evidence.** The comparison verified *labels about* the evidence — the
observation key, the count, the model reference — and the assessment did not
carry the material facts (observed value in its unit, likelihood sigma,
partition, posterior dataset, twin) in any form a comparison could check. A
shared key is a name; evidence is what was observed and what likelihood it was
read under.

**Independence.** `SharedComponent(kind, name)` was supplied by whoever built
the route, and the intersection of two caller-written label sets was the whole
of "not independent". Two routes could name one implementation differently, or
one route could be named twice, and the record could not tell. The module
reported repeated solver identities but explicitly did not judge them, so the
only signal that *could* have caught the production case was declared
non-binding.

## 5. CANONICAL EVIDENCE IDENTITY

`PredictiveEvidenceIdentity`, built by `assess_predictive_observation` from the
inputs the score was computed from, never supplied beside them:

| Field | Why it is identity |
|---|---|
| `observation_key` | which observable |
| `observed_value` + `unit` | the number the density was computed from, in the observable's declared unit |
| `likelihood_sigma` | the noise the likelihood used; it changes the density |
| `heldout_dataset_id` | which held-out partition the observation belongs to |
| `posterior_dataset_id` | the data the model was conditioned on |
| `twin` | the system all of it describes |

- One field list (`EVIDENCE_IDENTITY_FIELDS`) is read by the digest **and** by
  the pairing check, so neither can consult a field the other ignores.
- `digest` is SHA-256 over the canonical form, recomputed on every read.
- The assessment **checks itself against its identity** at construction: key,
  observed value in the identity's unit, posterior dataset, twin, and a sigma
  that cannot exceed the total predictive uncertainty the record reports. A
  direct constructor and `from_dict` both go through it (Part C).
- `compare_log_predictive_scores` refuses untyped items, a repeated
  observation, and any pair whose identities differ — naming the fields that
  differ — and records `evidence_digest` over the ordered identities it
  compared.

**Deliberately outside the identity**, with the reason:

| Field | Why not |
|---|---|
| `source_ref` | per-model provenance: K4 writes a different one for each model over one held-out set, so an identity including it would refuse every comparison K4 makes |
| `confidence_level` | sets the interval the coverage flag is read against; the log score does not read it |

## 6. ROUTE / COMPONENT IDENTITY MODEL

```
SolveRoute
  ├─ components      the author's description. Reported. Decides nothing.
  └─ dependencies    RouteDependencies: per dimension, canonical identities
                        py:<module>:<qualname>  resolved to the object it names
                        ext:<name>              outside the interpreter, normalised
engcore.domains.SCIENTIFIC_ROUTE_DECLARATIONS
  route_id -> { solver_id, [backend], dependency_digest }     ← the authority
```

At construction the core decides, per route, and reads only the pin:

1. the route must declare dependencies at all;
2. its route id must be one the domain layer declares;
3. the solver that ran must be the implementation the declaration is for (and
   the backend, where the pin binds one);
4. the dependencies must resolve, and hash to the pinned digest.

`py:` identities are resolved to the defining module and qualified name, so
`engcore.domains.electrical.dc:ElectricalDCSolver` and
`engcore.domains.electrical.dc.solver:ElectricalDCSolver` are one identity, and
an alias cannot become a second implementation. This is the rule threshold
authority already follows: the data travels with the record, and the core
checks it against a pin the caller does not hold.

**Declared in this round** (digests pinned in `engcore.domains`):

| Route | Implementation | Preprocessing | Numerical method | Backend |
|---|---|---|---|---|
| `electrical.dc.native_mna` | `ElectricalDCSolver` | `dc.mna:assemble` | `ext:lapack:gesv` | `scipy.linalg:solve` |
| `electrical.dc.external_simulator` | `NgspiceDCSolver` | `ngspice:build_netlist`, `ext:ngspice:internal_assembly` | `ext:ngspice:sparse_lu` | `ext:ngspice` |
| `kinetics.cstr.integration:BDF` | `CSTRSolver` | `cstr.solver:assemble` | `scipy.integrate:BDF` | `scipy.integrate:solve_ivp` |
| `kinetics.cstr.integration:Radau` | `CSTRSolver` | `cstr.solver:assemble` | `scipy.integrate:Radau` | `scipy.integrate:solve_ivp` |

Both DC routes declare one problem declaration, `DCCircuit`. The two CSTR
routes differ in the numerical method and in nothing else, which is what the
domain's prose already said and what the record now states.

The CSTR entries pin no backend: that solver names its backend with the library
version it ran against (`solve_ivp/scipy-1.18.1`), which is execution
provenance — pinning it would pin one environment.

**Provenance, at the domain entry point.** The core attributes numbers to
routes as the caller hands them over. `dc_consensus` now checks each result's
provenance against the identity it is presented under, which is what refuses a
native result offered as the external route.

## 7. INDEPENDENCE DIMENSIONS

| Dimension | Required for CROSS_SOLVER_VALIDATED |
|---|---|
| `problem_declaration` | no — two solvers asked one question share the question |
| `preprocessing` | **yes** |
| `numerical_method` | **yes** |
| `implementation` | **yes** |
| `backend` | **yes** |

| Verdict | Meaning |
|---|---|
| `FULLY_INDEPENDENT` | nothing shared in any dimension |
| `PARTIALLY_INDEPENDENT` | something shared, but not the implementation |
| `NOT_INDEPENDENT` | the implementation is shared |
| `UNVERIFIED` | a route's declaration is not the one the domain layer pins |
| `UNDECLARED` | a route declares no dependencies |
| `TOO_FEW_ROUTES` | fewer than two routes |

The level is awarded only when the verdict is FULLY or PARTIALLY **and**
nothing shared lies in the four required dimensions. So:

- the two DC routes are **partially independent** — they share the circuit —
  and earn the level, as they did before;
- the two CSTR integration routes are **not independent** — one right-hand
  side, one Jacobian, one library routine — and earn nothing, as before, while
  the record now also states that their numerical methods *are* independent;
- two implementations over one backend are partial and earn **nothing**.

## 8. BEFORE / AFTER BEHAVIOR

| Case | Before | After |
|---|---|---|
| same key, different observed value | compared, preference +31.79 | **refused**, naming `observed_value` |
| different likelihood sigma | compared, preference +1.03 | **refused**, naming `likelihood_sigma` |
| different partition / dataset / twin | compared | **refused**, naming the field |
| one observation twice | counted twice | **refused** |
| duck-typed assessment | scored | **refused** |
| serialized assessment, field edited | no reader existed | **refused** (identity digest, then coherence) |
| one solver identity under two route names | CROSS_SOLVER_VALIDATED | **UNDECLARED / UNVERIFIED**, no level |
| one function under two spellings | CROSS_SOLVER_VALIDATED | **NOT_INDEPENDENT**, one canonical identity |
| one backend, two wrappers | CROSS_SOLVER_VALIDATED | **PARTIALLY_INDEPENDENT**, no level |
| `dc_consensus` with one result and one solver twice | CROSS_SOLVER_VALIDATED | **UNVERIFIED**, no level |
| a native result under the external identity | accepted | **refused** on provenance |
| serialized record claiming a level its routes deny | accepted | **refused** |
| the two declared DC routes on a real circuit | CROSS_SOLVER_VALIDATED | **CROSS_SOLVER_VALIDATED**, partial independence |
| the CSTR cross-method arm | agrees, no level | agrees, no level |

## 9. MUTATION RESULTS

Planted by the targeted apply-and-revert script (`tests/mutation_guards.py` is
byte-pinned), each restored and verified by digest, control green first.

| Id | Spec | Planted defect | Result |
|---|---|---|---|
| EI1 | EI-1 | the pairing check stops comparing the observed value | **killed** |
| EI1b | EI-1 | an assessment whose observed value differs from its identity is accepted | **killed** |
| EI2 | EI-2 | the pairing check ignores the posterior dataset | **killed** |
| EI3 | EI-3 | the pairing check ignores the held-out partition | **killed** |
| EI4 | EI-4 | a comparison trusts matching observation keys alone | **killed** |
| EI5 | EI-5 | the pairing check ignores the likelihood's noise | **killed** |
| EI6 | — | a serialized identity is read without verifying its digest | **killed** |
| EI7 | — | a duck-typed object is scored as an assessment | **killed** |
| EI8 | — | one observation is counted twice in both scores | **killed** |
| EI9 | — | the pairing check ignores the twin | **killed** |
| RI1 | RI-1 | independence read from declared spellings, not canonical identity | **killed** |
| RI2 | RI-2 | two routes on one implementation are not called not-independent | **killed** |
| RI2b | RI-2 | the level stops requiring implementation independence | **INVALID — equivalent** |
| RI3 | RI-3 | the level stops requiring backend independence | **killed** |
| RI4 | RI-4 | the level stops requiring independent problem construction | **killed** |
| RI4b | RI-4 | routes sharing the problem declaration read as fully independent | **killed** |
| RI5 | RI-5 | a declaration missing a dimension is accepted | **killed** |
| RI5b | RI-5 | a route declaring no dependencies stops being reported undeclared | **killed** |
| RI6 | RI-6 | a serialized independence verdict is trusted without recomputation | **killed** |
| RI7 | — | a route accepted under another implementation's declaration | **killed** |
| RI8 | — | a declaration edited after it was pinned is accepted | **killed** |
| RI9 | — | a result accepted under another solver's route identity | **killed** |

**EI: CONTROL GREEN, 10/10 killed. RI: CONTROL GREEN, 11/11 valid killed.**

**RI2b is equivalent, and was proven so rather than assumed.** Removing
`IMPLEMENTATION` from `SOLVER_INDEPENDENCE_DIMENSIONS` changes nothing, because
a shared implementation already makes the verdict `NOT_INDEPENDENT` and
`routes_are_independent` refuses any verdict that is not FULLY or PARTIALLY.
Run with the mutation applied in memory, a shared-implementation consensus
reports `not_independent`, `routes_are_independent=False`, `establishes=None` —
identical to the unmutated record. The protection is doubled; the tuple entry
is unreachable on its own.

**RI7 was a real test gap and was closed.** It survived the first run because
both tests that exercised a route bound to another implementation *also*
carried a mismatched backend, so the backend check fired first. The guards now
isolate each binding — same backend and a different solver id, same solver id
and a different backend — and the mutation dies (`75d40a9`).

**Existing certified harness.** `tests/mutation_guards.py` was run unmodified against `65a64bb` — it is byte-pinned by `certification/current_core_v1.json`, and this round changed three files inside its scope (`scientific/consensus.py`, `domains/kinetics/cstr/validation.py`, `domains/electrical/dc_consensus.py`). Result: **CONTROL GREEN; 79/79 mutations were killed by the guard they name**, exit 0. The two guards anchored in a file this round edited went RED as they must — G2c (the repaired CSTR check loses its evidence) and G3b (a gate takes a bare float threshold again) — as did G3a, G4a and G9c beside them. No anchor text was disturbed.

## 10. OUTPUT EQUIVALENCE

15 cases, recorded on the unchanged tree at `3a4f063` and again at `3fe9711` --
the last commit of this round that changes runtime behaviour, the two after it
being test-only. Five model
comparisons over three models, every assessment behind them, the model ranking,
the DC consensus on a real circuit (with ngspice) and its check, its
deserialized level, the CSTR cross-method consensus, and the kinetics gate's
levels and checks.

| Preserved, value for value | Result |
|---|---|
| every score, delta and preferred model | **EQUAL** |
| the model ranking | **EQUAL** |
| the DC consensus check: outcome, establishes, residual, tolerance | **EQUAL** |
| the DC record's level after a serialization round trip | **EQUAL** |
| the kinetics gate's attained levels and every check | **EQUAL** |

Changed, and only this:

- **additive fields**: `evidence` and `schema` on every assessment,
  `evidence_digest` on every comparison, `dependencies` on every route, and
  `shared_dependencies` / `unverified_routes` / `independent_dimensions` on
  every consensus;
- **two derived verdict strings**: the DC consensus reads
  `independent` → `partially_independent`, the CSTR arm
  `shares_components` → `not_independent`, with the `reason` sentences that go
  with them. No level moved.

## 11. PERFORMANCE

Sequential, single process, median of 7 repeats, per call; two runs of each
tree. Before is `3a4f063`, after is `75d40a9`.

| Measurement | before r1 | before r2 | after r1 | after r2 |
|---|---:|---:|---:|---:|
| assess one held-out observation (50-point posterior) | 925.31 µs | 801.14 µs | 992.97 µs | 1012.88 µs |
| `compare_log_predictive_scores` (20 paired assessments) | 8.32 µs | 8.34 µs | 197.40 µs | 204.72 µs |
| consensus `over` (DC routes, 13 outputs) | 70.27 µs | 75.38 µs | 115.34 µs | 127.79 µs |
| consensus independence verdict | 2.44 µs | 2.62 µs | 9.52 µs | 11.15 µs |
| consensus `establishes` (promotion) | 9.00 µs | 9.75 µs | 30.83 µs | 30.95 µs |
| consensus `to_check` | 36.54 µs | 39.22 µs | 146.35 µs | 148.58 µs |
| consensus `from_dict` (revalidated) | 101.10 µs | 104.37 µs | 247.74 µs | 240.22 µs |

Stated plainly: the comparison of 20 paired assessments costs about **+190 µs**,
almost all of it the per-observation SHA-256 behind the recorded
`evidence_digest`; verifying a consensus costs about **+50 µs** at construction
and **+20 µs** per promotion.

Against what these sit beside — a DC solve is ~275 µs, a CSTR solve ~21 ms, and
`solve_circuit` end to end ~1.4 ms — the verification is not material to
scientific runtime. K4's whole run makes 21 comparisons: about 4 ms in total.
Nothing was optimized.

## 12. FAST / FULL / WHEEL

| Run | Tree | Result |
|---|---|---|
| evidence + adequacy + K4 configuration | `c0acdf6` | 53 passed |
| consensus suites (7 modules, expensive included) | `3fe9711` | 244 passed |
| **FAST** | `75d40a9` | **4175 passed, 3 skipped** |
| **FULL** | `65a64bb` | **4717 passed, 3 skipped, 0 failed** |
| **installed wheel** | wheel of `75d40a9` | **EVIDENCE AND INDEPENDENCE SMOKE OK · 383 passed** |

| Guard group | Files | Result at `75d40a9` |
|---|---|---|
| Contract Guard | `test_core_guards.py`, `test_design_d0_contracts.py`, `test_data_boundary0.py` | 305 passed |
| Capability Boundary | the six domain applicability suites (battery, DC, DC rating, material, CSTR, lumped), `mcp/test_battery_boundary.py` | 293 passed |
| Scientific Truth | `domains/test_evidentiary_level_audit.py`, `kinetics/test_k2_truth_admissibility.py`, both oracle truth suites, `test_result_validity.py`, `test_blind_challenge_guards.py` | 294 passed, 3 skipped |

The repository does not name suites this way; the grouping is by what each file guards, and every one of them also runs inside FULL.

**Wheel details.** Built from `git archive 75d40a9`, installed with `--target` on `D:` and run under `python -I -S` with no checkout on the path: 194 entries, 0 under `src/`, `engcore/py.typed` ships, and `import src` / `import src.engcore` both raise `ModuleNotFoundError`. The one commit after it, `65a64bb`, changes a test assertion only, so the wheel's contents are unaffected. Against the installed package the smoke compares one body of evidence, refuses a different observed value, a different held-out partition, a different likelihood sigma and a tampered serialized assessment, round trips an assessment with its identity, earns the level on the two declared DC routes, refuses one solver presented on both routes, resolves an alias to one canonical identity, checks the shipped declaration against the shipped pin, and refuses a declaration edited away from it.

**No frozen artifact changed.** Nothing under `experiments/` except
`kinetics_k4/k4_run.py` — which no freeze pins — and nothing under
`src/engcore/domains/thermal/`, `benchmarks/blind/`, `certification/`, nor
`tests/mutation_guards.py` or either pinned test module. The K4 experiment was
not re-run: its scores are unchanged (§10), and its serialized assessments gain
the evidence identity that made them comparable.

## 13. PUBLIC API CHANGES

| API | OLD | NEW | MIGRATION |
|---|---|---|---|
| `assess_predictive_observation` | — | requires `heldout_dataset_id` | pass the held-out set's `dataset_id` |
| `PredictiveObservationAssessment` | 14 fields, `to_dict` only | + `evidence`, a versioned `schema`, and `from_dict` | build it through `assess_predictive_observation` |
| `PredictiveEvidenceIdentity` | — | new, with `digest`, `differences`, `to_dict`/`from_dict` | additive |
| `compare_log_predictive_scores` | keys + model refs | + typed items, no repeats, identical evidence | pair assessments of one body of evidence |
| `ModelScoreComparison` | 6 fields | + `evidence_digest` | additive; readers of the payload gain a key |
| `SolveRoute` | `route_id`, `solver`, `components`, `notes` | + `dependencies` | declare them, and pin the declaration |
| `SolveRoute.declares_nothing` | no components | no dependencies | — |
| `IndependenceVerdict` | `INDEPENDENT`, `SHARES_COMPONENTS`, `UNDECLARED`, `TOO_FEW_ROUTES` | `FULLY_INDEPENDENT`, `PARTIALLY_INDEPENDENT`, `NOT_INDEPENDENT`, `UNVERIFIED`, `UNDECLARED`, `TOO_FEW_ROUTES` | read the new members; the serialized value changes with them |
| `CrossSolverConsensus` | `shared_components`, `shared_solver_identities` | + `shared_dependencies`, `shared_dimensions`, `unverified_routes`; three new payload keys | additive; `shared_components` still reports |
| `routes_are_independent` | verdict is INDEPENDENT | independent in the four required dimensions | — |
| `RouteDependencies`, `IndependenceDimension`, `SOLVER_INDEPENDENCE_DIMENSIONS`, `canonical_component_identity`, `ROUTE_DECLARATIONS_ATTRIBUTE` | — | new | additive |
| `dc_consensus` | took results and identities | refuses a result whose provenance does not name the identity it is presented under | pass the identity that produced each result |
| `engcore.domains` | threshold declarations | + `SCIENTIFIC_ROUTE_DECLARATIONS` | a new route declares itself here |

No solver constructor, `prepare`/`bind`/`solve`, `PreparedSolve`, threshold or
validation-report API changed.

## 14. FILES CHANGED

| File | Change |
|---|---|
| `src/engcore/adequacy/predictive.py` | canonical evidence identity, self-checking assessment, refusing comparison |
| `src/engcore/adequacy/__init__.py` | exports |
| `src/engcore/scientific/consensus.py` | dimensions, canonical identities, verified dependencies, new verdicts |
| `src/engcore/domains/__init__.py` | `SCIENTIFIC_ROUTE_DECLARATIONS` |
| `src/engcore/domains/electrical/dc_consensus.py` | both route declarations, provenance check |
| `src/engcore/domains/kinetics/cstr/validation.py` | both integration route declarations |
| `experiments/kinetics_k4/k4_run.py` | passes the held-out partition |
| `tests/test_evidence_pairing_integrity.py` | new — Part A matrix |
| `tests/test_route_independence_authority.py` | new — Part B matrix |
| `tests/route_declarations_for_tests.py` | new — routes a test declares and pins |
| `tests/test_k4_model_adequacy.py` | passes the held-out partition |
| `tests/mcp/test_problem.py` | reads the independence argument from the check's new sentence |
| `tests/test_cross_solver_consensus.py`, `tests/test_consensus_integrity.py`, `tests/test_trust_boundary_consensus.py`, `tests/test_trust_boundary_threshold_authority.py`, `tests/test_core_numerical_integrity.py`, `tests/test_core_invariants_adversarial.py` | declare and pin their routes; verdicts migrated |
| `benchmarks/hardening_evidence_integrity/ROUND_REPORT.md` | new — this report |

## 15. COMMITS

| Commit | Message |
|---|---|
| `e8043c7` | test(evidence): reproduce mismatched-evidence comparisons |
| `c0acdf6` | fix(evidence): enforce canonical comparison identity |
| `e610c4e` | test(consensus): reproduce false route independence |
| `3fe9711` | fix(consensus): verify canonical route independence |
| `75d40a9` | test(core): add evidence and independence mutation guards |
| `65a64bb` | test(mcp): read the independence argument from its new sentence |
| `this commit` | docs(core): close evidence integrity hardening sprint |

## 16. PUSH RESULT

Pushed to `origin` (`github.com:sharq-labs/forge`) as the **new branch `claude/evidence-integrity-hardening-sprint-3`**, upstream tracking set. `git ls-remote` shows the remote head at `65a64bb`, which carries every code and test commit in §15. This report commit follows on the same branch as a fast-forward. `main` was not touched, Sprint 2's branch was not touched, and nothing was force-pushed.

## 17. DEFERRED ITEMS

- **Score integrity is not claimed.** The pairing check proves two assessments
  describe one body of evidence; it cannot prove a record's
  `log_predictive_density` is the number that evidence produces. A record
  forged coherently states its own evidence honestly and its score falsely, and
  a test says so out loud.
- **Training-data identity is a label.** `posterior_dataset_id` names the data a
  model was conditioned on; there is no digest of the training set, so two
  different fits under one dataset id are not distinguishable here.
- **Unit identity is strict.** Evidence is compared in the observable's declared
  unit. The same physical observation declared in another unit is different
  evidence and is refused rather than converted — fail closed, and worth
  revisiting if a study ever needs it.
- **`ext:` identities are registry-owned strings.** They name what lives outside
  the interpreter and cannot be resolved, so two `ext:` spellings of one
  external program are not detectable as one identity.
- **A pin attests integrity, not truth.** A declaration that calls two routes
  disjoint when they are not is wrong in the pin, where a reviewer can read it;
  nothing here can check a declaration against the world.
- **Attribution is checked at one entry point.** `dc_consensus` verifies each
  result's provenance; the CSTR gate builds both of its routes itself, and the
  core still takes `values` as handed over.
- **K4 payload shape changed.** Serialized assessments and comparisons gain
  `evidence`, `schema` and `evidence_digest`. No stored K4 artifact exists in
  this repository, and the scores are unchanged.
- **The EI/RI mutations live in the targeted script**, not in the byte-pinned
  `tests/mutation_guards.py`. Joining them is a certification round, as it is
  for Sprint 1's and Sprint 2's targeted sets.
- **`certification/current_core_v1.json` is further stale.** It pins
  `core.path = src/engcore/scientific` by *tree* digest, and this round changes
  `scientific/consensus.py`, so that digest no longer describes the tree. It has
  been stale since Sprint 1 for the same reason and re-certification is its own
  round. `adequacy/predictive.py` sits outside that path and was never covered by
  it. What the snapshot pins about the harness -- `mutation.runner`,
  `tests/mutation_guards.py`, and its log digest -- is unchanged, which is what
  keeps this round's harness result comparable with Sprint 2's.
- **A documented stance was refined, not reversed.**
  `shared_solver_identities` still reports a repeated identity string without
  judging it — two methods of one program can be separate arithmetic. What is
  judged now is the *pinned implementation identity*, which is what the
  production case needed.
