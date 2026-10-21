# battery_rediscovery_v1 (BR-BATT-REDISC-02): clean confirmation run

Branch `research/battery-rediscovery-pilot-v0` (worktree `D:/forge-redisc`). Local only. This is a development
experiment: not formal, not certified, not a discovery claim. Commits:
- `53e6a6db`: pre-run freeze (PLAN.json `3b7e6676…`);
- `c0613435`: sealed outputs;
- the evaluation commit that follows them.

## v0, preserved as history (`V0_HISTORY.json`)

| Reading | Result |
|---|---|
| PREREGISTERED_RESULT | LEAKAGE_INVALIDATED |
| POST_SEAL_AMENDMENT_RESULT | REPRESENTATION_BOTTLENECK (exploratory only) |
| CONFIRMED_RESULT | NONE |

No v0 file was modified. V0_HISTORY.json binds every v0 artifact by sha256: plan, candidate code and pack, outputs and
traces, seal, both leakage audits, replay, the preregistered evaluation, AMENDMENT_01, scoring and baselines.

## Design

- **Hypotheses.** H1: the Mind underperforms CAREFUL_BASELINE primarily because of its representation. H0: the gap
  survives once representation is controlled. Neither is preregistered as true.
- **Arms.**
  - The candidate side is copied **byte-exact** from v0: the Mind arm (reported as MIND_V0_REPRESENTATION), the
    baselines and the pack. It is checked against v0's PLAN digests.
  - No hypothesis type, experiment selection, belief update or refusal logic was changed.
- **Leakage scanner v1** (`leakage.py`):
  - A numeric scanner reads complete tokens and compares them by value. It handles signs, exponents, integer/decimal
    equivalence and SI-prefixed units; a long transcription matches at its own precision.
  - A separate text scanner covers identities and verdict tokens.
  - A pack-key whitelist.
  - Raw measurement arrays are protected by **provenance** (the pack must rebuild byte-identically from the pinned
    splits), not by numeric scanning. A 12.5 s timestamp equals a 12.5 mV historical RMSE at 3 digits, so a numeric
    scan of raw data cannot be made safe.
  - Runtime path/module audit of the run and the replay.
- **Mutation test** (`mutation.py`).
  - It plants leaks into real candidate material as an integer, a decimal equivalent, a signed form, scientific
    notation, value+unit, an SI-prefixed unit, a prose label, a result label, a full-precision transcription, text
    tokens, and altered measurement arrays.
  - Pre-run: **420/420 caught, 0/219 benign controls triggered.** The benign controls include 760.006, 1760, 76001
    and a760b.
  - Post-seal, with the values re-derived from the historical records: **460/460 caught, 0/243 benign triggered.**
  - The suite found one real gap before the run: "8.4 mV" was missed for a protected 8.40 mV. That was fixed pre-run.
- **Representability instrument** (`evaluator/representability.py`). The reachable answer set of every
  (problem, axis) was frozen in PLAN.json before the run. It was computed from a capability table and the pack's
  structure only. After the seal, the historical answer is classified against that set, never against what the Mind
  answered.
- **Conclusion rule and thresholds** (`evaluator/conclusion.py`) are frozen in PLAN.json. There is no amendment
  mechanism: a post-seal defect would invalidate v1 and require v2.

## Result: REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY

| Axis | Mind | Careful baseline | Representability | Result |
|---|---:|---:|---|---|
| MODEL_ADEQUACY | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | NOT_SUPPORTED; NOT_SUPPORTED | NOT_REPR; NOT_REPR | FALSE_REFUSE; FALSE_REFUSE |
| IDENTIFIABILITY | P1 REFUSED; P2 REVIEW | SUPPORTED; SUPPORTED | NOT_REPR; APPROX | FALSE_REFUSE; FALSE_REFUSE |
| WITHIN_CELL | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | NOT_ASSESSABLE; NOT_SUPPORTED | APPROX; APPROX | CORRECT_REFUSAL; FALSE_REFUSE |
| CROSS_CELL | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | NOT_SUPPORTED; NOT_ASSESSABLE | APPROX; EXACT | FALSE_REFUSE; CORRECT_REFUSAL |
| MODEL_DISCREPANCY | P1 NOT_ASSESSABLE; P2 NOT_ASSESSABLE | NOT_SUPPORTED; NOT_SUPPORTED | NOT_REPR; NOT_REPR | FALSE_REFUSE; FALSE_REFUSE |
| CORRECT_REFUSAL | 2 | 2 | APPROX 1, EXACT 1 | |
| FALSE_SUPPORT | 0 | 1 | — | |
| FALSE_REFUSE | 8 | 0 | APPROX 3, NOT_REPR 5 | |

| Coverage | Count | Mind correct | Mind incorrect/refused |
|---|---:|---:|---:|
| REPRESENTABLE_EXACTLY | 1 | 1 | 0 |
| REPRESENTABLE_APPROXIMATELY | 4 | 1 | 3 |
| NOT_REPRESENTABLE | 5 | 0 | 5 |
| UNKNOWN | 0 | 0 | 0 |

The preregistered primary analysis:
- **Most failures are NOT_REPRESENTABLE: met.** Of the 8 Mind failures, 5 are NOT_REPRESENTABLE (share 0.625, above
  the 0.5 threshold).
- **Materially better where representable: met.** The Mind scores 0.40 on representable instances and 0.00 on the rest
  (a gap of at least 0.25).
- **Not poor where representable: failed.** On the representable instances the Mind scores 0.40 against CAREFUL's
  1.00, which is below half of CAREFUL.
- So the rule gives **REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY**, because at least 0.25 of the failures are
  NOT_REPRESENTABLE.
- The single exactly-representable instance (P2 cross-cell, with no set supplied) the Mind gets right.
- The three approximately-representable failures are where the Mind's proxy paths were open but it did not reach the
  correct answer:
  - P2 identifiability: its relaxation law came out linear, so it answered REVIEW where history found the parameters
    identifiable;
  - P1 cross-cell and P2 within-cell: no law was issued, because the protocol-set levels were read as passive
    associations, so it could not reach NOT_SUPPORTED.

**Totals** (CORRECT + CORRECT_REFUSAL): CAREFUL 9, FIXED_FIT 4, MIND 2, ALWAYS_REFUSE 2, ALWAYS_FIT 1.

**Leakage:**
- pre-run mutation suite: PASS;
- pre-seal audit: PASS;
- post-seal mutation suite: PASS;
- post-seal audit: PASS;
- the pre-run protected values equal those re-derived from the historical records.

**Replay:** 12/12 outputs re-execute byte-identically, and 5/5 traces are VERIFIED.

**v0 replication:** 12/12 sealed outputs are byte-identical to v0's.

## Read this before citing the result

- v1 is **not an independent replication**. The data, splits and deterministic candidate code are v0's, and the outputs
  are byte-identical to v0's. v1 adds a clean, unamended firewall and a preregistered representability analysis; it
  adds no new evidence about the data.
- The developer was **not blind**. v0's per-instance answers and the historical truth were known when the capability
  table, the reachable-set rules and the thresholds were written. The thresholds follow the brief's own wording
  (majority, materially, half), and the outcome was predictable before the freeze.
- REPRESENTABLE_APPROXIMATELY pools proxy paths of different fidelity, and the exact-only subset holds one instance.
