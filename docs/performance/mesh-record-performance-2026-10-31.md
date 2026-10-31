# Mesh record serialization performance, 2026-10-31

Classification: **MEASURED engineering performance on public synthetic fixtures**.
This is not physical validation, formal certification, or project-wide speedup.

The thermal vertex/dual path repeatedly reconstructs the same mesh material
inside one serialization call. `MeshVersion1D.to_dict` now builds that material
once and hashes the returned representation. `VertexState1D.to_dict` reuses the
mesh version already present in its current support representation. Neither value
is retained across calls. Issuance, fresh snapshots, lineage traversal, cycle
checks, mutation detection, solver settings and scientific budgets are unchanged.

Reuse applies only to exact concrete records with builtin string/float/tuple
representations. Eligibility checks do not convert or validate values and fall
back for custom or malformed representations. The complete original expression
preserves subclass overrides, custom conversion/iterator behavior and exception
order. This conservative eligibility is intentional; `frozen=True` alone does not
establish deep immutability.

## Revisions and scope

- Baseline: `d05b25eec565b48b4a024799cbda4f046e872d6c`.
- Measured and aggregate-tested implementation: `458e06215901ada5e2f7d70cdc769b70e0a0b81d`.
- Metadata-only provenance correction: `ac14845a8b423e40643b291bc42fb3558a60d148`;
  source, test code and golden fixture bytes are identical to the measured commit.
- Local isolated branch: `codex/mesh-record-performance`. The original published
  `codex/genesis-v04-performance` checkout remains unchanged.
- Source changes: `src/engcore/numerical/mesh_adaptation.py` and
  `src/engcore/numerical/vertex_state.py`; 27 focused tests plus baseline golden
  root/refine/coarsen mesh and state records.
- Owner authorization: 2026-10-31 14:17 UTC, first mesh/record improvement locally.
  No push, merge, formal/OD-3, 1000-campaign run or additional workers.
- Other project-wide review candidates, including runtime Mapping/error paths,
  external-provider configuration and persistent caches, were not implemented.

## Final matched timings

Python 3.12.3, existing `/opt/forge-mvp-20261028/.venv`, native WSL checkouts.
One outer worker and one numeric thread in **both** revisions. Each fresh process
warms the fixture, then times a fresh instance; three A/B pairs alternate execution
order. Every row includes the same setup and verification reads in both revisions.
No profiler runs inside the timed measurement. OS cache/frequency and unrelated
desktop load are not fully controlled; three repetitions are not a general
confidence interval. Compare the matched revisions, not earlier absolute timings.

| Public synthetic workload | Baseline mean ms | Candidate mean ms | Time reduction | Speed ratio |
|---|---:|---:|---:|---:|
| Set up 32-cell thermal session | 220.284 | 196.007 | 11.02% | 1.124x |
| Set up + one step + result read, 32 cells | 664.438 | 525.560 | 20.90% | 1.264x |
| Set up + four steps + result read, 8 cells | 888.404 | 666.799 | 24.94% | 1.332x |
| Set up + two steps + result read, 32 cells | 1266.619 | 941.937 | 25.63% | 1.345x |

All four workloads have identical serialized mesh, full thermal-step records,
output values and SHA-256 across all six measured runs: **24 exact wire checks**.
No fields are removed before comparison. Initial guesses, boundary conditions,
timesteps, tolerances and process counts are unchanged. These are equilibrium
synthetic cases, not large-mesh or general end-to-end performance claims.

Separate profiles of the one-step 32-cell workload explain the reduction:

| Operation | Baseline calls | Candidate calls |
|---|---:|---:|
| `MeshVersion1D.version_id` | 2580 | 1821 |
| `MeshVersion1D._material` | 2965 | 2206 |
| `timeline.canonical_digest` | 102310 | 76889 |
| `_IssuedRecords.snapshot` | 673 | 673 |
| `_IssuedRecords.require` | 665 | 665 |
| `_IssuedRecords.verify` | 392 | 392 |
| `MeshLineage1D.verify` | 181 | 181 |
| `AdaptiveMesh1D._guard` | 159 | 159 |
| `VertexDualAdapter1D._guard` | 50 | 50 |
| `VertexDualAdapter1D._require_parents` | 44 | 44 |

The ASTs of all eleven selected issuance/lineage/adapter guard methods and their
profiled call counts are unchanged. Lower hash-construction counts do not come
from omitted verification. Profile cumulative times overlap and are not used as
speedup estimates.

## Verification and independent review

Baseline golden fixtures were generated only from clean d05b25ee. Focused tests
cover nested mutation after serialization, equal-valued unissued replacements,
returned-payload edits, refinement/coarsening, subclasses, custom support side
effects, one-shot iterators, values becoming builtin during serialization,
stateful numeric conversion, missing-field first exceptions and access order.

The independent `forge-scientific-review` reviewer initially required changes for
eligibility timing and fallback evaluation order. Both were corrected before
freezing 458e0621; the final static verdict is **PASS**. The reviewer did not run
commands. PASS is a review result, not executed validation.

An earlier broader pack passed 201 tests in 74.553s, before the final guard
refinement. The frozen candidate separately passed all 27 focused tests and the
dependency guard. The aggregate gates below provide coverage after that refinement.

<!-- FINAL_GATE_RESULTS -->
| Ordinary gate | Passed | Failed | Skipped | Wall seconds |
|---|---:|---:|---:|---:|
| FAST on 458e0621 | 13810 | 4 | 184 | 384.003 |
| SCIENTIFIC on 458e0621 | 14394 | 4 | 185 | 650.223 |

These aggregate runs were red: two unchanged baseline certificate failures plus two new inventory failures because the new synthetic golden fixtures lacked explicit provenance declarations. The original failures and logs are retained. The metadata-only follow-up revision `ac14845a8b423e40643b291bc42fb3558a60d148` adds two exact SYNTHETIC declarations and their generation description. It changes no source, test code, fixture bytes, scanner, rule or gate. The complete domain/provenance test directory plus all 27 serialization tests then passed: **60 passed, 0 failed, 0 skipped**, in 49.015s. Historical-source hashes resolve to the actual immutable baseline commit. Independent static review of this correction: PASS.

The two new inventory failures are resolved by that executed follow-up; the two baseline certificate failures remain unresolved. Full aggregate suites were not repeated after this metadata-only correction, so no aggregate green result or invented revised aggregate count is claimed. Skip node identities match the retained pre-change gates exactly.
<!-- END_FINAL_GATE_RESULTS -->

The known baseline certificate failures are not masked or called green:

- `tests/test_core_certificate.py::test_the_certificate_describes_this_tree`
- `tests/test_core_certificate.py::test_the_certificate_records_the_v1_relationship_truthfully`

The focused certificate comparison ran on both clean baseline and candidate:
27 passed and the same two failed on each. No frozen certificate was regenerated.

## Reproduction and retained evidence

Task workspace: `C:/Users/dev_kaeem/Documents/Codex/2026-10-31/task-2`.
Native evidence: `/home/dev_kaeem/forge-mesh-record-evidence-20261031`.
Verified export: `mesh-evidence/` in the task workspace.

- `mesh_bench.py final`, with `FORGE_MESH_CANDIDATE` pointing to the clean native
  final checkout, runs the alternating one-worker comparison. `final-summary.json`,
  six run records, 24 full wire payloads and baseline/candidate pstats preserve it.
- `mesh_guard_audit.py` compares exact method ASTs and existing profile counts;
  `guard-audit.json` records the results.
- `mesh_validate.py run` records exact commands, clean states, logs, JUnit XML,
  failures and skips. Ordinary tests use `-n 4 --dist loadfile`, exactly as in the
  established gate setup; this test parallelism is not a performance optimization.
- FAST: `python -m pytest -m "not expensive" -q -n 4 --dist loadfile`, with the
  dependency guard executed once separately. SCIENTIFIC: `-m "not campaign"` with
  the repository's six CI deselections; their exact names are in the driver and
  command summaries. No validation test or gate was weakened.
- `mesh-scientific-review.md` preserves the independent review and resolutions.
- `mesh_export.py` copies evidence with source/destination SHA-256 verification.

Intermediate candidate1/candidate2 timings and the earlier targeted pass remain
labelled separately. The final measured source is the guarded implementation above.
