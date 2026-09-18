# Core intelligence layer — 2026-09-18

**Round:** CORE-1 … CORE-13, the generic claim → routing → plan → execution →
evidence → assurance → claim-verdict chain. The layer lives in `engcore.claims`.

**Delivery:** six stacked PRs.

| PR | contents |
|---|---|
| #51 A | the claim contract and capability registry |
| #52 B | the compiler, model selection and repair |
| #53 C | routes and planning |
| #54 D | the runtime, verdict, explanation and MCP tool |
| #55 E | uncertainty transport, context, sources and oracles |
| F | hardening, invariants, mutation checks and documentation |

**Base:** `origin/main` @ `3dbc8742`.

Design and use: [`docs/scientific-core/claims-layer.md`](../scientific-core/claims-layer.md).

## Historical findings, re-verified against current code

Status is as of the end of this round, with the evidence for each.

| ID | Before | After | Evidence |
|---|---|---|---|
| SDR-01 bridge from report to Evidence | CLOSED | CLOSED | reused by the claim runtime |
| SDR-02 context-blind belief key | CLOSED | CLOSED | — |
| SDR-03 ValidationLevel obligations | CLOSED | CLOSED | the claim runtime uses them, plus one obligation per required uncertainty channel |
| SDR-04 verification vs validation | CLOSED | CLOSED | `test_verification_cannot_satisfy_a_validation_requirement` |
| SDR-05 uncertainty closure | PARTIAL | **PARTIAL** | Transport from Core to SRIA to claim is now complete and tested end to end (`test_claims_uncertainty.py`). No production domain quantifies uncertainty yet, so on real systems every claim that requires quantified uncertainty is INSUFFICIENT_EVIDENCE. That result is honest, and it is tested |
| SDR-06 trusted external evidence | PARTIAL | **PARTIAL→improved** | NAFEMS T3 is now reachable by a claim, and trusted oracles can be discovered by QOI and context (`discover_oracles`). Still only one oracle |
| SDR-07 evidence ancestry | CLOSED | CLOSED | — |
| SDR-08 reference-posterior reproducibility | — | not re-run | SCIENTIFIC tier; unrelated to this round |
| SDR-09 claim fusion | PARTIAL by design | unchanged | still deliberately absent |
| SDR-10 generic claim boundary | PARTIAL | **CLOSED** | `assess_scientific_claim` (MCP 0.7.0) routes structured claims without the caller naming a system |
| N1 `main` red on the discrepancy test | OPEN | **CLOSED** | PR A, first commit |
| N2 the Arbiter never checks `context_ref` | OPEN | **CLOSED on the claim path / OPEN in the Arbiter** | `context_problems`. A test pins both halves. The Arbiter is certified and was left unchanged |
| N3 UNKNOWN discrepancy never blocks | OPEN | **CLOSED on the claim path** | A claim may require a supported discrepancy, and SRIA's `model_discrepancy_check` then judges it. `assess_claim` is unchanged |
| N4 `derive_verdict` crashes on NOT_APPLICABLE | OPEN | OPEN | separate task offered; not on any production path |
| N5 `ProblemPayloadError` not imported in `problem.py` | OPEN | OPEN | separate task offered |
| N6 only SIMULATION evidence exists | OPEN | **PARTIAL** | There is now one source adapter per `SourceClass`. Status comes from SRIA, and unimplemented sources return an explicit NOT_IMPLEMENTED. Ingestion is out of scope |
| N7 a quantified UNSPECIFIED record satisfies a channel obligation | PARTIAL | **CLOSED on the claim path** | The claim layer files only attributed records |
| N8 stale certificate; FAST tier does not deselect its self-check | OPEN | OPEN | process; needs a recertification round |
| N9 battery `cell_thermal_conductance` described as optional but required by the run | new | **handled** | The declaration marks it required. A test pins that the run refuses without it |
| N10 the battery boundary never assembles lumped applicability | new | **surfaced** | Battery claims are refused before execution with the reason. Fixing it is a domain change |

## Integrity invariants

`tests/claims/test_claims_invariants.py` maps each of the twelve invariants to at
least two tests that hold it, and fails if one of those tests is removed.
`tests/claims/test_claims_mutations.py` disables each load-bearing guard in turn
and requires the property it protects to fail. There are eleven guards, and all
of them were killed.

The first run of that harness found one surviving mutant. With the
required-input rule disabled, the property "a missing heat capacity is
NEEDS_INPUT" still held. The reason is that a lumped-model condition reads heat
capacity directly and blocks it independently. The property now uses an input
that no validity condition reads, so only the required-input rule can catch it.

## Tests

This round adds 353 collected tests in `tests/claims/`. The FAST tier
(`-m "not expensive" -n 4`) was run on every PR. Each run had **the same 10
failures as `origin/main`**, and no new ones. All ten are certification or
freeze drift that predates this round:

- the stale certificate (2);
- the V1, V3 and V4 freeze verifiers (6);
- the recertification-workflow pin (1);
- the batch38 hybrid-UQ read-back (1).

`main` itself had 11 failures; the 11th was N1, fixed in PR A.

## Core Freeze and certification

- **Frozen surface: nothing moved.** No canonical module's `__all__`, no frozen
  signature and no existing schema changed. The only existing-record change is
  one additive keyword on `evidence_from_credibility_report`, which is outside
  certified scope. Its default keeps the old behaviour.
- **Package classification.** `engcore.claims` is a new non-Core package. It is
  classified in the layering test and in the freeze policy, and listed in the
  certificate's `OUT_OF_SCOPE`.
- **Recertification.** Every PR changes `tests/**`, and PR D changes
  `mcp/server.py`, which is a mutation target. Each therefore needs the manual
  **Recertify Hardened Core** workflow. No certificate, manifest or pinned hash
  was regenerated in this round.
- **Proposed for a later certified round.** Two changes to certified SRIA code:
  - an Arbiter-level check of `context_ref` against the charter (N2 at the source);
  - bringing `engcore.claims.verdict` and `context` into a certified area.
