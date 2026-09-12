# Core Trust Boundary Closure — Hardening Sprint 1

Base `b5cedff` · code head `f8cfd9a` · 2026-09-11

## 1. FINAL RESULT

**TRUST BOUNDARY HARDENING COMPLETE**

| Acceptance condition | Verdict | Where |
|---|---|---|
| one canonical package identity | **HOLDS** | §4 · `018835b` |
| `AdmittedForwardRow` bypass closed | **HOLDS** | §2 TB-2 · `a572baa` |
| consensus completeness bypass closed | **HOLDS** | §2 TB-3 · `3d642dc`, `93992d6` |
| consensus numeric agreement forgery closed | **HOLDS** | §2 TB-3 · `57bacd9` |
| threshold authority impersonation closed | **HOLDS** | §3 · `f8cfd9a` |
| direct constructor cannot self-certify | **HOLDS** | §5 F |
| trust promotion independently verifies authority | **HOLDS** | §4 authority model |
| serialized tampering fails closed | **HOLDS** | §5 H–J |
| all valid targeted mutations killed | **HOLDS** — 36/36, 0 survivors, 0 invalid | §6 |
| FAST green | **HOLDS** — 4049 passed, 3 skipped | §9 |
| FULL green | **HOLDS** — 4590 passed, 3 skipped, 0 failed | §9 |
| installed wheel green | **HOLDS** — 355 passed against the installed wheel | §9 |
| no material performance regression | **HOLDS** — about 6 µs per promotion | §10 |

Every closure holds against every supported construction path: the
constructor, `from_dict`, `dataclasses.replace` / `copy.replace`, subclassing,
and duck-typed consumers. Deliberate circumvention through `object.__setattr__`,
a crafted pickle or rebinding a module attribute is outside that boundary for
every record in this repository (§14).

## 2. PREVIOUS MUTATION HARNESS RESULT

`tests/mutation_guards.py` was run unmodified; it is byte-pinned by
`certification/current_core_v1.json`.

| Tree | Result |
|---|---|
| `93992d6` | **CONTROL GREEN; 79/79 mutations were killed by the guard they name**, exit 0 |
| `57bacd9` (the code before this step) | **CONTROL GREEN; 79/79 mutations were killed by the guard they name**, exit 0 |
| `f8cfd9a` (this step touches `thresholds.py`, the file G3a mutates) | **CONTROL GREEN; 79/79 mutations were killed by the guard they name**, exit 0 |

## 3. THRESHOLD IMPERSONATION (TB4-c — closed)

**Reproduction** (red probe at `57bacd9`, 3/3 failed):

1. A legitimate gate exists: `DC_CONSENSUS_THRESHOLDS`, `electrical.dc.cross_solver@0.1.0`, `{"agreement_rel_tol": 1e-9}`.
2. Its identity is public: `.gate_id`, `.version`, `.identity`.
3. A caller builds `VerificationThresholds(gate_id="electrical.dc.cross_solver", version="0.1.0", values={"agreement_rel_tol": 0.5})`.
4. That is one material value, changed by eight orders of magnitude.
5. It is passed through `CrossSolverConsensus.over(...)` for routes whose numbers are 1.0 and 1.3.
6. `establishes` was `CROSS_SOLVER_VALIDATED`. With the canonical set it is `None`.

The same held on the frozen conduction report, where a set under `thermal.conduction1d.refinement` with loosened values earned `NUMERICALLY_CONVERGED` and `ANALYTICALLY_VERIFIED`, and for `dataclasses.replace(DC_CONSENSUS_THRESHOLDS, values=...)`.

**Root cause.** `VerificationThresholds.is_declared` was `not self.derived_from`. `derived_from` is an ordinary constructor argument that only `derive()` sets, so "declared" meant "did not say it was an override". The name was treated as the authority, and the name is public.

**Unsafe example.**
```python
forged = VerificationThresholds(gate_id=D.gate_id, version=D.version, values={"agreement_rel_tol": 0.5})
CrossSolverConsensus.over(..., thresholds=forged, tolerance_key="agreement_rel_tol").establishes
# before: ValidationLevel.CROSS_SOLVER_VALIDATED    after: None
```

**Fix (`f8cfd9a`).** Authority is verified by the core at promotion and is never data a caller supplies (§4). `award` keeps its exact text, because the certified G3a mutation anchors on it. What it consults, `is_declared`, is now the core's verification against the domain layer's pinned declarations.

## 4. AUTHORITY MODEL

| | Public threshold spec | Canonical declaration |
|---|---|---|
| what it is | numbers a gate is judged against | a domain gate's own numbers, pinned by the domain layer |
| who controls it | the caller | the engcore domain layer (`engcore.domains.SCIENTIFIC_THRESHOLD_DECLARATIONS`) |
| usable for comparisons | yes — every residual and detail reported | yes |
| grants a level | **no** | yes |

**Identity mechanism.**
- `SCIENTIFIC_THRESHOLD_DECLARATIONS` is an immutable `MappingProxyType` in `engcore/domains/__init__.py`. It maps each `gate_id` to `declared_by` (the constant), `version`, and `threshold_digest`, a full SHA-256 over the values serialized exactly as `VerificationThresholds.threshold_digest` does.
- Four gates are registered: `electrical.dc.cross_solver`, `electrical.dc.linear_residual`, `kinetics.cstr.verification_gate` and `thermal.conduction1d.refinement`. The last is declared in a T1-pinned module and is pinned from one package above the freeze, the repo's existing idiom.
- The existing 16-character `fingerprint` is the digest's prefix, so every evidence string is unchanged.
- The core knows only the attribute name (`THRESHOLD_DECLARATIONS_ATTRIBUTE`) and the package that carries it, never a gate.
- Changing a declared number now requires changing its pin, on purpose. A test checks every entry against the constant it names.

**Promotion verification** (`_verified_against_declaration`, a module function over the record's fields that no method can override). Every call:
1. fails a set that says it overrides another (`derived_from`);
2. fails an unregistered `gate_id`, because a name alone is not a declaration;
3. fails a `version` other than the registered one;
4. fails values whose digest, **recomputed now**, differs from the registered digest.

On top of that:
- `VerificationThresholds` cannot be subclassed, so nothing can answer `is_declared` or `award` for itself.
- `CrossSolverConsensus` already refuses thresholds that are not a `VerificationThresholds`.
- `from_dict` checks a serialized `fingerprint` against the values and refuses a mismatch.
- No serialized field is ever read as authority.

## 5. TEST MATRIX A–K

`tests/test_trust_boundary_threshold_authority.py` — 69 test cases, all green at `f8cfd9a`.

| | Case | Expected | Test(s) |
|---|---|---|---|
| A | real registered gate + canonical thresholds | PASS | `test_a_…` for all four gates (`is_declared`, `award`) |
| B | same gate identity + changed threshold | FAIL | `test_b_…` for all four gates, loosened and tightened; consensus compares but promotes nothing |
| C | real gate ID + changed threshold, any version | FAIL | `test_c_…` 4 gates × 4 versions |
| D | canonical values + fake/other gate ID | FAIL | `test_d_…` invented ids, case-changed id, another real gate's id |
| E | same gate + canonical values, missing/mismatched version; override marker | FAIL | `test_e_…` 4 gates × 4 versions; `derived_from` set on canonical numbers |
| F | direct constructor cannot self-certify | FAIL | no authority-asserting field (`declared`, `trusted`, `authoritative`, `threshold_digest` → `TypeError`); authoritative-sounding `basis`; `dataclasses.replace` / `copy.replace`; subclass refused; stand-in object refused; values altered after construction lose authority |
| G | official canonical declaration path | PASS | consensus over the DC declaration; unchanged `derive()` returns the declaration; DC settings; default conduction report; every registry entry equals the constant it names; registry immutable |
| H | valid serialization → deserialization | PASS after re-verification | all four gates round-trip; consensus round-trip keeps its level |
| I | serialized threshold value tampered | FAIL | fingerprint mismatch refused; a consistent fingerprint loads as a spec with no authority; consensus payload refused |
| J | serialized identity/version/digest tampered | FAIL | tampered fingerprint refused; version / gate id tampering loses authority; consensus payload claiming a level refused |
| K | ordinary non-authoritative spec | local checks, no promotion | a spec drives a PASSing comparison at its own tolerance, reports evidence, establishes nothing |

Plus the Step 1 reproduction, `test_an_impersonated_gate_earns_no_level_on_any_promotion_path`, which covers consensus, `to_check`, the report's attained levels, and the frozen conduction report.

## 6. TARGETED MUTATIONS

The same method as before: one tree copy on `D:`, each mutation applied, its trust-boundary test file run, the restore verified by digest, and an unmutated control for each file.

| | Count |
|---|---|
| total | **36** |
| killed | **36** |
| survivors | **0** |
| invalid | **0** |
| controls | **GREEN** (5 files) |

**Threshold authority (12 mutations, all VALID and killed):**
- TA-1 promotion stops consulting authority (the award check removed)
- TA-2 a registered gate name alone is trusted (version and digest checks removed)
- TA-3 the gate id is ignored, and any declaration with these numbers vouches
- TA-4 the threshold digest is ignored
- TA-5 the digest is remembered from declaration, so a threshold altered afterwards keeps authority
- TA-6 a missing or mismatched authority version is allowed
- TA-7 the caller or payload "declared" marker (empty `derived_from`) is trusted
- TA-8 the consensus promotion path bypasses threshold verification
- TA-9 a serialized fingerprint is no longer re-verified
- TA-10 a subclass may answer for its own authority
- TA-11 an unregistered gate is treated as declared
- TA-12 a set marked as an override is accepted as the declaration

**Earlier sprint invariants (24 mutations, all VALID and killed):** TB1a–b, TB2a–d, TB3a–m, TB5a, TB6a–c, TB7a.

**The stale mutant.** TB3c ("reports under undeclared routes are accepted") stopped matching when `57bacd9` rewrote the reporter check across three lines. It was classified **VALID_MUTANT**: the invariant still exists. It was re-anchored to the current code, without shrinking the denominator, and is **killed**.

## 7. SAME-CLASS BYPASSES

The search was limited to one pattern: a caller-controlled identifier treated as proof of authority. It covered the core, domains, inference, uq and MCP: domain gates, threshold sets, evidence sources, verification records and certification identities.

| Candidate | Verdict |
|---|---|
| `VerificationThresholds` identity (TB4-c) | REPRODUCED → **closed** (§3) |
| every identifier comparison in core/domains/systems/mcp (`gate_id`, `model_id`, `realization_id`, `solver_id`, `identity`, `key`, `fingerprint`) | NOT_REPRODUCED — lookups, de-duplication and selection; none grants a level, verdict or admission |
| `mcp/problem.py` `model.model_id == _RATED_TCR.model_id` | NOT_REPRODUCED — selects which repair guidance to collect; the assessment is still the domain's own model definition |
| `conduction1d_schemes.PreparedScheme.is_implicit` (realization key) | INTENTIONAL — scheme selection, no level |
| MCP evidence model index | NOT_REPRODUCED — authority comes from the core's walk of the package (`_declared_models`), not from the caller |
| frame-based constructing-module exemptions (`SCIENTIFIC_UNASSESSED_DECLARATIONS`) | NOT a promotion — a spoofed module name only lets a result record "not assessed", which is a weaker record |
| conduction/CSTR `VerificationReport` accepting any `thresholds` object and hand-set booleans | known evidence-model limit (TB4-x), no escalation: a hand-built report already earns levels through its booleans; the conduction module is T1-pinned |

No further trivially reproducible P0 bypass of this class was found, so the search stopped there.

## 8. PUBLIC API BREAKS

| Surface | Old behaviour | Why unsafe | New behaviour | Migration |
|---|---|---|---|---|
| `VerificationThresholds(gate_id=<real>, …)` with other numbers | awarded that gate's levels | name treated as authority | a threshold spec: compares, awards nothing | use the declared constant, or accept spec semantics |
| `VerificationThresholds(gate_id=<invented>, …)` | awarded levels | self-declared gate | awards nothing | register a real declaration in `engcore.domains.SCIENTIFIC_THRESHOLD_DECLARATIONS` (production code only); five test fixtures moved to real declarations |
| subclassing `VerificationThresholds` | allowed | could override `is_declared` / `award` | `TypeError` | none |
| `VerificationThresholds.from_dict` | ignored `fingerprint` | a tampered record loaded silently | refuses a fingerprint that disagrees with the values | write consistent payloads |
| changing a declared threshold constant | one edit | — | also update its registry digest, or the gate stops awarding (fail closed, and flagged by test) | edit both |
| new public names | — | — | `VerificationThresholds.threshold_digest`, `THRESHOLD_DECLARATIONS_ATTRIBUTE`, `engcore.domains.SCIENTIFIC_THRESHOLD_DECLARATIONS` | — |

The sprint's earlier breaks stand unchanged:
- `AdmittedForwardRow` constructor = admission gate; subclass and `replace` refused; `from_rows` real rows only; table admitted rows need admission refs.
- `CrossSolverConsensus` completeness over declared routes; coherence refusals; typed evidence; a level needs recorded numbers and a threshold key; schema `/3`, `/2` readable only without a level.
- `SolverSettings` negative tolerances, `RawSolverOutput` impossible bookkeeping and unrecordable diagnostics, `ScientificProblem` unrecordable metadata: all refused.
- `src.engcore` = alias of `engcore`.

## 9. FAST / FULL / WHEEL

| Run | Tree | Result |
|---|---|---|
| FAST baseline | `b5cedff` | 3832 passed, 3 skipped |
| FULL | `57bacd9` | 4521 passed, 3 skipped |
| heavy threshold consumers (T1/T2/T3, kinetics, ngspice, electrothermal, MCP, golden traces, thermal) with the fix | scratch copy of `f8cfd9a` content | 818 passed |
| focused: authority · consensus/promotion · serialization | `f8cfd9a` | 69 · 458 · 115 passed |
| **FAST** | `f8cfd9a` | **4049 passed, 3 skipped** |
| **FULL** | `f8cfd9a` | **4590 passed, 3 skipped, 0 failed** |
| **installed wheel** | wheel of `f8cfd9a` | **355 passed** — see below |

**Wheel details.**
- The wheel was built from `git archive f8cfd9a`, installed with `--target` on `D:` and run under `python -I -S` with no checkout on the path.
- Its top level is `engcore` and its dist-info only; there are no `src/` entries, and `engcore/py.typed` ships.
- `import src` and `import src.engcore` both raise `ModuleNotFoundError`.
- The tests run were the four trust-boundary files that need no checkout (including the A–K authority matrix), `inference/test_grid_inference.py` and `test_scientific_core.py`.
- The smoke script's own invented threshold set now correctly establishes nothing.

**No scientific equation changed.** This step's only source changes are `scientific/results/thresholds.py` (identity and authority) and the registry in `domains/__init__.py`. No solver, model, validity or domain-physics file was touched.

**No capability-boundary semantics changed.** No applicability or capability file was touched, and those suites pass inside FULL.

**No frozen artifact changed.** No file under `experiments/`, `src/engcore/domains/thermal/`, `benchmarks/blind/`, `certification/` or `tests/mutation_guards.py`, and neither pinned test module, was touched by this step. The T1/T2/T3 reproductions pass.

## 10. PERFORMANCE

Median of 7 repeats, single process, idle machine; before = `57bacd9`, after = `f8cfd9a`.

| Operation | `57bacd9` | `f8cfd9a` | Change |
|---|---:|---:|---:|
| declaration: `VerificationThresholds(3 values)` | 3.48 µs | 5.21 µs | +1.7 µs |
| verification: declared set `.is_declared` | 0.04 µs | 6.04 µs | +6.0 µs |
| verification: caller spec `.is_declared` | 0.04 µs | 1.41 µs | +1.4 µs |
| promotion: declared set `.award(earned=True)` | 0.27 µs | 6.08 µs | +5.8 µs |
| promotion: `CrossSolverConsensus.establishes` (3 routes × 10 q) | 4.87 µs | 10.74 µs | +5.9 µs |
| promotion: `CrossSolverConsensus.over` + `establishes` (3 × 10) | 91.9 µs | 103.3 µs | +12 % |
| round trip: `from_dict(to_dict())` | 6.79 µs | 9.80 µs | +3.0 µs |

**No material regression.**
- Authority verification used to be a field read, and is now real work: a package lookup plus a SHA-256 over the values, about 6 µs per promotion.
- The digest is recomputed on every call, deliberately, so a set whose values change after construction loses its authority (TA-5 is the mutation that proves it).
- A promotion happens once per check or report, not in an inner loop; end-to-end consensus construction moved 12 %.
- The declaration constructor itself is unchanged, so its +1.7 µs is run-to-run variation on this machine, not code.

No optimization was attempted.

Earlier in the sprint (`b5cedff` → `57bacd9`): no material regression. The only visible change was `CrossSolverConsensus.over`, about +115 µs for 3 routes × 50 quantities, because the constructor recomputes the comparison.

## 11. FILES CHANGED

**This step**
- `src/engcore/scientific/results/thresholds.py`
- `src/engcore/domains/__init__.py`
- new `tests/test_trust_boundary_threshold_authority.py`
- fixture migrations in `tests/test_cross_solver_consensus.py`, `tests/test_consensus_integrity.py`, `tests/test_core_numerical_integrity.py`, `tests/test_core_invariants_adversarial.py` and `tests/test_trust_boundary_consensus.py`
- this report

**Earlier in the sprint**
- `src/__init__.py`, 142 mechanical import migrations, `src/engcore/mcp/evidence.py` (comment), `tests/test_blind_challenge_guards.py`, `pyproject.toml`
- `src/engcore/inference/grid.py`
- `src/engcore/scientific/consensus.py`
- `src/engcore/scientific/solvers/protocol.py`, `src/engcore/scientific/ir/problem.py`
- `src/engcore/py.typed`
- tests `test_trust_boundary_{package_identity,admitted_row,consensus,bookkeeping}.py`

## 12. COMMITS

| Commit | Message |
|---|---|
| `018835b` | fix(packaging): enforce canonical engcore import namespace |
| `a572baa` | fix(inference): close admitted forward row trust boundary |
| `3d642dc` | fix(consensus): enforce consensus completeness invariants |
| `b6eea08` | fix(core): reject impossible solver bookkeeping states |
| `04dae1a` | chore(typing): mark engcore as typed |
| `93992d6` | test(consensus): observe the typed-evidence refusal failing |
| `57bacd9` | fix(consensus): a level needs the numbers its comparison was computed from |
| `f8cfd9a` | fix(thresholds): verify threshold authority against the domain layer's declarations |
| this commit | docs(hardening): trust boundary sprint 1 round report |

No commit was amended. *(Erratum: `b6eea08`'s message says "81 of 101"; the bookkeeping test file has 93 tests, 81 of which failed before the fix.)*

## 13. PUSH RESULT

The sprint was pushed to the dedicated branch **`claude/trust-boundary-hardening-sprint-1`** on `origin` (`sharq-labs/forge`), **not** to `main`.

- **What the branch holds:** local `main` at this report's commit, which is base `b5cedff` plus the nine commits in §12.
- **Why not `main`:** `origin/main` is `594ae17`, 39 commits ahead of the shared base, and the two sides overlap (§14). The branch therefore does not fast-forward `main`.
- **Integration:** merging it into `main` is a separate, reviewed step: a merge commit, re-running the import migration on the overlapping files, the one new pinned exemption, and moving upstream fixtures that invent threshold gates.

## 14. DEFERRED ITEMS

- **TB4-a — `AdmittedForwardTable` cache rehydration (P1).** The table's public constructor is the K2/K3/K3.1/K4 cache-rehydration API and cannot re-run admission. Invented admission refs still reach the posterior; this sprint added only the absence-of-evidence refusal. Closing it needs caches bound to their admission records.
- **TB4-b — `PredictiveAdmissionAudit` accounting (P2).** An audit with supported 0.1 / unsupported 0.9 over a 0.01 budget is accepted by `ConditionedPosterior`. Nothing in `src` promotes it; K3.1 re-checks.
- **TB4-x — hand-built verification reports (P2, evidence-model limit).** A conduction or CSTR `VerificationReport` with hand-set booleans, or a hand-authored `ValidationCheck` with a reference string, carries levels (GUARD 2 by design). `AdmissibleNumericalPrediction` rests on the same model.
- **Deliberate circumvention.** `object.__new__` / `object.__setattr__`, crafted pickles, and rebinding `engcore.domains.SCIENTIFIC_THRESHOLD_DECLARATIONS` at runtime can defeat any in-process invariant; the registry is immutable through the supported surface only.
- **Certification snapshot is stale.** `certification/current_core_v1.json` describes `b5cedff`; `scientific/` has changed since (`consensus.py`, `solvers/protocol.py`, `ir/problem.py`, `results/thresholds.py`). Re-certification is a separate round, and it is also where the 36 targeted mutations would join `tests/mutation_guards.py`.
- **Retiring the `src.engcore` alias** requires re-freezing E1/E2/T1/T2.
- **Integration with `origin/main` (`594ae17`, 39 commits ahead of the shared base `b5cedff`).**
  - 5 test files changed on both sides, all still spelling `src.engcore` upstream: resolve by taking upstream and re-running the migration.
  - One upstream byte-pinned file, `benchmarks/blind_v2/challenge/audit.py`, joins the pinned exemptions.
  - Upstream tests that construct invented `VerificationThresholds` and expect a level would need the same fixture move.
  - `docs/assurance/CLAIMS_AND_CAPABILITY.md` still names `cross_solver_consensus/2`.
