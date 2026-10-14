# BR-15 — Authority Boundary & Certification Closure

| Field | Value |
|---|---|
| Date | 2026-10-14 |
| Base | `origin/main` = `e193e573` (PR #142 merge; contains PR #140 `623149f3`) |
| Branch | `fix/br15-authority-closure`, clean worktree `D:/forge-br15`; Linux clone `~/forge-br15` (WSL) |
| Commits | `dc26175d` red reproducer · `6d62e5cf` closure fix · `a49e8d12` harness fix · `01073787` review LOWs |
| Not done | push, PR, merge, GitHub settings, hardened recertification (owner-run) |
| **Outcome** | **PARTIALLY_CLOSED — BLOCKED_OWNER_RECERTIFICATION and BLOCKED_OWNER_GOVERNANCE** |

BR-15 does not report PASS. Every investigated authority-critical path is now protected or dispositioned with
evidence. Every confirmed defect in scope has negative and positive regression tests. The independent
scientific review has no unresolved BLOCKER or HIGH. Two gates remain owner-only:

* The committed certificate does not describe `main`, and it does not describe this branch. Recertification
  (OD-3) has **not** run.
* Host branch protection cannot be enforced on this repository's plan.

## 1. Work package A — post-merge truth

| Check | Result (command / source) |
|---|---|
| HEAD | `origin/main` = `e193e573`. Lineage: `b1eea81b` (certificate child of `05522b59`) → `8df12a75` docs → `52bf55d3` merge of main → `623149f3` PR #140 → `15839996` PR #141 docs → `e193e573` PR #142. |
| Merge #140 tree | `git diff --name-only 05522b59 623149f3`: only the certificate, `docs/**` and `gaps/**` changed. **The merge introduced no source or test change** (NOT a regression). |
| Certificate at `623149f3` | `core_certificate.py --verify` (Windows) FAILED with one PROBLEM, a case-variant `src/engcore/scientific/results/Uncertainty.py`. Root cause below (A-3). It is a platform defect, not drift. |
| Certificate at `e193e573` | `--verify` **FAILED**. `harness: MODIFIED tests/mutation_guards.py`; `certification_control: MODIFIED tests/test_formal_xdist.py`. The certified commit is `05522b59`. PR #142 (`f869a737`) changed two certified files after recertification. |
| CI on `main` @ `e193e573` | Tests (push). `fast (py 3.11)` and `fast (py 3.12)` FAILURE, `scientific` FAILURE, each with exactly one failure: `test_core_certificate.py::test_the_certificate_describes_this_tree`. `reproduce` FAILURE (Docker image has no `.git` and runs as root; pre-existing). `mutations` in progress. Branch Policy FAILURE (HTTP 403 on the rules API). The Tests runs for `623149f3` and `15839996` were **cancelled** by concurrency. |
| CI on PR #140 (`52bf55d3`) | Recertify: `fast311` success. `fast312` FAILURE (`test_core_performance_guards.py::test_validity_assessment_construction_grows_linearly_with_its_unknowns`, 32.3x, timing). **All 8 `v4_mutations_*` FAILURE.** 4 `formal_mutations_*` still in progress when read. The PR merged at 09:18:48Z before the run completed. |
| CI on PR #142 (`f869a737`) | Recertify: `fast311`, `scientific312`, `campaign312`, `regression312`, `trust_mutations` success. `fast312` FAILURE (`test_formal_xdist.py::test_real_xdist_infrastructure_failure_never_earns_credit[worker_lost_before_target]`: REFUSED, but for "infrastructure events" rather than "exit 5"). **All 8 `v4_mutations_*` FAILURE.** 4 formal still in progress. Merged at 09:40:33Z with these gates red or pending. |

### Unreviewed commits

| Commit | In history | Verdict |
|---|---|---|
| `659da048` (system_runtime area) | yes | ACCEPT. It is the area this round extends, and the new closure check confirms its imports are covered. |
| `313bbf1e` (FAILED-line attribution) | yes | ACCEPT. It was superseded by `f869a737`. |
| `05522b59` (psutil-free liveness, case-twin) | yes | ACCEPT. It is test-only. Its C6 test overwrote a tracked file on a case-insensitive filesystem, which `f869a737` fixed with a skip that applies only there. |
| `f869a737` (post-merge review of the above) | yes | **CURRENT_DEFECT → FIXED (`a49e8d12`)**. `failed_test_names` read the **first** summary block. A nested pytest summary in captured output was credited as a kill, and the real summary was never read. |

## 2. Work package B — certified authority closure

The F2 closure is derived from six roots: `claims/verdict.py`, `assessment.py`, `adapters/nl.py`,
`credibility/evidence.py`, `authority/**` and `blindfold/**`. Certified modules outside it were never checked.
A static walk over all 440 certified `src` files found 27 uncertified non-exempt direct imports and 82
transitively. The old review's figure of "95" was never used as a target.

| Dependency | Certified importer (area) | Influence | Class | Disposition |
|---|---|---|---|---|
| `sria/decision/hypotheses.py` (`CLAIM_FIELDS`, `CONTENT_FIELDS`, `HypothesisStatus`, `NoveltyStatus`) | `claims/falsification.py`, `novelty.py`, `durable_campaign.py`, `discovery_passport.py` (verdict_authority) | Falsification verdict, novelty and passport identity. Reproduced: a refuted claim re-registered under a new id reads `surviving`, and `verify_status` reports no problems. | AUTHORITY_CRITICAL | Pinned (`sria/decision/**` → assurance_admission) |
| `sria/campaign/events.py` (`CampaignEventLog`), `checkpoint.py` (`EffectLedger`), `state.py`, `persistence.py` | `sria/campaign/runner.py` (assurance_admission) | The certified stop review receives Arbiter decisions and their order from the event log. Reproduced: dropping the INVALID decision turns `STOP_REJECTED` into `STOP_APPROVED`. | AUTHORITY_CRITICAL | Pinned (`sria/campaign/**`) |
| `systems/twin_revision.py` (+ `systems/__init__.py`) | `claims/twin_evidence.py` (verdict_authority) | Evidence context identity and the CANDIDATE ban on validation evidence. Reproduced: evidence for geometry G1 resolves as `validation / admitted_in_belief` on G2. The `systems/**` exemption ("answers") was false for this file. | AUTHORITY_CRITICAL (latent: only tests consume it) | Pinned; `systems/**` exemption narrowed to the named answer modules |
| `scenarios/environment.py` (+ `scenarios/**`) | `system_runtime/executor.py`, `execution/multiphysics/runtime.py` | No-extrapolation, max-gap and discontinuity refusals for boundary-condition channels that a certified node records as succeeded | AUTHORITY_CRITICAL | Pinned (new area `system_runtime_dependencies`) |
| `materials/properties.py` (+ `materials/**`) | via scenarios and the system runtime | A missing material uncertainty stays UNKNOWN; sources are never arbitrated | AUTHORITY_CRITICAL | Pinned |
| `multiscale/**` | `system_runtime/authorities.py` | The committed final slow state, uncertainty included, plus run status and resume context binding (review I-2) | AUTHORITY_CRITICAL | Pinned |
| `providers/**` | `claims/discovery_providers.py`; duck-typed by the system runtime | Provider record UNKNOWN default, "failed exposes no outputs", catalog version and digest feed the preflight (review I-2) | AUTHORITY_CRITICAL | Pinned |
| `numerical/**`, `pde/**`, `coupling/**`, `spatial/**` | pinned providers, multiscale and pde | Execution records, participant state contracts, mesh and field identity bound into `PDEProblem.identity` | AUTHORITY_CRITICAL (identity) | Pinned |
| `design/**` | `claims/design_memory.py` only | Search memory classified `search_history_not_evidence`; no evidence, belief, verdict or stop path reads it | DATA/NON-AUTHORITY | Declared edge `(claims/design_memory.py → design/**)`. Residual: the DesignHistory chain check is uncertified. |
| top-level `providers/<adapter>` (`forge_*`) | `providers/catalog.py` dynamic import | Adapter registration | UNRESOLVED → declared | `DYNAMIC_REACH` entry. Residual: adapter code is uncertified. |
| `systems/admissibility.py` (F6) | none certified (only `systems/products/drone_coupled.py`) | Physical admissibility of system-pack results, which are not certified results | IRRELEVANT to certified results | Deliberately **not** exempt, so any future certified importer fails. EXISTING_RISK: F6 is mutation-proven, not certificate-covered. |
| `engcore.studies` via `api_snapshot.py` (computed import) | certification_control, not a seed | Describes signatures only | DATA | Residual (LOW): a pinned non-seed file stops traversal. Nothing imports `api_snapshot`. |

Result: 71 more `src` files are pinned (440 → 511), with one declared non-authority edge. This is not a whole-tree
inclusion: `mcp/**`, `product/**`, `planning/**`, `design/**`, `domains/**` (exempt) and the rest stay out.

## 3. Findings

| Finding | Before | Reproducer | Root Cause | Fix | Tests | Residual Risk | Status |
|---|---|---|---|---|---|---|---|
| F-1 certified modules import uncertified authority code | `e193e573` | `dc26175d`, `test_a_committed_edit_to_a_dependency_that_decides_certified_meaning_fails_verification` ×7: `verify_certificate(...).ok == True` after each committed hostile edit | Closure derived only from 6 roots; certified leaf modules never walked | `certified_dependency_problems` in build and verify; scope extended (+71 files) | 7 negative (one per dependency) + fixture positive control + design-edge positive control | Duck-typed runtime objects (`Any`) are invisible to any static closure | FIXED (code), recert pending |
| F-2 `systems/**` exemption false for `twin_revision.py` | `e193e573` | `twin_revision` row of the F-1 reproducer; agent replay: geometry G1 evidence accepted for G2 | Package-wide "answers" exemption | Pinned; exemption lists the answer modules by name | `test_the_exemption_no_longer_covers_systems_as_a_whole` | none known | FIXED |
| F-3 closure evasions (review I-1, I-3, I-4, I-5) | `6d62e5cf` (first fix) | `test_a_declared_edge_excuses_its_importer_and_only_its_importer`, `..._behind_an_exempt_one_...`, `..._control_plane_package_init_is_a_seed`, `test_review_i5_*` (8 forms), `..._lookalike_names` | Package-wide exclusions; traversal stopped at exempt modules; `__init__` not a seed; loader aliases | Edge table; traverse through exempt modules; `__init__` seeds; builtins and `vars()` loaders; package star | all listed | `DYNAMIC_REACH` is per file; pinned non-seed `api_snapshot.py` | FIXED |
| F-4 Windows case-insensitive closure flake | `e193e573` | `--verify` at `623149f3` printed a `Uncertainty.py` PROBLEM; 2/60 `PYTHONHASHSEED` values reproduce it | `is_file()` is case-insensitive; set order picks the spelling | `_spelled_on_disk` | `test_the_closure_names_files_with_their_on_disk_spelling` | none | FIXED (fail-closed before) |
| F-5 nested pytest summary credited as a kill (`f869a737`) | `e193e573` | `test_a_nested_summary_block_in_captured_output_is_never_credited`: `['test_guard_named']` before the fix | First summary block read | Read only the last block | that test + the existing parser tests | none | FIXED (`a49e8d12`) |
| F-6 `main` is not certified | `e193e573` | `--verify` FAILED; CI `test_the_certificate_describes_this_tree` | PR #142 changed harness files after recertification and merged with gates red | Owner recertification (OD-3) of the intended HEAD | — | — | **BLOCKED_OWNER** |
| F-7 V4 mutation shards cannot run on GitHub runners | `e193e573` | CI logs of PR #140/#142: `MUTATION ROUND PROBLEM: pristine .git refers to external Git storage or rewritten history`. Locally, `git sparse-checkout disable` writes `.git/config.worktree`. | `actions/checkout` disables sparse checkout, which creates `config.worktree`. `mutation_workspace.py:322-326` (added `4f2cdf4b`, while workflows were manual-only) refuses it. | Not changed. Proposal: in the V4 and formal jobs, delete `.git/config.worktree` only when its content is exactly the sparse-disable stanza, else fail. Needs a pushed CI run to verify. | — | Recertify workflow cannot go green on GitHub; local assurance is unaffected | CURRENT_DEFECT (CI, fail-closed), owner |
| F-8 CI flakes | — | `fast312` timing guard (#140); xdist `worker_lost_before_target` refused for "infrastructure events" (#142) | Timing on shared runners; the lost-worker scenario races to two refusal reasons | none | — | Both refuse (fail-closed) | EXISTING_RISK; NOT_REPRODUCED in WSL (see §5) |
| F-9 in-process forged campaign checkpoint | — | Agent analysis: `runner.restore()` accepts a re-chained event log; `stop_review_outcome` is restored unchecked | Unkeyed SHA-256 chain (the accepted residual "F5 run records are unkeyed") | none (outside the dependency gap) | — | A forged record; belief and gateway unaffected | EXISTING_RISK → proposed next bounded task |

### Fixed-finding record

* **Before SHA:** `e193e573`. The failing proof is in `docs/work/br15-evidence/reproducer_before_fix.txt` (`dc26175d`: 14 failed,
  2 passed) and `reproducer_before_fix_final.txt` (the final test file against the base verifier: 23 failed, 2 passed).
* **Files changed:** `tools/certification/core_certificate.py`, `tests/test_certified_dependency_closure.py` (new),
  `tests/mutation_guards.py`, `tests/test_formal_xdist.py`, and docs.
* **After-fix evidence (Windows 3.14, serial):** `tests/test_certified_dependency_closure.py
  tests/test_certificate_verdict_scope.py tests/test_core_certificate.py`. Result: 90 passed, 1 skipped, 1 failed
  (`test_the_certificate_describes_this_tree`, expected until recertification). Closure tests at `01073787`: 68 passed.
  Real tree: `certified_dependency_problems == []` and `authority_closure_problems == []`. Linux tiers: §5.
* **Compatibility:** no `src/engcore` byte changed, so serialization, replay and import identity are untouched. The
  production registry pin is identical: 456 `evidence_code` files with equal digests, and `registry_problems == []`
  against the stored certificate. `REQUIRED_CERTIFICATE_AREAS` (Core V3) is unchanged: areas were extended, not
  renamed. `TOOL_VERSION` is 2.5.0.
* **Certification scope:** areas `assurance_admission` and `verdict_authority` changed patterns, and a new area
  `system_runtime_dependencies` was added. The stored certificate fails `scope_problems` until recertified. Every
  newly pinned file becomes a recertification trigger, because `recertification_scope.py` derives triggers from
  `SCOPE`. No support level, verdict or validation level was strengthened: the change only adds refusals.

## 4. Work package E — GitHub governance

| Item | Host state (read 2026-10-14) | `BRANCH_PROTECTION.md` | Gap |
|---|---|---|---|
| `main` protection | `protected: false`; `/branches/main/protection`, `/rules/branches/main` and `/rulesets` all return HTTP 403 "Upgrade to GitHub Pro or make this repository public" | ruleset with PR required, 1 approval, no force push, no deletion | **Not enforceable on the current plan** |
| Merge methods | `allow_merge_commit`, `allow_squash_merge` and `allow_rebase_merge` are all `true` | merge commit only | **Squash and rebase must be disabled** (available on the free plan) |
| Required status checks | none (cannot be read) | none, by design | consistent |
| Automatic workflows | Tests runs on PRs and pushes to main; Recertify runs on PRs; Branch Policy runs on pushes to main. All three ran. | as documented since F8 | Branch Policy fails on the 403; Recertify V4 cannot pass (F-7) |
| PR merges | #140 merged before Recertify finished; #142 merged with `fast312` and 8 V4 shards red and formal pending | "a branch is not ready merely because its tests were run" | Certified files reached `main` without recertification (F-6) |

GitHub checks remain transport, not attestation. Scientific assurance stays with the local certificate.

**Owner actions (exact):**

1. Settings → General → Pull Requests: untick "Allow squash merging" and "Allow rebase merging", leaving "Allow merge
   commits".
2. Either upgrade the owner account to GitHub Pro, or make the repository public. Then create the ruleset in
   `BRANCH_PROTECTION.md` §"Required branch rules" and re-run Branch Policy
   (`python -m tools.certification.branch_policy --repository sharq-labs/forge --branch main`).
3. Do not merge a PR that changes a certified file until `local_assurance` has produced a certificate child for it.
   PR #142 is the counterexample.
4. Run hardened recertification (OD-3) on the intended HEAD: this branch after review, or `main` plus this branch.
   In the WSL clone, use `python -m tools.certification.local_assurance run --reuse --repository sharq-labs/forge
   --python311 .forge/venvs/3.11/bin/python --python312 .forge/venvs/3.12/bin/python` (about 3.4 h).
5. Decide on F-7 (CI V4 workspace admission vs `actions/checkout`) and on F-9 (keyed campaign records) as the next
   bounded tasks.

## 5. Gates run

| Gate | HEAD / env | Result |
|---|---|---|
| FAST `-m "not expensive" -n 4` | base `e193e573`, WSL 3.12 | 10374 passed, 156 skipped, 1 failed (`test_the_certificate_describes_this_tree`) |
| FAST | fix `a22869d4`, WSL 3.12 | 10415 passed, 156 skipped, 1 failed (same; recertification pending) |
| FAST | fix `a22869d4`, WSL 3.11 | 10415 passed, 156 skipped, 1 failed (same) |
| impact selection (31 modules) | fix `a22869d4`, WSL 3.12 | 940 passed, 1 skipped, 1 failed (same) |
| regression `tools/forge_check.py --regression` | fix `a22869d4`, WSL 3.12 | 256 passed, exit 0 |
| certificate closure suites (serial) | Windows 3.14 | 90 passed, 1 skipped, 1 failed (same) |
| hardened recertification / local_assurance / Formal / V4 | — | **NOT RUN** (owner, OD-3) |

The failure sets of base and fix are identical; there is no new failure. The PR #142 CI flake
(`worker_lost_before_target`) did not reproduce in either FAST run. Exact commands are in `docs/work/PROGRESS.md`
(2026-10-14, BR-15).
