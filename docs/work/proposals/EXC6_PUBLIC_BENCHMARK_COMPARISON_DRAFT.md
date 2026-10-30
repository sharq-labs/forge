---
ai_schema_version: 1
doc_id: FORGE-EXC6-PUBLIC-BENCHMARK-COMPARISON-DRAFT
doc_kind: SCIENTIFIC_DESIGN
doc_status: PROPOSED
authority_scope: NONE
source_ref: a9ddbf274cc5d24a8f14236586d8bd94a2760fcb
evidence_level: REPORTED
last_reviewed: 2026-10-30
supersedes: none
---

# DRAFT EXC-6: public equation-recovery benchmarks as a development comparison

**DRAFT for the owner's decision. NOT approved, NOT in `ACTIVE_PLAN.md`, authorizes no download or code.**

## Why

Genesis-lite worlds are built and scored in-house. A public benchmark gives an outside reference point at low build
cost. Candidates (from a 2026-10-30 web search; contents NOT inspected, licences UNVERIFIED):

| Benchmark | What it offers | Reported caveat |
|---|---|---|
| SRBench 2.0 (Aldeia et al., arXiv 2505.03977) | first-principles track with known formulas; symbolic-accuracy metric | dataset counts differ between summaries; check the paper |
| LLM-SRBench (Shojaee et al., ICML 2025) | 239 problems; transformed and synthetic laws designed against memorization | aimed at LLM methods; best reported symbolic accuracy about 31.5 % |
| ERBench (arXiv 2606.09276, June 2026) | newer equation-recovery benchmark | very new; maturity unknown |

## What it is and is not

- It **is** a DEVELOPMENT_DESCRIPTIVE comparison of existing arms on public data.
- It is **not** Blindfold, not a hidden-truth evaluation, not evidence of discovery, and not a formal lift result.
  Public formulas are known to everyone; leakage cannot be excluded.

## Proposed exception (eight fields)

1. **Exact scope:** an adapter `benchmarks/public_sr/` that turns one benchmark's first-principles problems into
   Genesis-lite-style presented cards (public units only, sampled rows, no formula), runs existing registered arms
   unchanged, and scores with the existing v0.3 scorer where the escrow grammar can express the formula (others marked
   NOT_EXPRESSIBLE, not failures). Tests for the adapter.
2. **Allowed work:** licence check and download of **one** chosen benchmark (filename, source and size stated to the
   owner first); a pinned copy outside the pinned files with its SHA-256; one development run.
3. **Reason:** an outside reference at low build cost; checks whether in-house worlds are unrepresentatively easy or
   hard.
4. **Start condition:** owner approval; owner picks the benchmark; licence recorded.
5. **Exit condition:** adapter tests; `forge-scientific-review` of the card conversion (no formula or answer leakage
   into cards); a descriptive report per arm.
6. **Expiry / timebox:** `OWNER_DECISION_REQUIRED`.
7. **Owner approval:** not given.
8. **Prohibited:** treating any result as validation, discovery or Blindfold evidence; changing arms, scorer, escrows or
   pinned files; tuning on the public results; downloading more than the approved benchmark.
