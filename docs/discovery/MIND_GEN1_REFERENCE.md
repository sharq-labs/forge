# FORGE Mind Generation 1: sealed reference

This record pins FORGE Mind Generation 1 (Gen1) as a reference, so that Generation 2 can be compared against it. The
machine-readable equivalent is [`mind_gen1_reference.json`](mind_gen1_reference.json). It is rebuilt from git objects
at the Gen1 commit by `python -m benchmarks.battery_rediscovery_v3.gen1_reference --write`. `--check` exits 1 if a
bound file in the working tree differs, or if the record differs from that rebuild. No v0, v1 or v2 file was rewritten
to make this record.

| Status | Value |
|---|---|
| GENERATION | 1 |
| IMPLEMENTED | YES |
| TESTED | YES |
| MEASURED | YES |
| REAL_DATA_SIGNAL | YES |
| SCIENTIFICALLY_VERIFIED | **NO** |
| CERTIFIED | **NO** |
| FORMAL | **NO** |

## Identity

- **Gen1 commit:** `b8160e2101884b9f8018d4d3be5e1a80a8004b2d`, the head of the local branch
  `research/battery-rediscovery-v2`, tree `5c1c69a8d8b847071c9e0723a5429a91023bffd4`. The branch is not pushed.
- **Minimal Mind source:** `engcore.mind.minimal` is byte-exact from `e2b8037c881847a497c32f7ca56f82b95b493727`
  (BR-MIND-01). Its git tree is `17db855067a1d71f8b6da2c28d81f556d12a8905`.
- **Representation and semantics repair:** `engcore.mind.repsem`, git tree `9b25329da6d2928a5f9d711ebdb571495a7f1b5a`.
  - failing-first tests: `db439744`
  - repair: `cac1c584`
  - freeze recheck: `86034639`

The JSON record binds each file of the components below by git blob id and sha256.

| Component | What it is |
|---|---|
| `minimal_mind` | `src/engcore/mind/minimal/*` and `src/engcore/mind/__init__.py` |
| `repsem` | `src/engcore/mind/repsem/*`: roles, scoped claims, named refusals, `ScientificHypothesis`, role-typed binding, assessment and replay |
| `v2_primary_adapters` | `benchmarks/battery_rediscovery_v2/candidate/*`: the five compared arms, three reference arms, the v1 problem view, the declared Thevenin families, run and replay |
| `v1_adapters_and_baselines` | `benchmarks/battery_rediscovery_v1/candidate/*`: the Minimal Mind adapter, and the CAREFUL / FIXED_FIT / ALWAYS_FIT / ALWAYS_REFUSE baselines |
| `repsem_ablation_adapters` | `benchmarks/mind_repsem_v1/{arms,fixtures}.py`: the role-posed load pool reused by v2 |
| `leakage_firewall` | scanner v1 (numeric and text engines), firewall v2 (candidate-material policy, provenance, runtime audit), both mutation suites, the sandbox |
| `v2_reference_protocol` | the v2 evaluator's reference truth protocol, scoring and conclusion rule |
| `platform_dependencies` | `engcore.hybrid_uq.identifiability` and `engcore.inference.calibration`, which Gen1 calls directly. These are not Gen1 code; they are bound so that a platform change is visible. |

**Vocabularies,** copied from the code into the JSON record:
- dispositions: `SUPPORTED`, `NOT_SUPPORTED`, `REVIEW`, `NOT_ASSESSABLE`, `REFUSED` (the last three are non-committal);
- the 10 repsem claim states;
- the 6 refusal reasons;
- the 7 scientific roles.

**Replay format:**
- Arm outputs are compared by content digest after re-execution from the pack.
- Repsem assessments are re-assessed under the recorded roles and must match byte for byte (`EXACT`).
- Minimal Mind traces are checked over the `forge.mind.minimal.trace/1` hash chain (`VERIFIED`).

## Benchmarks bound

| Benchmark | Commits | PLAN sha256 | SEAL sha256 | Verdict |
|---|---|---|---|---|
| battery_rediscovery_v0 | freeze `085d9a7c`, seal `e1be5910`, eval `986cc43c`, amendment `dbf1794c` | `adc3a30f…` | `6d37cffb…` | LEAKAGE_INVALIDATED (amended reading REPRESENTATION_BOTTLENECK, disclosed post-seal) |
| battery_rediscovery_v1 | freeze `53e6a6db`, seal `c0613435`, eval `d516e681` | `3b7e6676…` | `65f9600f…` | REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY (same data as v0; not blind) |
| battery_rediscovery_v2 | freeze `f6229986`, seal `ee3a6946`, replay `6a75d816`, eval `625f5fea` | `85f1b7f3…` | `843c6e14…` | see below |
| mind_repsem_v1 | tests `db439744`, repair `cac1c584` | n/a | n/a | READY_FOR_BATTERY_V2 on synthetic fixtures only |

The JSON record also binds the sha256 of each benchmark's sealed candidate outputs, TRUTH, EVALUATION, REPLAY and
mutation reports.

## Battery v2 standing

- **Verdict:** `REAL_DATA_IMPROVEMENT_CONFIRMED_BY_PREREGISTERED_V2_RULE`.
- **EVIDENCE_STRENGTH:** `LIMITED_SMALL_N`.

The verdict is what the preregistered v2 rule returned. It is not verified science, and this record does not
strengthen it. Its limits:

- Only 5 instances have a decided truth, and only 2 of those are held out. One answer flip can change the result.
- Q1's fitted 1RC is physically degenerate: R1 sits on its 1 Ω bound with τ ≈ 5200 s.
- Q2 reuses the LG HG2 pulse windows that v1 had already seen. They were re-split, so Q2 is not new data.
- The combined arm and the independent reference reached effectively the same optimum. That shows the implementation is
  correct on real data, not that the model physics is right.
- The win is mostly structural. The v1-vocabulary arms cannot judge adequacy or discrepancy at all.
- The regression pack, the SCIENTIFIC tier and certification were NOT RUN.

## What Gen1 does not contain

ScientificWorld, ActionSpace, HypothesisPortfolio, SearchTree, AttemptMemory, Ax/BoTorch, PySINDy/PySR, ModelCritic,
mechanism reasoning. These are Generation 2 topics and are out of scope for this reference.
