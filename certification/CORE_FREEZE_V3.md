# Core Freeze V3 — hardened routed uncertainty

**Tag:** `v3.0-core-freeze` (created after merge) · **Candidate:** `1c734ed22296c64188567d3fe50279d8d71bc38e`
**Manifest:** `certification/core_freeze_v3.json` · **Assurance:** `certification/core_freeze_v3_assurance.json`
**Verifier:** `python -m tools.certification.core_freeze_v3 --verify` · **Audit:** `docs/audits/MAIN_AUDIT_2026-09-15.md`

## Why a third freeze

The main adversarial audit of 2026-09-15 rejected freezing the core at `1edddd7`: 7 P0, 23 P1, 22 P2 and 12 P3
findings, among them assessments of one subject admitting another, a caller-built obligation set standing in for
the charter's, any declared threshold set awarding cross-solver validation, a one-start multistart earning
SUPPORTED on a bimodal posterior, and a collapsed 3×3 grid reported with zero parameter uncertainty.

The Hybrid UQ fixes re-derive every route claim from the numbers a record carries. Core Freeze V2 pins as its
identity references literal records of exactly the kind now refused — a DOWNGRADED route whose thresholds are
missing and whose uniqueness its own starts do not imply — so the V2 serialization contract cannot hold on a
correct tree. Under `docs/CORE_FREEZE_POLICY.md` §10 an incompatible change is a new freeze, not a compatible one.

V1 is untouched. The frozen API surface does not move: V3 changes behaviour and records, not shapes.

## What binds

| check | meaning |
|---|---|
| `v1.freeze_verifies`, `v1.manifest_unchanged`, `v1.symbols_preserved` | Core Freeze V1 still verifies: 194 frozen symbols, digest `c80e6418…`, and V1's serialization contract (`ScientificResult` still `/1`–`/4`) |
| `v2.history_unchanged` | the V2 manifest is recorded by digest and never rewritten |
| `api.unchanged_from_v2`, `api.pinned_snapshot_bytes` | the live frozen surface is exactly what V2 recorded — frozen digest `fd7d3f9f…` |
| `v3.serialization_and_identity` | eight identity references, each consistent with its own numbers, round-trip byte-identically and refuse unknown schemas |
| `v3.v2_fixtures_still_refused` | the supersession is measured on every verify, not asserted |
| `v3.vocabulary`, `v3.no_exact_posterior`, `v1.thin_ridge_repair_in_force` | the route vocabulary, no class claiming exactness, the V1 repair still in force |
| `certificate.verifies`, `certificate.covers_required_areas` | the certificate covers `assurance_admission`, `core`, `evidence_identity`, `execution_trust`, `inference_admission`, `predictive_representation`, `routed_uncertainty` — every area the audit found a false accept in |
| `assurance.*` | required suites green, the formal population killed with a green control, the trust population killed with a green control |

## Assurance on this candidate

| suite | result |
|---|---|
| `FAST` | 6055 passed, 6 skipped |
| `hybrid_uq_focused` | 236 passed |
| `audit_regressions` | 452 passed |
| `api_snapshot_v1` | 17 passed |
| `api_snapshot_v2` | 5 passed |
| `freeze_manifest_v1` | 36 passed, 1 skipped, 2 deselected |
| `freeze_manifest_v3` | 15 passed, 1 skipped |
| `certificate` | 206 passed, 1 skipped, 2 deselected |

**Formal mutation population (GUARDS 1–35): 284/284 killed by the guard each names**, four shards of 71, each with
a green unmutated control (`benchmarks/core_freeze_v3/FORMAL_SHARD_*.log`, population `a05dcdad…`, each transcript
checked with `mutation_population.log_problems` before it was recorded).

**Trust-hardening population: 20/20 killed**, green control, every kill attributed to the test the mutation names
(`benchmarks/core_freeze_v3/TRUST_MUTATIONS.json`). Measured at `999dbdf`; `src/`, the runner and its six suites are
byte-identical at the candidate.

The first round of this population was not clean, and that is the point of running it: one mutation was GREEN
(the grid predictive's judgement, shadowed by the resolution refusal the same audit added — now isolated by its own
test) and two were red for another guard (the CSTR and K4 liquid-phase conditions, which actually refuse at import).
All three were corrected and the whole population re-run.

On a recertification source commit the four certificate/freeze self-checks read the previous certificate by
construction. They are deselected here exactly as the CI source gates deselect them, and the recertify workflow's
certificate-only child runs them.

## Capability claim

Core V3 keeps Core V2's routed uncertainty surface and makes each route's claim a function of evidence the record
carries. `route_uncertainty` returns, deterministically and with every route it considered recorded: POSTERIOR_GRID
when a supplied tensor grid of at most 5 parameters, bound to the request's parameter names and dataset and whose
weights are the normalized likelihood, passes the repaired V1 resolution checks (a collapsed posterior is refused
before any small-grid waiver); LOCAL_GAUSSIAN_APPROXIMATION when its validity diagnostics support it, at a cost of
4p+1+2p² forward evaluations for the axis and pairwise-diagonal probes plus a deterministic multistart of at least
max(6, 2p+2) starts — below that search the route is at most DOWNGRADED, and a converged refit below the estimate's
objective refuses; POSTERIOR_GRID rebuilt from the local covariance when a rebuild policy is supplied, p ≤ 5, the
rebuilt table agrees with the forward model at deterministic spot-check nodes and the V1 checks accept it; the local
Gaussian DOWNGRADED with its reasons; or REFUSED with no numbers. Identifiability widths of log parameters are
unit-invariant. Predictive uncertainty keeps parameter and measurement uncertainty separate, probes pairwise
diagonals and Σ∇g, judges nonlinearity against the parameter uncertainty, and names model discrepancy as not
modelled. Every record is re-derived from its carried numbers on read. No approximation class is an exact posterior.

## Non-claims

Recorded in full in the manifest. The four deferred items are shape changes the audit showed are needed and V3
deliberately does not make: applicability fields on inference results, content binding inside
`require_posterior_was_fitted_here` and `assess_predictive_observation`, a field tying a `ValidationCheck` to the
result it qualifies, and consensus execution bindings as a dataclass field. Each needs its own compatibility review
and freeze. Serialized digests remain integrity checks, not authority.
