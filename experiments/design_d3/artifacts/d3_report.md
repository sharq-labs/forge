# D3 Design Memory Evidence

## E6 Counts

- cap: `250`
- classified_discarded_by_cap_count: `654`
- d1_pareto_count: `38`
- d1_scoped_elite_count: `12`
- eligible_population_count: `1000`
- per_reason_census: `{'PARETO_MEMBER': 38, 'SCOPED_ELITE': 12, 'NEAR_EXTREME': 21, 'NEAR_THRESHOLD': 893, 'DIVERSITY_REPRESENTATIVE': 36, 'EXPLICIT': 3}`
- retained_after_cap_count: `250`
- retained_not_d1_archived_count: `212`
- tier1_count: `38`
- unclassified_count: `96`
- with_at_least_one_reason_count: `904`

## A1-A13

- A1: PASS - D3 source has no concrete domain/system-pack imports
- A2: PASS - D3 added adjacent module/tests/experiment only
- A3: PASS - E5 attribution mismatch checks failed closed
- A4: PASS - E1 classified all six preregistered predicates
- A5: PASS - E2 serialized records matched across deterministic permutations
- A6: PASS - cap applied after classification; tier-1 overflow covered by targeted tests
- A7: PASS - E3 changed assessment without changing Layer A digests or scope identity
- A8: PASS - E4 cross-scope operations failed closed and scopes round-tripped
- A9: PASS - serialized D3 records carry retention facts without status labels
- A10: PASS - scope, Layer A, policy, and record round-tripped deterministically
- A11: PASS - E6 recorded exact 1000-candidate counts
- A12: PASS - tests/test_design_d3_memory.py passed; full repository regression passed
- A13: PASS - E6 reconstructed Layer B byte-identically from Layer A plus policy

## Adversarial Review

- P0/P1: none
- P2: Insertion-time attribution verification is explicit; callers that bypass DesignMemoryLayerA.build and verify_layer_a_attribution can manufacture in-process objects, matching inherited Core non-cryptographic identity limits.
- P3: D3 V0.1 uses O(N^2) dominance checks inherited from frozen D1 archive semantics.
- P3: Partition keys are stored as Layer A feature bytes; a successor may need stronger provenance for the caller-owned partition function.
- P3: Storage remains deterministic JSON artifacts; durable external storage is still successor architecture.
