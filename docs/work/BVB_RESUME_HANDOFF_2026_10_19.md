---
ai_schema_version: 1
doc_id: FORGE-BVB-RESUME-20261019
doc_kind: AUDIT_HANDOFF
doc_status: SNAPSHOT
authority_scope: NONE
source_ref: multiple
evidence_level: REPORTED
last_reviewed: 2026-10-19
supersedes: none
---

# FORGE — Build vs Buy (BVB) Resumption Handoff — 2026-10-19

> **Historical audit navigation; not a replacement for `ACTIVE_PLAN.md`, not an authorization to replace code or install packages.** BVB-0 findings below are reported from the owner's Claude transcript at `abed661f`. The full six BVB reports and addendum were **reported untracked in a Windows worktree**, and are **not on `main` as of this snapshot**. Do not present this summary as an independent file-by-file verification of their contents.

## 1. Why Build vs Buy exists

**Goal:** make FORGE scientifically stronger at lower maintenance/implementation risk before formal Blindfold, while preserving FORGE-owned scientific authority (applicability, evidence admission, canonical identity, refusal, provenance, replay, uncertainty contracts, certification, falsification and benchmark verdicts).

**Decision vocabulary**
- **KEEP:** external substitution has no demonstrated net scientific benefit; KEEP **does not** mean bug-free.
- **WRAP:** use external library via typed, provenance-aware adapter after equivalence/licence/identity review.
- **REPLACE:** justified bounded implementation replacement, separately approved and verified.
- **AUDIT:** correctness, scope, epistemic limits or compatibility require independent evidence.
- **DEFER:** leave existing behavior and postpone the question, not an implicit PASS.
- **BASELINE ONLY:** independent equal-budget comparator, NOT production Trust authority.

BVB covers algorithm decisions, not scientific-authority ownership. **A mature library computing a value does not get to declare a claim SUPPORTED.**

## 2. Inventory reconciliation — don't merge proposed and accepted numbers

| Basis | KEEP | WRAP in existing code | REPLACE | DEFER | AUDIT | Total | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| Original BVB-0 report | 69 | 0 | 3 | 4 | 21 | 97 | Reported, not a scientific approval |
| Proposed FDA reconciliation | 67 | 0 | 3 | 4 | 23 | 97 | **PROPOSED**, A16/A21 changed KEEP→AUDIT |

Separate new benchmark arms **outside the 97**: WRAP PySR; WRAP BoTorch; BUILD full-grammar search. PySINDy only after a qualified dynamics task; no automatic LLM-ablation/model-swap admission without preregistration.

Original groups: Genesis-lite/Blindfold 25, Production statistics/UQ 42, Numerical/coupling/domain 29, test-oracle 1. The audit expanded an original §8 list of 37 rows into 97 identified components. This is a count of components, **not 97 defects**.

## 3. Review priorities, ranked by scientific consequence

| Rank | Component / evidence | Current epistemic state | ★ attention | Decision needed |
|---|---|---|---|---|
| 1 | **A16/A21** Genesis evaluator & escrow pair scoring, FDA-05 | Executed counterexample; KEEP in original audit is **incorrect as a correctness endorsement** | ★★★★★ | Scientific scoring semantics v0.3, independent challenge, escrow/evaluator agreement; proposed AUDIT |
| 2 | **A13** O-1 bootstrap-as-p / Holm | Validity and FWER guarantee unverified | ★★★★★ | Define valid inference after scoring is frozen; not automatic sign-flip |
| 3 | **A6/A17/A5/A3** baseline competence gate / noise / degrees of freedom | Source concerns; calibration unverified | ★★★★★ | Independent control and calibration; new arm if justified, never silently edit registered arm |
| 4 | **FDA-06** cap applicability across law-credit kinds | R-06 reproduces the capping-function issue, not a full lift PASS | ★★★★★ | Define per-kind cap and strong applicable *budget-attainable* baseline policy |
| 5 | **B26** MCP UQ sampler; FDA-04/14 | Executed negative controls and degenerate interval | ★★★★★ | Upgrade priority from original ★★★ after-Blindfold; isolated UQ repair, version/equivalence |
| 6 | **BO4 / BO9** predictive UQ unit dependence / propagation | Source-level concerns; scope not independently certified here | ★★★★★ | Independent unit invariance and uncertainty semantics |
| 7 | **B16/B13/BO8/BO1/B14/B2** statistics, confidence, randomness | Audit candidates, not fixed | ★★★★☆ | Independent evidence and scope-specific qualification |
| 8 | **C10/C11/CO12/CO10/CO6/CO14** coupling and numerics | Audit candidates | ★★★☆☆ | Oracle comparisons and conservation/conditioning tests; after primary freeze unless capability-dependent |
| 9 | **B22/B19** discovery ranking / novelty order | Potential correctness impact; exact fit last per audit | ★★★★☆ | Verify and repair via approved batch if claim depends on them |
| 10 | Optional library adoption: `expm1`, `solve_banded`, SciPy QMC | Proposed selective replacements, no integration measured | ★★★☆☆ | Decide after equivalence/identity review; no invented speedups |

**The other original AUDIT IDs:** A3, A5, A6, A13, A17; B2, B13, B14, B16, B19, B22, BO1, BO4, BO8, BO9; C10, C11, CO6, CO10, CO12, CO14. Original 21 total; with A16/A21 proposed 23.

**Gap outside BVB:** FDA-01 replay, FDA-02 clock and FDA-03 materials are Trust-lane scientific defects even though not scored as existing BVB algorithms. Preserve their workstream and do not dilute it into library substitution.

## 4. What changed after BVB-0

- FDA adversarial audit: **FDA-05** vacuous law pairs earned full credit in a bounded reproduction; **FDA-06** capping scope was partially reproduced. These invalidate any reading of original A16/A21 KEEP as scoring approval.
- Claude's later **self-challenge** found F5-A hidden-rival-relative informativeness exposed to sign changes/zero, generator-shape copying, absent-rival cases, and threshold gaming. It is **not author-independent**. F5-IS requires well-defined probabilistic predictive semantics; F5-D conservative fallback rewards refusal equivalently. **No FDA-05 design is approved.**
- For FDA-06, declaring a law expressible by a library is not evidence it is achievable under equal budget. Pilot-based qualification must not bias the formal evaluation; BoTorch does not automatically broaden law-family coverage.
- The O-1 statistical design depends on the final scoring, selected strongest baseline, family-wise multiplicity, proper null, non-inferiority and repeated submissions. **No O-1 simulation has been approved** by this record.

## 5. Libraries and licensing — pending due diligence

| Option | Proposed role | Prerequisite |
|---|---|---|
| PySR | Independent symbolic-regression baseline only initially | Licence and Julia transitive dependencies, environment pin, equal budget, no answer leakage |
| Full-grammar search | Benchmark baseline to challenge representation effects | Complexity ordering, fair budget, frozen identity and controls |
| BoTorch / Ax | Experiment-selection baseline, **not** blanket law-search family | Provider/env identity, deterministic budget, fair observable access |
| SciPy / SymPy | Existing numerical/symbolic providers and possible verified helpers | Unit/replay/numerical equivalence and API compatibility |
| SciPy QMC | Candidate repair for MCP sampling | Sampling assumptions, small-n statistical meaning and output schema version |
| preCICE | Independent coupling oracle/comparison | Not a drop-in replacement for generic FORGE coupling authority |
| Gmsh | Optional mesh provider with reported in-process GPL concern | **Legal/architecture review before applicable distribution** |
| PETSc/DOLFINx/Dakota distributions | Existing numerical providers; transitive licence flags | Inspect exact binaries and transitive licences, distribution modality and counsel |

Do not call any flagged package absolutely commercially forbidden on this record; the distribution and linkage facts must be established. Do not claim a licence PASS because a dependency installs successfully.

## 6. The six source reports — local-only preservation checklist

Reported original files at `D:/forge-main-337519d1/docs/work/`:

| Name | SHA-256 reported by the preservation session |
|---|---|
| `BVB_40_ALGORITHM_INVENTORY.md` | `9b1a2b9d89887a512c6aa203775f6329a959700e0eb8c65d8b742cfa7ef90f79` |
| `BVB_SCIENTIFIC_COMPARISON_MATRIX.md` | `2e995cbf861271183fbcc4d378adec03d04e42099b0f6ae7e5c7f3d9d658f1bb` |
| `BVB_LICENSE_AND_DEPENDENCY_AUDIT.md` | `cd25b738b74e761409e43f25954cdd35e6e07a78d7ffe2388737c3db3719fa79` |
| `BVB_NUMERICAL_EQUIVALENCE_PLAN.md` | `2b83d24491e35e2d348053e1fb76a482b665aef9079e9a87483fb9f8bababb05` |
| `BVB_PRE_BLINDFOLD_ROADMAP.md` | `697cfaf7dfbc2f9bc55dc7f7b2a3b81df6c9fee1f2c4c5cdb0fe2b7eafc3d899` |
| `BVB_OWNER_DECISIONS.md` | `654502880efa03e587d2f93e38189cf27b9b9d3fe3b33116e0636a0087a91612` |

Additional local `BVB_FDA_RECONCILIATION_ADDENDUM.md` was reported SHA-256 `5087c1772920a9890eedde9acddcd3a9aec5082f9975c04e77215e6597e8c246`. Existing untracked design reports and duplicated FDA preservation evidence must be inventoried separately.

**Recommended preservation procedure, not automatically authorized:**

1. Confirm real local worktree and file presence with read-only commands; inventory concurrent agents.
2. Re-hash exact bytes and match every reported digest; diagnose mismatch, do not overwrite.
3. Check whether each file already exists elsewhere on GitHub; do not duplicate SHA-pinned FDA evidence.
4. Propose a **separate docs-only branch/Draft PR** containing the original files plus dated follow-up errata, not mutated originals; scan for secrets/hidden answers and review GitHub rule/cert impact.
5. Request explicit approval for staging, committing, pushing and merging. No silent changes to `PR #169`, original FDA manifests, `main` or scientific contracts.

## 7. Proposed BVB phases and evidence gates

| Phase | Purpose | Proof before promotion | Owner status |
|---|---|---|---|
| **BVB-0** | Inventory and decisions | 97 entries source-linked; prioritize independent defects | Audit reported complete; decisions/open corrections |
| **BVB-1** | Independent benchmark arms | Equal-budget, pinned environments, no hidden data, independent eval | PROPOSED; **before Genesis v0.3 freeze if included** |
| **BVB-2** | Selective WRAP/REPLACE | Numerical and scientific equivalence, replay/identity, UQ, licences, independent controls | PROPOSED; item-specific authorization |
| **BVB-3** | Verification and freeze readiness | Independent scientific review, failed-first tests, no false support, correct certification | PROPOSED; do not claim achieved |

**Prioritization rule:** scientific false support > isolation/scoring validity > preserving evidence > baseline quality > optional convenience/maintenance. Parallel design and documentation can proceed where authorized; expensive verification and formal measurement remain separately controlled. BVB provider refactors are **not** a prerequisite for all baseline qualifications, and deferred optional adoption should not delay an otherwise valid Blindfold.

## 8. Resume signal

When the owner says `كمل آخر حاجة`, do not simply start installing packages: open the current dashboard, inspect this handoff, verify the local original BVB reports, show a table with audit vs implementation vs scientific PASS, then ask for the single authorization actually required by `ACTIVE_PLAN.md`. The first data-preservation recommendation is to secure the original six reports and addendum; it is **not** itself permission to push.
