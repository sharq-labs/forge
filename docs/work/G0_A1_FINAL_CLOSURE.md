# G0/A1 final closure and Genesis transition readiness (2026-10-14)

Local branch `integration/g0-a1-unblock` (worktree `D:/forge-g0a1`). It is `origin/main` `e193e573` (still the remote main
on 2026-10-14) plus `fix/br15-authority-closure` plus `feat/br16-genesis-lite-benchmark`.

**Nothing is pushed, opened as a PR or merged.** Hardened recertification, FULL local assurance and any formal campaign
were **not** run. No owner decision is assumed. BR-17 and BR-18 stay closed. The earlier report is
[G0_A1_UNBLOCKING.md](G0_A1_UNBLOCKING.md); the OD-6 package is
[OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md](OD6_GENESIS_EPIC_MIGRATION_PACKAGE.md).

## 1. Integration integrity

| Check | Result |
|---|---|
| Ancestry | `e193e573` → BR-15 tip `3c28bedf` and BR-16 tip `427dd66b`, merged with `--no-ff`. Every file in `e193e573..HEAD` is identical to the BR-15 or BR-16 tip, except `docs/work/{ACTIVE_PLAN,PROGRESS,G0_A1_UNBLOCKING,G0_A1_FINAL_CLOSURE,OD6_GENESIS_EPIC_MIGRATION_PACKAGE}.md`. |
| Tested vs candidate | The earlier tested `eb2720f9` and candidate `08c256c3` differed only in `docs/work/G0_A1_UNBLOCKING.md` and `PROGRESS.md`. Neither is in any certificate area nor a recertification trigger (checked with `core_certificate.enumerate_area` and `recertification_scope.requires_recertification`). Nothing executes or pins them; `tests/test_agent_workflow_contract.py` only requires PROGRESS to contain two fixed phrases. |
| Certificate-only files | `certification/` is unchanged from `e193e573`; the certificate child is reserved for recertification. |
| Unrelated changes | None. A first attribution script mislabelled `.github/workflows/recertify-hardened-core.yml` as integration-only; the blob is identical to BR-15's (`e9a977f3`). |
| Worktree | Clean apart from this sprint's committed documents. |

## 2. Findings and closures

Every fix below came with a reproducer that fails first and was committed red before the fix. The reviews were
independent and static; tests were run separately (§3).

### BR-15 certification import closure (`tools/certification/core_certificate.py`, tool 2.6.0)

| Id | Finding (review) | Reproducer → fix | Status |
|---|---|---|---|
| C1 | Loaders reached without a direct call: `__import__` with `fromlist` or level, a loader stored in a container, `importlib.__dict__[…]` | `bb4f08d9` (4 fail) → `aedc7b24` | closed for these forms |
| C2 | Dynamic loads in exempt modules on the walked path were not checked, and declared DYNAMIC_REACH targets were never traversed | `bb4f08d9` (2 fail) → `aedc7b24`. Real-tree mutation: adding `import engcore.systems.admissibility` to `domains/thermal_models/nafems_t3.py` gives `[]` with the old tool and is reported by the new one. | closed |
| C3 | A compiled module (`.pyc` in `__pycache__`, `.so`, `.pyd`) could run instead of pinned source while every digest matched | `bb4f08d9` (4 fail) → `aedc7b24` (tracked files) | closed |
| R2 | Nine further loader spellings (submodule aliases, `__dict__.get`, `vars(m).get`, `__builtins__[…]`, `e = exec`, `map(eval…)`, changed `sys.path`, `SourceFileLoader`, `pydoc.locate`) and an untracked unchecked-hash `.pyc` | `912539ac` (10 fail) → `26f2505c`. Precision tests: `x.locate()` and reading `sys.path` are not flagged. | closed for these forms |
| R3 | `importlib._bootstrap._gcd_import`; a symlinked `__pycache__`; a planted timestamp `.pyc` with a forged header read by the registry probe | `3c28bedf`: the private API is flagged (old tool `[]`, new `[2]`), symlinks under `src/engcore` are refused, and the probe runs with its own `-X pycache_prefix` | closed |
| — | **Static loader detection cannot be proven complete** (`operator.attrgetter`, `sys.modules[...]`, `pickle.loads`, and any spelling not yet listed) | A runtime cross-check (`sys.addaudithook` import/exec trace during the self-checks) is proposed, not implemented | **UNRESOLVED (declared)** |
| P1 | Runtime-injected objects (a caller-supplied `CapabilityRegistry`, first-wins registries in `claims/novelty.py`, rebinding from uncertified modules in the same process) are outside any file-digest certificate | Static evidence: nothing in `src/` registers into them today | NOT_VERIFIED (declared residual) |
| — | DYNAMIC_REACH exempts a whole declared file rather than its load sites | — | residual (a recertified edit is reviewed) |
| F-9 | Restored stop-review state (BR-15) | Earlier `01f9bee6`…`9df87275`; this review rejected every attack | closed. Residuals: the unkeyed chain; the Arbiter decision behind a review is not logged. |
| F-7 | CI V4 shards versus `actions/checkout` | Reviewed: fails closed. **Never run on GitHub.** | not verified in CI |
| Q3 | `design_memory → design/**` exception | REJECTED as a vulnerability. Residual: the edge stops traversal into `design/**`. | — |

Certification scope impact: no new SCOPE area. `tools/certification/core_certificate.py` (`certification_control`)
changed, and so did tests (triggers). All of this was certification-sensitive already; one recertification covers it.

### BR-16 Genesis-lite: v0.1 → v0.2 (new identity `genesis_lite.blindfold_l5.v0_2`, preregistration `878e6812…`)

v0 (`f99fcfbd…`) and v0.1 (`94efff08…`) and their pilots are preserved byte for byte (tested). **v0.1 is superseded and
never formal.**

| Id | Finding | Reproducer → fix | Status |
|---|---|---|---|
| D1 | An invalid or omitted registered baseline silently weakened the comparator (*removing evidence increased assurance*) | `a1b5ab9b` → `f3ca0e63`: every registered non-adversarial arm must be complete | closed |
| D2 | The grid and the record set were chosen by the caller; off-grid records steered the baseline | `FORMAL_GRID` is preregistered; another grid or off-grid records claim nothing; the code must rebuild the preregistration | closed (best-of-N attempts stay procedural, OD-8) |
| D3 | Discovery could be traded for control credit | Non-inferiority on every kind | closed |
| D4 / D6 | Lift from out-of-family discoverable worlds, and from REPRESENTATION_LIMITED cells (the rule was not implemented) | The candidate is capped at its comparator there | closed |
| D5 | No pairing without ids; per-kind references never pair-checked | Missing ids are a problem; every arm is pair-checked against the candidate | closed |
| D7 | Stimulus (renaming, trap template, wording) differed by arm name | `stimulus_key` per world set; only the pseudonym is per run | closed |
| — | Credit not bound to the table, its outcome or evaluator agreement; candidate could take a registered name | `f3ca0e63`, `80f798ba` | closed |
| PF | **Found by the v0.2 pilot:** the literal audit refused one world set for all 13 arms (a hidden exponent 0.642 equalled a public region bound 0.642). With the completeness rule, any such world set made a formal lift impossible. | `e7616785` → `80f798ba`: a world set screened identically for every arm is excluded for all alike; more than 5% screened is a benchmark defect. The audit is unchanged (still strict). | closed |
| A2 | The run-time identity was copied from the `.sha256` file, so edited code ran under the committed label | `f18bc4fc` → `4a302959`: the harness compares code digests with the preregistration and records the identity only when they match | closed |
| A1-low | Screened records are trusted as written | Same trust model as all unsigned records; the external evaluator recomputes them | residual (OD-8) |

Superseded, uncommitted pilot runs (roots retired, logs kept outside the repo):

| Preregistration | Runs | Invalid | Log sha256 | Note |
|---|---|---|---|---|
| `7cc71b13` | 1,560 | 13 | `6e70c72a…` | the PF finding |
| `ddc7c3a6` | 1,560 | 0 | `ca0716f3…` | — |

Committed pilot (`4a302959`, preregistration `878e6812`):

- 1,560 runs, **0 invalid**, 0 screened, 384.8 s on WSL 3.12 (MEASURED).
- Run log sha256 `d504f2e3…`.
- Strongest non-adversarial arm: `space_filling` (+3.129), then `careful` (+3.117).
- Floors: `always_law` −4.717, `always_insufficient` +1.5, `always_refuse` +1.0.
- In-family share: discoverable 0.433, spurious 0.383, confounded 0.4.
- Formal baseline ESTIMATE: 31,200 runs ≈ 6,608 s (95% 6,598–6,618).

Scientific claim limits (must be stated in any A1/A2 claim):

1. The joint endpoint is mostly **control classification**. An oracle that never proposes a law would score about 3.5,
   above every arm. The non-discoverer `single_setting` scores +2.48.
2. Law credit is **predictive adequacy within tolerance**, not structural recovery.
3. About 57% of discoverable worlds lie outside every run arm's family. PySR, BoTorch, PySINDy and full-grammar
   enumeration are NOT_AVAILABLE, so v0.2 caps any lift there and makes no discovery-only claim.
4. Per-kind references are refusal floors on three control kinds (`always_refuse`, `always_insufficient`). A future
   candidate must refuse about as reliably as those floors (margin 0.10).
5. Compute is not equalised beyond the escrow's query budget and a 600 s per-message timeout.

### Escrow security

| Label | Status | Evidence |
|---|---|---|
| IN_PROCESS_ATTACK_BLOCKED | yes, with `proposer_process` | Heap-scan and stack-walk attacks succeed in-process and find nothing isolated (tests). |
| PROCESS_ISOLATION_TESTED | yes (same account) | Measured probe (`D:/forge-g0a1-final-evidence/escrow_probe_2026-10-14.txt`):<br>• environment scrubbed; working directory empty; `/proc/<ppid>/mem` refused (YAMA 1);<br>• **but** `/proc/<ppid>/cmdline` and `environ` are readable. The proposer found `--root-file`, read the root and answered 5 of 6 cards with the true law while the run stayed **VALID**;<br>• outbound TCP worked; a detached child outlived the campaign; the benchmark package was writable. |
| DEPLOYMENT_BOUNDARY_VERIFIED | **no** | No deployment exists yet (OD-20). |
| Overall | **SECURITY_BOUNDARY_NOT_PROVEN** | Same-account runs are never formal evidence (preregistered). |

## 3. Gates

See PROGRESS for the exact commands. The final-HEAD results are filled in below from the actual run.

| Gate | HEAD | Result |
|---|---|---|
| Genesis-lite suite | BR-16 `4a302959`, Windows 3.14 / WSL 3.12 | 94 passed (both) |
| Certified dependency closure | BR-15 `3c28bedf`, Windows 3.14 | 58 passed, 1 skipped (symlink test needs privileges) |
| Certificate and BR-15 suites | BR-15 `aedc7b24`, Windows 3.14 | 193 passed, 1 skipped, 1 failed (`test_the_certificate_describes_this_tree`: expected drift until recertification) |
| v0.2 pilot | `4a302959` | 1,560 runs, 0 invalid |
| `forge_check --changed --base e193e573` | integration `7d6d398b`, WSL 3.12 | 10549 passed, 1 failed (the expected certificate test) |
| FAST 3.12 and 3.11 | `7d6d398b`, WSL | each 10549 passed, 156 skipped, 1 failed (same test, expected) |
| Focused set and regression | `7d6d398b`, WSL 3.12 | 169 passed; 256 passed, exit 0; every pin check `[]`; prereg rebuilds |
| Hardened recertification, FULL local assurance, formal campaign | — | **NOT RUN** (owner) |

## 4. Owner decisions

| Decision | Ready? | What is asked |
|---|---|---|
| **OD-3** | Source ready for **one** hardened recertification of the final HEAD in PROGRESS, unless OD-6 C is approved first (then include the migration PR to avoid a second recertification). Residuals: static loader completeness UNRESOLVED; runtime-injected objects NOT_VERIFIED; F-7 never run in CI. | Approve `local_assurance` on that SHA, and the push or PR that lets CI exercise F-7. |
| **OD-19** | v0.2 is FREEZE_READY. **v0.1 is not suitable** (D1–D7). | Approve v0.2 for formal preregistration with the claim limits in §2. |
| **OD-20** | Not met. | Choose and test a deployment in which the proposer cannot see operator processes or command lines (PID namespace or separate host/container), cannot read operator files (separate account or read-only filesystem without them), has no network, cannot persist processes beyond the campaign, and cannot write benchmark code. Rerun the escrow probe there before any formal run. |
| **OD-8** | Requirements set. | Name an evaluator outside FORGE without write access. It receives the frozen preregistration, the append-only run log (every attempt, every candidate name) and the answer keys after sealing; it recomputes credits, screens and the lift decision, and publishes agreement per universe; record a deadline. |
| **OD-18** | ESTIMATE ready. | Approve ≈ 6,608 s single-machine baseline compute plus OD-20 overhead (UNMEASURED). The Mind, LLM-ablation and model-swap costs are UNMEASURED and need their own estimate before A2. |
| **OD-6** | Package ready. | Option C (schema /2 research-program epic), Option A (one exception), or neither. |
| **OD-1** | Unchanged. | Branch protection needs a paid plan or a public repository; disable squash and rebase merges. |

**Not claimed:** G0 PASS (requires recertification), A1 PASS (requires the formal tier and OD-3/8/18/19/20), Minimal Mind
functional or validated, BR-17 or BR-18 progress.
