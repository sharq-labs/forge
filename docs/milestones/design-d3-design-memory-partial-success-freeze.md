# D3 - Scientific Design Memory / Partial Success V0.1 freeze

Status: **PASS / FROZEN**

Milestone ID: `D3`

## Frozen identities

- Starting frozen checkpoint (MVR1 PASS/FROZEN): `4a5f58408b597beae852c99f0ea4e53201cf99f0`
- Frozen D3 preregistration checkpoint: `809948794977f423a37768363134def943fb8b44`
- Final tested D3 scientific implementation checkpoint: `74d3df10f4ad43b554d7651823443caf00aec952`
- Preregistration: `docs/design-d3-design-memory-partial-success-prereg.md`

The D3 preregistration remained **FROZEN BEFORE IMPLEMENTATION** and was not rewritten after observing tests, experiment counts or adversarial review findings.

## Scope actually delivered

D3 adds a small adjacent domain-neutral design-memory layer beside frozen D0/D1/D2. The experiment justified:

- one adjacent domain-neutral D3 module;
- deterministic scientific-memory serialization;
- deterministic digest and identity semantics;
- explicit D1 attribution verification;
- Layer A scientifically attributable observations;
- Layer B reproducible retention and classification policy;
- deterministic bounded retention;
- exact scope separation;
- byte-identical Layer B reconstruction from stored Layer A plus declared policy.

The experiment did **not** justify a database, service layer, API, UI, LLM, optimizer, system-pack dependency, adaptive experimentation, recombination, Generation 1, or next-experiment planning.

## Layer boundary

Layer A records what was actually evaluated and attributable to exactly one D1 evaluation:

- candidate, design-space, evaluation, result-binding and scope attribution;
- typed assignments;
- typed objective values under the scope projection;
- deterministic entry digest covering Layer A only;
- caller-declared partition keys as opaque bytes.

Layer B records policy-derived retention/classification:

- retention reason membership;
- assessment-context threshold classification;
- cap retained/discarded split.

Layer B does not manufacture scientific truth. A13 passed: the complete Layer B result reconstructed byte-identically from stored Layer A plus the declared policy and assessment contexts.

## Frozen retention semantics

D3 preserves exactly the six preregistered reasons:

- R1 `PARETO_MEMBER`
- R2 `SCOPED_ELITE`
- R3 `NEAR_EXTREME`
- R4 `NEAR_THRESHOLD`
- R5 `DIVERSITY_REPRESENTATIVE`
- R6 `EXPLICIT`

Frozen properties:

- classification occurs before capacity;
- reasons are non-exclusive;
- reasons are not combined into a score;
- tolerance is absolute, caller-supplied, typed, dimensional, finite and `>= 0`;
- Core provides no default tolerance;
- capacity is `250` per scope for E1/E2/E6;
- Tier 1 is `PARETO_MEMBER union SCOPED_ELITE`;
- Tier 1 overflow fails closed;
- deterministic tie-breaking is identity-only;
- offer ordering cannot change the result.

D3 contains no weighted quality score, hidden scalar preference, objective-aware cap ordering, LLM classification, adaptive optimizer, recombination or next-experiment planner.

## Experiment results

### E1 - domain-neutral synthetic retention

PASS.

D1 Pareto/scoped-elite counts matched D3 R1/R2.

### E2 - insertion-order invariance

PASS.

Original, reverse and even-then-odd offer orders produced byte-identical records.

### E3 - assessment change with physics fixed

PASS.

Assessment changed without physics recomputation. Layer A entry digests and scope identity remained unchanged.

Observed strict near-threshold count: `342`.

### E4 - condition/context change

PASS.

The second physical/context scope remained separate. Cross-scope dominance, merge and co-classification each failed closed.

### E5 - attribution adversarial checks

PASS.

Candidate/Twin mismatch, scope mismatch, objective spoof and absent explicit reference failed closed.

### E6 - canonical 1000-candidate evidence run

PASS.

A13 reconstructed byte-identically.

## Canonical E6 evidence

| Measure | Observed |
|---|---:|
| eligible population | 1000 |
| D1 Pareto | 38 |
| D1 scoped elite | 12 |
| R1 `PARETO_MEMBER` | 38 |
| R2 `SCOPED_ELITE` | 12 |
| R3 `NEAR_EXTREME` | 21 |
| R4 `NEAR_THRESHOLD` | 893 |
| R5 `DIVERSITY_REPRESENTATIVE` | 36 |
| R6 `EXPLICIT` | 3 |
| entries with >=1 D3 reason | 904 |
| retained after cap | 250 |
| classified but discarded by cap | 654 |
| unclassified | 96 |
| Tier 1 | 38 |
| retained by D3 but not already represented in D1 Pareto/scoped elite | 212 |
| A13 byte-identical | true |
| all blocking gates | PASS |

Observed reason overlaps from the experiment artifact:

| Overlap | Count |
|---|---:|
| `PARETO_MEMBER&SCOPED_ELITE` | 12 |
| `PARETO_MEMBER&NEAR_EXTREME` | 13 |
| `PARETO_MEMBER&NEAR_THRESHOLD` | 36 |
| `PARETO_MEMBER&DIVERSITY_REPRESENTATIVE` | 1 |
| `PARETO_MEMBER&EXPLICIT` | 0 |
| `SCOPED_ELITE&NEAR_EXTREME` | 7 |
| `SCOPED_ELITE&NEAR_THRESHOLD` | 10 |
| `SCOPED_ELITE&DIVERSITY_REPRESENTATIVE` | 0 |
| `SCOPED_ELITE&EXPLICIT` | 0 |
| `NEAR_EXTREME&NEAR_THRESHOLD` | 16 |
| `NEAR_EXTREME&DIVERSITY_REPRESENTATIVE` | 1 |
| `NEAR_EXTREME&EXPLICIT` | 0 |
| `NEAR_THRESHOLD&DIVERSITY_REPRESENTATIVE` | 30 |
| `NEAR_THRESHOLD&EXPLICIT` | 3 |
| `DIVERSITY_REPRESENTATIVE&EXPLICIT` | 1 |

## Key scientific conclusion

Exact-Pareto/scoped-elite retention alone does **not** preserve all scientifically attributable evaluations identified by the preregistered D3 retention policies.

Under the frozen E6 experiment, `212` of the `250` retained D3 entries were not already represented in the D1 Pareto/scoped-elite archives.

This does **not** mean `212` universally good designs, feasible designs, validated designs, optimal designs or recommendations. It means only that D3 preserved additional attributable scientific observations under the preregistered retention policy.

## Epistemic boundary

D3 remembers attributable scientific observations and reproducible retention decisions.

D3 does **not**:

- create new physical truth;
- claim feasibility;
- claim safety;
- claim model adequacy;
- claim universal superiority;
- learn causal relationships;
- generate hypotheses;
- alter D2 generation;
- perform recombination;
- choose the next experiment.

Retention means only that an explicit caller-declared retention rule matched an attributable evaluation.

## Targeted test gate

D3 targeted suite against implementation source `74d3df10f4ad43b554d7651823443caf00aec952`:

- `10 passed`;
- `0 failed`;
- `0 errors`.

The targeted suite covered all six predicates, multiple reasons on one entry, boundary equality, zero tolerance, invalid tolerance, dimensional mismatch, cap binding, Tier 1 overflow, deterministic identity ordering, offer-order invariance, assessment-change invariance, context/scope separation, cross-scope failure, attribution spoof attempts, round-trip determinism, A13 reconstruction, no status inflation and frozen D1 compatibility.

## Full regression gate

Full repository regression executed against implementation source `74d3df10f4ad43b554d7651823443caf00aec952`:

- `1420 passed`;
- `0 failed`;
- `0 errors`;
- `4 warnings`.

The four warnings are the existing scikit-learn Gaussian-process `ConvergenceWarning` messages from `tests/test_smoke.py`; they are not D3 failures.

## Acceptance criteria

| Criterion | Result |
|---|---|
| A1 - domain neutrality | PASS |
| A2 - frozen milestone protection | PASS |
| A3 - exact attribution | PASS |
| A4 - representable partial success | PASS |
| A5 - order invariance | PASS |
| A6 - bounded retention fails closed | PASS |
| A7 - assessment/physics separation | PASS |
| A8 - scope separation | PASS |
| A9 - no status inflation | PASS |
| A10 - deterministic round-trip | PASS |
| A11 - quantified retention evidence | PASS |
| A12 - regression safety | PASS |
| A13 - Layer B rederivability | PASS |

## Adversarial review

### P0/P1

No scientific correctness or evidence-corruption blockers were found.

### P2

Direct construction can bypass the normal Layer A attribution builder/verifier inside the same trusted process.

This is consistent with inherited Core internal/non-cryptographic identity limits. It is not a D3 freeze blocker unless future evidence demonstrates a D3-specific scientific corruption pathway.

### P3

Successor evidence recorded but not fixed in D3:

- inherited `O(N^2)` dominance scaling;
- durable storage substrate;
- stronger caller-owned partition-function provenance;
- generic Core identity/authenticity debt.

## Frozen milestone protection

D3 was added as an adjacent design-memory layer. Frozen D0/D1/D2, Scientific Twin, K-series, MVR0 and MVR1 source semantics were not modified for the D3 freeze.

The D3 preregistration remained unchanged during implementation and freeze.

## Explicitly not part of D3

The following belong to successor milestones, not D3:

- knowledge consolidation;
- compatibility;
- recombination;
- generation learning;
- persistence at scale;
- next-experiment intelligence;
- adaptive or memory-directed candidate generation;
- relative/statistical/quantile/rank tolerance;
- per-reason quotas;
- objective-aware retention tie-breaking;
- LLM interpretation;
- system-pack integration.

## Frozen boundary

D3 is **complete**.

D3 must not receive further polishing, hardening, persistence infrastructure, optimization or threat-model expansion as part of this milestone. Any future work belongs to a successor preregistered milestone.

## Frozen outcome

D3 is **PASS / FROZEN**.

The milestone demonstrates that domain-neutral scientific design memory can retain, attribute and re-serve partial scientific success as reproducible policy-derived classification over immutable attributable observations, while preserving exact D1 attribution, exact scope separation, bounded deterministic retention and the epistemic boundary between memory and scientific truth.
