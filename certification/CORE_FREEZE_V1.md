# Core Freeze V1

Branch `claude/core-freeze-v1` · Tag `v1.0-core-freeze` · Manifest
`certification/core_freeze_v1.json` · Assurance
`certification/core_freeze_v1_assurance.json`

```
python -m tools.certification.core_freeze --verify
python -m tools.certification.core_certificate --verify
```

---

## 1. FINAL VERDICT

**CORE FROZEN — V1**

The first candidate was **FREEZE_BLOCKED** (§2). The defect was fixed, and
every assurance step then ran on the corrected candidate rather than being
carried across from the blocked one.

---

## 2. FREEZE COMMIT

| | |
|---|---|
| `FINAL_FREEZE_BASELINE` | `af43c896f79a37ac10c0c4e981836b85b24e5a5b` — Sprint 10 close |
| baseline verdict | **FREEZE_BLOCKED — broken compatibility claim** |
| assured candidate | **`48009651c5063eb22b873ea7300b69faab8f16c1`** |
| evidence commits | `d08e7c7` (assurance and evidence), `6636178` (log bytes, §27) |
| freeze commit | the commit `v1.0-core-freeze` names — the commit that adds this report |
| `src/` tree object | **`7b220ba2b28100a75e6138d9b233ba81823bd9e1`**, identical at baseline, candidate and tag |

A commit cannot contain its own hash, so the freeze commit is identified by the
tag, as the repository's existing release tags already do:

```bash
git rev-list -n 1 v1.0-core-freeze
git rev-parse v1.0-core-freeze^{}:src     # 7b220ba2…
```

**The tagged `src/` is provably the assured `src/`.** The candidate is an
ancestor of the tag, and every commit after it touches only paths on the
verifier's evidence list — no code, no tests. Check
`assurance.post_candidate_changes_are_evidence_only` enforces this.

### The blocked candidate

Before any assurance ran, the reproduction pass found that
`tests/test_core_api_serialization.py` stated the serialization policy as:

> `SUPPORTED_LEGACY` — none. No legacy format is supported
>
> `SUPPORTED_CURRENT` — 62 records

Both statements were false. Eight **frozen** readers accept older schema
versions, each through an explicit tuple, and loading real legacy payloads is
tested in the suites that own those records (`test_result_validity`,
`test_provenance_integrity`, `test_consensus_integrity`, …). The frozen
round-trippable count is 61.

The behaviour was right. The written contract contradicted it, and a freeze
cannot certify a contract whose own statement of itself is false.

- **Fix:** the module docstring only.
- **Proof it was docstring-only:** the AST of every non-docstring statement was
  compared before and after, and is identical.

---

## 3. FREEZE TAG

| | |
|---|---|
| tag | `v1.0-core-freeze`, annotated |
| convention | the repository's existing `v<major>.<minor>-<subject>` (`v1.0-benchmark`, `v1.1-benchmark`) — the brief's `core-v1.0-freeze` was not used, because it would have been a second scheme |
| release note | `docs/release/v1.0-core-freeze.md` |

---

## 4. CORE CERTIFICATE DIGEST

`619f43f7d1625f19c9a6bb98b401d79f4f9907695836a3dd2f4b72cc48927ca5`

- **Certified commit:** `b32f67d7ad16…`. 76 files are in certified scope.
- **Not reissued:** no file inside certified scope changed between the Sprint 10
  certificate and the freeze. The freeze adds tooling, tests, documentation and
  evidence, all outside scope.

---

## 5. FREEZE MANIFEST DIGEST

| | |
|---|---|
| `certification/core_freeze_v1.json` | **`eb7643007ca8ced81e80b0403fcf953c2d2f9855b92e2b1242255339f9220aee`** |
| `certification/core_freeze_v1_assurance.json` | `ffaac7dcbec48823cd0f06ff77158d4fa40f09f17ace1124bda8b9b13b716a4a` |

**The manifest was built inside the candidate commit it describes.** That
required `--allow-dirty`. On the clean candidate it was then rebuilt, and
`git diff --exit-code` showed the rebuild byte-identical to the committed file.

**Why the manifest and the assurance record are separate files:**

- The manifest holds facts about the candidate. It is committed *in* the
  candidate and verified by the candidate's own tests.
- The assurance record holds results *about* the candidate. It therefore cannot
  live in the candidate.

---

## 6. FROZEN PUBLIC SYMBOL COUNT

**194**, pinned in `tests/api/frozen_api_snapshot.json`. That file's sha256 is
recorded in the manifest.

---

## 7. FROZEN API DIGEST

`c80e6418592e94a05e3ae48e0856c96edb194054a312a8f78d10d133b72b4929`

The digest was reproduced in three places, all identical:

- the source checkout;
- the installed wheel under `python -S -E`;
- the Sprint 10 pinned value.

---

## 8. EXPERIMENTAL SYMBOLS

**11. EXPERIMENTAL != FROZEN.** These symbols are excluded from Core Freeze V1
and may change without violating it.

| module | symbols |
|---|---|
| `engcore.studies` | `TCR_MODEL_REF`, `TcrTruth`, `build_tcr_parameter_set`, `ols_reference_estimate`, `synthesize_tcr_observations`, `tcr_forward_evaluator`, `tcr_forward_table`, `tcr_prediction` |
| `engcore.inference` | `FieldObservationOperator`, `FieldObservationKind`, `FieldObservationError` |

Promotion requires, in order:

1. API review.
2. Compatibility review.
3. Tests.
4. A later freeze manifest.

**Silent promotion is refused by the verifier.** A test performs it carefully —
shortening the experimental list and raising the frozen count to match — and
requires `contract.api` and `experimental.visibly_classified` to fail.

The `workers` parameter of `run_sweep` / `rerun_failed` is also experimental.

---

## 9. CANONICAL IMPORT POLICY

A symbol is frozen **at** one of seven canonical modules: `engcore.scientific`,
`.data`, `.inference`, `.uq`, `.adequacy`, `.execution`, `.studies`. Deeper
paths are implementation detail.

- **Package identity:** `engcore` is the only supported package name.
- **Unsupported checkout alias:** `src.engcore` is not part of the contract.
  - Inside the installed wheel, top-level `src` does not resolve at all, even
    with the working directory at the repository root and `PYTHONPATH` pointing
    at the checkout.
- **Non-Core packages:** `domains`, `systems`, `sria`, `design` and `mcp` are
  classified non-Core and carry no freeze guarantee.

---

## 10. SERIALIZATION POLICY

- **61 frozen records round-trip:** `from_dict(to_dict(x)).to_dict()` is
  byte-identical to `to_dict(x)`.
- **16 are export-only**, each named in the manifest.
- **Unknown versions are refused:** every fixture that carries a schema marker
  refuses a version it did not write.

Reproduced on the candidate:

| check | result |
|---|---|
| inventory counts | 61 round-trippable / 16 export-only |
| round trips | all frozen fixtures byte-identical |
| unknown-version refusal | refused, for every schema-carrying fixture |
| in the wheel | reproduced identically |
| `serialization` suite group | **218 passed**, including the legacy loaders |

---

## 11. LEGACY FORMAT POLICY

**Eight frozen readers accept older versions**, each through an explicit tuple
of exact version strings — never a range, never a migration framework.

| reader | accepted |
|---|---|
| `ScientificResult` | `scientific_result/1` … `/4` |
| `ProvenanceRecord` | `provenance_record/1` … `/4` |
| `CrossSolverConsensus` | `cross_solver_consensus/1` … `/3` |
| `RawSolverOutput` | `raw_solver_output/1`, `/2` |
| `ScientificModelDefinition` | `scientific_model_definition/1`, `/2` |
| `ValidityAssessment` | `validity_assessment/1`, `/2` |
| `QuantityDependency` | `quantity_dependency/1`, `/2` |
| `QuantityTransfer` | `quantity_transfer/1`, `/2` |

**How the table is derived:** from each reader's `from_dict` source, by locating
its `require_schema_any` call and resolving the tuple against the module. It is
**not** parsed out of the refusal message, because error prose is explicitly
outside the contract and reading it would quietly make it load-bearing.

**Refusal is confirmed:** each reader refuses an undeclared version.

**What counts as a break:**

- **Removing a declared version:** a break. The verifier fails, and a test
  proves it.
- **Adding a declared version:** not a break.

**No legacy support was added in Sprint 11.**

---

## 12. IDENTITY / DIGEST CONTRACT

Scientific digests are SHA-256 over canonical field sets, serialized with
`sort_keys=True, separators=(",", ":"), allow_nan=False`. The Sprint 10 pairs
were reproduced unchanged.

| pair | expected | holds |
|---|---|---|
| a different model | digest moves | yes |
| a different unit | digest moves | yes |
| an equal range in another unit | digest stable | yes |
| a different observed value (evidence identity) | digest moves | yes |
| parameter-set order (contractual) | digest moves | yes |
| operator description *(experimental)* | stable | yes, recorded but not frozen |
| operator mesh *(experimental)* | moves | yes, recorded but not frozen |

**Where this was verified:**

- **Same process:** each pair rebuilt and compared.
- **Fresh processes:** four hash seeds and two working directories.
- **Installed wheel:** under `-S -E`.

**Reference digests are pinned.** The manifest records the digests for the
reference parameter, parameter set and evidence identity. A change to digest
*semantics* therefore fails `contract.identity` even when every pair still has
the right equality.

---

## 13. EXCEPTION CONTRACT

**Seven roots, 24 frozen exception classes.**
`except ScientificCoreError` does **not** catch everything the Core raises.

| root | frozen descendants |
|---|---|
| `scientific.errors.ScientificCoreError` | 13 |
| `inference.grid.InferenceProblemError` | 4 |
| `data.errors.BulkDataError` | 3 |
| `inference.admissibility.InferenceAdmissibilityError` | 1 |
| `inference.parameters.ParameterIdentityError` | 1 |
| `adequacy.predictive.ModelAdequacyError` | 1 |
| `uq.predictive.UQProblemError` | 1 |

- **Frozen:** the exception classes and their family roots.
- **Not frozen:** message text.

---

## 14. DEPENDENCY POLICY

- **Declared imports:** every third-party import is declared in `pyproject.toml`.
- **Runtime isolation:** no runtime module reaches a benchmark-only dependency.
- **Declared but unreached:** exactly `pytest-xdist` and `scikit-learn`, each
  named.
- **Reproduced:** the `dependency_layering` group passed (**41**), and the
  certified `contract_guard` passed (**305**).
- **Structure unchanged:** the dependency layout was not redesigned.

---

## 15. LAYERING POLICY

```
scientific → data → inference → uq → adequacy → studies
```

- **`execution` is off the ladder:** it may import `scientific` and `data`
  only, and only `studies` may import it.
- **One Core → non-Core edge is permitted:** `studies → domains`, and no other.
- **Package classification:** every package under `engcore` is classified.
- **Reproduced:** zero upward edges, zero cycles, zero unclassified packages.

---

## 16. DETERMINISM RESULT

**The reproduction document is byte-identical in all 9 runs:**
`4f8b4223eb2824aafe5fd2f41ed72b5ceedbd1ab6d1f44dcc0ca8539e3b6173b`.
This equals the manifest's recorded `reproduction_sha256`.

| side | hash seeds | working directory |
|---|---|---|
| source | 0, 1, 4242, random | repository |
| source | random | elsewhere |
| wheel (`-S -E`) | 0, random | repository and elsewhere |

**What the document covers:**

- API snapshot digests and the canonical-bytes digest;
- the scientific identity digests;
- the canonical serialization bytes of every fixture;
- result ordering;
- failure ordering, including FAIL_FAST;
- sweep and case identities.

**Ordering checked concretely.** Declared cases `3,1,4,1,5,9,2,6,7,12`, with
multiples of 3 refused:

- **Outcomes** come back in declaration order.
- **Failures** come back as `c3, c9, c6, c12` — declaration order, not value
  order.
- **FAIL_FAST** stops after the first case, leaving 9 cases NOT_RUN.
- **Reversing the declaration** changes the sweep identity but no case identity.

**Excluded, because the contract does not promise them:** wall-clock time,
tracebacks, memory addresses, and error prose.

---

## 17. INSTALLED WHEEL PROOF

**The wheel was built from `git archive` of the candidate**, so it contains
committed bytes only. It was built **twice**.

| | |
|---|---|
| file | `crafty-0.4.0-py3-none-any.whl`, tag `py3-none-any`, `Requires-Python >=3.11` |
| wheel sha256 | `456484d093b95a683ee784e5540834a710522686e96b9957269725fe798545a6` (with `SOURCE_DATE_EPOCH=1789236839`, the candidate's commit time) |
| RECORD content digest | **`93aca82b6ae69a750673e0fd77e6f7f14b88806ddc366a7ab36c1427ad29b9ff`** (213 entries) |
| reproducible across the two builds | **yes**, for both digests |
| installed top level | `engcore`, `crafty-0.4.0.dist-info` |
| `engcore` imported from | the install target — checked before anything else ran |
| top-level `src` importable | **no** |
| frozen count / digest | 194 / `c80e6418…` |
| Core tests against the wheel | **190 passed** |

**The checkout cannot satisfy a missing module.**

- **Setup:** a copy of the install had `engcore/inference/split.py` deleted.
- **Run:** it was imported with the working directory at the repository root and
  `PYTHONPATH` set to the checkout's `src/`.
- **Result:** `ModuleNotFoundError: No module named 'engcore.inference.split'`.
- **Strictness:** the check requires failure on *that* module. A launcher abort,
  or an unrelated import error, would not count.

**Wheel file hashes are not reproducible by default.** A build without
`SOURCE_DATE_EPOCH` produces a different file hash every time, because zip
entries carry timestamps. This was measured before the proof was written. It is
not a packaging defect: nothing ever claimed byte-reproducible wheels. The
RECORD content digest is the reproducible identity.

**Two tests were deselected in the wheel run only.** Both spawn
`sys.executable`, which is the venv interpreter *with* `site.py`: it would
import the checkout and pass without proving anything. Their property,
fresh-process determinism, is covered under `-S -E` by §16 instead.

**Tests that read `REPO / "src"` walk the wheel.** The install target sits at
`<work>/src`, so those tests read the installed files rather than finding
nothing and passing vacuously.

---

## 18. DOMAIN NON-INTERFERENCE

| | |
|---|---|
| `DOMAIN_FREEZE_START_DIGEST` (at `af43c89`) | `81bcc7f8527833a138009a2d9b19f11aefade2537315a6e33bcacdbbc3ce9a85` |
| `DOMAIN_FREEZE_END_DIGEST` | `81bcc7f8527833a138009a2d9b19f11aefade2537315a6e33bcacdbbc3ce9a85` |
| equal | **yes** |
| `git diff FINAL_FREEZE_BASELINE -- src/engcore/domains` | **empty** |
| files under `domains/` | 49 |
| domain regression | **11 suites, 355 tests, all green** |

The start digest was computed from git at the baseline commit, not taken from a
number recorded by hand.

---

## 19. SPRINT 10 MUTATIONS

**CONTROL GREEN. 21/21 written mutations killed on the candidate.** With the
two requested-but-unwritable candidates kept in the denominator: 21/23.

- **Families covered:** API-1…5, SER-1…4, DEP-1…2, M-1…2, S-1, T-1…2, DEF-1,
  ALIAS-1…2, DET-1, EXC-1.
- **PKG-1 and PKG-2:** still recorded as `INVALID_MUTATION`, with reasons.
- **No new mutation families were written for Sprint 11.**

---

## 20. CERTIFIED 79

**CONTROL GREEN, with 470 tests passing on the unmutated copy. 79/79 killed.
0 survivors.**

- **Run on:** the clean candidate.
- **Tally cross-checked:** the verifier re-derives it from the committed log —
  79 per-mutant RED lines, zero GREEN, and the runner's own tally line.
- **Committed log sha256:**
  `c4bcaeaf3d8c86b350db5b35f1fd3ea5019cdb1fe6e3466557e0b803c77757f0`
  (see §27).

---

## 21. EI/RI/FM/SP STATUS

**CARRIED_FORWARD — not re-measured.**

| | |
|---|---|
| figures | EI 10/10 · RI 11/12 (RI2b a known equivalent mutant) · FM 8/8 · SP 10/10 |
| last measured | Sprint 7, `benchmarks/core_v2_recertification` |
| justification | `src/` is byte-identical between the Sprint 10 close and the candidate, so Sprint 10's justification holds a fortiori |

**This carry-forward is weaker than it looks, and it is recorded as such.** The
harness that measured these families was kept outside the repository. It cannot
be re-run from tracked files, and the figures have now been carried through
Sprints 8, 9, 10 and 11.

**Nothing in Core Freeze V1 rests on them.** The freeze's mutation assurance is
the certified 79 and the Sprint 10 matrix, both re-run on the candidate.

---

## 22. FAST

| commit | result |
|---|---|
| candidate `4800965` | **4904 passed, 4 skipped, 0 failed** |
| `6636178` (all evidence committed) | **4904 passed, 4 skipped, 0 failed** |

---

## 23. FULL

| commit | result |
|---|---|
| candidate `4800965` | **5450 passed, 4 skipped, 0 failed** |
| `6636178` | **5450 passed, 4 skipped, 0 failed** |

---

## 24. GUARDS

All twelve suite groups were green on the candidate:

| group | result |
|---|---|
| contract guard | 305 passed |
| capability boundary | 306 passed |
| scientific truth | 293 passed |
| field suites | 124 passed |
| field-profile suites | 147 passed |
| API snapshot, deprecation, executable policy | 51 passed |
| serialization, incl. legacy loaders | 218 passed |
| dependency, layering, trust boundary | 41 passed |
| freeze manifest | 23 passed |
| certificate | 28 passed |
| wheel tests | 190 passed |

---

## 25. CERTIFICATE VERIFY

`python -m tools.certification.core_certificate --verify` → **OK**

The certificate matches the tree at the baseline, at the candidate and at every
commit after it.

---

## 26. FREEZE VERIFY

`python -m tools.certification.core_freeze --verify` → **OK**, mode
**EXACT_FREEZE**.

**Checks:** 34 binding checks, all passing. They cover:

- manifest schema and internal consistency;
- where the facts came from;
- the tree's relation to the baseline;
- the frozen API, serialization, identity, ordering and exception facts;
- experimental exclusions;
- certificate verification and identity;
- the pinned contract files;
- the reproduction digest, domain digest and package metadata;
- the assurance record — its manifest hash, tag, candidate ancestry, evidence
  hashes and post-candidate path restriction;
- every figure, re-derived from its evidence file.

**The verifier is tested against itself.** Twelve tamper tests break one fact at
a time in an in-memory copy, and require failure on the owning check:

- the frozen digest;
- a silent promotion;
- a dropped legacy version;
- the round-trip count;
- a reference digest;
- failure order;
- a new exception family;
- an internal inconsistency;
- a pinned file;
- a different manifest hash;
- code changed after the candidate;
- a contract-breaking descendant.

**Descendants.** A contract-keeping descendant is shown to verify, with
byte-level checks demoted to informational.

**Command-line and function results agree**, and a test checks that.

---

## 27. FILES CHANGED DURING FREEZE

**15 files** between `af43c89` and `6636178`, plus this report. **Zero under
`src/`.**

| kind | files |
|---|---|
| defect fix — docstring only | `tests/test_core_api_serialization.py` |
| freeze tooling | `tools/certification/core_freeze.py` |
| freeze tests | `tests/test_core_freeze_manifest.py` |
| reproduction | `benchmarks/core_freeze_v1/audit/reproduce.py`, `freeze_reproduction.py`, `suites.py` |
| contract manifest | `certification/core_freeze_v1.json` |
| policy (docs) | `docs/CORE_FREEZE_POLICY.md` — legacy table, §10 change policy, §11 experimental policy |
| evidence | `benchmarks/core_freeze_v1/{SUITES,REPRODUCTION,REPRODUCTION_OUTPUT}.json`, `MUTATION_HARNESS_79.log`, `benchmarks/core_api_stability/MUTATIONS.json` |
| assurance and release | `certification/core_freeze_v1_assurance.json`, `docs/release/v1.0-core-freeze.md`, this file |

`MUTATIONS.json` moved only because the matrix's summaries carry pytest
timings; its verdicts are unchanged. `DOMAIN_BOUNDARY.json` did not move.

### A defect in the freeze's own evidence, found and fixed

**What went wrong.** The first assurance record hashed the 79-mutant log as the
Windows harness wrote it: CRLF, 34 876 bytes, sha256 `75b95229…`. With
`core.autocrlf=true`, git stores that file as LF — 34 557 bytes, sha256
`c4bcaeaf…`.

**Why it mattered.** A fresh clone would have carried a log whose hash is not
the one the record named. `evidence.hashes` would have failed there while
passing here.

**How it was found.** After committing, every evidence file was compared with
its committed blob. Seven were byte-identical; the log was not.

**What was fixed, and what was not changed.**

- **Fixed:** the record now names the stored bytes, in a separate commit
  (`6636178`), not an amend.
- **Unchanged:**
  - the log content, apart from 319 carriage returns;
  - the candidate;
  - every result.
- **Nothing was re-run.**

---

## 28. DOMAIN FILES CHANGED

**0.**

---

## 29. COMMITS

| | |
|---|---|
| `4800965` | `freeze(core): Core Freeze V1 candidate -- manifest, verifier, reproduction` |
| `d08e7c7` | `cert(core): Core Freeze V1 assurance, run on candidate 4800965` |
| `6636178` | `fix(cert): record the harness log by the bytes git stores, not the bytes it was written with` |
| the tagged commit | `docs(cert): the Core Freeze V1 report` — adds this file only |

---

## 30. PUSH RESULT

**This file cannot contain its own publication.**

- **Procedure:** branch `claude/core-freeze-v1` is pushed to `origin`
  (`sharq-labs/forge`) after this commit, and the remote HEAD is compared with
  the local HEAD.
- **Checked against the server:** the comparison uses `git ls-remote` as well as
  the tracking ref.
- **Where the result lives:** it is recorded outside this commit, in the
  round's final response.

**How to check it independently:**

```bash
git ls-remote origin refs/heads/claude/core-freeze-v1
```

---

## 31. TAG PUSH RESULT

**For the same reason as §30, the result is not recorded here.**

- **Procedure:** `v1.0-core-freeze` is created as an annotated tag on this
  commit — branch HEAD, so tag == HEAD.
- **Push:** the tag is pushed explicitly.
- **Check:** it must resolve on the remote to the exact local commit.

**How to check it independently:**

```bash
git ls-remote origin refs/tags/v1.0-core-freeze 'refs/tags/v1.0-core-freeze^{}'
```

**A fresh clone of the remote tag is then verified with both commands in §1.**
It runs in an isolated interpreter, so the checkout under test — not this
working directory — supplies `engcore`. That is the proof that no untracked
evidence is needed.

---

## 32. POST-FREEZE CHANGE POLICY

This policy is in `docs/CORE_FREEZE_POLICY.md` §10–§11 and in the manifest's
`change_policy`. It is enforced by the verifier's EXACT/DESCENDANT modes.

**Allowed without breaking the freeze**

- bug fixes preserving frozen behaviour
- internal refactors preserving frozen contracts
- performance improvements preserving exact semantics
- new tests
- documentation
- new Domain work
- new optional internal implementations

**Requires a Core compatibility review**

- removing or renaming a frozen symbol
- a signature change, including required or default arguments
- changing enum members or values
- breaking a supported serialization format, current or legacy
- changing material digest semantics or evidence identity semantics
- changing trust or admission semantics
- removing public result fields
- changing stable exception classes or their roots

**Requires a new Core Freeze version**

Any intentional incompatible change to the frozen contract.

**How the verifier treats later commits:**

- **Byte-level checks become informational.** These are the `src/` tree, the
  domain digest, the certificate aggregate and package metadata.
- **Contract checks keep binding.** These are the frozen API digest, the
  experimental set, the serialization inventory and legacy table, the identity
  reference digests, the ordering, and the exception roots.

---

## 33. EXACT CORE CAPABILITY CLAIM

Core Freeze V1 claims exactly this, and each clause is checked by a named
verifier check or suite:

1. **Frozen surface.** 194 public symbols, exported from seven canonical
   `engcore` modules. Signatures, parameter kinds, defaults, dataclass fields
   and default factories, enum members and exception ancestry are pinned by the
   frozen API digest `c80e6418…`.
2. **Wheel parity.** The installed wheel exposes that same surface.
3. **Serialization.** 61 frozen records round-trip byte-identically, 16 are
   export-only, and eight frozen readers accept exactly the older schema
   versions listed in §11. Every other version is refused.
4. **Identity.** Scientific identity digests move on material changes and do not
   move on non-material ones. The pinned reference digests are reproduced in
   fresh processes and in the installed wheel.
5. **Ordering.** Sweep outcomes and failures return in declaration order.
6. **Exceptions.** There are seven exception families.
7. **Determinism.** The Core's deterministic artefacts are byte-identical across
   hash seeds, working directories, source and wheel.
8. **Trust boundary.** The admission and trust semantics exercised by the
   certified mutation harness hold: 79/79 killed.
9. **Domain non-interference.** The domains were not touched by the freeze, and
   their regressions pass.

---

## 34. EXPLICIT CORE NON-CLAIMS

- **Experimental surfaces:** the 11 experimental symbols are not frozen.
  EXPERIMENTAL != FROZEN.
- **Behaviour and performance:** no promise about behaviour, numerical results
  or performance figures.
- **Error prose:** undocumented error text is not frozen. Exception classes and
  roots are.
- **Internals:** internal implementation details, private helpers, submodule
  paths and benchmark implementation details are not frozen.
- **Catch-all exceptions:** `except ScientificCoreError` does not catch
  everything the Core raises.
- **Checkout alias:** `src.engcore` is an unsupported checkout alias, not part
  of the contract.
- **Non-Core packages:** `domains`, `systems`, `sria`, `design` and `mcp` carry
  no freeze guarantee.
- **Wheel file hash:** not byte-reproducible without `SOURCE_DATE_EPOCH`.
- **EI/RI/FM/SP:** not re-measured, and their harness is not in the repository.
- **Parallel execution:** `workers` is experimental; parallel execution is not
  frozen.
- **Benchmark performance numbers:** measurements, not promises.
