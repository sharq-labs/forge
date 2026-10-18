# FORGE Scientific Risk Matrix — 2026-10-19

This is a static audit of `abed661f`. Impact and confidence are scored separately.

- **Impact** is the worst credible scientific consequence if the path is reached: Critical, High, Medium, Low.
- **Confidence** is how well the defect is established:
  - **H**: SOURCE_PROVEN, and it survived independent disproval.
  - **M**: SOURCE_PROVEN by one reviewer plus the lead, but not cross-reviewed.
  - **L**: static suspicion.
- **Reach** is whether a production path triggers it today:
  - **Live**: a production path reaches it.
  - **Latent**: only tests or future callers reach it.
  - **Gate**: it affects a decision rule or benchmark identity.

Addendum 2026-10-19: the owner-authorized R-03..R-06 runs raise confidence to **X (EXECUTED_REPRODUCED)** for
FDA-03, FDA-04, FDA-05, FDA-06 and FDA-14. FDA-06's run covers the capping function only. Every other row is still
static.

## Matrix

| ID | Impact | Confidence | Reach | Severity | Invariant at risk | Blocks |
|---|---|---|---|---|---|---|
| FDA-01 | High | H | Live (certification replay of authorized multiphysics runs) | MAJOR | Evidence bound to its context; missing UQ never improves | Certification attestation of UQ/validation; Real Engineering Demo replay claims |
| FDA-02 | High | H | Latent (one production committer today) | MAJOR | Wrong admitted numerical state | System-runtime multi-stage claims; Real Engineering Demo |
| FDA-03 | High | H | Latent (no production InterpolationRule producer) | MAJOR | Sources never arbitrated | Material-property-driven PDE claims |
| FDA-05 | High (benchmark) | H (magnitude from simulation) | Gate | MAJOR | UNKNOWN never improves an answer | Step-1 scoring freeze, Step-2, Graduation |
| FDA-06 | High (benchmark) | H | Gate | MAJOR | No lift without an applicable baseline (§10.5) | Step-1 freeze (OD-19), Step-2, Graduation |
| FDA-04 | Medium | H | Live (MCP tool) | MAJOR | Missing uncertainty never becomes zero | MCP probabilistic UQ product output |
| FDA-09 | Medium | M | Live (claims replay API) | MINOR | Reproducibility ≠ support | Consumers of ReplayResult |
| FDA-12 | Medium | H | Live (DC validation), mitigated by FAIL→NOT_SUPPORTED | MINOR | Datum-invariant tolerance | DC numerical-convergence level |
| FDA-14 | Medium | H | Live (MCP tool) | MINOR | Stated mass equals realised mass | MCP UQ |
| FDA-18 | Medium (High while FDA-05 is open) | H (channel) / L (size) | Gate | MINOR | Benchmark independence | Step-2 / Graduation design |
| FDA-19 | Medium | H | Gate (B-LEAK lift) | MINOR | No isolation claim without demonstration | B-LEAK lift, Graduation |
| FDA-07 | Low | H | Live (offline verify) | MINOR | Tampering detection | — |
| FDA-08 | Low (availability) | H | Latent | MINOR | — (fails closed) | Grounded-record replay |
| FDA-10 | Low | H | Latent | MINOR | Verification ≠ physical conservation | — |
| FDA-11 | Low | H | Latent | MINOR | Provenance completeness | — |
| FDA-13 | Low | H | Latent | MINOR | Applicability precedes evidence | — |
| FDA-15 | Low | H | Latent (benchmarks only) | MINOR | Search adequacy behind "no second mode" | Frozen V3 review |
| FDA-16 | Low | H | Latent | MINOR | Holdout survival is not evidence | Mind Step-2 if adopted |
| FDA-17 | Low | H | Latent | MINOR | Extrapolation accounting | — |
| FDA-20..22 | Low–Medium | M–H | Gate | MINOR | Benchmark validity | v0.3 |
| FDA-23..26 | Low | M | Latent | MINOR | Assorted | — |
| OBS-01..08 | Low | — | — | OBSERVATION | — | — |

## Known open risks carried alongside (not new)

| Known | Impact | Status |
|---|---|---|
| B-LEAK | Critical (benchmark isolation) | OPEN_CONFIRMED; blocks all formal measurement |
| D4 archive readback | Medium (compatibility; fail-closed) | OPEN_CONFIRMED; UNCLASSIFIED |
| OD-29 FastSystem inner provenance | High if reached | OPEN_STATIC_SUSPICION |
| B2c / B2d flagship scenario and provider refs | Medium | OPEN_STATIC_SUSPICION |
| A2b tampered coupling plan not re-validated | Medium | OPEN_STATIC_SUSPICION |
| O-1 bootstrap "p" in Holm | High (FWER claim) | OPEN_STATIC_SUSPICION |
| Stale certificate, dark CI, no branch protection | High (governance) | OPEN_CONFIRMED |

## Heat summary

- **Highest combined risk to scientific truth:** FDA-01, then FDA-02, then FDA-03. All three are in the authority core, all are certified, and all can be fixed in one OD-3 batch.
- **Highest risk to the Blindfold goal:** the known B-LEAK, then FDA-05, then FDA-06. All are pre-freeze and land in v0.3.
- **Highest risk to product users today:** FDA-04 and FDA-14, in the live MCP tool. They are uncertified, so the fix is the cheapest of the set.
