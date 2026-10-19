# Deep Scientific Defect Audit — 2026-10-19 (pointer)

> **UNCERTIFIED developer audit of `abed661f` (PR #169's tree), not of this commit.** Evidence, hashes and full
> reports: [evidence/deep_audit_2026_10_19/](evidence/deep_audit_2026_10_19/README.md). Nothing here changes code, a
> contract, a certificate, a benchmark identity or the active epic. Every owner decision listed below is **open**.

## Findings

The audit found 26 defects (6 MAJOR, 20 MINOR) plus 8 observations, and labelled none BLOCKER. Five findings are
EXECUTED_REPRODUCED, by four owner-authorized runs; all others are static.

| ID | Area | Finding | Evidence | Severity |
|---|---|---|---|---|
| FDA-01 | Assembly replay / certification | `assembly/replay.py` compares only scalar magnitudes. Caller-supplied `external_uncertainty` is not bound, so REPLAYED_MATCH can attest UQ it never reproduced. | SOURCE_PROVEN | MAJOR |
| FDA-02 | System runtime | The committed state's time is not tied to the run's plan window, so a wrong state can be committed with valid receipts. | SOURCE_PROVEN (latent) | MAJOR |
| FDA-03 | Materials | Interpolation silently arbitrates two sources at one position; coverage hides the conflict. | EXECUTED_REPRODUCED (R-03) | MAJOR |
| FDA-04 | MCP UQ tool | Lattice "independent" inputs are exactly anti-correlated, giving a zero-width "completed" interval. | EXECUTED_REPRODUCED (R-04) | MAJOR |
| FDA-05 | Genesis-lite scoring | The INDISTINGUISHABLE bracket has no width bound. A vacuous pair scores +1.0 against two exclusive truths. | EXECUTED_REPRODUCED (R-05) | MAJOR |
| FDA-06 | Genesis-lite lift rule | Out-of-family credit is capped only for `discoverable`, not for `spurious_correlate` (or, statically, `confounded`). | EXECUTED_REPRODUCED (R-06, capping function) | MAJOR |
| FDA-14 | MCP UQ tool | A stated 0.95 interval holds 0.95 − 0.95/n of the mass. | EXECUTED_REPRODUCED (R-04) | MINOR |
| FDA-07..26 | Various | See the register. | Mostly SOURCE_PROVEN | MINOR |

The absence of a BLOCKER label does not lower closure priority.
- FDA-03, FDA-04 and FDA-05 each break a CLAUDE.md authority invariant.
- FDA-05 and FDA-06 must be closed before any Genesis-lite scoring freeze.

Known formal-measurement blockers (B-LEAK, the G0 items, O-1) are separate and unchanged.

## Where to read next

- `evidence/deep_audit_2026_10_19/package/FORGE_DEEP_SCIENTIFIC_DEFECT_AUDIT.md`: the full report.
- `evidence/deep_audit_2026_10_19/package/FORGE_NEW_FINDINGS_REGISTER.json`: every finding, all 20 fields.
- `evidence/deep_audit_2026_10_19/closure/SCIENTIFIC_FINDINGS_CLOSURE_PLAN.md`: proposed repairs and the shortest closure path.
- `evidence/deep_audit_2026_10_19/closure/SCIENTIFIC_FINDINGS_OWNER_DECISIONS.md`: open decisions ODC-*.
- `evidence/deep_audit_2026_10_19/closure/GENESIS_BLINDFOLD_BLOCKER_MATRIX.md`: per-step dependencies.
